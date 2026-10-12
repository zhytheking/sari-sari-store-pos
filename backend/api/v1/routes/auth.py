"""
Authentication routes.

Auth transport: HTTP-only cookies.
    - Login sets access_token + refresh_token cookies.
    - Refresh reads the refresh_token cookie.
    - Logout clears both cookies.

Lockout policy:
    - 5 failed login attempts → 5-minute lockout.
    - The lockout check, password verification, and attempt
      recording all happen inside ONE transaction.

Session invalidation on password change:
    - change_password and reset_user_password set
      users.password_changed_at = CURRENT_TIMESTAMP.

Audit:
    - Login (success/failure/lockout), logout, register, password
      changes all write to audit_logs.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
    set_access_cookies,
    set_refresh_cookies,
    unset_jwt_cookies,
)
from marshmallow import ValidationError
import bcrypt
from datetime import datetime, timedelta

from database.connection import get_db, transaction
from api.v1.schemas.user import (
    LoginSchema,
    RegisterSchema,
    ChangePasswordSchema,
    UserResponseSchema,
    UserUpdateSchema,
    ResetPasswordSchema,
)
from utils.validators import (
    validate_input, validate_password_strength, validate_username,
)
from utils.decorators import (
    role_required, audit_log, rate_limit, token_required,
)
from utils.responses import (
    success_response,
    created_response,
    bad_request,
    unauthorized,
    forbidden,
    not_found,
    conflict,
    validation_error,
    server_error,
)
from utils.logger import get_logger

auth_bp = Blueprint('auth', __name__)
logger = get_logger(__name__)

LOCKOUT_LIMIT = 5
LOCKOUT_MINUTES = 5


# ════════════════════════════════════════════════════════════
# DUMMY HASH (constant-time login failure path)
# ════════════════════════════════════════════════════════════

_DUMMY_HASH_CACHE = None


def _get_dummy_hash():
    global _DUMMY_HASH_CACHE
    if _DUMMY_HASH_CACHE is None:
        _DUMMY_HASH_CACHE = bcrypt.hashpw(b'dummy', bcrypt.gensalt())
    return _DUMMY_HASH_CACHE


def _record_audit(**kwargs):
    """Wrapper that never raises."""
    try:
        from backend.api.v1.routes.audit import record_audit
        record_audit(**kwargs)
    except Exception as e:
        logger.warning(f"Audit write failed: {e}")


# ════════════════════════════════════════════════════════════
# LOCKOUT HELPERS
# ════════════════════════════════════════════════════════════

def _parse_sqlite_timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace(' ', 'T'))
    except Exception:
        return None


def _get_lockout_state(cursor, username):
    cursor.execute(
        """SELECT attempt_count, locked_until, last_attempt_at
           FROM login_attempts
           WHERE username = ?""",
        (username,)
    )
    row = cursor.fetchone()
    if not row:
        return {'attempt_count': 0, 'locked_until': None}
    return {
        'attempt_count': row['attempt_count'] or 0,
        'locked_until': _parse_sqlite_timestamp(row['locked_until']),
    }


def _check_lockout_and_clear_if_expired(cursor, username):
    state = _get_lockout_state(cursor, username)
    locked_until = state['locked_until']

    if not locked_until:
        return False, 0

    now = datetime.now()
    if now >= locked_until:
        cursor.execute(
            """UPDATE login_attempts
               SET attempt_count = 0,
                   locked_until = NULL,
                   updated_at = CURRENT_TIMESTAMP
               WHERE username = ?""",
            (username,)
        )
        return False, 0

    remaining = locked_until - now
    minutes = int(remaining.total_seconds() / 60) + 1
    return True, minutes


def _record_failed_attempt(cursor, username):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    state = _get_lockout_state(cursor, username)
    new_count = state['attempt_count'] + 1

    if new_count >= LOCKOUT_LIMIT:
        locked_until = datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)
        locked_until_str = locked_until.strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute(
            """INSERT INTO login_attempts
               (username, attempt_count, last_attempt_at,
                locked_until, updated_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(username) DO UPDATE SET
                 attempt_count = excluded.attempt_count,
                 last_attempt_at = excluded.last_attempt_at,
                 locked_until = excluded.locked_until,
                 updated_at = CURRENT_TIMESTAMP""",
            (username, new_count, now_str, locked_until_str)
        )
        return new_count, True

    cursor.execute(
        """INSERT INTO login_attempts
           (username, attempt_count, last_attempt_at, updated_at)
           VALUES (?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(username) DO UPDATE SET
             attempt_count = excluded.attempt_count,
             last_attempt_at = excluded.last_attempt_at,
             updated_at = CURRENT_TIMESTAMP""",
        (username, new_count, now_str)
    )
    return new_count, False


def _reset_failed_attempts(cursor, username):
    cursor.execute(
        "DELETE FROM login_attempts WHERE username = ?",
        (username,)
    )


# ════════════════════════════════════════════════════════════
# LOGIN
# ════════════════════════════════════════════════════════════

@auth_bp.route('/login', methods=['POST'])
@rate_limit(limit=10, per='minute')
@validate_input(LoginSchema)
def login():
    try:
        data = request.validated_data
        username = data['username']
        password = data['password']
        requested_role = data.get('role', 'owner')

        user = None
        password_ok = False
        lockout_response = None
        auth_failed_response = None
        failed_count = 0

        with transaction() as db:
            cursor = db.cursor()

            is_locked, minutes_left = _check_lockout_and_clear_if_expired(
                cursor, username
            )

            if is_locked:
                lockout_response = (jsonify({
                    'success': False,
                    'error': 'account_locked',
                    'message': (
                        f"Too many failed login attempts. "
                        f"Try again in {minutes_left} minute(s)."
                    ),
                    'remaining_minutes': minutes_left,
                }), 403)

                _record_audit(
                    action='LOGIN',
                    category='auth',
                    user_id=None,
                    details=f"Login blocked for '{username}' — locked ({minutes_left} min left)",
                    result='failure',
                    metadata={'username': username, 'reason': 'lockout_pre_check'},
                    ip_address=request.remote_addr,
                )

            else:
                cursor.execute(
                    """SELECT id, username, password_hash, full_name,
                              email, role, is_active
                       FROM users WHERE username = ?""",
                    (username,)
                )
                user = cursor.fetchone()

                if user:
                    password_ok = bcrypt.checkpw(
                        password.encode('utf-8'),
                        user['password_hash'].encode('utf-8')
                    )
                else:
                    bcrypt.checkpw(
                        password.encode('utf-8'),
                        _get_dummy_hash()
                    )
                    password_ok = False

                if not user or not password_ok:
                    new_count, locked_now = _record_failed_attempt(
                        cursor, username
                    )
                    failed_count = new_count

                    if locked_now:
                        lockout_response = (jsonify({
                            'success': False,
                            'error': 'account_locked',
                            'message': (
                                f"Too many failed login attempts. "
                                f"Account locked for "
                                f"{LOCKOUT_MINUTES} minutes."
                            ),
                            'remaining_minutes': LOCKOUT_MINUTES,
                        }), 403)

                        logger.warning(
                            f"Account '{username}' locked after "
                            f"{new_count} failed attempts"
                        )

                        _record_audit(
                            action='LOGIN',
                            category='auth',
                            user_id=user['id'] if user else None,
                            details=f"Account locked for '{username}' after {new_count} failed attempts",
                            result='failure',
                            metadata={
                                'username': username,
                                'attempts': new_count,
                                'reason': 'lockout_triggered',
                            },
                            ip_address=request.remote_addr,
                        )
                    else:
                        auth_failed_response = (jsonify({
                            'success': False,
                            'error': 'authentication_failed',
                            'message': 'Invalid username or password',
                            'attempts_remaining': (
                                LOCKOUT_LIMIT - new_count
                            ),
                        }), 401)

                        logger.warning(
                            f"Failed login for '{username}' "
                            f"(attempt {new_count}/{LOCKOUT_LIMIT})"
                        )

                        _record_audit(
                            action='LOGIN',
                            category='auth',
                            user_id=user['id'] if user else None,
                            details=f"Failed login for '{username}' (attempt {new_count}/{LOCKOUT_LIMIT})",
                            result='failure',
                            metadata={
                                'username': username,
                                'attempts': new_count,
                                'reason': 'bad_password',
                            },
                            ip_address=request.remote_addr,
                        )

        if lockout_response is not None:
            return lockout_response

        if auth_failed_response is not None:
            return auth_failed_response

        # ── Post-verification checks ──
        if not user['is_active']:
            _record_audit(
                action='LOGIN',
                category='auth',
                user_id=user['id'],
                details=f"Login refused for '{username}' — account inactive",
                result='failure',
                metadata={'username': username, 'reason': 'inactive'},
                ip_address=request.remote_addr,
            )
            return unauthorized(
                'Account is inactive. Please contact the administrator.',
                code='account_inactive',
            )

        user_role = user['role']

        if user_role == 'cashier' and requested_role != 'cashier':
            _record_audit(
                action='LOGIN',
                category='auth',
                user_id=user['id'],
                details=f"Login refused for '{username}' — role mismatch (selected {requested_role}, actual {user_role})",
                result='failure',
                metadata={
                    'username': username,
                    'reason': 'role_mismatch',
                    'requested_role': requested_role,
                    'actual_role': user_role,
                },
                ip_address=request.remote_addr,
            )
            return forbidden(
                "You are registered as a cashier. "
                "Please select the 'Cashier' role to log in.",
                code='role_mismatch',
            )

        # ── Reset attempts + update last_login ──
        with transaction() as db:
            cursor = db.cursor()
            _reset_failed_attempts(cursor, username)
            cursor.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (user['id'],)
            )

        # ── Issue tokens ──
        access_token = create_access_token(
            identity=str(user['id']),
            additional_claims={
                'role': user_role,
                'username': user['username'],
                'full_name': user['full_name'],
            }
        )
        refresh_token = create_refresh_token(identity=str(user['id']))

        _record_audit(
            action='LOGIN',
            category='auth',
            user_id=user['id'],
            details=f"User '{username}' logged in as {user_role}",
            result='success',
            metadata={'username': username, 'role': user_role},
            ip_address=request.remote_addr,
        )

        logger.info(f"User '{username}' logged in as {user_role}")

        response = jsonify({
            'success': True,
            'message': f'Login successful as {user_role}',
            'data': {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'user': {
                    'id': user['id'],
                    'username': user['username'],
                    'full_name': user['full_name'],
                    'email': user['email'],
                    'role': user_role,
                    'is_active': bool(user['is_active']),
                }
            }
        })

        set_access_cookies(response, access_token)
        set_refresh_cookies(response, refresh_token)

        return response, 200

    except ValidationError as e:
        return validation_error(details=e.messages)
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        return server_error(str(e), code='login_failed')


# ════════════════════════════════════════════════════════════
# REGISTER (OWNER ONLY)
# ════════════════════════════════════════════════════════════

@auth_bp.route('/register', methods=['POST'])
@jwt_required()
@role_required(['owner'])
@rate_limit(limit=20, per='minute')
@validate_input(RegisterSchema)
def register():
    try:
        data = request.validated_data
        admin_id = get_jwt_identity()

        try:
            validate_password_strength(data['password'])
        except ValueError as e:
            return validation_error(message=str(e))

        password_hash = bcrypt.hashpw(
            data['password'].encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

        user_id = None
        admin_username = 'Unknown'

        with transaction() as db:
            cursor = db.cursor()

            cursor.execute(
                "SELECT username FROM users WHERE id = ?", (admin_id,)
            )
            admin_row = cursor.fetchone()
            if admin_row:
                admin_username = admin_row['username']

            cursor.execute(
                "SELECT id FROM users WHERE username = ?",
                (data['username'],)
            )
            if cursor.fetchone():
                raise ValueError("Username already exists")

            if data.get('email'):
                cursor.execute(
                    "SELECT id FROM users WHERE email = ?",
                    (data['email'],)
                )
                if cursor.fetchone():
                    raise ValueError("Email already exists")

            cursor.execute(
                """INSERT INTO users
                   (username, password_hash, full_name, email,
                    role, is_active)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    data['username'],
                    password_hash,
                    data['full_name'],
                    data.get('email'),
                    data.get('role', 'cashier'),
                    1,
                )
            )
            user_id = cursor.lastrowid

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """SELECT id, username, full_name, email, role, is_active,
                      created_at
               FROM users WHERE id = ?""",
            (user_id,)
        )
        new_user = dict(cursor.fetchone())

        _record_audit(
            action='USER_CREATE',
            category='user',
            user_id=admin_id,
            details=f"Created user '{data['username']}' ({new_user['role']})",
            target_type='user',
            target_id=user_id,
            result='success',
            metadata={
                'username': data['username'],
                'role': new_user['role'],
                'created_by': admin_username,
            },
            ip_address=request.remote_addr,
        )

        logger.info(
            f"New user registered: {data['username']} as "
            f"{new_user['role']} by admin {admin_username}"
        )

        return created_response(
            data={
                'id': new_user['id'],
                'username': new_user['username'],
                'full_name': new_user['full_name'],
                'email': new_user['email'],
                'role': new_user['role'],
                'is_active': bool(new_user['is_active']),
                'created_at': new_user['created_at'],
            },
            message='User created successfully',
        )

    except ValidationError as e:
        return validation_error(details=e.messages)
    except ValueError as e:
        msg = str(e)
        if 'Username' in msg:
            return conflict(msg, code='user_exists')
        if 'Email' in msg:
            return conflict(msg, code='email_exists')
        return validation_error(message=msg)
    except Exception as e:
        logger.error(f"Registration error: {e}", exc_info=True)
        return server_error(str(e), code='registration_failed')


# ════════════════════════════════════════════════════════════
# REFRESH
# ════════════════════════════════════════════════════════════

@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    try:
        user_id = get_jwt_identity()
        db = get_db()
        cursor = db.cursor()

        cursor.execute(
            """SELECT id, role, username, full_name, is_active,
                      password_changed_at
               FROM users WHERE id = ?""",
            (user_id,)
        )
        user = cursor.fetchone()

        if not user or not user['is_active']:
            return unauthorized(
                'User not found or inactive',
                code='user_not_found',
            )

        from flask_jwt_extended import get_jwt as _get_jwt
        claims = _get_jwt()
        from utils.decorators import (
            _token_is_stale, _parse_sqlite_timestamp,
        )
        if _token_is_stale(claims, _parse_sqlite_timestamp(
                user['password_changed_at'])):
            return unauthorized(
                'Session expired after a password change. '
                'Please sign in again.',
                code='token_stale',
            )

        access_token = create_access_token(
            identity=str(user['id']),
            additional_claims={
                'role': user['role'],
                'username': user['username'],
                'full_name': user['full_name'],
            }
        )

        logger.info(f"Token refreshed for user {user['username']}")

        response = jsonify({
            'success': True,
            'data': {'access_token': access_token}
        })
        set_access_cookies(response, access_token)
        return response, 200

    except Exception as e:
        logger.error(f"Refresh error: {e}", exc_info=True)
        return server_error(str(e), code='refresh_failed')


# ════════════════════════════════════════════════════════════
# LOGOUT
# ════════════════════════════════════════════════════════════

@auth_bp.route('/logout', methods=['POST'])
@jwt_required(optional=True)
def logout():
    try:
        user_id = get_jwt_identity()
        username = user_id

        if user_id:
            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                "SELECT username FROM users WHERE id = ?", (user_id,)
            )
            row = cursor.fetchone()
            if row:
                username = row['username']

        _record_audit(
            action='LOGOUT',
            category='auth',
            user_id=user_id,
            details=f"User '{username}' logged out",
            result='success',
            metadata={'username': username},
            ip_address=request.remote_addr,
        )

        logger.info(f"User '{username}' logged out")

        response = jsonify({
            'success': True,
            'message': 'Logout successful',
        })
        unset_jwt_cookies(response)
        return response, 200

    except Exception as e:
        logger.error(f"Logout error: {e}", exc_info=True)
        response = jsonify({
            'success': True,
            'message': 'Logout completed',
        })
        unset_jwt_cookies(response)
        return response, 200


# ════════════════════════════════════════════════════════════
# CURRENT USER
# ════════════════════════════════════════════════════════════

@auth_bp.route('/me', methods=['GET'])
@token_required
def get_current_user():
    try:
        user_id = get_jwt_identity()
        db = get_db()
        cursor = db.cursor()

        cursor.execute(
            """SELECT id, username, full_name, email, role, is_active,
                      last_login, created_at
               FROM users WHERE id = ?""",
            (user_id,)
        )
        user = cursor.fetchone()

        if not user:
            return not_found('User not found', code='user_not_found')

        return success_response(data={
            'id': user['id'],
            'username': user['username'],
            'full_name': user['full_name'],
            'email': user['email'],
            'role': user['role'],
            'is_active': bool(user['is_active']),
            'last_login': user['last_login'],
            'created_at': user['created_at'],
        })

    except Exception as e:
        logger.error(f"Get user error: {e}", exc_info=True)
        return server_error(str(e), code='get_user_failed')


# ════════════════════════════════════════════════════════════
# CHANGE OWN PASSWORD
# ════════════════════════════════════════════════════════════

@auth_bp.route('/change-password', methods=['POST'])
@token_required
@validate_input(ChangePasswordSchema)
def change_password():
    try:
        user_id = get_jwt_identity()
        data = request.validated_data

        db = get_db()
        cursor = db.cursor()

        cursor.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        )
        row = cursor.fetchone()

        if not row:
            return not_found('User not found', code='user_not_found')

        if not bcrypt.checkpw(
            data['old_password'].encode('utf-8'),
            row['password_hash'].encode('utf-8')
        ):
            return unauthorized(
                'Old password is incorrect',
                code='password_change_failed',
            )

        try:
            validate_password_strength(data['new_password'])
        except ValueError as e:
            return validation_error(message=str(e))

        new_hash = bcrypt.hashpw(
            data['new_password'].encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

        with transaction() as tdb:
            tcursor = tdb.cursor()
            tcursor.execute(
                """UPDATE users
                   SET password_hash = ?,
                       password_changed_at = CURRENT_TIMESTAMP,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (new_hash, user_id)
            )

        _record_audit(
            action='PASSWORD_CHANGE_SELF',
            category='auth',
            user_id=user_id,
            details="User changed their own password",
            target_type='user',
            target_id=user_id,
            result='success',
            ip_address=request.remote_addr,
        )

        logger.info(f"Password changed for user {user_id} (self)")

        return success_response(message='Password changed successfully')

    except ValidationError as e:
        return validation_error(details=e.messages)
    except ValueError as e:
        return validation_error(message=str(e))
    except Exception as e:
        logger.error(f"Password change error: {e}", exc_info=True)
        return server_error(str(e), code='password_change_failed')


# ════════════════════════════════════════════════════════════
# USERS LIST (OWNER ONLY)
# ════════════════════════════════════════════════════════════

@auth_bp.route('/users', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def list_users():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        role = request.args.get('role')
        search = request.args.get('search')

        db = get_db()
        cursor = db.cursor()

        conditions = []
        params = []

        if role:
            conditions.append("role = ?")
            params.append(role)

        if search:
            conditions.append(
                "(username LIKE ? OR full_name LIKE ? OR email LIKE ?)"
            )
            s = f"%{search}%"
            params.extend([s, s, s])

        where_clause = (
            "WHERE " + " AND ".join(conditions)) if conditions else ""

        query = f"""SELECT id, username, full_name, email, role,
                           is_active, last_login, created_at
                    FROM users
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?"""

        cursor.execute(
            query, params + [per_page, (page - 1) * per_page])
        rows = cursor.fetchall()

        count_query = f"SELECT COUNT(*) FROM users {where_clause}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        return success_response(data={
            'items': [
                {
                    'id': r['id'],
                    'username': r['username'],
                    'full_name': r['full_name'],
                    'email': r['email'],
                    'role': r['role'],
                    'is_active': bool(r['is_active']),
                    'last_login': r['last_login'],
                    'created_at': r['created_at'],
                }
                for r in rows
            ],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
            }
        })

    except Exception as e:
        logger.error(f"List users error: {e}", exc_info=True)
        return server_error(str(e), code='list_users_failed')


@auth_bp.route('/users/<int:user_id>', methods=['GET'])
@jwt_required()
@role_required(['owner'])
def get_user(user_id):
    try:
        db = get_db()
        cursor = db.cursor()

        cursor.execute(
            """SELECT id, username, full_name, email, role, is_active,
                      last_login, created_at, updated_at
               FROM users WHERE id = ?""",
            (user_id,)
        )
        user = cursor.fetchone()

        if not user:
            return not_found('User not found', code='user_not_found')

        return success_response(data={
            'id': user['id'],
            'username': user['username'],
            'full_name': user['full_name'],
            'email': user['email'],
            'role': user['role'],
            'is_active': bool(user['is_active']),
            'last_login': user['last_login'],
            'created_at': user['created_at'],
            'updated_at': user['updated_at'],
        })

    except Exception as e:
        logger.error(f"Get user error: {e}", exc_info=True)
        return server_error(str(e), code='get_user_failed')


@auth_bp.route('/users/<int:user_id>', methods=['PUT'])
@jwt_required()
@role_required(['owner'])
def update_user(user_id):
    try:
        current_user_id = get_jwt_identity()

        if str(user_id) == str(current_user_id):
            return bad_request(
                'Use /change-password to update your own account',
                code='cannot_update_self',
            )

        data = request.get_json() or {}

        with transaction() as db:
            cursor = db.cursor()

            cursor.execute(
                "SELECT id FROM users WHERE id = ?", (user_id,))
            if not cursor.fetchone():
                raise ValueError("User not found")

            updates = []
            params = []
            allowed = ['email', 'full_name', 'is_active', 'role']

            for field in allowed:
                if field in data and data[field] is not None:
                    if field == 'is_active':
                        updates.append("is_active = ?")
                        params.append(1 if data[field] else 0)
                    else:
                        updates.append(f"{field} = ?")
                        params.append(data[field])

            if not updates:
                raise ValueError("No fields to update")

            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(user_id)

            cursor.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                params
            )

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """SELECT id, username, full_name, email, role, is_active,
                      created_at, updated_at
               FROM users WHERE id = ?""",
            (user_id,)
        )
        user = cursor.fetchone()

        _record_audit(
            action='USER_UPDATE',
            category='user',
            user_id=current_user_id,
            details=f"Updated user '{user['username']}' (fields: {', '.join(data.keys())})",
            target_type='user',
            target_id=user_id,
            result='success',
            metadata={'fields': list(data.keys())},
            ip_address=request.remote_addr,
        )

        logger.info(
            f"User {user['username']} updated by admin {current_user_id}"
        )

        return success_response(
            data={
                'id': user['id'],
                'username': user['username'],
                'full_name': user['full_name'],
                'email': user['email'],
                'role': user['role'],
                'is_active': bool(user['is_active']),
                'created_at': user['created_at'],
                'updated_at': user['updated_at'],
            },
            message='User updated successfully',
        )

    except ValueError as e:
        msg = str(e)
        if 'not found' in msg.lower():
            return not_found(msg, code='user_not_found')
        if 'no fields' in msg.lower():
            return bad_request(msg, code='no_updates')
        return bad_request(msg)
    except Exception as e:
        logger.error(f"Update user error: {e}", exc_info=True)
        return server_error(str(e), code='update_user_failed')


@auth_bp.route('/users/<int:user_id>', methods=['DELETE'])
@jwt_required()
@role_required(['owner'])
def delete_user(user_id):
    try:
        current_user_id = get_jwt_identity()

        if str(user_id) == str(current_user_id):
            return bad_request(
                'You cannot delete your own account',
                code='cannot_delete_self',
            )

        username = None

        with transaction() as db:
            cursor = db.cursor()

            cursor.execute(
                "SELECT username FROM users WHERE id = ?", (user_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("User not found")

            username = row['username']

            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))

        _record_audit(
            action='USER_DELETE',
            category='user',
            user_id=current_user_id,
            details=f"Deleted user '{username}'",
            target_type='user',
            target_id=user_id,
            result='success',
            metadata={'username': username},
            ip_address=request.remote_addr,
        )

        logger.info(
            f"User '{username}' deleted by admin {current_user_id}"
        )

        return success_response(message='User deleted successfully')

    except ValueError as e:
        return not_found(str(e), code='user_not_found')
    except Exception as e:
        logger.error(f"Delete user error: {e}", exc_info=True)
        return server_error(str(e), code='delete_user_failed')


@auth_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@jwt_required()
@role_required(['owner'])
def reset_user_password(user_id):
    try:
        data = request.get_json() or {}
        new_password = data.get('new_password', 'Password123')

        try:
            validate_password_strength(new_password)
        except ValueError as e:
            return validation_error(message=str(e))

        username = None

        with transaction() as db:
            cursor = db.cursor()

            cursor.execute(
                "SELECT username FROM users WHERE id = ?", (user_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("User not found")

            username = row['username']

            new_hash = bcrypt.hashpw(
                new_password.encode('utf-8'),
                bcrypt.gensalt()
            ).decode('utf-8')

            cursor.execute(
                """UPDATE users
                   SET password_hash = ?,
                       password_changed_at = CURRENT_TIMESTAMP,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (new_hash, user_id)
            )

        _record_audit(
            action='PASSWORD_RESET',
            category='user',
            user_id=get_jwt_identity(),
            details=f"Admin reset password for '{username}'",
            target_type='user',
            target_id=user_id,
            result='success',
            metadata={'username': username},
            ip_address=request.remote_addr,
        )

        logger.info(f"Password reset for user '{username}' by admin")

        return success_response(
            message=(f"Password reset successfully. "
                     f"New password: {new_password}")
        )

    except ValueError as e:
        return not_found(str(e), code='user_not_found')
    except Exception as e:
        logger.error(f"Reset password error: {e}", exc_info=True)
        return server_error(str(e), code='reset_password_failed')

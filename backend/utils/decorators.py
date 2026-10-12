from functools import wraps
from flask import request, current_app
from flask_jwt_extended import (
    verify_jwt_in_request,
    get_jwt,
    get_jwt_identity,
)
from flask_jwt_extended.exceptions import (
    NoAuthorizationError,
    JWTExtendedException,
)
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidTokenError,
    DecodeError,
)

from database.connection import get_db
from utils.logger import get_logger
from utils.responses import (
    forbidden, server_error, rate_limited, unauthorized,
)

import os
import re
import time
from datetime import datetime, timezone

logger = get_logger(__name__)


# Auth-specific exceptions. Anything else propagates as a real bug.
_AUTH_EXCEPTIONS = (
    NoAuthorizationError,
    JWTExtendedException,
    ExpiredSignatureError,
    InvalidTokenError,
    DecodeError,
)


# ════════
# HELPERS
# ════════

_UA_SAFE_RE = re.compile(r'[^\w\s\-\./,:;()\[\]@=]')
_UA_MAX_LEN = 200


def _sanitize_user_agent(raw: str) -> str:
    #Strip dangerous chars from User-Agent; truncate to 200
    if not raw:
        return 'Unknown'
    s = re.sub(r'\s+', ' ', str(raw)).strip()
    s = _UA_SAFE_RE.sub('', s)
    if len(s) > _UA_MAX_LEN:
        s = s[:_UA_MAX_LEN] + '…'
    return s or 'Unknown'


def _parse_sqlite_timestamp(value):

    if not value:
        return None
    try:
        s = str(value).replace(' ', 'T')
        # SQLite timestamps are UTC but have no 'Z'. Add it.
        if not s.endswith('Z') and '+' not in s and '-' not in s[10:]:
            s += 'Z'
        dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _fetch_user_auth_state(user_id):

    if user_id is None:
        return {'exists': False}

    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """SELECT id, is_active, role, password_changed_at
               FROM users WHERE id = ?""",
            (user_id,)
        )
        row = cursor.fetchone()
        if not row:
            return {'exists': False}

        return {
            'exists': True,
            'is_active': bool(row['is_active']),
            'role': row['role'],
            'password_changed_at': _parse_sqlite_timestamp(
                row['password_changed_at']
            ),
        }
    except Exception as e:
        logger.error(f"_fetch_user_auth_state failed: {e}", exc_info=True)
        return {'exists': False}


def _token_is_stale(claims, password_changed_at):
    if password_changed_at is None:
        # User has never changed their password. Old tokens are OK.
        return False

    iat = claims.get('iat')
    if iat is None:
        # No iat claim — very old or malformed token. Reject it.
        return True

    try:
        issued_at = datetime.fromtimestamp(int(iat), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return True
    return issued_at <= password_changed_at


# ═══════════
# AUDIT LOG
# ═══════════
def audit_log(action):
    """
    Decorator that records a 'request entered' marker in the audit log.

    Delegates to `record_audit()` in the audit routes module, which
    uses its OWN connection (not the request-scoped one). This
    guarantees the audit write cannot accidentally commit a parent
    transaction.

    NOTE: Routes that use this decorator AND call `record_audit()`
    directly will produce two rows per action. The decorator logs
    "the request happened", the route logs "what actually resulted".
    To remove double rows, delete this decorator from a route and
    rely solely on `record_audit()`.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                user_id = None
                try:
                    verify_jwt_in_request(optional=True)
                    user_id = get_jwt_identity()
                except Exception:
                    pass

                ip_address = request.remote_addr or '0.0.0.0'
                user_agent = _sanitize_user_agent(
                    request.headers.get('User-Agent')
                )

                try:
                    from backend.api.v1.routes.audit import record_audit
                    record_audit(
                        action=action,
                        category='system',
                        user_id=user_id,
                        details=(
                            f"{request.method} {request.path} "
                            f"[{user_agent}]"
                        ),
                        result='success',
                        ip_address=ip_address,
                    )
                except Exception as e:
                    logger.warning(f"Failed to log audit: {e}")

                return f(*args, **kwargs)
            except Exception as e:
                logger.error(f"Audit decorator error: {e}", exc_info=True)
                return f(*args, **kwargs)

        return decorated_function
    return decorator


# ═══════════════
# ROLE REQUIRED
# ═══════════════
def role_required(roles):

    if isinstance(roles, str):
        roles = [roles]

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                verify_jwt_in_request()
            except _AUTH_EXCEPTIONS as e:
                logger.warning(f"Auth check failed: {e}")
                return unauthorized('Authentication required.')

            claims = get_jwt()
            user_id = get_jwt_identity()

            state = _fetch_user_auth_state(user_id)
            if not state.get('exists'):
                return unauthorized(
                    'Account no longer exists.',
                    code='account_missing',
                )
            if not state.get('is_active'):
                return unauthorized(
                    'Account is inactive.',
                    code='account_inactive',
                )
            if _token_is_stale(claims, state.get('password_changed_at')):
                return unauthorized(
                    'Session expired after a password change. '
                    'Please sign in again.',
                    code='token_stale',
                )

            user_role = state.get('role')
            if user_role not in roles:
                logger.warning(
                    f"Access denied for role {user_role}. Required: {roles}"
                )
                return forbidden(f'Required role: {", ".join(roles)}')

            return f(*args, **kwargs)

        return decorated_function

    return decorator


# ═══════════════
# TOKEN REQUIRED
# ═══════════════
def token_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            verify_jwt_in_request()
        except _AUTH_EXCEPTIONS as e:
            logger.warning(f"Token validation failed: {e}")
            return unauthorized('Authentication required.')

        claims = get_jwt()
        user_id = get_jwt_identity()

        state = _fetch_user_auth_state(user_id)
        if not state.get('exists'):
            return unauthorized(
                'Account no longer exists.',
                code='account_missing',
            )
        if not state.get('is_active'):
            return unauthorized(
                'Account is inactive.',
                code='account_inactive',
            )
        if _token_is_stale(claims, state.get('password_changed_at')):
            return unauthorized(
                'Session expired after a password change. '
                'Please sign in again.',
                code='token_stale',
            )

        return f(*args, **kwargs)

    return decorated_function


# ═══════════════════════════
# ADMIN / CASHIER SHORTCUTS
# ═══════════════════════════
def admin_required(f):
    """Require owner role."""
    return role_required(['owner'])(f)


def cashier_required(f):
    """Require cashier or owner role."""
    return role_required(['owner', 'cashier'])(f)


# ═════════════
# LOG REQUEST
# ═════════════
def log_request(f):
    #Log incoming requests at INFO level
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            logger.info(f"Request: {request.method} {request.path}")
        except Exception:
            pass
        return f(*args, **kwargs)

    return decorated_function


# ═══════════════════
# HANDLE EXCEPTIONS
# ═══════════════════
def handle_exceptions(f):

    #Catch ValueError and generic Exception, return a standard shape.

    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"Validation error: {e}")
            from utils.responses import bad_request
            return bad_request(str(e), code='validation_error')
        except Exception as e:
            logger.error(f"Unhandled exception in {f.__name__}: {e}",
                         exc_info=True)
            return server_error()

    return decorated_function


# ════════════
# RATE LIMIT
# ════════════

_RATE_LIMIT_STORE = {}

_TIME_WINDOW_SECONDS = {
    'second': 1,
    'minute': 60,
    'hour': 3600,
    'day': 86400,
}


def _rate_limiting_disabled() -> bool:
    """
    Return True only if rate limiting is explicitly disabled.

    Priority:
      1. Flask config RATELIMIT_ENABLED (the intended control).
      2. Falls back to True (rate limiting enabled) if config
         is unavailable.

    NOTE: `APP_ENV=testing` no longer disables rate limiting by
    itself. Tests set `RATELIMIT_ENABLED=False` via Flask config
    or `os.environ` explicitly.
    """
    try:
        if current_app and not current_app.config.get("RATELIMIT_ENABLED", True):
            return True
    except Exception:
        pass
    return False


def reset_rate_limits():
    #Clear all counters. Useful in tests
    _RATE_LIMIT_STORE.clear()


def rate_limit(limit: int, per: str = 'minute'):
    #Simple in-memory rate limiter keyed by client IP + endpoint
    window = _TIME_WINDOW_SECONDS.get(per, 60)

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if _rate_limiting_disabled():
                return f(*args, **kwargs)

            client_ip = request.remote_addr or '0.0.0.0'
            key = f"{client_ip}:{f.__name__}"
            now = time.time()

            recent = [
                t for t in _RATE_LIMIT_STORE.get(key, [])
                if now - t < window
            ]

            if len(recent) >= limit:
                return rate_limited(
                    f'Rate limit exceeded. Maximum {limit} requests '
                    f'per {per}.'
                )

            recent.append(now)
            _RATE_LIMIT_STORE[key] = recent
            return f(*args, **kwargs)

        return decorated_function

    return decorator

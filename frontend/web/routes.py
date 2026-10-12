"""
Web routes for the frontend application.

Auth model: HTTP-only cookies only.
    - Login  → POST /api/v1/auth/login  (sets access_token cookie)
    - Verify → GET  /api/auth/whoami    (reads cookie, returns user JSON)
    - Logout → POST /api/auth/logout    (clears both cookies)
"""
import sys
from pathlib import Path
from functools import wraps

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    jsonify,
    current_app,
    send_from_directory,
)
from flask_jwt_extended import decode_token, unset_jwt_cookies

from . import web_bp


COOKIE_NAME = 'access_token'
VALID_ROLES = ('owner', 'cashier')


# ════════════════════════════════════════════════════════════
# COOKIE HELPERS
# ════════════════════════════════════════════════════════════

def _clear_auth_cookie(response):
    response.set_cookie(
        COOKIE_NAME,
        '',
        expires=0,
        httponly=True,
        samesite='Lax',
        secure=current_app.config.get('JWT_COOKIE_SECURE', False),
        path='/',
    )
    return response


@web_bp.after_request
def add_no_cache_headers(response):
    protected = (
        request.path.startswith('/admin')
        or request.path.startswith('/cashier')
        or request.path == '/login'
    )
    if protected:
        response.headers['Cache-Control'] = (
            'no-store, no-cache, must-revalidate, max-age=0'
        )
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


# ════════════════════════════════════════════════════════════
# AUTH — READ USER FROM COOKIE
# ════════════════════════════════════════════════════════════

def _read_user_from_cookie():
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None

    try:
        decoded = decode_token(token)
    except Exception as e:
        current_app.logger.warning(
            f"[AUTH] Token decode failed for {request.path}: {e}"
        )
        return None

    role = decoded.get('role')
    if role not in VALID_ROLES:
        current_app.logger.warning(
            f"[AUTH] Invalid role in token: {role!r} for {request.path}"
        )
        return None

    return {
        'id':        decoded.get('sub'),
        'username':  decoded.get('username'),
        'role':      role,
        'full_name': decoded.get('full_name'),
    }


# ════════════════════════════════════════════════════════════
# DECORATORS
# ════════════════════════════════════════════════════════════

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = _read_user_from_cookie()
        if user is None:
            resp = redirect(url_for('web.login_page'))
            return _clear_auth_cookie(resp)
        request.current_user = user
        return f(*args, **kwargs)
    return decorated


def role_required(*allowed_roles):
    allowed = set(allowed_roles)

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = _read_user_from_cookie()

            if user is None:
                resp = redirect(url_for('web.login_page'))
                return _clear_auth_cookie(resp)

            if user['role'] not in allowed:
                current_app.logger.warning(
                    f"[AUTH] Role mismatch: {user['role']!r} "
                    f"not in {allowed} for {request.path}"
                )
                return render_template('errors/403.html'), 403

            request.current_user = user
            return f(*args, **kwargs)
        return decorated
    return decorator


# ════════════════════════════════════════════════════════════
# PUBLIC ROUTES
# ════════════════════════════════════════════════════════════

@web_bp.route('/')
def index():
    return render_template('index.html')


@web_bp.route('/products')
def products_page():
    return render_template('products/list.html')


@web_bp.route('/product/<int:product_id>')
def product_detail(product_id):
    return render_template('products/detail.html', product_id=product_id)


@web_bp.route('/login')
def login_page():
    user = _read_user_from_cookie()
    if user:
        if user['role'] == 'owner':
            return redirect(url_for('web.admin_dashboard'))
        return redirect(url_for('web.cashier_dashboard'))
    return render_template('login.html')


@web_bp.route('/logout')
def logout_page():
    resp = redirect(url_for('web.index'))
    return _clear_auth_cookie(resp)


# ════════════════════════════════════════════════════════════
# OWNER ROUTES
# ════════════════════════════════════════════════════════════

@web_bp.route('/admin/dashboard')
@role_required('owner')
def admin_dashboard():
    return render_template('dashboard/admin.html')


@web_bp.route('/admin/stocks')
@role_required('owner')
def admin_stocks():
    return render_template('admin/stocks.html')


@web_bp.route('/admin/categories')
@role_required('owner')
def admin_categories():
    return render_template('admin/categories.html')


@web_bp.route('/admin/settings')
@role_required('owner')
def admin_settings():
    return render_template('admin/settings.html')


@web_bp.route('/admin/all-sales')
@role_required('owner')
def admin_all_sales():
    return render_template('dashboard/all-sales.html')


@web_bp.route('/admin/reports')
@role_required('owner')
def admin_reports():
    return render_template('dashboard/reports.html')


@web_bp.route('/admin/audit-log')
@role_required('owner')
def admin_audit_log():
    return render_template('dashboard/audit.html')


# ════════════════════════════════════════════════════════════
# CASHIER ROUTES
# ════════════════════════════════════════════════════════════

@web_bp.route('/cashier/dashboard')
@role_required('cashier', 'owner')
def cashier_dashboard():
    return render_template('dashboard/cashier.html')


@web_bp.route('/cashier/sales')
@role_required('cashier', 'owner')
def cashier_sales():
    return render_template('dashboard/cashier_sales.html')


# ════════════════════════════════════════════════════════════
# SHARED ROUTES
# ════════════════════════════════════════════════════════════

@web_bp.route('/admin/pos')
@role_required('owner', 'cashier')
def admin_pos():
    return render_template('dashboard/pos.html')


# ════════════════════════════════════════════════════════════
# AUTH API — whoami / logout / clear-cookie
# ════════════════════════════════════════════════════════════

@web_bp.route('/api/auth/whoami', methods=['GET'])
def whoami():
    user = _read_user_from_cookie()
    if user is None:
        return jsonify({'authenticated': False}), 401
    return jsonify({'authenticated': True, 'user': user}), 200


@web_bp.route('/api/auth/clear-cookie', methods=['POST'])
def clear_auth_cookie():
    resp = jsonify({'success': True, 'message': 'Cookie cleared'})
    return _clear_auth_cookie(resp)


@web_bp.route('/api/auth/logout', methods=['POST'])
def api_logout():
    resp = jsonify({'success': True, 'message': 'Logged out'})
    unset_jwt_cookies(resp)
    return resp


# ════════════════════════════════════════════════════════════
# STATIC FILES
# ════════════════════════════════════════════════════════════

def _resolve_static_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'frontend' / 'web' / 'static'
    return Path(__file__).resolve().parent / 'static'


@web_bp.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(str(_resolve_static_dir()), filename)


# ════════════════════════════════════════════════════════════
# ERROR HANDLERS
# ════════════════════════════════════════════════════════════

@web_bp.app_errorhandler(404)
def page_not_found(error):
    if request.path.startswith('/api/'):
        return jsonify({
            'error': 'not_found',
            'message': 'The requested resource was not found.',
        }), 404
    return render_template('errors/404.html'), 404


@web_bp.app_errorhandler(403)
def forbidden(error):
    if request.path.startswith('/api/'):
        return jsonify({
            'error': 'forbidden',
            'message': 'You do not have permission for this action.',
        }), 403
    return render_template('errors/403.html'), 403


@web_bp.app_errorhandler(500)
def internal_server_error(error):
    if request.path.startswith('/api/'):
        return jsonify({
            'error': 'internal_server_error',
            'message': 'An unexpected error occurred.',
        }), 500
    return render_template('errors/500.html'), 500

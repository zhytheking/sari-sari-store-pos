"""
Application factory for Saliga Sari-Sari Store POS.
"""
import sys
import os
from pathlib import Path

from flask import Flask, jsonify, g, request, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_bcrypt import Bcrypt

from backend.config import config
from backend.database.connection import (
    get_db, init_db, close_db, DatabaseConnection,
)
from backend.api.v1.routes import (
    auth_bp, products_bp, sales_bp, inventory_bp,
    reports_bp, admin_bp, settings_bp, audit_bp,
)
from backend.utils.logger import setup_logger
from backend.utils.error_handler import register_error_handlers


def _detect_lan_ip():
    import socket as _s
    try:
        s = _s.socket(_s.AF_INET, _s.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return None


def _build_cors_origins(config_object):
    origins = set()
    for o in (config_object.CORS_ORIGINS or []):
        o = (o or '').strip()
        if o and o != '*':
            origins.add(o)
    port = config_object.PORT
    origins.add(f'http://127.0.0.1:{port}')
    origins.add(f'http://localhost:{port}')
    lan_ip = _detect_lan_ip()
    if lan_ip:
        origins.add(f'http://{lan_ip}:{port}')
    return sorted(origins)


def _runtime_upload_root():
    """
    Where uploaded files live at runtime.

    Frozen:  %LOCALAPPDATA%/SariSariPOS/uploads
    Source:  <project>/frontend/web/static/assets
    """
    if getattr(sys, 'frozen', False):
        local = os.getenv("LOCALAPPDATA")
        if local:
            return Path(local) / "SariSariPOS" / "uploads"
        return Path.home() / "AppData" / "Local" / "SariSariPOS" / "uploads"
    return Path(__file__).resolve().parent.parent / "frontend" / "web" / "static" / "assets"


def create_app(config_object=None):
    if config_object is None:
        config_object = config

    if getattr(sys, 'frozen', False):
        bundle_dir = Path(sys._MEIPASS)
        template_dir = bundle_dir / "frontend" / "web" / "templates"
        static_dir = bundle_dir / "frontend" / "web" / "static"
    else:
        base_dir = Path(__file__).resolve().parent.parent
        template_dir = base_dir / "frontend" / "web" / "templates"
        static_dir = base_dir / "frontend" / "web" / "static"

    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir),
    )
    app.config.from_object(config_object)
    app.config['SECRET_KEY'] = config_object.SECRET_KEY
    app.config['JWT_SECRET_KEY'] = config_object.JWT_SECRET_KEY
    app.config['DB_PATH'] = config_object.DB_PATH

    app.config['JWT_TOKEN_LOCATION'] = ['headers', 'cookies']
    use_https = os.getenv('USE_HTTPS', 'false').strip().lower() == 'true'
    app.config['JWT_COOKIE_SECURE'] = use_https
    app.config['JWT_COOKIE_CSRF_PROTECT'] = True
    app.config['JWT_ACCESS_COOKIE_NAME'] = 'access_token'
    app.config['JWT_REFRESH_COOKIE_NAME'] = 'refresh_token'
    app.config['JWT_COOKIE_SAMESITE'] = 'Lax'
    app.config['JWT_ACCESS_COOKIE_PATH'] = '/'
    app.config['JWT_REFRESH_COOKIE_PATH'] = '/'

    cors_origins = _build_cors_origins(config_object)
    CORS(
        app,
        origins=cors_origins,
        supports_credentials=True,
        allow_headers=['Content-Type', 'Authorization', 'X-CSRF-TOKEN'],
        expose_headers=['Content-Type'],
        methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    )

    JWTManager(app)
    Bcrypt(app)

    setup_logger(app)
    app.logger.info(f"[CORS] Allowed origins: {cors_origins}")

    register_error_handlers(app)

    # ════════════════════════════════════════════════════════════
    # API BLUEPRINTS
    # ════════════════════════════════════════════════════════════

    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(products_bp, url_prefix='/api/v1/products')
    app.register_blueprint(sales_bp, url_prefix='/api/v1/sales')
    app.register_blueprint(inventory_bp, url_prefix='/api/v1/inventory')
    app.register_blueprint(reports_bp, url_prefix='/api/v1/reports')
    app.register_blueprint(admin_bp, url_prefix='/api/v1/admin')
    app.register_blueprint(settings_bp, url_prefix='/api/v1/settings')
    app.register_blueprint(audit_bp, url_prefix='/api/v1/audit')

    # ════════════════════════════════════════════════════════════
    # WEB BLUEPRINT
    # ════════════════════════════════════════════════════════════
    try:
        from frontend.web.routes import web_bp
        app.register_blueprint(web_bp)
        app.logger.info("[app] web_bp registered")
    except Exception as e:
        app.logger.error(f"[app] FAILED to register web_bp: {e}",
                         exc_info=True)
        raise

    # ════════════════════════════════════════════════════════════
    # SERVE RUNTIME UPLOADS
    # ════════════════════════════════════════════════════════════
    #
    # In frozen mode, uploaded files live in %LOCALAPPDATA%.
    # This route serves them at /static/assets/* so the browser
    # can display the QR code and product images.
    #
    # In source mode, this route is a no-op passthrough because
    # the files are already inside the Flask static folder.

    @app.route('/static/assets/<path:filename>')
    def serve_runtime_upload(filename):
        safe = str(filename).replace('\\', '/')
        if '..' in safe.split('/'):
            return jsonify({'error': 'invalid_path'}), 400
        base = _runtime_upload_root()
        return send_from_directory(str(base), safe)

    @app.teardown_appcontext
    def teardown_db(exception):
        db = g.pop('db', None)
        if db is not None:
            DatabaseConnection.return_connection(db)

    @app.route('/health', methods=['GET'])
    def health_check():
        try:
            db = get_db()
            db.execute('SELECT 1')
            return jsonify({
                'status': 'healthy',
                'app': config_object.APP_NAME,
                'environment': config_object.APP_ENV,
                'database': 'connected',
            }), 200
        except Exception as e:
            app.logger.error(f"Health check failed: {e}")
            return jsonify({
                'status': 'unhealthy',
                'database': 'disconnected',
                'error': 'Database connection failed',
            }), 500

    @app.route('/api', methods=['GET'])
    def api_root():
        return jsonify({
            'app': config_object.APP_NAME,
            'version': '1.0.0',
            'status': 'running',
            'endpoints': {
                'auth': '/api/v1/auth',
                'products': '/api/v1/products',
                'sales': '/api/v1/sales',
                'inventory': '/api/v1/inventory',
                'reports': '/api/v1/reports',
                'admin': '/api/v1/admin',
                'settings': '/api/v1/settings',
                'audit': '/api/v1/audit',
            },
        }), 200

    with app.app_context():
        try:
            from backend.database.migrations import migration_manager
            migration_result = migration_manager.migrate()
            applied = migration_result.get('applied', [])
            errors = migration_result.get('errors', [])

            if applied:
                app.logger.info(f"[migrations] Applied: {applied}")
            if errors:
                app.logger.error(f"[migrations] Errors: {errors}")
                raise RuntimeError(
                    f"Migrations failed: {errors}. "
                    f"App cannot start with a broken schema."
                )
        except ImportError as e:
            app.logger.warning(f"Migrations not available: {e}")

        try:
            init_db()
        except Exception as e:
            app.logger.warning(f"Seed failed: {e}")

    return app


app = create_app()


if __name__ == '__main__':
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
    )

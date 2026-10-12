"""
API v1 route blueprints.
"""
from .auth import auth_bp
from .products import products_bp
from .sales import sales_bp
from .inventory import inventory_bp
from .reports import reports_bp
from .admin import admin_bp
from .settings import settings_bp
from .audit import audit_bp

__all__ = [
    'auth_bp',
    'products_bp',
    'sales_bp',
    'inventory_bp',
    'reports_bp',
    'admin_bp',
    'settings_bp',
    'audit_bp',
]

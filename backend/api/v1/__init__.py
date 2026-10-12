"""API v1 package."""
from .routes import (
    auth_bp,
    products_bp,
    sales_bp,
    inventory_bp,
    reports_bp,
    admin_bp,
    settings_bp,
)

__all__ = [
    'auth_bp',
    'products_bp',
    'sales_bp',
    'inventory_bp',
    'reports_bp',
    'admin_bp',
    'settings_bp',
]

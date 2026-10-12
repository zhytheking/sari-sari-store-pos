
__all__ = ['LoginWindow', 'MainWindow', 'POSWindow', 'AdminWindow', 'AuditWindow']


def __getattr__(name):
    if name == 'LoginWindow':
        from .login_window import LoginWindow
        return LoginWindow
    if name == 'MainWindow':
        from .main_window import MainWindow
        return MainWindow
    if name == 'POSWindow':
        from .pos_window import POSWindow
        return POSWindow
    if name == 'AdminWindow':
        from .admin_window import AdminWindow
        return AdminWindow
    if name == 'AuditWindow':
        from .audit_window import AuditWindow
        return AuditWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

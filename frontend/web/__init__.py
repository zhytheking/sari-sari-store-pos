"""
Web frontend package.

Resolves template and static folders in BOTH:
  - Source mode  (running from a .py file)
  - Frozen mode  (running inside a PyInstaller .exe)
"""
import sys
from pathlib import Path

from flask import Blueprint


def _resolve_web_root() -> Path:
    """Return the absolute path to frontend/web/ in both modes."""
    if getattr(sys, 'frozen', False):
        # PyInstaller extracts bundled files into sys._MEIPASS
        return Path(sys._MEIPASS) / 'frontend' / 'web'

    # Source mode: __file__ is .../frontend/web/__init__.py
    return Path(__file__).resolve().parent


_WEB_ROOT = _resolve_web_root()
_TEMPLATES = _WEB_ROOT / 'templates'
_STATIC = _WEB_ROOT / 'static'

# Sanity check — fail loudly at import time, not at first request
if not _TEMPLATES.is_dir():
    raise RuntimeError(
        f"[web_bp] Templates folder not found: {_TEMPLATES}\n"
        f"  frozen={getattr(sys, 'frozen', False)}\n"
        f"  _MEIPASS={getattr(sys, '_MEIPASS', 'N/A')}"
    )
if not _STATIC.is_dir():
    raise RuntimeError(
        f"[web_bp] Static folder not found: {_STATIC}"
    )


web_bp = Blueprint(
    'web',
    __name__,
    template_folder=str(_TEMPLATES),
    static_folder=str(_STATIC),
    static_url_path='/static',
)

# Routes must be imported AFTER the blueprint is created
from . import routes  # noqa: E402,F401

__all__ = ['web_bp', 'routes']

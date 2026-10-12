"""
Bootstrap module that makes `backend.X` imports work in both
source and frozen (PyInstaller) modes.
"""
import sys
import types
from pathlib import Path


# The top-level packages that live inside `backend/` in source mode.
_BACKEND_SUBPACKAGES = (
    "app",
    "config",
    "api",
    "core",
    "database",
    "utils",
)

# The top-level packages that live inside `frontend/` in source mode.
_FRONTEND_SUBPACKAGES = (
    "web",
    "gui",
)


def _register_virtual_package(parent_name: str, children) -> None:
    if parent_name in sys.modules:
        # Already real — nothing to do.
        return

    # Create an empty module to stand in for the package.
    parent = types.ModuleType(parent_name)
    parent.__path__ = []  # mark it as a package
    parent.__package__ = parent_name

    # Ensure any children that are already imported get attached.
    for child in children:
        full_child_name = f"{parent_name}.{child}"
        if child in sys.modules:
            child_module = sys.modules[child]
            setattr(parent, child, child_module)
            sys.modules[full_child_name] = child_module

    sys.modules[parent_name] = parent


def _find_frozen_root() -> Path:
    """Where PyInstaller extracted the bundle."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def install() -> None:
    """
    Idempotent installer. Call this from run.py at startup.
    Safe to call multiple times.
    """
    frozen = getattr(sys, "frozen", False)
    if not frozen:
        # Source mode: `backend/` and `frontend/` are real packages.
        # Nothing to do.
        return

    root = _find_frozen_root()

    # Ensure the bundle root is on sys.path so top-level imports
    # of `database`, `config`, etc. resolve.
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    # Register `backend` as a virtual package.
    _register_virtual_package("backend", _BACKEND_SUBPACKAGES)

    # Register `frontend` as a virtual package, if the frontend
    # modules are present.
    has_frontend = any(
        (root / child).exists() or child in sys.modules
        for child in _FRONTEND_SUBPACKAGES
    )
    if has_frontend:
        _register_virtual_package("frontend", _FRONTEND_SUBPACKAGES)


#Run on import so a bare `import _boot` in run.py is enough.
install()

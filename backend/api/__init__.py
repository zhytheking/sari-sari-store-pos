import sys
from pathlib import Path

# Ensure backend/ is on sys.path so we can import `_boot`.
_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

try:
    import _boot  # noqa: F401
except ImportError:
    pass

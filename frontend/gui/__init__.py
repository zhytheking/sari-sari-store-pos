import sys
from pathlib import Path

import tkinter


# ═══════════
# PATH SETUP
# ═══════════

def _setup_paths():
    #Add project root, backend, and frontend to sys.path
    if getattr(sys, 'frozen', False):
        project_root = Path(sys.executable).resolve().parent
    else:
        project_root = Path(__file__).resolve().parent.parent.parent

    paths_to_add = [
        str(project_root),
        str(project_root / 'backend'),
        str(project_root / 'frontend'),
    ]
    for p in paths_to_add:
        if p not in sys.path:
            sys.path.insert(0, p)


_setup_paths()
del _setup_paths


# ════════════════════════════════════════════════
# Tkinter teardown-bug workaround (Python 3.12+)
# ════════════════════════════════════════════════
# Only `deletecommand` needs patching. See the changelog above.

_orig_tk_deletecommand = tkinter.Tk.deletecommand
_orig_misc_deletecommand = tkinter.Misc.deletecommand


def _safe_deletecommand(self, name):
    try:
        return _orig_tk_deletecommand(self, name)
    except Exception:
        return None


def _safe_misc_deletecommand(self, name):
    try:
        return _orig_misc_deletecommand(self, name)
    except Exception:
        return None


tkinter.Tk.deletecommand = _safe_deletecommand
tkinter.Misc.deletecommand = _safe_misc_deletecommand


__all__ = []

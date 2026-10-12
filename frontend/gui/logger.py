#Logging for the GUI.

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _log_directory() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent / "logs"
    else:
        return Path(__file__).resolve().parents[2] / "logs"


_configured = False


def _configure_root_logger():
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger("gui")
    root.setLevel(logging.INFO)
    root.propagate = False

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    try:
        if sys.stdout is not None and sys.stdout.isatty():
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(logging.INFO)
            ch.setFormatter(formatter)
            root.addHandler(ch)
    except Exception:
        pass

    try:
        log_dir = _log_directory()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "gui.log"

        fh = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3,
            encoding='utf-8',
        )
        fh.setLevel(logging.INFO)
        fh.setFormatter(formatter)
        root.addHandler(fh)
    except Exception:
        pass


_configure_root_logger()


def get_logger(name: str = None) -> logging.Logger:
    if name:
        if not name.startswith('gui.'):
            name = f"gui.{name}"
        return logging.getLogger(name)
    return logging.getLogger("gui")

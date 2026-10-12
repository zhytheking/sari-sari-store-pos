"""
GUI runtime configuration.

All GUI windows must import get_api_url() from here. Never hardcode
"http://127.0.0.1:5000/api/v1" anywhere else in the GUI.
"""
import os
import sys
from pathlib import Path


def _project_root() -> Path:
    
    if getattr(sys, 'frozen', False):
       return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def get_api_url() -> str:
    """
    API base URL for the GUI.

    Precedence:
      1. POS_API_URL env var
      2. http://127.0.0.1:5000/api/v1

    Never returns a trailing slash.
    Normalizes localhost → 127.0.0.1 (Windows IPv6 resolution is slow).
    """
    raw = os.getenv("POS_API_URL", "http://127.0.0.1:5000/api/v1")
    return raw.rstrip("/").replace("localhost", "127.0.0.1")


def get_server_host() -> str:
    from urllib.parse import urlparse
    url = get_api_url()
    parsed = urlparse(url)
    return parsed.hostname or "127.0.0.1"


def get_server_port() -> int:
    from urllib.parse import urlparse
    url = get_api_url()
    parsed = urlparse(url)
    return parsed.port or 5000


def is_server_mode() -> bool:
    host = os.getenv("HOST", "127.0.0.1").strip()
    if host == "0.0.0.0":
        return True

    api = get_api_url()
    return "127.0.0.1" in api or "localhost" in api


def get_env_file_path() -> Path:
    return _project_root() / ".env"

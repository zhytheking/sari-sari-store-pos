
#Cnfiguration loader for Saliga Sari-Sari Store POS.

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


# ═══════════════
# PATH RESOLUTION
# ═══════════════

def _resolve_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _resolve_data_dir() -> Path:
    if getattr(sys, 'frozen', False):
        local = os.getenv("LOCALAPPDATA")
        if local:
            return Path(local) / "SariSariPOS"
        return Path.home() / "AppData" / "Local" / "SariSariPOS"
    return _resolve_base_dir() / "data"


BASE_DIR = _resolve_base_dir()
DATA_ROOT = _resolve_data_dir()

# Load .env from next to the exe / project root
load_dotenv(dotenv_path=BASE_DIR / ".env", override=False)


def _ensure_writable_dir(path: Path, label: str) -> bool:
    """Ensure a directory exists and is writable. Never raises."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return True
    except Exception as e:
        print(f"[config] WARNING: cannot write to {label} at {path}: {e}")
        return False


DATA_DIR = DATA_ROOT
LOGS_DIR = DATA_ROOT / "logs"
BACKUPS_DIR = DATA_ROOT / "backups"

_ensure_writable_dir(DATA_DIR, "data")
_ensure_writable_dir(LOGS_DIR, "logs")
_ensure_writable_dir(BACKUPS_DIR, "backups")

print(f"[config] BASE_DIR  = {BASE_DIR}")
print(f"[config] DATA_ROOT = {DATA_ROOT}")


# ═══════════════
# CONFIG CLASSES
# ═══════════════

def _parse_cors_origins(raw: str):
    if not raw:
        return []
    return [o.strip() for o in raw.split(',') if o.strip()]


class Config:
    APP_NAME = os.getenv("APP_NAME", "Sari-Sari Store POS")
    APP_ENV = os.getenv("APP_ENV", "development")

    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 5000))

    DB_TYPE = os.getenv("DB_TYPE", "sqlite")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_NAME = os.getenv("DB_NAME", "sari_sari_pos")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    _default_db_path = str(DATA_DIR / "sari_sari_pos.db")
    DB_PATH = os.getenv("DB_PATH", _default_db_path)

    SERVER_PID_FILE = str(DATA_DIR / "server.pid")

    JWT_ACCESS_TOKEN_EXPIRES = 28800  # 8 hours

    CORS_ORIGINS = _parse_cors_origins(os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5000,http://127.0.0.1:5000"
    ))

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = LOGS_DIR / "app.log"

    RATELIMIT_ENABLED = os.getenv("RATELIMIT_ENABLED", "True").lower() == "true"
    RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "100/hour")

    USE_HTTPS = os.getenv("USE_HTTPS", "false").lower() == "true"

    def __init__(self):
        self.DEBUG = (self.APP_ENV == "development")

        self.SECRET_KEY = os.environ.get("SECRET_KEY")
        if not self.SECRET_KEY:
            if self.APP_ENV == "production":
                raise RuntimeError(
                    "SECRET_KEY must be set in production."
                )
            self.SECRET_KEY = "dev-only-secret-change-me"

        self.JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
        if not self.JWT_SECRET_KEY:
            if self.APP_ENV == "production":
                raise RuntimeError(
                    "JWT_SECRET_KEY must be set in production."
                )
            self.JWT_SECRET_KEY = "dev-only-jwt-secret-change-me"

    @property
    def DATABASE_URL(self):
        if self.DB_TYPE == "sqlite":
            os.makedirs(os.path.dirname(self.DB_PATH), exist_ok=True)
            return f"sqlite:///{self.DB_PATH}"
        elif self.DB_TYPE == "mysql":
            return (f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
                    f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}")
        elif self.DB_TYPE == "postgresql":
            return (f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
                    f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}")
        else:
            raise ValueError(f"Unsupported database type: {self.DB_TYPE}")


class DevelopmentConfig(Config):
    APP_ENV = "development"


class ProductionConfig(Config):
    APP_ENV = "production"


class TestingConfig(Config):
    APP_ENV = "testing"
    TESTING = True
    DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "test.db"))


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config():
    env = os.getenv("APP_ENV", "development")
    config_class = config_map.get(env)
    if config_class is None:
        raise ValueError(f"Unknown environment: {env}")
    return config_class()


config = get_config()

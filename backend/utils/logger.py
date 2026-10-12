
#Logging configuration.

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logger(app):
 
    log_level = app.config.get('LOG_LEVEL', 'INFO')
    log_file = app.config.get('LOG_FILE', Path('logs/app.log'))

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    log_file.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation
    try:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Werkzeug: INFO so every HTTP request appears in the log ─
    logging.getLogger('werkzeug').setLevel(logging.INFO)

    # Flask-CORS is noisy on startup; keep at WARNING 
    logging.getLogger('flask_cors').setLevel(logging.WARNING)

    app.logger.info(f"Logger initialized with level {log_level}")
    app.logger.info(f"Log file: {log_file}")


def get_logger(name: str = None) -> logging.Logger:
    #Get a logger instance.
    if name:
        return logging.getLogger(name)
    return logging.getLogger()


class AppLogger:
    #Application logger wrapper for structured logging

    def __init__(self, name: str = None):
        self.logger = get_logger(name)

    def debug(self, message: str, **kwargs):
        self._log(logging.DEBUG, message, kwargs)

    def info(self, message: str, **kwargs):
        self._log(logging.INFO, message, kwargs)

    def warning(self, message: str, **kwargs):
        self._log(logging.WARNING, message, kwargs)

    def error(self, message: str, **kwargs):
        self._log(logging.ERROR, message, kwargs)

    def critical(self, message: str, **kwargs):
        self._log(logging.CRITICAL, message, kwargs)

    def _log(self, level: int, message: str, extra: dict):
        if extra:
            extra_str = " ".join([f"{k}={v}" for k, v in extra.items()])
            message = f"{message} {extra_str}"
        self.logger.log(level, message)

    def log_request(self, request):
        self.info(
            f"Request: {request.method} {request.path}",
            ip=request.remote_addr,
            user_agent=(request.user_agent.string
                        if request.user_agent else None)
        )

    def log_response(self, response):
        self.info(
            f"Response: {response.status_code}",
            status=response.status_code
        )

    def log_exception(self, exception, context: str = ""):
        self.error(
            f"Exception in {context}: {str(exception)}",
            error_type=type(exception).__name__,
            context=context
        )
        self.logger.exception(exception)

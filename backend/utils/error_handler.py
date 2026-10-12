
# Centralized error handlers for the API.
#All handlers return the standard error envelope from utils/responses.py so that clients always see the same shape.

from flask import request, current_app
import traceback

from utils.responses import (
    bad_request,
    unauthorized,
    forbidden,
    not_found,
    method_not_allowed,
    conflict,
    unprocessable,
    rate_limited,
    server_error,
)


def _log_error(message, exc=None, level='error'):
    
    try:
        method = request.method
        path = request.path
        ip = request.remote_addr or 'unknown'
        prefix = f"[{method} {path}] [{ip}]"

        log_fn = current_app.logger.error
        if level == 'warning':
            log_fn = current_app.logger.warning

        if exc:
            log_fn(f"{prefix} {message}: {exc}")
            current_app.logger.error(traceback.format_exc())
        else:
            log_fn(f"{prefix} {message}")
    except Exception:
        # If logging itself fails, don't crash the handler.
        pass


def register_error_handlers(app):
   #Attach error handlers to the Flask app

    @app.errorhandler(400)
    def handle_bad_request(e):
        _log_error("400 Bad Request", e, level='warning')
        return bad_request('The request could not be understood.')

    @app.errorhandler(401)
    def handle_unauthorized(e):
        _log_error("401 Unauthorized", e, level='warning')
        return unauthorized('Authentication required.')

    @app.errorhandler(403)
    def handle_forbidden(e):
        _log_error("403 Forbidden", e, level='warning')
        return forbidden()

    @app.errorhandler(404)
    def handle_not_found(e):
        try:
            current_app.logger.info(
                f"[{request.method} {request.path}] 404 Not Found"
            )
        except Exception:
            pass
        return not_found('The requested resource was not found.')

    @app.errorhandler(405)
    def handle_method_not_allowed(e):
        _log_error("405 Method Not Allowed", e, level='warning')
        return method_not_allowed()

    @app.errorhandler(409)
    def handle_conflict(e):
        _log_error("409 Conflict", e, level='warning')
        return conflict('The request conflicts with existing data.')

    @app.errorhandler(422)
    def handle_unprocessable(e):
        _log_error("422 Unprocessable Entity", e, level='warning')
        return unprocessable('The request could not be processed.')

    @app.errorhandler(429)
    def handle_too_many_requests(e):
        _log_error("429 Too Many Requests", e, level='warning')
        return rate_limited()

    @app.errorhandler(500)
    def handle_server_error(e):
        _log_error("500 Internal Server Error", e)
        return server_error()

    @app.errorhandler(Exception)
    def handle_unhandled(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            # Let Flask's built-in handlers deal with it.
            return e

        _log_error("Unhandled Exception", e)
        return server_error()

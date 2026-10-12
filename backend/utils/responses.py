#Standard response helpers for the API.

from typing import Any, Optional
from flask import jsonify


def _envelope_success(data=None, message=None):
    body = {'success': True}
    if message is not None:
        body['message'] = message
    if data is not None:
        body['data'] = data
    return body


def _envelope_error(code, message, details=None):
    body = {
        'success': False,
        'error': code,
        'message': message,
    }
    if details is not None:
        body['details'] = details
    return body


# ══════════════════
# SUCCESS RESPONSES
# ══════════════════

def success_response(data=None, message=None, status=200):
    #200-family success
    return jsonify(_envelope_success(data=data, message=message)), status


def created_response(data=None, message=None):
    #201 Created
    return success_response(data=data, message=message, status=201)


# ═════════════════
# ERROR RESPONSES
# ═════════════════

def error_response(code, message, status=400, details=None):
    return jsonify(_envelope_error(code, message, details=details)), status


def bad_request(message, code='bad_request', details=None):
    return error_response(code, message, status=400, details=details)


def unauthorized(message='Authentication required.', code='unauthorized'):
    return error_response(code, message, status=401)

        # Error found 403
def forbidden(message='You do not have permission for this action.', code='forbidden'):
    return error_response(code, message, status=403)

        # Error found 404
def not_found(message='Resource not found.', code='not_found'):
    return error_response(code, message, status=404)


def method_not_allowed(message='HTTP method not allowed.', code='method_not_allowed'):
    return error_response(code, message, status=405)

        #409 Conflict — duplicate resource, in-use constraint, etc
def conflict(message, code='conflict'):
    return error_response(code, message, status=409)

        #422 Unprocessable Entity
def unprocessable(message, code='unprocessable_entity'):    
    return error_response(code, message, status=422)

        #429 Too Many Requests
def rate_limited(message='Rate limit exceeded. Please try again later.', code='rate_limit_exceeded'):
    return error_response(code, message, status=429)

        #400 with structured details from marshmallow
def validation_error(details=None, message='Invalid input data.', code='validation_error'):
    return error_response(code, message, status=400, details=details)

        #500 Internal Server Error
def server_error(message='An unexpected error occurred.', code='internal_server_error'):
    return error_response(code, message, status=500)

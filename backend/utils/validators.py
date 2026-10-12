#Validation utilities.

import re
from functools import wraps
from typing import Optional, List, Dict, Any
from flask import request, jsonify
from marshmallow import ValidationError


def validate_username(username: str) -> bool:
    """
    Validate username format.

    Requirements:
    - 3-50 characters
    - Only letters, numbers, and underscores

    Args:
        username: Username to validate

    Returns:
        bool: True if valid

    Raises:
        ValueError: If username doesn't meet requirements
    """
    if not username:
        raise ValueError("Username is required")

    if len(username) < 3:
        raise ValueError("Username must be at least 3 characters long")

    if len(username) > 50:
        raise ValueError("Username must be less than 50 characters")

    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        raise ValueError("Username must contain only letters, numbers, and underscores")

    return True


def validate_password_strength(password: str) -> bool:
    """
    Validate password strength.

    Requirements:
    - At least 8 characters long
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number

    Args:
        password: Password to validate

    Returns:
        bool: True if valid

    Raises:
        ValueError: If password doesn't meet requirements
    """
    if not password:
        raise ValueError("Password is required")

    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")

    if not re.search(r'[A-Z]', password):
        raise ValueError("Password must contain at least one uppercase letter")

    if not re.search(r'[a-z]', password):
        raise ValueError("Password must contain at least one lowercase letter")

    if not re.search(r'[0-9]', password):
        raise ValueError("Password must contain at least one number")

    return True


def validate_email_address(email: str) -> bool:
    """
    Validate email address format.

    Args:
        email: Email address to validate

    Returns:
        bool: True if valid email format
    """
    if not email:
        return False

    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_input(schema):
    """
    Decorator to validate input data using marshmallow schema.

    Args:
        schema: Marshmallow schema class

    Returns:
        function: Decorated function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                # Load and validate data
                data = schema().load(request.get_json() or {})
                request.validated_data = data
                return f(*args, **kwargs)
            except ValidationError as e:
                return jsonify({
                    'error': 'validation_error',
                    'message': 'Invalid input data',
                    'details': e.messages
                }), 400
            except Exception as e:
                return jsonify({
                    'error': 'validation_error',
                    'message': str(e)
                }), 400

        return decorated_function

    return decorator

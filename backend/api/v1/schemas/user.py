#User schemas for request validation and response serialization.

from marshmallow import Schema, fields, validate, ValidationError, post_load
import re


def validate_password(value):
    """
    Validate password strength.
        Requirements:
    - At least 8 characters long
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number
    """
    if len(value) < 8:
        raise ValidationError("Password must be at least 8 characters long")
    if not re.search(r'[A-Z]', value):
        raise ValidationError("Password must contain at least one uppercase letter")
    if not re.search(r'[a-z]', value):
        raise ValidationError("Password must contain at least one lowercase letter")
    if not re.search(r'[0-9]', value):
        raise ValidationError("Password must contain at least one number")
    return value


def validate_username(value):
    """
    Validate username format.
    Requirements:
    - 3-50 characters
    - Only letters, numbers, and underscores
    """
    if not value:
        raise ValidationError("Username is required")
    if len(value) < 3:
        raise ValidationError("Username must be at least 3 characters")
    if len(value) > 50:
        raise ValidationError("Username must be less than 50 characters")
    if not re.match(r'^[a-zA-Z0-9_]+$', value):
        raise ValidationError(
            "Username must contain only letters, numbers, and underscores"
        )
    return value


class LoginSchema(Schema):
    #Login request schema with role support
    username = fields.Str(required=True, validate=validate_username)
    password = fields.Str(required=True)
    remember_me = fields.Bool(required=False, missing=False)
    role = fields.Str(
        required=False, 
        missing='owner', 
        validate=validate.OneOf(['owner', 'cashier'])
    )


class RegisterSchema(Schema):
    #User registration schema
    username = fields.Str(required=True, validate=validate_username)
    password = fields.Str(required=True, validate=validate_password)
    email = fields.Email(required=False, allow_none=True)
    full_name = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    role = fields.Str(
        required=False, 
        missing='cashier', 
        validate=validate.OneOf(['owner', 'cashier'])
    )


class ChangePasswordSchema(Schema):
  #Change password schema
    old_password = fields.Str(required=True)
    new_password = fields.Str(required=True, validate=validate_password)


class UserUpdateSchema(Schema):
    #User update schema (admin only)
    email = fields.Email(required=False, allow_none=True)
    full_name = fields.Str(required=False, validate=validate.Length(min=1, max=100))
    is_active = fields.Bool(required=False)
    role = fields.Str(required=False, validate=validate.OneOf(['owner', 'cashier']))


class ResetPasswordSchema(Schema):
    #"Reset password schema (admin only)
    new_password = fields.Str(required=True, validate=validate_password)


class UserResponseSchema(Schema):
    #User response schema
    id = fields.Int()
    username = fields.Str()
    email = fields.Email(allow_none=True)
    full_name = fields.Str()
    role = fields.Str()
    is_active = fields.Bool()
    last_login = fields.DateTime(allow_none=True)
    created_at = fields.DateTime()
    updated_at = fields.DateTime(allow_none=True)


class UserListResponseSchema(Schema):
    #User list response schema with pagination
    items = fields.List(fields.Nested(UserResponseSchema))
    pagination = fields.Dict()


# ===================
# VALIDATION HELPERS
# ===================

def validate_user_data(data):
    """
    Validate and sanitize user data for creation/update.
        Args:
        data: Dictionary of user data
        Returns:
        dict: Validated data
        Raises:
        ValidationError: If validation fails
    """
    errors = []
    
    # Validate username
    if 'username' in data and data['username']:
        try:
            validate_username(data['username'])
        except ValidationError as e:
            errors.append(str(e))
    
    #Validate password
    if 'password' in data and data['password']:
        try:
            validate_password(data['password'])
        except ValidationError as e:
            errors.append(str(e))
    
    #Validate email
    if 'email' in data and data['email']:
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, data['email']):
            errors.append("Invalid email address format")
    
    #Validate full_name
    if 'full_name' in data and data['full_name']:
        if len(data['full_name']) < 1:
            errors.append("Full name is required")
        elif len(data['full_name']) > 100:
            errors.append("Full name must be less than 100 characters")
    
    #Validate role
    if 'role' in data and data['role']:
        if data['role'] not in ['owner', 'cashier']:
            errors.append("Role must be either 'owner' or 'cashier'")
    
    if errors:
        raise ValidationError("; ".join(errors))
    
    return data


def validate_login_data(data):
    """
    Validate and sanitize login data.
        Args:
        data: Dictionary of login data
        Returns:
        dict: Validated data
        Raises:
        ValidationError: If validation fails
    """
    errors = []
    
    #Validate username
    if 'username' not in data or not data['username']:
        errors.append("Username is required")
    else:
        try:
            validate_username(data['username'])
        except ValidationError as e:
            errors.append(str(e))
    
    #Validate password
    if 'password' not in data or not data['password']:
        errors.append("Password is required")
    
    #Validate role
    if 'role' in data and data['role']:
        if data['role'] not in ['owner', 'cashier']:
            errors.append("Invalid role. Must be 'owner' or 'cashier'")
    
    if errors:
        raise ValidationError("; ".join(errors))
    
    return data

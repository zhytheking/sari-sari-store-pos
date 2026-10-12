#Helper utility functions for the application.

import uuid
import re
import json
from datetime import datetime, date
from typing import Optional, Dict, Any, List, Union
import random
import string


def generate_invoice_number(prefix: str = "INV-") -> str:
    timestamp = datetime.now().strftime('%Y%m%d')
    unique_id = str(uuid.uuid4())[:8].upper()
    return f"{prefix}{timestamp}-{unique_id}"


def format_currency(amount: Union[float, int, str], currency: str = "₱") -> str:
    try:
        amount = float(amount)
        return f"{currency}{amount:,.2f}"
    except (ValueError, TypeError):
        return f"{currency}0.00"


def parse_date(date_string: str) -> Optional[datetime]:
    """
    Parse date string to datetime object.

    Args:
        date_string: Date string in various formats

    Returns:
        datetime: Parsed datetime object or None if parsing fails
    """
    if not date_string:
        return None

    formats = [
        '%Y-%m-%d',
        '%Y-%m-%d %H:%M:%S',
        '%m/%d/%Y',
        '%d/%m/%Y',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%m-%d-%Y',
        '%d-%m-%Y'
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_string, fmt)
        except ValueError:
            continue

    return None


def format_datetime(dt: Union[datetime, str], format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format datetime to string.

    Args:
        dt: Datetime object or string
        format_str: Output format string

    Returns:
        str: Formatted datetime string
    """
    if isinstance(dt, str):
        dt = parse_date(dt)

    if dt is None:
        return ""

    return dt.strftime(format_str)


def sanitize_string(text: str) -> str:
    """
    Sanitize string input by removing HTML tags and special characters.

    Args:
        text: Input string

    Returns:
        str: Sanitized string
    """
    if not text:
        return ""

    # Remove HTML tags
    text = re.sub(r'<[^>]*>', '', text)

    # Remove special characters (keep alphanumeric, spaces, hyphens, dots, commas, apostrophes)
    text = re.sub(r'[^\w\s\-.,\' ]', '', text)

    return text.strip()


def truncate_text(text: str, length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to specified length.

    Args:
        text: Text to truncate
        length: Maximum length
        suffix: Suffix to append when truncated

    Returns:
        str: Truncated text
    """
    if not text:
        return ""

    if len(text) <= length:
        return text
    return text[:length] + suffix


def safe_json_loads(data: str) -> Dict[str, Any]:
    if not data:
        return {}

    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return {}


def safe_json_dumps(data: Any, indent: int = None) -> str:
    try:
        return json.dumps(data, indent=indent, default=str)
    except (TypeError, ValueError):
        return ""


def calculate_percentage(part: Union[float, int], total: Union[float, int]) -> float:
    try:
        part = float(part)
        total = float(total)
        if total == 0:
            return 0.0
        return (part / total) * 100
    except (ValueError, TypeError):
        return 0.0


def is_valid_uuid(uuid_string: str) -> bool:
    if not uuid_string:
        return False

    try:
        uuid.UUID(uuid_string)
        return True
    except ValueError:
        return False


def get_file_extension(filename: str) -> str:
    if not filename or '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[1].lower()


def generate_random_string(length: int = 8, include_digits: bool = True) -> str:
    """
    Generate a random string.

    Args:
        length: Length of the string
        include_digits: Include digits in the string

    Returns:
        str: Random string
    """
    chars = string.ascii_uppercase
    if include_digits:
        chars += string.digits

    return ''.join(random.choices(chars, k=length))


def generate_random_password(length: int = 12) -> str:
    """
    Generate a random password.

    Args:
        length: Length of the password

    Returns:
        str: Random password with uppercase, lowercase, digits, and special chars
    """
    chars = string.ascii_uppercase + string.ascii_lowercase + string.digits + "!@#$%^&*"
    return ''.join(random.choices(chars, k=length))


def get_current_timestamp() -> str:
    """
    Get current timestamp as string.

    Returns:
        str: Current timestamp
    """
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def get_current_date() -> str:
    """
    Get current date as string.

    Returns:
        str: Current date
    """
    return datetime.now().strftime('%Y-%m-%d')


def is_valid_phone(phone: str) -> bool:
    """
    Validate phone number (Philippine format).

    Args:
        phone: Phone number to validate

    Returns:
        bool: True if valid
    """
    if not phone:
        return False

    cleaned = re.sub(r'[\s\-()]', '', phone)
    pattern = r'^(09|639)\d{9}$'
    return bool(re.match(pattern, cleaned))


def is_valid_email(email: str) -> bool:
    """
    Validate email address.

    Args:
        email: Email to validate

    Returns:
        bool: True if valid
    """
    if not email:
        return False

    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

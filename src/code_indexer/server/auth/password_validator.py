"""
Password complexity validation for CIDX Server.

Enforces password complexity requirements to ensure secure user passwords.
"""

import re
from typing import Dict, Any


def validate_password_complexity(password: str) -> bool:
    """
    Validate password complexity requirements.

    Requirements:
    - Minimum 9 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character (!@#$%^&*()_+-=[]{}|;:,.<>?)

    Args:
        password: Password to validate

    Returns:
        True if password meets complexity requirements, False otherwise
    """
    if len(password) < 9:
        return False

    # Check for uppercase letter
    if not re.search(r"[A-Z]", password):
        return False

    # Check for lowercase letter
    if not re.search(r"[a-z]", password):
        return False

    # Check for digit
    if not re.search(r"\d", password):
        return False

    # Check for special character
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]", password):
        return False

    return True


def get_password_requirements() -> Dict[str, Any]:
    """
    Get password complexity requirements.

    Returns:
        Dictionary describing password requirements
    """
    return {
        "min_length": 9,
        "require_uppercase": True,
        "require_lowercase": True,
        "require_digits": True,
        "require_special_chars": True,
        "special_chars": "!@#$%^&*()_+-=[]{}|;:,.<>?",
        "description": "Password must be at least 9 characters long and contain at least one uppercase letter, one lowercase letter, one digit, and one special character.",
    }


def get_password_complexity_error_message() -> str:
    """
    Get user-friendly error message for password complexity validation.

    Returns:
        Error message explaining password requirements
    """
    requirements = get_password_requirements()
    return (
        f"Password must be at least {requirements['min_length']} characters long and contain "
        "at least one uppercase letter, one lowercase letter, one digit, "
        f"and one special character ({requirements['special_chars']})."
    )

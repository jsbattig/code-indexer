"""User input validation for admin operations."""

import re
from typing import Set


class UserValidationError(Exception):
    """Exception raised when user input validation fails."""

    pass


# Valid roles based on server UserRole enum
VALID_ROLES: Set[str] = {"admin", "power_user", "normal_user"}

# Username validation pattern: alphanumeric, underscores, hyphens, dots
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")

# Email validation pattern (basic RFC 5322 compliance)
EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)


def validate_username(username: str) -> str:
    """Validate username format and requirements.

    Args:
        username: Username to validate

    Returns:
        Validated and cleaned username

    Raises:
        UserValidationError: If username is invalid
    """
    if not username:
        raise UserValidationError("Username cannot be empty")

    # Strip whitespace
    username = username.strip()

    if not username:
        raise UserValidationError("Username cannot be empty or contain only whitespace")

    if len(username) < 3:
        raise UserValidationError("Username must be at least 3 characters long")

    if len(username) > 32:
        raise UserValidationError("Username cannot be longer than 32 characters")

    if not USERNAME_PATTERN.match(username):
        raise UserValidationError(
            "Username can only contain letters, numbers, underscores, hyphens, and dots"
        )

    # Username cannot start or end with special characters
    if username.startswith((".", "-", "_")) or username.endswith((".", "-", "_")):
        raise UserValidationError(
            "Username cannot start or end with dots, hyphens, or underscores"
        )

    # Username cannot contain consecutive special characters
    if re.search(r"[._-]{2,}", username):
        raise UserValidationError(
            "Username cannot contain consecutive dots, hyphens, or underscores"
        )

    return username


def validate_email(email: str) -> str:
    """Validate email format and requirements.

    Args:
        email: Email address to validate

    Returns:
        Validated and cleaned email address

    Raises:
        UserValidationError: If email is invalid
    """
    if not email:
        raise UserValidationError("Email cannot be empty")

    # Strip whitespace and convert to lowercase
    email = email.strip().lower()

    if not email:
        raise UserValidationError("Email cannot be empty or contain only whitespace")

    if len(email) > 254:  # RFC 5321 limit
        raise UserValidationError("Email address cannot be longer than 254 characters")

    # Additional checks for common issues (before regex)
    if email.startswith(".") or email.endswith("."):
        raise UserValidationError("Email address cannot start or end with a dot")

    if ".." in email:
        raise UserValidationError("Email address cannot contain consecutive dots")

    if not EMAIL_PATTERN.match(email):
        raise UserValidationError("Invalid email address format")

    # Check local part (before @) length
    local_part = email.split("@")[0]
    if len(local_part) > 64:  # RFC 5321 limit
        raise UserValidationError(
            "Email local part cannot be longer than 64 characters"
        )

    return email


def validate_password(password: str) -> str:
    """Validate password strength and requirements.

    Args:
        password: Password to validate

    Returns:
        Validated password (unchanged)

    Raises:
        UserValidationError: If password is invalid
    """
    if not password:
        raise UserValidationError("Password cannot be empty")

    if len(password) < 8:
        raise UserValidationError("Password must be at least 8 characters long")

    if len(password) > 128:
        raise UserValidationError("Password cannot be longer than 128 characters")

    # Check for common weak patterns first
    if password.lower() in ["password", "12345678", "qwerty123", "abc123456"]:
        raise UserValidationError("Password is too common and easily guessable")

    # Check for at least one uppercase letter
    if not re.search(r"[A-Z]", password):
        raise UserValidationError("Password must contain at least one uppercase letter")

    # Check for at least one lowercase letter
    if not re.search(r"[a-z]", password):
        raise UserValidationError("Password must contain at least one lowercase letter")

    # Check for at least one digit
    if not re.search(r"\d", password):
        raise UserValidationError("Password must contain at least one digit")

    # Check for at least one special character
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise UserValidationError(
            'Password must contain at least one special character (!@#$%^&*(),.?":{}|<>)'
        )

    return password


def validate_role(role: str) -> str:
    """Validate user role against available options.

    Args:
        role: Role to validate

    Returns:
        Validated role

    Raises:
        UserValidationError: If role is invalid
    """
    if not role:
        raise UserValidationError("Role cannot be empty")

    # Strip whitespace and convert to lowercase for comparison
    role = role.strip().lower()

    if not role:
        raise UserValidationError("Role cannot be empty or contain only whitespace")

    if role not in VALID_ROLES:
        valid_roles_str = ", ".join(sorted(VALID_ROLES))
        raise UserValidationError(
            f"Invalid role '{role}'. Valid roles are: {valid_roles_str}"
        )

    return role

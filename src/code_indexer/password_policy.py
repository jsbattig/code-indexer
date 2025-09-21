"""Password policy validation for CIDX authentication.

Provides password strength validation and policy enforcement for secure
password management operations.
"""

from typing import Tuple, List


class PasswordPolicy:
    """Password policy validation and enforcement."""

    MIN_LENGTH = 8
    REQUIRE_NUMBERS = True
    REQUIRE_SYMBOLS = True

    # Special characters that are considered valid
    VALID_SPECIAL_CHARS = "!@#$%^&*()_+-=[]{}|;:,.<>?"

    @staticmethod
    def validate(password: str) -> Tuple[bool, str]:
        """Validate password against policy requirements.

        Args:
            password: Password to validate

        Returns:
            Tuple[bool, str]: (is_valid, error_message_or_success)
        """
        if not password:
            return False, "Password too weak: Must be at least 8 characters long"

        violations = []

        # Check minimum length
        if len(password) < PasswordPolicy.MIN_LENGTH:
            violations.append("Must be at least 8 characters long")

        # Check for numbers if required
        if PasswordPolicy.REQUIRE_NUMBERS:
            if not any(char.isdigit() for char in password):
                violations.append("Must contain numbers")

        # Check for special characters if required
        if PasswordPolicy.REQUIRE_SYMBOLS:
            if not any(char in PasswordPolicy.VALID_SPECIAL_CHARS for char in password):
                violations.append("Must contain special characters")

        if violations:
            if len(violations) == 1:
                return False, f"Password too weak: {violations[0]}"
            else:
                return False, f"Password too weak: {' and '.join(violations)}"

        return True, "Password meets requirements"

    @staticmethod
    def get_policy_description() -> str:
        """Return human-readable policy description.

        Returns:
            str: Description of password policy requirements
        """
        requirements = [f"At least {PasswordPolicy.MIN_LENGTH} characters long"]

        if PasswordPolicy.REQUIRE_NUMBERS:
            requirements.append("Contains numbers")

        if PasswordPolicy.REQUIRE_SYMBOLS:
            requirements.append(
                f"Contains special characters ({PasswordPolicy.VALID_SPECIAL_CHARS})"
            )

        return "Password must be:\n• " + "\n• ".join(requirements)

    @staticmethod
    def get_strength_feedback(password: str) -> List[str]:
        """Get detailed feedback about password strength.

        Args:
            password: Password to analyze

        Returns:
            List[str]: List of feedback messages for improvement
        """
        feedback = []

        if len(password) < PasswordPolicy.MIN_LENGTH:
            feedback.append(
                f"Add {PasswordPolicy.MIN_LENGTH - len(password)} more characters"
            )

        if PasswordPolicy.REQUIRE_NUMBERS and not any(
            char.isdigit() for char in password
        ):
            feedback.append("Add at least one number (0-9)")

        if PasswordPolicy.REQUIRE_SYMBOLS and not any(
            char in PasswordPolicy.VALID_SPECIAL_CHARS for char in password
        ):
            feedback.append("Add at least one special character (!@#$%^&* etc.)")

        # Additional strength recommendations
        if len(password) >= PasswordPolicy.MIN_LENGTH:
            if not any(char.isupper() for char in password):
                feedback.append("Consider adding uppercase letters for better security")

            if not any(char.islower() for char in password):
                feedback.append("Consider adding lowercase letters for better security")

        if not feedback:
            feedback.append("Password meets all requirements!")

        return feedback


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """Convenience function for password validation.

    Args:
        password: Password to validate

    Returns:
        Tuple[bool, str]: (is_valid, message)
    """
    return PasswordPolicy.validate(password)


def get_password_policy_help() -> str:
    """Get help text for password policy requirements.

    Returns:
        str: Help text explaining password requirements
    """
    return PasswordPolicy.get_policy_description()

"""
Tests for user input validation functions.

Foundation #1 compliant tests with no mocks - testing actual validation
logic with real inputs and expected outcomes.
"""

import pytest

from code_indexer.validation.user_validation import (
    validate_username,
    validate_email,
    validate_password,
    validate_role,
    UserValidationError,
)


class TestUsernameValidation:
    """Test username validation with various input scenarios."""

    def test_valid_username_alphanumeric(self):
        """Test valid alphanumeric username."""
        result = validate_username("user123")
        assert result == "user123"

    def test_valid_username_with_underscores(self):
        """Test valid username with underscores."""
        result = validate_username("test_user")
        assert result == "test_user"

    def test_valid_username_with_hyphens(self):
        """Test valid username with hyphens."""
        result = validate_username("test-user")
        assert result == "test-user"

    def test_valid_username_with_dots(self):
        """Test valid username with dots."""
        result = validate_username("test.user")
        assert result == "test.user"

    def test_valid_username_mixed_special_chars(self):
        """Test valid username with mixed special characters."""
        result = validate_username("test_user-123.name")
        assert result == "test_user-123.name"

    def test_valid_username_minimum_length(self):
        """Test valid username at minimum length (3 chars)."""
        result = validate_username("abc")
        assert result == "abc"

    def test_valid_username_maximum_length(self):
        """Test valid username at maximum length (32 chars)."""
        username = "a" * 32
        result = validate_username(username)
        assert result == username

    def test_username_strips_whitespace(self):
        """Test username validation strips whitespace."""
        result = validate_username("  testuser  ")
        assert result == "testuser"

    def test_empty_username_raises_error(self):
        """Test empty username raises validation error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_username("")
        assert "cannot be empty" in str(exc_info.value)

    def test_whitespace_only_username_raises_error(self):
        """Test whitespace-only username raises validation error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_username("   ")
        assert "cannot be empty or contain only whitespace" in str(exc_info.value)

    def test_username_too_short_raises_error(self):
        """Test username shorter than 3 characters raises error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_username("ab")
        assert "at least 3 characters" in str(exc_info.value)

    def test_username_too_long_raises_error(self):
        """Test username longer than 32 characters raises error."""
        username = "a" * 33
        with pytest.raises(UserValidationError) as exc_info:
            validate_username(username)
        assert "cannot be longer than 32 characters" in str(exc_info.value)

    def test_username_invalid_characters_raises_error(self):
        """Test username with invalid characters raises error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_username("user@name")
        assert "can only contain letters, numbers" in str(exc_info.value)

    def test_username_starts_with_dot_raises_error(self):
        """Test username starting with dot raises error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_username(".username")
        assert "cannot start or end with" in str(exc_info.value)

    def test_username_ends_with_hyphen_raises_error(self):
        """Test username ending with hyphen raises error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_username("username-")
        assert "cannot start or end with" in str(exc_info.value)

    def test_username_consecutive_special_chars_raises_error(self):
        """Test username with consecutive special characters raises error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_username("user..name")
        assert "cannot contain consecutive" in str(exc_info.value)


class TestEmailValidation:
    """Test email validation with various input scenarios."""

    def test_valid_email_basic(self):
        """Test valid basic email address."""
        result = validate_email("user@example.com")
        assert result == "user@example.com"

    def test_valid_email_subdomain(self):
        """Test valid email with subdomain."""
        result = validate_email("user@mail.example.com")
        assert result == "user@mail.example.com"

    def test_valid_email_plus_sign(self):
        """Test valid email with plus sign."""
        result = validate_email("user+tag@example.com")
        assert result == "user+tag@example.com"

    def test_valid_email_dots_in_local(self):
        """Test valid email with dots in local part."""
        result = validate_email("first.last@example.com")
        assert result == "first.last@example.com"

    def test_email_converts_to_lowercase(self):
        """Test email validation converts to lowercase."""
        result = validate_email("USER@EXAMPLE.COM")
        assert result == "user@example.com"

    def test_email_strips_whitespace(self):
        """Test email validation strips whitespace."""
        result = validate_email("  user@example.com  ")
        assert result == "user@example.com"

    def test_empty_email_raises_error(self):
        """Test empty email raises validation error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_email("")
        assert "cannot be empty" in str(exc_info.value)

    def test_whitespace_only_email_raises_error(self):
        """Test whitespace-only email raises validation error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_email("   ")
        assert "cannot be empty or contain only whitespace" in str(exc_info.value)

    def test_email_too_long_raises_error(self):
        """Test email longer than 254 characters raises error."""
        long_email = "a" * 250 + "@example.com"
        with pytest.raises(UserValidationError) as exc_info:
            validate_email(long_email)
        assert "cannot be longer than 254 characters" in str(exc_info.value)

    def test_invalid_email_format_raises_error(self):
        """Test invalid email format raises error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_email("invalid.email")
        assert "Invalid email address format" in str(exc_info.value)

    def test_email_starts_with_dot_raises_error(self):
        """Test email starting with dot raises error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_email(".user@example.com")
        assert "cannot start or end with a dot" in str(exc_info.value)

    def test_email_ends_with_dot_raises_error(self):
        """Test email ending with dot raises error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_email("user@example.com.")
        assert "cannot start or end with a dot" in str(exc_info.value)

    def test_email_consecutive_dots_raises_error(self):
        """Test email with consecutive dots raises error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_email("user..name@example.com")
        assert "cannot contain consecutive dots" in str(exc_info.value)

    def test_email_local_part_too_long_raises_error(self):
        """Test email with local part longer than 64 characters raises error."""
        local_part = "a" * 65
        email = f"{local_part}@example.com"
        with pytest.raises(UserValidationError) as exc_info:
            validate_email(email)
        assert "local part cannot be longer than 64 characters" in str(exc_info.value)


class TestPasswordValidation:
    """Test password validation with various input scenarios."""

    def test_valid_password_basic(self):
        """Test valid basic password."""
        password = "TestPass123!"
        result = validate_password(password)
        assert result == password

    def test_valid_password_complex(self):
        """Test valid complex password."""
        password = "MyC0mpl3x@P4ssw0rd!"
        result = validate_password(password)
        assert result == password

    def test_valid_password_minimum_length(self):
        """Test valid password at minimum length (8 chars)."""
        password = "Test123!"
        result = validate_password(password)
        assert result == password

    def test_valid_password_maximum_length(self):
        """Test valid password at maximum length (128 chars)."""
        password = "A1!" + "a" * 125
        result = validate_password(password)
        assert result == password

    def test_empty_password_raises_error(self):
        """Test empty password raises validation error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_password("")
        assert "cannot be empty" in str(exc_info.value)

    def test_password_too_short_raises_error(self):
        """Test password shorter than 8 characters raises error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_password("Test12!")
        assert "at least 8 characters" in str(exc_info.value)

    def test_password_too_long_raises_error(self):
        """Test password longer than 128 characters raises error."""
        password = "A1!" + "a" * 126
        with pytest.raises(UserValidationError) as exc_info:
            validate_password(password)
        assert "cannot be longer than 128 characters" in str(exc_info.value)

    def test_password_missing_uppercase_raises_error(self):
        """Test password without uppercase letter raises error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_password("test123!")
        assert "at least one uppercase letter" in str(exc_info.value)

    def test_password_missing_lowercase_raises_error(self):
        """Test password without lowercase letter raises error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_password("TEST123!")
        assert "at least one lowercase letter" in str(exc_info.value)

    def test_password_missing_digit_raises_error(self):
        """Test password without digit raises error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_password("TestPass!")
        assert "at least one digit" in str(exc_info.value)

    def test_password_missing_special_char_raises_error(self):
        """Test password without special character raises error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_password("TestPass123")
        assert "at least one special character" in str(exc_info.value)

    def test_password_common_weak_patterns_raise_error(self):
        """Test common weak password patterns raise errors."""
        weak_passwords = ["password", "12345678", "qwerty123", "abc123456"]

        for weak_pass in weak_passwords:
            with pytest.raises(UserValidationError) as exc_info:
                validate_password(weak_pass)
            assert "too common and easily guessable" in str(exc_info.value)


class TestRoleValidation:
    """Test role validation with various input scenarios."""

    def test_valid_role_admin(self):
        """Test valid admin role."""
        result = validate_role("admin")
        assert result == "admin"

    def test_valid_role_power_user(self):
        """Test valid power_user role."""
        result = validate_role("power_user")
        assert result == "power_user"

    def test_valid_role_normal_user(self):
        """Test valid normal_user role."""
        result = validate_role("normal_user")
        assert result == "normal_user"

    def test_role_case_insensitive(self):
        """Test role validation is case insensitive."""
        result = validate_role("ADMIN")
        assert result == "admin"

    def test_role_strips_whitespace(self):
        """Test role validation strips whitespace."""
        result = validate_role("  admin  ")
        assert result == "admin"

    def test_empty_role_raises_error(self):
        """Test empty role raises validation error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_role("")
        assert "cannot be empty" in str(exc_info.value)

    def test_whitespace_only_role_raises_error(self):
        """Test whitespace-only role raises validation error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_role("   ")
        assert "cannot be empty or contain only whitespace" in str(exc_info.value)

    def test_invalid_role_raises_error(self):
        """Test invalid role raises validation error."""
        with pytest.raises(UserValidationError) as exc_info:
            validate_role("invalid_role")
        assert "Invalid role 'invalid_role'" in str(exc_info.value)
        assert "admin, normal_user, power_user" in str(exc_info.value)

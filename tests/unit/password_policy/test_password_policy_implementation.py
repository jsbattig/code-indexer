"""Tests for PasswordPolicy implementation.

Tests for actual password policy validation logic and requirements.
"""

from code_indexer.password_policy import (
    PasswordPolicy,
    validate_password_strength,
    get_password_policy_help,
)


class TestPasswordPolicyImplementation:
    """Test actual password policy implementation."""

    def test_password_policy_constants(self):
        """Test password policy constants are correctly defined."""
        assert PasswordPolicy.MIN_LENGTH == 8
        assert PasswordPolicy.REQUIRE_NUMBERS is True
        assert PasswordPolicy.REQUIRE_SYMBOLS is True
        assert isinstance(PasswordPolicy.VALID_SPECIAL_CHARS, str)
        assert len(PasswordPolicy.VALID_SPECIAL_CHARS) > 0

    def test_minimum_length_validation(self):
        """Test minimum length requirement validation."""
        # Too short passwords
        is_valid, message = PasswordPolicy.validate("short")
        assert not is_valid
        assert "Must be at least 8 characters long" in message

        is_valid, message = PasswordPolicy.validate("1234567")
        assert not is_valid
        assert "Must be at least 8 characters long" in message

        # Minimum length (but missing other requirements)
        is_valid, message = PasswordPolicy.validate("12345678")
        assert not is_valid  # Still invalid due to missing special chars

    def test_number_requirement_validation(self):
        """Test number requirement validation."""
        # No numbers
        is_valid, message = PasswordPolicy.validate("NoNumbers!")
        assert not is_valid
        assert "Must contain numbers" in message

        # With numbers but missing other requirements
        is_valid, message = PasswordPolicy.validate("WithNum123")
        assert not is_valid  # Still invalid due to missing special chars

    def test_special_character_requirement_validation(self):
        """Test special character requirement validation."""
        # No special characters
        is_valid, message = PasswordPolicy.validate("NoSpecials123")
        assert not is_valid
        assert "Must contain special characters" in message

        # With special characters but missing other requirements
        is_valid, message = PasswordPolicy.validate("Special!")
        assert not is_valid  # Still invalid due to missing numbers

    def test_valid_passwords(self):
        """Test passwords that meet all requirements."""
        valid_passwords = [
            "ValidPass123!",
            "Another1@Valid",
            "Complex$Password99",
            "Minimum8!1",
            "Test123#",
            "Strong2024!",
        ]

        for password in valid_passwords:
            is_valid, message = PasswordPolicy.validate(password)
            assert is_valid, f"Password '{password}' should be valid but got: {message}"
            assert message == "Password meets requirements"

    def test_invalid_passwords_with_specific_messages(self):
        """Test invalid passwords return specific error messages."""
        test_cases = [
            ("short", "Must be at least 8 characters long"),
            ("NoNumbers!", "Must contain numbers"),
            ("NoSpecials123", "Must contain special characters"),
            ("1234567", "Must be at least 8 characters long"),  # Only 7 chars
        ]

        for password, expected_error in test_cases:
            is_valid, message = PasswordPolicy.validate(password)
            assert not is_valid
            assert expected_error in message

        # Test combined violations
        is_valid, message = PasswordPolicy.validate("OnlyLetters")
        assert not is_valid
        assert "Must contain numbers" in message
        assert "Must contain special characters" in message

    def test_empty_password(self):
        """Test empty password validation."""
        is_valid, message = PasswordPolicy.validate("")
        assert not is_valid
        assert "Must be at least 8 characters long" in message

    def test_valid_special_characters(self):
        """Test that all specified special characters are accepted."""
        special_chars = PasswordPolicy.VALID_SPECIAL_CHARS

        for char in special_chars:
            password = f"Valid123{char}"
            is_valid, message = PasswordPolicy.validate(password)
            assert is_valid, f"Password with special char '{char}' should be valid"

    def test_convenience_function(self):
        """Test convenience function for password validation."""
        # Test valid password
        is_valid, message = validate_password_strength("ValidPass123!")
        assert is_valid
        assert message == "Password meets requirements"

        # Test invalid password
        is_valid, message = validate_password_strength("weak")
        assert not is_valid
        assert "Must be at least 8 characters long" in message

    def test_policy_description(self):
        """Test policy description function."""
        description = PasswordPolicy.get_policy_description()
        assert isinstance(description, str)
        assert "8 characters" in description
        assert "numbers" in description
        assert "special characters" in description

        # Test convenience function
        help_text = get_password_policy_help()
        assert isinstance(help_text, str)
        assert len(help_text) > 0

    def test_password_strength_feedback(self):
        """Test password strength feedback function."""
        # Test weak password
        feedback = PasswordPolicy.get_strength_feedback("weak")
        assert isinstance(feedback, list)
        assert len(feedback) > 0
        assert any("characters" in f for f in feedback)

        # Test strong password
        feedback = PasswordPolicy.get_strength_feedback("StrongPass123!")
        assert isinstance(feedback, list)
        assert any("meets all requirements" in f for f in feedback)

    def test_combined_policy_violations(self):
        """Test passwords that violate multiple policy requirements."""
        # Password that violates length and missing numbers/special chars
        is_valid, message = PasswordPolicy.validate("abc")
        assert not is_valid
        assert "Must be at least 8 characters long" in message

        # Password that violates numbers and special chars but has correct length
        is_valid, message = PasswordPolicy.validate("OnlyLetters")
        assert not is_valid
        # Should mention both missing requirements
        assert (
            "Must contain numbers" in message
            or "Must contain special characters" in message
        )

    def test_unicode_password_handling(self):
        """Test handling of unicode characters in passwords."""
        # Unicode passwords that meet requirements
        unicode_passwords = [
            "Pássword123!",  # Accented characters
            "密码Valid123!",  # Chinese characters
            "Valid123!😀",  # Emoji
        ]

        for password in unicode_passwords:
            # Should work with unicode, focusing on length, numbers, and special chars
            is_valid, message = PasswordPolicy.validate(password)
            # These should be valid as they have 8+ chars, numbers, and special chars
            assert is_valid, f"Unicode password '{password}' should be valid"

    def test_edge_case_passwords(self):
        """Test edge case password scenarios."""
        edge_cases = [
            # Exactly minimum length with requirements
            ("Minimum1!", True),
            # Spaces in password (should be valid if other requirements met)
            ("My Pass1!", True),
            # Only special characters and numbers (actually valid per our policy)
            ("12345678!", True),  # Has 8+ chars, numbers, and special chars
            # Only numbers
            ("12345678", False),  # Missing special chars
            # Only special characters
            ("!@#$%^&*", False),  # Missing numbers
        ]

        for password, expected_valid in edge_cases:
            is_valid, message = PasswordPolicy.validate(password)
            assert (
                is_valid == expected_valid
            ), f"Password '{password}' validation unexpected: {message}"

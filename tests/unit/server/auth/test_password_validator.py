"""
Comprehensive unit tests for password complexity validation.

Critical security component - tests password validation logic thoroughly.
"""

from code_indexer.server.auth.password_validator import (
    validate_password_complexity,
    get_password_requirements,
    get_password_complexity_error_message,
)


class TestValidatePasswordComplexity:
    """Test password complexity validation function."""

    def test_valid_strong_passwords(self):
        """Test that strong passwords pass validation."""
        valid_passwords = [
            "SecurePass123!",
            "ComplexP@ssw0rd",
            "MyStr0ng!P@ssw0rd",
            "C0mpl3x!ty#2024",
            "ValidPass456$",
            "Test!ng123#",
            "P@ssw0rd!2024",
            "Str0ng&SecureP@ss",
            "C0mpl3x!Password123",
            "MySecure123!Pass",
        ]

        for password in valid_passwords:
            assert validate_password_complexity(
                password
            ), f"Password '{password}' should be valid"

    def test_passwords_too_short(self):
        """Test that passwords under 9 characters fail validation."""
        short_passwords = [
            "Short1!",  # 7 chars
            "Test123!",  # 8 chars
            "Aa1!",  # 4 chars
            "A1!a",  # 4 chars
            "Test1!B",  # 8 chars
            "Sh0rt!",  # 6 chars
        ]

        for password in short_passwords:
            assert not validate_password_complexity(
                password
            ), f"Password '{password}' should be invalid (too short)"

    def test_passwords_missing_uppercase(self):
        """Test that passwords without uppercase letters fail validation."""
        no_uppercase_passwords = [
            "lowercase123!",
            "password123$",
            "test!ng567#",
            "secure@password123",
            "my!complex123password",
            "all-lower-case-123!",
        ]

        for password in no_uppercase_passwords:
            assert not validate_password_complexity(
                password
            ), f"Password '{password}' should be invalid (no uppercase)"

    def test_passwords_missing_lowercase(self):
        """Test that passwords without lowercase letters fail validation."""
        no_lowercase_passwords = [
            "UPPERCASE123!",
            "PASSWORD123$",
            "TEST!NG567#",
            "SECURE@PASSWORD123",
            "MY!COMPLEX123PASSWORD",
            "ALL-UPPER-CASE-123!",
        ]

        for password in no_lowercase_passwords:
            assert not validate_password_complexity(
                password
            ), f"Password '{password}' should be invalid (no lowercase)"

    def test_passwords_missing_digits(self):
        """Test that passwords without digits fail validation."""
        no_digits_passwords = [
            "NoNumbers!Pass",
            "Password!@#$",
            "SecurePass!@#",
            "MyComplex!Password",
            "TestPassword!@#$",
            "NoDigits!Here@",
        ]

        for password in no_digits_passwords:
            assert not validate_password_complexity(
                password
            ), f"Password '{password}' should be invalid (no digits)"

    def test_passwords_missing_special_chars(self):
        """Test that passwords without special characters fail validation."""
        no_special_passwords = [
            "NoSpecial123Pass",
            "Password123ABC",
            "SecurePass123ABC",
            "MyComplex123Password",
            "TestPassword123DEF",
            "NoSpecials123Here",
        ]

        for password in no_special_passwords:
            assert not validate_password_complexity(
                password
            ), f"Password '{password}' should be invalid (no special chars)"

    def test_edge_case_exactly_9_characters(self):
        """Test passwords that are exactly 9 characters."""
        exactly_9_char_passwords = [
            ("ValidP1!x", True),  # V-a-l-i-d-P-1-!-x = 9 chars
            ("Test123!A", True),  # T-e-s-t-1-2-3-!-A = 9 chars
            ("Weak123!x", True),  # W-e-a-k-1-2-3-!-x = 9 chars
            ("Strong1!x", True),  # S-t-r-o-n-g-1-!-x = 9 chars
            ("noupper1!", False),  # n-o-u-p-p-e-r-1-! = 9 chars - no uppercase
            ("NOLOWER1!", False),  # N-O-L-O-W-E-R-1-! = 9 chars - no lowercase
            ("NoDigits!", False),  # N-o-D-i-g-i-t-s-! = 9 chars - no digits
            ("NoSpec123", False),  # N-o-S-p-e-c-1-2-3 = 9 chars - no special chars
        ]

        for password, expected in exactly_9_char_passwords:
            assert (
                len(password) == 9
            ), f"Test setup error: '{password}' is not exactly 9 characters"
            actual = validate_password_complexity(password)
            assert (
                actual == expected
            ), f"Password '{password}' validation result should be {expected}, got {actual}"

    def test_all_required_special_characters(self):
        """Test that all documented special characters are accepted."""
        special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"

        for char in special_chars:
            password = f"ValidPass123{char}"
            assert validate_password_complexity(
                password
            ), f"Password with special char '{char}' should be valid"

    def test_multiple_failures(self):
        """Test passwords that fail multiple requirements."""
        multiple_failure_passwords = [
            "weak",  # Too short, no uppercase, no digits, no special chars
            "password",  # No uppercase, no digits, no special chars
            "123456",  # Too short, no letters, no special chars
            "PASSWORD",  # Too short, no lowercase, no digits, no special chars
            "Pass",  # Too short, no digits, no special chars
            "WEAK123",  # Too short, no lowercase, no special chars
        ]

        for password in multiple_failure_passwords:
            assert not validate_password_complexity(
                password
            ), f"Password '{password}' should be invalid (multiple failures)"

    def test_empty_and_whitespace_passwords(self):
        """Test edge cases with empty or whitespace-only passwords."""
        edge_case_passwords = [
            "",  # Empty
            " " * 9,  # Whitespace only
            " " * 15,  # Longer whitespace
            "\t\n\r   \t",  # Various whitespace chars
        ]

        for password in edge_case_passwords:
            assert not validate_password_complexity(
                password
            ), f"Password '{password}' should be invalid"

    def test_unicode_and_international_characters(self):
        """Test passwords with unicode and international characters."""
        unicode_passwords = [
            ("Pássw0rd123!", True),  # Valid with accented chars
            ("Ñoñó123!Pass", True),  # Valid with Spanish chars
            ("Тест123!Pass", True),  # Valid with Cyrillic chars
            ("密码123!Pass", True),  # Valid with Chinese chars
            ("🔒Secure123!", True),  # Valid with emoji
            ("Café123!Pass", True),  # Valid with French chars
            ("münchen123!", False),  # Invalid - no uppercase
            ("MÜNCHEN123!", False),  # Invalid - no lowercase
            ("Münchén!Pass", False),  # Invalid - no digits
            ("München123", False),  # Invalid - no special chars
        ]

        for password, expected in unicode_passwords:
            actual = validate_password_complexity(password)
            assert (
                actual == expected
            ), f"Unicode password '{password}' validation should be {expected}, got {actual}"


class TestGetPasswordRequirements:
    """Test password requirements retrieval function."""

    def test_returns_dict(self):
        """Test that function returns a dictionary."""
        requirements = get_password_requirements()
        assert isinstance(requirements, dict)

    def test_contains_required_keys(self):
        """Test that requirements dictionary contains all required keys."""
        requirements = get_password_requirements()

        required_keys = [
            "min_length",
            "require_uppercase",
            "require_lowercase",
            "require_digits",
            "require_special_chars",
            "special_chars",
            "description",
        ]

        for key in required_keys:
            assert key in requirements, f"Requirements should contain key '{key}'"

    def test_min_length_value(self):
        """Test that minimum length is correct."""
        requirements = get_password_requirements()
        assert requirements["min_length"] == 9

    def test_boolean_requirements(self):
        """Test that boolean requirements are all True."""
        requirements = get_password_requirements()

        boolean_keys = [
            "require_uppercase",
            "require_lowercase",
            "require_digits",
            "require_special_chars",
        ]

        for key in boolean_keys:
            assert requirements[key] is True, f"Requirement '{key}' should be True"

    def test_special_chars_string(self):
        """Test that special characters string is correct."""
        requirements = get_password_requirements()
        expected_special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        assert requirements["special_chars"] == expected_special_chars

    def test_description_exists(self):
        """Test that description exists and is non-empty string."""
        requirements = get_password_requirements()
        description = requirements["description"]

        assert isinstance(description, str)
        assert len(description) > 0
        assert "9 characters" in description
        assert "uppercase" in description
        assert "lowercase" in description
        assert "digit" in description
        assert "special character" in description


class TestGetPasswordComplexityErrorMessage:
    """Test password complexity error message function."""

    def test_returns_string(self):
        """Test that function returns a string."""
        message = get_password_complexity_error_message()
        assert isinstance(message, str)

    def test_message_not_empty(self):
        """Test that error message is not empty."""
        message = get_password_complexity_error_message()
        assert len(message) > 0

    def test_message_contains_requirements(self):
        """Test that error message contains all requirement details."""
        message = get_password_complexity_error_message()

        required_elements = [
            "9 characters",
            "uppercase",
            "lowercase",
            "digit",
            "special character",
            "!@#$%^&*()_+-=[]{}|;:,.<>?",
        ]

        for element in required_elements:
            assert element in message, f"Error message should contain '{element}'"

    def test_message_consistency_with_requirements(self):
        """Test that error message is consistent with requirements."""
        requirements = get_password_requirements()
        message = get_password_complexity_error_message()

        # Check that minimum length matches
        assert str(requirements["min_length"]) in message

        # Check that special chars match
        assert requirements["special_chars"] in message

    def test_message_user_friendly(self):
        """Test that error message is user-friendly."""
        message = get_password_complexity_error_message()

        # Should be a complete sentence
        assert message.endswith(".")

        # Should use clear language
        user_friendly_terms = ["must", "at least", "contain"]
        for term in user_friendly_terms:
            assert (
                term in message.lower()
            ), f"Message should contain user-friendly term '{term}'"


class TestPasswordValidatorIntegration:
    """Integration tests for password validator components."""

    def test_validate_against_requirements(self):
        """Test that validation logic matches documented requirements."""
        requirements = get_password_requirements()

        # Create a password that meets all requirements from the spec
        test_password = "A" + "a" + "1" + "!" + "x" * (requirements["min_length"] - 4)

        assert validate_password_complexity(
            test_password
        ), "Password built from requirements should be valid"

    def test_error_message_matches_validation_logic(self):
        """Test that error message accurately describes validation logic."""
        # Test each requirement mentioned in error message
        message = get_password_complexity_error_message()

        # Length requirement
        if "9 characters" in message:
            assert not validate_password_complexity(
                "Test123!"
            ), "8 char password should fail"
            assert validate_password_complexity(
                "Test123!A"
            ), "9 char password should pass"

        # Case requirements
        if "uppercase" in message:
            assert not validate_password_complexity(
                "nouppercasepass123!"
            ), "No uppercase should fail"

        if "lowercase" in message:
            assert not validate_password_complexity(
                "NOLOWERCASEPASS123!"
            ), "No lowercase should fail"

        # Digit requirement
        if "digit" in message:
            assert not validate_password_complexity(
                "NoDigitsPass!"
            ), "No digits should fail"

        # Special char requirement
        if "special character" in message:
            assert not validate_password_complexity(
                "NoSpecialChars123"
            ), "No special chars should fail"

    def test_comprehensive_password_scenarios(self):
        """Test comprehensive real-world password scenarios."""
        test_scenarios = [
            # Common weak passwords that should fail
            ("password", False, "Common weak password"),
            ("123456789", False, "All numbers"),
            ("qwertyuiop", False, "Keyboard pattern"),
            ("Password123", False, "Missing special chars"),
            ("PASSWORD123!", False, "Missing lowercase"),
            ("password123!", False, "Missing uppercase"),
            ("Password!@#", False, "Missing digits"),
            ("Pass123!", False, "Too short"),
            # Strong passwords that should pass
            ("MySecure123!Pass", True, "Strong password"),
            ("C0mpl3x!P@ssw0rd", True, "Complex password"),
            ("Str0ng&Secure!2024", True, "Very strong password"),
            ("Test!ng123#Here", True, "Valid test password"),
            ("Qwerty123!@#", True, "Valid with common base"),
            ("MyP@ssw0rd123!", True, "Valid with special chars"),
            # Edge cases that should pass
            ("A1!bcdefg", True, "Minimum valid length"),
            ("Test123!!" * 5, True, "Very long password"),
            ("Ñoñó123!Pass", True, "International characters"),
        ]

        for password, expected, description in test_scenarios:
            actual = validate_password_complexity(password)
            assert (
                actual == expected
            ), f"{description}: Password '{password}' should be {expected}, got {actual}"

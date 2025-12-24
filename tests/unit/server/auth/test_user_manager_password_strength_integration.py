"""
Integration tests for UserManager with password strength validation.

Tests that the UserManager properly integrates with the new PasswordStrengthValidator
for both user creation and password changes.
"""

import pytest
import tempfile
import os
from code_indexer.server.auth.user_manager import UserManager, UserRole


class TestUserManagerPasswordStrengthIntegration:
    """Test integration between UserManager and PasswordStrengthValidator."""

    def setup_method(self):
        """Set up test fixtures with temporary users file."""
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_file.write(b"{}")  # Initialize with empty JSON object
        self.temp_file.close()
        self.user_manager = UserManager(users_file_path=self.temp_file.name)

    def teardown_method(self):
        """Clean up temporary files."""
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)

    def test_create_user_with_strong_password_succeeds(self):
        """Test that creating a user with a strong password succeeds."""
        username = "testuser"
        strong_password = "MyStr0ng!P@ssw0rd2024"
        role = UserRole.NORMAL_USER

        # Should succeed
        user = self.user_manager.create_user(username, strong_password, role)

        assert user.username == username
        assert user.role == role
        assert user.password_hash != strong_password  # Should be hashed

    def test_create_user_with_weak_password_fails(self):
        """Test that creating a user with a weak password fails."""
        username = "testuser"
        weak_password = "weak123"  # Too short, missing uppercase and special chars
        role = UserRole.NORMAL_USER

        # Should fail with detailed error message
        with pytest.raises(ValueError) as exc_info:
            self.user_manager.create_user(username, weak_password, role)

        error_message = str(exc_info.value)
        assert "Password does not meet security requirements" in error_message
        assert "12 characters" in error_message
        assert "uppercase" in error_message
        assert "special character" in error_message

    def test_create_user_password_contains_username_fails(self):
        """Test that password containing username is rejected."""
        username = "johndoe"
        password_with_username = "JohnDoe12345!@#"  # Contains username
        role = UserRole.NORMAL_USER

        # Should fail due to personal information
        with pytest.raises(ValueError) as exc_info:
            self.user_manager.create_user(username, password_with_username, role)

        error_message = str(exc_info.value)
        assert "personal information" in error_message.lower()

    def test_create_user_with_common_password_fails(self):
        """Test that common passwords are rejected."""
        username = "testuser"
        common_password = "Password123!@#$"  # Common password with sufficient length
        role = UserRole.NORMAL_USER

        # Should fail due to common password detection
        with pytest.raises(ValueError) as exc_info:
            self.user_manager.create_user(username, common_password, role)

        error_message = str(exc_info.value)
        assert "common" in error_message.lower()

    def test_change_password_with_strong_password_succeeds(self):
        """Test that changing to a strong password succeeds."""
        username = "testuser"
        initial_password = "InitialStr0ng!P@ss"
        new_strong_password = "NewStr0ng!P@ssw0rd2024"
        role = UserRole.NORMAL_USER

        # Create user with initial strong password
        self.user_manager.create_user(username, initial_password, role)

        # Change to new strong password should succeed
        result = self.user_manager.change_password(username, new_strong_password)
        assert result is True

    def test_change_password_with_weak_password_fails(self):
        """Test that changing to a weak password fails."""
        username = "testuser"
        initial_password = "InitialStr0ng!P@ss"
        weak_new_password = "weak"
        role = UserRole.NORMAL_USER

        # Create user with initial strong password
        self.user_manager.create_user(username, initial_password, role)

        # Change to weak password should fail
        with pytest.raises(ValueError) as exc_info:
            self.user_manager.change_password(username, weak_new_password)

        error_message = str(exc_info.value)
        assert "Password does not meet security requirements" in error_message

    def test_change_password_with_personal_info_fails(self):
        """Test that changing to password with personal info fails."""
        username = "johndoe"
        initial_password = "InitialStr0ng!P@ss"
        personal_password = "JohnDoe2024!@#$"
        role = UserRole.NORMAL_USER

        # Create user with initial strong password
        self.user_manager.create_user(username, initial_password, role)

        # Change to password with personal info should fail
        with pytest.raises(ValueError) as exc_info:
            self.user_manager.change_password(username, personal_password)

        error_message = str(exc_info.value)
        assert "personal information" in error_message.lower()

    def test_validate_password_strength_method(self):
        """Test the password strength validation method."""
        username = "testuser"

        # Test strong password
        strong_password = "MyStr0ng!P@ssw0rd2024"
        result = self.user_manager.validate_password_strength(strong_password, username)

        assert result["valid"] is True
        assert result["score"] >= 4
        assert result["strength"] == "strong"
        assert len(result["issues"]) == 0
        assert "requirements" in result

        # Test weak password
        weak_password = "weak"
        result = self.user_manager.validate_password_strength(weak_password, username)

        assert result["valid"] is False
        assert result["score"] < 4
        assert result["strength"] == "weak"
        assert len(result["issues"]) > 0
        assert len(result["suggestions"]) > 0
        assert result["entropy"] >= 0

    def test_password_suggestions_provided(self):
        """Test that password suggestions are provided for weak passwords."""
        weak_password = "weak123"
        result = self.user_manager.validate_password_strength(weak_password)

        assert not result["valid"]
        assert len(result["suggestions"]) > 0

        # Should suggest improvements
        suggestions_text = " ".join(result["suggestions"]).lower()
        assert any(
            keyword in suggestions_text
            for keyword in ["longer", "uppercase", "special"]
        )

    def test_requirements_specification(self):
        """Test that password requirements are properly specified."""
        result = self.user_manager.validate_password_strength("test")
        requirements = result["requirements"]

        assert requirements["min_length"] == 12
        assert requirements["require_uppercase"] is True
        assert requirements["require_lowercase"] is True
        assert requirements["require_digits"] is True
        assert requirements["require_special_chars"] is True
        assert "description" in requirements

    def test_entropy_calculation_integration(self):
        """Test that entropy calculation is integrated properly."""
        # Test different entropy levels
        test_cases = [
            ("a" * 12, 0),  # All same character = 0 entropy
            ("MyStr0ng!P@ssw0rd2024", 50),  # Should have high entropy
        ]

        for password, min_expected_entropy in test_cases:
            result = self.user_manager.validate_password_strength(password)
            if min_expected_entropy == 0:
                assert (
                    result["entropy"] == 0
                ), f"Password '{password}' should have 0 entropy"
            else:
                assert (
                    result["entropy"] >= min_expected_entropy
                ), f"Password '{password}' should have entropy >= {min_expected_entropy}"

    def test_multiple_password_validations_performance(self):
        """Test that multiple password validations perform well."""
        import time

        passwords = [
            "TestPassword123!",
            "AnotherStr0ng!P@ss",
            "FinalP@ssw0rd2024#",
        ]

        start_time = time.time()
        for password in passwords * 10:  # Test 30 validations
            self.user_manager.validate_password_strength(password, "testuser")
        end_time = time.time()

        total_time = end_time - start_time
        # Should complete 30 validations in reasonable time
        assert (
            total_time < 1.0
        ), f"30 password validations took {total_time:.2f}s, should be < 1.0s"

    def test_backward_compatibility_with_existing_password_validator(self):
        """Test that new system is more restrictive than old system."""
        # These passwords pass the old validator (9 chars) but should fail new one (12 chars)
        old_style_passwords = [
            "Test123!A",  # 9 chars - valid in old system
            "Pass123!B",  # 9 chars - valid in old system
        ]

        for password in old_style_passwords:
            result = self.user_manager.validate_password_strength(password)
            assert not result[
                "valid"
            ], f"Password '{password}' should be rejected by new 12-char requirement"
            assert any("12 character" in issue for issue in result["issues"])

    def test_error_message_formatting(self):
        """Test that error messages are properly formatted with issues and suggestions."""
        username = "testuser"
        weak_password = "short"
        role = UserRole.NORMAL_USER

        with pytest.raises(ValueError) as exc_info:
            self.user_manager.create_user(username, weak_password, role)

        error_message = str(exc_info.value)

        # Should contain formatted error message
        assert "Password does not meet security requirements:" in error_message
        assert "- " in error_message  # Should have bullet points for issues
        assert "Suggestions:" in error_message

        # Should contain specific issues
        assert "12 character" in error_message
        assert "uppercase" in error_message
        assert "special character" in error_message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Integration tests for password management functionality.

Tests the integration between CLI commands, password policy validation,
and API client methods to ensure end-to-end functionality works correctly.
"""

import pytest
from pathlib import Path

from code_indexer.password_policy import (
    PasswordPolicy,
    validate_password_strength,
    get_password_policy_help,
)
from code_indexer.api_clients.auth_client import AuthAPIClient


class TestPasswordPolicyIntegration:
    """Test password policy integration with the full system."""

    def test_password_policy_validation_with_cli_import(self):
        """Test that CLI can import and use password validation."""
        # Import the validation function as the CLI does
        from code_indexer.password_policy import validate_password_strength

        # Test with a valid password
        is_valid, message = validate_password_strength("ValidPass123!")
        assert is_valid
        assert message == "Password meets requirements"

        # Test with an invalid password
        is_valid, message = validate_password_strength("weak")
        assert not is_valid
        assert "Must be at least 8 characters long" in message

    def test_password_policy_help_integration(self):
        """Test that password policy help can be imported and used."""
        from code_indexer.password_policy import get_password_policy_help

        help_text = get_password_policy_help()
        assert isinstance(help_text, str)
        assert "8 characters" in help_text
        assert "numbers" in help_text
        assert "special characters" in help_text

    def test_auth_client_password_methods_integration(self):
        """Test that AuthAPIClient password methods are properly integrated."""
        server_url = "https://test.example.com"
        project_root = Path("/test/project")
        credentials = {"username": "testuser", "password": "testpass"}

        client = AuthAPIClient(
            server_url=server_url, project_root=project_root, credentials=credentials
        )

        # Verify methods exist
        assert hasattr(client, "change_password")
        assert hasattr(client, "reset_password")

        # Verify they're async methods
        import asyncio

        assert asyncio.iscoroutinefunction(client.change_password)
        assert asyncio.iscoroutinefunction(client.reset_password)

    def test_end_to_end_password_validation_workflow(self):
        """Test the complete password validation workflow."""
        # Simulate the workflow that would happen in the CLI

        # Step 1: User enters a weak password
        user_password = "weak"
        is_valid, message = validate_password_strength(user_password)
        assert not is_valid
        assert "Must be at least 8 characters long" in message

        # Step 2: User gets help
        help_text = get_password_policy_help()
        assert "8 characters" in help_text

        # Step 3: User enters a password missing numbers
        user_password = "NoNumbers!"
        is_valid, message = validate_password_strength(user_password)
        assert not is_valid
        assert "Must contain numbers" in message

        # Step 4: User enters a password missing special characters
        user_password = "NoSpecials123"
        is_valid, message = validate_password_strength(user_password)
        assert not is_valid
        assert "Must contain special characters" in message

        # Step 5: User enters a valid password
        user_password = "ValidPass123!"
        is_valid, message = validate_password_strength(user_password)
        assert is_valid
        assert message == "Password meets requirements"

    def test_password_policy_configuration_values(self):
        """Test that password policy values match expected requirements."""
        # These values should match what's documented in the story
        assert PasswordPolicy.MIN_LENGTH == 8
        assert PasswordPolicy.REQUIRE_NUMBERS is True
        assert PasswordPolicy.REQUIRE_SYMBOLS is True

        # Valid special characters should include common ones
        valid_chars = PasswordPolicy.VALID_SPECIAL_CHARS
        assert "!" in valid_chars
        assert "@" in valid_chars
        assert "#" in valid_chars
        assert "$" in valid_chars
        assert "%" in valid_chars
        assert "^" in valid_chars
        assert "&" in valid_chars
        assert "*" in valid_chars

    def test_story_acceptance_criteria_passwords(self):
        """Test passwords from the story acceptance criteria."""
        # From the story, these should be valid
        valid_passwords = [
            "ValidPass123!",
            "Another1@Valid",
            "Complex$Password99",
        ]

        for password in valid_passwords:
            is_valid, message = validate_password_strength(password)
            assert is_valid, f"Password '{password}' should be valid: {message}"

        # From the story, these should be invalid
        invalid_passwords = [
            ("short", "Must be at least 8 characters long"),
            ("NoNumbers!", "Must contain numbers"),
            ("NoSpecials123", "Must contain special characters"),
        ]

        for password, expected_error in invalid_passwords:
            is_valid, message = validate_password_strength(password)
            assert not is_valid, f"Password '{password}' should be invalid"
            assert expected_error in message

    def test_authentication_client_integration(self):
        """Test that authentication client integrates with password operations."""
        # This tests the integration points mentioned in the story
        from code_indexer.api_clients.auth_client import (
            AuthAPIClient,
            create_auth_client,
        )

        # Test that create_auth_client works
        server_url = "https://test.example.com"
        project_root = Path("/test/project")

        client = create_auth_client(server_url, project_root)
        assert isinstance(client, AuthAPIClient)
        assert client.server_url == server_url
        assert client.project_root == project_root

    def test_cli_imports_work_correctly(self):
        """Test that all CLI imports work as expected."""
        # Test imports that would be used in the CLI commands
        try:
            from code_indexer.api_clients.auth_client import AuthAPIClient
            from code_indexer.mode_detection.command_mode_detector import (
                find_project_root,
            )
            from code_indexer.password_policy import validate_password_strength
            from code_indexer.password_policy import get_password_policy_help

            # All imports should work without errors
            assert True

        except ImportError as e:
            pytest.fail(f"CLI import failed: {e}")

    def test_error_message_consistency(self):
        """Test that error messages are consistent across the system."""
        # Test that the error messages match what's expected in the story
        error_cases = [
            ("", "Must be at least 8 characters long"),
            ("1234567", "Must be at least 8 characters long"),
            ("NoNumbers!", "Must contain numbers"),
            ("NoSpecials123", "Must contain special characters"),
        ]

        for password, expected_fragment in error_cases:
            is_valid, message = validate_password_strength(password)
            assert not is_valid
            assert expected_fragment in message

    def test_password_strength_feedback_integration(self):
        """Test password strength feedback functionality."""
        # Test the feedback functionality
        feedback = PasswordPolicy.get_strength_feedback("weak")
        assert isinstance(feedback, list)
        assert len(feedback) > 0

        # Test with a strong password
        feedback = PasswordPolicy.get_strength_feedback("StrongPass123!")
        assert isinstance(feedback, list)
        assert any("meets all requirements" in f for f in feedback)

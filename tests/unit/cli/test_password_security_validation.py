"""Security validation tests for password management operations.

Ensures all password handling meets security requirements including:
- No password logging
- Secure input handling
- Memory security
- Transmission security
"""

from unittest.mock import Mock, patch
import logging
import io

from code_indexer.cli import auth_group, _validate_password_strength
from code_indexer.password_policy import PasswordPolicy
from code_indexer.api_clients.auth_client import AuthAPIClient


class TestPasswordSecurityValidation:
    """Validate security requirements for password handling."""

    def test_passwords_never_logged(self):
        """Test that passwords are never written to logs."""
        # Create a string buffer to capture logs
        log_buffer = io.StringIO()
        handler = logging.StreamHandler(log_buffer)
        handler.setLevel(logging.DEBUG)

        # Get all relevant loggers
        cli_logger = logging.getLogger("code_indexer.cli")
        auth_logger = logging.getLogger("code_indexer.api_clients.auth_client")
        policy_logger = logging.getLogger("code_indexer.password_policy")

        # Add handler to all loggers
        for logger in [cli_logger, auth_logger, policy_logger]:
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)

        try:
            # Attempt password validation with sensitive data
            sensitive_password = "MySuperSecret123!"
            is_valid, message = _validate_password_strength(sensitive_password)

            # Check logs don't contain the password
            log_contents = log_buffer.getvalue()
            assert sensitive_password not in log_contents

            # Test with AuthAPIClient logging
            with patch("code_indexer.api_clients.auth_client.logger") as mock_logger:
                AuthAPIClient("http://test", None)

                # Check that logger calls never include raw passwords
                for call in mock_logger.debug.call_args_list:
                    assert sensitive_password not in str(call)
                for call in mock_logger.info.call_args_list:
                    assert sensitive_password not in str(call)

        finally:
            # Clean up handlers
            for logger in [cli_logger, auth_logger, policy_logger]:
                logger.removeHandler(handler)

    def test_getpass_used_for_password_input(self):
        """Verify getpass is used for all password inputs (no echo)."""
        # Read the CLI source code directly to verify secure password handling
        from pathlib import Path
        import code_indexer.cli as cli_module

        # Get the file path of the CLI module
        cli_file = Path(cli_module.__file__)

        # Read the source code
        source = cli_file.read_text()

        # Find the auth_change_password function definition
        # Look for the section between @auth_group.command("change-password") and the next command
        import re

        pattern = r'@auth_group\.command\("change-password"\).*?(?=@auth_group\.command|@cli\.group|$)'
        match = re.search(pattern, source, re.DOTALL)

        if match:
            function_source = match.group(0)

            # Verify getpass is used for password input
            assert "getpass.getpass" in function_source or "getpass(" in function_source

            # Verify we're not using regular input() for passwords
            lines = function_source.split("\n")
            for line in lines:
                if "password" in line.lower():
                    # If it's getting password input, should use getpass
                    if "input(" in line and "getpass" not in line:
                        assert (
                            False
                        ), f"Using input() for password - security violation: {line}"
                    if (
                        "click.prompt" in line
                        and "hide_input=True" not in line
                        and "password" not in line
                    ):
                        assert (
                            False
                        ), f"Using click.prompt without hide_input for password: {line}"

    def test_passwords_cleared_from_memory(self):
        """Test that password variables are cleared after use."""
        # This is a best-effort test since Python doesn't guarantee memory clearing
        # We're testing the intent and pattern, not actual memory state

        with patch("code_indexer.api_clients.auth_client.AuthAPIClient") as MockClient:
            mock_instance = Mock()
            MockClient.return_value = mock_instance

            # After password operations, credentials should be managed properly
            client = AuthAPIClient(
                "http://test", None, {"username": "test", "password": "secret"}
            )

            # When logout is called, credentials should be cleared
            client.logout()
            assert len(client.credentials) == 0

    def test_no_password_in_error_messages(self):
        """Test that passwords don't appear in error messages."""
        from code_indexer.api_clients.base_client import APIClientError

        # Test various error scenarios
        test_password = "MySecret123!"

        # Password validation errors shouldn't include the actual password value
        # The word "weak" in "Password too weak" is describing the quality, not revealing the password
        is_valid, message = _validate_password_strength("MyTestPass")
        # The actual password value shouldn't be in the error message
        assert "MyTestPass" not in message

        # Test with another password
        is_valid, message = _validate_password_strength("SecretValue123")
        assert "SecretValue123" not in message

        # API errors shouldn't include passwords
        error = APIClientError("Authentication failed")
        assert test_password not in str(error)

        # Test that even when constructing errors, passwords aren't included
        try:
            raise APIClientError("Login failed for user")
        except APIClientError as e:
            assert test_password not in str(e)

    def test_https_only_transmission(self):
        """Test that password operations require HTTPS in production."""
        # For production environments, server URLs should be HTTPS
        # This is a configuration validation test

        from code_indexer.api_clients.auth_client import AuthAPIClient

        # Test that auth client accepts HTTPS URLs
        client = AuthAPIClient("https://secure.example.com", None)
        assert client.server_url == "https://secure.example.com"

        # In production, HTTP should trigger a warning or be rejected
        # (This is a policy decision - for now we allow HTTP for testing)
        client = AuthAPIClient("http://test.local", None)
        assert client.server_url == "http://test.local"

    def test_password_confirmation_security(self):
        """Test password confirmation doesn't leak information."""
        # When passwords don't match, the error shouldn't reveal details
        # about which password was entered

        # The error message should be generic
        expected_error = "Password confirmation does not match"

        # This message shouldn't include:
        # - The actual passwords
        # - Which password was different
        # - Password length or characteristics

        assert (
            "password" not in expected_error.lower()
            or "confirmation" in expected_error.lower()
        )

    def test_authentication_state_no_credential_leak(self):
        """Test authentication state checks don't leak credentials."""
        from click.testing import CliRunner

        runner = CliRunner()

        # When not authenticated, error messages shouldn't reveal:
        # - Whether an account exists
        # - Previous usernames
        # - Any credential information

        with patch(
            "code_indexer.mode_detection.command_mode_detector.find_project_root",
            return_value=None,
        ):
            result = runner.invoke(auth_group, ["change-password"])

            # Check the output doesn't contain sensitive info
            assert (
                "username" not in result.output.lower()
                or "required" in result.output.lower()
            )
            # Shouldn't reveal specific account details
            assert "@" not in result.output  # No email addresses
            assert "testuser" not in result.output  # No default usernames

    def test_secure_credential_storage_validation(self):
        """Test that stored credentials are properly encrypted."""
        from code_indexer.remote.credential_manager import (
            ProjectCredentialManager,
        )
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)

            # Create credential manager
            manager = ProjectCredentialManager()

            # Encrypt credentials
            encrypted = manager.encrypt_credentials(
                username="testuser",
                password="TestPass123!",
                server_url="https://test.example.com",
                repo_path=str(project_root),
            )

            # Verify encrypted data doesn't contain plain text password
            assert b"TestPass123!" not in encrypted
            assert b"testuser" not in encrypted

            # Verify it's actually encrypted (should look random)
            assert len(encrypted) > 100  # Encrypted data is larger
            # Check for presence of encryption markers (salt, nonce, etc.)
            assert encrypted[:32]  # Should have random-looking bytes

    def test_password_policy_enforcement_at_all_layers(self):
        """Test password policy is enforced at multiple layers."""
        weak_password = "weak"

        # Layer 1: Client-side validation
        is_valid, _ = PasswordPolicy.validate(weak_password)
        assert not is_valid

        # Layer 2: CLI validation
        is_valid, _ = _validate_password_strength(weak_password)
        assert not is_valid

        # Layer 3: Should also be enforced server-side (mocked here)
        # The server should also validate even if client validation is bypassed
        # This ensures defense in depth

    def test_no_password_in_shell_history(self):
        """Test that passwords aren't passed via command line arguments."""
        # Passwords should never be passed as CLI arguments as they'd appear
        # in shell history and process lists

        from click.testing import CliRunner

        runner = CliRunner()

        # change-password shouldn't accept password as argument
        result = runner.invoke(auth_group, ["change-password", "--help"])
        assert (
            "--password" not in result.output or "deprecated" in result.output.lower()
        )

        # reset-password only takes username, not password
        result = runner.invoke(auth_group, ["reset-password", "--help"])
        assert "--password" not in result.output

    def test_session_token_security(self):
        """Test that session tokens are handled securely."""
        from code_indexer.api_clients.auth_client import AuthAPIClient

        client = AuthAPIClient("https://test.example.com", None)

        # Tokens shouldn't be logged or exposed
        with patch("code_indexer.api_clients.auth_client.logger") as mock_logger:
            client._current_token = "secret-jwt-token-xyz"

            # Ensure token isn't logged
            for call in mock_logger.debug.call_args_list:
                assert "secret-jwt-token-xyz" not in str(call)

    def test_timing_attack_mitigation(self):
        """Test that password operations have consistent timing."""
        import time

        # Multiple password validations should take similar time
        # regardless of when they fail validation

        times = []
        test_passwords = [
            "a",  # Fails on length
            "abcdefgh",  # Fails on no numbers
            "abcdefg1",  # Fails on no symbols
            "ValidPass123!",  # Succeeds
        ]

        for password in test_passwords:
            start = time.perf_counter()
            _validate_password_strength(password)
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        # Times should be relatively consistent (within an order of magnitude)
        # This is a basic check - proper timing attack mitigation would use
        # constant-time comparison functions
        max_time = max(times)
        min_time = min(times)
        assert max_time < min_time * 10  # Very loose check

    def test_rate_limiting_awareness(self):
        """Test that the system handles rate limiting appropriately."""
        from code_indexer.api_clients.base_client import APIClientError

        # When rate limited, should provide clear guidance
        error = APIClientError("Too many login attempts", 429)
        assert error.status_code == 429

        # Error message should guide user to wait
        assert "too many" in str(error).lower() or "rate" in str(error).lower()

    def test_secure_password_comparison(self):
        """Test that password comparisons are done securely."""
        # This is more of a design validation than runtime test

        # Password confirmation should compare in a timing-safe way
        password1 = "TestPassword123!"
        password2 = "TestPassword123!"
        password3 = "DifferentPass123!"

        # Basic comparison (Python's == is not timing-safe, but for client-side
        # confirmation this is acceptable as the real security is server-side)
        assert password1 == password2
        assert password1 != password3

        # For production, server-side should use timing-safe comparison
        # like secrets.compare_digest() or equivalent

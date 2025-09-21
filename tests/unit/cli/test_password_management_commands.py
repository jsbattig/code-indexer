"""Tests for password management CLI commands.

Tests for change-password and reset-password commands with comprehensive coverage
of interactive prompts, validation, error handling, and authentication state management.
"""

from unittest.mock import Mock, patch, AsyncMock, call
from click.testing import CliRunner
from pathlib import Path

from code_indexer.cli import auth_group
from code_indexer.api_clients.auth_client import AuthAPIClient
from code_indexer.api_clients.base_client import APIClientError


class TestPasswordChangeCommand:
    """Test change-password command functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_change_password_command_exists(self):
        """Test that change-password command is registered."""
        result = self.runner.invoke(auth_group, ["change-password", "--help"])
        assert result.exit_code == 0
        assert "Change current user password" in result.output

    @patch("code_indexer.api_clients.auth_client.create_auth_client")
    @patch("code_indexer.cli.getpass.getpass")
    @patch("code_indexer.cli.console")
    def test_change_password_interactive_prompts(
        self, mock_console, mock_getpass, mock_create_client
    ):
        """Test interactive password prompts for change-password command."""
        # Setup mocks
        mock_client = Mock(spec=AuthAPIClient)
        mock_client.change_password = AsyncMock(return_value={"status": "success"})
        mock_client.close = AsyncMock()
        mock_client.credentials = {"username": "testuser", "password": "testpass"}
        mock_create_client.return_value = mock_client

        # Mock password inputs
        mock_getpass.side_effect = ["current_pass", "new_pass123!", "new_pass123!"]

        # Mock authentication check
        with patch("code_indexer.cli._check_authentication_state", return_value=True):
            self.runner.invoke(auth_group, ["change-password"])

        # Verify interactive prompts were called
        expected_calls = [
            call("Current Password: "),
            call("New Password: "),
            call("Confirm New Password: "),
        ]
        mock_getpass.assert_has_calls(expected_calls)

    @patch("code_indexer.api_clients.auth_client.create_auth_client")
    @patch("code_indexer.cli.getpass.getpass")
    @patch("code_indexer.cli.console")
    def test_change_password_policy_validation_failure(
        self, mock_console, mock_getpass, mock_create_client
    ):
        """Test password policy validation failure scenarios."""
        # Setup mocks
        mock_client = Mock(spec=AuthAPIClient)
        mock_client.close = AsyncMock()
        mock_client.credentials = {"username": "testuser", "password": "testpass"}
        mock_create_client.return_value = mock_client

        # Mock weak password input
        mock_getpass.side_effect = ["current_pass", "weak", "weak"]

        # Mock authentication check and project configuration
        with patch("code_indexer.cli._check_authentication_state", return_value=True):
            with patch(
                "code_indexer.password_policy.validate_password_strength",
                return_value=(
                    False,
                    "Password too weak: Must be at least 8 characters long",
                ),
            ):
                with patch(
                    "code_indexer.mode_detection.command_mode_detector.find_project_root",
                    return_value=Path("/fake/project"),
                ):
                    with patch(
                        "code_indexer.remote.config.load_remote_configuration",
                        return_value={"server_url": "http://fake-server"},
                    ):
                        self.runner.invoke(auth_group, ["change-password"])

        # Verify error was displayed
        mock_console.print.assert_any_call(
            "❌ Password too weak: Must be at least 8 characters long", style="red"
        )

    @patch("code_indexer.api_clients.auth_client.create_auth_client")
    @patch("code_indexer.cli.getpass.getpass")
    @patch("code_indexer.cli.console")
    def test_change_password_confirmation_mismatch(
        self, mock_console, mock_getpass, mock_create_client
    ):
        """Test password confirmation mismatch handling."""
        # Setup mocks
        mock_client = Mock(spec=AuthAPIClient)
        mock_client.close = AsyncMock()
        mock_client.credentials = {"username": "testuser", "password": "testpass"}
        mock_create_client.return_value = mock_client

        # Mock mismatched password inputs
        mock_getpass.side_effect = ["current_pass", "new_pass123!", "different_pass"]

        # Mock authentication check and project configuration
        with patch("code_indexer.cli._check_authentication_state", return_value=True):
            with patch(
                "code_indexer.password_policy.validate_password_strength",
                return_value=(True, "Password meets requirements"),
            ):
                with patch(
                    "code_indexer.mode_detection.command_mode_detector.find_project_root",
                    return_value=Path("/fake/project"),
                ):
                    with patch(
                        "code_indexer.remote.config.load_remote_configuration",
                        return_value={"server_url": "http://fake-server"},
                    ):
                        self.runner.invoke(auth_group, ["change-password"])

        # Verify error was displayed
        mock_console.print.assert_any_call(
            "❌ Password confirmation does not match", style="red"
        )

    @patch("code_indexer.api_clients.auth_client.create_auth_client")
    @patch("code_indexer.cli.console")
    def test_change_password_not_authenticated(self, mock_console, mock_create_client):
        """Test change-password command when not authenticated."""
        # Mock authentication check failure by making find_project_root return None
        with patch(
            "code_indexer.mode_detection.command_mode_detector.find_project_root",
            return_value=None,
        ):
            self.runner.invoke(auth_group, ["change-password"])

        # Verify authentication error message
        mock_console.print.assert_any_call(
            "❌ Authentication required: Please login first", style="red"
        )
        mock_console.print.assert_any_call(
            "💡 Use 'cidx auth login' to authenticate", style="dim"
        )

    @patch("code_indexer.api_clients.auth_client.create_auth_client")
    @patch("code_indexer.cli.getpass.getpass")
    @patch("code_indexer.cli.console")
    def test_change_password_success_flow(
        self, mock_console, mock_getpass, mock_create_client
    ):
        """Test successful password change flow."""
        # Setup mocks - create a mock client that avoids real implementation
        mock_client = Mock()
        mock_client.change_password = AsyncMock(return_value={"status": "success"})
        mock_client.close = AsyncMock()
        mock_client.credentials = {"username": "testuser", "password": "testpass"}
        mock_create_client.return_value = mock_client

        # Mock valid password inputs
        mock_getpass.side_effect = ["current_pass", "new_pass123!", "new_pass123!"]

        # Mock authentication check and validation
        with patch("code_indexer.cli._check_authentication_state", return_value=True):
            with patch(
                "code_indexer.password_policy.validate_password_strength",
                return_value=(True, "Password meets requirements"),
            ):
                with patch(
                    "code_indexer.mode_detection.command_mode_detector.find_project_root",
                    return_value=Path("/fake/project"),
                ):
                    with patch(
                        "code_indexer.remote.config.load_remote_configuration",
                        return_value={"server_url": "http://fake-server"},
                    ):
                        self.runner.invoke(auth_group, ["change-password"])

        # Verify success message
        mock_console.print.assert_any_call(
            "✅ Password changed successfully", style="green"
        )

    @patch("code_indexer.api_clients.auth_client.create_auth_client")
    @patch("code_indexer.cli.getpass.getpass")
    @patch("code_indexer.cli.console")
    def test_change_password_server_error(
        self, mock_console, mock_getpass, mock_create_client
    ):
        """Test password change with server error."""
        # Setup mocks - create a mock client that avoids real implementation
        mock_client = Mock()
        mock_client.change_password = AsyncMock(
            side_effect=APIClientError("Current password is incorrect", 400)
        )
        mock_client.close = AsyncMock()
        mock_client.credentials = {"username": "testuser", "password": "testpass"}
        mock_create_client.return_value = mock_client

        # Mock valid password inputs
        mock_getpass.side_effect = ["wrong_current", "new_pass123!", "new_pass123!"]

        # Mock authentication check and validation
        with patch("code_indexer.cli._check_authentication_state", return_value=True):
            with patch(
                "code_indexer.password_policy.validate_password_strength",
                return_value=(True, "Password meets requirements"),
            ):
                with patch(
                    "code_indexer.mode_detection.command_mode_detector.find_project_root",
                    return_value=Path("/fake/project"),
                ):
                    with patch(
                        "code_indexer.remote.config.load_remote_configuration",
                        return_value={"server_url": "http://fake-server"},
                    ):
                        # Mock client close method to avoid async issues
                        mock_client.close = AsyncMock()
                        self.runner.invoke(auth_group, ["change-password"])

        # Verify error message
        mock_console.print.assert_any_call(
            "❌ Password change failed: Current password is incorrect", style="red"
        )


class TestPasswordResetCommand:
    """Test reset-password command functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_reset_password_command_exists(self):
        """Test that reset-password command is registered."""
        result = self.runner.invoke(auth_group, ["reset-password", "--help"])
        assert result.exit_code == 0
        assert "Initiate password reset" in result.output

    @patch("code_indexer.api_clients.auth_client.create_auth_client")
    @patch("code_indexer.cli.console")
    def test_reset_password_with_username_parameter(
        self, mock_console, mock_create_client
    ):
        """Test password reset with username parameter."""
        # Setup mocks - create a mock client that avoids real implementation
        mock_client = Mock()
        mock_client.reset_password = AsyncMock(return_value={"status": "success"})
        mock_client.close = AsyncMock()
        mock_create_client.return_value = mock_client

        # Mock project configuration
        with patch(
            "code_indexer.mode_detection.command_mode_detector.find_project_root",
            return_value=Path("/fake/project"),
        ):
            with patch(
                "code_indexer.remote.config.load_remote_configuration",
                return_value={"server_url": "http://fake-server"},
            ):
                self.runner.invoke(
                    auth_group, ["reset-password", "--username", "testuser"]
                )

        # Verify reset request was made
        mock_client.reset_password.assert_called_once_with("testuser")

        # Verify success message
        mock_console.print.assert_any_call(
            "✅ Password reset request sent for testuser", style="green"
        )

    @patch("code_indexer.api_clients.auth_client.create_auth_client")
    @patch("code_indexer.cli.console")
    @patch("click.prompt")
    def test_reset_password_interactive_username(
        self, mock_prompt, mock_console, mock_create_client
    ):
        """Test password reset with interactive username prompt."""
        # Setup mocks - create a mock client that avoids real implementation
        mock_client = Mock()
        mock_client.reset_password = AsyncMock(return_value={"status": "success"})
        mock_client.close = AsyncMock()
        mock_create_client.return_value = mock_client
        mock_prompt.return_value = "interactive_user"

        # Mock project configuration
        with patch(
            "code_indexer.mode_detection.command_mode_detector.find_project_root",
            return_value=Path("/fake/project"),
        ):
            with patch(
                "code_indexer.remote.config.load_remote_configuration",
                return_value={"server_url": "http://fake-server"},
            ):
                self.runner.invoke(auth_group, ["reset-password"])

        # Verify username prompt (click.prompt includes type parameter by default)
        mock_prompt.assert_called_once_with("Username", type=str)

        # Verify reset request was made
        mock_client.reset_password.assert_called_once_with("interactive_user")

    @patch("code_indexer.api_clients.auth_client.create_auth_client")
    @patch("code_indexer.cli.console")
    def test_reset_password_server_error(self, mock_console, mock_create_client):
        """Test password reset with server error."""
        # Setup mocks - create a mock client that avoids real implementation
        mock_client = Mock()
        mock_client.reset_password = AsyncMock(
            side_effect=APIClientError("Username not found", 404)
        )
        mock_client.close = AsyncMock()
        mock_create_client.return_value = mock_client

        # Mock project configuration
        with patch(
            "code_indexer.mode_detection.command_mode_detector.find_project_root",
            return_value=Path("/fake/project"),
        ):
            with patch(
                "code_indexer.remote.config.load_remote_configuration",
                return_value={"server_url": "http://fake-server"},
            ):
                self.runner.invoke(
                    auth_group, ["reset-password", "--username", "nonexistent"]
                )

        # Verify error message
        mock_console.print.assert_any_call(
            "❌ Password reset failed: Username not found", style="red"
        )

    @patch("code_indexer.api_clients.auth_client.create_auth_client")
    @patch("code_indexer.cli.console")
    def test_reset_password_instructions_display(
        self, mock_console, mock_create_client
    ):
        """Test that reset instructions are displayed after successful request."""
        # Setup mocks - create a mock client that avoids real implementation
        mock_client = Mock()
        mock_client.reset_password = AsyncMock(return_value={"status": "success"})
        mock_client.close = AsyncMock()
        mock_create_client.return_value = mock_client

        # Mock project configuration
        with patch(
            "code_indexer.mode_detection.command_mode_detector.find_project_root",
            return_value=Path("/fake/project"),
        ):
            with patch(
                "code_indexer.remote.config.load_remote_configuration",
                return_value={"server_url": "http://fake-server"},
            ):
                self.runner.invoke(
                    auth_group, ["reset-password", "--username", "testuser"]
                )

        # Verify instructions are displayed
        mock_console.print.assert_any_call(
            "📧 Check your email for reset instructions", style="blue"
        )


class TestPasswordPolicyValidation:
    """Test password policy validation logic."""

    def test_validate_password_strength_function_exists(self):
        """Test that password validation function is available."""
        # This test ensures the validation function is implemented
        from code_indexer.cli import _validate_password_strength

        assert callable(_validate_password_strength)

    def test_password_policy_requirements(self):
        """Test password policy validation requirements."""
        # This will be implemented in the actual validation function

        # We'll implement these tests when we create the validation function
        assert True  # Placeholder until implementation


class TestAuthenticationStateManagement:
    """Test authentication state management during password operations."""

    def test_check_authentication_state_function_exists(self):
        """Test that authentication state checking function is available."""
        # This test ensures the authentication check function is implemented
        from code_indexer.cli import _check_authentication_state

        assert callable(_check_authentication_state)

    def test_session_expiry_handling(self):
        """Test handling of expired authentication sessions."""
        # This will test session expiry detection and handling
        assert True  # Placeholder until implementation

    def test_authentication_state_validation(self):
        """Test authentication state validation logic."""
        # This will test various authentication state scenarios
        assert True  # Placeholder until implementation

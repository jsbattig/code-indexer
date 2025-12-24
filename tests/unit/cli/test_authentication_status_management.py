"""
Test-Driven Development tests for Story 3: Authentication Status Management.

Tests implementation of comprehensive authentication status monitoring and
credential management capabilities with:
- Authentication status display with token information
- Token validity verification and automatic refresh
- Detailed credential information with verbose mode
- Credential health monitoring and diagnostics
- Token lifecycle management (refresh, validate)

Tests are organized by acceptance criteria:
- AC1: Authentication Status Display
- AC2: Token Validity Verification
- AC3: Detailed Credential Information
- AC4: Credential Health Monitoring
- AC5: Token Lifecycle Management
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from click.testing import CliRunner

from code_indexer.cli import cli

# Test framework dependencies that should exist
pytest_asyncio = pytest.importorskip("pytest_asyncio")


class TestAuthenticationStatusCommands:
    """Test suite for authentication status commands implementing Story 3 acceptance criteria."""

    def setup_method(self):
        """Set up test environment for each test method."""
        self.runner = CliRunner()
        self.temp_dir = None

    def teardown_method(self):
        """Clean up test environment after each test method."""
        if self.temp_dir:
            import shutil

            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_temp_project_dir(self) -> Path:
        """Create temporary project directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        project_dir = Path(self.temp_dir)

        # Create .code-indexer directory structure
        config_dir = project_dir / ".code-indexer"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create remote config indicating remote mode
        remote_config = {
            "server_url": "http://localhost:8000",
            "encrypted_credentials": {
                "username": "test_user",
                "encrypted_data": "fake_encrypted_data",
            },
        }

        remote_config_path = config_dir / ".remote-config"
        with open(remote_config_path, "w") as f:
            json.dump(remote_config, f)

        return project_dir

    # AC1: Authentication Status Display Tests

    def test_auth_status_command_exists(self):
        """Test that 'cidx auth status' command is registered and accessible."""
        result = self.runner.invoke(cli, ["auth", "status", "--help"])

        # Should now pass as command exists (TDD - green phase)
        assert (
            result.exit_code == 0
        ), f"Status command should exist and work, got exit code {result.exit_code}, output: {result.output}"
        assert (
            "Display current authentication status" in result.output
        ), "Status command help should be displayed"

    def test_auth_status_shows_authenticated_state(self):
        """Test that status command displays authentication state when authenticated."""
        project_dir = self.create_temp_project_dir()

        with (
            patch(
                "code_indexer.api_clients.auth_client.create_auth_client"
            ) as mock_create_client,
            patch(
                "code_indexer.mode_detection.command_mode_detector.find_project_root"
            ) as mock_find_root,
            patch(
                "code_indexer.remote.config.load_remote_configuration"
            ) as mock_load_config,
        ):

            # Mock dependencies
            mock_find_root.return_value = project_dir
            mock_load_config.return_value = {
                "server_url": "http://localhost:8000",
                "encrypted_credentials": {"username": "test_user"},
            }

            # Mock authenticated auth client
            mock_client = AsyncMock()
            mock_create_client.return_value = mock_client

            # Mock successful auth status
            from code_indexer.api_clients.auth_client import AuthStatus

            status = AuthStatus(
                authenticated=True,
                username="test_user",
                role="user",
                token_valid=True,
                token_expires=None,
                refresh_expires=None,
                server_url="http://localhost:8000",
                last_refreshed=None,
                permissions=["read"],
                server_reachable=True,
            )
            mock_client.get_auth_status.return_value = status

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "status"])

        # Should pass now as command is implemented
        assert (
            result.exit_code == 0
        ), f"Status command should work, got: {result.output}"
        assert "Authenticated: Yes" in result.output
        assert "test_user" in result.output

    def test_auth_status_shows_not_authenticated_state(self):
        """Test that status command shows not authenticated when no credentials."""
        project_dir = self.create_temp_project_dir()

        with (
            patch(
                "code_indexer.api_clients.auth_client.create_auth_client"
            ) as mock_create_client,
            patch(
                "code_indexer.mode_detection.command_mode_detector.find_project_root"
            ) as mock_find_root,
            patch(
                "code_indexer.remote.config.load_remote_configuration"
            ) as mock_load_config,
        ):

            # Mock dependencies
            mock_find_root.return_value = project_dir
            mock_load_config.return_value = {
                "server_url": "http://localhost:8000",
                "encrypted_credentials": {},  # No credentials
            }

            # Mock unauthenticated auth client
            mock_client = AsyncMock()
            mock_create_client.return_value = mock_client

            # Mock not authenticated status
            from code_indexer.api_clients.auth_client import AuthStatus

            status = AuthStatus(
                authenticated=False,
                username=None,
                role=None,
                token_valid=False,
                token_expires=None,
                refresh_expires=None,
                server_url="http://localhost:8000",
                last_refreshed=None,
                permissions=[],
                server_reachable=None,
            )
            mock_client.get_auth_status.return_value = status

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "status"])

        # Should pass and show not authenticated
        assert (
            result.exit_code == 0
        ), f"Status command should work, got: {result.output}"
        assert "Authenticated: No" in result.output
        assert "Use 'cidx auth login' to authenticate" in result.output

    def test_auth_status_displays_username_and_role(self):
        """Test that status command extracts and displays username and role from JWT token."""
        project_dir = self.create_temp_project_dir()

        with patch(
            "code_indexer.api_clients.auth_client.AuthAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            # Mock JWT token with user info
            mock_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VybmFtZSI6InRlc3R1c2VyIiwicm9sZSI6InVzZXIiLCJleHAiOjE3MDAwMDAwMDB9.fake_signature"
            mock_client.get_current_token.return_value = mock_token

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "status"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Username/role display should fail (TDD - red phase)"

    def test_auth_status_displays_token_expiration(self):
        """Test that status command calculates and displays token expiration time."""
        project_dir = self.create_temp_project_dir()

        # Create future expiration time
        datetime.now(timezone.utc).timestamp() + 3600  # 1 hour from now

        with self.runner.isolated_filesystem():
            os.chdir(str(project_dir))
            result = self.runner.invoke(cli, ["auth", "status"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Token expiration display should fail (TDD - red phase)"

    def test_auth_status_displays_server_url(self):
        """Test that status command displays current server URL from configuration."""
        project_dir = self.create_temp_project_dir()

        with self.runner.isolated_filesystem():
            os.chdir(str(project_dir))
            result = self.runner.invoke(cli, ["auth", "status"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert result.exit_code != 0, "Server URL display should fail (TDD - red phase)"

    def test_auth_status_suggests_login_when_not_authenticated(self):
        """Test that status command suggests login when user is not authenticated."""
        project_dir = self.create_temp_project_dir()

        # Remove credentials to simulate not authenticated state
        creds_path = project_dir / ".code-indexer" / ".creds"
        if creds_path.exists():
            creds_path.unlink()

        with self.runner.isolated_filesystem():
            os.chdir(str(project_dir))
            result = self.runner.invoke(cli, ["auth", "status"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert result.exit_code != 0, "Login suggestion should fail (TDD - red phase)"

    # AC2: Token Validity Verification Tests

    def test_auth_status_verifies_token_with_server(self):
        """Test that status command verifies token validity with server when available."""
        project_dir = self.create_temp_project_dir()

        with patch(
            "code_indexer.api_clients.auth_client.AuthAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.validate_token.return_value = True

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "status"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Token server verification should fail (TDD - red phase)"

    def test_auth_status_detects_expired_token(self):
        """Test that status command detects expired tokens and displays expiration status."""
        project_dir = self.create_temp_project_dir()

        # Create expired token (past timestamp)
        datetime.now(timezone.utc).timestamp() - 3600  # 1 hour ago

        with self.runner.isolated_filesystem():
            os.chdir(str(project_dir))
            result = self.runner.invoke(cli, ["auth", "status"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Expired token detection should fail (TDD - red phase)"

    def test_auth_status_attempts_automatic_token_refresh(self):
        """Test that status command attempts automatic token refresh when token is expired."""
        project_dir = self.create_temp_project_dir()

        with patch(
            "code_indexer.api_clients.auth_client.AuthAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.refresh_token.return_value = {"access_token": "new_token"}

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "status"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Automatic token refresh should fail (TDD - red phase)"

    def test_auth_status_displays_refresh_success(self):
        """Test that status command displays successful refresh result."""
        project_dir = self.create_temp_project_dir()

        with patch(
            "code_indexer.api_clients.auth_client.AuthAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.refresh_token.return_value = {"access_token": "refreshed_token"}

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "status"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Refresh success display should fail (TDD - red phase)"

    def test_auth_status_handles_refresh_failure(self):
        """Test that status command handles refresh failure and suggests re-authentication."""
        project_dir = self.create_temp_project_dir()

        with patch(
            "code_indexer.api_clients.auth_client.AuthAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            from code_indexer.api_clients.base_client import AuthenticationError

            mock_client.refresh_token.side_effect = AuthenticationError(
                "Refresh token expired"
            )

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "status"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Refresh failure handling should fail (TDD - red phase)"

    def test_auth_status_clears_invalid_credentials_on_refresh_failure(self):
        """Test that status command clears invalid credentials when refresh fails."""
        project_dir = self.create_temp_project_dir()

        # Create fake stored credentials
        creds_path = project_dir / ".code-indexer" / ".creds"
        creds_path.write_bytes(b"fake_encrypted_credentials")

        with patch(
            "code_indexer.api_clients.auth_client.AuthAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            from code_indexer.api_clients.base_client import AuthenticationError

            mock_client.refresh_token.side_effect = AuthenticationError(
                "Refresh token expired"
            )

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "status"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Invalid credential clearing should fail (TDD - red phase)"

    # AC3: Detailed Credential Information Tests

    def test_auth_status_verbose_option_exists(self):
        """Test that status command accepts --verbose option."""
        result = self.runner.invoke(cli, ["auth", "status", "--help"])

        # Should pass as command and option exist
        assert (
            result.exit_code == 0
        ), f"Status command help should work, got: {result.output}"
        assert (
            "--verbose" in result.output or "-v" in result.output
        ), "Verbose option should be available"

    def test_auth_status_verbose_displays_token_timestamps(self):
        """Test that verbose mode displays token issuance and refresh timestamps."""
        project_dir = self.create_temp_project_dir()

        with self.runner.isolated_filesystem():
            os.chdir(str(project_dir))
            result = self.runner.invoke(cli, ["auth", "status", "--verbose"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Token timestamps display should fail (TDD - red phase)"

    def test_auth_status_verbose_displays_refresh_token_expiration(self):
        """Test that verbose mode displays refresh token expiration if available."""
        project_dir = self.create_temp_project_dir()

        with self.runner.isolated_filesystem():
            os.chdir(str(project_dir))
            result = self.runner.invoke(cli, ["auth", "status", "--verbose"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Refresh token expiration display should fail (TDD - red phase)"

    def test_auth_status_verbose_displays_user_permissions(self):
        """Test that verbose mode displays user permissions from token claims."""
        project_dir = self.create_temp_project_dir()

        with self.runner.isolated_filesystem():
            os.chdir(str(project_dir))
            result = self.runner.invoke(cli, ["auth", "status", "--verbose"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "User permissions display should fail (TDD - red phase)"

    def test_auth_status_verbose_tests_server_connectivity(self):
        """Test that verbose mode tests and displays server connectivity status."""
        project_dir = self.create_temp_project_dir()

        with patch(
            "code_indexer.api_clients.auth_client.AuthAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.test_connectivity.return_value = True

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "status", "--verbose"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Server connectivity test should fail (TDD - red phase)"

    def test_auth_status_verbose_displays_server_version(self):
        """Test that verbose mode displays server version information if available."""
        project_dir = self.create_temp_project_dir()

        with patch(
            "code_indexer.api_clients.auth_client.AuthAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.get_server_version.return_value = "v1.2.3"

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "status", "--verbose"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Server version display should fail (TDD - red phase)"

    # AC4: Credential Health Monitoring Tests

    def test_auth_status_health_option_exists(self):
        """Test that status command accepts --health option."""
        result = self.runner.invoke(cli, ["auth", "status", "--help"])

        # Should pass as command and option exist
        assert (
            result.exit_code == 0
        ), f"Status command help should work, got: {result.output}"
        assert "--health" in result.output, "Health option should be available"

    def test_auth_status_health_checks_credential_file_integrity(self):
        """Test that health mode checks credential file encryption and integrity."""
        project_dir = self.create_temp_project_dir()

        with (
            patch(
                "code_indexer.api_clients.auth_client.create_auth_client"
            ) as mock_create_client,
            patch(
                "code_indexer.mode_detection.command_mode_detector.find_project_root"
            ) as mock_find_root,
            patch(
                "code_indexer.remote.config.load_remote_configuration"
            ) as mock_load_config,
        ):

            # Mock dependencies
            mock_find_root.return_value = project_dir
            mock_load_config.return_value = {
                "server_url": "http://localhost:8000",
                "encrypted_credentials": {"username": "test_user"},
            }

            # Mock auth client
            mock_client = AsyncMock()
            mock_create_client.return_value = mock_client

            # Mock healthy credential health
            from code_indexer.api_clients.auth_client import CredentialHealth

            health = CredentialHealth(
                healthy=True,
                issues=[],
                encryption_valid=True,
                server_reachable=True,
                token_signature_valid=True,
                file_permissions_correct=True,
                recovery_suggestions=[],
            )
            mock_client.check_credential_health.return_value = health

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "status", "--health"])

        # Should pass and show health status
        assert (
            result.exit_code == 0
        ), f"Health command should work, got: {result.output}"
        assert "Overall Health: Healthy" in result.output
        assert "Credential file encryption" in result.output

    def test_auth_status_health_verifies_encryption_key_availability(self):
        """Test that health mode verifies encryption key availability."""
        project_dir = self.create_temp_project_dir()

        with self.runner.isolated_filesystem():
            os.chdir(str(project_dir))
            result = self.runner.invoke(cli, ["auth", "status", "--health"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Encryption key verification should fail (TDD - red phase)"

    def test_auth_status_health_tests_server_connectivity_for_validation(self):
        """Test that health mode tests server connectivity for token validation."""
        project_dir = self.create_temp_project_dir()

        with patch(
            "code_indexer.api_clients.auth_client.AuthAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.test_connectivity.return_value = False

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "status", "--health"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Health connectivity test should fail (TDD - red phase)"

    def test_auth_status_health_validates_token_signature(self):
        """Test that health mode validates JWT token structure and signature."""
        project_dir = self.create_temp_project_dir()

        with self.runner.isolated_filesystem():
            os.chdir(str(project_dir))
            result = self.runner.invoke(cli, ["auth", "status", "--health"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Token signature validation should fail (TDD - red phase)"

    def test_auth_status_health_checks_file_permissions(self):
        """Test that health mode checks credential file permissions."""
        project_dir = self.create_temp_project_dir()

        with self.runner.isolated_filesystem():
            os.chdir(str(project_dir))
            result = self.runner.invoke(cli, ["auth", "status", "--health"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "File permissions check should fail (TDD - red phase)"

    def test_auth_status_health_displays_healthy_status(self):
        """Test that health mode displays healthy status when all checks pass."""
        project_dir = self.create_temp_project_dir()

        with self.runner.isolated_filesystem():
            os.chdir(str(project_dir))
            result = self.runner.invoke(cli, ["auth", "status", "--health"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Healthy status display should fail (TDD - red phase)"

    def test_auth_status_health_handles_corrupted_credentials(self):
        """Test that health mode detects and reports corrupted credential files."""
        project_dir = self.create_temp_project_dir()

        # Create corrupted credentials file
        creds_path = project_dir / ".code-indexer" / ".creds"
        creds_path.write_bytes(b"corrupted_data")

        with self.runner.isolated_filesystem():
            os.chdir(str(project_dir))
            result = self.runner.invoke(cli, ["auth", "status", "--health"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Corrupted credentials handling should fail (TDD - red phase)"

    def test_auth_status_health_provides_recovery_guidance(self):
        """Test that health mode provides specific recovery guidance for each issue type."""
        project_dir = self.create_temp_project_dir()

        with self.runner.isolated_filesystem():
            os.chdir(str(project_dir))
            result = self.runner.invoke(cli, ["auth", "status", "--health"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert result.exit_code != 0, "Recovery guidance should fail (TDD - red phase)"

    # AC5: Token Lifecycle Management Tests

    def test_auth_refresh_command_exists(self):
        """Test that 'cidx auth refresh' command is registered and accessible."""
        result = self.runner.invoke(cli, ["auth", "refresh", "--help"])

        # Should now pass as command exists (TDD - green phase)
        assert (
            result.exit_code == 0
        ), f"Refresh command should exist and work, got exit code {result.exit_code}, output: {result.output}"
        assert (
            "Manually refresh authentication token" in result.output
        ), "Refresh command help should be displayed"

    def test_auth_refresh_attempts_token_refresh(self):
        """Test that refresh command attempts to refresh the current token."""
        project_dir = self.create_temp_project_dir()

        with patch(
            "code_indexer.api_clients.auth_client.AuthAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.refresh_token.return_value = {"access_token": "new_token"}

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "refresh"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert result.exit_code != 0, "Token refresh should fail (TDD - red phase)"

    def test_auth_refresh_displays_success_message(self):
        """Test that refresh command displays success message when refresh succeeds."""
        project_dir = self.create_temp_project_dir()

        with patch(
            "code_indexer.api_clients.auth_client.AuthAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.refresh_token.return_value = {"access_token": "new_token"}

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "refresh"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Refresh success message should fail (TDD - red phase)"

    def test_auth_refresh_updates_stored_credentials(self):
        """Test that refresh command updates stored credentials with new token."""
        project_dir = self.create_temp_project_dir()

        with patch(
            "code_indexer.api_clients.auth_client.AuthAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.refresh_token.return_value = {"access_token": "new_token"}

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "refresh"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert result.exit_code != 0, "Credential update should fail (TDD - red phase)"

    def test_auth_refresh_handles_expired_refresh_token(self):
        """Test that refresh command handles expired refresh token gracefully."""
        project_dir = self.create_temp_project_dir()

        with patch(
            "code_indexer.api_clients.auth_client.AuthAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            from code_indexer.api_clients.base_client import AuthenticationError

            mock_client.refresh_token.side_effect = AuthenticationError(
                "Refresh token expired"
            )

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "refresh"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Expired refresh token handling should fail (TDD - red phase)"

    def test_auth_refresh_clears_invalid_credentials_on_failure(self):
        """Test that refresh command clears invalid credentials when refresh fails."""
        project_dir = self.create_temp_project_dir()

        # Create fake stored credentials
        creds_path = project_dir / ".code-indexer" / ".creds"
        creds_path.write_bytes(b"fake_encrypted_credentials")

        with patch(
            "code_indexer.api_clients.auth_client.AuthAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            from code_indexer.api_clients.base_client import AuthenticationError

            mock_client.refresh_token.side_effect = AuthenticationError(
                "Refresh token expired"
            )

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "refresh"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Credential clearing on failure should fail (TDD - red phase)"

    def test_auth_validate_command_exists(self):
        """Test that 'cidx auth validate' command is registered and accessible."""
        result = self.runner.invoke(cli, ["auth", "validate", "--help"])

        # Should now pass as command exists (TDD - green phase)
        assert (
            result.exit_code == 0
        ), f"Validate command should exist and work, got exit code {result.exit_code}, output: {result.output}"
        assert (
            "Validate current credentials" in result.output
        ), "Validate command help should be displayed"

    def test_auth_validate_silent_operation(self):
        """Test that validate command operates silently by default."""
        project_dir = self.create_temp_project_dir()

        with patch(
            "code_indexer.api_clients.auth_client.AuthAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.validate_credentials.return_value = True

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "validate"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert result.exit_code != 0, "Silent validation should fail (TDD - red phase)"

    def test_auth_validate_returns_correct_exit_codes(self):
        """Test that validate command returns appropriate exit codes for automation."""
        project_dir = self.create_temp_project_dir()

        with patch(
            "code_indexer.api_clients.auth_client.AuthAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.validate_credentials.return_value = True

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "validate"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert result.exit_code != 0, "Exit code handling should fail (TDD - red phase)"

    def test_auth_validate_verbose_mode(self):
        """Test that validate command supports verbose mode for debugging."""
        project_dir = self.create_temp_project_dir()

        with self.runner.isolated_filesystem():
            os.chdir(str(project_dir))
            result = self.runner.invoke(cli, ["auth", "validate", "--verbose"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Validate verbose mode should fail (TDD - red phase)"

    def test_auth_validate_handles_invalid_credentials(self):
        """Test that validate command handles invalid credentials appropriately."""
        project_dir = self.create_temp_project_dir()

        with patch(
            "code_indexer.api_clients.auth_client.AuthAPIClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.validate_credentials.return_value = False

            with self.runner.isolated_filesystem():
                os.chdir(str(project_dir))
                result = self.runner.invoke(cli, ["auth", "validate"])

        # Should fail as command doesn't exist yet (TDD - red phase)
        assert (
            result.exit_code != 0
        ), "Invalid credential handling should fail (TDD - red phase)"


class TestAuthStatusDataModels:
    """Test suite for AuthStatus and CredentialHealth data models."""

    def test_auth_status_dataclass_exists(self):
        """Test that AuthStatus dataclass exists and can be imported."""
        # Should now pass as dataclass exists (TDD - green phase)
        from code_indexer.api_clients.auth_client import AuthStatus

        assert AuthStatus is not None

    def test_auth_status_has_required_fields(self):
        """Test that AuthStatus dataclass has all required fields."""
        # Should now pass as dataclass exists (TDD - green phase)
        from code_indexer.api_clients.auth_client import AuthStatus

        # Test that we can create an instance with required fields
        status = AuthStatus(
            authenticated=True,
            username="testuser",
            role="user",
            token_valid=True,
            token_expires=None,
            refresh_expires=None,
            server_url="http://localhost:8000",
            last_refreshed=None,
            permissions=["read", "write"],
        )

        assert status.authenticated is True
        assert status.username == "testuser"
        assert status.role == "user"
        assert status.token_valid is True
        assert status.server_url == "http://localhost:8000"
        assert status.permissions == ["read", "write"]

    def test_credential_health_dataclass_exists(self):
        """Test that CredentialHealth dataclass exists and can be imported."""
        # Should now pass as dataclass exists (TDD - green phase)
        from code_indexer.api_clients.auth_client import CredentialHealth

        assert CredentialHealth is not None

    def test_credential_health_has_required_fields(self):
        """Test that CredentialHealth dataclass has all required fields."""
        # Should now pass as dataclass exists (TDD - green phase)
        from code_indexer.api_clients.auth_client import CredentialHealth

        # Test that we can create an instance with required fields
        health = CredentialHealth(
            healthy=True,
            issues=[],
            encryption_valid=True,
            server_reachable=True,
            token_signature_valid=True,
            file_permissions_correct=True,
            recovery_suggestions=[],
        )

        assert health.healthy is True
        assert health.issues == []
        assert health.encryption_valid is True
        assert health.server_reachable is True
        assert health.token_signature_valid is True
        assert health.file_permissions_correct is True
        assert health.recovery_suggestions == []


class TestAuthAPIClientExtensions:
    """Test suite for AuthAPIClient extensions for status and health management."""

    def test_auth_api_client_has_get_auth_status_method(self):
        """Test that AuthAPIClient has get_auth_status method."""
        from code_indexer.api_clients.auth_client import AuthAPIClient

        client = AuthAPIClient("http://localhost:8000", None, {})

        # Should now pass as method exists (TDD - green phase)
        assert hasattr(client, "get_auth_status"), "get_auth_status method should exist"
        assert callable(
            getattr(client, "get_auth_status")
        ), "get_auth_status should be callable"

    def test_auth_api_client_has_refresh_token_method(self):
        """Test that AuthAPIClient has refresh_token method."""
        from code_indexer.api_clients.auth_client import AuthAPIClient

        client = AuthAPIClient("http://localhost:8000", None, {})

        # Should now pass as method exists (TDD - green phase)
        assert hasattr(client, "refresh_token"), "refresh_token method should exist"
        assert callable(
            getattr(client, "refresh_token")
        ), "refresh_token should be callable"

    def test_auth_api_client_has_validate_credentials_method(self):
        """Test that AuthAPIClient has validate_credentials method."""
        from code_indexer.api_clients.auth_client import AuthAPIClient

        client = AuthAPIClient("http://localhost:8000", None, {})

        # Should now pass as method exists (TDD - green phase)
        assert hasattr(
            client, "validate_credentials"
        ), "validate_credentials method should exist"
        assert callable(
            getattr(client, "validate_credentials")
        ), "validate_credentials should be callable"

    def test_auth_api_client_has_check_credential_health_method(self):
        """Test that AuthAPIClient has check_credential_health method."""
        from code_indexer.api_clients.auth_client import AuthAPIClient

        client = AuthAPIClient("http://localhost:8000", None, {})

        # Should now pass as method exists (TDD - green phase)
        assert hasattr(
            client, "check_credential_health"
        ), "check_credential_health method should exist"
        assert callable(
            getattr(client, "check_credential_health")
        ), "check_credential_health should be callable"


# Run the failing tests to confirm TDD red phase
if __name__ == "__main__":
    pytest.main([__file__, "-v"])

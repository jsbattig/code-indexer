"""Tests for CLI remote initialization functionality.

Following TDD principles - these tests define the expected behavior
for remote mode initialization including parameter validation,
server URL validation, connectivity testing, and credential validation.
"""

import json
import subprocess
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import httpx

from code_indexer.api_clients.base_client import (
    CIDXRemoteAPIClient,
    APIClientError,
    AuthenticationError,
)


class TestRemoteInitParameterValidation:
    """Test parameter validation for remote initialization."""

    def run_init_command(self, args, cwd=None, expect_failure=False):
        """Run init command and return result."""
        cmd = [sys.executable, "-m", "code_indexer.cli", "init"] + args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=cwd,
        )

        if expect_failure:
            assert (
                result.returncode != 0
            ), f"Command should have failed: {' '.join(cmd)}"
        else:
            assert (
                result.returncode == 0
            ), f"Command failed: {result.stderr}\nStdout: {result.stdout}"

        return result

    def test_remote_flag_without_username_fails(self):
        """Test that --remote without --username fails with clear error message."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)

            result = self.run_init_command(
                ["--remote", "https://cidx.example.com", "--password", "secret123"],
                cwd=test_dir,
                expect_failure=True,
            )

            # Should fail with clear error message
            assert (
                "Remote initialization requires --username and --password"
                in result.stdout
            )
            assert (
                "Usage: cidx init --remote <server-url> --username <user> --password <pass>"
                in result.stdout
            )

            # Should provide example (check key components due to line wrapping)
            assert "cidx init --remote" in result.stdout
            assert "https://cidx.example.com" in result.stdout
            assert "--username john" in result.stdout
            assert "--password" in result.stdout

            # Should not create any configuration files
            config_dir = test_dir / ".code-indexer"
            assert not config_dir.exists()

    def test_remote_flag_without_password_fails(self):
        """Test that --remote without --password fails with clear error message."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)

            result = self.run_init_command(
                ["--remote", "https://cidx.example.com", "--username", "testuser"],
                cwd=test_dir,
                expect_failure=True,
            )

            # Should fail with clear error message
            assert (
                "Remote initialization requires --username and --password"
                in result.stdout
            )
            assert (
                "Usage: cidx init --remote <server-url> --username <user> --password <pass>"
                in result.stdout
            )

            # Should not create any configuration files
            config_dir = test_dir / ".code-indexer"
            assert not config_dir.exists()

    def test_remote_flag_without_credentials_fails(self):
        """Test that --remote without both --username and --password fails."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)

            result = self.run_init_command(
                ["--remote", "https://cidx.example.com"],
                cwd=test_dir,
                expect_failure=True,
            )

            # Should fail with clear error message
            assert (
                "Remote initialization requires --username and --password"
                in result.stdout
            )

            # Should not create any configuration files
            config_dir = test_dir / ".code-indexer"
            assert not config_dir.exists()

    def test_remote_initialization_help_shows_parameters(self):
        """Test that help shows remote, username, and password parameters."""
        result = subprocess.run(
            [sys.executable, "-m", "code_indexer.cli", "init", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "--remote" in result.stdout
        assert "--username" in result.stdout
        assert "--password" in result.stdout
        assert "Remote Mode" in result.stdout or "remote mode" in result.stdout


class TestServerURLValidation:
    """Test server URL validation and normalization."""

    def test_validate_and_normalize_url_adds_https_by_default(self):
        """Test URL validation adds HTTPS protocol by default."""
        # This test will fail until we implement the functionality
        from code_indexer.remote.url_validator import validate_and_normalize_server_url

        result = validate_and_normalize_server_url("cidx.example.com")
        assert result == "https://cidx.example.com"

    def test_validate_and_normalize_url_preserves_https(self):
        """Test URL validation preserves existing HTTPS protocol."""
        from code_indexer.remote.url_validator import validate_and_normalize_server_url

        result = validate_and_normalize_server_url("https://cidx.example.com")
        assert result == "https://cidx.example.com"

    def test_validate_and_normalize_url_preserves_http(self):
        """Test URL validation preserves existing HTTP protocol."""
        from code_indexer.remote.url_validator import validate_and_normalize_server_url

        result = validate_and_normalize_server_url("http://cidx.example.com")
        assert result == "http://cidx.example.com"

    def test_validate_and_normalize_url_removes_trailing_slash(self):
        """Test URL validation removes trailing slashes."""
        from code_indexer.remote.url_validator import validate_and_normalize_server_url

        result = validate_and_normalize_server_url("https://cidx.example.com/")
        assert result == "https://cidx.example.com"

        result = validate_and_normalize_server_url("https://cidx.example.com///")
        assert result == "https://cidx.example.com"

    def test_validate_and_normalize_url_handles_port_numbers(self):
        """Test URL validation handles port numbers correctly."""
        from code_indexer.remote.url_validator import validate_and_normalize_server_url

        result = validate_and_normalize_server_url("cidx.example.com:8080")
        assert result == "https://cidx.example.com:8080"

        result = validate_and_normalize_server_url("https://cidx.example.com:8080/")
        assert result == "https://cidx.example.com:8080"

    def test_validate_and_normalize_url_handles_paths(self):
        """Test URL validation handles paths correctly."""
        from code_indexer.remote.url_validator import validate_and_normalize_server_url

        result = validate_and_normalize_server_url("https://cidx.example.com/api")
        assert result == "https://cidx.example.com/api"

    def test_validate_and_normalize_url_rejects_invalid_protocols(self):
        """Test URL validation rejects invalid protocols."""
        from code_indexer.remote.url_validator import (
            validate_and_normalize_server_url,
            URLValidationError,
        )

        with pytest.raises(URLValidationError) as exc_info:
            validate_and_normalize_server_url("ftp://cidx.example.com")

        assert "Unsupported protocol" in str(exc_info.value)
        assert "Only HTTP and HTTPS are supported" in str(exc_info.value)

    def test_validate_and_normalize_url_rejects_malformed_urls(self):
        """Test URL validation rejects malformed URLs."""
        from code_indexer.remote.url_validator import (
            validate_and_normalize_server_url,
            URLValidationError,
        )

        with pytest.raises(URLValidationError) as exc_info:
            validate_and_normalize_server_url("not-a-valid-url")

        assert "Invalid URL format" in str(exc_info.value)

    def test_validate_and_normalize_url_rejects_empty_urls(self):
        """Test URL validation rejects empty or None URLs."""
        from code_indexer.remote.url_validator import (
            validate_and_normalize_server_url,
            URLValidationError,
        )

        with pytest.raises(URLValidationError):
            validate_and_normalize_server_url("")

        with pytest.raises(URLValidationError):
            validate_and_normalize_server_url(None)


class TestServerConnectivityTesting:
    """Test server connectivity validation."""

    @pytest.mark.asyncio
    async def test_server_connectivity_success(self):
        """Test successful server connectivity check."""
        from code_indexer.remote.connectivity import test_server_connectivity

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "ok"}
            mock_get.return_value = mock_response

            # Should not raise any exception
            await test_server_connectivity("https://cidx.example.com")

            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_server_connectivity_network_error(self):
        """Test server connectivity with network error."""
        from code_indexer.remote.connectivity import (
            test_server_connectivity,
            ServerConnectivityError,
        )

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.NetworkError("Connection failed")

            with pytest.raises(ServerConnectivityError) as exc_info:
                await test_server_connectivity("https://cidx.example.com")

            assert "Cannot connect to server" in str(exc_info.value)
            assert "Connection failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_server_connectivity_timeout_error(self):
        """Test server connectivity with timeout error."""
        from code_indexer.remote.connectivity import (
            test_server_connectivity,
            ServerConnectivityError,
        )

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Timeout")

            with pytest.raises(ServerConnectivityError) as exc_info:
                await test_server_connectivity("https://cidx.example.com")

            assert "Cannot connect to server" in str(exc_info.value)
            assert "Timeout" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_server_connectivity_unexpected_status_code(self):
        """Test server connectivity with unexpected HTTP status."""
        from code_indexer.remote.connectivity import (
            test_server_connectivity,
            ServerConnectivityError,
        )

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_get.return_value = mock_response

            with pytest.raises(ServerConnectivityError) as exc_info:
                await test_server_connectivity("https://cidx.example.com")

            assert "Server returned unexpected status" in str(exc_info.value)
            assert "500" in str(exc_info.value)


class TestCredentialValidation:
    """Test credential validation with server authentication."""

    @pytest.mark.asyncio
    async def test_credential_validation_success(self):
        """Test successful credential validation."""
        from code_indexer.remote.auth import validate_credentials

        with patch.object(CIDXRemoteAPIClient, "_authenticate") as mock_auth:
            mock_auth.return_value = "valid.jwt.token"

            # Should return user info on success
            user_info = await validate_credentials(
                "https://cidx.example.com", "testuser", "testpass123"
            )

            assert user_info is not None
            assert "username" in user_info
            mock_auth.assert_called_once()

    @pytest.mark.asyncio
    async def test_credential_validation_invalid_credentials(self):
        """Test credential validation with invalid credentials."""
        from code_indexer.remote.auth import (
            validate_credentials,
            CredentialValidationError,
        )

        with patch.object(CIDXRemoteAPIClient, "_authenticate") as mock_auth:
            mock_auth.side_effect = AuthenticationError("Invalid credentials")

            with pytest.raises(CredentialValidationError) as exc_info:
                await validate_credentials(
                    "https://cidx.example.com", "baduser", "badpass"
                )

            assert "Invalid credentials" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_credential_validation_server_error(self):
        """Test credential validation with server error."""
        from code_indexer.remote.auth import (
            validate_credentials,
            CredentialValidationError,
        )

        with patch.object(CIDXRemoteAPIClient, "_authenticate") as mock_auth:
            mock_auth.side_effect = APIClientError("Server error", status_code=500)

            with pytest.raises(CredentialValidationError) as exc_info:
                await validate_credentials(
                    "https://cidx.example.com", "testuser", "testpass123"
                )

            assert "Server error during authentication" in str(exc_info.value)


class TestRemoteConfigurationCreation:
    """Test remote configuration file creation and management."""

    def test_create_remote_configuration_creates_directory(self):
        """Test remote configuration creates .code-indexer directory."""
        from code_indexer.remote.config import create_remote_configuration

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)

            create_remote_configuration(
                project_root=test_dir,
                server_url="https://cidx.example.com",
                username="testuser",
                # Don't pass actual password in tests - will be encrypted
                encrypted_credentials="encrypted_credentials_hash",
            )

            config_dir = test_dir / ".code-indexer"
            assert config_dir.exists()
            assert config_dir.is_dir()

    def test_create_remote_configuration_creates_remote_config_file(self):
        """Test remote configuration creates .remote-config file."""
        from code_indexer.remote.config import create_remote_configuration

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)

            create_remote_configuration(
                project_root=test_dir,
                server_url="https://cidx.example.com",
                username="testuser",
                encrypted_credentials="encrypted_credentials_hash",
            )

            remote_config_file = test_dir / ".code-indexer" / ".remote-config"
            assert remote_config_file.exists()
            assert remote_config_file.is_file()

    def test_create_remote_configuration_file_structure(self):
        """Test remote configuration file has correct structure."""
        from code_indexer.remote.config import create_remote_configuration

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)

            create_remote_configuration(
                project_root=test_dir,
                server_url="https://cidx.example.com",
                username="testuser",
                encrypted_credentials="encrypted_credentials_hash",
            )

            remote_config_file = test_dir / ".code-indexer" / ".remote-config"
            with open(remote_config_file) as f:
                config = json.load(f)

            assert "server_url" in config
            assert "username" in config
            assert "encrypted_credentials" in config
            assert "mode" in config
            assert "created_at" in config

            assert config["server_url"] == "https://cidx.example.com"
            assert config["username"] == "testuser"
            assert config["mode"] == "remote"

    def test_create_remote_configuration_secure_permissions(self):
        """Test remote configuration file has secure permissions (0o600)."""
        from code_indexer.remote.config import create_remote_configuration

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)

            create_remote_configuration(
                project_root=test_dir,
                server_url="https://cidx.example.com",
                username="testuser",
                encrypted_credentials="encrypted_credentials_hash",
            )

            remote_config_file = test_dir / ".code-indexer" / ".remote-config"
            file_mode = remote_config_file.stat().st_mode & 0o777
            assert file_mode == 0o600

    def test_create_remote_configuration_overwrites_existing(self):
        """Test remote configuration overwrites existing configuration."""
        from code_indexer.remote.config import create_remote_configuration

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)
            config_dir = test_dir / ".code-indexer"
            config_dir.mkdir()

            # Create existing config
            existing_config = config_dir / ".remote-config"
            existing_config.write_text('{"old": "config"}')

            create_remote_configuration(
                project_root=test_dir,
                server_url="https://cidx.example.com",
                username="testuser",
                encrypted_credentials="encrypted_credentials_hash",
            )

            with open(existing_config) as f:
                config = json.load(f)

            assert "old" not in config
            assert config["server_url"] == "https://cidx.example.com"


class TestEndToEndRemoteInitialization:
    """Test complete end-to-end remote initialization workflow."""

    @pytest.mark.asyncio
    async def test_remote_initialization_orchestrator_success(self):
        """Test complete remote initialization orchestrator with mocked dependencies."""
        from code_indexer.remote.initialization import initialize_remote_mode
        from rich.console import Console
        import io

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)

            # Capture console output
            console_output = io.StringIO()
            test_console = Console(file=console_output, width=80, legacy_windows=False)

            # Mock all the external dependencies
            with (
                patch(
                    "code_indexer.remote.initialization.validate_and_normalize_server_url"
                ) as mock_url_validate,
                patch(
                    "code_indexer.remote.initialization.test_server_connectivity"
                ) as mock_connectivity,
                patch(
                    "code_indexer.remote.initialization.validate_credentials"
                ) as mock_credentials,
                patch(
                    "code_indexer.remote.initialization.create_remote_configuration"
                ) as mock_create_config,
                patch(
                    "code_indexer.remote.initialization.RemoteConfig"
                ) as mock_remote_config_class,
            ):
                # Configure mocks for success case
                mock_url_validate.return_value = "https://cidx.example.com"
                mock_connectivity.return_value = None  # Async function, no return
                mock_credentials.return_value = {
                    "username": "testuser",
                    "permissions": ["read", "write"],
                }
                mock_create_config.return_value = None
                # Configure mock RemoteConfig instance
                mock_remote_config = MagicMock()
                mock_remote_config_class.return_value = mock_remote_config

                # Should complete successfully
                await initialize_remote_mode(
                    project_root=test_dir,
                    server_url="https://cidx.example.com",
                    username="testuser",
                    password="testpass123",
                    console=test_console,
                )

                # Verify all steps were called in correct order
                mock_url_validate.assert_called_once_with("https://cidx.example.com")
                mock_connectivity.assert_called_once_with("https://cidx.example.com")
                mock_credentials.assert_called_once_with(
                    "https://cidx.example.com", "testuser", "testpass123"
                )
                mock_remote_config.store_credentials.assert_called_once_with(
                    "testpass123"
                )
                mock_create_config.assert_called_once_with(
                    project_root=test_dir,
                    server_url="https://cidx.example.com",
                    username="testuser",
                    encrypted_credentials="",
                )

                # Check console output contains success message
                output = console_output.getvalue()
                assert "Remote mode initialized successfully" in output
                assert "cidx start" in output
                assert "cidx query" in output

    def test_remote_initialization_cli_integration_parameter_validation(self):
        """Test CLI integration with parameter validation (should work without mocks)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)

            # Test parameter validation (this should work without network calls)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "code_indexer.cli",
                    "init",
                    "--remote",
                    "https://cidx.example.com",
                    "--username",
                    "testuser",
                    # Missing --password intentionally
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=test_dir,
            )

            # Should fail with parameter validation error
            assert result.returncode == 1
            assert (
                "Remote initialization requires --username and --password"
                in result.stdout
            )

    @pytest.mark.asyncio
    async def test_remote_initialization_failure_cleanup(self):
        """Test that remote initialization cleans up on failure."""
        from code_indexer.remote.initialization import initialize_remote_mode
        from code_indexer.remote.exceptions import RemoteInitializationError
        from rich.console import Console
        import io

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)

            # Capture console output
            console_output = io.StringIO()
            test_console = Console(file=console_output, width=80, legacy_windows=False)

            # Mock failure during credential validation
            with (
                patch(
                    "code_indexer.remote.initialization.validate_and_normalize_server_url"
                ) as mock_url_validate,
                patch(
                    "code_indexer.remote.initialization.test_server_connectivity"
                ) as mock_connectivity,
                patch(
                    "code_indexer.remote.initialization.validate_credentials"
                ) as mock_credentials,
                patch("code_indexer.remote.initialization.create_remote_configuration"),
                patch(
                    "code_indexer.remote.initialization._cleanup_on_failure"
                ) as mock_cleanup,
            ):
                mock_url_validate.return_value = "https://cidx.example.com"
                mock_connectivity.return_value = None  # Success
                mock_credentials.side_effect = Exception("Authentication failed")

                # Should fail with RemoteInitializationError
                with pytest.raises(RemoteInitializationError):
                    await initialize_remote_mode(
                        project_root=test_dir,
                        server_url="https://cidx.example.com",
                        username="testuser",
                        password="badpass",
                        console=test_console,
                    )

                # Should call cleanup on failure
                mock_cleanup.assert_called_once_with(test_dir)

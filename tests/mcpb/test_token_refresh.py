"""Unit tests for token refresh CLI command.

This module tests the cidx-token-refresh CLI command that refreshes
authentication tokens with the CIDX server.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import httpx
import pytest

from code_indexer.mcpb.token_refresh import (
    load_config,
    save_config,
    refresh_token,
    main,
    DEFAULT_CONFIG_PATH,
)


class TestLoadConfig:
    """Test loading configuration from file."""

    def test_load_config_success(self):
        """Test loading valid configuration file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://cidx.test.com",
                "bearer_token": "old-token-123",
                "refresh_token": "refresh-token-456",
            }
            json.dump(config_data, f)
            config_path = Path(f.name)

        try:
            config = load_config(config_path)
            assert config["server_url"] == "https://cidx.test.com"
            assert config["bearer_token"] == "old-token-123"
            assert config["refresh_token"] == "refresh-token-456"
        finally:
            config_path.unlink()

    def test_load_config_file_not_found(self):
        """Test loading non-existent config file exits with error."""
        non_existent_path = Path("/tmp/non-existent-config.json")
        with pytest.raises(SystemExit) as exc_info:
            load_config(non_existent_path)
        assert exc_info.value.code == 1

    def test_load_config_invalid_json(self):
        """Test loading invalid JSON exits with error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ invalid json }")
            config_path = Path(f.name)

        try:
            with pytest.raises(SystemExit) as exc_info:
                load_config(config_path)
            assert exc_info.value.code == 1
        finally:
            config_path.unlink()


class TestSaveConfig:
    """Test saving configuration to file."""

    def test_save_config_success(self):
        """Test saving configuration file with secure permissions."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_path = Path(f.name)

        try:
            config_data = {
                "server_url": "https://cidx.test.com",
                "bearer_token": "new-token-789",
                "refresh_token": "new-refresh-token-012",
            }
            save_config(config_path, config_data)

            # Verify file contents
            with open(config_path) as f:
                saved_data = json.load(f)
            assert saved_data == config_data

            # Verify secure permissions (600)
            import stat

            file_stat = config_path.stat()
            file_perms = stat.S_IMODE(file_stat.st_mode)
            assert file_perms == 0o600
        finally:
            if config_path.exists():
                config_path.unlink()

    def test_save_config_write_error(self):
        """Test save_config exits on write error."""
        invalid_path = Path("/root/cannot-write/config.json")
        config_data = {"server_url": "https://test.com"}

        with pytest.raises(SystemExit) as exc_info:
            save_config(invalid_path, config_data)
        assert exc_info.value.code == 1


class TestRefreshToken:
    """Test calling the /auth/refresh endpoint."""

    @patch("code_indexer.mcpb.token_refresh.httpx.Client")
    def test_refresh_token_success(self, mock_client_class):
        """Test successful token refresh."""
        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "access_token_expires_in": 3600,
        }

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        result = refresh_token(
            server_url="https://cidx.test.com",
            refresh_token="old-refresh-token",
        )

        assert result["access_token"] == "new-access-token"
        assert result["refresh_token"] == "new-refresh-token"
        assert result["access_token_expires_in"] == 3600

        # Verify HTTP call
        mock_client.post.assert_called_once_with(
            "https://cidx.test.com/auth/refresh",
            json={"refresh_token": "old-refresh-token"},
            headers={"Content-Type": "application/json"},
        )

    @patch("code_indexer.mcpb.token_refresh.httpx.Client")
    def test_refresh_token_strips_trailing_slash(self, mock_client_class):
        """Test that trailing slash is stripped from server URL."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-token",
            "refresh_token": "new-refresh",
            "access_token_expires_in": 3600,
        }

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        refresh_token(
            server_url="https://cidx.test.com/",  # Note trailing slash
            refresh_token="old-refresh-token",
        )

        # Verify trailing slash was stripped
        mock_client.post.assert_called_once_with(
            "https://cidx.test.com/auth/refresh",  # No trailing slash
            json={"refresh_token": "old-refresh-token"},
            headers={"Content-Type": "application/json"},
        )

    @patch("code_indexer.mcpb.token_refresh.httpx.Client")
    def test_refresh_token_401_unauthorized(self, mock_client_class):
        """Test refresh token expired (401 Unauthorized)."""
        mock_response = Mock()
        mock_response.status_code = 401

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            refresh_token(
                server_url="https://cidx.test.com",
                refresh_token="expired-refresh-token",
            )
        assert exc_info.value.code == 1

    @patch("code_indexer.mcpb.token_refresh.httpx.Client")
    def test_refresh_token_500_server_error(self, mock_client_class):
        """Test server error response."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            refresh_token(
                server_url="https://cidx.test.com",
                refresh_token="some-refresh-token",
            )
        assert exc_info.value.code == 1

    @patch("code_indexer.mcpb.token_refresh.httpx.Client")
    def test_refresh_token_network_error(self, mock_client_class):
        """Test network connection error."""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client_class.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            refresh_token(
                server_url="https://cidx.test.com",
                refresh_token="some-refresh-token",
            )
        assert exc_info.value.code == 1

    @patch("code_indexer.mcpb.token_refresh.httpx.Client")
    def test_refresh_token_timeout_error(self, mock_client_class):
        """Test request timeout."""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.side_effect = httpx.TimeoutException("Request timed out")
        mock_client_class.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            refresh_token(
                server_url="https://cidx.test.com",
                refresh_token="some-refresh-token",
            )
        assert exc_info.value.code == 1

    @patch("code_indexer.mcpb.token_refresh.httpx.Client")
    def test_refresh_token_uses_30_second_timeout(self, mock_client_class):
        """Test that httpx client uses 30 second timeout."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-token",
            "refresh_token": "new-refresh",
            "access_token_expires_in": 3600,
        }

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        refresh_token(
            server_url="https://cidx.test.com",
            refresh_token="old-refresh-token",
        )

        # Verify timeout was set
        mock_client_class.assert_called_once_with(timeout=30.0, verify=True)

    @patch("code_indexer.mcpb.token_refresh.httpx.Client")
    def test_refresh_token_verifies_ssl(self, mock_client_class):
        """Test that SSL verification is enabled."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-token",
            "refresh_token": "new-refresh",
            "access_token_expires_in": 3600,
        }

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        refresh_token(
            server_url="https://cidx.test.com",
            refresh_token="old-refresh-token",
        )

        # Verify SSL verification was enabled
        mock_client_class.assert_called_once_with(timeout=30.0, verify=True)


class TestMainFunction:
    """Test main entry point for CLI command."""

    @patch("code_indexer.mcpb.token_refresh.load_config")
    @patch("code_indexer.mcpb.token_refresh.refresh_token")
    @patch("code_indexer.mcpb.token_refresh.save_config")
    @patch("sys.argv", ["cidx-token-refresh"])
    def test_main_success_with_default_config(self, mock_save, mock_refresh, mock_load):
        """Test successful token refresh with default config path."""
        # Setup mocks
        mock_load.return_value = {
            "server_url": "https://cidx.test.com",
            "bearer_token": "old-token",
            "refresh_token": "old-refresh-token",
        }
        mock_refresh.return_value = {
            "access_token": "new-token",
            "refresh_token": "new-refresh-token",
            "access_token_expires_in": 3600,
        }

        main()

        # Verify calls
        mock_load.assert_called_once_with(DEFAULT_CONFIG_PATH)
        mock_refresh.assert_called_once_with(
            "https://cidx.test.com", "old-refresh-token"
        )
        expected_config = {
            "server_url": "https://cidx.test.com",
            "bearer_token": "new-token",
            "refresh_token": "new-refresh-token",
        }
        mock_save.assert_called_once_with(DEFAULT_CONFIG_PATH, expected_config)

    @patch("code_indexer.mcpb.token_refresh.load_config")
    @patch("code_indexer.mcpb.token_refresh.refresh_token")
    @patch("code_indexer.mcpb.token_refresh.save_config")
    @patch("sys.argv", ["cidx-token-refresh", "--config", "/tmp/custom-config.json"])
    def test_main_success_with_custom_config(self, mock_save, mock_refresh, mock_load):
        """Test successful token refresh with custom config path."""
        # Setup mocks
        mock_load.return_value = {
            "server_url": "https://cidx.test.com",
            "bearer_token": "old-token",
            "refresh_token": "old-refresh-token",
        }
        mock_refresh.return_value = {
            "access_token": "new-token",
            "refresh_token": "new-refresh-token",
            "access_token_expires_in": 3600,
        }

        main()

        # Verify custom config path was used
        mock_load.assert_called_once_with(Path("/tmp/custom-config.json"))
        mock_save.assert_called_once()
        # Get the actual path argument passed to save_config
        save_path_arg = mock_save.call_args[0][0]
        assert save_path_arg == Path("/tmp/custom-config.json")

    @patch("code_indexer.mcpb.token_refresh.load_config")
    @patch("sys.argv", ["cidx-token-refresh"])
    def test_main_missing_server_url(self, mock_load):
        """Test error when server_url missing from config."""
        mock_load.return_value = {
            "refresh_token": "some-refresh-token",
        }

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("code_indexer.mcpb.token_refresh.load_config")
    @patch("sys.argv", ["cidx-token-refresh"])
    def test_main_missing_refresh_token(self, mock_load):
        """Test error when refresh_token missing from config."""
        mock_load.return_value = {
            "server_url": "https://cidx.test.com",
        }

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("code_indexer.mcpb.token_refresh.load_config")
    @patch("code_indexer.mcpb.token_refresh.refresh_token")
    @patch("code_indexer.mcpb.token_refresh.save_config")
    @patch("sys.argv", ["cidx-token-refresh"])
    def test_main_preserves_old_refresh_token_if_not_returned(
        self, mock_save, mock_refresh, mock_load
    ):
        """Test that old refresh token is preserved if new one not returned."""
        # Setup mocks - API returns access_token but not refresh_token
        mock_load.return_value = {
            "server_url": "https://cidx.test.com",
            "bearer_token": "old-token",
            "refresh_token": "old-refresh-token",
        }
        mock_refresh.return_value = {
            "access_token": "new-token",
            "access_token_expires_in": 3600,
            # Note: no refresh_token in response
        }

        main()

        # Verify old refresh token was preserved
        expected_config = {
            "server_url": "https://cidx.test.com",
            "bearer_token": "new-token",
            "refresh_token": "old-refresh-token",  # Old token preserved
        }
        mock_save.assert_called_once_with(DEFAULT_CONFIG_PATH, expected_config)


class TestEndToEndIntegration:
    """Integration tests for complete token refresh flow."""

    @patch("code_indexer.mcpb.token_refresh.httpx.Client")
    def test_full_refresh_flow(self, mock_client_class):
        """Test complete flow from config load to save."""
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            initial_config = {
                "server_url": "https://cidx.test.com",
                "bearer_token": "old-token",
                "refresh_token": "old-refresh-token",
            }
            json.dump(initial_config, f)
            config_path = Path(f.name)

        try:
            # Mock HTTP response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "access_token": "new-token",
                "refresh_token": "new-refresh-token",
                "access_token_expires_in": 3600,
            }

            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            # Load config
            config = load_config(config_path)
            assert config["refresh_token"] == "old-refresh-token"

            # Refresh token
            result = refresh_token(config["server_url"], config["refresh_token"])

            # Update config
            config["bearer_token"] = result["access_token"]
            config["refresh_token"] = result["refresh_token"]

            # Save config
            save_config(config_path, config)

            # Verify final config
            with open(config_path) as f:
                final_config = json.load(f)

            assert final_config["bearer_token"] == "new-token"
            assert final_config["refresh_token"] == "new-refresh-token"
            assert final_config["server_url"] == "https://cidx.test.com"

            # Verify permissions
            import stat

            file_stat = config_path.stat()
            file_perms = stat.S_IMODE(file_stat.st_mode)
            assert file_perms == 0o600

        finally:
            if config_path.exists():
                config_path.unlink()

"""Unit tests for configuration loading and validation.

This module tests loading configuration from config file, environment variables,
and validation of configuration values.
"""

import json
import os
import tempfile

import pytest

from code_indexer.mcpb.config import (
    BridgeConfig,
    load_config,
    DEFAULT_TIMEOUT,
    DEFAULT_CONFIG_PATH,
)


class TestBridgeConfig:
    """Test BridgeConfig data class."""

    def test_config_with_all_fields(self):
        """Test creating config with all fields."""
        config = BridgeConfig(
            server_url="https://cidx.example.com",
            bearer_token="test-token-123",
            timeout=30,
        )

        assert config.server_url == "https://cidx.example.com"
        assert config.bearer_token == "test-token-123"
        assert config.timeout == 30

    def test_config_with_refresh_token(self):
        """Test creating config with refresh_token."""
        config = BridgeConfig(
            server_url="https://cidx.example.com",
            bearer_token="test-token-123",
            refresh_token="refresh-token-456",
            timeout=30,
        )

        assert config.server_url == "https://cidx.example.com"
        assert config.bearer_token == "test-token-123"
        assert config.refresh_token == "refresh-token-456"
        assert config.timeout == 30

    def test_config_without_refresh_token(self):
        """Test creating config without refresh_token (optional field)."""
        config = BridgeConfig(
            server_url="https://cidx.example.com",
            bearer_token="test-token-123",
        )

        assert config.server_url == "https://cidx.example.com"
        assert config.bearer_token == "test-token-123"
        assert config.refresh_token is None

    def test_config_with_default_timeout(self):
        """Test creating config with default timeout."""
        config = BridgeConfig(
            server_url="https://cidx.example.com", bearer_token="test-token-123"
        )

        assert config.timeout == DEFAULT_TIMEOUT

    def test_config_validates_server_url_not_empty(self):
        """Test that empty server_url raises validation error."""
        with pytest.raises(ValueError, match="server_url cannot be empty"):
            BridgeConfig(server_url="", bearer_token="test-token")

    def test_config_validates_bearer_token_not_empty(self):
        """Test that empty bearer_token raises validation error."""
        with pytest.raises(ValueError, match="bearer_token cannot be empty"):
            BridgeConfig(server_url="https://example.com", bearer_token="")

    def test_config_validates_timeout_positive(self):
        """Test that negative timeout raises validation error."""
        with pytest.raises(ValueError, match="timeout must be between 1 and 300"):
            BridgeConfig(
                server_url="https://example.com", bearer_token="test-token", timeout=-1
            )

    def test_config_validates_timeout_not_zero(self):
        """Test that zero timeout raises validation error."""
        with pytest.raises(ValueError, match="timeout must be between 1 and 300"):
            BridgeConfig(
                server_url="https://example.com", bearer_token="test-token", timeout=0
            )

    def test_config_strips_trailing_slash_from_url(self):
        """Test that trailing slash is stripped from server_url."""
        config = BridgeConfig(
            server_url="https://cidx.example.com/", bearer_token="test-token"
        )

        assert config.server_url == "https://cidx.example.com"

    def test_config_allows_url_with_path(self):
        """Test that URL with path is preserved."""
        config = BridgeConfig(
            server_url="https://cidx.example.com/api", bearer_token="test-token"
        )

        assert config.server_url == "https://cidx.example.com/api"


class TestLoadConfig:
    """Test configuration loading from file and environment."""

    def test_load_config_from_file(self):
        """Test loading configuration from JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://cidx.test.com",
                "bearer_token": "file-token-123",
                "timeout": 45,
            }
            json.dump(config_data, f)
            config_path = f.name

        try:
            config = load_config(config_path)

            assert config.server_url == "https://cidx.test.com"
            assert config.bearer_token == "file-token-123"
            assert config.timeout == 45
        finally:
            os.unlink(config_path)

    def test_load_config_file_not_found_raises_error(self):
        """Test that missing config file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            load_config("/nonexistent/config.json")

    def test_load_config_invalid_json_raises_error(self):
        """Test that invalid JSON raises appropriate error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"server_url": "test", invalid json}')
            config_path = f.name

        try:
            with pytest.raises(json.JSONDecodeError):
                load_config(config_path)
        finally:
            os.unlink(config_path)

    def test_load_config_missing_server_url_raises_error(self):
        """Test that missing server_url in config raises error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {"bearer_token": "test-token", "timeout": 30}
            json.dump(config_data, f)
            config_path = f.name

        try:
            with pytest.raises(ValueError, match="Missing required field: server_url"):
                load_config(config_path)
        finally:
            os.unlink(config_path)

    def test_load_config_missing_bearer_token_raises_error(self):
        """Test that missing bearer_token raises error when no encrypted credentials exist."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {"server_url": "https://example.com", "timeout": 30}
            json.dump(config_data, f)
            config_path = f.name

        try:
            # Mock credentials_exist to return False (no encrypted credentials)
            from unittest.mock import patch
            with patch("code_indexer.mcpb.credential_storage.credentials_exist", return_value=False):
                with pytest.raises(
                    ValueError, match="Missing required field: bearer_token"
                ):
                    load_config(config_path)
        finally:
            os.unlink(config_path)

    def test_load_config_with_default_timeout(self):
        """Test that config without timeout uses default."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://example.com",
                "bearer_token": "test-token",
            }
            json.dump(config_data, f)
            config_path = f.name

        try:
            config = load_config(config_path)

            assert config.timeout == DEFAULT_TIMEOUT
        finally:
            os.unlink(config_path)

    def test_load_config_from_environment_variables(self):
        """Test loading configuration from environment variables."""
        os.environ["MCPB_SERVER_URL"] = "https://env.example.com"
        os.environ["MCPB_BEARER_TOKEN"] = "env-token-456"
        os.environ["MCPB_TIMEOUT"] = "60"

        try:
            config = load_config(use_env=True)

            assert config.server_url == "https://env.example.com"
            assert config.bearer_token == "env-token-456"
            assert config.timeout == 60
        finally:
            del os.environ["MCPB_SERVER_URL"]
            del os.environ["MCPB_BEARER_TOKEN"]
            del os.environ["MCPB_TIMEOUT"]

    def test_load_config_env_overrides_file(self):
        """Test that environment variables override file config."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://file.example.com",
                "bearer_token": "file-token",
                "timeout": 30,
            }
            json.dump(config_data, f)
            config_path = f.name

        os.environ["MCPB_SERVER_URL"] = "https://env.example.com"

        try:
            config = load_config(config_path, use_env=True)

            assert config.server_url == "https://env.example.com"
            assert config.bearer_token == "file-token"
            assert config.timeout == 30
        finally:
            os.unlink(config_path)
            del os.environ["MCPB_SERVER_URL"]

    def test_default_config_path_expansion(self):
        """Test that default config path expands ~ correctly."""
        assert "~" not in str(DEFAULT_CONFIG_PATH)
        assert DEFAULT_CONFIG_PATH.is_absolute()


class TestHTTPSValidation:
    """Test HTTPS validation requirement from Story #517."""

    def test_config_requires_https_url(self):
        """Test that non-HTTPS URL raises validation error."""
        with pytest.raises(ValueError, match="server_url must use HTTPS"):
            BridgeConfig(
                server_url="http://cidx.example.com", bearer_token="test-token"
            )

    def test_config_allows_https_url(self):
        """Test that HTTPS URL is accepted."""
        config = BridgeConfig(
            server_url="https://cidx.example.com", bearer_token="test-token"
        )
        assert config.server_url == "https://cidx.example.com"

    def test_config_rejects_ftp_url(self):
        """Test that FTP URL raises validation error."""
        with pytest.raises(ValueError, match="server_url must use HTTPS"):
            BridgeConfig(server_url="ftp://cidx.example.com", bearer_token="test-token")

    def test_config_rejects_ws_url(self):
        """Test that WebSocket URL raises validation error."""
        with pytest.raises(ValueError, match="server_url must use HTTPS"):
            BridgeConfig(server_url="ws://cidx.example.com", bearer_token="test-token")

    def test_config_allows_localhost_http(self):
        """Test that localhost HTTP URLs are allowed for testing."""
        config = BridgeConfig(
            server_url="http://localhost:8080", bearer_token="test-token"
        )
        assert config.server_url == "http://localhost:8080"

    def test_config_allows_127_0_0_1_http(self):
        """Test that 127.0.0.1 HTTP URLs are allowed for testing."""
        config = BridgeConfig(
            server_url="http://127.0.0.1:9000", bearer_token="test-token"
        )
        assert config.server_url == "http://127.0.0.1:9000"


class TestLogLevelConfiguration:
    """Test log_level configuration field from Story #517."""

    def test_config_with_valid_log_level(self):
        """Test config with valid log_level."""
        config = BridgeConfig(
            server_url="https://cidx.example.com",
            bearer_token="test-token",
            log_level="debug",
        )
        assert config.log_level == "debug"

    def test_config_with_default_log_level(self):
        """Test config uses default log_level when not specified."""
        config = BridgeConfig(
            server_url="https://cidx.example.com", bearer_token="test-token"
        )
        assert config.log_level == "info"

    def test_config_rejects_invalid_log_level(self):
        """Test that invalid log_level raises validation error."""
        with pytest.raises(ValueError, match="log_level must be one of"):
            BridgeConfig(
                server_url="https://cidx.example.com",
                bearer_token="test-token",
                log_level="invalid",
            )

    def test_config_allows_all_valid_log_levels(self):
        """Test that all valid log_levels are accepted."""
        valid_levels = ["debug", "info", "warning", "error"]
        for level in valid_levels:
            config = BridgeConfig(
                server_url="https://cidx.example.com",
                bearer_token="test-token",
                log_level=level,
            )
            assert config.log_level == level


class TestTimeoutRangeValidation:
    """Test timeout range validation (1-300 seconds) from Story #517."""

    def test_config_allows_timeout_in_valid_range(self):
        """Test that timeout within 1-300 range is accepted."""
        for timeout in [1, 30, 150, 300]:
            config = BridgeConfig(
                server_url="https://cidx.example.com",
                bearer_token="test-token",
                timeout=timeout,
            )
            assert config.timeout == timeout

    def test_config_rejects_timeout_above_maximum(self):
        """Test that timeout > 300 raises validation error."""
        with pytest.raises(ValueError, match="timeout must be between 1 and 300"):
            BridgeConfig(
                server_url="https://cidx.example.com",
                bearer_token="test-token",
                timeout=301,
            )

    def test_config_rejects_timeout_of_zero(self):
        """Test that timeout = 0 raises validation error."""
        with pytest.raises(ValueError, match="timeout must be between 1 and 300"):
            BridgeConfig(
                server_url="https://cidx.example.com",
                bearer_token="test-token",
                timeout=0,
            )

    def test_config_rejects_negative_timeout(self):
        """Test that negative timeout raises validation error."""
        with pytest.raises(ValueError, match="timeout must be between 1 and 300"):
            BridgeConfig(
                server_url="https://cidx.example.com",
                bearer_token="test-token",
                timeout=-1,
            )


class TestDualEnvVarSupport:
    """Test dual environment variable support (CIDX_* and MCPB_*) from Story #517."""

    def test_load_config_from_cidx_env_vars(self):
        """Test loading configuration from CIDX_* environment variables."""
        os.environ["CIDX_SERVER_URL"] = "https://cidx-env.example.com"
        os.environ["CIDX_TOKEN"] = "cidx-token-789"
        os.environ["CIDX_TIMEOUT"] = "90"
        os.environ["CIDX_LOG_LEVEL"] = "debug"

        try:
            config = load_config(use_env=True)

            assert config.server_url == "https://cidx-env.example.com"
            assert config.bearer_token == "cidx-token-789"
            assert config.timeout == 90
            assert config.log_level == "debug"
        finally:
            del os.environ["CIDX_SERVER_URL"]
            del os.environ["CIDX_TOKEN"]
            del os.environ["CIDX_TIMEOUT"]
            del os.environ["CIDX_LOG_LEVEL"]

    def test_cidx_env_vars_take_precedence_over_mcpb(self):
        """Test that CIDX_* env vars override MCPB_* when both present."""
        os.environ["CIDX_SERVER_URL"] = "https://cidx.example.com"
        os.environ["MCPB_SERVER_URL"] = "https://mcpb.example.com"
        os.environ["CIDX_TOKEN"] = "cidx-token"
        os.environ["MCPB_BEARER_TOKEN"] = "mcpb-token"

        try:
            config = load_config(use_env=True)

            assert config.server_url == "https://cidx.example.com"
            assert config.bearer_token == "cidx-token"
        finally:
            del os.environ["CIDX_SERVER_URL"]
            del os.environ["MCPB_SERVER_URL"]
            del os.environ["CIDX_TOKEN"]
            del os.environ["MCPB_BEARER_TOKEN"]

    def test_mcpb_env_vars_still_work(self):
        """Test backward compatibility - MCPB_* env vars still work."""
        os.environ["MCPB_SERVER_URL"] = "https://mcpb.example.com"
        os.environ["MCPB_BEARER_TOKEN"] = "mcpb-token"

        try:
            config = load_config(use_env=True)

            assert config.server_url == "https://mcpb.example.com"
            assert config.bearer_token == "mcpb-token"
        finally:
            del os.environ["MCPB_SERVER_URL"]
            del os.environ["MCPB_BEARER_TOKEN"]

    def test_mixed_cidx_and_mcpb_env_vars(self):
        """Test mixing CIDX_* and MCPB_* env vars with correct precedence."""
        os.environ["CIDX_SERVER_URL"] = "https://cidx.example.com"
        os.environ["MCPB_BEARER_TOKEN"] = "mcpb-token"
        os.environ["MCPB_TIMEOUT"] = "60"

        try:
            config = load_config(use_env=True)

            assert config.server_url == "https://cidx.example.com"
            assert config.bearer_token == "mcpb-token"
            assert config.timeout == 60
        finally:
            del os.environ["CIDX_SERVER_URL"]
            del os.environ["MCPB_BEARER_TOKEN"]
            del os.environ["MCPB_TIMEOUT"]

    def test_load_config_with_refresh_token_from_file(self):
        """Test loading refresh_token from config file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://cidx.test.com",
                "bearer_token": "test-access-token",
                "refresh_token": "test-refresh-token",
            }
            json.dump(config_data, f)
            config_path = f.name

        try:
            config = load_config(config_path)

            assert config.server_url == "https://cidx.test.com"
            assert config.bearer_token == "test-access-token"
            assert config.refresh_token == "test-refresh-token"
        finally:
            os.unlink(config_path)

    def test_load_config_without_refresh_token_from_file(self):
        """Test loading config without refresh_token (optional field)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://cidx.test.com",
                "bearer_token": "test-access-token",
            }
            json.dump(config_data, f)
            config_path = f.name

        try:
            config = load_config(config_path)

            assert config.server_url == "https://cidx.test.com"
            assert config.bearer_token == "test-access-token"
            assert config.refresh_token is None
        finally:
            os.unlink(config_path)

    def test_cidx_refresh_token_env_var(self):
        """Test CIDX_REFRESH_TOKEN environment variable."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://cidx.test.com",
                "bearer_token": "test-token",
            }
            json.dump(config_data, f)
            config_path = f.name

        os.environ["CIDX_REFRESH_TOKEN"] = "env-refresh-token"

        try:
            config = load_config(config_path, use_env=True)

            assert config.refresh_token == "env-refresh-token"
        finally:
            os.unlink(config_path)
            del os.environ["CIDX_REFRESH_TOKEN"]

    def test_mcpb_refresh_token_env_var(self):
        """Test MCPB_REFRESH_TOKEN environment variable."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://cidx.test.com",
                "bearer_token": "test-token",
            }
            json.dump(config_data, f)
            config_path = f.name

        os.environ["MCPB_REFRESH_TOKEN"] = "mcpb-env-refresh-token"

        try:
            config = load_config(config_path, use_env=True)

            assert config.refresh_token == "mcpb-env-refresh-token"
        finally:
            os.unlink(config_path)
            del os.environ["MCPB_REFRESH_TOKEN"]

    def test_cidx_refresh_token_takes_precedence_over_mcpb(self):
        """Test CIDX_REFRESH_TOKEN takes precedence over MCPB_REFRESH_TOKEN."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://cidx.test.com",
                "bearer_token": "test-token",
            }
            json.dump(config_data, f)
            config_path = f.name

        os.environ["CIDX_REFRESH_TOKEN"] = "cidx-refresh-token"
        os.environ["MCPB_REFRESH_TOKEN"] = "mcpb-refresh-token"

        try:
            config = load_config(config_path, use_env=True)

            assert config.refresh_token == "cidx-refresh-token"
        finally:
            os.unlink(config_path)
            del os.environ["CIDX_REFRESH_TOKEN"]
            del os.environ["MCPB_REFRESH_TOKEN"]

    def test_refresh_token_env_var_overrides_file(self):
        """Test refresh_token env var overrides file value."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://cidx.test.com",
                "bearer_token": "test-token",
                "refresh_token": "file-refresh-token",
            }
            json.dump(config_data, f)
            config_path = f.name

        os.environ["CIDX_REFRESH_TOKEN"] = "env-refresh-token"

        try:
            config = load_config(config_path, use_env=True)

            assert config.refresh_token == "env-refresh-token"
        finally:
            os.unlink(config_path)
            del os.environ["CIDX_REFRESH_TOKEN"]


class TestEnhancedErrorMessages:
    """Test enhanced error messages with suggestions from Story #517."""

    def test_missing_server_url_has_helpful_error(self):
        """Test missing server_url provides suggestion."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {"bearer_token": "test-token"}
            json.dump(config_data, f)
            config_path = f.name

        try:
            with pytest.raises(ValueError) as excinfo:
                load_config(config_path)

            error_msg = str(excinfo.value)
            assert "Missing required field: server_url" in error_msg
            assert "CIDX_SERVER_URL" in error_msg
            assert "config.json" in error_msg
        finally:
            os.unlink(config_path)

    def test_missing_bearer_token_has_helpful_error_when_no_credentials(self):
        """Test missing bearer_token provides suggestion when no encrypted credentials exist."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {"server_url": "https://example.com"}
            json.dump(config_data, f)
            config_path = f.name

        try:
            # Mock credentials_exist to return False (no encrypted credentials)
            from unittest.mock import patch
            with patch("code_indexer.mcpb.credential_storage.credentials_exist", return_value=False):
                with pytest.raises(ValueError) as excinfo:
                    load_config(config_path)

                error_msg = str(excinfo.value)
                assert "Missing required field: bearer_token" in error_msg
                assert "CIDX_TOKEN" in error_msg
                assert "config.json" in error_msg
        finally:
            os.unlink(config_path)


class TestFilePermissionWarning:
    """Test file permission check from Story #517."""

    def test_load_config_warns_on_insecure_permissions(self, caplog):
        """Test that insecure file permissions generate warning."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://example.com",
                "bearer_token": "test-token",
            }
            json.dump(config_data, f)
            config_path = f.name

        try:
            # Set insecure permissions (0644)
            os.chmod(config_path, 0o644)

            # Load config and check for warning
            import logging

            with caplog.at_level(logging.WARNING):
                config = load_config(config_path)

            # Should have warning about insecure permissions
            assert any("0600" in record.message for record in caplog.records)
            assert config is not None
        finally:
            os.unlink(config_path)

    def test_load_config_accepts_secure_permissions(self, caplog):
        """Test that secure file permissions (0600) do not generate warning."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://example.com",
                "bearer_token": "test-token",
            }
            json.dump(config_data, f)
            config_path = f.name

        try:
            # Set secure permissions (0600)
            os.chmod(config_path, 0o600)

            # Load config and verify no warning
            import logging

            with caplog.at_level(logging.WARNING):
                config = load_config(config_path)

            # Should NOT have permission warnings
            assert not any("0600" in record.message for record in caplog.records)
            assert config is not None
        finally:
            os.unlink(config_path)

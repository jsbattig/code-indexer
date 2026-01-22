"""
Unit tests for Claude Delegation Configuration (Story #721).

Tests verify that ClaudeDelegationConfig dataclass has correct structure and defaults.
"""

import pytest


class TestClaudeDelegationConfigDataclass:
    """Test ClaudeDelegationConfig dataclass structure and defaults."""

    def test_claude_delegation_config_exists(self):
        """Test that ClaudeDelegationConfig dataclass can be imported."""
        from code_indexer.server.config.delegation_config import ClaudeDelegationConfig

        config = ClaudeDelegationConfig()
        assert config is not None

    def test_claude_delegation_config_default_function_repo_alias(self):
        """Test that function_repo_alias defaults to 'claude-delegation-functions-global'."""
        from code_indexer.server.config.delegation_config import ClaudeDelegationConfig

        config = ClaudeDelegationConfig()
        assert config.function_repo_alias == "claude-delegation-functions-global"

    def test_claude_delegation_config_default_claude_server_url_empty(self):
        """Test that claude_server_url defaults to empty string."""
        from code_indexer.server.config.delegation_config import ClaudeDelegationConfig

        config = ClaudeDelegationConfig()
        assert config.claude_server_url == ""

    def test_claude_delegation_config_default_username_empty(self):
        """Test that claude_server_username defaults to empty string."""
        from code_indexer.server.config.delegation_config import ClaudeDelegationConfig

        config = ClaudeDelegationConfig()
        assert config.claude_server_username == ""

    def test_claude_delegation_config_default_credential_type_password(self):
        """Test that claude_server_credential_type defaults to 'password'."""
        from code_indexer.server.config.delegation_config import ClaudeDelegationConfig

        config = ClaudeDelegationConfig()
        assert config.claude_server_credential_type == "password"

    def test_claude_delegation_config_default_credential_empty(self):
        """Test that claude_server_credential defaults to empty string."""
        from code_indexer.server.config.delegation_config import ClaudeDelegationConfig

        config = ClaudeDelegationConfig()
        assert config.claude_server_credential == ""

    def test_claude_delegation_config_default_cidx_callback_url_empty(self):
        """Test that cidx_callback_url defaults to empty string (Story #720)."""
        from code_indexer.server.config.delegation_config import ClaudeDelegationConfig

        config = ClaudeDelegationConfig()
        assert config.cidx_callback_url == ""

    def test_claude_delegation_config_is_configured_false_by_default(self):
        """Test that is_configured returns False when not configured."""
        from code_indexer.server.config.delegation_config import ClaudeDelegationConfig

        config = ClaudeDelegationConfig()
        assert config.is_configured is False

    def test_claude_delegation_config_is_configured_true_when_complete(self):
        """Test that is_configured returns True when fully configured."""
        from code_indexer.server.config.delegation_config import ClaudeDelegationConfig

        config = ClaudeDelegationConfig(
            claude_server_url="https://claude.example.com",
            claude_server_username="admin",
            claude_server_credential="secret123",
        )
        assert config.is_configured is True


class TestClaudeDelegationManager:
    """Test ClaudeDelegationManager with credential encryption."""

    def test_claude_delegation_manager_exists(self, tmp_path):
        """Test that ClaudeDelegationManager can be imported and instantiated."""
        from code_indexer.server.config.delegation_config import ClaudeDelegationManager

        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))
        assert manager is not None

    def test_save_and_load_config_roundtrip(self, tmp_path):
        """Test saving and loading config with credential encryption roundtrip."""
        from code_indexer.server.config.delegation_config import (
            ClaudeDelegationManager,
            ClaudeDelegationConfig,
        )

        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))
        secret = "my_secret_password_123"

        config = ClaudeDelegationConfig(
            function_repo_alias="test-repo",
            claude_server_url="https://claude.example.com",
            claude_server_username="testuser",
            claude_server_credential_type="password",
            claude_server_credential=secret,
        )

        manager.save_config(config)
        loaded_config = manager.load_config()

        # Verify all fields including decrypted credential
        assert loaded_config is not None
        assert loaded_config.function_repo_alias == "test-repo"
        assert loaded_config.claude_server_url == "https://claude.example.com"
        assert loaded_config.claude_server_username == "testuser"
        assert loaded_config.claude_server_credential_type == "password"
        assert loaded_config.claude_server_credential == secret

    def test_save_and_load_config_with_cidx_callback_url(self, tmp_path):
        """Test saving and loading config with cidx_callback_url field (Story #720)."""
        from code_indexer.server.config.delegation_config import (
            ClaudeDelegationManager,
            ClaudeDelegationConfig,
        )

        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))
        callback_url = "http://192.168.60.20:8000"

        config = ClaudeDelegationConfig(
            function_repo_alias="test-repo",
            claude_server_url="https://claude.example.com",
            claude_server_username="testuser",
            claude_server_credential_type="password",
            claude_server_credential="secret",
            cidx_callback_url=callback_url,
        )

        manager.save_config(config)
        loaded_config = manager.load_config()

        assert loaded_config is not None
        assert loaded_config.cidx_callback_url == callback_url

    def test_credential_is_encrypted_on_disk(self, tmp_path):
        """Test that credentials are stored encrypted, not in plaintext."""
        from code_indexer.server.config.delegation_config import (
            ClaudeDelegationManager,
            ClaudeDelegationConfig,
        )

        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))
        secret = "my_secret_password_123"

        config = ClaudeDelegationConfig(
            function_repo_alias="test-repo",
            claude_server_url="https://claude.example.com",
            claude_server_username="testuser",
            claude_server_credential_type="password",
            claude_server_credential=secret,
        )

        manager.save_config(config)

        # Read raw file and verify credential is NOT stored in plaintext
        config_file = tmp_path / "claude_delegation.json"
        raw_content = config_file.read_text()

        assert secret not in raw_content, "Credential should be encrypted"

    def test_load_config_returns_none_if_not_exists(self, tmp_path):
        """Test that load_config returns None if no config exists."""
        from code_indexer.server.config.delegation_config import ClaudeDelegationManager

        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))
        config = manager.load_config()

        assert config is None


class TestClaudeDelegationConnectivityValidation:
    """Test Claude Server connectivity validation."""

    def test_validate_connectivity_success(self, tmp_path, httpx_mock):
        """Test successful connectivity validation returns success result."""
        from code_indexer.server.config.delegation_config import ClaudeDelegationManager

        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))

        httpx_mock.add_response(
            url="https://claude.example.com/auth/login",
            method="POST",
            json={"access_token": "valid-jwt-token"},
            status_code=200,
        )

        result = manager.validate_connectivity(
            url="https://claude.example.com",
            username="testuser",
            credential="password123",
            credential_type="password",
        )

        assert result.success is True
        assert result.error_message is None

    def test_validate_connectivity_invalid_credentials(self, tmp_path, httpx_mock):
        """Test connectivity validation with 401 unauthorized."""
        from code_indexer.server.config.delegation_config import ClaudeDelegationManager

        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))

        httpx_mock.add_response(
            url="https://claude.example.com/auth/login",
            method="POST",
            json={"error": "Invalid credentials"},
            status_code=401,
        )

        result = manager.validate_connectivity(
            url="https://claude.example.com",
            username="testuser",
            credential="wrongpassword",
            credential_type="password",
        )

        assert result.success is False
        assert (
            "401" in result.error_message
            or "unauthorized" in result.error_message.lower()
        )


class TestConfigServiceDelegationIntegration:
    """Test ConfigService integration with Claude Delegation config."""

    def test_get_all_settings_includes_claude_delegation(self, tmp_path):
        """Test that get_all_settings includes claude_delegation section."""
        from code_indexer.server.services.config_service import ConfigService

        service = ConfigService(server_dir_path=str(tmp_path))
        settings = service.get_all_settings()

        assert "claude_delegation" in settings

    def test_get_all_settings_claude_delegation_defaults(self, tmp_path):
        """Test that claude_delegation has correct default values."""
        from code_indexer.server.services.config_service import ConfigService

        service = ConfigService(server_dir_path=str(tmp_path))
        settings = service.get_all_settings()

        delegation = settings["claude_delegation"]
        assert delegation["function_repo_alias"] == "claude-delegation-functions-global"
        assert delegation["claude_server_url"] == ""
        assert delegation["claude_server_username"] == ""
        assert delegation["claude_server_credential_type"] == "password"
        assert delegation["is_configured"] is False

    def test_get_all_settings_claude_delegation_includes_cidx_callback_url(
        self, tmp_path
    ):
        """Test that cidx_callback_url is included in settings output (Story #720)."""
        from code_indexer.server.services.config_service import ConfigService

        service = ConfigService(server_dir_path=str(tmp_path))
        settings = service.get_all_settings()

        delegation = settings["claude_delegation"]
        assert "cidx_callback_url" in delegation
        assert delegation["cidx_callback_url"] == ""


class TestGetCidxCallbackBaseUrl:
    """Test _get_cidx_callback_base_url function reads from config (Story #720)."""

    def test_returns_callback_url_from_config(self, tmp_path):
        """Test that _get_cidx_callback_base_url returns URL from delegation config."""
        from code_indexer.server.config.delegation_config import (
            ClaudeDelegationManager,
            ClaudeDelegationConfig,
        )
        from code_indexer.server.mcp.handlers import _get_cidx_callback_base_url
        from code_indexer.server.services.config_service import ConfigService

        # Set up config with callback URL
        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))
        config = ClaudeDelegationConfig(
            claude_server_url="https://claude.example.com",
            claude_server_username="user",
            claude_server_credential="pass",
            cidx_callback_url="http://192.168.60.20:8000",
        )
        manager.save_config(config)

        # Mock the config service to use our temp directory
        with pytest.MonkeyPatch.context() as mp:
            mock_service = ConfigService(server_dir_path=str(tmp_path))
            mp.setattr(
                "code_indexer.server.services.config_service.get_config_service",
                lambda: mock_service,
            )

            result = _get_cidx_callback_base_url()

        assert result == "http://192.168.60.20:8000"

    def test_returns_none_when_not_configured(self, tmp_path):
        """Test that _get_cidx_callback_base_url returns None when callback URL is empty."""
        from code_indexer.server.mcp.handlers import _get_cidx_callback_base_url
        from code_indexer.server.services.config_service import ConfigService

        with pytest.MonkeyPatch.context() as mp:
            mock_service = ConfigService(server_dir_path=str(tmp_path))
            mp.setattr(
                "code_indexer.server.services.config_service.get_config_service",
                lambda: mock_service,
            )

            result = _get_cidx_callback_base_url()

        assert result is None


class TestKeyDerivationConsistency:
    """Test key derivation consistency with CITokenManager."""

    def test_key_derivation_uses_os_uname_nodename(self, tmp_path, monkeypatch):
        """
        Test that key derivation uses os.uname().nodename consistently with CITokenManager.

        This ensures that the key derivation approach is consistent across
        all credential encryption in the codebase.
        """
        import os

        from code_indexer.server.config.delegation_config import ClaudeDelegationManager

        # Mock os.uname to verify it's called (not platform.node)
        uname_called = []
        original_uname = os.uname

        def mock_uname():
            uname_called.append(True)
            return original_uname()

        monkeypatch.setattr(os, "uname", mock_uname)

        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))
        # Force key derivation
        _ = manager._encryption_key

        assert len(uname_called) > 0, "os.uname() should be called for key derivation"


class TestURLValidationSSRF:
    """Test URL validation for SSRF protection."""

    def test_validate_connectivity_rejects_file_scheme(self, tmp_path):
        """Test that file:// URLs are rejected for SSRF protection."""
        from code_indexer.server.config.delegation_config import ClaudeDelegationManager

        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))

        result = manager.validate_connectivity(
            url="file:///etc/passwd",
            username="testuser",
            credential="password123",
            credential_type="password",
        )

        assert result.success is False
        assert (
            "scheme" in result.error_message.lower()
            or "url" in result.error_message.lower()
        )

    def test_validate_connectivity_accepts_https_scheme(self, tmp_path, httpx_mock):
        """Test that https:// URLs are accepted."""
        from code_indexer.server.config.delegation_config import ClaudeDelegationManager

        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))

        httpx_mock.add_response(
            url="https://valid-server.com/auth/login",
            method="POST",
            json={"access_token": "token"},
            status_code=200,
        )

        result = manager.validate_connectivity(
            url="https://valid-server.com",
            username="testuser",
            credential="password123",
            credential_type="password",
        )

        assert result.success is True


class TestCredentialTypeValidation:
    """Test credential type validation."""

    def test_validate_connectivity_rejects_invalid_credential_type(self, tmp_path):
        """Test that invalid credential types are rejected."""
        from code_indexer.server.config.delegation_config import ClaudeDelegationManager

        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))

        result = manager.validate_connectivity(
            url="https://valid-server.com",
            username="testuser",
            credential="password123",
            credential_type="invalid_type",
        )

        assert result.success is False
        assert (
            "credential" in result.error_message.lower()
            or "type" in result.error_message.lower()
        )

    def test_validate_connectivity_accepts_password_type(self, tmp_path, httpx_mock):
        """Test that 'password' credential type is accepted."""
        from code_indexer.server.config.delegation_config import ClaudeDelegationManager

        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))

        httpx_mock.add_response(
            url="https://valid-server.com/auth/login",
            method="POST",
            json={"access_token": "token"},
            status_code=200,
        )

        result = manager.validate_connectivity(
            url="https://valid-server.com",
            username="testuser",
            credential="password123",
            credential_type="password",
        )

        assert result.success is True


class TestErrorMessageSanitization:
    """Test that error messages don't expose credentials."""

    def test_error_message_does_not_contain_credential(self, tmp_path, httpx_mock):
        """Test that error messages don't expose the credential value."""
        import httpx

        from code_indexer.server.config.delegation_config import ClaudeDelegationManager

        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))
        secret_credential = "super_secret_password_12345"

        # Simulate a connection error that might include request details
        httpx_mock.add_exception(
            httpx.ConnectError(f"Connection failed with credential {secret_credential}")
        )

        result = manager.validate_connectivity(
            url="https://failing-server.com",
            username="testuser",
            credential=secret_credential,
            credential_type="password",
        )

        assert result.success is False
        assert secret_credential not in result.error_message

    def test_error_message_does_not_contain_password(self, tmp_path, httpx_mock):
        """Test that password is not leaked in any error scenario."""

        from code_indexer.server.config.delegation_config import ClaudeDelegationManager

        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))
        password = "my_secret_password_xyz"

        # Simulate a generic exception that might include password
        httpx_mock.add_exception(Exception(f"Error: password={password}"))

        result = manager.validate_connectivity(
            url="https://failing-server.com",
            username="testuser",
            credential=password,
            credential_type="password",
        )

        assert result.success is False
        assert password not in result.error_message


class TestFilePermissionsCheck:
    """Test file permission verification on load."""

    def test_load_config_warns_if_permissions_not_600(self, tmp_path, caplog):
        """Test that a warning is logged if config file permissions are not 0600."""
        import json
        import logging
        import os

        from code_indexer.server.config.delegation_config import ClaudeDelegationManager

        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))

        # Create config file with insecure permissions (0644)
        config_file = tmp_path / "claude_delegation.json"
        config_data = {
            "function_repo_alias": "test-repo",
            "claude_server_url": "https://example.com",
            "claude_server_username": "user",
            "claude_server_credential_type": "password",
            "claude_server_credential": "",  # Empty credential - no encryption needed
        }
        config_file.write_text(json.dumps(config_data))
        os.chmod(config_file, 0o644)  # Insecure permissions

        with caplog.at_level(logging.WARNING):
            manager.load_config()

        # Check that a warning was logged about permissions
        permission_warnings = [
            record
            for record in caplog.records
            if "permission" in record.message.lower() or "600" in record.message
        ]
        assert (
            len(permission_warnings) > 0
        ), "Should warn about insecure file permissions"

    def test_load_config_no_warning_if_permissions_600(self, tmp_path, caplog):
        """Test that no warning is logged if config file permissions are 0600."""
        import json
        import logging
        import os

        from code_indexer.server.config.delegation_config import ClaudeDelegationManager

        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))

        # Create config file with secure permissions (0600)
        config_file = tmp_path / "claude_delegation.json"
        config_data = {
            "function_repo_alias": "test-repo",
            "claude_server_url": "https://example.com",
            "claude_server_username": "user",
            "claude_server_credential_type": "password",
            "claude_server_credential": "",
        }
        config_file.write_text(json.dumps(config_data))
        os.chmod(config_file, 0o600)  # Secure permissions

        with caplog.at_level(logging.WARNING):
            manager.load_config()

        # Check that no permission warning was logged
        permission_warnings = [
            record
            for record in caplog.records
            if "permission" in record.message.lower() and "600" in record.message
        ]
        assert (
            len(permission_warnings) == 0
        ), "Should not warn about secure file permissions"


class TestDefaultFunctionRepoAliasConstant:
    """Test that the default function repo alias is defined as a constant."""

    def test_default_function_repo_alias_constant_exists(self):
        """Test that DEFAULT_FUNCTION_REPO_ALIAS constant is defined."""
        from code_indexer.server.config import delegation_config

        assert hasattr(delegation_config, "DEFAULT_FUNCTION_REPO_ALIAS")
        assert (
            delegation_config.DEFAULT_FUNCTION_REPO_ALIAS
            == "claude-delegation-functions-global"
        )

    def test_dataclass_uses_constant_for_default(self):
        """Test that ClaudeDelegationConfig uses the constant for its default."""
        from code_indexer.server.config.delegation_config import (
            ClaudeDelegationConfig,
            DEFAULT_FUNCTION_REPO_ALIAS,
        )

        config = ClaudeDelegationConfig()
        assert config.function_repo_alias == DEFAULT_FUNCTION_REPO_ALIAS

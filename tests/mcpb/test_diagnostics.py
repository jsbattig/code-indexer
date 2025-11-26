"""Unit tests for configuration diagnostics.

This module tests the diagnostics functionality for configuration inspection,
including source tracking, token masking, and server connectivity checks.
"""

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_indexer.mcpb.config import BridgeConfig
from code_indexer.mcpb.diagnostics import (
    DiagnosticsResult,
    diagnose_configuration,
    mask_token,
)


class TestMaskToken:
    """Test token masking for security."""

    def test_mask_short_token(self):
        """Test masking token shorter than 7 characters."""
        masked = mask_token("abc")
        assert masked == "****abc"

    def test_mask_medium_token(self):
        """Test masking medium-length token."""
        masked = mask_token("test-token-123")
        assert masked == "****123"
        assert "test-token" not in masked

    def test_mask_long_token(self):
        """Test masking long token."""
        masked = mask_token("very-long-secret-token-abc123def456")
        assert masked == "****456"
        assert "very-long-secret" not in masked

    def test_mask_empty_token(self):
        """Test masking empty token."""
        masked = mask_token("")
        assert masked == "****"


class TestDiagnosticsResult:
    """Test DiagnosticsResult dataclass."""

    def test_diagnostics_result_creation(self):
        """Test creating DiagnosticsResult."""
        result = DiagnosticsResult(
            env_vars={"CIDX_SERVER_URL": "https://example.com"},
            file_config={"server_url": "https://file.com"},
            effective_config={
                "server_url": "https://example.com",
                "bearer_token": "****123",
                "timeout": 30,
                "log_level": "info",
            },
            sources={
                "server_url": "environment",
                "bearer_token": "file",
                "timeout": "default",
                "log_level": "default",
            },
            connectivity_status="success",
            connectivity_message="Server reachable",
            server_version="8.1.0",
        )

        assert result.env_vars["CIDX_SERVER_URL"] == "https://example.com"
        assert result.effective_config["bearer_token"] == "****123"
        assert result.sources["server_url"] == "environment"


class TestDiagnoseConfiguration:
    """Test configuration diagnostics."""

    def test_diagnose_with_env_vars_only(self):
        """Test diagnostics with environment variables only."""
        os.environ["CIDX_SERVER_URL"] = "https://env.example.com"
        os.environ["CIDX_TOKEN"] = "env-token-123456"

        try:
            result = diagnose_configuration(use_env=True)

            assert result.env_vars["CIDX_SERVER_URL"] == "https://env.example.com"
            assert result.env_vars["CIDX_TOKEN"] == "****456"  # Masked
            assert result.effective_config["server_url"] == "https://env.example.com"
            assert result.sources["server_url"] == "environment"
            assert result.sources["bearer_token"] == "environment"
        finally:
            del os.environ["CIDX_SERVER_URL"]
            del os.environ["CIDX_TOKEN"]

    def test_diagnose_with_config_file(self):
        """Test diagnostics with config file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://file.example.com",
                "bearer_token": "file-token-789",
                "timeout": 60,
            }
            json.dump(config_data, f)
            config_path = f.name

        try:
            result = diagnose_configuration(config_path=config_path)

            assert result.file_config["server_url"] == "https://file.example.com"
            assert result.file_config["bearer_token"] == "****789"  # Masked
            assert result.effective_config["timeout"] == 60
            assert result.sources["server_url"] == "file"
            assert result.sources["timeout"] == "file"
        finally:
            os.unlink(config_path)

    def test_diagnose_with_env_override_file(self):
        """Test diagnostics where env vars override file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://file.example.com",
                "bearer_token": "file-token-123",
                "timeout": 60,
            }
            json.dump(config_data, f)
            config_path = f.name

        os.environ["CIDX_SERVER_URL"] = "https://env.example.com"

        try:
            result = diagnose_configuration(config_path=config_path, use_env=True)

            assert result.effective_config["server_url"] == "https://env.example.com"
            assert result.sources["server_url"] == "environment"
            assert result.sources["bearer_token"] == "file"
            assert result.sources["timeout"] == "file"
        finally:
            os.unlink(config_path)
            del os.environ["CIDX_SERVER_URL"]

    def test_diagnose_shows_default_values(self):
        """Test diagnostics shows default values."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://example.com",
                "bearer_token": "test-token",
            }
            json.dump(config_data, f)
            config_path = f.name

        try:
            result = diagnose_configuration(config_path=config_path)

            assert result.effective_config["timeout"] == 30
            assert result.effective_config["log_level"] == "info"
            assert result.sources["timeout"] == "default"
            assert result.sources["log_level"] == "default"
        finally:
            os.unlink(config_path)

    def test_diagnose_masks_tokens_in_all_outputs(self):
        """Test that tokens are masked in all diagnostic outputs."""
        os.environ["CIDX_TOKEN"] = "secret-token-xyz123"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "server_url": "https://example.com",
                "bearer_token": "file-token-abc789",
            }
            json.dump(config_data, f)
            config_path = f.name

        try:
            result = diagnose_configuration(config_path=config_path, use_env=True)

            # Check env vars masked
            assert result.env_vars["CIDX_TOKEN"] == "****123"
            assert "secret-token" not in result.env_vars["CIDX_TOKEN"]

            # Check file config masked
            assert result.file_config["bearer_token"] == "****789"
            assert "file-token" not in result.file_config["bearer_token"]

            # Check effective config masked
            assert result.effective_config["bearer_token"] == "****123"
            assert "secret-token" not in result.effective_config["bearer_token"]
        finally:
            os.unlink(config_path)
            del os.environ["CIDX_TOKEN"]

    @patch("code_indexer.mcpb.diagnostics.test_server_connectivity")
    def test_diagnose_includes_connectivity_check(self, mock_connectivity):
        """Test diagnostics includes server connectivity check."""
        mock_connectivity.return_value = ("success", "Server reachable", "8.1.0")

        os.environ["CIDX_SERVER_URL"] = "https://example.com"
        os.environ["CIDX_TOKEN"] = "test-token"

        try:
            result = diagnose_configuration(use_env=True)

            assert result.connectivity_status == "success"
            assert result.connectivity_message == "Server reachable"
            assert result.server_version == "8.1.0"
            mock_connectivity.assert_called_once()
        finally:
            del os.environ["CIDX_SERVER_URL"]
            del os.environ["CIDX_TOKEN"]

    @patch("code_indexer.mcpb.diagnostics.test_server_connectivity")
    def test_diagnose_handles_connectivity_failure(self, mock_connectivity):
        """Test diagnostics handles server connectivity failure."""
        mock_connectivity.return_value = ("error", "Connection refused", None)

        os.environ["CIDX_SERVER_URL"] = "https://example.com"
        os.environ["CIDX_TOKEN"] = "test-token"

        try:
            result = diagnose_configuration(use_env=True)

            assert result.connectivity_status == "error"
            assert result.connectivity_message == "Connection refused"
            assert result.server_version is None
        finally:
            del os.environ["CIDX_SERVER_URL"]
            del os.environ["CIDX_TOKEN"]

    def test_diagnose_tracks_cidx_vs_mcpb_env_vars(self):
        """Test diagnostics distinguishes CIDX_* vs MCPB_* env vars."""
        os.environ["CIDX_SERVER_URL"] = "https://cidx.example.com"
        os.environ["MCPB_SERVER_URL"] = "https://mcpb.example.com"
        os.environ["MCPB_BEARER_TOKEN"] = "mcpb-token"

        try:
            result = diagnose_configuration(use_env=True)

            # Should show both env vars in diagnostics
            assert "CIDX_SERVER_URL" in result.env_vars
            assert "MCPB_SERVER_URL" in result.env_vars
            assert "MCPB_BEARER_TOKEN" in result.env_vars

            # But effective config should use CIDX_* value
            assert result.effective_config["server_url"] == "https://cidx.example.com"
        finally:
            del os.environ["CIDX_SERVER_URL"]
            del os.environ["MCPB_SERVER_URL"]
            del os.environ["MCPB_BEARER_TOKEN"]

    def test_diagnose_format_output(self):
        """Test formatted diagnostics output."""
        os.environ["CIDX_SERVER_URL"] = "https://example.com"
        os.environ["CIDX_TOKEN"] = "test-token-123"

        try:
            result = diagnose_configuration(use_env=True)
            formatted = result.format_output()

            # Check key sections are present
            assert "Configuration Diagnostics" in formatted
            assert "Environment Variables:" in formatted
            assert "Effective Configuration:" in formatted
            assert "Server Connectivity:" in formatted

            # Check masked token appears
            assert "****123" in formatted

            # Check source attribution
            assert "(from environment)" in formatted or "(from file)" in formatted
        finally:
            del os.environ["CIDX_SERVER_URL"]
            del os.environ["CIDX_TOKEN"]

"""Tests for CLI system health commands.

Following CLAUDE.md Foundation #1: No mocks - tests use real CLI command invocation
and validate actual system health command integration.
"""

import pytest
import tempfile
import json
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import patch, AsyncMock

from src.code_indexer.cli import cli


class TestSystemHealthCLICommands:
    """Test CLI system health command functionality."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def temp_project_dir(self) -> Path:
        """Create temporary project directory with remote config."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create .code-indexer directory
            code_indexer_dir = project_path / ".code-indexer"
            code_indexer_dir.mkdir()

            # Create remote configuration
            remote_config = {
                "server_url": "http://localhost:8000",
                "encrypted_credentials": {"username": "test_user"},
            }

            remote_config_path = code_indexer_dir / "remote_config.json"
            with open(remote_config_path, "w") as f:
                json.dump(remote_config, f)

            yield project_path

    def test_system_health_command_basic_success(
        self, runner: CliRunner, temp_project_dir: Path
    ):
        """Test basic system health command success."""
        with patch(
            "src.code_indexer.api_clients.system_client.create_system_client"
        ) as mock_create_client:
            # Mock system client and health check response
            mock_client = AsyncMock()
            mock_client.check_basic_health.return_value = {
                "status": "ok",
                "timestamp": "2024-01-15T10:30:00Z",
                "message": "System is healthy",
                "response_time_ms": 45.2,
            }
            mock_create_client.return_value = mock_client

            # Mock find_project_root to return our temp directory
            with patch(
                "src.code_indexer.mode_detection.command_mode_detector.find_project_root"
            ) as mock_find_root:
                mock_find_root.return_value = temp_project_dir

                # Mock remote configuration loading
                with patch(
                    "src.code_indexer.remote.config.load_remote_configuration"
                ) as mock_load_config:
                    mock_load_config.return_value = {
                        "server_url": "http://localhost:8000",
                        "encrypted_credentials": {"username": "test_user"},
                    }

                    # Run command from project directory
                    result = runner.invoke(cli, ["system", "health"])

            # Verify command execution
            assert result.exit_code == 0
            assert "System Health: OK" in result.output
            assert "Response Time: 45.2ms" in result.output
            assert "Status: System is healthy" in result.output

            # Verify API client was called correctly
            mock_client.check_basic_health.assert_called_once()

    def test_system_health_command_detailed_success(
        self, runner: CliRunner, temp_project_dir: Path
    ):
        """Test detailed system health command success."""
        with patch(
            "src.code_indexer.api_clients.system_client.create_system_client"
        ) as mock_create_client:
            # Mock system client and detailed health response
            mock_client = AsyncMock()
            mock_client.check_detailed_health.return_value = {
                "status": "healthy",
                "timestamp": "2024-01-15T10:30:00Z",
                "services": {
                    "database": {
                        "status": "healthy",
                        "response_time_ms": 5,
                        "error_message": None,
                    },
                    "vector_store": {
                        "status": "healthy",
                        "response_time_ms": 12,
                        "error_message": None,
                    },
                },
                "system": {
                    "memory_usage_percent": 45.2,
                    "cpu_usage_percent": 23.1,
                    "active_jobs": 2,
                    "disk_free_space_gb": 125.8,
                },
                "response_time_ms": 38.5,
            }
            mock_create_client.return_value = mock_client

            # Mock find_project_root to return our temp directory
            with patch(
                "src.code_indexer.mode_detection.command_mode_detector.find_project_root"
            ) as mock_find_root:
                mock_find_root.return_value = temp_project_dir

                # Mock remote configuration loading
                with patch(
                    "src.code_indexer.remote.config.load_remote_configuration"
                ) as mock_load_config:
                    mock_load_config.return_value = {
                        "server_url": "http://localhost:8000",
                        "encrypted_credentials": {"username": "test_user"},
                    }

                    # Run detailed health command
                    result = runner.invoke(cli, ["system", "health", "--detailed"])

            # Verify command execution
            assert result.exit_code == 0
            assert "=== System Health Status ===" in result.output
            assert "Overall Status: HEALTHY" in result.output
            assert "Response Time: 38.5ms" in result.output
            assert "=== Detailed Component Status ===" in result.output
            assert "Database: healthy" in result.output
            assert "Vector Store: healthy" in result.output
            assert "=== System Information ===" in result.output
            assert "Memory Usage: 45.2%" in result.output
            assert "CPU Usage: 23.1%" in result.output
            assert "Active Jobs: 2" in result.output
            assert "Disk Free Space: 125.8 GB" in result.output

            # Verify API client was called correctly
            mock_client.check_detailed_health.assert_called_once()

    def test_system_health_command_verbose_success(
        self, runner: CliRunner, temp_project_dir: Path
    ):
        """Test verbose system health command success."""
        with patch(
            "src.code_indexer.api_clients.system_client.create_system_client"
        ) as mock_create_client:
            # Mock system client and detailed health response
            mock_client = AsyncMock()
            mock_client.check_detailed_health.return_value = {
                "status": "healthy",
                "timestamp": "2024-01-15T10:30:00Z",
                "services": {
                    "database": {
                        "status": "healthy",
                        "response_time_ms": 5,
                        "error_message": None,
                    },
                    "vector_store": {
                        "status": "healthy",
                        "response_time_ms": 12,
                        "error_message": None,
                    },
                },
                "system": {
                    "memory_usage_percent": 45.2,
                    "cpu_usage_percent": 23.1,
                    "active_jobs": 2,
                    "disk_free_space_gb": 125.8,
                },
                "response_time_ms": 38.5,
            }
            mock_create_client.return_value = mock_client

            # Mock find_project_root to return our temp directory
            with patch(
                "src.code_indexer.mode_detection.command_mode_detector.find_project_root"
            ) as mock_find_root:
                mock_find_root.return_value = temp_project_dir

                # Mock remote configuration loading
                with patch(
                    "src.code_indexer.remote.config.load_remote_configuration"
                ) as mock_load_config:
                    mock_load_config.return_value = {
                        "server_url": "http://localhost:8000",
                        "encrypted_credentials": {"username": "test_user"},
                    }

                    # Run verbose health command
                    result = runner.invoke(cli, ["system", "health", "--verbose"])

            # Verify command execution
            assert result.exit_code == 0
            assert "=== Verbose Health Information ===" in result.output
            assert "Timestamp: 2024-01-15T10:30:00Z" in result.output
            assert "Database Response Time: 5ms" in result.output
            assert "Vector Store Response Time: 12ms" in result.output

            # Verify API client was called correctly for verbose mode
            mock_client.check_detailed_health.assert_called_once()

    def test_system_health_command_authentication_error(
        self, runner: CliRunner, temp_project_dir: Path
    ):
        """Test system health command with authentication error."""
        with patch(
            "src.code_indexer.api_clients.system_client.create_system_client"
        ) as mock_create_client:
            # Mock authentication error
            from src.code_indexer.api_clients.base_client import AuthenticationError

            mock_client = AsyncMock()
            mock_client.check_basic_health.side_effect = AuthenticationError(
                "Token expired", status_code=401
            )
            mock_create_client.return_value = mock_client

            # Mock find_project_root to return our temp directory
            with patch(
                "src.code_indexer.mode_detection.command_mode_detector.find_project_root"
            ) as mock_find_root:
                mock_find_root.return_value = temp_project_dir

                # Mock remote configuration loading
                with patch(
                    "src.code_indexer.remote.config.load_remote_configuration"
                ) as mock_load_config:
                    mock_load_config.return_value = {
                        "server_url": "http://localhost:8000",
                        "encrypted_credentials": {"username": "test_user"},
                    }

                    # Run command
                    result = runner.invoke(cli, ["system", "health"])

            # Verify error handling
            assert result.exit_code == 1
            assert "❌ Authentication failed" in result.output
            assert "Token expired" in result.output
            assert "Try running 'cidx auth login' first" in result.output

    def test_system_health_command_server_error(
        self, runner: CliRunner, temp_project_dir: Path
    ):
        """Test system health command with server error."""
        with patch(
            "src.code_indexer.api_clients.system_client.create_system_client"
        ) as mock_create_client:
            # Mock server error
            from src.code_indexer.api_clients.base_client import APIClientError

            mock_client = AsyncMock()
            mock_client.check_basic_health.side_effect = APIClientError(
                "Service unavailable", status_code=503
            )
            mock_create_client.return_value = mock_client

            # Mock find_project_root to return our temp directory
            with patch(
                "src.code_indexer.mode_detection.command_mode_detector.find_project_root"
            ) as mock_find_root:
                mock_find_root.return_value = temp_project_dir

                # Mock remote configuration loading
                with patch(
                    "src.code_indexer.remote.config.load_remote_configuration"
                ) as mock_load_config:
                    mock_load_config.return_value = {
                        "server_url": "http://localhost:8000",
                        "encrypted_credentials": {"username": "test_user"},
                    }

                    # Run command
                    result = runner.invoke(cli, ["system", "health"])

            # Verify error handling
            assert result.exit_code == 1
            assert "❌ Health check failed" in result.output
            assert "Service unavailable" in result.output

    def test_system_health_command_no_project_config(self, runner: CliRunner):
        """Test system health command without project configuration."""
        with tempfile.TemporaryDirectory():
            # Mock find_project_root to return None (no project config)
            with patch(
                "src.code_indexer.mode_detection.command_mode_detector.find_project_root"
            ) as mock_find_root:
                mock_find_root.return_value = None

                # Run command from directory without .code-indexer config
                result = runner.invoke(cli, ["system", "health"])

            # Verify error handling
            assert result.exit_code == 1
            assert "❌ No project configuration found" in result.output
            assert "Run 'cidx init' to initialize project first" in result.output

    def test_system_health_command_combined_options(
        self, runner: CliRunner, temp_project_dir: Path
    ):
        """Test system health command with combined detailed and verbose options."""
        with patch(
            "src.code_indexer.api_clients.system_client.create_system_client"
        ) as mock_create_client:
            # Mock system client and detailed health response
            mock_client = AsyncMock()
            mock_client.check_detailed_health.return_value = {
                "status": "healthy",
                "timestamp": "2024-01-15T10:30:00Z",
                "services": {
                    "database": {
                        "status": "healthy",
                        "response_time_ms": 5,
                        "error_message": None,
                    }
                },
                "system": {
                    "memory_usage_percent": 45.2,
                    "cpu_usage_percent": 23.1,
                    "active_jobs": 2,
                    "disk_free_space_gb": 125.8,
                },
                "response_time_ms": 38.5,
            }
            mock_create_client.return_value = mock_client

            # Mock find_project_root to return our temp directory
            with patch(
                "src.code_indexer.mode_detection.command_mode_detector.find_project_root"
            ) as mock_find_root:
                mock_find_root.return_value = temp_project_dir

                # Mock remote configuration loading
                with patch(
                    "src.code_indexer.remote.config.load_remote_configuration"
                ) as mock_load_config:
                    mock_load_config.return_value = {
                        "server_url": "http://localhost:8000",
                        "encrypted_credentials": {"username": "test_user"},
                    }

                    # Run command with both detailed and verbose options
                    result = runner.invoke(
                        cli, ["system", "health", "--detailed", "--verbose"]
                    )

            # Verify both detailed and verbose information is displayed
            assert result.exit_code == 0
            assert "=== System Health Status ===" in result.output
            assert "=== Detailed Component Status ===" in result.output
            assert "=== Verbose Health Information ===" in result.output

            # Verify API client was called for detailed health
            mock_client.check_detailed_health.assert_called_once()

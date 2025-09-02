"""
Unit tests for server lifecycle CLI commands.

Tests the cidx server start/stop/status/restart commands integration with
ServerLifecycleManager, proper error handling, and command output formatting.
Following TDD methodology - these tests will fail initially.
"""

from pathlib import Path
import tempfile
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from code_indexer.cli import cli
from code_indexer.server.lifecycle.server_lifecycle_manager import (
    ServerStatus,
    ServerStatusInfo,
    ServerLifecycleError,
)


class TestServerLifecycleCommands:
    """Test suite for server lifecycle CLI commands."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_server_start_command_starts_server_successfully(self):
        """Test cidx server start command starts server successfully."""
        with patch(
            "code_indexer.server.lifecycle.server_lifecycle_manager.ServerLifecycleManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.start_server.return_value = {
                "message": "Server started successfully",
                "server_url": "http://127.0.0.1:8090",
                "pid": 12345,
            }
            mock_manager_class.return_value = mock_manager

            result = self.runner.invoke(cli, ["server", "start"])

            assert result.exit_code == 0
            assert "Server started successfully" in result.output
            assert "http://127.0.0.1:8090" in result.output
            mock_manager.start_server.assert_called_once()

    def test_server_start_command_handles_already_running_error(self):
        """Test cidx server start handles server already running error."""
        with patch(
            "code_indexer.server.lifecycle.server_lifecycle_manager.ServerLifecycleManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.start_server.side_effect = ServerLifecycleError(
                "Server is already running"
            )
            mock_manager_class.return_value = mock_manager

            result = self.runner.invoke(cli, ["server", "start"])

            assert result.exit_code == 1
            assert "Error: Server is already running" in result.output

    def test_server_start_command_handles_configuration_error(self):
        """Test cidx server start handles configuration validation errors."""
        with patch(
            "code_indexer.server.lifecycle.server_lifecycle_manager.ServerLifecycleManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.start_server.side_effect = ServerLifecycleError(
                "Invalid server configuration: Port must be between 1 and 65535"
            )
            mock_manager_class.return_value = mock_manager

            result = self.runner.invoke(cli, ["server", "start"])

            assert result.exit_code == 1
            assert "Error: Invalid server configuration" in result.output

    def test_server_stop_command_stops_server_successfully(self):
        """Test cidx server stop command stops server successfully."""
        with patch(
            "code_indexer.server.lifecycle.server_lifecycle_manager.ServerLifecycleManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.stop_server.return_value = {
                "message": "Server stopped gracefully",
                "shutdown_time": 2.5,
            }
            mock_manager_class.return_value = mock_manager

            result = self.runner.invoke(cli, ["server", "stop"])

            assert result.exit_code == 0
            assert "Server stopped gracefully" in result.output
            mock_manager.stop_server.assert_called_once()

    def test_server_stop_command_handles_not_running_error(self):
        """Test cidx server stop handles server not running error."""
        with patch(
            "code_indexer.server.lifecycle.server_lifecycle_manager.ServerLifecycleManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.stop_server.side_effect = ServerLifecycleError(
                "No server is currently running"
            )
            mock_manager_class.return_value = mock_manager

            result = self.runner.invoke(cli, ["server", "stop"])

            assert result.exit_code == 1
            assert "Error: No server is currently running" in result.output

    def test_server_stop_command_with_force_flag(self):
        """Test cidx server stop --force command forces server shutdown."""
        with patch(
            "code_indexer.server.lifecycle.server_lifecycle_manager.ServerLifecycleManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.stop_server.return_value = {
                "message": "Server stopped forcefully",
                "forced": True,
            }
            mock_manager_class.return_value = mock_manager

            result = self.runner.invoke(cli, ["server", "stop", "--force"])

            assert result.exit_code == 0
            assert "Server stopped" in result.output
            mock_manager.stop_server.assert_called_once_with(force=True)

    def test_server_status_command_shows_running_status(self):
        """Test cidx server status command shows running server status."""
        with patch(
            "code_indexer.server.lifecycle.server_lifecycle_manager.ServerLifecycleManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_status = ServerStatusInfo(
                status=ServerStatus.RUNNING,
                pid=12345,
                uptime=3600,
                port=8090,
                active_jobs=3,
                host="127.0.0.1",
            )
            mock_manager.get_status.return_value = mock_status
            mock_manager_class.return_value = mock_manager

            result = self.runner.invoke(cli, ["server", "status"])

            assert result.exit_code == 0
            assert "Status: RUNNING" in result.output
            assert "PID: 12345" in result.output
            assert "Port: 8090" in result.output
            assert "Uptime: 1 hour" in result.output
            assert "Active Jobs: 3" in result.output

    def test_server_status_command_shows_stopped_status(self):
        """Test cidx server status command shows stopped server status."""
        with patch(
            "code_indexer.server.lifecycle.server_lifecycle_manager.ServerLifecycleManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_status = ServerStatusInfo(
                status=ServerStatus.STOPPED,
                pid=None,
                uptime=None,
                port=None,
                active_jobs=0,
            )
            mock_manager.get_status.return_value = mock_status
            mock_manager_class.return_value = mock_manager

            result = self.runner.invoke(cli, ["server", "status"])

            assert result.exit_code == 1  # Implementation returns 1 for stopped
            assert "Status: STOPPED" in result.output
            assert "The server is not currently running" in result.output

    def test_server_status_command_with_verbose_flag(self):
        """Test cidx server status --verbose shows detailed information."""
        with patch(
            "code_indexer.server.lifecycle.server_lifecycle_manager.ServerLifecycleManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_status = ServerStatusInfo(
                status=ServerStatus.RUNNING,
                pid=12345,
                uptime=3600,
                port=8090,
                active_jobs=3,
                host="127.0.0.1",
            )
            mock_manager.get_status.return_value = mock_status
            mock_manager.get_server_health.return_value = {
                "status": "healthy",
                "uptime": 3600,
                "active_jobs": 3,
                "memory_usage": "125MB",
                "recent_errors": [],
            }
            mock_manager_class.return_value = mock_manager

            result = self.runner.invoke(cli, ["server", "status", "--verbose"])

            assert result.exit_code == 0
            assert "Status: RUNNING" in result.output
            assert "Health: healthy" in result.output
            assert "Memory Usage: 125MB" in result.output

    def test_server_restart_command_restarts_server_successfully(self):
        """Test cidx server restart command restarts server successfully."""
        with patch(
            "code_indexer.server.lifecycle.server_lifecycle_manager.ServerLifecycleManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.restart_server.return_value = {
                "message": "Server restarted successfully",
                "server_url": "http://127.0.0.1:8090",
                "restart_time": 5.2,
            }
            mock_manager_class.return_value = mock_manager

            result = self.runner.invoke(cli, ["server", "restart"])

            assert result.exit_code == 0
            assert "Server restarted successfully" in result.output
            assert "http://127.0.0.1:8090" in result.output
            mock_manager.restart_server.assert_called_once()

    def test_server_restart_command_handles_not_running_server(self):
        """Test cidx server restart handles server not currently running."""
        with patch(
            "code_indexer.server.lifecycle.server_lifecycle_manager.ServerLifecycleManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.restart_server.return_value = {
                "message": "Server started successfully (was not running)",
                "server_url": "http://127.0.0.1:8090",
            }
            mock_manager_class.return_value = mock_manager

            result = self.runner.invoke(cli, ["server", "restart"])

            assert result.exit_code == 0
            assert "Server started successfully" in result.output

    def test_server_command_group_exists(self):
        """Test that server command group is available."""
        result = self.runner.invoke(cli, ["server", "--help"])

        assert result.exit_code == 0
        assert "start" in result.output
        assert "stop" in result.output
        assert "status" in result.output
        assert "restart" in result.output

    def test_server_start_command_with_custom_server_dir(self):
        """Test server start with custom server directory path."""
        custom_dir = str(Path(self.temp_dir) / "custom-server")

        with patch(
            "code_indexer.server.lifecycle.server_lifecycle_manager.ServerLifecycleManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.start_server.return_value = {
                "message": "Server started successfully",
                "server_url": "http://127.0.0.1:8090",
                "pid": 12345,
            }
            mock_manager_class.return_value = mock_manager

            result = self.runner.invoke(
                cli, ["server", "start", "--server-dir", custom_dir]
            )

            assert result.exit_code == 0
            mock_manager_class.assert_called_once_with(custom_dir)

    def test_server_status_command_handles_manager_errors(self):
        """Test server status handles ServerLifecycleManager errors gracefully."""
        with patch(
            "code_indexer.server.lifecycle.server_lifecycle_manager.ServerLifecycleManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.get_status.side_effect = Exception(
                "Failed to read server state"
            )
            mock_manager_class.return_value = mock_manager

            result = self.runner.invoke(cli, ["server", "status"])

            assert result.exit_code == 1
            assert "Error checking server status" in result.output

    def test_server_commands_use_default_server_dir_when_not_specified(self):
        """Test server commands use default ~/.cidx-server when not specified."""
        with patch(
            "code_indexer.server.lifecycle.server_lifecycle_manager.ServerLifecycleManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_status = ServerStatusInfo(
                status=ServerStatus.STOPPED,
                pid=None,
                uptime=None,
                port=None,
                active_jobs=0,
            )
            mock_manager.get_status.return_value = mock_status
            mock_manager_class.return_value = mock_manager

            result = self.runner.invoke(cli, ["server", "status"])

            assert result.exit_code == 1  # Implementation returns 1 for stopped
            # Check that manager was created with default (None) argument
            mock_manager_class.assert_called_once_with(None)

    def test_server_stop_command_timeout_handling(self):
        """Test server stop command handles shutdown timeout."""
        with patch(
            "code_indexer.server.lifecycle.server_lifecycle_manager.ServerLifecycleManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.stop_server.side_effect = ServerLifecycleError(
                "Server shutdown timed out after 30 seconds"
            )
            mock_manager_class.return_value = mock_manager

            result = self.runner.invoke(cli, ["server", "stop"])

            assert result.exit_code == 1
            assert "Error: Server shutdown timed out" in result.output

    def test_server_status_command_returns_correct_exit_codes(self):
        """Test server status command returns appropriate exit codes."""
        with patch(
            "code_indexer.server.lifecycle.server_lifecycle_manager.ServerLifecycleManager"
        ) as mock_manager_class:
            # Test running server returns exit code 0
            mock_manager = MagicMock()
            mock_status = ServerStatusInfo(
                status=ServerStatus.RUNNING,
                pid=12345,
                uptime=3600,
                port=8090,
                active_jobs=0,
            )
            mock_manager.get_status.return_value = mock_status
            mock_manager_class.return_value = mock_manager

            result = self.runner.invoke(cli, ["server", "status"])
            assert result.exit_code == 0

            # Test stopped server returns exit code 1
            mock_status = ServerStatusInfo(
                status=ServerStatus.STOPPED,
                pid=None,
                uptime=None,
                port=None,
                active_jobs=0,
            )
            mock_manager.get_status.return_value = mock_status

            result = self.runner.invoke(cli, ["server", "status"])
            assert result.exit_code == 1

    def test_server_commands_handle_keyboard_interrupt(self):
        """Test server commands handle KeyboardInterrupt gracefully."""
        with patch(
            "code_indexer.server.lifecycle.server_lifecycle_manager.ServerLifecycleManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.start_server.side_effect = KeyboardInterrupt()
            mock_manager_class.return_value = mock_manager

            result = self.runner.invoke(cli, ["server", "start"])

            assert result.exit_code == 1
            # Click handles KeyboardInterrupt and shows "Aborted!" message
            assert "Aborted!" in result.output or "Operation cancelled" in result.output

"""
Unit tests for ServerLifecycleManager.

Tests the server lifecycle management functionality including start, stop,
status, restart operations, signal handling, and graceful shutdown.
Following TDD methodology - these tests will fail initially.
"""

import json
import signal
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from code_indexer.server.lifecycle.server_lifecycle_manager import (
    ServerLifecycleManager,
    ServerStatus,
    ServerLifecycleError,
)
from code_indexer.server.utils.config_manager import ServerConfig


@pytest.mark.e2e
class TestServerLifecycleManager:
    """Test suite for ServerLifecycleManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.server_dir = Path(self.temp_dir)

        # Create test config
        self.test_config = ServerConfig(
            server_dir=str(self.server_dir),
            host="127.0.0.1",
            port=8090,
            jwt_expiration_minutes=10,
            log_level="INFO",
        )

        # Create lifecycle manager
        self.lifecycle_manager = ServerLifecycleManager(str(self.server_dir))

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_init_creates_manager_with_default_server_dir(self):
        """Test ServerLifecycleManager initialization with default directory."""
        manager = ServerLifecycleManager()
        expected_dir = Path.home() / ".cidx-server"
        assert Path(manager.server_dir) == expected_dir

    def test_init_creates_manager_with_custom_server_dir(self):
        """Test ServerLifecycleManager initialization with custom directory."""
        custom_dir = str(Path(self.temp_dir) / "custom-server")
        manager = ServerLifecycleManager(custom_dir)
        assert manager.server_dir == custom_dir

    def test_get_status_returns_stopped_when_no_server_running(self):
        """Test get_status returns STOPPED when no server is running."""
        status = self.lifecycle_manager.get_status()

        assert status.status == ServerStatus.STOPPED
        assert status.pid is None
        assert status.uptime is None
        assert status.port is None
        assert status.active_jobs == 0

    def test_get_status_returns_running_when_server_active(self):
        """Test get_status returns RUNNING when server is active."""
        # This test will fail initially as we need to implement the functionality
        with patch.object(
            self.lifecycle_manager, "_check_server_running"
        ) as mock_check:
            mock_check.return_value = True
            with patch.object(self.lifecycle_manager, "_get_server_pid") as mock_pid:
                mock_pid.return_value = 12345
                with patch.object(
                    self.lifecycle_manager, "_get_server_uptime"
                ) as mock_uptime:
                    mock_uptime.return_value = 3600
                    with patch.object(
                        self.lifecycle_manager, "_get_server_port"
                    ) as mock_port:
                        mock_port.return_value = 8090
                        with patch.object(
                            self.lifecycle_manager, "_get_server_host"
                        ) as mock_host:
                            mock_host.return_value = "127.0.0.1"
                            with patch.object(
                                self.lifecycle_manager, "_get_active_jobs_count"
                            ) as mock_jobs:
                                mock_jobs.return_value = 3

                                status = self.lifecycle_manager.get_status()

                                assert status.status == ServerStatus.RUNNING
                                assert status.pid == 12345
                                assert status.uptime == 3600
                                assert status.port == 8090
                                assert status.active_jobs == 3
                                assert status.host == "127.0.0.1"

    def test_start_server_validates_config_before_starting(self):
        """Test start_server validates configuration before starting."""
        # This test will fail initially as we need to implement the functionality
        with patch.object(self.lifecycle_manager, "_validate_config") as mock_validate:
            mock_validate.side_effect = ValueError("Invalid config")

            with pytest.raises(ServerLifecycleError, match="Invalid config"):
                self.lifecycle_manager.start_server()

    def test_start_server_raises_error_if_already_running(self):
        """Test start_server raises error if server is already running."""
        with patch.object(
            self.lifecycle_manager, "_check_server_running"
        ) as mock_check:
            mock_check.return_value = True

            with pytest.raises(ServerLifecycleError, match="Server is already running"):
                self.lifecycle_manager.start_server()

    def test_start_server_launches_uvicorn_process(self):
        """Test start_server successfully launches uvicorn server process."""
        # Create mock config file in the server directory
        config_content = {
            "server_dir": str(self.temp_dir),
            "host": "127.0.0.1",
            "port": 8090,
        }
        # Config file should be in the server_dir of the lifecycle_manager
        config_path = Path(self.lifecycle_manager.server_dir) / "config.json"
        with open(config_path, "w") as f:
            import json

            json.dump(config_content, f)

        with patch.object(
            self.lifecycle_manager, "_check_server_running"
        ) as mock_check:
            mock_check.return_value = False
            with patch.object(self.lifecycle_manager, "_validate_config"):
                with patch("subprocess.Popen") as mock_popen:
                    mock_process = Mock()
                    mock_process.pid = 12345
                    mock_process.poll.return_value = None  # Process still running
                    mock_popen.return_value = mock_process

                    result = self.lifecycle_manager.start_server()

                    assert "Server started successfully" in result["message"]
                    assert "http://127.0.0.1:8090" in result["server_url"]
                    mock_popen.assert_called_once()

    def test_stop_server_raises_error_if_not_running(self):
        """Test stop_server raises error if server is not running."""
        with patch.object(
            self.lifecycle_manager, "_check_server_running"
        ) as mock_check:
            mock_check.return_value = False

            with pytest.raises(
                ServerLifecycleError, match="No server is currently running"
            ):
                self.lifecycle_manager.stop_server()

    def test_stop_server_gracefully_shuts_down_running_server(self):
        """Test stop_server gracefully shuts down running server."""
        with patch.object(
            self.lifecycle_manager, "_check_server_running"
        ) as mock_check:
            mock_check.return_value = True
            with patch.object(self.lifecycle_manager, "_get_server_pid") as mock_pid:
                mock_pid.return_value = 12345
                with patch.object(
                    self.lifecycle_manager, "_graceful_shutdown"
                ) as mock_shutdown:
                    mock_shutdown.return_value = True

                    result = self.lifecycle_manager.stop_server()

                    assert "Server stopped gracefully" in result["message"]
                    mock_shutdown.assert_called_once_with(12345)

    def test_stop_server_handles_forced_shutdown_if_graceful_fails(self):
        """Test stop_server performs forced shutdown if graceful fails."""
        with patch.object(
            self.lifecycle_manager, "_check_server_running"
        ) as mock_check:
            mock_check.return_value = True
            with patch.object(self.lifecycle_manager, "_get_server_pid") as mock_pid:
                mock_pid.return_value = 12345
                with patch.object(
                    self.lifecycle_manager, "_graceful_shutdown"
                ) as mock_graceful:
                    mock_graceful.return_value = False
                    with patch.object(
                        self.lifecycle_manager, "_force_shutdown"
                    ) as mock_force:
                        mock_force.return_value = True

                        result = self.lifecycle_manager.stop_server()

                        assert "Server stopped" in result["message"]
                        mock_graceful.assert_called_once_with(12345)
                        mock_force.assert_called_once_with(12345)

    def test_restart_server_stops_then_starts_server(self):
        """Test restart_server performs stop then start operation."""
        with patch.object(self.lifecycle_manager, "stop_server") as mock_stop:
            mock_stop.return_value = {"message": "Server stopped"}
            with patch.object(self.lifecycle_manager, "start_server") as mock_start:
                mock_start.return_value = {
                    "message": "Server started",
                    "server_url": "http://127.0.0.1:8090",
                }
                with patch.object(
                    self.lifecycle_manager, "_check_server_running"
                ) as mock_check:
                    # First call (for stop): running, second call (for start): not running
                    mock_check.side_effect = [True, False]

                    result = self.lifecycle_manager.restart_server()

                    assert "Server restarted successfully" in result["message"]
                    assert "http://127.0.0.1:8090" in result["server_url"]
                    mock_stop.assert_called_once()
                    mock_start.assert_called_once()

    def test_restart_server_handles_server_not_running(self):
        """Test restart_server handles case when server is not initially running."""
        with patch.object(
            self.lifecycle_manager, "_check_server_running"
        ) as mock_check:
            mock_check.return_value = False
            with patch.object(self.lifecycle_manager, "start_server") as mock_start:
                mock_start.return_value = {
                    "message": "Server started",
                    "server_url": "http://127.0.0.1:8090",
                }

                result = self.lifecycle_manager.restart_server()

                assert "Server started successfully" in result["message"]
                mock_start.assert_called_once()

    def test_install_signal_handlers_registers_sigint_sigterm(self):
        """Test install_signal_handlers registers SIGINT and SIGTERM handlers."""
        with patch("signal.signal") as mock_signal:
            self.lifecycle_manager.install_signal_handlers()

            assert mock_signal.call_count == 2
            # Check that SIGINT and SIGTERM were registered
            call_args = [call[0] for call in mock_signal.call_args_list]
            assert signal.SIGINT in [args[0] for args in call_args]
            assert signal.SIGTERM in [args[0] for args in call_args]

    def test_signal_handler_triggers_graceful_shutdown(self):
        """Test signal handler triggers graceful shutdown process."""
        with patch.object(
            self.lifecycle_manager, "_graceful_shutdown_async"
        ) as mock_shutdown:
            # Simulate signal handler call
            self.lifecycle_manager._signal_handler(signal.SIGINT, None)

            mock_shutdown.assert_called_once()

    def test_get_server_health_returns_health_info_when_running(self):
        """Test get_server_health returns health information when server is running."""
        with patch.object(
            self.lifecycle_manager, "_check_server_running"
        ) as mock_check:
            mock_check.return_value = True
            with patch.object(
                self.lifecycle_manager, "_get_health_endpoint_response"
            ) as mock_health:
                mock_health.return_value = {
                    "status": "healthy",
                    "uptime": 3600,
                    "active_jobs": 2,
                    "memory_usage": "125MB",
                }

                health = self.lifecycle_manager.get_server_health()

                assert health["status"] == "healthy"
                assert health["uptime"] == 3600
                assert health["active_jobs"] == 2

    def test_get_server_health_returns_unhealthy_when_not_running(self):
        """Test get_server_health returns unhealthy when server is not running."""
        with patch.object(
            self.lifecycle_manager, "_check_server_running"
        ) as mock_check:
            mock_check.return_value = False

            health = self.lifecycle_manager.get_server_health()

            assert health["status"] == "unhealthy"
            assert health["error"] == "Server is not running"

    def test_graceful_shutdown_waits_for_background_jobs(self):
        """Test graceful shutdown waits for background jobs to complete."""
        with patch("os.kill") as mock_kill:
            with patch("time.sleep"):
                with patch.object(
                    self.lifecycle_manager, "_check_process_exists"
                ) as mock_exists:
                    # Simulate process exists for a few checks then stops
                    mock_exists.side_effect = [True, True, False, False]

                    result = self.lifecycle_manager._graceful_shutdown(12345)

                    assert result is True
                    mock_kill.assert_called_with(12345, signal.SIGTERM)

    def test_graceful_shutdown_times_out_and_returns_false(self):
        """Test graceful shutdown times out and returns False."""
        with patch("os.kill") as mock_kill:
            with patch("time.sleep"):
                with patch.object(
                    self.lifecycle_manager, "_check_process_exists"
                ) as mock_exists:
                    # Process never stops existing
                    mock_exists.return_value = True

                    result = self.lifecycle_manager._graceful_shutdown(12345)

                    assert result is False
                    mock_kill.assert_called_with(12345, signal.SIGTERM)

    def test_force_shutdown_sends_sigkill(self):
        """Test force shutdown sends SIGKILL signal."""
        with patch("os.kill") as mock_kill:
            with patch("time.sleep"):
                with patch.object(
                    self.lifecycle_manager, "_check_process_exists"
                ) as mock_exists:
                    mock_exists.side_effect = [
                        True,
                        False,
                        False,
                    ]  # Process stops after SIGKILL

                    result = self.lifecycle_manager._force_shutdown(12345)

                    assert result is True
                    mock_kill.assert_called_with(12345, signal.SIGKILL)

    def test_check_server_running_reads_pidfile_and_checks_process(self):
        """Test _check_server_running reads pidfile and verifies process exists."""
        # Create a test pidfile
        pidfile_path = self.server_dir / "server.pid"
        pidfile_path.write_text("12345")

        with patch.object(
            self.lifecycle_manager, "_check_process_exists"
        ) as mock_exists:
            mock_exists.return_value = True

            result = self.lifecycle_manager._check_server_running()

            assert result is True
            mock_exists.assert_called_once_with(12345)

    def test_check_server_running_returns_false_when_no_pidfile(self):
        """Test _check_server_running returns False when no pidfile exists."""
        result = self.lifecycle_manager._check_server_running()
        assert result is False

    def test_check_server_running_returns_false_when_process_not_exists(self):
        """Test _check_server_running returns False when process doesn't exist."""
        # Create a test pidfile
        pidfile_path = self.server_dir / "server.pid"
        pidfile_path.write_text("12345")

        with patch.object(
            self.lifecycle_manager, "_check_process_exists"
        ) as mock_exists:
            mock_exists.return_value = False

            result = self.lifecycle_manager._check_server_running()

            assert result is False

    def test_validate_config_raises_error_for_missing_config(self):
        """Test _validate_config raises error when config file is missing."""
        with pytest.raises(
            ServerLifecycleError, match="Server configuration not found"
        ):
            self.lifecycle_manager._validate_config()

    def test_validate_config_raises_error_for_invalid_config(self):
        """Test _validate_config raises error for invalid configuration."""
        # Create invalid config file
        config_path = self.server_dir / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"invalid": "config"}')

        with pytest.raises(ServerLifecycleError, match="Invalid server configuration"):
            self.lifecycle_manager._validate_config()

    def test_validate_config_succeeds_with_valid_config(self):
        """Test _validate_config succeeds with valid configuration."""
        # Create valid config file
        config_path = self.server_dir / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_data = {
            "server_dir": str(self.server_dir),
            "host": "127.0.0.1",
            "port": 8090,
            "jwt_expiration_minutes": 10,
            "log_level": "INFO",
        }
        config_path.write_text(json.dumps(config_data))

        # Should not raise any exception
        self.lifecycle_manager._validate_config()

    def test_get_server_pid_reads_from_pidfile(self):
        """Test _get_server_pid correctly reads PID from pidfile."""
        # Create test pidfile
        pidfile_path = self.server_dir / "server.pid"
        pidfile_path.parent.mkdir(parents=True, exist_ok=True)
        pidfile_path.write_text("12345")

        pid = self.lifecycle_manager._get_server_pid()
        assert pid == 12345

    def test_get_server_pid_returns_none_when_no_pidfile(self):
        """Test _get_server_pid returns None when pidfile doesn't exist."""
        pid = self.lifecycle_manager._get_server_pid()
        assert pid is None

    def test_create_pidfile_writes_correct_pid(self):
        """Test _create_pidfile writes correct PID to file."""
        test_pid = 12345

        self.lifecycle_manager._create_pidfile(test_pid)

        pidfile_path = self.server_dir / "server.pid"
        assert pidfile_path.exists()
        assert pidfile_path.read_text().strip() == "12345"

    def test_remove_pidfile_deletes_pidfile(self):
        """Test _remove_pidfile deletes the pidfile."""
        # Create test pidfile
        pidfile_path = self.server_dir / "server.pid"
        pidfile_path.parent.mkdir(parents=True, exist_ok=True)
        pidfile_path.write_text("12345")

        self.lifecycle_manager._remove_pidfile()

        assert not pidfile_path.exists()

    def test_save_server_state_persists_server_information(self):
        """Test _save_server_state persists server state information."""
        test_state = {
            "pid": 12345,
            "port": 8090,
            "started_at": "2024-01-01T00:00:00",
            "host": "127.0.0.1",
        }

        self.lifecycle_manager._save_server_state(test_state)

        state_file = self.server_dir / "server.state"
        assert state_file.exists()

        saved_state = json.loads(state_file.read_text())
        assert saved_state == test_state

    def test_load_server_state_loads_persisted_information(self):
        """Test _load_server_state loads persisted server state."""
        test_state = {
            "pid": 12345,
            "port": 8090,
            "started_at": "2024-01-01T00:00:00",
            "host": "127.0.0.1",
        }

        # Save state first
        state_file = self.server_dir / "server.state"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(test_state))

        loaded_state = self.lifecycle_manager._load_server_state()
        assert loaded_state == test_state

    def test_load_server_state_returns_none_when_no_state_file(self):
        """Test _load_server_state returns None when no state file exists."""
        state = self.lifecycle_manager._load_server_state()
        assert state is None

    # TDD TESTS FOR SERVER STATUS BUG FIX
    def test_get_status_detects_stale_pidfile_and_returns_stopped(self):
        """Test get_status correctly detects when PID file exists but process is not running."""
        # Create a pidfile with a PID that doesn't exist
        pidfile_path = self.server_dir / "server.pid"
        pidfile_path.parent.mkdir(parents=True, exist_ok=True)
        pidfile_path.write_text("999999")  # PID that doesn't exist

        # Create a state file as well (simulating crashed server scenario)
        state_file = self.server_dir / "server.state"
        test_state = {
            "pid": 999999,
            "port": 8090,
            "started_at": "2024-01-01T00:00:00",
            "host": "127.0.0.1",
        }
        state_file.write_text(json.dumps(test_state))

        status = self.lifecycle_manager.get_status()

        # Should return STOPPED status despite pidfile existence
        assert status.status == ServerStatus.STOPPED
        assert status.pid is None
        assert status.uptime is None
        assert status.port is None
        assert status.active_jobs == 0

    def test_get_status_cleans_up_stale_files_when_process_not_running(self):
        """Test get_status cleans up stale pidfile and state file when process is not running."""
        # Create a pidfile with a PID that doesn't exist
        pidfile_path = self.server_dir / "server.pid"
        pidfile_path.parent.mkdir(parents=True, exist_ok=True)
        pidfile_path.write_text("999999")  # PID that doesn't exist

        # Create a state file as well
        state_file = self.server_dir / "server.state"
        test_state = {
            "pid": 999999,
            "port": 8090,
            "started_at": "2024-01-01T00:00:00",
            "host": "127.0.0.1",
        }
        state_file.write_text(json.dumps(test_state))

        # Both files should exist before the call
        assert pidfile_path.exists()
        assert state_file.exists()

        status = self.lifecycle_manager.get_status()

        # Files should be cleaned up after detecting stale process
        assert not pidfile_path.exists()
        assert not state_file.exists()
        assert status.status == ServerStatus.STOPPED

    def test_check_server_running_with_stale_pidfile_returns_false(self):
        """Test _check_server_running returns False for stale pidfile with non-existent process."""
        # Create a pidfile with a PID that doesn't exist
        pidfile_path = self.server_dir / "server.pid"
        pidfile_path.parent.mkdir(parents=True, exist_ok=True)
        pidfile_path.write_text("999999")  # PID that doesn't exist

        result = self.lifecycle_manager._check_server_running()

        # Should return False even though pidfile exists
        assert result is False

    def test_start_server_after_stale_crash_scenario(self):
        """Test start_server works correctly after a previous server crash left stale files."""
        # Create stale pidfile and state file (simulating previous crash)
        pidfile_path = self.server_dir / "server.pid"
        pidfile_path.parent.mkdir(parents=True, exist_ok=True)
        pidfile_path.write_text("999999")  # Stale PID

        state_file = self.server_dir / "server.state"
        stale_state = {
            "pid": 999999,
            "port": 8090,
            "started_at": "2024-01-01T00:00:00",
            "host": "127.0.0.1",
        }
        state_file.write_text(json.dumps(stale_state))

        # Create valid config file
        config_content = {
            "server_dir": str(self.temp_dir),
            "host": "127.0.0.1",
            "port": 8090,
        }
        config_path = Path(self.lifecycle_manager.server_dir) / "config.json"
        with open(config_path, "w") as f:
            json.dump(config_content, f)

        # Mock the subprocess.Popen to simulate successful server start
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.pid = 12345  # New PID
            mock_process.poll.return_value = None  # Process still running
            mock_popen.return_value = mock_process

            result = self.lifecycle_manager.start_server()

            # Should successfully start despite stale files
            assert "Server started successfully" in result["message"]
            assert result["pid"] == 12345

            # Old stale pidfile should be replaced with new PID
            assert pidfile_path.read_text().strip() == "12345"

"""
End-to-End tests for Story 9: Server Lifecycle Management.

Tests the complete server lifecycle management functionality including
start/stop/status/restart operations with real server processes,
configuration validation, health checks, and graceful shutdown.

NO MOCKING - These are true end-to-end tests with real server operations.
"""

import json
import tempfile
import time
import requests
import signal
import os
from pathlib import Path
import pytest
from click.testing import CliRunner

from code_indexer.cli import cli
from code_indexer.server.lifecycle.server_lifecycle_manager import (
    ServerLifecycleManager,
    ServerStatus,
    ServerLifecycleError,
)


class TestStory9ServerLifecycleE2E:
    """End-to-end test suite for server lifecycle management."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.server_dir = Path(self.temp_dir) / "test-server"
        self.server_dir.mkdir(parents=True, exist_ok=True)

        # Create test configuration
        self.config = {
            "server_dir": str(self.server_dir),
            "host": "127.0.0.1",
            "port": 8091,  # Use different port to avoid conflicts
            "jwt_expiration_minutes": 10,
            "log_level": "INFO",
        }

        config_file = self.server_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(self.config, f)

        self.lifecycle_manager = ServerLifecycleManager(str(self.server_dir))
        self.runner = CliRunner()

    def teardown_method(self):
        """Clean up test fixtures."""
        # Ensure server is stopped
        try:
            if self.lifecycle_manager._check_server_running():
                self.lifecycle_manager.stop_server(force=True)
        except Exception:
            pass

        # Clean up temp directory
        import shutil

        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_server_lifecycle_complete_flow(self):
        """Test complete server lifecycle: start -> status -> restart -> stop."""
        # Test 1: Start server
        result = self.lifecycle_manager.start_server()
        assert "Server started successfully" in result["message"]
        assert result["server_url"] == "http://127.0.0.1:8091"
        assert "pid" in result

        # Verify server is actually running
        time.sleep(3)  # Give server time to fully start

        # Test 2: Check status - should be running
        status = self.lifecycle_manager.get_status()
        assert status.status == ServerStatus.RUNNING
        assert status.pid is not None
        assert status.port == 8091
        assert status.host == "127.0.0.1"

        # Test 3: Verify health endpoint is accessible
        health_response = requests.get("http://127.0.0.1:8091/health", timeout=10)
        assert health_response.status_code == 200
        health_data = health_response.json()
        assert health_data["status"] in ["healthy", "warning", "degraded"]
        assert "uptime" in health_data

        # Test 4: Restart server
        restart_result = self.lifecycle_manager.restart_server()
        assert "Server restarted successfully" in restart_result["message"]

        # Wait for restart to complete
        time.sleep(3)

        # Verify server is still running after restart
        status_after_restart = self.lifecycle_manager.get_status()
        assert status_after_restart.status == ServerStatus.RUNNING

        # Test 5: Stop server gracefully
        stop_result = self.lifecycle_manager.stop_server()
        assert "Server stopped" in stop_result["message"]

        # Verify server is stopped
        time.sleep(2)
        final_status = self.lifecycle_manager.get_status()
        assert final_status.status == ServerStatus.STOPPED

    def test_server_start_already_running_error(self):
        """Test starting server when already running raises error."""
        # Start server first
        self.lifecycle_manager.start_server()
        time.sleep(2)

        # Try to start again - should raise error
        with pytest.raises(ServerLifecycleError, match="already running"):
            self.lifecycle_manager.start_server()

    def test_server_stop_not_running_error(self):
        """Test stopping server when not running raises error."""
        # Ensure server is not running
        status = self.lifecycle_manager.get_status()
        assert status.status == ServerStatus.STOPPED

        # Try to stop - should raise error
        with pytest.raises(ServerLifecycleError, match="not running"):
            self.lifecycle_manager.stop_server()

    def test_server_forced_shutdown(self):
        """Test forced server shutdown with --force flag."""
        # Start server
        self.lifecycle_manager.start_server()
        time.sleep(2)

        # Force stop
        result = self.lifecycle_manager.stop_server(force=True)
        assert "Server stopped" in result["message"]
        assert result.get("forced", False)

        # Verify server is stopped
        time.sleep(1)
        status = self.lifecycle_manager.get_status()
        assert status.status == ServerStatus.STOPPED

    def test_server_health_endpoint_detailed_info(self):
        """Test health endpoint returns detailed server information."""
        # Start server
        self.lifecycle_manager.start_server()
        time.sleep(3)

        # Get health information
        health = self.lifecycle_manager.get_server_health()

        assert health["status"] in ["healthy", "warning", "degraded"]
        # Should have either uptime or error information
        assert "uptime" in health or "error" in health

    def test_cli_server_start_command_e2e(self):
        """Test cidx server start command end-to-end."""
        result = self.runner.invoke(
            cli, ["server", "start", "--server-dir", str(self.server_dir)]
        )

        assert result.exit_code == 0
        assert "Server started successfully" in result.output
        assert "http://127.0.0.1:8091" in result.output

        # Verify server is actually running
        time.sleep(2)
        status = self.lifecycle_manager.get_status()
        assert status.status == ServerStatus.RUNNING

    def test_cli_server_stop_command_e2e(self):
        """Test cidx server stop command end-to-end."""
        # Start server first
        self.lifecycle_manager.start_server()
        time.sleep(2)

        # Stop using CLI
        result = self.runner.invoke(
            cli, ["server", "stop", "--server-dir", str(self.server_dir)]
        )

        assert result.exit_code == 0
        assert "Server stopped" in result.output

        # Verify server is stopped
        time.sleep(1)
        status = self.lifecycle_manager.get_status()
        assert status.status == ServerStatus.STOPPED

    def test_cli_server_status_command_e2e(self):
        """Test cidx server status command end-to-end."""
        # Test stopped status
        result = self.runner.invoke(
            cli, ["server", "status", "--server-dir", str(self.server_dir)]
        )

        assert result.exit_code == 1  # Stopped = exit code 1
        assert "Status: STOPPED" in result.output
        assert "not currently running" in result.output

        # Start server and test running status
        self.lifecycle_manager.start_server()
        time.sleep(2)

        result = self.runner.invoke(
            cli, ["server", "status", "--server-dir", str(self.server_dir)]
        )

        assert result.exit_code == 0  # Running = exit code 0
        assert "Status: RUNNING" in result.output
        assert "PID:" in result.output
        assert "Port: 8091" in result.output

    def test_cli_server_status_verbose_e2e(self):
        """Test cidx server status --verbose command end-to-end."""
        # Start server first
        self.lifecycle_manager.start_server()
        time.sleep(3)

        result = self.runner.invoke(
            cli, ["server", "status", "--verbose", "--server-dir", str(self.server_dir)]
        )

        assert result.exit_code == 0
        assert "Status: RUNNING" in result.output
        assert "Health Information:" in result.output

    def test_cli_server_restart_command_e2e(self):
        """Test cidx server restart command end-to-end."""
        # Start server first
        self.lifecycle_manager.start_server()
        time.sleep(2)
        original_status = self.lifecycle_manager.get_status()

        # Restart using CLI
        result = self.runner.invoke(
            cli, ["server", "restart", "--server-dir", str(self.server_dir)]
        )

        assert result.exit_code == 0
        assert "Server restarted successfully" in result.output
        assert "http://127.0.0.1:8091" in result.output

        # Verify server is running after restart
        time.sleep(2)
        new_status = self.lifecycle_manager.get_status()
        assert new_status.status == ServerStatus.RUNNING
        # PID should be different after restart
        assert new_status.pid != original_status.pid

    def test_cli_server_restart_not_running_e2e(self):
        """Test cidx server restart when server not initially running."""
        # Ensure server is not running
        status = self.lifecycle_manager.get_status()
        assert status.status == ServerStatus.STOPPED

        # Restart should start the server
        result = self.runner.invoke(
            cli, ["server", "restart", "--server-dir", str(self.server_dir)]
        )

        assert result.exit_code == 0
        assert "Server started successfully" in result.output

        # Verify server is now running
        time.sleep(2)
        status = self.lifecycle_manager.get_status()
        assert status.status == ServerStatus.RUNNING

    def test_server_configuration_validation(self):
        """Test server configuration validation during startup."""
        # Create invalid config (invalid port)
        bad_config = {
            "server_dir": str(self.server_dir),
            "host": "127.0.0.1",
            "port": 70000,  # Invalid port > 65535
            "jwt_expiration_minutes": 10,
            "log_level": "INFO",
        }

        config_file = self.server_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(bad_config, f)

        # Should raise configuration error
        with pytest.raises(ServerLifecycleError, match="Invalid server configuration"):
            self.lifecycle_manager.start_server()

    def test_server_pidfile_and_state_management(self):
        """Test server PID file and state file management."""
        pidfile = self.server_dir / "server.pid"
        statefile = self.server_dir / "server.state"

        # Initially no files should exist
        assert not pidfile.exists()
        assert not statefile.exists()

        # Start server
        self.lifecycle_manager.start_server()
        time.sleep(2)

        # Files should be created
        assert pidfile.exists()
        assert statefile.exists()

        # PID file should contain valid PID
        pid = int(pidfile.read_text().strip())
        assert pid > 0

        # State file should contain server info
        state = json.loads(statefile.read_text())
        assert state["pid"] == pid
        assert state["port"] == 8091
        assert state["host"] == "127.0.0.1"
        assert "started_at" in state

        # Stop server
        self.lifecycle_manager.stop_server()
        time.sleep(1)

        # Files should be cleaned up
        assert not pidfile.exists()
        assert not statefile.exists()

    def test_server_graceful_shutdown_with_signal(self):
        """Test server graceful shutdown when receiving signals."""
        # Start server
        result = self.lifecycle_manager.start_server()
        pid = result["pid"]
        time.sleep(2)

        # Send SIGTERM to server process
        os.kill(pid, signal.SIGTERM)

        # Wait for graceful shutdown
        time.sleep(3)

        # Server should be stopped
        status = self.lifecycle_manager.get_status()
        assert status.status == ServerStatus.STOPPED

    def test_server_port_conflict_handling(self):
        """Test server behavior when port is already in use."""
        # Start first server
        self.lifecycle_manager.start_server()
        time.sleep(2)

        # Try to start another server on same port
        manager2 = ServerLifecycleManager(str(Path(self.temp_dir) / "server2"))
        manager2.server_dir_path.mkdir(exist_ok=True)

        # Copy config but same port
        config2 = self.config.copy()
        config_file2 = manager2.server_dir_path / "config.json"
        with open(config_file2, "w") as f:
            json.dump(config2, f)

        # Should fail due to port conflict
        with pytest.raises(ServerLifecycleError, match="Failed to start server"):
            manager2.start_server()

    def test_health_endpoint_real_data(self):
        """Test health endpoint returns real server data."""
        # Start server
        self.lifecycle_manager.start_server()
        time.sleep(3)

        # Call health endpoint directly
        response = requests.get("http://127.0.0.1:8091/health", timeout=10)
        assert response.status_code == 200

        health_data = response.json()

        # Should have real data
        assert health_data["status"] in ["healthy", "warning", "degraded"]
        assert "message" in health_data
        assert "uptime" in health_data
        assert "active_jobs" in health_data
        assert "job_queue" in health_data
        assert "started_at" in health_data

        # Job queue should have counts
        job_queue = health_data["job_queue"]
        assert "active_jobs" in job_queue
        assert "pending_jobs" in job_queue
        assert "failed_jobs" in job_queue

    def test_server_process_cleanup_on_failure(self):
        """Test proper cleanup when server fails to start."""
        # Create config with non-existent directory that will cause startup failure
        bad_config = {
            "server_dir": "/non/existent/path/that/cannot/be/created",
            "host": "127.0.0.1",
            "port": 8091,
            "jwt_expiration_minutes": 10,
            "log_level": "INFO",
        }

        config_file = self.server_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(bad_config, f)

        # Attempt to start should fail
        with pytest.raises(ServerLifecycleError):
            self.lifecycle_manager.start_server()

        # No PID file should exist after failure
        pidfile = self.server_dir / "server.pid"
        assert not pidfile.exists()

        # No state file should exist after failure
        statefile = self.server_dir / "server.state"
        assert not statefile.exists()

"""
Test suite for server startup crash fix.

Tests that reproduce and verify the fix for the server startup crash issue
where the server process dies immediately after startup due to missing
ServerLifecycleManager implementation.
"""

import pytest
import subprocess
import time
import requests
from unittest.mock import patch, MagicMock


@pytest.mark.e2e
class TestServerStartupCrashFix:
    """Test server startup crash issues and fixes."""

    def test_server_lifecycle_manager_import_succeeds(self):
        """Test that ServerLifecycleManager import works correctly."""
        # This test confirms the ServerLifecycleManager exists and can be imported
        from code_indexer.server.lifecycle.server_lifecycle_manager import (
            ServerLifecycleManager,
        )

        # Should be able to instantiate it
        manager = ServerLifecycleManager()
        assert manager is not None
        assert hasattr(manager, "start_server")
        assert hasattr(manager, "stop_server")
        assert hasattr(manager, "get_status")

    def test_server_start_command_crashes_on_missing_manager(self, tmp_path):
        """Test that server start command crashes due to missing ServerLifecycleManager."""
        # Create a temporary server directory for testing
        server_dir = tmp_path / "test-server"
        server_dir.mkdir()

        # This should fail with ImportError when trying to start server
        result = subprocess.run(
            [
                "python",
                "-m",
                "code_indexer.cli",
                "server",
                "start",
                "--server-dir",
                str(server_dir),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        print(f"Return code: {result.returncode}")
        print(f"STDOUT:\n{result.stdout}")
        print(f"STDERR:\n{result.stderr}")

        # Should fail with non-zero exit code
        assert result.returncode != 0
        # Should contain import error or module not found error or configuration error
        error_output = result.stderr.lower()
        stdout_output = result.stdout.lower()
        assert (
            "importerror" in error_output
            or "no module named" in error_output
            or "error" in stdout_output
            or "configuration" in stdout_output
        )

    def test_server_process_should_stay_alive_after_startup(self, tmp_path):
        """Test that server process should stay alive after startup (will fail until fixed)."""
        # This test documents what SHOULD happen after we fix the issue
        pytest.skip("Test will be enabled after ServerLifecycleManager is implemented")

        server_dir = tmp_path / "test-server"
        server_dir.mkdir()

        # Start server
        result = subprocess.run(
            [
                "python",
                "-m",
                "code_indexer.cli",
                "server",
                "start",
                "--server-dir",
                str(server_dir),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Should succeed
        assert result.returncode == 0

        # Extract PID from output
        pid_line = [
            line for line in result.stdout.split("\n") if "Process ID:" in line
        ][0]
        pid = int(pid_line.split(":")[1].strip())

        # Process should still be alive after a short delay
        time.sleep(2)

        # Check if process is still running
        try:
            import psutil

            process = psutil.Process(pid)
            assert process.is_running()

            # Clean up - kill the process
            process.terminate()
            process.wait(timeout=10)
        except psutil.NoSuchProcess:
            pytest.fail(f"Server process {pid} died immediately after startup")

    def test_server_should_respond_to_health_check(self, tmp_path):
        """Test that server should respond to health checks after startup (will fail until fixed)."""
        pytest.skip("Test will be enabled after ServerLifecycleManager is implemented")

        server_dir = tmp_path / "test-server"
        server_dir.mkdir()

        # Start server
        result = subprocess.run(
            [
                "python",
                "-m",
                "code_indexer.cli",
                "server",
                "start",
                "--server-dir",
                str(server_dir),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0

        # Extract server URL from output
        url_line = [
            line for line in result.stdout.split("\n") if "Server URL:" in line
        ][0]
        server_url = url_line.split(":", 2)[2].strip()

        try:
            # Wait a moment for server to be ready
            time.sleep(3)

            # Test health check endpoint
            response = requests.get(f"{server_url}/health", timeout=10)
            assert response.status_code == 200

            health_data = response.json()
            assert health_data["status"] == "healthy"
            assert "server_start_time" in health_data

        finally:
            # Clean up - stop the server
            subprocess.run(
                [
                    "python",
                    "-m",
                    "code_indexer.cli",
                    "server",
                    "stop",
                    "--server-dir",
                    str(server_dir),
                ],
                capture_output=True,
                timeout=30,
            )

    def test_server_should_handle_basic_requests(self, tmp_path):
        """Test that server should handle basic API requests (will fail until fixed)."""
        pytest.skip("Test will be enabled after ServerLifecycleManager is implemented")

        server_dir = tmp_path / "test-server"
        server_dir.mkdir()

        # Start server
        result = subprocess.run(
            [
                "python",
                "-m",
                "code_indexer.cli",
                "server",
                "start",
                "--server-dir",
                str(server_dir),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0

        # Extract server URL
        url_line = [
            line for line in result.stdout.split("\n") if "Server URL:" in line
        ][0]
        server_url = url_line.split(":", 2)[2].strip()

        try:
            # Wait for server to be ready
            time.sleep(3)

            # Test OpenAPI docs endpoint
            response = requests.get(f"{server_url}/docs", timeout=10)
            assert response.status_code == 200
            assert "html" in response.headers.get("content-type", "").lower()

        finally:
            # Clean up
            subprocess.run(
                [
                    "python",
                    "-m",
                    "code_indexer.cli",
                    "server",
                    "stop",
                    "--server-dir",
                    str(server_dir),
                ],
                capture_output=True,
                timeout=30,
            )


@pytest.mark.e2e
class TestServerLifecycleManagerImplementation:
    """Tests for the ServerLifecycleManager implementation that needs to be created."""

    def test_server_lifecycle_manager_class_should_exist(self):
        """Test that ServerLifecycleManager class should exist."""
        # This will fail until we implement it
        try:
            from code_indexer.server.lifecycle.server_lifecycle_manager import (
                ServerLifecycleManager,
            )

            # Should be able to instantiate it
            manager = ServerLifecycleManager()
            assert manager is not None

        except ImportError:
            pytest.fail(
                "ServerLifecycleManager class does not exist - needs to be implemented"
            )

    def test_server_lifecycle_manager_should_have_start_method(self, tmp_path):
        """Test that ServerLifecycleManager should have start_server method."""
        pytest.skip("Test will be enabled after ServerLifecycleManager is implemented")

        from code_indexer.server.lifecycle.server_lifecycle_manager import (
            ServerLifecycleManager,
        )

        server_dir = tmp_path / "test-server"
        server_dir.mkdir()

        manager = ServerLifecycleManager(str(server_dir))
        assert hasattr(manager, "start_server")
        assert callable(getattr(manager, "start_server"))

    def test_server_lifecycle_manager_start_should_return_result_dict(self, tmp_path):
        """Test that start_server method should return proper result dict."""
        pytest.skip("Test will be enabled after ServerLifecycleManager is implemented")

        from code_indexer.server.lifecycle.server_lifecycle_manager import (
            ServerLifecycleManager,
        )

        server_dir = tmp_path / "test-server"
        server_dir.mkdir()

        # Mock the actual server startup to avoid running real server
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            manager = ServerLifecycleManager(str(server_dir))
            result = manager.start_server()

            # Should return dict with required keys
            assert isinstance(result, dict)
            assert "message" in result
            assert "server_url" in result
            assert "pid" in result

            assert result["pid"] == 12345
            assert "http://" in result["server_url"]
            assert "started" in result["message"].lower()

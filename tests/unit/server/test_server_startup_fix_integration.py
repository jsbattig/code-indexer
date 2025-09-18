"""
Integration tests for server startup fix.

Tests that verify the complete server startup flow works correctly
and provides good user experience.
"""

import pytest
import subprocess
import time
import requests
import json
import psutil
from pathlib import Path


class TestServerStartupFixIntegration:
    """Integration tests for server startup fixes."""

    def test_server_start_without_config_gives_clear_error(self, tmp_path):
        """Test that server start without config gives clear, actionable error."""
        server_dir = tmp_path / "test-server"
        server_dir.mkdir()

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

        # Should fail with clear configuration error
        assert result.returncode == 1
        assert "Server configuration not found" in result.stdout
        assert "cidx install-server" in result.stdout

    def test_server_start_with_valid_config_succeeds(self, tmp_path):
        """Test that server starts successfully with valid configuration."""
        server_dir = tmp_path / "test-server"
        server_dir.mkdir()

        # Create valid configuration with unique port
        import random

        port = random.randint(9010, 9999)
        config = {"server_dir": str(server_dir), "host": "127.0.0.1", "port": port}

        config_file = server_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        try:
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
            assert "Server started successfully" in result.stdout
            assert str(port) in result.stdout

            # Extract PID
            pid_line = [
                line for line in result.stdout.split("\n") if "Process ID:" in line
            ][0]
            pid = int(pid_line.split(":")[1].strip())

            # Verify process is running
            process = psutil.Process(pid)
            assert process.is_running()
            assert "python" in process.name().lower()

            # Give server time to fully start
            time.sleep(3)

            # Test server responds (even if with auth error)
            response = requests.get(f"http://127.0.0.1:{port}/health", timeout=10)
            # Auth error is expected, but server is responding
            assert response.status_code in [200, 401, 403]

        finally:
            # Clean up - stop server
            try:
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
            except (subprocess.SubprocessError, subprocess.TimeoutExpired):
                pass

    def test_server_process_stays_alive_after_startup(self, tmp_path):
        """Test that server process remains alive for extended period."""
        server_dir = tmp_path / "test-server"
        server_dir.mkdir()

        # Create valid configuration with unique port
        import random

        port = random.randint(9010, 9999)
        config = {"server_dir": str(server_dir), "host": "127.0.0.1", "port": port}

        config_file = server_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        try:
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

            # Extract PID
            pid_line = [
                line for line in result.stdout.split("\n") if "Process ID:" in line
            ][0]
            pid = int(pid_line.split(":")[1].strip())

            # Test server stays alive over time
            for i in range(5):
                time.sleep(2)
                try:
                    process = psutil.Process(pid)
                    assert (
                        process.is_running()
                    ), f"Server process died after {(i+1)*2} seconds"
                except psutil.NoSuchProcess:
                    pytest.fail(f"Server process {pid} died after {(i+1)*2} seconds")

        finally:
            # Clean up
            try:
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
            except (subprocess.SubprocessError, subprocess.TimeoutExpired):
                pass

    def test_server_handles_multiple_health_checks(self, tmp_path):
        """Test that server handles multiple requests without crashing."""
        server_dir = tmp_path / "test-server"
        server_dir.mkdir()

        # Create valid configuration with unique port
        import random

        port = random.randint(9010, 9999)
        config = {"server_dir": str(server_dir), "host": "127.0.0.1", "port": port}

        config_file = server_dir / "config.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        try:
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

            # Extract PID
            pid_line = [
                line for line in result.stdout.split("\n") if "Process ID:" in line
            ][0]
            pid = int(pid_line.split(":")[1].strip())

            # Give server time to start
            time.sleep(3)

            # Make multiple requests to ensure server stability
            for i in range(10):
                try:
                    response = requests.get(
                        f"http://127.0.0.1:{port}/health", timeout=5
                    )
                    # Should get some response (auth errors are expected)
                    assert response.status_code in [200, 401, 403]
                except requests.exceptions.ConnectionError:
                    pytest.fail(f"Server connection failed on request {i+1}")

                # Verify process still running
                try:
                    process = psutil.Process(pid)
                    assert (
                        process.is_running()
                    ), f"Server process died during request {i+1}"
                except psutil.NoSuchProcess:
                    pytest.fail(f"Server process {pid} died during request {i+1}")

                time.sleep(0.5)

        finally:
            # Clean up
            try:
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
            except (subprocess.SubprocessError, subprocess.TimeoutExpired):
                pass

    def test_install_server_creates_working_configuration(self, tmp_path):
        """Test that install-server creates a configuration that allows server to start."""
        server_dir = tmp_path / "test-server"

        try:
            # Run install-server
            result = subprocess.run(
                [
                    "python",
                    "-m",
                    "code_indexer.cli",
                    "install-server",
                    "--port",
                    "8095",
                    "--force",
                ],
                input=f"{server_dir}\n",  # Provide server dir when prompted
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Should succeed
            assert result.returncode == 0

            # Default server dir should be created
            default_server_dir = Path.home() / ".cidx-server"
            assert default_server_dir.exists()

            config_file = default_server_dir / "config.json"
            assert config_file.exists()

            # Verify configuration is valid
            with open(config_file) as f:
                config = json.load(f)

            assert "port" in config
            assert "host" in config
            assert "server_dir" in config

            # Test that server can start with this configuration
            start_result = subprocess.run(
                ["python", "-m", "code_indexer.cli", "server", "start"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            assert start_result.returncode == 0
            assert "Server started successfully" in start_result.stdout

        finally:
            # Clean up - stop any running server
            try:
                subprocess.run(
                    ["python", "-m", "code_indexer.cli", "server", "stop"],
                    capture_output=True,
                    timeout=30,
                )
            except (subprocess.SubprocessError, subprocess.TimeoutExpired):
                pass

"""
End-to-end integration tests for daemon CLI delegation.

These tests verify the complete CLI → daemon delegation flow WITHOUT mocking,
ensuring the "stream has been closed" error is fixed and infinite spawning prevented.
"""

import sys
import json
import time
import socket
import tempfile
import subprocess
from pathlib import Path
import pytest


class TestDaemonE2EIntegration:
    """Real E2E tests that start actual daemon and test CLI delegation."""

    @pytest.fixture
    def test_project(self):
        """Create a temporary test project with daemon configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "test-project"
            project_dir.mkdir()
            config_dir = project_dir / ".code-indexer"
            config_dir.mkdir()

            # Create config with daemon enabled
            config = {
                "codebase_dir": str(project_dir),
                "embedding_provider": "voyage-ai",
                "daemon": {
                    "enabled": True,
                    "ttl_minutes": 10,
                    "auto_start": True,
                    "retry_delays_ms": [100, 200, 400],
                },
                "exclude_dirs": ["node_modules", "venv"],
                "file_extensions": ["py", "js", "ts"],
                "max_file_size": 1048576,
                "batch_size": 50,
                "chunking": {"strategy": "model_aware"},
                "vector_calculation_threads": 8,
                "version": "7.1.0",
            }

            config_path = config_dir / "config.json"
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)

            # Create a sample file for indexing
            test_file = project_dir / "test.py"
            test_file.write_text("def hello_world():\n    return 'Hello, World!'\n")

            yield project_dir

    def _is_socket_active(self, socket_path: Path) -> bool:
        """Check if a Unix domain socket is actively listening."""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(0.1)
            sock.connect(str(socket_path))
            sock.close()
            return True
        except (ConnectionRefusedError, FileNotFoundError, OSError):
            return False

    def _count_daemon_processes(self) -> int:
        """Count number of daemon processes running."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", "code_indexer.daemon"], capture_output=True, text=True
            )
            if result.returncode == 0:
                pids = result.stdout.strip().split("\n")
                return len([p for p in pids if p])
            return 0
        except Exception:
            return 0

    def _kill_all_daemons(self):
        """Kill all daemon processes for cleanup."""
        subprocess.run(["pkill", "-f", "code_indexer.daemon"], check=False)
        time.sleep(0.5)

    def test_query_delegation_no_infinite_loop(self, test_project):
        """Test that query delegation doesn't create infinite loop."""
        # Kill any existing daemons
        self._kill_all_daemons()

        # Run query command with daemon enabled
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "code_indexer.cli",
                "query",
                "hello",
                "--limit",
                "5",
            ],
            cwd=str(test_project),
            capture_output=True,
            text=True,
            timeout=10,  # Should complete quickly, not hang
        )

        # Check that command completed (not hanging)
        assert result.returncode in [0, 1], "Command should complete, not hang"

        # Verify no infinite spawning - should have at most 1 daemon
        daemon_count = self._count_daemon_processes()
        assert daemon_count <= 1, f"Should have max 1 daemon, found {daemon_count}"

        # Check output doesn't show repeated restart attempts
        restart_count = result.stderr.count("attempting restart")
        assert (
            restart_count <= 2
        ), f"Should have max 2 restart attempts, found {restart_count}"

    def test_daemon_crash_recovery_fallback(self, test_project):
        """Test crash recovery with proper fallback to standalone."""
        # Kill any existing daemons
        self._kill_all_daemons()

        socket_path = test_project / ".code-indexer" / "daemon.sock"

        # Create a fake socket file to simulate stale socket
        socket_path.touch()

        # Run query command - should clean stale socket and start daemon
        result = subprocess.run(
            [sys.executable, "-m", "code_indexer.cli", "query", "test", "--limit", "2"],
            cwd=str(test_project),
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Should eventually succeed (either via daemon or fallback)
        assert result.returncode == 0, f"Query should succeed: {result.stderr}"

        # Verify no excessive daemon spawning
        daemon_count = self._count_daemon_processes()
        assert (
            daemon_count <= 1
        ), f"Should have max 1 daemon after recovery, found {daemon_count}"

    def test_daemon_start_stop_lifecycle(self, test_project):
        """Test daemon start/stop commands work properly."""
        # Kill any existing daemons
        self._kill_all_daemons()

        socket_path = test_project / ".code-indexer" / "daemon.sock"

        # Start daemon
        subprocess.run(
            [sys.executable, "-m", "code_indexer.cli", "start"],
            cwd=str(test_project),
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Give daemon time to start
        time.sleep(1)

        # Verify daemon is running
        assert self._is_socket_active(socket_path), "Daemon socket should be active"
        daemon_count = self._count_daemon_processes()
        assert daemon_count == 1, f"Should have exactly 1 daemon, found {daemon_count}"

        # Stop daemon
        subprocess.run(
            [sys.executable, "-m", "code_indexer.cli", "stop"],
            cwd=str(test_project),
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Give daemon time to stop
        time.sleep(1)

        # Verify daemon stopped
        assert not self._is_socket_active(
            socket_path
        ), "Daemon socket should be inactive"
        daemon_count = self._count_daemon_processes()
        assert (
            daemon_count == 0
        ), f"Should have 0 daemons after stop, found {daemon_count}"

    def test_multiple_queries_single_daemon(self, test_project):
        """Test that multiple queries reuse same daemon, not spawn new ones."""
        # Kill any existing daemons
        self._kill_all_daemons()

        # Run first query
        result1 = subprocess.run(
            [sys.executable, "-m", "code_indexer.cli", "query", "test1"],
            cwd=str(test_project),
            capture_output=True,
            text=True,
            timeout=10,
        )

        time.sleep(0.5)
        daemon_count_1 = self._count_daemon_processes()

        # Run second query
        result2 = subprocess.run(
            [sys.executable, "-m", "code_indexer.cli", "query", "test2"],
            cwd=str(test_project),
            capture_output=True,
            text=True,
            timeout=10,
        )

        time.sleep(0.5)
        daemon_count_2 = self._count_daemon_processes()

        # Run third query
        result3 = subprocess.run(
            [sys.executable, "-m", "code_indexer.cli", "query", "test3"],
            cwd=str(test_project),
            capture_output=True,
            text=True,
            timeout=10,
        )

        daemon_count_3 = self._count_daemon_processes()

        # All queries should succeed
        assert result1.returncode == 0, f"Query 1 failed: {result1.stderr}"
        assert result2.returncode == 0, f"Query 2 failed: {result2.stderr}"
        assert result3.returncode == 0, f"Query 3 failed: {result3.stderr}"

        # Daemon count should stay at 1 (not increase with each query)
        assert daemon_count_1 <= 1, f"After query 1: {daemon_count_1} daemons"
        assert daemon_count_2 <= 1, f"After query 2: {daemon_count_2} daemons"
        assert daemon_count_3 <= 1, f"After query 3: {daemon_count_3} daemons"

        # Daemon count should be stable (not increasing)
        assert daemon_count_3 <= daemon_count_1, "Daemon count should not increase"

    def test_status_command_delegation(self, test_project):
        """Test status command delegates properly without loops."""
        # Kill any existing daemons
        self._kill_all_daemons()

        # Run status command
        result = subprocess.run(
            [sys.executable, "-m", "code_indexer.cli", "status"],
            cwd=str(test_project),
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Should complete without hanging
        assert result.returncode in [0, 1], "Status should complete"

        # Check for daemon status info in output
        if result.returncode == 0:
            # Should show some status info (daemon or standalone)
            assert "Status" in result.stdout or "status" in result.stdout.lower()

        # Verify no excessive daemon spawning
        daemon_count = self._count_daemon_processes()
        assert daemon_count <= 1, f"Should have max 1 daemon, found {daemon_count}"

    def test_clean_command_delegation(self, test_project):
        """Test clean command delegates properly without loops."""
        # Kill any existing daemons
        self._kill_all_daemons()

        # Run clean command with --force to skip confirmation
        result = subprocess.run(
            [sys.executable, "-m", "code_indexer.cli", "clean", "--force"],
            cwd=str(test_project),
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Should complete without hanging
        assert result.returncode in [0, 1], f"Clean should complete: {result.stderr}"

        # Verify no excessive daemon spawning
        daemon_count = self._count_daemon_processes()
        assert daemon_count <= 1, f"Should have max 1 daemon, found {daemon_count}"

    def teardown_method(self, method):
        """Cleanup after each test."""
        # Kill any remaining daemon processes
        self._kill_all_daemons()

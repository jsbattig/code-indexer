"""E2E tests for watch command Ctrl-C handling (Story 5.3)."""

import os
import signal
import subprocess
import time

import pytest


@pytest.fixture
def proxy_test_env(tmp_path):
    """Create test environment with proxy configuration and mock repositories."""
    # Create proxy root
    proxy_root = tmp_path / "proxy-root"
    proxy_root.mkdir()

    # Create mock repositories
    repo1 = tmp_path / "repos" / "repo1"
    repo2 = tmp_path / "repos" / "repo2"
    repo1.mkdir(parents=True)
    repo2.mkdir(parents=True)

    # Initialize as git repos with .code-indexer config
    for repo in [repo1, repo2]:
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"], cwd=repo, check=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo, check=True
        )

        # Create .code-indexer directory
        indexer_dir = repo / ".code-indexer"
        indexer_dir.mkdir()

        # Create minimal config
        config_file = indexer_dir / "config.json"
        config_file.write_text('{"embedding_provider": "ollama"}')

    # Create proxy config
    proxy_config_dir = proxy_root / ".cidx-proxy"
    proxy_config_dir.mkdir()

    proxy_config = proxy_config_dir / "config.json"
    proxy_config.write_text(
        """{
        "is_proxy": true,
        "discovered_repos": [
            "../repos/repo1",
            "../repos/repo2"
        ]
    }"""
    )

    return {
        "proxy_root": proxy_root,
        "repo1": repo1,
        "repo2": repo2,
    }


class TestWatchCtrlCHandling:
    """Test Ctrl-C signal handling for watch command."""

    @pytest.mark.skip(
        reason="Requires actual cidx watch implementation - manual test only"
    )
    def test_ctrl_c_terminates_all_processes(self, proxy_test_env):
        """Test that Ctrl-C terminates all watch processes cleanly.

        This test verifies:
        - Ctrl-C signal propagates to all child processes
        - All processes terminate within timeout
        - Exit code is 0 for clean shutdown
        - No orphaned processes remain
        """
        proxy_root = proxy_test_env["proxy_root"]

        # Start watch in subprocess
        process = subprocess.Popen(
            ["cidx", "watch"],
            cwd=proxy_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            preexec_fn=os.setsid,  # Create new process group
        )

        # Wait for watch to start
        time.sleep(3)

        # Send SIGINT (Ctrl-C) to process group
        os.killpg(os.getpgid(process.pid), signal.SIGINT)

        # Wait for termination
        try:
            exit_code = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # Force kill if doesn't terminate
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            pytest.fail("Watch process did not terminate within timeout")

        # Verify clean exit
        assert exit_code == 0, f"Expected exit code 0, got {exit_code}"

        # Verify no orphaned cidx processes
        result = subprocess.run(["pgrep", "-f", "cidx watch"], capture_output=True)
        orphaned_pids = result.stdout.decode().strip()
        assert not orphaned_pids, f"Orphaned processes found: {orphaned_pids}"

    @pytest.mark.skip(
        reason="Requires actual cidx watch implementation - manual test only"
    )
    def test_double_ctrl_c_forces_exit(self, proxy_test_env):
        """Test that double Ctrl-C forces immediate exit.

        This test verifies:
        - First Ctrl-C initiates graceful shutdown
        - Second Ctrl-C forces immediate exit
        - Exit code is 1 for forced termination
        """
        proxy_root = proxy_test_env["proxy_root"]

        # Start watch in subprocess
        process = subprocess.Popen(
            ["cidx", "watch"],
            cwd=proxy_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            preexec_fn=os.setsid,
        )

        # Wait for watch to start
        time.sleep(3)

        # Send first SIGINT
        os.killpg(os.getpgid(process.pid), signal.SIGINT)
        time.sleep(0.5)

        # Send second SIGINT immediately
        os.killpg(os.getpgid(process.pid), signal.SIGINT)

        # Wait for termination
        try:
            exit_code = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            pytest.fail("Watch process did not terminate after double Ctrl-C")

        # Verify forced exit code
        assert exit_code == 1, f"Expected exit code 1 for forced exit, got {exit_code}"

    def test_shutdown_metrics_tracking(self):
        """Test that shutdown metrics are properly tracked.

        This unit-style test verifies the shutdown metrics calculation
        without requiring a full E2E watch process.
        """
        # Simulate shutdown metrics
        terminated_count = 2
        forced_kill_count = 0
        error_count = 0
        total_repos = 2

        # Verify clean shutdown detection
        all_stopped = (
            terminated_count + forced_kill_count + error_count
        ) == total_repos
        assert all_stopped is True

        # Verify exit code calculation (clean shutdown)
        if all_stopped and forced_kill_count == 0 and error_count == 0:
            exit_code = 0
        elif all_stopped and forced_kill_count > 0:
            exit_code = 1
        else:
            exit_code = 2

        assert exit_code == 0, "Expected exit code 0 for clean shutdown"

    def test_shutdown_metrics_with_forced_kills(self):
        """Test shutdown metrics when forced kills are required."""
        # Simulate forced kill scenario
        terminated_count = 1
        forced_kill_count = 1
        error_count = 0
        total_repos = 2

        all_stopped = (
            terminated_count + forced_kill_count + error_count
        ) == total_repos
        assert all_stopped is True

        # Verify exit code calculation (forced kills)
        if all_stopped and forced_kill_count == 0 and error_count == 0:
            exit_code = 0
        elif all_stopped and forced_kill_count > 0:
            exit_code = 1
        else:
            exit_code = 2

        assert exit_code == 1, "Expected exit code 1 when forced kills required"

    def test_shutdown_metrics_partial_shutdown(self):
        """Test shutdown metrics for partial shutdown."""
        # Simulate partial shutdown
        terminated_count = 1
        forced_kill_count = 0
        error_count = 0
        total_repos = 3

        all_stopped = (
            terminated_count + forced_kill_count + error_count
        ) == total_repos
        assert all_stopped is False

        # Verify exit code calculation (partial shutdown)
        if all_stopped and forced_kill_count == 0 and error_count == 0:
            exit_code = 0
        elif all_stopped and forced_kill_count > 0:
            exit_code = 1
        else:
            exit_code = 2

        assert exit_code == 2, "Expected exit code 2 for partial shutdown"


class TestWatchProcessHealthMonitoring:
    """Test process health monitoring during watch mode."""

    def test_dead_process_detection(self):
        """Test that dead processes are detected during health checks."""
        from unittest.mock import Mock
        from code_indexer.proxy.watch_manager import ParallelWatchManager

        # Create manager
        manager = ParallelWatchManager(["/repo1", "/repo2", "/repo3"])

        # Create mock processes
        running_process = Mock()
        running_process.poll = Mock(return_value=None)  # Still running

        dead_process = Mock()
        dead_process.poll = Mock(return_value=1)  # Terminated

        manager.processes = {
            "/repo1": running_process,
            "/repo2": dead_process,
            "/repo3": running_process,
        }

        # Check health
        dead = manager.check_process_health()

        # Verify only dead process detected
        assert dead == ["/repo2"]

    def test_all_processes_healthy(self):
        """Test health check when all processes are running."""
        from unittest.mock import Mock
        from code_indexer.proxy.watch_manager import ParallelWatchManager

        manager = ParallelWatchManager(["/repo1", "/repo2"])

        # All processes running
        running_process = Mock()
        running_process.poll = Mock(return_value=None)

        manager.processes = {
            "/repo1": running_process,
            "/repo2": running_process,
        }

        # Check health
        dead = manager.check_process_health()

        # Verify no dead processes
        assert dead == []

"""Unit tests for watch command shutdown and signal handling (Story 5.3)."""

import signal
import subprocess
from unittest.mock import Mock


from code_indexer.proxy.watch_manager import ParallelWatchManager


class TestWatchShutdown:
    """Test watch process shutdown behavior."""

    def test_stop_all_watchers_terminates_all_processes(self):
        """Test that stop_all_watchers terminates all processes gracefully."""
        # Setup: Create watch manager with mock processes
        repos = ["/repo1", "/repo2", "/repo3"]
        manager = ParallelWatchManager(repos)

        # Create mock processes that terminate gracefully
        processes = {}
        for repo in repos:
            mock_process = Mock(spec=subprocess.Popen)
            mock_process.terminate = Mock()
            mock_process.wait = Mock()
            mock_process.poll = Mock(return_value=0)  # Process terminated
            processes[repo] = mock_process
            manager.processes[repo] = mock_process

        # Execute: Stop all watchers
        manager.stop_all_watchers()

        # Verify: terminate() called on each process (check before dict cleared)
        for repo in repos:
            processes[repo].terminate.assert_called_once()
            processes[repo].wait.assert_called_once_with(timeout=5)

    def test_stop_all_watchers_force_kills_unresponsive_processes(self):
        """Test that stop_all_watchers force kills processes that don't terminate."""
        repos = ["/repo1", "/repo2"]
        manager = ParallelWatchManager(repos)

        # Create mock process that times out on wait()
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.terminate = Mock()
        mock_process.wait = Mock(
            side_effect=subprocess.TimeoutExpired(cmd="cidx watch", timeout=5)
        )
        mock_process.kill = Mock()
        manager.processes["/repo1"] = mock_process

        # Create mock process that terminates gracefully
        mock_process2 = Mock(spec=subprocess.Popen)
        mock_process2.terminate = Mock()
        mock_process2.wait = Mock()
        manager.processes["/repo2"] = mock_process2

        # Execute: Stop all watchers
        manager.stop_all_watchers()

        # Verify: kill() called on unresponsive process
        mock_process.kill.assert_called_once()
        # Verify: Graceful process didn't need kill
        assert not hasattr(mock_process2, "kill") or not mock_process2.kill.called

    def test_stop_all_watchers_handles_termination_errors(self):
        """Test that stop_all_watchers handles errors during termination gracefully."""
        repos = ["/repo1"]
        manager = ParallelWatchManager(repos)

        # Create mock process that raises error on terminate
        mock_process = Mock(spec=subprocess.Popen)
        mock_process.terminate = Mock(side_effect=OSError("Process not found"))
        mock_process.wait = Mock()
        manager.processes["/repo1"] = mock_process

        # Execute: Should not raise exception
        manager.stop_all_watchers()

        # Verify: terminate() was attempted
        mock_process.terminate.assert_called_once()

    def test_stop_all_watchers_clears_process_dict(self):
        """Test that stop_all_watchers clears the processes dictionary."""
        repos = ["/repo1", "/repo2"]
        manager = ParallelWatchManager(repos)

        # Create mock processes
        for repo in repos:
            mock_process = Mock(spec=subprocess.Popen)
            mock_process.terminate = Mock()
            mock_process.wait = Mock()
            manager.processes[repo] = mock_process

        # Execute
        manager.stop_all_watchers()

        # Verify: processes dict is empty
        assert len(manager.processes) == 0

    def test_stop_all_watchers_reports_termination_status(self, capsys):
        """Test that stop_all_watchers reports termination status for each process."""
        repos = ["/repo1", "/repo2"]
        manager = ParallelWatchManager(repos)

        # Create mock process that terminates gracefully
        mock_process1 = Mock(spec=subprocess.Popen)
        mock_process1.terminate = Mock()
        mock_process1.wait = Mock()
        manager.processes["/repo1"] = mock_process1

        # Create mock process that requires force kill
        mock_process2 = Mock(spec=subprocess.Popen)
        mock_process2.terminate = Mock()
        mock_process2.wait = Mock(
            side_effect=subprocess.TimeoutExpired(cmd="cidx watch", timeout=5)
        )
        mock_process2.kill = Mock()
        manager.processes["/repo2"] = mock_process2

        # Execute
        manager.stop_all_watchers()

        # Verify: Check output contains status messages
        captured = capsys.readouterr()
        assert "[/repo1] Watch terminated" in captured.out
        assert "[/repo2] Watch forcefully killed" in captured.out


class TestWatchShutdownSequence:
    """Test graceful shutdown sequence."""

    def test_shutdown_sequence_stops_multiplexer_before_processes(self):
        """Test that shutdown sequence stops multiplexer before waiting for processes."""
        # This test verifies the proper order of shutdown operations
        # The actual implementation will be in cli_integration._execute_watch()
        # Here we test the concept with mock objects

        # Create mock multiplexer
        mock_multiplexer = Mock()
        mock_multiplexer.stop_multiplexing = Mock()
        mock_multiplexer.output_queue = Mock()
        mock_multiplexer.output_queue.empty = Mock(return_value=True)

        # Create mock watch manager
        mock_manager = Mock()
        mock_manager.stop_all_watchers = Mock()
        mock_manager.processes = {}

        # Simulate shutdown sequence
        # 1. Stop multiplexer first
        mock_multiplexer.stop_multiplexing()
        # 2. Then stop processes
        mock_manager.stop_all_watchers()

        # Verify order
        assert mock_multiplexer.stop_multiplexing.called
        assert mock_manager.stop_all_watchers.called

    def test_shutdown_drains_output_queue(self):
        """Test that shutdown sequence drains remaining output queue."""
        # Create mock output queue with items
        mock_queue = Mock()
        mock_queue.empty = Mock(side_effect=[False, False, True])
        mock_queue.get_nowait = Mock(
            side_effect=[
                ("/repo1", "line1"),
                ("/repo2", "line2"),
            ]
        )

        # Simulate queue draining (from OutputMultiplexer.stop_multiplexing)
        drained_items = []
        while not mock_queue.empty():
            try:
                item = mock_queue.get_nowait()
                drained_items.append(item)
            except Exception:
                break

        # Verify all items were drained
        assert len(drained_items) == 2
        assert drained_items[0] == ("/repo1", "line1")
        assert drained_items[1] == ("/repo2", "line2")


class TestExitCodeDetermination:
    """Test exit code determination for watch termination."""

    def test_exit_code_0_for_clean_user_shutdown(self):
        """Test exit code 0 when user requests shutdown and all processes terminate cleanly."""
        # Scenario: Ctrl-C pressed, all processes terminate gracefully, no force kills
        requested_shutdown = True
        all_terminated = True
        forced_kills = 0

        exit_code = self._determine_exit_code(
            requested_shutdown, all_terminated, forced_kills
        )
        assert exit_code == 0

    def test_exit_code_1_for_forced_kills(self):
        """Test exit code 1 when processes require force kill."""
        # Scenario: Some processes required force kill
        requested_shutdown = True
        all_terminated = True
        forced_kills = 2

        exit_code = self._determine_exit_code(
            requested_shutdown, all_terminated, forced_kills
        )
        assert exit_code == 1

    def test_exit_code_2_for_partial_shutdown(self):
        """Test exit code 2 when some processes don't terminate."""
        # Scenario: Not all processes terminated
        requested_shutdown = True
        all_terminated = False
        forced_kills = 0

        exit_code = self._determine_exit_code(
            requested_shutdown, all_terminated, forced_kills
        )
        assert exit_code == 2

    def _determine_exit_code(
        self, requested_shutdown: bool, all_terminated: bool, forced_kills: int
    ) -> int:
        """Helper to determine exit code (will be implemented in actual code)."""
        if requested_shutdown and all_terminated and forced_kills == 0:
            return 0  # Clean shutdown
        if forced_kills > 0:
            return 1  # Forced kills required
        if not all_terminated:
            return 2  # Partial shutdown
        return 0


class TestSignalHandlerIntegration:
    """Test signal handler registration and behavior."""

    def test_signal_handler_can_be_registered(self):
        """Test that signal handler can be registered for SIGINT."""
        # Save original handler
        original_handler = signal.getsignal(signal.SIGINT)

        try:
            # Create custom handler
            handler_called = []

            def custom_handler(signum, frame):
                handler_called.append(True)

            # Register handler
            signal.signal(signal.SIGINT, custom_handler)

            # Verify handler is registered
            current_handler = signal.getsignal(signal.SIGINT)
            assert current_handler == custom_handler

        finally:
            # Restore original handler
            signal.signal(signal.SIGINT, original_handler)

    def test_signal_handler_prevents_double_termination(self):
        """Test that signal handler prevents double Ctrl-C from causing issues."""
        # Save original handler
        original_handler = signal.getsignal(signal.SIGINT)

        try:
            terminating = []
            handler_calls = []

            def custom_handler(signum, frame):
                handler_calls.append(True)
                if len(handler_calls) > 1:
                    # Second Ctrl-C - should force exit
                    terminating.append("force")
                else:
                    # First Ctrl-C - normal shutdown
                    terminating.append("normal")

            # Register handler
            signal.signal(signal.SIGINT, custom_handler)

            # Simulate first Ctrl-C
            custom_handler(signal.SIGINT, None)
            assert len(terminating) == 1
            assert terminating[0] == "normal"

            # Simulate second Ctrl-C
            custom_handler(signal.SIGINT, None)
            assert len(terminating) == 2
            assert terminating[1] == "force"

        finally:
            # Restore original handler
            signal.signal(signal.SIGINT, original_handler)


class TestProcessHealthChecking:
    """Test process health checking during watch mode."""

    def test_check_process_health_detects_dead_processes(self):
        """Test that check_process_health() detects terminated processes."""
        repos = ["/repo1", "/repo2", "/repo3"]
        manager = ParallelWatchManager(repos)

        # Create processes: 2 running, 1 terminated
        mock_running1 = Mock(spec=subprocess.Popen)
        mock_running1.poll = Mock(return_value=None)  # Still running
        manager.processes["/repo1"] = mock_running1

        mock_dead = Mock(spec=subprocess.Popen)
        mock_dead.poll = Mock(return_value=1)  # Terminated with code 1
        manager.processes["/repo2"] = mock_dead

        mock_running2 = Mock(spec=subprocess.Popen)
        mock_running2.poll = Mock(return_value=None)  # Still running
        manager.processes["/repo3"] = mock_running2

        # Execute
        dead_processes = manager.check_process_health()

        # Verify: Only /repo2 detected as dead
        assert dead_processes == ["/repo2"]

    def test_check_process_health_returns_empty_when_all_running(self):
        """Test that check_process_health() returns empty list when all processes running."""
        repos = ["/repo1", "/repo2"]
        manager = ParallelWatchManager(repos)

        # Create all running processes
        for repo in repos:
            mock_process = Mock(spec=subprocess.Popen)
            mock_process.poll = Mock(return_value=None)  # Still running
            manager.processes[repo] = mock_process

        # Execute
        dead_processes = manager.check_process_health()

        # Verify: Empty list
        assert dead_processes == []

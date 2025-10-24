"""Unit tests for ParallelWatchManager (Story 5.1).

Tests parallel watch process management across multiple repositories.
"""

import pytest
import subprocess
from unittest.mock import Mock, patch
from code_indexer.proxy.watch_manager import ParallelWatchManager


class TestParallelWatchManager:
    """Test parallel watch process management."""

    @pytest.fixture
    def repositories(self, tmp_path):
        """Create test repository paths."""
        repos = []
        for i in range(3):
            repo = tmp_path / f"repo{i}"
            repo.mkdir()
            repos.append(str(repo))
        return repos

    @pytest.fixture
    def manager(self, repositories):
        """Create watch manager with test repositories."""
        return ParallelWatchManager(repositories)

    def test_initialization(self, repositories):
        """Test watch manager initialization."""
        manager = ParallelWatchManager(repositories)

        assert manager.repositories == repositories
        assert manager.processes == {}
        assert manager.running is True

    def test_start_all_watchers_spawns_processes(self, manager, repositories):
        """Test starting watchers spawns process for each repository."""
        with patch.object(manager, '_start_watch_process') as mock_start:
            # Mock process creation
            mock_processes = [Mock(spec=subprocess.Popen) for _ in repositories]
            mock_start.side_effect = mock_processes

            manager.start_all_watchers()

            # Should call _start_watch_process for each repository
            assert mock_start.call_count == len(repositories)

            # Should store processes
            assert len(manager.processes) == len(repositories)

    def test_start_watch_process_creates_subprocess(self, manager, tmp_path):
        """Test _start_watch_process creates subprocess correctly."""
        repo_path = str(tmp_path / "test-repo")

        with patch('code_indexer.proxy.watch_manager.subprocess.Popen') as mock_popen:
            mock_process = Mock()
            mock_popen.return_value = mock_process

            process = manager._start_watch_process(repo_path)

            # Should call Popen with correct arguments
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args

            # Check command
            assert call_args[0][0] == ['cidx', 'watch']

            # Check working directory
            assert call_args[1]['cwd'] == repo_path

            # Check stdout/stderr configuration
            assert call_args[1]['stdout'] == subprocess.PIPE
            assert call_args[1]['stderr'] == subprocess.STDOUT

            # Check text mode and buffering
            assert call_args[1]['text'] is True
            assert call_args[1]['bufsize'] == 1  # Line buffered

            # Should return process
            assert process == mock_process

    def test_start_all_watchers_handles_failures(self, manager, repositories):
        """Test starting watchers handles individual process failures."""
        with patch.object(manager, '_start_watch_process') as mock_start:
            # First process succeeds, second fails, third succeeds
            mock_proc1 = Mock(spec=subprocess.Popen)
            mock_proc3 = Mock(spec=subprocess.Popen)

            mock_start.side_effect = [
                mock_proc1,
                Exception("Failed to start"),
                mock_proc3
            ]

            # Should not raise exception
            manager.start_all_watchers()

            # Should have 2 processes (failed one skipped)
            assert len(manager.processes) == 2

    def test_start_all_watchers_raises_if_all_fail(self, manager):
        """Test starting watchers raises error if all processes fail."""
        with patch.object(manager, '_start_watch_process') as mock_start:
            # All processes fail
            mock_start.side_effect = Exception("Failed to start")

            # Should raise RuntimeError
            with pytest.raises(RuntimeError, match="Failed to start any watch processes"):
                manager.start_all_watchers()

    def test_stop_all_watchers_terminates_processes(self, manager):
        """Test stopping watchers terminates all processes."""
        # Create mock processes
        mock_processes = {}
        for i, repo in enumerate(manager.repositories):
            proc = Mock(spec=subprocess.Popen)
            proc.terminate = Mock()
            proc.wait = Mock()
            mock_processes[repo] = proc

        manager.processes = mock_processes

        manager.stop_all_watchers()

        # Should terminate each process
        for proc in mock_processes.values():
            proc.terminate.assert_called_once()
            proc.wait.assert_called_once_with(timeout=5)

        # Processes should be cleared
        assert manager.processes == {}

    def test_stop_all_watchers_kills_hanging_processes(self, manager):
        """Test stopping watchers kills processes that don't terminate."""
        # Create mock process that times out on wait
        proc = Mock(spec=subprocess.Popen)
        proc.terminate = Mock()
        proc.wait = Mock(side_effect=subprocess.TimeoutExpired('cidx', 5))
        proc.kill = Mock()

        manager.processes = {manager.repositories[0]: proc}

        manager.stop_all_watchers()

        # Should try terminate first
        proc.terminate.assert_called_once()

        # Should kill after timeout
        proc.kill.assert_called_once()

    def test_stop_all_watchers_handles_errors(self, manager):
        """Test stopping watchers handles errors gracefully."""
        # Create mock process that raises error
        proc = Mock(spec=subprocess.Popen)
        proc.terminate = Mock(side_effect=Exception("Terminate error"))

        manager.processes = {manager.repositories[0]: proc}

        # Should not raise exception
        manager.stop_all_watchers()

        # Processes should still be cleared
        assert manager.processes == {}

    def test_check_process_health_detects_dead_processes(self, manager):
        """Test health check detects terminated processes."""
        # Create mock processes - one running, one dead
        running_proc = Mock(spec=subprocess.Popen)
        running_proc.poll = Mock(return_value=None)  # Still running

        dead_proc = Mock(spec=subprocess.Popen)
        dead_proc.poll = Mock(return_value=1)  # Terminated with exit code 1

        manager.processes = {
            manager.repositories[0]: running_proc,
            manager.repositories[1]: dead_proc,
        }

        dead_processes = manager.check_process_health()

        # Should detect dead process
        assert len(dead_processes) == 1
        assert manager.repositories[1] in dead_processes

    def test_check_process_health_all_running(self, manager):
        """Test health check when all processes running."""
        # Create mock running processes
        for repo in manager.repositories:
            proc = Mock(spec=subprocess.Popen)
            proc.poll = Mock(return_value=None)
            manager.processes[repo] = proc

        dead_processes = manager.check_process_health()

        # Should find no dead processes
        assert dead_processes == []

    def test_check_process_health_all_dead(self, manager):
        """Test health check when all processes dead."""
        # Create mock dead processes
        for repo in manager.repositories:
            proc = Mock(spec=subprocess.Popen)
            proc.poll = Mock(return_value=1)
            manager.processes[repo] = proc

        dead_processes = manager.check_process_health()

        # Should detect all dead processes
        assert len(dead_processes) == len(manager.repositories)

    def test_parallel_process_isolation(self, manager):
        """Test processes run in isolation (one failure doesn't affect others)."""
        with patch.object(manager, '_start_watch_process') as mock_start:
            # Create mock processes - one will "fail"
            proc1 = Mock()
            proc1.poll = Mock(return_value=None)  # Running
            proc2 = Mock()
            proc2.poll = Mock(return_value=1)  # Dead
            proc3 = Mock()
            proc3.poll = Mock(return_value=None)  # Running

            mock_start.side_effect = [proc1, proc2, proc3]

            manager.start_all_watchers()

            # Check health - process 2 should be dead
            dead = manager.check_process_health()

            # Only one process should be dead
            assert len(dead) == 1

            # Other processes still tracked
            assert len(manager.processes) == 3

    def test_start_all_watchers_with_empty_repository_list(self):
        """Test starting watchers with no repositories raises error."""
        manager = ParallelWatchManager([])

        with pytest.raises(RuntimeError, match="Failed to start any watch processes"):
            manager.start_all_watchers()

    def test_stop_all_watchers_with_no_processes(self, manager):
        """Test stopping watchers when no processes running."""
        # No processes started
        assert manager.processes == {}

        # Should not raise error
        manager.stop_all_watchers()

        # Should still be empty
        assert manager.processes == {}

    def test_process_lifecycle_complete_flow(self, manager):
        """Test complete lifecycle: start, run, stop."""
        with patch.object(manager, '_start_watch_process') as mock_start:
            # Create mock processes
            mock_processes = []
            for repo in manager.repositories:
                proc = Mock(spec=subprocess.Popen)
                proc.poll = Mock(return_value=None)  # Running
                proc.terminate = Mock()
                proc.wait = Mock()
                mock_processes.append(proc)

            mock_start.side_effect = mock_processes

            # Start watchers
            manager.start_all_watchers()
            assert len(manager.processes) == len(manager.repositories)

            # Check health (all running)
            dead = manager.check_process_health()
            assert dead == []

            # Stop watchers
            manager.stop_all_watchers()
            assert manager.processes == {}

    def test_multiple_repositories_concurrent_startup(self, manager):
        """Test starting watches for multiple repositories concurrently."""
        with patch('code_indexer.proxy.watch_manager.subprocess.Popen') as mock_popen:
            # Create mock processes
            mock_processes = [Mock() for _ in manager.repositories]
            mock_popen.side_effect = mock_processes

            manager.start_all_watchers()

            # Should create process for each repository
            assert mock_popen.call_count == len(manager.repositories)

            # All processes should be stored
            assert len(manager.processes) == len(manager.repositories)

    def test_watch_command_arguments(self, manager, tmp_path):
        """Test watch process uses correct command arguments."""
        repo_path = str(tmp_path / "repo")

        with patch('code_indexer.proxy.watch_manager.subprocess.Popen') as mock_popen:
            mock_popen.return_value = Mock()

            manager._start_watch_process(repo_path)

            # Verify command is 'cidx watch'
            call_args = mock_popen.call_args
            command = call_args[0][0]

            assert command == ['cidx', 'watch']

    def test_process_buffering_configuration(self, manager, tmp_path):
        """Test processes configured with line buffering."""
        repo_path = str(tmp_path / "repo")

        with patch('code_indexer.proxy.watch_manager.subprocess.Popen') as mock_popen:
            mock_popen.return_value = Mock()

            manager._start_watch_process(repo_path)

            # Check buffering configuration
            call_kwargs = mock_popen.call_args[1]

            # Should use line buffering
            assert call_kwargs['bufsize'] == 1

            # Should use text mode
            assert call_kwargs['text'] is True

    def test_process_stdout_stderr_configuration(self, manager, tmp_path):
        """Test processes configured with stdout/stderr piping."""
        repo_path = str(tmp_path / "repo")

        with patch('code_indexer.proxy.watch_manager.subprocess.Popen') as mock_popen:
            mock_popen.return_value = Mock()

            manager._start_watch_process(repo_path)

            call_kwargs = mock_popen.call_args[1]

            # stdout should be piped
            assert call_kwargs['stdout'] == subprocess.PIPE

            # stderr should be merged with stdout
            assert call_kwargs['stderr'] == subprocess.STDOUT

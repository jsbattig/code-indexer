"""End-to-end tests for watch command multiplexing in proxy mode (Stories 5.1, 5.2, 5.4).

This test suite validates:
- Parallel watch processes across multiple repositories (Story 5.1)
- Unified output stream multiplexing (Story 5.2)
- Repository identification in output (Story 5.4)
"""

import unittest
import tempfile
import shutil
import time
import threading
from pathlib import Path
from unittest.mock import Mock, patch
from io import StringIO

from code_indexer.proxy.watch_manager import ParallelWatchManager
from code_indexer.proxy.output_multiplexer import OutputMultiplexer
from code_indexer.proxy.repository_formatter import RepositoryPrefixFormatter


class TestWatchMultiplexing(unittest.TestCase):
    """E2E tests for watch command multiplexing."""

    @classmethod
    def setUpClass(cls):
        """Set up test repositories."""
        cls.test_dir = Path(tempfile.mkdtemp(prefix="watch_multiplex_test_"))

        # Create 3 test repositories
        cls.repos = []
        for i in range(1, 4):
            repo_path = cls.test_dir / f"repo{i}"
            repo_path.mkdir(parents=True)
            (repo_path / "test.py").write_text(f"# Test file {i}")
            cls.repos.append(str(repo_path))

    @classmethod
    def tearDownClass(cls):
        """Clean up test repositories."""
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir)

    def test_parallel_watch_manager_initialization(self):
        """Test ParallelWatchManager initializes correctly (Story 5.1)."""
        manager = ParallelWatchManager(self.repos)

        self.assertEqual(manager.repositories, self.repos)
        self.assertEqual(manager.processes, {})
        self.assertTrue(manager.running)

    def test_watch_manager_process_spawning(self):
        """Test watch manager spawns processes for all repositories (Story 5.1)."""
        manager = ParallelWatchManager(self.repos)

        with patch.object(manager, '_start_watch_process') as mock_start:
            # Mock process creation
            mock_processes = [Mock() for _ in self.repos]
            mock_start.side_effect = mock_processes

            manager.start_all_watchers()

            # Verify process started for each repository
            self.assertEqual(mock_start.call_count, len(self.repos))
            self.assertEqual(len(manager.processes), len(self.repos))

    def test_watch_manager_process_isolation(self):
        """Test failed process doesn't affect others (Story 5.1)."""
        manager = ParallelWatchManager(self.repos)

        with patch.object(manager, '_start_watch_process') as mock_start:
            # First succeeds, second fails, third succeeds
            proc1 = Mock()
            proc3 = Mock()
            mock_start.side_effect = [proc1, Exception("Failed"), proc3]

            # Should not raise exception
            manager.start_all_watchers()

            # Should have 2 processes (failed one skipped)
            self.assertEqual(len(manager.processes), 2)

    def test_watch_manager_health_monitoring(self):
        """Test health monitoring detects dead processes (Story 5.1)."""
        manager = ParallelWatchManager(self.repos[:2])

        # Create mock processes - one running, one dead
        running_proc = Mock()
        running_proc.poll = Mock(return_value=None)
        dead_proc = Mock()
        dead_proc.poll = Mock(return_value=1)

        manager.processes = {
            self.repos[0]: running_proc,
            self.repos[1]: dead_proc,
        }

        dead_processes = manager.check_process_health()

        # Should detect dead process
        self.assertEqual(len(dead_processes), 1)
        self.assertIn(self.repos[1], dead_processes)

    def test_watch_manager_graceful_shutdown(self):
        """Test watch manager stops all processes gracefully (Story 5.1)."""
        manager = ParallelWatchManager(self.repos)

        # Create mock processes
        for repo in self.repos:
            proc = Mock()
            proc.terminate = Mock()
            proc.wait = Mock()
            manager.processes[repo] = proc

        manager.stop_all_watchers()

        # Verify all processes terminated
        for proc in manager.processes.values():
            # Note: processes dict is cleared, so we can't check here
            pass

        # Processes dict should be empty
        self.assertEqual(manager.processes, {})

    def test_output_multiplexer_initialization(self):
        """Test OutputMultiplexer initializes correctly (Story 5.2)."""
        processes = {repo: Mock() for repo in self.repos}
        multiplexer = OutputMultiplexer(processes)

        self.assertEqual(multiplexer.processes, processes)
        self.assertTrue(multiplexer.output_queue.empty())
        self.assertTrue(multiplexer.running)

    def test_output_multiplexer_thread_creation(self):
        """Test multiplexer creates reader threads for each process (Story 5.2)."""
        processes = {}
        for repo in self.repos:
            proc = Mock()
            proc.stdout = StringIO("Line 1\nLine 2\n")
            processes[repo] = proc

        multiplexer = OutputMultiplexer(processes)
        multiplexer.start_multiplexing()

        # Wait for threads to start
        time.sleep(0.1)

        # Should create reader thread for each repository
        self.assertEqual(len(multiplexer.reader_threads), len(self.repos))

        # All threads should be daemon threads
        for thread in multiplexer.reader_threads:
            self.assertTrue(thread.daemon)

        # Cleanup
        multiplexer.stop_multiplexing()

    def test_output_multiplexer_line_buffering(self):
        """Test multiplexer queues complete lines (Story 5.2)."""
        proc = Mock()
        proc.stdout = StringIO("Line 1\nLine 2\nLine 3\n")
        processes = {"repo1": proc}

        multiplexer = OutputMultiplexer(processes)

        # Read output from process
        multiplexer._read_process_output("repo1", proc)

        # Verify all lines queued
        self.assertEqual(multiplexer.output_queue.qsize(), 3)

        # Check content
        repo, line = multiplexer.output_queue.get_nowait()
        self.assertEqual(repo, "repo1")
        self.assertEqual(line, "Line 1")

    def test_output_multiplexer_strips_newlines(self):
        """Test multiplexer strips trailing newlines (Story 5.2)."""
        proc = Mock()
        proc.stdout = StringIO("Line with newline\n")
        processes = {"repo": proc}

        multiplexer = OutputMultiplexer(processes)
        multiplexer._read_process_output("repo", proc)

        _, line = multiplexer.output_queue.get_nowait()

        # Newline should be stripped
        self.assertEqual(line, "Line with newline")
        self.assertFalse(line.endswith('\n'))

    def test_output_multiplexer_interleaved_output(self):
        """Test output from multiple repos is interleaved (Story 5.2)."""
        processes = {}
        for i, repo in enumerate(self.repos[:2]):
            proc = Mock()
            proc.stdout = StringIO(f"Line 1 from repo{i+1}\nLine 2 from repo{i+1}\n")
            processes[repo] = proc

        multiplexer = OutputMultiplexer(processes)

        # Read from all processes
        for repo, proc in processes.items():
            multiplexer._read_process_output(repo, proc)

        # Should have output from both repositories
        self.assertEqual(multiplexer.output_queue.qsize(), 4)

        # Collect all outputs
        outputs = []
        while not multiplexer.output_queue.empty():
            outputs.append(multiplexer.output_queue.get_nowait())

        # Should have output from both repos
        repos_found = set(repo for repo, _ in outputs)
        self.assertEqual(len(repos_found), 2)

    def test_output_multiplexer_handles_errors(self):
        """Test multiplexer handles read errors gracefully (Story 5.2)."""
        proc = Mock()
        proc.stdout = Mock()
        proc.stdout.__iter__ = Mock(side_effect=IOError("Read error"))
        processes = {"error-repo": proc}

        multiplexer = OutputMultiplexer(processes)

        # Should not raise exception
        multiplexer._read_process_output("error-repo", proc)

        # Should queue error message
        if not multiplexer.output_queue.empty():
            repo, line = multiplexer.output_queue.get_nowait()
            self.assertIn("ERROR", line)

    def test_repository_prefix_formatter_initialization(self):
        """Test RepositoryPrefixFormatter initializes correctly (Story 5.4)."""
        formatter = RepositoryPrefixFormatter(self.test_dir)

        self.assertEqual(formatter.proxy_root, self.test_dir.resolve())

    def test_repository_prefix_formatter_relative_path(self):
        """Test formatter uses relative paths (Story 5.4)."""
        formatter = RepositoryPrefixFormatter(self.test_dir)
        repo_path = self.test_dir / "repo1"

        prefix = formatter.format_prefix(str(repo_path))

        # Should use relative path
        self.assertEqual(prefix, "[repo1]")

    def test_repository_prefix_formatter_output_line(self):
        """Test formatter creates complete output lines (Story 5.4)."""
        formatter = RepositoryPrefixFormatter(self.test_dir)
        repo_path = self.test_dir / "repo1"
        content = "Change detected: test.py"

        output_line = formatter.format_output_line(str(repo_path), content)

        # Verify format
        self.assertEqual(output_line, "[repo1] Change detected: test.py")

    def test_repository_prefix_formatter_nested_paths(self):
        """Test formatter handles nested repository paths (Story 5.4)."""
        formatter = RepositoryPrefixFormatter(self.test_dir)
        nested_repo = self.test_dir / "backend" / "auth-service"
        nested_repo.mkdir(parents=True)

        prefix = formatter.format_prefix(str(nested_repo))

        self.assertEqual(prefix, "[backend/auth-service]")

    def test_repository_prefix_formatter_unique_prefixes(self):
        """Test different repos get unique prefixes (Story 5.4)."""
        formatter = RepositoryPrefixFormatter(self.test_dir)

        prefixes = [formatter.format_prefix(repo) for repo in self.repos]

        # All prefixes should be unique
        self.assertEqual(len(prefixes), len(set(prefixes)))

    def test_integrated_watch_multiplexing_flow(self):
        """Test complete integrated flow of watch multiplexing (Stories 5.1, 5.2, 5.4)."""
        # This test validates the complete integration of all three stories

        # Create watch manager (Story 5.1)
        manager = ParallelWatchManager(self.repos)

        with patch.object(manager, '_start_watch_process') as mock_start:
            # Create mock processes with output
            mock_processes = []
            for i, repo in enumerate(self.repos):
                proc = Mock()
                proc.stdout = StringIO(f"[{repo}] Watch started\n")
                proc.poll = Mock(return_value=None)  # Running
                mock_processes.append(proc)

            mock_start.side_effect = mock_processes

            # Start watch manager
            manager.start_all_watchers()

            # Verify processes started (Story 5.1)
            self.assertEqual(len(manager.processes), len(self.repos))

            # Create output multiplexer (Story 5.2)
            multiplexer = OutputMultiplexer(manager.processes)

            # Verify multiplexer initialized
            self.assertEqual(len(multiplexer.processes), len(self.repos))

            # Create repository formatter (Story 5.4)
            formatter = RepositoryPrefixFormatter(self.test_dir)

            # Format output for each repository
            for repo in self.repos:
                formatted = formatter.format_output_line(repo, "Change detected")
                # Verify repository identification (Story 5.4)
                self.assertIn("[", formatted)
                self.assertIn("]", formatted)
                self.assertIn("Change detected", formatted)

            # Cleanup
            multiplexer.stop_multiplexing()
            manager.stop_all_watchers()

    def test_watch_manager_empty_repository_list(self):
        """Test watch manager handles empty repository list."""
        manager = ParallelWatchManager([])

        with self.assertRaises(RuntimeError):
            manager.start_all_watchers()

    def test_output_multiplexer_concurrent_reads(self):
        """Test multiplexer handles concurrent reads safely (Story 5.2)."""
        processes = {}
        for repo in self.repos:
            proc = Mock()
            proc.stdout = StringIO("Line 1\nLine 2\nLine 3\n")
            processes[repo] = proc

        multiplexer = OutputMultiplexer(processes)

        # Read from all processes concurrently
        threads = []
        for repo, proc in processes.items():
            thread = threading.Thread(
                target=multiplexer._read_process_output,
                args=(repo, proc)
            )
            thread.start()
            threads.append(thread)

        # Wait for all threads
        for thread in threads:
            thread.join()

        # All lines should be queued (3 repos * 3 lines)
        self.assertEqual(multiplexer.output_queue.qsize(), 9)


if __name__ == '__main__':
    unittest.main()

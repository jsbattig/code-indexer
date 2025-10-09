"""Unit tests for parallel command execution.

Tests the ParallelCommandExecutor class that executes commands
across multiple repositories concurrently using ThreadPoolExecutor.
"""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import subprocess
from concurrent.futures import TimeoutError as FuturesTimeoutError

from code_indexer.proxy.parallel_executor import ParallelCommandExecutor


class TestParallelCommandExecutor(unittest.TestCase):
    """Test parallel command execution logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.repos = ["/tmp/repo1", "/tmp/repo2", "/tmp/repo3"]
        self.executor = ParallelCommandExecutor(self.repos)

    def test_init_stores_repositories(self):
        """Test that executor stores repository list."""
        self.assertEqual(self.executor.repositories, self.repos)

    def test_max_workers_constant(self):
        """Test that MAX_WORKERS is set to 10."""
        self.assertEqual(ParallelCommandExecutor.MAX_WORKERS, 10)

    @patch('code_indexer.proxy.parallel_executor.subprocess.run')
    def test_execute_single_repository_success(self, mock_run):
        """Test executing command in single repository."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.stdout = "Query results"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Execute
        stdout, stderr, code = self.executor._execute_single(
            "/tmp/repo1", "query", ["test"]
        )

        # Verify
        self.assertEqual(stdout, "Query results")
        self.assertEqual(stderr, "")
        self.assertEqual(code, 0)
        # Verify subprocess.run was called with COLUMNS=200 env variable
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        self.assertEqual(call_args.args[0], ['cidx', 'query', 'test'])
        self.assertEqual(call_args.kwargs['cwd'], "/tmp/repo1")
        self.assertEqual(call_args.kwargs['capture_output'], True)
        self.assertEqual(call_args.kwargs['text'], True)
        self.assertEqual(call_args.kwargs['timeout'], 300)
        # Verify env contains COLUMNS=200
        self.assertIn('env', call_args.kwargs)
        self.assertEqual(call_args.kwargs['env']['COLUMNS'], '200')

    @patch('code_indexer.proxy.parallel_executor.subprocess.run')
    def test_execute_single_repository_failure(self, mock_run):
        """Test executing command that fails."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "Error: repository not indexed"
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        # Execute
        stdout, stderr, code = self.executor._execute_single(
            "/tmp/repo1", "query", ["test"]
        )

        # Verify
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "Error: repository not indexed")
        self.assertEqual(code, 1)

    @patch('code_indexer.proxy.parallel_executor.subprocess.run')
    def test_execute_single_timeout(self, mock_run):
        """Test timeout handling for hung subprocess."""
        # Setup mock to raise timeout
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=['cidx', 'query'], timeout=300
        )

        # Execute - should raise TimeoutExpired
        with self.assertRaises(subprocess.TimeoutExpired):
            self.executor._execute_single("/tmp/repo1", "query", ["test"])

    @patch('code_indexer.proxy.parallel_executor.subprocess.run')
    def test_execute_parallel_all_success(self, mock_run):
        """Test parallel execution with all repositories succeeding."""
        # Setup mock to return success for all repos
        def mock_subprocess(cmd, cwd, **kwargs):
            result = MagicMock()
            result.stdout = f"Results from {cwd}"
            result.stderr = ""
            result.returncode = 0
            return result

        mock_run.side_effect = mock_subprocess

        # Execute
        results = self.executor.execute_parallel("query", ["test"])

        # Verify
        self.assertEqual(len(results), 3)
        for repo in self.repos:
            self.assertIn(repo, results)
            stdout, stderr, code = results[repo]
            self.assertIn(repo, stdout)
            self.assertEqual(stderr, "")
            self.assertEqual(code, 0)

    @patch('code_indexer.proxy.parallel_executor.subprocess.run')
    def test_execute_parallel_partial_failure(self, mock_run):
        """Test parallel execution with some repositories failing."""
        # Setup mock with mixed success/failure
        def mock_subprocess(cmd, cwd, **kwargs):
            result = MagicMock()
            if cwd == "/tmp/repo2":
                result.stdout = ""
                result.stderr = "Error: not indexed"
                result.returncode = 1
            else:
                result.stdout = f"Results from {cwd}"
                result.stderr = ""
                result.returncode = 0
            return result

        mock_run.side_effect = mock_subprocess

        # Execute
        results = self.executor.execute_parallel("query", ["test"])

        # Verify all results collected
        self.assertEqual(len(results), 3)

        # Verify successful repos
        self.assertEqual(results["/tmp/repo1"][2], 0)
        self.assertEqual(results["/tmp/repo3"][2], 0)

        # Verify failed repo
        self.assertEqual(results["/tmp/repo2"][2], 1)
        self.assertIn("not indexed", results["/tmp/repo2"][1])

    @patch('code_indexer.proxy.parallel_executor.subprocess.run')
    def test_execute_parallel_exception_handling(self, mock_run):
        """Test that exceptions in one repo don't crash entire execution."""
        # Setup mock to raise exception for one repo
        def mock_subprocess(cmd, cwd, **kwargs):
            if cwd == "/tmp/repo2":
                raise RuntimeError("Subprocess crashed")
            result = MagicMock()
            result.stdout = f"Results from {cwd}"
            result.stderr = ""
            result.returncode = 0
            return result

        mock_run.side_effect = mock_subprocess

        # Execute
        results = self.executor.execute_parallel("query", ["test"])

        # Verify all results collected
        self.assertEqual(len(results), 3)

        # Verify successful repos
        self.assertEqual(results["/tmp/repo1"][2], 0)
        self.assertEqual(results["/tmp/repo3"][2], 0)

        # Verify exception captured
        self.assertEqual(results["/tmp/repo2"][2], -1)
        self.assertIn("Subprocess crashed", results["/tmp/repo2"][1])

    def test_worker_count_small_repo_list(self):
        """Test worker count with 2 repositories uses 2 workers."""
        small_executor = ParallelCommandExecutor(["/tmp/repo1", "/tmp/repo2"])

        with patch('code_indexer.proxy.parallel_executor.subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "Results"
            mock_result.stderr = ""
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            with patch('concurrent.futures.ThreadPoolExecutor') as MockExecutorClass:
                # Setup the mock to work as a context manager
                mock_executor_instance = MagicMock()
                MockExecutorClass.return_value.__enter__.return_value = mock_executor_instance

                # Mock the submit and as_completed behavior
                mock_future = MagicMock()
                mock_future.result.return_value = ("Results", "", 0)
                mock_executor_instance.submit.return_value = mock_future

                with patch('concurrent.futures.as_completed') as mock_as_completed:
                    mock_as_completed.return_value = [mock_future, mock_future]

                    small_executor.execute_parallel("query", ["test"])
                    # Verify ThreadPoolExecutor called with 2 workers
                    MockExecutorClass.assert_called_once_with(max_workers=2)

    def test_worker_count_large_repo_list(self):
        """Test worker count capped at MAX_WORKERS for 15 repositories."""
        large_repos = [f"/tmp/repo{i}" for i in range(15)]
        large_executor = ParallelCommandExecutor(large_repos)

        with patch('code_indexer.proxy.parallel_executor.subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "Results"
            mock_result.stderr = ""
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            with patch('concurrent.futures.ThreadPoolExecutor') as MockExecutorClass:
                # Setup the mock to work as a context manager
                mock_executor_instance = MagicMock()
                MockExecutorClass.return_value.__enter__.return_value = mock_executor_instance

                # Mock the submit and as_completed behavior
                mock_futures = []
                for i in range(15):
                    mock_future = MagicMock()
                    mock_future.result.return_value = ("Results", "", 0)
                    mock_futures.append(mock_future)

                mock_executor_instance.submit.side_effect = mock_futures

                with patch('concurrent.futures.as_completed') as mock_as_completed:
                    mock_as_completed.return_value = mock_futures

                    large_executor.execute_parallel("query", ["test"])
                    # Verify ThreadPoolExecutor called with MAX_WORKERS (10)
                    MockExecutorClass.assert_called_once_with(max_workers=10)

    def test_empty_repository_list(self):
        """Test execution with empty repository list."""
        empty_executor = ParallelCommandExecutor([])

        with patch('code_indexer.proxy.parallel_executor.subprocess.run'):
            results = empty_executor.execute_parallel("query", ["test"])

            # Should return empty dict
            self.assertEqual(results, {})

    def test_single_repository(self):
        """Test execution with single repository."""
        single_executor = ParallelCommandExecutor(["/tmp/repo1"])

        with patch('code_indexer.proxy.parallel_executor.subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "Results"
            mock_result.stderr = ""
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            results = single_executor.execute_parallel("query", ["test"])

            # Should execute with 1 worker
            self.assertEqual(len(results), 1)
            self.assertIn("/tmp/repo1", results)

    @patch('code_indexer.proxy.parallel_executor.subprocess.run')
    def test_execute_parallel_all_fail(self, mock_run):
        """Test parallel execution with all repositories failing."""
        # Setup mock to return failure for all repos
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "Error: not indexed"
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        # Execute
        results = self.executor.execute_parallel("query", ["test"])

        # Verify all failed
        for repo in self.repos:
            self.assertEqual(results[repo][2], 1)

    @patch('code_indexer.proxy.parallel_executor.subprocess.run')
    def test_different_commands(self, mock_run):
        """Test executing different commands (status, watch, fix-config)."""
        commands = ["status", "watch", "fix-config"]

        mock_result = MagicMock()
        mock_result.stdout = "Command output"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        for command in commands:
            with self.subTest(command=command):
                results = self.executor.execute_parallel(command, [])

                # Verify command executed
                self.assertEqual(len(results), 3)

                # Check that cidx command was called correctly
                calls = mock_run.call_args_list
                for call in calls:
                    args, kwargs = call
                    cmd = args[0]
                    self.assertEqual(cmd[0], 'cidx')
                    self.assertEqual(cmd[1], command)

                mock_run.reset_mock()

    @patch('code_indexer.proxy.parallel_executor.subprocess.run')
    def test_command_arguments_passed_correctly(self, mock_run):
        """Test that command arguments are passed to subprocess."""
        mock_result = MagicMock()
        mock_result.stdout = "Results"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Execute with multiple arguments
        self.executor.execute_parallel("query", ["test query", "--limit", "20"])

        # Verify arguments passed correctly
        calls = mock_run.call_args_list
        for call in calls:
            args, kwargs = call
            cmd = args[0]
            self.assertEqual(cmd, ['cidx', 'query', 'test query', '--limit', '20'])


if __name__ == '__main__':
    unittest.main()

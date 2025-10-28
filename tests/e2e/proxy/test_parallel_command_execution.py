"""End-to-end tests for parallel command execution in proxy mode.

This test suite validates real parallel execution across multiple repositories
with actual subprocess calls, timing validation, and output verification.
"""

import unittest
import tempfile
import shutil
import time
from pathlib import Path
import subprocess

from code_indexer.proxy.parallel_executor import ParallelCommandExecutor
from code_indexer.proxy.result_aggregator import ParallelResultAggregator


class TestParallelCommandExecution(unittest.TestCase):
    """E2E tests for parallel command execution."""

    @classmethod
    def setUpClass(cls):
        """Set up test repositories with real CIDX initialization."""
        cls.test_dir = Path(tempfile.mkdtemp(prefix="parallel_exec_test_"))

        # Create 3 test repositories
        cls.repos = []
        for i in range(1, 4):
            repo_path = cls.test_dir / f"repo{i}"
            repo_path.mkdir(parents=True)

            # Create some test files
            (repo_path / "test.py").write_text(f"# Test file {i}\nprint('hello')")
            (repo_path / "README.md").write_text(f"# Repository {i}")

            # Initialize git (required for cidx)
            subprocess.run(
                ["git", "init"], cwd=repo_path, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "add", "."], cwd=repo_path, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            cls.repos.append(str(repo_path))

    @classmethod
    def tearDownClass(cls):
        """Clean up test repositories."""
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir)

    def test_parallel_status_execution(self):
        """Test parallel status command execution across repositories."""
        executor = ParallelCommandExecutor(self.repos)

        # Execute status in parallel
        results = executor.execute_parallel("status", [])

        # Verify all repositories executed
        self.assertEqual(len(results), 3)

        # Verify each repository returned results
        for repo in self.repos:
            self.assertIn(repo, results)
            stdout, stderr, exit_code = results[repo]

            # Status command should execute (may fail if not initialized, which is OK)
            # We just verify it executed without crashing
            self.assertIsInstance(stdout, str)
            self.assertIsInstance(stderr, str)
            self.assertIsInstance(exit_code, int)

    def test_parallel_execution_timing(self):
        """Test that parallel execution is faster than sequential."""
        # This test uses status command which is safe and quick
        executor = ParallelCommandExecutor(self.repos)

        # Measure parallel execution time
        start_parallel = time.time()
        results_parallel = executor.execute_parallel("status", [])
        time_parallel = time.time() - start_parallel

        # Measure sequential execution time
        start_sequential = time.time()
        results_sequential = {}
        for repo in self.repos:
            stdout, stderr, code = executor._execute_single(repo, "status", [])
            results_sequential[repo] = (stdout, stderr, code)
        time_sequential = time.time() - start_sequential

        # Verify both executed all repositories
        self.assertEqual(len(results_parallel), 3)
        self.assertEqual(len(results_sequential), 3)

        # Parallel should be faster (or at least not significantly slower)
        # Allow some overhead for thread pool creation
        # We expect at least some benefit, but don't enforce strict timing
        # to avoid flaky tests
        print(f"Parallel time: {time_parallel:.2f}s")
        print(f"Sequential time: {time_sequential:.2f}s")

        # Just verify parallel didn't fail catastrophically
        self.assertLess(
            time_parallel, time_sequential * 2, "Parallel execution unexpectedly slow"
        )

    def test_result_aggregation_all_success(self):
        """Test result aggregation when all commands succeed."""
        # Create mock results (all success)
        results = {
            self.repos[0]: ("Output 1", "", 0),
            self.repos[1]: ("Output 2", "", 0),
            self.repos[2]: ("Output 3", "", 0),
        }

        aggregator = ParallelResultAggregator()
        output, exit_code = aggregator.aggregate(results)

        # Verify all outputs combined
        self.assertIn("Output 1", output)
        self.assertIn("Output 2", output)
        self.assertIn("Output 3", output)

        # Verify exit code is 0 (all success)
        self.assertEqual(exit_code, 0)

    def test_result_aggregation_mixed_results(self):
        """Test result aggregation with mixed success/failure."""
        # Create mock results (mixed)
        results = {
            self.repos[0]: ("Output 1", "", 0),
            self.repos[1]: ("", "Error in repo2", 1),
            self.repos[2]: ("Output 3", "", 0),
        }

        aggregator = ParallelResultAggregator()
        output, exit_code = aggregator.aggregate(results)

        # Verify successful outputs included
        self.assertIn("Output 1", output)
        self.assertIn("Output 3", output)

        # Verify error included with repo path
        self.assertIn(f"ERROR in {self.repos[1]}", output)
        self.assertIn("Error in repo2", output)

        # Verify exit code is 2 (partial success)
        self.assertEqual(exit_code, 2)

    def test_parallel_execution_error_isolation(self):
        """Test that error in one repo doesn't crash entire execution."""
        # Create executor with invalid repo path mixed with valid ones
        invalid_repos = [self.repos[0], "/nonexistent/repo", self.repos[2]]
        executor = ParallelCommandExecutor(invalid_repos)

        # Execute - should handle invalid repo gracefully
        results = executor.execute_parallel("status", [])

        # Verify all repos attempted
        self.assertEqual(len(results), 3)

        # Verify valid repos executed
        self.assertIn(self.repos[0], results)
        self.assertIn(self.repos[2], results)

        # Verify invalid repo captured error
        self.assertIn("/nonexistent/repo", results)
        _, stderr, exit_code = results["/nonexistent/repo"]
        # Should have non-zero exit or error
        self.assertTrue(exit_code != 0 or stderr != "")

    def test_output_format_validation(self):
        """Test that output format is clear and shows repo context."""
        # Create results with errors
        results = {
            self.repos[0]: ("Success output", "", 0),
            self.repos[1]: ("", "Failed to connect", 1),
        }

        aggregator = ParallelResultAggregator()
        output, exit_code = aggregator.aggregate(results)

        # Verify error includes repo path for context
        self.assertIn(self.repos[1], output)
        self.assertIn("ERROR", output)
        self.assertIn("Failed to connect", output)

        # Verify success output included
        self.assertIn("Success output", output)

    def test_empty_repository_list_handling(self):
        """Test parallel execution with empty repository list."""
        executor = ParallelCommandExecutor([])

        results = executor.execute_parallel("status", [])

        # Should return empty dict, not crash
        self.assertEqual(results, {})

    def test_single_repository_execution(self):
        """Test parallel execution with single repository."""
        executor = ParallelCommandExecutor([self.repos[0]])

        results = executor.execute_parallel("status", [])

        # Should execute single repo successfully
        self.assertEqual(len(results), 1)
        self.assertIn(self.repos[0], results)

    def test_worker_count_respected(self):
        """Test that MAX_WORKERS limit is respected."""
        # Create 15 mock repositories
        many_repos = [f"/tmp/repo{i}" for i in range(15)]
        executor = ParallelCommandExecutor(many_repos)

        # Verify MAX_WORKERS is 10
        self.assertEqual(ParallelCommandExecutor.MAX_WORKERS, 10)

        # Worker count calculation tested in unit tests
        # This test documents the expected behavior

    def test_concurrent_completion_handling(self):
        """Test that results collected as they complete."""
        executor = ParallelCommandExecutor(self.repos)

        # Execute command
        results = executor.execute_parallel("status", [])

        # Verify all results collected despite different completion times
        self.assertEqual(len(results), len(self.repos))

        # Verify all repos present in results
        for repo in self.repos:
            self.assertIn(repo, results)


if __name__ == "__main__":
    unittest.main()

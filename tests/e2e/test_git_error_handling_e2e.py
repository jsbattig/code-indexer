"""End-to-end tests for complete git error handling and logging workflow.

Tests the full integration of exception logging and git retry logic:
- Log file creation in appropriate locations
- Git command failure logging with full context
- Automatic retry behavior for transient failures
- Error propagation after exhausting retries
"""

import os
import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest


class TestGitErrorHandlingE2E:
    """E2E tests for git error handling with exception logging."""

    def test_git_error_logged_with_full_context_e2e(self, tmp_path):
        """Test that git errors are logged with command, cwd, and stack trace."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger
        from src.code_indexer.utils.git_runner import run_git_command_with_retry

        # Setup: Create a real git repository
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        # Initialize exception logger
        logger = ExceptionLogger.initialize(repo_dir, mode="cli")

        # Execute git command that will fail (both attempts)
        with pytest.raises(subprocess.CalledProcessError):
            run_git_command_with_retry(
                ["git", "add", "nonexistent_file.txt"],
                cwd=repo_dir,
                check=True,
                capture_output=True,
                text=True,
            )

        # Verify log file exists
        assert logger.log_file_path.exists()

        # Read and verify log contents
        with open(logger.log_file_path) as f:
            content = f.read()

        # Should have 2 log entries (one for each attempt)
        entries = [e for e in content.split("\n---\n") if e.strip()]
        assert len(entries) == 2

        # Verify first failure log
        log1 = json.loads(entries[0])
        assert "git_command" in log1["context"]
        assert "add" in log1["context"]["git_command"]
        assert "nonexistent_file.txt" in log1["context"]["git_command"]
        assert (
            log1["context"]["returncode"] != 0
        )  # Non-zero return code (may be 1 or 128)
        assert "attempt" in log1["context"]
        assert "1/2" in log1["context"]["attempt"]

        # Verify second failure log
        log2 = json.loads(entries[1])
        assert "attempt" in log2["context"]
        assert "2/2" in log2["context"]["attempt"]

    def test_cli_mode_log_file_location_e2e(self, tmp_path):
        """Test that CLI mode creates log file in .code-indexer directory."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger

        project_root = tmp_path / "cli_project"
        project_root.mkdir()

        logger = ExceptionLogger.initialize(project_root, mode="cli")

        # Verify log file is in .code-indexer directory
        assert logger.log_file_path.parent == project_root / ".code-indexer"
        assert logger.log_file_path.exists()

        # Verify filename format
        filename = logger.log_file_path.name
        assert filename.startswith("error_")
        assert str(os.getpid()) in filename
        assert filename.endswith(".log")

    def test_server_mode_log_file_location_e2e(self, tmp_path, monkeypatch):
        """Test that Server mode creates log file in ~/.cidx-server/logs/."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger

        # Mock home directory
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        project_root = tmp_path / "server_project"
        project_root.mkdir()

        logger = ExceptionLogger.initialize(project_root, mode="server")

        # Verify log file is in ~/.cidx-server/logs/
        expected_log_dir = fake_home / ".cidx-server" / "logs"
        assert logger.log_file_path.parent == expected_log_dir
        assert logger.log_file_path.exists()

    def test_retry_behavior_e2e(self, tmp_path):
        """Test retry behavior with simulated transient failure."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger
        from src.code_indexer.utils.git_runner import run_git_command_with_retry
        from unittest.mock import patch

        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # Initialize git
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)

        # Initialize exception logger
        logger = ExceptionLogger.initialize(repo_dir, mode="cli")

        call_count = 0
        original_run = subprocess.run

        def mock_run_with_recovery(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # First call fails, second succeeds
            if call_count == 1:
                error = subprocess.CalledProcessError(
                    returncode=1,
                    cmd=args[0],
                )
                error.stderr = "fatal: Unable to create '.git/index.lock': File exists"
                raise error
            else:
                # Call real subprocess.run for success
                return original_run(*args, **kwargs)

        with patch("subprocess.run", side_effect=mock_run_with_recovery):
            # This should succeed after retry
            result = run_git_command_with_retry(
                ["git", "status"],
                cwd=repo_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0
            assert call_count == 2  # Initial + 1 retry

        # Verify only 1 log entry (for the first failure)
        with open(logger.log_file_path) as f:
            content = f.read()

        entries = [e for e in content.split("\n---\n") if e.strip()]
        assert len(entries) == 1

        log1 = json.loads(entries[0])
        assert "1/2" in log1["context"]["attempt"]

    def test_thread_exception_captured_e2e(self, tmp_path):
        """Test that uncaught thread exceptions are captured and logged."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger
        import threading

        project_root = tmp_path / "thread_test_project"
        project_root.mkdir()

        logger = ExceptionLogger.initialize(project_root, mode="cli")
        logger.install_thread_exception_hook()

        exception_raised = threading.Event()

        def failing_thread():
            try:
                raise ValueError("Thread exception test")
            finally:
                exception_raised.set()

        thread = threading.Thread(target=failing_thread, name="TestThread")
        thread.start()
        thread.join(timeout=2)

        # Wait for exception to be logged
        assert exception_raised.wait(timeout=2)
        time.sleep(0.1)

        # Verify exception was logged
        with open(logger.log_file_path) as f:
            content = f.read()

        assert "ValueError" in content
        assert "Thread exception test" in content
        assert "TestThread" in content

    def test_remove_git_directory_during_operation_e2e(self, tmp_path):
        """Test handling when .git directory is removed during operation."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger
        from src.code_indexer.utils.git_runner import run_git_command_with_retry

        # Setup: Create a real git repository with a commit
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        # Create a file and commit it
        test_file = repo_dir / "test.txt"
        test_file.write_text("test content")
        subprocess.run(
            ["git", "add", "."], cwd=repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        # Initialize exception logger
        logger = ExceptionLogger.initialize(repo_dir, mode="cli")

        # Remove .git directory
        shutil.rmtree(repo_dir / ".git")

        # Try to run git command - should fail and log
        with pytest.raises(subprocess.CalledProcessError):
            run_git_command_with_retry(
                ["git", "log"],
                cwd=repo_dir,
                check=True,
                capture_output=True,
                text=True,
            )

        # Verify both retry attempts were logged
        with open(logger.log_file_path) as f:
            content = f.read()

        assert (
            "not a git repository" in content.lower() or "not a git" in content.lower()
        )

        # Should have 2 log entries
        entries = [e for e in content.split("\n---\n") if e.strip()]
        assert len(entries) == 2

    def test_multiple_operations_append_to_log_e2e(self, tmp_path):
        """Test that multiple operations append to the same log file."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger
        from src.code_indexer.utils.git_runner import run_git_command_with_retry

        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)

        logger = ExceptionLogger.initialize(repo_dir, mode="cli")

        # Perform multiple failing operations
        for i in range(3):
            with pytest.raises(subprocess.CalledProcessError):
                run_git_command_with_retry(
                    ["git", "add", f"nonexistent_{i}.txt"],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                )

        # Verify all operations were logged
        with open(logger.log_file_path) as f:
            content = f.read()

        # Each operation tries twice, so we should have 6 entries total
        entries = [e for e in content.split("\n---\n") if e.strip()]
        assert len(entries) == 6

        # Verify each file appears in logs
        assert "nonexistent_0.txt" in content
        assert "nonexistent_1.txt" in content
        assert "nonexistent_2.txt" in content

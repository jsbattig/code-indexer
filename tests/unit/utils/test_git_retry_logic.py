"""Unit tests for git command retry logic.

Tests automatic retry functionality for transient git failures including:
- Successful execution on first attempt (no retry needed)
- Failure followed by successful retry
- Double failure with error propagation
- Full command context logging on failures
"""

import subprocess
from unittest.mock import Mock, patch

import pytest


class TestGitRetryLogic:
    """Test git command retry wrapper."""

    def test_successful_command_no_retry(self, tmp_path):
        """Test that successful git command executes once without retry."""
        from src.code_indexer.utils.git_runner import run_git_command_with_retry

        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # Initialize real git repo
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

        # Mock subprocess.run to count calls
        with patch("subprocess.run") as mock_run:
            # Return successful result
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "success output"
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            result = run_git_command_with_retry(
                ["git", "status"],
                cwd=repo_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            # Should only be called once (no retry needed)
            assert mock_run.call_count == 1
            assert result.returncode == 0
            assert result.stdout == "success output"

    def test_failure_then_success_on_retry(self, tmp_path):
        """Test that transient failure triggers retry and succeeds."""
        from src.code_indexer.utils.git_runner import run_git_command_with_retry

        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        call_count = 0

        def mock_subprocess_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First attempt fails with lock contention
                error = subprocess.CalledProcessError(
                    returncode=1,
                    cmd=args[0],
                    stderr="fatal: Unable to create '.git/index.lock': File exists",
                )
                raise error
            else:
                # Second attempt succeeds
                result = Mock()
                result.returncode = 0
                result.stdout = "retry success"
                result.stderr = ""
                return result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            with patch("time.sleep") as mock_sleep:
                result = run_git_command_with_retry(
                    ["git", "add", "."],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                )

                # Should be called twice (initial + 1 retry)
                assert call_count == 2

                # Should wait before retry
                mock_sleep.assert_called_once_with(1)

                # Final result should be success
                assert result.returncode == 0
                assert result.stdout == "retry success"

    def test_double_failure_propagates_exception(self, tmp_path):
        """Test that persistent failure exhausts retries and propagates error."""
        from src.code_indexer.utils.git_runner import run_git_command_with_retry

        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        call_count = 0

        def mock_subprocess_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # Always fail
            error = subprocess.CalledProcessError(
                returncode=128,
                cmd=args[0],
                stderr="fatal: not a git repository",
            )
            raise error

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            with patch("time.sleep") as mock_sleep:
                with pytest.raises(subprocess.CalledProcessError) as exc_info:
                    run_git_command_with_retry(
                        ["git", "log"],
                        cwd=repo_dir,
                        check=True,
                        capture_output=True,
                        text=True,
                    )

                # Should be called twice (initial + 1 retry)
                assert call_count == 2

                # Should wait before retry
                mock_sleep.assert_called_once_with(1)

                # Exception should be the git error
                assert exc_info.value.returncode == 128
                assert "not a git repository" in exc_info.value.stderr

    def test_timeout_not_retried(self, tmp_path):
        """Test that timeout exceptions are not retried (not transient)."""
        from src.code_indexer.utils.git_runner import run_git_command_with_retry

        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        call_count = 0

        def mock_subprocess_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # Timeout on first attempt
            raise subprocess.TimeoutExpired(cmd=args[0], timeout=5)

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            with patch("time.sleep") as mock_sleep:
                with pytest.raises(subprocess.TimeoutExpired):
                    run_git_command_with_retry(
                        ["git", "clone", "large-repo"],
                        cwd=repo_dir,
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )

                # Should only be called once (timeout not retried)
                assert call_count == 1

                # Should NOT wait/retry
                mock_sleep.assert_not_called()

    def test_retry_logs_failures_with_full_context(self, tmp_path):
        """Test that git failures are logged with command, cwd, and stack trace."""
        from src.code_indexer.utils.git_runner import run_git_command_with_retry
        from src.code_indexer.utils.exception_logger import ExceptionLogger

        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # Initialize exception logger
        logger = ExceptionLogger.initialize(repo_dir, mode="cli")

        call_count = 0

        def mock_subprocess_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # Both attempts fail
            error = subprocess.CalledProcessError(
                returncode=1,
                cmd=args[0],
            )
            # Set stdout and stderr as attributes
            error.stdout = ""
            error.stderr = "error: pathspec 'nonexistent' did not match any file(s)"
            raise error

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            with patch("time.sleep"):
                with pytest.raises(subprocess.CalledProcessError):
                    run_git_command_with_retry(
                        ["git", "add", "nonexistent"],
                        cwd=repo_dir,
                        check=True,
                        capture_output=True,
                        text=True,
                    )

        # Read log file
        with open(logger.log_file_path) as f:
            content = f.read()

        # Should have 2 log entries (one for each attempt)
        entries = [e for e in content.split("\n---\n") if e.strip()]
        assert len(entries) == 2

        # Verify first failure log
        import json

        log1 = json.loads(entries[0])
        assert "git" in str(log1.get("context", {}))
        assert "add" in str(log1.get("context", {}))
        assert "nonexistent" in str(log1.get("context", {}))
        assert "attempt 1" in log1.get("exception_message", "").lower()

        # Verify second failure log
        log2 = json.loads(entries[1])
        assert "attempt 2" in log2.get("exception_message", "").lower()

    def test_retry_delay_is_one_second(self, tmp_path):
        """Test that retry delay is exactly 1 second."""
        from src.code_indexer.utils.git_runner import run_git_command_with_retry

        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        call_count = 0

        def mock_subprocess_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                raise subprocess.CalledProcessError(
                    returncode=1, cmd=args[0], stderr="transient error"
                )
            else:
                result = Mock()
                result.returncode = 0
                result.stdout = "success"
                return result

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            with patch("time.sleep") as mock_sleep:
                run_git_command_with_retry(
                    ["git", "status"],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                )

                # Verify sleep was called with exactly 1 second
                mock_sleep.assert_called_once_with(1)

    def test_max_retries_is_one(self, tmp_path):
        """Test that maximum retry attempts is 1 (total 2 attempts)."""
        from src.code_indexer.utils.git_runner import run_git_command_with_retry

        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        call_count = 0

        def mock_subprocess_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise subprocess.CalledProcessError(
                returncode=1, cmd=args[0], stderr="persistent error"
            )

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            with patch("time.sleep"):
                with pytest.raises(subprocess.CalledProcessError):
                    run_git_command_with_retry(
                        ["git", "status"],
                        cwd=repo_dir,
                        check=True,
                        capture_output=True,
                        text=True,
                    )

                # Should only retry once (2 total attempts)
                assert call_count == 2


class TestGitRetryIntegrationWithExistingRunner:
    """Test that retry logic integrates with existing git_runner.py."""

    def test_backward_compatibility_with_run_git_command(self, tmp_path):
        """Test that existing run_git_command still works without retry."""
        from src.code_indexer.utils.git_runner import run_git_command

        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)

        # Old function should still work
        result = run_git_command(["git", "status"], cwd=repo_dir, check=True)

        assert result.returncode == 0

    def test_run_git_command_with_retry_is_new_function(self):
        """Test that run_git_command_with_retry is a separate new function."""
        from src.code_indexer.utils import git_runner

        # Both functions should exist
        assert hasattr(git_runner, "run_git_command")
        assert hasattr(git_runner, "run_git_command_with_retry")

        # They should be different functions
        assert git_runner.run_git_command != git_runner.run_git_command_with_retry

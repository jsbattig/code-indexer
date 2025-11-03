"""Unit tests for sequential command execution in proxy mode.

Tests the sequential executor that processes start, stop, and uninstall
commands one repository at a time to prevent resource contention.
"""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

from code_indexer.proxy.sequential_executor import (
    SequentialCommandExecutor,
    SequentialExecutionResult,
)


class TestSequentialCommandExecutor:
    """Test the SequentialCommandExecutor class."""

    def test_initialization_with_repositories(self):
        """Verify executor initializes with repository list."""
        repos = ["repo1", "repo2", "repo3"]
        executor = SequentialCommandExecutor(repos)
        assert executor.repositories == repos

    def test_initialization_with_empty_list(self):
        """Verify executor handles empty repository list."""
        executor = SequentialCommandExecutor([])
        assert executor.repositories == []

    def test_initialization_with_proxy_root(self):
        """Verify executor stores proxy root for path resolution."""
        repos = ["repo1", "repo2"]
        proxy_root = Path("/tmp/test-proxy")
        executor = SequentialCommandExecutor(repos, proxy_root=proxy_root)
        assert executor.proxy_root == proxy_root


class TestExecuteSequential:
    """Test the execute_sequential method."""

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    def test_sequential_execution_order(self, mock_run):
        """Verify repositories processed one at a time in order."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)

        repos = ["repo1", "repo2", "repo3"]
        executor = SequentialCommandExecutor(repos)
        executor.execute_sequential("start", [])

        # Verify exactly 3 subprocess calls
        assert mock_run.call_count == 3

        # Verify calls happened in order
        calls = mock_run.call_args_list
        assert "repo1" in str(calls[0])
        assert "repo2" in str(calls[1])
        assert "repo3" in str(calls[2])

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    def test_command_completes_before_next_begins(self, mock_run):
        """Verify each command completes before next starts."""
        call_order = []

        def record_call(*args, **kwargs):
            call_order.append(kwargs.get("cwd"))
            return Mock(stdout="", stderr="", returncode=0)

        mock_run.side_effect = record_call

        repos = ["repo1", "repo2", "repo3"]
        executor = SequentialCommandExecutor(repos)
        executor.execute_sequential("start", [])

        # Verify sequential order (no interleaving)
        assert call_order == ["repo1", "repo2", "repo3"]

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    def test_timeout_configuration(self, mock_run):
        """Verify 10-minute timeout used for container operations."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)

        executor = SequentialCommandExecutor(["repo1"])
        executor.execute_sequential("start", [])

        # Verify timeout is 600 seconds (10 minutes)
        call_args = mock_run.call_args
        assert call_args.kwargs["timeout"] == 600

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    def test_returns_results_dict(self, mock_run):
        """Verify execute_sequential returns results dictionary."""
        mock_run.return_value = Mock(stdout="success", stderr="", returncode=0)

        repos = ["repo1", "repo2"]
        executor = SequentialCommandExecutor(repos)
        result = executor.execute_sequential("start", [])

        # Verify result is SequentialExecutionResult
        assert isinstance(result, SequentialExecutionResult)
        assert len(result.results) == 2
        assert "repo1" in result.results
        assert "repo2" in result.results

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    def test_result_contains_stdout_stderr_exitcode(self, mock_run):
        """Verify each result contains stdout, stderr, and exit code."""
        mock_run.return_value = Mock(stdout="output", stderr="error", returncode=0)

        executor = SequentialCommandExecutor(["repo1"])
        result = executor.execute_sequential("start", [])

        repo_result = result.results["repo1"]
        assert repo_result["stdout"] == "output"
        assert repo_result["stderr"] == "error"
        assert repo_result["exit_code"] == 0

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    def test_command_with_arguments(self, mock_run):
        """Verify command arguments passed correctly."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)

        executor = SequentialCommandExecutor(["repo1"])
        executor.execute_sequential("start", ["--force-docker"])

        # Verify command includes arguments
        call_args = mock_run.call_args
        cmd = call_args.args[0]
        assert "start" in cmd
        assert "--force-docker" in cmd


class TestErrorContinuity:
    """Test error handling and continuity."""

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    def test_failed_repo_doesnt_prevent_next(self, mock_run):
        """Verify failed repository doesn't prevent processing remaining repos."""
        # First call fails, second succeeds
        mock_run.side_effect = [
            Mock(stdout="", stderr="error1", returncode=1),
            Mock(stdout="success", stderr="", returncode=0),
        ]

        repos = ["repo1", "repo2"]
        executor = SequentialCommandExecutor(repos)
        result = executor.execute_sequential("start", [])

        # Both repos should be in results
        assert len(result.results) == 2
        assert result.results["repo1"]["exit_code"] == 1
        assert result.results["repo2"]["exit_code"] == 0

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    def test_exception_doesnt_stop_processing(self, mock_run):
        """Verify exception in one repo doesn't stop others."""
        # First call raises exception, second succeeds
        mock_run.side_effect = [
            subprocess.TimeoutExpired("cidx", 600),
            Mock(stdout="success", stderr="", returncode=0),
        ]

        repos = ["repo1", "repo2"]
        executor = SequentialCommandExecutor(repos)
        result = executor.execute_sequential("start", [])

        # Both repos should be in results
        assert len(result.results) == 2
        # First repo should have error recorded (check for timeout message)
        assert "timed out" in result.results["repo1"]["stderr"].lower()
        # Second repo should succeed
        assert result.results["repo2"]["exit_code"] == 0

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    def test_partial_success_tracking(self, mock_run):
        """Verify partial success/failure tracking."""
        # Mix of success and failure
        mock_run.side_effect = [
            Mock(stdout="", stderr="", returncode=0),  # success
            Mock(stdout="", stderr="error", returncode=1),  # failure
            Mock(stdout="", stderr="", returncode=0),  # success
        ]

        repos = ["repo1", "repo2", "repo3"]
        executor = SequentialCommandExecutor(repos)
        result = executor.execute_sequential("start", [])

        # Verify counts
        assert result.success_count == 2
        assert result.failure_count == 1
        assert result.total_repos == 3


class TestProgressReporting:
    """Test progress indication during execution."""

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    @patch("builtins.print")
    def test_progress_shows_current_repository(self, mock_print, mock_run):
        """Verify progress indication shows current repository."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)

        repos = ["repo1", "repo2", "repo3"]
        executor = SequentialCommandExecutor(repos)
        executor.execute_sequential("start", [])

        # Verify progress messages printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        progress_messages = [
            c for c in print_calls if "[1/3]" in c or "[2/3]" in c or "[3/3]" in c
        ]
        assert len(progress_messages) >= 3

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    @patch("builtins.print")
    def test_progress_counter_increments(self, mock_print, mock_run):
        """Verify progress counter increments correctly."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)

        repos = ["repo1", "repo2"]
        executor = SequentialCommandExecutor(repos)
        executor.execute_sequential("start", [])

        # Check for [1/2] and [2/2] in output
        print_output = " ".join([str(call) for call in mock_print.call_args_list])
        assert "[1/2]" in print_output
        assert "[2/2]" in print_output

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    @patch("builtins.print")
    def test_success_failure_indicators(self, mock_print, mock_run):
        """Verify success/failure indicators shown."""
        # First succeeds, second fails
        mock_run.side_effect = [
            Mock(stdout="", stderr="", returncode=0),
            Mock(stdout="", stderr="error", returncode=1),
        ]

        repos = ["repo1", "repo2"]
        executor = SequentialCommandExecutor(repos)
        executor.execute_sequential("start", [])

        # Check for success/failure indicators
        print_output = " ".join([str(call) for call in mock_print.call_args_list])
        assert "Success" in print_output or "✓" in print_output
        assert "Failed" in print_output or "✗" in print_output


class TestRepositoryOrdering:
    """Test repository execution order."""

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    def test_follows_configuration_order(self, mock_run):
        """Verify execution follows configuration list order."""
        call_order = []

        def record_call(*args, **kwargs):
            call_order.append(kwargs.get("cwd"))
            return Mock(stdout="", stderr="", returncode=0)

        mock_run.side_effect = record_call

        # Specific order
        repos = ["z-repo", "a-repo", "m-repo"]
        executor = SequentialCommandExecutor(repos)
        executor.execute_sequential("start", [])

        # Should maintain input order, not alphabetical
        assert call_order == ["z-repo", "a-repo", "m-repo"]

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    def test_order_preserved_with_failures(self, mock_run):
        """Verify order preserved even when some repos fail."""
        call_order = []

        def record_call(*args, **kwargs):
            cwd = kwargs.get("cwd")
            call_order.append(cwd)
            # Fail repo2
            if cwd == "repo2":
                return Mock(stdout="", stderr="error", returncode=1)
            return Mock(stdout="", stderr="", returncode=0)

        mock_run.side_effect = record_call

        repos = ["repo1", "repo2", "repo3"]
        executor = SequentialCommandExecutor(repos)
        executor.execute_sequential("start", [])

        # Order should be maintained
        assert call_order == ["repo1", "repo2", "repo3"]


class TestSequentialExecutionResult:
    """Test the SequentialExecutionResult class."""

    def test_result_initialization(self):
        """Verify result object initializes correctly."""
        result = SequentialExecutionResult()
        assert result.results == {}
        assert result.success_count == 0
        assert result.failure_count == 0
        assert result.total_repos == 0

    def test_add_success_result(self):
        """Verify adding successful result."""
        result = SequentialExecutionResult()
        result.add_result("repo1", stdout="ok", stderr="", exit_code=0)

        assert result.success_count == 1
        assert result.failure_count == 0
        assert "repo1" in result.results

    def test_add_failure_result(self):
        """Verify adding failed result."""
        result = SequentialExecutionResult()
        result.add_result("repo1", stdout="", stderr="error", exit_code=1)

        assert result.success_count == 0
        assert result.failure_count == 1
        assert result.results["repo1"]["exit_code"] == 1

    def test_total_repos_count(self):
        """Verify total_repos counts all repositories."""
        result = SequentialExecutionResult()
        result.add_result("repo1", stdout="", stderr="", exit_code=0)
        result.add_result("repo2", stdout="", stderr="error", exit_code=1)

        assert result.total_repos == 2

    def test_is_complete_success(self):
        """Verify is_complete_success returns True when all succeed."""
        result = SequentialExecutionResult()
        result.add_result("repo1", stdout="", stderr="", exit_code=0)
        result.add_result("repo2", stdout="", stderr="", exit_code=0)

        assert result.is_complete_success() is True

    def test_is_complete_success_false_on_failure(self):
        """Verify is_complete_success returns False when any fail."""
        result = SequentialExecutionResult()
        result.add_result("repo1", stdout="", stderr="", exit_code=0)
        result.add_result("repo2", stdout="", stderr="error", exit_code=1)

        assert result.is_complete_success() is False

    def test_get_failed_repositories(self):
        """Verify get_failed_repositories returns failed repos."""
        result = SequentialExecutionResult()
        result.add_result("repo1", stdout="", stderr="", exit_code=0)
        result.add_result("repo2", stdout="", stderr="error", exit_code=1)
        result.add_result("repo3", stdout="", stderr="error", exit_code=1)

        failed = result.get_failed_repositories()
        assert len(failed) == 2
        assert "repo2" in failed
        assert "repo3" in failed

    def test_get_successful_repositories(self):
        """Verify get_successful_repositories returns successful repos."""
        result = SequentialExecutionResult()
        result.add_result("repo1", stdout="", stderr="", exit_code=0)
        result.add_result("repo2", stdout="", stderr="error", exit_code=1)
        result.add_result("repo3", stdout="", stderr="", exit_code=0)

        successful = result.get_successful_repositories()
        assert len(successful) == 2
        assert "repo1" in successful
        assert "repo3" in successful


class TestCommandConstruction:
    """Test command construction for subprocess calls."""

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    def test_cidx_command_construction(self, mock_run):
        """Verify cidx command constructed correctly."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)

        executor = SequentialCommandExecutor(["repo1"])
        executor.execute_sequential("start", [])

        # Verify command structure
        call_args = mock_run.call_args
        cmd = call_args.args[0]
        assert cmd[0] == "cidx"
        assert cmd[1] == "start"

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    def test_cwd_set_to_repository(self, mock_run):
        """Verify cwd set to repository path."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)

        executor = SequentialCommandExecutor(["repo1"])
        executor.execute_sequential("start", [])

        # Verify cwd is set
        call_args = mock_run.call_args
        assert call_args.kwargs["cwd"] == "repo1"

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    def test_capture_output_enabled(self, mock_run):
        """Verify subprocess captures output."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)

        executor = SequentialCommandExecutor(["repo1"])
        executor.execute_sequential("start", [])

        # Verify output capture settings
        call_args = mock_run.call_args
        assert call_args.kwargs["capture_output"] is True
        assert call_args.kwargs["text"] is True


class TestFormattedErrorOutput:
    """Test formatted error output in sequential execution."""

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    @patch("builtins.print")
    def test_formatted_error_for_failure(self, mock_print, mock_run):
        """Verify formatted error shown for failed repository."""
        mock_run.return_value = Mock(
            stdout="", stderr="Cannot connect to Qdrant", returncode=1
        )

        executor = SequentialCommandExecutor(["backend/auth-service"])
        executor.execute_sequential("start", [])

        # Check print calls for formatted error
        print_calls = [str(call) for call in mock_print.call_args_list]
        print_output = " ".join(print_calls)

        # Should have error indicator
        assert "✗" in print_output or "Failed" in print_output

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    @patch("builtins.print")
    def test_repository_number_in_progress(self, mock_print, mock_run):
        """Verify repository number shown in progress ([1/3], [2/3], etc)."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)

        repos = ["repo1", "repo2", "repo3"]
        executor = SequentialCommandExecutor(repos)
        executor.execute_sequential("start", [])

        # Check for [N/Total] format in print calls
        print_calls = [str(call) for call in mock_print.call_args_list]
        print_output = " ".join(print_calls)

        assert "[1/3]" in print_output
        assert "[2/3]" in print_output
        assert "[3/3]" in print_output

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    @patch("builtins.print")
    def test_inline_error_during_execution(self, mock_print, mock_run):
        """Verify inline error shown during execution."""
        # First succeeds, second fails
        mock_run.side_effect = [
            Mock(stdout="", stderr="", returncode=0),
            Mock(stdout="", stderr="Port conflict", returncode=1),
        ]

        repos = ["repo1", "repo2"]
        executor = SequentialCommandExecutor(repos)
        executor.execute_sequential("start", [])

        # Check print calls
        print_calls = [str(call) for call in mock_print.call_args_list]
        print_output = " ".join(print_calls)

        # Should have inline failure indicator
        assert "✗" in print_output or "Failed" in print_output

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    @patch("builtins.print")
    def test_detailed_error_section_at_end(self, mock_print, mock_run):
        """Verify detailed error section shown at end."""
        mock_run.side_effect = [
            Mock(stdout="", stderr="", returncode=0),
            Mock(stdout="", stderr="Error 1", returncode=1),
            Mock(stdout="", stderr="Error 2", returncode=1),
        ]

        repos = ["repo1", "repo2", "repo3"]
        executor = SequentialCommandExecutor(repos)
        executor.execute_sequential("start", [])

        # Check print calls for error section
        print_calls = [str(call) for call in mock_print.call_args_list]
        print_output = " ".join(print_calls)

        # Should have summary with error count
        assert "2 failed" in print_output

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    @patch("builtins.print")
    def test_success_indicator_format(self, mock_print, mock_run):
        """Verify success indicator uses checkmark."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)

        executor = SequentialCommandExecutor(["repo1"])
        executor.execute_sequential("start", [])

        print_calls = [str(call) for call in mock_print.call_args_list]
        print_output = " ".join(print_calls)

        # Should have success indicator
        assert "✓" in print_output or "Success" in print_output

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    @patch("builtins.print")
    def test_error_count_in_summary(self, mock_print, mock_run):
        """Verify error count shown in summary."""
        mock_run.side_effect = [
            Mock(stdout="", stderr="", returncode=0),
            Mock(stdout="", stderr="Error", returncode=1),
            Mock(stdout="", stderr="Error", returncode=1),
            Mock(stdout="", stderr="Error", returncode=1),
        ]

        repos = ["repo1", "repo2", "repo3", "repo4"]
        executor = SequentialCommandExecutor(repos)
        executor.execute_sequential("start", [])

        print_calls = [str(call) for call in mock_print.call_args_list]
        print_output = " ".join(print_calls)

        # Should show error count
        assert "3 failed" in print_output
        assert "1 succeeded" in print_output


class TestDetailedErrorReporting:
    """Test detailed error reporting with ErrorMessageFormatter."""

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    @patch("builtins.print")
    def test_detailed_error_format_at_end(self, mock_print, mock_run):
        """Verify detailed errors shown at end with formatting."""
        mock_run.return_value = Mock(
            stdout="", stderr="Cannot connect to Qdrant service", returncode=1
        )

        executor = SequentialCommandExecutor(["backend/auth-service"])
        result = executor.execute_sequential("start", [])

        # Check that result contains error information
        assert result.failure_count == 1
        assert "backend/auth-service" in result.get_failed_repositories()

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    @patch("builtins.print")
    def test_multiple_errors_each_formatted(self, mock_print, mock_run):
        """Verify each error gets its own formatted block."""
        mock_run.side_effect = [
            Mock(stdout="", stderr="Error 1", returncode=1),
            Mock(stdout="", stderr="Error 2", returncode=1),
        ]

        repos = ["repo1", "repo2"]
        executor = SequentialCommandExecutor(repos)
        result = executor.execute_sequential("start", [])

        # Check result has both failures
        assert result.failure_count == 2
        failed_repos = result.get_failed_repositories()
        assert "repo1" in failed_repos
        assert "repo2" in failed_repos

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    @patch("builtins.print")
    def test_no_error_section_when_all_succeed(self, mock_print, mock_run):
        """Verify no error section when all succeed."""
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)

        repos = ["repo1", "repo2"]
        executor = SequentialCommandExecutor(repos)
        result = executor.execute_sequential("start", [])

        print_calls = [str(call) for call in mock_print.call_args_list]
        print_output = " ".join(print_calls)

        # Should not have error formatting
        assert result.failure_count == 0
        assert "0 failed" in print_output

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    @patch("builtins.print")
    def test_repository_name_in_error_block(self, mock_print, mock_run):
        """Verify repository name appears in error block."""
        mock_run.return_value = Mock(
            stdout="", stderr="Service failed to start", returncode=1
        )

        executor = SequentialCommandExecutor(["backend/auth-service"])
        result = executor.execute_sequential("start", [])

        # Repository should be in failed list
        failed = result.get_failed_repositories()
        assert "backend/auth-service" in failed

    @patch("code_indexer.proxy.sequential_executor.subprocess.run")
    @patch("builtins.print")
    def test_visual_separation_between_repos(self, mock_print, mock_run):
        """Verify visual separation between repository operations."""
        mock_run.side_effect = [
            Mock(stdout="", stderr="", returncode=0),
            Mock(stdout="", stderr="Error", returncode=1),
            Mock(stdout="", stderr="", returncode=0),
        ]

        repos = ["repo1", "repo2", "repo3"]
        executor = SequentialCommandExecutor(repos)
        executor.execute_sequential("start", [])

        print_calls = [str(call) for call in mock_print.call_args_list]

        # Should have progress indicators for each repo
        assert len([c for c in print_calls if "[1/3]" in str(c)]) > 0
        assert len([c for c in print_calls if "[2/3]" in str(c)]) > 0
        assert len([c for c in print_calls if "[3/3]" in str(c)]) > 0

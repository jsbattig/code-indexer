"""Sequential command execution for proxy mode.

This module executes container lifecycle commands (start, stop, uninstall)
sequentially across repositories to prevent resource contention and race conditions.

Key features:
- One repository at a time execution
- 10-minute timeout per repository
- Progress reporting with [N/Total] format
- Partial success model (failures don't stop processing)
- Maintains configuration list order
- Formatted error reporting with ErrorMessageFormatter
"""

import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

from .error_formatter import ErrorMessage, ErrorMessageFormatter
from .hint_generator import HintGenerator


class SequentialExecutionResult:
    """Result of sequential command execution across repositories.

    Tracks success/failure for each repository and provides summary methods.
    """

    def __init__(self):
        """Initialize empty result."""
        self.results: Dict[str, Dict[str, Any]] = {}
        self.success_count: int = 0
        self.failure_count: int = 0
        self.total_repos: int = 0

    def add_result(
        self,
        repo_path: str,
        stdout: str,
        stderr: str,
        exit_code: int
    ) -> None:
        """Add result for a repository.

        Args:
            repo_path: Repository path (relative or absolute)
            stdout: Standard output from command
            stderr: Standard error from command
            exit_code: Process exit code (0 = success)
        """
        self.results[repo_path] = {
            'stdout': stdout,
            'stderr': stderr,
            'exit_code': exit_code
        }

        if exit_code == 0:
            self.success_count += 1
        else:
            self.failure_count += 1

        self.total_repos += 1

    def is_complete_success(self) -> bool:
        """Check if all repositories succeeded.

        Returns:
            True if all repositories succeeded, False otherwise
        """
        return self.failure_count == 0 and self.total_repos > 0

    def get_failed_repositories(self) -> List[str]:
        """Get list of failed repository paths.

        Returns:
            List of repository paths that failed
        """
        return [
            repo for repo, result in self.results.items()
            if result['exit_code'] != 0
        ]

    def get_successful_repositories(self) -> List[str]:
        """Get list of successful repository paths.

        Returns:
            List of repository paths that succeeded
        """
        return [
            repo for repo, result in self.results.items()
            if result['exit_code'] == 0
        ]


class SequentialCommandExecutor:
    """Execute commands sequentially across multiple repositories.

    Container lifecycle commands (start, stop, uninstall) execute one
    repository at a time to prevent resource contention, port conflicts,
    and race conditions. Uses ErrorMessageFormatter for clear error reporting.
    """

    def __init__(
        self,
        repositories: List[str],
        proxy_root: Optional[Path] = None
    ):
        """Initialize sequential executor.

        Args:
            repositories: List of repository paths (relative to proxy_root)
            proxy_root: Optional proxy root directory for path resolution
        """
        self.repositories = repositories
        self.proxy_root = proxy_root
        self.formatter = ErrorMessageFormatter()
        self.hint_generator = HintGenerator()

    def execute_sequential(
        self,
        command: str,
        args: List[str]
    ) -> SequentialExecutionResult:
        """Execute command sequentially across all repositories.

        Processes repositories one at a time in configuration order.
        Failures in one repository don't prevent processing others.

        Args:
            command: CIDX command to execute (start/stop/uninstall)
            args: Command arguments (e.g., ['--force-docker'])

        Returns:
            SequentialExecutionResult with results for each repository
        """
        result = SequentialExecutionResult()

        total = len(self.repositories)

        for i, repo in enumerate(self.repositories, 1):
            # Progress indication
            print(f"[{i}/{total}] Processing {repo}...")

            # Execute command for this repository
            stdout, stderr, exit_code = self._execute_single(repo, command, args)

            # Store result
            result.add_result(repo, stdout, stderr, exit_code)

            # Report result immediately with formatted output
            if exit_code == 0:
                print(f"  {self.formatter.format_success(repo, 'Success')}")
            else:
                print(f"  {self.formatter.format_inline_error(repo, 'Failed')}")

        # Print summary with detailed errors
        self._print_summary(result, command)

        return result

    def _execute_single(
        self,
        repo_path: str,
        command: str,
        args: List[str]
    ) -> tuple:
        """Execute command in single repository.

        Args:
            repo_path: Repository path (relative to proxy_root)
            command: CIDX command (start/stop/uninstall)
            args: Command arguments

        Returns:
            Tuple of (stdout, stderr, exit_code)
        """
        # Construct command
        cmd = ['cidx', command] + args

        try:
            # Execute with 10-minute timeout for container operations
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes
            )

            return result.stdout, result.stderr, result.returncode

        except subprocess.TimeoutExpired as e:
            # Timeout is a failure condition
            stderr = f"Command timed out after 600 seconds: {e}"
            return '', stderr, 1

        except Exception as e:
            # Any other exception is a failure
            stderr = f"Exception during execution: {type(e).__name__}: {e}"
            return '', stderr, 1

    def _print_summary(
        self,
        result: SequentialExecutionResult,
        command: str
    ) -> None:
        """Print execution summary with detailed error reporting.

        Args:
            result: Execution result with success/failure counts
            command: Command that was executed
        """
        print(f"\n{'='*50}")
        print(f"Summary: {result.success_count} succeeded, {result.failure_count} failed")
        print(f"{'='*50}")

        # If there were failures, show detailed error section
        if result.failure_count > 0:
            self._print_detailed_errors(result, command)

    def _print_detailed_errors(
        self,
        result: SequentialExecutionResult,
        command: str
    ) -> None:
        """Print detailed error section for failed repositories.

        Args:
            result: Execution result with failure information
            command: Command that was executed
        """
        failed_repos = result.get_failed_repositories()

        print(f"\n{'='*60}")
        print(f"ERRORS ENCOUNTERED ({len(failed_repos)} total)")
        print(f"{'='*60}\n")

        for i, repo in enumerate(failed_repos, 1):
            if i > 1:
                print()  # Blank line between errors

            repo_result = result.results[repo]

            # Generate actionable hint for this error
            hint = self.hint_generator.generate_hint(
                command=command,
                error_text=repo_result['stderr'] if repo_result['stderr'] else "Unknown error",
                repository=repo
            )

            error = ErrorMessage(
                repository=repo,
                command=command,
                error_text=repo_result['stderr'] if repo_result['stderr'] else "Unknown error",
                exit_code=repo_result['exit_code'],
                hint=hint,
            )

            print(f"Error {i} of {len(failed_repos)}:")
            print(self.formatter.format_error(error))

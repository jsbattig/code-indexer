"""Parallel command execution engine for proxy mode.

This module provides the ParallelCommandExecutor class that executes
commands across multiple repositories concurrently using ThreadPoolExecutor.
"""

import os
import subprocess
import concurrent.futures
from typing import List, Dict, Tuple


class ParallelCommandExecutor:
    """Execute commands across multiple repositories in parallel.

    This class manages concurrent execution of CIDX commands across
    multiple repositories, respecting resource limits and handling
    errors gracefully.
    """

    MAX_WORKERS = 10  # Prevent system overload

    def __init__(self, repositories: List[str]):
        """Initialize parallel executor.

        Args:
            repositories: List of repository paths to execute commands in
        """
        self.repositories = repositories

    def execute_parallel(
        self, command: str, args: List[str]
    ) -> Dict[str, Tuple[str, str, int]]:
        """Execute command in parallel across all repositories.

        Args:
            command: CIDX command to execute (e.g., 'query', 'status')
            args: Command arguments

        Returns:
            Dictionary mapping repo_path -> (stdout, stderr, exit_code)
        """
        # Handle empty repository list
        if not self.repositories:
            return {}

        # Calculate worker count: min(repo_count, MAX_WORKERS)
        worker_count = min(len(self.repositories), self.MAX_WORKERS)
        results = {}

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=worker_count
        ) as executor:
            # Submit all tasks
            future_to_repo = {
                executor.submit(self._execute_single, repo, command, args): repo
                for repo in self.repositories
            }

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_repo):
                repo = future_to_repo[future]
                try:
                    stdout, stderr, exit_code = future.result()
                    results[repo] = (stdout, stderr, exit_code)
                except Exception as exc:
                    # Capture exceptions as failed execution
                    results[repo] = ("", str(exc), -1)

        return results

    def _execute_single(
        self, repo_path: str, command: str, args: List[str]
    ) -> Tuple[str, str, int]:
        """Execute command in single repository.

        Args:
            repo_path: Path to repository
            command: CIDX command to execute
            args: Command arguments

        Returns:
            Tuple of (stdout, stderr, exit_code)

        Raises:
            subprocess.TimeoutExpired: If command exceeds timeout
        """
        cmd = ["cidx", command] + args

        # Force wide terminal output to prevent line wrapping in captured output
        # Rich Console wraps text at COLUMNS width when output is captured.
        # By forcing COLUMNS=200, we ensure metadata lines don't wrap and break parsing.
        env = os.environ.copy()
        env["COLUMNS"] = "200"

        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            env=env,  # Use modified environment
        )

        return result.stdout, result.stderr, result.returncode

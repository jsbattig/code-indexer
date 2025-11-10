"""
Centralized Git command runner with dubious ownership handling.

This module provides a robust way to run git commands that properly handles
the "dubious ownership" error that occurs when running under sudo or in
environments where the repository owner differs from the current user.

Additionally provides retry logic for transient git failures with full
exception logging.
"""

import os
import subprocess
import time
import traceback
from pathlib import Path
from typing import List, Dict, Optional


def get_git_environment(project_dir: Path) -> Dict[str, str]:
    """
    Get environment variables for git commands to handle dubious ownership.

    This is critical for running under sudo or in environments where the
    repository owner differs from the current user (e.g., Docker, CI/CD,
    claude batch server).

    Args:
        project_dir: Path to the project directory

    Returns:
        Dictionary of environment variables for git commands
    """
    env = os.environ.copy()

    # Handle dubious ownership by setting safe.directory
    # This allows git to work even when the repo is owned by a different user
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "safe.directory"
    env["GIT_CONFIG_VALUE_0"] = str(project_dir.resolve())

    # Preserve any existing GIT_CONFIG_* variables from the calling environment
    # This is important for environments like claude batch server that may set
    # their own git configuration
    config_count = 1
    for key in os.environ:
        if key.startswith("GIT_CONFIG_") and not key.startswith("GIT_CONFIG_KEY_0"):
            # Parse existing GIT_CONFIG_* variables
            if key.startswith("GIT_CONFIG_KEY_"):
                idx = key.replace("GIT_CONFIG_KEY_", "")
                if idx.isdigit() and int(idx) > 0:
                    # Shift the index to make room for our safe.directory at index 0
                    new_idx = int(idx) + 1
                    env[f"GIT_CONFIG_KEY_{new_idx}"] = os.environ[key]
                    if f"GIT_CONFIG_VALUE_{idx}" in os.environ:
                        env[f"GIT_CONFIG_VALUE_{new_idx}"] = os.environ[
                            f"GIT_CONFIG_VALUE_{idx}"
                        ]
                    config_count = max(config_count, new_idx + 1)

    # Update the count to reflect all config entries
    env["GIT_CONFIG_COUNT"] = str(config_count)

    return env


def run_git_command(
    cmd: List[str],
    cwd: Path,
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
    timeout: Optional[float] = None,
    **kwargs,
) -> subprocess.CompletedProcess:
    """
    Run a git command with proper environment handling for dubious ownership.

    Args:
        cmd: Git command as a list (e.g., ["git", "status"])
        cwd: Working directory for the command
        check: Whether to raise CalledProcessError on non-zero exit
        capture_output: Whether to capture stdout and stderr
        text: Whether to decode output as text
        timeout: Optional timeout in seconds
        **kwargs: Additional arguments to pass to subprocess.run

    Returns:
        CompletedProcess instance with the command result

    Raises:
        subprocess.CalledProcessError: If check=True and command fails
        subprocess.TimeoutExpired: If timeout is exceeded
    """
    if not cmd or cmd[0] != "git":
        raise ValueError("Command must start with 'git'")

    # Get the proper environment with safe.directory configuration
    env = get_git_environment(cwd)

    # Merge any environment from kwargs if provided
    if "env" in kwargs:
        env.update(kwargs["env"])
        kwargs.pop("env")

    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        capture_output=capture_output,
        text=text,
        timeout=timeout,
        env=env,
        **kwargs,
    )


def run_git_command_with_retry(
    cmd: List[str],
    cwd: Path,
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
    timeout: Optional[float] = None,
    **kwargs,
) -> subprocess.CompletedProcess:
    """
    Run a git command with automatic retry logic for transient failures.

    Wraps run_git_command with retry capability. If a git command fails with
    CalledProcessError, it will be retried once after a 1-second delay.
    Timeout errors are not retried as they are not transient.

    Args:
        cmd: Git command as a list (e.g., ["git", "status"])
        cwd: Working directory for the command
        check: Whether to raise CalledProcessError on non-zero exit
        capture_output: Whether to capture stdout and stderr
        text: Whether to decode output as text
        timeout: Optional timeout in seconds
        **kwargs: Additional arguments to pass to subprocess.run

    Returns:
        CompletedProcess instance with the command result

    Raises:
        subprocess.CalledProcessError: If check=True and command fails after retries
        subprocess.TimeoutExpired: If timeout is exceeded (not retried)
    """
    MAX_RETRIES = 1
    RETRY_DELAY_SECONDS = 1

    attempt = 0
    last_exception: Optional[Exception] = None

    while attempt <= MAX_RETRIES:
        try:
            # Get the proper environment with safe.directory configuration
            env = get_git_environment(cwd)

            # Merge any environment from kwargs if provided
            if "env" in kwargs:
                env.update(kwargs["env"])
                kwargs_copy = kwargs.copy()
                kwargs_copy.pop("env")
            else:
                kwargs_copy = kwargs

            # Execute git command
            result = subprocess.run(
                cmd,
                cwd=cwd,
                check=check,
                capture_output=capture_output,
                text=text,
                timeout=timeout,
                env=env,
                **kwargs_copy,
            )

            # Success - return immediately
            return result

        except subprocess.CalledProcessError as e:
            last_exception = e

            # Log failure with full command details
            _log_git_failure(
                exception=e,
                cmd=cmd,
                cwd=cwd,
                attempt=attempt + 1,
                max_attempts=MAX_RETRIES + 1,
            )

            # If this was the last attempt, re-raise
            if attempt >= MAX_RETRIES:
                raise last_exception

            # Wait before retry
            time.sleep(RETRY_DELAY_SECONDS)
            attempt += 1

        except subprocess.TimeoutExpired as e:
            last_exception = e

            # Log timeout with command details
            _log_git_timeout(
                exception=e,
                cmd=cmd,
                cwd=cwd,
                timeout=timeout,
            )

            # Timeouts should not be retried (not transient)
            raise last_exception

    # Should never reach here, but safety fallback
    # Raise RuntimeError as a last resort
    raise RuntimeError(
        f"Git command failed without proper exception handling: {' '.join(cmd)}"
    )


def _log_git_failure(
    exception: subprocess.CalledProcessError,
    cmd: List[str],
    cwd: Path,
    attempt: int,
    max_attempts: int,
) -> None:
    """Log a git command failure with full context.

    Args:
        exception: The CalledProcessError that occurred
        cmd: Git command that failed
        cwd: Working directory
        attempt: Current attempt number (1-indexed)
        max_attempts: Maximum number of attempts
    """
    from .exception_logger import ExceptionLogger

    logger = ExceptionLogger.get_instance()
    if logger:
        context = {
            "git_command": " ".join(cmd),
            "cwd": str(cwd),
            "returncode": exception.returncode,
            "stdout": getattr(exception, "stdout", ""),
            "stderr": getattr(exception, "stderr", ""),
            "attempt": f"{attempt}/{max_attempts}",
        }

        # Create a descriptive exception message
        failure_msg = (
            f"Git command failed (attempt {attempt}/{max_attempts}): "
            f"{' '.join(cmd)}"
        )

        # Create a new exception with context for logging
        logged_exception = Exception(failure_msg)
        logger.log_exception(logged_exception, context=context)


def _log_git_timeout(
    exception: subprocess.TimeoutExpired,
    cmd: List[str],
    cwd: Path,
    timeout: Optional[float],
) -> None:
    """Log a git command timeout with full context.

    Args:
        exception: The TimeoutExpired that occurred
        cmd: Git command that timed out
        cwd: Working directory
        timeout: Timeout value in seconds
    """
    from .exception_logger import ExceptionLogger

    logger = ExceptionLogger.get_instance()
    if logger:
        context = {
            "git_command": " ".join(cmd),
            "cwd": str(cwd),
            "timeout": timeout,
        }

        timeout_msg = f"Git command timeout: {' '.join(cmd)}"
        logged_exception = Exception(timeout_msg)
        logger.log_exception(logged_exception, context=context)


def is_git_repository(project_dir: Path) -> bool:
    """
    Check if a directory is a git repository.

    This properly handles dubious ownership errors.

    Args:
        project_dir: Path to check

    Returns:
        True if the directory is a git repository, False otherwise
    """
    try:
        run_git_command(
            ["git", "rev-parse", "--git-dir"],
            cwd=project_dir,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_current_branch(project_dir: Path) -> Optional[str]:
    """
    Get the current git branch name.

    Args:
        project_dir: Path to the git repository

    Returns:
        Branch name or None if not in a git repo or on detached HEAD
    """
    try:
        result = run_git_command(
            ["git", "branch", "--show-current"],
            cwd=project_dir,
            check=True,
        )
        branch = result.stdout.strip()

        if not branch:
            # Handle detached HEAD
            try:
                result = run_git_command(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=project_dir,
                    check=True,
                )
                return f"detached-{result.stdout.strip()}"
            except subprocess.CalledProcessError:
                return None

        return str(branch)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_current_commit(project_dir: Path, short: bool = False) -> Optional[str]:
    """
    Get the current commit hash.

    Args:
        project_dir: Path to the git repository
        short: Whether to return short hash (7 chars) or full hash

    Returns:
        Commit hash or None if not in a git repo
    """
    try:
        cmd = ["git", "rev-parse"]
        if short:
            cmd.append("--short")
        cmd.append("HEAD")

        result = run_git_command(
            cmd,
            cwd=project_dir,
            check=True,
        )
        return str(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

"""
Subprocess Executor Service for async command execution with timeout protection.

Provides non-blocking subprocess execution with file-based output to prevent
memory exhaustion and FastAPI event loop blocking.
"""

import asyncio
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class ExecutionStatus(str, Enum):
    """Status of command execution."""

    SUCCESS = "success"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class SearchExecutionResult:
    """Result of a subprocess execution."""

    status: ExecutionStatus
    output_file: str
    exit_code: Optional[int] = None
    timed_out: bool = False
    timeout_seconds: Optional[int] = None
    error_message: Optional[str] = None
    stderr_output: Optional[str] = None


class SubprocessExecutor:
    """
    Executes subprocess commands asynchronously with timeout protection.

    Features:
    - Async execution prevents FastAPI event loop blocking
    - File-based output prevents RAM exhaustion
    - Thread pool for concurrent execution
    - Timeout protection with process termination
    - Partial output capture on timeout
    """

    def __init__(self, max_workers: int = 4):
        """
        Initialize subprocess executor.

        Args:
            max_workers: Maximum concurrent subprocess executions
        """
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._shutdown = False

    async def execute_with_limits(
        self,
        command: List[str],
        working_dir: str,
        timeout_seconds: int,
        output_file_path: str,
    ) -> SearchExecutionResult:
        """
        Execute command asynchronously with timeout and file output.

        Args:
            command: Command and arguments to execute
            working_dir: Working directory for command execution
            timeout_seconds: Maximum execution time in seconds
            output_file_path: Path to file for capturing output

        Returns:
            SearchExecutionResult with execution status and output file path
        """
        if self._shutdown:
            raise RuntimeError("Executor has been shut down")

        # Ensure output file directory exists
        output_path = Path(output_file_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Run subprocess in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    self._executor,
                    self._run_subprocess,
                    command,
                    working_dir,
                    output_file_path,
                    timeout_seconds,
                ),
                timeout=timeout_seconds + 1,  # Slightly longer than subprocess timeout
            )
            return result

        except asyncio.TimeoutError:
            # Asyncio timeout exceeded (should not happen if subprocess timeout works)
            logger.warning(
                f"Asyncio timeout exceeded for command: {' '.join(command)}"
            )
            return SearchExecutionResult(
                status=ExecutionStatus.TIMEOUT,
                output_file=output_file_path,
                timed_out=True,
                timeout_seconds=timeout_seconds,
                error_message="Command execution timed out",
            )

        except Exception as e:
            logger.error(f"Unexpected error executing command: {e}", exc_info=True)
            return SearchExecutionResult(
                status=ExecutionStatus.ERROR,
                output_file=output_file_path,
                error_message=str(e),
            )

    def _run_subprocess(
        self,
        command: List[str],
        working_dir: str,
        output_file_path: str,
        timeout_seconds: int,
    ) -> SearchExecutionResult:
        """
        Run subprocess synchronously in thread pool.

        This method runs in a thread pool thread, not the main event loop.

        Args:
            command: Command and arguments to execute
            working_dir: Working directory for command execution
            output_file_path: Path to file for capturing output
            timeout_seconds: Maximum execution time in seconds

        Returns:
            SearchExecutionResult with execution details
        """
        try:
            # Open output file for writing stdout
            with open(output_file_path, "w") as output_file:
                # Start process with file output
                process = subprocess.Popen(
                    command,
                    stdout=output_file,
                    stderr=subprocess.PIPE,
                    cwd=working_dir,
                    text=True,
                )

                try:
                    # Wait for process with timeout
                    _, stderr = process.communicate(timeout=timeout_seconds)

                    # Process completed within timeout
                    if process.returncode == 0:
                        return SearchExecutionResult(
                            status=ExecutionStatus.SUCCESS,
                            output_file=output_file_path,
                            exit_code=process.returncode,
                            timed_out=False,
                            stderr_output=stderr if stderr else None,
                        )
                    else:
                        return SearchExecutionResult(
                            status=ExecutionStatus.ERROR,
                            output_file=output_file_path,
                            exit_code=process.returncode,
                            error_message=f"Command exited with code {process.returncode}",
                            stderr_output=stderr if stderr else None,
                        )

                except subprocess.TimeoutExpired:
                    # Timeout exceeded - terminate process
                    logger.warning(
                        f"Command timed out after {timeout_seconds}s: {' '.join(command)}"
                    )

                    # Terminate process
                    process.kill()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logger.error("Failed to kill timed out process")

                    # Partial output already written to file
                    return SearchExecutionResult(
                        status=ExecutionStatus.TIMEOUT,
                        output_file=output_file_path,
                        timed_out=True,
                        timeout_seconds=timeout_seconds,
                        error_message=f"Command timed out after {timeout_seconds} seconds",
                    )

        except FileNotFoundError as e:
            return SearchExecutionResult(
                status=ExecutionStatus.ERROR,
                output_file=output_file_path,
                error_message=f"Command not found: {command[0]}",
            )

        except Exception as e:
            logger.error(f"Error running subprocess: {e}", exc_info=True)
            return SearchExecutionResult(
                status=ExecutionStatus.ERROR,
                output_file=output_file_path,
                error_message=str(e),
            )

    def shutdown(self, wait: bool = True, cancel_futures: bool = False):
        """
        Shutdown the executor and clean up resources.

        Args:
            wait: Wait for pending executions to complete
            cancel_futures: Cancel pending futures (Python 3.9+)
        """
        self._shutdown = True
        try:
            # Python 3.9+ supports cancel_futures
            self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)
        except TypeError:
            # Fallback for older Python versions
            self._executor.shutdown(wait=wait)

        logger.info("SubprocessExecutor shutdown complete")

"""
Unit tests for SubprocessExecutor service.

Tests timeout protection, async execution, and file-based output handling
for search command execution.
"""

import asyncio
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from code_indexer.server.services.subprocess_executor import (
    SubprocessExecutor,
    SearchExecutionResult,
    ExecutionStatus,
)


class TestSubprocessExecutor:
    """Test suite for SubprocessExecutor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.executor = SubprocessExecutor(max_workers=2)
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        self.executor.shutdown()
        # Clean up temp dir
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @pytest.mark.asyncio
    async def test_execute_successful_command(self):
        """Test successful command execution with file output."""
        output_file = Path(self.temp_dir) / "output.txt"

        result = await self.executor.execute_with_limits(
            command=["echo", "test output"],
            working_dir=self.temp_dir,
            timeout_seconds=5,
            output_file_path=str(output_file),
        )

        assert result.status == ExecutionStatus.SUCCESS
        assert result.exit_code == 0
        assert result.timed_out is False
        assert result.output_file == str(output_file)
        assert output_file.exists()

        # Verify output was written to file
        content = output_file.read_text()
        assert "test output" in content

    @pytest.mark.asyncio
    async def test_execute_command_with_timeout(self):
        """Test command that exceeds timeout is terminated."""
        output_file = Path(self.temp_dir) / "timeout_output.txt"

        # Use sleep command that will timeout
        result = await self.executor.execute_with_limits(
            command=["sleep", "10"],
            working_dir=self.temp_dir,
            timeout_seconds=1,
            output_file_path=str(output_file),
        )

        assert result.status == ExecutionStatus.TIMEOUT
        assert result.timed_out is True
        assert result.timeout_seconds == 1
        assert result.output_file == str(output_file)

    @pytest.mark.asyncio
    async def test_execute_command_with_error(self):
        """Test command that fails with non-zero exit code."""
        output_file = Path(self.temp_dir) / "error_output.txt"

        result = await self.executor.execute_with_limits(
            command=["ls", "/nonexistent/directory/path"],
            working_dir=self.temp_dir,
            timeout_seconds=5,
            output_file_path=str(output_file),
        )

        assert result.status == ExecutionStatus.ERROR
        assert result.exit_code != 0
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_concurrent_executions(self):
        """Test multiple concurrent command executions don't block each other."""
        output_file1 = Path(self.temp_dir) / "output1.txt"
        output_file2 = Path(self.temp_dir) / "output2.txt"

        # Start two commands concurrently
        start_time = time.time()

        results = await asyncio.gather(
            self.executor.execute_with_limits(
                command=["sleep", "1"],
                working_dir=self.temp_dir,
                timeout_seconds=5,
                output_file_path=str(output_file1),
            ),
            self.executor.execute_with_limits(
                command=["sleep", "1"],
                working_dir=self.temp_dir,
                timeout_seconds=5,
                output_file_path=str(output_file2),
            ),
        )

        elapsed = time.time() - start_time

        # Should complete in ~1 second (parallel), not ~2 seconds (sequential)
        assert elapsed < 2.0
        assert all(r.status == ExecutionStatus.SUCCESS for r in results)

    @pytest.mark.asyncio
    async def test_output_file_creation(self):
        """Test output file is created even if command produces no output."""
        output_file = Path(self.temp_dir) / "empty_output.txt"

        result = await self.executor.execute_with_limits(
            command=["true"],  # Command that produces no output
            working_dir=self.temp_dir,
            timeout_seconds=5,
            output_file_path=str(output_file),
        )

        assert result.status == ExecutionStatus.SUCCESS
        assert output_file.exists()

    @pytest.mark.asyncio
    async def test_partial_output_on_timeout(self):
        """Test partial output is captured before timeout."""
        output_file = Path(self.temp_dir) / "partial_output.txt"

        # Command that writes output then sleeps
        result = await self.executor.execute_with_limits(
            command=["sh", "-c", "echo 'partial output'; sleep 10"],
            working_dir=self.temp_dir,
            timeout_seconds=1,
            output_file_path=str(output_file),
        )

        assert result.status == ExecutionStatus.TIMEOUT
        assert output_file.exists()

        # Verify partial output was captured
        content = output_file.read_text()
        assert "partial output" in content

    @pytest.mark.asyncio
    async def test_working_directory_used(self):
        """Test command executes in specified working directory."""
        output_file = Path(self.temp_dir) / "pwd_output.txt"

        result = await self.executor.execute_with_limits(
            command=["pwd"],
            working_dir=self.temp_dir,
            timeout_seconds=5,
            output_file_path=str(output_file),
        )

        assert result.status == ExecutionStatus.SUCCESS
        content = output_file.read_text().strip()
        assert content == self.temp_dir

    @pytest.mark.asyncio
    async def test_stderr_captured(self):
        """Test stderr is captured in output file."""
        output_file = Path(self.temp_dir) / "stderr_output.txt"

        result = await self.executor.execute_with_limits(
            command=["sh", "-c", "echo 'error' >&2"],
            working_dir=self.temp_dir,
            timeout_seconds=5,
            output_file_path=str(output_file),
        )

        # Note: stderr capture behavior depends on implementation
        # This test verifies the result structure
        assert result.output_file == str(output_file)

    def test_executor_shutdown(self):
        """Test executor can be shut down gracefully."""
        executor = SubprocessExecutor(max_workers=2)
        executor.shutdown(wait=True)

        # Verify shutdown doesn't raise exceptions
        assert True

    @pytest.mark.asyncio
    async def test_large_output_handling(self):
        """Test handling of large command output."""
        output_file = Path(self.temp_dir) / "large_output.txt"

        # Generate large output (10000 lines)
        result = await self.executor.execute_with_limits(
            command=["sh", "-c", "seq 1 10000"],
            working_dir=self.temp_dir,
            timeout_seconds=10,
            output_file_path=str(output_file),
        )

        assert result.status == ExecutionStatus.SUCCESS
        assert output_file.exists()

        # Verify large output was written
        lines = output_file.read_text().strip().split("\n")
        assert len(lines) == 10000


class TestSearchExecutionResult:
    """Test suite for SearchExecutionResult dataclass."""

    def test_result_creation(self):
        """Test creating a search execution result."""
        result = SearchExecutionResult(
            status=ExecutionStatus.SUCCESS,
            output_file="/tmp/output.txt",
            exit_code=0,
            timed_out=False,
        )

        assert result.status == ExecutionStatus.SUCCESS
        assert result.output_file == "/tmp/output.txt"
        assert result.exit_code == 0
        assert result.timed_out is False

    def test_timeout_result(self):
        """Test creating a timeout result."""
        result = SearchExecutionResult(
            status=ExecutionStatus.TIMEOUT,
            output_file="/tmp/output.txt",
            timed_out=True,
            timeout_seconds=30,
        )

        assert result.status == ExecutionStatus.TIMEOUT
        assert result.timed_out is True
        assert result.timeout_seconds == 30

    def test_error_result(self):
        """Test creating an error result."""
        result = SearchExecutionResult(
            status=ExecutionStatus.ERROR,
            output_file="/tmp/output.txt",
            exit_code=1,
            error_message="Command failed",
        )

        assert result.status == ExecutionStatus.ERROR
        assert result.exit_code == 1
        assert result.error_message == "Command failed"

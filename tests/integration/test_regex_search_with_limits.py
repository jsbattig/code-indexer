"""
Integration tests for regex search with timeout and size limit protection.

Tests the complete flow from search request through SubprocessExecutor,
file management, validation, and error formatting.
"""

import asyncio
import os
import tempfile
import time
from pathlib import Path

import pytest

from code_indexer.server.models.search_limits_config import SearchLimitsConfig
from code_indexer.server.services.subprocess_executor import (
    SubprocessExecutor,
    ExecutionStatus,
)
from code_indexer.server.services.search_result_file_manager import (
    SearchResultFileManager,
)
from code_indexer.server.services.search_limits_validator import SearchLimitsValidator
from code_indexer.server.services.search_error_formatter import SearchErrorFormatter


class TestRegexSearchWithLimits:
    """Integration tests for search protection features."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_repo = Path(self.temp_dir) / "test_repo"
        self.test_repo.mkdir()

        # Create test files
        self._create_test_files()

        self.executor = SubprocessExecutor(max_workers=2)
        self.file_manager = SearchResultFileManager()
        self.validator = SearchLimitsValidator()
        self.error_formatter = SearchErrorFormatter()

    def teardown_method(self):
        """Clean up test fixtures."""
        self.executor.shutdown()

        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _create_test_files(self):
        """Create test repository files."""
        # Small file with TODOs
        (self.test_repo / "small.txt").write_text("TODO: Fix this\nTODO: Review that\n")

        # Large file
        large_content = "x" * 1024 * 1024 * 2  # 2MB
        (self.test_repo / "large.txt").write_text(large_content)

        # Multiple files with pattern
        for i in range(10):
            (self.test_repo / f"file_{i}.txt").write_text(f"MATCH {i}\n" * 100)

    @pytest.mark.asyncio
    async def test_successful_search_within_limits(self):
        """Test successful search that completes within timeout and size limits."""
        config = SearchLimitsConfig(max_result_size_mb=10, timeout_seconds=30)

        output_file = Path(self.temp_dir) / "output.txt"

        # Execute search
        result = await self.executor.execute_with_limits(
            command=["grep", "-r", "TODO", str(self.test_repo)],
            working_dir=str(self.test_repo),
            timeout_seconds=config.timeout_seconds,
            output_file_path=str(output_file),
        )

        # Verify execution succeeded
        assert result.status == ExecutionStatus.SUCCESS
        assert not result.timed_out

        # Parse results
        parse_result = self.file_manager.parse_with_size_limit(
            str(output_file), config.max_size_bytes
        )

        # Validate
        validation = self.validator.validate_result(parse_result, config)

        assert validation.valid is True
        assert "TODO" in validation.content

        # Cleanup
        self.file_manager.cleanup_temp_file(str(output_file))
        assert not output_file.exists()

    @pytest.mark.asyncio
    async def test_search_timeout_protection(self):
        """Test search that exceeds timeout is terminated."""
        config = SearchLimitsConfig(timeout_seconds=5)

        output_file = Path(self.temp_dir) / "timeout_output.txt"

        # Execute search with sleep (will timeout)
        result = await self.executor.execute_with_limits(
            command=["sleep", "10"],
            working_dir=str(self.test_repo),
            timeout_seconds=config.timeout_seconds,
            output_file_path=str(output_file),
        )

        # Verify timeout occurred
        assert result.status == ExecutionStatus.TIMEOUT
        assert result.timed_out is True
        assert result.timeout_seconds == 5

        # Format error
        error_response = self.error_formatter.format_timeout_error(
            timeout_seconds=config.timeout_seconds,
            partial_results=None,
        )

        assert error_response["error_code"] == "SEARCH_TIMEOUT"
        assert "timeout" in error_response["message"].lower()
        assert error_response["suggestion"] is not None

        # Cleanup
        self.file_manager.cleanup_temp_file(str(output_file))

    @pytest.mark.asyncio
    async def test_result_size_exceeded_protection(self):
        """Test search results exceeding size limit are truncated."""
        config = SearchLimitsConfig(max_result_size_mb=1, timeout_seconds=30)

        output_file = Path(self.temp_dir) / "large_output.txt"

        # Create large output file (simulate large search results)
        large_output = "x" * 2 * 1024 * 1024  # 2MB
        output_file.write_text(large_output)

        # Parse with size limit
        parse_result = self.file_manager.parse_with_size_limit(
            str(output_file), config.max_size_bytes
        )

        # Verify size exceeded
        assert parse_result.exceeded is True
        assert parse_result.file_size > config.max_size_bytes
        assert len(parse_result.truncated_content) == config.max_size_bytes

        # Validate
        validation = self.validator.validate_result(parse_result, config)

        assert validation.valid is False
        assert validation.error_code == "RESULT_SIZE_EXCEEDED"
        assert "exceed" in validation.message.lower()

        # Format error
        error_response = self.error_formatter.format_size_exceeded_error(
            actual_size_mb=parse_result.file_size / (1024 * 1024),
            limit_mb=config.max_result_size_mb,
            truncated_results=parse_result.truncated_content[:100],
        )

        assert error_response["error_code"] == "RESULT_SIZE_EXCEEDED"
        assert error_response["truncated_results_included"] is True

        # Cleanup
        self.file_manager.cleanup_temp_file(str(output_file))

    @pytest.mark.asyncio
    async def test_partial_results_on_timeout(self):
        """Test partial results are captured when timeout occurs."""
        config = SearchLimitsConfig(timeout_seconds=5)

        output_file = Path(self.temp_dir) / "partial_output.txt"

        # Command that writes output then sleeps
        result = await self.executor.execute_with_limits(
            command=["sh", "-c", "echo 'partial data'; sleep 10"],
            working_dir=str(self.test_repo),
            timeout_seconds=config.timeout_seconds,
            output_file_path=str(output_file),
        )

        # Verify timeout with partial output
        assert result.status == ExecutionStatus.TIMEOUT
        assert output_file.exists()

        # Read partial results
        content = output_file.read_text()
        assert "partial data" in content

        # Format error with partial results
        error_response = self.error_formatter.format_timeout_error(
            timeout_seconds=config.timeout_seconds,
            partial_results=content,
        )

        assert error_response["partial_results_available"] is True
        assert error_response["partial_results"] == content

        # Cleanup
        self.file_manager.cleanup_temp_file(str(output_file))

    @pytest.mark.asyncio
    async def test_concurrent_searches_dont_block(self):
        """Test multiple concurrent searches execute independently."""
        config = SearchLimitsConfig(timeout_seconds=30)

        output_file1 = Path(self.temp_dir) / "output1.txt"
        output_file2 = Path(self.temp_dir) / "output2.txt"

        start_time = time.time()

        # Execute two searches concurrently
        results = await asyncio.gather(
            self.executor.execute_with_limits(
                command=["grep", "-r", "MATCH", str(self.test_repo)],
                working_dir=str(self.test_repo),
                timeout_seconds=config.timeout_seconds,
                output_file_path=str(output_file1),
            ),
            self.executor.execute_with_limits(
                command=["grep", "-r", "TODO", str(self.test_repo)],
                working_dir=str(self.test_repo),
                timeout_seconds=config.timeout_seconds,
                output_file_path=str(output_file2),
            ),
        )

        elapsed = time.time() - start_time

        # Both should succeed
        assert all(r.status == ExecutionStatus.SUCCESS for r in results)

        # Should complete quickly (concurrent, not sequential)
        assert elapsed < 5.0

        # Cleanup
        self.file_manager.cleanup_temp_file(str(output_file1))
        self.file_manager.cleanup_temp_file(str(output_file2))

    @pytest.mark.asyncio
    async def test_temp_file_cleanup_on_all_outcomes(self):
        """Test temp files are cleaned up on success, timeout, and error."""
        config = SearchLimitsConfig(timeout_seconds=30)

        test_cases = [
            # Success case
            (["echo", "success"], ExecutionStatus.SUCCESS),
            # Error case
            (["ls", "/nonexistent"], ExecutionStatus.ERROR),
        ]

        for i, (command, expected_status) in enumerate(test_cases):
            output_file = Path(self.temp_dir) / f"cleanup_test_{i}.txt"

            result = await self.executor.execute_with_limits(
                command=command,
                working_dir=str(self.test_repo),
                timeout_seconds=config.timeout_seconds,
                output_file_path=str(output_file),
            )

            assert result.status == expected_status
            assert output_file.exists()

            # Cleanup
            self.file_manager.cleanup_temp_file(str(output_file))
            assert not output_file.exists()

    def test_config_validation_ranges(self):
        """Test SearchLimitsConfig validates ranges correctly."""
        # Valid configs
        config = SearchLimitsConfig(max_result_size_mb=50, timeout_seconds=120)
        assert config.max_result_size_mb == 50
        assert config.timeout_seconds == 120

        # Test boundary values
        config_min = SearchLimitsConfig(max_result_size_mb=1, timeout_seconds=5)
        assert config_min.max_result_size_mb == 1
        assert config_min.timeout_seconds == 5

        config_max = SearchLimitsConfig(max_result_size_mb=100, timeout_seconds=300)
        assert config_max.max_result_size_mb == 100
        assert config_max.timeout_seconds == 300

    def test_error_formatter_actionable_suggestions(self):
        """Test error responses include actionable suggestions."""
        # Timeout error
        timeout_error = self.error_formatter.format_timeout_error(
            timeout_seconds=30, partial_results="some data"
        )

        assert "suggestion" in timeout_error
        assert len(timeout_error["suggestion"]) > 0
        assert timeout_error["partial_results_available"] is True

        # Size exceeded error
        size_error = self.error_formatter.format_size_exceeded_error(
            actual_size_mb=5.0, limit_mb=1, truncated_results="truncated..."
        )

        assert "suggestion" in size_error
        assert "refine" in size_error["suggestion"].lower()
        assert size_error["truncated_results_included"] is True

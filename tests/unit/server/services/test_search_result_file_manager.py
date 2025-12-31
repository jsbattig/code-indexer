"""
Unit tests for SearchResultFileManager service.

Tests temp file management, size checking, and truncation behavior
for search result handling.
"""

import os
import tempfile
from pathlib import Path

import pytest

from code_indexer.server.services.search_result_file_manager import (
    SearchResultFileManager,
    ParseResult,
    SizeCheckResult,
)


class TestSearchResultFileManager:
    """Test suite for SearchResultFileManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = SearchResultFileManager()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        # Clean up temp dir
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_parse_within_size_limit(self):
        """Test parsing file within size limit returns full content."""
        # Create test file with small content
        test_file = Path(self.temp_dir) / "small.txt"
        content = "Small test content\n"
        test_file.write_text(content)

        # Parse with 1MB limit (way above file size)
        result = self.manager.parse_with_size_limit(
            str(test_file), max_size_bytes=1024 * 1024
        )

        assert result.exceeded is False
        assert result.content == content
        assert result.file_size == len(content.encode("utf-8"))
        assert result.limit == 1024 * 1024

    def test_parse_exceeds_size_limit(self):
        """Test parsing file exceeding size limit returns truncated content."""
        # Create test file with content larger than limit
        test_file = Path(self.temp_dir) / "large.txt"
        content = "x" * 10000  # 10KB of content
        test_file.write_text(content)

        # Parse with 1KB limit
        result = self.manager.parse_with_size_limit(str(test_file), max_size_bytes=1024)

        assert result.exceeded is True
        assert result.file_size == 10000
        assert result.limit == 1024
        assert len(result.truncated_content) == 1024
        assert result.truncated_content == content[:1024]

    def test_parse_nonexistent_file(self):
        """Test parsing nonexistent file raises appropriate error."""
        with pytest.raises(FileNotFoundError):
            self.manager.parse_with_size_limit(
                "/nonexistent/file.txt", max_size_bytes=1024
            )

    def test_check_size_within_limit(self):
        """Test size check for file within limit."""
        test_file = Path(self.temp_dir) / "size_test.txt"
        test_file.write_text("Small content")

        result = self.manager.check_size(str(test_file), max_size_bytes=1024 * 1024)

        assert result.exceeded is False
        assert result.file_size > 0
        assert result.limit == 1024 * 1024

    def test_check_size_exceeds_limit(self):
        """Test size check for file exceeding limit."""
        test_file = Path(self.temp_dir) / "size_test.txt"
        test_file.write_text("x" * 10000)

        result = self.manager.check_size(str(test_file), max_size_bytes=1024)

        assert result.exceeded is True
        assert result.file_size == 10000
        assert result.limit == 1024

    def test_cleanup_temp_file(self):
        """Test temp file cleanup removes file."""
        test_file = Path(self.temp_dir) / "cleanup_test.txt"
        test_file.write_text("temporary content")

        assert test_file.exists()

        self.manager.cleanup_temp_file(str(test_file))

        assert not test_file.exists()

    def test_cleanup_nonexistent_file(self):
        """Test cleanup of nonexistent file doesn't raise error."""
        # Should not raise exception
        self.manager.cleanup_temp_file("/nonexistent/file.txt")

    def test_cleanup_multiple_files(self):
        """Test cleanup of multiple files."""
        files = []
        for i in range(5):
            test_file = Path(self.temp_dir) / f"cleanup_{i}.txt"
            test_file.write_text(f"content {i}")
            files.append(str(test_file))

        # Verify all exist
        assert all(Path(f).exists() for f in files)

        # Cleanup all
        for file_path in files:
            self.manager.cleanup_temp_file(file_path)

        # Verify all removed
        assert not any(Path(f).exists() for f in files)

    def test_read_limited_content(self):
        """Test reading first N bytes of file."""
        test_file = Path(self.temp_dir) / "limited.txt"
        content = "0123456789" * 100  # 1000 bytes
        test_file.write_text(content)

        limited_content = self.manager.read_limited_content(
            str(test_file), max_bytes=50
        )

        assert len(limited_content) == 50
        assert limited_content == content[:50]

    def test_read_limited_content_file_smaller_than_limit(self):
        """Test reading limited content when file is smaller than limit."""
        test_file = Path(self.temp_dir) / "small.txt"
        content = "small content"
        test_file.write_text(content)

        limited_content = self.manager.read_limited_content(
            str(test_file), max_bytes=1024
        )

        assert limited_content == content

    def test_get_file_size(self):
        """Test getting file size."""
        test_file = Path(self.temp_dir) / "size.txt"
        content = "x" * 1234
        test_file.write_text(content)

        size = self.manager.get_file_size(str(test_file))

        assert size == 1234

    def test_parse_empty_file(self):
        """Test parsing empty file."""
        test_file = Path(self.temp_dir) / "empty.txt"
        test_file.write_text("")

        result = self.manager.parse_with_size_limit(str(test_file), max_size_bytes=1024)

        assert result.exceeded is False
        assert result.content == ""
        assert result.file_size == 0


class TestParseResult:
    """Test suite for ParseResult dataclass."""

    def test_parse_result_creation(self):
        """Test creating a parse result."""
        result = ParseResult(
            exceeded=False,
            file_size=100,
            limit=1024,
            content="test content",
        )

        assert result.exceeded is False
        assert result.file_size == 100
        assert result.limit == 1024
        assert result.content == "test content"
        assert result.truncated_content is None

    def test_parse_result_truncated(self):
        """Test creating a truncated parse result."""
        result = ParseResult(
            exceeded=True,
            file_size=10000,
            limit=1024,
            truncated_content="truncated...",
        )

        assert result.exceeded is True
        assert result.file_size == 10000
        assert result.limit == 1024
        assert result.truncated_content == "truncated..."
        assert result.content is None


class TestSizeCheckResult:
    """Test suite for SizeCheckResult dataclass."""

    def test_size_check_result_creation(self):
        """Test creating a size check result."""
        result = SizeCheckResult(exceeded=False, file_size=500, limit=1024)

        assert result.exceeded is False
        assert result.file_size == 500
        assert result.limit == 1024

    def test_size_check_result_exceeded(self):
        """Test creating an exceeded size check result."""
        result = SizeCheckResult(exceeded=True, file_size=2048, limit=1024)

        assert result.exceeded is True
        assert result.file_size == 2048
        assert result.limit == 1024

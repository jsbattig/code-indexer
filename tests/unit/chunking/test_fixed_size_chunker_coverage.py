"""Additional tests to achieve >95% coverage for FixedSizeChunker.

These tests cover edge cases and error conditions that aren't covered
by the main test suite.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch
from src.code_indexer.indexing.fixed_size_chunker import FixedSizeChunker
from src.code_indexer.config import IndexingConfig


class TestFixedSizeChunkerCoverage:
    """Tests to achieve comprehensive coverage of FixedSizeChunker."""

    @pytest.fixture
    def chunker(self):
        """Create a FixedSizeChunker with standard configuration."""
        config = IndexingConfig()
        return FixedSizeChunker(config)

    def test_line_calculation_with_empty_text(self, chunker):
        """Test line number calculation with empty text."""
        # This covers line 53-54: if not text or start_pos >= len(text)
        line_start, line_end = chunker._calculate_line_numbers("", 0, 0)
        assert line_start == 1
        assert line_end == 1

        line_start, line_end = chunker._calculate_line_numbers("", 10, 20)
        assert line_start == 1
        assert line_end == 1

    def test_line_calculation_with_start_pos_beyond_text(self, chunker):
        """Test line number calculation when start position is beyond text length."""
        # This covers line 53-54: if not text or start_pos >= len(text)
        text = "hello world"
        line_start, line_end = chunker._calculate_line_numbers(text, 100, 110)
        assert line_start == 1
        assert line_end == 1

    def test_chunk_file_with_encoding_errors(self, chunker):
        """Test chunk_file with various encoding scenarios."""
        # Create a temporary file with problematic encoding
        temp_file = tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".txt")

        # Write some bytes that might cause encoding issues
        problematic_bytes = (
            b"\xff\xfe\x00\x00Hello World\x00\x00"  # UTF-32 BOM + content
        )
        temp_file.write(problematic_bytes)
        temp_file.close()
        temp_path = Path(temp_file.name)

        try:
            # This should eventually succeed with one of the fallback encodings
            # covering lines 153-159 (encoding fallback loop)
            chunks = chunker.chunk_file(temp_path)
            assert len(chunks) >= 1

        finally:
            temp_path.unlink()

    def test_chunk_file_with_complete_encoding_failure(self, chunker):
        """Test chunk_file when all encodings fail."""
        # Since latin-1 can decode any byte sequence, we need to mock
        # the encoding attempts to all fail
        temp_file = tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".txt")
        temp_file.write(b"some content")
        temp_file.close()
        temp_path = Path(temp_file.name)

        try:
            # Mock all encodings to fail
            with patch("builtins.open") as mock_open_func:
                mock_open_func.side_effect = UnicodeDecodeError(
                    "utf-8", b"", 0, 1, "invalid"
                )

                # This should raise ValueError covering lines 161-162
                with pytest.raises(ValueError, match="Could not decode file"):
                    chunker.chunk_file(temp_path)

        finally:
            temp_path.unlink()

    def test_chunk_file_with_permission_error(self, chunker):
        """Test chunk_file when file cannot be opened due to permissions."""
        # Create a file that exists but simulate permission error
        temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
        temp_file.write("test content")
        temp_file.close()
        temp_path = Path(temp_file.name)

        try:
            # Mock open to raise PermissionError
            with patch(
                "builtins.open", side_effect=PermissionError("Permission denied")
            ):
                # This should raise ValueError covering lines 166-167
                with pytest.raises(ValueError, match="Failed to process file"):
                    chunker.chunk_file(temp_path)

        finally:
            temp_path.unlink()

    def test_chunk_file_with_general_exception(self, chunker):
        """Test chunk_file with a general exception during processing."""
        temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
        temp_file.write("test content")
        temp_file.close()
        temp_path = Path(temp_file.name)

        try:
            # Mock open to raise a general exception
            with patch("builtins.open", side_effect=OSError("General I/O error")):
                # This should raise ValueError covering lines 166-167
                with pytest.raises(ValueError, match="Failed to process file"):
                    chunker.chunk_file(temp_path)

        finally:
            temp_path.unlink()

    def test_estimate_chunks_with_empty_text(self, chunker):
        """Test estimate_chunks with empty text."""
        # This covers line 178-179: if not text
        result = chunker.estimate_chunks("")
        assert result == 0

        result = chunker.estimate_chunks(None)
        assert result == 0

    def test_estimate_chunks_with_small_text(self, chunker):
        """Test estimate_chunks with text smaller than chunk size."""
        # This covers lines 184-185: if len(text) <= self.CHUNK_SIZE
        small_text = "a" * 500  # Less than 1000
        result = chunker.estimate_chunks(small_text)
        assert result == 1

        exact_size_text = "a" * 1000  # Exactly 1000
        result = chunker.estimate_chunks(exact_size_text)
        assert result == 1

    def test_estimate_chunks_with_large_text(self, chunker):
        """Test estimate_chunks with text larger than chunk size."""
        # This covers lines 187-191: arithmetic estimation
        large_text = "a" * 2500  # Should result in 3 chunks
        result = chunker.estimate_chunks(large_text)

        # Manual calculation:
        # First chunk: 1000 chars
        # Remaining: 2500 - 1000 = 1500 chars
        # Additional chunks: ceil(1500 / 850) = 2
        # Total: 1 + 2 = 3
        assert result == 3

        # Test with a size that requires ceiling division
        text_size = 1000 + 850 + 1  # 1851 characters
        medium_text = "a" * text_size
        result = chunker.estimate_chunks(medium_text)

        # Manual calculation:
        # First chunk: 1000 chars
        # Remaining: 1851 - 1000 = 851 chars
        # Additional chunks: ceil(851 / 850) = ceil(1.001...) = 2
        # Total: 1 + 2 = 3
        assert result == 3

    def test_estimate_chunks_accuracy(self, chunker):
        """Test that estimate_chunks is accurate compared to actual chunking."""
        test_sizes = [500, 1000, 1500, 2000, 3000, 5000]

        for size in test_sizes:
            text = "x" * size
            estimated = chunker.estimate_chunks(text)
            actual_chunks = chunker.chunk_text(text)
            actual_count = len(actual_chunks)

            assert estimated == actual_count, (
                f"Estimation inaccurate for size {size}: "
                f"estimated {estimated}, actual {actual_count}"
            )

    def test_chunk_text_with_none_file_path(self, chunker):
        """Test chunk_text with None file_path to ensure default values."""
        text = "a" * 1500
        chunks = chunker.chunk_text(text, file_path=None)

        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk["file_path"] is None
            assert chunk["file_extension"] == ""

    def test_chunk_file_with_different_encodings(self, chunker):
        """Test chunk_file successfully handles different encodings."""
        # Test UTF-8 with BOM
        temp_file = tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".txt")
        utf8_bom_content = "\ufeffHello World UTF-8 BOM".encode("utf-8-sig")
        temp_file.write(utf8_bom_content)
        temp_file.close()
        temp_path = Path(temp_file.name)

        try:
            chunks = chunker.chunk_file(temp_path)
            assert len(chunks) >= 1
            # The BOM should be handled correctly
            assert "Hello World" in chunks[0]["text"]

        finally:
            temp_path.unlink()

        # Test Latin-1 encoding
        temp_file = tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".txt")
        latin1_content = "Héllo Wörld Latin-1 éncoding".encode("latin-1")
        temp_file.write(latin1_content)
        temp_file.close()
        temp_path = Path(temp_file.name)

        try:
            chunks = chunker.chunk_file(temp_path)
            assert len(chunks) >= 1
            assert "Hello" in chunks[0]["text"] or "Héllo" in chunks[0]["text"]

        finally:
            temp_path.unlink()

    def test_edge_case_single_character_file(self, chunker):
        """Test chunking a file with just one character."""
        temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
        temp_file.write("x")
        temp_file.close()
        temp_path = Path(temp_file.name)

        try:
            chunks = chunker.chunk_file(temp_path)
            assert len(chunks) == 1
            assert len(chunks[0]["text"]) == 1
            assert chunks[0]["text"] == "x"
            assert chunks[0]["chunk_index"] == 0
            assert chunks[0]["total_chunks"] == 1

        finally:
            temp_path.unlink()

    def test_chunk_text_whitespace_only(self, chunker):
        """Test chunking text that contains only whitespace."""
        whitespace_text = "   \n\t  \n   "
        chunks = chunker.chunk_text(whitespace_text)

        # The chunker returns empty list for whitespace-only content after strip()
        # This is expected behavior based on the implementation
        assert len(chunks) == 0

    def test_line_calculation_edge_cases(self, chunker):
        """Test line number calculation with various edge cases."""
        # Text with multiple newlines at start
        text = "\n\n\nhello\nworld\n"
        line_start, line_end = chunker._calculate_line_numbers(text, 0, 5)
        assert line_start == 1
        assert line_end > line_start

        # End position beyond text length
        line_start, line_end = chunker._calculate_line_numbers(text, 2, 1000)
        expected_end = text.count("\n") + 1
        assert line_end == expected_end

        # Start and end at same position
        line_start, line_end = chunker._calculate_line_numbers(text, 5, 5)
        assert line_start == line_end

"""Tests for FixedSizeChunker - ultra-simple fixed-size chunking algorithm."""

import pytest
from pathlib import Path
from src.code_indexer.indexing.fixed_size_chunker import FixedSizeChunker
from src.code_indexer.config import IndexingConfig


class TestFixedSizeChunker:
    """Test suite for FixedSizeChunker implementation."""

    @pytest.fixture
    def chunker(self):
        """Create a FixedSizeChunker with standard configuration."""
        config = IndexingConfig()
        return FixedSizeChunker(config)

    def test_fixed_chunk_size_exactly_1000_characters(self, chunker):
        """Test that all chunks (except last) are exactly 1000 characters."""
        # Create text longer than 2000 characters to ensure multiple chunks
        text = "a" * 2500  # 2500 characters
        file_path = Path("test.py")

        chunks = chunker.chunk_text(text, file_path)

        # Should have 3 chunks with this math:
        # Chunk 1: chars 0-999 (1000 chars)
        # Chunk 2: chars 850-1849 (1000 chars)
        # Chunk 3: chars 1700-2499 (800 chars)
        assert len(chunks) == 3

        # First two chunks should be exactly 1000 characters
        assert (
            len(chunks[0]["text"]) == 1000
        ), f"First chunk has {len(chunks[0]['text'])} chars, expected 1000"
        assert (
            len(chunks[1]["text"]) == 1000
        ), f"Second chunk has {len(chunks[1]['text'])} chars, expected 1000"

        # Last chunk should be remainder (2500 - 1700 = 800 characters)
        assert (
            len(chunks[2]["text"]) == 800
        ), f"Last chunk has {len(chunks[2]['text'])} chars, expected 800"

    def test_fixed_overlap_exactly_150_characters(self, chunker):
        """Test that there's exactly 150 characters overlap between adjacent chunks."""
        # Create text with identifiable patterns
        text = ""
        for i in range(300):  # 300 * 10 = 3000 characters
            text += f"{i:04d}12345"  # Each segment is 9 characters, padded to 10

        file_path = Path("test.py")
        chunks = chunker.chunk_text(text, file_path)

        # Should have multiple chunks
        assert len(chunks) >= 3

        # Check overlap between first two chunks
        first_chunk = chunks[0]["text"]
        second_chunk = chunks[1]["text"]

        # Last 150 characters of first chunk should match first 150 characters of second chunk
        first_chunk_ending = first_chunk[-150:]
        second_chunk_beginning = second_chunk[:150]

        assert (
            first_chunk_ending == second_chunk_beginning
        ), "Overlap between chunks is not exactly 150 characters"

    def test_chunk_positioning_math_next_start_calculation(self, chunker):
        """Test that chunk positioning follows the pattern: next_start = current_start + 850."""
        text = "x" * 5000  # 5000 characters to get multiple chunks
        file_path = Path("test.py")

        chunks = chunker.chunk_text(text, file_path)

        # Should have multiple chunks
        assert len(chunks) >= 5

        # Verify the mathematical progression
        # Chunk 1: chars 0-999 (1000 chars)
        # Chunk 2: chars 850-1849 (1000 chars, starts 850 chars from start)
        # Chunk 3: chars 1700-2699 (1000 chars, starts 850 chars from chunk 2 start)

        # We can't directly access start positions from chunks, but we can verify
        # the overlap pattern matches the expected 850-character step
        for i in range(len(chunks) - 1):
            current_chunk = chunks[i]["text"]
            next_chunk = chunks[i + 1]["text"]

            # The next chunk should start 850 characters into the current chunk
            # So the last 150 chars of current should match first 150 of next
            expected_overlap = current_chunk[-150:]
            actual_overlap = next_chunk[:150]

            assert (
                expected_overlap == actual_overlap
            ), f"Chunk {i} to {i+1} overlap doesn't match expected 850-character step pattern"

    def test_last_chunk_handling_remainder_text(self, chunker):
        """Test that the last chunk handles remainder text correctly."""
        # Test various remainder sizes
        test_cases = [
            2050,  # Remainder of 50 characters
            2200,  # Remainder of 200 characters
            2999,  # Remainder of 999 characters (almost full chunk)
            3001,  # Remainder of 1 character (tiny remainder)
        ]

        for total_size in test_cases:
            text = "z" * total_size
            file_path = Path("test.py")

            chunks = chunker.chunk_text(text, file_path)

            # Calculate expected chunks: (total_size - 1000) / 850 + 1
            # First chunk: 1000 chars
            # Remaining: total_size - 1000
            # Each additional full chunk covers 850 new chars (1000 - 150 overlap)
            remaining_after_first = total_size - 1000
            if remaining_after_first <= 0:
                expected_chunks = 1
                expected_last_size = total_size
            else:
                full_additional_chunks = remaining_after_first // 850
                final_remainder = remaining_after_first % 850
                if final_remainder > 0:
                    expected_chunks = 1 + full_additional_chunks + 1
                    expected_last_size = (
                        150 + final_remainder
                    )  # 150 overlap + remainder
                else:
                    expected_chunks = 1 + full_additional_chunks
                    expected_last_size = 1000  # Full chunk

            assert (
                len(chunks) == expected_chunks
            ), f"For {total_size} chars: expected {expected_chunks} chunks, got {len(chunks)}"

            # Last chunk size should match calculation
            actual_last_size = len(chunks[-1]["text"])
            assert (
                actual_last_size == expected_last_size
            ), f"For {total_size} chars: expected last chunk {expected_last_size}, got {actual_last_size}"

    def test_edge_case_empty_file(self, chunker):
        """Test handling of empty files."""
        text = ""
        file_path = Path("test.py")

        chunks = chunker.chunk_text(text, file_path)

        assert chunks == [], "Empty file should produce no chunks"

    def test_edge_case_very_small_file(self, chunker):
        """Test handling of files smaller than chunk size."""
        small_sizes = [1, 50, 100, 500, 999]

        for size in small_sizes:
            text = "a" * size
            file_path = Path("test.py")

            chunks = chunker.chunk_text(text, file_path)

            assert (
                len(chunks) == 1
            ), f"File with {size} chars should produce exactly 1 chunk"
            assert (
                len(chunks[0]["text"]) == size
            ), f"Single chunk should have {size} chars"

    def test_edge_case_very_large_file(self, chunker):
        """Test handling of very large files."""
        # Test with 1MB worth of characters (reduced from 10MB to prevent test timeouts)
        large_size = 1_000_000  # Still large enough to test edge cases
        text = "x" * large_size
        file_path = Path("test.py")

        chunks = chunker.chunk_text(text, file_path)

        # All chunks except last should be exactly 1000 characters
        for i, chunk in enumerate(chunks[:-1]):
            assert (
                len(chunk["text"]) == 1000
            ), f"Chunk {i} in large file should be exactly 1000 chars, got {len(chunk['text'])}"

        # Verify total character coverage (accounting for overlaps)
        expected_chunks = 1 + ((large_size - 1000) + 849) // 850  # Ceiling division
        assert (
            len(chunks) == expected_chunks
        ), f"Large file should produce {expected_chunks} chunks, got {len(chunks)}"

    def test_line_number_calculation_accuracy(self, chunker):
        """Test that line numbers are calculated correctly."""
        # Create text with known line structure
        lines = []
        for i in range(200):  # 200 lines
            lines.append(
                f"Line {i:03d}: This is line number {i} with some content to make it longer"
            )

        text = "\n".join(lines)
        file_path = Path("test.py")

        chunks = chunker.chunk_text(text, file_path)

        # Verify each chunk has valid line start/end
        for i, chunk in enumerate(chunks):
            assert "line_start" in chunk, f"Chunk {i} missing line_start"
            assert "line_end" in chunk, f"Chunk {i} missing line_end"
            assert isinstance(
                chunk["line_start"], int
            ), f"Chunk {i} line_start not integer"
            assert isinstance(chunk["line_end"], int), f"Chunk {i} line_end not integer"
            assert chunk["line_start"] > 0, f"Chunk {i} line_start should be 1-based"
            assert (
                chunk["line_end"] >= chunk["line_start"]
            ), f"Chunk {i} line_end should be >= line_start"

        # Verify line numbers are sequential (accounting for overlap)
        for i in range(len(chunks) - 1):
            current_end = chunks[i]["line_end"]
            next_start = chunks[i + 1]["line_start"]

            # Due to character-based cutting, line numbers may overlap or have gaps
            # but they should be in reasonable proximity
            assert (
                abs(current_end - next_start) <= 10
            ), f"Line numbers between chunks {i} and {i+1} too far apart: {current_end} to {next_start}"

    def test_chunk_metadata_completeness(self, chunker):
        """Test that chunk metadata includes all required fields."""
        text = "a" * 1500
        file_path = Path("test/example.py")

        chunks = chunker.chunk_text(text, file_path)

        required_fields = [
            "text",
            "chunk_index",
            "total_chunks",
            "size",
            "file_path",
            "file_extension",
            "line_start",
            "line_end",
        ]

        for i, chunk in enumerate(chunks):
            for field in required_fields:
                assert field in chunk, f"Chunk {i} missing required field: {field}"

            # Verify field types and values
            assert isinstance(chunk["text"], str), f"Chunk {i} text should be string"
            assert isinstance(
                chunk["chunk_index"], int
            ), f"Chunk {i} chunk_index should be int"
            assert isinstance(
                chunk["total_chunks"], int
            ), f"Chunk {i} total_chunks should be int"
            assert isinstance(chunk["size"], int), f"Chunk {i} size should be int"
            assert chunk["chunk_index"] == i, f"Chunk {i} has wrong chunk_index"
            assert chunk["total_chunks"] == len(
                chunks
            ), f"Chunk {i} has wrong total_chunks"
            assert chunk["size"] == len(
                chunk["text"]
            ), f"Chunk {i} size doesn't match text length"
            assert (
                chunk["file_extension"] == "py"
            ), f"Chunk {i} has wrong file_extension"

    def test_no_boundary_detection_cuts_exact_positions(self, chunker):
        """Test that chunking cuts at exact character positions without boundary detection."""
        # Create text with clear word boundaries that should be ignored
        words = ["function", "class", "method", "variable"] * 100
        text = " ".join(words)  # Clear word boundaries with spaces
        file_path = Path("test.py")

        chunks = chunker.chunk_text(text, file_path)

        # Verify chunks are cut at exact positions, not at word boundaries
        for i, chunk in enumerate(chunks[:-1]):  # Exclude last chunk
            chunk_text = chunk["text"]
            assert len(chunk_text) == 1000, f"Chunk {i} should be exactly 1000 chars"

            # The chunk might end in the middle of a word - this is expected
            # We're not looking for word boundaries, just exact character counts

        # Verify overlap is exactly 150 characters regardless of word boundaries
        if len(chunks) >= 2:
            first_chunk = chunks[0]["text"]
            second_chunk = chunks[1]["text"]

            overlap = first_chunk[-150:]
            beginning = second_chunk[:150]

            assert overlap == beginning, "Overlap should be exactly 150 characters"

    def test_consistent_chunk_sizes_100_percent(self, chunker):
        """Test that 100% of chunks (except last) are exactly 1000 characters."""
        # Test with multiple different text sizes
        test_sizes = [1000, 1500, 2000, 2500, 3000, 5000, 10000]

        for size in test_sizes:
            text = "x" * size
            file_path = Path("test.py")

            chunks = chunker.chunk_text(text, file_path)

            # All chunks except the last MUST be exactly 1000 characters
            for i in range(len(chunks) - 1):
                chunk_size = len(chunks[i]["text"])
                assert (
                    chunk_size == 1000
                ), f"For text size {size}, chunk {i} has {chunk_size} chars, expected exactly 1000"

            # Only the last chunk may be different from 1000
            if len(chunks) > 1:
                last_chunk_size = len(chunks[-1]["text"])
                # Last chunk should be > 0 and <= 1000
                assert (
                    0 < last_chunk_size <= 1000
                ), f"Last chunk size {last_chunk_size} should be between 1 and 1000"

    def test_no_parsing_pure_arithmetic(self, chunker):
        """Test that implementation uses no string analysis, regex, or complexity."""
        # This test verifies behavior consistent with pure arithmetic approach
        # by using text that would confuse a parsing-based approach

        text = (
            """
        def function():
            if True:
                # This comment spans
                # multiple lines and has
                "strings with \\"quotes\\" and 
                more strings"
                return {"key": "value",
                       "another": "string"}
        """
            * 100
        )  # Repeat to get multiple chunks

        file_path = Path("test.py")
        chunks = chunker.chunk_text(text, file_path)

        # Should still follow exact character arithmetic regardless of syntax
        for i in range(len(chunks) - 1):
            assert (
                len(chunks[i]["text"]) == 1000
            ), f"Even with complex syntax, chunk {i} should be exactly 1000 chars"

        # Overlap should still be exactly 150 characters
        if len(chunks) >= 2:
            overlap_expected = chunks[0]["text"][-150:]
            overlap_actual = chunks[1]["text"][:150]
            assert (
                overlap_expected == overlap_actual
            ), "Complex syntax should not affect exact character overlap"

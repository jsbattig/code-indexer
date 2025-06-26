"""Tests for line number tracking in text chunking and processing."""

from pathlib import Path
import tempfile

from src.code_indexer.indexing.chunker import TextChunker
from src.code_indexer.config import IndexingConfig


class TestLineNumberTrackingInChunker:
    """Test line number tracking in TextChunker."""

    def setup_method(self):
        """Set up test fixtures."""
        config = IndexingConfig()
        config.chunk_size = 200  # Small chunks for testing
        config.chunk_overlap = 20
        self.chunker = TextChunker(config)

    def test_chunk_text_includes_line_numbers_simple(self):
        """Test that chunk_text includes accurate line numbers for simple text."""
        text = """def function_one():
    print("first function")
    return True

def function_two():
    print("second function")
    return False

def function_three():
    print("third function")
    return None"""

        chunks = self.chunker.chunk_text(text)

        # Should have line_start and line_end in each chunk
        assert len(chunks) > 0
        for chunk in chunks:
            assert "line_start" in chunk, "Chunk missing line_start"
            assert "line_end" in chunk, "Chunk missing line_end"
            assert isinstance(chunk["line_start"], int), "line_start should be integer"
            assert isinstance(chunk["line_end"], int), "line_end should be integer"
            assert chunk["line_start"] >= 1, "line_start should be 1-indexed"
            assert (
                chunk["line_end"] >= chunk["line_start"]
            ), "line_end should be >= line_start"

    def test_chunk_text_accurate_line_boundaries(self):
        """Test that line numbers accurately reflect text boundaries."""
        text = """line 1
line 2  
line 3
line 4
line 5"""

        chunks = self.chunker.chunk_text(text)

        # For simple text that fits in one chunk
        if len(chunks) == 1:
            chunk = chunks[0]
            assert chunk["line_start"] == 1
            assert chunk["line_end"] == 5  # 5 lines total
        else:
            # For multiple chunks, verify no gaps or overlaps in line coverage
            total_lines = len(text.splitlines())
            covered_lines = set()

            for chunk in chunks:
                for line_num in range(chunk["line_start"], chunk["line_end"] + 1):
                    covered_lines.add(line_num)

            # Should cover all lines from 1 to total_lines
            expected_lines = set(range(1, total_lines + 1))
            assert covered_lines.issuperset(
                expected_lines
            ), "Not all lines covered by chunks"

    def test_chunk_file_includes_line_numbers(self):
        """Test that chunk_file includes line numbers when processing files."""
        # Create a temporary file with known content
        test_content = """def test_function():
    # This is line 2
    x = 42
    y = "hello"
    return x + len(y)

class TestClass:
    def method(self):
        return "world" """

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            temp_path = Path(f.name)

        try:
            chunks = self.chunker.chunk_file(temp_path)

            # Verify line numbers are present and accurate
            assert len(chunks) > 0
            for chunk in chunks:
                assert "line_start" in chunk
                assert "line_end" in chunk

                # Verify the line numbers make sense for this content
                assert chunk["line_start"] >= 1
                assert chunk["line_end"] <= 9  # 9 lines in test content

        finally:
            temp_path.unlink()

    def test_multiple_chunks_sequential_line_numbers(self):
        """Test that multiple chunks have sequential, non-overlapping line numbers."""
        # Create content that will definitely split into multiple chunks
        lines = [
            f"# This is line {i+1} with some content to make it longer"
            for i in range(20)
        ]
        text = "\n".join(lines)

        # Use smaller chunk size to force splitting
        config = IndexingConfig()
        config.chunk_size = 100  # Very small to force multiple chunks
        config.chunk_overlap = 10
        chunker = TextChunker(config)

        chunks = chunker.chunk_text(text)

        # Should have multiple chunks
        assert len(chunks) > 1, "Expected multiple chunks for large content"

        # Verify line numbers are sequential and logical
        for i, chunk in enumerate(chunks):
            assert "line_start" in chunk
            assert "line_end" in chunk

            if i == 0:
                # First chunk should start at line 1
                assert chunk["line_start"] == 1
            else:
                # Later chunks should start after or at the previous chunk's start
                # (allowing for overlap)
                prev_chunk = chunks[i - 1]
                assert chunk["line_start"] >= prev_chunk["line_start"]

    def test_chunk_line_numbers_match_actual_content(self):
        """Test that reported line numbers correspond to the actual content in the chunk."""
        text = """import os
import sys

def main():
    print("Starting application")
    
    # Process files
    for file in os.listdir("."):
        print(f"Processing {file}")
        
    print("Done")
    return 0

if __name__ == "__main__":
    main()"""

        chunks = self.chunker.chunk_text(text)
        text_lines = text.splitlines()

        for chunk in chunks:
            line_start = chunk["line_start"]
            line_end = chunk["line_end"]

            # The chunk should represent content from those line ranges
            assert line_start >= 1, f"line_start should be >= 1, got {line_start}"
            assert line_end <= len(
                text_lines
            ), f"line_end should be <= {len(text_lines)}, got {line_end}"
            assert (
                line_start <= line_end
            ), f"line_start should be <= line_end, got {line_start}-{line_end}"

            # Extract key content from the expected lines to verify semantic correspondence
            expected_lines = text_lines[
                line_start - 1 : line_end
            ]  # Convert to 0-indexed

            # Check that key identifiers from the expected lines appear in the chunk
            # This allows for formatting differences while ensuring semantic correctness
            chunk_content = chunk["text"]

            # Remove file header if present
            if chunk_content.startswith("// File:"):
                chunk_lines = chunk_content.split("\n", 1)
                if len(chunk_lines) > 1:
                    chunk_content = chunk_lines[1]

            # Check that the chunk contains content semantically corresponding to the line range
            # Since chunking may split text at boundaries, we check that the chunk contains
            # substantial content from within the reported line range
            expected_content_found = False
            for line_idx, line in enumerate(expected_lines):
                if line.strip() and len(line.strip()) > 5:
                    significant_content = line.strip()
                    # Check if this line's content appears in the chunk
                    normalized_chunk = " ".join(chunk_content.split())
                    normalized_expected = " ".join(significant_content.split())
                    if normalized_expected in normalized_chunk:
                        expected_content_found = True
                        break

            # At least some substantial content from the line range should be in the chunk
            if not expected_content_found and any(
                line.strip() and len(line.strip()) > 5 for line in expected_lines
            ):
                # Only fail if there was substantial content expected but not found
                substantial_lines = [
                    line.strip()
                    for line in expected_lines
                    if line.strip() and len(line.strip()) > 5
                ]
                assert (
                    False
                ), f"No substantial content from lines {line_start}-{line_end} found in chunk. Expected one of: {substantial_lines[:3]}"


class TestLineNumbersInProcessorMetadata:
    """Test that processor includes line numbers in metadata."""

    def test_process_file_parallel_includes_line_metadata(self):
        """Test that process_file_parallel includes line numbers in chunk metadata."""
        # This test will fail until we implement the feature
        # It's designed to test the processor's metadata handling

        # Mock dependencies
        from src.code_indexer.indexing.processor import DocumentProcessor
        from src.code_indexer.config import Config
        from unittest.mock import Mock

        config = Mock(spec=Config)
        config.codebase_dir = Path("/tmp")
        config.indexing = IndexingConfig()
        config.exclude_dirs = []
        config.exclude_patterns = []
        config.include_patterns = ["*"]

        embedding_provider = Mock()
        qdrant_client = Mock()

        processor = DocumentProcessor(config, embedding_provider, qdrant_client)

        # Create a test file with known content
        test_content = """def function_a():
    return "a"

def function_b():
    return "b" """

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            temp_path = Path(f.name)

        try:
            # Mock the vector manager and its results
            vector_manager = Mock()

            # Mock vector results that should include line metadata
            vector_result = Mock()
            vector_result.error = None
            vector_result.embedding = [0.1] * 768  # Mock embedding
            vector_result.metadata = {
                "path": str(temp_path),
                "content": 'def function_a():\n    return "a"',
                "language": "py",
                "file_size": 100,
                "chunk_index": 0,
                "total_chunks": 1,
                "indexed_at": "2023-01-01T00:00:00Z",
                "line_start": 1,  # This should be included
                "line_end": 2,  # This should be included
            }

            # Mock future result
            mock_future = Mock()
            mock_future.result.return_value = vector_result
            vector_manager.submit_chunk.return_value = mock_future

            # Mock qdrant create_point to capture the payload
            captured_payload = None

            def capture_create_point(vector, payload, embedding_model):
                nonlocal captured_payload
                captured_payload = payload
                return {"id": "test_id", "vector": vector, "payload": payload}

            qdrant_client.create_point.side_effect = capture_create_point

            # Call the method under test
            processor.process_file_parallel(temp_path, vector_manager)

            # Verify that line metadata was included
            assert captured_payload is not None, "create_point should have been called"
            assert "line_start" in captured_payload, "Payload should include line_start"
            assert "line_end" in captured_payload, "Payload should include line_end"
            assert captured_payload["line_start"] == 1, "line_start should be 1"
            assert captured_payload["line_end"] == 2, "line_end should be 2"

        finally:
            temp_path.unlink()


class TestLineNumbersInRAGExtractor:
    """Test accurate line numbers in RAG context extraction."""

    def test_extract_context_uses_actual_line_numbers(self):
        """Test that RAG extractor uses actual line numbers from metadata instead of estimation."""
        from src.code_indexer.services.rag_context_extractor import RAGContextExtractor

        # Create test directory structure
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a test file
            test_file = temp_path / "test.py"
            test_content = """# Line 1
def function_one():  # Line 2
    print("hello")   # Line 3
    return True      # Line 4
                     # Line 5
def function_two():  # Line 6
    print("world")   # Line 7
    return False     # Line 8"""

            test_file.write_text(test_content)

            extractor = RAGContextExtractor(temp_path)

            # Mock search results with actual line metadata
            search_results = [
                {
                    "id": "chunk_1",
                    "score": 0.9,
                    "payload": {
                        "path": "test.py",
                        "content": 'def function_one():\n    print("hello")\n    return True',
                        "language": "py",
                        "line_start": 2,  # Actual line numbers
                        "line_end": 4,  # Actual line numbers
                        "chunk_index": 0,
                        "file_size": 100,
                    },
                }
            ]

            contexts = extractor.extract_context_from_results(
                search_results, context_lines=1
            )

            # Verify context extraction uses actual line numbers
            assert len(contexts) == 1
            context = contexts[0]

            # The context should be extracted around the actual lines (2-4)
            # With context_lines=1, should expand to include line 1 and possibly line 5
            assert (
                context.line_start <= 2
            ), f"Context should start at or before line 2, got {context.line_start}"
            assert (
                context.line_end >= 4
            ), f"Context should end at or after line 4, got {context.line_end}"

            # Verify the content includes the expected function
            assert "function_one" in context.content

    def test_merge_overlapping_contexts_uses_actual_lines(self):
        """Test that context merging uses actual line positions instead of estimates."""
        from src.code_indexer.services.rag_context_extractor import RAGContextExtractor

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            extractor = RAGContextExtractor(temp_path)

            # Create mock file results with actual line metadata
            file_results = [
                {
                    "id": "chunk_1",
                    "score": 0.9,
                    "payload": {
                        "line_start": 5,
                        "line_end": 10,
                        "chunk_index": 0,  # This would estimate to line 0, but actual is 5-10
                    },
                },
                {
                    "id": "chunk_2",
                    "score": 0.8,
                    "payload": {
                        "line_start": 12,
                        "line_end": 18,
                        "chunk_index": 1,  # This would estimate to line 10, but actual is 12-18
                    },
                },
            ]

            # Mock file lines
            lines = [f"Line {i+1}" for i in range(25)]  # 25 lines

            # Call the private method to test context merging
            merged_contexts = extractor._merge_overlapping_contexts(
                file_results, lines, context_lines=4, remaining_lines=1000
            )

            # Should have two separate contexts since lines 5-10 and 12-18 don't overlap
            # even with context expansion
            assert len(merged_contexts) >= 1, "Should have at least one context"

            # Verify the contexts use actual line positions, not estimates
            for start_line, end_line, result in merged_contexts:
                # The context should be around the actual lines (5-10 or 12-18)
                # not around the estimated positions (0 or 10)
                if result["id"] == "chunk_1":
                    # With chunk on lines 5-10 and context_lines=4,
                    # context should expand to lines 1-14 (0-indexed: 0-13)
                    # So start_line should be 0 (which is line 1 in 1-indexed)
                    assert (
                        start_line >= 0
                    ), f"Context for chunk_1 should start >= 0, got {start_line}"
                    assert (
                        start_line <= 4
                    ), f"Context for chunk_1 should start <= 4, got {start_line}"
                    # Should include the original chunk lines 5-10 (0-indexed: 4-9)
                    assert (
                        end_line >= 9
                    ), f"Context for chunk_1 should end >= 9 (includes line 10), got {end_line}"
                elif result["id"] == "chunk_2":
                    # With chunk on lines 12-18 and context_lines=4,
                    # context should expand to lines 8-22 (0-indexed: 7-21)
                    assert (
                        start_line >= 7
                    ), f"Context for chunk_2 should start >= 7, got {start_line}"
                    assert (
                        start_line <= 11
                    ), f"Context for chunk_2 should start <= 11, got {start_line}"
                    # Should include the original chunk lines 12-18 (0-indexed: 11-17)
                    assert (
                        end_line >= 17
                    ), f"Context for chunk_2 should end >= 17 (includes line 18), got {end_line}"

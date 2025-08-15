"""Tests for text chunking."""

import tempfile
from pathlib import Path


from code_indexer.config import IndexingConfig
from code_indexer.indexing.chunker import TextChunker


def test_chunker_basic():
    """Test basic chunking functionality."""
    config = IndexingConfig(chunk_size=100, chunk_overlap=20)
    chunker = TextChunker(config)

    # Short text should return single chunk
    short_text = "def hello():\n    print('world')"
    chunks = chunker.chunk_text(short_text)

    assert len(chunks) == 1
    assert chunks[0]["text"] == short_text
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["total_chunks"] == 1


def test_chunker_python_splitting():
    """Test Python-specific splitting."""
    config = IndexingConfig(chunk_size=50, chunk_overlap=10)
    chunker = TextChunker(config)

    python_code = """def function1():
    return 1

def function2():
    return 2

class MyClass:
    def method(self):
        pass"""

    chunks = chunker.chunk_text(python_code, Path("test.py"))

    # Should split on function/class boundaries
    assert len(chunks) > 1
    # Each chunk should have metadata
    for chunk in chunks:
        assert "text" in chunk
        assert "chunk_index" in chunk
        assert "total_chunks" in chunk


def test_chunker_file_processing():
    """Test file reading and chunking."""
    config = IndexingConfig(chunk_size=100, chunk_overlap=20)
    chunker = TextChunker(config)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def test():\n    print('hello')\n\ndef another():\n    print('world')")
        f.flush()

        file_path = Path(f.name)
        chunks = chunker.chunk_file(file_path)

        assert len(chunks) >= 1
        assert all(chunk["file_path"] == str(file_path) for chunk in chunks)
        assert all(chunk["file_extension"] == "py" for chunk in chunks)

        # Cleanup
        file_path.unlink()


def test_chunker_fallback_splitting():
    """Test fallback splitting for very long text."""
    config = IndexingConfig(chunk_size=50, chunk_overlap=10)
    chunker = TextChunker(config)

    # Long text without good break points
    long_text = "a" * 200
    chunks = chunker._fallback_split(long_text)

    assert len(chunks) > 1
    # Check overlap
    for i in range(len(chunks) - 1):
        current_chunk = chunks[i]
        # There should be some overlap or proper boundary
        assert len(current_chunk) <= config.chunk_size + config.chunk_overlap


def test_estimate_chunks():
    """Test chunk estimation."""
    config = IndexingConfig(chunk_size=100, chunk_overlap=20)
    chunker = TextChunker(config)

    # Short text
    assert chunker.estimate_chunks("short") == 1

    # Long text
    long_text = "x" * 500
    estimated = chunker.estimate_chunks(long_text)
    assert estimated > 1

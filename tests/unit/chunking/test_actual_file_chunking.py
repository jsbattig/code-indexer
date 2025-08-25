"""
Test chunking with actual file content to debug the tiny chunk issue.
"""

import pytest
from pathlib import Path
from code_indexer.indexing.chunker import TextChunker
from code_indexer.config import IndexingConfig


def test_actual_claude_integration_file_chunking():
    """Test chunking with the actual claude_integration.py file."""
    config = IndexingConfig(chunk_size=1500, chunk_overlap=150)
    chunker = TextChunker(config)

    # Test with the actual file
    claude_integration_path = Path("src/code_indexer/services/claude_integration.py")

    if claude_integration_path.exists():
        chunks = chunker.chunk_file(claude_integration_path)

        print(f"\nDEBUG: File: {claude_integration_path}")
        print(f"DEBUG: Number of chunks created: {len(chunks)}")

        for i, chunk in enumerate(chunks):
            print(f"DEBUG: Chunk {i}: size={chunk['size']} bytes")
            print(f"  Content preview: {repr(chunk['text'][:100])}")

            # Check for problematic tiny chunks
            if chunk["size"] < 100:
                print(f"  TINY CHUNK FOUND: {repr(chunk['text'])}")

        # Verify no tiny chunks
        tiny_chunks = [chunk for chunk in chunks if chunk["size"] < 100]
        if tiny_chunks:
            print(f"\nFound {len(tiny_chunks)} tiny chunks:")
            for chunk in tiny_chunks:
                print(f"  Size: {chunk['size']}, Content: {repr(chunk['text'])}")

        # This might fail if tiny chunks exist
        assert len(tiny_chunks) == 0, f"Found {len(tiny_chunks)} tiny chunks"

    else:
        pytest.skip("Claude integration file not found")

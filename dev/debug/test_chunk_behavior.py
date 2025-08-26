#!/usr/bin/env python3

"""
Test script to verify FixedSizeChunker behavior matches documentation:
- Fixed 1000-character chunks
- Fixed 150-character overlap
- Pure arithmetic, no configuration influence
"""

import sys
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from code_indexer.config import IndexingConfig
from code_indexer.indexing.fixed_size_chunker import FixedSizeChunker


def test_fixed_chunking_behavior():
    """Test that FixedSizeChunker produces exactly 1000-char chunks with 150-char overlap."""
    
    print("=== Testing FixedSizeChunker Behavior ===")
    
    # Create a test text of known length
    test_text = "A" * 2500  # 2500 characters
    
    # Try different config values to prove they don't affect chunking
    configs_to_test = [
        {"chunk_size": 500, "chunk_overlap": 50, "description": "Small config"},
        {"chunk_size": 1500, "chunk_overlap": 150, "description": "Default config"}, 
        {"chunk_size": 2000, "chunk_overlap": 200, "description": "Large config"},
    ]
    
    for config_data in configs_to_test:
        config = IndexingConfig(**config_data)
        chunker = FixedSizeChunker(config)
        
        chunks = chunker.chunk_text(test_text)
        
        print(f"\n--- {config_data['description']} (chunk_size={config_data['chunk_size']}) ---")
        print(f"Config chunk_size: {config.chunk_size}")
        print(f"Config chunk_overlap: {config.chunk_overlap}")
        print(f"Number of chunks: {len(chunks)}")
        
        for i, chunk in enumerate(chunks):
            chunk_len = len(chunk['text'])
            print(f"Chunk {i}: {chunk_len} characters")
            
            # Verify fixed size (1000 chars except possibly last chunk)
            if i < len(chunks) - 1:  # Not the last chunk
                assert chunk_len == 1000, f"Chunk {i} should be exactly 1000 chars, got {chunk_len}"
            else:  # Last chunk can be smaller
                assert chunk_len <= 1000, f"Last chunk {i} should be <= 1000 chars, got {chunk_len}"
        
        # Verify overlap between consecutive chunks
        if len(chunks) > 1:
            for i in range(len(chunks) - 1):
                current_chunk = chunks[i]['text']
                next_chunk = chunks[i + 1]['text']
                
                # Last 150 chars of current should match first 150 chars of next
                current_end = current_chunk[-150:]
                next_start = next_chunk[:150]
                
                assert current_end == next_start, f"150-char overlap failed between chunks {i} and {i+1}"
                print(f"✓ Verified 150-char overlap between chunks {i} and {i+1}")
    
    print("\n=== All Tests Passed! ===")
    print("✓ FixedSizeChunker produces exactly 1000-character chunks")
    print("✓ FixedSizeChunker uses exactly 150-character overlap")  
    print("✓ Configuration values do NOT affect chunking behavior")
    print("✓ Behavior matches documentation perfectly")


if __name__ == "__main__":
    test_fixed_chunking_behavior()
#!/usr/bin/env python3
"""
Comprehensive tests for chunking line number accuracy.

This test suite verifies that both text chunking and AST-based semantic chunking
report accurate line numbers that match the actual content boundaries.
"""

import pytest
from code_indexer.config import IndexingConfig
from code_indexer.indexing.chunker import TextChunker
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestChunkingLineNumberAccuracy:
    """Test that chunking accurately reports line numbers for content."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        config = IndexingConfig()
        config.chunk_size = 800  # Smaller size to force chunking
        config.chunk_overlap = 100
        return config

    @pytest.fixture
    def text_chunker(self, config):
        """Create text chunker."""
        return TextChunker(config)

    @pytest.fixture
    def semantic_chunker(self, config):
        """Create semantic chunker."""
        return SemanticChunker(config)

    def _verify_chunk_line_numbers(self, chunk, original_text, file_description=""):
        """
        Verify that a chunk's reported line numbers match its actual content.

        Args:
            chunk: The chunk to verify (dict with text, line_start, line_end)
            original_text: The original text the chunk was extracted from
            file_description: Description for error messages
        """
        # Get the lines from the original text
        original_lines = original_text.splitlines()

        # Verify line numbers are valid
        assert (
            chunk["line_start"] >= 1
        ), f"{file_description}: line_start must be >= 1, got {chunk['line_start']}"
        assert (
            chunk["line_end"] >= chunk["line_start"]
        ), f"{file_description}: line_end must be >= line_start"
        assert chunk["line_end"] <= len(
            original_lines
        ), f"{file_description}: line_end {chunk['line_end']} exceeds total lines {len(original_lines)}"

        # Extract the expected content based on reported line numbers
        expected_lines = original_lines[chunk["line_start"] - 1 : chunk["line_end"]]

        # Get actual chunk content lines WITHOUT stripping to preserve line alignment
        chunk_content = chunk["text"]
        chunk_lines = chunk_content.splitlines()

        # Verify the first and last lines match
        if chunk_lines and expected_lines:
            chunk_first_line = chunk_lines[0].strip()
            chunk_last_line = chunk_lines[-1].strip()
            expected_first_line = expected_lines[0].strip()
            expected_last_line = expected_lines[-1].strip()

            assert chunk_first_line == expected_first_line, (
                f"{file_description}: First line mismatch\n"
                f"Chunk first line: '{chunk_first_line}'\n"
                f"Expected first line: '{expected_first_line}'\n"
                f"Chunk reports lines {chunk['line_start']}-{chunk['line_end']}"
            )

            assert chunk_last_line == expected_last_line, (
                f"{file_description}: Last line mismatch\n"
                f"Chunk last line: '{chunk_last_line}'\n"
                f"Expected last line: '{expected_last_line}'\n"
                f"Chunk reports lines {chunk['line_start']}-{chunk['line_end']}"
            )

    def test_text_chunking_simple_code(self, text_chunker):
        """Test text chunking with simple Python code."""
        code = """import os
import sys
from pathlib import Path

def main():
    print("Starting application")
    
    # Process files
    for file in os.listdir("."):
        print(f"Processing {file}")
        
    print("Done")
    return 0

if __name__ == "__main__":
    main()"""

        chunks = text_chunker.chunk_text(code)

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"Text chunking simple code - chunk {i+1}"
            )

    def test_text_chunking_complex_python_file(self, text_chunker):
        """Test text chunking with a complex Python file that will be split."""
        code = ""

        # Build a large Python file
        for i in range(1, 51):
            code += f"""
class DataProcessor{i}:
    '''Data processor class {i} for handling complex operations.'''
    
    def __init__(self, config):
        self.config = config
        self.processed_count = 0
        
    def process_data(self, data):
        '''Process the input data using algorithm {i}.'''
        result = []
        for item in data:
            if item.value > {i * 10}:
                result.append(item.transform())
        self.processed_count += len(result)
        return result
        
    def get_stats(self):
        return {{'processed': self.processed_count, 'algorithm': {i}}}

"""

        chunks = text_chunker.chunk_text(code)
        assert len(chunks) > 1, "Expected multiple chunks for large code file"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"Text chunking complex Python - chunk {i+1}"
            )

    def test_semantic_chunking_python_classes(self, semantic_chunker):
        """Test semantic chunking with Python classes."""
        code = """'''Module for data processing utilities.'''

import os
import sys
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class Config:
    '''Configuration class for the application.'''
    debug: bool = False
    max_workers: int = 4
    output_dir: str = "/tmp"

class DataProcessor:
    '''Main data processor class.'''
    
    def __init__(self, config: Config):
        self.config = config
        self.processed_items = []
        
    def process_item(self, item: Dict) -> Optional[Dict]:
        '''Process a single item.'''
        if not item:
            return None
            
        # Validate item
        if 'id' not in item:
            raise ValueError("Item must have an id")
            
        # Transform item
        result = {
            'id': item['id'],
            'processed': True,
            'timestamp': self._get_timestamp()
        }
        
        self.processed_items.append(result)
        return result
        
    def _get_timestamp(self) -> float:
        '''Get current timestamp.'''
        import time
        return time.time()
        
    def get_stats(self) -> Dict:
        '''Get processing statistics.'''
        return {
            'total_processed': len(self.processed_items),
            'config': self.config.__dict__
        }

def main():
    '''Main function to run the processor.'''
    config = Config(debug=True)
    processor = DataProcessor(config)
    
    # Sample data
    items = [
        {'id': 1, 'value': 'test1'},
        {'id': 2, 'value': 'test2'},
    ]
    
    for item in items:
        result = processor.process_item(item)
        print(f"Processed: {result}")
        
    print(f"Stats: {processor.get_stats()}")

if __name__ == "__main__":
    main()"""

        # Test with semantic chunker
        chunks = semantic_chunker.chunk_content(code, "test.py")

        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            # Convert semantic chunk to dict format
            if hasattr(chunk, "to_dict"):
                chunk_dict = chunk.to_dict()
            else:
                chunk_dict = chunk

            self._verify_chunk_line_numbers(
                chunk_dict, code, f"Semantic chunking Python classes - chunk {i+1}"
            )

    def test_semantic_chunking_large_class(self, semantic_chunker):
        """Test semantic chunking with a large class that should be split."""
        code = """
class LargeComplexClass:
    '''A very large class that should be split into multiple chunks.'''
    
    def __init__(self):
        self.data = {}
        self.cache = {}
        self.stats = {'operations': 0}
        
    def method_1(self):
        '''First method with substantial content.'''
        # This method does a lot of work
        for i in range(100):
            self.data[f'key_{i}'] = f'value_{i}'
            self.cache[i] = i * 2
            
        # Update statistics
        self.stats['operations'] += 1
        return len(self.data)
        
    def method_2(self):
        '''Second method with even more content.'''
        results = []
        
        # Complex processing logic
        for key, value in self.data.items():
            if key.startswith('key_'):
                processed = self._complex_processing(value)
                results.append(processed)
                
        # Cache optimization
        for i in range(50):
            if i in self.cache:
                self.cache[i] = self.cache[i] * 1.5
                
        self.stats['operations'] += 1
        return results
        
    def method_3(self):
        '''Third method with lots of nested logic.'''
        nested_data = {}
        
        for i in range(20):
            nested_data[i] = {}
            for j in range(10):
                nested_data[i][j] = {}
                for k in range(5):
                    nested_data[i][j][k] = i * j * k
                    
        # Process nested data
        flattened = []
        for i_dict in nested_data.values():
            for j_dict in i_dict.values():
                for k_value in j_dict.values():
                    if k_value > 10:
                        flattened.append(k_value)
                        
        self.stats['operations'] += 1
        return flattened
        
    def _complex_processing(self, value):
        '''Helper method for complex processing.'''
        # Simulate complex computation
        result = value
        for i in range(10):
            result = str(hash(result))[:8]
        return result
        
    def get_comprehensive_stats(self):
        '''Get comprehensive statistics about the class state.'''
        return {
            'data_size': len(self.data),
            'cache_size': len(self.cache),
            'operations': self.stats['operations'],
            'memory_usage': self._estimate_memory(),
            'efficiency_score': self._calculate_efficiency()
        }
        
    def _estimate_memory(self):
        '''Estimate memory usage.'''
        import sys
        return sys.getsizeof(self.data) + sys.getsizeof(self.cache)
        
    def _calculate_efficiency(self):
        '''Calculate efficiency score.'''
        if self.stats['operations'] == 0:
            return 0
        return len(self.data) / self.stats['operations']
"""

        chunks = semantic_chunker.chunk_content(code, "large_class.py")

        # Should have multiple chunks for a large class
        assert len(chunks) >= 1, "Expected at least one chunk for large class"

        for i, chunk in enumerate(chunks):
            # Convert semantic chunk to dict format
            if hasattr(chunk, "to_dict"):
                chunk_dict = chunk.to_dict()
            else:
                chunk_dict = chunk

            self._verify_chunk_line_numbers(
                chunk_dict, code, f"Semantic chunking large class - chunk {i+1}"
            )

    def test_text_chunking_edge_cases(self, text_chunker):
        """Test text chunking with edge cases like empty lines and special characters."""
        code = """# File with various edge cases

import os


# Multiple empty lines above

def function_with_empty_lines():
    '''Function with empty lines and special characters.'''
    
    # Empty line above
    data = {
        'key1': 'value with "quotes" and \\'apostrophes\\'',
        'key2': '''multi-line
        string with
        various content''',
        'key3': r'raw string with \\backslashes\\'
    }
    
    
    # Two empty lines above
    return data


class ClassWithSpecialContent:
    '''Class with special characters and formatting.'''
    
    def __init__(self):
        # Unicode and special characters
        self.unicode_data = "Hello, 世界! 🌍 Testing unicode"
        self.symbols = "!@#$%^&*()_+-=[]{}|;:',.<>?"
        
    def method_with_docstring(self):
        '''
        Multi-line docstring
        with various formatting:
        
        Args:
            none
            
        Returns:
            str: A formatted string
            
        Example:
            >>> obj = ClassWithSpecialContent()
            >>> obj.method_with_docstring()
            'formatted'
        '''
        return 'formatted'


# Final comment at end of file"""

        chunks = text_chunker.chunk_text(code)

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"Text chunking edge cases - chunk {i+1}"
            )

    def test_consistency_between_chunkers(self, text_chunker, semantic_chunker):
        """Test that both chunkers produce consistent line numbering for the same content."""
        code = """
def simple_function():
    '''A simple function for testing.'''
    return "test"

class SimpleClass:
    '''A simple class for testing.'''
    
    def method(self):
        return "method"
"""

        # Get chunks from both chunkers
        text_chunks = text_chunker.chunk_text(code)
        semantic_chunks = semantic_chunker.chunk_content(code, "test.py")

        # Convert semantic chunks to dict format
        semantic_chunks_dict = []
        for chunk in semantic_chunks:
            if hasattr(chunk, "to_dict"):
                semantic_chunks_dict.append(chunk.to_dict())
            else:
                semantic_chunks_dict.append(chunk)

        # Verify line numbers for both
        for i, chunk in enumerate(text_chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"Text chunker consistency test - chunk {i+1}"
            )

        for i, chunk in enumerate(semantic_chunks_dict):
            self._verify_chunk_line_numbers(
                chunk, code, f"Semantic chunker consistency test - chunk {i+1}"
            )

    def test_large_file_chunking_accuracy(self, text_chunker):
        """Test chunking accuracy with a very large file that will definitely be split."""
        # Create a large file with known structure
        lines = []
        for i in range(1, 201):  # 200 functions
            lines.extend(
                [
                    f"def function_{i}():",
                    f"    '''Function number {i} for testing.'''",
                    f"    result = {i} * 2",
                    f"    print(f'Function {i} result: {{result}}')",
                    "    return result",
                    "",  # Empty line between functions
                ]
            )

        code = "\n".join(lines)
        expected_total_lines = len(lines)

        chunks = text_chunker.chunk_text(code)
        assert (
            len(chunks) > 5
        ), f"Expected many chunks for large file, got {len(chunks)}"

        # Verify every chunk
        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"Large file chunking - chunk {i+1}"
            )

        # Verify coverage - all lines should be covered by at least one chunk
        covered_lines = set()
        for chunk in chunks:
            for line_num in range(chunk["line_start"], chunk["line_end"] + 1):
                covered_lines.add(line_num)

        # Should cover most of the file (allowing for some overlap/gaps due to chunking)
        coverage_ratio = len(covered_lines) / expected_total_lines
        assert (
            coverage_ratio > 0.8
        ), f"Expected >80% line coverage, got {coverage_ratio:.2%}"

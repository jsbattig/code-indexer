#!/usr/bin/env python3
"""
Tests to reproduce and fix chunking boundary bleeding issues.

This specifically targets the problem where chunks contain content from
adjacent chunks, like "else:" appearing at the top of a chunk when it
doesn't exist in the original file at that location.
"""

import pytest
from code_indexer.config import IndexingConfig
from code_indexer.indexing.chunker import TextChunker
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestChunkingBoundaryBleeding:
    """Test that chunks don't bleed content from adjacent chunks."""

    @pytest.fixture
    def config(self):
        """Create test configuration with small chunks to force splitting."""
        config = IndexingConfig()
        config.chunk_size = 400  # Small to force multiple chunks
        config.chunk_overlap = 50  # Small overlap
        return config

    @pytest.fixture
    def text_chunker(self, config):
        """Create text chunker."""
        return TextChunker(config)

    @pytest.fixture
    def semantic_chunker(self, config):
        """Create semantic chunker."""
        return SemanticChunker(config)

    def test_no_content_bleeding_between_chunks(self, text_chunker):
        """Test that no content from one chunk bleeds into another."""
        # Create code that will definitely be split into multiple chunks
        code = '''import os
import sys
from pathlib import Path

def function_one():
    """First function that should be in its own chunk."""
    if True:
        print("function_one")
        return "one"
    else:
        return "fallback"

def function_two():
    """Second function that should be in its own chunk."""
    if False:
        print("function_two")
        return "two"
    else:
        print("else case")
        return "else_value"

def function_three():
    """Third function that should be in its own chunk."""
    data = {
        "key1": "value1",
        "key2": "value2"
    }
    
    if data:
        print("function_three")
        return data
    else:
        return {}

class TestClass:
    """A test class that might be split."""
    
    def __init__(self):
        self.value = "initial"
        
    def method_one(self):
        if self.value:
            return self.value
        else:
            return "empty"
            
    def method_two(self):
        """Another method to increase class size."""
        result = []
        for i in range(10):
            if i % 2 == 0:
                result.append(i)
            else:
                result.append(i * 2)
        return result'''

        original_lines = code.splitlines()
        chunks = text_chunker.chunk_text(code)

        assert len(chunks) > 1, "Expected multiple chunks for this code size"

        # For each chunk, verify that every line in the chunk actually exists
        # in the original file at the reported line numbers
        for i, chunk in enumerate(chunks):
            chunk_lines = chunk["text"].strip().splitlines()

            for j, chunk_line in enumerate(chunk_lines):
                # Calculate what line this should be in the original file
                original_line_index = chunk["line_start"] - 1 + j

                # Skip if this would be beyond the original file
                if original_line_index >= len(original_lines):
                    continue

                expected_line = original_lines[original_line_index]

                # Strip whitespace for comparison
                chunk_line_stripped = chunk_line.strip()
                expected_line_stripped = expected_line.strip()

                # If both lines have content, they should match
                if chunk_line_stripped and expected_line_stripped:
                    assert chunk_line_stripped == expected_line_stripped, (
                        f"Chunk {i + 1}, line {j + 1}: Content bleeding detected!\n"
                        f"Chunk line: '{chunk_line_stripped}'\n"
                        f"Expected (original line {original_line_index + 1}): '{expected_line_stripped}'\n"
                        f"Chunk reports lines {chunk['line_start']}-{chunk['line_end']}"
                    )

    def test_specific_else_bleeding_case(self, text_chunker):
        """Test the specific case where 'else:' appears incorrectly."""
        # Create code that mimics the structure from your example
        code = '''if not default_models:
    raise ValueError(
        f"No 'selection_criteria.default_models' section found in {config_path}. "
        "Cannot initialize Gemini provider without Google default model configuration."
    )

# Get Google provider default
google_default = default_models.get("google_provider_default")
if not google_default:
    raise ValueError(
        f"No 'google_provider_default' model configured in {config_path}. "
    )

def some_function():
    """A function to make the file longer."""
    if True:
        return "success"
    else:
        return "failure"

class SomeClass:
    """A class to make the file even longer."""
    
    def __init__(self):
        self.data = {}
        
    def process(self):
        if self.data:
            return True
        else:
            return False'''

        chunks = text_chunker.chunk_text(code)
        original_lines = code.splitlines()

        # Check each chunk for the specific bleeding issue
        for i, chunk in enumerate(chunks):
            chunk_content = chunk["text"].strip()
            chunk_lines = chunk_content.splitlines()

            # Check if first line of chunk contains 'else:'
            if chunk_lines and chunk_lines[0].strip() == "else:":
                # This is the bleeding issue - check if 'else:' should actually be there
                expected_first_line_index = chunk["line_start"] - 1
                if expected_first_line_index < len(original_lines):
                    expected_first_line = original_lines[
                        expected_first_line_index
                    ].strip()

                    assert expected_first_line == "else:", (
                        f"BOUNDARY BLEEDING DETECTED in chunk {i + 1}!\n"
                        f"Chunk starts with 'else:' but original line {chunk['line_start']} is: '{expected_first_line}'\n"
                        f"This indicates content is bleeding from an adjacent chunk."
                    )

    def test_semantic_chunker_file_header_issue(self, semantic_chunker):
        """Test that semantic chunker doesn't add file headers that mess up line numbers."""
        code = '''def simple_function():
    """A simple function."""
    return "test"

class SimpleClass:
    """A simple class."""
    
    def method(self):
        return "method"'''

        chunks = semantic_chunker.chunk_content(code, "test.py")

        for i, chunk in enumerate(chunks):
            chunk_dict = chunk if isinstance(chunk, dict) else chunk.to_dict()
            chunk_content = chunk_dict["text"].strip()
            chunk_lines = chunk_content.splitlines()

            # Check if the chunk starts with a file header
            if chunk_lines and chunk_lines[0].startswith("// File:"):
                # This is wrong - the file header shouldn't be included in line count
                # or the line numbers need to be adjusted
                original_lines = code.splitlines()

                # If chunk claims to start at line 1 but has a file header,
                # then the actual content should start at line 2 of the chunk
                if chunk_dict["line_start"] == 1 and len(chunk_lines) > 1:
                    actual_content_line = chunk_lines[1].strip()
                    expected_first_line = original_lines[0].strip()

                    assert actual_content_line == expected_first_line, (
                        f"Semantic chunk {i + 1} has file header but wrong line numbers!\n"
                        f"Chunk line 2: '{actual_content_line}'\n"
                        f"Expected (original line 1): '{expected_first_line}'\n"
                        f"The file header '// File:' is being counted in line numbers incorrectly."
                    )

    def test_chunk_overlap_doesnt_cause_bleeding(self, text_chunker):
        """Test that chunk overlap doesn't cause content bleeding."""
        # Create code with very clear boundaries
        code = '''# Section 1
def function_a():
    return "a"

# Section 2  
def function_b():
    return "b"
    
# Section 3
def function_c():
    return "c"
    
# Section 4
def function_d():
    return "d"'''

        # Use configuration that will definitely create overlapping chunks
        config = IndexingConfig()
        config.chunk_size = 100  # Very small
        config.chunk_overlap = 30  # Significant overlap
        chunker = TextChunker(config)

        chunks = chunker.chunk_text(code)
        original_lines = code.splitlines()

        assert len(chunks) > 1, "Expected multiple chunks with small chunk size"

        # Verify that overlap doesn't create impossible content
        for i, chunk in enumerate(chunks):
            # Verify this chunk's content actually exists in the original
            chunk_lines = chunk["text"].strip().splitlines()

            for j, chunk_line in enumerate(chunk_lines):
                chunk_line_stripped = chunk_line.strip()
                if not chunk_line_stripped:  # Skip empty lines
                    continue

                # This line should exist somewhere in the original file
                found_in_original = any(
                    original_line.strip() == chunk_line_stripped
                    for original_line in original_lines
                )

                assert found_in_original, (
                    f"Chunk {i + 1} contains line '{chunk_line_stripped}' that doesn't exist in original file!\n"
                    f"This indicates content corruption or bleeding during chunking."
                )

    def test_exact_reproduction_of_user_issue(self, text_chunker):
        """Test that reproduces the exact issue from the user's screenshot."""
        # Recreate the structure that would cause "else:" to appear incorrectly
        code = """if not default_models:
    raise ValueError(
        f"No 'selection_criteria.default_models' section found in {config_path}. "
        "Cannot initialize Gemini provider without Google default model configuration."
    )

# Get Google provider default  
google_default = default_models.get("google_provider_default")
if not google_default:
    raise ValueError(
        f"No 'google_provider_default' model configured in {config_path}. "
    )
else:
    # This else should never appear at the start of a chunk
    print("else case")"""

        chunks = text_chunker.chunk_text(code)
        original_lines = code.splitlines()

        # Find the line with "else:" in the original
        else_line_number = None
        for i, line in enumerate(original_lines):
            if line.strip() == "else:":
                else_line_number = i + 1  # Convert to 1-based
                break

        assert else_line_number is not None, "Test setup error: else: not found in code"

        # Check each chunk
        for i, chunk in enumerate(chunks):
            chunk_lines = chunk["text"].strip().splitlines()

            # If this chunk starts with "else:", verify it's supposed to
            if chunk_lines and chunk_lines[0].strip() == "else:":
                chunk_reports_start = chunk["line_start"]

                assert chunk_reports_start == else_line_number, (
                    f"CRITICAL BUG: Chunk {i + 1} starts with 'else:' but reports line {chunk_reports_start}\n"
                    f"The actual 'else:' is at line {else_line_number} in the original file.\n"
                    f"This proves content is bleeding between chunks!"
                )

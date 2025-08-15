"""
Tests for chunker docstring handling fix.

This test module ensures that the text chunker properly handles Python docstrings
and creates meaningful chunks instead of tiny fragments.
"""

from pathlib import Path
import tempfile
from code_indexer.indexing.chunker import TextChunker
from code_indexer.config import IndexingConfig


class TestChunkerDocstringFix:
    """Test the chunker's improved docstring handling."""

    def setup_method(self):
        """Set up test fixtures."""
        # Use a reasonable chunk size for testing
        self.config = IndexingConfig(chunk_size=1500, chunk_overlap=150)
        self.chunker = TextChunker(self.config)

    def test_docstring_not_split_into_tiny_fragments(self):
        """Test that docstrings don't get split into tiny 34-byte fragments."""
        # This reproduces the actual chunking behavior that creates tiny fragments
        # Based on real files that create 34-byte and 31-byte chunks
        python_code = '''"""
Claude Code SDK integration service for RAG-based code analysis.

This module provides intelligent code analysis using semantic search results.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class ClaudeIntegrationService:
    """Service for integrating Claude Code SDK with semantic search results."""

    def __init__(self, codebase_dir: Path):
        """Initialize the Claude integration service.

        Args:
            codebase_dir: Root directory of the codebase
        """
        self.codebase_dir = Path(codebase_dir)

    def create_analysis_prompt(self, user_query: str) -> str:
        """Create an optimized prompt for Claude analysis.

        Args:
            user_query: The user's question about the code

        Returns:
            Formatted prompt string for Claude
        """
        return f"Analyze this code: {user_query}"


def standalone_function():
    """Another function."""
    pass


def another_function_that_might_create_fragments():
    """This function might create split fragments."""
    return True
'''

        # Test with the actual file chunking method to match real behavior
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(python_code)
            temp_path = Path(f.name)

        try:
            # Use chunk_file to match the exact behavior from the failing test
            chunks = self.chunker.chunk_file(temp_path)

            # This should FAIL initially - we expect the current chunker to create tiny fragments
            print(f"DEBUG: Number of chunks created: {len(chunks)}")
            for i, chunk in enumerate(chunks):
                print(f"DEBUG: Chunk {i}: size={chunk['size']} bytes")
                print(f"  Content preview: {repr(chunk['text'][:100])}")

            # Verify no tiny fragments are created (this is the fix we want)
            tiny_chunks = [chunk for chunk in chunks if chunk["size"] < 100]
            if tiny_chunks:
                print(f"Found {len(tiny_chunks)} tiny chunks:")
                for chunk in tiny_chunks:
                    print(f"  Size: {chunk['size']}, Content: {repr(chunk['text'])}")

            assert (
                len(tiny_chunks) == 0
            ), f"Found {len(tiny_chunks)} tiny chunks under 100 bytes"

            # Verify chunks contain meaningful content
            for chunk in chunks:
                content = chunk["text"].strip()
                # Each chunk should contain substantial content, not just delimiters
                assert (
                    len(content) >= 100
                ), f"Chunk too small ({len(content)} chars): {repr(content[:50])}"

                # Should not be just docstring delimiters or keywords
                problematic_content = [
                    '// File: test.py\n"""',
                    "// File: test.py\ndef",
                    '"""',
                    "'''",
                    "def",
                ]
                assert (
                    content not in problematic_content
                ), f"Chunk should not be just delimiter/keyword: {repr(content)}"
        finally:
            temp_path.unlink()

    def test_docstring_stays_with_function(self):
        """Test that function docstrings stay together with their function definitions."""
        python_code = '''def create_analysis_prompt(self, user_query: str) -> str:
    """Create an optimized prompt for Claude analysis.

    This is a detailed docstring that explains what the function does.
    It has multiple lines and should stay with the function.

    Args:
        user_query: The user's question about the code

    Returns:
        Formatted prompt string for Claude
    """
    # Implementation starts here
    prompt = f"Analyze this code: {user_query}"
    return prompt

def another_function():
    """Another function with its own docstring."""
    return "test"
'''

        chunks = self.chunker.chunk_text(python_code, Path("test.py"))

        # Should create chunks where docstrings stay with their functions
        function_chunks = []
        for chunk in chunks:
            if "create_analysis_prompt" in chunk["text"]:
                function_chunks.append(chunk)

        # Should find the function with its docstring in at least one chunk
        assert len(function_chunks) > 0, "Should find chunks containing the function"

        # At least one chunk should contain both the function definition AND its docstring
        complete_function_chunks = []
        for chunk in function_chunks:
            content = chunk["text"]
            if (
                "def create_analysis_prompt" in content
                and "Create an optimized prompt" in content
                and "Args:" in content
            ):
                complete_function_chunks.append(chunk)

        assert (
            len(complete_function_chunks) > 0
        ), "Function docstring should stay with function definition"

    def test_class_docstring_stays_with_class(self):
        """Test that class docstrings stay together with their class definitions."""
        python_code = '''class ClaudeIntegrationService:
    """Service for integrating Claude Code SDK with semantic search results.
    
    This class provides comprehensive integration between Claude AI and 
    semantic search capabilities for intelligent code analysis.
    
    Attributes:
        codebase_dir: Root directory of the codebase
        context_extractor: Extracts relevant code contexts
    """

    def __init__(self, codebase_dir: Path):
        """Initialize the service."""
        self.codebase_dir = codebase_dir

    def method_one(self):
        """First method."""
        pass
'''

        chunks = self.chunker.chunk_text(python_code, Path("test.py"))

        # Should find class definition with its docstring together
        class_chunks = []
        for chunk in chunks:
            content = chunk["text"]
            if (
                "class ClaudeIntegrationService" in content
                and "Service for integrating Claude" in content
                and "Attributes:" in content
            ):
                class_chunks.append(chunk)

        assert (
            len(class_chunks) > 0
        ), "Class docstring should stay with class definition"

    def test_module_docstring_handling(self):
        """Test that module-level docstrings are handled properly."""
        python_code = '''"""
Module-level docstring explaining the entire module.

This is a comprehensive description of what this module does
and how it should be used. It's important context.
"""

import os
import sys

def first_function():
    """First function in the module."""
    return "test"
'''

        chunks = self.chunker.chunk_text(python_code, Path("test.py"))

        # Module docstring should not be a tiny fragment
        module_docstring_chunks = []
        for chunk in chunks:
            if "Module-level docstring" in chunk["text"]:
                module_docstring_chunks.append(chunk)

        assert len(module_docstring_chunks) > 0, "Should find module docstring"

        for chunk in module_docstring_chunks:
            # Should be substantial, not just the opening """
            assert (
                chunk["size"] > 100
            ), f"Module docstring chunk too small: {chunk['size']} bytes"
            assert (
                "comprehensive description" in chunk["text"]
            ), "Should contain full docstring content"

    def test_no_empty_or_whitespace_only_chunks(self):
        """Test that no empty or whitespace-only chunks are created."""
        python_code = '''"""Module docstring."""

import logging


class TestClass:
    """Class docstring."""
    
    def method(self):
        """Method docstring."""
        pass
'''

        chunks = self.chunker.chunk_text(python_code, Path("test.py"))

        for chunk in chunks:
            content = chunk["text"].strip()
            assert len(content) > 0, "Should not create empty chunks"
            assert content != "", "Should not create whitespace-only chunks"

            # Should contain actual meaningful content
            meaningful_content = any(
                keyword in content.lower()
                for keyword in [
                    "def",
                    "class",
                    "import",
                    "return",
                    "if",
                    "for",
                    "while",
                ]
            )
            docstring_content = '"""' in content or "'''" in content

            assert (
                meaningful_content or docstring_content
            ), f"Chunk should contain meaningful content: {repr(content[:100])}"

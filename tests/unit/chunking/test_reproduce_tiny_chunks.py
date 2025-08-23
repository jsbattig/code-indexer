"""
Test to reproduce the exact tiny chunk problem observed in real files.
"""

import tempfile
from pathlib import Path
from code_indexer.indexing.chunker import TextChunker
from code_indexer.config import IndexingConfig


def test_reproduce_34_byte_chunk_problem():
    """Test that reproduces the exact 34-byte chunk problem from claude_integration.py."""

    # Create a very long file that will force aggressive chunking
    # This simulates the structure that leads to the tiny chunks
    python_code = (
        '''"""
Claude Code SDK integration service for RAG-based code analysis.

Provides intelligent code analysis using semantic search results and Claude AI.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# Very long content to force chunking
'''
        + '''

class ClaudeIntegrationService:
    """Service for integrating Claude Code SDK with semantic search results."""

    def __init__(self, codebase_dir: Path, project_name: str = ""):
        """Initialize the Claude integration service.

        Args:
            codebase_dir: Root directory of the codebase
            project_name: Name of the project for context
        """
        self.codebase_dir = Path(codebase_dir)
        self.project_name = project_name

    def create_analysis_prompt(self, user_query: str, contexts: List, project_info: Optional[Dict] = None, enable_exploration: bool = True) -> str:
        """Create an optimized prompt for Claude analysis.

        Args:
            user_query: The user's question about the code
            contexts: List of extracted code contexts
            project_info: Optional project metadata (git info, etc.)
            enable_exploration: Whether to encourage file exploration

        Returns:
            Formatted prompt string for Claude
        """
        # Long implementation
        return "test"
'''
        * 20
    )  # Repeat the class content 20 times to make it long enough to force chunking

    config = IndexingConfig(
        chunk_size=1500, chunk_overlap=150
    )  # Use realistic chunk size
    chunker = TextChunker(config)

    # Create a temporary file to test actual file chunking
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(python_code)
        temp_path = Path(f.name)

    try:
        # Use chunk_file to match the exact real-world behavior
        chunks = chunker.chunk_file(temp_path)

        print(f"DEBUG: Number of chunks created: {len(chunks)}")

        # Look for tiny chunks
        tiny_chunks = []
        for i, chunk in enumerate(chunks):
            if chunk["size"] < 100:
                tiny_chunks.append(chunk)
                print(f"TINY CHUNK {i}: size={chunk['size']} bytes")
                print(f"  Content: {repr(chunk['text'])}")

        # This test should FAIL initially, showing the tiny chunk problem exists
        assert (
            len(tiny_chunks) == 0
        ), f"Found {len(tiny_chunks)} tiny chunks: {[c['text'] for c in tiny_chunks]}"

    finally:
        temp_path.unlink()


def test_reproduce_31_byte_def_chunk_problem():
    """Test that reproduces the 31-byte 'def' chunk problem."""

    # Create content that triggers splitting on 'def' keywords
    python_code = (
        '''"""
Test module with many function definitions.
"""

import pytest
from .infrastructure import create_fast_e2e_setup

'''
        + '''

def test_function_one():
    """Test function one."""
    pass


def test_function_two():
    """Test function two."""  
    pass


def another_test():
    """Another test."""
    return True


def yet_another_function():
    """Yet another function."""
    return False
'''
        * 30
    )  # Repeat many times to force chunking

    config = IndexingConfig(chunk_size=1500, chunk_overlap=150)
    chunker = TextChunker(config)

    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(python_code)
        temp_path = Path(f.name)

    try:
        chunks = chunker.chunk_file(temp_path)

        print(f"DEBUG: Number of chunks created: {len(chunks)}")

        # Look for tiny chunks with just 'def'
        def_chunks = []
        for i, chunk in enumerate(chunks):
            content = chunk["text"].strip()
            if (
                chunk["size"] < 100
                or content.endswith("def")
                or content == f"// File: {temp_path.name}\ndef"
            ):
                def_chunks.append(chunk)
                print(f"DEF CHUNK {i}: size={chunk['size']} bytes")
                print(f"  Content: {repr(chunk['text'])}")

        # This test should FAIL initially, showing def chunks are being created
        assert len(def_chunks) == 0, f"Found {len(def_chunks)} problematic def chunks"

    finally:
        temp_path.unlink()


if __name__ == "__main__":
    # Run directly to debug
    test_reproduce_34_byte_chunk_problem()
    test_reproduce_31_byte_def_chunk_problem()

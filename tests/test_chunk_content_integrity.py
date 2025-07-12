#!/usr/bin/env python3
"""
Tests for complete chunk content integrity.

This test suite verifies that chunks contain ONLY the content they should contain,
with no bleeding from adjacent chunks, especially in error handling scenarios.
"""

import pytest
from code_indexer.config import IndexingConfig
from code_indexer.indexing.chunker import TextChunker
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestChunkContentIntegrity:
    """Test complete chunk content integrity and correctness."""

    @pytest.fixture
    def config(self):
        """Create test configuration with small chunks to force splitting."""
        config = IndexingConfig()
        config.chunk_size = 500  # Small to force multiple chunks
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

    def _extract_expected_content(self, original_lines, start_line, end_line):
        """Extract the exact content that should be in a chunk based on line numbers."""
        # Convert to 0-based indices
        start_idx = start_line - 1
        end_idx = end_line - 1

        if start_idx < 0 or end_idx >= len(original_lines):
            return None

        return "\n".join(original_lines[start_idx : end_idx + 1])

    def test_chunk_contains_only_expected_content(self, text_chunker):
        """Test that each chunk contains EXACTLY the content from its reported line range."""
        code = """import os
import sys
from typing import List, Dict

def process_data(items: List[Dict]) -> Dict:
    '''Process a list of items and return statistics.'''
    if not items:
        raise ValueError(
            "Cannot process empty list. "
            "Please provide at least one item to process."
        )
    
    total = 0
    errors = []
    
    for i, item in enumerate(items):
        try:
            if 'value' not in item:
                raise KeyError(
                    f"Item at index {i} missing required 'value' field. "
                    f"Got keys: {list(item.keys())}"
                )
            
            value = item['value']
            if not isinstance(value, (int, float)):
                raise TypeError(
                    f"Invalid type for item {i}: expected int or float, "
                    f"got {type(value).__name__}"
                )
            
            total += value
            
        except (KeyError, TypeError) as e:
            errors.append({
                'index': i,
                'error': str(e),
                'item': item
            })
    
    if errors:
        error_summary = "\\n".join([
            f"  - Item {err['index']}: {err['error']}"
            for err in errors
        ])
        raise ValueError(
            f"Processing failed with {len(errors)} errors:\\n"
            f"{error_summary}"
        )
    
    return {
        'count': len(items),
        'total': total,
        'average': total / len(items) if items else 0
    }

def validate_config(config: Dict) -> None:
    '''Validate configuration dictionary.'''
    required_fields = ['host', 'port', 'timeout']
    missing = [field for field in required_fields if field not in config]
    
    if missing:
        raise ValueError(
            f"Configuration missing required fields: {missing}. "
            f"Please ensure all of the following are present: {required_fields}"
        )
    
    if not isinstance(config['port'], int) or config['port'] <= 0:
        raise ValueError(
            f"Invalid port number: {config['port']}. "
            "Port must be a positive integer."
        )

class DataProcessor:
    '''A class that processes data with extensive error handling.'''
    
    def __init__(self, config: Dict):
        validate_config(config)
        self.config = config
        self.processed_count = 0
        
    def process_batch(self, batch: List[Dict]) -> List[Dict]:
        '''Process a batch of items.'''
        if not batch:
            raise ValueError(
                "Cannot process empty batch. "
                "Batch must contain at least one item. "
                "If you have no items to process, skip calling this method."
            )
        
        results = []
        for item in batch:
            try:
                result = self._process_single(item)
                results.append(result)
                self.processed_count += 1
            except Exception as e:
                # Log error and continue
                print(f"Error processing item: {e}")
                raise RuntimeError(
                    f"Failed to process item after {self.processed_count} successful items. "
                    f"Error details: {str(e)}. "
                    f"Item data: {item}"
                ) from e
        
        return results
    
    def _process_single(self, item: Dict) -> Dict:
        '''Process a single item.'''
        if 'id' not in item:
            raise KeyError(
                "Item missing required 'id' field. "
                "Every item must have a unique identifier."
            )
        
        # Simulate processing
        return {
            'id': item['id'],
            'processed': True,
            'timestamp': '2024-01-01'
        }"""

        original_lines = code.splitlines()
        chunks = text_chunker.chunk_text(code)

        assert len(chunks) > 1, "Expected multiple chunks for this large code"

        # For each chunk, verify its content EXACTLY matches the expected range
        for i, chunk in enumerate(chunks):
            chunk_text = chunk["text"]
            start_line = chunk["line_start"]
            end_line = chunk["line_end"]

            # Extract what should be in this chunk
            expected_content = self._extract_expected_content(
                original_lines, start_line, end_line
            )

            # Normalize for comparison (handle trailing newlines)
            chunk_text_normalized = chunk_text.rstrip("\n")
            expected_normalized = expected_content.rstrip("\n")

            assert chunk_text_normalized == expected_normalized, (
                f"Chunk {i+1} content doesn't match expected content!\n"
                f"Chunk reports lines {start_line}-{end_line}\n"
                f"Expected length: {len(expected_normalized)}\n"
                f"Actual length: {len(chunk_text_normalized)}\n"
                f"Content mismatch indicates bleeding or incorrect extraction"
            )

    def test_error_message_bleeding_prevention(self, text_chunker):
        """Test that multi-line error messages don't bleed between chunks."""
        # Code with multiple multi-line error messages
        code = '''def function_one():
    """First function with error handling."""
    if condition_one:
        raise ValueError(
            "This is a multi-line error message that should stay together. "
            "It continues on this line and should not bleed into other chunks. "
            "The error provides detailed context about what went wrong."
        )
    return "success"

def function_two():
    """Second function with different error."""
    if condition_two:
        raise TypeError(
            "Another multi-line error that is completely different. "
            "This error belongs to function_two only. "
            "It should never appear in chunks containing function_one."
        )
    else:
        # This else block should not bleed
        return "fallback"

def function_three():
    """Third function to ensure proper boundaries."""
    try:
        dangerous_operation()
    except Exception as e:
        raise RuntimeError(
            f"Operation failed with error: {e}. "
            "This is a comprehensive error message that provides context. "
            "It should remain within function_three's chunk only."
        ) from e
    return "completed"'''

        chunks = text_chunker.chunk_text(code)
        original_lines = code.splitlines()

        # Verify no chunk contains content from functions it shouldn't
        for i, chunk in enumerate(chunks):
            chunk_text = chunk["text"]

            # Check for bleeding - these combinations should never appear in same chunk
            # unless they're actually adjacent in the reported line range
            forbidden_combinations = [
                ("function_one", "This error belongs to function_two"),
                (
                    "function_two",
                    "This is a multi-line error message that should stay together",
                ),
                ("function_one", "Operation failed with error"),
                (
                    "function_three",
                    "Another multi-line error that is completely different",
                ),
            ]

            for func_name, error_fragment in forbidden_combinations:
                if func_name in chunk_text and error_fragment in chunk_text:
                    # Verify this combination actually exists in the reported line range
                    expected_content = self._extract_expected_content(
                        original_lines, chunk["line_start"], chunk["line_end"]
                    )

                    # If both appear in chunk but not in expected content, we have bleeding
                    if not (
                        func_name in expected_content
                        and error_fragment in expected_content
                    ):
                        pytest.fail(
                            f"Content bleeding detected in chunk {i+1}!\n"
                            f"Chunk contains both '{func_name}' and '{error_fragment}'\n"
                            f"But these should not appear together based on line range {chunk['line_start']}-{chunk['line_end']}\n"
                            f"This indicates content from different functions is bleeding together"
                        )

    def test_chunk_boundaries_respect_error_blocks(self, text_chunker):
        """Test that chunk boundaries don't split error messages inappropriately."""
        code = '''def validate_user_input(data):
    """Validate user input with detailed error messages."""
    
    # Check required fields
    required = ['username', 'email', 'age']
    missing = [f for f in required if f not in data]
    
    if missing:
        # This error block should ideally stay together
        raise ValueError(
            f"Missing required fields: {missing}. "
            f"The following fields are mandatory: "
            f"- username: unique identifier for the user "
            f"- email: valid email address for communication "
            f"- age: user age for verification purposes"
        )
    
    # Validate email format
    email = data['email']
    if '@' not in email or '.' not in email.split('@')[1]:
        raise ValueError(
            f"Invalid email format: '{email}'. "
            "Email must contain @ symbol and domain with extension. "
            "Examples: user@example.com, info@company.org"
        )
    
    # Validate age
    age = data['age']
    if not isinstance(age, int) or age < 0 or age > 150:
        raise ValueError(
            f"Invalid age: {age}. "
            "Age must be a positive integer between 0 and 150."
        )
    
    return True

def process_request(request_data):
    """Process a request with comprehensive validation."""
    
    # First validation layer
    if not request_data:
        raise ValueError(
            "Empty request data received. "
            "Request must contain valid JSON payload with required fields."
        )
    
    # Validate structure
    if not isinstance(request_data, dict):
        raise TypeError(
            f"Invalid request type: {type(request_data).__name__}. "
            "Request data must be a dictionary/object, not a primitive type or list."
        )
    
    # Validate user data if present  
    if 'user' in request_data:
        validate_user_input(request_data['user'])
    
    return {"status": "processed", "data": request_data}'''

        chunks = text_chunker.chunk_text(code)

        # Check that error messages aren't awkwardly split
        for i, chunk in enumerate(chunks):
            chunk_lines = chunk["text"].splitlines()

            # Look for signs of badly split error messages
            for j, line in enumerate(chunk_lines):
                line_stripped = line.strip()

                # Check if line starts with a string continuation that might indicate bad split
                suspicious_starts = [
                    '"The following fields are mandatory:',
                    '"Email must contain @ symbol',
                    '"Age must be a positive integer',
                    '"Request must contain valid JSON',
                    '"Request data must be a dictionary',
                    'f"- username:',
                    'f"- email:',
                    'f"- age:',
                ]

                for suspicious in suspicious_starts:
                    if line_stripped.startswith(suspicious):
                        # Check if this is actually the start of the chunk (bleeding)
                        if j == 0:  # First line of chunk
                            # Verify this is actually what should be at this line
                            original_line_idx = chunk["line_start"] - 1
                            if original_line_idx < len(chunk_lines):
                                original_line = chunk_lines[original_line_idx].strip()
                                if not original_line.startswith(suspicious):
                                    pytest.fail(
                                        f"Chunk {i+1} starts with continuation of error message!\n"
                                        f"First line: '{line_stripped}'\n"
                                        f"This suggests an error message was split inappropriately\n"
                                        f"and is bleeding into this chunk"
                                    )

    def test_semantic_chunker_error_handling_integrity(self, semantic_chunker):
        """Test semantic chunker handles error blocks correctly."""
        code = '''class APIClient:
    """Client for API communication with robust error handling."""
    
    def __init__(self, base_url, timeout=30):
        if not base_url:
            raise ValueError(
                "Base URL cannot be empty. "
                "Please provide a valid API endpoint URL, "
                "for example: https://api.example.com"
            )
        
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
    
    def make_request(self, endpoint, method='GET', data=None):
        """Make an API request with comprehensive error handling."""
        
        if not endpoint:
            raise ValueError(
                "Endpoint cannot be empty. "
                "Specify the API endpoint path, e.g., '/users' or '/api/v1/data'"
            )
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            response = self._send_request(url, method, data)
            
            if response.status_code >= 400:
                raise APIError(
                    f"API request failed with status {response.status_code}. "
                    f"URL: {url}, Method: {method}. "
                    f"Response: {response.text[:200]}..."
                )
                
            return response.json()
            
        except ConnectionError as e:
            raise APIError(
                f"Failed to connect to API at {url}. "
                "Please check your network connection and ensure the API is accessible. "
                f"Original error: {str(e)}"
            ) from e
        
        except TimeoutError as e:
            raise APIError(
                f"Request to {url} timed out after {self.timeout} seconds. "
                "The API might be slow or unresponsive. "
                "Consider increasing the timeout or retrying later."
            ) from e
    
    def _send_request(self, url, method, data):
        """Internal method to send HTTP request."""
        # Simulated implementation
        pass

class APIError(Exception):
    """Custom exception for API-related errors."""
    pass'''

        chunks = semantic_chunker.chunk_content(code, "api_client.py")

        # Verify each chunk is self-contained and complete
        for i, chunk in enumerate(chunks):
            chunk_dict = chunk if isinstance(chunk, dict) else chunk.to_dict()
            chunk_text = chunk_dict["text"]

            # Check that error messages are complete within their semantic boundaries
            if "raise ValueError(" in chunk_text:
                # Ensure the complete error message is in the chunk
                assert '")' in chunk_text or ")" in chunk_text, (
                    f"Semantic chunk {i+1} contains incomplete error message!\n"
                    f"Chunk type: {chunk_dict.get('semantic_type', 'unknown')}\n"
                    f"This suggests the error was split across chunk boundaries"
                )

            if "raise APIError(" in chunk_text:
                # Check for complete error block
                # Find all occurrences of "raise APIError("
                raise_positions = []
                search_text = chunk_text
                pos = 0
                while True:
                    idx = search_text.find("raise APIError(", pos)
                    if idx == -1:
                        break
                    raise_positions.append(idx)
                    pos = idx + 1

                # Check each raise statement
                for idx in raise_positions:
                    # Find the matching closing parenthesis
                    open_count = (
                        1  # We already have the opening paren from "raise APIError("
                    )
                    found_closing = False
                    j = idx + len("raise APIError(")

                    while j < len(chunk_text):
                        if chunk_text[j] == "(":
                            open_count += 1
                        elif chunk_text[j] == ")":
                            open_count -= 1
                            if open_count == 0:
                                found_closing = True
                                break
                        j += 1

                    assert found_closing, (
                        f"Semantic chunk {i+1} contains incomplete APIError!\n"
                        f"The error message appears to be split across chunk boundaries"
                    )

    def test_no_phantom_content_in_chunks(self, text_chunker):
        """Test that chunks don't contain phantom content that doesn't exist in original."""
        code = '''def main():
    """Main entry point."""
    try:
        result = process_data()
        print(f"Success: {result}")
    except Exception as e:
        print(f"Failed: {e}")
        raise
    finally:
        cleanup()

def process_data():
    """Process some data."""
    data = load_data()
    if not data:
        return None
    
    transformed = transform(data)
    validated = validate(transformed)
    
    return validated

def cleanup():
    """Clean up resources."""
    print("Cleaning up...")
    # Cleanup code here
    pass'''

        chunks = text_chunker.chunk_text(code)
        original_text = code

        # Verify no phantom content appears
        phantom_strings = [
            "else:",  # Should not appear unless actually in code
            "except:",  # Should not appear without proper context
            "elif",  # Not in this code at all
            "TODO",  # Not in this code
            "FIXME",  # Not in this code
        ]

        for i, chunk in enumerate(chunks):
            chunk_text = chunk["text"]

            for phantom in phantom_strings:
                if phantom in chunk_text:
                    # Verify it actually exists in the original at this location
                    if phantom not in original_text:
                        pytest.fail(
                            f"Chunk {i+1} contains phantom content '{phantom}' "
                            f"that doesn't exist in the original file!\n"
                            f"This indicates content generation or corruption bug"
                        )
                    else:
                        # If it exists in original, verify it's in the right position
                        chunk_start_char = original_text.find(chunk_text)
                        phantom_in_chunk_pos = chunk_text.find(phantom)
                        phantom_in_original_pos = original_text.find(phantom)

                        # The phantom string should appear at the same relative position
                        expected_pos = phantom_in_original_pos - chunk_start_char

                        # Allow some tolerance for whitespace differences
                        assert abs(phantom_in_chunk_pos - expected_pos) < 10, (
                            f"Chunk {i+1} contains '{phantom}' at wrong position!\n"
                            f"Expected at position ~{expected_pos}, found at {phantom_in_chunk_pos}\n"
                            f"This suggests content misalignment or bleeding"
                        )

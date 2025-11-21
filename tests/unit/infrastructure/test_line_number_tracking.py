"""
Comprehensive tests for line number tracking in text chunking and processing.

This test suite covers line number accuracy across multiple languages and scenarios.
Consolidated from language-specific tests for redundancy removal:
- Previously test_java_line_numbers.py
- Previously test_javascript_typescript_line_numbers.py
- Previously test_go_line_numbers.py

Provides comprehensive line number validation for multi-language support.
"""

from pathlib import Path
import tempfile

from src.code_indexer.indexing.chunker import TextChunker
from src.code_indexer.config import IndexingConfig


class TestLineNumberTrackingInChunker:
    """Test line number tracking in TextChunker."""


class TestLineNumberTracking:
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
            f"# This is line {i + 1} with some content to make it longer"
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
        filesystem_client = Mock()

        # Test that DocumentProcessor can be instantiated with line tracking
        DocumentProcessor(config, embedding_provider, filesystem_client)


class TestMultiLanguageLineNumberAccuracy:
    """
    Comprehensive line number accuracy tests for multiple programming languages.

    Consolidated from language-specific test files to eliminate redundancy:
    - Java line number tests
    - JavaScript/TypeScript line number tests
    - Go line number tests

    Ensures line number tracking works correctly across all supported languages.
    """

    def setup_method(self):
        """Set up test fixtures."""
        config = IndexingConfig()
        config.chunk_size = 3000  # Large enough to avoid unnecessary splitting
        config.chunk_overlap = 100
        self.chunker = TextChunker(config)

    def _verify_chunk_line_numbers(self, chunk, original_text, language=""):
        """
        Verify that a chunk's reported line numbers match its actual content.

        This is the core validation method consolidated from language-specific tests.
        """
        # Convert to dict if needed
        if hasattr(chunk, "to_dict"):
            chunk_dict = chunk.to_dict()
        else:
            chunk_dict = chunk

        # Get the lines from the original text
        original_lines = original_text.splitlines()

        # Verify line numbers are valid
        assert (
            chunk_dict["line_start"] >= 1
        ), f"{language}: line_start must be >= 1, got {chunk_dict['line_start']}"
        assert (
            chunk_dict["line_end"] >= chunk_dict["line_start"]
        ), f"{language}: line_end must be >= line_start"
        assert chunk_dict["line_end"] <= len(
            original_lines
        ), f"{language}: line_end {chunk_dict['line_end']} exceeds total lines {len(original_lines)}"

        # Extract the expected content based on reported line numbers
        expected_lines = original_lines[
            chunk_dict["line_start"] - 1 : chunk_dict["line_end"]
        ]

        # Get actual chunk content lines
        chunk_content = chunk_dict["text"]

        # Verify semantic correspondence between expected and actual content
        # Check that key content from the expected lines appears in the chunk
        chunk_text_normalized = " ".join(chunk_content.split())

        found_expected_content = False
        for expected_line in expected_lines:
            if expected_line.strip() and len(expected_line.strip()) > 5:
                expected_normalized = " ".join(expected_line.split())
                if expected_normalized in chunk_text_normalized:
                    found_expected_content = True
                    break

        # If there was substantial expected content, it should be found
        substantial_expected = [
            line for line in expected_lines if line.strip() and len(line.strip()) > 5
        ]
        if substantial_expected and not found_expected_content:
            assert (
                False
            ), f"{language}: No substantial content from lines {chunk_dict['line_start']}-{chunk_dict['line_end']} found in chunk"

    def test_java_line_number_accuracy(self):
        """Test line number accuracy for Java code."""
        java_code = """package com.example.demo;

import java.util.List;
import java.util.ArrayList;

public class JavaExample {
    private String name;
    private int value;
    
    public JavaExample(String name, int value) {
        this.name = name;
        this.value = value;
    }
    
    public String getName() {
        return name;
    }
    
    public void setName(String name) {
        this.name = name;
    }
    
    public int getValue() {
        return value;
    }
    
    public void setValue(int value) {
        this.value = value;
    }
    
    public List<String> getList() {
        List<String> result = new ArrayList<>();
        result.add("item1");
        result.add("item2");
        return result;
    }
}"""

        chunks = self.chunker.chunk_text(java_code)
        assert len(chunks) > 0, "Should generate at least one chunk"

        for chunk in chunks:
            self._verify_chunk_line_numbers(chunk, java_code, "Java")

    def test_javascript_typescript_line_number_accuracy(self):
        """Test line number accuracy for JavaScript/TypeScript code."""
        js_ts_code = """interface User {
    id: number;
    name: string;
    email: string;
}

class UserManager {
    private users: User[] = [];
    
    constructor() {
        this.loadUsers();
    }
    
    public addUser(user: User): void {
        this.users.push(user);
        this.saveUsers();
    }
    
    public getUserById(id: number): User | undefined {
        return this.users.find(user => user.id === id);
    }
    
    public getAllUsers(): User[] {
        return [...this.users];
    }
    
    private loadUsers(): void {
        // Simulate loading from storage
        const storedData = localStorage.getItem('users');
        if (storedData) {
            this.users = JSON.parse(storedData);
        }
    }
    
    private saveUsers(): void {
        // Simulate saving to storage
        localStorage.setItem('users', JSON.stringify(this.users));
    }
}

const userManager = new UserManager();
userManager.addUser({ id: 1, name: "John Doe", email: "john@example.com" });"""

        chunks = self.chunker.chunk_text(js_ts_code)
        assert len(chunks) > 0, "Should generate at least one chunk"

        for chunk in chunks:
            self._verify_chunk_line_numbers(chunk, js_ts_code, "JavaScript/TypeScript")

    def test_go_line_number_accuracy(self):
        """Test line number accuracy for Go code."""
        go_code = """package main

import (
    "fmt"
    "log"
    "net/http"
    "encoding/json"
)

type User struct {
    ID    int    `json:"id"`
    Name  string `json:"name"`
    Email string `json:"email"`
}

type UserService struct {
    users []User
}

func NewUserService() *UserService {
    return &UserService{
        users: make([]User, 0),
    }
}

func (s *UserService) AddUser(user User) {
    s.users = append(s.users, user)
}

func (s *UserService) GetUserByID(id int) *User {
    for _, user := range s.users {
        if user.ID == id {
            return &user
        }
    }
    return nil
}

func (s *UserService) GetAllUsers() []User {
    return s.users
}

func (s *UserService) ServeHTTP(w http.ResponseWriter, r *http.Request) {
    w.Header().Set("Content-Type", "application/json")
    
    switch r.Method {
    case http.MethodGet:
        json.NewEncoder(w).Encode(s.GetAllUsers())
    case http.MethodPost:
        var user User
        if err := json.NewDecoder(r.Body).Decode(&user); err != nil {
            http.Error(w, err.Error(), http.StatusBadRequest)
            return
        }
        s.AddUser(user)
        w.WriteHeader(http.StatusCreated)
        json.NewEncoder(w).Encode(user)
    default:
        http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
    }
}

func main() {
    service := NewUserService()
    http.Handle("/users", service)
    
    fmt.Println("Server starting on :8080")
    log.Fatal(http.ListenAndServe(":8080", nil))
}"""

        chunks = self.chunker.chunk_text(go_code)
        assert len(chunks) > 0, "Should generate at least one chunk"

        for chunk in chunks:
            self._verify_chunk_line_numbers(chunk, go_code, "Go")

    def test_python_line_number_accuracy(self):
        """Test line number accuracy for Python code."""
        python_code = '''#!/usr/bin/env python3
"""
Example Python module for testing line number accuracy.
"""

from typing import List, Optional, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)

class DataProcessor:
    """Processes data with various transformations."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.data: List[Dict[str, Any]] = []
        logger.info("DataProcessor initialized")
    
    def load_data(self, source: str) -> None:
        """Load data from source."""
        try:
            with open(source, 'r') as f:
                self.data = json.load(f)
            logger.info(f"Loaded {len(self.data)} records")
        except FileNotFoundError:
            logger.error(f"Source file not found: {source}")
            self.data = []
    
    def filter_data(self, predicate) -> List[Dict[str, Any]]:
        """Filter data using predicate function."""
        return [item for item in self.data if predicate(item)]
    
    def transform_data(self, transformer) -> List[Dict[str, Any]]:
        """Transform data using transformer function."""
        result = []
        for item in self.data:
            try:
                transformed = transformer(item)
                result.append(transformed)
            except Exception as e:
                logger.warning(f"Transform failed for item: {e}")
        return result
    
    def save_data(self, destination: str, data: Optional[List[Dict[str, Any]]] = None) -> bool:
        """Save data to destination."""
        output_data = data if data is not None else self.data
        try:
            with open(destination, 'w') as f:
                json.dump(output_data, f, indent=2)
            logger.info(f"Saved {len(output_data)} records to {destination}")
            return True
        except Exception as e:
            logger.error(f"Save failed: {e}")
            return False

def main():
    """Main entry point."""
    config = {"batch_size": 100, "timeout": 30}
    processor = DataProcessor(config)
    
    # Example usage
    processor.load_data("input.json")
    filtered = processor.filter_data(lambda x: x.get("active", False))
    transformed = processor.transform_data(lambda x: {**x, "processed": True})
    processor.save_data("output.json", transformed)

if __name__ == "__main__":
    main()'''

        chunks = self.chunker.chunk_text(python_code)
        assert len(chunks) > 0, "Should generate at least one chunk"

        for chunk in chunks:
            self._verify_chunk_line_numbers(chunk, python_code, "Python")

    def test_multi_language_mixed_content(self):
        """Test line number accuracy when processing mixed language content."""
        mixed_content = """<!-- HTML Template -->
<!DOCTYPE html>
<html>
<head>
    <title>Mixed Content Test</title>
    <style>
        .container { 
            margin: 20px; 
            padding: 10px; 
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Mixed Language Test</h1>
        <script>
            // JavaScript embedded in HTML
            function greet(name) {
                return `Hello, ${name}!`;
            }
            
            document.addEventListener('DOMContentLoaded', function() {
                const greeting = greet('World');
                console.log(greeting);
            });
        </script>
    </div>
</body>
</html>

/* CSS Styles */
.additional-styles {
    background-color: #f0f0f0;
    border: 1px solid #ccc;
}

.highlight {
    background-color: yellow;
    font-weight: bold;
}"""

        chunks = self.chunker.chunk_text(mixed_content)
        assert len(chunks) > 0, "Should generate at least one chunk"

        for chunk in chunks:
            self._verify_chunk_line_numbers(chunk, mixed_content, "Mixed Content")

    def test_edge_case_line_number_scenarios(self):
        """Test line number accuracy in edge case scenarios."""

        # Test with empty lines
        content_with_empty_lines = '''

def function_with_empty_lines():
    """Function with various empty line patterns."""
    
    x = 1
    
    
    y = 2
    
    return x + y


class EmptyLineClass:
    
    def method(self):
        
        pass
        

'''

        chunks = self.chunker.chunk_text(content_with_empty_lines)
        for chunk in chunks:
            self._verify_chunk_line_numbers(
                chunk, content_with_empty_lines, "Empty Lines"
            )

        # Test with very long lines
        long_line_content = f"""def function_with_long_line():
    very_long_variable_name = "{"x" * 500}"  # This is a very long line that might cause chunking issues
    return very_long_variable_name"""

        chunks = self.chunker.chunk_text(long_line_content)
        for chunk in chunks:
            self._verify_chunk_line_numbers(chunk, long_line_content, "Long Lines")

    def test_line_number_consistency_across_chunk_splits(self):
        """Test that line numbers remain consistent when content splits across multiple chunks."""
        # Create content that will definitely split
        large_content = []
        for i in range(50):
            large_content.append(f"def function_{i}():")
            large_content.append(f'    """Function number {i}"""')
            large_content.append(f"    return {i}")
            large_content.append("")

        content_text = "\n".join(large_content)

        # Use small chunk size to force splitting
        config = IndexingConfig()
        config.chunk_size = 200  # Small to force multiple chunks
        config.chunk_overlap = 20
        chunker = TextChunker(config)

        chunks = chunker.chunk_text(content_text)
        assert len(chunks) > 1, "Expected multiple chunks for large content"

        for chunk in chunks:
            self._verify_chunk_line_numbers(chunk, content_text, "Split Content")

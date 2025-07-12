"""
Tests for multi-line construct handling in semantic parsers.
Ensures that multi-line error messages and strings are kept together.
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestSemanticMultilineConstructs:
    """Test multi-line construct handling across all language parsers."""

    @pytest.fixture
    def chunker(self):
        """Create a semantic chunker with small chunk size to test splitting."""
        config = IndexingConfig(
            chunk_size=500,  # Small to force potential splits
            chunk_overlap=50,
            use_semantic_chunking=True,
        )
        return SemanticChunker(config)

    def test_python_multiline_error_messages(self, chunker):
        """Test Python parser handles multi-line error messages correctly."""
        content = dedent(
            '''
            def validate_input(data):
                """Validate user input."""
                if not data:
                    raise ValueError(
                        "Invalid input data provided. "
                        "The data dictionary must contain: "
                        "- username: a valid string "
                        "- email: a valid email address "
                        "- age: a positive integer"
                    )
                
                if "email" not in data:
                    raise KeyError(
                        f"Missing required field 'email'. "
                        f"Received fields: {list(data.keys())}. "
                        f"Please ensure all required fields are present."
                    )
                
                return True
        '''
        ).strip()

        chunks = chunker.chunk_content(content, "validator.py")

        # Should create one chunk for the function
        assert len(chunks) == 1
        chunk = chunks[0]

        # Verify the entire error messages are included
        assert "Invalid input data provided." in chunk["text"]
        assert "- age: a positive integer" in chunk["text"]
        assert "Missing required field 'email'." in chunk["text"]
        assert "Please ensure all required fields are present." in chunk["text"]

    def test_javascript_multiline_error_messages(self, chunker):
        """Test JavaScript parser handles multi-line error messages correctly."""
        content = dedent(
            """
            function processOrder(order) {
                if (!order || !order.items) {
                    throw new Error(
                        `Invalid order structure. ` +
                        `Order must contain: ` +
                        `- items: array of products ` +
                        `- customer: customer information ` +
                        `- payment: payment details`
                    );
                }
                
                if (order.items.length === 0) {
                    throw new Error(
                        "Order contains no items. " +
                        "Please add at least one item to the order " +
                        "before attempting to process it."
                    );
                }
                
                return processPayment(order);
            }
        """
        ).strip()

        chunks = chunker.chunk_content(content, "order.js")

        # Function should be in one chunk with complete error messages
        assert len(chunks) == 1
        chunk = chunks[0]

        assert "Invalid order structure." in chunk["text"]
        assert "- payment: payment details" in chunk["text"]
        assert "Order contains no items." in chunk["text"]
        assert "before attempting to process it." in chunk["text"]

    def test_java_multiline_error_messages(self, chunker):
        """Test Java parser handles multi-line error messages correctly."""
        content = dedent(
            """
            public class UserValidator {
                public void validateUser(User user) throws ValidationException {
                    if (user == null) {
                        throw new ValidationException(
                            "User object cannot be null. " +
                            "Please provide a valid User instance with: " +
                            "- username: non-empty string " +
                            "- email: valid email format " +
                            "- age: between 0 and 150"
                        );
                    }
                    
                    if (user.getEmail() == null || !user.getEmail().contains("@")) {
                        throw new ValidationException(
                            String.format(
                                "Invalid email address: '%s'. " +
                                "Email must contain @ symbol and be in format: " +
                                "username@domain.com",
                                user.getEmail()
                            )
                        );
                    }
                }
            }
        """
        ).strip()

        chunks = chunker.chunk_content(content, "UserValidator.java")

        # Java parser creates both class and method chunks
        assert len(chunks) == 2

        # Find the method chunk (which contains the actual error messages)
        method_chunk = None
        for chunk in chunks:
            if chunk["semantic_type"] == "method":
                method_chunk = chunk
                break

        assert method_chunk is not None

        # Verify the method chunk contains complete error messages
        assert "User object cannot be null." in method_chunk["text"]
        assert "- age: between 0 and 150" in method_chunk["text"]
        assert "Invalid email address:" in method_chunk["text"]
        assert "username@domain.com" in method_chunk["text"]

    def test_go_multiline_error_messages(self, chunker):
        """Test Go parser handles multi-line error messages correctly."""
        content = dedent(
            """
            func ValidateConfig(config *Config) error {
                if config == nil {
                    return fmt.Errorf(
                        "configuration cannot be nil: " +
                        "please provide a valid Config struct with " +
                        "- Host: server hostname " +
                        "- Port: valid port number (1-65535) " +
                        "- Timeout: duration in seconds"
                    )
                }
                
                if config.Port <= 0 || config.Port > 65535 {
                    return errors.New(
                        "invalid port number: " +
                        "port must be between 1 and 65535, " +
                        "commonly used ports are 80 (HTTP), 443 (HTTPS), " +
                        "8080 (development), 3000 (Node.js)"
                    )
                }
                
                return nil
            }
        """
        ).strip()

        chunks = chunker.chunk_content(content, "validator.go")

        # Function should be in one chunk with complete error messages
        assert len(chunks) == 1
        chunk = chunks[0]

        assert "configuration cannot be nil:" in chunk["text"]
        assert "- Timeout: duration in seconds" in chunk["text"]
        assert "invalid port number:" in chunk["text"]
        assert "3000 (Node.js)" in chunk["text"]

    def test_semantic_chunker_preserves_multiline_errors_in_splits(self, chunker):
        """Test that semantic chunker preserves multi-line error messages when splitting."""
        # Create a simple test with a method containing multi-line error
        content = dedent(
            '''
            class DataProcessor:
                """Process data with validation."""
                
                def __init__(self):
                    self.data = {}
                
                def validate_data(self, data):
                    """Validate input data."""
                    if not data:
                        raise ValueError(
                            "Input data cannot be empty. "
                            "Please provide a dictionary with: "
                            "- name: string identifier "
                            "- value: numeric value "
                            "- enabled: boolean flag"
                        )
                    
                    if "name" not in data:
                        raise KeyError(
                            "Missing required field 'name'. "
                            "All data items must have a name identifier."
                        )
                    
                    return True
                
                def process_data(self, data):
                    """Process validated data."""
                    if not self.validate_data(data):
                        return None
                    
                    return {
                        "processed": True,
                        "name": data["name"],
                        "value": data.get("value", 0) * 2
                    }
        '''
        ).strip()

        chunks = chunker.chunk_content(content, "processor.py")

        # Check all chunks that contain error messages have them complete
        for chunk in chunks:
            chunk_text = chunk["text"]
            # If chunk contains start of a ValueError, it should contain the whole message
            if "Input data cannot be empty." in chunk_text:
                assert "- enabled: boolean flag" in chunk_text

            # If chunk contains start of KeyError, it should contain the whole message
            if "Missing required field 'name'." in chunk_text:
                assert "All data items must have a name identifier." in chunk_text

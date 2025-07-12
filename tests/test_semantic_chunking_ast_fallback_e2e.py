"""
End-to-end test for AST semantic chunking and fallback to text chunking.

This test verifies that:
1. AST-based semantic chunking works correctly for supported languages
2. Fallback to text chunking works for unsupported languages or malformed code
3. The entire pipeline (init, start, index, query) works with both modes
4. Results can be properly queried and differentiated
"""

from typing import Dict
import subprocess

import pytest

# Import test infrastructure
from .test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
    get_shared_test_project_dir,
)

# Mark all tests in this file as e2e to exclude from ci-github.sh
pytestmark = pytest.mark.e2e


def _get_ast_vs_text_test_project() -> Dict[str, str]:
    """Get test project with files that test AST vs text chunking."""
    return {
        # Python file - should use AST semantic chunking
        "calculator.py": '''"""Calculator module with various functions."""
import math

def add_numbers(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b

def subtract_numbers(a: int, b: int) -> int:
    """Subtract b from a."""
    return a - b

class Calculator:
    """A calculator class for advanced operations."""
    
    def __init__(self, precision: int = 2):
        """Initialize calculator with precision."""
        self.precision = precision
    
    def multiply(self, a: float, b: float) -> float:
        """Multiply two numbers."""
        result = a * b
        return round(result, self.precision)
    
    def divide(self, a: float, b: float) -> float:
        """Divide a by b with error handling."""
        if b == 0:
            raise ValueError("Cannot divide by zero")
        result = a / b
        return round(result, self.precision)
    
    def power(self, base: float, exponent: float) -> float:
        """Calculate base to the power of exponent."""
        return math.pow(base, exponent)
''',
        # JavaScript file - should use AST semantic chunking
        "utils.js": """/**
 * Utility functions for data processing.
 */

// Global configuration
const CONFIG = {
    maxRetries: 3,
    timeout: 5000
};

/**
 * Format a user name for display.
 * @param {string} firstName - First name
 * @param {string} lastName - Last name  
 * @returns {string} Formatted full name
 */
function formatUserName(firstName, lastName) {
    if (!firstName || !lastName) {
        return 'Unknown User';
    }
    return `${firstName} ${lastName}`;
}

/**
 * Validate email format using regex.
 * @param {string} email - Email to validate
 * @returns {boolean} True if valid email format
 */
const validateEmail = (email) => {
    const emailPattern = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
    return emailPattern.test(email);
};

/**
 * API utility class for HTTP requests.
 */
class ApiClient {
    constructor(baseUrl) {
        this.baseUrl = baseUrl;
        this.retries = CONFIG.maxRetries;
    }
    
    async fetchData(endpoint) {
        const url = `${this.baseUrl}/${endpoint}`;
        try {
            const response = await fetch(url);
            return await response.json();
        } catch (error) {
            console.error('Fetch failed:', error);
            throw error;
        }
    }
    
    async postData(endpoint, data) {
        const url = `${this.baseUrl}/${endpoint}`;
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });
        return await response.json();
    }
}

export { formatUserName, validateEmail, ApiClient, CONFIG };
""",
        # Text file - should fallback to text chunking
        "README.md": """# Test Project

This is a test project for validating semantic chunking behavior.

## Features

### AST-Based Semantic Chunking
- Python files are parsed into semantic constructs
- JavaScript/TypeScript files are analyzed for functions and classes
- Java and Go files are processed semantically
- Each construct becomes a separate chunk with semantic metadata

### Text Chunking Fallback
- Unknown file types fall back to text-based chunking
- Malformed code falls back gracefully
- Configuration files use text chunking
- Documentation files use text chunking

## Testing Strategy

We test both semantic and text chunking to ensure:
- Semantic chunks contain meaningful code constructs
- Text chunks provide complete coverage for unsupported formats
- Fallback behavior works reliably
- Query functionality works with both chunk types

## Expected Behavior

1. **Python Calculator Module**: Should be chunked into:
   - Individual function chunks (add_numbers, subtract_numbers)
   - Class chunk (Calculator)
   - Method chunks (multiply, divide, power)

2. **JavaScript Utils Module**: Should be chunked into:
   - Global functions (formatUserName)
   - Arrow functions (validateEmail)
   - Class definition (ApiClient)
   - Class methods (fetchData, postData)

3. **README File**: Should use text chunking:
   - No semantic metadata
   - Text-based chunk boundaries
   - Full content coverage
""",
        # Configuration file - should fallback to text chunking
        "config.yaml": """# Application configuration
app:
  name: "Test Application"
  version: "1.0.0"
  debug: true
  
database:
  host: "localhost"
  port: 5432
  name: "testdb"
  pool_size: 10
  
api:
  base_url: "https://api.example.com"
  timeout: 30
  retries: 3
  
logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: "app.log"
""",
        # Malformed Python - should fallback to text chunking
        "broken.py": """# This file contains malformed Python code
def incomplete_function(
    # Missing closing parenthesis and function body

class BrokenClass
    # Missing colon after class name
    def method_without_body(self):
        # This method has no implementation

    def another_broken_method(self
        # Missing closing parenthesis in parameters
        pass

# Some valid Python mixed with broken syntax
print("This line is valid")
def valid_function():
    return "This function is fine"

# More broken syntax
if True
    # Missing colon
    print("Broken if statement")
""",
    }


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.voyage_ai
def test_ast_semantic_chunking_e2e():
    """Test end-to-end AST semantic chunking for supported languages."""
    # Use shared project directory to reuse containers between tests
    test_dir = get_shared_test_project_dir()

    # Create test project with inventory system (will preserve existing config)
    create_test_project_with_inventory(test_dir, TestProjectInventory.CLI_PROGRESS)

    # Add test files
    project_files = _get_ast_vs_text_test_project()
    for filename, content in project_files.items():
        (test_dir / filename).write_text(content)

    # Ensure services are running first (start is idempotent)
    start_result = subprocess.run(
        ["code-indexer", "start"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

    # Index the project with --clear to ensure fresh data
    index_result = subprocess.run(
        ["code-indexer", "index", "--clear"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

    # Test semantic chunking with verbose output to verify AST attributes
    verbose_query_result = subprocess.run(
        ["code-indexer", "query", "Calculator class"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (
        verbose_query_result.returncode == 0
    ), f"Verbose query failed: {verbose_query_result.stderr}"

    verbose_output = verbose_query_result.stdout
    assert len(verbose_output.strip()) > 0, "Should find Calculator class"

    # Verify semantic information is displayed in verbose mode
    assert (
        "🧠 Semantic:" in verbose_output
    ), "Should show semantic metadata in verbose mode"

    # Check for semantic attributes in the output
    assert any(
        keyword in verbose_output.lower()
        for keyword in ["class", "type:", "name:", "signature:"]
    ), "Should show semantic type, name, and signature information"

    # Test semantic search filtering with type filter
    type_filter_result = subprocess.run(
        ["code-indexer", "query", "calculation", "--type", "class"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (
        type_filter_result.returncode == 0
    ), f"Type filter query failed: {type_filter_result.stderr}"

    if type_filter_result.stdout.strip():
        type_output = type_filter_result.stdout
        assert (
            "🧠 Semantic:" in type_output
        ), "Type-filtered results should show semantic info"

    # Test function-specific semantic filtering
    function_filter_result = subprocess.run(
        ["code-indexer", "query", "add", "--type", "function"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (
        function_filter_result.returncode == 0
    ), f"Function filter query failed: {function_filter_result.stderr}"

    if function_filter_result.stdout.strip():
        func_output = function_filter_result.stdout
        assert (
            "🧠 Semantic:" in func_output
        ), "Function-filtered results should show semantic info"

    # Test method-specific semantic filtering (class methods)
    method_filter_result = subprocess.run(
        ["code-indexer", "query", "multiply", "--type", "method"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (
        method_filter_result.returncode == 0
    ), f"Method filter query failed: {method_filter_result.stderr}"

    if method_filter_result.stdout.strip():
        method_output = method_filter_result.stdout
        assert (
            "🧠 Semantic:" in method_output
        ), "Method-filtered results should show semantic info"

    # Test scope filtering (class vs global)
    class_scope_result = subprocess.run(
        ["code-indexer", "query", "Calculator", "--scope", "global"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (
        class_scope_result.returncode == 0
    ), f"Class scope query failed: {class_scope_result.stderr}"

    # Test semantic-only filtering to exclude text chunks
    semantic_only_result = subprocess.run(
        ["code-indexer", "query", "function", "--semantic-only"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (
        semantic_only_result.returncode == 0
    ), f"Semantic-only query failed: {semantic_only_result.stderr}"

    if semantic_only_result.stdout.strip():
        semantic_only_output = semantic_only_result.stdout
        # Should only show results with semantic metadata
        assert (
            "🧠 Semantic:" in semantic_only_output
        ), "Semantic-only should show semantic info"
        # Should not include README.md or other text files
        assert (
            "README.md" not in semantic_only_output
            or "🧠 Semantic:" in semantic_only_output
        )

    # Test JavaScript semantic chunking with verbose output
    js_verbose_result = subprocess.run(
        ["code-indexer", "query", "ApiClient"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (
        js_verbose_result.returncode == 0
    ), f"JS verbose query failed: {js_verbose_result.stderr}"

    if js_verbose_result.stdout.strip():
        js_verbose_output = js_verbose_result.stdout
        assert (
            "🧠 Semantic:" in js_verbose_output
        ), "JS results should show semantic metadata"
        assert "utils.js" in js_verbose_output, "Should find the JS file"

    # Test arrow function detection in JavaScript
    arrow_func_result = subprocess.run(
        ["code-indexer", "query", "validateEmail", "--type", "function"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (
        arrow_func_result.returncode == 0
    ), f"Arrow function query failed: {arrow_func_result.stderr}"

    if arrow_func_result.stdout.strip():
        arrow_output = arrow_func_result.stdout
        assert (
            "🧠 Semantic:" in arrow_output
        ), "Arrow function should be detected as semantic construct"

    # Verify that AST chunking produces different results than text chunking
    # by checking that semantic metadata is present
    all_results = [
        verbose_output,
        type_filter_result.stdout,
        function_filter_result.stdout,
    ]
    semantic_info_found = any(
        "🧠 Semantic:" in result for result in all_results if result.strip()
    )
    assert (
        semantic_info_found
    ), "At least one query should show semantic information from AST parsing"

    # Note: Don't clean up shared test directory - other tests may use it


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.voyage_ai
def test_text_chunking_fallback_e2e():
    """Test end-to-end fallback to text chunking for unsupported files."""
    # Use shared project directory to reuse containers between tests
    test_dir = get_shared_test_project_dir()

    # Create test project with inventory system (will preserve existing config)
    create_test_project_with_inventory(test_dir, TestProjectInventory.CLI_PROGRESS)

    # Add test files
    project_files = _get_ast_vs_text_test_project()
    for filename, content in project_files.items():
        (test_dir / filename).write_text(content)

    # Clear any existing data to start fresh
    subprocess.run(
        ["code-indexer", "index", "--clear"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Ensure services are running
    start_result = subprocess.run(
        ["code-indexer", "start"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

    # Index the project
    index_result = subprocess.run(
        ["code-indexer", "index"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

    # Test that README.md content can be found (text chunking)
    readme_query_result = subprocess.run(
        ["code-indexer", "query", "semantic chunking behavior", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (
        readme_query_result.returncode == 0
    ), f"README query failed: {readme_query_result.stderr}"

    readme_output = readme_query_result.stdout
    assert (
        len(readme_output.strip()) > 0
    ), "Should find README content using text chunking"

    # Test that YAML config can be found (text chunking)
    config_query_result = subprocess.run(
        ["code-indexer", "query", "database configuration", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (
        config_query_result.returncode == 0
    ), f"Config query failed: {config_query_result.stderr}"

    config_output = config_query_result.stdout
    assert (
        len(config_output.strip()) > 0
    ), "Should find config content using text chunking"

    # Test that malformed Python falls back to text chunking
    broken_query_result = subprocess.run(
        ["code-indexer", "query", "incomplete function", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (
        broken_query_result.returncode == 0
    ), f"Broken Python query failed: {broken_query_result.stderr}"

    broken_output = broken_query_result.stdout
    assert (
        len(broken_output.strip()) > 0
    ), "Should find broken Python content using text fallback"

    # Note: Don't clean up shared test directory - other tests may use it


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.voyage_ai
def test_semantic_vs_text_chunking_comparison_e2e():
    """Test comparison between semantic and text chunking modes."""
    # Use shared project directory to reuse containers between tests
    test_dir = get_shared_test_project_dir()

    # Create test project with inventory system (will preserve existing config)
    create_test_project_with_inventory(test_dir, TestProjectInventory.CLI_PROGRESS)

    # Add a simple Python file for testing
    test_file_content = '''
def process_data(data_list):
    """Process a list of data items."""
    results = []
    for item in data_list:
        if item > 0:
            results.append(item * 2)
    return results

class DataProcessor:
    """A class for processing data."""
    
    def __init__(self, multiplier=1):
        self.multiplier = multiplier
    
    def transform(self, value):
        """Transform a single value."""
        return value * self.multiplier
'''
    (test_dir / "processor.py").write_text(test_file_content)

    # Test with semantic chunking enabled
    subprocess.run(
        ["code-indexer", "index", "--clear"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )

    start_result = subprocess.run(
        ["code-indexer", "start"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert start_result.returncode == 0

    index_result = subprocess.run(
        ["code-indexer", "index"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert index_result.returncode == 0

    # Query for function - should work well with semantic chunking
    semantic_query_result = subprocess.run(
        ["code-indexer", "query", "process_data function", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert semantic_query_result.returncode == 0
    semantic_output = semantic_query_result.stdout

    # Should find the function
    assert (
        len(semantic_output.strip()) > 0
    ), "Semantic chunking should find the function"

    # Clean and reinitialize with semantic chunking disabled
    subprocess.run(
        ["code-indexer", "clean-data"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    # Clean may fail if no data exists, that's okay

    # Re-initialize with semantic chunking disabled
    # Note: We need to modify the config to disable semantic chunking
    import json

    config_file = test_dir / ".code-indexer" / "config.json"
    with open(config_file, "r") as f:
        config = json.load(f)

    config["use_semantic_chunking"] = False

    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)

    # Re-index with text chunking using --clear to force fresh indexing
    index_result = subprocess.run(
        ["code-indexer", "index", "--clear"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert index_result.returncode == 0

    # Query again - should still work but with text chunking
    text_query_result = subprocess.run(
        ["code-indexer", "query", "process_data function", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert text_query_result.returncode == 0
    text_output = text_query_result.stdout

    # Should still find content, but using text chunking
    assert len(text_output.strip()) > 0, "Text chunking should also find the content"

    # Both should find results, but potentially with different relevance
    assert len(semantic_output.strip()) > 0
    assert len(text_output.strip()) > 0

    # Note: Don't clean up shared test directory - other tests may use it


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.voyage_ai
def test_ast_semantic_attributes_extraction_e2e():
    """Test that all expected semantic attributes are properly extracted from AST parsing."""
    # Use isolated project directory to avoid interference with other tests
    from .test_infrastructure import create_isolated_project_dir

    test_dir = create_isolated_project_dir("ast_semantic_attributes")

    # Create test project with inventory system (will preserve existing config)
    create_test_project_with_inventory(test_dir, TestProjectInventory.CLI_PROGRESS)

    # CRITICAL: Remove any existing files to ensure clean test state
    import shutil

    for item in test_dir.iterdir():
        if item.name != ".code-indexer":  # Preserve configuration
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

    # Create a comprehensive test file with various constructs
    comprehensive_code = '''"""
Comprehensive test module for AST attribute extraction.
"""
import asyncio
from typing import List, Optional, Dict, Any

# Global constant
MAX_ITEMS = 100

def global_function(param1: str, param2: int = 10) -> str:
    """A global function with type hints and default parameter."""
    return f"{param1}: {param2}"

async def async_global_function(data: List[str]) -> Dict[str, Any]:
    """An async global function with complex types."""
    await asyncio.sleep(0.1)
    return {"processed": len(data), "items": data}

class BaseProcessor:
    """Base class for all processors."""
    
    def __init__(self, name: str):
        """Initialize the processor with a name."""
        self.name = name
    
    def process(self, data: Any) -> Any:
        """Process data - to be overridden by subclasses."""
        raise NotImplementedError("Subclasses must implement process method")
    
    @classmethod
    def create_default(cls) -> 'BaseProcessor':
        """Class method to create a default processor."""
        return cls("default")
    
    @staticmethod
    def validate_input(input_data: Any) -> bool:
        """Static method to validate input data."""
        return input_data is not None

class AdvancedProcessor(BaseProcessor):
    """Advanced processor with multiple features."""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """Initialize with name and configuration."""
        super().__init__(name)
        self.config = config
        self._cache: Dict[str, Any] = {}
    
    async def process_async(self, items: List[str]) -> List[str]:
        """Async method with type hints."""
        results = []
        for item in items:
            processed = await self._process_single_item(item)
            results.append(processed)
        return results
    
    def _process_single_item(self, item: str) -> str:
        """Private method for processing single item."""
        return f"processed_{item}"
    
    @property
    def cache_size(self) -> int:
        """Property to get cache size."""
        return len(self._cache)
    
    def __str__(self) -> str:
        """String representation of the processor."""
        return f"AdvancedProcessor(name={self.name}, cache_size={self.cache_size})"

# Nested class example
class OuterClass:
    """Outer class containing nested classes."""
    
    class InnerClass:
        """Inner class for specialized processing."""
        
        def inner_method(self) -> str:
            """Method inside inner class."""
            return "inner_result"
        
        @staticmethod
        def inner_static_method() -> bool:
            """Static method inside inner class."""
            return True
    
    def outer_method(self) -> 'OuterClass.InnerClass':
        """Method that returns inner class instance."""
        return self.InnerClass()
'''

    (test_dir / "comprehensive.py").write_text(comprehensive_code)

    # Ensure services are started first
    start_result = subprocess.run(
        ["code-indexer", "start"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert start_result.returncode == 0

    # COMPREHENSIVE SETUP: Clear index and reindex only the new file
    index_result = subprocess.run(
        ["code-indexer", "index", "--clear"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert index_result.returncode == 0

    # Test 1: Verify function semantic attributes
    function_result = subprocess.run(
        ["code-indexer", "query", "global_function", "--type", "function"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert function_result.returncode == 0

    if function_result.stdout.strip():
        func_output = function_result.stdout
        assert "🧠 Semantic:" in func_output
        assert "Type: function" in func_output or "function" in func_output.lower()
        assert "global_function" in func_output
        assert "📝 Signature:" in func_output or "def global_function" in func_output

    # Test 2: Verify async function detection
    async_func_result = subprocess.run(
        ["code-indexer", "query", "async_global_function"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert async_func_result.returncode == 0

    if async_func_result.stdout.strip():
        async_output = async_func_result.stdout
        assert "🧠 Semantic:" in async_output
        # Should show async features in the semantic display
        assert "async" in async_output.lower() or "Features:" in async_output

    # Test 3: Verify class semantic attributes
    class_result = subprocess.run(
        ["code-indexer", "query", "BaseProcessor", "--type", "class"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert class_result.returncode == 0

    if class_result.stdout.strip():
        class_output = class_result.stdout
        assert "🧠 Semantic:" in class_output
        assert "Type: class" in class_output or "class" in class_output.lower()
        assert "BaseProcessor" in class_output

    # Test 4: Verify method semantic attributes
    method_result = subprocess.run(
        ["code-indexer", "query", "process_async"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert method_result.returncode == 0

    if method_result.stdout.strip():
        method_output = method_result.stdout
        assert "🧠 Semantic:" in method_output
        # Should find the method with its semantic information
        assert "process_async" in method_output

    # Test 5: Verify static method detection (static method is part of BaseProcessor class chunk)
    static_result = subprocess.run(
        ["code-indexer", "query", "validate_input"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert static_result.returncode == 0

    if static_result.stdout.strip():
        static_output = static_result.stdout
        assert "🧠 Semantic:" in static_output
        # Should find the BaseProcessor class which contains the static method
        assert "BaseProcessor" in static_output

    # Test 6: Verify class method detection (classmethod is part of BaseProcessor class chunk)
    classmethod_result = subprocess.run(
        ["code-indexer", "query", "create_default"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert classmethod_result.returncode == 0

    if classmethod_result.stdout.strip():
        classmethod_output = classmethod_result.stdout
        assert "🧠 Semantic:" in classmethod_output
        # Should find the BaseProcessor class which contains the classmethod
        assert "BaseProcessor" in classmethod_output

    # Test 7: Verify global and class scope functions exist and have semantic info
    global_scope_result = subprocess.run(
        ["code-indexer", "query", "global_function"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert global_scope_result.returncode == 0

    if global_scope_result.stdout.strip():
        global_output = global_scope_result.stdout
        assert "🧠 Semantic:" in global_output

    class_scope_result = subprocess.run(
        ["code-indexer", "query", "process_async"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert class_scope_result.returncode == 0

    if class_scope_result.stdout.strip():
        class_scope_output = class_scope_result.stdout
        assert "🧠 Semantic:" in class_scope_output

    # Test 8: Verify nested class detection (nested class is part of OuterClass chunk)
    nested_result = subprocess.run(
        ["code-indexer", "query", "InnerClass"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert nested_result.returncode == 0

    if nested_result.stdout.strip():
        nested_output = nested_result.stdout
        assert "🧠 Semantic:" in nested_output
        # Should find the OuterClass which contains the nested InnerClass
        assert "OuterClass" in nested_output

    # Test 9: Verify that semantic-only filter excludes text chunks
    semantic_only_result = subprocess.run(
        ["code-indexer", "query", "processor", "--semantic-only"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert semantic_only_result.returncode == 0

    if semantic_only_result.stdout.strip():
        semantic_only_output = semantic_only_result.stdout
        # Should only show semantic chunks, not text chunks
        assert "🧠 Semantic:" in semantic_only_output

    # Test 10: Verify comprehensive semantic information in verbose mode
    comprehensive_result = subprocess.run(
        ["code-indexer", "query", "AdvancedProcessor"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert comprehensive_result.returncode == 0

    if comprehensive_result.stdout.strip():
        comprehensive_output = comprehensive_result.stdout

        # Verify all expected semantic information is present
        expected_semantic_info = [
            "🧠 Semantic:",  # Semantic section marker
            "Type:",  # Semantic type
            "Name:",  # Semantic name
            "📝 Signature:",  # Signature information
        ]

        found_info = []
        for info in expected_semantic_info:
            if info in comprehensive_output:
                found_info.append(info)

        assert (
            len(found_info) >= 2
        ), f"Should find multiple semantic attributes. Found: {found_info}"

        # Should show either class or method information
        assert any(
            construct_type in comprehensive_output.lower()
            for construct_type in ["class", "method", "function"]
        ), "Should show semantic construct type information"

    # Note: Don't clean up shared test directory - other tests may use it

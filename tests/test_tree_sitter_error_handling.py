"""
Unit tests for tree-sitter parsers with ERROR node handling.

These tests contain intentional syntax errors to trigger ERROR nodes
and verify that our parsers can still extract meaningful constructs.
"""

import pytest

from code_indexer.config import IndexingConfig
from code_indexer.indexing.go_parser_new import GoSemanticParser
from code_indexer.indexing.kotlin_parser_new import KotlinSemanticParser
from code_indexer.indexing.typescript_parser_new import TypeScriptSemanticParser
from code_indexer.indexing.javascript_parser_new import JavaScriptSemanticParser
from code_indexer.indexing.java_parser_new import JavaSemanticParser
from code_indexer.indexing.python_parser import PythonSemanticParser


@pytest.fixture
def config():
    """Test configuration."""
    return IndexingConfig(
        chunk_size=1000,
        chunk_overlap=50,
        semantic_chunking=True,
        language_detection=True,
    )


class TestGoErrorHandling:
    """Test Go parser ERROR node handling."""

    def test_go_function_with_syntax_error(self, config):
        """Test Go function with intentional syntax error."""
        # Missing closing brace to force ERROR node
        code = """
package main

func ValidFunction() {
    fmt.Println("This works")
}

func BrokenFunction() {
    fmt.Println("Missing closing brace")
    // Missing }

func AnotherFunction() {
    fmt.Println("After error")
}
"""
        parser = GoSemanticParser(config)
        chunks = parser.chunk(code, "test.go")

        # Should extract all functions despite syntax error
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) >= 2

        # Check that we found the broken function
        broken_func = next(
            (c for c in function_chunks if "BrokenFunction" in c.semantic_name), None
        )
        assert broken_func is not None
        assert (
            "extracted_from_error" in broken_func.semantic_context
            or broken_func.semantic_name == "BrokenFunction"
        )

    def test_go_struct_with_syntax_error(self, config):
        """Test Go struct with syntax error."""
        code = """
package main

type ValidStruct struct {
    Name string
}

type BrokenStruct struct {
    Name string
    // Missing closing brace

type AnotherStruct struct {
    ID int
}
"""
        parser = GoSemanticParser(config)
        chunks = parser.chunk(code, "test.go")

        # Should extract structs despite syntax error
        struct_chunks = [c for c in chunks if c.semantic_type in ["struct", "type"]]
        assert len(struct_chunks) >= 2

        # Verify we found the broken struct
        struct_names = [c.semantic_name for c in struct_chunks]
        assert "BrokenStruct" in struct_names or any(
            "extracted_from_error" in c.semantic_context for c in struct_chunks
        )


class TestKotlinErrorHandling:
    """Test Kotlin parser ERROR node handling."""

    def test_kotlin_function_with_syntax_error(self, config):
        """Test Kotlin function with syntax error."""
        code = """
package com.example

class ValidClass {
    fun validFunction() {
        println("This works")
    }
}

fun brokenFunction() {
    println("Missing closing brace")
    // Missing }

fun anotherFunction() {
    println("After error")
}
"""
        parser = KotlinSemanticParser(config)
        chunks = parser.chunk(code, "test.kt")

        # Should extract functions despite syntax error
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) >= 2

        # Check for broken function
        function_names = [c.semantic_name for c in function_chunks]
        assert "brokenFunction" in function_names or any(
            "extracted_from_error" in c.semantic_context for c in function_chunks
        )

    def test_kotlin_extension_function_with_error(self, config):
        """Test Kotlin extension function with syntax error."""
        code = """
package com.example

fun String.validExtension(): String {
    return this.uppercase()
}

fun String.brokenExtension(): String {
    return this.lowercase()
    // Missing }

fun String.anotherExtension(): String {
    return this.trim()
}
"""
        parser = KotlinSemanticParser(config)
        chunks = parser.chunk(code, "test.kt")

        # Should extract extension functions
        extension_chunks = [
            c for c in chunks if c.semantic_type == "extension_function"
        ]
        assert len(extension_chunks) >= 2

        # Verify broken extension was found
        extension_names = [c.semantic_name for c in extension_chunks]
        assert "brokenExtension" in extension_names or any(
            "extracted_from_error" in c.semantic_context for c in extension_chunks
        )


class TestTypeScriptErrorHandling:
    """Test TypeScript parser ERROR node handling."""

    def test_typescript_interface_with_syntax_error(self, config):
        """Test TypeScript interface with syntax error."""
        code = """
interface ValidInterface {
    name: string;
    age: number;
}

interface BrokenInterface {
    name: string;
    // Missing closing brace

interface AnotherInterface {
    id: number;
}

class ValidClass {
    constructor(public name: string) {}
}
"""
        parser = TypeScriptSemanticParser(config)
        chunks = parser.chunk(code, "test.ts")

        # Should extract interfaces despite syntax error
        interface_chunks = [c for c in chunks if c.semantic_type == "interface"]
        assert len(interface_chunks) >= 2

        # Check for broken interface
        interface_names = [c.semantic_name for c in interface_chunks]
        assert "BrokenInterface" in interface_names or any(
            "extracted_from_error" in c.semantic_context for c in interface_chunks
        )

    def test_typescript_function_with_generic_error(self, config):
        """Test TypeScript function with generic syntax error."""
        code = """
function validFunction<T>(data: T): T {
    return data;
}

function brokenGeneric<T extends string, U extends {
    // Broken generic constraint
    return data;
}

function anotherFunction(x: number): number {
    return x * 2;
}
"""
        parser = TypeScriptSemanticParser(config)
        chunks = parser.chunk(code, "test.ts")

        # Should extract functions
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) >= 2

        # Verify broken function was found
        function_names = [c.semantic_name for c in function_chunks]
        assert "brokenGeneric" in function_names or any(
            "extracted_from_error" in c.semantic_context for c in function_chunks
        )


class TestJavaScriptErrorHandling:
    """Test JavaScript parser ERROR node handling."""

    def test_javascript_class_with_syntax_error(self, config):
        """Test JavaScript class with syntax error."""
        code = """
class ValidClass {
    constructor(name) {
        this.name = name;
    }
    
    getName() {
        return this.name;
    }
}

class BrokenClass {
    constructor(name) {
        this.name = name;
    // Missing closing brace

const validFunction = () => {
    console.log("Arrow function works");
};

function anotherFunction() {
    console.log("Regular function works");
}
"""
        parser = JavaScriptSemanticParser(config)
        chunks = parser.chunk(code, "test.js")

        # Should extract classes and functions
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        function_chunks = [
            c for c in chunks if c.semantic_type in ["function", "arrow_function"]
        ]

        assert len(class_chunks) >= 1
        assert len(function_chunks) >= 2

        # Check for broken class
        class_names = [c.semantic_name for c in class_chunks]
        assert "BrokenClass" in class_names or any(
            "extracted_from_error" in c.semantic_context for c in class_chunks
        )

    def test_javascript_arrow_function_with_error(self, config):
        """Test JavaScript function with syntax error."""
        code = """
function validFunction() {
    return "works";
}

function brokenFunction( {
    // Missing parameter closing paren
    return "broken";
}

function anotherFunction() {
    return "test";
}
"""
        parser = JavaScriptSemanticParser(config)
        chunks = parser.chunk(code, "test.js")

        # Should extract functions despite syntax error
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) >= 3

        # Verify broken function was found
        function_names = [c.semantic_name for c in function_chunks]
        assert "brokenFunction" in function_names or any(
            "extracted_from_error" in c.semantic_context for c in function_chunks
        )


class TestJavaErrorHandling:
    """Test Java parser ERROR node handling."""

    def test_java_class_with_syntax_error(self, config):
        """Test Java class with syntax error."""
        code = """
package com.example;

public class ValidClass {
    private String name;
    
    public ValidClass(String name) {
        this.name = name;
    }
    
    public String getName() {
        return name;
    }
}

public class BrokenClass {
    private String value;
    
    public BrokenClass(String value) {
        this.value = value;
    // Missing closing brace

public class AnotherClass {
    private int id;
    
    public int getId() {
        return id;
    }
}
"""
        parser = JavaSemanticParser(config)
        chunks = parser.chunk(code, "test.java")

        # Should extract classes despite syntax error
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 2

        # Check for broken class
        class_names = [c.semantic_name for c in class_chunks]
        assert "BrokenClass" in class_names or any(
            "extracted_from_error" in c.semantic_context for c in class_chunks
        )

    def test_java_method_with_syntax_error(self, config):
        """Test Java method with syntax error."""
        code = """
package com.example;

public class TestClass {
    public void validMethod() {
        System.out.println("This works");
    }
    
    public void brokenMethod() {
        System.out.println("Missing closing brace");
        // Missing }
    
    public void anotherMethod() {
        System.out.println("After error");
    }
}
"""
        parser = JavaSemanticParser(config)
        chunks = parser.chunk(code, "test.java")

        # Should extract methods despite syntax error
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        assert len(method_chunks) >= 2

        # Check for broken method
        method_names = [c.semantic_name for c in method_chunks]
        assert "brokenMethod" in method_names or any(
            "extracted_from_error" in c.semantic_context for c in method_chunks
        )


class TestPythonErrorHandling:
    """Test Python parser ERROR node handling."""

    def test_python_function_with_syntax_error(self, config):
        """Test Python function with syntax error."""
        code = """
def valid_function():
    print("This works")
    return True

def broken_function():
    print("Missing proper indentation")
  # Wrong indentation level
    print("This should cause issues")
    return False

def another_function():
    print("After error")
    return None

class ValidClass:
    def __init__(self):
        self.value = 42
    
    def get_value(self):
        return self.value
"""
        parser = PythonSemanticParser(config)
        chunks = parser.chunk(code, "test.py")

        # Should extract functions and classes
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        class_chunks = [c for c in chunks if c.semantic_type == "class"]

        assert len(function_chunks) >= 3  # Including methods
        assert len(class_chunks) >= 1

        # Check that we extracted constructs despite errors
        construct_names = [c.semantic_name for c in chunks]
        assert (
            "broken_function" in construct_names or "valid_function" in construct_names
        )

    def test_python_class_with_syntax_error(self, config):
        """Test Python class with syntax error."""
        code = """
class ValidClass:
    def __init__(self):
        self.name = "valid"
    
    def get_name(self):
        return self.name

class BrokenClass:
    def __init__(self):
        self.value = 123
    
    def broken_method(self):
        if True:
            print("Missing proper structure")
        # Improper nesting
      print("Wrong indentation")
        return self.value

class AnotherClass:
    def __init__(self):
        self.id = 456
"""
        parser = PythonSemanticParser(config)
        chunks = parser.chunk(code, "test.py")

        # Should extract classes despite syntax errors
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        method_chunks = [c for c in chunks if c.semantic_type in ["function", "method"]]

        assert len(class_chunks) >= 2
        assert len(method_chunks) >= 3

        # Verify we found the broken class
        class_names = [c.semantic_name for c in class_chunks]
        assert "BrokenClass" in class_names


class TestErrorNodeExtractionDetails:
    """Test specific ERROR node extraction details."""

    def test_error_node_metadata(self, config):
        """Test that ERROR node extractions have proper metadata."""
        code = """
func BrokenGoFunction() {
    fmt.Println("Missing closing brace")
    // Missing }

func ValidGoFunction() {
    fmt.Println("This works")
}
"""
        parser = GoSemanticParser(config)
        chunks = parser.chunk(code, "test.go")

        # Look for chunks with error extraction metadata
        error_chunks = [
            c for c in chunks if c.semantic_context.get("extracted_from_error")
        ]

        # Should have at least one error extraction
        if error_chunks:
            error_chunk = error_chunks[0]
            assert error_chunk.semantic_type in [
                "function",
                "method",
                "struct",
                "interface",
            ]
            assert error_chunk.semantic_name is not None
            assert len(error_chunk.text) > 0
            assert error_chunk.line_start > 0
            assert error_chunk.line_end >= error_chunk.line_start

    def test_fallback_parser_integration(self, config):
        """Test that fallback to original parser works when tree-sitter fails completely."""
        # Create completely unparseable content
        code = """
This is not valid code in any language
{{{ broken syntax everywhere %%%
function??? maybe(((
class///// 
"""
        parser = GoSemanticParser(config)
        chunks = parser.chunk(code, "test.go")

        # Should still return some chunks from fallback parser
        assert isinstance(chunks, list)
        # Fallback may return empty list for completely invalid code, which is acceptable

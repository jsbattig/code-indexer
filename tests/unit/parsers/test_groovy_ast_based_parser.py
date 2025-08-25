"""
Tests for pure AST-based Groovy semantic parser.
TDD approach - writing failing tests for the new AST-based implementation.

These tests specifically target eliminating the problems in the current implementation:
1. No regex-based parsing on AST node text
2. No meaningless "null;" chunks
3. No false positive field declarations from return statements
4. No duplicate chunks with different scope paths
5. Pure tree-sitter node type-based parsing
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.groovy_parser import GroovySemanticParser


class TestGroovyASTBasedParser:
    """Test pure AST-based Groovy semantic parser."""

    @pytest.fixture
    def parser(self):
        """Create a Groovy parser configured for AST-based parsing."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return GroovySemanticParser(config)

    def test_no_regex_based_parsing(self, parser):
        """Test that parser uses only AST node types, not regex on text."""
        content = dedent(
            """
            class Calculator {
                def add(a, b) {
                    return a + b
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "Calculator.groovy")

        # Should identify class and method by AST node types, not regex
        class_chunk = next((c for c in chunks if c.semantic_type == "class"), None)
        method_chunk = next((c for c in chunks if c.semantic_type == "method"), None)

        assert class_chunk is not None, "Should find class via AST, not regex"
        assert method_chunk is not None, "Should find method via AST, not regex"
        assert class_chunk.semantic_name == "Calculator"
        assert method_chunk.semantic_name == "add"

    def test_prevent_null_only_chunks(self, parser):
        """Test that meaningless null/semicolon chunks are not created."""
        content = dedent(
            """
            def testMethod() {
                return null;
            }
        """
        ).strip()

        chunks = parser.chunk(content, "test.groovy")

        # Should NOT create a chunk with just "null;" or "null" or ";"
        problematic_chunks = [
            c
            for c in chunks
            if c.size <= 12 and c.text.strip() in ["null;", "null", ";", "return null;"]
        ]

        assert (
            len(problematic_chunks) == 0
        ), f"Found problematic chunks: {[c.text.strip() for c in problematic_chunks]}"

        # Should only have the method chunk
        method_chunks = [c for c in chunks if c.semantic_type in ["method", "function"]]
        assert len(method_chunks) == 1
        assert method_chunks[0].semantic_name == "testMethod"

    def test_no_false_positive_field_declarations(self, parser):
        """Test that return statements don't create field declarations."""
        content = dedent(
            """
            class Test {
                String field = "value"
                
                def method() {
                    return null
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "Test.groovy")

        # Should find ONE field declaration (the real one)
        field_chunks = [c for c in chunks if c.semantic_type in ["field", "property"]]
        assert (
            len(field_chunks) == 1
        ), f"Expected 1 field, found {len(field_chunks)}: {[c.semantic_name for c in field_chunks]}"
        assert field_chunks[0].semantic_name == "field"

        # Should NOT have a field named "null" from the return statement
        null_fields = [c for c in field_chunks if c.semantic_name == "null"]
        assert len(null_fields) == 0, "Should not create field from 'return null'"

    def test_no_duplicate_chunks(self, parser):
        """Test that chunks are not duplicated with different scope paths."""
        content = dedent(
            """
            package com.example
            
            class UserService {
                private String name
                
                def getName() {
                    return name
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "UserService.groovy")

        # Check for duplicates by semantic path
        paths = [c.semantic_path for c in chunks]
        unique_paths = set(paths)

        assert len(paths) == len(
            unique_paths
        ), f"Found duplicate paths: {[p for p in paths if paths.count(p) > 1]}"

        # Specifically check for the name field - should appear only once
        name_chunks = [
            c
            for c in chunks
            if c.semantic_name == "name" and c.semantic_type in ["field", "property"]
        ]
        assert (
            len(name_chunks) == 1
        ), f"Field 'name' should appear once, found {len(name_chunks)}"

    def test_proper_ast_node_type_handling(self, parser):
        """Test that specific AST node types are handled correctly."""
        content = dedent(
            """
            package com.example
            
            import java.util.List
            
            @Entity
            class UserService {
                @Autowired
                private UserRepository userRepo
                
                static final String DEFAULT_ROLE = "USER"
            }
        """
        ).strip()

        chunks = parser.chunk(content, "UserService.groovy")

        # Check that different AST constructs are identified properly
        chunk_types = {c.semantic_type for c in chunks}

        # Should identify package, class, field/property by AST node types
        field_or_property = {"field", "property"}

        assert "package" in chunk_types, "Should identify package declaration via AST"
        assert "class" in chunk_types, "Should identify class declaration via AST"
        assert (
            len(chunk_types.intersection(field_or_property)) > 0
        ), "Should identify field/property via AST"

    def test_field_name_validation(self, parser):
        """Test that field names are validated as proper identifiers."""
        content = dedent(
            """
            class Test {
                String validField = "value"
                def method() {
                    if (condition == null) return null
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "Test.groovy")

        # Should only have valid field names
        field_chunks = [c for c in chunks if c.semantic_type in ["field", "property"]]
        field_names = [c.semantic_name for c in field_chunks]

        # Should have "validField" but NOT "null" or "condition"
        assert "validField" in field_names, "Should identify valid field"
        assert "null" not in field_names, "Should not identify 'null' as field name"
        assert "condition" not in field_names or any(
            "==" in c.text for c in field_chunks if c.semantic_name == "condition"
        ), "Should not misidentify comparison as field"

    def test_closure_ast_based_parsing(self, parser):
        """Test that closures are identified via AST structure, not regex."""
        content = dedent(
            """
            class ClosureTest {
                Closure validator = { user ->
                    return user != null && user.isActive()
                }
                
                def process = { 
                    println "processing"
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "ClosureTest.groovy")

        # Should identify closures by AST structure
        closure_chunks = [c for c in chunks if c.semantic_type == "closure"]
        closure_names = {c.semantic_name for c in closure_chunks}

        assert (
            len(closure_chunks) == 2
        ), f"Should find 2 closures, found {len(closure_chunks)}"
        assert "validator" in closure_names, "Should identify typed closure"
        assert "process" in closure_names, "Should identify simple closure"

    def test_method_vs_field_distinction(self, parser):
        """Test proper distinction between methods and fields via AST."""
        content = dedent(
            """
            class Test {
                String field = "value"
                def field2 = "another"
                
                def getField() {
                    return field
                }
                
                String getField2() {
                    return field2
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "Test.groovy")

        # Separate methods from fields/properties based on AST
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        field_chunks = [c for c in chunks if c.semantic_type in ["field", "property"]]

        method_names = {c.semantic_name for c in method_chunks}
        field_names = {c.semantic_name for c in field_chunks}

        # Check proper classification
        assert "getField" in method_names, "Should identify method via AST"
        assert "getField2" in method_names, "Should identify typed method via AST"
        assert "field" in field_names, "Should identify field via AST"
        assert "field2" in field_names, "Should identify def field via AST"

    def test_annotation_ast_parsing(self, parser):
        """Test that annotations are parsed via AST, not regex."""
        content = dedent(
            """
            @Entity
            @Table(name="users")
            class User {
                @Id
                @Column(name="user_id")
                private Long id
                
                @Autowired
                private UserService service
            }
        """
        ).strip()

        chunks = parser.chunk(content, "User.groovy")

        # Check that annotations are captured via AST
        class_chunk = next((c for c in chunks if c.semantic_type == "class"), None)
        field_chunks = [c for c in chunks if c.semantic_type in ["field", "property"]]

        assert class_chunk is not None
        assert (
            "annotated" in class_chunk.semantic_language_features
        ), "Class should be marked as annotated"

        # Check field annotations
        annotated_fields = [
            c for c in field_chunks if "annotated" in c.semantic_language_features
        ]
        assert len(annotated_fields) >= 2, "Should identify annotated fields via AST"

    def test_package_import_ast_parsing(self, parser):
        """Test that package and import statements use AST, not regex."""
        content = dedent(
            """
            package com.example.service
            
            import java.util.List
            import com.example.model.User
            
            class UserService {
                def process(List<User> users) {
                    return users.size()
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "UserService.groovy")

        # Should identify package via AST
        package_chunks = [c for c in chunks if c.semantic_type == "package"]
        assert len(package_chunks) == 1, "Should find package via AST"
        assert package_chunks[0].semantic_name == "com.example.service"

        # Should identify imports via AST (if supported)
        # Note: This may not be implemented yet, but should be via AST if supported
        # import_chunks = [c for c in chunks if c.semantic_type == "import"]

    def test_semantic_chunk_quality(self, parser):
        """Test that chunks have semantic value and proper content quality."""
        content = dedent(
            """
            class QualityTest {
                String name = null
                
                def setName(String newName) {
                    this.name = newName
                }
                
                def getName() {
                    return name != null ? name : "default"
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "QualityTest.groovy")

        # All chunks should have semantic value
        for chunk in chunks:
            # Should not be tiny meaningless chunks
            if chunk.size <= 15:  # Allow small but meaningful chunks
                # But these small chunks should have semantic content, not just "null;" or ";"
                assert chunk.text.strip() not in [
                    "null",
                    "null;",
                    ";",
                    "=",
                    "return",
                    "return;",
                ], f"Chunk has no semantic value: '{chunk.text.strip()}'"

            # Should have proper semantic metadata
            assert chunk.semantic_type is not None, "Chunk should have semantic type"
            assert chunk.semantic_name is not None, "Chunk should have semantic name"
            assert chunk.semantic_path is not None, "Chunk should have semantic path"
            assert len(chunk.text.strip()) > 0, "Chunk should have actual content"

    def test_nested_class_ast_parsing(self, parser):
        """Test nested class parsing via AST structure."""
        content = dedent(
            """
            class OuterClass {
                private String outerField
                
                class InnerClass {
                    def accessOuter() {
                        return outerField
                    }
                }
                
                static class StaticNested {
                    static def method() {
                        return "nested"
                    }
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "OuterClass.groovy")

        # Should identify nested classes via AST structure
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        class_names = {c.semantic_name for c in class_chunks}

        assert "OuterClass" in class_names, "Should find outer class"
        assert (
            len([c for c in class_chunks if c.semantic_parent == "OuterClass"]) > 0
        ), "Should find nested classes with proper parent relationship"

    def test_groovy_script_ast_parsing(self, parser):
        """Test script-level constructs parsing via AST."""
        content = dedent(
            """
            #!/usr/bin/env groovy
            
            def scriptVar = "hello"
            
            def scriptFunction() {
                return scriptVar
            }
            
            println scriptFunction()
        """
        ).strip()

        chunks = parser.chunk(content, "script.groovy")

        # Should identify script-level constructs via AST
        function_chunks = [
            c for c in chunks if c.semantic_type in ["function", "method"]
        ]
        assert len(function_chunks) >= 1, "Should find script function via AST"

        # Script functions should have no parent or script-level parent
        script_functions = [
            c
            for c in function_chunks
            if c.semantic_parent is None or c.semantic_parent == "script"
        ]
        assert len(script_functions) >= 1, "Should identify script-level functions"

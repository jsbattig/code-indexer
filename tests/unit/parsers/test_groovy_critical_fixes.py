"""
Specific failing tests for the 5 critical issues in Groovy AST parser.
These tests are designed to fail initially and guide the fixes.

CRITICAL ISSUES TO FIX:
1. Duplicate chunk generation - dual traversal paths
2. Closure detection logic failure - incorrect AST pattern matching
3. Incomplete method detection - missing typed methods
4. Annotation fallback to regex - AST parsing fails
5. Scope path inconsistencies - different traversal creates different paths
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.groovy_parser import GroovySemanticParser


class TestGroovyCriticalFixes:
    """Test specific critical issues that need fixing."""

    @pytest.fixture
    def parser(self):
        """Create a Groovy parser."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return GroovySemanticParser(config)

    def test_duplicate_chunk_generation_critical(self, parser):
        """CRITICAL: Test that dual traversal paths create duplicate chunks."""
        content = dedent(
            """
            class Test {
                String field = "value"
            }
        """
        ).strip()

        chunks = parser.chunk(content, "Test.groovy")

        # Should NOT have the same field with different paths
        field_chunks = [
            c
            for c in chunks
            if c.semantic_name == "field" and c.semantic_type in ["field", "property"]
        ]
        paths = [c.semantic_path for c in field_chunks]

        # CRITICAL BUG: Same field appears with 'Test.field' and 'field' paths
        assert len(field_chunks) == 1, f"Field 'field' duplicated: {paths}"
        assert paths[0] == "Test.field", f"Expected 'Test.field', got {paths}"

    def test_closure_detection_failure_critical(self, parser):
        """CRITICAL: Test that closure detection logic fails to identify closures."""
        content = dedent(
            """
            class Test {
                Closure validator = { user ->
                    user != null
                }
                
                def process = { 
                    println "processing"
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "Test.groovy")

        # CRITICAL BUG: Closures are classified as "property" instead of "closure"
        closure_chunks = [c for c in chunks if c.semantic_type == "closure"]
        property_chunks = [
            c
            for c in chunks
            if c.semantic_type == "property"
            and c.semantic_name in ["validator", "process"]
        ]

        print(f"Closure chunks found: {[c.semantic_name for c in closure_chunks]}")
        print(
            f"Property chunks (should be closures): {[c.semantic_name for c in property_chunks]}"
        )

        assert (
            len(closure_chunks) == 2
        ), f"Expected 2 closures, found {len(closure_chunks)}"
        assert "validator" in [
            c.semantic_name for c in closure_chunks
        ], "validator should be closure"
        assert "process" in [
            c.semantic_name for c in closure_chunks
        ], "process should be closure"

    def test_incomplete_method_detection_critical(self, parser):
        """CRITICAL: Test that typed methods are not detected, only 'def' methods."""
        content = dedent(
            """
            class Test {
                def methodWithDef() {
                    return "def method"
                }
                
                String methodWithType() {
                    return "typed method"
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "Test.groovy")

        # CRITICAL BUG: Only 'def' methods detected, typed methods missed
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        method_names = [c.semantic_name for c in method_chunks]

        print(f"Methods found: {method_names}")

        assert "methodWithDef" in method_names, "Should find 'def' method"
        assert (
            "methodWithType" in method_names
        ), "Should find typed method (CRITICAL BUG)"

    def test_annotation_fallback_to_regex_critical(self, parser):
        """CRITICAL: Test that annotated classes fall back to regex parsing."""
        content = dedent(
            """
            @Entity
            class User {
                @Id
                private Long id
            }
        """
        ).strip()

        chunks = parser.chunk(content, "User.groovy")

        # CRITICAL BUG: Annotated classes fall back to regex parsing
        class_chunk = next((c for c in chunks if c.semantic_type == "class"), None)
        assert class_chunk is not None, "Should find class"

        print(f"Class features: {class_chunk.semantic_language_features}")
        print(f"Class context: {class_chunk.semantic_context}")

        # Should NOT have 'class_fallback' feature indicating regex fallback
        assert (
            "class_fallback" not in class_chunk.semantic_language_features
        ), "Class should NOT fall back to regex parsing (CRITICAL BUG)"
        assert (
            "extracted_from_regex" not in class_chunk.semantic_context
        ), "Class should be parsed via AST, not regex (CRITICAL BUG)"

    def test_scope_path_inconsistencies_critical(self, parser):
        """CRITICAL: Test that different traversal paths create inconsistent scope paths."""
        content = dedent(
            """
            package com.example
            
            class Service {
                private String name = "test"
                
                def getName() {
                    return name
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "Service.groovy")

        # All constructs should have consistent scope paths
        field_chunks = [
            c
            for c in chunks
            if c.semantic_name == "name" and c.semantic_type in ["field", "property"]
        ]

        print(
            f"Field chunks: {[(c.semantic_path, c.semantic_parent) for c in field_chunks]}"
        )

        # CRITICAL BUG: Same field appears with different parent paths
        assert (
            len(field_chunks) == 1
        ), f"Field 'name' should appear once, found {len(field_chunks)}"
        if field_chunks:
            assert (
                field_chunks[0].semantic_path == "com.example.Service.name"
            ), f"Expected 'com.example.Service.name', got '{field_chunks[0].semantic_path}'"

    def test_debug_ast_structure_for_closure(self, parser):
        """Debug helper to understand actual AST structure for closures."""
        content = dedent(
            """
            def process = { 
                println "test"
            }
        """
        ).strip()

        # Parse and debug
        tree = parser._parse_content(content)
        if tree and tree.root_node:
            lines = content.split("\n")
            print("DEBUG: AST Structure for closure:")
            parser._debug_ast_structure(tree.root_node, lines)

    def test_debug_ast_structure_for_typed_method(self, parser):
        """Debug helper to understand actual AST structure for typed methods."""
        content = dedent(
            """
            String getField() {
                return field
            }
        """
        ).strip()

        # Parse and debug
        tree = parser._parse_content(content)
        if tree and tree.root_node:
            lines = content.split("\n")
            print("DEBUG: AST Structure for typed method:")
            parser._debug_ast_structure(tree.root_node, lines)

    def test_debug_ast_structure_for_annotation(self, parser):
        """Debug helper to understand actual AST structure for annotations."""
        content = dedent(
            """
            @Entity
            class User {
                @Id
                private Long id
            }
        """
        ).strip()

        # Parse and debug
        tree = parser._parse_content(content)
        if tree and tree.root_node:
            lines = content.split("\n")
            print("DEBUG: AST Structure for annotation:")
            parser._debug_ast_structure(tree.root_node, lines)

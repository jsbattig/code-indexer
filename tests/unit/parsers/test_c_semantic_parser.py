"""
Tests for C semantic parser.
Following TDD approach - writing comprehensive tests to ensure complete coverage
of C language constructs including ERROR node handling.
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestCSemanticParser:
    """Test C semantic parser using tree-sitter."""

    @pytest.fixture
    def chunker(self):
        """Create a semantic chunker with semantic chunking enabled."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return SemanticChunker(config)

    @pytest.fixture
    def parser(self):
        """Create a C parser directly."""
        from code_indexer.indexing.c_parser import CSemanticParser

        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return CSemanticParser(config)

    def test_basic_struct_declaration(self, parser):
        """Test parsing basic C struct definitions."""
        content = dedent(
            """
            struct Point {
                int x;
                int y;
            };

            struct Rectangle {
                struct Point top_left;
                struct Point bottom_right;
                int width;
                int height;
            };
        """
        ).strip()

        chunks = parser.chunk(content, "point.c")

        # Should find structs and their fields
        assert len(chunks) >= 2

        # Check struct chunks
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        assert len(struct_chunks) >= 2

        struct_names = {c.semantic_name for c in struct_chunks}
        assert "Point" in struct_names
        assert "Rectangle" in struct_names

        # Check Point struct
        point_struct = next(c for c in struct_chunks if c.semantic_name == "Point")
        assert point_struct.semantic_path == "Point"
        assert "struct Point" in point_struct.semantic_signature

        # Check Rectangle struct
        rect_struct = next(c for c in struct_chunks if c.semantic_name == "Rectangle")
        assert rect_struct.semantic_path == "Rectangle"
        assert "struct Rectangle" in rect_struct.semantic_signature

    def test_function_declarations_and_definitions(self, parser):
        """Test parsing C function declarations and definitions."""
        content = dedent(
            """
            // Function declarations
            int add(int a, int b);
            double calculate_area(double width, double height);
            void print_message(const char* message);

            // Function definitions
            int add(int a, int b) {
                return a + b;
            }

            double calculate_area(double width, double height) {
                return width * height;
            }

            void print_message(const char* message) {
                printf("%s\\n", message);
            }

            // Static function
            static int helper_function(int x) {
                return x * 2;
            }
        """
        ).strip()

        chunks = parser.chunk(content, "functions.c")

        # Should find function definitions (declarations might not be separate chunks)
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) >= 4

        function_names = {c.semantic_name for c in function_chunks}
        assert "add" in function_names
        assert "calculate_area" in function_names
        assert "print_message" in function_names
        assert "helper_function" in function_names

        # Check function signatures
        add_func = next(c for c in function_chunks if c.semantic_name == "add")
        assert "int add" in add_func.semantic_signature
        assert add_func.semantic_scope == "global"

    def test_enum_declarations(self, parser):
        """Test parsing C enum declarations."""
        content = dedent(
            """
            enum Color {
                RED,
                GREEN,
                BLUE,
                YELLOW = 10,
                ORANGE
            };

            enum Status {
                SUCCESS = 0,
                ERROR = -1,
                PENDING = 1
            };

            typedef enum {
                NORTH,
                SOUTH,
                EAST,
                WEST
            } Direction;
        """
        ).strip()

        chunks = parser.chunk(content, "enums.c")

        # Should find enum declarations
        enum_chunks = [c for c in chunks if c.semantic_type == "enum"]
        assert len(enum_chunks) >= 2

        enum_names = {c.semantic_name for c in enum_chunks if c.semantic_name}
        assert "Color" in enum_names
        assert "Status" in enum_names

        # Check enum features
        color_enum = next(c for c in enum_chunks if c.semantic_name == "Color")
        assert "enum_declaration" in color_enum.semantic_language_features
        assert "enum Color" in color_enum.semantic_signature

    def test_union_declarations(self, parser):
        """Test parsing C union declarations."""
        content = dedent(
            """
            union Value {
                int integer_value;
                double double_value;
                char string_value[256];
            };

            union Data {
                struct {
                    int x, y;
                } point;
                struct {
                    char name[32];
                    int age;
                } person;
            };
        """
        ).strip()

        chunks = parser.chunk(content, "unions.c")

        # Should find union declarations
        union_chunks = [c for c in chunks if c.semantic_type == "union"]
        assert len(union_chunks) >= 2

        union_names = {c.semantic_name for c in union_chunks}
        assert "Value" in union_names
        assert "Data" in union_names

        # Check union features
        value_union = next(c for c in union_chunks if c.semantic_name == "Value")
        assert "union_declaration" in value_union.semantic_language_features

    def test_typedef_declarations(self, parser):
        """Test parsing C typedef declarations."""
        content = dedent(
            """
            typedef int MyInt;
            typedef unsigned long long UInt64;
            typedef char* String;

            typedef struct {
                int x, y;
            } Point2D;

            typedef union {
                int i;
                float f;
            } Number; 

            typedef int (*FunctionPointer)(int, int);
        """
        ).strip()

        chunks = parser.chunk(content, "typedefs.c")

        # Should find typedef declarations
        typedef_chunks = [c for c in chunks if c.semantic_type == "typedef"]
        assert len(typedef_chunks) >= 3

        typedef_names = {c.semantic_name for c in typedef_chunks}
        assert "MyInt" in typedef_names or "String" in typedef_names

    def test_preprocessor_directives(self, parser):
        """Test parsing C preprocessor directives."""
        content = dedent(
            """
            #include <stdio.h>
            #include <stdlib.h>
            #include "myheader.h"

            #define MAX_SIZE 1024
            #define PI 3.14159
            #define SQUARE(x) ((x) * (x))

            #ifdef DEBUG
            #define DBG_PRINT(x) printf(x)
            #else
            #define DBG_PRINT(x)
            #endif

            int main() {
                printf("MAX_SIZE: %d\\n", MAX_SIZE);
                return 0;
            }
        """
        ).strip()

        chunks = parser.chunk(content, "preprocessor.c")

        # Should find includes and defines
        include_chunks = [c for c in chunks if c.semantic_type == "include"]
        define_chunks = [c for c in chunks if c.semantic_type == "define"]

        assert len(include_chunks) >= 2
        assert len(define_chunks) >= 2

        # Check include names
        include_names = {c.semantic_name for c in include_chunks}
        assert "stdio.h" in include_names or "stdlib.h" in include_names

        # Check define names
        define_names = {c.semantic_name for c in define_chunks}
        assert "MAX_SIZE" in define_names or "PI" in define_names

    def test_global_variables(self, parser):
        """Test parsing C global variable declarations."""
        content = dedent(
            """
            int global_counter = 0;
            static int internal_counter = 0;
            extern int external_var;
            const double PI = 3.14159;

            char buffer[1024];
            int *dynamic_array;

            struct Config {
                int setting1;
                char setting2[64];
            } global_config = {42, "default"};
        """
        ).strip()

        chunks = parser.chunk(content, "globals.c")

        # Should find variable declarations
        var_chunks = [c for c in chunks if c.semantic_type == "variable"]
        assert len(var_chunks) >= 3

        var_names = {c.semantic_name for c in var_chunks}
        # At least some of these should be found
        expected_vars = {
            "global_counter",
            "internal_counter",
            "buffer",
            "dynamic_array",
        }
        assert len(var_names.intersection(expected_vars)) >= 2

    def test_complex_nested_structures(self, parser):
        """Test parsing complex nested C structures."""
        content = dedent(
            """
            struct Node {
                int data;
                struct Node* next;
                struct Node* prev;
            };

            struct Tree {
                int value;
                struct Tree* left;
                struct Tree* right;
                struct {
                    int height;
                    int balance;
                } metadata;
            };

            typedef struct {
                union {
                    struct {
                        int x, y;
                    } point;
                    struct {
                        double radius;
                        double angle;
                    } polar;
                } coordinates;
                enum {
                    CARTESIAN,
                    POLAR
                } type;
            } Position;
        """
        ).strip()

        chunks = parser.chunk(content, "nested.c")

        # Should find the main structures
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        assert len(struct_chunks) >= 2

        struct_names = {c.semantic_name for c in struct_chunks}
        assert "Node" in struct_names
        assert "Tree" in struct_names

    def test_function_pointers_and_callbacks(self, parser):
        """Test parsing C function pointers and callback patterns."""
        content = dedent(
            """
            // Function pointer typedefs
            typedef int (*CompareFunc)(const void* a, const void* b);
            typedef void (*EventHandler)(int event, void* data);

            // Function that takes callback
            void process_array(int* array, int size, CompareFunc compare) {
                // Process array with comparison function
            }

            // Function that returns function pointer
            CompareFunc get_comparator(int type) {
                if (type == 1) {
                    return &int_compare;
                }
                return &default_compare;
            }

            // Actual comparison functions
            int int_compare(const void* a, const void* b) {
                int ia = *(const int*)a;
                int ib = *(const int*)b;
                return (ia > ib) - (ia < ib);
            }

            int default_compare(const void* a, const void* b) {
                return 0;
            }
        """
        ).strip()

        chunks = parser.chunk(content, "callbacks.c")

        # Should find function definitions and possibly typedefs
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) >= 3

        function_names = {c.semantic_name for c in function_chunks}
        assert "process_array" in function_names
        assert "int_compare" in function_names

    def test_error_node_handling_basic(self, parser):
        """Test ERROR node handling for basic syntax errors."""
        content = dedent(
            """
            struct ValidStruct {
                int field1;
                int field2;
            };

            struct BrokenStruct {
                int field1
                // Missing semicolon
                int field2;
            }; // Missing brace somewhere

            int valid_function() {
                return 42;
            }

            int broken_function() {
                return 123
                // Missing semicolon
            }

            int another_valid_function() {
                return 0;
            }
        """
        ).strip()

        chunks = parser.chunk(content, "broken.c")

        # Should extract constructs despite syntax errors
        assert len(chunks) >= 3

        # Should find at least some valid constructs
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        function_chunks = [c for c in chunks if c.semantic_type == "function"]

        assert len(struct_chunks) >= 1
        assert len(function_chunks) >= 2

        # Check that valid constructs are found
        struct_names = {c.semantic_name for c in struct_chunks}
        function_names = {c.semantic_name for c in function_chunks}

        assert "ValidStruct" in struct_names or "BrokenStruct" in struct_names
        assert (
            "valid_function" in function_names
            or "another_valid_function" in function_names
        )

    def test_error_node_handling_malformed_includes(self, parser):
        """Test ERROR node handling for malformed preprocessor directives."""
        content = dedent(
            """
            #include <stdio.h>
            #include "valid.h"

            #include <broken
            // Malformed include

            #define VALID_MACRO 42
            #define BROKEN_MACRO 
            // Incomplete macro

            int main() {
                printf("Hello World\\n");
                return 0;
            }

            #include "after_code.h"
        """
        ).strip()

        chunks = parser.chunk(content, "broken_includes.c")

        # Should extract valid constructs despite preprocessing errors
        assert len(chunks) >= 2

        # Should find valid includes and functions
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        include_chunks = [c for c in chunks if c.semantic_type == "include"]

        assert len(function_chunks) >= 1
        assert len(include_chunks) >= 1

        function_names = {c.semantic_name for c in function_chunks}
        assert "main" in function_names

    def test_error_node_handling_incomplete_functions(self, parser):
        """Test ERROR node handling for incomplete function definitions."""
        content = dedent(
            """
            // Valid function
            int complete_function(int x) {
                return x * 2;
            }

            // Incomplete function - missing body
            int incomplete_function(int a, int b)

            // Another incomplete - missing closing brace
            int missing_brace_function(int y) {
                if (y > 0) {
                    return y;
                // Missing closing brace

            // Valid function after errors
            void cleanup_function() {
                // cleanup code
            }
        """
        ).strip()

        chunks = parser.chunk(content, "incomplete.c")

        # Should extract functions despite syntax errors
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) >= 2

        function_names = {c.semantic_name for c in function_chunks}
        # Should find at least the complete functions
        assert (
            "complete_function" in function_names
            or "cleanup_function" in function_names
        )

    def test_error_extraction_metadata(self, parser):
        """Test that ERROR node extractions have proper metadata."""
        content = dedent(
            """
            struct BrokenStruct {
                int field1
                int field2;
                // Missing semicolon and brace
            
            int valid_after_error() {
                return 1;
            }
        """
        ).strip()

        chunks = parser.chunk(content, "metadata_test.c")

        # Look for chunks with error extraction metadata
        error_chunks = [
            c
            for c in chunks
            if c.semantic_context and c.semantic_context.get("extracted_from_error")
        ]

        # If error chunks exist, verify they have proper metadata
        if error_chunks:
            error_chunk = error_chunks[0]
            assert error_chunk.semantic_type in ["struct", "function"]
            assert error_chunk.semantic_name is not None
            assert len(error_chunk.text) > 0
            assert error_chunk.line_start > 0
            assert error_chunk.line_end >= error_chunk.line_start

        # Should still find valid constructs
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) >= 1

    def test_malformed_c_code_handling(self, parser):
        """Test handling of completely malformed C code."""
        malformed_content = """
            This is not valid C code at all!
            {{{ broken syntax everywhere %%%
            struct??? maybe
            int incomplete(((
            #define BROKEN
        """

        # Should not crash and should return minimal chunks
        chunks = parser.chunk(malformed_content, "malformed.c")

        # Parser should handle gracefully
        assert isinstance(chunks, list)
        # May return empty list for completely invalid code, which is acceptable

    def test_chunker_integration(self, chunker):
        """Test integration with SemanticChunker for C files."""
        content = dedent(
            """
            #include <stdio.h>

            struct Point {
                int x, y;
            };

            int distance_squared(struct Point p1, struct Point p2) {
                int dx = p1.x - p2.x;
                int dy = p1.y - p2.y;
                return dx * dx + dy * dy;
            }

            int main() {
                struct Point origin = {0, 0};
                struct Point point = {3, 4};
                
                int dist_sq = distance_squared(origin, point);
                printf("Distance squared: %d\\n", dist_sq);
                
                return 0;
            }
        """
        ).strip()

        chunks = chunker.chunk_content(content, "integration.c")

        # Should get semantic chunks from C parser
        assert len(chunks) >= 3

        # Verify chunks have semantic metadata
        for chunk in chunks:
            assert chunk.get("semantic_chunking") is True
            assert "semantic_type" in chunk
            assert "semantic_name" in chunk
            assert "semantic_path" in chunk

    def test_regex_fallback_functionality(self, parser):
        """Test regex fallback for C when tree-sitter fails."""
        # Test the regex fallback method directly
        error_text = """
            struct TestStruct {
                int field;
            };
            
            int test_function(int param) {
                return param;
            }
            
            #define TEST_MACRO 42
            #include <test.h>
        """

        constructs = parser._extract_constructs_from_error_text(error_text, 1, [])

        # Should find constructs through regex
        assert len(constructs) >= 2

        # Check that different construct types were found
        construct_types = {c["type"] for c in constructs}
        expected_types = {"struct", "function", "define", "include"}
        assert len(construct_types.intersection(expected_types)) >= 2

    def test_file_extension_detection(self, parser):
        """Test detection of different C file extensions."""
        simple_content = """
            int test() {
                return 0;
            }
        """

        # Test various C file extensions
        extensions = [".c", ".h"]

        for ext in extensions:
            chunks = parser.chunk(simple_content, f"test{ext}")
            assert len(chunks) >= 1
            assert chunks[0].file_extension == ext

    def test_data_preservation_no_loss(self, parser):
        """Test that chunking preserves all content without data loss."""
        content = dedent(
            """
            #include <stdio.h>
            #include <stdlib.h>

            #define MAX_ITEMS 100
            #define BUFFER_SIZE 1024

            typedef struct {
                int id;
                char name[64];
                double value;
            } Item;

            static int item_count = 0;
            extern char global_buffer[BUFFER_SIZE];

            int compare_items(const void *a, const void *b) {
                const Item *item_a = (const Item *)a;
                const Item *item_b = (const Item *)b;
                return (item_a->value > item_b->value) - (item_a->value < item_b->value);
            }

            void process_items(Item *items, int count) {
                qsort(items, count, sizeof(Item), compare_items);
                
                for (int i = 0; i < count; i++) {
                    printf("Item %d: %s = %.2f\\n", 
                           items[i].id, items[i].name, items[i].value);
                }
            }

            int main(int argc, char *argv[]) {
                Item items[MAX_ITEMS];
                
                // Initialize items
                for (int i = 0; i < 5; i++) {
                    items[i].id = i;
                    snprintf(items[i].name, sizeof(items[i].name), "Item_%d", i);
                    items[i].value = (double)rand() / RAND_MAX * 100.0;
                }
                
                process_items(items, 5);
                return 0;
            }
        """
        ).strip()

        chunks = parser.chunk(content, "data_preservation.c")

        # Verify no data loss by checking that all content is captured
        all_chunk_content = "\n".join(chunk.text for chunk in chunks)

        # Check that essential elements are preserved
        assert "#include <stdio.h>" in all_chunk_content
        assert "#define MAX_ITEMS" in all_chunk_content
        assert "typedef struct" in all_chunk_content
        assert "compare_items" in all_chunk_content
        assert "process_items" in all_chunk_content
        assert "main" in all_chunk_content

        # Check that we have reasonable chunk coverage
        assert len(chunks) >= 4  # Should have multiple semantic chunks

        # Verify all chunks have proper metadata
        for chunk in chunks:
            assert chunk.semantic_chunking is True
            assert chunk.semantic_type is not None
            assert chunk.semantic_name is not None
            assert chunk.file_path == "data_preservation.c"
            assert chunk.line_start > 0
            assert chunk.line_end >= chunk.line_start

    def test_large_constructs_handling(self, parser):
        """Test handling of very large constructs that might exceed chunk size."""
        # Use smaller chunk size to test splitting
        small_config = IndexingConfig(
            chunk_size=300, chunk_overlap=50, use_semantic_chunking=True
        )
        small_parser = parser.__class__(small_config)

        # Create a large function
        large_function_lines = []
        large_function_lines.append("int large_function(int param) {")

        # Add many lines to exceed chunk size
        for i in range(50):
            large_function_lines.append(
                f'    printf("This is line {i} of a very long function\\n");'
            )

        large_function_lines.append("    return param;")
        large_function_lines.append("}")

        content = "\n".join(large_function_lines)

        chunks = small_parser.chunk(content, "large.c")

        # Should handle large constructs
        assert len(chunks) >= 1

        # Verify all content is preserved
        all_content = "\n".join(chunk.text for chunk in chunks)
        assert "large_function" in all_content
        assert "line 25" in all_content  # Check middle content is preserved
        assert "return param" in all_content

    def test_special_characters_and_strings(self, parser):
        """Test handling of special characters and string literals."""
        content = dedent(
            r"""
            #include <stdio.h>

            const char* special_strings[] = {
                "String with \"quotes\" inside",
                "String with \n newlines \t tabs",
                "String with \\ backslashes",
                "Unicode: \u00E9\u00F1\u00FC",
                ""  // Empty string
            };

            int process_string(const char* str) {
                printf("Processing: %s\n", str);
                return strlen(str);
            }

            int main() {
                char buffer[256] = "Test string with special chars: !@#$%^&*()";
                process_string(buffer);
                return 0;
            }
        """
        ).strip()

        chunks = parser.chunk(content, "special_chars.c")

        # Should handle special characters without issues
        assert len(chunks) >= 2

        all_content = "\n".join(chunk.text for chunk in chunks)
        assert "process_string" in all_content
        assert "main" in all_content
        assert "special_strings" in all_content

    def test_different_formatting_styles(self, parser):
        """Test handling of different C formatting styles."""
        # K&R style
        kr_style = dedent(
            """
            struct Point {
                int x, y;
            };

            int add(int a, int b) {
                return a + b;
            }
        """
        ).strip()

        # Allman style
        allman_style = dedent(
            """
            struct Point
            {
                int x, y;
            };

            int add(int a, int b)
            {
                return a + b;
            }
        """
        ).strip()

        kr_chunks = parser.chunk(kr_style, "kr.c")
        allman_chunks = parser.chunk(allman_style, "allman.c")

        # Both styles should be parsed correctly
        assert len(kr_chunks) >= 2
        assert len(allman_chunks) >= 2

        # Check that structs and functions are found in both styles
        kr_types = {c.semantic_type for c in kr_chunks}
        allman_types = {c.semantic_type for c in allman_chunks}

        assert "struct" in kr_types
        assert "function" in kr_types
        assert "struct" in allman_types
        assert "function" in allman_types

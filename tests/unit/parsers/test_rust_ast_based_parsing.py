"""
TDD tests for pure AST-based Rust parsing without regex patterns.

These tests drive the implementation to eliminate all regex patterns
and use pure tree-sitter AST-based parsing for impl blocks and functions.
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.rust_parser import RustSemanticParser


class TestRustASTBasedParsing:
    """Test AST-based Rust parsing without regex fallbacks."""

    @pytest.fixture
    def parser(self):
        """Create a Rust parser directly."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return RustSemanticParser(config)

    def test_basic_impl_block_ast_parsing(self, parser):
        """Test basic impl block parsing using pure AST."""
        content = dedent(
            """
            struct User {
                name: String,
                age: u32,
            }

            impl User {
                fn new(name: String, age: u32) -> Self {
                    Self { name, age }
                }

                fn display(&self) {
                    println!("{} is {} years old", self.name, self.age);
                }
            }
            """
        ).strip()

        chunks = parser.chunk(content, "basic_impl.rs")

        # Find impl block
        impl_chunks = [c for c in chunks if c.semantic_type == "impl"]
        assert len(impl_chunks) == 1

        impl_chunk = impl_chunks[0]
        assert impl_chunk.semantic_name == "impl User"
        assert impl_chunk.semantic_context["target"] == "User"
        assert "impl User" in impl_chunk.semantic_signature

        # Find methods within impl
        function_chunks = [
            c
            for c in chunks
            if c.semantic_type == "function" and c.semantic_scope == "impl"
        ]
        assert len(function_chunks) == 2

        method_names = {c.semantic_name for c in function_chunks}
        assert "new" in method_names
        assert "display" in method_names

    def test_generic_impl_block_ast_parsing(self, parser):
        """Test generic impl block parsing using pure AST."""
        content = dedent(
            """
            struct Container<T> {
                data: T,
            }

            impl<T: Clone> Container<T> {
                fn new(data: T) -> Self {
                    Self { data }
                }

                fn get(&self) -> T {
                    self.data.clone()
                }
            }

            impl<T, E> Container<Result<T, E>> 
            where 
                T: Clone,
                E: std::error::Error,
            {
                fn unwrap_or_default(self) -> T 
                where 
                    T: Default,
                {
                    self.data.unwrap_or_default()
                }
            }
            """
        ).strip()

        chunks = parser.chunk(content, "generic_impl.rs")

        # Find impl blocks
        impl_chunks = [c for c in chunks if c.semantic_type == "impl"]
        assert len(impl_chunks) == 2

        # Check basic generic impl
        basic_impl = next(c for c in impl_chunks if "Container<T>" in c.semantic_name)
        assert "generic" in basic_impl.semantic_language_features
        assert basic_impl.semantic_context["target"] == "Container<T>"

        # Check complex generic impl with where clause
        complex_impl = next(c for c in impl_chunks if "Result<T, E>" in c.semantic_name)
        assert "generic" in complex_impl.semantic_language_features
        assert "Container<Result<T, E>>" in complex_impl.semantic_context["target"]

    def test_trait_impl_block_ast_parsing(self, parser):
        """Test trait implementation parsing using pure AST."""
        content = dedent(
            """
            use std::fmt::{Display, Formatter, Result};

            struct Point {
                x: f64,
                y: f64,
            }

            impl Display for Point {
                fn fmt(&self, f: &mut Formatter<'_>) -> Result {
                    write!(f, "Point({}, {})", self.x, self.y)
                }
            }

            impl From<(f64, f64)> for Point {
                fn from(tuple: (f64, f64)) -> Self {
                    Point { x: tuple.0, y: tuple.1 }
                }
            }

            impl<T> From<T> for Point 
            where 
                T: Into<f64>,
            {
                fn from(value: T) -> Self {
                    let val = value.into();
                    Point { x: val, y: val }
                }
            }
            """
        ).strip()

        chunks = parser.chunk(content, "trait_impl.rs")

        # Find trait impl blocks
        impl_chunks = [c for c in chunks if c.semantic_type == "impl"]
        assert len(impl_chunks) == 3

        # Check Display implementation
        display_impl = next(
            c for c in impl_chunks if "Display for Point" in c.semantic_name
        )
        assert "trait_impl" in display_impl.semantic_language_features
        assert display_impl.semantic_context["trait"] == "Display"
        assert display_impl.semantic_context["target"] == "Point"

        # Check From implementation
        from_impl = next(
            c for c in impl_chunks if "From<(f64, f64)> for Point" in c.semantic_name
        )
        assert "trait_impl" in from_impl.semantic_language_features
        assert from_impl.semantic_context["trait"] == "From<(f64, f64)>"
        assert from_impl.semantic_context["target"] == "Point"

        # Check generic From implementation
        generic_from = next(
            c for c in impl_chunks if "From<T> for Point" in c.semantic_name
        )
        assert "trait_impl" in generic_from.semantic_language_features
        assert "generic" in generic_from.semantic_language_features

    def test_async_function_ast_parsing(self, parser):
        """Test async function parsing using pure AST."""
        content = dedent(
            """
            use std::error::Error;
            use tokio::time::{sleep, Duration};

            struct DataService {
                url: String,
            }

            impl DataService {
                async fn fetch_data(&self) -> Result<String, Box<dyn Error>> {
                    sleep(Duration::from_millis(100)).await;
                    Ok("data".to_string())
                }

                async fn process_async<T>(&self, data: T) -> T 
                where 
                    T: Clone + Send,
                {
                    // Processing logic here
                    data
                }
            }

            async fn global_async_function(url: &str) -> Result<String, reqwest::Error> {
                let response = reqwest::get(url).await?;
                response.text().await
            }

            pub async unsafe fn complex_async<T, E>(
                param: T,
            ) -> Result<T, E>
            where
                T: Send + Sync,
                E: From<std::io::Error>,
            {
                // Complex async logic
                Ok(param)
            }
            """
        ).strip()

        chunks = parser.chunk(content, "async_functions.rs")

        # Find async functions
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        async_functions = [
            c for c in function_chunks if "async" in c.semantic_language_features
        ]

        assert len(async_functions) == 4

        # Check method-level async function
        fetch_method = next(
            c for c in async_functions if c.semantic_name == "fetch_data"
        )
        assert "async" in fetch_method.semantic_language_features
        assert "async fn fetch_data" in fetch_method.semantic_signature

        # Check generic async method
        process_method = next(
            c for c in async_functions if c.semantic_name == "process_async"
        )
        assert "async" in process_method.semantic_language_features
        assert "generic" in process_method.semantic_language_features

        # Check global async function
        global_func = next(
            c for c in async_functions if c.semantic_name == "global_async_function"
        )
        assert global_func.semantic_scope == "global"
        assert "async" in global_func.semantic_language_features

        # Check complex async function with multiple modifiers
        complex_func = next(
            c for c in async_functions if c.semantic_name == "complex_async"
        )
        assert "async" in complex_func.semantic_language_features
        assert "unsafe" in complex_func.semantic_language_features
        assert "public" in complex_func.semantic_language_features
        assert "generic" in complex_func.semantic_language_features

    def test_macro_definition_ast_parsing(self, parser):
        """Test macro definition parsing using pure AST."""
        content = dedent(
            """
            macro_rules! debug_print {
                ($val:expr) => {
                    println!("{} = {:?}", stringify!($val), $val);
                };
            }

            macro_rules! create_struct {
                ($name:ident, $($field:ident: $type:ty),*) => {
                    struct $name {
                        $($field: $type,)*
                    }
                };
            }

            macro_rules! impl_default {
                ($type:ty, $default_val:expr) => {
                    impl Default for $type {
                        fn default() -> Self {
                            $default_val
                        }
                    }
                };
            }

            // Complex macro with multiple patterns
            macro_rules! match_or_default {
                ($val:expr, $pattern:pat => $result:expr) => {
                    match $val {
                        $pattern => $result,
                        _ => Default::default(),
                    }
                };
                ($val:expr, $pattern:pat => $result:expr, $default:expr) => {
                    match $val {
                        $pattern => $result,
                        _ => $default,
                    }
                };
            }
            """
        ).strip()

        chunks = parser.chunk(content, "macros.rs")

        # Find macro definitions
        macro_chunks = [c for c in chunks if c.semantic_type == "macro"]
        assert len(macro_chunks) == 4

        macro_names = {c.semantic_name for c in macro_chunks}
        assert "debug_print" in macro_names
        assert "create_struct" in macro_names
        assert "impl_default" in macro_names
        assert "match_or_default" in macro_names

        # Check macro features
        for macro_chunk in macro_chunks:
            assert "macro_definition" in macro_chunk.semantic_language_features
            assert "macro_rules!" in macro_chunk.semantic_signature

    def test_derive_attributes_ast_parsing(self, parser):
        """Test parsing of derive attributes using pure AST."""
        content = dedent(
            """
            use serde::{Serialize, Deserialize};

            #[derive(Debug, Clone, PartialEq, Eq)]
            pub struct BasicStruct {
                value: i32,
            }

            #[derive(Debug, Clone, Serialize, Deserialize)]
            #[serde(rename_all = "camelCase")]
            pub struct SerializableStruct {
                field_name: String,
                #[serde(skip_serializing_if = "Option::is_none")]
                optional_field: Option<i32>,
            }

            #[derive(Debug)]
            #[repr(C)]
            pub enum ErrorType {
                NetworkError,
                ParseError,
                #[deprecated(since = "1.0.0", note = "Use ValidationError instead")]
                InvalidInput,
                ValidationError,
            }
            """
        ).strip()

        chunks = parser.chunk(content, "attributes.rs")

        # Find structs and enums with derive attributes
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        enum_chunks = [c for c in chunks if c.semantic_type == "enum"]

        assert len(struct_chunks) == 2
        assert len(enum_chunks) == 1

        # Check basic struct with derive
        basic_struct = next(
            c for c in struct_chunks if c.semantic_name == "BasicStruct"
        )
        assert "derive_debug" in basic_struct.semantic_language_features
        assert "derive_clone" in basic_struct.semantic_language_features
        assert "derive_partialeq" in basic_struct.semantic_language_features

        # Check serializable struct with multiple derives
        ser_struct = next(
            c for c in struct_chunks if c.semantic_name == "SerializableStruct"
        )
        assert "derive_serialize" in ser_struct.semantic_language_features
        assert "derive_deserialize" in ser_struct.semantic_language_features
        assert "serde_attributes" in ser_struct.semantic_language_features

        # Check enum with derive
        error_enum = enum_chunks[0]
        assert "derive_debug" in error_enum.semantic_language_features
        assert "repr_c" in error_enum.semantic_language_features

    def test_associated_types_ast_parsing(self, parser):
        """Test parsing of associated types using pure AST."""
        content = dedent(
            """
            trait Iterator {
                type Item;
                
                fn next(&mut self) -> Option<Self::Item>;
                
                fn collect<B: FromIterator<Self::Item>>(self) -> B 
                where
                    Self: Sized,
                {
                    FromIterator::from_iter(self)
                }
            }

            trait IntoIterator {
                type Item;
                type IntoIter: Iterator<Item = Self::Item>;
                
                fn into_iter(self) -> Self::IntoIter;
            }

            struct NumberIterator {
                current: i32,
                max: i32,
            }

            impl Iterator for NumberIterator {
                type Item = i32;
                
                fn next(&mut self) -> Option<Self::Item> {
                    if self.current < self.max {
                        let current = self.current;
                        self.current += 1;
                        Some(current)
                    } else {
                        None
                    }
                }
            }

            impl IntoIterator for NumberIterator {
                type Item = i32;
                type IntoIter = Self;
                
                fn into_iter(self) -> Self::IntoIter {
                    self
                }
            }
            """
        ).strip()

        chunks = parser.chunk(content, "associated_types.rs")

        # Find traits with associated types
        trait_chunks = [c for c in chunks if c.semantic_type == "trait"]
        impl_chunks = [c for c in chunks if c.semantic_type == "impl"]

        assert len(trait_chunks) == 2
        assert len(impl_chunks) == 2

        # Check Iterator trait
        iterator_trait = next(c for c in trait_chunks if c.semantic_name == "Iterator")
        assert "associated_types" in iterator_trait.semantic_language_features
        assert "type Item" in iterator_trait.text

        # Check trait implementation with associated type
        iter_impl = next(
            c for c in impl_chunks if "Iterator for NumberIterator" in c.semantic_name
        )
        assert "trait_impl" in iter_impl.semantic_language_features
        assert "associated_type_impl" in iter_impl.semantic_language_features
        assert "type Item = i32" in iter_impl.text

    def test_complex_generic_bounds_ast_parsing(self, parser):
        """Test parsing of complex generic bounds using pure AST."""
        content = dedent(
            """
            use std::fmt::Debug;
            use std::ops::Add;

            fn complex_function<T, U, V>(a: T, b: U) -> V
            where
                T: Clone + Debug + Send + Sync,
                U: Into<V> + Copy,
                V: Add<Output = V> + Default,
            {
                let cloned_a = a.clone();
                b.into()
            }

            struct GenericStruct<T, U = String>
            where
                T: Clone,
                U: Default,
            {
                field1: T,
                field2: U,
            }

            impl<T, U> GenericStruct<T, U>
            where
                T: Clone + Debug,
                U: Default + PartialEq,
            {
                fn new(field1: T) -> Self {
                    Self {
                        field1,
                        field2: U::default(),
                    }
                }
            }

            trait ComplexTrait<T>
            where
                T: Clone + Send + Sync + 'static,
            {
                type Output: Debug + Send;
                
                fn process(&self, input: T) -> Self::Output;
            }
            """
        ).strip()

        chunks = parser.chunk(content, "complex_generics.rs")

        # Find generic constructs
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        trait_chunks = [c for c in chunks if c.semantic_type == "trait"]

        # Check complex function
        complex_func = next(
            c for c in function_chunks if c.semantic_name == "complex_function"
        )
        assert "generic" in complex_func.semantic_language_features
        assert "where_clause" in complex_func.semantic_language_features
        assert "multiple_bounds" in complex_func.semantic_language_features

        # Check generic struct with defaults
        generic_struct = next(
            c for c in struct_chunks if c.semantic_name == "GenericStruct"
        )
        assert "generic" in generic_struct.semantic_language_features
        assert "default_type_params" in generic_struct.semantic_language_features
        assert "where_clause" in generic_struct.semantic_language_features

        # Check trait with complex bounds
        complex_trait = next(
            c for c in trait_chunks if c.semantic_name == "ComplexTrait"
        )
        assert "generic" in complex_trait.semantic_language_features
        assert "lifetime_bounds" in complex_trait.semantic_language_features
        assert "associated_types" in complex_trait.semantic_language_features

    def test_no_regex_patterns_used(self, parser):
        """Test that no regex patterns are used in AST parsing - implementation check."""
        content = dedent(
            """
            impl<T: Clone> Container<T> for Vec<T> {
                fn new() -> Self {
                    Vec::new()
                }
            }
            """
        ).strip()

        chunks = parser.chunk(content, "no_regex.rs")

        impl_chunks = [c for c in chunks if c.semantic_type == "impl"]
        assert len(impl_chunks) == 1

        # This test will pass only when regex patterns are eliminated
        # The implementation should not use any regex for AST node parsing
        impl_chunk = impl_chunks[0]
        assert impl_chunk.semantic_context.get("parsed_via_ast") is True
        assert impl_chunk.semantic_context.get("regex_fallback") is not True

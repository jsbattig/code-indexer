"""
Tests for Rust semantic parser.
Following TDD approach - writing comprehensive tests to ensure complete coverage
of Rust language constructs including ERROR node handling.
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestRustSemanticParser:
    """Test Rust semantic parser using tree-sitter."""

    @pytest.fixture
    def chunker(self):
        """Create a semantic chunker with semantic chunking enabled."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return SemanticChunker(config)

    @pytest.fixture
    def parser(self):
        """Create a Rust parser directly."""
        from code_indexer.indexing.rust_parser import RustSemanticParser

        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return RustSemanticParser(config)

    def test_basic_struct_declarations(self, parser):
        """Test parsing basic Rust struct definitions."""
        content = dedent(
            """
            struct Point {
                x: f64,
                y: f64,
            }

            pub struct Rectangle {
                width: f64,
                height: f64,
            }

            struct Circle(f64);

            struct Unit;

            pub struct Person {
                name: String,
                age: u32,
                email: Option<String>,
            }
        """
        ).strip()

        chunks = parser.chunk(content, "structs.rs")

        # Should find struct declarations
        assert len(chunks) >= 5

        # Check struct chunks
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        assert len(struct_chunks) >= 5

        struct_names = {c.semantic_name for c in struct_chunks}
        assert "Point" in struct_names
        assert "Rectangle" in struct_names
        assert "Circle" in struct_names
        assert "Unit" in struct_names
        assert "Person" in struct_names

        # Check Point struct
        point_struct = next(c for c in struct_chunks if c.semantic_name == "Point")
        assert point_struct.semantic_path == "Point"
        assert "struct Point" in point_struct.semantic_signature

        # Check public struct
        rect_struct = next(c for c in struct_chunks if c.semantic_name == "Rectangle")
        assert "public" in rect_struct.semantic_language_features

    def test_enum_declarations(self, parser):
        """Test parsing Rust enum definitions."""
        content = dedent(
            """
            enum Color {
                Red,
                Green,
                Blue,
            }

            pub enum Result<T, E> {
                Ok(T),
                Err(E),
            }

            enum IpAddr {
                V4(u8, u8, u8, u8),
                V6(String),
            }

            pub enum Message {
                Quit,
                Move { x: i32, y: i32 },
                Write(String),
                ChangeColor(i32, i32, i32),
            }

            #[derive(Debug, Clone)]
            enum Status {
                Active,
                Inactive,
                Pending,
            }
        """
        ).strip()

        chunks = parser.chunk(content, "enums.rs")

        # Should find enum declarations
        enum_chunks = [c for c in chunks if c.semantic_type == "enum"]
        assert len(enum_chunks) >= 5

        enum_names = {c.semantic_name for c in enum_chunks}
        assert "Color" in enum_names
        assert "Result" in enum_names
        assert "IpAddr" in enum_names
        assert "Message" in enum_names
        assert "Status" in enum_names

        # Check generic enum
        result_enum = next(c for c in enum_chunks if c.semantic_name == "Result")
        assert "generic" in result_enum.semantic_language_features
        assert "public" in result_enum.semantic_language_features

    def test_trait_declarations(self, parser):
        """Test parsing Rust trait definitions."""
        content = dedent(
            """
            trait Drawable {
                fn draw(&self);
                fn area(&self) -> f64;
            }

            pub trait Clone {
                fn clone(&self) -> Self;
            }

            trait Iterator<Item> {
                type Item;
                fn next(&mut self) -> Option<Self::Item>;
                
                fn collect<B: FromIterator<Self::Item>>(self) -> B
                where
                    Self: Sized,
                {
                    FromIterator::from_iter(self)
                }
            }

            pub trait Display {
                fn fmt(&self, f: &mut Formatter<'_>) -> Result<(), Error>;
            }

            trait Default {
                fn default() -> Self;
            }
        """
        ).strip()

        chunks = parser.chunk(content, "traits.rs")

        # Should find trait declarations
        trait_chunks = [c for c in chunks if c.semantic_type == "trait"]
        assert len(trait_chunks) >= 5

        trait_names = {c.semantic_name for c in trait_chunks}
        assert "Drawable" in trait_names
        assert "Clone" in trait_names
        assert "Iterator" in trait_names
        assert "Display" in trait_names
        assert "Default" in trait_names

        # Check trait features
        iter_trait = next(c for c in trait_chunks if c.semantic_name == "Iterator")
        assert "generic" in iter_trait.semantic_language_features

        # Should also find trait methods
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) >= 3

    def test_impl_blocks(self, parser):
        """Test parsing Rust impl blocks."""
        content = dedent(
            """
            struct Rectangle {
                width: f64,
                height: f64,
            }

            impl Rectangle {
                fn new(width: f64, height: f64) -> Rectangle {
                    Rectangle { width, height }
                }

                fn area(&self) -> f64 {
                    self.width * self.height
                }

                fn can_hold(&self, other: &Rectangle) -> bool {
                    self.width > other.width && self.height > other.height
                }
            }

            impl Drawable for Rectangle {
                fn draw(&self) {
                    println!("Drawing rectangle {}x{}", self.width, self.height);
                }

                fn area(&self) -> f64 {
                    self.width * self.height
                }
            }

            impl<T> Vec<T> {
                fn push(&mut self, item: T) {
                    // Implementation
                }
            }

            impl Default for Rectangle {
                fn default() -> Self {
                    Rectangle {
                        width: 0.0,
                        height: 0.0,
                    }
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "impls.rs")

        # Should find impl blocks and their methods
        impl_chunks = [c for c in chunks if c.semantic_type == "impl"]
        function_chunks = [c for c in chunks if c.semantic_type == "function"]

        assert len(impl_chunks) >= 4
        assert len(function_chunks) >= 6

        # Check impl block names
        impl_names = {c.semantic_name for c in impl_chunks}
        assert "impl Rectangle" in impl_names
        assert "impl Drawable for Rectangle" in impl_names
        assert "impl Vec" in impl_names or "impl Vec<T>" in impl_names

        # Check trait impl
        trait_impl = next(
            (c for c in impl_chunks if "for Rectangle" in c.semantic_name), None
        )
        if trait_impl:
            assert "trait_impl" in trait_impl.semantic_language_features

        # Check generic impl
        generic_impl = next((c for c in impl_chunks if "Vec" in c.semantic_name), None)
        if generic_impl:
            assert "generic" in generic_impl.semantic_language_features

    def test_function_declarations(self, parser):
        """Test parsing Rust function definitions."""
        content = dedent(
            """
            fn main() {
                println!("Hello, world!");
            }

            pub fn add(a: i32, b: i32) -> i32 {
                a + b
            }

            async fn fetch_data(url: &str) -> Result<String, Error> {
                // Async implementation
                Ok(String::new())
            }

            unsafe fn raw_pointer_access(ptr: *const u8) -> u8 {
                *ptr
            }

            fn generic_function<T: Clone>(item: T) -> T {
                item.clone()
            }

            pub async unsafe fn complex_function<T, U>(
                param1: T,
                param2: U,
            ) -> Result<(T, U), Box<dyn Error>>
            where
                T: Clone + Send,
                U: Debug,
            {
                Ok((param1, param2))
            }

            fn closure_example() {
                let add = |x, y| x + y;
                let result = add(5, 3);
            }
        """
        ).strip()

        chunks = parser.chunk(content, "functions.rs")

        # Should find function declarations
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) >= 7

        function_names = {c.semantic_name for c in function_chunks}
        assert "main" in function_names
        assert "add" in function_names
        assert "fetch_data" in function_names
        assert "raw_pointer_access" in function_names
        assert "generic_function" in function_names
        assert "complex_function" in function_names

        # Check function features
        add_func = next(c for c in function_chunks if c.semantic_name == "add")
        assert "public" in add_func.semantic_language_features

        fetch_func = next(c for c in function_chunks if c.semantic_name == "fetch_data")
        assert "async" in fetch_func.semantic_language_features

        unsafe_func = next(
            c for c in function_chunks if c.semantic_name == "raw_pointer_access"
        )
        assert "unsafe" in unsafe_func.semantic_language_features

        generic_func = next(
            c for c in function_chunks if c.semantic_name == "generic_function"
        )
        assert "generic" in generic_func.semantic_language_features

    def test_macro_definitions(self, parser):
        """Test parsing Rust macro definitions."""
        content = dedent(
            """
            macro_rules! vec {
                ( $( $x:expr ),* ) => {
                    {
                        let mut temp_vec = Vec::new();
                        $(
                            temp_vec.push($x);
                        )*
                        temp_vec
                    }
                };
            }

            macro_rules! println {
                () => (print!("\\n"));
                ($($arg:tt)*) => (print!("{}\n", format_args!($($arg)*)));
            }

            macro_rules! debug_print {
                ($val:expr) => {
                    println!("{} = {:?}", stringify!($val), $val);
                };
            }

            macro_rules! create_function {
                ($func_name:ident) => {
                    fn $func_name() {
                        println!("You called {:?}()", stringify!($func_name));
                    }
                };
            }

            // Use the macro
            create_function!(foo);
            create_function!(bar);
        """
        ).strip()

        chunks = parser.chunk(content, "macros.rs")

        # Should find macro definitions
        macro_chunks = [c for c in chunks if c.semantic_type == "macro"]
        assert len(macro_chunks) >= 4

        macro_names = {c.semantic_name for c in macro_chunks}
        assert "vec" in macro_names
        assert "println" in macro_names
        assert "debug_print" in macro_names
        assert "create_function" in macro_names

        # Check macro features
        for macro_chunk in macro_chunks:
            assert "macro_definition" in macro_chunk.semantic_language_features

    def test_constants_and_statics(self, parser):
        """Test parsing Rust const and static declarations."""
        content = dedent(
            """
            const PI: f64 = 3.14159265359;
            pub const MAX_SIZE: usize = 1000;
            const GREETING: &str = "Hello, Rust!";

            static GLOBAL_COUNTER: AtomicI32 = AtomicI32::new(0);
            pub static mut GLOBAL_ARRAY: [i32; 10] = [0; 10];
            static VERSION: &str = "1.0.0";

            const fn compile_time_computation(n: u32) -> u32 {
                n * n
            }

            pub const COMPUTED_VALUE: u32 = compile_time_computation(5);
        """
        ).strip()

        chunks = parser.chunk(content, "constants.rs")

        # Should find const and static declarations
        const_chunks = [c for c in chunks if c.semantic_type == "const"]
        static_chunks = [c for c in chunks if c.semantic_type == "static"]
        function_chunks = [c for c in chunks if c.semantic_type == "function"]

        assert len(const_chunks) >= 4
        assert len(static_chunks) >= 3
        assert len(function_chunks) >= 1

        # Check const names
        const_names = {c.semantic_name for c in const_chunks}
        assert "PI" in const_names
        assert "MAX_SIZE" in const_names
        assert "GREETING" in const_names
        assert "COMPUTED_VALUE" in const_names

        # Check static names
        static_names = {c.semantic_name for c in static_chunks}
        assert "GLOBAL_COUNTER" in static_names
        assert "GLOBAL_ARRAY" in static_names
        assert "VERSION" in static_names

        # Check features
        max_size_const = next(c for c in const_chunks if c.semantic_name == "MAX_SIZE")
        assert "public" in max_size_const.semantic_language_features

        global_array_static = next(
            c for c in static_chunks if c.semantic_name == "GLOBAL_ARRAY"
        )
        assert "public" in global_array_static.semantic_language_features
        assert "mutable" in global_array_static.semantic_language_features

    def test_type_aliases(self, parser):
        """Test parsing Rust type aliases."""
        content = dedent(
            """
            type Result<T> = std::result::Result<T, Box<dyn Error>>;
            pub type IoResult<T> = std::io::Result<T>;
            type Point3D = (f64, f64, f64);

            type GenericCallback<T> = Box<dyn Fn(T) -> T>;
            pub type StringCallback = GenericCallback<String>;

            type ComplexType<'a, T, U> = HashMap<&'a str, (T, U)>
            where
                T: Clone,
                U: Debug;
        """
        ).strip()

        chunks = parser.chunk(content, "types.rs")

        # Should find type alias declarations
        type_chunks = [c for c in chunks if c.semantic_type == "type"]
        assert len(type_chunks) >= 6

        type_names = {c.semantic_name for c in type_chunks}
        assert "Result" in type_names
        assert "IoResult" in type_names
        assert "Point3D" in type_names
        assert "GenericCallback" in type_names
        assert "StringCallback" in type_names
        assert "ComplexType" in type_names

        # Check generic types
        result_type = next(c for c in type_chunks if c.semantic_name == "Result")
        assert "generic" in result_type.semantic_language_features

        # Check public types
        io_result_type = next(c for c in type_chunks if c.semantic_name == "IoResult")
        assert "public" in io_result_type.semantic_language_features

    def test_union_declarations(self, parser):
        """Test parsing Rust union definitions."""
        content = dedent(
            """
            union IntOrFloat {
                i: i32,
                f: f32,
            }

            pub union Value {
                integer: i64,
                float: f64,
                boolean: bool,
            }

            #[repr(C)]
            union CCompatible {
                a: u32,
                b: [u8; 4],
            }
        """
        ).strip()

        chunks = parser.chunk(content, "unions.rs")

        # Should find union declarations
        union_chunks = [c for c in chunks if c.semantic_type == "union"]
        assert len(union_chunks) >= 3

        union_names = {c.semantic_name for c in union_chunks}
        assert "IntOrFloat" in union_names
        assert "Value" in union_names
        assert "CCompatible" in union_names

        # Check public union
        value_union = next(c for c in union_chunks if c.semantic_name == "Value")
        assert "public" in value_union.semantic_language_features

    def test_module_declarations(self, parser):
        """Test parsing Rust module declarations."""
        content = dedent(
            """
            mod utils;
            pub mod network;
            mod database {
                pub fn connect() -> Connection {
                    // Implementation
                }
                
                mod internal {
                    fn helper() {}
                }
            }

            pub mod math {
                pub fn add(a: i32, b: i32) -> i32 {
                    a + b
                }
                
                pub mod advanced {
                    pub fn complex_calculation() -> f64 {
                        3.14159
                    }
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "modules.rs")

        # Should find module declarations
        module_chunks = [c for c in chunks if c.semantic_type == "module"]
        function_chunks = [c for c in chunks if c.semantic_type == "function"]

        assert len(module_chunks) >= 2  # Only inline modules are captured
        assert len(function_chunks) >= 3

        # Check inline modules
        inline_modules = [
            c
            for c in module_chunks
            if "database" in c.semantic_name or "math" in c.semantic_name
        ]
        assert len(inline_modules) >= 2

    def test_use_statements(self, parser):
        """Test parsing Rust use statements."""
        content = dedent(
            """
            use std::collections::HashMap;
            use std::io::{self, Write};
            use std::thread;
            use serde::{Deserialize, Serialize};

            use crate::utils::*;
            use super::parent_module::SomeStruct;
            use self::nested::NestedStruct;

            pub use std::collections::BTreeMap;
            use std::sync::{Arc, Mutex};

            #[cfg(feature = "network")]
            use reqwest::Client;
        """
        ).strip()

        chunks = parser.chunk(content, "imports.rs")

        # Should find use statements
        use_chunks = [c for c in chunks if c.semantic_type == "use"]
        assert len(use_chunks) >= 8

        # Check use statement content
        use_names = {c.semantic_name for c in use_chunks}
        assert "std::collections::HashMap" in use_names or "HashMap" in use_names
        assert any("serde" in name for name in use_names)
        assert any("thread" in name for name in use_names)

    def test_generic_constructs(self, parser):
        """Test parsing Rust generic constructs."""
        content = dedent(
            """
            struct Container<T> {
                value: T,
            }

            impl<T: Clone> Container<T> {
                fn new(value: T) -> Self {
                    Container { value }
                }

                fn get(&self) -> T {
                    self.value.clone()
                }
            }

            enum Option<T> {
                Some(T),
                None,
            }

            trait Iterator<Item> {
                type Item;
                fn next(&mut self) -> Option<Self::Item>;
            }

            fn generic_function<T, U>(a: T, b: U) -> (T, U)
            where
                T: Clone + Debug,
                U: Send + Sync,
            {
                (a, b)
            }

            struct PhantomContainer<T> {
                _phantom: std::marker::PhantomData<T>,
            }
        """
        ).strip()

        chunks = parser.chunk(content, "generics.rs")

        # Should find generic constructs
        generic_chunks = [
            c for c in chunks if "generic" in c.semantic_language_features
        ]
        assert len(generic_chunks) >= 6

        # Check different types of generic constructs
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        [c for c in chunks if c.semantic_type == "impl"]
        enum_chunks = [c for c in chunks if c.semantic_type == "enum"]
        [c for c in chunks if c.semantic_type == "trait"]
        [c for c in chunks if c.semantic_type == "function"]

        # Verify generics are detected
        container_struct = next(
            c for c in struct_chunks if c.semantic_name == "Container"
        )
        assert "generic" in container_struct.semantic_language_features

        option_enum = next(c for c in enum_chunks if c.semantic_name == "Option")
        assert "generic" in option_enum.semantic_language_features

    def test_error_node_handling_basic(self, parser):
        """Test ERROR node handling for basic syntax errors."""
        content = dedent(
            """
            struct ValidStruct {
                field: i32,
            }

            struct BrokenStruct {
                field: i32  // Missing semicolon
                another_field: String,
            }

            fn valid_function() -> i32 {
                42
            }

            fn broken_function() -> i32 {
                // Missing return statement or expression
            }

            enum ValidEnum {
                Variant1,
                Variant2,
            }
        """
        ).strip()

        chunks = parser.chunk(content, "broken.rs")

        # Should extract constructs despite syntax errors
        assert len(chunks) >= 3

        # Should find valid constructs
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        enum_chunks = [c for c in chunks if c.semantic_type == "enum"]

        assert len(struct_chunks) >= 1
        assert len(function_chunks) >= 1
        assert len(enum_chunks) >= 1

        # Check that valid names are found
        all_names = {c.semantic_name for c in chunks if c.semantic_name}
        assert (
            "ValidStruct" in all_names
            or "valid_function" in all_names
            or "ValidEnum" in all_names
        )

    def test_error_node_handling_impl_errors(self, parser):
        """Test ERROR node handling for impl block syntax errors."""
        content = dedent(
            """
            struct Rectangle {
                width: f64,
                height: f64,
            }

            impl Rectangle {
                fn area(&self) -> f64 {
                    self.width * self.height
                }
                
                fn broken_method(&self) -> f64 {
                    // Missing implementation
                }
                
                fn valid_method(&self) -> bool {
                    self.width > 0.0 && self.height > 0.0
                }
            }

            impl Display for Rectangle
            // Missing opening brace
                fn fmt(&self, f: &mut Formatter) -> Result<(), Error> {
                    write!(f, "{}x{}", self.width, self.height)
                }
            }

            impl Clone for Rectangle {
                fn clone(&self) -> Self {
                    Rectangle {
                        width: self.width,
                        height: self.height,
                    }
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "impl_errors.rs")

        # Should extract constructs despite impl syntax errors
        assert len(chunks) >= 3

        # Should find valid constructs
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        impl_chunks = [c for c in chunks if c.semantic_type == "impl"]
        function_chunks = [c for c in chunks if c.semantic_type == "function"]

        assert len(struct_chunks) >= 1
        assert len(impl_chunks) >= 2
        assert len(function_chunks) >= 3

    def test_error_node_handling_generic_errors(self, parser):
        """Test ERROR node handling for generic syntax errors."""
        content = dedent(
            """
            struct ValidGeneric<T> {
                value: T,
            }

            struct BrokenGeneric<T where
            // Incomplete where clause
            {
                value: T,
            }

            impl<T: Clone> ValidGeneric<T> {
                fn new(value: T) -> Self {
                    ValidGeneric { value }
                }
            }

            trait ValidTrait<T> {
                fn method(&self) -> T;
            }

            fn valid_generic_function<T, U>(a: T, b: U) -> (T, U) {
                (a, b)
            }
        """
        ).strip()

        chunks = parser.chunk(content, "generic_errors.rs")

        # Should extract constructs despite generic syntax errors
        assert len(chunks) >= 3

        # Should find valid constructs
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        impl_chunks = [c for c in chunks if c.semantic_type == "impl"]
        trait_chunks = [c for c in chunks if c.semantic_type == "trait"]
        function_chunks = [c for c in chunks if c.semantic_type == "function"]

        valid_chunks = struct_chunks + impl_chunks + trait_chunks + function_chunks
        assert len(valid_chunks) >= 4

        # Check that valid names are found
        all_names = {c.semantic_name for c in valid_chunks if c.semantic_name}
        assert "ValidGeneric" in all_names or "ValidTrait" in all_names

    def test_malformed_rust_code_handling(self, parser):
        """Test handling of completely malformed Rust code."""
        malformed_content = """
            This is not valid Rust code at all!
            struct??? broken syntax everywhere
            fn incomplete((( parameters
            impl Invalid for %%% nonsense
            trait:::: malformed
        """

        # Should not crash and should return minimal chunks
        chunks = parser.chunk(malformed_content, "malformed.rs")

        # Parser should handle gracefully
        assert isinstance(chunks, list)

    def test_chunker_integration(self, chunker):
        """Test integration with SemanticChunker for Rust files."""
        content = dedent(
            """
            use std::collections::HashMap;

            #[derive(Debug, Clone)]
            pub struct User {
                pub id: u32,
                pub name: String,
                pub email: String,
            }

            impl User {
                pub fn new(id: u32, name: String, email: String) -> Self {
                    Self { id, name, email }
                }

                pub fn display_info(&self) {
                    println!("User {}: {} ({})", self.id, self.name, self.email);
                }
            }

            pub trait Storage {
                fn store(&mut self, user: User) -> Result<(), Box<dyn Error>>;
                fn retrieve(&self, id: u32) -> Option<&User>;
            }

            pub struct InMemoryStorage {
                users: HashMap<u32, User>,
            }

            impl Storage for InMemoryStorage {
                fn store(&mut self, user: User) -> Result<(), Box<dyn Error>> {
                    self.users.insert(user.id, user);
                    Ok(())
                }

                fn retrieve(&self, id: u32) -> Option<&User> {
                    self.users.get(&id)
                }
            }
        """
        ).strip()

        chunks = chunker.chunk_content(content, "user_system.rs")

        # Should get semantic chunks from Rust parser
        assert len(chunks) >= 5

        # Verify chunks have semantic metadata
        for chunk in chunks:
            assert chunk.get("semantic_chunking") is True
            assert "semantic_type" in chunk
            assert "semantic_name" in chunk
            assert "semantic_path" in chunk

    def test_advanced_rust_features(self, parser):
        """Test parsing advanced Rust features."""
        content = dedent(
            """
            use std::pin::Pin;
            use std::future::Future;

            // Async trait
            #[async_trait]
            pub trait AsyncProcessor {
                async fn process(&self, data: &str) -> Result<String, ProcessError>;
            }

            // Lifetime parameters
            struct LifetimeExample<'a> {
                data: &'a str,
            }

            impl<'a> LifetimeExample<'a> {
                fn new(data: &'a str) -> Self {
                    Self { data }
                }
            }

            // Associated types
            trait Collector {
                type Item;
                type Output;
                
                fn collect(items: Vec<Self::Item>) -> Self::Output;
            }

            // Higher-ranked trait bounds
            fn higher_ranked<F>(f: F) 
            where
                F: for<'a> Fn(&'a str) -> &'a str,
            {
                // Implementation
            }

            // Const generics
            struct ArrayWrapper<T, const N: usize> {
                array: [T; N],
            }

            impl<T: Clone, const N: usize> ArrayWrapper<T, N> {
                fn new(value: T) -> Self {
                    Self {
                        array: [value; N],
                    }
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "advanced.rs")

        # Should handle advanced features without crashing
        assert len(chunks) >= 5

        # Should find the main constructs
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        trait_chunks = [c for c in chunks if c.semantic_type == "trait"]
        impl_chunks = [c for c in chunks if c.semantic_type == "impl"]
        [c for c in chunks if c.semantic_type == "function"]

        assert len(struct_chunks) >= 2
        assert len(trait_chunks) >= 2
        assert len(impl_chunks) >= 2

        # Check names
        all_names = {c.semantic_name for c in struct_chunks + trait_chunks}
        assert "LifetimeExample" in all_names or "AsyncProcessor" in all_names

    def test_regex_fallback_functionality(self, parser):
        """Test regex fallback for Rust when tree-sitter fails."""
        # Test the regex fallback method directly
        error_text = """
            struct TestStruct {
                field: i32,
            }
            
            pub enum TestEnum {
                Variant1,
                Variant2,
            }
            
            impl TestStruct {
                fn method(&self) -> i32 {
                    self.field
                }
            }
            
            trait TestTrait {
                fn required_method(&self);
            }
            
            fn test_function() -> i32 {
                42
            }
            
            const TEST_CONST: i32 = 42;
            static TEST_STATIC: &str = "test";
            type TestType = Vec<i32>;
            
            macro_rules! test_macro {
                () => { println!("test"); };
            }
            
            use std::collections::HashMap;
            mod test_module;
        """

        constructs = parser._extract_constructs_from_error_text(error_text, 1, [])

        # Should find constructs through regex
        assert len(constructs) >= 8

        # Check that different construct types were found
        construct_types = {c["type"] for c in constructs}
        expected_types = {
            "struct",
            "enum",
            "impl",
            "trait",
            "function",
            "const",
            "static",
            "type",
            "macro",
            "use",
            "module",
        }
        assert len(construct_types.intersection(expected_types)) >= 6

    def test_ownership_and_borrowing_patterns(self, parser):
        """Test parsing Rust ownership and borrowing patterns."""
        content = dedent(
            """
            fn take_ownership(s: String) {
                println!("{}", s);
            }

            fn borrow_string(s: &String) {
                println!("{}", s);
            }

            fn mutable_borrow(s: &mut String) {
                s.push_str(" world");
            }

            fn return_ownership() -> String {
                String::from("hello")
            }

            fn multiple_references(s1: &str, s2: &str) -> bool {
                s1.len() > s2.len()
            }

            struct Owner {
                data: Box<i32>,
            }

            impl Owner {
                fn new(value: i32) -> Self {
                    Self {
                        data: Box::new(value),
                    }
                }

                fn get_ref(&self) -> &i32 {
                    &self.data
                }

                fn get_mut(&mut self) -> &mut i32 {
                    &mut self.data
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "ownership.rs")

        # Should handle ownership patterns without issues
        assert len(chunks) >= 5

        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        impl_chunks = [c for c in chunks if c.semantic_type == "impl"]

        assert len(function_chunks) >= 5
        assert len(struct_chunks) >= 1
        assert len(impl_chunks) >= 1

        # Check function names
        function_names = {c.semantic_name for c in function_chunks}
        assert "take_ownership" in function_names
        assert "borrow_string" in function_names
        assert "mutable_borrow" in function_names

    def test_data_preservation_no_loss(self, parser):
        """Test that chunking preserves all content without data loss."""
        content = dedent(
            """
            //! A comprehensive Rust library demonstrating various language features.
            //! 
            //! This library showcases structs, enums, traits, implementations,
            //! generics, lifetimes, and error handling.

            use std::collections::HashMap;
            use std::error::Error;
            use std::fmt::{self, Display, Formatter};
            use std::result::Result;

            /// Custom error type for the library
            #[derive(Debug, Clone)]
            pub struct LibraryError {
                message: String,
            }

            impl Display for LibraryError {
                fn fmt(&self, f: &mut Formatter<'_>) -> fmt::Result {
                    write!(f, "Library error: {}", self.message)
                }
            }

            impl Error for LibraryError {}

            /// A generic container that can hold any type implementing Clone
            #[derive(Debug, Clone)]
            pub struct Container<T: Clone> {
                items: Vec<T>,
                metadata: HashMap<String, String>,
            }

            impl<T: Clone> Container<T> {
                /// Creates a new empty container
                pub fn new() -> Self {
                    Self {
                        items: Vec::new(),
                        metadata: HashMap::new(),
                    }
                }

                /// Adds an item to the container
                pub fn add(&mut self, item: T) {
                    self.items.push(item);
                }

                /// Gets a reference to an item by index
                pub fn get(&self, index: usize) -> Option<&T> {
                    self.items.get(index)
                }

                /// Returns the number of items in the container
                pub fn len(&self) -> usize {
                    self.items.len()
                }

                /// Checks if the container is empty
                pub fn is_empty(&self) -> bool {
                    self.items.is_empty()
                }

                /// Sets metadata for the container
                pub fn set_metadata(&mut self, key: String, value: String) {
                    self.metadata.insert(key, value);
                }
            }

            impl<T: Clone> Default for Container<T> {
                fn default() -> Self {
                    Self::new()
                }
            }

            /// Trait for objects that can be processed
            pub trait Processable {
                type Output;
                type Error: Error;

                fn process(&self) -> Result<Self::Output, Self::Error>;
            }

            /// Enum representing different processing states
            #[derive(Debug, Clone, PartialEq)]
            pub enum ProcessingState {
                Pending,
                Processing,
                Completed(String),
                Failed(String),
            }

            impl Display for ProcessingState {
                fn fmt(&self, f: &mut Formatter<'_>) -> fmt::Result {
                    match self {
                        ProcessingState::Pending => write!(f, "Pending"),
                        ProcessingState::Processing => write!(f, "Processing"),
                        ProcessingState::Completed(msg) => write!(f, "Completed: {}", msg),
                        ProcessingState::Failed(err) => write!(f, "Failed: {}", err),
                    }
                }
            }

            /// Async trait for background processing
            #[async_trait::async_trait]
            pub trait AsyncProcessor {
                async fn process_async(&self, data: &str) -> Result<String, Box<dyn Error>>;
            }

            /// A processor implementation
            pub struct DataProcessor {
                pub name: String,
                pub state: ProcessingState,
            }

            impl DataProcessor {
                pub fn new(name: String) -> Self {
                    Self {
                        name,
                        state: ProcessingState::Pending,
                    }
                }
            }

            #[async_trait::async_trait]
            impl AsyncProcessor for DataProcessor {
                async fn process_async(&self, data: &str) -> Result<String, Box<dyn Error>> {
                    // Simulate async processing
                    tokio::time::sleep(std::time::Duration::from_millis(100)).await;
                    Ok(format!("Processed: {}", data))
                }
            }

            /// Module for utility functions
            pub mod utils {
                use super::*;

                /// Utility function to create a container with initial items
                pub fn create_container_with_items<T: Clone>(items: Vec<T>) -> Container<T> {
                    let mut container = Container::new();
                    for item in items {
                        container.add(item);
                    }
                    container
                }

                /// Macro for easy container creation
                macro_rules! container {
                    ($($item:expr),* $(,)?) => {
                        {
                            let mut container = Container::new();
                            $(
                                container.add($item);
                            )*
                            container
                        }
                    };
                }

                pub(crate) use container;
            }

            /// Constants used throughout the library
            pub const DEFAULT_CAPACITY: usize = 100;
            pub const VERSION: &str = "1.0.0";
            static GLOBAL_COUNTER: std::sync::atomic::AtomicUsize = 
                std::sync::atomic::AtomicUsize::new(0);

            /// Type alias for convenience
            pub type StringContainer = Container<String>;
            pub type Result<T> = std::result::Result<T, LibraryError>;
        """
        ).strip()

        chunks = parser.chunk(content, "data_preservation.rs")

        # Verify no data loss by checking that all content is captured
        all_chunk_content = "\n".join(chunk.text for chunk in chunks)

        # Check that essential elements are preserved
        assert "use std::collections::HashMap" in all_chunk_content
        assert "pub struct LibraryError" in all_chunk_content
        assert "pub struct Container<T: Clone>" in all_chunk_content
        assert "pub trait Processable" in all_chunk_content
        assert "pub enum ProcessingState" in all_chunk_content
        assert "impl<T: Clone> Container<T>" in all_chunk_content
        assert "pub mod utils" in all_chunk_content
        assert "macro_rules! container" in all_chunk_content
        assert "pub const DEFAULT_CAPACITY" in all_chunk_content

        # Check that we have reasonable chunk coverage
        assert len(chunks) >= 8  # Should have multiple semantic chunks

        # Verify all chunks have proper metadata
        for chunk in chunks:
            assert chunk.semantic_chunking is True
            assert chunk.semantic_type is not None
            assert chunk.semantic_name is not None
            assert chunk.file_path == "data_preservation.rs"
            assert chunk.line_start > 0
            assert chunk.line_end >= chunk.line_start

    def test_file_extension_detection(self, parser):
        """Test detection of Rust file extensions."""
        simple_content = """
            fn main() {
                println!("Hello, world!");
            }
        """

        # Test Rust file extension
        chunks = parser.chunk(simple_content, "main.rs")
        assert len(chunks) >= 1
        assert chunks[0].file_extension == ".rs"

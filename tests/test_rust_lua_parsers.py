"""Tests for Rust and Lua semantic parsers."""

import pytest
from pathlib import Path

from code_indexer.config import IndexingConfig
from code_indexer.indexing.rust_parser import RustSemanticParser
from code_indexer.indexing.lua_parser import LuaSemanticParser
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestRustSemanticParser:
    """Test Rust semantic parser functionality."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return IndexingConfig(use_semantic_chunking=True)

    @pytest.fixture
    def rust_parser(self, config):
        """Create Rust parser instance."""
        return RustSemanticParser(config)

    def test_rust_basic_constructs(self, rust_parser):
        """Test parsing basic Rust constructs."""
        code = """
use std::collections::HashMap;

pub struct User {
    id: u32,
    name: String,
}

impl User {
    pub fn new(id: u32, name: String) -> Self {
        Self { id, name }
    }
}

pub fn process_user(user: &User) -> String {
    format!("User: {}", user.name)
}

const MAX_USERS: usize = 100;
"""
        chunks = rust_parser.chunk(code, "test.rs")

        # Should have use, struct, impl, function, and const
        assert len(chunks) >= 4

        # Check for expected construct types
        types = [chunk.semantic_type for chunk in chunks]
        assert "use" in types
        assert "struct" in types
        assert "impl" in types
        assert "function" in types
        assert "const" in types

    def test_rust_traits_and_enums(self, rust_parser):
        """Test parsing Rust traits and enums."""
        code = """
pub trait Display {
    fn fmt(&self) -> String;
}

pub enum Color {
    Red,
    Green,
    Blue,
}
"""
        chunks = rust_parser.chunk(code, "test.rs")

        types = [chunk.semantic_type for chunk in chunks]
        assert "trait" in types
        assert "enum" in types

    def test_rust_macros(self, rust_parser):
        """Test parsing Rust macros."""
        code = """
macro_rules! debug_print {
    ($x:expr) => {
        println!("{:?}", $x);
    };
}
"""
        chunks = rust_parser.chunk(code, "test.rs")

        types = [chunk.semantic_type for chunk in chunks]
        assert "macro" in types

    def test_rust_error_fallback(self, rust_parser):
        """Test Rust ERROR node fallback."""
        # This should cause tree-sitter errors and trigger fallback
        malformed_code = """
struct User
    id: u32,
    name: String
}

fn broken_function(
    user
"""
        chunks = rust_parser.chunk(malformed_code, "test.rs")

        # Should still extract something via regex fallback
        assert len(chunks) > 0


class TestLuaSemanticParser:
    """Test Lua semantic parser functionality."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return IndexingConfig(use_semantic_chunking=True)

    @pytest.fixture
    def lua_parser(self, config):
        """Create Lua parser instance."""
        return LuaSemanticParser(config)

    def test_lua_basic_functions(self, lua_parser):
        """Test parsing basic Lua functions."""
        code = """
local json = require("json")

function global_function(name)
    return "Hello " .. name
end

local function local_function(x, y)
    return x + y
end

local UserManager = {}

function UserManager:new(config)
    local obj = {config = config}
    setmetatable(obj, self)
    self.__index = self
    return obj
end

function UserManager.static_method()
    return "static"
end
"""
        chunks = lua_parser.chunk(code, "test.lua")

        # Should have require, functions, table, and methods
        assert len(chunks) >= 4

        types = [chunk.semantic_type for chunk in chunks]
        [chunk.semantic_name for chunk in chunks]

        assert "function" in types
        assert "local_function" in types
        assert "method" in types
        # Should have either "table" or "local_table" depending on scope
        assert "table" in types or "local_table" in types

        # Check for method vs function distinction
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        assert any(":" in c.semantic_name for c in method_chunks)

    def test_lua_tables_and_modules(self, lua_parser):
        """Test parsing Lua tables and module patterns."""
        code = """
local M = {}

M.config = {
    debug = true,
    version = "1.0"
}

M.utils = {
    trim = function(str)
        return str:match("^%s*(.-)%s*$")
    end,
    
    split = function(str, delimiter)
        local result = {}
        -- implementation here
        return result
    end
}

return M
"""
        chunks = lua_parser.chunk(code, "test.lua")

        types = [chunk.semantic_type for chunk in chunks]
        assert "table" in types
        assert "module_return" in types

    def test_lua_error_fallback(self, lua_parser):
        """Test Lua ERROR node fallback."""
        # Malformed Lua code that should trigger fallback
        malformed_code = """
function broken_function(
    name
    return "Hello " .. name

local table = {
    key = value
"""
        chunks = lua_parser.chunk(malformed_code, "test.lua")

        # Should still extract something via regex fallback
        assert len(chunks) > 0

    def test_error_node_handling_table_errors(self, lua_parser):
        """Test that functions are extracted even when there are table syntax errors."""
        # Code with valid functions but malformed table syntax
        code_with_table_errors = """
function valid_function()
    return 'works'
end

local broken_table = {
    key = value  -- Missing quotes, should cause parse error
    unclosed_key = 
}

function another_function()
    print('also works')
end
"""
        chunks = lua_parser.chunk(code_with_table_errors, "test.lua")

        # Should extract at least the 2 valid functions
        function_chunks = [
            c
            for c in chunks
            if hasattr(c, "semantic_type") and "function" in c.semantic_type
        ]
        assert (
            len(function_chunks) >= 2
        ), f"Expected at least 2 functions, got {len(function_chunks)}"

        # Check that the function names are correct
        function_names = [c.semantic_name for c in function_chunks]
        assert "valid_function" in function_names
        assert "another_function" in function_names

    def test_data_preservation_no_loss(self, lua_parser):
        """Test that semantic parsing preserves all meaningful constructs without duplication."""
        original_code = """
function test_func()
    local x = 1
    return x
end

local table = {
    key = "value"
}
"""
        chunks = lua_parser.chunk(original_code, "test.lua")

        assert len(chunks) > 0, "Should produce at least one chunk"

        # Check that we have the expected constructs without duplicates

        # Should have exactly one function and one table
        function_chunks = [c for c in chunks if "function" in c.semantic_type]
        table_chunks = [c for c in chunks if "table" in c.semantic_type]

        assert (
            len(function_chunks) == 1
        ), f"Expected exactly 1 function chunk, got {len(function_chunks)}"
        assert (
            len(table_chunks) == 1
        ), f"Expected exactly 1 table chunk, got {len(table_chunks)}"

        # Verify function construct
        func_chunk = function_chunks[0]
        assert func_chunk.semantic_name == "test_func"
        assert "local x = 1" in func_chunk.text
        assert "return x" in func_chunk.text

        # Verify table construct
        table_chunk = table_chunks[0]
        assert table_chunk.semantic_name == "table"
        assert 'key = "value"' in table_chunk.text

        # Ensure no duplicate constructs (same name, same lines)
        construct_signatures = []
        for chunk in chunks:
            signature = (chunk.semantic_name, chunk.line_start, chunk.line_end)
            assert (
                signature not in construct_signatures
            ), f"Duplicate construct found: {chunk.semantic_name} at lines {chunk.line_start}-{chunk.line_end}"
            construct_signatures.append(signature)


class TestSemanticChunkerIntegration:
    """Test integration of Rust and Lua parsers with SemanticChunker."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return IndexingConfig(use_semantic_chunking=True)

    @pytest.fixture
    def chunker(self, config):
        """Create semantic chunker instance."""
        return SemanticChunker(config)

    def test_rust_file_detection(self, chunker):
        """Test that .rs files are detected as Rust."""
        # Create a temporary Rust file
        test_file = Path("test.rs")
        rust_code = """
pub fn hello() {
    println!("Hello, world!");
}
"""
        try:
            with open(test_file, "w") as f:
                f.write(rust_code)

            chunks = chunker.chunk_file(test_file)

            # Should have semantic chunking enabled
            assert any(chunk.get("semantic_chunking", False) for chunk in chunks)

        finally:
            if test_file.exists():
                test_file.unlink()

    def test_lua_file_detection(self, chunker):
        """Test that .lua files are detected as Lua."""
        # Create a temporary Lua file
        test_file = Path("test.lua")
        lua_code = """
function hello()
    print("Hello, world!")
end
"""
        try:
            with open(test_file, "w") as f:
                f.write(lua_code)

            chunks = chunker.chunk_file(test_file)

            # Should have semantic chunking enabled
            assert any(chunk.get("semantic_chunking", False) for chunk in chunks)

        finally:
            if test_file.exists():
                test_file.unlink()

    def test_language_map_includes_rust_and_lua(self, chunker):
        """Test that language detection includes Rust and Lua."""
        assert chunker._detect_language("test.rs") == "rust"
        assert chunker._detect_language("test.lua") == "lua"
        assert chunker._detect_language("script.lua") == "lua"

    def test_parser_registration(self, chunker):
        """Test that parsers are properly registered."""
        assert "rust" in chunker.parsers
        assert "lua" in chunker.parsers
        assert isinstance(chunker.parsers["rust"], RustSemanticParser)
        assert isinstance(chunker.parsers["lua"], LuaSemanticParser)

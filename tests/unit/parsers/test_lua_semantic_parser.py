"""
Tests for Lua semantic parser.
Following TDD approach - writing comprehensive tests to ensure complete coverage
of Lua language constructs including ERROR node handling.
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestLuaSemanticParser:
    """Test Lua semantic parser using tree-sitter."""

    @pytest.fixture
    def chunker(self):
        """Create a semantic chunker with semantic chunking enabled."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return SemanticChunker(config)

    @pytest.fixture
    def parser(self):
        """Create a Lua parser directly."""
        from code_indexer.indexing.lua_parser import LuaSemanticParser

        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return LuaSemanticParser(config)

    def test_basic_function_declarations(self, parser):
        """Test parsing basic Lua function definitions."""
        content = dedent(
            """
            function hello()
                print("Hello, World!")
            end

            function add(a, b)
                return a + b
            end

            function greet(name)
                return "Hello, " .. name
            end

            function multiply(x, y, z)
                if z then
                    return x * y * z
                else
                    return x * y
                end
            end

            function factorial(n)
                if n <= 1 then
                    return 1
                else
                    return n * factorial(n - 1)
                end
            end
        """
        ).strip()

        chunks = parser.chunk(content, "functions.lua")

        # Should find function declarations
        assert len(chunks) >= 5

        # Check function chunks
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) >= 5

        function_names = {c.semantic_name for c in function_chunks}
        assert "hello" in function_names
        assert "add" in function_names
        assert "greet" in function_names
        assert "multiply" in function_names
        assert "factorial" in function_names

        # Check function signatures
        add_func = next(c for c in function_chunks if c.semantic_name == "add")
        assert add_func.semantic_path == "add"
        assert "function add" in add_func.semantic_signature

    def test_local_function_declarations(self, parser):
        """Test parsing Lua local function definitions."""
        content = dedent(
            """
            local function helper()
                return "I'm a helper function"
            end

            local function calculate(x, y)
                return x * y + 10
            end

            function main()
                local result = calculate(5, 3)
                print(helper())
                return result
            end

            local function private_operation(data)
                -- Process data locally
                return data:upper()
            end

            local my_func = function(param)
                return param * 2
            end
        """
        ).strip()

        chunks = parser.chunk(content, "local_functions.lua")

        # Should find both local and global functions
        function_chunks = [
            c for c in chunks if c.semantic_type in ["function", "local_function"]
        ]
        assert len(function_chunks) >= 5

        # Check local functions
        local_functions = [
            c for c in function_chunks if c.semantic_type == "local_function"
        ]
        assert len(local_functions) >= 3

        local_names = {c.semantic_name for c in local_functions}
        assert (
            "helper" in local_names
            or "calculate" in local_names
            or "my_func" in local_names
        )

        # Check features
        helper_func = next(
            (c for c in local_functions if c.semantic_name == "helper"), None
        )
        if helper_func:
            assert "local" in helper_func.semantic_language_features
            assert helper_func.semantic_scope == "local"

    def test_table_declarations(self, parser):
        """Test parsing Lua table definitions."""
        content = dedent(
            """
            local person = {
                name = "John",
                age = 30,
                city = "New York"
            }

            local calculator = {
                add = function(a, b)
                    return a + b
                end,
                
                subtract = function(a, b)
                    return a - b
                end,
                
                multiply = function(a, b)
                    return a * b
                end
            }

            config = {
                debug = true,
                timeout = 5000,
                retries = 3
            }

            local animals = {
                "cat", "dog", "bird", "fish"
            }

            mixed_table = {
                [1] = "first",
                [2] = "second",
                name = "mixed",
                func = function() return "hello" end
            }
        """
        ).strip()

        chunks = parser.chunk(content, "tables.lua")

        # Should find table declarations
        table_chunks = [
            c for c in chunks if c.semantic_type in ["table", "local_table"]
        ]
        assert len(table_chunks) >= 5

        table_names = {c.semantic_name for c in table_chunks}
        assert "person" in table_names
        assert "calculator" in table_names
        assert "config" in table_names
        assert "animals" in table_names
        assert "mixed_table" in table_names

        # Should also find functions within tables
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) >= 3

        # Check local tables
        local_tables = [c for c in table_chunks if c.semantic_type == "local_table"]
        assert len(local_tables) >= 2

        # Check features
        person_table = next(
            (c for c in table_chunks if c.semantic_name == "person"), None
        )
        if person_table:
            assert "local" in person_table.semantic_language_features
            assert "table" in person_table.semantic_language_features

    def test_method_declarations(self, parser):
        """Test parsing Lua method definitions (using colon syntax)."""
        content = dedent(
            """
            Person = {}

            function Person:new(name, age)
                local obj = {
                    name = name,
                    age = age
                }
                setmetatable(obj, self)
                self.__index = self
                return obj
            end

            function Person:getName()
                return self.name
            end

            function Person:setName(name)
                self.name = name
            end

            function Person:getAge()
                return self.age
            end

            function Person:birthday()
                self.age = self.age + 1
            end

            function Person:toString()
                return self.name .. " is " .. self.age .. " years old"
            end

            -- Static method using dot notation
            function Person.createChild(parent, name)
                return Person:new(name, 0)
            end
        """
        ).strip()

        chunks = parser.chunk(content, "methods.lua")

        # Should find methods and functions
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        function_chunks = [c for c in chunks if c.semantic_type == "function"]

        assert len(method_chunks) >= 6
        assert len(function_chunks) >= 1  # The static method

        # Check method names
        method_names = {c.semantic_name for c in method_chunks}
        assert "Person:new" in method_names
        assert "Person:getName" in method_names
        assert "Person:setName" in method_names
        assert "Person:getAge" in method_names
        assert "Person:birthday" in method_names
        assert "Person:toString" in method_names

        # Check method features
        new_method = next(c for c in method_chunks if c.semantic_name == "Person:new")
        assert "method" in new_method.semantic_language_features

    def test_module_patterns(self, parser):
        """Test parsing Lua module patterns."""
        content = dedent(
            """
            local M = {}

            local function private_helper()
                return "private"
            end

            function M.public_function(param)
                return private_helper() .. " " .. param
            end

            function M:method_style(data)
                return self.process(data)
            end

            M.process = function(data)
                return data:upper()
            end

            M.constants = {
                VERSION = "1.0.0",
                DEBUG = false
            }

            local function init()
                M.initialized = true
            end

            init()

            return M
        """
        ).strip()

        chunks = parser.chunk(content, "module.lua")

        # Should find various constructs
        table_chunks = [
            c for c in chunks if c.semantic_type in ["table", "local_table"]
        ]
        function_chunks = [
            c for c in chunks if c.semantic_type in ["function", "local_function"]
        ]
        return_chunks = [c for c in chunks if c.semantic_type == "module_return"]

        assert len(table_chunks) >= 2  # M and M.constants
        assert len(function_chunks) >= 4
        assert len(return_chunks) >= 1

        # Check module return
        module_return = return_chunks[0]
        assert module_return.semantic_name == "M"
        assert "module_export" in module_return.semantic_language_features

    def test_require_statements(self, parser):
        """Test parsing Lua require statements."""
        content = dedent(
            """
            local json = require("json")
            local http = require("socket.http")
            local utils = require("my.utils")

            require("strict")

            local socket = require "socket"
            local lfs = require 'lfs'

            local has_lpeg, lpeg = pcall(require, "lpeg")

            function load_modules()
                local config = require("config.settings")
                local db = require("database.connection")
                return config, db
            end

            -- Dynamic require
            local module_name = "dynamic.module"
            local dynamic = require(module_name)
        """
        ).strip()

        chunks = parser.chunk(content, "requires.lua")

        # Should find require statements
        require_chunks = [c for c in chunks if c.semantic_type == "require"]
        assert len(require_chunks) >= 6

        # Check require names and modules
        require_names = {c.semantic_name for c in require_chunks}
        assert "json" in require_names
        assert "http" in require_names
        assert "utils" in require_names

        # Check module paths
        json_require = next(
            (c for c in require_chunks if c.semantic_name == "json"), None
        )
        if json_require and json_require.semantic_context.get("module_path"):
            assert json_require.semantic_context["module_path"] == "json"

        # Check features
        for require_chunk in require_chunks:
            assert "module_import" in require_chunk.semantic_language_features

    def test_coroutine_functions(self, parser):
        """Test parsing Lua coroutine functions."""
        content = dedent(
            """
            function producer()
                return coroutine.create(function()
                    while true do
                        local x = io.read()
                        coroutine.yield(x)
                    end
                end)
            end

            function consumer(prod)
                while true do
                    local status, value = coroutine.resume(prod)
                    if not status then break end
                    print(value)
                end
            end

            local co = coroutine.create(function(a, b)
                print("Started coroutine with", a, b)
                local r = coroutine.yield(a + b)
                print("Resumed with", r)
                return b * r
            end)

            function async_task()
                coroutine.yield("Starting task")
                
                for i = 1, 5 do
                    coroutine.yield("Step " .. i)
                end
                
                return "Task completed"
            end

            local task_co = coroutine.create(async_task)
        """
        ).strip()

        chunks = parser.chunk(content, "coroutines.lua")

        # Should find function declarations
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(function_chunks) >= 4

        function_names = {c.semantic_name for c in function_chunks}
        assert "producer" in function_names
        assert "consumer" in function_names
        assert "async_task" in function_names

    def test_metamethods_and_metatables(self, parser):
        """Test parsing Lua metamethods and metatable patterns."""
        content = dedent(
            """
            Vector = {}
            Vector.__index = Vector

            function Vector:new(x, y)
                return setmetatable({x = x or 0, y = y or 0}, self)
            end

            function Vector:__add(other)
                return Vector:new(self.x + other.x, self.y + other.y)
            end

            function Vector:__sub(other)
                return Vector:new(self.x - other.x, self.y - other.y)
            end

            function Vector:__mul(scalar)
                if type(scalar) == "number" then
                    return Vector:new(self.x * scalar, self.y * scalar)
                end
            end

            function Vector:__tostring()
                return "(" .. self.x .. ", " .. self.y .. ")"
            end

            function Vector:__eq(other)
                return self.x == other.x and self.y == other.y
            end

            function Vector:__len()
                return math.sqrt(self.x^2 + self.y^2)
            end

            local mt = {
                __index = function(t, k)
                    return "Key " .. k .. " not found"
                end,
                
                __call = function(t, ...)
                    return "Called with " .. table.concat({...}, ", ")
                end
            }
        """
        ).strip()

        chunks = parser.chunk(content, "metamethods.lua")

        # Should find methods and functions
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        assert len(method_chunks) >= 7

        # Check metamethod names
        method_names = {c.semantic_name for c in method_chunks}
        assert "Vector:new" in method_names
        assert "Vector:__add" in method_names
        assert "Vector:__sub" in method_names
        assert "Vector:__tostring" in method_names

        # Should also find the metatable
        table_chunks = [
            c for c in chunks if c.semantic_type in ["table", "local_table"]
        ]
        assert len(table_chunks) >= 1

    def test_closure_patterns(self, parser):
        """Test parsing Lua closure patterns."""
        content = dedent(
            """
            function create_counter()
                local count = 0
                return function()
                    count = count + 1
                    return count
                end
            end

            function make_adder(x)
                return function(y)
                    return x + y
                end
            end

            local function factory(prefix)
                return function(suffix)
                    return prefix .. "_" .. suffix
                end
            end

            function timer(callback, delay)
                local start_time = os.time()
                
                return function()
                    if os.time() - start_time >= delay then
                        callback()
                        return true
                    end
                    return false
                end
            end

            -- Higher-order function
            function map(func, list)
                local result = {}
                for i, v in ipairs(list) do
                    result[i] = func(v)
                end
                return result
            end

            local function filter(predicate, list)
                local result = {}
                for _, v in ipairs(list) do
                    if predicate(v) then
                        table.insert(result, v)
                    end
                end
                return result
            end
        """
        ).strip()

        chunks = parser.chunk(content, "closures.lua")

        # Should find function declarations
        function_chunks = [
            c for c in chunks if c.semantic_type in ["function", "local_function"]
        ]
        assert len(function_chunks) >= 6

        function_names = {c.semantic_name for c in function_chunks}
        assert "create_counter" in function_names
        assert "make_adder" in function_names
        assert "factory" in function_names
        assert "timer" in function_names
        assert "map" in function_names
        assert "filter" in function_names

    def test_error_node_handling_basic(self, parser):
        """Test ERROR node handling for basic syntax errors."""
        content = dedent(
            """
            function valid_function()
                print("This is valid")
            end

            function broken_function()
                print("Missing end")
                -- Missing 'end' keyword

            function another_valid()
                return "Still works"
            end

            local broken_table = {
                key1 = "value1"
                key2 = "value2"  -- Missing comma
                key3 = "value3"
            }

            local valid_table = {
                item1 = 1,
                item2 = 2
            }
        """
        ).strip()

        chunks = parser.chunk(content, "broken.lua")

        # Should extract constructs despite syntax errors
        assert len(chunks) >= 3

        # Should find valid constructs
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        table_chunks = [
            c for c in chunks if c.semantic_type in ["table", "local_table"]
        ]

        assert len(function_chunks) >= 2
        assert len(table_chunks) >= 1

        # Check that valid names are found
        all_names = {c.semantic_name for c in chunks if c.semantic_name}
        assert "valid_function" in all_names or "another_valid" in all_names

    def test_error_node_handling_table_errors(self, parser):
        """Test ERROR node handling for table syntax errors."""
        content = dedent(
            """
            local good_table = {
                name = "John",
                age = 30
            }

            local broken_table = {
                name = "Jane"
                age = 25,  -- Missing comma before this line
                city = "NYC"
                -- Missing closing brace

            function still_works()
                return "Function after broken table"
            end

            another_table = {
                valid = true,
                working = "yes"
            }
        """
        ).strip()

        chunks = parser.chunk(content, "table_errors.lua")

        # Should extract constructs despite table syntax errors
        assert len(chunks) >= 2

        # Should find valid constructs
        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        table_chunks = [
            c for c in chunks if c.semantic_type in ["table", "local_table"]
        ]

        assert len(function_chunks) >= 1
        assert len(table_chunks) >= 2

        # Check function is found
        function_names = {c.semantic_name for c in function_chunks}
        assert "still_works" in function_names

    def test_error_node_handling_function_errors(self, parser):
        """Test ERROR node handling for function syntax errors."""
        content = dedent(
            """
            function valid_start()
                print("Valid function")
            end

            function broken_params(a, b, c
                -- Missing closing parenthesis
                return a + b + c

            local function valid_local()
                return "Local function works"
            end

            function incomplete_function()
                local x = 10
                -- Function body is incomplete but has some content

            function recovery_function()
                print("This should be found")
                return true
            end
        """
        ).strip()

        chunks = parser.chunk(content, "function_errors.lua")

        # Should extract functions despite syntax errors
        function_chunks = [
            c for c in chunks if c.semantic_type in ["function", "local_function"]
        ]
        assert len(function_chunks) >= 3

        function_names = {c.semantic_name for c in function_chunks}
        assert "valid_start" in function_names or "recovery_function" in function_names

    def test_malformed_lua_code_handling(self, parser):
        """Test handling of completely malformed Lua code."""
        malformed_content = """
            This is not valid Lua code at all!
            function??? broken syntax everywhere
            local table = { invalid structure %%%
            require incomplete((((
            end end end without matching begins
        """

        # Should not crash and should return minimal chunks
        chunks = parser.chunk(malformed_content, "malformed.lua")

        # Parser should handle gracefully
        assert isinstance(chunks, list)

    def test_chunker_integration(self, chunker):
        """Test integration with SemanticChunker for Lua files."""
        content = dedent(
            """
            local json = require("json")

            local UserManager = {}

            function UserManager:new()
                local obj = {
                    users = {},
                    count = 0
                }
                setmetatable(obj, self)
                self.__index = self
                return obj
            end

            function UserManager:addUser(user)
                table.insert(self.users, user)
                self.count = self.count + 1
            end

            function UserManager:getUser(id)
                for _, user in ipairs(self.users) do
                    if user.id == id then
                        return user
                    end
                end
                return nil
            end

            function UserManager:toJson()
                return json.encode(self.users)
            end

            return UserManager
        """
        ).strip()

        chunks = chunker.chunk_content(content, "user_manager.lua")

        # Should get semantic chunks from Lua parser
        assert len(chunks) >= 5

        # Verify chunks have semantic metadata
        for chunk in chunks:
            assert chunk.get("semantic_chunking") is True
            assert "semantic_type" in chunk
            assert "semantic_name" in chunk
            assert "semantic_path" in chunk

    def test_lua_iterators_and_generators(self, parser):
        """Test parsing Lua iterator and generator patterns."""
        content = dedent(
            """
            function ipairs_clone(t)
                local i = 0
                return function()
                    i = i + 1
                    return i, t[i]
                end
            end

            function pairs_clone(t)
                local key = nil
                return function()
                    key = next(t, key)
                    return key, t[key]
                end
            end

            local function range(n)
                local i = 0
                return function()
                    i = i + 1
                    if i <= n then
                        return i
                    end
                end
            end

            function file_lines(filename)
                local file = io.open(filename, "r")
                if not file then return nil end
                
                return function()
                    local line = file:read("*line")
                    if line == nil then
                        file:close()
                    end
                    return line
                end
            end

            -- Custom iterator with state
            function string_chars(str)
                local index = 0
                local len = #str
                
                return function()
                    index = index + 1
                    if index <= len then
                        return index, str:sub(index, index)
                    end
                end
            end
        """
        ).strip()

        chunks = parser.chunk(content, "iterators.lua")

        # Should find function declarations
        function_chunks = [
            c for c in chunks if c.semantic_type in ["function", "local_function"]
        ]
        assert len(function_chunks) >= 5

        function_names = {c.semantic_name for c in function_chunks}
        assert "ipairs_clone" in function_names
        assert "pairs_clone" in function_names
        assert "range" in function_names
        assert "file_lines" in function_names
        assert "string_chars" in function_names

    def test_regex_fallback_functionality(self, parser):
        """Test regex fallback for Lua when tree-sitter fails."""
        # Test the regex fallback method directly
        error_text = """
            function test_function(param)
                return param * 2
            end
            
            local function local_test()
                print("local")
            end
            
            local table_var = {
                key = "value"
            }
            
            global_table = {
                name = "global"
            }
            
            local my_func = function(x)
                return x + 1
            end
            
            TestClass = {}
            
            function TestClass:method(self)
                return self.value
            end
            
            local json = require("json")
            local utils = require("my.utils")
            
            return TestClass
        """

        constructs = parser._extract_constructs_from_error_text(error_text, 1, [])

        # Should find constructs through regex
        assert len(constructs) >= 7

        # Check that different construct types were found
        construct_types = {c["type"] for c in constructs}
        expected_types = {
            "function",
            "local_function",
            "table",
            "local_table",
            "method",
            "require",
            "module_return",
        }
        assert len(construct_types.intersection(expected_types)) >= 5

    def test_lua_string_and_comments(self, parser):
        """Test parsing Lua with various string types and comments."""
        content = dedent(
            """
            --[[
            Multi-line comment
            describing the module
            ]]

            -- Single line comment
            function string_examples()
                local single_quote = 'Single quote string'
                local double_quote = "Double quote string"
                local multiline = [[
                    This is a
                    multiline string
                ]]
                
                local escaped = "String with \\"quotes\\" and \\n newlines"
                
                return single_quote, double_quote, multiline, escaped
            end

            --[[ Another comment block ]]
            local config = {
                -- Inline comment
                debug = true,
                version = "1.0.0", -- End of line comment
                description = [[
                    Long description that
                    spans multiple lines
                ]]
            }

            function process_strings(str)
                -- Comment inside function
                local result = str:gsub("%s+", "_")
                return result:lower()
            end

            --[[
            TODO: Implement advanced string processing
            FIXME: Handle edge cases
            ]]
            function advanced_processing()
                -- Implementation pending
                return nil
            end
            """
        ).strip()

        chunks = parser.chunk(content, "strings_comments.lua")

        # Should handle strings and comments without issues
        assert len(chunks) >= 3

        function_chunks = [c for c in chunks if c.semantic_type == "function"]
        table_chunks = [
            c for c in chunks if c.semantic_type in ["table", "local_table"]
        ]

        assert len(function_chunks) >= 3
        assert len(table_chunks) >= 1

        # Check function names
        function_names = {c.semantic_name for c in function_chunks}
        assert "string_examples" in function_names
        assert "process_strings" in function_names
        assert "advanced_processing" in function_names

    def test_lua_operator_overloading_patterns(self, parser):
        """Test parsing Lua operator overloading through metamethods."""
        content = dedent(
            """
            Complex = {}
            Complex.__index = Complex

            function Complex.new(real, imag)
                local self = setmetatable({}, Complex)
                self.real = real or 0
                self.imag = imag or 0
                return self
            end

            function Complex:__add(other)
                return Complex.new(
                    self.real + other.real,
                    self.imag + other.imag
                )
            end

            function Complex:__sub(other)
                return Complex.new(
                    self.real - other.real,
                    self.imag - other.imag
                )
            end

            function Complex:__mul(other)
                return Complex.new(
                    self.real * other.real - self.imag * other.imag,
                    self.real * other.imag + self.imag * other.real
                )
            end

            function Complex:__div(other)
                local denom = other.real^2 + other.imag^2
                return Complex.new(
                    (self.real * other.real + self.imag * other.imag) / denom,
                    (self.imag * other.real - self.real * other.imag) / denom
                )
            end

            function Complex:__tostring()
                if self.imag >= 0 then
                    return self.real .. "+" .. self.imag .. "i"
                else
                    return self.real .. self.imag .. "i"
                end
            end

            function Complex:__eq(other)
                return self.real == other.real and self.imag == other.imag
            end
        """
        ).strip()

        chunks = parser.chunk(content, "complex.lua")

        # Should find methods and functions
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        function_chunks = [c for c in chunks if c.semantic_type == "function"]

        assert len(method_chunks) >= 6
        assert len(function_chunks) >= 1

        # Check metamethod names
        method_names = {c.semantic_name for c in method_chunks}
        assert "Complex:__add" in method_names
        assert "Complex:__sub" in method_names
        assert "Complex:__mul" in method_names
        assert "Complex:__tostring" in method_names

        # Check static method
        function_names = {c.semantic_name for c in function_chunks}
        assert "Complex.new" in function_names

    def test_data_preservation_no_loss(self, parser):
        """Test that chunking preserves all content without data loss."""
        content = dedent(
            """
            #!/usr/bin/env lua

            --[[
            Game Engine Module
            Comprehensive example showing various Lua patterns
            ]]

            local json = require("json")
            local socket = require("socket")
            local lfs = require("lfs")

            -- Module definition
            local GameEngine = {
                VERSION = "1.2.0",
                DEBUG = false
            }

            -- Private helper functions
            local function log_message(level, message)
                if GameEngine.DEBUG then
                    print(string.format("[%s] %s: %s", 
                        os.date("%Y-%m-%d %H:%M:%S"), 
                        level, 
                        message))
                end
            end

            local function validate_config(config)
                local required_fields = {"width", "height", "title"}
                for _, field in ipairs(required_fields) do
                    if not config[field] then
                        error("Missing required field: " .. field)
                    end
                end
                return true
            end

            -- Game object class
            local GameObject = {}
            GameObject.__index = GameObject

            function GameObject:new(x, y, sprite)
                local obj = {
                    x = x or 0,
                    y = y or 0,
                    sprite = sprite,
                    velocity = {x = 0, y = 0},
                    active = true,
                    components = {}
                }
                setmetatable(obj, self)
                return obj
            end

            function GameObject:update(dt)
                if not self.active then return end
                
                self.x = self.x + self.velocity.x * dt
                self.y = self.y + self.velocity.y * dt
                
                -- Update all components
                for _, component in pairs(self.components) do
                    if component.update then
                        component:update(dt)
                    end
                end
            end

            function GameObject:render(renderer)
                if self.active and self.sprite then
                    renderer:draw_sprite(self.sprite, self.x, self.y)
                end
            end

            function GameObject:add_component(name, component)
                self.components[name] = component
                component.owner = self
            end

            function GameObject:get_component(name)
                return self.components[name]
            end

            -- Scene management
            GameEngine.scenes = {}
            GameEngine.current_scene = nil

            function GameEngine:create_scene(name)
                local scene = {
                    name = name,
                    objects = {},
                    systems = {},
                    active = false
                }
                
                function scene:add_object(obj)
                    table.insert(self.objects, obj)
                end
                
                function scene:remove_object(obj)
                    for i, existing in ipairs(self.objects) do
                        if existing == obj then
                            table.remove(self.objects, i)
                            break
                        end
                    end
                end
                
                function scene:update(dt)
                    for _, obj in ipairs(self.objects) do
                        obj:update(dt)
                    end
                    
                    for _, system in pairs(self.systems) do
                        system:update(dt, self.objects)
                    end
                end
                
                self.scenes[name] = scene
                return scene
            end

            function GameEngine:switch_scene(name)
                local scene = self.scenes[name]
                if scene then
                    if self.current_scene then
                        self.current_scene.active = false
                    end
                    self.current_scene = scene
                    scene.active = true
                    log_message("INFO", "Switched to scene: " .. name)
                else
                    log_message("ERROR", "Scene not found: " .. name)
                end
            end

            -- Input handling
            GameEngine.input = {
                keys = {},
                mouse = {x = 0, y = 0, buttons = {}}
            }

            function GameEngine.input:is_key_pressed(key)
                return self.keys[key] == "pressed"
            end

            function GameEngine.input:is_key_held(key)
                return self.keys[key] == "held"
            end

            function GameEngine.input:update()
                -- Update key states from pressed to held
                for key, state in pairs(self.keys) do
                    if state == "pressed" then
                        self.keys[key] = "held"
                    end
                end
            end

            -- Configuration and initialization
            local default_config = {
                width = 800,
                height = 600,
                title = "Lua Game Engine",
                fullscreen = false,
                vsync = true
            }

            function GameEngine:init(config)
                config = config or {}
                
                -- Merge with defaults
                for key, value in pairs(default_config) do
                    if config[key] == nil then
                        config[key] = value
                    end
                end
                
                validate_config(config)
                self.config = config
                
                log_message("INFO", "Game engine initialized")
                log_message("INFO", "Config: " .. json.encode(config))
                
                return true
            end

            function GameEngine:run()
                if not self.config then
                    error("Engine not initialized. Call init() first.")
                end
                
                log_message("INFO", "Starting game loop")
                
                local last_time = socket.gettime()
                local running = true
                
                while running do
                    local current_time = socket.gettime()
                    local dt = current_time - last_time
                    last_time = current_time
                    
                    -- Update input
                    self.input:update()
                    
                    -- Update current scene
                    if self.current_scene and self.current_scene.active then
                        self.current_scene:update(dt)
                    end
                    
                    -- Check for exit condition
                    if self.input:is_key_pressed("escape") then
                        running = false
                    end
                    
                    -- Limit frame rate
                    socket.sleep(0.016) -- ~60 FPS
                end
                
                log_message("INFO", "Game loop ended")
            end

            -- Export the module
            return GameEngine
            """
        ).strip()

        chunks = parser.chunk(content, "data_preservation.lua")

        # Verify no data loss by checking that all content is captured
        all_chunk_content = "\n".join(chunk.text for chunk in chunks)

        # Check that essential elements are preserved
        assert 'local json = require("json")' in all_chunk_content
        assert "local GameEngine = {" in all_chunk_content
        assert "local function log_message" in all_chunk_content
        assert "local GameObject = {}" in all_chunk_content
        assert "function GameObject:new" in all_chunk_content
        assert "function GameEngine:create_scene" in all_chunk_content
        assert "function GameEngine:init" in all_chunk_content
        assert "return GameEngine" in all_chunk_content

        # Check that we have reasonable chunk coverage
        assert len(chunks) >= 10  # Should have multiple semantic chunks

        # Verify all chunks have proper metadata
        for chunk in chunks:
            assert chunk.semantic_chunking is True
            assert chunk.semantic_type is not None
            assert chunk.semantic_name is not None
            assert chunk.file_path == "data_preservation.lua"
            assert chunk.line_start > 0
            assert chunk.line_end >= chunk.line_start

    def test_file_extension_detection(self, parser):
        """Test detection of Lua file extensions."""
        simple_content = """
            function hello()
                print("Hello, World!")
            end
        """

        # Test Lua file extension
        chunks = parser.chunk(simple_content, "hello.lua")
        assert len(chunks) >= 1
        assert chunks[0].file_extension == ".lua"

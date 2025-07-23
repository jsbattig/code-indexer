"""
Tests for Ruby semantic parser.
Following TDD approach - writing comprehensive tests to ensure complete coverage
of Ruby language constructs including ERROR node handling.
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestRubySemanticParser:
    """Test Ruby semantic parser using tree-sitter."""

    @pytest.fixture
    def chunker(self):
        """Create a semantic chunker with semantic chunking enabled."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return SemanticChunker(config)

    @pytest.fixture
    def parser(self):
        """Create a Ruby parser directly."""
        from code_indexer.indexing.ruby_parser import RubySemanticParser

        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return RubySemanticParser(config)

    def test_basic_class_declaration(self, parser):
        """Test parsing basic Ruby class definitions."""
        content = dedent(
            """
            class Rectangle
              def initialize(width, height)
                @width = width
                @height = height
              end
              
              def area
                @width * @height
              end
              
              def perimeter
                2 * (@width + @height)
              end
              
              private
              
              def validate_dimensions
                @width > 0 && @height > 0
              end
            end

            class Square < Rectangle
              def initialize(side)
                super(side, side)
              end
              
              def self.create(side)
                new(side)
              end
              
              def to_s
                "Square with side #{@width}"
              end
            end
        """
        ).strip()

        chunks = parser.chunk(content, "shapes.rb")

        # Should find classes and their methods
        assert len(chunks) >= 2

        # Check class chunks
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 2

        class_names = {c.semantic_name for c in class_chunks}
        assert "Rectangle" in class_names
        assert "Square" in class_names

        # Check Rectangle class
        rect_class = next(c for c in class_chunks if c.semantic_name == "Rectangle")
        assert rect_class.semantic_path == "Rectangle"
        assert "class Rectangle" in rect_class.semantic_signature

        # Check Square class with inheritance
        square_class = next(c for c in class_chunks if c.semantic_name == "Square")
        assert "class Square < Rectangle" in square_class.semantic_signature
        if square_class.semantic_context.get("superclass"):
            assert square_class.semantic_context["superclass"] == "Rectangle"

    def test_module_declarations(self, parser):
        """Test parsing Ruby module definitions."""
        content = dedent(
            """
            module Math
              PI = 3.14159
              
              def self.circle_area(radius)
                PI * radius * radius
              end
              
              def self.square_area(side)
                side * side
              end
              
              module Utils
                def self.round_to(number, places)
                  (number * (10 ** places)).round / (10.0 ** places)
                end
              end
            end

            module Comparable
              def between?(min, max)
                self >= min && self <= max
              end
              
              def clamp(min, max)
                return min if self < min
                return max if self > max
                self
              end
            end

            class Number
              include Comparable
              
              def initialize(value)
                @value = value
              end
            end
        """
        ).strip()

        chunks = parser.chunk(content, "modules.rb")

        # Should find modules and classes
        module_chunks = [c for c in chunks if c.semantic_type == "module"]
        assert len(module_chunks) >= 2

        module_names = {c.semantic_name for c in module_chunks}
        assert "Math" in module_names
        assert "Comparable" in module_names

        # Check nested module
        if "Utils" in module_names:
            utils_module = next(c for c in module_chunks if c.semantic_name == "Utils")
            assert "Math::Utils" in utils_module.semantic_path

    def test_method_declarations(self, parser):
        """Test parsing Ruby method definitions."""
        content = dedent(
            """
            class Calculator
              def initialize
                @history = []
              end
              
              def add(a, b)
                result = a + b
                @history << result
                result
              end
              
              def subtract(a, b = 0)
                result = a - b
                @history << result
                result
              end
              
              def multiply(*args)
                result = args.reduce(1, :*)
                @history << result
                result
              end
              
              def divide(a, b, **options)
                raise ArgumentError, "Division by zero" if b == 0
                result = options[:round] ? (a / b).round : a / b
                @history << result
                result
              end
              
              def self.version
                "1.0.0"
              end
              
              private
              
              def clear_history
                @history.clear
              end
              
              protected
              
              def validate_number(n)
                n.is_a?(Numeric)
              end
              
              public
              
              def history
                @history.dup
              end
            end
        """
        ).strip()

        chunks = parser.chunk(content, "calculator.rb")

        # Should find class and methods
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        assert len(method_chunks) >= 6

        method_names = {c.semantic_name for c in method_chunks}
        assert "add" in method_names
        assert "multiply" in method_names
        assert "version" in method_names

        # Check method visibility
        private_methods = [
            c
            for c in method_chunks
            if c.semantic_context.get("visibility") == "private"
        ]
        protected_methods = [
            c
            for c in method_chunks
            if c.semantic_context.get("visibility") == "protected"
        ]

        # Should find methods with different visibility levels
        assert len(private_methods) >= 1 or len(protected_methods) >= 1

        # Check class method
        class_methods = [
            c for c in method_chunks if c.semantic_context.get("is_class_method")
        ]
        assert len(class_methods) >= 1

    def test_block_and_lambda_declarations(self, parser):
        """Test parsing Ruby blocks and lambda expressions."""
        content = dedent(
            """
            class BlockDemo
              def initialize
                @data = []
              end
              
              def process_with_block
                [1, 2, 3, 4, 5].each do |item|
                  puts "Processing: #{item}"
                  @data << item * 2
                end
              end
              
              def filter_data(&block)
                @data.select(&block)
              end
              
              def setup_callbacks
                @on_success = lambda { |result| puts "Success: #{result}" }
                @on_error = -> (error) { puts "Error: #{error}" }
                
                @processor = proc do |data|
                  data.map { |item| item.to_s.upcase }
                end
              end
              
              def apply_transformations
                numbers = (1..10).to_a
                
                # Block with parameters
                squared = numbers.map { |n| n * n }
                
                # Block with index
                indexed = numbers.each_with_index.map do |value, index|
                  "#{index}: #{value}"
                end
                
                # Nested blocks
                grouped = numbers.group_by { |n| n.even? ? :even : :odd }
                                .transform_values { |values| values.sum }
                
                [squared, indexed, grouped]
              end
            end
        """
        ).strip()

        chunks = parser.chunk(content, "blocks.rb")

        # Should find class, methods, and blocks/lambdas
        block_chunks = [c for c in chunks if c.semantic_type == "block"]
        lambda_chunks = [c for c in chunks if c.semantic_type == "lambda"]
        method_chunks = [c for c in chunks if c.semantic_type == "method"]

        assert len(chunks) >= 5

        # Should find some blocks or lambdas
        assert len(block_chunks) >= 1 or len(lambda_chunks) >= 1

        # Check method names
        method_names = {c.semantic_name for c in method_chunks}
        assert (
            "process_with_block" in method_names
            or "apply_transformations" in method_names
        )

    def test_variable_and_constant_declarations(self, parser):
        """Test parsing Ruby variable and constant declarations."""
        content = dedent(
            """
            # Global variables
            $global_counter = 0
            $debug_mode = true

            class Configuration
              # Class variables
              @@instance_count = 0
              @@default_settings = {}
              
              # Constants
              VERSION = "2.1.0"
              MAX_CONNECTIONS = 100
              DEFAULT_TIMEOUT = 30.seconds
              
              def initialize(name)
                # Instance variables
                @name = name
                @settings = {}
                @created_at = Time.now
                
                @@instance_count += 1
                $global_counter += 1
              end
              
              def self.instance_count
                @@instance_count
              end
              
              def update_setting(key, value)
                @settings[key] = value
              end
              
              def get_setting(key)
                @settings[key] || @@default_settings[key]
              end
              
              private
              
              def validate_name
                @name && !@name.empty?
              end
            end

            # Module constants
            module ErrorCodes
              SUCCESS = 0
              NOT_FOUND = 404
              INTERNAL_ERROR = 500
              
              def self.message_for(code)
                case code
                when SUCCESS then "Operation successful"
                when NOT_FOUND then "Resource not found"  
                when INTERNAL_ERROR then "Internal server error"
                else "Unknown error"
                end
              end
            end
        """
        ).strip()

        chunks = parser.chunk(content, "variables.rb")

        # Should find various types of variables and constants
        global_var_chunks = [c for c in chunks if c.semantic_type == "global_variable"]
        class_var_chunks = [c for c in chunks if c.semantic_type == "class_variable"]
        instance_var_chunks = [
            c for c in chunks if c.semantic_type == "instance_variable"
        ]
        constant_chunks = [c for c in chunks if c.semantic_type == "constant"]

        # Should find at least some variables
        total_vars = (
            len(global_var_chunks)
            + len(class_var_chunks)
            + len(instance_var_chunks)
            + len(constant_chunks)
        )
        assert total_vars >= 3

        # Check variable names
        if global_var_chunks:
            global_names = {c.semantic_name for c in global_var_chunks}
            assert "$global_counter" in global_names or "$debug_mode" in global_names

        if constant_chunks:
            constant_names = {c.semantic_name for c in constant_chunks}
            assert "VERSION" in constant_names or "MAX_CONNECTIONS" in constant_names

    def test_mixin_declarations(self, parser):
        """Test parsing Ruby mixin declarations (include, extend, prepend)."""
        content = dedent(
            """
            module Loggable
              def log(message)
                puts "[#{Time.now}] #{message}"
              end
              
              def self.included(base)
                base.extend(ClassMethods)
              end
              
              module ClassMethods
                def logger_name
                  self.name.downcase
                end
              end
            end

            module Comparable
              def between?(min, max)
                self >= min && self <= max
              end
            end

            module Serializable
              def to_hash
                instance_variables.each_with_object({}) do |var, hash|
                  hash[var.to_s.delete("@")] = instance_variable_get(var)
                end
              end
            end

            class User
              include Loggable
              include Comparable
              extend Serializable
              
              def initialize(name, age)
                @name = name
                @age = age
              end
              
              def <=>(other)
                @age <=> other.age
              end
              
              def greet
                log("Hello, I'm #{@name}")
              end
            end

            class AdminUser < User
              prepend Loggable
              
              def greet
                super
                log("I'm an admin user")
              end
            end
        """
        ).strip()

        chunks = parser.chunk(content, "mixins.rb")

        # Should find modules, classes, and mixin declarations
        mixin_chunks = [c for c in chunks if c.semantic_type == "mixin"]
        [c for c in chunks if c.semantic_type == "module"]
        [c for c in chunks if c.semantic_type == "class"]

        assert len(chunks) >= 5

        # Should find mixin usage
        if mixin_chunks:
            mixin_types = {
                c.semantic_context.get("mixin_type")
                for c in mixin_chunks
                if c.semantic_context
            }
            assert "include" in mixin_types or "extend" in mixin_types

    def test_alias_and_metaprogramming(self, parser):
        """Test parsing Ruby alias declarations and metaprogramming constructs."""
        content = dedent(
            """
            class StringProcessor
              def process(text)
                text.strip.upcase
              end
              
              # Alias method
              alias_method :transform, :process
              alias handle process
              
              def self.define_processor(name, &block)
                define_method(name, &block)
              end
              
              def self.create_accessor(name)
                attr_accessor name
                alias_method "get_#{name}", name
                alias_method "set_#{name}", "#{name}="
              end
              
              # Metaprogramming examples
              %w[upcase downcase capitalize].each do |method_name|
                define_method("#{method_name}_text") do |text|
                  text.send(method_name)
                end
              end
              
              private
              
              def method_missing(method_name, *args, &block)
                if method_name.to_s.start_with?('process_')
                  suffix = method_name.to_s.sub('process_', '')
                  process(args.first).send(suffix)
                else
                  super
                end
              end
              
              def respond_to_missing?(method_name, include_private = false)
                method_name.to_s.start_with?('process_') || super
              end
            end

            module DynamicMethods
              def self.included(base)
                base.class_eval do
                  define_method :dynamic_method do
                    "This was defined dynamically"
                  end
                end
              end
            end

            class Example
              include DynamicMethods
              
              def self.method_added(method_name)
                puts "Method #{method_name} was added to #{self}"
              end
            end
        """
        ).strip()

        chunks = parser.chunk(content, "metaprogramming.rb")

        # Should find classes, methods, and alias declarations
        alias_chunks = [c for c in chunks if c.semantic_type == "alias"]
        [c for c in chunks if c.semantic_type == "class"]
        [c for c in chunks if c.semantic_type == "method"]

        assert len(chunks) >= 4

        # Should find alias declarations
        if alias_chunks:
            alias_names = {c.semantic_name for c in alias_chunks}
            # Alias names might be prefixed
            found_aliases = [
                name for name in alias_names if "transform" in name or "handle" in name
            ]
            assert len(found_aliases) >= 1

    def test_error_node_handling_basic(self, parser):
        """Test ERROR node handling for basic syntax errors."""
        content = dedent(
            """
            class ValidClass
              def valid_method
                puts "This is valid"
              end
            end

            class BrokenClass
              def broken_method
                puts "Missing end"
              # Missing 'end' for method
              
              def another_method
                puts "This should still be found"
              end
            end # This might be missing too

            module ValidModule
              def module_method
                "Valid module method"
              end
            end
        """
        ).strip()

        chunks = parser.chunk(content, "broken.rb")

        # Should extract constructs despite syntax errors
        assert len(chunks) >= 2

        # Should find valid constructs
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        module_chunks = [c for c in chunks if c.semantic_type == "module"]
        method_chunks = [c for c in chunks if c.semantic_type == "method"]

        valid_chunks = class_chunks + module_chunks + method_chunks
        assert len(valid_chunks) >= 2

        # Check that some valid names are found
        all_names = {c.semantic_name for c in chunks if c.semantic_name}
        assert "ValidClass" in all_names or "ValidModule" in all_names

    def test_error_node_handling_block_errors(self, parser):
        """Test ERROR node handling for block syntax errors."""
        content = dedent(
            """
            class BlockErrors
              def valid_method
                [1, 2, 3].each do |item|
                  puts item
                end
              end
              
              def broken_block_method
                [1, 2, 3].each do |item
                  puts item
                # Missing 'end' for block
              
              def another_valid_method
                puts "Another valid method"
              end
              
              def with_proc
                my_proc = proc { |x| x * 2 }
                my_proc.call(5)
              end
            end
        """
        ).strip()

        chunks = parser.chunk(content, "block_errors.rb")

        # Should extract methods despite block syntax errors
        assert len(chunks) >= 2

        # Should find valid methods
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        assert len(method_chunks) >= 2

        method_names = {c.semantic_name for c in method_chunks}
        assert "valid_method" in method_names or "another_valid_method" in method_names

    def test_error_node_handling_class_errors(self, parser):
        """Test ERROR node handling for class definition errors."""
        content = dedent(
            """
            class ValidParent
              def parent_method
                "From parent"
              end
            end

            class BrokenChild < ValidParent
              def initialize(name
                # Missing closing parenthesis and method body
              
              def valid_child_method
                "From child"
              end
            # Missing end for class

            module RecoveryModule
              def recovery_method
                "Recovery successful"
              end
            end
        """
        ).strip()

        chunks = parser.chunk(content, "class_errors.rb")

        # Should extract constructs despite class definition errors
        assert len(chunks) >= 2

        # Should find valid constructs
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        module_chunks = [c for c in chunks if c.semantic_type == "module"]

        valid_chunks = class_chunks + module_chunks
        assert len(valid_chunks) >= 1

        # Check that valid names are found
        all_names = {c.semantic_name for c in valid_chunks}
        assert "ValidParent" in all_names or "RecoveryModule" in all_names

    def test_malformed_ruby_code_handling(self, parser):
        """Test handling of completely malformed Ruby code."""
        malformed_content = """
            This is not valid Ruby code!
            class??? broken {{{
            def incomplete(((
            module:::: wrong
            @@@invalid_instance_var
        """

        # Should not crash and should return minimal chunks
        chunks = parser.chunk(malformed_content, "malformed.rb")

        # Parser should handle gracefully
        assert isinstance(chunks, list)

    def test_chunker_integration(self, chunker):
        """Test integration with SemanticChunker for Ruby files."""
        content = dedent(
            """
            require 'json'

            module DataProcessor
              class JsonParser
                def initialize(data)
                  @data = data
                end
                
                def parse
                  JSON.parse(@data)
                rescue JSON::ParserError => e
                  puts "Error parsing JSON: #{e.message}"
                  {}
                end
                
                def self.parse_file(filename)
                  content = File.read(filename)
                  new(content).parse
                end
              end
            end

            # Usage
            parser = DataProcessor::JsonParser.new('{"key": "value"}')
            result = parser.parse
            puts result.inspect
        """
        ).strip()

        chunks = chunker.chunk_content(content, "json_parser.rb")

        # Should get semantic chunks from Ruby parser
        assert len(chunks) >= 3

        # Verify chunks have semantic metadata
        for chunk in chunks:
            assert chunk.get("semantic_chunking") is True
            assert "semantic_type" in chunk
            assert "semantic_name" in chunk
            assert "semantic_path" in chunk

    def test_require_and_load_statements(self, parser):
        """Test parsing Ruby require and load statements."""
        content = dedent(
            """
            require 'json'
            require 'net/http'
            require_relative 'helper'
            require_relative '../config/database'

            load 'tasks/migrate.rb'
            load File.join(File.dirname(__FILE__), 'utils.rb')

            class ApiClient
              def initialize
                @http = Net::HTTP.new('api.example.com', 443)
                @http.use_ssl = true
              end
              
              def fetch_data
                response = @http.get('/data')
                JSON.parse(response.body)
              end
            end

            # Conditional require
            begin
              require 'optional_gem'
            rescue LoadError
              puts "Optional gem not available"
            end
        """
        ).strip()

        chunks = parser.chunk(content, "api_client.rb")

        # Should find require statements and class
        require_chunks = [c for c in chunks if c.semantic_type == "require"]
        class_chunks = [c for c in chunks if c.semantic_type == "class"]

        assert len(chunks) >= 2

        # Should find at least some require statements
        if require_chunks:
            require_names = {c.semantic_name for c in require_chunks}
            assert "json" in require_names or "net/http" in require_names

        # Should find the class
        assert len(class_chunks) >= 1
        class_names = {c.semantic_name for c in class_chunks}
        assert "ApiClient" in class_names

    def test_regex_fallback_functionality(self, parser):
        """Test regex fallback for Ruby when tree-sitter fails."""
        # Test the regex fallback method directly
        error_text = """
            class TestClass
              def instance_method
                @instance_var = "test"
              end
              
              def self.class_method
                @@class_var = "test"
              end
            end
            
            module TestModule
              def module_method
                puts "test"
              end
            end
            
            CONSTANT = "test_constant"
            
            require 'test_gem'
            include TestModule
            extend AnotherModule
        """

        constructs = parser._extract_constructs_from_error_text(error_text, 1, [])

        # Should find constructs through regex
        assert len(constructs) >= 4

        # Check that different construct types were found
        construct_types = {c["type"] for c in constructs}
        expected_types = {
            "class",
            "module",
            "method",
            "singleton_method",
            "constant",
            "require",
            "include",
        }
        assert len(construct_types.intersection(expected_types)) >= 3

    def test_special_method_names(self, parser):
        """Test parsing Ruby special method names (operators, predicates, etc.)."""
        content = dedent(
            """
            class SpecialMethods
              def initialize(value)
                @value = value
              end
              
              # Predicate methods
              def empty?
                @value.nil? || (@value.respond_to?(:empty?) && @value.empty?)
              end
              
              def valid?
                !empty? && @value.is_a?(String)
              end
              
              # Destructive methods
              def upcase!
                @value = @value.upcase if @value.is_a?(String)
                self
              end
              
              def reverse!
                @value = @value.reverse if @value.respond_to?(:reverse)
                self
              end
              
              # Operator methods
              def +(other)
                self.class.new(@value + other.value)
              end
              
              def ==(other)
                other.is_a?(self.class) && @value == other.value
              end
              
              def [](index)
                @value[index] if @value.respond_to?(:[])
              end
              
              def []=(index, value)
                @value[index] = value if @value.respond_to?(:[]=)
              end
              
              # Access to value
              attr_reader :value
              
              # Method with special characters in different positions
              def method_with_underscore
                "underscore method"
              end
              
              protected
              
              def protected_method?
                true
              end
              
              private
              
              def private_method!
                "private destructive method"
              end
            end
        """
        ).strip()

        chunks = parser.chunk(content, "special_methods.rb")

        # Should find class and various methods
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        assert len(method_chunks) >= 8

        method_names = {c.semantic_name for c in method_chunks}

        # Check for predicate methods
        predicate_methods = [name for name in method_names if name.endswith("?")]
        assert len(predicate_methods) >= 2

        # Check for destructive methods
        destructive_methods = [name for name in method_names if name.endswith("!")]
        assert len(destructive_methods) >= 2

        # Check method features
        predicate_features = [
            c
            for c in method_chunks
            if "predicate_method" in c.semantic_language_features
        ]
        destructive_features = [
            c
            for c in method_chunks
            if "mutating_method" in c.semantic_language_features
        ]

        assert len(predicate_features) >= 1 or len(destructive_features) >= 1

    def test_nested_structures(self, parser):
        """Test parsing nested Ruby structures (classes within modules, etc.)."""
        content = dedent(
            """
            module Namespace
              VERSION = "1.0.0"
              
              class OuterClass
                def initialize
                  @data = []
                end
                
                class InnerClass
                  def initialize(parent)
                    @parent = parent
                  end
                  
                  def access_parent
                    @parent.instance_variable_get(:@data)
                  end
                  
                  class DeeplyNested
                    def deep_method
                      "Very deep"
                    end
                  end
                end
                
                def create_inner
                  InnerClass.new(self)
                end
                
                module NestedModule
                  def nested_module_method
                    "From nested module"
                  end
                  
                  class ModuleClass
                    def module_class_method
                      "From module class"
                    end
                  end
                end
                
                include NestedModule
              end
              
              def self.info
                "Namespace version #{VERSION}"
              end
            end

            # Access nested classes
            outer = Namespace::OuterClass.new
            inner = outer.create_inner
            deep = Namespace::OuterClass::InnerClass::DeeplyNested.new
        """
        ).strip()

        chunks = parser.chunk(content, "nested.rb")

        # Should find nested structures
        [c for c in chunks if c.semantic_type == "module"]
        class_chunks = [c for c in chunks if c.semantic_type == "class"]

        assert len(chunks) >= 5

        # Check nested paths
        nested_classes = [c for c in class_chunks if "::" in c.semantic_path]
        assert len(nested_classes) >= 1

        # Check class names
        class_names = {c.semantic_name for c in class_chunks}
        assert "OuterClass" in class_names
        assert "InnerClass" in class_names or "DeeplyNested" in class_names

    def test_data_preservation_no_loss(self, parser):
        """Test that chunking preserves all content without data loss."""
        content = dedent(
            """
            #!/usr/bin/env ruby

            require 'json'
            require 'net/http'
            require_relative 'config/database'

            # Global configuration
            $debug_mode = ENV['DEBUG'] == 'true'

            module WebService
              VERSION = '2.1.0'
              BASE_URL = 'https://api.example.com'
              
              class ApiError < StandardError
                attr_reader :code, :message
                
                def initialize(code, message)
                  @code = code
                  @message = message
                  super("API Error #{code}: #{message}")
                end
              end

              class Client
                include Enumerable
                
                @@instances = []
                
                def initialize(api_key, timeout: 30)
                  @api_key = api_key
                  @timeout = timeout
                  @cache = {}
                  @@instances << self
                end
                
                def get(endpoint, params = {})
                  url = build_url(endpoint, params)
                  response = perform_request(:get, url)
                  
                  case response.code.to_i
                  when 200
                    JSON.parse(response.body)
                  when 404
                    raise ApiError.new(404, "Not found")
                  when 500
                    raise ApiError.new(500, "Server error")
                  else
                    raise ApiError.new(response.code.to_i, "Unexpected error")
                  end
                rescue JSON::ParserError => e
                  $stderr.puts "JSON parse error: #{e.message}" if $debug_mode
                  {}
                end
                
                def post(endpoint, data = {})
                  url = build_url(endpoint)
                  response = perform_request(:post, url, data.to_json)
                  handle_response(response)
                end
                
                def each(&block)
                  return enum_for(:each) unless block_given?
                  @cache.each(&block)
                end
                
                def self.total_instances
                  @@instances.count
                end
                
                def self.cleanup_instances
                  @@instances.clear
                end
                
                private
                
                def build_url(endpoint, params = {})
                  uri = URI.join(BASE_URL, endpoint)
                  uri.query = URI.encode_www_form(params) unless params.empty?
                  uri.to_s
                end
                
                def perform_request(method, url, body = nil)
                  uri = URI(url)
                  http = Net::HTTP.new(uri.host, uri.port)
                  http.use_ssl = uri.scheme == 'https'
                  http.read_timeout = @timeout
                  
                  request = case method
                           when :get
                             Net::HTTP::Get.new(uri)
                           when :post
                             req = Net::HTTP::Post.new(uri)
                             req.body = body if body
                             req['Content-Type'] = 'application/json'
                             req
                           end
                  
                  request['Authorization'] = "Bearer #{@api_key}"
                  request['User-Agent'] = "WebService/#{VERSION}"
                  
                  http.request(request)
                end
                
                def handle_response(response)
                  JSON.parse(response.body)
                rescue => e
                  puts "Error handling response: #{e.message}"
                  nil
                end
                
                protected
                
                def cache_key(endpoint, params)
                  "#{endpoint}:#{params.hash}"
                end
              end
            end

            # Usage example
            client = WebService::Client.new('your-api-key', timeout: 60)
            data = client.get('/users', { page: 1, limit: 10 })
            puts "Retrieved #{data.size} users"
        """
        ).strip()

        chunks = parser.chunk(content, "data_preservation.rb")

        # Verify no data loss by checking that all content is captured
        all_chunk_content = "\n".join(chunk.text for chunk in chunks)

        # Check that essential elements are preserved
        assert "require 'json'" in all_chunk_content
        assert "module WebService" in all_chunk_content
        assert "class ApiError" in all_chunk_content
        assert "class Client" in all_chunk_content
        assert "def get(endpoint" in all_chunk_content
        assert "def post(endpoint" in all_chunk_content
        assert "private" in all_chunk_content

        # Check that we have reasonable chunk coverage
        assert len(chunks) >= 5  # Should have multiple semantic chunks

        # Verify all chunks have proper metadata
        for chunk in chunks:
            assert chunk.semantic_chunking is True
            assert chunk.semantic_type is not None
            assert chunk.semantic_name is not None
            assert chunk.file_path == "data_preservation.rb"
            assert chunk.line_start > 0
            assert chunk.line_end >= chunk.line_start

    def test_file_extension_detection(self, parser):
        """Test detection of different Ruby file extensions."""
        simple_content = """
            class Test
              def method
                "test"
              end
            end
        """

        # Test various Ruby file extensions
        extensions = [".rb", ".rake", ".gemspec"]

        for ext in extensions:
            chunks = parser.chunk(simple_content, f"test{ext}")
            assert len(chunks) >= 1
            assert chunks[0].file_extension == ext

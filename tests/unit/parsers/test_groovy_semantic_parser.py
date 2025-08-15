"""
Tests for Groovy semantic parser using tree-sitter.
Following TDD approach - writing comprehensive tests first.

Tests cover Groovy language constructs:
- Classes/Interfaces/Enums/Traits
- Methods/Functions/Closures
- Properties/Fields
- Annotations
- DSL patterns/Builders
- Gradle build scripts
- Script mode vs class mode
- ERROR node handling
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestGroovySemanticParser:
    """Test Groovy semantic parser using tree-sitter."""

    @pytest.fixture
    def chunker(self):
        """Create a semantic chunker with semantic chunking enabled."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return SemanticChunker(config)

    @pytest.fixture
    def parser(self):
        """Create a Groovy parser directly."""
        from code_indexer.indexing.groovy_parser import GroovySemanticParser

        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return GroovySemanticParser(config)

    def test_basic_class_chunking(self, parser):
        """Test parsing basic Groovy class definitions."""
        content = dedent(
            """
            package com.example

            class Calculator {
                private int value = 0
                
                def add(a, b) {
                    return a + b
                }
                
                public int getValue() {
                    return value
                }
                
                void setValue(int newValue) {
                    this.value = newValue
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "Calculator.groovy")

        # Should find: package, class, field, multiple methods
        assert len(chunks) >= 4

        # Check class chunk
        class_chunk = next((c for c in chunks if c.semantic_type == "class"), None)
        assert class_chunk is not None
        assert class_chunk.semantic_name == "Calculator"
        assert class_chunk.semantic_path == "com.example.Calculator"

        # Check methods
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        assert len(method_chunks) >= 3

        method_names = {c.semantic_name for c in method_chunks}
        assert "add" in method_names
        assert "getValue" in method_names
        assert "setValue" in method_names

        # Check method signatures
        add_method = next((c for c in method_chunks if c.semantic_name == "add"), None)
        assert add_method is not None
        assert add_method.semantic_parent == "Calculator"
        assert add_method.semantic_path == "com.example.Calculator.add"

    def test_closures_and_lambda_expressions(self, parser):
        """Test parsing Groovy closures and lambda expressions."""
        content = dedent(
            """
            class ClosureDemo {
                // Simple closure
                def multiply = { x, y ->
                    x * y
                }
                
                // Closure with explicit types
                Closure<Integer> square = { Integer n ->
                    n * n
                }
                
                // Method using closure parameter
                def processNumbers(List<Integer> numbers, Closure processor) {
                    return numbers.collect(processor)
                }
                
                // Closure passed as method argument
                def calculate() {
                    def numbers = [1, 2, 3, 4, 5]
                    return processNumbers(numbers) { it * 2 }
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "ClosureDemo.groovy")

        # Should find: class, closures, methods
        assert len(chunks) >= 5

        # Check closure chunks
        closure_chunks = [c for c in chunks if c.semantic_type == "closure"]
        assert len(closure_chunks) >= 2

        closure_names = {c.semantic_name for c in closure_chunks}
        assert "multiply" in closure_names
        assert "square" in closure_names

        # Check closure properties
        multiply_closure = next(
            (c for c in closure_chunks if c.semantic_name == "multiply"), None
        )
        assert multiply_closure is not None
        assert multiply_closure.semantic_parent == "ClosureDemo"
        assert "closure_declaration" in multiply_closure.semantic_language_features

    def test_groovy_properties_and_fields(self, parser):
        """Test parsing Groovy properties and field declarations."""
        content = dedent(
            """
            class PropertyDemo {
                // Groovy properties (automatic getter/setter)
                String name
                int age
                
                // Explicit fields
                private String internalId
                protected boolean initialized = false
                
                // Properties with custom getter/setter
                private String _email
                
                String getEmail() {
                    return _email?.toLowerCase()
                }
                
                void setEmail(String email) {
                    this._email = email?.trim()
                }
                
                // Static properties
                static final String DEFAULT_NAME = "Unknown"
                static int instanceCount = 0
            }
        """
        ).strip()

        chunks = parser.chunk(content, "PropertyDemo.groovy")

        # Should find: class, properties/fields, getter/setter methods
        assert len(chunks) >= 7

        # Check property chunks
        property_chunks = [
            c for c in chunks if c.semantic_type in ["property", "field"]
        ]
        assert len(property_chunks) >= 5

        property_names = {c.semantic_name for c in property_chunks}
        expected_names = {
            "name",
            "age",
            "internalId",
            "initialized",
            "_email",
            "DEFAULT_NAME",
            "instanceCount",
        }
        assert len(property_names.intersection(expected_names)) >= 4

        # Check static property
        static_chunks = [
            c for c in property_chunks if "static" in c.semantic_language_features
        ]
        assert len(static_chunks) >= 1

    def test_interfaces_and_traits(self, parser):
        """Test parsing Groovy interfaces and traits."""
        content = dedent(
            """
            interface Calculable {
                def add(a, b)
                def subtract(a, b)
            }
            
            trait Loggable {
                void log(String message) {
                    println "[LOG] ${message}"
                }
                
                abstract String getLoggerName()
            }
            
            class Calculator implements Calculable, Loggable {
                @Override
                def add(a, b) {
                    log("Adding ${a} + ${b}")
                    return a + b
                }
                
                @Override
                def subtract(a, b) {
                    log("Subtracting ${a} - ${b}")
                    return a - b
                }
                
                @Override
                String getLoggerName() {
                    return "Calculator"
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "Calculator.groovy")

        # Should find: interface, trait, class, multiple methods
        assert len(chunks) >= 7

        # Check interface
        interface_chunk = next(
            (c for c in chunks if c.semantic_type == "interface"), None
        )
        assert interface_chunk is not None
        assert interface_chunk.semantic_name == "Calculable"

        # Check trait
        trait_chunk = next((c for c in chunks if c.semantic_type == "trait"), None)
        assert trait_chunk is not None
        assert trait_chunk.semantic_name == "Loggable"

        # Check implementation class
        class_chunk = next((c for c in chunks if c.semantic_type == "class"), None)
        assert class_chunk is not None
        assert class_chunk.semantic_name == "Calculator"
        assert "implements" in str(class_chunk.semantic_context)

    def test_annotations_and_metadata(self, parser):
        """Test parsing Groovy annotations and metadata."""
        content = dedent(
            """
            @Singleton
            @CompileStatic
            class ConfigManager {
                
                @Value('${app.name}')
                private String appName
                
                @Autowired
                private DatabaseService dbService
                
                @PostConstruct
                void initialize() {
                    println "ConfigManager initialized"
                }
                
                @PreDestroy
                void cleanup() {
                    println "ConfigManager cleanup"
                }
                
                @Cacheable("config")
                String getConfiguration(String key) {
                    return dbService.getConfig(key)
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "ConfigManager.groovy")

        # Should find: class, fields, methods, all with annotations
        assert len(chunks) >= 5

        # Check annotated class
        class_chunk = next((c for c in chunks if c.semantic_type == "class"), None)
        assert class_chunk is not None
        assert class_chunk.semantic_name == "ConfigManager"
        annotated_features = class_chunk.semantic_language_features
        assert "annotated" in annotated_features or any(
            "annotation" in str(f) for f in annotated_features
        )

        # Check annotated methods
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        annotated_methods = [
            c
            for c in method_chunks
            if "annotated" in c.semantic_language_features
            or any("annotation" in str(f) for f in c.semantic_language_features)
        ]
        assert len(annotated_methods) >= 2

    def test_groovy_script_mode(self, parser):
        """Test parsing Groovy scripts (no explicit class)."""
        content = dedent(
            """
            #!/usr/bin/env groovy
            
            // Script-level variables
            def name = "Groovy Script"
            int version = 1
            
            // Script-level functions
            def sayHello(String target = "World") {
                println "Hello, ${target}!"
            }
            
            def calculateFactorial(int n) {
                if (n <= 1) return 1
                return n * calculateFactorial(n - 1)
            }
            
            // Script execution
            sayHello()
            sayHello("Groovy")
            println "Factorial of 5: ${calculateFactorial(5)}"
        """
        ).strip()

        chunks = parser.chunk(content, "hello.groovy")

        # Should find: script variables, functions
        assert len(chunks) >= 3

        # Check script-level functions
        function_chunks = [
            c for c in chunks if c.semantic_type in ["function", "method"]
        ]
        assert len(function_chunks) >= 2

        function_names = {c.semantic_name for c in function_chunks}
        assert "sayHello" in function_names
        assert "calculateFactorial" in function_names

        # Check function scope (should be script-level, not class-level)
        say_hello = next(
            (c for c in function_chunks if c.semantic_name == "sayHello"), None
        )
        assert say_hello is not None
        assert say_hello.semantic_scope == "script" or say_hello.semantic_parent is None

    def test_gradle_build_script(self, parser):
        """Test parsing Gradle build scripts (Groovy DSL)."""
        content = dedent(
            """
            plugins {
                id 'java'
                id 'org.springframework.boot' version '2.7.0'
            }
            
            group = 'com.example'
            version = '1.0.0'
            sourceCompatibility = '11'
            
            repositories {
                mavenCentral()
                maven {
                    url 'https://repo.spring.io/milestone'
                }
            }
            
            dependencies {
                implementation 'org.springframework.boot:spring-boot-starter-web'
                testImplementation 'org.springframework.boot:spring-boot-starter-test'
            }
            
            tasks.named('test') {
                useJUnitPlatform()
            }
            
            task customTask(type: Copy) {
                from 'src/main/resources'
                into 'build/custom'
            }
        """
        ).strip()

        chunks = parser.chunk(content, "build.gradle")

        # Should find: configuration blocks, tasks, properties
        assert len(chunks) >= 3

        # Check for DSL blocks and configurations
        chunk_names = {c.semantic_name for c in chunks if c.semantic_name}
        # DSL parsing might identify these as methods or blocks
        expected_elements = {"plugins", "repositories", "dependencies", "customTask"}
        found_elements = chunk_names.intersection(expected_elements)
        assert len(found_elements) >= 1

    def test_nested_classes_and_inner_classes(self, parser):
        """Test parsing nested and inner classes."""
        content = dedent(
            """
            class OuterClass {
                private String outerField = "outer"
                
                class InnerClass {
                    def accessOuter() {
                        return outerField  // Access to outer class
                    }
                }
                
                static class StaticNestedClass {
                    static def staticMethod() {
                        return "from static nested"
                    }
                }
                
                def createAnonymousClass() {
                    return new Runnable() {
                        @Override
                        void run() {
                            println "Anonymous class execution"
                        }
                    }
                }
                
                // Local class in method
                def createLocalClass() {
                    class LocalClass {
                        def localMethod() {
                            return "local"
                        }
                    }
                    return new LocalClass()
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "OuterClass.groovy")

        # Should find: outer class, inner classes, methods
        assert len(chunks) >= 5

        # Check outer class
        outer_class = next((c for c in chunks if c.semantic_name == "OuterClass"), None)
        assert outer_class is not None
        assert outer_class.semantic_type == "class"

        # Check nested classes
        nested_classes = [
            c
            for c in chunks
            if c.semantic_type == "class" and c.semantic_parent == "OuterClass"
        ]
        assert len(nested_classes) >= 1

        nested_names = {c.semantic_name for c in nested_classes}
        assert "InnerClass" in nested_names or "StaticNestedClass" in nested_names

    def test_error_node_handling_basic(self, parser):
        """Test ERROR node handling for basic syntax errors."""
        content = dedent(
            """
            class BrokenClass {
                def validMethod() {
                    return "works"
                }
                
                def brokenMethod() {
                    return "missing brace"
                // Missing closing brace
                
                def anotherMethod() {
                    return "after error"
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "BrokenClass.groovy")

        # Should extract methods despite syntax error
        assert len(chunks) >= 2

        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        method_names = {c.semantic_name for c in method_chunks}

        # Should find at least some methods
        assert len(method_names) >= 2
        assert "validMethod" in method_names or "anotherMethod" in method_names

    def test_error_node_handling_malformed_closure(self, parser):
        """Test ERROR node handling for malformed closures."""
        content = dedent(
            """
            class ClosureErrors {
                def validClosure = { x ->
                    x * 2
                }
                
                def brokenClosure = { x, y ->
                    x + y
                // Missing closing brace
                
                def anotherMethod() {
                    return "method after error"
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "ClosureErrors.groovy")

        # Should handle broken closure gracefully
        assert len(chunks) >= 2

        # Should find class and at least some constructs
        class_chunk = next((c for c in chunks if c.semantic_type == "class"), None)
        assert class_chunk is not None

    def test_error_node_handling_incomplete_annotation(self, parser):
        """Test ERROR node handling for incomplete annotations."""
        content = dedent(
            """
            @Service
            class ValidService {
                def process() {
                    return "valid"
                }
            }
            
            @Component(value=
            // Incomplete annotation
            class BrokenService {
                def process() {
                    return "broken annotation"
                }
            }
            
            class AnotherService {
                def process() {
                    return "after error"
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "Services.groovy")

        # Should extract classes despite annotation error
        assert len(chunks) >= 2

        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        class_names = {c.semantic_name for c in class_chunks}

        # Should find at least some classes
        assert len(class_names) >= 2
        assert "ValidService" in class_names or "AnotherService" in class_names

    def test_error_node_extraction_metadata(self, parser):
        """Test that ERROR node extractions have proper metadata."""
        content = dedent(
            """
            def brokenFunction() {
                println "Missing closing brace"
                // Missing }
            
            def validFunction() {
                println "This works"
            }
        """
        ).strip()

        chunks = parser.chunk(content, "broken.groovy")

        # Look for chunks with error extraction metadata
        error_chunks = [
            c
            for c in chunks
            if c.semantic_context and c.semantic_context.get("extracted_from_error")
        ]

        # Should have proper metadata for error extractions
        if error_chunks:
            error_chunk = error_chunks[0]
            assert error_chunk.semantic_type in ["function", "method", "closure"]
            assert error_chunk.semantic_name is not None
            assert len(error_chunk.text) > 0
            assert error_chunk.line_start > 0
            assert error_chunk.line_end >= error_chunk.line_start

    def test_malformed_groovy_code_handling(self, parser):
        """Test handling of completely malformed Groovy code."""
        malformed_content = """
            This is not valid Groovy code at all!
            {{{ broken syntax everywhere %%%
            def??? maybe(((
            class///// 
            closure -> -> ->
        """

        # Should not crash and should return empty or minimal chunks
        chunks = parser.chunk(malformed_content, "malformed.groovy")

        # Parser should handle gracefully
        assert isinstance(chunks, list)
        # Fallback may return empty list for completely invalid code, which is acceptable

    def test_file_extension_detection(self, parser):
        """Test detection of different Groovy file extensions."""
        simple_content = """
            class Test {
                def method() {
                    return "test"
                }
            }
        """

        # Test various Groovy file extensions
        extensions = [".groovy", ".gradle", ".gvy", ".gy"]

        for ext in extensions:
            chunks = parser.chunk(simple_content, f"test{ext}")
            assert len(chunks) >= 1
            assert chunks[0].file_extension == ext

    def test_chunker_integration(self, chunker):
        """Test integration with SemanticChunker for Groovy files."""
        content = dedent(
            """
            package com.example
            
            class Integration {
                def doSomething() {
                    return "integration test"
                }
                
                def closure = { x ->
                    x.toString()
                }
            }
        """
        ).strip()

        chunks = chunker.chunk_content(content, "integration.groovy")

        # Should get semantic chunks from Groovy parser
        assert len(chunks) >= 2

        # Verify chunks have semantic metadata
        for chunk in chunks:
            assert chunk.get("semantic_chunking") is True
            assert "semantic_type" in chunk
            assert "semantic_name" in chunk
            assert "semantic_path" in chunk

    def test_groovy_builder_pattern(self, parser):
        """Test parsing Groovy builder patterns and DSLs."""
        content = dedent(
            """
            class XmlBuilder {
                def createXml() {
                    def writer = new StringWriter()
                    def xml = new groovy.xml.MarkupBuilder(writer)
                    
                    xml.html {
                        head {
                            title("Test Page")
                        }
                        body {
                            h1("Welcome")
                            p("This is a test")
                            div(class: "content") {
                                span("Nested content")
                            }
                        }
                    }
                    
                    return writer.toString()
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "XmlBuilder.groovy")

        # Should find class and method
        assert len(chunks) >= 2

        class_chunk = next((c for c in chunks if c.semantic_type == "class"), None)
        assert class_chunk is not None
        assert class_chunk.semantic_name == "XmlBuilder"

        method_chunk = next((c for c in chunks if c.semantic_type == "method"), None)
        assert method_chunk is not None
        assert method_chunk.semantic_name == "createXml"

    def test_groovy_dynamic_methods(self, parser):
        """Test parsing Groovy dynamic method features."""
        content = dedent(
            """
            class DynamicDemo {
                def methodMissing(String name, args) {
                    return "Called missing method: ${name} with args: ${args}"
                }
                
                def propertyMissing(String name) {
                    return "Missing property: ${name}"
                }
                
                def invokeMethod(String name, args) {
                    return "Invoke method: ${name}"
                }
                
                static def staticMethod() {
                    return "static"
                }
                
                @Override
                String toString() {
                    return "DynamicDemo instance"
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "DynamicDemo.groovy")

        # Should find class and multiple methods
        assert len(chunks) >= 4

        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        method_names = {c.semantic_name for c in method_chunks}

        expected_methods = {
            "methodMissing",
            "propertyMissing",
            "invokeMethod",
            "staticMethod",
            "toString",
        }
        found_methods = method_names.intersection(expected_methods)
        assert len(found_methods) >= 3

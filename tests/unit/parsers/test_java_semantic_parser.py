"""
Tests for Java semantic parser.
Following TDD approach - writing tests first.
"""

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestJavaSemanticParser:
    """Test the Java semantic parser."""

    def setup_method(self):
        """Set up test configuration."""
        self.config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )

    def test_java_class_chunking(self):
        """Test parsing Java classes."""
        from code_indexer.indexing.java_parser import JavaSemanticParser

        parser = JavaSemanticParser(self.config)
        content = """
public class Calculator {
    private int value;
    
    public Calculator(int initialValue) {
        this.value = initialValue;
    }
    
    public int add(int number) {
        return this.value + number;
    }
    
    public static int multiply(int a, int b) {
        return a * b;
    }
}
"""

        chunks = parser.chunk(content, "Calculator.java")

        assert len(chunks) == 4  # class + constructor + 2 methods

        # Check class chunk
        class_chunk = chunks[0]
        assert class_chunk.semantic_type == "class"
        assert class_chunk.semantic_name == "Calculator"
        assert class_chunk.semantic_signature == "public class Calculator"
        assert "public" in class_chunk.semantic_language_features

        # Check method chunks
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        assert len(method_chunks) == 3
        method_names = [c.semantic_name for c in method_chunks]
        assert "Calculator" in method_names  # constructor
        assert "add" in method_names
        assert "multiply" in method_names

    def test_java_interface_chunking(self):
        """Test parsing Java interfaces."""
        from code_indexer.indexing.java_parser import JavaSemanticParser

        parser = JavaSemanticParser(self.config)
        content = """
public interface Drawable {
    void draw();
    void setColor(String color);
    
    default void reset() {
        System.out.println("Resetting drawable");
    }
}
"""

        chunks = parser.chunk(content, "Drawable.java")

        assert len(chunks) == 4  # interface + 3 methods

        # Check interface chunk
        interface_chunk = chunks[0]
        assert interface_chunk.semantic_type == "interface"
        assert interface_chunk.semantic_name == "Drawable"
        assert interface_chunk.semantic_signature == "public interface Drawable"

        # Check method chunks
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        assert len(method_chunks) == 3
        method_names = [c.semantic_name for c in method_chunks]
        assert "draw" in method_names
        assert "setColor" in method_names
        assert "reset" in method_names

    def test_java_enum_chunking(self):
        """Test parsing Java enums."""
        from code_indexer.indexing.java_parser import JavaSemanticParser

        parser = JavaSemanticParser(self.config)
        content = """
public enum Color {
    RED("red"),
    GREEN("green"),
    BLUE("blue");
    
    private final String value;
    
    Color(String value) {
        this.value = value;
    }
    
    public String getValue() {
        return value;
    }
}
"""

        chunks = parser.chunk(content, "Color.java")

        # Should have enum + constructor + method
        enum_chunks = [c for c in chunks if c.semantic_type == "enum"]
        assert len(enum_chunks) == 1
        assert enum_chunks[0].semantic_name == "Color"

        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        assert len(method_chunks) >= 1
        method_names = [c.semantic_name for c in method_chunks]
        assert "getValue" in method_names

    def test_java_abstract_class_chunking(self):
        """Test parsing Java abstract classes."""
        from code_indexer.indexing.java_parser import JavaSemanticParser

        parser = JavaSemanticParser(self.config)
        content = """
public abstract class Shape {
    protected String name;
    
    public Shape(String name) {
        this.name = name;
    }
    
    public abstract double getArea();
    
    public String getName() {
        return name;
    }
}
"""

        chunks = parser.chunk(content, "Shape.java")

        # Check class chunk
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) == 1
        class_chunk = class_chunks[0]
        assert class_chunk.semantic_name == "Shape"
        assert "abstract" in class_chunk.semantic_language_features

        # Check methods
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        method_names = [c.semantic_name for c in method_chunks]
        assert "Shape" in method_names  # constructor
        assert "getArea" in method_names
        assert "getName" in method_names

    def test_java_generic_class_chunking(self):
        """Test parsing Java generic classes."""
        from code_indexer.indexing.java_parser import JavaSemanticParser

        parser = JavaSemanticParser(self.config)
        content = """
public class Container<T> {
    private T item;
    
    public Container(T item) {
        this.item = item;
    }
    
    public T getItem() {
        return item;
    }
    
    public <U> void process(U processor) {
        // Generic method
    }
}
"""

        chunks = parser.chunk(content, "Container.java")

        # Check class chunk
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) == 1
        class_chunk = class_chunks[0]
        assert class_chunk.semantic_name == "Container"
        assert "generic" in class_chunk.semantic_language_features
        assert "T" in class_chunk.semantic_context.get("generics", [])

        # Check generic method
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        generic_methods = [
            c for c in method_chunks if "generic" in c.semantic_language_features
        ]
        assert len(generic_methods) >= 1

    def test_java_annotation_chunking(self):
        """Test parsing Java annotations."""
        from code_indexer.indexing.java_parser import JavaSemanticParser

        parser = JavaSemanticParser(self.config)
        content = """
@Entity
@Table(name = "users")
public class User {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    
    @Column(nullable = false)
    private String name;
    
    @Override
    public String toString() {
        return "User{name='" + name + "'}";
    }
}
"""

        chunks = parser.chunk(content, "User.java")

        # Check class has annotations
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) == 1
        class_chunk = class_chunks[0]
        assert "annotation" in class_chunk.semantic_language_features
        annotations = class_chunk.semantic_context.get("annotations", [])
        assert "Entity" in annotations
        assert "Table" in annotations

        # Check method has Override annotation
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        override_methods = [
            c
            for c in method_chunks
            if "Override" in c.semantic_context.get("annotations", [])
        ]
        assert len(override_methods) >= 1

    def test_java_nested_class_chunking(self):
        """Test parsing Java nested classes."""
        from code_indexer.indexing.java_parser import JavaSemanticParser

        parser = JavaSemanticParser(self.config)
        content = """
public class OuterClass {
    private String outerField;
    
    public void outerMethod() {
        System.out.println("Outer method");
    }
    
    public static class StaticNestedClass {
        public void nestedMethod() {
            System.out.println("Static nested method");
        }
    }
    
    public class InnerClass {
        public void innerMethod() {
            System.out.println("Inner method");
        }
    }
}
"""

        chunks = parser.chunk(content, "OuterClass.java")

        # Should have outer class, nested classes, and methods
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) == 3
        class_names = [c.semantic_name for c in class_chunks]
        assert "OuterClass" in class_names
        assert "StaticNestedClass" in class_names
        assert "InnerClass" in class_names

        # Check nested class has proper parent
        nested_classes = [c for c in class_chunks if c.semantic_parent == "OuterClass"]
        assert len(nested_classes) == 2

    def test_java_package_handling(self):
        """Test handling Java package declarations."""
        from code_indexer.indexing.java_parser import JavaSemanticParser

        parser = JavaSemanticParser(self.config)
        content = """
package com.example.utils;

import java.util.List;
import java.util.ArrayList;

public class StringUtils {
    public static boolean isEmpty(String str) {
        return str == null || str.length() == 0;
    }
}
"""

        chunks = parser.chunk(content, "StringUtils.java")

        # Check package information is captured
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) == 1
        class_chunk = class_chunks[0]
        assert class_chunk.semantic_context.get("package") == "com.example.utils"


class TestJavaSemanticParserIntegration:
    """Test Java parser integration with SemanticChunker."""

    def setup_method(self):
        """Set up test configuration."""
        self.config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )

    def test_java_integration_with_semantic_chunker(self):
        """Test Java parser works with SemanticChunker."""
        chunker = SemanticChunker(self.config)

        content = """
public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}
"""

        chunks = chunker.chunk_content(content, "HelloWorld.java")

        assert len(chunks) >= 1
        semantic_chunks = [c for c in chunks if c.get("semantic_chunking")]
        assert len(semantic_chunks) >= 1

        # Should have class and method
        types = [c.get("semantic_type") for c in semantic_chunks]
        assert "class" in types
        assert "method" in types

        class_chunks = [c for c in semantic_chunks if c.get("semantic_type") == "class"]
        assert len(class_chunks) == 1
        assert class_chunks[0]["semantic_name"] == "HelloWorld"

    def test_java_fallback_integration(self):
        """Test Java parser fallback to text chunking."""
        chunker = SemanticChunker(self.config)

        # Malformed Java that should fail parsing
        content = """
public class BrokenClass {
    this is not valid Java syntax at all
    random words that make no sense
"""

        chunks = chunker.chunk_content(content, "BrokenClass.java")

        # Should fall back to text chunking
        assert len(chunks) > 0
        assert chunks[0]["semantic_chunking"] is False

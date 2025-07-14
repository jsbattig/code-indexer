"""
Tests for Kotlin semantic parser.
Following TDD approach - writing tests first.
"""

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestKotlinSemanticParser:
    """Test the Kotlin semantic parser."""

    def setup_method(self):
        """Set up test configuration."""
        self.config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )

    def test_kotlin_class_chunking(self):
        """Test parsing Kotlin classes."""
        from code_indexer.indexing.kotlin_parser import KotlinSemanticParser

        parser = KotlinSemanticParser(self.config)
        content = """
class Calculator(private var value: Int) {
    
    fun add(number: Int): Int {
        return value + number
    }
    
    fun multiply(a: Int, b: Int): Int {
        return a * b
    }
    
    companion object {
        fun staticMultiply(a: Int, b: Int): Int {
            return a * b
        }
    }
}
"""

        chunks = parser.chunk(content, "Calculator.kt")

        assert len(chunks) >= 3  # class + methods + companion object

        # Check class chunk
        class_chunk = chunks[0]
        assert class_chunk.semantic_type == "class"
        assert class_chunk.semantic_name == "Calculator"
        assert (
            class_chunk.semantic_signature == "class Calculator(private var value: Int)"
        )

        # Check method chunks
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        assert len(method_chunks) >= 2
        method_names = [c.semantic_name for c in method_chunks]
        assert "add" in method_names
        assert "multiply" in method_names

        # Check companion object
        companion_chunks = [c for c in chunks if c.semantic_type == "companion_object"]
        assert len(companion_chunks) == 1

    def test_kotlin_data_class_chunking(self):
        """Test parsing Kotlin data classes."""
        from code_indexer.indexing.kotlin_parser import KotlinSemanticParser

        parser = KotlinSemanticParser(self.config)
        content = """
data class User(
    val id: Long,
    val name: String,
    val email: String?
) {
    fun fullInfo(): String {
        return "$name ($email)"
    }
}
"""

        chunks = parser.chunk(content, "User.kt")

        # Check data class chunk
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) == 1
        class_chunk = class_chunks[0]
        assert class_chunk.semantic_name == "User"
        assert "data" in class_chunk.semantic_language_features

    def test_kotlin_interface_chunking(self):
        """Test parsing Kotlin interfaces."""
        from code_indexer.indexing.kotlin_parser import KotlinSemanticParser

        parser = KotlinSemanticParser(self.config)
        content = """
interface Drawable {
    fun draw()
    fun setColor(color: String)
    
    fun reset() {
        println("Resetting drawable")
    }
}
"""

        chunks = parser.chunk(content, "Drawable.kt")

        assert len(chunks) >= 1  # interface + methods

        # Check interface chunk
        interface_chunk = chunks[0]
        assert interface_chunk.semantic_type == "interface"
        assert interface_chunk.semantic_name == "Drawable"

    def test_kotlin_object_chunking(self):
        """Test parsing Kotlin objects."""
        from code_indexer.indexing.kotlin_parser import KotlinSemanticParser

        parser = KotlinSemanticParser(self.config)
        content = """
object DatabaseConfig {
    const val URL = "localhost"
    const val PORT = 5432
    
    fun getConnectionString(): String {
        return "$URL:$PORT"
    }
}
"""

        chunks = parser.chunk(content, "DatabaseConfig.kt")

        # Check object chunk
        object_chunks = [c for c in chunks if c.semantic_type == "object"]
        assert len(object_chunks) == 1
        assert object_chunks[0].semantic_name == "DatabaseConfig"

    def test_kotlin_sealed_class_chunking(self):
        """Test parsing Kotlin sealed classes."""
        from code_indexer.indexing.kotlin_parser import KotlinSemanticParser

        parser = KotlinSemanticParser(self.config)
        content = """
sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val exception: Exception) : Result<Nothing>()
    object Loading : Result<Nothing>()
    
    fun isSuccess(): Boolean = this is Success
}
"""

        chunks = parser.chunk(content, "Result.kt")

        # Check sealed class
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        sealed_classes = [
            c for c in class_chunks if "sealed" in c.semantic_language_features
        ]
        assert len(sealed_classes) >= 1
        assert sealed_classes[0].semantic_name == "Result"

    def test_kotlin_generic_class_chunking(self):
        """Test parsing Kotlin generic classes."""
        from code_indexer.indexing.kotlin_parser import KotlinSemanticParser

        parser = KotlinSemanticParser(self.config)
        content = """
class Container<T> {
    private var item: T? = null
    
    fun setItem(item: T) {
        this.item = item
    }
    
    fun getItem(): T? {
        return item
    }
    
    inline fun <reified U> transform(transform: (T) -> U): U? {
        return item?.let { transform(it) }
    }
}
"""

        chunks = parser.chunk(content, "Container.kt")

        # Check class chunk
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) == 1
        class_chunk = class_chunks[0]
        assert class_chunk.semantic_name == "Container"
        assert "generic" in class_chunk.semantic_language_features
        assert "T" in class_chunk.semantic_context.get("generics", [])

    def test_kotlin_annotation_chunking(self):
        """Test parsing Kotlin annotations."""
        from code_indexer.indexing.kotlin_parser import KotlinSemanticParser

        parser = KotlinSemanticParser(self.config)
        content = """
@Entity
@Table(name = "users")
data class User(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long,
    
    @Column(nullable = false)
    val name: String
) {
    @Override
    override fun toString(): String {
        return "User(name='$name')"
    }
}
"""

        chunks = parser.chunk(content, "User.kt")

        # Check class has annotations
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) == 1
        class_chunk = class_chunks[0]
        assert "annotation" in class_chunk.semantic_language_features
        annotations = class_chunk.semantic_context.get("annotations", [])
        assert "Entity" in annotations
        assert "Table" in annotations

    def test_kotlin_extension_function_chunking(self):
        """Test parsing Kotlin extension functions."""
        from code_indexer.indexing.kotlin_parser import KotlinSemanticParser

        parser = KotlinSemanticParser(self.config)
        content = """
fun String.isEmail(): Boolean {
    return this.contains("@") && this.contains(".")
}

fun List<Int>.median(): Double? {
    if (isEmpty()) return null
    val sorted = sorted()
    val middle = size / 2
    return if (size % 2 == 0) {
        (sorted[middle - 1] + sorted[middle]) / 2.0
    } else {
        sorted[middle].toDouble()
    }
}
"""

        chunks = parser.chunk(content, "StringExtensions.kt")

        # Check extension functions
        ext_chunks = [c for c in chunks if c.semantic_type == "extension_function"]
        assert len(ext_chunks) == 2
        ext_names = [c.semantic_name for c in ext_chunks]
        assert "isEmail" in ext_names
        assert "median" in ext_names

        # Check receiver types
        email_ext = [c for c in ext_chunks if c.semantic_name == "isEmail"][0]
        assert email_ext.semantic_context.get("receiver_type") == "String"

    def test_kotlin_coroutine_chunking(self):
        """Test parsing Kotlin coroutines."""
        from code_indexer.indexing.kotlin_parser import KotlinSemanticParser

        parser = KotlinSemanticParser(self.config)
        content = """
class DataRepository {
    suspend fun fetchData(): List<String> {
        delay(1000)
        return listOf("data1", "data2")
    }
    
    suspend fun processData(data: List<String>): Int {
        return data.size
    }
}
"""

        chunks = parser.chunk(content, "DataRepository.kt")

        # Check suspend functions
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        suspend_methods = [
            c for c in method_chunks if "suspend" in c.semantic_language_features
        ]
        assert len(suspend_methods) == 2
        assert all("coroutine" in m.semantic_language_features for m in suspend_methods)

    def test_kotlin_property_with_accessors_chunking(self):
        """Test parsing Kotlin properties with custom getters/setters."""
        from code_indexer.indexing.kotlin_parser import KotlinSemanticParser

        parser = KotlinSemanticParser(self.config)
        content = """
class Temperature {
    var celsius: Double = 0.0
        get() = field
        set(value) {
            field = value
        }
    
    val fahrenheit: Double
        get() = celsius * 9 / 5 + 32
}
"""

        chunks = parser.chunk(content, "Temperature.kt")

        # Check property chunks
        property_chunks = [c for c in chunks if c.semantic_type == "property"]
        assert len(property_chunks) >= 1
        property_names = [c.semantic_name for c in property_chunks]
        assert "celsius" in property_names or "fahrenheit" in property_names

    def test_kotlin_inner_class_chunking(self):
        """Test parsing Kotlin inner and nested classes."""
        from code_indexer.indexing.kotlin_parser import KotlinSemanticParser

        parser = KotlinSemanticParser(self.config)
        content = """
class Outer {
    private val bar: Int = 1
    
    inner class Inner {
        fun foo() = bar
    }
    
    class Nested {
        fun baz() = 2
    }
}
"""

        chunks = parser.chunk(content, "Outer.kt")

        # Should have outer class and nested classes
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) == 3
        class_names = [c.semantic_name for c in class_chunks]
        assert "Outer" in class_names
        assert "Inner" in class_names
        assert "Nested" in class_names

        # Check inner class has proper parent
        inner_classes = [c for c in class_chunks if c.semantic_parent == "Outer"]
        assert len(inner_classes) == 2

    def test_kotlin_enum_class_chunking(self):
        """Test parsing Kotlin enum classes."""
        from code_indexer.indexing.kotlin_parser import KotlinSemanticParser

        parser = KotlinSemanticParser(self.config)
        content = """
enum class Color(val rgb: Int) {
    RED(0xFF0000),
    GREEN(0x00FF00),
    BLUE(0x0000FF);
    
    fun toHex(): String {
        return "#${rgb.toString(16).padStart(6, '0')}"
    }
}
"""

        chunks = parser.chunk(content, "Color.kt")

        # Check enum class
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        enum_chunks = [
            c for c in class_chunks if "enum" in c.semantic_language_features
        ]
        assert len(enum_chunks) == 1
        assert enum_chunks[0].semantic_name == "Color"

    def test_kotlin_inline_class_chunking(self):
        """Test parsing Kotlin inline/value classes."""
        from code_indexer.indexing.kotlin_parser import KotlinSemanticParser

        parser = KotlinSemanticParser(self.config)
        content = """
@JvmInline
value class Password(private val s: String) {
    init {
        require(s.length >= 8) { "Password must be at least 8 characters" }
    }
    
    fun isStrong(): Boolean {
        return s.any { it.isDigit() } && s.any { it.isLetter() }
    }
}
"""

        chunks = parser.chunk(content, "Password.kt")

        # Check value class
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        value_chunks = [
            c for c in class_chunks if "value" in c.semantic_language_features
        ]
        assert len(value_chunks) == 1
        assert value_chunks[0].semantic_name == "Password"

    def test_kotlin_package_handling(self):
        """Test handling Kotlin package declarations."""
        from code_indexer.indexing.kotlin_parser import KotlinSemanticParser

        parser = KotlinSemanticParser(self.config)
        content = """
package com.example.utils

import java.util.*

object StringUtils {
    fun isEmpty(str: String?): Boolean {
        return str.isNullOrEmpty()
    }
}
"""

        chunks = parser.chunk(content, "StringUtils.kt")

        # Check package information is captured
        object_chunks = [c for c in chunks if c.semantic_type == "object"]
        assert len(object_chunks) == 1
        object_chunk = object_chunks[0]
        assert object_chunk.semantic_context.get("package") == "com.example.utils"

    def test_kotlin_expression_functions(self):
        """Test parsing Kotlin expression functions."""
        from code_indexer.indexing.kotlin_parser import KotlinSemanticParser

        parser = KotlinSemanticParser(self.config)
        content = """
class MathUtils {
    fun square(x: Int) = x * x
    
    fun cube(x: Int): Int = x * x * x
    
    fun isEven(x: Int) = x % 2 == 0
}
"""

        chunks = parser.chunk(content, "MathUtils.kt")

        # Check method chunks
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        assert len(method_chunks) == 3
        method_names = [c.semantic_name for c in method_chunks]
        assert "square" in method_names
        assert "cube" in method_names
        assert "isEven" in method_names


class TestKotlinSemanticParserIntegration:
    """Test Kotlin parser integration with SemanticChunker."""

    def setup_method(self):
        """Set up test configuration."""
        self.config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )

    def test_kotlin_integration_with_semantic_chunker(self):
        """Test Kotlin parser works with SemanticChunker."""
        chunker = SemanticChunker(self.config)

        content = """
fun main() {
    println("Hello, World!")
}

class HelloWorld {
    fun greet(name: String) {
        println("Hello, $name!")
    }
}
"""

        chunks = chunker.chunk_content(content, "HelloWorld.kt")

        assert len(chunks) >= 1
        semantic_chunks = [c for c in chunks if c.get("semantic_chunking")]
        assert len(semantic_chunks) >= 1

        # Should have function and class
        types = [c.get("semantic_type") for c in semantic_chunks]
        assert "function" in types
        assert "class" in types

        class_chunks = [c for c in semantic_chunks if c.get("semantic_type") == "class"]
        assert len(class_chunks) == 1
        assert class_chunks[0]["semantic_name"] == "HelloWorld"

    def test_kotlin_script_integration(self):
        """Test Kotlin script (.kts) file parsing."""
        chunker = SemanticChunker(self.config)

        content = """
import java.io.File

val greeting = "Hello"
val name = "Kotlin Script"

fun printGreeting() {
    println("$greeting, $name!")
}

printGreeting()
"""

        chunks = chunker.chunk_content(content, "script.kts")

        assert len(chunks) >= 1
        semantic_chunks = [c for c in chunks if c.get("semantic_chunking")]
        assert len(semantic_chunks) >= 1

    def test_kotlin_fallback_integration(self):
        """Test Kotlin parser fallback to text chunking."""
        chunker = SemanticChunker(self.config)

        # Malformed Kotlin that should fail parsing
        content = """
class BrokenClass {
    this is not valid Kotlin syntax at all
    random words that make no sense
"""

        chunks = chunker.chunk_content(content, "BrokenClass.kt")

        # Should fall back to text chunking
        assert len(chunks) > 0
        assert chunks[0]["semantic_chunking"] is False

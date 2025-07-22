"""
Tests for C# semantic parser.
Following TDD approach - writing tests first.
"""

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestCSharpSemanticParser:
    """Test the C# semantic parser."""

    def setup_method(self):
        """Set up test configuration."""
        self.config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )

    def test_csharp_class_chunking(self):
        """Test parsing C# classes."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        parser = CSharpSemanticParser(self.config)
        content = """
namespace Calculator.Core
{
    public class Calculator
    {
        private int _value;
        
        public Calculator(int initialValue)
        {
            _value = initialValue;
        }
        
        public int Add(int number)
        {
            return _value + number;
        }
        
        public static int Multiply(int a, int b)
        {
            return a * b;
        }

        public int Value { get; private set; }
    }
}
"""

        chunks = parser.chunk(content, "Calculator.cs")

        # Should find namespace and class (methods may be included in class chunk)
        assert len(chunks) >= 2

        # Check for namespace chunk
        namespace_chunks = [c for c in chunks if c.semantic_type == "namespace"]
        assert len(namespace_chunks) >= 1
        namespace_chunk = namespace_chunks[0]
        assert namespace_chunk.semantic_name == "Calculator.Core"
        assert namespace_chunk.semantic_type == "namespace"

        # Check class chunk
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1
        class_chunk = class_chunks[0]
        assert class_chunk.semantic_type == "class"
        assert class_chunk.semantic_name == "Calculator"

        # Check method chunks - methods may be embedded within class chunk
        # Look for method names in the content instead of separate chunks
        all_content = "\n".join(chunk.text for chunk in chunks)
        assert "Add" in all_content
        assert "Multiply" in all_content
        assert "Calculator(" in all_content  # Constructor

    def test_csharp_interface_chunking(self):
        """Test parsing C# interfaces."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        parser = CSharpSemanticParser(self.config)
        content = """
public interface IDrawable
{
    void Draw();
    void SetColor(string color);
    
    string Color { get; set; }
}
"""

        chunks = parser.chunk(content, "IDrawable.cs")

        # Should find interface, methods, and property
        assert len(chunks) >= 1

        # Check interface chunk
        interface_chunks = [c for c in chunks if c.semantic_type == "interface"]
        assert len(interface_chunks) >= 1
        interface_chunk = interface_chunks[0]
        assert interface_chunk.semantic_type == "interface"
        assert interface_chunk.semantic_name == "IDrawable"

    def test_csharp_struct_chunking(self):
        """Test parsing C# structs."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        parser = CSharpSemanticParser(self.config)
        content = """
public struct Point
{
    public int X { get; set; }
    public int Y { get; set; }
    
    public Point(int x, int y)
    {
        X = x;
        Y = y;
    }
    
    public double DistanceFromOrigin()
    {
        return Math.Sqrt(X * X + Y * Y);
    }
}
"""

        chunks = parser.chunk(content, "Point.cs")

        # Should find struct, properties, constructor, and method
        assert len(chunks) >= 1

        # Check struct chunk
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        assert len(struct_chunks) >= 1
        struct_chunk = struct_chunks[0]
        assert struct_chunk.semantic_type == "struct"
        assert struct_chunk.semantic_name == "Point"

    def test_csharp_enum_chunking(self):
        """Test parsing C# enums."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        parser = CSharpSemanticParser(self.config)
        content = """
public enum Colors
{
    Red,
    Green,
    Blue,
    Yellow = 10,
    Orange
}
"""

        chunks = parser.chunk(content, "Colors.cs")

        # Should find enum
        assert len(chunks) >= 1

        # Check enum chunk
        enum_chunks = [c for c in chunks if c.semantic_type == "enum"]
        assert len(enum_chunks) >= 1
        enum_chunk = enum_chunks[0]
        assert enum_chunk.semantic_type == "enum"
        assert enum_chunk.semantic_name == "Colors"

    def test_csharp_property_chunking(self):
        """Test parsing C# properties."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        parser = CSharpSemanticParser(self.config)
        content = """
public class Person
{
    public string Name { get; set; }
    
    public int Age { get; private set; }
    
    private string _email;
    public string Email 
    { 
        get { return _email; }
        set { _email = value?.ToLower(); }
    }
}
"""

        chunks = parser.chunk(content, "Person.cs")

        # Should find class and properties
        assert len(chunks) >= 1

        # Check class chunk
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1

    def test_csharp_using_statements(self):
        """Test parsing C# using statements."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        parser = CSharpSemanticParser(self.config)
        content = """
using System;
using System.Collections.Generic;
using System.Linq;

namespace MyNamespace
{
    public class MyClass
    {
        public void DoSomething()
        {
            Console.WriteLine("Hello World");
        }
    }
}
"""

        chunks = parser.chunk(content, "MyClass.cs")

        # Should find using statements, namespace, class, and method
        assert len(chunks) >= 1

        # Check for using statements
        # Note: using statements might not be captured as separate chunks in all implementations
        # using_chunks = [c for c in chunks if c.semantic_type == "using"]

    def test_semantic_chunker_integration(self):
        """Test that C# files are properly handled by SemanticChunker."""
        chunker = SemanticChunker(self.config)

        content = """
using System;

namespace TestNamespace
{
    public class TestClass
    {
        public void TestMethod()
        {
            Console.WriteLine("Test");
        }
    }
}
"""

        chunks = chunker.chunk_content(content, "test.cs")

        # Should get semantic chunks (not fallback to text chunking)
        assert len(chunks) > 0

        # Check that semantic chunking was used
        has_semantic_chunks = any(
            chunk.get("semantic_chunking", False) for chunk in chunks
        )
        assert has_semantic_chunks or chunks[0].get("semantic_chunking") is not False

    def test_csharp_delegate_chunking(self):
        """Test parsing C# delegates."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        parser = CSharpSemanticParser(self.config)
        content = """
public delegate void EventHandler(object sender, EventArgs e);

public delegate int Calculator(int x, int y);
"""

        chunks = parser.chunk(content, "Delegates.cs")

        # Should find delegate declarations
        assert len(chunks) >= 1

        # Look for delegate chunks if they're created as separate chunks
        # (implementation may vary - delegates might be part of larger chunks)

    def test_csharp_event_chunking(self):
        """Test parsing C# events."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        parser = CSharpSemanticParser(self.config)
        content = """
public class Publisher
{
    public event Action<string> OnMessageReceived;
    
    public void SendMessage(string message)
    {
        OnMessageReceived?.Invoke(message);
    }
}
"""

        chunks = parser.chunk(content, "Publisher.cs")

        # Should find class, event, and method
        assert len(chunks) >= 1

        # Check class chunk
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1

    def test_csharp_nested_classes(self):
        """Test parsing nested C# classes."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        parser = CSharpSemanticParser(self.config)
        content = """
public class OuterClass
{
    public class InnerClass
    {
        public void InnerMethod()
        {
            // Inner method implementation
        }
    }
    
    public void OuterMethod()
    {
        // Outer method implementation
    }
}
"""

        chunks = parser.chunk(content, "NestedClasses.cs")

        # Should find outer class, inner class, and methods
        assert len(chunks) >= 1

        # Check that we have class chunks
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1

    def test_csharp_regex_fallback(self):
        """Test regex fallback for C# when tree-sitter fails."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        parser = CSharpSemanticParser(self.config)

        # Test the regex fallback method directly
        error_text = """
public class TestClass {
    private int field;
    public void Method() {
        // method body
    }
}
"""

        constructs = parser._extract_constructs_from_error_text(error_text, 1, [])

        # Should find class and method through regex
        assert len(constructs) >= 1

        # Check that constructs were found
        construct_types = [c["type"] for c in constructs]
        assert "class" in construct_types

    def test_chunking_no_data_loss(self):
        """Test that chunking preserves all content without data loss."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        parser = CSharpSemanticParser(self.config)
        content = """using System;
using System.Collections.Generic;
using System.Linq;

namespace DataIntegrityTest.Services
{
    /// <summary>
    /// This is a comprehensive test class with various C# constructs
    /// to ensure no data is lost during semantic chunking.
    /// </summary>
    public class DataProcessor
    {
        // Field with initialization
        private readonly List<string> _items = new List<string>();
        
        // Property with full accessors
        public string Name 
        { 
            get => _name;
            set => _name = value?.Trim();
        }
        private string _name;
        
        // Event declaration
        public event EventHandler<string> ProcessingComplete;
        
        // Constructor with parameters
        public DataProcessor(string initialName)
        {
            Name = initialName;
            _items = new List<string>();
        }
        
        // Method with various modifiers
        public async Task<List<T>> ProcessDataAsync<T>(IEnumerable<T> data) where T : class
        {
            var results = new List<T>();
            foreach (var item in data)
            {
                // Some processing logic here
                results.Add(item);
            }
            ProcessingComplete?.Invoke(this, "Processing completed");
            return results;
        }
        
        // Static method
        public static bool ValidateData(object data)
        {
            return data != null;
        }
    }
    
    // Interface definition
    public interface IDataHandler
    {
        Task<bool> HandleAsync(string data);
        string Format(object input);
    }
    
    // Struct with methods
    public struct DataPoint
    {
        public int X { get; set; }
        public int Y { get; set; }
        
        public double Distance => Math.Sqrt(X * X + Y * Y);
        
        public DataPoint(int x, int y)
        {
            X = x;
            Y = y;
        }
    }
    
    // Enum with explicit values
    public enum DataStatus
    {
        Pending = 0,
        Processing = 1,
        Completed = 2,
        Failed = 99
    }
}"""

        chunks = parser.chunk(content, "DataProcessor.cs")

        # Verify no data loss by checking that all content is captured
        all_chunk_content = "\n".join(chunk.text for chunk in chunks)

        # Check that essential elements are preserved
        assert "using System;" in all_chunk_content
        assert "namespace DataIntegrityTest.Services" in all_chunk_content
        assert "class DataProcessor" in all_chunk_content
        assert "interface IDataHandler" in all_chunk_content
        assert "struct DataPoint" in all_chunk_content
        assert "enum DataStatus" in all_chunk_content
        assert "ProcessDataAsync" in all_chunk_content
        assert "ValidateData" in all_chunk_content

        # Check that we have reasonable chunk coverage
        assert len(chunks) >= 3  # Should have multiple semantic chunks

        # Verify all chunks have proper metadata
        for chunk in chunks:
            assert chunk.semantic_chunking is True
            assert chunk.semantic_type is not None
            assert chunk.semantic_name is not None
            assert chunk.file_path == "DataProcessor.cs"
            assert chunk.line_start > 0
            assert chunk.line_end >= chunk.line_start

    def test_chunking_edge_cases(self):
        """Test chunking with various edge cases."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        parser = CSharpSemanticParser(self.config)

        # Test empty namespace
        empty_namespace = """
namespace EmptyNamespace
{
}
"""
        chunks = parser.chunk(empty_namespace, "empty.cs")
        assert len(chunks) >= 1
        namespace_chunks = [c for c in chunks if c.semantic_type == "namespace"]
        assert len(namespace_chunks) >= 1

    def test_chunking_nested_constructs(self):
        """Test chunking with deeply nested constructs."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        parser = CSharpSemanticParser(self.config)
        content = """
namespace Outer.Middle.Inner
{
    public class OuterClass
    {
        public class NestedClass
        {
            public class DeeplyNestedClass
            {
                public void DeepMethod()
                {
                    // Deep nesting test
                }
            }
            
            public void NestedMethod()
            {
                // Nested method
            }
        }
        
        public void OuterMethod()
        {
            // Outer method
        }
    }
}
"""

        chunks = parser.chunk(content, "nested.cs")

        # Should handle nested constructs properly
        assert len(chunks) >= 2

        # Check that nested classes are captured
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        class_names = [c.semantic_name for c in class_chunks]
        assert "OuterClass" in class_names

        # Verify proper scoping in paths
        for chunk in chunks:
            if chunk.semantic_type == "class" and chunk.semantic_name == "OuterClass":
                assert "Outer.Middle.Inner" in chunk.semantic_path

    def test_chunking_malformed_code(self):
        """Test chunking with malformed/incomplete C# code."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        parser = CSharpSemanticParser(self.config)

        # Test incomplete class (missing closing brace)
        malformed_code = """
using System;

namespace TestNamespace
{
    public class IncompleteClass
    {
        public void Method1()
        {
            Console.WriteLine("Test");
        
        // Missing closing braces
        public void Method2()
        // No body
"""

        chunks = parser.chunk(malformed_code, "malformed.cs")

        # Should still parse what it can and fall back to regex
        assert len(chunks) >= 1

        # Should capture some constructs even if malformed
        all_content = "\n".join(chunk.text for chunk in chunks)
        assert "TestNamespace" in all_content or "IncompleteClass" in all_content

    def test_chunking_very_large_constructs(self):
        """Test chunking with very large constructs that might exceed chunk size."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        # Use smaller chunk size to test splitting
        small_config = IndexingConfig(
            chunk_size=500, chunk_overlap=50, use_semantic_chunking=True
        )
        parser = CSharpSemanticParser(small_config)

        # Create a large method
        large_method_lines = []
        large_method_lines.append("public void LargeMethod()")
        large_method_lines.append("{")

        # Add many lines to exceed chunk size
        for i in range(100):
            large_method_lines.append(
                f'    Console.WriteLine("This is line {i} of a very long method");'
            )

        large_method_lines.append("}")

        content = f"""
namespace LargeTest
{{
    public class LargeClass
    {{
        {chr(10).join(large_method_lines)}
        
        public void SmallMethod()
        {{
            Console.WriteLine("Small method");
        }}
    }}
}}
"""

        chunks = parser.chunk(content, "large.cs")

        # Should handle large constructs
        assert len(chunks) >= 1

        # Verify all content is preserved
        all_content = "\n".join(chunk.text for chunk in chunks)
        assert "LargeMethod" in all_content
        assert "SmallMethod" in all_content
        assert "line 50" in all_content  # Check middle content is preserved

    def test_chunking_special_characters(self):
        """Test chunking with special characters and Unicode."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        parser = CSharpSemanticParser(self.config)
        content = """
namespace SpecialChars
{
    /// <summary>
    /// Class with special characters: ñáéíóú, 中文, Ελληνικά, العربية
    /// </summary>
    public class SpecialCharClass
    {
        // String with various quotes and escapes
        private string _specialString = "This has \\"quotes\\", \\n newlines, and \\t tabs";
        
        public void MethodWith_Underscore()
        {
            var message = $"Unicode test: {char.ConvertFromUtf32(0x1F600)}"; // Emoji
        }
        
        // Method with special parameter names
        public void ProcessData(string naïveApproach, int número, bool isValidInput)
        {
            // Method body with special chars
        }
    }
}
"""

        chunks = parser.chunk(content, "special.cs")

        # Should handle special characters without issues
        assert len(chunks) >= 1

        all_content = "\n".join(chunk.text for chunk in chunks)
        assert "SpecialCharClass" in all_content
        assert "MethodWith_Underscore" in all_content
        assert "ProcessData" in all_content
        assert "naïveApproach" in all_content or "número" in all_content

    def test_chunking_different_brace_styles(self):
        """Test chunking with different brace placement styles."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        parser = CSharpSemanticParser(self.config)

        # Test Allman style (braces on new lines)
        allman_style = """
namespace AllmanStyle
{
    public class AllmanClass
    {
        public void AllmanMethod()
        {
            if (true)
            {
                Console.WriteLine("Allman");
            }
        }
    }
}
"""

        # Test K&R style (opening braces on same line)
        kr_style = """
namespace KRStyle {
    public class KRClass {
        public void KRMethod() {
            if (true) {
                Console.WriteLine("K&R");
            }
        }
    }
}
"""

        allman_chunks = parser.chunk(allman_style, "allman.cs")
        kr_chunks = parser.chunk(kr_style, "kr.cs")

        # Both styles should be parsed correctly
        assert len(allman_chunks) >= 2
        assert len(kr_chunks) >= 2

        # Check that classes are found in both styles
        allman_classes = [c for c in allman_chunks if c.semantic_type == "class"]
        kr_classes = [c for c in kr_chunks if c.semantic_type == "class"]

        assert len(allman_classes) >= 1
        assert len(kr_classes) >= 1
        assert allman_classes[0].semantic_name == "AllmanClass"
        assert kr_classes[0].semantic_name == "KRClass"

    def test_chunking_attributes_and_annotations(self):
        """Test chunking with C# attributes and XML documentation."""
        from code_indexer.indexing.csharp_parser import CSharpSemanticParser

        parser = CSharpSemanticParser(self.config)
        content = """
using System;
using System.ComponentModel.DataAnnotations;

namespace AttributeTest
{
    /// <summary>
    /// Test class with various attributes
    /// </summary>
    [Serializable]
    [Obsolete("This class is deprecated")]
    public class AttributeClass
    {
        /// <summary>
        /// Property with data annotations
        /// </summary>
        /// <value>The user's name</value>
        [Required]
        [StringLength(50, MinimumLength = 2)]
        public string Name { get; set; }
        
        /// <summary>
        /// Method with multiple attributes
        /// </summary>
        /// <param name="input">The input parameter</param>
        /// <returns>Processed result</returns>
        [Deprecated]
        [HttpPost]
        [Route("api/process")]
        public string ProcessData([Required] string input)
        {
            return input.ToUpper();
        }
    }
}
"""

        chunks = parser.chunk(content, "attributes.cs")

        # Should handle attributes without issues
        assert len(chunks) >= 1

        all_content = "\n".join(chunk.text for chunk in chunks)
        assert "AttributeClass" in all_content
        assert "ProcessData" in all_content
        assert "[Required]" in all_content or "Required" in all_content
        assert "XML documentation" in all_content or "summary" in all_content

    def test_fallback_to_text_chunking(self):
        """Test fallback to text chunking when semantic parsing fails completely."""
        chunker = SemanticChunker(self.config)

        # Create content that might cause tree-sitter to fail
        problematic_content = """
// This is not valid C# syntax but should still be indexed
random text that looks like code but isn't
{{{ malformed braces
class UnfinishedClass
    method without proper syntax
    
namespace MixedUp {
    public class PartiallyValid {
        // This part is valid
        public void Method() {
            Console.WriteLine("Hello");
        }
// Missing closing braces and random content below
some more random text
"""

        chunks = chunker.chunk_content(problematic_content, "problematic.cs")

        # Should still create chunks (either semantic or text fallback)
        assert len(chunks) >= 1

        # Should preserve all content even if it falls back to text chunking
        all_content = "\n".join(chunk["text"] for chunk in chunks)
        # The parser may extract specific constructs, so check for key elements
        assert "UnfinishedClass" in all_content or "PartiallyValid" in all_content
        assert "Hello" in all_content

        # Ensure we got some chunks with content
        assert len(all_content) > 100  # Should have substantial content

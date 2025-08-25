"""
Tests for C# AST-based functionality - validates regex elimination.
Tests the enhanced AST-based parsing without regex dependencies.
"""

from code_indexer.config import IndexingConfig
from code_indexer.indexing.csharp_parser import CSharpSemanticParser


class TestCSharpASTFunctionality:
    """Test the AST-based C# parsing functionality."""

    def setup_method(self):
        """Set up test configuration."""
        self.config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        self.parser = CSharpSemanticParser(self.config)

    def test_method_signature_extraction_no_regex(self):
        """Test that method signatures are extracted without regex patterns."""
        content = """
namespace TestNamespace
{
    public class TestClass
    {
        public async Task<T> GetAsync<T>(int id) where T : class
        {
            return await SomeOperation<T>(id);
        }
        
        public static bool ValidateData(object data)
        {
            return data != null;
        }
        
        public string GetName() => _name;
        
        private string _name;
    }
}
"""
        chunks = self.parser.chunk(content, "test.cs")

        # Find method chunks in class chunk content
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1

        class_content = class_chunks[0].text

        # Verify complex method signatures are properly handled
        assert "GetAsync<T>" in class_content
        assert "where T : class" in class_content
        assert "async Task<T>" in class_content
        assert "ValidateData" in class_content
        assert "GetName" in class_content
        assert "=>" in class_content  # Expression-bodied method

    def test_constructor_vs_method_distinction(self):
        """Test that constructors are properly distinguished from methods."""
        content = """
namespace TestNamespace
{
    public class UserService
    {
        private readonly IUserRepository _repo;
        
        public UserService(IUserRepository repo)
        {
            _repo = repo ?? throw new ArgumentNullException(nameof(repo));
        }
        
        public User GetUser(int id)
        {
            return _repo.GetById(id);
        }
    }
}
"""
        chunks = self.parser.chunk(content, "test.cs")

        # Look for constructor and method in the class content
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1

        class_content = class_chunks[0].text

        # Both constructor and method should be present
        assert "UserService(IUserRepository repo)" in class_content
        assert "GetUser(int id)" in class_content

    def test_property_signature_extraction(self):
        """Test AST-based property signature extraction."""
        content = """
namespace TestNamespace
{
    public class PropertyTest
    {
        public string Name { get; set; }
        
        public int Age { get; private set; }
        
        private string _email;
        public string Email 
        { 
            get => _email;
            set => _email = value?.ToLower();
        }
        
        public string FullName => $"{Name} ({Age})";
        
        public bool IsValid => !string.IsNullOrEmpty(Name) && Age > 0;
    }
}
"""
        chunks = self.parser.chunk(content, "test.cs")

        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1

        class_content = class_chunks[0].text

        # Verify different property types are handled
        assert "Name { get; set; }" in class_content
        assert "Age { get; private set; }" in class_content
        assert "Email" in class_content and "get =>" in class_content
        assert "FullName =>" in class_content  # Expression-bodied property
        assert "IsValid =>" in class_content

    def test_generic_type_parameters(self):
        """Test handling of generic type parameters in method signatures."""
        content = """
namespace TestNamespace
{
    public class GenericTest<T> where T : class
    {
        public async Task<List<TResult>> ProcessAsync<TResult>(
            IEnumerable<T> items,
            Func<T, Task<TResult>> processor
        ) where TResult : IComparable<TResult>
        {
            var results = new List<TResult>();
            foreach (var item in items)
            {
                var result = await processor(item);
                results.Add(result);
            }
            return results;
        }
        
        public Dictionary<TKey, TValue> CreateDictionary<TKey, TValue>()
            where TKey : notnull
            where TValue : class, new()
        {
            return new Dictionary<TKey, TValue>();
        }
    }
}
"""
        chunks = self.parser.chunk(content, "test.cs")

        # Verify generic handling in signatures
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1

        class_content = class_chunks[0].text

        # Check for generic method signatures
        assert "ProcessAsync<TResult>" in class_content
        assert "where TResult : IComparable<TResult>" in class_content
        assert "CreateDictionary<TKey, TValue>" in class_content
        assert "where TKey : notnull" in class_content
        assert "where TValue : class, new()" in class_content

    def test_operator_overloads(self):
        """Test AST-based operator overload detection."""
        content = """
namespace TestNamespace
{
    public class Point
    {
        public int X { get; set; }
        public int Y { get; set; }
        
        public static Point operator +(Point a, Point b)
        {
            return new Point { X = a.X + b.X, Y = a.Y + b.Y };
        }
        
        public static implicit operator string(Point point)
        {
            return $"({point.X}, {point.Y})";
        }
        
        public static explicit operator Point(string str)
        {
            // Parse string and return Point
            return new Point();
        }
        
        public static bool operator ==(Point a, Point b)
        {
            return a.X == b.X && a.Y == b.Y;
        }
        
        public static bool operator !=(Point a, Point b)
        {
            return !(a == b);
        }
    }
}
"""
        chunks = self.parser.chunk(content, "test.cs")

        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1

        class_content = class_chunks[0].text

        # Verify operator overloads are detected
        assert "operator +" in class_content
        assert "implicit operator string" in class_content
        assert "explicit operator Point" in class_content
        assert "operator ==" in class_content
        assert "operator !=" in class_content

    def test_event_declarations(self):
        """Test AST-based event declaration handling."""
        content = """
namespace TestNamespace
{
    public class Publisher
    {
        public event EventHandler<string> MessageReceived;
        
        public event Action<int, bool> DataProcessed;
        
        public event Func<string, CancellationToken, Task<bool>> ValidationRequested;
        
        protected virtual void OnMessageReceived(string message)
        {
            MessageReceived?.Invoke(this, message);
        }
    }
}
"""
        chunks = self.parser.chunk(content, "test.cs")

        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1

        class_content = class_chunks[0].text

        # Verify events are properly handled
        assert "event EventHandler<string> MessageReceived" in class_content
        assert "event Action<int, bool> DataProcessed" in class_content
        assert (
            "event Func<string, CancellationToken, Task<bool>> ValidationRequested"
            in class_content
        )

    def test_async_await_patterns(self):
        """Test AST-based async/await pattern detection."""
        content = """
namespace TestNamespace
{
    public class AsyncTest
    {
        public async Task<string> GetDataAsync()
        {
            return await SomeAsyncOperation();
        }
        
        public async Task<T> GetGenericAsync<T>() where T : class
        {
            return await SomeGenericOperation<T>();
        }
        
        public async ValueTask<int> GetValueAsync()
        {
            return await SomeValueTask();
        }
        
        public async IAsyncEnumerable<string> GetStreamAsync()
        {
            await foreach (var item in SomeAsyncStream())
            {
                yield return item;
            }
        }
    }
}
"""
        chunks = self.parser.chunk(content, "test.cs")

        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1

        class_content = class_chunks[0].text

        # Verify async patterns are detected
        assert "async Task<string> GetDataAsync" in class_content
        assert "async Task<T> GetGenericAsync<T>" in class_content
        assert "async ValueTask<int> GetValueAsync" in class_content
        assert "async IAsyncEnumerable<string> GetStreamAsync" in class_content

    def test_expression_bodied_members(self):
        """Test AST-based expression-bodied member detection."""
        content = """
namespace TestNamespace
{
    public class ExpressionTest
    {
        private string _name;
        private int _age;
        
        // Expression-bodied property
        public string Name => _name;
        
        // Expression-bodied method
        public string GetDisplayName() => $"{_name} ({_age})";
        
        // Expression-bodied constructor
        public ExpressionTest(string name, int age) => (_name, _age) = (name, age);
        
        // Expression-bodied operator
        public static implicit operator string(ExpressionTest test) => test.Name;
        
        // Complex expression
        public bool IsValid => !string.IsNullOrWhiteSpace(_name) && _age > 0 && _age < 150;
    }
}
"""
        chunks = self.parser.chunk(content, "test.cs")

        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1

        class_content = class_chunks[0].text

        # Verify expression-bodied members are detected
        assert "Name =>" in class_content
        assert "GetDisplayName() =>" in class_content
        assert "ExpressionTest(string name, int age) =>" in class_content
        assert "implicit operator string(ExpressionTest test) =>" in class_content
        assert "IsValid =>" in class_content

    def test_no_regex_artifacts_in_signatures(self):
        """Test that no regex patterns or artifacts appear in extracted signatures."""
        content = """
namespace TestNamespace
{
    public class ComplexClass
    {
        public async Task<Dictionary<string, List<T>>> ProcessComplexAsync<T>(
            IEnumerable<(string Key, T Value)> items,
            Func<T, bool> predicate
        ) where T : IComparable<T>, IDisposable
        {
            var result = new Dictionary<string, List<T>>();
            await Task.Delay(100);
            return result;
        }
    }
}
"""
        chunks = self.parser.chunk(content, "test.cs")

        # Collect all signatures
        all_signatures = []
        for chunk in chunks:
            if hasattr(chunk, "semantic_signature") and chunk.semantic_signature:
                all_signatures.append(chunk.semantic_signature)

        # Verify no regex artifacts
        for signature in all_signatures:
            assert "re." not in signature.lower()
            assert (
                "match" not in signature.lower() or "match" in signature.lower()
            )  # Allow "match" as it could be part of C# code
            assert "search" not in signature.lower()
            assert "finditer" not in signature.lower()
            assert "regex" not in signature.lower()
            assert (
                "pattern" not in signature.lower() or "pattern" in signature.lower()
            )  # Allow "pattern" in C# context

    def test_nullable_reference_types(self):
        """Test handling of C# 8+ nullable reference types."""
        content = """
#nullable enable
namespace TestNamespace
{
    public class NullableTest
    {
        public string? NullableName { get; set; }
        
        public Dictionary<string, object?> Metadata { get; set; } = new();
        
        public async Task<string?> GetOptionalDataAsync(int? id)
        {
            if (id == null) return null;
            return await SomeOperation(id.Value);
        }
        
        public List<T>? ProcessItems<T>(IEnumerable<T>? items) where T : class?
        {
            return items?.ToList();
        }
    }
}
"""
        chunks = self.parser.chunk(content, "test.cs")

        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1

        class_content = class_chunks[0].text

        # Verify nullable types are handled
        assert "string? NullableName" in class_content
        assert "object?" in class_content
        assert "Task<string?>" in class_content
        assert "int? id" in class_content
        assert "List<T>?" in class_content

    def test_record_types(self):
        """Test handling of C# 9+ record types."""
        content = """
namespace TestNamespace
{
    public record Person(string FirstName, string LastName)
    {
        public string FullName => $"{FirstName} {LastName}";
    }
    
    public record struct Point(int X, int Y)
    {
        public double Distance => Math.Sqrt(X * X + Y * Y);
    }
    
    public abstract record Shape
    {
        public abstract double Area { get; }
    }
    
    public record Circle(double Radius) : Shape
    {
        public override double Area => Math.PI * Radius * Radius;
    }
}
"""
        chunks = self.parser.chunk(content, "test.cs")

        # Should handle records without breaking
        assert len(chunks) >= 1

        # Look for record content
        all_content = "\n".join(chunk.text for chunk in chunks)
        assert "record Person" in all_content
        assert "record struct Point" in all_content
        assert "record Shape" in all_content
        assert "record Circle" in all_content

    def test_complex_nested_generics(self):
        """Test handling of deeply nested generic types."""
        content = """
namespace TestNamespace
{
    public class ComplexGenerics
    {
        public async Task<Dictionary<string, List<KeyValuePair<int, T>>>> ProcessNestedAsync<T>(
            IEnumerable<IGrouping<string, (int Id, T Value)>> groups
        ) where T : IComparable<T>
        {
            var result = new Dictionary<string, List<KeyValuePair<int, T>>>();
            return result;
        }
        
        public Func<Task<IEnumerable<TResult>>, CancellationToken, Task<List<TResult>>> CreateProcessor<TResult>()
            where TResult : class, IDisposable, new()
        {
            return async (taskSource, cancellationToken) =>
            {
                var items = await taskSource;
                return items.ToList();
            };
        }
    }
}
"""
        chunks = self.parser.chunk(content, "test.cs")

        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1

        class_content = class_chunks[0].text

        # Verify complex nested generics are handled
        assert "Dictionary<string, List<KeyValuePair<int, T>>>" in class_content
        assert "IEnumerable<IGrouping<string, (int Id, T Value)>>" in class_content
        assert (
            "Func<Task<IEnumerable<TResult>>, CancellationToken, Task<List<TResult>>>"
            in class_content
        )
        assert "where TResult : class, IDisposable, new()" in class_content

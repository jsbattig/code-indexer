"""
Tests for C++ semantic parser.
Following TDD approach - writing comprehensive tests to ensure complete coverage
of C++ language constructs including ERROR node handling.
"""

import pytest
from textwrap import dedent

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestCppSemanticParser:
    """Test C++ semantic parser using tree-sitter."""

    @pytest.fixture
    def chunker(self):
        """Create a semantic chunker with semantic chunking enabled."""
        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return SemanticChunker(config)

    @pytest.fixture
    def parser(self):
        """Create a C++ parser directly."""
        from code_indexer.indexing.cpp_parser import CppSemanticParser

        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        return CppSemanticParser(config)

    def test_basic_class_declaration(self, parser):
        """Test parsing basic C++ class definitions."""
        content = dedent(
            """
            class Rectangle {
            private:
                double width;
                double height;
                
            public:
                Rectangle(double w, double h) : width(w), height(h) {}
                
                double getArea() const {
                    return width * height;
                }
                
                void setDimensions(double w, double h) {
                    width = w;
                    height = h;
                }
                
                ~Rectangle() {}
            };

            class Circle : public Shape {
            private:
                double radius;
                
            public:
                explicit Circle(double r) : radius(r) {}
                
                double getArea() const override {
                    return 3.14159 * radius * radius;
                }
            };
        """
        ).strip()

        chunks = parser.chunk(content, "shapes.cpp")

        # Should find classes and their methods
        assert len(chunks) >= 2

        # Check class chunks
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 2

        class_names = {c.semantic_name for c in class_chunks}
        assert "Rectangle" in class_names
        assert "Circle" in class_names

        # Check Rectangle class
        rect_class = next(c for c in class_chunks if c.semantic_name == "Rectangle")
        assert rect_class.semantic_path == "Rectangle"
        assert "class Rectangle" in rect_class.semantic_signature

        # Check Circle class with inheritance
        circle_class = next(c for c in class_chunks if c.semantic_name == "Circle")
        assert circle_class.semantic_path == "Circle"
        assert "class Circle" in circle_class.semantic_signature

        # Check inheritance features
        if circle_class.semantic_context.get("inheritance"):
            inheritance = circle_class.semantic_context["inheritance"]
            assert "Shape" in str(inheritance)

    def test_namespace_declarations(self, parser):
        """Test parsing C++ namespace declarations."""
        content = dedent(
            """
            namespace Graphics {
                class Point {
                public:
                    int x, y;
                    Point(int x = 0, int y = 0) : x(x), y(y) {}
                };
                
                namespace Utils {
                    double distance(const Point& p1, const Point& p2) {
                        int dx = p1.x - p2.x;
                        int dy = p1.y - p2.y;
                        return sqrt(dx*dx + dy*dy);
                    }
                }
            }

            namespace Math {
                const double PI = 3.14159;
                
                template<typename T>
                T max(T a, T b) {
                    return (a > b) ? a : b;
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "namespaces.cpp")

        # Should find namespaces, classes, and functions
        namespace_chunks = [c for c in chunks if c.semantic_type == "namespace"]
        assert len(namespace_chunks) >= 2

        namespace_names = {c.semantic_name for c in namespace_chunks}
        assert "Graphics" in namespace_names
        assert "Math" in namespace_names

        # Check nested namespace
        if "Utils" in namespace_names:
            utils_ns = next(c for c in namespace_chunks if c.semantic_name == "Utils")
            assert "Graphics.Utils" in utils_ns.semantic_path

    def test_template_declarations(self, parser):
        """Test parsing C++ template declarations."""
        content = dedent(
            """
            template<typename T>
            class Vector {
            private:
                T* data;
                size_t size_;
                size_t capacity_;
                
            public:
                Vector() : data(nullptr), size_(0), capacity_(0) {}
                
                template<typename U>
                Vector(const Vector<U>& other) {
                    // Copy constructor template
                }
                
                T& operator[](size_t index) {
                    return data[index];
                }
                
                template<typename... Args>
                void emplace_back(Args&&... args) {
                    // Variadic template method
                }
            };

            template<typename T, int N>
            class Array {
            private:
                T elements[N];
                
            public:
                constexpr size_t size() const { return N; }
                T& at(size_t index) { return elements[index]; }
            };

            // Template specialization
            template<>
            class Vector<bool> {
                // Specialized implementation for bool
            };

            // Function template
            template<typename T>
            T add(T a, T b) {
                return a + b;
            }
        """
        ).strip()

        chunks = parser.chunk(content, "templates.cpp")

        # Should find template classes and functions
        template_chunks = [c for c in chunks if "template" in c.semantic_type]
        class_chunks = [c for c in chunks if c.semantic_type == "class"]

        assert len(chunks) >= 3

        # Check template features
        template_names = {c.semantic_name for c in template_chunks if c.semantic_name}
        class_names = {c.semantic_name for c in class_chunks}

        assert "Vector" in template_names or "Vector" in class_names
        assert "Array" in template_names or "Array" in class_names

    def test_inheritance_and_access_specifiers(self, parser):
        """Test parsing C++ inheritance and access specifiers."""
        content = dedent(
            """
            class Base {
            protected:
                int protected_member;
                
            public:
                virtual void virtual_method() = 0;
                virtual ~Base() = default;
            };

            class Derived : public Base {
            private:
                int private_member;
                
            protected:
                void protected_method() {
                    protected_member = 42;
                }
                
            public:
                void virtual_method() override {
                    // Implementation
                }
                
                static void static_method() {
                    // Static method
                }
            };

            class MultipleInheritance : public Base, private Another {
            public:
                void combined_functionality() {
                    // Uses both base classes
                }
            };
        """
        ).strip()

        chunks = parser.chunk(content, "inheritance.cpp")

        # Should find classes with proper inheritance information
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 3

        class_names = {c.semantic_name for c in class_chunks}
        assert "Base" in class_names
        assert "Derived" in class_names
        assert "MultipleInheritance" in class_names

        # Check inheritance context
        derived_class = next(c for c in class_chunks if c.semantic_name == "Derived")
        if derived_class.semantic_context.get("inheritance"):
            inheritance = derived_class.semantic_context["inheritance"]
            assert "Base" in str(inheritance)

    def test_operator_overloading(self, parser):
        """Test parsing C++ operator overloading."""
        content = dedent(
            """
            class Complex {
            private:
                double real, imag;
                
            public:
                Complex(double r = 0, double i = 0) : real(r), imag(i) {}
                
                // Arithmetic operators
                Complex operator+(const Complex& other) const {
                    return Complex(real + other.real, imag + other.imag);
                }
                
                Complex operator-(const Complex& other) const {
                    return Complex(real - other.real, imag - other.imag);
                }
                
                // Assignment operators
                Complex& operator+=(const Complex& other) {
                    real += other.real;
                    imag += other.imag;
                    return *this;
                }
                
                // Comparison operators
                bool operator==(const Complex& other) const {
                    return (real == other.real) && (imag == other.imag);
                }
                
                // Stream operators
                friend std::ostream& operator<<(std::ostream& os, const Complex& c) {
                    os << c.real << " + " << c.imag << "i";
                    return os;
                }
                
                // Index operator
                double& operator[](int index) {
                    return (index == 0) ? real : imag;
                }
                
                // Function call operator
                double operator()() const {
                    return sqrt(real*real + imag*imag);
                }
            };
        """
        ).strip()

        chunks = parser.chunk(content, "operators.cpp")

        # Should find class and operator methods
        operator_chunks = [c for c in chunks if c.semantic_type == "operator"]
        method_chunks = [c for c in chunks if c.semantic_type == "method"]

        # Operators might be categorized as methods or operators
        assert len(chunks) >= 3

        # Check that operator names are captured
        all_chunks = operator_chunks + method_chunks
        operator_names = {
            c.semantic_name for c in all_chunks if "operator" in str(c.semantic_name)
        }

        # Should find some operators
        assert len(operator_names) >= 2

    def test_struct_with_methods(self, parser):
        """Test parsing C++ structs with methods (differ from C structs)."""
        content = dedent(
            """
            struct Point {
                double x, y;
                
                Point() : x(0), y(0) {}
                Point(double x, double y) : x(x), y(y) {}
                
                double distance(const Point& other) const {
                    double dx = x - other.x;
                    double dy = y - other.y;
                    return sqrt(dx*dx + dy*dy);
                }
                
                Point operator+(const Point& other) const {
                    return Point(x + other.x, y + other.y);
                }
                
                bool operator<(const Point& other) const {
                    return (x < other.x) || (x == other.x && y < other.y);
                }
            };

            struct Config {
                std::string name;
                int value;
                bool enabled = true;
                
                void validate() {
                    if (value < 0) {
                        throw std::invalid_argument("Value cannot be negative");
                    }
                }
            };
        """
        ).strip()

        chunks = parser.chunk(content, "cpp_structs.cpp")

        # Should find structs and their methods
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        assert len(struct_chunks) >= 2

        struct_names = {c.semantic_name for c in struct_chunks}
        assert "Point" in struct_names
        assert "Config" in struct_names

        # Structs should have methods/constructors
        method_chunks = [
            c
            for c in chunks
            if c.semantic_type in ["method", "constructor", "operator"]
        ]
        assert len(method_chunks) >= 2

    def test_enum_class_declarations(self, parser):
        """Test parsing C++ enum class declarations."""
        content = dedent(
            """
            enum Color {
                RED,
                GREEN,
                BLUE
            };

            enum class Status : int {
                PENDING = 0,
                PROCESSING = 1,
                COMPLETED = 2,
                FAILED = -1
            };

            enum class Priority : unsigned char {
                LOW,
                MEDIUM,
                HIGH,
                CRITICAL
            };

            void process_status(Status s) {
                switch (s) {
                    case Status::PENDING:
                        // Handle pending
                        break;
                    case Status::PROCESSING:
                        // Handle processing
                        break;
                    default:
                        // Handle other cases
                        break;
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "enums.cpp")

        # Should find both regular enums and scoped enums
        enum_chunks = [c for c in chunks if c.semantic_type in ["enum", "enum_class"]]
        assert len(enum_chunks) >= 2

        enum_names = {c.semantic_name for c in enum_chunks}
        assert "Color" in enum_names or "Status" in enum_names

        # Check for scoped enum features
        scoped_enums = [c for c in enum_chunks if c.semantic_type == "enum_class"]
        if scoped_enums:
            scoped_enum = scoped_enums[0]
            assert scoped_enum.semantic_context.get("is_scoped")

    def test_constructor_destructor_patterns(self, parser):
        """Test parsing C++ constructors and destructors."""
        content = dedent(
            """
            class Resource {
            private:
                int* data;
                size_t size;
                
            public:
                // Default constructor
                Resource() : data(nullptr), size(0) {}
                
                // Parameterized constructor
                Resource(size_t n) : data(new int[n]), size(n) {
                    std::fill(data, data + size, 0);
                }
                
                // Copy constructor
                Resource(const Resource& other) : data(new int[other.size]), size(other.size) {
                    std::copy(other.data, other.data + size, data);
                }
                
                // Move constructor
                Resource(Resource&& other) noexcept : data(other.data), size(other.size) {
                    other.data = nullptr;
                    other.size = 0;
                }
                
                // Copy assignment operator
                Resource& operator=(const Resource& other) {
                    if (this != &other) {
                        delete[] data;
                        data = new int[other.size];
                        size = other.size;
                        std::copy(other.data, other.data + size, data);
                    }
                    return *this;
                }
                
                // Move assignment operator
                Resource& operator=(Resource&& other) noexcept {
                    if (this != &other) {
                        delete[] data;
                        data = other.data;
                        size = other.size;
                        other.data = nullptr;
                        other.size = 0;
                    }
                    return *this;
                }
                
                // Destructor
                ~Resource() {
                    delete[] data;
                }
            };
        """
        ).strip()

        chunks = parser.chunk(content, "raii.cpp")

        # Should find class and special member functions
        constructor_chunks = [c for c in chunks if c.semantic_type == "constructor"]
        destructor_chunks = [c for c in chunks if c.semantic_type == "destructor"]

        assert len(chunks) >= 3

        # Should identify constructors and destructors
        if constructor_chunks:
            assert len(constructor_chunks) >= 1
        if destructor_chunks:
            assert len(destructor_chunks) >= 1

    def test_error_node_handling_template_errors(self, parser):
        """Test ERROR node handling for template syntax errors."""
        content = dedent(
            """
            template<typename T>
            class ValidTemplate {
            public:
                T value;
                T getValue() const { return value; }
            };

            template<typename T, typename U
            // Missing closing angle bracket
            class BrokenTemplate {
            public:
                T first;
                U second;
            };

            template<typename T>
            T valid_function(T param) {
                return param;
            }

            // Another valid construct after error
            class SimpleClass {
            public:
                void method() {}
            };
        """
        ).strip()

        chunks = parser.chunk(content, "template_errors.cpp")

        # Should extract constructs despite template syntax errors
        assert len(chunks) >= 2

        # Should find valid constructs
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1

        class_names = {c.semantic_name for c in class_chunks}
        assert "ValidTemplate" in class_names or "SimpleClass" in class_names

    def test_error_node_handling_namespace_errors(self, parser):
        """Test ERROR node handling for namespace syntax errors."""
        content = dedent(
            """
            namespace ValidNamespace {
                class ValidClass {
                public:
                    void method() {}
                };
            }

            namespace BrokenNamespace {
                class IncompleteClass {
                // Missing closing brace and namespace brace

            namespace AnotherValid {
                void function() {
                    // Valid function
                }
            }
        """
        ).strip()

        chunks = parser.chunk(content, "namespace_errors.cpp")

        # Should extract constructs despite namespace syntax errors
        assert len(chunks) >= 2

        # Should find valid namespaces and classes
        namespace_chunks = [c for c in chunks if c.semantic_type == "namespace"]
        class_chunks = [c for c in chunks if c.semantic_type == "class"]

        assert len(namespace_chunks) >= 1 or len(class_chunks) >= 1

    def test_error_node_handling_inheritance_errors(self, parser):
        """Test ERROR node handling for inheritance syntax errors."""
        content = dedent(
            """
            class ValidBase {
            public:
                virtual void method() = 0;
            };

            class BrokenDerived : public ValidBase, private
            // Incomplete inheritance specification
            {
            public:
                void method() override {}
            };

            class AnotherValid : public ValidBase {
            public:
                void method() override {
                    // Valid implementation
                }
            };
        """
        ).strip()

        chunks = parser.chunk(content, "inheritance_errors.cpp")

        # Should extract classes despite inheritance syntax errors
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 2

        class_names = {c.semantic_name for c in class_chunks}
        assert "ValidBase" in class_names or "AnotherValid" in class_names

    def test_malformed_cpp_code_handling(self, parser):
        """Test handling of completely malformed C++ code."""
        malformed_content = """
            This is not valid C++ code!
            class??? broken {{{
            template<>>> invalid
            namespace:::: wrong
            operator++--() nonsense
        """

        # Should not crash and should return minimal chunks
        chunks = parser.chunk(malformed_content, "malformed.cpp")

        # Parser should handle gracefully
        assert isinstance(chunks, list)

    def test_chunker_integration(self, chunker):
        """Test integration with SemanticChunker for C++ files."""
        content = dedent(
            """
            #include <iostream>
            #include <vector>

            namespace Math {
                template<typename T>
                class Calculator {
                private:
                    std::vector<T> history;
                    
                public:
                    T add(T a, T b) {
                        T result = a + b;
                        history.push_back(result);
                        return result;
                    }
                    
                    T multiply(T a, T b) {
                        T result = a * b;
                        history.push_back(result);
                        return result;
                    }
                    
                    void printHistory() const {
                        for (const auto& value : history) {
                            std::cout << value << " ";
                        }
                        std::cout << std::endl;
                    }
                };
            }

            int main() {
                Math::Calculator<int> calc;
                int sum = calc.add(5, 3);
                int product = calc.multiply(4, 7);
                calc.printHistory();
                return 0;
            }
        """
        ).strip()

        chunks = chunker.chunk_content(content, "calculator.cpp")

        # Should get semantic chunks from C++ parser
        assert len(chunks) >= 3

        # Verify chunks have semantic metadata
        for chunk in chunks:
            assert chunk.get("semantic_chunking") is True
            assert "semantic_type" in chunk
            assert "semantic_name" in chunk
            assert "semantic_path" in chunk

    def test_modern_cpp_features(self, parser):
        """Test parsing modern C++ features (C++11 and later)."""
        content = dedent(
            """
            #include <memory>
            #include <functional>

            class ModernClass {
            private:
                std::unique_ptr<int> ptr;
                
            public:
                // Delegating constructor
                ModernClass() : ModernClass(42) {}
                ModernClass(int value) : ptr(std::make_unique<int>(value)) {}
                
                // Range-based for loop
                void processVector(const std::vector<int>& vec) {
                    for (auto&& item : vec) {
                        std::cout << item << " ";
                    }
                }
                
                // Lambda expressions
                auto getLambda() {
                    return [this](int x) -> int {
                        return *ptr + x;
                    };
                }
                
                // Auto return type deduction
                auto getValue() const {
                    return *ptr;
                }
                
                // Variadic templates
                template<typename... Args>
                void print(Args&&... args) {
                    ((std::cout << args << " "), ...);
                }
            };

            // Alias templates
            template<typename T>
            using Vector = std::vector<T>;

            // Variable templates (C++14)
            template<typename T>
            constexpr T pi = T(3.1415926535897932385);

            // Concepts (C++20) - might not parse perfectly but shouldn't crash
            template<typename T>
            concept Addable = requires(T a, T b) {
                a + b;
            };
        """
        ).strip()

        chunks = parser.chunk(content, "modern.cpp")

        # Should handle modern C++ features without crashing
        assert len(chunks) >= 2

        # Should find the main class and some methods
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) >= 1

        class_names = {c.semantic_name for c in class_chunks}
        assert "ModernClass" in class_names

    def test_regex_fallback_functionality(self, parser):
        """Test regex fallback for C++ when tree-sitter fails."""
        # Test the regex fallback method directly
        error_text = """
            namespace TestNamespace {
                class TestClass {
                public:
                    void method();
                };
                
                template<typename T>
                class TemplateClass {
                    T member;
                };
            }
            
            enum class Status { OK, ERROR };
            
            void free_function() {}
        """

        constructs = parser._extract_constructs_from_error_text(error_text, 1, [])

        # Should find constructs through regex
        assert len(constructs) >= 3

        # Check that different construct types were found
        construct_types = {c["type"] for c in constructs}
        expected_types = {"namespace", "class", "enum_class", "method", "function"}
        assert len(construct_types.intersection(expected_types)) >= 2

    def test_using_declarations_and_directives(self, parser):
        """Test parsing C++ using declarations and directives."""
        content = dedent(
            """
            #include <iostream>
            #include <vector>

            using namespace std;
            using std::vector;
            using MyInt = int;
            using FuncPtr = void(*)(int);

            namespace MyNamespace {
                using Base::method;  // Using declaration
                
                class Derived : public Base {
                public:
                    using Base::Base;  // Inheriting constructors
                    void newMethod() {}
                };
            }

            int main() {
                vector<int> vec;
                MyInt value = 42;
                cout << "Hello World" << endl;
                return 0;
            }
        """
        ).strip()

        chunks = parser.chunk(content, "using.cpp")

        # Should find using statements, namespace, class, and function
        [c for c in chunks if c.semantic_type == "using"]
        [c for c in chunks if c.semantic_type == "namespace"]
        function_chunks = [c for c in chunks if c.semantic_type == "function"]

        assert len(chunks) >= 3

        # Should find main function at minimum
        function_names = {c.semantic_name for c in function_chunks}
        assert "main" in function_names

    def test_friend_declarations(self, parser):
        """Test parsing C++ friend declarations."""
        content = dedent(
            """
            class Matrix;  // Forward declaration

            class Vector {
            private:
                double x, y, z;
                
            public:
                Vector(double x = 0, double y = 0, double z = 0) : x(x), y(y), z(z) {}
                
                // Friend function
                friend double dot(const Vector& a, const Vector& b);
                
                // Friend class
                friend class Matrix;
                
                // Friend operator
                friend std::ostream& operator<<(std::ostream& os, const Vector& v) {
                    os << "(" << v.x << ", " << v.y << ", " << v.z << ")";
                    return os;
                }
            };

            double dot(const Vector& a, const Vector& b) {
                return a.x * b.x + a.y * b.y + a.z * b.z;
            }

            class Matrix {
            public:
                void processVector(Vector& v) {
                    // Can access private members due to friendship
                    v.x *= 2;
                    v.y *= 2;
                    v.z *= 2;
                }
            };
        """
        ).strip()

        chunks = parser.chunk(content, "friends.cpp")

        # Should find classes and functions
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        function_chunks = [c for c in chunks if c.semantic_type == "function"]

        assert len(class_chunks) >= 2
        assert len(function_chunks) >= 1

        class_names = {c.semantic_name for c in class_chunks}
        assert "Vector" in class_names
        assert "Matrix" in class_names

    def test_data_preservation_no_loss(self, parser):
        """Test that chunking preserves all content without data loss."""
        content = dedent(
            """
            #include <iostream>
            #include <vector>
            #include <memory>
            #include <algorithm>

            namespace DataStructures {
                template<typename T>
                class SmartContainer {
                private:
                    std::vector<std::unique_ptr<T>> data;
                    size_t capacity_;
                    
                public:
                    explicit SmartContainer(size_t initial_capacity = 10) 
                        : capacity_(initial_capacity) {
                        data.reserve(capacity_);
                    }
                    
                    SmartContainer(const SmartContainer&) = delete;
                    SmartContainer& operator=(const SmartContainer&) = delete;
                    
                    SmartContainer(SmartContainer&& other) noexcept 
                        : data(std::move(other.data)), capacity_(other.capacity_) {
                        other.capacity_ = 0;
                    }
                    
                    template<typename... Args>
                    void emplace(Args&&... args) {
                        data.emplace_back(std::make_unique<T>(std::forward<Args>(args)...));
                    }
                    
                    void sort() {
                        std::sort(data.begin(), data.end(), 
                                [](const auto& a, const auto& b) {
                                    return *a < *b;
                                });
                    }
                    
                    size_t size() const noexcept { return data.size(); }
                    bool empty() const noexcept { return data.empty(); }
                    
                    ~SmartContainer() = default;
                };
            }

            int main() {
                DataStructures::SmartContainer<int> container(20);
                
                for (int i = 0; i < 10; ++i) {
                    container.emplace(i * i);
                }
                
                container.sort();
                
                std::cout << "Container size: " << container.size() << std::endl;
                return 0;
            }
        """
        ).strip()

        chunks = parser.chunk(content, "data_preservation.cpp")

        # Verify no data loss by checking that all content is captured
        all_chunk_content = "\n".join(chunk.text for chunk in chunks)

        # Check that essential elements are preserved
        assert "#include <iostream>" in all_chunk_content
        assert "namespace DataStructures" in all_chunk_content
        assert "template<typename T>" in all_chunk_content
        assert "class SmartContainer" in all_chunk_content
        assert "emplace" in all_chunk_content
        assert "main" in all_chunk_content

        # Check that we have reasonable chunk coverage
        assert len(chunks) >= 3  # Should have multiple semantic chunks

        # Verify all chunks have proper metadata
        for chunk in chunks:
            assert chunk.semantic_chunking is True
            assert chunk.semantic_type is not None
            assert chunk.semantic_name is not None
            assert chunk.file_path == "data_preservation.cpp"
            assert chunk.line_start > 0
            assert chunk.line_end >= chunk.line_start

"""
Tests for Go semantic parser.
Following TDD approach - writing tests first.
"""

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestGoSemanticParser:
    """Test the Go semantic parser."""

    def setup_method(self):
        """Set up test configuration."""
        self.config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )

    def test_go_function_chunking(self):
        """Test parsing Go functions."""
        from code_indexer.indexing.go_parser import GoSemanticParser

        parser = GoSemanticParser(self.config)
        content = """
package main

import "fmt"

func main() {
    fmt.Println("Hello, World!")
}

func add(a int, b int) int {
    return a + b
}

func divide(a, b float64) (float64, error) {
    if b == 0 {
        return 0, fmt.Errorf("cannot divide by zero")
    }
    return a / b, nil
}
"""

        chunks = parser.chunk(content, "main.go")

        assert len(chunks) == 3  # 3 functions

        # Check function chunks
        func_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(func_chunks) == 3
        func_names = [c.semantic_name for c in func_chunks]
        assert "main" in func_names
        assert "add" in func_names
        assert "divide" in func_names

        # Check function with multiple return values
        divide_chunk = next(c for c in func_chunks if c.semantic_name == "divide")
        assert "multiple_returns" in divide_chunk.semantic_language_features

    def test_go_struct_chunking(self):
        """Test parsing Go structs."""
        from code_indexer.indexing.go_parser import GoSemanticParser

        parser = GoSemanticParser(self.config)
        content = """
package models

type User struct {
    ID       int    `json:"id"`
    Name     string `json:"name"`
    Email    string `json:"email"`
    IsActive bool   `json:"is_active"`
}

func (u *User) GetFullInfo() string {
    return fmt.Sprintf("User: %s (%s)", u.Name, u.Email)
}

func (u User) IsValid() bool {
    return u.Name != "" && u.Email != ""
}

func NewUser(name, email string) *User {
    return &User{
        Name:     name,
        Email:    email,
        IsActive: true,
    }
}
"""

        chunks = parser.chunk(content, "user.go")

        # Should have struct + 3 functions (2 methods + 1 constructor)
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        assert len(struct_chunks) == 1
        assert struct_chunks[0].semantic_name == "User"

        func_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(func_chunks) == 3
        func_names = [c.semantic_name for c in func_chunks]
        assert "GetFullInfo" in func_names
        assert "IsValid" in func_names
        assert "NewUser" in func_names

        # Check method receivers
        method_chunks = [c for c in func_chunks if c.semantic_context.get("receiver")]
        assert len(method_chunks) == 2
        receiver_types = [c.semantic_context["receiver"] for c in method_chunks]
        assert "*User" in receiver_types
        assert "User" in receiver_types

    def test_go_interface_chunking(self):
        """Test parsing Go interfaces."""
        from code_indexer.indexing.go_parser import GoSemanticParser

        parser = GoSemanticParser(self.config)
        content = """
package interfaces

type Reader interface {
    Read([]byte) (int, error)
}

type Writer interface {
    Write([]byte) (int, error)
}

type ReadWriter interface {
    Reader
    Writer
}

type Closer interface {
    Close() error
}

type ReadWriteCloser interface {
    ReadWriter
    Closer
}
"""

        chunks = parser.chunk(content, "interfaces.go")

        interface_chunks = [c for c in chunks if c.semantic_type == "interface"]
        assert len(interface_chunks) == 5
        interface_names = [c.semantic_name for c in interface_chunks]
        assert "Reader" in interface_names
        assert "Writer" in interface_names
        assert "ReadWriter" in interface_names
        assert "Closer" in interface_names
        assert "ReadWriteCloser" in interface_names

        # Check embedded interfaces
        embedded_chunks = [
            c for c in interface_chunks if c.semantic_context.get("embedded_interfaces")
        ]
        assert len(embedded_chunks) >= 2  # ReadWriter and ReadWriteCloser

    def test_go_method_chunking(self):
        """Test parsing Go methods with different receivers."""
        from code_indexer.indexing.go_parser import GoSemanticParser

        parser = GoSemanticParser(self.config)
        content = """
package calculator

type Calculator struct {
    value float64
}

func (c *Calculator) Add(n float64) {
    c.value += n
}

func (c Calculator) Get() float64 {
    return c.value
}

func (c *Calculator) Reset() {
    c.value = 0
}

type StringCalculator string

func (sc StringCalculator) Length() int {
    return len(string(sc))
}
"""

        chunks = parser.chunk(content, "calculator.go")

        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        assert len(struct_chunks) == 1

        func_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(func_chunks) == 4

        # Check pointer and value receivers
        pointer_receivers = [
            c
            for c in func_chunks
            if c.semantic_context.get("receiver", "").startswith("*")
        ]
        value_receivers = [
            c
            for c in func_chunks
            if c.semantic_context.get("receiver", "")
            and not c.semantic_context.get("receiver", "").startswith("*")
        ]

        assert len(pointer_receivers) == 2  # Add, Reset
        assert len(value_receivers) == 2  # Get, Length

    def test_go_type_alias_chunking(self):
        """Test parsing Go type aliases and type definitions."""
        from code_indexer.indexing.go_parser import GoSemanticParser

        parser = GoSemanticParser(self.config)
        content = """
package types

type UserID int
type Username = string
type EventHandler func(event string) error

type Status int

const (
    StatusPending Status = iota
    StatusActive
    StatusInactive
)

func (s Status) String() string {
    switch s {
    case StatusPending:
        return "pending"
    case StatusActive:
        return "active"
    case StatusInactive:
        return "inactive"
    default:
        return "unknown"
    }
}
"""

        chunks = parser.chunk(content, "types.go")

        type_chunks = [c for c in chunks if c.semantic_type == "type"]
        assert len(type_chunks) >= 3
        type_names = [c.semantic_name for c in type_chunks]
        assert "UserID" in type_names
        assert "Username" in type_names
        assert "EventHandler" in type_names
        assert "Status" in type_names

        # Check function type
        func_type_chunks = [
            c for c in type_chunks if "function_type" in c.semantic_language_features
        ]
        assert len(func_type_chunks) >= 1

    def test_go_package_and_imports(self):
        """Test handling Go package declarations and imports."""
        from code_indexer.indexing.go_parser import GoSemanticParser

        parser = GoSemanticParser(self.config)
        content = """
package main

import (
    "fmt"
    "log"
    "net/http"
    
    "github.com/gorilla/mux"
    custom "github.com/custom/package"
)

func main() {
    router := mux.NewRouter()
    log.Fatal(http.ListenAndServe(":8080", router))
}
"""

        chunks = parser.chunk(content, "main.go")

        # Check package information is captured
        func_chunks = [c for c in chunks if c.semantic_type == "function"]
        assert len(func_chunks) >= 1
        main_chunk = next(c for c in func_chunks if c.semantic_name == "main")
        assert main_chunk.semantic_context.get("package") == "main"

    def test_go_generic_functions(self):
        """Test parsing Go generic functions (Go 1.18+)."""
        from code_indexer.indexing.go_parser import GoSemanticParser

        parser = GoSemanticParser(self.config)
        content = """
package generics

func Max[T comparable](a, b T) T {
    if a > b {
        return a
    }
    return b
}

func Map[T, U any](slice []T, fn func(T) U) []U {
    result := make([]U, len(slice))
    for i, v := range slice {
        result[i] = fn(v)
    }
    return result
}

type Stack[T any] struct {
    items []T
}

func (s *Stack[T]) Push(item T) {
    s.items = append(s.items, item)
}

func (s *Stack[T]) Pop() (T, bool) {
    if len(s.items) == 0 {
        var zero T
        return zero, false
    }
    item := s.items[len(s.items)-1]
    s.items = s.items[:len(s.items)-1]
    return item, true
}
"""

        chunks = parser.chunk(content, "generics.go")

        # Check generic functions
        func_chunks = [c for c in chunks if c.semantic_type == "function"]
        generic_funcs = [
            c for c in func_chunks if "generic" in c.semantic_language_features
        ]
        assert len(generic_funcs) >= 2

        # Check generic struct
        struct_chunks = [c for c in chunks if c.semantic_type == "struct"]
        generic_structs = [
            c for c in struct_chunks if "generic" in c.semantic_language_features
        ]
        assert len(generic_structs) >= 1

    def test_go_constants_and_variables(self):
        """Test parsing Go constants and variables."""
        from code_indexer.indexing.go_parser import GoSemanticParser

        parser = GoSemanticParser(self.config)
        content = """
package config

const (
    MaxRetries = 3
    DefaultTimeout = 30
)

var (
    GlobalCounter int
    ConfigPath = "/etc/app/config.yaml"
)

const APIVersion = "v1"

var Logger = log.New(os.Stdout, "INFO: ", log.Ldate|log.Ltime)
"""

        chunks = parser.chunk(content, "config.go")

        const_chunks = [c for c in chunks if c.semantic_type == "const"]
        var_chunks = [c for c in chunks if c.semantic_type == "var"]

        # Should find constant and variable declarations
        assert len(const_chunks) >= 1
        assert len(var_chunks) >= 1


class TestGoSemanticParserIntegration:
    """Test Go parser integration with SemanticChunker."""

    def setup_method(self):
        """Set up test configuration."""
        self.config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )

    def test_go_integration_with_semantic_chunker(self):
        """Test Go parser works with SemanticChunker."""
        chunker = SemanticChunker(self.config)

        content = """
package main

import "fmt"

func main() {
    fmt.Println("Hello, Go!")
}

type Person struct {
    Name string
    Age  int
}

func (p Person) Greet() string {
    return fmt.Sprintf("Hello, I'm %s", p.Name)
}
"""

        chunks = chunker.chunk_content(content, "hello.go")

        assert len(chunks) >= 2
        semantic_chunks = [c for c in chunks if c.get("semantic_chunking")]
        assert len(semantic_chunks) >= 2

        # Should have function and struct
        types = [c.get("semantic_type") for c in semantic_chunks]
        assert "function" in types
        assert "struct" in types

    def test_go_fallback_integration(self):
        """Test Go parser fallback to text chunking."""
        chunker = SemanticChunker(self.config)

        # Malformed Go that should fail parsing
        content = """
package main

this is not valid Go syntax at all
func broken syntax here
"""

        chunks = chunker.chunk_content(content, "broken.go")

        # Should fall back to text chunking
        assert len(chunks) > 0
        assert chunks[0]["semantic_chunking"] is False

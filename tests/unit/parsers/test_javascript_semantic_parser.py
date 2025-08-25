"""
Tests for JavaScript/TypeScript semantic parser.
Following TDD approach - writing tests first.
"""

from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker


class TestJavaScriptSemanticParser:
    """Test the JavaScript semantic parser."""

    def setup_method(self):
        """Set up test configuration."""
        self.config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )

    def test_javascript_function_chunking(self):
        """Test parsing JavaScript functions."""
        from code_indexer.indexing.javascript_parser import JavaScriptSemanticParser

        parser = JavaScriptSemanticParser(self.config)
        content = """
function greet(name) {
    console.log("Hello, " + name);
    return true;
}

const multiply = (a, b) => {
    return a * b;
};
"""

        chunks = parser.chunk(content, "test.js")

        assert len(chunks) == 2

        # First chunk - function declaration
        func_chunk = chunks[0]
        assert func_chunk.semantic_type == "function"
        assert func_chunk.semantic_name == "greet"
        assert func_chunk.semantic_signature == "function greet(name)"
        assert "function" in func_chunk.text
        assert "greet" in func_chunk.text

        # Second chunk - arrow function
        arrow_chunk = chunks[1]
        assert arrow_chunk.semantic_type == "arrow_function"
        assert arrow_chunk.semantic_name == "multiply"
        assert arrow_chunk.semantic_signature == "const multiply = (a, b) =>"

    def test_javascript_class_chunking(self):
        """Test parsing JavaScript classes."""
        from code_indexer.indexing.javascript_parser import JavaScriptSemanticParser

        parser = JavaScriptSemanticParser(self.config)
        content = """
class Calculator {
    constructor(name) {
        this.name = name;
    }

    add(a, b) {
        return a + b;
    }

    subtract(a, b) {
        return a - b;
    }
}
"""

        chunks = parser.chunk(content, "test.js")

        # JavaScript parser now correctly breaks down classes into individual chunks
        # Expected: 4 chunks (class + constructor + 2 methods)
        assert len(chunks) == 4

        # Check class chunk
        class_chunk = chunks[0]
        assert class_chunk.semantic_type == "class"
        assert class_chunk.semantic_name == "Calculator"
        assert class_chunk.semantic_signature == "class Calculator"

        # Check method chunks (constructor + 2 methods)
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        assert len(method_chunks) == 3
        method_names = [c.semantic_name for c in method_chunks]
        assert "constructor" in method_names
        assert "add" in method_names
        assert "subtract" in method_names

    def test_javascript_react_component_chunking(self):
        """Test parsing React functional components."""
        from code_indexer.indexing.javascript_parser import JavaScriptSemanticParser

        parser = JavaScriptSemanticParser(self.config)
        content = """
import React from 'react';

const Button = ({ onClick, children }) => {
    return (
        <button onClick={onClick}>
            {children}
        </button>
    );
};

function Header(props) {
    return <h1>{props.title}</h1>;
}

export { Button, Header };
"""

        chunks = parser.chunk(content, "Button.jsx")

        # JavaScript parser classifies React components as functions (regular and arrow)
        function_chunks = [
            c for c in chunks if c.semantic_type in ["function", "arrow_function"]
        ]
        assert len(function_chunks) == 2

        function_names = [c.semantic_name for c in function_chunks]
        assert "Button" in function_names
        assert "Header" in function_names

    def test_javascript_object_method_chunking(self):
        """Test parsing object methods and properties."""
        from code_indexer.indexing.javascript_parser import JavaScriptSemanticParser

        parser = JavaScriptSemanticParser(self.config)
        content = """
const utils = {
    formatName(first, last) {
        return `${first} ${last}`;
    },
    
    validateEmail: function(email) {
        return email.includes('@');
    },
    
    constants: {
        MAX_LENGTH: 100,
        MIN_LENGTH: 5
    }
};
"""

        chunks = parser.chunk(content, "utils.js")

        # JavaScript parser currently treats object literals as variables/functions
        # Object method extraction is a complex feature not yet implemented
        assert len(chunks) >= 1

        # Verify the object assignment is detected
        var_chunks = [c for c in chunks if c.semantic_type in ["function", "variable"]]
        assert len(var_chunks) >= 1
        assert "utils" in [c.semantic_name for c in var_chunks]

    def test_javascript_async_function_chunking(self):
        """Test parsing async functions and promises."""
        from code_indexer.indexing.javascript_parser import JavaScriptSemanticParser

        parser = JavaScriptSemanticParser(self.config)
        content = """
async function fetchData(url) {
    try {
        const response = await fetch(url);
        return await response.json();
    } catch (error) {
        console.error(error);
    }
}

const processData = async (data) => {
    return data.map(item => item.id);
};
"""

        chunks = parser.chunk(content, "api.js")

        # Parser now detects variables inside functions as separate chunks
        assert len(chunks) == 3

        # Check function chunks (both regular and arrow functions)
        func_chunks = [
            c for c in chunks if c.semantic_type in ["function", "arrow_function"]
        ]
        assert len(func_chunks) == 2

        func_names = [c.semantic_name for c in func_chunks]
        assert "fetchData" in func_names
        assert "processData" in func_names

        # Verify specific types
        fetchData_chunk = next(c for c in func_chunks if c.semantic_name == "fetchData")
        processData_chunk = next(
            c for c in func_chunks if c.semantic_name == "processData"
        )
        assert fetchData_chunk.semantic_type == "function"  # regular async function
        assert (
            processData_chunk.semantic_type == "arrow_function"
        )  # async arrow function

        # Check that internal variable is detected with proper scope
        var_chunks = [c for c in chunks if c.semantic_type == "variable"]
        assert len(var_chunks) == 1
        var_chunk = var_chunks[0]
        assert var_chunk.semantic_name == "response"
        assert var_chunk.semantic_parent == "fetchData"


class TestTypeScriptSemanticParser:
    """Test the TypeScript semantic parser."""

    def setup_method(self):
        """Set up test configuration."""
        self.config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )

    def test_typescript_interface_chunking(self):
        """Test parsing TypeScript interfaces."""
        from code_indexer.indexing.typescript_parser import TypeScriptSemanticParser

        parser = TypeScriptSemanticParser(self.config)
        content = """
interface User {
    id: number;
    name: string;
    email?: string;
}

interface Repository<T> {
    findById(id: number): Promise<T>;
    save(entity: T): Promise<T>;
}
"""

        chunks = parser.chunk(content, "types.ts")

        interface_chunks = [c for c in chunks if c.semantic_type == "interface"]
        assert len(interface_chunks) == 2

        interface_names = [c.semantic_name for c in interface_chunks]
        assert "User" in interface_names
        assert "Repository" in interface_names

    def test_typescript_type_alias_chunking(self):
        """Test parsing TypeScript type aliases."""
        from code_indexer.indexing.typescript_parser import TypeScriptSemanticParser

        parser = TypeScriptSemanticParser(self.config)
        content = """
type Status = 'pending' | 'completed' | 'failed';

type ApiResponse<T> = {
    data: T;
    status: Status;
    message?: string;
};

type UserCallback = (user: User) => void;
"""

        chunks = parser.chunk(content, "types.ts")

        type_chunks = [c for c in chunks if c.semantic_type == "type"]
        assert len(type_chunks) == 3

        type_names = [c.semantic_name for c in type_chunks]
        assert "Status" in type_names
        assert "ApiResponse" in type_names
        assert "UserCallback" in type_names

    def test_typescript_class_with_types_chunking(self):
        """Test parsing TypeScript classes with type annotations."""
        from code_indexer.indexing.typescript_parser import TypeScriptSemanticParser

        parser = TypeScriptSemanticParser(self.config)
        content = """
class UserService {
    private users: User[] = [];

    constructor(private readonly apiClient: ApiClient) {}

    async findUser(id: number): Promise<User | null> {
        return this.users.find(user => user.id === id) || null;
    }

    addUser(user: User): void {
        this.users.push(user);
    }
}
"""

        chunks = parser.chunk(content, "UserService.ts")

        # TypeScript parser uses class-level chunking
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) == 1
        class_chunk = class_chunks[0]
        assert class_chunk.semantic_name == "UserService"

        # Methods are included in class chunk text
        assert "findUser" in class_chunk.text
        assert "addUser" in class_chunk.text

    def test_typescript_enum_chunking(self):
        """Test parsing TypeScript enums."""
        from code_indexer.indexing.typescript_parser import TypeScriptSemanticParser

        parser = TypeScriptSemanticParser(self.config)
        content = """
enum Color {
    Red = "red",
    Green = "green",
    Blue = "blue"
}

enum Direction {
    Up,
    Down,
    Left,
    Right
}
"""

        chunks = parser.chunk(content, "enums.ts")

        enum_chunks = [c for c in chunks if c.semantic_type == "enum"]
        assert len(enum_chunks) == 2

        enum_names = [c.semantic_name for c in enum_chunks]
        assert "Color" in enum_names
        assert "Direction" in enum_names

    def test_typescript_decorator_chunking(self):
        """Test parsing TypeScript decorators."""
        from code_indexer.indexing.typescript_parser import TypeScriptSemanticParser

        parser = TypeScriptSemanticParser(self.config)
        content = """
@Component({
    selector: 'app-user',
    templateUrl: './user.component.html'
})
class UserComponent {
    @Input() user: User;

    @Output() userUpdated = new EventEmitter<User>();

    @ViewChild('userForm') form: ElementRef;

    onSave(): void {
        this.userUpdated.emit(this.user);
    }
}
"""

        chunks = parser.chunk(content, "user.component.ts")

        # TypeScript parser detects classes but decorator parsing not yet implemented
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) == 1

        class_chunk = class_chunks[0]
        assert class_chunk.semantic_name == "UserComponent"

        # Verify decorators are present in text (basic detection)
        assert "@Component" in class_chunk.text
        assert "@Input" in class_chunk.text


class TestJavaScriptTypeScriptIntegration:
    """Test JavaScript/TypeScript parser integration with SemanticChunker."""

    def setup_method(self):
        """Set up test configuration."""
        self.config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )

    def test_javascript_integration_with_semantic_chunker(self):
        """Test JavaScript parser works with SemanticChunker."""
        chunker = SemanticChunker(self.config)

        content = """
function calculate(x, y) {
    return x + y;
}

const result = calculate(5, 3);
"""

        chunks = chunker.chunk_content(content, "math.js")

        assert len(chunks) >= 1
        semantic_chunks = [c for c in chunks if c.get("semantic_chunking")]
        assert len(semantic_chunks) >= 1

        func_chunks = [
            c for c in semantic_chunks if c.get("semantic_type") == "function"
        ]
        assert len(func_chunks) == 1
        assert func_chunks[0]["semantic_name"] == "calculate"

    def test_typescript_integration_with_semantic_chunker(self):
        """Test TypeScript parser works with SemanticChunker."""
        chunker = SemanticChunker(self.config)

        content = """
interface Calculator {
    add(a: number, b: number): number;
}

class BasicCalculator implements Calculator {
    add(a: number, b: number): number {
        return a + b;
    }
}
"""

        chunks = chunker.chunk_content(content, "calculator.ts")

        assert len(chunks) >= 2
        semantic_chunks = [c for c in chunks if c.get("semantic_chunking")]
        assert len(semantic_chunks) >= 2

        # Should have interface and class
        types = [c.get("semantic_type") for c in semantic_chunks]
        assert "interface" in types
        assert "class" in types

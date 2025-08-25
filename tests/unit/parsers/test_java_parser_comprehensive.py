"""
Comprehensive tests for Java semantic parser.
Tests AST-based parsing, edge cases, complex constructs, and fallback behavior.
"""

from pathlib import Path
from code_indexer.config import IndexingConfig
from code_indexer.indexing.semantic_chunker import SemanticChunker
from code_indexer.indexing.java_parser import JavaSemanticParser


class TestJavaParserComprehensive:
    """Comprehensive tests for Java semantic parser with realistic code examples."""

    def setup_method(self):
        """Set up test configuration."""
        self.config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )
        self.parser = JavaSemanticParser(self.config)
        self.chunker = SemanticChunker(self.config)
        self.test_files_dir = Path(__file__).parent / "test_files"

    def test_complex_web_service_parsing(self):
        """Test parsing of complex Spring Boot microservice."""
        test_file = self.test_files_dir / "java" / "ComplexWebService.java"

        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        chunks = self.parser.chunk(content, str(test_file))

        # Should have many chunks for complex service
        assert len(chunks) > 20, f"Expected > 20 chunks, got {len(chunks)}"

        # Verify we capture all major constructs
        chunk_types = [chunk.semantic_type for chunk in chunks if chunk.semantic_type]

        assert "class" in chunk_types, "Should find class declarations"
        assert "method" in chunk_types, "Should find method declarations"
        assert "constructor" in chunk_types, "Should find constructor declarations"
        assert "enum" in chunk_types, "Should find enum declarations"
        assert "interface" in chunk_types, "Should find interface declarations"

        # Test specific constructs
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert (
            len(class_chunks) >= 5
        ), f"Should find multiple classes, got {len(class_chunks)}"

        # Find OrderMicroservice class
        main_class = next(
            (c for c in class_chunks if c.semantic_name == "OrderMicroservice"), None
        )
        assert main_class is not None, "Should find OrderMicroservice class"
        assert (
            "@RestController" in main_class.text or "RestController" in main_class.text
        )

        # Test method detection
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        assert (
            len(method_chunks) >= 10
        ), f"Should find multiple methods, got {len(method_chunks)}"

        # Test annotation handling
        annotated_chunks = [c for c in chunks if "@" in c.text]
        assert len(annotated_chunks) > 5, "Should find chunks with annotations"

    def test_generic_utilities_parsing(self):
        """Test parsing of complex generic Java utilities."""
        test_file = self.test_files_dir / "java" / "GenericUtilities.java"

        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        chunks = self.parser.chunk(content, str(test_file))

        # Should have many chunks for complex generics
        assert len(chunks) > 15, f"Expected > 15 chunks, got {len(chunks)}"

        # Test generic class detection
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        generic_classes = [c for c in class_chunks if "<" in c.text and ">" in c.text]
        assert len(generic_classes) > 0, "Should find generic classes"

        # Test nested class detection
        nested_classes = [c for c in class_chunks if c.semantic_parent is not None]
        assert (
            len(nested_classes) > 3
        ), f"Should find nested classes, got {len(nested_classes)}"

        # Test enum with methods
        enum_chunks = [c for c in chunks if c.semantic_type == "enum"]
        assert len(enum_chunks) > 0, "Should find enum declarations"

        # Test annotation detection
        annotation_chunks = [
            c
            for c in chunks
            if c.semantic_type == "annotation" or "@interface" in c.text
        ]
        assert len(annotation_chunks) > 0, "Should find custom annotations"

    def test_basic_java_constructs(self):
        """Test basic Java constructs parsing."""
        content = """
package com.example.test;

import java.util.List;
import java.util.ArrayList;

/**
 * Test class for basic constructs
 */
public class BasicTest {
    private String name;
    protected int age;
    public static final String CONSTANT = "value";
    
    public BasicTest(String name) {
        this.name = name;
    }
    
    public String getName() {
        return name;
    }
    
    public void setName(String name) {
        this.name = name;
    }
    
    public static void main(String[] args) {
        BasicTest test = new BasicTest("Test");
        System.out.println(test.getName());
    }
}
"""

        chunks = self.parser.chunk(content, "BasicTest.java")

        # Test basic structure
        assert len(chunks) >= 5, f"Expected >= 5 chunks, got {len(chunks)}"

        # Test package detection
        package_chunks = [c for c in chunks if c.semantic_type == "package"]
        if package_chunks:
            assert package_chunks[0].semantic_name == "com.example.test"

        # Test class detection
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) == 1, f"Expected 1 class, got {len(class_chunks)}"
        assert class_chunks[0].semantic_name == "BasicTest"

        # Test method detection
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        method_names = {c.semantic_name for c in method_chunks}
        expected_methods = {
            "getName",
            "setName",
            "main",
        }
        assert expected_methods.issubset(
            method_names
        ), f"Missing methods. Found: {method_names}"

        # Test constructor detection
        constructor_chunks = [c for c in chunks if c.semantic_type == "constructor"]
        assert (
            len(constructor_chunks) == 1
        ), f"Expected 1 constructor, got {len(constructor_chunks)}"
        assert constructor_chunks[0].semantic_name == "BasicTest"

    def test_inheritance_and_interfaces(self):
        """Test parsing of inheritance hierarchies and interface implementations."""
        content = """
package com.example.inheritance;

public interface Drawable {
    void draw();
    default void initialize() {
        System.out.println("Initializing drawable");
    }
}

public abstract class Shape implements Drawable {
    protected String color;
    
    public Shape(String color) {
        this.color = color;
    }
    
    public abstract double getArea();
    
    public String getColor() {
        return color;
    }
}

public class Circle extends Shape {
    private double radius;
    
    public Circle(String color, double radius) {
        super(color);
        this.radius = radius;
    }
    
    @Override
    public double getArea() {
        return Math.PI * radius * radius;
    }
    
    @Override
    public void draw() {
        System.out.println("Drawing circle");
    }
}
"""

        chunks = self.parser.chunk(content, "InheritanceTest.java")

        # Test interface detection
        interface_chunks = [c for c in chunks if c.semantic_type == "interface"]
        assert (
            len(interface_chunks) == 1
        ), f"Expected 1 interface, got {len(interface_chunks)}"
        assert interface_chunks[0].semantic_name == "Drawable"

        # Test class hierarchy
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        class_names = {c.semantic_name for c in class_chunks}
        assert "Shape" in class_names, "Should find Shape class"
        assert "Circle" in class_names, "Should find Circle class"

        # Test method detection in different contexts
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        method_names = {c.semantic_name for c in method_chunks}
        assert "draw" in method_names, "Should find draw method"
        assert "getArea" in method_names, "Should find getArea method"

    def test_annotation_processing(self):
        """Test complex annotation parsing."""
        content = """
package com.example.annotations;

import javax.persistence.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/users")
@CrossOrigin(origins = "http://localhost:3000")
public class UserController {
    
    @Autowired
    private UserService userService;
    
    @GetMapping("/{id}")
    @ResponseBody
    public ResponseEntity<User> getUser(@PathVariable Long id) {
        return ResponseEntity.ok(userService.findById(id));
    }
    
    @PostMapping
    @Transactional
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<User> createUser(@Valid @RequestBody CreateUserRequest request) {
        User user = userService.create(request);
        return ResponseEntity.ok(user);
    }
}
"""

        chunks = self.parser.chunk(content, "UserController.java")

        # Test that annotations are captured in context
        annotated_chunks = [c for c in chunks if "@" in c.text]
        assert len(annotated_chunks) > 0, "Should find chunks with annotations"

        # Test method with multiple annotations
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        create_user_method = next(
            (c for c in method_chunks if c.semantic_name == "createUser"), None
        )
        assert create_user_method is not None, "Should find createUser method"
        assert (
            "@PostMapping" in create_user_method.text
            or "PostMapping" in create_user_method.text
        )

    def test_generics_and_wildcards(self):
        """Test parsing of complex generics and wildcards."""
        content = """
package com.example.generics;

import java.util.*;

public class GenericRepository<T, ID extends Serializable> {
    private Map<ID, T> storage = new HashMap<>();
    
    public <S extends T> S save(S entity) {
        // Generic method with bounded type parameter
        return entity;
    }
    
    public Optional<T> findById(ID id) {
        return Optional.ofNullable(storage.get(id));
    }
    
    public <R> List<R> findAllProjected(Function<T, R> projection) {
        return storage.values().stream()
                .map(projection)
                .collect(Collectors.toList());
    }
    
    public void addAll(Collection<? extends T> entities) {
        // Wildcard with upper bound
        entities.forEach(entity -> save(entity));
    }
    
    public void copyTo(Collection<? super T> destination) {
        // Wildcard with lower bound
        destination.addAll(storage.values());
    }
}
"""

        chunks = self.parser.chunk(content, "GenericRepository.java")

        # Test generic class detection
        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) == 1, f"Expected 1 class, got {len(class_chunks)}"

        generic_class = class_chunks[0]
        assert (
            "<" in generic_class.text and ">" in generic_class.text
        ), "Should capture generic parameters"

        # Test generic methods
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        assert (
            len(method_chunks) >= 5
        ), f"Expected >= 5 methods, got {len(method_chunks)}"

        # Test wildcard handling
        wildcard_methods = [c for c in method_chunks if "?" in c.text]
        assert len(wildcard_methods) >= 2, "Should find methods with wildcards"

    def test_edge_cases(self):
        """Test various edge cases in Java parsing."""
        content = """
public class EdgeCases {
    // Anonymous inner classes
    Runnable task = new Runnable() {
        @Override
        public void run() {
            System.out.println("Running task");
        }
    };
    
    // Lambda expressions
    Function<String, Integer> parser = s -> Integer.parseInt(s);
    
    // Method references
    Supplier<List<String>> listSupplier = ArrayList::new;
    
    // Nested generic types
    Map<String, List<Map<Integer, String>>> complexMap = new HashMap<>();
    
    // Varargs method
    public void processItems(String... items) {
        Arrays.stream(items).forEach(System.out::println);
    }
    
    // Static initialization block
    static {
        System.loadLibrary("native-lib");
    }
    
    // Instance initialization block
    {
        complexMap = new HashMap<>();
    }
    
    // Enum with constructor and methods
    enum Status {
        ACTIVE("active", 1),
        INACTIVE("inactive", 0);
        
        private final String name;
        private final int code;
        
        Status(String name, int code) {
            this.name = name;
            this.code = code;
        }
        
        public String getName() { return name; }
        public int getCode() { return code; }
    }
}
"""

        chunks = self.parser.chunk(content, "EdgeCases.java")

        # Should successfully parse despite complex constructs
        assert len(chunks) >= 5, f"Expected >= 5 chunks, got {len(chunks)}"

        # Test enum detection
        enum_chunks = [c for c in chunks if c.semantic_type == "enum"]
        assert len(enum_chunks) >= 1, "Should find enum declarations"

        # Test method detection (including enum methods)
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        method_names = {c.semantic_name for c in method_chunks}
        assert "processItems" in method_names, "Should find varargs method"

    def test_fallback_behavior_broken_java(self):
        """Test that broken Java is handled gracefully, extracting what's possible."""
        broken_file = self.test_files_dir / "broken" / "BrokenJava.java"

        with open(broken_file, "r", encoding="utf-8") as f:
            broken_content = f.read()

        # Test with SemanticChunker
        chunks = self.chunker.chunk_content(broken_content, str(broken_file))

        # Should produce chunks even for broken Java
        assert len(chunks) > 0, "Should produce chunks even for broken Java"

        # Test data preservation - all content should be preserved
        all_chunk_text = "".join(chunk["text"] for chunk in chunks)

        # Key content should be preserved - verify some meaningful content exists
        assert "package com.example.broken" in all_chunk_text
        assert len(all_chunk_text.strip()) > 50, "Should preserve substantial content"

        # Verify some Java-related content is preserved
        java_keywords = ["String", "void", "int", "public"]
        assert any(
            keyword in all_chunk_text for keyword in java_keywords
        ), "Should preserve some Java keywords"

        # The AST parser may extract some semantic information even from broken code
        semantic_chunks = [c for c in chunks if c.get("semantic_chunking")]
        if semantic_chunks:
            # If semantic parsing worked, check for error extraction markers
            error_extracted_chunks = [
                c
                for c in semantic_chunks
                if c.get("semantic_context", {}).get("extracted_from_error")
            ]
            # Should have some chunks marked as extracted from error
            assert (
                len(error_extracted_chunks) > 0
            ), "Should mark chunks as extracted from error context"

    def test_minimal_valid_java(self):
        """Test parsing of minimal valid Java."""
        content = """
public class Minimal {
}
"""

        chunks = self.parser.chunk(content, "Minimal.java")

        assert len(chunks) >= 1, "Should create at least one chunk"

        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) == 1, "Should find exactly one class"
        assert class_chunks[0].semantic_name == "Minimal"

    def test_no_package_declaration(self):
        """Test Java file without package declaration."""
        content = """
public class NoPackage {
    public static void main(String[] args) {
        System.out.println("Hello World");
    }
}
"""

        chunks = self.parser.chunk(content, "NoPackage.java")

        assert len(chunks) >= 2, "Should create chunks for class and main method"

        class_chunks = [c for c in chunks if c.semantic_type == "class"]
        assert len(class_chunks) == 1, "Should find one class"
        assert class_chunks[0].semantic_name == "NoPackage"

    def test_integration_with_semantic_chunker(self):
        """Test integration with SemanticChunker."""
        content = """
package com.example.integration;

public class IntegrationTest {
    private String field;
    
    public IntegrationTest(String field) {
        this.field = field;
    }
    
    public String getField() {
        return field;
    }
}
"""

        # Test through SemanticChunker
        chunks = self.chunker.chunk_content(content, "IntegrationTest.java")

        assert len(chunks) > 0, "Should produce chunks"

        # Should use semantic chunking
        semantic_chunks = [c for c in chunks if c.get("semantic_chunking")]
        assert len(semantic_chunks) > 0, "Should use semantic chunking for valid Java"

        # Test chunk structure
        class_chunks = [c for c in semantic_chunks if c.get("semantic_type") == "class"]
        assert len(class_chunks) == 1, "Should find one class through SemanticChunker"

    def test_line_number_tracking(self):
        """Test that line numbers are correctly tracked."""
        content = """package com.test;

public class LineTest {
    private int field;
    
    public LineTest() {
        field = 0;
    }
    
    public int getField() {
        return field;
    }
}"""

        chunks = self.parser.chunk(content, "LineTest.java")

        for chunk in chunks:
            assert chunk.line_start > 0, "Line start should be positive"
            assert (
                chunk.line_end >= chunk.line_start
            ), "Line end should be >= line start"

        # Test specific line numbers for predictable content
        class_chunk = next((c for c in chunks if c.semantic_type == "class"), None)
        assert class_chunk is not None, "Should find class chunk"
        assert class_chunk.line_start <= 3, "Class should start early in file"

    def test_semantic_metadata_completeness(self):
        """Test that semantic metadata is complete and accurate."""
        content = """
package com.example.metadata;

public class MetadataTest {
    public MetadataTest() {
        // Constructor
    }
    
    public void testMethod() {
        // Method
    }
}
"""

        chunks = self.parser.chunk(content, "MetadataTest.java")

        for chunk in chunks:
            if chunk.semantic_chunking:
                # Required fields should be present
                assert chunk.semantic_type is not None, "semantic_type should be set"
                assert chunk.semantic_name is not None, "semantic_name should be set"
                assert chunk.semantic_path is not None, "semantic_path should be set"
                assert chunk.line_start > 0, "line_start should be positive"
                assert chunk.line_end >= chunk.line_start, "line_end should be valid"

        # Test class metadata
        class_chunk = next((c for c in chunks if c.semantic_type == "class"), None)
        assert class_chunk is not None, "Should find class chunk"
        assert class_chunk.semantic_name == "MetadataTest"
        assert "MetadataTest" in class_chunk.semantic_path

        # Test method metadata
        method_chunks = [c for c in chunks if c.semantic_type == "method"]
        assert len(method_chunks) >= 1, "Should find method chunks"

        for method_chunk in method_chunks:
            assert (
                method_chunk.semantic_parent == "MetadataTest"
            ), "Methods should have correct parent"

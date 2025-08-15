#!/usr/bin/env python3
"""
Comprehensive tests for Java parser line number accuracy.

This test suite verifies that Java semantic parser
reports accurate line numbers that match the actual content boundaries.
"""

import pytest
from code_indexer.config import IndexingConfig
from code_indexer.indexing.java_parser import JavaSemanticParser


class TestJavaLineNumbers:
    """Test line number accuracy for Java parser."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        config = IndexingConfig()
        config.chunk_size = 3000  # Large enough to avoid splitting
        config.chunk_overlap = 100
        return config

    @pytest.fixture
    def java_parser(self, config):
        """Create Java parser."""
        return JavaSemanticParser(config)

    def _verify_chunk_line_numbers(self, chunk, original_text, file_description=""):
        """
        Verify that a chunk's reported line numbers match its actual content.

        Args:
            chunk: The chunk to verify (SemanticChunk object or dict)
            original_text: The original text the chunk was extracted from
            file_description: Description for error messages
        """
        # Convert to dict if needed
        if hasattr(chunk, "to_dict"):
            chunk_dict = chunk.to_dict()
        else:
            chunk_dict = chunk

        # Get the lines from the original text
        original_lines = original_text.splitlines()

        # Verify line numbers are valid
        assert (
            chunk_dict["line_start"] >= 1
        ), f"{file_description}: line_start must be >= 1, got {chunk_dict['line_start']}"
        assert (
            chunk_dict["line_end"] >= chunk_dict["line_start"]
        ), f"{file_description}: line_end must be >= line_start"
        assert chunk_dict["line_end"] <= len(
            original_lines
        ), f"{file_description}: line_end {chunk_dict['line_end']} exceeds total lines {len(original_lines)}"

        # Extract the expected content based on reported line numbers
        expected_lines = original_lines[
            chunk_dict["line_start"] - 1 : chunk_dict["line_end"]
        ]

        # Get actual chunk content lines
        chunk_content = chunk_dict["text"]
        chunk_lines = chunk_content.splitlines()

        # For basic verification, check first and last non-empty lines
        chunk_first_line = None
        chunk_last_line = None
        expected_first_line = None
        expected_last_line = None

        # Find first non-empty chunk line
        for line in chunk_lines:
            if line.strip():
                chunk_first_line = line.strip()
                break

        # Find last non-empty chunk line
        for line in reversed(chunk_lines):
            if line.strip():
                chunk_last_line = line.strip()
                break

        # Find first non-empty expected line
        for line in expected_lines:
            if line.strip():
                expected_first_line = line.strip()
                break

        # Find last non-empty expected line
        for line in reversed(expected_lines):
            if line.strip():
                expected_last_line = line.strip()
                break

        # Verify the first lines match
        if chunk_first_line and expected_first_line:
            assert chunk_first_line == expected_first_line, (
                f"{file_description}: First line mismatch\n"
                f"Chunk first line: '{chunk_first_line}'\n"
                f"Expected first line: '{expected_first_line}'\n"
                f"Chunk reports lines {chunk_dict['line_start']}-{chunk_dict['line_end']}"
            )

        # Verify the last lines match
        if chunk_last_line and expected_last_line:
            assert chunk_last_line == expected_last_line, (
                f"{file_description}: Last line mismatch\n"
                f"Chunk last line: '{chunk_last_line}'\n"
                f"Expected last line: '{expected_last_line}'\n"
                f"Chunk reports lines {chunk_dict['line_start']}-{chunk_dict['line_end']}"
            )

    def test_java_simple_class(self, java_parser):
        """Test Java simple class definition line number accuracy."""
        code = """package com.example.demo;

import java.util.List;
import java.util.ArrayList;

/**
 * A simple person class for demonstration.
 */
public class Person {
    private String name;
    private int age;
    private List<String> hobbies;
    
    public Person(String name, int age) {
        this.name = name;
        this.age = age;
        this.hobbies = new ArrayList<>();
    }
    
    public String getName() {
        return name;
    }
    
    public void setName(String name) {
        this.name = name;
    }
    
    public int getAge() {
        return age;
    }
    
    public void setAge(int age) {
        this.age = age;
    }
    
    public List<String> getHobbies() {
        return hobbies;
    }
    
    public void addHobby(String hobby) {
        if (hobby != null && !hobby.trim().isEmpty()) {
            hobbies.add(hobby);
        }
    }
}"""

        chunks = java_parser.chunk(code, "Person.java")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"Java simple class - chunk {i+1}"
            )

    def test_java_interface_and_enum(self, java_parser):
        """Test Java interface and enum definitions line number accuracy."""
        code = """package com.example.types;

import java.util.function.Function;

/**
 * Interface for data processing operations.
 */
public interface DataProcessor<T, R> {
    
    /**
     * Process input data and return result.
     */
    R process(T input);
    
    /**
     * Validate input before processing.
     */
    default boolean validate(T input) {
        return input != null;
    }
    
    /**
     * Create a chain of processors.
     */
    static <T, R, S> DataProcessor<T, S> chain(
            DataProcessor<T, R> first,
            DataProcessor<R, S> second) {
        return input -> second.process(first.process(input));
    }
}

/**
 * Status enum for processing results.
 */
public enum ProcessingStatus {
    PENDING("Processing pending"),
    IN_PROGRESS("Currently processing"),
    COMPLETED("Processing completed"),
    FAILED("Processing failed"),
    CANCELLED("Processing cancelled");
    
    private final String description;
    
    ProcessingStatus(String description) {
        this.description = description;
    }
    
    public String getDescription() {
        return description;
    }
    
    public boolean isFinished() {
        return this == COMPLETED || this == FAILED || this == CANCELLED;
    }
}

/**
 * Utility class for processing operations.
 */
public final class ProcessingUtils {
    
    private ProcessingUtils() {
        // Utility class
    }
    
    public static <T> boolean isEmpty(T[] array) {
        return array == null || array.length == 0;
    }
    
    public static void logStatus(ProcessingStatus status) {
        System.out.println("Status: " + status.getDescription());
    }
}"""

        chunks = java_parser.chunk(code, "DataProcessor.java")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"Java interface/enum - chunk {i+1}"
            )

    def test_java_abstract_class_inheritance(self, java_parser):
        """Test Java abstract class and inheritance line number accuracy."""
        code = """package com.example.shapes;

import java.awt.Color;

/**
 * Abstract base class for all shapes.
 */
public abstract class Shape {
    protected Color color;
    protected double x, y;
    
    public Shape(double x, double y) {
        this.x = x;
        this.y = y;
        this.color = Color.BLACK;
    }
    
    public Shape(double x, double y, Color color) {
        this.x = x;
        this.y = y;
        this.color = color;
    }
    
    // Abstract methods
    public abstract double calculateArea();
    public abstract double calculatePerimeter();
    public abstract void draw();
    
    // Concrete methods
    public void move(double deltaX, double deltaY) {
        this.x += deltaX;
        this.y += deltaY;
    }
    
    public Color getColor() {
        return color;
    }
    
    public void setColor(Color color) {
        this.color = color;
    }
    
    public double getX() { return x; }
    public double getY() { return y; }
}

/**
 * Circle implementation of Shape.
 */
public class Circle extends Shape {
    private double radius;
    
    public Circle(double x, double y, double radius) {
        super(x, y);
        this.radius = radius;
    }
    
    public Circle(double x, double y, double radius, Color color) {
        super(x, y, color);
        this.radius = radius;
    }
    
    @Override
    public double calculateArea() {
        return Math.PI * radius * radius;
    }
    
    @Override
    public double calculatePerimeter() {
        return 2 * Math.PI * radius;
    }
    
    @Override
    public void draw() {
        System.out.printf("Drawing circle at (%.2f, %.2f) with radius %.2f%n",
                         x, y, radius);
    }
    
    public double getRadius() {
        return radius;
    }
    
    public void setRadius(double radius) {
        if (radius > 0) {
            this.radius = radius;
        }
    }
}

/**
 * Rectangle implementation of Shape.
 */
public class Rectangle extends Shape {
    private double width, height;
    
    public Rectangle(double x, double y, double width, double height) {
        super(x, y);
        this.width = width;
        this.height = height;
    }
    
    @Override
    public double calculateArea() {
        return width * height;
    }
    
    @Override
    public double calculatePerimeter() {
        return 2 * (width + height);
    }
    
    @Override
    public void draw() {
        System.out.printf("Drawing rectangle at (%.2f, %.2f) with dimensions %.2fx%.2f%n",
                         x, y, width, height);
    }
    
    public double getWidth() { return width; }
    public double getHeight() { return height; }
}"""

        chunks = java_parser.chunk(code, "Shapes.java")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"Java inheritance - chunk {i+1}"
            )

    def test_java_generics_and_annotations(self, java_parser):
        """Test Java generics and annotations line number accuracy."""
        code = """package com.example.repository;

import java.util.*;
import java.util.function.Predicate;
import javax.persistence.*;

/**
 * Generic repository interface with annotation support.
 */
@Repository
@Transactional
public interface GenericRepository<T, ID> {
    
    @Query("SELECT e FROM #{#entityName} e")
    List<T> findAll();
    
    @Query("SELECT e FROM #{#entityName} e WHERE e.id = :id")
    Optional<T> findById(@Param("id") ID id);
    
    @Modifying
    @Query("DELETE FROM #{#entityName} e WHERE e.id = :id")
    void deleteById(@Param("id") ID id);
    
    T save(T entity);
    
    default List<T> findByPredicate(Predicate<T> predicate) {
        return findAll().stream()
                .filter(predicate)
                .collect(Collectors.toList());
    }
}

/**
 * Generic service class with complex generics.
 */
@Service
@Transactional(readOnly = true)
public class GenericService<T extends BaseEntity<ID>, ID extends Serializable> {
    
    @Autowired
    private GenericRepository<T, ID> repository;
    
    @Autowired
    private EntityManager entityManager;
    
    @PostConstruct
    public void init() {
        System.out.println("GenericService initialized");
    }
    
    @Transactional(readOnly = false)
    public T save(T entity) {
        validateEntity(entity);
        return repository.save(entity);
    }
    
    public Optional<T> findById(ID id) {
        return repository.findById(id);
    }
    
    public List<T> findAll() {
        return repository.findAll();
    }
    
    @Transactional(readOnly = false)
    public void deleteById(ID id) {
        repository.deleteById(id);
    }
    
    private void validateEntity(T entity) {
        if (entity == null) {
            throw new IllegalArgumentException("Entity cannot be null");
        }
    }
    
    public <R> List<R> transformEntities(
            List<T> entities, 
            Function<T, R> transformer) {
        return entities.stream()
                .map(transformer)
                .collect(Collectors.toList());
    }
}

/**
 * Base entity class with generic ID.
 */
@MappedSuperclass
public abstract class BaseEntity<ID extends Serializable> {
    
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private ID id;
    
    @Column(name = "created_at")
    @Temporal(TemporalType.TIMESTAMP)
    private Date createdAt;
    
    @Column(name = "updated_at")
    @Temporal(TemporalType.TIMESTAMP)
    private Date updatedAt;
    
    @PrePersist
    protected void onCreate() {
        this.createdAt = new Date();
        this.updatedAt = new Date();
    }
    
    @PreUpdate
    protected void onUpdate() {
        this.updatedAt = new Date();
    }
    
    // Getters and setters
    public ID getId() { return id; }
    public void setId(ID id) { this.id = id; }
    
    public Date getCreatedAt() { return createdAt; }
    public Date getUpdatedAt() { return updatedAt; }
}"""

        chunks = java_parser.chunk(code, "GenericRepository.java")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"Java generics/annotations - chunk {i+1}"
            )

    def test_java_nested_classes(self, java_parser):
        """Test Java nested classes line number accuracy."""
        code = """package com.example.nested;

import java.util.Iterator;
import java.util.NoSuchElementException;

/**
 * Example of nested classes and inner classes.
 */
public class OuterClass {
    private int outerValue;
    private static int staticValue = 100;
    
    public OuterClass(int value) {
        this.outerValue = value;
    }
    
    /**
     * Static nested class.
     */
    public static class StaticNestedClass {
        private int nestedValue;
        
        public StaticNestedClass(int value) {
            this.nestedValue = value;
        }
        
        public void display() {
            System.out.println("Static nested class value: " + nestedValue);
            System.out.println("Static outer value: " + staticValue);
            // Cannot access outerValue directly
        }
        
        public int getNestedValue() {
            return nestedValue;
        }
    }
    
    /**
     * Non-static inner class.
     */
    public class InnerClass {
        private int innerValue;
        
        public InnerClass(int value) {
            this.innerValue = value;
        }
        
        public void display() {
            System.out.println("Inner class value: " + innerValue);
            System.out.println("Outer class value: " + outerValue);
            System.out.println("Static value: " + staticValue);
        }
        
        public int getInnerValue() {
            return innerValue;
        }
    }
    
    /**
     * Local class example within a method.
     */
    public Iterator<String> createIterator(String[] items) {
        class LocalIterator implements Iterator<String> {
            private int index = 0;
            
            @Override
            public boolean hasNext() {
                return index < items.length;
            }
            
            @Override
            public String next() {
                if (!hasNext()) {
                    throw new NoSuchElementException();
                }
                return items[index++];
            }
        }
        
        return new LocalIterator();
    }
    
    /**
     * Anonymous class example.
     */
    public Runnable createTask(final String message) {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("Task executing: " + message);
                System.out.println("Outer value: " + outerValue);
            }
        };
    }
    
    public int getOuterValue() {
        return outerValue;
    }
    
    public void setOuterValue(int outerValue) {
        this.outerValue = outerValue;
    }
}

/**
 * Builder pattern example with nested builder class.
 */
public class Person {
    private final String firstName;
    private final String lastName;
    private final int age;
    private final String email;
    private final String phone;
    
    private Person(Builder builder) {
        this.firstName = builder.firstName;
        this.lastName = builder.lastName;
        this.age = builder.age;
        this.email = builder.email;
        this.phone = builder.phone;
    }
    
    public static class Builder {
        private String firstName;
        private String lastName;
        private int age;
        private String email;
        private String phone;
        
        public Builder(String firstName, String lastName) {
            this.firstName = firstName;
            this.lastName = lastName;
        }
        
        public Builder age(int age) {
            this.age = age;
            return this;
        }
        
        public Builder email(String email) {
            this.email = email;
            return this;
        }
        
        public Builder phone(String phone) {
            this.phone = phone;
            return this;
        }
        
        public Person build() {
            return new Person(this);
        }
    }
    
    // Getters
    public String getFirstName() { return firstName; }
    public String getLastName() { return lastName; }
    public int getAge() { return age; }
    public String getEmail() { return email; }
    public String getPhone() { return phone; }
}"""

        chunks = java_parser.chunk(code, "NestedClasses.java")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"Java nested classes - chunk {i+1}"
            )

    def test_java_exception_handling(self, java_parser):
        """Test Java exception handling constructs line number accuracy."""
        code = """package com.example.exceptions;

import java.io.*;
import java.util.logging.Logger;

/**
 * Custom exception hierarchy.
 */
public class ProcessingException extends Exception {
    private static final long serialVersionUID = 1L;
    private final String errorCode;
    
    public ProcessingException(String message) {
        super(message);
        this.errorCode = "UNKNOWN";
    }
    
    public ProcessingException(String message, String errorCode) {
        super(message);
        this.errorCode = errorCode;
    }
    
    public ProcessingException(String message, Throwable cause) {
        super(message, cause);
        this.errorCode = "UNKNOWN";
    }
    
    public ProcessingException(String message, String errorCode, Throwable cause) {
        super(message, cause);
        this.errorCode = errorCode;
    }
    
    public String getErrorCode() {
        return errorCode;
    }
}

/**
 * Validation exception for input validation errors.
 */
public class ValidationException extends ProcessingException {
    private static final long serialVersionUID = 1L;
    private final String fieldName;
    
    public ValidationException(String fieldName, String message) {
        super(message, "VALIDATION_ERROR");
        this.fieldName = fieldName;
    }
    
    public String getFieldName() {
        return fieldName;
    }
}

/**
 * File processing service with comprehensive error handling.
 */
public class FileProcessingService {
    private static final Logger logger = Logger.getLogger(FileProcessingService.class.getName());
    
    public String processFile(String filePath) throws ProcessingException {
        if (filePath == null || filePath.trim().isEmpty()) {
            throw new ValidationException("filePath", "File path cannot be null or empty");
        }
        
        File file = new File(filePath);
        if (!file.exists()) {
            throw new ProcessingException(
                "File not found: " + filePath, 
                "FILE_NOT_FOUND"
            );
        }
        
        if (!file.canRead()) {
            throw new ProcessingException(
                "Cannot read file: " + filePath, 
                "FILE_NOT_READABLE"
            );
        }
        
        StringBuilder content = new StringBuilder();
        
        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
            String line;
            while ((line = reader.readLine()) != null) {
                content.append(line).append("\\n");
            }
        } catch (FileNotFoundException e) {
            throw new ProcessingException(
                "File not found during processing: " + filePath, 
                "FILE_NOT_FOUND", 
                e
            );
        } catch (IOException e) {
            throw new ProcessingException(
                "Error reading file: " + filePath, 
                "IO_ERROR", 
                e
            );
        }
        
        return content.toString();
    }
    
    public void processMultipleFiles(String[] filePaths) {
        for (String filePath : filePaths) {
            try {
                String content = processFile(filePath);
                logger.info("Successfully processed file: " + filePath);
                
                // Simulate some processing
                validateContent(content);
                
            } catch (ValidationException e) {
                logger.warning("Validation error for file " + filePath + 
                              ": " + e.getMessage() + " (field: " + e.getFieldName() + ")");
            } catch (ProcessingException e) {
                logger.severe("Processing error for file " + filePath + 
                             ": " + e.getMessage() + " (code: " + e.getErrorCode() + ")");
                
                if (e.getCause() != null) {
                    logger.severe("Caused by: " + e.getCause().getMessage());
                }
            } catch (Exception e) {
                logger.severe("Unexpected error processing file " + filePath + ": " + e.getMessage());
            }
        }
    }
    
    private void validateContent(String content) throws ValidationException {
        if (content == null) {
            throw new ValidationException("content", "Content cannot be null");
        }
        
        if (content.trim().isEmpty()) {
            throw new ValidationException("content", "Content cannot be empty");
        }
        
        if (content.length() > 1_000_000) {
            throw new ValidationException("content", "Content too large (max 1MB)");
        }
    }
    
    public void handleResourcesWithTryWithResources(String inputPath, String outputPath) 
            throws ProcessingException {
        try (FileInputStream input = new FileInputStream(inputPath);
             FileOutputStream output = new FileOutputStream(outputPath);
             BufferedInputStream bufferedInput = new BufferedInputStream(input);
             BufferedOutputStream bufferedOutput = new BufferedOutputStream(output)) {
            
            byte[] buffer = new byte[8192];
            int bytesRead;
            
            while ((bytesRead = bufferedInput.read(buffer)) != -1) {
                bufferedOutput.write(buffer, 0, bytesRead);
            }
            
            bufferedOutput.flush();
            
        } catch (FileNotFoundException e) {
            throw new ProcessingException("File not found", "FILE_NOT_FOUND", e);
        } catch (IOException e) {
            throw new ProcessingException("IO error during file copy", "IO_ERROR", e);
        }
    }
}"""

        chunks = java_parser.chunk(code, "ExceptionHandling.java")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"Java exceptions - chunk {i+1}"
            )

    def test_java_complex_method_signatures(self, java_parser):
        """Test Java complex method signatures line number accuracy."""
        code = """package com.example.complex;

import java.util.*;
import java.util.function.*;
import java.util.concurrent.Future;
import java.util.stream.Collectors;

/**
 * Class demonstrating complex method signatures.
 */
public class ComplexMethods {
    
    // Method with multiple generic parameters
    public <T, R, E extends Exception> Optional<R> safeTransform(
            T input,
            Function<T, R> transformer,
            Class<E> exceptionType
    ) throws E {
        try {
            return Optional.ofNullable(transformer.apply(input));
        } catch (Exception e) {
            if (exceptionType.isInstance(e)) {
                throw exceptionType.cast(e);
            }
            throw new RuntimeException("Unexpected exception", e);
        }
    }
    
    // Method with bounded wildcards
    public void processCollections(
            List<? extends Number> numbers,
            Consumer<? super Number> processor,
            Supplier<? extends Collection<Number>> collectionFactory
    ) {
        Collection<Number> result = collectionFactory.get();
        for (Number number : numbers) {
            processor.accept(number);
            result.add(number);
        }
    }
    
    // Method with varargs and throws clause
    public static <T> CompletableFuture<List<T>> combineResults(
            Executor executor,
            Function<String, T> mapper,
            String... inputs
    ) throws IllegalArgumentException, NullPointerException {
        if (inputs == null || inputs.length == 0) {
            throw new IllegalArgumentException("Inputs cannot be null or empty");
        }
        
        List<CompletableFuture<T>> futures = Arrays.stream(inputs)
                .filter(Objects::nonNull)
                .map(input -> CompletableFuture.supplyAsync(() -> mapper.apply(input), executor))
                .collect(Collectors.toList());
        
        return CompletableFuture.allOf(futures.toArray(new CompletableFuture[0]))
                .thenApply(v -> futures.stream()
                        .map(CompletableFuture::join)
                        .collect(Collectors.toList()));
    }
    
    // Method with array parameters and return types
    public int[][] multiplyMatrices(
            int[][] matrix1,
            int[][] matrix2
    ) throws IllegalArgumentException {
        if (matrix1 == null || matrix2 == null) {
            throw new IllegalArgumentException("Matrices cannot be null");
        }
        
        int rows1 = matrix1.length;
        int cols1 = matrix1[0].length;
        int rows2 = matrix2.length;
        int cols2 = matrix2[0].length;
        
        if (cols1 != rows2) {
            throw new IllegalArgumentException(
                "Number of columns in first matrix must equal number of rows in second matrix"
            );
        }
        
        int[][] result = new int[rows1][cols2];
        
        for (int i = 0; i < rows1; i++) {
            for (int j = 0; j < cols2; j++) {
                for (int k = 0; k < cols1; k++) {
                    result[i][j] += matrix1[i][k] * matrix2[k][j];
                }
            }
        }
        
        return result;
    }
    
    // Method with complex lambda parameters
    public <T, K, V> Map<K, List<V>> groupAndTransform(
            Collection<T> items,
            Function<T, K> keyExtractor,
            Function<T, V> valueTransformer,
            BinaryOperator<List<V>> listMerger
    ) {
        return items.stream()
                .collect(Collectors.toMap(
                    keyExtractor,
                    item -> Arrays.asList(valueTransformer.apply(item)),
                    listMerger
                ));
    }
    
    // Synchronized method with complex signature
    public synchronized <T extends Comparable<T>> Future<Optional<T>> findMaximumAsync(
            Collection<T> collection,
            Predicate<T> filter,
            Executor executor
    ) {
        return CompletableFuture.supplyAsync(() -> {
            return collection.stream()
                    .filter(filter)
                    .max(Comparator.naturalOrder());
        }, executor);
    }
    
    // Method with annotation and complex generics
    @SuppressWarnings({"unchecked", "rawtypes"})
    public <T extends Serializable & Comparable<T>> Map<String, T> processSerializableComparables(
            Map<String, ? extends T> input,
            Function<T, Boolean> validator,
            BiFunction<String, T, T> processor
    ) {
        Map<String, T> result = new HashMap<>();
        
        for (Map.Entry<String, ? extends T> entry : input.entrySet()) {
            String key = entry.getKey();
            T value = entry.getValue();
            
            if (validator.apply(value)) {
                T processedValue = processor.apply(key, value);
                result.put(key, processedValue);
            }
        }
        
        return result;
    }
    
    // Final method with package-private access
    final Map<String, Integer> calculateWordFrequencies(String text) {
        if (text == null || text.trim().isEmpty()) {
            return Collections.emptyMap();
        }
        
        return Arrays.stream(text.toLowerCase().split("\\\\W+"))
                .filter(word -> !word.isEmpty())
                .collect(Collectors.toMap(
                    Function.identity(),
                    word -> 1,
                    Integer::sum
                ));
    }
}"""

        chunks = java_parser.chunk(code, "ComplexMethods.java")
        assert len(chunks) > 0, "Expected at least one chunk"

        for i, chunk in enumerate(chunks):
            self._verify_chunk_line_numbers(
                chunk, code, f"Java complex methods - chunk {i+1}"
            )

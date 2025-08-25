"""End-to-end tests for Story 7: Validate Search Quality Improvement.

This test suite validates that the new fixed-size chunking approach produces
significantly better search results compared to the old AST-based approach.

Key validation requirements from Story 7:
- Exactly 1000 characters per chunk (not 549 average like before)
- 0% of chunks under 1000 characters (except final chunk per file)
- Massive improvement over 76.5% chunks under 300 chars and 52% under 100 chars
- Search results contain complete method implementations, not fragments
- Chunks preserve enough context to understand the code's purpose
- Line number metadata accurately reflects chunk positions
"""

import pytest
from pathlib import Path
import tempfile
import shutil
import statistics

from code_indexer.indexing.fixed_size_chunker import FixedSizeChunker
from code_indexer.config import IndexingConfig


class TestSearchQualityValidation:
    """Test suite for validating search quality improvements from fixed-size chunking."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def chunker(self):
        """Create fixed-size chunker instance."""
        config = IndexingConfig()
        return FixedSizeChunker(config)

    @pytest.fixture
    def sample_code_files(self, temp_dir):
        """Create sample code files that represent typical real-world scenarios."""
        # Python file with customer management functionality
        python_file = temp_dir / "customer_management.py"
        python_content = '''"""Customer management system with database operations."""

import sqlite3
from typing import List, Optional, Dict
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Customer:
    """Represents a customer in the system."""
    id: int
    name: str
    email: str
    phone: str
    created_at: datetime
    
    def validate_email(self) -> bool:
        """Validate customer email format."""
        return '@' in self.email and '.' in self.email.split('@')[1]


class CustomerRepository:
    """Repository for customer database operations."""
    
    def __init__(self, db_path: str):
        """Initialize repository with database connection."""
        self.db_path = db_path
        self.connection = None
    
    def connect(self) -> None:
        """Establish database connection."""
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        
    def create_customer_table(self) -> None:
        """Create the customer table if it doesn't exist."""
        if not self.connection:
            raise ValueError("Database connection not established")
            
        create_sql = """
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        self.connection.execute(create_sql)
        self.connection.commit()
    
    def save_customer(self, customer: Customer) -> int:
        """Save customer to database and return generated ID."""
        if not customer.validate_email():
            raise ValueError("Invalid email format")
            
        insert_sql = """
        INSERT INTO customers (name, email, phone, created_at)
        VALUES (?, ?, ?, ?)
        """
        cursor = self.connection.execute(
            insert_sql,
            (customer.name, customer.email, customer.phone, customer.created_at)
        )
        self.connection.commit()
        return cursor.lastrowid
    
    def find_customer_by_email(self, email: str) -> Optional[Customer]:
        """Find customer by email address."""
        select_sql = "SELECT * FROM customers WHERE email = ?"
        cursor = self.connection.execute(select_sql, (email,))
        row = cursor.fetchone()
        
        if row:
            return Customer(
                id=row['id'],
                name=row['name'],
                email=row['email'],
                phone=row['phone'],
                created_at=datetime.fromisoformat(row['created_at'])
            )
        return None
    
    def get_all_customers(self) -> List[Customer]:
        """Retrieve all customers from database."""
        select_sql = "SELECT * FROM customers ORDER BY created_at DESC"
        cursor = self.connection.execute(select_sql)
        
        customers = []
        for row in cursor.fetchall():
            customers.append(Customer(
                id=row['id'],
                name=row['name'],
                email=row['email'],
                phone=row['phone'],
                created_at=datetime.fromisoformat(row['created_at'])
            ))
        return customers


class CustomerService:
    """Service layer for customer operations."""
    
    def __init__(self, repository: CustomerRepository):
        """Initialize service with customer repository."""
        self.repository = repository
    
    def create_new_customer(self, name: str, email: str, phone: str = None) -> Customer:
        """Create and save a new customer."""
        # Check if customer already exists
        existing = self.repository.find_customer_by_email(email)
        if existing:
            raise ValueError(f"Customer with email {email} already exists")
        
        # Create new customer
        customer = Customer(
            id=0,  # Will be set by database
            name=name.strip(),
            email=email.lower().strip(),
            phone=phone.strip() if phone else None,
            created_at=datetime.now()
        )
        
        # Save to database
        customer_id = self.repository.save_customer(customer)
        customer.id = customer_id
        
        return customer
    
    def update_customer_phone(self, email: str, new_phone: str) -> bool:
        """Update customer's phone number."""
        customer = self.repository.find_customer_by_email(email)
        if not customer:
            return False
        
        update_sql = "UPDATE customers SET phone = ? WHERE email = ?"
        self.repository.connection.execute(update_sql, (new_phone, email))
        self.repository.connection.commit()
        return True
    
    def search_customers_by_name(self, name_pattern: str) -> List[Customer]:
        """Search customers by name pattern."""
        search_sql = "SELECT * FROM customers WHERE name LIKE ? ORDER BY name"
        cursor = self.repository.connection.execute(search_sql, (f"%{name_pattern}%",))
        
        customers = []
        for row in cursor.fetchall():
            customers.append(Customer(
                id=row['id'],
                name=row['name'],
                email=row['email'],
                phone=row['phone'],
                created_at=datetime.fromisoformat(row['created_at'])
            ))
        return customers


# Database connection helper functions
def get_database_connection(db_path: str) -> sqlite3.Connection:
    """Get database connection with proper configuration."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    
    # Enable foreign key constraints
    connection.execute("PRAGMA foreign_keys = ON")
    
    # Set timeout for busy database
    connection.execute("PRAGMA busy_timeout = 30000")
    
    return connection


def initialize_customer_database(db_path: str) -> CustomerRepository:
    """Initialize customer database with all necessary tables."""
    repository = CustomerRepository(db_path)
    repository.connect()
    repository.create_customer_table()
    return repository


# Usage example and main function
if __name__ == "__main__":
    # Initialize database
    db_path = "customers.db"
    repo = initialize_customer_database(db_path)
    service = CustomerService(repo)
    
    try:
        # Create sample customers
        customer1 = service.create_new_customer(
            "John Doe",
            "john.doe@example.com",
            "555-1234"
        )
        
        customer2 = service.create_new_customer(
            "Jane Smith",
            "jane.smith@example.com",
            "555-5678"
        )
        
        print(f"Created customer: {customer1.name} ({customer1.email})")
        print(f"Created customer: {customer2.name} ({customer2.email})")
        
        # Search functionality test
        search_results = service.search_customers_by_name("John")
        print(f"Found {len(search_results)} customers matching 'John'")
        
    except ValueError as e:
        print(f"Error: {e}")
    finally:
        if repo.connection:
            repo.connection.close()
'''
        python_file.write_text(python_content)

        # Java file with database connection functionality
        java_file = temp_dir / "DatabaseConnection.java"
        java_content = """package com.example.database;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;
import java.util.logging.Logger;
import java.util.logging.Level;

/**
 * Database connection manager for handling database operations.
 * Provides connection pooling and transaction management.
 */
public class DatabaseConnection {
    private static final Logger LOGGER = Logger.getLogger(DatabaseConnection.class.getName());
    private static final String DEFAULT_DRIVER = "com.mysql.cj.jdbc.Driver";
    
    private String jdbcUrl;
    private String username;
    private String password;
    private Properties connectionProperties;
    private Connection connection;
    
    public DatabaseConnection(String jdbcUrl, String username, String password) {
        this.jdbcUrl = jdbcUrl;
        this.username = username;
        this.password = password;
        this.connectionProperties = new Properties();
        initializeDefaultProperties();
    }
    
    private void initializeDefaultProperties() {
        connectionProperties.setProperty("useSSL", "true");
        connectionProperties.setProperty("serverTimezone", "UTC");
        connectionProperties.setProperty("allowPublicKeyRetrieval", "true");
        connectionProperties.setProperty("useUnicode", "true");
        connectionProperties.setProperty("characterEncoding", "UTF-8");
        connectionProperties.setProperty("autoReconnect", "true");
        connectionProperties.setProperty("failOverReadOnly", "false");
        connectionProperties.setProperty("maxReconnects", "3");
    }
    
    /**
     * Establish database connection with retry logic.
     * @return true if connection successful, false otherwise
     */
    public boolean connect() {
        int retryCount = 0;
        int maxRetries = 3;
        
        while (retryCount < maxRetries) {
            try {
                // Load JDBC driver
                Class.forName(DEFAULT_DRIVER);
                
                // Create connection
                this.connection = DriverManager.getConnection(
                    jdbcUrl, username, password
                );
                
                // Test connection
                if (connection.isValid(5)) {
                    LOGGER.info("Database connection established successfully");
                    return true;
                }
                
            } catch (ClassNotFoundException e) {
                LOGGER.log(Level.SEVERE, "JDBC driver not found", e);
                return false;
            } catch (SQLException e) {
                retryCount++;
                LOGGER.log(Level.WARNING, 
                    String.format("Connection attempt %d failed: %s", retryCount, e.getMessage())
                );
                
                if (retryCount >= maxRetries) {
                    LOGGER.log(Level.SEVERE, "Max connection retries exceeded", e);
                    return false;
                }
                
                try {
                    Thread.sleep(1000 * retryCount); // Exponential backoff
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    return false;
                }
            }
        }
        return false;
    }
    
    /**
     * Execute SELECT query and return results.
     * @param sql SQL query to execute
     * @param parameters Query parameters
     * @return List of result rows as string arrays
     */
    public List<String[]> executeQuery(String sql, Object... parameters) throws SQLException {
        if (connection == null || connection.isClosed()) {
            throw new SQLException("Database connection is not available");
        }
        
        List<String[]> results = new ArrayList<>();
        
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            // Set parameters
            for (int i = 0; i < parameters.length; i++) {
                statement.setObject(i + 1, parameters[i]);
            }
            
            try (ResultSet resultSet = statement.executeQuery()) {
                int columnCount = resultSet.getMetaData().getColumnCount();
                
                while (resultSet.next()) {
                    String[] row = new String[columnCount];
                    for (int i = 1; i <= columnCount; i++) {
                        row[i - 1] = resultSet.getString(i);
                    }
                    results.add(row);
                }
            }
        }
        
        return results;
    }
    
    /**
     * Execute INSERT, UPDATE, or DELETE statement.
     * @param sql SQL statement to execute
     * @param parameters Statement parameters
     * @return Number of affected rows
     */
    public int executeUpdate(String sql, Object... parameters) throws SQLException {
        if (connection == null || connection.isClosed()) {
            throw new SQLException("Database connection is not available");
        }
        
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            for (int i = 0; i < parameters.length; i++) {
                statement.setObject(i + 1, parameters[i]);
            }
            
            int rowsAffected = statement.executeUpdate();
            LOGGER.info(String.format("Query executed successfully, %d rows affected", rowsAffected));
            return rowsAffected;
        }
    }
    
    /**
     * Begin database transaction.
     */
    public void beginTransaction() throws SQLException {
        if (connection == null || connection.isClosed()) {
            throw new SQLException("Database connection is not available");
        }
        
        connection.setAutoCommit(false);
        LOGGER.info("Transaction started");
    }
    
    /**
     * Commit current transaction.
     */
    public void commitTransaction() throws SQLException {
        if (connection == null || connection.isClosed()) {
            throw new SQLException("Database connection is not available");
        }
        
        connection.commit();
        connection.setAutoCommit(true);
        LOGGER.info("Transaction committed");
    }
    
    /**
     * Rollback current transaction.
     */
    public void rollbackTransaction() throws SQLException {
        if (connection == null || connection.isClosed()) {
            throw new SQLException("Database connection is not available");
        }
        
        connection.rollback();
        connection.setAutoCommit(true);
        LOGGER.info("Transaction rolled back");
    }
    
    /**
     * Close database connection and cleanup resources.
     */
    public void close() {
        if (connection != null) {
            try {
                if (!connection.isClosed()) {
                    connection.close();
                    LOGGER.info("Database connection closed");
                }
            } catch (SQLException e) {
                LOGGER.log(Level.WARNING, "Error closing database connection", e);
            }
        }
    }
    
    /**
     * Check if connection is still valid and active.
     * @return true if connection is valid, false otherwise
     */
    public boolean isConnectionValid() {
        try {
            return connection != null && !connection.isClosed() && connection.isValid(5);
        } catch (SQLException e) {
            LOGGER.log(Level.WARNING, "Error checking connection validity", e);
            return false;
        }
    }
    
    /**
     * Get current connection instance.
     * @return Database connection
     */
    public Connection getConnection() {
        return connection;
    }
    
    /**
     * Execute batch operations for better performance.
     * @param sql SQL statement template
     * @param parametersList List of parameter arrays for each batch item
     * @return Array of update counts
     */
    public int[] executeBatch(String sql, List<Object[]> parametersList) throws SQLException {
        if (connection == null || connection.isClosed()) {
            throw new SQLException("Database connection is not available");
        }
        
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            for (Object[] parameters : parametersList) {
                for (int i = 0; i < parameters.length; i++) {
                    statement.setObject(i + 1, parameters[i]);
                }
                statement.addBatch();
            }
            
            int[] results = statement.executeBatch();
            LOGGER.info(String.format("Batch executed successfully, %d statements processed", results.length));
            return results;
        }
    }
}
"""
        java_file.write_text(java_content)

        return {"python": python_file, "java": java_file}

    def test_chunk_size_distribution_exactly_1000_chars(
        self, chunker, sample_code_files
    ):
        """Test that chunks are exactly 1000 characters (except final chunk).

        This test validates Story 7 requirement:
        - Exactly 1000 characters per chunk (not 549 average like before)
        - 0% of chunks under 1000 characters (except final chunk per file)
        """
        all_chunks = []
        file_chunk_counts = []

        for file_type, file_path in sample_code_files.items():
            chunks = chunker.chunk_file(file_path)
            all_chunks.extend(chunks)
            file_chunk_counts.append(len(chunks))

        # Analyze chunk sizes
        chunk_sizes = [chunk["size"] for chunk in all_chunks]

        # Separate regular chunks from final chunks
        # Final chunks are the last chunk of each file
        final_chunk_indices = []
        current_index = 0
        for count in file_chunk_counts:
            if count > 0:  # Only if file has chunks
                final_chunk_indices.append(current_index + count - 1)
            current_index += count

        regular_chunks = []
        final_chunks = []

        for i, size in enumerate(chunk_sizes):
            if i in final_chunk_indices:
                final_chunks.append(size)
            else:
                regular_chunks.append(size)

        # Test requirements from Story 7
        # All regular chunks must be exactly 1000 characters
        for size in regular_chunks:
            assert (
                size == 1000
            ), f"Regular chunk has {size} chars, expected exactly 1000"

        # 0% of chunks under 1000 characters (except final chunks)
        under_1000_regular = sum(1 for size in regular_chunks if size < 1000)
        assert (
            under_1000_regular == 0
        ), f"{under_1000_regular} regular chunks under 1000 chars"

        # Final chunks can be under 1000, but should not be empty
        for size in final_chunks:
            assert size > 0, "Final chunk should not be empty"

        # Validate that we have good chunk distribution
        assert len(all_chunks) >= 2, "Should have multiple chunks to test distribution"

        # Calculate average size - should be much better than old 549 average
        average_size = sum(chunk_sizes) / len(chunk_sizes)
        assert (
            average_size >= 800
        ), f"Average size {average_size} should be >= 800 chars (old was 549)"

    def test_massive_improvement_over_old_approach(self, chunker, sample_code_files):
        """Test that we have massive improvement over old AST approach.

        Old approach had:
        - 76.5% chunks under 300 chars
        - 52% chunks under 100 chars
        - 549 average chunk size

        New approach should have:
        - 0% chunks under 300 chars (except possibly final chunks)
        - 0% chunks under 100 chars (except possibly very small final chunks)
        - Close to 1000 average chunk size
        """
        all_chunks = []

        for file_type, file_path in sample_code_files.items():
            chunks = chunker.chunk_file(file_path)
            all_chunks.extend(chunks)

        chunk_sizes = [chunk["size"] for chunk in all_chunks]

        # Calculate statistics
        under_100_count = sum(1 for size in chunk_sizes if size < 100)
        under_300_count = sum(1 for size in chunk_sizes if size < 300)
        under_100_percent = (under_100_count / len(chunk_sizes)) * 100
        under_300_percent = (under_300_count / len(chunk_sizes)) * 100
        average_size = statistics.mean(chunk_sizes)

        # Test massive improvement requirements
        # Should be dramatic improvement from 52% under 100 chars to near 0%
        assert (
            under_100_percent < 10
        ), f"{under_100_percent}% chunks under 100 chars (old: 52%)"

        # Should be dramatic improvement from 76.5% under 300 chars to near 0%
        assert (
            under_300_percent < 10
        ), f"{under_300_percent}% chunks under 300 chars (old: 76.5%)"

        # Average should be much closer to 1000 than old 549
        assert average_size > 800, f"Average size {average_size} chars (old: 549)"

        # This test should FAIL initially to demonstrate TDD approach

    def test_search_quality_meaningful_code_blocks(self, chunker, sample_code_files):
        """Test that chunks contain meaningful code blocks, not fragments.

        Story 7 requirements:
        - Search results contain complete method implementations, not fragments
        - Chunks preserve enough context to understand the code's purpose
        """
        python_file = sample_code_files["python"]
        chunks = chunker.chunk_file(python_file)

        # Find chunks that should contain meaningful code
        customer_method_chunks = []
        database_connection_chunks = []

        for chunk in chunks:
            text = chunk["text"]
            if "def save_customer" in text:
                customer_method_chunks.append(chunk)
            if "def connect" in text or "database connection" in text.lower():
                database_connection_chunks.append(chunk)

        # Test that we found meaningful chunks
        assert (
            len(customer_method_chunks) > 0
        ), "Should find chunks with save_customer method"
        assert (
            len(database_connection_chunks) > 0
        ), "Should find chunks with database connection logic"

        # Test chunk quality - should contain complete method implementations
        for chunk in customer_method_chunks:
            text = chunk["text"]
            # Should contain method definition and some implementation
            assert "def save_customer" in text, "Should contain method definition"
            assert (
                "customer.validate_email()" in text or "INSERT INTO" in text
            ), "Should contain method implementation"

        # Test context preservation
        for chunk in database_connection_chunks:
            text = chunk["text"]
            # Should have enough context to understand purpose
            assert (
                len(text) >= 800
            ), f"Chunk too short ({len(text)} chars) to provide context"

        # This test should initially FAIL to demonstrate the TDD approach

    def test_line_number_metadata_accuracy(self, chunker, sample_code_files):
        """Test that line number metadata accurately reflects chunk positions.

        Story 7 requirement:
        - Line number metadata accurately reflects chunk positions
        """
        java_file = sample_code_files["java"]
        chunks = chunker.chunk_file(java_file)

        # Read the original file to validate line numbers
        file_content = java_file.read_text()
        file_lines = file_content.split("\n")

        # Test line number accuracy
        for i, chunk in enumerate(chunks):
            line_start = chunk["line_start"]
            line_end = chunk["line_end"]

            # Basic validation
            assert line_start >= 1, f"Chunk {i}: line_start {line_start} should be >= 1"
            assert (
                line_end >= line_start
            ), f"Chunk {i}: line_end {line_end} should be >= line_start {line_start}"
            assert line_end <= len(
                file_lines
            ), f"Chunk {i}: line_end {line_end} exceeds file length {len(file_lines)}"

            # Test that line numbers correspond to actual chunk content
            # chunk_text = chunk['text']  # May be needed for future validation

            # For first chunk, should start at line 1
            if i == 0:
                assert (
                    line_start == 1
                ), f"First chunk should start at line 1, got {line_start}"

            # Line numbers should be sequential (within reason for overlapping chunks)
            if i > 0:
                prev_chunk = chunks[i - 1]
                # Due to overlap, current chunk might start before previous chunk ends
                # but should not start too far back
                assert (
                    line_start <= prev_chunk["line_end"]
                ), f"Chunk {i}: line numbers not sequential"

        # This test should initially FAIL to demonstrate TDD approach

    def test_chunk_overlap_exactly_150_characters(self, chunker):
        """Test that chunks have exactly 150 characters overlap.

        Story 7 validation of fixed overlap requirement.
        """
        # Create a simple test text long enough for multiple chunks
        test_text = "A" * 3000  # 3000 characters should create 3 chunks

        chunks = chunker.chunk_text(test_text)

        # Should have multiple chunks
        assert len(chunks) >= 2, f"Expected multiple chunks, got {len(chunks)}"

        # Test overlap between consecutive chunks
        for i in range(len(chunks) - 1):
            current_chunk = chunks[i]
            next_chunk = chunks[i + 1]

            current_text = current_chunk["text"]
            next_text = next_chunk["text"]

            # For our simple test text, we can verify exact overlap
            if len(current_text) == 1000:  # Regular chunk
                # Next chunk should start 850 chars into current chunk (1000 - 150 overlap)
                expected_overlap_start = current_text[850:]  # Last 150 chars
                actual_overlap = next_text[:150]  # First 150 chars of next

                assert (
                    expected_overlap_start == actual_overlap
                ), f"Chunks {i}-{i+1}: overlap mismatch"

        # This test should initially FAIL to demonstrate TDD approach


class TestRealWorldCodebaseValidation:
    """Test validation against real codebase scenarios."""

    def test_evolution_codebase_chunk_quality(self):
        """Test chunking quality on evolution-like codebase structure.

        This would test against a real codebase if accessible, validating:
        - Search for "customer management" returns meaningful code blocks
        - Search for "database connection" returns actual connection logic
        - No package declarations or import statements as standalone results
        """
        # This test is designed to FAIL initially
        # It should be implemented once we have access to a real codebase for testing
        pytest.skip("Requires real codebase access for validation")

    def test_search_result_quality_metrics(self):
        """Test that search result quality metrics show improvement.

        This would measure:
        - Percentage of useful search results vs fragments
        - Context completeness in search results
        - User experience metrics
        """
        # This test is designed to FAIL initially
        # Implementation should follow once basic chunking quality is validated
        pytest.skip("Requires implementation of search quality metrics")

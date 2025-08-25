"""Simplified end-to-end tests for FixedSizeChunker.

These tests focus on the most important end-to-end functionality without
getting into complex mocking of the entire processing pipeline.
"""

import pytest
import tempfile
from pathlib import Path
from src.code_indexer.indexing.fixed_size_chunker import FixedSizeChunker
from src.code_indexer.config import IndexingConfig


class TestFixedSizeChunkerSimpleE2E:
    """Simplified end-to-end tests focusing on core functionality."""

    @pytest.fixture
    def chunker(self):
        """Create a FixedSizeChunker with standard configuration."""
        config = IndexingConfig()
        return FixedSizeChunker(config)

    def test_e2e_chunking_java_service_file(self, chunker):
        """End-to-end test with a realistic Java service file."""
        # Create a realistic Java file with complex content
        java_content = """
package com.example.service;

import java.util.List;
import java.util.ArrayList;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;

/**
 * Customer service handling all customer-related business operations.
 * This service provides comprehensive customer management functionality
 * including registration, updates, search, and data validation.
 */
@Service
@Transactional
public class CustomerService {

    @Autowired
    private CustomerRepository customerRepository;
    
    @Autowired
    private ValidationService validationService;
    
    @Autowired
    private NotificationService notificationService;
    
    private static final int MAX_SEARCH_RESULTS = 100;
    private static final String DEFAULT_SORT_FIELD = "lastName";

    /**
     * Creates a new customer with comprehensive validation.
     * 
     * @param customerRequest The customer creation request
     * @return CompletableFuture containing the created customer
     * @throws ValidationException if the request is invalid
     * @throws DuplicateCustomerException if customer already exists
     */
    public CompletableFuture<Customer> createCustomer(CreateCustomerRequest customerRequest) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                // Validate the incoming request
                ValidationResult validation = validationService.validateCreateRequest(customerRequest);
                if (!validation.isValid()) {
                    throw new ValidationException("Customer validation failed", validation.getErrors());
                }
                
                // Check for duplicate email addresses
                Optional<Customer> existingCustomer = customerRepository.findByEmail(customerRequest.getEmail());
                if (existingCustomer.isPresent()) {
                    throw new DuplicateCustomerException("Customer with email already exists: " + customerRequest.getEmail());
                }
                
                // Create the new customer entity
                Customer customer = new Customer();
                customer.setFirstName(customerRequest.getFirstName());
                customer.setLastName(customerRequest.getLastName());
                customer.setEmail(customerRequest.getEmail());
                customer.setPhoneNumber(customerRequest.getPhoneNumber());
                customer.setAddress(mapToAddress(customerRequest.getAddress()));
                customer.setDateOfBirth(customerRequest.getDateOfBirth());
                customer.setCreatedAt(LocalDateTime.now());
                customer.setUpdatedAt(LocalDateTime.now());
                customer.setStatus(CustomerStatus.ACTIVE);
                
                // Save the customer to the database
                Customer savedCustomer = customerRepository.save(customer);
                
                // Send welcome notification asynchronously
                notificationService.sendWelcomeNotificationAsync(savedCustomer);
                
                // Log the successful customer creation
                auditLogger.info("Customer created successfully: ID={}, Email={}", 
                    savedCustomer.getId(), savedCustomer.getEmail());
                
                return savedCustomer;
                
            } catch (ValidationException | DuplicateCustomerException e) {
                auditLogger.warn("Customer creation failed: {}", e.getMessage());
                throw e;
            } catch (Exception e) {
                auditLogger.error("Unexpected error during customer creation", e);
                throw new ServiceException("Failed to create customer", e);
            }
        });
    }

    /**
     * Searches for customers based on various criteria with pagination.
     * 
     * @param searchCriteria The search criteria including filters and pagination
     * @return PagedResult containing matching customers and pagination info
     */
    public PagedResult<Customer> searchCustomers(CustomerSearchCriteria searchCriteria) {
        try {
            // Validate search criteria
            if (searchCriteria.getPageSize() > MAX_SEARCH_RESULTS) {
                throw new ValidationException("Page size exceeds maximum allowed: " + MAX_SEARCH_RESULTS);
            }
            
            // Build dynamic query based on criteria
            CustomerQueryBuilder queryBuilder = new CustomerQueryBuilder();
            
            if (searchCriteria.getEmailFilter() != null) {
                queryBuilder.withEmailContaining(searchCriteria.getEmailFilter());
            }
            
            if (searchCriteria.getNameFilter() != null) {
                queryBuilder.withFirstNameOrLastNameContaining(searchCriteria.getNameFilter());
            }
            
            if (searchCriteria.getStatusFilter() != null) {
                queryBuilder.withStatus(searchCriteria.getStatusFilter());
            }
            
            if (searchCriteria.getDateRange() != null) {
                queryBuilder.withCreatedDateBetween(
                    searchCriteria.getDateRange().getStartDate(),
                    searchCriteria.getDateRange().getEndDate()
                );
            }
            
            // Apply sorting
            String sortField = searchCriteria.getSortField() != null ? 
                searchCriteria.getSortField() : DEFAULT_SORT_FIELD;
            SortDirection sortDirection = searchCriteria.getSortDirection() != null ?
                searchCriteria.getSortDirection() : SortDirection.ASC;
                
            queryBuilder.orderBy(sortField, sortDirection);
            
            // Execute the query with pagination
            CustomerQuery query = queryBuilder.build();
            Page<Customer> customerPage = customerRepository.findByQuery(query, 
                PageRequest.of(searchCriteria.getPageNumber(), searchCriteria.getPageSize()));
            
            // Convert to PagedResult
            return new PagedResult<>(
                customerPage.getContent(),
                customerPage.getTotalElements(),
                customerPage.getTotalPages(),
                customerPage.getNumber(),
                customerPage.getSize()
            );
            
        } catch (ValidationException e) {
            auditLogger.warn("Customer search validation failed: {}", e.getMessage());
            throw e;
        } catch (Exception e) {
            auditLogger.error("Unexpected error during customer search", e);
            throw new ServiceException("Failed to search customers", e);
        }
    }
    
    private Address mapToAddress(AddressRequest addressRequest) {
        if (addressRequest == null) {
            return null;
        }
        
        Address address = new Address();
        address.setStreet(addressRequest.getStreet());
        address.setCity(addressRequest.getCity());
        address.setState(addressRequest.getState());
        address.setZipCode(addressRequest.getZipCode());
        address.setCountry(addressRequest.getCountry());
        
        return address;
    }
}
"""

        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False)
        temp_file.write(java_content)
        temp_file.close()
        temp_path = Path(temp_file.name)

        try:
            # Test end-to-end chunking
            chunks = chunker.chunk_file(temp_path)

            # Verify chunking worked correctly
            assert len(chunks) > 1, "Should produce multiple chunks for this large file"

            # Verify all chunks except last are exactly 1000 characters
            for i, chunk in enumerate(chunks[:-1]):
                assert (
                    len(chunk["text"]) == 1000
                ), f"Chunk {i} should be exactly 1000 chars, got {len(chunk['text'])}"

            # Verify metadata is complete and accurate
            for i, chunk in enumerate(chunks):
                # All required metadata fields present
                required_fields = [
                    "text",
                    "chunk_index",
                    "total_chunks",
                    "size",
                    "file_path",
                    "file_extension",
                    "line_start",
                    "line_end",
                ]
                for field in required_fields:
                    assert field in chunk, f"Chunk {i} missing field: {field}"

                # Metadata values are correct
                assert chunk["chunk_index"] == i
                assert chunk["total_chunks"] == len(chunks)
                assert chunk["size"] == len(chunk["text"])
                assert chunk["file_extension"] == "java"
                assert chunk["line_start"] > 0
                assert chunk["line_end"] >= chunk["line_start"]

            # Verify chunk content quality (meaningful code, not fragments)
            meaningful_chunks = 0
            for chunk in chunks:
                text = chunk["text"]
                # Look for meaningful Java constructs
                if any(
                    pattern in text
                    for pattern in [
                        "public ",
                        "private ",
                        "protected ",
                        "@",
                        "class ",
                        "interface ",
                        "return ",
                        "if (",
                        "for (",
                        "while (",
                        "try {",
                        "catch (",
                    ]
                ):
                    meaningful_chunks += 1

            # Most chunks should contain meaningful code
            meaningful_ratio = meaningful_chunks / len(chunks)
            assert (
                meaningful_ratio > 0.7
            ), f"Only {meaningful_ratio:.1%} of chunks contain meaningful code"

            # Verify overlap between consecutive chunks
            for i in range(len(chunks) - 1):
                current_chunk = chunks[i]["text"]
                next_chunk = chunks[i + 1]["text"]

                # Last 150 characters of current should match first 150 of next
                overlap_current = current_chunk[-150:]
                overlap_next = next_chunk[:150]

                assert (
                    overlap_current == overlap_next
                ), f"Overlap mismatch between chunks {i} and {i+1}"

            print(
                f"E2E Java test: {len(chunks)} chunks, "
                f"{meaningful_chunks} meaningful ({meaningful_ratio:.1%})"
            )

        finally:
            temp_path.unlink()  # Clean up

    def test_e2e_chunking_python_data_processor(self, chunker):
        """End-to-end test with a realistic Python data processing file."""
        python_content = '''
import asyncio
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Union, Any, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from functools import lru_cache, wraps, partial
import aiohttp
import aiofiles
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
import redis.asyncio as redis
from contextlib import asynccontextmanager
import json
import yaml

logger = logging.getLogger(__name__)


@dataclass
class ProcessingConfig:
    """Configuration for advanced data processing operations."""
    batch_size: int = 1000
    max_workers: int = 4
    timeout_seconds: int = 300
    retry_attempts: int = 3
    enable_caching: bool = True
    cache_ttl_seconds: int = 3600
    database_url: str = "postgresql://localhost/data_processing"
    redis_url: str = "redis://localhost:6379/0"


class AdvancedDataProcessor:
    """
    High-performance data processing engine with advanced features.
    
    This processor provides:
    - Asynchronous batch processing with configurable parallelism
    - Intelligent caching with Redis integration
    - Comprehensive error handling and retry mechanisms
    - Real-time progress monitoring and metrics collection
    - Database integration with connection pooling
    - Memory-efficient streaming for large datasets
    - Flexible transformation pipeline architecture
    """
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.stats = {
            'items_processed': 0,
            'items_failed': 0,
            'batches_completed': 0,
            'total_processing_time': 0.0,
            'cache_hits': 0,
            'cache_misses': 0,
            'database_operations': 0,
            'start_time': datetime.now()
        }
        self.cache_client: Optional[redis.Redis] = None
        self.database_engine = None
        self.session_factory = None
        self.thread_pool = ThreadPoolExecutor(max_workers=config.max_workers)
        self.process_pool = ProcessPoolExecutor(max_workers=config.max_workers)
        
    async def initialize(self) -> None:
        """Initialize all external connections and resources."""
        try:
            # Initialize Redis cache client
            if self.config.enable_caching:
                self.cache_client = redis.from_url(
                    self.config.redis_url,
                    encoding='utf-8',
                    decode_responses=True
                )
                await self.cache_client.ping()
                logger.info("Redis cache connection established")
            
            # Initialize database connection
            self.database_engine = create_engine(
                self.config.database_url,
                pool_size=20,
                max_overflow=30,
                pool_timeout=30,
                pool_recycle=1800
            )
            self.session_factory = sessionmaker(bind=self.database_engine)
            logger.info("Database connection established")
            
        except Exception as e:
            logger.error(f"Failed to initialize data processor: {e}")
            raise
    
    async def process_dataset_async(
        self, 
        dataset: List[Dict[str, Any]], 
        transformation_pipeline: List[Callable],
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Process a complete dataset using the specified transformation pipeline.
        
        Args:
            dataset: List of data items to process
            transformation_pipeline: List of transformation functions to apply
            progress_callback: Optional callback for progress updates
        
        Returns:
            Comprehensive results including processed data, statistics, and errors
        """
        start_time = datetime.now()
        logger.info(f"Starting dataset processing: {len(dataset)} items, "
                   f"{len(transformation_pipeline)} transformations")
        
        try:
            # Split dataset into batches for parallel processing
            batches = [
                dataset[i:i + self.config.batch_size]
                for i in range(0, len(dataset), self.config.batch_size)
            ]
            
            # Process batches concurrently with semaphore for resource control
            semaphore = asyncio.Semaphore(self.config.max_workers)
            tasks = []
            
            for batch_idx, batch in enumerate(batches):
                task = self._process_batch_with_semaphore(
                    semaphore, batch, transformation_pipeline, batch_idx
                )
                tasks.append(task)
            
            # Execute all batch processing tasks
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Aggregate results from all batches
            all_processed_items = []
            all_errors = []
            successful_batches = 0
            failed_batches = 0
            
            for batch_idx, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Batch {batch_idx} failed completely: {result}")
                    failed_batches += 1
                    all_errors.append({
                        'batch_idx': batch_idx,
                        'error_type': type(result).__name__,
                        'error_message': str(result),
                        'items_affected': len(batches[batch_idx])
                    })
                else:
                    successful_batches += 1
                    all_processed_items.extend(result.get('processed_items', []))
                    all_errors.extend(result.get('errors', []))
                    
                    # Update progress if callback provided
                    if progress_callback:
                        progress_callback(batch_idx + 1, len(batches))
            
            # Update global statistics
            processing_time = (datetime.now() - start_time).total_seconds()
            self.stats['items_processed'] += len(all_processed_items)
            self.stats['items_failed'] += len(all_errors)
            self.stats['batches_completed'] += successful_batches
            self.stats['total_processing_time'] += processing_time
            
            # Generate comprehensive result summary
            return {
                'success': True,
                'processed_items': all_processed_items,
                'total_items_processed': len(all_processed_items),
                'total_errors': len(all_errors),
                'error_details': all_errors,
                'successful_batches': successful_batches,
                'failed_batches': failed_batches,
                'total_batches': len(batches),
                'processing_time_seconds': processing_time,
                'items_per_second': len(all_processed_items) / processing_time if processing_time > 0 else 0,
                'batch_success_rate': successful_batches / len(batches) if batches else 0,
                'overall_stats': self.stats.copy(),
                'cache_performance': {
                    'hit_rate': self.stats['cache_hits'] / max(1, self.stats['cache_hits'] + self.stats['cache_misses']),
                    'total_cache_operations': self.stats['cache_hits'] + self.stats['cache_misses']
                }
            }
            
        except Exception as e:
            logger.error(f"Critical error in dataset processing: {e}")
            return {
                'success': False,
                'error_type': type(e).__name__,
                'error_message': str(e),
                'processed_items': [],
                'total_errors': len(dataset),
                'processing_time_seconds': (datetime.now() - start_time).total_seconds()
            }
    
    async def _process_batch_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        batch: List[Dict[str, Any]],
        transformation_pipeline: List[Callable],
        batch_idx: int
    ) -> Dict[str, Any]:
        """Process a single batch with semaphore-controlled concurrency."""
        async with semaphore:
            return await self._process_batch_with_retry(batch, transformation_pipeline, batch_idx)
    
    async def _process_batch_with_retry(
        self,
        batch: List[Dict[str, Any]],
        transformation_pipeline: List[Callable],
        batch_idx: int
    ) -> Dict[str, Any]:
        """Process a batch with retry logic for resilience."""
        last_exception = None
        
        for attempt in range(self.config.retry_attempts):
            try:
                logger.debug(f"Processing batch {batch_idx}, attempt {attempt + 1}")
                
                processed_items = []
                errors = []
                
                # Process each item in the batch
                for item_idx, item in enumerate(batch):
                    try:
                        processed_item = await self._process_single_item(
                            item, transformation_pipeline, f"{batch_idx}_{item_idx}"
                        )
                        processed_items.append(processed_item)
                        
                    except Exception as e:
                        logger.warning(f"Item {item_idx} in batch {batch_idx} failed: {e}")
                        errors.append({
                            'batch_idx': batch_idx,
                            'item_idx': item_idx,
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'original_item': item,
                            'attempt': attempt + 1
                        })
                
                return {
                    'processed_items': processed_items,
                    'errors': errors,
                    'batch_idx': batch_idx,
                    'successful_attempt': attempt + 1,
                    'items_processed': len(processed_items),
                    'items_failed': len(errors)
                }
                
            except Exception as e:
                last_exception = e
                logger.warning(f"Batch {batch_idx} attempt {attempt + 1} failed: {e}")
                if attempt < self.config.retry_attempts - 1:
                    # Exponential backoff with jitter
                    delay = (2 ** attempt) + np.random.uniform(0, 1)
                    await asyncio.sleep(delay)
        
        # All retry attempts failed
        raise last_exception or Exception(f"All retry attempts failed for batch {batch_idx}")
'''

        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
        temp_file.write(python_content)
        temp_file.close()
        temp_path = Path(temp_file.name)

        try:
            # Test end-to-end chunking
            chunks = chunker.chunk_file(temp_path)

            # Verify chunking worked correctly
            assert len(chunks) > 1, "Should produce multiple chunks for this large file"

            # Verify all chunks except last are exactly 1000 characters
            for i, chunk in enumerate(chunks[:-1]):
                assert (
                    len(chunk["text"]) == 1000
                ), f"Chunk {i} should be exactly 1000 chars, got {len(chunk['text'])}"

            # Verify Python-specific content is handled well
            python_constructs = 0
            for chunk in chunks:
                text = chunk["text"]
                # Look for Python-specific patterns
                if any(
                    pattern in text
                    for pattern in [
                        "def ",
                        "class ",
                        "import ",
                        "from ",
                        "async def",
                        "return ",
                        "if ",
                        "for ",
                        "while ",
                        "try:",
                        "except:",
                        "await ",
                        "async ",
                        "@dataclass",
                        "__init__",
                    ]
                ):
                    python_constructs += 1

            python_ratio = python_constructs / len(chunks)
            assert (
                python_ratio > 0.8
            ), f"Only {python_ratio:.1%} of chunks contain Python constructs"

            print(
                f"E2E Python test: {len(chunks)} chunks, "
                f"{python_constructs} with Python constructs ({python_ratio:.1%})"
            )

        finally:
            temp_path.unlink()  # Clean up

    def test_e2e_chunking_preserves_code_structure(self, chunker):
        """Test that chunking preserves important code structure across boundaries."""
        # Create a file with clear structural elements
        code_content = """
public class DatabaseManager {
    private static final String CONNECTION_URL = "jdbc:postgresql://localhost:5432/app";
    private static final int MAX_CONNECTIONS = 100;
    private static final int CONNECTION_TIMEOUT = 30000;
    
    private DataSource dataSource;
    private ConnectionPool connectionPool;
    private MetricsCollector metricsCollector;
    
    public DatabaseManager(DataSourceConfig config) {
        this.dataSource = createDataSource(config);
        this.connectionPool = new ConnectionPool(MAX_CONNECTIONS);
        this.metricsCollector = new MetricsCollector("database");
    }
    
    public CompletableFuture<List<User>> findUsersByEmail(String emailPattern) {
        return CompletableFuture.supplyAsync(() -> {
            String sql = "SELECT u.id, u.first_name, u.last_name, u.email, u.created_at, " +
                        "u.updated_at, u.status FROM users u WHERE u.email ILIKE ? ORDER BY u.email";
            
            try (Connection conn = connectionPool.getConnection();
                 PreparedStatement stmt = conn.prepareStatement(sql)) {
                
                stmt.setString(1, "%" + emailPattern + "%");
                
                try (ResultSet rs = stmt.executeQuery()) {
                    List<User> users = new ArrayList<>();
                    
                    while (rs.next()) {
                        User user = new User();
                        user.setId(rs.getLong("id"));
                        user.setFirstName(rs.getString("first_name"));
                        user.setLastName(rs.getString("last_name"));
                        user.setEmail(rs.getString("email"));
                        user.setCreatedAt(rs.getTimestamp("created_at").toLocalDateTime());
                        user.setUpdatedAt(rs.getTimestamp("updated_at").toLocalDateTime());
                        user.setStatus(UserStatus.valueOf(rs.getString("status")));
                        
                        users.add(user);
                    }
                    
                    metricsCollector.recordQuery("findUsersByEmail", users.size());
                    return users;
                }
                
            } catch (SQLException e) {
                metricsCollector.recordError("findUsersByEmail", e);
                throw new DataAccessException("Failed to find users by email pattern: " + emailPattern, e);
            }
        });
    }
    
    public boolean updateUserStatus(Long userId, UserStatus newStatus) {
        String sql = "UPDATE users SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?";
        
        try (Connection conn = connectionPool.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql)) {
            
            stmt.setString(1, newStatus.name());
            stmt.setLong(2, userId);
            
            int rowsUpdated = stmt.executeUpdate();
            boolean success = rowsUpdated > 0;
            
            if (success) {
                metricsCollector.recordUpdate("updateUserStatus", 1);
            } else {
                metricsCollector.recordWarning("updateUserStatus", "No rows updated for user: " + userId);
            }
            
            return success;
            
        } catch (SQLException e) {
            metricsCollector.recordError("updateUserStatus", e);
            throw new DataAccessException("Failed to update user status: " + userId, e);
        }
    }
}
"""

        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False)
        temp_file.write(code_content)
        temp_file.close()
        temp_path = Path(temp_file.name)

        try:
            chunks = chunker.chunk_file(temp_path)

            # Reconstruct content from chunks (removing overlaps)
            reconstructed = ""
            for i, chunk in enumerate(chunks):
                if i == 0:
                    reconstructed += chunk["text"]
                else:
                    # Skip the overlap (first 150 chars)
                    reconstructed += chunk["text"][150:]

            # Verify that important structures are preserved
            original_content = code_content.strip()
            reconstructed_content = reconstructed.strip()

            # Count key structural elements
            original_methods = original_content.count("public ")
            reconstructed_methods = reconstructed_content.count("public ")

            original_braces_open = original_content.count("{")
            original_braces_close = original_content.count("}")
            reconstructed_braces_open = reconstructed_content.count("{")
            reconstructed_braces_close = reconstructed_content.count("}")

            # Structure should be preserved
            assert original_methods == reconstructed_methods, (
                f"Method count changed: original {original_methods}, "
                f"reconstructed {reconstructed_methods}"
            )

            assert original_braces_open == reconstructed_braces_open, (
                f"Opening braces count changed: original {original_braces_open}, "
                f"reconstructed {reconstructed_braces_open}"
            )

            assert original_braces_close == reconstructed_braces_close, (
                f"Closing braces count changed: original {original_braces_close}, "
                f"reconstructed {reconstructed_braces_close}"
            )

            # Content length should be very similar (allowing for slight differences in whitespace)
            length_diff = abs(len(original_content) - len(reconstructed_content))
            length_diff_ratio = length_diff / len(original_content)

            assert length_diff_ratio < 0.01, (
                f"Content length differs too much: {length_diff} chars "
                f"({length_diff_ratio:.2%}) difference"
            )

            print(
                f"E2E structure preservation test: {len(chunks)} chunks, "
                f"structure preserved, length diff: {length_diff} chars"
            )

        finally:
            temp_path.unlink()  # Clean up

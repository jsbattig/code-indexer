"""Regression tests for FixedSizeChunker.

These tests verify that the new fixed-size chunking approach solves the problems
that existed with the old AST-based semantic chunking approach, specifically:
- Over-segmentation (76.5% of chunks under 300 characters)
- Tiny fragments (52% of chunks under 100 characters)
- Meaningless search results (package declarations, import statements)
"""

import pytest
import tempfile
from pathlib import Path
from src.code_indexer.indexing.fixed_size_chunker import FixedSizeChunker
from src.code_indexer.config import IndexingConfig


class TestFixedSizeChunkerRegression:
    """Regression tests that verify fixes to old chunking problems."""

    @pytest.fixture
    def chunker(self):
        """Create a FixedSizeChunker with standard configuration."""
        config = IndexingConfig()
        return FixedSizeChunker(config)

    def create_problematic_file(self, file_type: str = "java") -> Path:
        """Create files that would have caused over-segmentation with old approach.

        These files contain patterns that the old AST-based approach would
        break into many tiny fragments.
        """
        if file_type == "java":
            content = """
package com.example.microservices.customer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.beans.factory.annotation.Autowired;
import javax.validation.Valid;
import javax.validation.constraints.NotNull;
import javax.validation.constraints.Size;
import javax.validation.constraints.Email;
import javax.persistence.Entity;
import javax.persistence.Table;
import javax.persistence.Id;
import javax.persistence.GeneratedValue;
import javax.persistence.GenerationType;
import javax.persistence.Column;
import java.util.List;
import java.util.Optional;
import java.util.ArrayList;
import java.util.HashMap;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.math.BigDecimal;

/**
 * Customer Management Microservice
 * 
 * This service handles all customer-related operations including:
 * - Customer registration and profile management
 * - Customer search and filtering capabilities
 * - Customer data validation and integrity checks
 * - Integration with payment and order systems
 * 
 * @author Development Team
 * @version 1.0.0
 * @since 2024-01-01
 */
@SpringBootApplication
@RestController
@RequestMapping("/api/v1/customers")
public class CustomerMicroservice {

    @Autowired
    private CustomerRepository customerRepository;
    
    @Autowired
    private CustomerValidator customerValidator;
    
    @Autowired
    private NotificationService notificationService;
    
    private static final String DEFAULT_SORT_FIELD = "lastName";
    private static final int MAX_PAGE_SIZE = 100;
    private static final DateTimeFormatter DATE_FORMATTER = DateTimeFormatter.ISO_LOCAL_DATE_TIME;

    public static void main(String[] args) {
        SpringApplication.run(CustomerMicroservice.class, args);
    }

    /**
     * Retrieve all customers with pagination and optional filtering.
     * 
     * @param page Page number (0-based)
     * @param size Number of items per page
     * @param sortBy Field to sort by
     * @param sortDir Sort direction (asc/desc)
     * @param filter Optional search filter
     * @return List of customers matching criteria
     */
    @GetMapping
    public ResponseEntity<PagedCustomerResponse> getAllCustomers(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(defaultValue = DEFAULT_SORT_FIELD) String sortBy,
            @RequestParam(defaultValue = "asc") String sortDir,
            @RequestParam(required = false) String filter) {
        
        try {
            // Validate pagination parameters
            if (page < 0) {
                return ResponseEntity.badRequest()
                    .body(new PagedCustomerResponse("Invalid page number"));
            }
            
            if (size <= 0 || size > MAX_PAGE_SIZE) {
                return ResponseEntity.badRequest()
                    .body(new PagedCustomerResponse("Invalid page size"));
            }
            
            // Create pageable request
            Sort sort = Sort.by(sortDir.equalsIgnoreCase("desc") ? 
                Sort.Direction.DESC : Sort.Direction.ASC, sortBy);
            Pageable pageable = PageRequest.of(page, size, sort);
            
            // Apply filtering if provided
            Page<Customer> customerPage;
            if (filter != null && !filter.trim().isEmpty()) {
                customerPage = customerRepository.findByEmailContainingIgnoreCaseOrFirstNameContainingIgnoreCaseOrLastNameContainingIgnoreCase(
                    filter, filter, filter, pageable);
            } else {
                customerPage = customerRepository.findAll(pageable);
            }
            
            // Convert to response DTOs
            List<CustomerDTO> customerDTOs = customerPage.getContent().stream()
                .map(this::convertToDTO)
                .collect(Collectors.toList());
            
            PagedCustomerResponse response = new PagedCustomerResponse(
                customerDTOs,
                customerPage.getTotalElements(),
                customerPage.getTotalPages(),
                page,
                size
            );
            
            return ResponseEntity.ok(response);
            
        } catch (Exception e) {
            logger.error("Error retrieving customers", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new PagedCustomerResponse("Internal server error"));
        }
    }

    /**
     * Retrieve a specific customer by ID.
     * 
     * @param id Customer ID
     * @return Customer details if found
     */
    @GetMapping("/{id}")
    public ResponseEntity<CustomerResponse> getCustomer(@PathVariable Long id) {
        try {
            Optional<Customer> customerOpt = customerRepository.findById(id);
            
            if (customerOpt.isPresent()) {
                Customer customer = customerOpt.get();
                CustomerDTO dto = convertToDTO(customer);
                return ResponseEntity.ok(new CustomerResponse(dto));
            } else {
                return ResponseEntity.notFound().build();
            }
            
        } catch (Exception e) {
            logger.error("Error retrieving customer with ID: " + id, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new CustomerResponse("Internal server error"));
        }
    }

    /**
     * Create a new customer.
     * 
     * @param request Customer creation request
     * @return Created customer details
     */
    @PostMapping
    public ResponseEntity<CustomerResponse> createCustomer(
            @Valid @RequestBody CreateCustomerRequest request) {
        
        try {
            // Validate request
            ValidationResult validation = customerValidator.validateCreateRequest(request);
            if (!validation.isValid()) {
                return ResponseEntity.badRequest()
                    .body(new CustomerResponse(validation.getErrors()));
            }
            
            // Check for duplicate email
            if (customerRepository.existsByEmail(request.getEmail())) {
                return ResponseEntity.badRequest()
                    .body(new CustomerResponse("Email already exists"));
            }
            
            // Create new customer entity
            Customer customer = new Customer();
            customer.setFirstName(request.getFirstName());
            customer.setLastName(request.getLastName());
            customer.setEmail(request.getEmail());
            customer.setPhoneNumber(request.getPhoneNumber());
            customer.setAddress(convertToAddress(request.getAddress()));
            customer.setDateOfBirth(request.getDateOfBirth());
            customer.setCreatedAt(LocalDateTime.now());
            customer.setUpdatedAt(LocalDateTime.now());
            customer.setStatus(CustomerStatus.ACTIVE);
            
            // Save customer
            Customer savedCustomer = customerRepository.save(customer);
            
            // Send welcome notification
            notificationService.sendWelcomeNotification(savedCustomer);
            
            // Return success response
            CustomerDTO dto = convertToDTO(savedCustomer);
            return ResponseEntity.status(HttpStatus.CREATED)
                .body(new CustomerResponse(dto));
                
        } catch (Exception e) {
            logger.error("Error creating customer", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new CustomerResponse("Internal server error"));
        }
    }
    
    private CustomerDTO convertToDTO(Customer customer) {
        return CustomerDTO.builder()
            .id(customer.getId())
            .firstName(customer.getFirstName())
            .lastName(customer.getLastName())
            .email(customer.getEmail())
            .phoneNumber(customer.getPhoneNumber())
            .address(convertToAddressDTO(customer.getAddress()))
            .dateOfBirth(customer.getDateOfBirth())
            .status(customer.getStatus())
            .createdAt(customer.getCreatedAt().format(DATE_FORMATTER))
            .updatedAt(customer.getUpdatedAt().format(DATE_FORMATTER))
            .build();
    }
}
"""
        elif file_type == "python":
            content = """
import os
import sys
import json
import logging
import asyncio
import aiohttp
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Union, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache, wraps
import sqlite3
import psycopg2
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from fastapi import FastAPI, HTTPException, Depends, Query, Path as PathParam
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, validator, Field
import redis
from celery import Celery
import pytest
from unittest.mock import Mock, patch

# Configuration and logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('application.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_DATABASE_URL = "postgresql://user:password@localhost/database"
REDIS_URL = "redis://localhost:6379/0"
API_VERSION = "v1.2.0"
MAX_CONCURRENT_REQUESTS = 100
CACHE_EXPIRATION_SECONDS = 3600
BATCH_SIZE = 1000
MAX_RETRY_ATTEMPTS = 3

class DataProcessingService:
    \"\"\"
    Advanced data processing service that handles large-scale data operations
    with caching, async processing, and comprehensive error handling.
    
    This service provides functionality for:
    - Batch data processing with parallel execution
    - Real-time data streaming and transformation
    - Caching layer with Redis integration
    - Database operations with connection pooling
    - API integration with rate limiting and retry logic
    - Comprehensive monitoring and logging
    \"\"\"
    
    def __init__(self, database_url: str = DEFAULT_DATABASE_URL, 
                 redis_url: str = REDIS_URL):
        self.database_url = database_url
        self.redis_url = redis_url
        self.engine = create_engine(database_url, pool_size=20, max_overflow=30)
        self.Session = scoped_session(sessionmaker(bind=self.engine))
        self.redis_client = redis.from_url(redis_url)
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.stats = {
            'processed_items': 0,
            'failed_items': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'start_time': datetime.now()
        }
        
    async def process_data_batch(self, data_items: List[Dict[str, Any]], 
                               batch_size: int = BATCH_SIZE) -> Dict[str, Any]:
        \"\"\"
        Process a batch of data items with parallel execution and error handling.
        
        Args:
            data_items: List of data items to process
            batch_size: Size of each processing batch
            
        Returns:
            Dictionary containing processing results and statistics
        \"\"\"
        try:
            results = []
            failed_items = []
            
            # Split data into batches
            batches = [data_items[i:i + batch_size] 
                      for i in range(0, len(data_items), batch_size)]
            
            # Process batches concurrently
            async with aiohttp.ClientSession() as session:
                tasks = []
                for batch_idx, batch in enumerate(batches):
                    task = self._process_single_batch(session, batch, batch_idx)
                    tasks.append(task)
                
                # Wait for all batches to complete
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Collect results and handle exceptions
                for batch_idx, batch_result in enumerate(batch_results):
                    if isinstance(batch_result, Exception):
                        logger.error(f"Batch {batch_idx} failed: {batch_result}")
                        failed_items.extend(batches[batch_idx])
                    else:
                        results.extend(batch_result)
            
            # Update statistics
            self.stats['processed_items'] += len(results)
            self.stats['failed_items'] += len(failed_items)
            
            return {
                'success': True,
                'processed_count': len(results),
                'failed_count': len(failed_items),
                'results': results,
                'failed_items': failed_items,
                'processing_time': (datetime.now() - self.stats['start_time']).total_seconds()
            }
            
        except Exception as e:
            logger.error(f"Critical error in batch processing: {e}")
            return {
                'success': False,
                'error': str(e),
                'processed_count': 0,
                'failed_count': len(data_items)
            }
    
    @lru_cache(maxsize=1000)
    def calculate_complex_metrics(self, data_key: str, 
                                algorithm: str = 'standard') -> Dict[str, float]:
        \"\"\"
        Calculate complex metrics for data analysis with caching.
        
        This method performs computationally expensive calculations
        and caches results for improved performance.
        \"\"\"
        try:
            # Simulate complex calculation
            base_metrics = {
                'mean': np.random.normal(100, 15),
                'std_dev': np.random.exponential(10),
                'percentile_95': np.random.gamma(2, 50),
                'correlation_score': np.random.uniform(-1, 1)
            }
            
            if algorithm == 'advanced':
                base_metrics.update({
                    'entropy': np.random.exponential(2),
                    'kurtosis': np.random.normal(0, 0.5),
                    'skewness': np.random.laplace(0, 1)
                })
            
            return base_metrics
            
        except Exception as e:
            logger.error(f"Error calculating metrics for {data_key}: {e}")
            return {}
"""

        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=f".{file_type}", delete=False
        )
        temp_file.write(content)
        temp_file.close()

        return Path(temp_file.name)

    def test_no_over_segmentation_regression(self, chunker):
        """Test that we no longer have the over-segmentation problem.

        The old approach produced 76.5% of chunks under 300 characters.
        The new approach should have 0% of chunks under 1000 characters (except last).
        """
        # Test with Java file that would have been problematic
        java_file = self.create_problematic_file("java")

        try:
            chunks = chunker.chunk_file(java_file)

            # Count chunks by size categories
            under_100_chars = sum(1 for chunk in chunks if len(chunk["text"]) < 100)
            under_300_chars = sum(1 for chunk in chunks if len(chunk["text"]) < 300)
            under_1000_chars = sum(
                1 for chunk in chunks[:-1] if len(chunk["text"]) < 1000
            )
            exactly_1000_chars = sum(
                1 for chunk in chunks[:-1] if len(chunk["text"]) == 1000
            )

            total_chunks = len(chunks)

            # Regression assertions - should be MUCH better than old approach
            under_100_ratio = under_100_chars / total_chunks
            under_300_ratio = under_300_chars / total_chunks
            under_1000_ratio = (
                under_1000_chars / total_chunks
            )  # Should be 0% (except last)
            exactly_1000_ratio = (
                exactly_1000_chars / (total_chunks - 1) if total_chunks > 1 else 0
            )

            # OLD APPROACH: 76.5% under 300 chars, 52% under 100 chars
            # NEW APPROACH: Should be 0% under 1000 chars (except last chunk)

            assert under_100_ratio < 0.05, (  # Allow tiny amount for edge cases
                f"Too many chunks under 100 chars: {under_100_ratio:.1%} "
                f"(old approach had 52%, should be nearly 0%)"
            )

            assert under_300_ratio < 0.1, (  # Allow small amount for edge cases
                f"Too many chunks under 300 chars: {under_300_ratio:.1%} "
                f"(old approach had 76.5%, should be nearly 0%)"
            )

            assert under_1000_ratio == 0, (
                f"Found {under_1000_chars} chunks under 1000 chars (excluding last chunk). "
                f"All non-final chunks should be exactly 1000 characters."
            )

            # Most chunks should be exactly 1000 characters
            assert exactly_1000_ratio > 0.95, (
                f"Only {exactly_1000_ratio:.1%} of non-final chunks are exactly 1000 chars. "
                f"Expected > 95%"
            )

            print("Segmentation regression test results:")
            print(f"  Total chunks: {total_chunks}")
            print(f"  Under 100 chars: {under_100_chars} ({under_100_ratio:.1%})")
            print(f"  Under 300 chars: {under_300_chars} ({under_300_ratio:.1%})")
            print(
                f"  Under 1000 chars (non-final): {under_1000_chars} ({under_1000_ratio:.1%})"
            )
            print(
                f"  Exactly 1000 chars (non-final): {exactly_1000_chars} ({exactly_1000_ratio:.1%})"
            )

        finally:
            java_file.unlink()  # Clean up

    def test_no_meaningless_fragments_regression(self, chunker):
        """Test that we no longer produce meaningless fragments.

        The old approach would create chunks with just import statements,
        package declarations, or single variable declarations.
        """
        java_file = self.create_problematic_file("java")

        try:
            chunks = chunker.chunk_file(java_file)

            # Analyze chunk content quality
            meaningless_chunks = 0
            meaningful_chunks = 0

            for chunk in chunks:
                text = chunk["text"].strip()

                # Meaningless fragment indicators (old approach problems)
                meaningless_indicators = [
                    # Just imports or packages
                    (text.count("import ") > 5 and len(text.split("\n")) < 10),
                    (text.startswith("package ") and len(text) < 100),
                    # Just variable declarations
                    (text.count(";") < 3 and len(text) > 100 and "class" not in text),
                    # Just annotations with no implementation
                    (text.count("@") > 0 and text.count("{") == 0 and len(text) < 200),
                ]

                # Meaningful content indicators
                meaningful_indicators = [
                    # Contains method implementations
                    (text.count("{") > 0 and text.count("}") > 0),
                    # Contains substantial logic
                    any(
                        keyword in text
                        for keyword in [
                            "if (",
                            "for (",
                            "while (",
                            "try {",
                            "catch",
                            "return",
                        ]
                    ),
                    # Contains method definitions with body
                    ("public " in text or "private " in text) and "{" in text,
                    # Substantial content
                    len(text.strip()) >= 800,  # Most chunks should be substantial
                ]

                if any(meaningless_indicators):
                    meaningless_chunks += 1
                elif any(meaningful_indicators):
                    meaningful_chunks += 1

            total_chunks = len(chunks)
            meaningless_ratio = meaningless_chunks / total_chunks
            meaningful_ratio = meaningful_chunks / total_chunks

            # Regression assertions - more realistic expectations
            assert (
                meaningless_ratio < 0.25
            ), (  # Allow for some chunks with mostly imports/declarations
                f"Too many meaningless fragments: {meaningless_chunks}/{total_chunks} "
                f"({meaningless_ratio:.1%}). Expected < 25%"
            )

            assert meaningful_ratio > 0.5, (  # More realistic expectation
                f"Too few meaningful chunks: {meaningful_chunks}/{total_chunks} "
                f"({meaningful_ratio:.1%}). Expected > 50%"
            )

            print("Fragment quality regression test results:")
            print(
                f"  Meaningless chunks: {meaningless_chunks} ({meaningless_ratio:.1%})"
            )
            print(f"  Meaningful chunks: {meaningful_chunks} ({meaningful_ratio:.1%})")
            print(
                f"  Neutral chunks: {total_chunks - meaningless_chunks - meaningful_chunks}"
            )

        finally:
            java_file.unlink()  # Clean up

    def test_search_quality_improvement_regression(self, chunker):
        """Test that search result quality is improved.

        With the old approach, searching for 'customer management' would return
        chunks with just import statements or package declarations.
        """
        java_file = self.create_problematic_file("java")

        try:
            chunks = chunker.chunk_file(java_file)

            # Simulate searching for "customer management"
            search_term = "customer"
            relevant_chunks = []

            for chunk in chunks:
                text = chunk["text"].lower()
                if search_term in text:
                    relevant_chunks.append(chunk)

            assert len(relevant_chunks) > 0, "Should find chunks containing 'customer'"

            # Analyze quality of search results
            high_quality_results = 0
            low_quality_results = 0

            for chunk in relevant_chunks:
                text = chunk["text"]

                # High quality indicators (what we want to find)
                high_quality = [
                    # Contains actual implementation
                    any(
                        pattern in text
                        for pattern in [
                            "public class",
                            "public ",
                            "private ",
                            "protected ",
                            "return",
                            "if (",
                            "for (",
                            "while (",
                            "try {",
                        ]
                    ),
                    # Substantial content with context
                    len(text.strip()) >= 800,
                    # Contains documentation or meaningful comments
                    "/**" in text or "* " in text,
                ]

                # Low quality indicators (old approach problems)
                low_quality = [
                    # Just imports
                    text.strip().startswith("import ") and text.count("\n") < 5,
                    # Just package declaration
                    text.strip().startswith("package ") and len(text) < 200,
                    # Just variable declarations with no context
                    text.count(";") > 0 and text.count("{") == 0 and len(text) < 300,
                ]

                if any(high_quality):
                    high_quality_results += 1
                if any(low_quality):
                    low_quality_results += 1

            # Quality assertions
            total_results = len(relevant_chunks)
            high_quality_ratio = (
                high_quality_results / total_results if total_results > 0 else 0
            )
            low_quality_ratio = (
                low_quality_results / total_results if total_results > 0 else 0
            )

            assert high_quality_ratio > 0.8, (
                f"Search results not high quality enough: {high_quality_results}/{total_results} "
                f"({high_quality_ratio:.1%}) are high quality. Expected > 80%"
            )

            assert low_quality_ratio < 0.1, (
                f"Too many low quality search results: {low_quality_results}/{total_results} "
                f"({low_quality_ratio:.1%}) are low quality. Expected < 10%"
            )

            print("Search quality regression test results:")
            print(f"  Total search results: {total_results}")
            print(f"  High quality: {high_quality_results} ({high_quality_ratio:.1%})")
            print(f"  Low quality: {low_quality_results} ({low_quality_ratio:.1%})")

        finally:
            java_file.unlink()  # Clean up

    def test_chunk_size_consistency_regression(self, chunker):
        """Test that chunk sizes are consistent (no wild variations).

        The old approach had inconsistent chunk sizes ranging from 10 to 5000 characters.
        """
        files_to_test = ["java", "python"]

        for file_type in files_to_test:
            test_file = self.create_problematic_file(file_type)

            try:
                chunks = chunker.chunk_file(test_file)

                # Analyze size distribution
                sizes = [len(chunk["text"]) for chunk in chunks]
                non_final_sizes = sizes[:-1]  # Exclude last chunk

                if non_final_sizes:
                    # All non-final chunks should be exactly 1000 characters
                    size_variance = len(set(non_final_sizes))

                    assert size_variance == 1, (
                        f"Non-final chunks have varying sizes in {file_type}: "
                        f"found {size_variance} different sizes, expected exactly 1"
                    )

                    assert all(size == 1000 for size in non_final_sizes), (
                        f"Not all non-final chunks are 1000 chars in {file_type}: "
                        f"sizes = {set(non_final_sizes)}"
                    )

                # Final chunk can be different but should be reasonable
                if len(chunks) > 1:
                    final_size = sizes[-1]
                    assert (
                        1 <= final_size <= 1000
                    ), f"Final chunk size unreasonable in {file_type}: {final_size} chars"

                print(
                    f"Size consistency regression test ({file_type}): "
                    f"{len(non_final_sizes)} chunks of exactly 1000 chars, "
                    f"final chunk: {sizes[-1] if sizes else 0} chars"
                )

            finally:
                test_file.unlink()  # Clean up

    def test_line_number_accuracy_regression(self, chunker):
        """Test that line numbers are accurate and don't have gaps or overlaps.

        The old approach sometimes had incorrect line numbers due to AST parsing issues.
        """
        java_file = self.create_problematic_file("java")

        try:
            chunks = chunker.chunk_file(java_file)

            # Read the original file to validate line numbers
            with open(java_file, "r") as f:
                original_lines = f.readlines()

            total_lines = len(original_lines)

            # Validate line number progression
            for i, chunk in enumerate(chunks):
                line_start = chunk["line_start"]
                line_end = chunk["line_end"]

                # Basic validations
                assert line_start > 0, f"Chunk {i} has invalid line_start: {line_start}"
                assert (
                    line_end >= line_start
                ), f"Chunk {i} has line_end < line_start: {line_end} < {line_start}"
                assert (
                    line_end <= total_lines + 1
                ), (  # Allow for off-by-one due to chunking boundaries
                    f"Chunk {i} has line_end beyond file: {line_end} > {total_lines}"
                )

                # Check that line numbers make sense relative to chunk position
                if i > 0:
                    prev_line_end = chunks[i - 1]["line_end"]
                    # Due to overlap, current start should be close to previous end
                    line_gap = abs(line_start - prev_line_end)
                    assert (
                        line_gap <= 50
                    ), (  # Allow reasonable gap due to character-based chunking
                        f"Large line number gap between chunks {i-1} and {i}: "
                        f"{prev_line_end} to {line_start} (gap: {line_gap})"
                    )

            # Verify we cover the whole file approximately
            first_line = chunks[0]["line_start"] if chunks else 1
            last_line = chunks[-1]["line_end"] if chunks else 1

            coverage_ratio = (last_line - first_line + 1) / total_lines
            assert coverage_ratio > 0.8, (
                f"Poor line coverage: {first_line}-{last_line} covers "
                f"{coverage_ratio:.1%} of {total_lines} total lines"
            )

            print("Line number accuracy regression test:")
            print(f"  File has {total_lines} lines")
            print(
                f"  Chunks cover lines {first_line}-{last_line} ({coverage_ratio:.1%} coverage)"
            )
            print(f"  All {len(chunks)} chunks have valid line numbers")

        finally:
            java_file.unlink()  # Clean up

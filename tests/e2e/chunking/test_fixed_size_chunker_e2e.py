"""End-to-end tests for FixedSizeChunker within the full processing pipeline.

These tests verify that the fixed-size chunker works correctly when integrated
with the DocumentProcessor and the entire indexing workflow.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from src.code_indexer.indexing.fixed_size_chunker import FixedSizeChunker
from src.code_indexer.indexing.processor import DocumentProcessor
from src.code_indexer.config import Config, IndexingConfig
from src.code_indexer.services.vector_calculation_manager import VectorResult


class TestFixedSizeChunkerE2E:
    """End-to-end tests for FixedSizeChunker in full processing pipeline."""

    @pytest.fixture
    def temp_codebase_dir(self):
        """Create a temporary codebase directory with test files."""
        temp_dir = Path(tempfile.mkdtemp())

        # Create a Java file
        java_file = temp_dir / "TestService.java"
        java_file.write_text(
            """
package com.example.service;

import java.util.List;
import java.util.ArrayList;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;

/**
 * Test service for end-to-end chunking verification.
 * This service demonstrates various Java constructs that should be
 * properly chunked by the fixed-size chunker without over-segmentation.
 */
@Service
public class TestService {
    
    @Autowired
    private DataRepository dataRepository;
    
    @Autowired
    private ValidationService validationService;
    
    private static final String DEFAULT_STATUS = "ACTIVE";
    private static final int MAX_BATCH_SIZE = 100;
    
    /**
     * Process a batch of items with comprehensive error handling.
     * This method demonstrates complex business logic that should
     * remain together in meaningful chunks.
     */
    public ProcessingResult processBatch(List<InputItem> items) {
        try {
            // Input validation
            if (items == null || items.isEmpty()) {
                return ProcessingResult.failure("No items to process");
            }
            
            if (items.size() > MAX_BATCH_SIZE) {
                return ProcessingResult.failure("Batch size exceeds maximum");
            }
            
            // Validate each item
            List<ValidationError> errors = new ArrayList<>();
            for (InputItem item : items) {
                ValidationResult validation = validationService.validate(item);
                if (!validation.isValid()) {
                    errors.addAll(validation.getErrors());
                }
            }
            
            if (!errors.isEmpty()) {
                return ProcessingResult.failure("Validation failed", errors);
            }
            
            // Process items
            List<ProcessedItem> processedItems = new ArrayList<>();
            int successCount = 0;
            int failureCount = 0;
            
            for (InputItem item : items) {
                try {
                    ProcessedItem processed = processItem(item);
                    processedItems.add(processed);
                    successCount++;
                } catch (ProcessingException e) {
                    logger.error("Failed to process item: " + item.getId(), e);
                    failureCount++;
                }
            }
            
            // Save processed items
            if (!processedItems.isEmpty()) {
                dataRepository.saveAll(processedItems);
            }
            
            return ProcessingResult.success(
                successCount, failureCount, processedItems);
                
        } catch (Exception e) {
            logger.error("Critical error in batch processing", e);
            return ProcessingResult.failure("Internal processing error");
        }
    }
    
    private ProcessedItem processItem(InputItem item) throws ProcessingException {
        // Complex item processing logic
        ProcessedItem processed = new ProcessedItem();
        processed.setId(item.getId());
        processed.setData(transformData(item.getData()));
        processed.setStatus(DEFAULT_STATUS);
        processed.setProcessedAt(LocalDateTime.now());
        
        // Apply business rules
        if (item.getType() == ItemType.PREMIUM) {
            processed = applyPremiumProcessing(processed);
        } else if (item.getType() == ItemType.STANDARD) {
            processed = applyStandardProcessing(processed);
        }
        
        return processed;
    }
    
    private ProcessedItem applyPremiumProcessing(ProcessedItem item) {
        item.setPriority(Priority.HIGH);
        item.setExpirationDays(365);
        item.addFeature("premium_support");
        item.addFeature("priority_handling");
        return item;
    }
    
    private ProcessedItem applyStandardProcessing(ProcessedItem item) {
        item.setPriority(Priority.NORMAL);
        item.setExpirationDays(90);
        item.addFeature("standard_support");
        return item;
    }
    
    private String transformData(String inputData) {
        if (inputData == null || inputData.trim().isEmpty()) {
            return "";
        }
        
        // Complex transformation logic
        StringBuilder result = new StringBuilder();
        String[] parts = inputData.split(",");
        
        for (int i = 0; i < parts.length; i++) {
            String part = parts[i].trim();
            if (!part.isEmpty()) {
                if (i > 0) {
                    result.append("|");
                }
                result.append(part.toUpperCase());
            }
        }
        
        return result.toString();
    }
}
"""
        )

        # Create a Python file
        python_file = temp_dir / "data_processor.py"
        python_file.write_text(
            """
import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import json

logger = logging.getLogger(__name__)


@dataclass
class ProcessingConfig:
    \"\"\"Configuration for data processing operations.\"\"\"
    batch_size: int = 100
    max_retries: int = 3
    timeout_seconds: int = 30
    enable_caching: bool = True


class DataProcessor:
    \"\"\"
    Advanced data processor with async capabilities.
    
    This processor handles large-scale data operations with:
    - Asynchronous batch processing
    - Comprehensive error handling and retries
    - Performance monitoring and logging
    - Configurable caching layer
    \"\"\"
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.stats = {
            'processed_items': 0,
            'failed_items': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'start_time': datetime.now()
        }
        self.cache = {} if config.enable_caching else None
        
    async def process_data_async(self, data_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        \"\"\"
        Process data items asynchronously with batching and error handling.
        
        Args:
            data_items: List of data items to process
            
        Returns:
            Processing results with statistics and processed data
        \"\"\"
        try:
            logger.info(f"Starting async processing of {len(data_items)} items")
            
            # Split into batches
            batches = [
                data_items[i:i + self.config.batch_size] 
                for i in range(0, len(data_items), self.config.batch_size)
            ]
            
            # Process batches concurrently
            tasks = [
                self._process_batch_with_retry(batch, batch_idx) 
                for batch_idx, batch in enumerate(batches)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Collect results
            all_processed = []
            total_errors = []
            
            for batch_idx, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Batch {batch_idx} failed completely: {result}")
                    total_errors.append({
                        'batch_idx': batch_idx,
                        'error': str(result),
                        'items_affected': len(batches[batch_idx])
                    })
                else:
                    all_processed.extend(result.get('processed', []))
                    total_errors.extend(result.get('errors', []))
            
            # Update statistics
            self.stats['processed_items'] += len(all_processed)
            self.stats['failed_items'] += len(total_errors)
            
            processing_time = (datetime.now() - self.stats['start_time']).total_seconds()
            
            return {
                'success': True,
                'processed_items': all_processed,
                'error_count': len(total_errors),
                'errors': total_errors,
                'processing_time_seconds': processing_time,
                'items_per_second': len(all_processed) / processing_time if processing_time > 0 else 0,
                'cache_hit_ratio': self.stats['cache_hits'] / max(1, self.stats['cache_hits'] + self.stats['cache_misses']),
                'stats': self.stats.copy()
            }
            
        except Exception as e:
            logger.error(f"Critical error in async processing: {e}")
            return {
                'success': False,
                'error': str(e),
                'processed_items': [],
                'error_count': len(data_items)
            }
    
    async def _process_batch_with_retry(self, batch: List[Dict[str, Any]], batch_idx: int) -> Dict[str, Any]:
        \"\"\"Process a batch with retry logic.\"\"\"
        for attempt in range(self.config.max_retries):
            try:
                logger.debug(f"Processing batch {batch_idx}, attempt {attempt + 1}")
                
                processed_items = []
                errors = []
                
                for item_idx, item in enumerate(batch):
                    try:
                        processed = await self._process_single_item(item)
                        processed_items.append(processed)
                    except Exception as e:
                        logger.warning(f"Item {item_idx} in batch {batch_idx} failed: {e}")
                        errors.append({
                            'item_idx': item_idx,
                            'batch_idx': batch_idx,
                            'error': str(e),
                            'item_data': item
                        })
                
                return {
                    'processed': processed_items,
                    'errors': errors,
                    'batch_idx': batch_idx,
                    'attempt': attempt + 1
                }
                
            except Exception as e:
                logger.warning(f"Batch {batch_idx} attempt {attempt + 1} failed: {e}")
                if attempt == self.config.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    async def _process_single_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        \"\"\"Process a single data item with caching.\"\"\"
        item_id = item.get('id', 'unknown')
        
        # Check cache
        if self.cache and item_id in self.cache:
            self.stats['cache_hits'] += 1
            return self.cache[item_id]
        
        self.stats['cache_misses'] += 1
        
        # Simulate processing time
        await asyncio.sleep(0.001)  # 1ms processing time
        
        # Transform the item
        processed = {
            'id': item_id,
            'original_data': item,
            'processed_at': datetime.now().isoformat(),
            'transformations_applied': [],
            'metadata': {}
        }
        
        # Apply transformations based on item type
        if item.get('type') == 'financial':
            processed = await self._apply_financial_transformations(processed)
        elif item.get('type') == 'personal':
            processed = await self._apply_personal_data_transformations(processed)
        else:
            processed = await self._apply_default_transformations(processed)
        
        # Cache result
        if self.cache:
            self.cache[item_id] = processed
        
        return processed
    
    async def _apply_financial_transformations(self, item: Dict[str, Any]) -> Dict[str, Any]:
        \"\"\"Apply financial data specific transformations.\"\"\"
        item['transformations_applied'].extend([
            'currency_normalization',
            'fraud_detection',
            'compliance_check'
        ])
        item['metadata']['risk_score'] = 0.1
        item['metadata']['compliance_status'] = 'verified'
        return item
"""
        )

        yield temp_dir

        # Cleanup
        import shutil

        shutil.rmtree(temp_dir)

    @pytest.fixture
    def mock_config(self, temp_codebase_dir):
        """Create a mock configuration for testing."""
        config = Mock(spec=Config)
        config.codebase_dir = temp_codebase_dir
        config.indexing = Mock(spec=IndexingConfig)
        config.exclude_dirs = ["node_modules", "venv", "__pycache__", ".git"]
        config.include_extensions = ["java", "py", "js", "ts"]
        config.gitignore_file = temp_codebase_dir / ".gitignore"
        return config

    @pytest.fixture
    def mock_embedding_provider(self):
        """Create a mock embedding provider."""
        provider = Mock()
        provider.get_embeddings.return_value = [
            [0.1] * 384 for _ in range(10)
        ]  # Mock embeddings
        return provider

    @pytest.fixture
    def mock_vector_store_client(self):
        """Create a mock vector store client."""
        client = Mock()
        client.upsert_points.return_value = True

        # Mock create_point to return a dictionary with expected structure
        def create_point(vector, payload, embedding_model):
            return {"embedding": vector, "metadata": payload, "model": embedding_model}

        client.create_point.side_effect = create_point

        return client

    def test_fixed_size_chunker_in_document_processor(
        self, mock_config, mock_embedding_provider, mock_vector_store_client
    ):
        """Test that FixedSizeChunker works correctly within DocumentProcessor."""
        # Create processor with mocked dependencies
        processor = DocumentProcessor(
            config=mock_config,
            embedding_provider=mock_embedding_provider,
            vector_store_client=mock_vector_store_client,
        )

        # Verify that the processor uses FixedSizeChunker
        assert isinstance(processor.fixed_size_chunker, FixedSizeChunker)

        # Test chunking a file through the processor
        java_file = mock_config.codebase_dir / "TestService.java"

        # Mock the vector calculation manager
        with patch(
            "src.code_indexer.indexing.processor.VectorCalculationManager"
        ) as MockVectorManager:
            mock_vector_manager = Mock()
            MockVectorManager.return_value = mock_vector_manager

            # Mock the submit_chunk method to return a future with dynamic metadata
            def create_mock_future(text, metadata):
                """Create a mock future with proper metadata from actual chunking."""
                mock_future = Mock()
                mock_future.result.return_value = VectorResult(
                    task_id="test_task",
                    embeddings=((0.1,) * 384,),  # Use batch format with immutable tuple
                    metadata=metadata,  # Use the actual metadata passed by the processor
                    processing_time=0.001,
                    error=None,
                )
                return mock_future

            mock_vector_manager.submit_chunk.side_effect = create_mock_future

            # Call the file processing method
            chunks = processor.process_file_parallel(java_file, mock_vector_manager)

            # Verify chunks were created
            assert len(chunks) > 0

            # Verify chunk structure
            for chunk in chunks:
                assert "embedding" in chunk
                assert "metadata" in chunk

            # Verify that chunks follow fixed-size chunking rules
            non_final_chunks = chunks[:-1] if len(chunks) > 1 else []
            for i, chunk in enumerate(non_final_chunks):
                metadata = chunk["metadata"]
                # The content should have been 1000 chars (in the chunker)
                # But we can't verify that directly here since it's processed
                assert "chunk_index" in metadata
                assert "total_chunks" in metadata
                assert metadata["chunk_index"] == i
                assert metadata["total_chunks"] == len(chunks)

    def test_end_to_end_chunking_metadata_consistency(
        self, mock_config, mock_embedding_provider, mock_vector_store_client
    ):
        """Test that chunking metadata is consistent throughout the processing pipeline."""
        processor = DocumentProcessor(
            config=mock_config,
            embedding_provider=mock_embedding_provider,
            vector_store_client=mock_vector_store_client,
        )

        # Test with Python file
        python_file = mock_config.codebase_dir / "data_processor.py"

        with patch(
            "src.code_indexer.indexing.processor.VectorCalculationManager"
        ) as MockVectorManager:
            mock_vector_manager = Mock()
            MockVectorManager.return_value = mock_vector_manager

            # Collect all submitted chunks
            submitted_chunks = []

            def mock_submit_chunk(text, metadata):
                submitted_chunks.append({"text": text, "metadata": metadata})
                mock_future = Mock()
                mock_future.result.return_value = VectorResult(
                    task_id="test_task",
                    embeddings=((0.1,) * 384,),  # Use batch format with immutable tuple
                    metadata=metadata,
                    processing_time=0.001,
                    error=None,
                )
                return mock_future

            mock_vector_manager.submit_chunk.side_effect = mock_submit_chunk

            # Process the file
            processor.process_file_parallel(python_file, mock_vector_manager)

            # Verify metadata consistency
            assert len(submitted_chunks) > 0

            for i, submitted in enumerate(submitted_chunks):
                text = submitted["text"]
                metadata = submitted["metadata"]

                # Verify chunk text follows fixed-size rules
                if i < len(submitted_chunks) - 1:  # Not the last chunk
                    assert (
                        len(text) == 1000
                    ), f"Chunk {i} should be exactly 1000 chars, got {len(text)}"
                else:  # Last chunk
                    assert (
                        0 < len(text) <= 1000
                    ), f"Last chunk should be 1-1000 chars, got {len(text)}"

                # Verify metadata completeness
                required_fields = [
                    "path",
                    "language",
                    "chunk_index",
                    "total_chunks",
                    "indexed_at",
                    "content",
                    "line_start",
                    "line_end",
                ]
                for field in required_fields:
                    assert field in metadata, f"Missing metadata field: {field}"

                # Verify metadata values
                assert metadata["chunk_index"] == i
                assert metadata["total_chunks"] == len(submitted_chunks)
                assert metadata["language"] == "py"
                assert metadata["content"] == text
                assert metadata["line_start"] > 0
                assert metadata["line_end"] >= metadata["line_start"]
                # Note: semantic_chunking field is not set by fixed-size chunker

    def test_chunking_overlap_in_processing_pipeline(
        self, mock_config, mock_embedding_provider, mock_vector_store_client
    ):
        """Test that chunk overlap is preserved through the entire processing pipeline."""
        processor = DocumentProcessor(
            config=mock_config,
            embedding_provider=mock_embedding_provider,
            vector_store_client=mock_vector_store_client,
        )

        java_file = mock_config.codebase_dir / "TestService.java"

        with patch(
            "src.code_indexer.indexing.processor.VectorCalculationManager"
        ) as MockVectorManager:
            mock_vector_manager = Mock()
            MockVectorManager.return_value = mock_vector_manager

            # Collect submitted chunk texts
            chunk_texts = []

            def mock_submit_chunk(text, metadata):
                chunk_texts.append(text)
                mock_future = Mock()
                mock_future.result.return_value = VectorResult(
                    task_id="test_task",
                    embeddings=((0.1,) * 384,),  # Use batch format with immutable tuple
                    metadata=metadata,
                    processing_time=0.001,
                    error=None,
                )
                return mock_future

            mock_vector_manager.submit_chunk.side_effect = mock_submit_chunk

            # Process the file
            processor.process_file_parallel(java_file, mock_vector_manager)

            # Verify overlap between consecutive chunks
            if len(chunk_texts) >= 2:
                for i in range(len(chunk_texts) - 1):
                    current_chunk = chunk_texts[i]
                    next_chunk = chunk_texts[i + 1]

                    # Verify current chunk is 1000 characters
                    assert (
                        len(current_chunk) == 1000
                    ), f"Chunk {i} should be 1000 chars, got {len(current_chunk)}"

                    # Verify 150-character overlap
                    current_ending = current_chunk[-150:]
                    next_beginning = next_chunk[:150]

                    assert (
                        current_ending == next_beginning
                    ), f"Overlap mismatch between chunks {i} and {i+1} in processing pipeline"

    def test_chunking_performance_in_pipeline(
        self, mock_config, mock_embedding_provider, mock_vector_store_client
    ):
        """Test that chunking performance is acceptable within the full pipeline."""
        import time

        processor = DocumentProcessor(
            config=mock_config,
            embedding_provider=mock_embedding_provider,
            vector_store_client=mock_vector_store_client,
        )

        # Test with both files
        test_files = [
            mock_config.codebase_dir / "TestService.java",
            mock_config.codebase_dir / "data_processor.py",
        ]

        total_chunks = 0
        total_time = 0.0

        with patch(
            "src.code_indexer.indexing.processor.VectorCalculationManager"
        ) as MockVectorManager:
            mock_vector_manager = Mock()
            MockVectorManager.return_value = mock_vector_manager

            # Mock fast vector calculation with dynamic metadata
            def create_mock_future(text, metadata):
                """Create a mock future with proper metadata from actual chunking."""
                mock_future = Mock()
                mock_future.result.return_value = VectorResult(
                    task_id="test_task",
                    embeddings=((0.1,) * 384,),  # Use batch format with immutable tuple
                    metadata=metadata,  # Use the actual metadata passed by the processor
                    processing_time=0.001,
                    error=None,
                )
                return mock_future

            mock_vector_manager.submit_chunk.side_effect = create_mock_future

            for file_path in test_files:
                start_time = time.perf_counter()

                chunks = processor.process_file_parallel(file_path, mock_vector_manager)

                end_time = time.perf_counter()
                file_time = end_time - start_time

                total_chunks += len(chunks)
                total_time = float(total_time) + file_time

                # Per-file performance assertions
                assert (
                    file_time < 1.0
                ), f"Processing {file_path.name} took {file_time:.3f}s, expected < 1.0s"

                chunks_per_second = (
                    len(chunks) / file_time if file_time > 0 else float("inf")
                )
                assert chunks_per_second > 100, (
                    f"Processing rate too slow for {file_path.name}: "
                    f"{chunks_per_second:.0f} chunks/sec, expected > 100"
                )

        # Overall performance
        overall_rate = total_chunks / total_time if total_time > 0 else float("inf")
        assert (
            overall_rate > 100
        ), f"Overall processing rate too slow: {overall_rate:.0f} chunks/sec"

        print(
            f"Pipeline performance: {total_chunks} chunks in {total_time:.3f}s "
            f"({overall_rate:.0f} chunks/sec)"
        )

    def test_error_handling_in_chunking_pipeline(
        self, mock_config, mock_embedding_provider, mock_vector_store_client
    ):
        """Test error handling when chunking fails within the pipeline."""
        processor = DocumentProcessor(
            config=mock_config,
            embedding_provider=mock_embedding_provider,
            vector_store_client=mock_vector_store_client,
        )

        # Create a file that might cause issues
        problematic_file = mock_config.codebase_dir / "problematic.java"
        problematic_file.write_text("a" * 10_000)  # Very large, simple content

        with patch(
            "src.code_indexer.indexing.processor.VectorCalculationManager"
        ) as MockVectorManager:
            mock_vector_manager = Mock()
            MockVectorManager.return_value = mock_vector_manager

            # Mock successful chunking but failed embedding
            def mock_submit_chunk(text, metadata):
                # Simulate some chunks failing
                mock_future = Mock()
                if len(text) > 500:  # Arbitrary condition
                    mock_future.result.side_effect = Exception("Embedding failed")
                else:
                    mock_future.result.return_value = VectorResult(
                        task_id="test_task",
                        embeddings=(
                            (0.1,) * 384,
                        ),  # Use batch format with immutable tuple
                        metadata=metadata,
                        processing_time=0.001,
                        error=None,
                    )
                return mock_future

            mock_vector_manager.submit_chunk.side_effect = mock_submit_chunk

            # Process should handle errors gracefully
            try:
                chunks = processor.process_file_parallel(
                    problematic_file, mock_vector_manager
                )
                # Should not crash, but may have fewer successful chunks
                assert isinstance(chunks, list)
            except Exception as e:
                # If it does raise an exception, it should be informative
                assert "Embedding failed" in str(e) or "processing" in str(e).lower()

    def test_chunker_integration_with_file_types(
        self, mock_config, mock_embedding_provider, mock_vector_store_client
    ):
        """Test that the chunker handles different file types correctly in the pipeline."""
        processor = DocumentProcessor(
            config=mock_config,
            embedding_provider=mock_embedding_provider,
            vector_store_client=mock_vector_store_client,
        )

        # Test files
        files_to_test = [("TestService.java", "java"), ("data_processor.py", "py")]

        with patch(
            "src.code_indexer.indexing.processor.VectorCalculationManager"
        ) as MockVectorManager:
            mock_vector_manager = Mock()
            MockVectorManager.return_value = mock_vector_manager

            submitted_data = []

            def mock_submit_chunk(text, metadata):
                submitted_data.append({"text": text, "metadata": metadata})
                mock_future = Mock()
                mock_future.result.return_value = VectorResult(
                    task_id="test_task",
                    embeddings=((0.1,) * 384,),  # Use batch format with immutable tuple
                    metadata=metadata,
                    processing_time=0.001,
                    error=None,
                )
                return mock_future

            mock_vector_manager.submit_chunk.side_effect = mock_submit_chunk

            for filename, expected_extension in files_to_test:
                submitted_data.clear()
                file_path = mock_config.codebase_dir / filename

                processor.process_file_parallel(file_path, mock_vector_manager)

                assert len(submitted_data) > 0, f"No chunks created for {filename}"

                # Verify file extension is correctly set
                for data in submitted_data:
                    metadata = data["metadata"]
                    assert metadata["language"] == expected_extension, (
                        f"Wrong language for {filename}: got {metadata['language']}, "
                        f"expected {expected_extension}"
                    )

                    # Verify path is correctly set
                    assert (
                        filename in metadata["path"]
                    ), f"Path metadata incorrect for {filename}: {metadata['path']}"

                print(
                    f"File type test passed for {filename}: "
                    f"{len(submitted_data)} chunks with language={expected_extension}"
                )

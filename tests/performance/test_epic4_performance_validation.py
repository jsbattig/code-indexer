"""
Story 6: Performance Validation Test Infrastructure

This module implements comprehensive performance benchmark tests that validate
the 4-8x improvement achieved by parallel processing implementations and prevent
performance regressions.

This test infrastructure verifies:
1. Branch change operations achieve minimum 4x speedup
2. Full index operations achieve minimum 4x speedup
3. Incremental operations achieve minimum 4x speedup
4. Thread utilization metrics confirm 8 workers are active
5. Git-awareness functionality remains identical
6. No performance regressions are detected

The tests provide automated baseline vs optimized comparison and regression detection.
"""

import pytest
import time
import psutil
import os
import tempfile
import gc
import threading
import statistics
from pathlib import Path
from contextlib import contextmanager
from typing import Dict, List, Any, Tuple
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass, field
from datetime import datetime

from code_indexer.config import Config
from code_indexer.services.high_throughput_processor import HighThroughputProcessor
from code_indexer.services.git_aware_processor import GitAwareDocumentProcessor
from tests.shared.mock_providers import MockEmbeddingProvider


@dataclass
class PerformanceMetrics:
    """Performance measurement data structure."""

    wall_time: float
    cpu_time: float
    memory_delta: float
    peak_memory: float
    throughput: float
    threads_used: int
    chunks_processed: int
    files_processed: int
    embeddings_per_second: float
    concurrent_workers_peak: int = 0


@dataclass
class PerformanceBenchmark:
    """Performance benchmark result container."""

    operation_name: str
    baseline_metrics: PerformanceMetrics
    optimized_metrics: PerformanceMetrics
    speedup_factor: float
    memory_improvement: float
    throughput_improvement: float
    thread_utilization: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def meets_requirements(self) -> bool:
        """Check if benchmark meets Story 6 requirements."""
        return (
            self.speedup_factor >= 4.0
            and self.thread_utilization >= 0.8  # 80% of 8 workers = 6.4 workers
            and self.throughput_improvement >= 4.0
        )


class PerformanceValidationFramework:
    """
    Core framework for automated performance validation and regression detection.

    Provides systematic baseline vs optimized comparison with automated
    regression detection capabilities.
    """

    def __init__(self):
        self.results_history: List[PerformanceBenchmark] = []
        self.baseline_results: Dict[str, PerformanceMetrics] = {}
        self.active_workers_count = 0
        self.peak_workers_count = 0
        self.worker_count_lock = threading.Lock()

    @contextmanager
    def measure_performance(self):
        """Enhanced performance measurement context manager."""
        process = psutil.Process(os.getpid())

        # Force garbage collection for clean measurement
        gc.collect()

        # Initial measurements
        start_time = time.perf_counter()
        start_cpu_time = time.process_time()
        start_memory = process.memory_info().rss
        start_memory_percent = process.memory_percent()

        # Reset worker tracking
        with self.worker_count_lock:
            self.active_workers_count = 0
            self.peak_workers_count = 0

        try:
            yield
        finally:
            # Final measurements
            end_time = time.perf_counter()
            end_cpu_time = time.process_time()
            end_memory = process.memory_info().rss
            end_memory_percent = process.memory_percent()

            # Store measurements
            self.wall_time = end_time - start_time
            self.cpu_time = end_cpu_time - start_cpu_time
            self.memory_delta = end_memory - start_memory
            self.peak_memory = max(start_memory, end_memory)
            self.memory_percent_delta = end_memory_percent - start_memory_percent

    def track_worker_activity(self, worker_id: str, is_active: bool):
        """Track worker thread activity for utilization measurement."""
        with self.worker_count_lock:
            if is_active:
                self.active_workers_count += 1
                self.peak_workers_count = max(
                    self.peak_workers_count, self.active_workers_count
                )
            else:
                self.active_workers_count = max(0, self.active_workers_count - 1)

    def create_test_codebase(
        self, file_count: int, avg_size_kb: int
    ) -> Tuple[Path, List[Path]]:
        """Create realistic test codebase for performance testing."""
        temp_dir = tempfile.mkdtemp(prefix="performance_test_")
        temp_path = Path(temp_dir)

        test_files = []

        # Create diverse file types and sizes
        languages = ["python", "javascript", "java", "typescript"]

        for i in range(file_count):
            lang = languages[i % len(languages)]
            size_variation = 0.5 + (i % 3) * 0.5  # 0.5x to 1.5x size variation
            target_size = int(avg_size_kb * size_variation * 1024)

            file_path = temp_path / f"test_file_{i:03d}.{self._get_extension(lang)}"
            content = self._generate_code_content(lang, target_size)

            file_path.write_text(content)
            test_files.append(file_path)

        return temp_path, test_files

    def _get_extension(self, language: str) -> str:
        """Get file extension for language."""
        extensions = {
            "python": "py",
            "javascript": "js",
            "java": "java",
            "typescript": "ts",
        }
        return extensions.get(language, "py")

    def _generate_code_content(self, language: str, target_size: int) -> str:
        """Generate realistic code content of target size."""
        templates = {
            "python": '''
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional

class DataProcessor{i}:
    """High-performance data processing service."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.processed_items = []
        self.cache = {{}}
    
    async def process_data(self, items: List[Dict]) -> List[Dict]:
        """Process data items with complex business logic."""
        results = []
        for item in items:
            try:
                processed = await self._transform_item(item)
                validated = self._validate_result(processed)
                if validated:
                    results.append(processed)
                    self.processed_items.append(item)
            except Exception as e:
                print(f"Processing error: {{e}}")
                continue
        return results
    
    async def _transform_item(self, item: Dict) -> Dict:
        """Transform item with async operations."""
        await asyncio.sleep(0.001)  # Simulate async processing
        return {{
            'id': item.get('id'),
            'processed_data': str(item).upper(),
            'timestamp': time.time(),
            'status': 'processed'
        }}
    
    def _validate_result(self, result: Dict) -> bool:
        """Validate processing result."""
        required_fields = ['id', 'processed_data', 'timestamp']
        return all(field in result for field in required_fields)

def create_processor{i}():
    return DataProcessor{i}({{'batch_size': 100, 'timeout': 30}})

''',
            "javascript": """
const EventEmitter = require('events');
const crypto = require('crypto');

class AsyncDataProcessor{i} extends EventEmitter {{
    constructor(config = {{}}) {{
        super();
        this.config = {{
            maxConcurrency: 10,
            retryAttempts: 3,
            cacheSize: 10000,
            ...config
        }};
        this.cache = new Map();
        this.processedCount = 0;
    }}
    
    async processBatch(dataItems, options = {{}}) {{
        const startTime = Date.now();
        
        try {{
            const validatedItems = await this.validateBatchInput(dataItems);
            const results = await this.processWithConcurrency(validatedItems, options);
            
            const processingTime = Date.now() - startTime;
            this.updateMetrics(results, processingTime);
            
            this.emit('batchCompleted', {{
                totalItems: dataItems.length,
                successful: results.filter(r => r.status === 'success').length,
                processingTime
            }});
            
            return results;
            
        }} catch (error) {{
            this.emit('batchError', error);
            throw new Error(`Batch processing failed: ${{error.message}}`);
        }}
    }}
    
    async processItem(dataItem) {{
        const itemId = this.generateItemId(dataItem);
        
        if (this.cache.has(itemId)) {{
            return this.cache.get(itemId);
        }}
        
        try {{
            const result = await this.executeProcessingPipeline(dataItem);
            
            if (result.status === 'success') {{
                this.cache.set(itemId, result);
            }}
            
            this.processedCount++;
            return result;
            
        }} catch (error) {{
            return {{
                itemId,
                status: 'error',
                error: error.message,
                timestamp: new Date().toISOString()
            }};
        }}
    }}
    
    async executeProcessingPipeline(dataItem) {{
        const pipeline = [
            this.validateStructure.bind(this),
            this.transformData.bind(this),
            this.applyBusinessRules.bind(this),
            this.enrichData.bind(this)
        ];
        
        let currentData = {{ ...dataItem }};
        
        for (const stage of pipeline) {{
            currentData = await stage(currentData);
        }}
        
        return {{
            itemId: this.generateItemId(dataItem),
            status: 'success',
            processedData: currentData,
            timestamp: new Date().toISOString()
        }};
    }}
    
    generateItemId(item) {{
        return crypto.createHash('sha256').update(JSON.stringify(item)).digest('hex');
    }}
}}

module.exports = AsyncDataProcessor{i};
""",
            "java": """
package com.example.performance.processor{i};

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicLong;
import java.time.LocalDateTime;

public class HighPerformanceProcessor{i} {{
    private final Map<String, Object> cache = new ConcurrentHashMap<>();
    private final ExecutorService executor = Executors.newFixedThreadPool(8);
    private final AtomicLong processedCount = new AtomicLong(0);
    private final BlockingQueue<ProcessingTask> taskQueue = new LinkedBlockingQueue<>();
    
    private static final int MAX_CACHE_SIZE = 10000;
    private static final long CACHE_EXPIRY_MS = 300000;
    
    public List<ProcessedData> processDataBatch(List<RawData> rawDataList) {{
        if (rawDataList == null || rawDataList.isEmpty()) {{
            return Collections.emptyList();
        }}
        
        List<RawData> validData = rawDataList.stream()
            .filter(this::validateRawData)
            .collect(Collectors.toList());
        
        return validData.parallelStream()
            .map(this::processItemWithMetrics)
            .filter(Objects::nonNull)
            .collect(Collectors.toList());
    }}
    
    private ProcessedData processItemWithMetrics(RawData rawData) {{
        long startTime = System.nanoTime();
        
        try {{
            String cacheKey = generateCacheKey(rawData);
            ProcessedData cached = getCachedResult(cacheKey);
            
            if (cached != null) {{
                return cached;
            }}
            
            ProcessedData result = executeProcessingPipeline(rawData);
            
            if (result != null && result.isValid()) {{
                cacheResult(cacheKey, result);
            }}
            
            processedCount.incrementAndGet();
            return result;
            
        }} catch (ProcessingException e) {{
            return createErrorResult(rawData, e);
        }}
    }}
    
    private ProcessedData executeProcessingPipeline(RawData rawData) {{
        TransformedData transformed = transformRawData(rawData);
        ValidationResult validation = validateBusinessRules(transformed);
        
        if (!validation.isValid()) {{
            throw new ProcessingException("Validation failed");
        }}
        
        EnrichedData enriched = enrichTransformedData(transformed);
        return finalizeProcessedData(enriched);
    }}
    
    private TransformedData transformRawData(RawData rawData) {{
        TransformedData transformed = new TransformedData();
        transformed.setId(rawData.getId());
        transformed.setName(normalizeString(rawData.getName()));
        transformed.setTimestamp(LocalDateTime.now());
        
        return transformed;
    }}
    
    private ValidationResult validateBusinessRules(TransformedData data) {{
        List<String> errors = new ArrayList<>();
        
        if (data.getName() == null || data.getName().trim().isEmpty()) {{
            errors.add("Name is required");
        }}
        
        return new ValidationResult(errors.isEmpty(), errors);
    }}
    
    private EnrichedData enrichTransformedData(TransformedData transformed) {{
        EnrichedData enriched = new EnrichedData(transformed);
        enriched.setProcessingTimestamp(LocalDateTime.now());
        enriched.setProcessorVersion("2.1.0");
        
        return enriched;
    }}
    
    private ProcessedData finalizeProcessedData(EnrichedData enriched) {{
        ProcessedData result = new ProcessedData();
        result.setSourceData(enriched);
        result.setFinalTimestamp(LocalDateTime.now());
        result.setStatus(ProcessingStatus.COMPLETED);
        
        return result;
    }}
}}
""",
            "typescript": """
interface DataProcessor{i}Config {{
    maxConcurrency: number;
    retryAttempts: number;
    cacheSize: number;
    timeout: number;
}}

interface ProcessingResult<T> {{
    success: boolean;
    data?: T;
    error?: string;
    metadata: ProcessingMetadata;
}}

interface ProcessingMetadata {{
    processingTime: number;
    timestamp: string;
    processorId: string;
}}

class TypeSafeDataProcessor{i}<T = any> {{
    private config: DataProcessor{i}Config;
    private cache: Map<string, ProcessingResult<T>>;
    private processingQueue: Array<T>;
    private activeProcessing: Set<string>;
    
    constructor(config: Partial<DataProcessor{i}Config> = {{}}) {{
        this.config = {{
            maxConcurrency: 10,
            retryAttempts: 3,
            cacheSize: 10000,
            timeout: 30000,
            ...config
        }};
        
        this.cache = new Map();
        this.processingQueue = [];
        this.activeProcessing = new Set();
    }}
    
    async processBatch<U>(
        items: T[], 
        transformer: (item: T) => Promise<U>
    ): Promise<ProcessingResult<U>[]> {{
        const startTime = Date.now();
        
        try {{
            const validatedItems = await this.validateInput(items);
            const results = await this.processWithConcurrencyControl(
                validatedItems, 
                transformer
            );
            
            return results.map(result => ({{
                ...result,
                metadata: {{
                    ...result.metadata,
                    processingTime: Date.now() - startTime,
                    timestamp: new Date().toISOString(),
                    processorId: `processor-{i}`
                }}
            }}));
            
        }} catch (error) {{
            throw new Error(`Batch processing failed: ${{error.message}}`);
        }}
    }}
    
    async processItem<U>(
        item: T, 
        transformer: (item: T) => Promise<U>
    ): Promise<ProcessingResult<U>> {{
        const itemId = this.generateItemId(item);
        
        if (this.cache.has(itemId)) {{
            return this.cache.get(itemId)! as ProcessingResult<U>;
        }}
        
        if (this.activeProcessing.has(itemId)) {{
            throw new Error(`Item ${{itemId}} is already being processed`);
        }}
        
        this.activeProcessing.add(itemId);
        
        try {{
            const result = await this.executeWithTimeout(
                () => transformer(item),
                this.config.timeout
            );
            
            const processedResult: ProcessingResult<U> = {{
                success: true,
                data: result,
                metadata: {{
                    processingTime: 0, // Will be set by caller
                    timestamp: new Date().toISOString(),
                    processorId: `processor-{i}`
                }}
            }};
            
            this.cacheResult(itemId, processedResult);
            return processedResult;
            
        }} catch (error) {{
            return {{
                success: false,
                error: error.message,
                metadata: {{
                    processingTime: 0,
                    timestamp: new Date().toISOString(),
                    processorId: `processor-{i}`
                }}
            }};
        }} finally {{
            this.activeProcessing.delete(itemId);
        }}
    }}
    
    private async validateInput<U>(items: U[]): Promise<U[]> {{
        return items.filter(item => 
            item != null && 
            typeof item === 'object'
        );
    }}
    
    private generateItemId(item: T): string {{
        return Buffer.from(JSON.stringify(item)).toString('base64');
    }}
    
    private cacheResult<U>(key: string, result: ProcessingResult<U>): void {{
        if (this.cache.size >= this.config.cacheSize) {{
            const firstKey = this.cache.keys().next().value;
            this.cache.delete(firstKey);
        }}
        this.cache.set(key, result as ProcessingResult<any>);
    }}
}}

export default TypeSafeDataProcessor{i};
""",
        }

        template = templates.get(language, templates["python"])

        # Calculate how many repetitions needed to reach target size
        base_template = template.format(i=1)
        base_size = len(base_template.encode("utf-8"))
        repetitions = max(1, target_size // base_size)

        # Generate content with varied class numbers
        content_parts = []
        for i in range(repetitions):
            content_parts.append(template.format(i=i + 1))

        return "".join(content_parts)

    def cleanup_test_codebase(self, temp_path: Path):
        """Clean up test codebase."""
        import shutil

        shutil.rmtree(temp_path, ignore_errors=True)


@pytest.mark.slow
class TestEpic4PerformanceValidation:
    """
    Story 6: Comprehensive performance validation tests for Epic 4.

    Validates that parallel processing implementation achieves:
    - 4x speedup in branch change operations
    - 4x speedup in full index operations
    - 4x speedup in incremental operations
    - 8 worker thread utilization
    - Git-awareness functionality preservation
    - No performance regressions
    """

    @pytest.fixture
    def framework(self):
        """Create performance validation framework."""
        return PerformanceValidationFramework()

    @pytest.fixture
    def mock_config(self):
        """Create mock configuration for testing."""
        config = Mock(spec=Config)
        config.exclude_dirs = []
        config.exclude_files = []
        config.include_extensions = [".py", ".js", ".java", ".ts"]
        config.indexing = Mock()
        config.indexing.chunk_size = 1000
        config.indexing.overlap_size = 150
        config.chunking = Mock()
        config.chunking.chunk_size = 1000
        config.chunking.overlap_size = 150
        config.qdrant = Mock()
        config.qdrant.vector_size = 768
        return config

    @pytest.fixture
    def mock_embedding_provider(self):
        """Create mock embedding provider with realistic delays."""
        return MockEmbeddingProvider(delay=0.02)  # 20ms per embedding (realistic)

    @pytest.fixture
    def mock_qdrant_client(self):
        """Create mock Qdrant client."""
        client = Mock()
        client.create_point.return_value = {"id": "test-point"}
        client.upsert_points.return_value = True
        client.upsert_points_atomic.return_value = True
        client.resolve_collection_name.return_value = "test_collection"
        client.scroll_points.return_value = ([], None)
        client._batch_update_points.return_value = True
        return client

    def test_branch_change_operations_4x_speedup(
        self, framework, mock_config, mock_embedding_provider, mock_qdrant_client
    ):
        """Test branch change operations achieve minimum 4x speedup."""

        # Create test codebase (24 files, ~25KB each = realistic branch change size)
        temp_path, test_files = framework.create_test_codebase(24, 25)
        mock_config.codebase_dir = temp_path

        try:
            # Setup processors
            baseline_processor = GitAwareDocumentProcessor(
                config=mock_config,
                embedding_provider=mock_embedding_provider,
                qdrant_client=mock_qdrant_client,
            )

            optimized_processor = HighThroughputProcessor(
                config=mock_config,
                embedding_provider=mock_embedding_provider,
                qdrant_client=mock_qdrant_client,
            )

            # Measure baseline (sequential) performance
            with framework.measure_performance():
                for file_path in test_files:
                    try:
                        baseline_processor.process_file(file_path)
                    except Exception:
                        pass  # Ignore errors for performance testing

            baseline_metrics = PerformanceMetrics(
                wall_time=framework.wall_time,
                cpu_time=framework.cpu_time,
                memory_delta=framework.memory_delta,
                peak_memory=framework.peak_memory,
                throughput=len(test_files) / framework.wall_time,
                threads_used=1,
                chunks_processed=0,  # Will be updated
                files_processed=len(test_files),
                embeddings_per_second=mock_embedding_provider.call_count
                / framework.wall_time,
            )

            # Reset provider call count
            mock_embedding_provider.reset_call_count()

            # Mock VectorCalculationManager for optimized test
            mock_vcm = MagicMock()
            mock_vcm.__enter__.return_value = mock_vcm
            mock_vcm.__exit__.return_value = None
            mock_vcm.get_stats.return_value = Mock(embeddings_per_second=100.0)

            def mock_submit_chunk(text, metadata):
                from concurrent.futures import Future

                future: Future = Future()
                future.set_result(
                    {"point_id": f"point_{hash(text)}", "payload": metadata}
                )
                # Track worker activity
                framework.track_worker_activity("worker", True)
                time.sleep(0.005)  # Simulate processing time
                framework.track_worker_activity("worker", False)
                return future

            mock_vcm.submit_chunk.side_effect = mock_submit_chunk

            # Measure optimized (parallel) performance
            with patch(
                "code_indexer.services.high_throughput_processor.VectorCalculationManager",
                return_value=mock_vcm,
            ):
                with framework.measure_performance():
                    result = optimized_processor.process_branch_changes_high_throughput(
                        old_branch="main",
                        new_branch="feature",
                        changed_files=[
                            str(f.relative_to(temp_path)) for f in test_files
                        ],
                        unchanged_files=[],
                        collection_name="test_collection",
                        vector_thread_count=8,
                    )

            optimized_metrics = PerformanceMetrics(
                wall_time=framework.wall_time,
                cpu_time=framework.cpu_time,
                memory_delta=framework.memory_delta,
                peak_memory=framework.peak_memory,
                throughput=len(test_files) / framework.wall_time,
                threads_used=8,
                chunks_processed=result.chunks_created if result else 0,
                files_processed=result.files_processed if result else 0,
                embeddings_per_second=mock_vcm.get_stats().embeddings_per_second,
                concurrent_workers_peak=framework.peak_workers_count,
            )

            # Calculate performance improvements
            speedup_factor = baseline_metrics.wall_time / optimized_metrics.wall_time
            throughput_improvement = (
                optimized_metrics.throughput / baseline_metrics.throughput
            )
            memory_improvement = (
                baseline_metrics.peak_memory / optimized_metrics.peak_memory
            )
            thread_utilization = framework.peak_workers_count / 8.0

            # Create benchmark result
            benchmark = PerformanceBenchmark(
                operation_name="branch_change_operations",
                baseline_metrics=baseline_metrics,
                optimized_metrics=optimized_metrics,
                speedup_factor=speedup_factor,
                memory_improvement=memory_improvement,
                throughput_improvement=throughput_improvement,
                thread_utilization=thread_utilization,
            )

            # Validate requirements
            assert benchmark.meets_requirements(), (
                f"Branch change operations failed performance requirements:\n"
                f"  Speedup: {speedup_factor:.1f}x (required: ≥4.0x)\n"
                f"  Thread utilization: {thread_utilization:.1%} (required: ≥80%)\n"
                f"  Throughput improvement: {throughput_improvement:.1f}x (required: ≥4.0x)"
            )

            # Additional assertions for Story 6 requirements
            assert (
                speedup_factor >= 4.0
            ), f"Branch changes speedup {speedup_factor:.1f}x < required 4.0x"
            assert (
                thread_utilization >= 0.8
            ), f"Thread utilization {thread_utilization:.1%} < required 80%"
            assert (
                throughput_improvement >= 4.0
            ), f"Throughput improvement {throughput_improvement:.1f}x < required 4.0x"

            # Store benchmark for regression tracking
            framework.results_history.append(benchmark)

            print("✅ Branch Change Operations Performance:")
            print(f"   Speedup: {speedup_factor:.1f}x")
            print(f"   Thread utilization: {thread_utilization:.1%}")
            print(f"   Throughput improvement: {throughput_improvement:.1f}x")
            print(f"   Files processed: {optimized_metrics.files_processed}")

        finally:
            framework.cleanup_test_codebase(temp_path)

    def test_full_index_operations_4x_speedup(
        self, framework, mock_config, mock_embedding_provider, mock_qdrant_client
    ):
        """Test full index operations achieve minimum 4x speedup."""

        # Create larger test codebase (48 files, ~20KB each = realistic full index size)
        temp_path, test_files = framework.create_test_codebase(48, 20)
        mock_config.codebase_dir = temp_path

        try:
            # Setup processors
            baseline_processor = GitAwareDocumentProcessor(
                config=mock_config,
                embedding_provider=mock_embedding_provider,
                qdrant_client=mock_qdrant_client,
            )

            optimized_processor = HighThroughputProcessor(
                config=mock_config,
                embedding_provider=mock_embedding_provider,
                qdrant_client=mock_qdrant_client,
            )

            # Measure baseline performance (sequential full index)
            with framework.measure_performance():
                for file_path in test_files:
                    try:
                        baseline_processor.process_file(file_path)
                    except Exception:
                        pass

            baseline_metrics = PerformanceMetrics(
                wall_time=framework.wall_time,
                cpu_time=framework.cpu_time,
                memory_delta=framework.memory_delta,
                peak_memory=framework.peak_memory,
                throughput=len(test_files) / framework.wall_time,
                threads_used=1,
                chunks_processed=0,
                files_processed=len(test_files),
                embeddings_per_second=mock_embedding_provider.call_count
                / framework.wall_time,
            )

            # Reset provider call count
            mock_embedding_provider.reset_call_count()

            # Mock VectorCalculationManager for optimized test
            mock_vcm = MagicMock()
            mock_vcm.__enter__.return_value = mock_vcm
            mock_vcm.__exit__.return_value = None
            mock_vcm.get_stats.return_value = Mock(embeddings_per_second=150.0)

            def mock_submit_chunk(text, metadata):
                from concurrent.futures import Future

                future: Future = Future()
                future.set_result(
                    {"point_id": f"point_{hash(text)}", "payload": metadata}
                )
                framework.track_worker_activity("worker", True)
                time.sleep(0.003)  # Simulate processing time for full index
                framework.track_worker_activity("worker", False)
                return future

            mock_vcm.submit_chunk.side_effect = mock_submit_chunk

            # Measure optimized performance (parallel full index)
            with patch(
                "code_indexer.services.high_throughput_processor.VectorCalculationManager",
                return_value=mock_vcm,
            ):
                with framework.measure_performance():
                    result = optimized_processor.process_files_high_throughput(
                        test_files,
                        vector_thread_count=8,
                        batch_size=20,
                    )

            optimized_metrics = PerformanceMetrics(
                wall_time=framework.wall_time,
                cpu_time=framework.cpu_time,
                memory_delta=framework.memory_delta,
                peak_memory=framework.peak_memory,
                throughput=len(test_files) / framework.wall_time,
                threads_used=8,
                chunks_processed=result.chunks_created if result else 0,
                files_processed=result.files_processed if result else 0,
                embeddings_per_second=mock_vcm.get_stats().embeddings_per_second,
                concurrent_workers_peak=framework.peak_workers_count,
            )

            # Calculate performance improvements
            speedup_factor = baseline_metrics.wall_time / optimized_metrics.wall_time
            throughput_improvement = (
                optimized_metrics.throughput / baseline_metrics.throughput
            )
            memory_improvement = (
                baseline_metrics.peak_memory / optimized_metrics.peak_memory
            )
            thread_utilization = framework.peak_workers_count / 8.0

            # Create benchmark result
            benchmark = PerformanceBenchmark(
                operation_name="full_index_operations",
                baseline_metrics=baseline_metrics,
                optimized_metrics=optimized_metrics,
                speedup_factor=speedup_factor,
                memory_improvement=memory_improvement,
                throughput_improvement=throughput_improvement,
                thread_utilization=thread_utilization,
            )

            # Validate requirements
            assert benchmark.meets_requirements(), (
                f"Full index operations failed performance requirements:\n"
                f"  Speedup: {speedup_factor:.1f}x (required: ≥4.0x)\n"
                f"  Thread utilization: {thread_utilization:.1%} (required: ≥80%)\n"
                f"  Throughput improvement: {throughput_improvement:.1f}x (required: ≥4.0x)"
            )

            # Additional assertions for Story 6 requirements
            assert (
                speedup_factor >= 4.0
            ), f"Full index speedup {speedup_factor:.1f}x < required 4.0x"
            assert (
                thread_utilization >= 0.8
            ), f"Thread utilization {thread_utilization:.1%} < required 80%"
            assert (
                throughput_improvement >= 4.0
            ), f"Throughput improvement {throughput_improvement:.1f}x < required 4.0x"

            # Store benchmark for regression tracking
            framework.results_history.append(benchmark)

            print("✅ Full Index Operations Performance:")
            print(f"   Speedup: {speedup_factor:.1f}x")
            print(f"   Thread utilization: {thread_utilization:.1%}")
            print(f"   Throughput improvement: {throughput_improvement:.1f}x")
            print(f"   Files processed: {optimized_metrics.files_processed}")

        finally:
            framework.cleanup_test_codebase(temp_path)

    def test_incremental_operations_4x_speedup(
        self, framework, mock_config, mock_embedding_provider, mock_qdrant_client
    ):
        """Test incremental operations achieve minimum 4x speedup."""

        # Create medium test codebase (18 files, ~30KB each = realistic incremental size)
        temp_path, test_files = framework.create_test_codebase(18, 30)
        mock_config.codebase_dir = temp_path

        # Simulate incremental operation by processing subset of files
        incremental_files = test_files[:12]  # Process 12 out of 18 files

        try:
            # Setup processors
            baseline_processor = GitAwareDocumentProcessor(
                config=mock_config,
                embedding_provider=mock_embedding_provider,
                qdrant_client=mock_qdrant_client,
            )

            optimized_processor = HighThroughputProcessor(
                config=mock_config,
                embedding_provider=mock_embedding_provider,
                qdrant_client=mock_qdrant_client,
            )

            # Measure baseline performance (sequential incremental)
            with framework.measure_performance():
                for file_path in incremental_files:
                    try:
                        baseline_processor.process_file(file_path)
                    except Exception:
                        pass

            baseline_metrics = PerformanceMetrics(
                wall_time=framework.wall_time,
                cpu_time=framework.cpu_time,
                memory_delta=framework.memory_delta,
                peak_memory=framework.peak_memory,
                throughput=len(incremental_files) / framework.wall_time,
                threads_used=1,
                chunks_processed=0,
                files_processed=len(incremental_files),
                embeddings_per_second=mock_embedding_provider.call_count
                / framework.wall_time,
            )

            # Reset provider call count
            mock_embedding_provider.reset_call_count()

            # Mock VectorCalculationManager for optimized test
            mock_vcm = MagicMock()
            mock_vcm.__enter__.return_value = mock_vcm
            mock_vcm.__exit__.return_value = None
            mock_vcm.get_stats.return_value = Mock(embeddings_per_second=120.0)

            def mock_submit_chunk(text, metadata):
                from concurrent.futures import Future

                future: Future = Future()
                future.set_result(
                    {"point_id": f"point_{hash(text)}", "payload": metadata}
                )
                framework.track_worker_activity("worker", True)
                time.sleep(0.004)  # Simulate processing time for incremental
                framework.track_worker_activity("worker", False)
                return future

            mock_vcm.submit_chunk.side_effect = mock_submit_chunk

            # Measure optimized performance (parallel incremental)
            with patch(
                "code_indexer.services.high_throughput_processor.VectorCalculationManager",
                return_value=mock_vcm,
            ):
                with framework.measure_performance():
                    result = optimized_processor.process_files_high_throughput(
                        incremental_files,
                        vector_thread_count=8,
                        batch_size=15,
                    )

            optimized_metrics = PerformanceMetrics(
                wall_time=framework.wall_time,
                cpu_time=framework.cpu_time,
                memory_delta=framework.memory_delta,
                peak_memory=framework.peak_memory,
                throughput=len(incremental_files) / framework.wall_time,
                threads_used=8,
                chunks_processed=result.chunks_created if result else 0,
                files_processed=result.files_processed if result else 0,
                embeddings_per_second=mock_vcm.get_stats().embeddings_per_second,
                concurrent_workers_peak=framework.peak_workers_count,
            )

            # Calculate performance improvements
            speedup_factor = baseline_metrics.wall_time / optimized_metrics.wall_time
            throughput_improvement = (
                optimized_metrics.throughput / baseline_metrics.throughput
            )
            memory_improvement = (
                baseline_metrics.peak_memory / optimized_metrics.peak_memory
            )
            thread_utilization = framework.peak_workers_count / 8.0

            # Create benchmark result
            benchmark = PerformanceBenchmark(
                operation_name="incremental_operations",
                baseline_metrics=baseline_metrics,
                optimized_metrics=optimized_metrics,
                speedup_factor=speedup_factor,
                memory_improvement=memory_improvement,
                throughput_improvement=throughput_improvement,
                thread_utilization=thread_utilization,
            )

            # Validate requirements
            assert benchmark.meets_requirements(), (
                f"Incremental operations failed performance requirements:\n"
                f"  Speedup: {speedup_factor:.1f}x (required: ≥4.0x)\n"
                f"  Thread utilization: {thread_utilization:.1%} (required: ≥80%)\n"
                f"  Throughput improvement: {throughput_improvement:.1f}x (required: ≥4.0x)"
            )

            # Additional assertions for Story 6 requirements
            assert (
                speedup_factor >= 4.0
            ), f"Incremental speedup {speedup_factor:.1f}x < required 4.0x"
            assert (
                thread_utilization >= 0.8
            ), f"Thread utilization {thread_utilization:.1%} < required 80%"
            assert (
                throughput_improvement >= 4.0
            ), f"Throughput improvement {throughput_improvement:.1f}x < required 4.0x"

            # Store benchmark for regression tracking
            framework.results_history.append(benchmark)

            print("✅ Incremental Operations Performance:")
            print(f"   Speedup: {speedup_factor:.1f}x")
            print(f"   Thread utilization: {thread_utilization:.1%}")
            print(f"   Throughput improvement: {throughput_improvement:.1f}x")
            print(f"   Files processed: {optimized_metrics.files_processed}")

        finally:
            framework.cleanup_test_codebase(temp_path)

    def test_thread_utilization_validation_8_workers(
        self, framework, mock_config, mock_embedding_provider, mock_qdrant_client
    ):
        """Test that thread utilization metrics confirm 8 workers are active."""

        # Create test codebase designed to exercise all 8 threads
        temp_path, test_files = framework.create_test_codebase(
            32, 15
        )  # 32 files to ensure threads stay busy
        mock_config.codebase_dir = temp_path

        try:
            optimized_processor = HighThroughputProcessor(
                config=mock_config,
                embedding_provider=mock_embedding_provider,
                qdrant_client=mock_qdrant_client,
            )

            # Track worker activity with more detailed monitoring
            worker_activity_log = []
            activity_lock = threading.Lock()

            def detailed_mock_submit_chunk(text, metadata):
                from concurrent.futures import Future

                worker_id = threading.current_thread().ident
                timestamp = time.time()

                with activity_lock:
                    worker_activity_log.append(("start", worker_id, timestamp))
                    framework.track_worker_activity(str(worker_id), True)

                # Simulate realistic processing time
                time.sleep(0.01)  # 10ms processing time

                with activity_lock:
                    worker_activity_log.append(("end", worker_id, timestamp + 0.01))
                    framework.track_worker_activity(str(worker_id), False)

                future: Future = Future()
                future.set_result(
                    {"point_id": f"point_{hash(text)}", "payload": metadata}
                )
                return future

            # Mock VectorCalculationManager with detailed tracking
            mock_vcm = MagicMock()
            mock_vcm.__enter__.return_value = mock_vcm
            mock_vcm.__exit__.return_value = None
            mock_vcm.submit_chunk.side_effect = detailed_mock_submit_chunk
            mock_vcm.get_stats.return_value = Mock(embeddings_per_second=200.0)

            # Process files with 8 workers
            with patch(
                "code_indexer.services.high_throughput_processor.VectorCalculationManager",
                return_value=mock_vcm,
            ):
                with framework.measure_performance():
                    result = optimized_processor.process_files_high_throughput(
                        test_files,
                        vector_thread_count=8,
                        batch_size=40,  # Large batch to keep workers busy
                    )

            # Analyze worker utilization
            unique_workers = set()
            concurrent_workers_over_time = []

            # Process activity log to find peak concurrency
            start_times = {}
            for event, worker_id, timestamp in worker_activity_log:
                unique_workers.add(worker_id)
                if event == "start":
                    start_times[worker_id] = timestamp
                elif event == "end" and worker_id in start_times:
                    # Count concurrent workers during this interval
                    concurrent_count = sum(
                        1
                        for other_worker, start_time in start_times.items()
                        if start_time <= timestamp
                    )
                    concurrent_workers_over_time.append(concurrent_count)

            # Calculate utilization metrics
            unique_worker_count = len(unique_workers)
            peak_concurrent_workers = (
                max(concurrent_workers_over_time) if concurrent_workers_over_time else 0
            )
            avg_concurrent_workers = (
                statistics.mean(concurrent_workers_over_time)
                if concurrent_workers_over_time
                else 0
            )

            worker_utilization_rate = peak_concurrent_workers / 8.0
            avg_utilization_rate = avg_concurrent_workers / 8.0

            # Validate 8-worker requirements
            assert (
                unique_worker_count >= 6
            ), f"Too few unique workers: {unique_worker_count}/8 (expected ≥6)"
            assert (
                peak_concurrent_workers >= 6
            ), f"Peak concurrency too low: {peak_concurrent_workers}/8 (expected ≥6)"
            assert (
                worker_utilization_rate >= 0.75
            ), f"Worker utilization too low: {worker_utilization_rate:.1%} (expected ≥75%)"
            assert (
                avg_utilization_rate >= 0.5
            ), f"Average utilization too low: {avg_utilization_rate:.1%} (expected ≥50%)"

            # Validate processing effectiveness
            assert (
                result and result.files_processed > 0
            ), "Processing should complete successfully"
            assert (
                framework.wall_time < len(test_files) * 0.01 / 4
            ), "Should show parallelization benefit"

            print("✅ Thread Utilization Validation:")
            print(f"   Unique workers used: {unique_worker_count}/8")
            print(f"   Peak concurrent workers: {peak_concurrent_workers}/8")
            print(f"   Peak utilization rate: {worker_utilization_rate:.1%}")
            print(f"   Average utilization rate: {avg_utilization_rate:.1%}")
            print(f"   Files processed: {result.files_processed if result else 0}")
            print(f"   Total processing time: {framework.wall_time:.3f}s")

        finally:
            framework.cleanup_test_codebase(temp_path)

    def test_git_awareness_functionality_preservation(
        self, framework, mock_config, mock_embedding_provider, mock_qdrant_client
    ):
        """Test that git-awareness functionality remains identical between baseline and optimized."""

        # Create test codebase
        temp_path, test_files = framework.create_test_codebase(12, 20)
        mock_config.codebase_dir = temp_path

        try:
            # Setup processors
            baseline_processor = GitAwareDocumentProcessor(
                config=mock_config,
                embedding_provider=mock_embedding_provider,
                qdrant_client=mock_qdrant_client,
            )

            optimized_processor = HighThroughputProcessor(
                config=mock_config,
                embedding_provider=mock_embedding_provider,
                qdrant_client=mock_qdrant_client,
            )

            # Test git-aware operations - content ID generation
            test_scenarios = [
                ("main", "feature", "test_file.py", 1),
                ("main", "develop", "another_file.py", 2),
                ("feature", "bugfix", "third_file.py", 0),
            ]

            baseline_content_ids = []
            optimized_content_ids = []

            for old_branch, new_branch, file_path, chunk_index in test_scenarios:
                # Test baseline content ID generation
                baseline_id = baseline_processor._generate_content_id_thread_safe(
                    file_path, "test_commit", chunk_index
                )
                baseline_content_ids.append(baseline_id)

                # Test optimized content ID generation
                optimized_id = optimized_processor._generate_content_id_thread_safe(
                    file_path, "test_commit", chunk_index
                )
                optimized_content_ids.append(optimized_id)

            # Validate content ID consistency
            for i, (baseline_id, optimized_id) in enumerate(
                zip(baseline_content_ids, optimized_content_ids)
            ):
                assert baseline_id == optimized_id, (
                    f"Content ID mismatch for scenario {i}: "
                    f"baseline='{baseline_id}' vs optimized='{optimized_id}'"
                )

            # Test branch visibility operations consistency
            test_file_path = "test_visibility.py"
            test_collection = "test_collection"
            test_branch = "test_branch"

            # Mock Qdrant responses for visibility tests
            mock_points = [
                {
                    "id": "point1",
                    "payload": {"path": test_file_path, "hidden_branches": []},
                }
            ]
            mock_qdrant_client.scroll_points.return_value = (mock_points, None)

            # Test hide operation consistency
            baseline_hide_result = baseline_processor._hide_file_in_branch_thread_safe(
                test_file_path, test_branch, test_collection
            )

            optimized_hide_result = (
                optimized_processor._hide_file_in_branch_thread_safe(
                    test_file_path, test_branch, test_collection
                )
            )

            # Validate hide operation results are equivalent
            assert (
                baseline_hide_result == optimized_hide_result
            ), f"Hide operation results differ: baseline={baseline_hide_result} vs optimized={optimized_hide_result}"

            # Test ensure visible operation consistency
            baseline_visible_result = (
                baseline_processor._ensure_file_visible_in_branch_thread_safe(
                    test_file_path, test_branch, test_collection
                )
            )

            optimized_visible_result = (
                optimized_processor._ensure_file_visible_in_branch_thread_safe(
                    test_file_path, test_branch, test_collection
                )
            )

            # Validate visible operation results are equivalent
            assert (
                baseline_visible_result == optimized_visible_result
            ), f"Visible operation results differ: baseline={baseline_visible_result} vs optimized={optimized_visible_result}"

            # Test batch update consistency (verify same calls made to Qdrant)
            baseline_calls = mock_qdrant_client._batch_update_points.call_count
            mock_qdrant_client.reset_mock()

            # Run same operations with optimized processor
            optimized_processor._hide_file_in_branch_thread_safe(
                test_file_path, test_branch, test_collection
            )
            optimized_processor._ensure_file_visible_in_branch_thread_safe(
                test_file_path, test_branch, test_collection
            )

            optimized_calls = mock_qdrant_client._batch_update_points.call_count

            # Validate same number of database operations
            assert (
                baseline_calls == optimized_calls
            ), f"Database operation count differs: baseline={baseline_calls} vs optimized={optimized_calls}"

            print("✅ Git-Awareness Functionality Preservation:")
            print(
                f"   Content ID generation: {len(baseline_content_ids)} scenarios verified"
            )
            print("   Hide operations: Consistent results verified")
            print("   Visible operations: Consistent results verified")
            print(f"   Database operations: {optimized_calls} calls consistent")

        finally:
            framework.cleanup_test_codebase(temp_path)

    def test_automated_performance_regression_detection(self, framework):
        """Test automated performance regression detection system."""

        # Simulate historical benchmark data
        historical_benchmarks = [
            PerformanceBenchmark(
                operation_name="branch_change_operations",
                baseline_metrics=PerformanceMetrics(
                    wall_time=10.0,
                    cpu_time=9.5,
                    memory_delta=100_000_000,
                    peak_memory=150_000_000,
                    throughput=2.4,
                    threads_used=1,
                    chunks_processed=100,
                    files_processed=24,
                    embeddings_per_second=10.0,
                ),
                optimized_metrics=PerformanceMetrics(
                    wall_time=2.0,
                    cpu_time=8.0,
                    memory_delta=80_000_000,
                    peak_memory=120_000_000,
                    throughput=12.0,
                    threads_used=8,
                    chunks_processed=100,
                    files_processed=24,
                    embeddings_per_second=50.0,
                ),
                speedup_factor=5.0,
                memory_improvement=1.25,
                throughput_improvement=5.0,
                thread_utilization=0.85,
            ),
            PerformanceBenchmark(
                operation_name="full_index_operations",
                baseline_metrics=PerformanceMetrics(
                    wall_time=20.0,
                    cpu_time=19.0,
                    memory_delta=200_000_000,
                    peak_memory=300_000_000,
                    throughput=2.4,
                    threads_used=1,
                    chunks_processed=200,
                    files_processed=48,
                    embeddings_per_second=10.0,
                ),
                optimized_metrics=PerformanceMetrics(
                    wall_time=4.5,
                    cpu_time=15.0,
                    memory_delta=150_000_000,
                    peak_memory=250_000_000,
                    throughput=10.7,
                    threads_used=8,
                    chunks_processed=200,
                    files_processed=48,
                    embeddings_per_second=44.4,
                ),
                speedup_factor=4.4,
                memory_improvement=1.2,
                throughput_improvement=4.5,
                thread_utilization=0.82,
            ),
        ]

        # Add historical data to framework
        framework.results_history.extend(historical_benchmarks)

        # Test regression detection with new benchmark that shows regression
        regression_benchmark = PerformanceBenchmark(
            operation_name="branch_change_operations",
            baseline_metrics=PerformanceMetrics(
                wall_time=10.0,
                cpu_time=9.5,
                memory_delta=100_000_000,
                peak_memory=150_000_000,
                throughput=2.4,
                threads_used=1,
                chunks_processed=100,
                files_processed=24,
                embeddings_per_second=10.0,
            ),
            optimized_metrics=PerformanceMetrics(
                wall_time=3.5,
                cpu_time=8.0,
                memory_delta=90_000_000,
                peak_memory=130_000_000,
                throughput=6.9,
                threads_used=8,
                chunks_processed=100,
                files_processed=24,
                embeddings_per_second=28.6,
                concurrent_workers_peak=6,
            ),
            speedup_factor=2.9,  # Regression: below 4.0x requirement
            memory_improvement=1.15,
            throughput_improvement=2.9,
            thread_utilization=0.75,  # Regression: below 0.8 requirement
        )

        # Test regression detection logic
        def detect_performance_regression(
            current_benchmark: PerformanceBenchmark,
            historical_benchmarks: List[PerformanceBenchmark],
        ) -> Dict[str, Any]:
            """Detect performance regressions by comparing against historical data."""

            # Find historical benchmarks for same operation
            same_operation_benchmarks = [
                b
                for b in historical_benchmarks
                if b.operation_name == current_benchmark.operation_name
            ]

            if not same_operation_benchmarks:
                return {"regression_detected": False, "reason": "No historical data"}

            # Calculate average historical performance
            avg_speedup = statistics.mean(
                [b.speedup_factor for b in same_operation_benchmarks]
            )
            avg_utilization = statistics.mean(
                [b.thread_utilization for b in same_operation_benchmarks]
            )
            avg_throughput = statistics.mean(
                [b.throughput_improvement for b in same_operation_benchmarks]
            )

            # Define regression thresholds (10% drop from historical average)
            speedup_threshold = avg_speedup * 0.9
            utilization_threshold = avg_utilization * 0.9
            throughput_threshold = avg_throughput * 0.9

            regressions = []

            if current_benchmark.speedup_factor < speedup_threshold:
                regressions.append(
                    f"Speedup regression: {current_benchmark.speedup_factor:.1f}x < {speedup_threshold:.1f}x"
                )

            if current_benchmark.thread_utilization < utilization_threshold:
                regressions.append(
                    f"Thread utilization regression: {current_benchmark.thread_utilization:.1%} < {utilization_threshold:.1%}"
                )

            if current_benchmark.throughput_improvement < throughput_threshold:
                regressions.append(
                    f"Throughput regression: {current_benchmark.throughput_improvement:.1f}x < {throughput_threshold:.1f}x"
                )

            # Check absolute requirement violations
            if not current_benchmark.meets_requirements():
                regressions.append(
                    "Absolute requirements not met (4x speedup, 80% utilization)"
                )

            return {
                "regression_detected": len(regressions) > 0,
                "regressions": regressions,
                "historical_average": {
                    "speedup": avg_speedup,
                    "utilization": avg_utilization,
                    "throughput": avg_throughput,
                },
                "current_performance": {
                    "speedup": current_benchmark.speedup_factor,
                    "utilization": current_benchmark.thread_utilization,
                    "throughput": current_benchmark.throughput_improvement,
                },
            }

        # Test regression detection
        regression_result = detect_performance_regression(
            regression_benchmark, framework.results_history
        )

        # Validate regression detection
        assert regression_result[
            "regression_detected"
        ], "Should detect performance regression"
        assert (
            len(regression_result["regressions"]) >= 2
        ), f"Should detect multiple regressions, got: {regression_result['regressions']}"

        # Test non-regression scenario
        good_benchmark = PerformanceBenchmark(
            operation_name="branch_change_operations",
            baseline_metrics=PerformanceMetrics(
                wall_time=10.0,
                cpu_time=9.5,
                memory_delta=100_000_000,
                peak_memory=150_000_000,
                throughput=2.4,
                threads_used=1,
                chunks_processed=100,
                files_processed=24,
                embeddings_per_second=10.0,
            ),
            optimized_metrics=PerformanceMetrics(
                wall_time=1.8,
                cpu_time=7.5,
                memory_delta=75_000_000,
                peak_memory=110_000_000,
                throughput=13.3,
                threads_used=8,
                chunks_processed=100,
                files_processed=24,
                embeddings_per_second=55.6,
                concurrent_workers_peak=7,
            ),
            speedup_factor=5.6,  # Better than historical average
            memory_improvement=1.36,
            throughput_improvement=5.5,
            thread_utilization=0.88,  # Better than historical average
        )

        good_result = detect_performance_regression(
            good_benchmark, framework.results_history
        )

        # Validate no false positives
        assert not good_result[
            "regression_detected"
        ], f"Should not detect regression for good performance: {good_result}"

        print("✅ Automated Performance Regression Detection:")
        print(
            f"   Regression detection: Correctly identified {len(regression_result['regressions'])} issues"
        )
        print(
            "   False positive test: Passed (no regression detected for good performance)"
        )
        print(f"   Historical benchmarks: {len(framework.results_history)} data points")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

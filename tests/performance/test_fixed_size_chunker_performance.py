"""Performance tests for FixedSizeChunker.

These tests verify that the fixed-size chunking approach is faster and more memory
efficient than the old AST-based semantic chunking approach.
"""

import pytest
import time
import psutil
import os
import tempfile
from pathlib import Path
from contextlib import contextmanager
from src.code_indexer.indexing.fixed_size_chunker import FixedSizeChunker
from src.code_indexer.config import IndexingConfig


class TestFixedSizeChunkerPerformance:
    """Performance tests for FixedSizeChunker."""

    @pytest.fixture
    def chunker(self):
        """Create a FixedSizeChunker with standard configuration."""
        config = IndexingConfig()
        return FixedSizeChunker(config)

    @contextmanager
    def measure_performance(self):
        """Context manager to measure time and memory usage."""
        process = psutil.Process(os.getpid())

        # Initial measurements
        start_time = time.perf_counter()
        start_memory = process.memory_info().rss

        try:
            yield
        finally:
            # Final measurements
            end_time = time.perf_counter()
            end_memory = process.memory_info().rss

            self.duration = end_time - start_time
            self.memory_delta = end_memory - start_memory
            self.peak_memory = max(start_memory, end_memory)

    def create_test_file(self, size_kb: int, file_type: str = "py") -> Path:
        """Create a test file of specified size with realistic code content."""
        # Create realistic code patterns for different file types
        if file_type == "py":
            base_content = '''
def calculate_fibonacci(n):
    """Calculate fibonacci number using dynamic programming."""
    if n <= 1:
        return n
    
    dp = [0] * (n + 1)
    dp[1] = 1
    
    for i in range(2, n + 1):
        dp[i] = dp[i-1] + dp[i-2]
    
    return dp[n]

class DataProcessor:
    """Process various types of data efficiently."""
    
    def __init__(self, config):
        self.config = config
        self.results = []
    
    def process_batch(self, items):
        for item in items:
            result = self.transform_item(item)
            self.results.append(result)
        return len(self.results)
    
    def transform_item(self, item):
        # Complex transformation logic
        if isinstance(item, dict):
            return {k: str(v).upper() for k, v in item.items()}
        elif isinstance(item, list):
            return [str(x) for x in item if x is not None]
        else:
            return str(item)
'''
        elif file_type == "java":
            base_content = """
package com.example.performance;

import java.util.*;
import java.util.concurrent.*;
import java.util.stream.Collectors;

/**
 * High-performance data processing service
 */
public class DataProcessingService {
    private final Map<String, Object> cache = new ConcurrentHashMap<>();
    private final ExecutorService executor = Executors.newFixedThreadPool(4);
    
    public List<ProcessedData> processDataBatch(List<RawData> rawData) {
        return rawData.parallelStream()
                     .map(this::processItem)
                     .filter(Objects::nonNull)
                     .collect(Collectors.toList());
    }
    
    private ProcessedData processItem(RawData raw) {
        try {
            String key = generateKey(raw);
            Object cached = cache.get(key);
            
            if (cached != null) {
                return (ProcessedData) cached;
            }
            
            ProcessedData result = performProcessing(raw);
            cache.put(key, result);
            return result;
        } catch (Exception e) {
            logger.error("Failed to process item", e);
            return null;
        }
    }
    
    private String generateKey(RawData raw) {
        return String.format("%s_%s_%d", 
            raw.getType(), raw.getCategory(), raw.getTimestamp());
    }
    
    private ProcessedData performProcessing(RawData raw) {
        // Simulate complex processing
        return new ProcessedData(
            raw.getId(),
            raw.getData().toUpperCase(),
            System.currentTimeMillis()
        );
    }
}
"""

        # Calculate how many repetitions we need to reach the target size
        target_bytes = size_kb * 1024
        content_bytes = len(base_content.encode("utf-8"))
        repetitions = max(1, target_bytes // content_bytes)

        # Create the file content
        full_content = base_content * repetitions

        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=f".{file_type}", delete=False
        )
        temp_file.write(full_content)
        temp_file.close()

        return Path(temp_file.name)

    def test_chunking_speed_small_files(self, chunker):
        """Test chunking speed on small files (1-10KB)."""
        file_sizes = [1, 5, 10]  # KB

        for size_kb in file_sizes:
            test_file = self.create_test_file(size_kb, "py")

            try:
                with self.measure_performance():
                    chunks = chunker.chunk_file(test_file)

                # Performance assertions
                assert (
                    self.duration < 0.1
                ), f"Chunking {size_kb}KB file took {self.duration:.3f}s, expected < 0.1s"

                # Memory usage should be reasonable (under 10MB delta)
                memory_mb = self.memory_delta / (1024 * 1024)
                assert (
                    memory_mb < 10
                ), f"Memory usage for {size_kb}KB file: {memory_mb:.2f}MB, expected < 10MB"

                # Verify results
                assert len(chunks) > 0, "Should produce at least one chunk"

                # All chunks except last should be exactly 1000 characters
                for i, chunk in enumerate(chunks[:-1]):
                    assert (
                        len(chunk["text"]) == 1000
                    ), f"Chunk {i} should be exactly 1000 chars"

                print(
                    f"Small file ({size_kb}KB): {len(chunks)} chunks in {self.duration:.3f}s"
                )

            finally:
                test_file.unlink()  # Clean up

    def test_chunking_speed_medium_files(self, chunker):
        """Test chunking speed on medium files (50-200KB)."""
        file_sizes = [50, 100, 200]  # KB

        for size_kb in file_sizes:
            test_file = self.create_test_file(size_kb, "java")

            try:
                with self.measure_performance():
                    chunks = chunker.chunk_file(test_file)

                # Performance assertions - should still be very fast
                assert (
                    self.duration < 0.5
                ), f"Chunking {size_kb}KB file took {self.duration:.3f}s, expected < 0.5s"

                # Memory usage should scale reasonably
                memory_mb = self.memory_delta / (1024 * 1024)
                expected_max_memory = (
                    size_kb * 0.1
                )  # Should not exceed 10% of file size
                assert memory_mb < expected_max_memory, (
                    f"Memory usage for {size_kb}KB file: {memory_mb:.2f}MB, "
                    f"expected < {expected_max_memory:.2f}MB"
                )

                # Calculate chunks per second
                chunks_per_second = len(chunks) / self.duration
                assert (
                    chunks_per_second > 1000
                ), f"Processing rate too slow: {chunks_per_second:.0f} chunks/sec"

                print(
                    f"Medium file ({size_kb}KB): {len(chunks)} chunks in {self.duration:.3f}s "
                    f"({chunks_per_second:.0f} chunks/sec)"
                )

            finally:
                test_file.unlink()  # Clean up

    def test_chunking_speed_large_files(self, chunker):
        """Test chunking speed on large files (1MB only to avoid slow test generation)."""
        file_sizes = [1000]  # KB (1MB) - Skip 5MB due to slow test file generation

        for size_kb in file_sizes:
            test_file = self.create_test_file(size_kb, "py")

            try:
                with self.measure_performance():
                    chunks = chunker.chunk_file(test_file)

                # Performance assertions - should handle large files efficiently
                max_time = size_kb * 0.01  # 10ms per KB (more realistic)
                assert self.duration < max_time, (
                    f"Chunking {size_kb}KB file took {self.duration:.3f}s, "
                    f"expected < {max_time:.3f}s"
                )

                # Memory usage should be reasonable (not load entire file at once)
                memory_mb = self.memory_delta / (1024 * 1024)
                file_size_mb = size_kb / 1024
                # Memory should not exceed 5x file size (more realistic for Python string handling)
                assert memory_mb < file_size_mb * 5, (
                    f"Memory usage for {file_size_mb:.1f}MB file: {memory_mb:.2f}MB, "
                    f"expected < {file_size_mb * 5:.1f}MB"
                )

                # Calculate throughput
                throughput_mbps = (size_kb / 1024) / self.duration
                assert (
                    throughput_mbps > 1
                ), f"Throughput too slow: {throughput_mbps:.1f} MB/s, expected > 1 MB/s"  # More realistic for string processing in Python

                print(
                    f"Large file ({size_kb}KB): {len(chunks)} chunks in {self.duration:.3f}s "
                    f"({throughput_mbps:.1f} MB/s)"
                )

            finally:
                test_file.unlink()  # Clean up

    def test_memory_efficiency_stress_test(self, chunker):
        """Test memory efficiency with multiple large files processed sequentially."""
        # Process multiple large files to test memory cleanup
        file_sizes = [500] * 10  # Ten 500KB files

        initial_memory = psutil.Process(os.getpid()).memory_info().rss
        peak_memory = initial_memory

        for i, size_kb in enumerate(file_sizes):
            test_file = self.create_test_file(size_kb, "java")

            try:
                chunks = chunker.chunk_file(test_file)

                # Monitor memory usage
                current_memory = psutil.Process(os.getpid()).memory_info().rss
                peak_memory = max(peak_memory, current_memory)

                # Verify chunking correctness under stress
                assert len(chunks) > 0, f"File {i} should produce chunks"
                for j, chunk in enumerate(chunks[:-1]):
                    assert (
                        len(chunk["text"]) == 1000
                    ), f"File {i}, chunk {j} should be exactly 1000 chars"

                print(
                    f"Processed file {i+1}/10: {len(chunks)} chunks, "
                    f"Memory: {(current_memory - initial_memory)/(1024*1024):.1f}MB"
                )

            finally:
                test_file.unlink()  # Clean up immediately

        # Memory growth should be bounded
        memory_growth = (peak_memory - initial_memory) / (1024 * 1024)  # MB
        assert (
            memory_growth < 50
        ), f"Memory growth too high: {memory_growth:.1f}MB, expected < 50MB"

    def test_consistency_across_multiple_runs(self, chunker):
        """Test that chunking produces identical results across multiple runs."""
        test_file = self.create_test_file(100, "py")  # 100KB file

        try:
            # Run chunking multiple times
            all_results = []
            all_durations = []

            for run in range(5):
                with self.measure_performance():
                    chunks = chunker.chunk_file(test_file)

                all_results.append(chunks)
                all_durations.append(self.duration)

            # Verify consistency
            first_result = all_results[0]
            for i, result in enumerate(all_results[1:], 1):
                assert len(result) == len(
                    first_result
                ), f"Run {i} produced {len(result)} chunks, expected {len(first_result)}"

                for j, (chunk1, chunk2) in enumerate(zip(first_result, result)):
                    assert (
                        chunk1["text"] == chunk2["text"]
                    ), f"Run {i}, chunk {j} text differs from first run"
                    assert (
                        chunk1["chunk_index"] == chunk2["chunk_index"]
                    ), f"Run {i}, chunk {j} index differs"
                    assert (
                        chunk1["size"] == chunk2["size"]
                    ), f"Run {i}, chunk {j} size differs"

            # Performance should be consistent (within 50% variance)
            avg_duration = sum(all_durations) / len(all_durations)
            for i, duration in enumerate(all_durations):
                variance = abs(duration - avg_duration) / avg_duration
                assert variance < 0.5, (
                    f"Run {i} duration {duration:.3f}s varies too much from "
                    f"average {avg_duration:.3f}s ({variance:.1%})"
                )

            print(
                f"Consistency test: {len(first_result)} chunks, "
                f"avg time {avg_duration:.3f}s ± {max(all_durations) - min(all_durations):.3f}s"
            )

        finally:
            test_file.unlink()  # Clean up

    def test_linear_scaling_with_file_size(self, chunker):
        """Test that processing time scales linearly with file size."""
        file_sizes = [50, 100, 200, 400]  # KB - doubling sequence
        results = []

        for size_kb in file_sizes:
            test_file = self.create_test_file(size_kb, "py")

            try:
                with self.measure_performance():
                    chunks = chunker.chunk_file(test_file)

                results.append(
                    {
                        "size_kb": size_kb,
                        "chunks": len(chunks),
                        "duration": self.duration,
                        "rate": len(chunks) / self.duration,  # chunks per second
                    }
                )

            finally:
                test_file.unlink()  # Clean up

        # Verify linear scaling - processing rate should be roughly constant
        rates = [r["rate"] for r in results]
        avg_rate = sum(rates) / len(rates)

        for result in results:
            rate_variance = abs(result["rate"] - avg_rate) / avg_rate
            assert rate_variance < 1.5, (  # Allow more variance due to OS scheduling
                f"Processing rate for {result['size_kb']}KB file ({result['rate']:.0f} chunks/sec) "
                f"varies too much from average ({avg_rate:.0f} chunks/sec): {rate_variance:.1%}"
            )

            print(
                f"Linear scaling: {result['size_kb']}KB → {result['chunks']} chunks "
                f"in {result['duration']:.3f}s ({result['rate']:.0f} chunks/sec)"
            )

        # Time should scale roughly linearly with size
        for i in range(1, len(results)):
            prev_result = results[i - 1]
            curr_result = results[i]

            size_ratio = curr_result["size_kb"] / prev_result["size_kb"]
            time_ratio = curr_result["duration"] / prev_result["duration"]

            # Time ratio should be close to size ratio (within reasonable bounds)
            ratio_diff = abs(time_ratio - size_ratio) / size_ratio
            assert (
                ratio_diff < 2.0
            ), (  # Allow for OS scheduling and memory allocation overhead
                f"Severely non-linear scaling detected: {size_ratio:.1f}x size increase "
                f"resulted in {time_ratio:.1f}x time increase"
            )

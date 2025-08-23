# Parallel Processing Performance Test

## Overview

The `tests/integration/performance/` directory contains comprehensive performance tests that verify parallel processing capabilities with various embedding providers. These tests are part of the organized test structure and validate performance characteristics across different threading configurations.

## What It Tests

This test exercises the queue-based parallel embedding generation layer specifically against VoyageAI with:

- **1 thread** vs **4 threads** vs **8 threads**
- Same set of **15 realistic code chunks** for all configurations
- Measures **embeddings per second (emb/s)** for each configuration
- **Fails if velocity doesn't improve** with more threads

## Requirements

- VoyageAI API key in environment (`VOYAGE_API_KEY`)
- VoyageAI service available and responsive

## Test Location and Structure

### File Location
```bash
tests/integration/performance/test_parallel_voyage_performance.py
```

### Related Performance Tests
- `test_parallel_throughput_engine.py` - General throughput engine testing
- `test_payload_index_performance_*.py` - Payload index performance validation
- `test_cancellation_high_throughput_processor.py` - Cancellation under load

## Running the Test

```bash
# Run all performance tests
pytest tests/integration/performance/ -v

# Run specific parallel performance test
pytest tests/integration/performance/test_parallel_voyage_performance.py -v

# Run with performance markers
pytest -m performance -v
```

## Expected Results

The test validates:

1. **4 threads ≥ 1.5x faster than 1 thread**
2. **8 threads ≥ 1.2x faster than 4 threads**  
3. **All configurations ≥ 1.0 emb/s absolute performance**

## Example Output

```
🚀 Testing VoyageAI Parallel Processing Performance
📊 Testing with 15 code chunks
🔗 Provider: voyage
🤖 Model: voyage-code-2

🧵 Testing with 1 threads...
  ✅ 1 threads: 3.21 emb/s in 4.67s

🧵 Testing with 4 threads...  
  ✅ 4 threads: 8.45 emb/s in 1.78s

🧵 Testing with 8 threads...
  ✅ 8 threads: 12.33 emb/s in 1.22s

📈 Performance Summary
 1 threads:   3.21 emb/s |   4.67s total | 15/15 successful
 4 threads:   8.45 emb/s |   1.78s total | 15/15 successful  
 8 threads:  12.33 emb/s |   1.22s total | 15/15 successful

🔄 Performance Improvements:
   1→4 threads: 2.63x improvement
   4→8 threads: 1.46x improvement

✅ All parallel processing tests passed!
```

## Purpose

This test ensures that:
- Parallel processing actually works (no queue bottlenecks)
- Thread scaling provides real performance benefits
- VoyageAI API handles concurrent requests properly
- No defects introduced in the parallel processing pipeline
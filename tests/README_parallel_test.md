# Parallel Processing Performance Test

## Overview

`test_parallel_voyage_performance.py` is a comprehensive test that verifies VoyageAI parallel processing performance with the `VectorCalculationManager`.

## What It Tests

This test exercises the queue-based parallel embedding generation layer specifically against VoyageAI with:

- **1 thread** vs **4 threads** vs **8 threads**
- Same set of **15 realistic code chunks** for all configurations
- Measures **embeddings per second (emb/s)** for each configuration
- **Fails if velocity doesn't improve** with more threads

## Requirements

- VoyageAI API key in environment (`VOYAGE_API_KEY`)
- VoyageAI service available and responsive

## Running the Test

```bash
# Run with pytest
pytest tests/test_parallel_voyage_performance.py -v

# Run directly
python tests/test_parallel_voyage_performance.py
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
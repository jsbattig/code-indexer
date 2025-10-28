# Story: Implement POC Test Framework

**Story ID:** S00-01
**Feature:** F00 - Proof of Concept
**Priority:** Critical
**Points:** 8
**Dependencies:** None

## User Story

As a **developer**, I want to **validate filesystem-based vector search performance** so that **we can make an informed Go/No-Go decision before implementing the full system**.

**User Requirement Citation:** *"I want it to be about doing a proof of concept, where you lay on disk mocked structures emulating differing levels of indexing size... I want you run the OS commands to fetch the data, and do the in memory filtering, and time it."*

## Acceptance Criteria

✅ **Given** a configuration for test parameters (scale, dimensions, depth)
   **When** I run the POC generator
   **Then** it creates mock vector data with the specified structure

✅ **Given** mock vector data on disk
   **When** I run query simulations
   **Then** it measures and reports query performance metrics

✅ **Given** multiple depth factor configurations
   **When** I run the comparison tool
   **Then** it identifies the optimal depth factor for 40K vectors

✅ **Given** completed performance tests
   **When** I review the report
   **Then** it provides clear Go/No-Go recommendation with supporting data

## Technical Implementation

### 1. Mock Data Generator (`poc_data_generator.py`)

```python
class MockVectorGenerator:
    def __init__(self, config):
        self.num_vectors = config['num_vectors']
        self.reduced_dims = config['reduced_dims']
        self.quantization_bits = config['quantization_bits']
        self.depth_factor = config['depth_factor']
        self.output_dir = Path(config['output_dir'])

    def generate_projection_matrix(self):
        """Create deterministic random projection matrix"""
        np.random.seed(42)  # Reproducible
        return np.random.randn(1536, self.reduced_dims)

    def quantize_vector(self, vector):
        """Quantize reduced vector to bit representation"""
        if self.quantization_bits == 1:
            return (vector > 0).astype(int)
        elif self.quantization_bits == 2:
            # 2-bit quantization into 4 levels
            quartiles = np.percentile(vector, [25, 50, 75])
            quantized = np.digitize(vector, quartiles)
            return quantized

    def vector_to_path(self, quantized_vector):
        """Convert quantized vector to filesystem path"""
        # Convert to hex representation
        hex_string = ''.join(format(x, 'x') for x in quantized_vector)

        # Split based on depth factor
        path_parts = []
        for i in range(0, len(hex_string), self.depth_factor):
            path_parts.append(hex_string[i:i+self.depth_factor])
            if len(path_parts) >= 8:  # Max depth limit
                break

        return Path(*path_parts)

    def generate_mock_data(self):
        """Generate full mock dataset"""
        projection_matrix = self.generate_projection_matrix()

        for i in range(self.num_vectors):
            # Generate random 1536-dim vector
            full_vector = np.random.randn(1536)

            # Project to lower dimensions
            reduced = full_vector @ projection_matrix

            # Quantize
            quantized = self.quantize_vector(reduced)

            # Get filesystem path
            rel_path = self.vector_to_path(quantized)
            full_path = self.output_dir / rel_path

            # Create directory
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Write JSON file
            vector_data = {
                'id': f'vec_{i:06d}',
                'file_path': f'src/file_{i:04d}.py',
                'start_line': i * 10,
                'end_line': i * 10 + 50,
                'vector': full_vector.tolist(),
                'metadata': {
                    'indexed_at': '2025-01-23T10:00:00Z',
                    'model': 'voyage-code-3'
                }
            }

            json_file = full_path / f'vector_{i:06d}.json'
            json_file.write_text(json.dumps(vector_data))
```

### 2. Performance Test Harness (`poc_performance_test.py`)

```python
class PerformanceTestHarness:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.results = []

    def clear_os_cache(self):
        """Clear OS filesystem cache (Linux)"""
        if platform.system() == 'Linux':
            subprocess.run(['sync'])
            subprocess.run(['sudo', 'echo', '3', '>', '/proc/sys/vm/drop_caches'])

    def measure_query(self, query_vector, neighbor_levels=2):
        """Measure single query performance"""
        start_total = time.perf_counter()

        # Quantize query vector
        start_quantize = time.perf_counter()
        query_path = self.vector_to_path(self.quantize_vector(query_vector))
        time_quantize = time.perf_counter() - start_quantize

        # Find neighbor paths (Hamming distance)
        start_traverse = time.perf_counter()
        paths = self.find_neighbor_paths(query_path, neighbor_levels)
        time_traverse = time.perf_counter() - start_traverse

        # Load JSON files
        start_load = time.perf_counter()
        vectors = []
        for path in paths:
            json_files = path.glob('*.json')
            for json_file in json_files:
                with open(json_file) as f:
                    vectors.append(json.load(f))
        time_load = time.perf_counter() - start_load

        # Rank by cosine similarity
        start_rank = time.perf_counter()
        similarities = []
        for vec_data in vectors:
            similarity = self.cosine_similarity(query_vector, vec_data['vector'])
            similarities.append((similarity, vec_data))
        similarities.sort(reverse=True, key=lambda x: x[0])
        top_k = similarities[:10]
        time_rank = time.perf_counter() - start_rank

        time_total = time.perf_counter() - start_total

        return {
            'time_total_ms': time_total * 1000,
            'time_quantize_ms': time_quantize * 1000,
            'time_traverse_ms': time_traverse * 1000,
            'time_load_ms': time_load * 1000,
            'time_rank_ms': time_rank * 1000,
            'files_loaded': len(vectors),
            'results_returned': len(top_k),
            'over_fetch_ratio': len(vectors) / max(len(top_k), 1)
        }

    def run_test_suite(self, num_queries=100):
        """Run complete test suite"""
        results = []

        for i in range(num_queries):
            # Generate random query
            query_vector = np.random.randn(1536)

            # Test different neighbor levels
            for neighbors in [0, 1, 2]:
                result = self.measure_query(query_vector, neighbors)
                result['query_id'] = i
                result['neighbor_levels'] = neighbors
                results.append(result)

        return results
```

### 3. Depth Factor Analyzer (`poc_depth_analyzer.py`)

```python
class DepthFactorAnalyzer:
    def __init__(self, test_results):
        self.results = test_results

    def analyze_depth_performance(self):
        """Compare performance across depth factors"""
        depth_summary = {}

        for depth in [2, 3, 4, 6, 8]:
            depth_results = [r for r in self.results if r['depth_factor'] == depth]

            depth_summary[depth] = {
                'avg_query_time_ms': np.mean([r['time_total_ms'] for r in depth_results]),
                'p95_query_time_ms': np.percentile([r['time_total_ms'] for r in depth_results], 95),
                'avg_over_fetch': np.mean([r['over_fetch_ratio'] for r in depth_results]),
                'avg_files_per_dir': self.calculate_files_per_dir(depth),
                'meets_target': np.percentile([r['time_total_ms'] for r in depth_results], 95) < 1000
            }

        return depth_summary

    def generate_recommendation(self):
        """Generate Go/No-Go recommendation"""
        summary = self.analyze_depth_performance()

        # Find optimal depth
        optimal_depth = None
        for depth, metrics in summary.items():
            if metrics['meets_target'] and metrics['avg_files_per_dir'] <= 10:
                if optimal_depth is None or metrics['avg_query_time_ms'] < summary[optimal_depth]['avg_query_time_ms']:
                    optimal_depth = depth

        if optimal_depth:
            return {
                'decision': 'GO',
                'optimal_depth': optimal_depth,
                'expected_performance': summary[optimal_depth],
                'rationale': f"Depth factor {optimal_depth} achieves <1s query time with reasonable over-fetch"
            }
        else:
            return {
                'decision': 'NO-GO',
                'rationale': "No configuration meets performance targets",
                'best_attempt': min(summary.items(), key=lambda x: x[1]['avg_query_time_ms'])
            }
```

### 4. POC Runner Script (`run_poc.py`)

```python
def run_complete_poc():
    """Execute complete POC test suite"""

    configs = [
        {'num_vectors': 1000, 'reduced_dims': 64, 'bits': 2, 'depth': 2},
        {'num_vectors': 10000, 'reduced_dims': 64, 'bits': 2, 'depth': 3},
        {'num_vectors': 40000, 'reduced_dims': 64, 'bits': 2, 'depth': 4},
        {'num_vectors': 100000, 'reduced_dims': 64, 'bits': 2, 'depth': 4},
    ]

    all_results = []

    for config in configs:
        print(f"Testing {config['num_vectors']} vectors, depth={config['depth']}")

        # Generate mock data
        generator = MockVectorGenerator(config)
        generator.generate_mock_data()

        # Run performance tests
        harness = PerformanceTestHarness(config['output_dir'])
        results = harness.run_test_suite(num_queries=100)

        # Add config to results
        for r in results:
            r.update(config)

        all_results.extend(results)

    # Analyze results
    analyzer = DepthFactorAnalyzer(all_results)
    recommendation = analyzer.generate_recommendation()

    # Generate report
    print("\n" + "="*50)
    print("POC RESULTS")
    print("="*50)
    print(f"Decision: {recommendation['decision']}")
    if recommendation['decision'] == 'GO':
        print(f"Optimal Depth Factor: {recommendation['optimal_depth']}")
        print(f"Expected Performance: {recommendation['expected_performance']}")
    print(f"Rationale: {recommendation['rationale']}")

    # Save detailed results
    with open('poc_results.json', 'w') as f:
        json.dump({
            'results': all_results,
            'recommendation': recommendation
        }, f, indent=2)
```

## Test Data

### Test Configurations

| Scale | Vectors | Depth | Expected Time | Expected Files/Dir |
|-------|---------|-------|---------------|-------------------|
| Small | 1K | 2 | <100ms | 1-3 |
| Medium | 10K | 3 | <300ms | 3-7 |
| Target | 40K | 4 | <1000ms | 5-10 |
| Large | 100K | 4 | <2000ms | 10-20 |

## Deliverables

1. **Mock Data Generator** - Script to create test datasets
2. **Performance Harness** - Measure query performance
3. **Depth Analyzer** - Compare configurations
4. **Results Report** - JSON with all metrics
5. **Go/No-Go Decision** - Clear recommendation

## Unit Test Coverage Requirements

**Test Strategy:** POC framework IS the test - use real filesystem operations with deterministic data

**Required Tests:**

### Performance Validation Tests
```python
def test_40k_vectors_query_under_1_second():
    """GIVEN 40K vectors in filesystem with optimal config
    WHEN performing 100 query simulations
    THEN P95 query time < 1s"""
    # Generate 40K test vectors
    # Run query simulations
    # Assert P95 < 1000ms

def test_depth_factor_4_has_optimal_files_per_directory():
    """GIVEN depth factor 4 with 40K vectors
    WHEN analyzing directory distribution
    THEN average files per directory is 1-10"""
    # Generate data with depth=4
    # Count files in all leaf directories
    # Assert 1 <= avg_files <= 10

def test_over_fetch_ratio_acceptable():
    """GIVEN search with 2-level neighbors
    WHEN measuring over-fetch
    THEN ratio < 20x (acceptable RAM usage)"""
    # Search simulation
    # Count: files loaded / results returned
    # Assert ratio < 20
```

### Determinism Tests
```python
def test_same_vector_produces_same_path():
    """GIVEN the same 1536-dim vector quantized twice
    WHEN using same projection matrix
    THEN produces identical filesystem path"""
    # Use seeded random for reproducibility

def test_projection_matrix_is_reusable():
    """GIVEN saved projection matrix
    WHEN loaded and used for quantization
    THEN produces same paths as original"""
    # Save matrix, reload, verify paths match
```

### Scalability Tests
```python
def test_scales_sublinearly():
    """GIVEN tests at 10K, 40K, 100K vectors
    WHEN measuring query time
    THEN time increase is sublinear"""
    # 100K should NOT be 10x slower than 10K
```

**Test Data:**
- Deterministic vectors (seeded random: np.random.seed(42))
- Real filesystem directories in /tmp
- No mocking of file I/O operations

**Performance Assertions:**
- Query time P95 < 1s for 40K vectors
- Files per directory 1-10 (optimal range)
- Over-fetch ratio < 20x

## Definition of Done

✅ POC scripts created and tested
✅ Performance tests run for all configurations
✅ Results analyzed and documented
✅ Go/No-Go recommendation provided
✅ Optimal depth factor identified for 40K vectors
✅ Performance report shows <1s query time achievable
✅ **Unit tests validate determinism and scalability**
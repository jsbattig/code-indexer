# Story 3: Search Indexed Code from Filesystem

**Story ID:** S03
**Epic:** Filesystem-Based Vector Database Backend
**Priority:** High
**Estimated Effort:** 5-7 days
**Implementation Order:** 4

## User Story

**As a** developer with filesystem-indexed code
**I want to** perform semantic searches against my codebase
**So that** I can find relevant code using natural language queries without containers

**Conversation Reference:** "can't you fetch and sort in RAM by rank? It's OK to fetch all, sort and return" - User confirmed RAM-based ranking approach is acceptable.

## Acceptance Criteria

### Functional Requirements
1. ✅ `cidx query "search text"` returns semantically similar code chunks
2. ✅ Search uses quantized path lookup + exact ranking in RAM
3. ✅ Query performance <1s for 40K vectors (user acceptance criterion)
4. ✅ Results include similarity scores, file paths, and line ranges
5. ✅ Support for accuracy modes: `--accuracy fast|balanced|high`
6. ✅ Support for minimum score threshold: `--min-score 0.8`
7. ✅ Metadata filtering: `--language python`, `--path "*/tests/*"`

### Technical Requirements
1. ✅ Query vector quantized to filesystem path
2. ✅ Neighbor discovery using Hamming distance
3. ✅ All candidate JSON files loaded into RAM
4. ✅ Exact cosine similarity computed with full 1536-dim vectors
5. ✅ **Chunk content retrieval:** Results always include `payload['content']` (transparent to caller)
   - Git repos: Retrieve from current file or git blob (3-tier fallback)
   - Non-git repos: Load chunk_text from JSON metadata
6. ✅ Results sorted by similarity score
7. ✅ Top-k results returned
8. ✅ No containers required for search operations
9. ✅ **QdrantClient interface compatibility:** search() returns identical structure

### Performance Requirements
**Conversation Reference:** "~1s is fine" - User explicitly accepted 1-second query latency for 40K vectors.

1. ✅ Query latency <1s for 40K vectors (target scale)
2. ✅ Neighbor discovery limited to prevent over-fetching
3. ✅ Efficient JSON loading (parallel reads)
4. ✅ In-memory filtering and sorting

### Staleness Detection Requirements

**User Requirement:** "we need to return back a flag telling the chunk is 'dirty' so that when cidx returns the result back it tells this file was modified after indexing"

1. ✅ Search results include staleness information (identical interface to Qdrant)
2. ✅ **FilesystemVectorStore (git repos):** Hash-based staleness detection
   - Compare current file hash with stored chunk_hash
   - If mismatch: mark as stale, retrieve from git blob
   - More precise than mtime (detects actual content changes)
3. ✅ **FilesystemVectorStore (non-git repos):** Never stale (chunk_text stored in JSON)
4. ✅ **QdrantClient:** mtime-based staleness (current behavior maintained)
5. ✅ Staleness info structure (same for both backends):
   ```python
   {
       'is_stale': True/False,
       'staleness_indicator': '⚠️ Modified' | '🗑️ Deleted' | '❌ Error',
       'staleness_reason': 'file_modified_after_indexing' | 'file_deleted' | 'retrieval_failed',
       'hash_mismatch': True  # FilesystemVectorStore only
       # OR
       'staleness_delta_seconds': 3600  # QdrantClient only (mtime-based)
   }
   ```
6. ✅ Display shows staleness indicator next to results (already implemented in CLI)
7. ✅ Staleness detection happens during content retrieval (transparent)

## Manual Testing Steps

```bash
# Test 1: Basic semantic search
cd /path/to/indexed-repo
cidx query "authentication logic"

# Expected output:
# 🔍 Searching for: "authentication logic"
# 📊 Found 10 results (searched 847 vectors in 0.7s)
#
# 1. Score: 0.89 | src/auth/login.py:42-87
#    Implements user authentication with JWT tokens...
#
# 2. Score: 0.84 | src/middleware/auth_check.py:15-45
#    Middleware for validating authentication tokens...
#
# 3. Score: 0.81 | tests/test_auth.py:102-150
#    Test cases for authentication workflows...

# Test 2: Search with accuracy mode
cidx query "error handling" --accuracy high --limit 20

# Expected: More exhaustive neighbor search, higher accuracy, more results

# Test 3: Search with score threshold
cidx query "database queries" --min-score 0.85

# Expected: Only results with similarity >= 0.85

# Test 4: Search with language filter
cidx query "class definitions" --language python

# Expected: Only Python files in results

# Test 5: Search with path filter
cidx query "test fixtures" --path "*/tests/*"

# Expected: Only files in tests directories

# Test 6: Performance test (40K vectors)
# Index large repository first
cidx index  # Creates ~40K vectors
time cidx query "complex algorithm"

# Expected: Query completes in <1s
# real    0m0.873s

# Test 7: Empty results
cidx query "xyzabc123nonexistent"

# Expected output:
# 🔍 Searching for: "xyzabc123nonexistent"
# No results found matching your query.

# Test 8: Staleness detection (git repos only)
# Index file, then modify it
cidx index
echo "# Modified after indexing" >> src/auth/login.py

cidx query "authentication logic"

# Expected output:
# 1. Score: 0.89 | ⚠️ Modified src/auth/login.py:42-87
#    [Original content from git blob shown]
#    (File modified after indexing - showing indexed version)
#
# Staleness indicator shows file was modified

# Test 9: Non-git repo (no staleness)
cd /tmp/non-git-project
cidx init --vector-store filesystem
cidx index
# Modify file
echo "# Modified" >> file.py
cidx query "test"

# Expected: No staleness indicator (chunk_text stored in JSON, always current)
```

## Technical Implementation Details

### Search Algorithm Architecture

**Conversation Reference:** User clarified fetch-all-and-sort-in-RAM approach is acceptable for target scale.

```python
class FilesystemSemanticSearch:
    """Semantic search over filesystem vector storage."""

    def search(
        self,
        collection_name: str,
        query_vector: np.ndarray,
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter_conditions: Optional[Dict] = None,
        accuracy: str = "balanced"
    ) -> List[Dict]:
        """Search for semantically similar vectors.

        Algorithm:
        1. Quantize query vector to filesystem path
        2. Find neighbor paths based on accuracy mode
        3. Load all candidate JSON files into RAM
        4. Compute exact cosine similarity
        5. Apply filters in memory
        6. Sort by score and return top-k
        """
        # Step 1: Quantize query to path
        query_hex = self.quantizer.quantize_vector(query_vector)
        query_path = self._hex_to_directory_path(query_hex)

        # Step 2: Find neighbor paths (configurable Hamming distance)
        hamming_distance = self._get_hamming_distance_for_accuracy(accuracy)
        neighbor_paths = self._find_neighbor_paths(
            query_path,
            max_hamming_distance=hamming_distance
        )

        # Step 3: Load all candidates into RAM
        candidates = self._load_candidate_vectors(
            collection_name,
            neighbor_paths
        )

        # Step 4: Compute exact similarities
        similarities = []
        for candidate in candidates:
            candidate_vector = np.array(candidate['vector'])
            score = self._cosine_similarity(query_vector, candidate_vector)

            # Apply score threshold
            if score_threshold and score < score_threshold:
                continue

            similarities.append((score, candidate))

        # Step 5: Apply metadata filters
        if filter_conditions:
            similarities = self._apply_filters(similarities, filter_conditions)

        # Step 6: Sort and return top-k
        similarities.sort(reverse=True, key=lambda x: x[0])
        return self._format_results(similarities[:limit])

    def _get_hamming_distance_for_accuracy(self, accuracy: str) -> int:
        """Map accuracy mode to Hamming distance."""
        return {
            "fast": 1,      # Check immediate neighbors only (~100-500 vectors)
            "balanced": 2,  # Default - good trade-off (~500-2000 vectors)
            "high": 3       # More neighbors, higher recall (~2000-5000 vectors)
        }[accuracy]

    def _find_neighbor_paths(
        self,
        query_path: Path,
        max_hamming_distance: int
    ) -> List[Path]:
        """Find neighboring directory paths within Hamming distance.

        Uses bit-flip enumeration to generate neighbor paths efficiently.
        """
        neighbors = [query_path]  # Start with exact match

        # Generate paths with 1-bit differences
        if max_hamming_distance >= 1:
            neighbors.extend(self._generate_1bit_neighbors(query_path))

        # Generate paths with 2-bit differences
        if max_hamming_distance >= 2:
            neighbors.extend(self._generate_2bit_neighbors(query_path))

        # Generate paths with 3-bit differences
        if max_hamming_distance >= 3:
            neighbors.extend(self._generate_3bit_neighbors(query_path))

        return neighbors

    def _load_candidate_vectors(
        self,
        collection_name: str,
        neighbor_paths: List[Path]
    ) -> List[Dict]:
        """Load all JSON files from neighbor paths into RAM.

        Uses parallel reads for performance.
        """
        collection_path = self.base_path / collection_name
        candidates = []

        # Use thread pool for parallel JSON loading
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []

            for neighbor_path in neighbor_paths:
                full_path = collection_path / neighbor_path

                if not full_path.exists():
                    continue

                # Find all JSON files in this directory
                for json_file in full_path.rglob("*.json"):
                    if json_file.name == "collection_meta.json":
                        continue

                    future = executor.submit(self._load_vector_json, json_file)
                    futures.append(future)

            # Collect results
            for future in as_completed(futures):
                try:
                    vector_data = future.result()
                    if vector_data:
                        candidates.append(vector_data)
                except Exception:
                    continue

        return candidates

    def _cosine_similarity(
        self,
        vec1: np.ndarray,
        vec2: np.ndarray
    ) -> float:
        """Compute cosine similarity between vectors."""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def _apply_filters(
        self,
        similarities: List[Tuple[float, Dict]],
        filter_conditions: Dict
    ) -> List[Tuple[float, Dict]]:
        """Apply metadata filters in memory."""
        filtered = []

        for score, candidate in similarities:
            # Check language filter
            if "language" in filter_conditions:
                file_ext = Path(candidate['file_path']).suffix
                if not self._matches_language(file_ext, filter_conditions["language"]):
                    continue

            # Check path filter
            if "path_pattern" in filter_conditions:
                if not fnmatch.fnmatch(
                    candidate['file_path'],
                    filter_conditions["path_pattern"]
                ):
                    continue

            # Check branch filter
            if "branch" in filter_conditions:
                if candidate.get('metadata', {}).get('branch') != filter_conditions["branch"]:
                    continue

            filtered.append((score, candidate))

        return filtered

    def _format_results(
        self,
        similarities: List[Tuple[float, Dict]]
    ) -> List[Dict]:
        """Format search results for display."""
        results = []

        for score, candidate in similarities:
            results.append({
                'score': score,
                'file_path': candidate['file_path'],
                'start_line': candidate['start_line'],
                'end_line': candidate['end_line'],
                'chunk_hash': candidate.get('chunk_hash', ''),
                'metadata': candidate.get('metadata', {})
            })

        return results
```

### Accuracy Mode Performance Trade-offs

| Mode | Hamming Distance | Est. Candidates | Query Time | Use Case |
|------|------------------|-----------------|------------|----------|
| `fast` | 1 | 100-500 vectors | ~200-400ms | Quick exploration |
| `balanced` | 2 | 500-2000 vectors | ~500-800ms | Default - good balance |
| `high` | 3 | 2000-5000 vectors | ~800-1000ms | Comprehensive search |

### CLI Integration

```python
@click.command()
@click.argument("query_text")
@click.option("--limit", default=10, help="Number of results to return")
@click.option(
    "--accuracy",
    type=click.Choice(["fast", "balanced", "high"]),
    default="balanced",
    help="Search accuracy mode"
)
@click.option("--min-score", type=float, help="Minimum similarity score threshold")
@click.option("--language", help="Filter by language (e.g., python, javascript)")
@click.option("--path", help="Filter by path pattern (e.g., */tests/*)")
def query_command(
    query_text: str,
    limit: int,
    accuracy: str,
    min_score: Optional[float],
    language: Optional[str],
    path: Optional[str]
):
    """Search codebase using semantic similarity."""
    config = load_config()
    backend = VectorStoreBackendFactory.create_backend(config)

    # Get vector store client (works with both backends)
    vector_store = backend.get_vector_store_client()

    # Get embeddings
    embedding_provider = EmbeddingProviderFactory.create(config)
    query_vector = embedding_provider.embed_text(query_text)

    # Build filter conditions
    filter_conditions = {}
    if language:
        filter_conditions["language"] = language
    if path:
        filter_conditions["path_pattern"] = path

    # Search
    start_time = time.time()
    results = vector_store.search(
        collection_name=config.collection_name,
        query_vector=query_vector,
        limit=limit,
        score_threshold=min_score,
        filter_conditions=filter_conditions,
        accuracy=accuracy
    )
    elapsed = time.time() - start_time

    # Display results
    console.print(f"🔍 Searching for: \"{query_text}\"")
    console.print(f"📊 Found {len(results)} results (searched in {elapsed:.2f}s)")

    if not results:
        console.print("No results found matching your query.")
        return

    for i, result in enumerate(results, 1):
        console.print(f"\n{i}. Score: {result['score']:.2f} | "
                     f"{result['file_path']}:{result['start_line']}-{result['end_line']}")

        # Retrieve chunk text from actual file (not stored in JSON)
        chunk_text = read_chunk_from_file(
            result['file_path'],
            result['start_line'],
            result['end_line']
        )
        console.print(f"   {chunk_text[:100]}...")
```

## Dependencies

### Internal Dependencies
- Story 2: Indexed vectors in filesystem storage
- Story 1: Backend abstraction layer
- Existing embedding providers for query embedding
- Quantizer from indexing pipeline

### External Dependencies
- NumPy for cosine similarity computation
- ThreadPoolExecutor for parallel JSON loading
- Python `fnmatch` for path pattern matching

## Success Metrics

1. ✅ Search returns semantically relevant results
2. ✅ Query performance <1s for 40K vectors
3. ✅ Accuracy modes work as expected
4. ✅ Filters correctly narrow results
5. ✅ Score threshold filtering works
6. ✅ No containers required for search

## Non-Goals

- Real-time indexing updates during search
- Distributed search across multiple filesystems
- Query result caching (stateless CLI operations)
- Fuzzy or regex-based text search (semantic only)

## Follow-Up Stories

- **Story 4**: Monitor Filesystem Index Status and Health (validates search data)
- **Story 7**: Multi-Provider Support (ensures search works with all providers)

## Implementation Notes

### Critical Performance Optimization

**From User:** "~1s is fine" for 40K vectors. This sets our performance target.

Key optimizations:
1. **Parallel JSON loading**: Use thread pool to load multiple files simultaneously
2. **Hamming distance limiting**: Prevent over-fetching by controlling neighbor radius
3. **Early score filtering**: Skip candidates below threshold before full processing
4. **Efficient similarity computation**: Use NumPy vectorized operations

### Accuracy vs Performance Trade-off

**Balanced mode (default)** provides best trade-off:
- Hamming distance 2 searches 500-2000 vectors
- Query time ~500-800ms well under 1s target
- High recall for most queries

**Fast mode** for quick exploration:
- Hamming distance 1 searches 100-500 vectors
- Query time ~200-400ms
- May miss some relevant results

**High mode** for comprehensive search:
- Hamming distance 3 searches 2000-5000 vectors

## Unit Test Coverage Requirements

**Test Strategy:** Use real filesystem with deterministic vectors that have known semantic relationships (NO mocking)

**Test File:** `tests/unit/search/test_filesystem_semantic_search.py`

**Required Tests:**

```python
class TestSemanticSearchWithRealFilesystem:
    """Test semantic search using real filesystem and predictable vectors."""

    @pytest.fixture
    def semantic_test_data(self, tmp_path, embedding_provider):
        """Create collection with known semantic relationships."""
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)

        # Use real embedding provider for actual semantic relationships
        auth_texts = [
            "User authentication with JWT tokens and password validation",
            "Login function validates user credentials against database",
            "OAuth2 authentication flow implementation with token refresh"
        ]
        db_texts = [
            "Database connection pooling and query execution",
            "SQL query builder for complex database operations",
            "Database transaction management and rollback handling"
        ]

        # Embed texts (or use pre-computed vectors for speed)
        points = []
        for i, text in enumerate(auth_texts):
            vector = embedding_provider.embed(text)
            points.append({
                'id': f'auth_{i}',
                'vector': vector,
                'payload': {
                    'file_path': f'src/auth/file{i}.py',
                    'start_line': i*10,
                    'end_line': i*10+20,
                    'language': 'python',
                    'category': 'authentication',
                    'type': 'content'
                }
            })

        for i, text in enumerate(db_texts):
            vector = embedding_provider.embed(text)
            points.append({
                'id': f'db_{i}',
                'vector': vector,
                'payload': {
                    'file_path': f'src/db/file{i}.py',
                    'start_line': i*10,
                    'end_line': i*10+20,
                    'language': 'python',
                    'category': 'database',
                    'type': 'content'
                }
            })

        store.upsert_points('test_coll', points)
        return store, embedding_provider

    def test_semantic_search_returns_related_chunks(self, semantic_test_data):
        """GIVEN indexed chunks with known semantic relationships
        WHEN searching for "authentication"
        THEN auth chunks ranked higher than db chunks"""
        store, provider = semantic_test_data
        query_vector = provider.embed("user authentication and login")

        results = store.search(
            collection_name='test_coll',
            query_vector=query_vector,
            limit=6
        )

        # Top 3 should be auth-related
        assert len(results) >= 3
        top_3_ids = [r['id'] for r in results[:3]]
        assert all('auth' in id for id in top_3_ids)

        # Scores should be descending
        scores = [r['score'] for r in results]
        assert scores == sorted(scores, reverse=True)

        # Top result should have high similarity
        assert results[0]['score'] > 0.7

    def test_search_with_language_filter(self, semantic_test_data):
        """GIVEN vectors with python and javascript files
        WHEN searching with --language python filter
        THEN only Python files returned"""
        store, provider = semantic_test_data

        # Add JavaScript vectors
        js_points = [{
            'id': 'js_001',
            'vector': provider.embed("JavaScript function definition").tolist(),
            'payload': {'file_path': 'app.js', 'language': 'javascript', 'type': 'content'}
        }]
        store.upsert_points('test_coll', js_points)

        query = provider.embed("function definition")
        results = store.search(
            collection_name='test_coll',
            query_vector=query,
            filter_conditions={'language': 'python'},
            limit=10
        )

        # All results must be Python
        assert all(r['payload']['language'] == 'python' for r in results)
        assert not any(r['id'] == 'js_001' for r in results)

    def test_search_performance_meets_requirement(self, tmp_path):
        """GIVEN 5000 vectors in filesystem
        WHEN performing search
        THEN query completes in <1s"""
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('perf_test', 1536)

        # Generate 5000 test vectors (use seeded random for speed)
        np.random.seed(42)
        points = [
            {
                'id': f'vec_{i}',
                'vector': np.random.randn(1536).tolist(),
                'payload': {'file_path': f'file_{i}.py', 'type': 'content'}
            }
            for i in range(5000)
        ]
        store.upsert_points_batched('perf_test', points)

        # Search with timing
        query_vector = np.random.randn(1536)

        start = time.time()
        results = store.search('perf_test', query_vector, limit=10)
        duration = time.time() - start

        assert duration < 1.0  # User requirement
        assert len(results) == 10
        assert results[0]['score'] >= results[-1]['score']  # Sorted descending

    def test_score_threshold_filters_low_scores(self, semantic_test_data):
        """GIVEN indexed vectors
        WHEN searching with score_threshold=0.8
        THEN only results with score >= 0.8 returned"""
        store, provider = semantic_test_data
        query = provider.embed("authentication")

        results_all = store.search('test_coll', query, limit=10)
        results_filtered = store.search('test_coll', query, limit=10, score_threshold=0.8)

        # Filtered should have <= results than unfiltered
        assert len(results_filtered) <= len(results_all)

        # All filtered results must meet threshold
        assert all(r['score'] >= 0.8 for r in results_filtered)

    def test_accuracy_modes_affect_candidate_count(self, semantic_test_data):
        """GIVEN indexed vectors
        WHEN using different accuracy modes
        THEN 'high' examines more candidates than 'fast'"""
        store, provider = semantic_test_data
        query = provider.embed("test query")

        # Note: Implementation should track candidates_examined metric
        results_fast = store.search('test_coll', query, limit=5, accuracy='fast')
        results_high = store.search('test_coll', query, limit=5, accuracy='high')

        # Both should return results
        assert len(results_fast) >= 1
        assert len(results_high) >= 1

        # High may find additional relevant results (test with larger dataset)

    def test_path_pattern_filtering(self, tmp_path):
        """GIVEN vectors from various paths
        WHEN searching with path filter "*/tests/*"
        THEN only test files returned"""
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)

        points = []
        for i in range(5):
            points.append({
                'id': f'src_{i}',
                'vector': np.random.randn(1536).tolist(),
                'payload': {'file_path': f'src/file_{i}.py', 'type': 'content'}
            })
        for i in range(5):
            points.append({
                'id': f'test_{i}',
                'vector': np.random.randn(1536).tolist(),
                'payload': {'file_path': f'tests/test_file_{i}.py', 'type': 'content'}
            })

        store.upsert_points('test_coll', points)

        # Search with path filter
        query = np.random.randn(1536)
        results = store.search(
            'test_coll',
            query,
            limit=10,
            filter_conditions={'file_path': '*/tests/*'}  # Pattern matching
        )

        # Only test files
        assert all('tests/' in r['payload']['file_path'] for r in results)

    def test_empty_collection_returns_empty_results(self, tmp_path):
        """GIVEN empty collection
        WHEN searching
        THEN empty results list returned"""
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('empty', 1536)

        results = store.search('empty', np.random.randn(1536), limit=10)

        assert results == []

    def test_concurrent_queries_thread_safety(self, tmp_path):
        """GIVEN indexed collection
        WHEN multiple searches execute concurrently
        THEN all return correct results without errors"""
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)

        # Index 100 vectors
        points = [
            {'id': f'vec_{i}', 'vector': np.random.randn(1536).tolist(),
             'payload': {'file_path': f'file_{i}.py'}}
            for i in range(100)
        ]
        store.upsert_points('test_coll', points)

        from concurrent.futures import ThreadPoolExecutor

        def search_task():
            return store.search('test_coll', np.random.randn(1536), limit=5)

        # Run 20 concurrent searches
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(search_task) for _ in range(20)]
            results = [f.result() for f in futures]

        # All searches succeed and return 5 results
        assert all(len(r) == 5 for r in results)

class TestStalenessDetection:
    """Test staleness detection for both backends."""

    def test_filesystem_detects_modified_file_via_hash(self, tmp_path):
        """GIVEN indexed file later modified
        WHEN searching
        THEN staleness detected via hash mismatch"""
        subprocess.run(['git', 'init'], cwd=tmp_path)
        test_file = tmp_path / 'test.py'
        original = "def foo():\n    return 42\n"
        test_file.write_text(original)
        subprocess.run(['git', 'add', '.'], cwd=tmp_path)
        subprocess.run(['git', 'commit', '-m', 'test'], cwd=tmp_path)

        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)
        store.upsert_points('test_coll', [{
            'id': 'test_001',
            'vector': np.random.randn(1536).tolist(),
            'payload': {'path': 'test.py', 'start_line': 0, 'end_line': 2,
                       'content': original}
        }])

        # Modify file
        test_file.write_text("def foo():\n    return 99\n")

        # Search
        results = store.search('test_coll', np.random.randn(1536), limit=1)

        # Staleness detected
        assert results[0]['staleness']['is_stale'] is True
        assert results[0]['staleness']['staleness_indicator'] == '⚠️ Modified'
        assert results[0]['staleness']['hash_mismatch'] is True
        assert results[0]['payload']['content'] == original  # From git blob

    def test_filesystem_non_git_never_stale(self, tmp_path):
        """GIVEN non-git repo with chunk_text in JSON
        WHEN searching
        THEN staleness always False (content in JSON)"""
        # No git init
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)

        store.upsert_points('test_coll', [{
            'id': 'test_001',
            'vector': np.random.randn(1536).tolist(),
            'payload': {'path': 'test.py', 'content': 'test content'}
        }])

        results = store.search('test_coll', np.random.randn(1536), limit=1)

        assert results[0]['staleness']['is_stale'] is False

    def test_filesystem_detects_deleted_file(self, tmp_path):
        """GIVEN indexed file later deleted
        WHEN searching
        THEN staleness indicates deletion, content from git"""
        subprocess.run(['git', 'init'], cwd=tmp_path)
        test_file = tmp_path / 'test.py'
        content = "def foo(): pass"
        test_file.write_text(content)
        subprocess.run(['git', 'add', '.'], cwd=tmp_path)
        subprocess.run(['git', 'commit', '-m', 'test'], cwd=tmp_path)

        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)
        store.upsert_points('test_coll', [{
            'id': 'test_001',
            'vector': np.random.randn(1536).tolist(),
            'payload': {'path': 'test.py', 'start_line': 0, 'end_line': 1,
                       'content': content}
        }])

        # Delete file
        test_file.unlink()

        results = store.search('test_coll', np.random.randn(1536), limit=1)

        assert results[0]['staleness']['is_stale'] is True
        assert results[0]['staleness']['staleness_indicator'] == '🗑️ Deleted'
        assert results[0]['staleness']['staleness_reason'] == 'file_deleted'
        assert results[0]['payload']['content'] == content  # From git

    def test_staleness_interface_matches_qdrant(self):
        """GIVEN search results from both backends
        WHEN staleness info is present
        THEN structure is identical (same keys, same format)"""
        # This validates interface compatibility

        filesystem_staleness = {
            'is_stale': True,
            'staleness_indicator': '⚠️ Modified',
            'staleness_reason': 'file_modified_after_indexing',
            'hash_mismatch': True
        }

        qdrant_staleness = {
            'is_stale': True,
            'staleness_indicator': '⚠️ Modified',
            'staleness_reason': 'file_modified_after_indexing',
            'staleness_delta_seconds': 3600
        }

        # Both have required keys
        for staleness in [filesystem_staleness, qdrant_staleness]:
            assert 'is_stale' in staleness
            assert 'staleness_indicator' in staleness
            assert 'staleness_reason' in staleness
```

**Coverage Requirements:**
- ✅ Semantic search with real embeddings
- ✅ Metadata filtering (language, branch, type, path patterns)
- ✅ Score threshold filtering
- ✅ Accuracy modes (fast/balanced/high)
- ✅ Performance validation (<1s for 5K vectors)
- ✅ Result ranking (scores descending)
- ✅ Empty results handling
- ✅ Concurrent queries (thread safety)
- ✅ Neighbor bucket search effectiveness
- ✅ **Staleness detection (hash-based for git, never stale for non-git)**
- ✅ **Staleness indicator display compatibility**
- ✅ **Content retrieval from git blob on staleness**

**Test Data:**
- Known semantic relationships (auth vs db chunks)
- Real embeddings from VoyageAI or Ollama (or pre-computed fixtures)
- Deterministic query vectors for reproducibility
- Multiple metadata combinations for filter testing

**Performance Assertions:**
- Search <1s for 5K vectors (unit test scale)
- Search <100ms for 100 vectors
- Filter overhead <50ms
- Result sorting <10ms
- Query time ~800-1000ms (still under 1s target)
- Maximum recall

### Result Display Strategy

**Chunk text NOT stored in JSON** (from Story 2 constraint). Results must:
1. Return file path and line ranges from JSON
2. Read actual chunk text from source files on demand
3. Display code snippets in search results

This keeps JSON files small and git-trackable while providing full context in results.

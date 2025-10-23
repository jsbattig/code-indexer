# Unit Test Requirements for Filesystem Vector Store Epic

**Epic:** Filesystem-Based Vector Database Backend
**Purpose:** Define comprehensive unit test coverage using real filesystem operations

## Testing Philosophy

**NO MOCKING OF FILESYSTEM** - All tests use real file I/O operations with predictable test data.

**Rationale:**
- Filesystem operations are the CORE functionality - mocking defeats the purpose
- Need to validate actual filesystem performance and behavior
- Must test on real directory structures to catch OS-specific issues
- Test data can be deterministic (seeded random vectors)
- Similar to POC approach but with assertions and edge case coverage

## Test Data Strategy

### Fixture-Based Test Data

Use `/tmp/cidx-test-fixtures/` for deterministic test data:

```python
@pytest.fixture
def test_vectors():
    """Generate deterministic test vectors."""
    np.random.seed(42)  # Deterministic
    return {
        'small': np.random.randn(10, 1536),      # 10 vectors
        'medium': np.random.randn(100, 1536),     # 100 vectors
        'large': np.random.randn(1000, 1536),     # 1K vectors
        'realistic': np.random.randn(5000, 1536)  # 5K vectors (fast enough for unit tests)
    }

@pytest.fixture
def test_collection(tmp_path):
    """Create test collection with predictable structure."""
    collection_path = tmp_path / "test_collection"
    collection_path.mkdir()

    # Create projection matrix (deterministic)
    np.random.seed(42)
    proj_matrix = np.random.randn(1536, 64) / np.sqrt(64)
    np.save(collection_path / "projection_matrix.npy", proj_matrix)

    return collection_path
```

### Known-Content Test Files

Create test vectors with **known semantic relationships** for search validation:

```python
TEST_CHUNKS = [
    {
        'id': 'auth_001',
        'text': 'User authentication with JWT tokens and password validation',
        'file_path': 'src/auth/login.py',
        'start': 10, 'end': 50,
        'metadata': {'language': 'python', 'type': 'content', 'git_branch': 'main'}
    },
    {
        'id': 'auth_002',
        'text': 'Login function authenticates users via OAuth2 flow',
        'file_path': 'src/auth/oauth.py',
        'start': 20, 'end': 60,
        'metadata': {'language': 'python', 'type': 'content', 'git_branch': 'main'}
    },
    {
        'id': 'db_001',
        'text': 'Database connection pooling and query execution',
        'file_path': 'src/db/connection.py',
        'start': 5, 'end': 30,
        'metadata': {'language': 'python', 'type': 'content', 'git_branch': 'main'}
    }
]

# Embed using real embedding provider (or use pre-computed vectors for speed)
# Store in test collection
# Verify search for "authentication" returns auth_001, auth_002 (not db_001)
```

## Story-by-Story Unit Test Requirements

### Story 0: POC (Already Complete)
- ✅ POC framework includes performance tests
- No additional unit tests required (POC validates approach)

---

### Story 1: Initialize Filesystem Backend

**Test File:** `tests/unit/backends/test_filesystem_backend.py`

**Test Cases:**

```python
class TestFilesystemBackendInitialization:
    """Test backend initialization without mocking filesystem."""

    def test_initialize_creates_directory_structure(self, tmp_path):
        """GIVEN a config with filesystem backend
        WHEN initialize() is called
        THEN .code-indexer/vectors/ directory is created"""
        config = create_test_config(vector_store_provider="filesystem")
        backend = FilesystemBackend(config, base_path=tmp_path)

        assert backend.initialize(config)
        assert (tmp_path / ".code-indexer" / "vectors").exists()

    def test_start_returns_true_immediately(self, tmp_path):
        """GIVEN a filesystem backend
        WHEN start() is called
        THEN it returns True immediately (no containers to start)"""
        backend = FilesystemBackend(config, base_path=tmp_path)

        start_time = time.time()
        result = backend.start()
        duration = time.time() - start_time

        assert result is True
        assert duration < 0.01  # <10ms (essentially instant)

    def test_health_check_validates_write_access(self, tmp_path):
        """GIVEN a filesystem backend
        WHEN health_check() is called
        THEN it verifies directory exists and is writable"""
        backend = FilesystemBackend(config, base_path=tmp_path)
        backend.initialize(config)

        assert backend.health_check() is True

        # Make directory read-only
        vectors_dir = tmp_path / ".code-indexer" / "vectors"
        os.chmod(vectors_dir, 0o444)

        assert backend.health_check() is False
```

**Coverage Requirements:**
- ✅ Directory creation (real filesystem)
- ✅ Start/stop operations (no-ops with timing validation)
- ✅ Health checks (write permission validation)
- ✅ Configuration parsing
- ✅ Backend factory selection

---

### Story 2: Index Code to Filesystem

**Test File:** `tests/unit/storage/test_filesystem_vector_store.py`

**Test Cases:**

```python
class TestVectorQuantizationAndStorage:
    """Test vector quantization and storage without filesystem mocking."""

    def test_deterministic_quantization(self, test_collection):
        """GIVEN the same vector quantized twice
        WHEN using the same projection matrix
        THEN it produces the same filesystem path"""
        quantizer = VectorQuantizer(depth_factor=4, reduced_dimensions=64)

        vector = np.random.randn(1536)
        path1 = quantizer.quantize_vector(vector)
        path2 = quantizer.quantize_vector(vector)

        assert path1 == path2  # Deterministic

    def test_upsert_creates_json_file_at_quantized_path(self, test_collection, test_vectors):
        """GIVEN vectors to store
        WHEN upsert_points() is called
        THEN JSON files are created at quantized paths with correct structure"""
        store = FilesystemVectorStore(test_collection, config)

        points = [{
            'id': 'test_001',
            'vector': test_vectors['small'][0].tolist(),
            'payload': {
                'file_path': 'src/test.py',
                'start_line': 10,
                'end_line': 20,
                'language': 'python',
                'type': 'content'
            }
        }]

        result = store.upsert_points('test_coll', points)

        assert result['status'] == 'ok'

        # Verify JSON file exists
        json_files = list(test_collection.rglob('*.json'))
        assert len(json_files) == 1

        # Verify JSON structure (NO chunk text)
        with open(json_files[0]) as f:
            data = json.load(f)

        assert data['id'] == 'test_001'
        assert data['file_path'] == 'src/test.py'
        assert len(data['vector']) == 1536
        assert 'chunk_text' not in data  # CRITICAL: No chunk text
        assert 'content' not in data  # No duplication

    def test_batch_upsert_performance(self, test_collection, test_vectors):
        """GIVEN 1000 vectors to store
        WHEN upsert_points_batched() is called
        THEN all vectors stored in <5s (performance requirement)"""
        store = FilesystemVectorStore(test_collection, config)

        points = [
            {
                'id': f'vec_{i}',
                'vector': test_vectors['large'][i].tolist(),
                'payload': {'file_path': f'file_{i}.py', 'start_line': i}
            }
            for i in range(1000)
        ]

        start = time.time()
        result = store.upsert_points_batched('test_coll', points, batch_size=100)
        duration = time.time() - start

        assert result['status'] == 'ok'
        assert duration < 5.0  # Performance requirement
        assert store.count_points('test_coll') == 1000

    def test_delete_points_removes_files(self, test_collection):
        """GIVEN vectors stored in filesystem
        WHEN delete_points() is called
        THEN JSON files are removed from filesystem"""
        store = FilesystemVectorStore(test_collection, config)

        # Store test vectors
        store.upsert_points('test_coll', [...])
        initial_count = store.count_points('test_coll')

        # Delete specific points
        result = store.delete_points('test_coll', ['vec_1', 'vec_2'])

        assert result['result']['deleted'] == 2
        assert store.count_points('test_coll') == initial_count - 2

        # Verify files actually deleted from filesystem
        remaining_files = list(test_collection.rglob('*.json'))
        assert len(remaining_files) == initial_count - 2

    def test_delete_by_filter_with_real_metadata(self, test_collection):
        """GIVEN vectors with various metadata
        WHEN delete_by_filter() is called
        THEN only matching vectors are deleted from filesystem"""
        store = FilesystemVectorStore(test_collection, config)

        # Store vectors with different branches
        points = [
            {'id': f'main_{i}', 'vector': [...], 'payload': {'git_branch': 'main'}},
            {'id': f'feat_{i}', 'vector': [...], 'payload': {'git_branch': 'feature'}},
        ]
        store.upsert_points('test_coll', points)

        # Delete only feature branch vectors
        result = store.delete_by_filter('test_coll', {'git_branch': 'feature'})

        # Verify only main branch vectors remain
        remaining = store.scroll_points('test_coll', limit=100)
        assert all(p['payload']['git_branch'] == 'main' for p in remaining[0])
```

**Coverage Requirements:**
- ✅ Deterministic quantization (same vector → same path)
- ✅ JSON file creation at correct paths (real filesystem)
- ✅ NO chunk text in JSON files (critical validation)
- ✅ Batch performance (1000 vectors in <5s)
- ✅ Delete operations (files actually removed)
- ✅ Filter-based deletion (metadata filtering)
- ✅ Concurrent writes (thread safety)

---

### Story 3: Search Indexed Code

**Test File:** `tests/unit/search/test_filesystem_semantic_search.py`

**Test Cases:**

```python
class TestSemanticSearchWithRealFilesystem:
    """Test semantic search using real filesystem and predictable vectors."""

    @pytest.fixture
    def indexed_collection(self, tmp_path, embedding_provider):
        """Create collection with known semantic relationships."""
        store = FilesystemVectorStore(tmp_path, config)

        # Use real embedding provider for semantic relationships
        auth_chunks = [
            "User authentication with JWT tokens",
            "Login function validates credentials",
            "OAuth2 authentication flow implementation"
        ]
        db_chunks = [
            "Database connection pooling",
            "SQL query execution and result parsing"
        ]

        # Embed and store
        auth_vectors = [embedding_provider.embed(text) for text in auth_chunks]
        db_vectors = [embedding_provider.embed(text) for text in db_chunks]

        points = []
        for i, vec in enumerate(auth_vectors):
            points.append({
                'id': f'auth_{i}',
                'vector': vec,
                'payload': {
                    'file_path': f'src/auth/file{i}.py',
                    'start_line': i*10,
                    'end_line': i*10+20,
                    'language': 'python',
                    'category': 'authentication'
                }
            })

        for i, vec in enumerate(db_vectors):
            points.append({
                'id': f'db_{i}',
                'vector': vec,
                'payload': {
                    'file_path': f'src/db/file{i}.py',
                    'start_line': i*10,
                    'end_line': i*10+20,
                    'language': 'python',
                    'category': 'database'
                }
            })

        store.upsert_points('test_coll', points)
        return store

    def test_semantic_search_returns_related_chunks(self, indexed_collection, embedding_provider):
        """GIVEN indexed chunks with known semantic relationships
        WHEN searching for "authentication"
        THEN auth chunks are returned (not db chunks)"""
        query_vector = embedding_provider.embed("authentication tokens")

        results = indexed_collection.search(
            collection_name='test_coll',
            query_vector=query_vector,
            limit=3
        )

        # Verify semantic relevance
        assert len(results) >= 2
        assert all('auth' in r['id'] for r in results[:2])  # Top 2 are auth
        assert results[0]['score'] > 0.7  # High similarity

    def test_search_with_metadata_filter(self, indexed_collection, embedding_provider):
        """GIVEN vectors with various metadata
        WHEN searching with language filter
        THEN only matching language results returned"""
        # Add some JavaScript vectors
        js_vector = embedding_provider.embed("JavaScript function definition")
        indexed_collection.upsert_points('test_coll', [{
            'id': 'js_001',
            'vector': js_vector,
            'payload': {'file_path': 'app.js', 'language': 'javascript'}
        }])

        query = embedding_provider.embed("function definition")

        # Search with Python filter
        results = indexed_collection.search(
            collection_name='test_coll',
            query_vector=query,
            filter_conditions={'language': 'python'},
            limit=10
        )

        # All results should be Python
        assert all(r['payload']['language'] == 'python' for r in results)
        assert not any(r['id'] == 'js_001' for r in results)

    def test_search_performance_meets_requirement(self, tmp_path, test_vectors):
        """GIVEN 5000 vectors stored in filesystem
        WHEN performing search
        THEN query completes in <1s (performance requirement)"""
        store = FilesystemVectorStore(tmp_path, config)

        # Store 5000 vectors
        points = [
            {
                'id': f'vec_{i}',
                'vector': test_vectors['realistic'][i].tolist(),
                'payload': {'file_path': f'file_{i}.py'}
            }
            for i in range(5000)
        ]
        store.upsert_points_batched('perf_test', points)

        # Search with timing
        query_vector = test_vectors['realistic'][0]

        start = time.time()
        results = store.search('perf_test', query_vector, limit=10)
        duration = time.time() - start

        assert duration < 1.0  # User requirement: <1s for 40K (we test 5K)
        assert len(results) == 10
        assert results[0]['score'] > results[-1]['score']  # Sorted

    def test_score_threshold_filters_results(self, indexed_collection, embedding_provider):
        """GIVEN indexed vectors
        WHEN searching with score_threshold=0.8
        THEN only results with score >= 0.8 are returned"""
        query = embedding_provider.embed("authentication")

        results = indexed_collection.search(
            collection_name='test_coll',
            query_vector=query,
            limit=10,
            score_threshold=0.8
        )

        assert all(r['score'] >= 0.8 for r in results)

    def test_accuracy_modes_affect_neighbor_search(self, indexed_collection, embedding_provider):
        """GIVEN indexed vectors
        WHEN using different accuracy modes
        THEN 'high' finds more candidates than 'fast'"""
        query = embedding_provider.embed("test query")

        results_fast = indexed_collection.search(
            collection_name='test_coll',
            query_vector=query,
            limit=10,
            accuracy='fast'  # 1-level neighbors
        )

        results_high = indexed_collection.search(
            collection_name='test_coll',
            query_vector=query,
            limit=10,
            accuracy='high'  # 2-level neighbors
        )

        # High accuracy may find different/additional results
        # (Implementation should track candidates examined)
        assert len(results_high) >= len(results_fast)
```

**Coverage Requirements:**
- ✅ Semantic search with real embeddings
- ✅ Metadata filtering (language, branch, type, path patterns)
- ✅ Score threshold filtering
- ✅ Accuracy modes (fast/balanced/high)
- ✅ Performance validation (<1s for 5K vectors in unit tests)
- ✅ Result ranking (scores in descending order)
- ✅ Neighbor bucket search effectiveness

---

### Story 4: Collection Management

**Test File:** `tests/unit/storage/test_collection_management.py`

**Test Cases:**

```python
class TestCollectionManagementWithRealFilesystem:
    """Test collection operations using real filesystem."""

    def test_create_collection_initializes_structure(self, tmp_path):
        """GIVEN a collection name
        WHEN create_collection() is called
        THEN directory and metadata files are created"""
        store = FilesystemVectorStore(tmp_path, config)

        result = store.create_collection('test_coll', vector_size=1536)

        assert result is True
        coll_path = tmp_path / 'test_coll'
        assert coll_path.exists()
        assert (coll_path / 'collection_meta.json').exists()
        assert (coll_path / 'projection_matrix.npy').exists()

        # Verify metadata content
        with open(coll_path / 'collection_meta.json') as f:
            meta = json.load(f)
        assert meta['vector_size'] == 1536
        assert meta['depth_factor'] == 4

    def test_delete_collection_removes_directory_tree(self, tmp_path):
        """GIVEN a collection with 100 vectors
        WHEN delete_collection() is called
        THEN entire directory tree is removed"""
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)

        # Add 100 vectors
        points = create_test_points(100)
        store.upsert_points('test_coll', points)

        # Verify exists
        assert (tmp_path / 'test_coll').exists()
        assert store.count_points('test_coll') == 100

        # Delete collection
        result = store.delete_collection('test_coll')

        assert result is True
        assert not (tmp_path / 'test_coll').exists()
        assert store.count_points('test_coll') == 0

    def test_clear_collection_preserves_structure(self, tmp_path):
        """GIVEN a collection with vectors
        WHEN clear_collection() is called
        THEN vectors deleted but collection structure preserved"""
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)
        store.upsert_points('test_coll', create_test_points(50))

        # Clear collection
        result = store.clear_collection('test_coll')

        assert result is True
        assert (tmp_path / 'test_coll').exists()  # Collection still exists
        assert (tmp_path / 'test_coll' / 'projection_matrix.npy').exists()
        assert store.count_points('test_coll') == 0  # Vectors removed

    def test_list_collections_returns_all_collections(self, tmp_path):
        """GIVEN multiple collections
        WHEN list_collections() is called
        THEN all collection names are returned"""
        store = FilesystemVectorStore(tmp_path, config)

        collections = ['coll_a', 'coll_b', 'coll_c']
        for coll in collections:
            store.create_collection(coll, 1536)

        result = store.list_collections()

        assert set(result) == set(collections)
```

**Coverage Requirements:**
- ✅ Collection creation (real directory/file creation)
- ✅ Collection deletion (actual filesystem removal)
- ✅ Collection clearing (structure preserved, vectors removed)
- ✅ Collection listing (real directory enumeration)
- ✅ Metadata persistence and retrieval

---

### Story 5: Health & Validation

**Test File:** `tests/unit/validation/test_filesystem_health.py`

**Test Cases:**

```python
class TestHealthValidationWithRealData:
    """Test health and validation using real filesystem operations."""

    def test_get_all_indexed_files_returns_unique_paths(self, test_collection):
        """GIVEN 100 chunks from 20 files
        WHEN get_all_indexed_files() is called
        THEN 20 unique file paths are returned"""
        store = FilesystemVectorStore(test_collection, config)

        # Create 100 chunks from 20 files (5 chunks per file)
        points = []
        for file_idx in range(20):
            for chunk_idx in range(5):
                points.append({
                    'id': f'file{file_idx}_chunk{chunk_idx}',
                    'vector': np.random.randn(1536).tolist(),
                    'payload': {
                        'file_path': f'src/file_{file_idx}.py',
                        'start_line': chunk_idx * 10
                    }
                })

        store.upsert_points('test_coll', points)

        # Get unique file paths
        files = store.get_all_indexed_files('test_coll')

        assert len(files) == 20  # Unique files
        assert all('src/file_' in f for f in files)

    def test_validate_embedding_dimensions(self, test_collection):
        """GIVEN vectors with specific dimensions
        WHEN validate_embedding_dimensions() is called
        THEN it correctly identifies dimension mismatches"""
        store = FilesystemVectorStore(test_collection, config)

        # Store correct dimension vectors
        correct_points = [{
            'id': 'correct',
            'vector': np.random.randn(1536).tolist(),
            'payload': {}
        }]
        store.upsert_points('test_coll', correct_points)

        assert store.validate_embedding_dimensions('test_coll', 1536) is True
        assert store.validate_embedding_dimensions('test_coll', 768) is False

    def test_sample_vectors_returns_real_data(self, test_collection):
        """GIVEN 1000 indexed vectors
        WHEN sample_vectors(50) is called
        THEN 50 vectors are loaded from actual JSON files"""
        store = FilesystemVectorStore(test_collection, config)
        store.upsert_points('test_coll', create_test_points(1000))

        samples = store.sample_vectors('test_coll', sample_size=50)

        assert len(samples) == 50
        assert all('vector' in s for s in samples)
        assert all(len(s['vector']) == 1536 for s in samples)
```

**Coverage Requirements:**
- ✅ File enumeration from filesystem
- ✅ Dimension validation from real JSON files
- ✅ Vector sampling (random file selection)
- ✅ Timestamp extraction and parsing

---

## Cross-Cutting Test Requirements

### Performance Testing (All Stories)

```python
@pytest.mark.performance
class TestPerformanceRequirements:
    """Validate performance requirements using real operations."""

    def test_40k_vector_search_under_1_second(self, tmp_path):
        """GIVEN 40,000 vectors in filesystem (user requirement)
        WHEN performing semantic search
        THEN query completes in <1s"""
        # This test may be slow - mark as optional for fast CI
        store = setup_40k_vectors(tmp_path)

        start = time.time()
        results = store.search('large_coll', random_query_vector(), limit=10)
        duration = time.time() - start

        assert duration < 1.0  # User requirement
        assert len(results) == 10

    def test_indexing_throughput_acceptable(self, tmp_path):
        """GIVEN 1000 files to index
        WHEN indexing to filesystem
        THEN achieves >10 files/second"""
        # Measure actual filesystem write performance
        ...
```

### Edge Case Testing

```python
class TestEdgeCasesWithRealFilesystem:
    """Test edge cases using real filesystem operations."""

    def test_empty_collection_search_returns_empty(self, tmp_path):
        """GIVEN empty collection
        WHEN searching
        THEN empty results returned"""
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('empty', 1536)

        results = store.search('empty', np.random.randn(1536), limit=10)

        assert results == []

    def test_corrupt_json_file_is_skipped(self, test_collection):
        """GIVEN collection with one corrupt JSON file
        WHEN searching or scrolling
        THEN corrupt file is skipped, other results returned"""
        store = FilesystemVectorStore(test_collection, config)
        store.upsert_points('test_coll', create_test_points(10))

        # Corrupt one JSON file
        json_files = list(test_collection.rglob('*.json'))
        json_files[0].write_text("{ corrupt json content")

        # Search should still work
        results = store.search('test_coll', np.random.randn(1536), limit=10)

        assert len(results) == 9  # 10 - 1 corrupt

    def test_concurrent_reads_during_search(self, test_collection):
        """GIVEN indexed collection
        WHEN multiple searches execute concurrently
        THEN all return correct results without errors"""
        store = FilesystemVectorStore(test_collection, config)
        store.upsert_points('test_coll', create_test_points(100))

        from concurrent.futures import ThreadPoolExecutor

        def search_task():
            return store.search('test_coll', np.random.randn(1536), limit=5)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(search_task) for _ in range(20)]
            results = [f.result() for f in futures]

        # All searches succeed
        assert all(len(r) == 5 for r in results)
```

---

## Test Data Organization

```
tests/fixtures/
├── test_vectors/
│   ├── small_10.npy          # 10 deterministic vectors
│   ├── medium_100.npy         # 100 deterministic vectors
│   ├── semantic_auth.npy      # Vectors for "authentication" concept
│   ├── semantic_db.npy        # Vectors for "database" concept
│   └── projection_64d.npy     # Deterministic projection matrix
└── expected_results/
    ├── auth_search_top10.json # Expected top-10 for auth queries
    └── filter_results.json    # Expected filter outputs
```

## Acceptance Criteria Additions

For **EACH story**, add these test requirements:

### Story 2 (Indexing) - Enhanced Acceptance Criteria

**Unit Test Requirements:**
- ✅ Test with 10, 100, 1000 vectors (no mocking)
- ✅ Verify JSON structure matches spec (no chunk text)
- ✅ Verify deterministic quantization (same vector → same path)
- ✅ Verify batch performance (<5s for 1000 vectors)
- ✅ Test delete operations (files actually removed)
- ✅ Test filter-based deletion (correct files deleted)
- ✅ Test concurrent writes (thread safety)
- ✅ Test ID index consistency

### Story 3 (Search) - Enhanced Acceptance Criteria

**Unit Test Requirements:**
- ✅ Test semantic search with known relationships (auth vs db chunks)
- ✅ Test metadata filtering (language, branch, type, path)
- ✅ Test score threshold filtering
- ✅ Test accuracy modes (fast/balanced/high)
- ✅ Test performance with 5K vectors (<1s requirement)
- ✅ Test result ranking (scores descending)
- ✅ Test neighbor bucket search
- ✅ Test empty results handling
- ✅ Test concurrent queries (thread safety)

### Story 4 (Status) - Enhanced Acceptance Criteria

**Unit Test Requirements:**
- ✅ Test file counting (real filesystem count)
- ✅ Test timestamp extraction (parse all JSON files)
- ✅ Test dimension validation (check actual vectors)
- ✅ Test sampling (load random files)
- ✅ Test collection stats (size, count, health)

### Story 5 (Collection Management) - Enhanced Acceptance Criteria

**Unit Test Requirements:**
- ✅ Test collection creation (real directories)
- ✅ Test collection deletion (actual removal)
- ✅ Test collection clearing (structure preserved, data removed)
- ✅ Test collection listing (real directory enumeration)
- ✅ Test cleanup operations (verify filesystem state)

---

## Test Execution Strategy

### Fast Tests (Run in CI)
- Use small datasets (10-100 vectors)
- Focus on correctness, not performance
- Complete in <30s total

### Performance Tests (Optional in CI)
- Use larger datasets (1K-5K vectors)
- Validate performance requirements
- May run slower, mark with `@pytest.mark.slow`

### Integration Tests (Local only)
- Use 40K vectors (full scale)
- End-to-end workflows
- Run before releases

---

## Recommended Epic Update

Add to **EACH story's Acceptance Criteria** section:

```markdown
### Unit Test Coverage Requirements

**Test Strategy:** Use real filesystem operations with deterministic test data (NO filesystem mocking)

**Required Tests:**
1. Functional correctness with real file I/O
2. Performance validation with timing assertions
3. Edge case handling (empty, corrupt, concurrent)
4. Metadata filtering with predictable data
5. Integration with actual embedding providers (or pre-computed fixtures)

**Test Data:**
- Deterministic vectors (seeded random)
- Known semantic relationships (auth vs db chunks)
- Predictable metadata for filter testing
- Multiple scales (10, 100, 1K, 5K vectors)

**Performance Assertions:**
- Indexing: >10 files/second
- Search: <1s for 5K vectors (unit test scale)
- Count: <100ms for any collection
- Delete: <500ms for 100 vectors
```

---

**Should I update the epic stories to include these comprehensive unit test requirements in the acceptance criteria?**
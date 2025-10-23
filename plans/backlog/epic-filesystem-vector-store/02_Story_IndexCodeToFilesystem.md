# Story 2: Index Code to Filesystem Without Containers

**Story ID:** S02
**Epic:** Filesystem-Based Vector Database Backend
**Priority:** High
**Estimated Effort:** 8-12 days
**Implementation Order:** 3

## User Story

**As a** developer with a filesystem-initialized project
**I want to** index my codebase to filesystem-based vector storage
**So that** I can create searchable semantic embeddings without running containers

**Conversation Reference:** "I don't want to run ANY containers, zero. I want to store my index, side by side, with my code, and I want it to go inside git, as the code." - User explicitly requested container-free indexing with git-trackable storage.

## Acceptance Criteria

### Functional Requirements
1. ✅ `cidx index` stores vectors as JSON files in `.code-indexer/vectors/`
2. ✅ Path-as-vector quantization creates directory hierarchy for efficient lookups
3. ✅ Projection matrix generated once per collection (deterministic, reusable)
4. ✅ JSON files contain only file references, not chunk text content
5. ✅ Progress reporting shows indexing speed and file counts
6. ✅ Works with both VoyageAI and Ollama embedding providers
7. ✅ Branch-aware indexing (separate collections per branch)

### Technical Requirements
1. ✅ FilesystemVectorStore implements QdrantClient-compatible interface
2. ✅ Vector storage pipeline: 1536-dim → Random Projection → 64-dim → 2-bit Quantization → Path
3. ✅ Directory structure uses depth factor 4 (from POC optimal results)
4. ✅ Concurrent vector writes with thread safety
5. ✅ ID indexing for fast lookups by point ID
6. ✅ Collection management (create, exists, list collections)

### Storage Requirements
**Conversation Reference:** "no chunk data is stored in the json objects, but relative references to the files that contain the chunks" - Storage must only contain file references.

1. ✅ JSON format includes: file_path, start_line, end_line, start_offset, end_offset, chunk_hash
2. ✅ Full 1536-dim vector stored for exact ranking
3. ✅ Git-aware storage:
   - **Git repos:** Store git blob hash, NO chunk text (space efficient)
   - **Non-git repos:** Store chunk_text in metadata (fallback mode)
4. ✅ Metadata includes: indexed_at, embedding_model, branch, git_blob_hash (if git)

### Chunk Content Retrieval Requirements

**User Requirement:** "when querying our system for a match, we will lift up the chunk from the disk using our reference, we will calculate the hash and match against our metadata, and if it doesn't match, we will need to find in git the file that was actually indexed"

**Implementation Strategy:**

1. ✅ **Transparent retrieval:** `search()` results always include `payload['content']` (identical to Qdrant interface)
2. ✅ **3-tier fallback for git repos:**
   - Try current file (hash verification)
   - Try git blob (fast: `git cat-file -p <blob_hash>`)
   - Return error message if both fail
3. ✅ **Direct retrieval for non-git repos:** Load chunk_text from JSON metadata
4. ✅ **Clean git state mandate:** Indexing requires `git status --porcelain` == empty
5. ✅ **Batch git metadata collection:** Use `git ls-tree -r HEAD` for all blob hashes in single command (~100ms)

## Manual Testing Steps

```bash
# Test 1: Index repository to filesystem
cd /path/to/test-repo
cidx init --vector-store filesystem
cidx index

# Expected output:
# ℹ️ Using filesystem vector store at .code-indexer/vectors/
# ℹ️ Creating projection matrix for collection...
# ⏳ Indexing files: [=========>  ] 45/100 files (45%) | 12 emb/s | file.py
# ✅ Indexed 100 files, 523 vectors to filesystem
# 📁 Vectors stored in .code-indexer/vectors/voyage-code-3/

# Verify directory structure
ls -la .code-indexer/vectors/voyage-code-3/
# Expected: projection_matrix.npy, collection_meta.json, [hex directories]

# Test 2: Verify JSON structure (no chunk text)
cat .code-indexer/vectors/voyage-code-3/a3/b7/2f/vector_abc123.json
# Expected JSON:
# {
#   "id": "file.py:42-87:hash",
#   "file_path": "src/module/file.py",
#   "start_line": 42,
#   "end_line": 87,
#   "start_offset": 1234,
#   "end_offset": 2567,
#   "chunk_hash": "abc123...",
#   "vector": [0.123, -0.456, ...],  // 1536 dimensions
#   "metadata": {
#     "indexed_at": "2025-01-23T10:00:00Z",
#     "embedding_model": "voyage-code-3",
#     "branch": "main"
#   }
# }

# Test 3: Force reindex
cidx index --force-reindex
# Expected: Clears existing vectors, reindexes all files

# Test 4: Branch-aware indexing
git checkout feature-branch
cidx index
# Expected: Separate collection for feature-branch

ls .code-indexer/vectors/
# Expected: voyage-code-3_main/, voyage-code-3_feature-branch/

# Test 5: Multi-provider support
cidx init --vector-store filesystem --embedding-provider ollama
cidx index
# Expected: Collection with ollama-nomic-embed-text, 768-dim vectors
```

## Technical Implementation Details

### Quantization Pipeline Architecture

**Conversation Reference:** "can't you lay, on disk, json files that represent the metadata related to the vector, and the entire path IS the vector?" - User proposed path-as-vector quantization strategy.

```python
# Step 1: Random Projection (1536 → 64 dimensions)
projection_matrix = np.random.randn(1536, 64)  # Deterministic seed
reduced_vector = vector @ projection_matrix

# Step 2: 2-bit Quantization (64 floats → 128 bits → 32 hex chars)
quantized = quantize_to_2bit(reduced_vector)  # Each dim → 2 bits
hex_path = convert_to_hex(quantized)  # 32 hex characters

# Step 3: Directory Structure (depth factor 4)
# 32 hex chars split: 2/2/2/2/24
# Example: a3/b7/2f/c9/d8e4f1a2b5c3...
path_segments = split_with_depth_factor(hex_path, depth_factor=4)
storage_path = Path(*path_segments) / f"vector_{point_id}.json"
```

### FilesystemVectorStore Implementation

```python
class FilesystemVectorStore:
    """Filesystem-based vector storage with QdrantClient interface."""

    def __init__(self, base_path: Path, config: Config):
        self.base_path = base_path
        self.config = config
        self.operations = FilesystemVectorOperations(base_path)
        self.collections = FilesystemCollectionManager(base_path)
        self.quantizer = VectorQuantizer(
            depth_factor=config.vector_store.depth_factor,
            reduced_dimensions=config.vector_store.reduced_dimensions
        )

    # Core CRUD Operations (QdrantClient-compatible)

    def upsert_points(
        self,
        collection_name: str,
        points: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Store vectors as JSON files at quantized paths."""
        for point in points:
            vector = np.array(point['vector'])
            payload = point['payload']

            # Get quantized path
            hex_path = self.quantizer.quantize_vector(vector)
            storage_path = self._resolve_storage_path(
                collection_name,
                hex_path,
                point['id']
            )

            # Prepare JSON (NO CHUNK TEXT - only file references)
            vector_data = {
                'id': point['id'],
                'file_path': payload['file_path'],
                'start_line': payload['start_line'],
                'end_line': payload['end_line'],
                'start_offset': payload.get('start_offset', 0),
                'end_offset': payload.get('end_offset', 0),
                'chunk_hash': payload.get('chunk_hash', ''),
                'vector': vector.tolist(),  # Full 1536-dim vector
                'metadata': {
                    'indexed_at': datetime.utcnow().isoformat(),
                    'embedding_model': self.config.embedding_model,
                    'branch': payload.get('branch', 'main')
                }
            }

            # Write atomically
            self._write_vector_json(storage_path, vector_data)

    def create_collection(
        self,
        collection_name: str,
        vector_size: int = 1536
    ) -> bool:
        """Create collection with deterministic projection matrix."""
        collection_path = self.base_path / collection_name
        collection_path.mkdir(parents=True, exist_ok=True)

        # Generate deterministic projection matrix
        projection_matrix = self._create_projection_matrix(
            input_dim=vector_size,
            output_dim=self.config.vector_store.reduced_dimensions
        )

        # Save projection matrix (reusable for same collection)
        np.save(collection_path / "projection_matrix.npy", projection_matrix)

        # Create collection metadata
        metadata = {
            "name": collection_name,
            "vector_size": vector_size,
            "created_at": datetime.utcnow().isoformat(),
            "depth_factor": self.config.vector_store.depth_factor,
            "reduced_dimensions": self.config.vector_store.reduced_dimensions
        }

        meta_path = collection_path / "collection_meta.json"
        meta_path.write_text(json.dumps(metadata, indent=2))

        return True

    def delete_points(
        self,
        collection_name: str,
        point_ids: List[str]
    ) -> Dict[str, Any]:
        """Delete vectors by removing JSON files."""
        deleted = 0
        for point_id in point_ids:
            file_path = self._find_vector_by_id(collection_name, point_id)
            if file_path and file_path.exists():
                file_path.unlink()
                deleted += 1
        return {"status": "ok", "deleted": deleted}

    def count_points(self, collection_name: str) -> int:
        """Count JSON files in collection."""
        collection_path = self.base_path / collection_name
        return sum(1 for _ in collection_path.rglob('*.json')
                   if _.name != "collection_meta.json")
```

### Vector Quantizer

```python
class VectorQuantizer:
    """Quantize high-dimensional vectors to filesystem paths."""

    def __init__(self, depth_factor: int = 4, reduced_dimensions: int = 64):
        self.depth_factor = depth_factor
        self.reduced_dimensions = reduced_dimensions

    def quantize_vector(self, vector: np.ndarray) -> str:
        """Convert vector to hex path string.

        Pipeline: 1536-dim → project → 64-dim → quantize → 128 bits → 32 hex chars
        """
        # Load projection matrix from collection
        reduced = self._project_vector(vector)

        # 2-bit quantization
        quantized_bits = self._quantize_to_2bit(reduced)

        # Convert to hex
        hex_string = self._bits_to_hex(quantized_bits)

        return hex_string  # 32 hex characters

    def _quantize_to_2bit(self, vector: np.ndarray) -> np.ndarray:
        """Quantize float vector to 2-bit representation."""
        # Compute thresholds (quartiles)
        q1, q2, q3 = np.percentile(vector, [25, 50, 75])

        # Map to 2 bits: 00, 01, 10, 11
        quantized = np.zeros(len(vector), dtype=np.uint8)
        quantized[vector >= q3] = 3
        quantized[(vector >= q2) & (vector < q3)] = 2
        quantized[(vector >= q1) & (vector < q2)] = 1
        quantized[vector < q1] = 0

        return quantized
```

### Projection Matrix Manager

```python
class ProjectionMatrixManager:
    """Manage deterministic projection matrices for collections."""

    def create_projection_matrix(
        self,
        input_dim: int,
        output_dim: int,
        seed: Optional[int] = None
    ) -> np.ndarray:
        """Create deterministic projection matrix.

        Uses random projection for dimensionality reduction.
        Deterministic seed ensures reproducibility.
        """
        if seed is None:
            # Use collection name hash as seed for determinism
            seed = hash(f"projection_matrix_{input_dim}_{output_dim}") % (2**32)

        np.random.seed(seed)
        matrix = np.random.randn(input_dim, output_dim)

        # Normalize for stable projection
        matrix /= np.sqrt(output_dim)

        return matrix

    def load_matrix(self, collection_path: Path) -> np.ndarray:
        """Load existing projection matrix."""
        matrix_path = collection_path / "projection_matrix.npy"
        return np.load(matrix_path)

    def save_matrix(self, matrix: np.ndarray, collection_path: Path):
        """Save projection matrix to collection."""
        matrix_path = collection_path / "projection_matrix.npy"
        np.save(matrix_path, matrix)
```

## Dependencies

### Internal Dependencies
- Story 1: Backend abstraction layer (FilesystemBackend)
- Story 0: POC results (optimal depth factor = 4)
- Existing embedding providers (VoyageAI, Ollama)
- Existing file chunking logic

### External Dependencies
- NumPy for vector operations and projection
- Python `json` for serialization
- Python `pathlib` for filesystem operations
- ThreadPoolExecutor for parallel writes

## Success Metrics

1. ✅ Indexing completes without errors
2. ✅ Vector JSON files created with correct structure
3. ✅ No chunk text stored in JSON files (only file references)
4. ✅ Projection matrix saved and reusable
5. ✅ Directory structure matches quantization scheme
6. ✅ Indexing performance comparable to Qdrant workflow
7. ✅ Progress reporting shows real-time feedback

## Non-Goals

- Query/search functionality (covered in Story 3)
- Health monitoring (covered in Story 4)
- Backend switching (covered in Story 8)
- Migration from existing Qdrant data

## Follow-Up Stories

- **Story 3**: Search Indexed Code from Filesystem (searches these vectors)
- **Story 4**: Monitor Filesystem Index Status and Health (validates this indexing)
- **Story 7**: Multi-Provider Support (extends indexing to multiple providers)

## Implementation Notes

### Critical Storage Constraint

**Conversation Reference:** "no chunk data is stored in the json objects, but relative references to the files that contain the chunks" - This is NON-NEGOTIABLE.

The JSON files MUST NOT contain chunk text. They contain ONLY:
- File path references (relative to repo root)
- Line and byte offsets for chunk boundaries
- The full vector for exact ranking
- Metadata (timestamps, model, branch)

Chunk text is retrieved from actual source files during result display.

### Directory Structure Optimization

**From POC Results:** Depth factor 4 provides optimal balance of:
- 1-10 files per directory (avoids filesystem performance issues)
- Fast neighbor discovery for search
- Reasonable directory depth (8 levels)

### Thread Safety

Parallel writes require:
- Atomic file writes (write to temp, then rename)
- No shared mutable state during indexing
- ID index updates synchronized

### Progress Reporting Format

**From CLAUDE.md:** "When indexing, progress reporting is done real-time, in a single line at the bottom, showing a progress bar, and right next to it we show speed metrics and current file being processed."

Format: `⏳ Indexing files: [=========>  ] 45/100 files (45%) | 12 emb/s | src/module/file.py`

## Unit Test Coverage Requirements

**Test Strategy:** Use real filesystem operations with deterministic test data (NO mocking of file I/O)

**Test File:** `tests/unit/storage/test_filesystem_vector_store.py`

**Required Tests:**

```python
class TestVectorQuantizationAndStorage:
    """Test vector quantization and storage without filesystem mocking."""

    @pytest.fixture
    def test_vectors(self):
        """Generate deterministic test vectors."""
        np.random.seed(42)
        return {
            'small': np.random.randn(10, 1536),
            'medium': np.random.randn(100, 1536),
            'large': np.random.randn(1000, 1536)
        }

    def test_deterministic_quantization(self, tmp_path, test_vectors):
        """GIVEN the same vector quantized twice
        WHEN using the same projection matrix
        THEN it produces the same filesystem path"""
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)

        vector = test_vectors['small'][0]
        path1 = store._vector_to_path(vector, 'test_coll')
        path2 = store._vector_to_path(vector, 'test_coll')

        assert path1 == path2  # Deterministic

    def test_upsert_creates_json_at_quantized_path(self, tmp_path, test_vectors):
        """GIVEN vectors to store
        WHEN upsert_points() is called
        THEN JSON files created at quantized paths with NO chunk text"""
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)

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

        # Verify JSON file exists on actual filesystem
        json_files = list((tmp_path / 'test_coll').rglob('*.json'))
        assert len(json_files) >= 1  # At least collection_meta + 1 vector

        # Find vector file (not collection_meta)
        vector_files = [f for f in json_files if 'collection_meta' not in f.name]
        assert len(vector_files) == 1

        # Verify JSON structure (CRITICAL: NO chunk text)
        with open(vector_files[0]) as f:
            data = json.load(f)

        assert data['id'] == 'test_001'
        assert data['file_path'] == 'src/test.py'
        assert data['start_line'] == 10
        assert len(data['vector']) == 1536
        assert 'chunk_text' not in data  # CRITICAL
        assert 'content' not in data  # CRITICAL
        assert 'text' not in data  # CRITICAL

    def test_batch_upsert_performance(self, tmp_path, test_vectors):
        """GIVEN 1000 vectors to store
        WHEN upsert_points_batched() is called
        THEN all vectors stored in <5s"""
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)

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

        # Verify files actually exist on filesystem
        json_count = sum(1 for _ in (tmp_path / 'test_coll').rglob('*.json')
                        if 'collection_meta' not in _.name)
        assert json_count == 1000

    def test_delete_points_removes_files(self, tmp_path, test_vectors):
        """GIVEN vectors stored in filesystem
        WHEN delete_points() is called
        THEN JSON files are actually removed from filesystem"""
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)

        # Store 10 vectors
        points = [
            {'id': f'vec_{i}', 'vector': test_vectors['small'][i].tolist(),
             'payload': {'file_path': f'file_{i}.py'}}
            for i in range(10)
        ]
        store.upsert_points('test_coll', points)

        initial_count = store.count_points('test_coll')
        assert initial_count == 10

        # Delete specific points
        result = store.delete_points('test_coll', ['vec_1', 'vec_2', 'vec_3'])

        assert result['result']['deleted'] == 3
        assert store.count_points('test_coll') == 7

        # Verify files actually deleted from filesystem
        remaining = sum(1 for _ in (tmp_path / 'test_coll').rglob('*.json')
                       if 'collection_meta' not in _.name)
        assert remaining == 7

    def test_delete_by_filter_with_metadata(self, tmp_path, test_vectors):
        """GIVEN vectors with various metadata
        WHEN delete_by_filter() is called
        THEN only matching vectors deleted from filesystem"""
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)

        # Store vectors with different branches
        points = []
        for i in range(5):
            points.append({
                'id': f'main_{i}',
                'vector': test_vectors['small'][i].tolist(),
                'payload': {'git_branch': 'main', 'file_path': f'file_{i}.py'}
            })
        for i in range(5, 10):
            points.append({
                'id': f'feat_{i}',
                'vector': test_vectors['small'][i].tolist(),
                'payload': {'git_branch': 'feature', 'file_path': f'file_{i}.py'}
            })

        store.upsert_points('test_coll', points)
        assert store.count_points('test_coll') == 10

        # Delete only feature branch vectors
        result = store.delete_by_filter('test_coll', {'git_branch': 'feature'})

        assert result['result']['deleted'] == 5
        assert store.count_points('test_coll') == 5

        # Verify only main branch vectors remain
        remaining = store.scroll_points('test_coll', limit=100)[0]
        assert all(p['payload']['git_branch'] == 'main' for p in remaining)

    def test_concurrent_writes_thread_safety(self, tmp_path, test_vectors):
        """GIVEN concurrent upsert operations
        WHEN multiple threads write simultaneously
        THEN all vectors stored without corruption"""
        from concurrent.futures import ThreadPoolExecutor

        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)

        def write_batch(start_idx):
            points = [
                {
                    'id': f'vec_{start_idx}_{i}',
                    'vector': np.random.randn(1536).tolist(),
                    'payload': {'file_path': f'file_{i}.py'}
                }
                for i in range(10)
            ]
            return store.upsert_points('test_coll', points)

        # Write 100 vectors across 10 threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(write_batch, i*10) for i in range(10)]
            results = [f.result() for f in futures]

        # All writes succeed
        assert all(r['status'] == 'ok' for r in results)
        assert store.count_points('test_coll') == 100

        # No corrupted JSON files
        for json_file in (tmp_path / 'test_coll').rglob('*.json'):
            if 'collection_meta' in json_file.name:
                continue
            with open(json_file) as f:
                data = json.load(f)  # Should not raise JSONDecodeError
            assert 'vector' in data
            assert len(data['vector']) == 1536
```

**Coverage Requirements:**
- ✅ Deterministic quantization (same vector → same path)
- ✅ JSON file creation at correct paths (real filesystem)
- ✅ NO chunk text in JSON files (critical validation)
- ✅ Batch performance (1000 vectors in <5s)
- ✅ Delete operations (files actually removed)
- ✅ Filter-based deletion (metadata filtering)
- ✅ Concurrent writes (thread safety)
- ✅ ID index consistency

**Test Data:**
- Deterministic vectors using seeded random (np.random.seed(42))
- Multiple scales: 10, 100, 1000 vectors
- Use pytest tmp_path for isolated test directories
- No mocking of pathlib, os, or json operations

**Performance Assertions:**
- Batch upsert: <5s for 1000 vectors
- Single upsert: <50ms
- Delete: <500ms for 100 vectors
- Count: <100ms for any collection

### Chunk Content Retrieval Tests

```python
class TestChunkContentRetrieval:
    """Test chunk content retrieval with git fallback."""

    def test_git_repo_stores_blob_hash_not_content(self, tmp_path):
        """GIVEN a git repository
        WHEN indexing chunks
        THEN git blob hash stored, NO chunk_text in JSON"""
        # Initialize git repo
        subprocess.run(['git', 'init'], cwd=tmp_path)
        test_file = tmp_path / 'test.py'
        test_file.write_text("def foo():\n    return 42\n")
        subprocess.run(['git', 'add', '.'], cwd=tmp_path)
        subprocess.run(['git', 'commit', '-m', 'test'], cwd=tmp_path)

        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)

        points = [{
            'id': 'test_001',
            'vector': np.random.randn(1536).tolist(),
            'payload': {
                'path': 'test.py',
                'start_line': 0,
                'end_line': 2,
                'content': 'def foo():\n    return 42\n'  # Provided by core
            }
        }]

        store.upsert_points('test_coll', points)

        # Verify JSON does NOT contain chunk text
        json_files = [f for f in (tmp_path / 'test_coll').rglob('*.json')
                     if 'collection_meta' not in f.name]
        with open(json_files[0]) as f:
            data = json.load(f)

        assert 'git_blob_hash' in data  # Git blob stored
        assert 'chunk_text' not in data  # Chunk text NOT stored
        assert 'content' not in data  # Content NOT duplicated
        assert 'chunk_hash' in data  # Content hash stored

    def test_non_git_repo_stores_chunk_text(self, tmp_path):
        """GIVEN a non-git directory
        WHEN indexing chunks
        THEN chunk_text stored in JSON (no git fallback)"""
        # No git init - plain directory
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)

        points = [{
            'id': 'test_001',
            'vector': np.random.randn(1536).tolist(),
            'payload': {
                'path': 'test.py',
                'start_line': 0,
                'end_line': 2,
                'content': 'def foo():\n    return 42\n'
            }
        }]

        store.upsert_points('test_coll', points)

        # Verify JSON DOES contain chunk text (no git fallback)
        json_files = [f for f in (tmp_path / 'test_coll').rglob('*.json')
                     if 'collection_meta' not in f.name]
        with open(json_files[0]) as f:
            data = json.load(f)

        assert 'chunk_text' in data  # Chunk text stored
        assert data['chunk_text'] == 'def foo():\n    return 42\n'
        assert 'git_blob_hash' not in data  # No git metadata

    def test_search_retrieves_content_from_current_file(self, tmp_path):
        """GIVEN indexed git repo
        WHEN file unchanged and searching
        THEN content retrieved from current file (fast path)"""
        # Setup git repo with file
        subprocess.run(['git', 'init'], cwd=tmp_path)
        test_file = tmp_path / 'test.py'
        test_content = "def foo():\n    return 42\n"
        test_file.write_text(test_content)
        subprocess.run(['git', 'add', '.'], cwd=tmp_path)
        subprocess.run(['git', 'commit', '-m', 'test'], cwd=tmp_path)

        # Index
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)
        store.upsert_points('test_coll', [{
            'id': 'test_001',
            'vector': np.random.randn(1536).tolist(),
            'payload': {'path': 'test.py', 'start_line': 0, 'end_line': 2,
                       'content': test_content}
        }])

        # Search
        results = store.search('test_coll', np.random.randn(1536), limit=1)

        # Content should be retrieved and included
        assert len(results) == 1
        assert 'content' in results[0]['payload']
        assert results[0]['payload']['content'] == test_content

    def test_search_falls_back_to_git_blob_when_file_modified(self, tmp_path):
        """GIVEN indexed file that was later modified
        WHEN searching
        THEN content retrieved from git blob (hash verified)"""
        # Setup and index
        subprocess.run(['git', 'init'], cwd=tmp_path)
        test_file = tmp_path / 'test.py'
        original_content = "def foo():\n    return 42\n"
        test_file.write_text(original_content)
        subprocess.run(['git', 'add', '.'], cwd=tmp_path)
        subprocess.run(['git', 'commit', '-m', 'original'], cwd=tmp_path)

        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)
        store.upsert_points('test_coll', [{
            'id': 'test_001',
            'vector': np.random.randn(1536).tolist(),
            'payload': {'path': 'test.py', 'start_line': 0, 'end_line': 2,
                       'content': original_content}
        }])

        # Modify file (break hash)
        test_file.write_text("def foo():\n    return 99\n")

        # Search - should fall back to git blob
        results = store.search('test_coll', np.random.randn(1536), limit=1)

        assert len(results) == 1
        assert results[0]['payload']['content'] == original_content  # From git!

    def test_indexing_requires_clean_git_state(self, tmp_path):
        """GIVEN git repo with uncommitted changes
        WHEN attempting to index
        THEN error raised requiring clean state"""
        subprocess.run(['git', 'init'], cwd=tmp_path)
        test_file = tmp_path / 'test.py'
        test_file.write_text("def foo(): pass")
        # Don't commit - leave dirty

        store = FilesystemVectorStore(tmp_path, config)

        with pytest.raises(ValueError, match="uncommitted changes"):
            store.validate_git_state_before_indexing()

    def test_batch_git_metadata_collection_performance(self, tmp_path):
        """GIVEN 100 files to index
        WHEN collecting git blob hashes
        THEN completes in <500ms using batch command"""
        # Setup git repo with 100 files
        subprocess.run(['git', 'init'], cwd=tmp_path)
        for i in range(100):
            (tmp_path / f'file_{i}.py').write_text(f"# File {i}")
        subprocess.run(['git', 'add', '.'], cwd=tmp_path)
        subprocess.run(['git', 'commit', '-m', 'test'], cwd=tmp_path)

        store = FilesystemVectorStore(tmp_path, config)

        # Measure git metadata collection
        start = time.time()
        blob_hashes = store._get_blob_hashes_batch([f'file_{i}.py' for i in range(100)])
        duration = time.time() - start

        assert len(blob_hashes) == 100
        assert duration < 0.5  # <500ms for batch operation
```

**Additional Coverage:**
- ✅ Git vs non-git detection
- ✅ Git blob hash storage (git repos)
- ✅ Chunk text storage (non-git repos)
- ✅ Content retrieval with current file (fast path)
- ✅ Content retrieval with git blob fallback
- ✅ Clean git state validation
- ✅ Batch git metadata collection performance

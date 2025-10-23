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
5. ✅ Results sorted by similarity score
6. ✅ Top-k results returned
7. ✅ No containers required for search operations

### Performance Requirements
**Conversation Reference:** "~1s is fine" - User explicitly accepted 1-second query latency for 40K vectors.

1. ✅ Query latency <1s for 40K vectors (target scale)
2. ✅ Neighbor discovery limited to prevent over-fetching
3. ✅ Efficient JSON loading (parallel reads)
4. ✅ In-memory filtering and sorting

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
- Query time ~800-1000ms (still under 1s target)
- Maximum recall

### Result Display Strategy

**Chunk text NOT stored in JSON** (from Story 2 constraint). Results must:
1. Return file path and line ranges from JSON
2. Read actual chunk text from source files on demand
3. Display code snippets in search results

This keeps JSON files small and git-trackable while providing full context in results.

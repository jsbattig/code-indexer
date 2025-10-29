# Full-Text Search Architecture Analysis for CIDX

## Executive Summary

This document provides comprehensive architectural analysis for integrating full-text search (FTS) capabilities into CIDX using Tantivy. The analysis covers integration points, technical feasibility, and architectural recommendations for implementing efficient text search alongside the existing semantic search infrastructure.

## 1. Codebase Integration Analysis

### 1.1 Existing Command Structure

#### CLI Command Integration Points

**`cidx index` Command** (`cli.py:2186-2690`)
- Current implementation: `SmartIndexer` class orchestrates semantic indexing
- Integration point: Add `--fts` flag in CLI decorator
- Processing flow: `SmartIndexer` → `HighThroughputProcessor` → vector embeddings
- FTS integration: Parallel Tantivy indexing alongside vector processing
- Progress reporting: Rich Live progress manager with bottom-anchored display

**`cidx watch` Command** (`cli.py:2699-2868`)
- Current implementation: `GitAwareWatchHandler` monitors file changes
- Integration point: Add `--fts` flag for real-time FTS updates
- Processing flow: Watchdog observer → debounced batch processing → SmartIndexer
- FTS integration: Hook into `on_modified`/`on_created` events for incremental updates

**`cidx query` Command** (`cli.py:2912-3868`)
- Current implementation: Semantic search via vector similarity
- Integration points:
  - Add `--fts` flag for text-only search
  - Add `--semantic` flag to enable both modes
  - Modify result display logic for dual-mode results
- Processing flow: Query → embedding → vector search → result formatting

### 1.2 Storage Architecture Analysis

#### Current FilesystemVectorStore Architecture
```
.code-indexer/
├── config.json           # Project configuration
├── metadata.json         # Indexing metadata (git state, progress)
├── index/                # FilesystemVectorStore location
│   └── <collection>/
│       ├── collection_meta.json
│       ├── projection_matrix.npz
│       ├── id_index.json
│       └── chunks/       # Quantized vector storage
└── tantivy_index/        # NEW: Tantivy FTS index directory
    ├── meta.json         # Index schema and settings
    └── <segment_files>   # Tantivy index segments
```

#### Integration Strategy
- Tantivy index stored parallel to vector index
- Shared metadata for synchronized state tracking
- Independent segment management for non-blocking commits

### 1.3 Indexing Pipeline Architecture

#### Current HighThroughputProcessor Flow
1. File discovery via `FileFinder`
2. Content chunking via `Chunker`
3. Parallel embedding generation (8 threads default)
4. Vector quantization and storage
5. Progress reporting via `MultiThreadedProgressManager`

#### FTS Integration Points
```python
class SmartIndexer(HighThroughputProcessor):
    def __init__(self, ...):
        super().__init__(...)
        self.fts_indexer = None  # TantivyIndexer instance when --fts enabled

    def process_file(self, file_path: Path):
        content = self.read_file(file_path)

        # Existing: Semantic indexing
        chunks = self.chunk_content(content)
        embeddings = self.generate_embeddings(chunks)
        self.store_vectors(embeddings)

        # NEW: FTS indexing (parallel)
        if self.fts_indexer:
            self.fts_indexer.index_document(file_path, content)
```

### 1.4 Server API Integration

#### Current Query Endpoint (`app.py:3538`)
```python
@app.post("/api/query")
async def semantic_query(request: QueryRequest):
    # Current: Semantic search only
    results = semantic_query_manager.execute_query(...)
```

#### Enhanced Endpoint Design
```python
class QueryRequest(BaseModel):
    query_text: str
    search_mode: Literal["semantic", "fts", "hybrid"] = "semantic"
    fts_options: Optional[FTSOptions] = None

class FTSOptions(BaseModel):
    case_sensitive: bool = False
    fuzzy_distance: int = 0  # Levenshtein distance
    context_lines: int = 2    # Lines before/after match
```

## 2. Technical Feasibility Assessment

### 2.1 Tantivy Python Bindings Evaluation

#### Library Maturity
- **Latest Version**: tantivy-0.25.0 (September 2025)
- **Maintenance**: Actively maintained by quickwit-oss
- **Python Support**: PyO3 bindings, Python 3.8+
- **Installation**: `pip install tantivy` with pre-built wheels
- **Documentation**: Comprehensive with code examples

#### API Capabilities
```python
import tantivy

# Schema definition for code search
schema_builder = tantivy.SchemaBuilder()
schema_builder.add_text_field("path", stored=True)
schema_builder.add_text_field("content", stored=True, tokenizer_name="code")
schema_builder.add_u64_field("line_start", stored=True, indexed=True)
schema_builder.add_u64_field("line_end", stored=True, indexed=True)
schema_builder.add_text_field("language", stored=True, indexed=True)
schema = schema_builder.build()

# Index management
index = tantivy.Index(schema, path=".code-indexer/tantivy_index/")
writer = index.writer(heap_size=100_000_000)  # 100MB heap
```

### 2.2 Parallel Indexing Architecture

#### Non-Blocking Design
```python
class TantivyIndexer:
    def __init__(self, index_path: Path, commit_interval_ms: int = 50):
        self.index = self._create_or_open_index(index_path)
        self.writer = self.index.writer(heap_size=100_000_000)
        self.commit_interval = commit_interval_ms
        self.pending_docs = []
        self.lock = threading.Lock()

    def index_document_batch(self, documents: List[Dict]):
        """Batch indexing with commit-based visibility."""
        with self.lock:
            for doc in documents:
                tantivy_doc = tantivy.Document()
                tantivy_doc.add_text("path", doc["path"])
                tantivy_doc.add_text("content", doc["content"])
                self.writer.add_document(tantivy_doc)

            # Commit for visibility (5-50ms blocking)
            self.writer.commit()
```

### 2.3 Performance Characteristics

#### Indexing Performance
- **Write throughput**: 10,000-50,000 docs/second (depending on size)
- **Commit latency**: 5-50ms for visibility
- **Memory usage**: 100MB heap + OS page cache
- **Parallel capability**: Thread-safe writer with internal locking

#### Query Performance
- **Simple term queries**: <1ms for most codebases
- **Fuzzy queries**: 5-50ms depending on edit distance
- **Phrase queries**: 1-10ms with positional index
- **Snippet extraction**: 1-5ms per result

### 2.4 Race Condition Analysis

#### Watch Mode Challenges
1. **File change during indexing**: Tantivy handles via MVCC segments
2. **Concurrent writes**: Single writer enforced by Tantivy
3. **Reader consistency**: Point-in-time snapshots via searcher

#### Mitigation Strategies
```python
class GitAwareWatchHandler:
    def _process_changes_with_fts(self):
        # Coordinate semantic and FTS updates
        with self.change_lock:
            changes = list(self.pending_changes)
            self.pending_changes.clear()

        # Process both indexes atomically
        semantic_future = self.smart_indexer.process_async(changes)
        fts_future = self.fts_indexer.process_async(changes)

        # Wait for both to complete
        semantic_future.result()
        fts_future.result()
```

## 3. Architecture Recommendations

### 3.1 Tantivy Schema Design for Code Search

```python
def create_code_search_schema():
    """Optimal schema for code search with Tantivy."""
    schema_builder = tantivy.SchemaBuilder()

    # File metadata
    schema_builder.add_text_field("path", stored=True, tokenizer_name="raw")
    schema_builder.add_text_field("language", stored=True, indexed=True)
    schema_builder.add_u64_field("file_size", stored=True, indexed=True)
    schema_builder.add_date_field("modified_time", stored=True, indexed=True)

    # Content fields with different tokenizers
    schema_builder.add_text_field("content", stored=True, tokenizer_name="code")
    schema_builder.add_text_field("content_raw", stored=False, tokenizer_name="raw")
    schema_builder.add_text_field("identifiers", stored=False, tokenizer_name="simple")

    # Position tracking for snippets
    schema_builder.add_u64_field("line_start", stored=True, indexed=True)
    schema_builder.add_u64_field("line_end", stored=True, indexed=True)
    schema_builder.add_u64_field("byte_start", stored=True, indexed=True)
    schema_builder.add_u64_field("byte_end", stored=True, indexed=True)

    # Git metadata (optional)
    schema_builder.add_text_field("commit_hash", stored=True, indexed=True)
    schema_builder.add_text_field("branch", stored=True, indexed=True)

    return schema_builder.build()
```

### 3.2 Tokenizer Configuration

```python
def configure_tokenizers(index):
    """Configure specialized tokenizers for code search."""

    # Code tokenizer: splits on non-alphanumeric, preserves underscores
    code_tokenizer = tantivy.Tokenizer(
        name="code",
        pattern=r"[a-zA-Z_][a-zA-Z0-9_]*|[0-9]+",
        lowercase=True,
        remove_stop_words=False
    )

    # Raw tokenizer: no tokenization for exact matches
    raw_tokenizer = tantivy.Tokenizer(
        name="raw",
        pattern=None,  # No splitting
        lowercase=False
    )

    # Simple tokenizer: basic word splitting
    simple_tokenizer = tantivy.Tokenizer(
        name="simple",
        pattern=r"\w+",
        lowercase=True
    )

    index.register_tokenizer("code", code_tokenizer)
    index.register_tokenizer("raw", raw_tokenizer)
    index.register_tokenizer("simple", simple_tokenizer)
```

### 3.3 Fuzzy Matching Implementation

```python
class FuzzySearchEngine:
    def __init__(self, index, max_edit_distance: int = 2):
        self.index = index
        self.max_distance = max_edit_distance

    def search_fuzzy(self, query_text: str, field: str = "content"):
        """Perform fuzzy search with Levenshtein distance."""
        parser = tantivy.QueryParser.for_index(self.index, [field])

        # Build fuzzy query with edit distance
        fuzzy_query = f'{field}:"{query_text}"~{self.max_distance}'
        query = parser.parse_query(fuzzy_query)

        searcher = self.index.searcher()
        results = searcher.search(query, limit=100)

        # Post-process to calculate exact edit distances
        return self._rank_by_edit_distance(results, query_text)
```

### 3.4 Snippet Extraction Strategy

```python
class SnippetExtractor:
    def extract_with_context(
        self,
        document: tantivy.Document,
        query: str,
        context_lines: int = 2
    ) -> Dict[str, Any]:
        """Extract matching snippet with configurable context."""
        content = document.get_first("content")
        path = document.get_first("path")

        # Find match position using Tantivy's built-in highlighting
        snippet_generator = tantivy.SnippetGenerator.create(
            searcher=self.searcher,
            query=query,
            field_name="content",
            max_num_chars=500,
            highlight_markup=("<<<", ">>>")
        )

        snippet = snippet_generator.generate(document)

        # Extract surrounding context
        lines = content.split('\n')
        match_line = self._find_match_line(lines, snippet)

        start = max(0, match_line - context_lines)
        end = min(len(lines), match_line + context_lines + 1)

        return {
            "path": path,
            "line_number": match_line + 1,
            "snippet": '\n'.join(lines[start:end]),
            "highlighted": snippet
        }
```

### 3.5 Hybrid Search Result Merging

```python
class HybridSearchEngine:
    def __init__(self, semantic_engine, fts_engine):
        self.semantic = semantic_engine
        self.fts = fts_engine

    def search_hybrid(
        self,
        query: str,
        semantic_weight: float = 0.5,
        fts_weight: float = 0.5
    ) -> List[SearchResult]:
        """Combine FTS and semantic results with weighted scoring."""

        # Execute both searches in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            semantic_future = executor.submit(self.semantic.search, query)
            fts_future = executor.submit(self.fts.search, query)

            semantic_results = semantic_future.result()
            fts_results = fts_future.result()

        # Normalize and merge scores
        merged = {}

        # Add semantic results
        for result in semantic_results:
            key = (result.path, result.line_number)
            merged[key] = SearchResult(
                path=result.path,
                score=result.score * semantic_weight,
                semantic_score=result.score,
                fts_score=0.0,
                content=result.content
            )

        # Merge FTS results
        for result in fts_results:
            key = (result.path, result.line_number)
            if key in merged:
                merged[key].fts_score = result.score
                merged[key].score += result.score * fts_weight
            else:
                merged[key] = SearchResult(
                    path=result.path,
                    score=result.score * fts_weight,
                    semantic_score=0.0,
                    fts_score=result.score,
                    content=result.content
                )

        # Sort by combined score
        return sorted(merged.values(), key=lambda x: x.score, reverse=True)
```

## 4. Critical Design Decisions

### 4.1 Commit Strategy Trade-offs

| Strategy | Latency | Durability | Use Case |
|----------|---------|------------|----------|
| Per-file commit | 5-50ms per file | High | Watch mode, real-time |
| Batch commit (100 files) | 50-100ms total | Medium | Initial indexing |
| Time-based commit (1s) | 0ms write, 50ms/second | Low | High-throughput |
| Manual commit | 0ms write, 50ms on demand | Variable | User-controlled |

**Recommendation**: Adaptive strategy based on mode
- Watch mode: Per-file or small batch (10 files)
- Initial index: Large batch (100-1000 files)
- Server mode: Time-based (1 second intervals)

### 4.2 Index Storage Trade-offs

| Approach | Storage Size | Query Speed | Update Speed |
|----------|--------------|-------------|--------------|
| Single segment | Minimal | Fastest | Slowest |
| Many segments | Larger | Slower | Fastest |
| Optimized (merged) | Medium | Fast | Medium |

**Recommendation**: Automatic merge policy
- Keep 10-20 segments during active indexing
- Merge to 3-5 segments when idle
- Full optimization only on explicit command

### 4.3 Memory Management

```python
class TantivyMemoryManager:
    """Adaptive memory management for Tantivy indexing."""

    def calculate_heap_size(self, available_memory_mb: int) -> int:
        """Calculate optimal heap size based on system resources."""
        # Use 10% of available memory, max 500MB
        heap_mb = min(available_memory_mb * 0.1, 500)

        # Minimum 50MB for reasonable performance
        heap_mb = max(heap_mb, 50)

        return int(heap_mb * 1_000_000)  # Convert to bytes
```

## 5. Implementation Risks and Mitigations

### 5.1 Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Tantivy API changes | Low | High | Pin version, comprehensive tests |
| Index corruption | Low | High | Backup strategy, atomic operations |
| Memory exhaustion | Medium | Medium | Heap limits, monitoring |
| Slow commits blocking UI | Medium | Low | Async commits, progress indication |
| Index size explosion | Medium | Medium | Compression, segment merging |
| Query performance degradation | Low | Medium | Query optimization, caching |

### 5.2 Graceful Degradation Pattern

```python
class FTSManager:
    def __init__(self, index_path: Path):
        self.index_path = index_path
        self.index = None
        self.available = False

    def initialize(self) -> bool:
        """Initialize FTS with graceful fallback."""
        try:
            if not self.index_path.exists():
                logger.warning("FTS index not found - text search unavailable")
                return False

            self.index = tantivy.Index.open(str(self.index_path))
            self.available = True
            logger.info("FTS index loaded successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to load FTS index: {e}")
            logger.info("Falling back to semantic search only")
            return False

    def search(self, query: str) -> Optional[List[SearchResult]]:
        """Search with automatic fallback."""
        if not self.available:
            logger.debug("FTS unavailable - skipping text search")
            return None

        try:
            return self._execute_search(query)
        except Exception as e:
            logger.error(f"FTS search failed: {e}")
            return None
```

## 6. Integration Sequence

### Phase 1: Core FTS Infrastructure
1. Add Tantivy dependency to requirements
2. Implement `TantivyIndexer` class
3. Add schema definition for code search
4. Integrate with `SmartIndexer` for parallel processing

### Phase 2: CLI Integration
1. Add `--fts` flag to `index` command
2. Implement progress reporting for dual indexing
3. Add `--fts` flag to `watch` command
4. Implement incremental FTS updates

### Phase 3: Query Implementation
1. Add `--fts` flag to `query` command
2. Implement fuzzy matching logic
3. Add snippet extraction with context
4. Implement result formatting

### Phase 4: Hybrid Search
1. Add `--semantic` flag for dual mode
2. Implement result merging strategy
3. Add weighted scoring configuration
4. Optimize performance for parallel queries

### Phase 5: Server API
1. Extend `QueryRequest` model
2. Add FTS support to `SemanticQueryManager`
3. Implement index availability checks
4. Add FTS-specific error handling

## 7. Performance Projections

### Indexing Performance
- **Small codebase** (1,000 files): <5 seconds additional
- **Medium codebase** (10,000 files): 30-60 seconds additional
- **Large codebase** (100,000 files): 5-10 minutes additional

### Query Performance
- **Simple term query**: <5ms
- **Fuzzy query** (distance=1): 10-20ms
- **Fuzzy query** (distance=2): 30-50ms
- **Hybrid search**: Max(semantic, FTS) + 5ms merging

### Storage Overhead
- **Index size**: ~30-50% of source code size
- **With compression**: ~15-25% of source code size
- **Segment files**: 10-20 files per index

## 8. Conclusion

The integration of Tantivy-based full-text search into CIDX is technically feasible and architecturally sound. The proposed design:

1. **Preserves existing functionality** - All semantic search capabilities remain unchanged
2. **Enables efficient text search** - Sub-millisecond exact matching with fuzzy support
3. **Maintains performance** - Parallel indexing with minimal overhead
4. **Provides flexibility** - Opt-in via flags, graceful degradation
5. **Scales appropriately** - Handles codebases from small to very large

The key architectural decisions focus on:
- **Non-invasive integration** through optional flags
- **Parallel processing** to minimize indexing time
- **Adaptive commit strategies** for different use cases
- **Graceful error handling** when FTS is unavailable

The implementation can proceed in phases, with each phase delivering incremental value while maintaining system stability.
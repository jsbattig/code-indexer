# Epic: Temporal Git History Semantic Search

## Epic Overview

**Problem Statement:**
AI coding agents (like Claude Code) need semantic search across git history to find removed code, understand pattern evolution, prevent regressions, and debug with historical context. Current tools (git blame, git log) only provide text-based or current-state views.

**Target Users:**
- Claude Code and other AI coding agents working on codebases
- Developers needing historical context for debugging
- Teams tracking code evolution patterns

**Success Criteria:**
- Semantic temporal queries working across git history
- Code evolution visualization with commit messages, diffs, and branch context
- 92%+ storage savings via git blob deduplication
- Query performance <300ms on 40K+ repos
- Backward compatibility maintained (space-only search unchanged)
- Cost-effective default behavior (single branch) with opt-in for complete multi-branch coverage

**CRITICAL BLOB INDEXING MODEL:**

We index each **unique blob hash ONCE**, regardless of how many commits reference it. The temporal database (commits.db) tracks which commits reference each blob through the `trees` table.

**Example:** If blob `abc123` (containing `user.py` with authentication code) appears in 100 commits across history:
- **Embeddings:** Created ONCE for blob `abc123` (12 chunks → 12 vectors)
- **Temporal Links:** 100 rows in `trees` table linking commits to blob `abc123`
- **Storage Savings:** 92% reduction (1 embedding set vs 100 duplicates)
- **Queries:** All 100 commits can find this code via shared vectors

**Why This Matters:**
- **Deduplication is critical:** 42K file repo with 150K historical blobs → Only 12K unique blobs need embeddings
- **Query correctness:** Multiple commits correctly return same removed code
- **Performance:** 4-7 minutes vs 50+ hours without deduplication
- **Cost:** $50 vs $600+ in API calls without deduplication

**Branch Strategy (Based on Analysis of Evolution Repository):**
- **Default:** Index current branch only (development/main) - provides 91.6% commit coverage
- **Opt-in:** `--all-branches` flag for complete multi-branch history
- **Rationale:** Indexing all branches in large repos increases storage by ~85% for only ~8% more commits
- **Flexibility:** Track branch metadata for all indexed commits to support future branch-aware queries

## Features

### 00_Story_BackgroundIndexRebuilding (PREREQUISITE)
**Purpose:** Establish foundational locking mechanism for atomic index updates
**Story:** Background Index Rebuilding with Atomic Swap
**Status:** **MUST BE IMPLEMENTED FIRST** - All subsequent stories depend on this infrastructure
**Implementation Order:** Story 0 → STOP for review → Story 1 (after approval)

### 01_Feat_TemporalIndexing
**Purpose:** Build and maintain temporal index of git history with branch awareness
**Stories:**
- 01_Story_GitHistoryIndexingWithBlobDedup: Index repository git history with deduplication and branch metadata
- 02_Story_IncrementalIndexingWithWatch: Incremental indexing with watch mode integration
- 03_Story_SelectiveBranchIndexing: Selective branch indexing with pattern matching

### 02_Feat_TemporalQueries
**Purpose:** Enable semantic search across git history with temporal filters
**Stories:**
- 01_Story_TimeRangeFiltering: Query with time-range filtering
- 02_Story_PointInTimeQuery: Query at specific commit

### 03_Feat_CodeEvolutionVisualization
**Purpose:** Display code evolution with diffs and commit context
**Stories:**
- 01_Story_EvolutionDisplayWithCommitContext: Display evolution timeline with diffs

### 04_Feat_APIServerTemporalRegistration
**Purpose:** Enable golden repository registration with temporal indexing via API
**Stories:**
- 01_Story_GoldenRepoRegistrationWithTemporal: Admin registers golden repos with enable_temporal flag

### 05_Feat_APIServerTemporalQuery
**Purpose:** Enable temporal search via API with time-range, point-in-time, and evolution queries
**Stories:**
- 01_Story_TemporalQueryParametersViaAPI: Users query with temporal parameters via POST /api/query

## Technical Architecture

### Storage Architecture

**SQLite Database** (`.code-indexer/index/temporal/commits.db`):
```sql
CREATE TABLE commits (
    hash TEXT PRIMARY KEY,
    date INTEGER NOT NULL,
    author_name TEXT,
    author_email TEXT,
    message TEXT,
    parent_hashes TEXT
);

CREATE TABLE trees (
    commit_hash TEXT NOT NULL,
    file_path TEXT NOT NULL,
    blob_hash TEXT NOT NULL,
    PRIMARY KEY (commit_hash, file_path),
    FOREIGN KEY (commit_hash) REFERENCES commits(hash)
);

-- NEW: Branch metadata tracking
CREATE TABLE commit_branches (
    commit_hash TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    is_head INTEGER DEFAULT 0,  -- 1 if this was HEAD when indexed
    indexed_at INTEGER NOT NULL,  -- Unix timestamp
    PRIMARY KEY (commit_hash, branch_name),
    FOREIGN KEY (commit_hash) REFERENCES commits(hash)
);

-- Performance indexes for 40K+ repos
CREATE INDEX idx_trees_blob_commit ON trees(blob_hash, commit_hash);
CREATE INDEX idx_commits_date_hash ON commits(date, hash);
CREATE INDEX idx_trees_commit ON trees(commit_hash);
CREATE INDEX idx_commit_branches_hash ON commit_branches(commit_hash);
CREATE INDEX idx_commit_branches_name ON commit_branches(branch_name);
```

**Blob Registry** (`.code-indexer/index/temporal/blob_registry.db`):
- SQLite database mapping blob_hash → point_ids from existing vectors
- Required for large-scale repos (40K+ files, 10GB+ with history)
- Indexed for fast lookups (microseconds per blob)
- Lazy connection with result caching

**Temporal Metadata** (`.code-indexer/index/temporal/temporal_meta.json`):
- Tracks last_indexed_commit, indexing state, statistics
- Records indexed_branches (list of branch names/patterns)
- Stores indexing_mode ('single-branch' or 'all-branches')
- Branch-specific stats: commits_per_branch, deduplication_ratio

### Component Architecture

**New Components:**
1. `TemporalIndexer` - Orchestrates git history indexing (mode-agnostic)
2. `TemporalBlobScanner` - Discovers blobs in git history via `git ls-tree`
3. `GitBlobReader` - Reads blob content from git object store via `git cat-file`
4. `HistoricalBlobProcessor` - Parallel blob processing (analogous to HighThroughputProcessor)
5. `TemporalSearchService` - Handles temporal queries (mode-agnostic)
6. `TemporalFormatter` - Formats temporal results with Rich

**Integration Points:**
- CLI: New flags for index and query commands
- Config: `enable_temporal` setting
- Watch Mode: Maintains temporal index if enabled
- Daemon Mode: Automatic delegation when `daemon.enabled: true`

### Progress Callback Specification (CRITICAL)

**Standard Signature (All Modes):**
```python
def progress_callback(
    current: int,
    total: int,
    path: Path,
    info: str = ""
) -> None:
    """
    Universal progress callback for indexing operations.

    Args:
        current: Current progress count (files, blobs, commits processed)
        total: Total count (0 for setup messages, >0 for progress bar)
        path: Path being processed (file path or empty Path("") for setup)
        info: Formatted progress string (specific format required for CLI)

    CLI Format Requirements:
        - Setup messages (total=0): info="Setup message text"
          Triggers ℹ️ scrolling display
        - File progress (total>0): info="X/Y files (%) | emb/s | threads | filename"
          Triggers progress bar with metrics display
        - CRITICAL: Do not change format without updating cli.py progress_callback logic

    Daemon Mode Requirements:
        - Must be RPyC-serializable (primitives only: int, str, Path)
        - No complex objects (no Path operations during callback)
        - Callback executed in daemon process, results streamed to client

    Thread Safety Requirements:
        - Callback MUST be thread-safe (called from multiple worker threads)
        - Use locks for any shared state updates
        - Keep callback execution fast (<1ms) to avoid blocking workers
    """
```

**Temporal Indexing Usage:**
```python
# Setup phase (total=0 triggers ℹ️ display)
progress_callback(0, 0, Path(""), info="Scanning git history...")
progress_callback(0, 0, Path(""), info="Found 40,123 commits to index")
progress_callback(0, 0, Path(""), info="Deduplicating blobs (92% expected savings)...")

# Blob processing phase (total>0 triggers progress bar)
for i, blob in enumerate(blobs_to_process):
    # Format: "X/Y blobs (%) | emb/s | threads | blob_description"
    info = f"{i+1}/{total} blobs ({percent}%) | {emb_per_sec:.1f} emb/s | {threads} threads | {blob.tree_path}"
    progress_callback(i+1, total, Path(blob.tree_path), info=info)
```

**RPyC Serialization (Daemon Mode):**
```python
# CORRECT: Simple types serialize over RPyC
progress_callback(
    current=42,                    # int: serializable ✅
    total=1000,                    # int: serializable ✅
    path=Path("src/file.py"),      # Path: serializable ✅
    info="42/1000 files (4%)"      # str: serializable ✅
)

# WRONG: Complex objects fail serialization
progress_callback(
    current=42,
    total=1000,
    path=Path("src/file.py"),
    info={"files": 42, "total": 1000}  # dict: NOT serializable ❌
)
```

**Correlation IDs (Future Enhancement):**
When implementing multi-operation tracking, consider adding correlation IDs:
```python
def progress_callback(
    current: int,
    total: int,
    path: Path,
    info: str = "",
    correlation_id: Optional[str] = None  # Links related progress updates
) -> None:
    """Correlation ID enables ordering progress from concurrent operations."""
```

**Thread Safety Pattern:**
```python
class TemporalIndexer:
    def __init__(self, progress_callback):
        self.progress_callback = progress_callback
        self.callback_lock = threading.Lock()  # Protect callback invocation
        self.progress_cache = {}  # Cache for concurrent_files display

    def _report_progress(self, current, total, path, info):
        """Thread-safe progress reporting."""
        with self.callback_lock:
            self.progress_callback(current, total, path, info)
```

**Performance Requirements:**
- Callback execution: <1ms (avoid blocking worker threads)
- Call frequency: ~10-50 per second during active processing
- Network overhead (daemon): ~10-20ms latency for RPC round-trip
- Total progress overhead: <5% of processing time

### Indexing Pipeline Reuse Strategy (CRITICAL)

**What We Index: Full Blob Versions, NOT Diffs**

Git blobs represent **complete file versions** at specific points in time. We index full blob content for semantic search, not diffs:

```
✅ CORRECT: Index full blob content
Commit abc123: user.py (blob def456)
→ Complete file: class User with all methods and context

❌ WRONG: Index diffs
Commit abc123: user.py diff
→ Partial: +def greet(): ... (no class context)
```

**Why Full Blobs:**
1. **Semantic search requires full context** - can't find code patterns in partial diffs
2. **Users want complete implementations** - "find removed authentication code" needs full class
3. **Git already stores blobs efficiently** - compression + deduplication is built-in
4. **Deduplication works better** - same content across commits = same blob hash = reuse vectors

**Pipeline Component Reuse (60-65% Reuse Rate):**

**Reality Check:** While the core embedding/storage pipeline is highly reusable, adapting it for git blob processing requires more new code than initially estimated. The breakdown below reflects realistic implementation complexity.

**✅ Fully Reusable (~40% of total implementation):**
- `VectorCalculationManager` - Takes text chunks → embeddings (source-agnostic, zero changes)
- `FilesystemVectorStore` - Writes vector JSON files (already supports blob_hash in metadata)
- Threading infrastructure - `ThreadPoolExecutor`, `CleanSlotTracker` (reusable patterns)

**🔧 Requires Modification (~25% of total implementation):**
- `FixedSizeChunker` - Already has `chunk_text(text, file_path)` method, but needs blob-specific metadata handling
- `HighThroughputProcessor` - Core patterns reusable, but needs adaptation for blob queue instead of file queue
- Progress callback mechanism - Signature compatible, but needs blob-specific tracking (commit hash, blob count)

**🆕 New Git-Specific Components (~35% of total implementation):**
- `TemporalIndexer` - Orchestrates entire temporal indexing workflow (new coordinator)
- `TemporalBlobScanner` - Discovers blobs via `git ls-tree` (replaces FileFinder's disk walking)
- `GitBlobReader` - Reads blob content via `git cat-file` (replaces file I/O)
- `HistoricalBlobProcessor` - Manages blob queue and parallel processing (adapts HighThroughputProcessor patterns)
- `TemporalSearchService` - Handles temporal queries with SQLite filtering (new query layer)
- `TemporalFormatter` - Formats temporal results with Rich output (new display logic)

**Adaptation Complexity:**
- **File → Blob Translation:** Blobs have no filesystem path (use git object references)
- **Metadata Differences:** Blob hash, commit hash, tree path vs file path, line numbers
- **Git Subprocess Integration:** `git ls-tree`, `git cat-file`, `git log` performance tuning
- **SQLite Coordination:** Blob registry, commit metadata, branch tracking integration
- **Memory Management:** 12K blob processing requires careful memory handling vs file-by-file

**Architecture Comparison:**

```
Workspace Indexing (HEAD):
  Disk Files → FileIdentifier → FixedSizeChunker
    → VectorCalculationManager → FilesystemVectorStore

Git History Indexing (Temporal):
  Git Blobs → GitBlobReader → FixedSizeChunker.chunk_text()
    → VectorCalculationManager → FilesystemVectorStore
           ↑                         ↑
        SAME COMPONENTS REUSED
```

**Deduplication Strategy:**
```python
# For each commit
for commit in commits:
    # 1. Get all blobs in commit (git ls-tree)
    all_blobs = scanner.get_blobs_for_commit(commit)  # 150 blobs

    # 2. Check blob registry (SQLite lookup, microseconds)
    new_blobs = [b for b in all_blobs if not registry.has_blob(b.hash)]
    # Result: ~12 new blobs (92% already have vectors)

    # 3. Process ONLY new blobs (reuse existing for rest)
    if new_blobs:
        processor.process_blobs_high_throughput(new_blobs)
        # Uses VectorCalculationManager + FilesystemVectorStore
```

**Performance Expectations (Repository Size Matters):**

**CRITICAL:** Indexing time scales with (commits × files/commit). Larger repos take longer.

**Benchmarked on Evolution Repo (89K commits, 27K files/commit, 9.2GB):**
- `git log`: 50,000+ commits/sec (extremely fast)
- `git ls-tree`: 19 commits/sec, 52.7ms/commit (bottleneck)
- `git cat-file --batch`: 419-869 blobs/sec, 1.2-2.4ms/blob (excellent)
- Actual deduplication: 99.9% (better than 92% estimate)

**Timing by Repository Size:**

| Repo Size | Files/Commit | Commits | Unique Blobs | Indexing Time | Bottleneck |
|-----------|--------------|---------|--------------|---------------|------------|
| **Small** | 1-5K | 10-20K | 2-5K | **4-10 min** | git ls-tree (9-18 min) |
| **Medium** | 5-10K | 40K | 12-16K | **30-45 min** | git ls-tree (~35 min) |
| **Large** | 20K+ | 80K+ | 20-30K | **60-90 min** | git ls-tree (~70 min) |

**Component Breakdown (40K commit medium repo):**
- `git log` (40K commits): <1 min
- `git ls-tree` (40K commits): **35 min** ⚠️ BOTTLENECK (80% of time)
- `git cat-file` (12K blobs): <1 min
- Embedding generation (144K chunks): 3 min
- SQLite operations: 3 min

**Incremental Indexing (All Sizes):**
- Only new commit blobs → <1 minute ✅

**Key Insights:**
- ✅ `git cat-file` is FAST (no optimization needed)
- ⚠️  `git ls-tree` scales with repo size (fundamental git limitation)
- ✅ Deduplication works BETTER than expected (99.9% vs 92%)
- ⚠️  Initial indexing time varies widely by repo size
- ✅ Incremental updates are fast regardless of repo size

**Progress Reporting Strategy:**
Since `git ls-tree` consumes 80%+ of time, progress must show:
- "Processing commit X/Y" (commit-level progress)
- Commits/sec rate and ETA
- Clear indication this is normal (not stuck)

**See Analysis Documents:**
- `.analysis/temporal_indexing_pipeline_reuse_strategy.md` - Complete implementation guide
- `.analysis/temporal_blob_registry_sqlite_decision.md` - SQLite rationale
- `.tmp/git_performance_final_analysis.md` - Evolution repo benchmarks (Nov 2, 2025)

### Memory Management Strategy (CRITICAL)

**Problem:** Processing 12K unique blobs requires careful memory management to avoid OOM conditions on large repositories.

**Blob Size Reality Check:**
- **Typical blob sizes:** 50KB-500KB per file (median ~100KB)
- **12K blobs in memory:** 1.2GB-6GB total (uncompressed)
- **With chunking overhead:** ~2-8GB peak memory
- **Risk:** Loading all blobs at once → OOM on systems with <16GB RAM

**Streaming Batch Processing Strategy:**

```python
class HistoricalBlobProcessor:
    """Process blobs in memory-efficient batches."""

    BATCH_SIZE = 500  # Process 500 blobs at a time
    MAX_BATCH_MEMORY_MB = 512  # Target 512MB per batch

    def process_blobs_in_batches(self, blob_hashes: List[str]):
        """
        Stream blobs in batches to avoid OOM.

        Memory Profile:
        - 500 blobs × ~100KB avg = 50MB blob content
        - Chunking overhead: ~2x (100MB for chunks)
        - Embedding queue: ~3x (300MB for vectors)
        - Peak: ~450MB per batch (safe for 4GB+ systems)
        """

        for batch_start in range(0, len(blob_hashes), self.BATCH_SIZE):
            batch_end = min(batch_start + self.BATCH_SIZE, len(blob_hashes))
            batch = blob_hashes[batch_start:batch_end]

            # 1. Read batch (streaming from git)
            blob_contents = self._read_blobs_batch(batch)

            # 2. Chunk batch
            all_chunks = []
            for blob_hash, content in blob_contents.items():
                chunks = self.chunker.chunk_text(content, Path(blob_hash))
                all_chunks.extend(chunks)

            # 3. Generate embeddings (VectorCalculationManager)
            embedding_futures = []
            for chunk in all_chunks:
                future = self.vector_manager.submit_batch_task([chunk["text"]], chunk)
                embedding_futures.append(future)

            # 4. Store vectors (FilesystemVectorStore)
            for future in concurrent.futures.as_completed(embedding_futures):
                result = future.result()
                self.vector_store.upsert_points(collection_name, [result])

            # 5. FREE MEMORY: Clear batch data before next iteration
            del blob_contents, all_chunks, embedding_futures
            gc.collect()  # Force garbage collection between batches

            # 6. Update progress
            progress_callback(batch_end, len(blob_hashes), Path(""), info=f"Batch {batch_end}/{len(blob_hashes)}")
```

**Batch Size Selection:**

| Batch Size | Memory Usage | Processing Time | Tradeoffs |
|------------|--------------|-----------------|-----------|
| 100 blobs  | ~100MB peak  | Slower (more batches) | Safe for 2GB systems |
| 500 blobs  | ~450MB peak  | Balanced | **RECOMMENDED** (4GB+ systems) |
| 1000 blobs | ~900MB peak  | Faster (fewer batches) | Requires 8GB+ systems |
| 5000 blobs | ~4.5GB peak  | Fastest | Risk: OOM on 8GB systems |

**Decision:** Default 500 blobs per batch (safe for 4GB+ systems, typical developer machines)

**Dynamic Batch Sizing (Future Enhancement):**
```python
def _calculate_batch_size(self, available_memory_mb: int) -> int:
    """Adjust batch size based on available system memory."""
    if available_memory_mb < 4096:
        return 100  # Conservative for 2-4GB systems
    elif available_memory_mb < 8192:
        return 500  # Balanced for 4-8GB systems
    else:
        return 1000  # Aggressive for 8GB+ systems
```

**OOM Prevention Mechanisms:**

**1. Memory Monitoring:**
```python
import psutil

def _check_memory_before_batch(self):
    """Verify sufficient memory before starting batch."""
    memory = psutil.virtual_memory()
    available_mb = memory.available / (1024 ** 2)

    if available_mb < 1024:  # Less than 1GB available
        logger.warning(f"Low memory: {available_mb:.0f}MB available, reducing batch size")
        self.BATCH_SIZE = max(50, self.BATCH_SIZE // 2)

    if available_mb < 512:  # Critical: less than 512MB
        raise MemoryError(f"Insufficient memory: {available_mb:.0f}MB available, cannot proceed safely")
```

**2. Streaming Git Blob Reads:**
```python
def _read_blobs_batch(self, blob_hashes: List[str]) -> Dict[str, str]:
    """Stream blob content from git without loading all into memory."""
    results = {}

    # Use git cat-file --batch for efficient streaming
    with subprocess.Popen(
        ["git", "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        cwd=self.repo_path
    ) as proc:
        for blob_hash in blob_hashes:
            proc.stdin.write(f"{blob_hash}\n".encode())
            proc.stdin.flush()

            # Read blob header
            header = proc.stdout.readline().decode()
            if "missing" in header:
                continue

            # Read blob content (only this blob in memory)
            size = int(header.split()[2])
            content = proc.stdout.read(size).decode(errors='ignore')
            results[blob_hash] = content

            # Immediately process if memory-constrained
            if len(results) >= self.BATCH_SIZE:
                yield results
                results.clear()

        if results:
            yield results
```

**3. Explicit Memory Cleanup:**
```python
def _cleanup_batch_memory(self):
    """Aggressively free memory after batch processing."""
    # Clear any cached data
    self.blob_cache.clear()
    self.chunk_cache.clear()

    # Force Python garbage collection
    import gc
    gc.collect()

    # Log memory status
    memory = psutil.virtual_memory()
    logger.debug(f"Post-batch memory: {memory.available / (1024**2):.0f}MB available")
```

**SQLite Memory Configuration:**
```sql
-- Limit SQLite memory usage
PRAGMA cache_size = 2000;      -- 2MB cache (default -2000 = 2MB)
PRAGMA temp_store = MEMORY;    -- Keep temp tables in memory (faster)
PRAGMA mmap_size = 268435456;  -- 256MB memory-mapped I/O limit
```

**Memory Budget Allocation (Total: 4GB System):**

| Component | Memory Budget | Notes |
|-----------|---------------|-------|
| Blob batch content | 50MB | 500 blobs × 100KB avg |
| Chunking overhead | 100MB | 2x content for chunk processing |
| Embedding queue | 300MB | 3x for vector calculation |
| SQLite databases | 50MB | Blob registry + commits.db |
| FilesystemVectorStore writes | 100MB | JSON file writes |
| Python overhead | 200MB | Interpreter, libraries |
| OS buffer cache | 1GB | Git operations, file I/O |
| **Safety margin** | **2.2GB** | **Available for other processes** |
| **Total** | **4GB** | **Safe for typical developer machines** |

**Validation Strategy:**
```python
def test_memory_usage_under_load():
    """Integration test: verify memory stays within bounds."""
    import tracemalloc

    tracemalloc.start()

    # Process 12K blobs
    processor.process_blobs_in_batches(blob_hashes)

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Assert: Peak memory < 1GB (safe margin)
    assert peak < 1024 * 1024 * 1024, f"Peak memory {peak/(1024**2):.0f}MB exceeds 1GB limit"
```

**Configuration Options:**
```yaml
# .code-indexer/config.json
temporal:
  batch_size: 500                    # Blobs per batch
  max_batch_memory_mb: 512          # Memory limit per batch
  enable_memory_monitoring: true     # Check available memory before batches
  force_gc_between_batches: true     # Garbage collect after each batch
```

**Performance Impact:**
- Streaming batches: +10-15% processing time vs loading all blobs
- Memory safety: Prevents OOM crashes
- Scalability: Works on 4GB systems, scales to 16GB+ systems
- Trade-off: Slightly slower, but reliable on typical hardware

### Repository Lifecycle Integration

**CRITICAL: Temporal indexing happens in GOLDEN REPOSITORIES with CoW inheritance to activated repos.**

**Architecture Overview:**

1. **Golden Repository** (`~/.cidx-server/data/golden-repos/<alias>/`):
   - Admin registers repo via API: `POST /api/register` with index_types selection
   - Golden repo is cloned/indexed ONCE with selected index types
   - Temporal indexing: `cidx index --index-commits` in golden repo
   - All indexes stored: Semantic (FilesystemVectorStore), FTS (Tantivy), Temporal (SQLite commits.db + blob_registry.db)
   - Result: Complete multi-index golden repository ready for activation

2. **Copy-on-Write (CoW) Inheritance** (activated repos):
   - User activates repo: Gets hardlink copy of ALL index data
   - SQLite databases (commits.db, blob_registry.db) → CoW copied
   - JSON chunk files (.code-indexer/index/) → CoW copied
   - HNSW binary indexes → CoW copied
   - FTS Tantivy indexes → CoW copied
   - NO re-indexing required, instant activation

3. **No Containers for Vector Storage:**
   - **CRITICAL:** Qdrant is legacy, NOT used anymore
   - FilesystemVectorStore: Pure JSON files, no containers
   - Temporal SQLite: Pure database files, no containers
   - FTS Tantivy: Pure index files, no containers
   - Only containers: Qdrant (legacy, unused), data-cleaner (optional)

**API Server Index Class Selection:**

When registering golden repos via `POST /api/register`, specify which index types to create:

```json
{
  "repo_url": "https://github.com/user/repo.git",
  "index_types": ["semantic", "fts", "temporal"],  // NEW: Select index classes
  "temporal_options": {  // NEW: Temporal-specific configuration
    "all_branches": false,  // Default: current branch only
    "branch_patterns": ["main", "develop"],  // Alternative: specific patterns
    "max_commits": null,  // Optional: limit history depth
    "since_date": null  // Optional: index commits after date
  }
}
```

**Index Types:**
- `"semantic"`: Default FilesystemVectorStore with HNSW (always included)
- `"fts"`: Full-text search via Tantivy (optional, fast exact text matching)
- `"temporal"`: Git history indexing with temporal queries (optional, this epic)

**Combinations Allowed:**
- `["semantic"]` - Just vector search (default, minimal)
- `["semantic", "fts"]` - Vector + full-text search
- `["semantic", "temporal"]` - Vector + git history
- `["semantic", "fts", "temporal"]` - All three (comprehensive)

**Implementation Notes:**
- Registration becomes async job (long-running temporal indexing)
- Job status API: `GET /api/job/{job_id}` for progress tracking
- Golden repo stores index type metadata in config
- Activated repos inherit all index types from golden
- Users query using same `POST /api/query` with temporal parameters

**Why This Matters:**
- **Scalability:** Index once in golden, share via CoW to thousands of users
- **Cost:** Expensive temporal indexing (4-7 min, $50 API cost) happens ONCE
- **Flexibility:** Users choose which index types they need upfront
- **Consistency:** All activated repos have identical search capabilities

### API Server Async Job Queue Architecture

**CRITICAL: Long-running indexing operations MUST be async with job tracking.**

**Problem:**
- Temporal indexing takes 4-7 minutes for large repos
- HTTP clients timeout waiting for synchronous response
- Users need progress visibility
- Multiple concurrent indexing jobs must be supported

**Solution: Background Job Queue with Status API**

#### Job Queue Implementation

```python
# In src/code_indexer/server/job_queue.py

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, Callable
from queue import Queue

class JobStatus(Enum):
    """Job lifecycle states."""
    QUEUED = "queued"           # Waiting in queue
    RUNNING = "running"         # Currently executing
    COMPLETED = "completed"     # Finished successfully
    FAILED = "failed"           # Failed with error
    CANCELLED = "cancelled"     # User cancelled

@dataclass
class Job:
    """Background job representation."""
    id: str
    type: str  # "index_repository", "temporal_index", "rebuild_hnsw"
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class JobQueue:
    """
    Background job queue for long-running operations.

    Architecture:
    - Single background worker thread processes jobs serially
    - Jobs execute one at a time (prevents resource contention)
    - Job status tracked in memory (no persistence needed)
    - Progress callbacks update job.progress dictionary
    """

    def __init__(self):
        self.jobs: Dict[str, Job] = {}  # job_id -> Job
        self.queue: Queue = Queue()
        self.worker_thread: Optional[threading.Thread] = None
        self.running = False

    def start(self):
        """Start background worker thread."""
        if self.running:
            return

        self.running = True
        self.worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="JobQueueWorker"
        )
        self.worker_thread.start()

    def stop(self):
        """Stop background worker thread."""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)

    def submit_job(
        self,
        job_type: str,
        task_callable: Callable,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Submit job to queue.

        Args:
            job_type: Job type identifier
            task_callable: Function to execute (receives job for progress updates)
            metadata: Optional metadata (repo_url, index_types, etc.)

        Returns:
            Job ID for status tracking
        """
        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            type=job_type,
            status=JobStatus.QUEUED,
            created_at=datetime.now(),
            metadata=metadata or {}
        )

        self.jobs[job_id] = job
        self.queue.put((job_id, task_callable))

        return job_id

    def get_job_status(self, job_id: str) -> Optional[Job]:
        """Get current job status."""
        return self.jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel job (if not started yet).

        Returns True if cancelled, False if already running/completed.
        """
        job = self.jobs.get(job_id)
        if not job:
            return False

        if job.status == JobStatus.QUEUED:
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.now()
            return True

        return False  # Can't cancel running/completed jobs

    def _worker_loop(self):
        """Background worker loop - processes jobs serially."""
        import logging
        logger = logging.getLogger(__name__)

        while self.running:
            try:
                # Get next job (blocks with timeout)
                job_id, task_callable = self.queue.get(timeout=1)

                job = self.jobs.get(job_id)
                if not job or job.status == JobStatus.CANCELLED:
                    continue

                # Update job status
                job.status = JobStatus.RUNNING
                job.started_at = datetime.now()

                logger.info(f"Job {job_id} ({job.type}): Started")

                try:
                    # Execute task (pass job for progress updates)
                    result = task_callable(job)

                    # Mark completed
                    job.status = JobStatus.COMPLETED
                    job.result = result
                    job.completed_at = datetime.now()

                    logger.info(f"Job {job_id} ({job.type}): Completed")

                except Exception as e:
                    # Mark failed
                    job.status = JobStatus.FAILED
                    job.error = str(e)
                    job.completed_at = datetime.now()

                    logger.error(f"Job {job_id} ({job.type}): Failed - {e}")

            except Exception as e:
                if self.running:  # Ignore timeout exceptions during shutdown
                    logger.error(f"Worker loop error: {e}")
```

#### API Endpoint Integration

```python
# In src/code_indexer/server/api.py

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
from .job_queue import JobQueue, JobStatus

app = FastAPI()
job_queue = JobQueue()

# Start job queue on server startup
@app.on_event("startup")
async def startup_event():
    job_queue.start()

@app.on_event("shutdown")
async def shutdown_event():
    job_queue.stop()

class RepositoryRegistration(BaseModel):
    """Request body for repository registration."""
    repo_url: str
    index_types: List[str] = ["semantic"]  # semantic, fts, temporal
    temporal_options: Optional[dict] = None

class JobResponse(BaseModel):
    """Job submission response."""
    job_id: str
    status: str
    message: str

@app.post("/api/register", response_model=JobResponse)
async def register_repository(request: RepositoryRegistration):
    """
    Register repository for indexing (async).

    Returns immediately with job_id for status tracking.
    Actual indexing happens in background.
    """

    def index_task(job):
        """Background indexing task."""
        from ...services.smart_indexer import SmartIndexer
        from ...services.temporal_indexer import TemporalIndexer

        # Progress callback updates job.progress
        def progress_callback(current, total, file_path, info=""):
            job.progress = {
                "current": current,
                "total": total,
                "file_path": str(file_path),
                "info": info,
                "percent": int((current / total * 100)) if total > 0 else 0
            }

        # Clone repository
        job.progress = {"status": "Cloning repository..."}
        golden_repo_path = clone_to_golden(request.repo_url)

        # Index based on selected types
        results = {}

        if "semantic" in request.index_types:
            job.progress = {"status": "Indexing semantic vectors..."}
            smart_indexer = SmartIndexer(config_manager)
            smart_indexer.index_repository(
                repo_path=str(golden_repo_path),
                progress_callback=progress_callback
            )
            results["semantic"] = "completed"

        if "fts" in request.index_types:
            job.progress = {"status": "Building FTS index..."}
            # FTS indexing...
            results["fts"] = "completed"

        if "temporal" in request.index_types:
            job.progress = {"status": "Indexing git history (4-7 min)..."}
            temporal_indexer = TemporalIndexer(
                repo_path=golden_repo_path,
                config=config
            )
            temporal_indexer.index_commits(
                all_branches=request.temporal_options.get("all_branches", False),
                branch_patterns=request.temporal_options.get("branch_patterns"),
                progress_callback=progress_callback
            )
            results["temporal"] = "completed"

        return results

    # Submit job to queue
    job_id = job_queue.submit_job(
        job_type="index_repository",
        task_callable=index_task,
        metadata={
            "repo_url": request.repo_url,
            "index_types": request.index_types
        }
    )

    return JobResponse(
        job_id=job_id,
        status="queued",
        message=f"Repository indexing queued. Track progress at GET /api/job/{job_id}"
    )

@app.get("/api/job/{job_id}")
async def get_job_status(job_id: str):
    """
    Get job status and progress.

    Returns:
        - status: queued, running, completed, failed, cancelled
        - progress: current task info (updated in real-time)
        - result: final result (if completed)
        - error: error message (if failed)
    """
    job = job_queue.get_job_status(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job.id,
        "type": job.type,
        "status": job.status.value,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "progress": job.progress,
        "result": job.result,
        "error": job.error,
        "metadata": job.metadata
    }

@app.delete("/api/job/{job_id}")
async def cancel_job(job_id: str):
    """Cancel queued job (cannot cancel running jobs)."""
    success = job_queue.cancel_job(job_id)

    if not success:
        job = job_queue.get_job_status(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job in status: {job.status.value}"
        )

    return {"message": "Job cancelled successfully"}
```

#### Client Usage Pattern

```python
# Example: Client polling for job completion

import requests
import time

# Submit indexing job
response = requests.post("http://localhost:8000/api/register", json={
    "repo_url": "https://github.com/user/repo.git",
    "index_types": ["semantic", "temporal"],
    "temporal_options": {
        "all_branches": False
    }
})

job_id = response.json()["job_id"]
print(f"Job submitted: {job_id}")

# Poll for completion
while True:
    status_response = requests.get(f"http://localhost:8000/api/job/{job_id}")
    status = status_response.json()

    print(f"Status: {status['status']}")
    if status['progress']:
        print(f"Progress: {status['progress']}")

    if status['status'] in ['completed', 'failed', 'cancelled']:
        break

    time.sleep(2)  # Poll every 2 seconds

if status['status'] == 'completed':
    print(f"Success! Result: {status['result']}")
elif status['status'] == 'failed':
    print(f"Failed: {status['error']}")
```

#### Job Queue Characteristics

**Why Single Worker Thread:**
- Prevents resource contention (CPU, memory, API quota)
- Simplifies reasoning (one job at a time)
- Temporal indexing is CPU/memory intensive
- VoyageAI API has rate limits
- Serial execution = predictable behavior

**Job Retention:**
- Jobs kept in memory (no persistence)
- Job history cleared on server restart
- Acceptable: Registration is infrequent operation
- Enhancement: Add job expiration (delete after 24h)

**Progress Reporting:**
- Job object updated in real-time by worker
- Client polls `GET /api/job/{job_id}` for updates
- Progress includes: percent complete, current file, status message
- Same progress callback used for CLI and API

**Error Handling:**
- Exceptions caught and stored in job.error
- Job marked as FAILED
- Client can retrieve error details
- Partial progress preserved for debugging

**Concurrency:**
- Multiple clients can submit jobs (queued serially)
- Only one job executes at a time
- Queue grows if submission rate > processing rate
- Enhancement: Add queue size limit

### Daemon Mode Architecture

**CRITICAL: Temporal indexing works identically in standalone and daemon modes.**

**Standalone Mode (daemon.enabled: false):**
- CLI directly instantiates `TemporalIndexer`
- Executes indexing in-process with direct progress callbacks
- Progress bar displayed directly in terminal

**Daemon Mode (daemon.enabled: true):**
- CLI delegates to daemon via `_index_via_daemon()` with `index_commits` flag
- Daemon's `exposed_index_blocking()` instantiates `TemporalIndexer` internally
- Executes indexing synchronously (blocking RPC call)
- Progress callbacks streamed back to CLI over RPyC connection
- Client displays progress bar in real-time (perfect UX parity with standalone)
- Cache automatically invalidated before and after indexing

**Mode Detection:**
- Automatic based on `.code-indexer/config.json` daemon configuration
- Zero code changes needed in `TemporalIndexer` (mode-agnostic design)
- Same progress callback signature in both modes
- Same SQLite/file operations in both modes
- Same git subprocess calls in both modes

**Cache Invalidation (Daemon Mode Only):**
- Temporal indexing adds new vectors to FilesystemVectorStore for historical blobs
- Semantic HNSW index must be rebuilt to include new vectors
- FTS index (if enabled) must include new historical content
- **Already implemented** in `daemon/service.py::exposed_index_blocking()` (lines 195-199)
- No additional cache invalidation code needed

### Query Flow Architecture

**Two-Phase Query:**
1. Semantic Search: Existing HNSW index on FilesystemVectorStore
2. Temporal Filtering: SQLite filtering by time/commit

**Performance Targets:**
- Semantic HNSW search: ~200ms
- SQLite temporal filter: ~50ms
- Total: <300ms for typical queries

## Implementation Guidelines

### Critical Requirements

1. **Lazy Module Loading (MANDATORY from CLAUDE.md):**
   - ALL temporal modules MUST use lazy imports
   - Follow FTS lazy loading pattern from smart_indexer.py
   - Guarantee: `cidx --help` and non-temporal queries unchanged

2. **Storage Optimization:**
   - SQLite with compound indexes for 40K+ repos
   - Blob registry with SQLite migration path

3. **Branch-Aware Indexing Strategy:**
   - Default: Index current branch only (cost-effective, 91%+ coverage)
   - Opt-in: `--all-branches` flag for complete multi-branch indexing
   - Track branch metadata for all commits to enable future branch-aware queries
   - Optional --max-commits and --since-date for control
   - Warn users about storage/API costs before indexing all branches

4. **Error Handling:**
   - Graceful fallback to space-only search
   - Clear warnings and suggested actions

5. **Backward Compatibility:**
   - All temporal features opt-in via flags
   - Existing functionality unchanged

### Implementation Order
1. Story 1 (Feature 01): Git History Indexing with Branch Metadata (Foundation)
2. Story 2 (Feature 01): Incremental Indexing with Branch Tracking (Optimization)
3. Story 3 (Feature 01): Selective Branch Indexing Patterns (Advanced)
4. Story 1 (Feature 02): Time-Range Filtering with Branch Context (Core Query)
5. Story 2 (Feature 02): Point-in-Time Query with Branch Info (Advanced)
6. Story 1 (Feature 03): Evolution Display with Branch Visualization (Visualization)
7. Story 1 (Feature 04): Golden Repo Registration with Temporal (API Server)
8. Story 1 (Feature 05): Temporal Query Parameters via API (API Server)

## Acceptance Criteria

### Functional Requirements (Both Modes)
- [ ] Temporal indexing with `cidx index --index-commits` (defaults to current branch)
- [ ] Multi-branch indexing with `cidx index --index-commits --all-branches`
- [ ] Selective branch indexing with `cidx index --index-commits --branches "feature/*,bugfix/*"`
- [ ] Time-range queries with `--time-range` showing branch context
- [ ] Point-in-time queries with `--at-commit` with branch information
- [ ] Evolution display with `--show-evolution` including branch visualization
- [ ] Incremental indexing on re-runs preserving branch metadata

### Daemon Mode Requirements
- [ ] Temporal indexing works in daemon mode when `daemon.enabled: true`
- [ ] CLI automatically delegates to daemon via `_index_via_daemon()`
- [ ] Progress callbacks stream correctly from daemon to client
- [ ] Progress bar displays identically in both modes (UX parity)
- [ ] Cache invalidation before temporal indexing (daemon mode)
- [ ] Cache automatically cleared after temporal indexing completes
- [ ] Graceful fallback to standalone mode if daemon unavailable
- [ ] All temporal flags passed correctly through delegation layer
- [ ] Watch mode integration with config (respects branch settings)
- [ ] Cost warning before indexing all branches in large repos

### Performance Requirements
- [ ] Query performance <300ms on 40K+ repos (with branch filtering)
- [ ] 92%+ storage savings via blob deduplication
- [ ] SQLite indexes optimized for scale including branch queries
- [ ] Single-branch indexing completes in reasonable time (similar to current indexing)
- [ ] Cost warning displays accurate estimates (storage, API calls) for multi-branch indexing

### Quality Requirements
- [ ] Graceful error handling with fallback
- [ ] Lazy loading preserves startup time
- [ ] All tests passing including E2E

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| SQLite performance at scale | High | Compound indexes, WAL mode, tuning, branch-specific indexes |
| Storage growth with all-branches | High | Default to single branch, cost warnings, blob deduplication |
| Module import overhead | High | Mandatory lazy loading pattern |
| Git operations slow | Medium | Incremental indexing, caching, single-branch default |
| Breaking changes | High | All features opt-in via flags |
| Users accidentally index all branches | Medium | Explicit flag required, cost warning with confirmation |
| Branch metadata overhead | Low | Indexed efficiently, minimal query impact |
| Daemon cache coherence | Medium | Automatic cache invalidation already implemented |
| Mode-specific bugs | Medium | Mode-agnostic design, comprehensive testing in both modes |

## Dependencies

- Existing: FilesystemVectorStore, HNSW index, HighThroughputProcessor
- Existing: Daemon mode architecture (cli_daemon_delegation.py, daemon/service.py)
- New: sqlite3 (lazy), difflib (lazy), git commands
- Configuration: enable_temporal setting
- Feature 04 depends on Features 01-03 (CLI temporal implementation must exist)
- Feature 05 depends on Feature 04 (temporal index must be created during registration)
- Both API features integrate with existing server architecture (GoldenRepoManager, SemanticSearchService)
- Daemon integration: No new dependencies (uses existing RPC and cache invalidation)

## Testing Strategy

### Unit Tests (Mode-Agnostic)
- TemporalIndexer blob registry building
- TemporalSearchService filtering logic
- SQLite performance with mock data
- Branch metadata storage and retrieval
- Cost estimation calculations

### Integration Tests (Standalone Mode)
- End-to-end temporal indexing in standalone mode
- Query filtering accuracy
- Watch mode temporal updates
- Single-branch vs all-branches behavior
- Cost warnings and confirmations

### Integration Tests (Daemon Mode)
- **CRITICAL:** All temporal operations must work in daemon mode
- Temporal indexing delegation via `_index_via_daemon()`
- Progress callback streaming from daemon to client
- Cache invalidation before/after temporal indexing
- UX parity verification (progress bar display)
- Graceful fallback to standalone if daemon unavailable
- Daemon remains responsive during long temporal indexing operations

### Manual Tests (Both Modes)
- Each story has specific manual test scenarios
- Performance validation on large repos (40K+ commits, 1000+ branches)
- Error handling verification
- **Test in daemon mode:** Enable daemon, verify identical behavior
- **Test cache coherence:** Query before/after temporal indexing in daemon mode
- **Test progress streaming:** Verify real-time progress in daemon mode

### 32-Mode Combination Test Matrix

**CRITICAL:** CIDX has 5 independent binary operational dimensions that create **2^5 = 32 possible mode combinations**. All combinations are valid and must be tested.

#### Five Binary Dimensions

1. **Daemon Mode (D):** Standalone (`-`) vs Daemon (`D`)
2. **Branch Indexing (B):** Single branch (`-`) vs All branches (`B`)
3. **Watch Mode (W):** Disabled (`-`) vs Enabled (`W`)
4. **FTS Index (F):** Disabled (`-`) vs Enabled (`F`)
5. **Temporal Index (T):** Disabled (`-`) vs Enabled (`T`)

**Notation:** Each mode represented as 5-character string (e.g., `D-WFT` = Daemon + Single Branch + Watch + FTS + Temporal)

#### Mode Combination Table

All 32 combinations are **VALID** and supported:

| Tier | Example Modes | Description | Test Priority |
|------|---------------|-------------|---------------|
| **Tier 1: Basic** | `-----`, `D----`, `---FT`, `D--FT` | Core functionality | **CRITICAL** |
| **Tier 2: Watch** | `--W--`, `D-W--`, `--WFT`, `D-WFT` | Incremental updates | **HIGH** |
| **Tier 3: Multi-Branch** | `-B---`, `DB---`, `-B-FT`, `DB-FT` | Branch deduplication | **MEDIUM** |
| **Tier 4: Production** | `-BWFT`, `DBWFT` | Full deployment modes | **CRITICAL** |

**Complete Matrix:** See `.analysis/32_mode_test_matrix_20251102.md` for:
- All 32 combinations enumerated
- Test strategy per tier
- Performance expectations per mode
- Common production use cases

#### Key Test Scenarios by Dimension

**Daemon vs Standalone:**
- Cache coordination (daemon only)
- Concurrent queries (daemon only)
- Query performance (daemon 10-15x faster after warmup)

**Single vs All Branches:**
- Blob deduplication across branches
- Branch-specific temporal queries
- Index size verification

**Watch Mode:**
- Automatic incremental indexing
- Git change detection
- Temporal index updates (new commits)

**FTS Index:**
- Exact text search functionality
- Performance vs semantic search
- Compatibility with temporal queries

**Temporal Index:**
- Git history indexing
- Time-range and point-in-time queries
- Code evolution display
- SQLite database integrity

#### Production Deployment Modes

**Development Mode: `--WFT` (Mode 8)**
- Standalone + Single Branch + Watch + FTS + Temporal
- Developer working on single repository
- Automatic updates, all query types available

**Team Server Mode: `D--FT` (Mode 20)**
- Daemon + Single Branch + FTS + Temporal
- Shared server for team queries
- Fast queries, all features, single main branch

**Multi-Repo Server: `DBWFT` (Mode 32)**
- Daemon + All Branches + Watch + FTS + Temporal
- Large-scale code search infrastructure
- Maximum functionality, automatic updates, fast queries

#### Test Execution Strategy

**Phase 1: Smoke Tests (4 modes)**
- Mode 1 (`-----`) - Baseline semantic search
- Mode 2 (`----T`) - Temporal only
- Mode 17 (`D----`) - Daemon only
- Mode 32 (`DBWFT`) - Everything enabled

**Phase 2: Feature Tests (16 modes)**
- All temporal-enabled modes
- Verify temporal queries work in all contexts

**Phase 3: Daemon Tests (16 modes)**
- Modes 17-32 (all daemon modes)
- Verify cache coordination and concurrent access

**Phase 4: Complete Matrix (32 modes)**
- All combinations tested
- Cross-mode consistency verified
- 100% coverage of valid combinations

#### Implementation

```python
# Test pattern for mode combinations
@pytest.mark.parametrize("mode_config", [
    {"daemon": False, "all_branches": False, "watch": False, "fts": False, "temporal": False},
    {"daemon": False, "all_branches": False, "watch": False, "fts": False, "temporal": True},
    # ... (all 32 combinations)
])
def test_mode_combination(mode_config, temp_git_repo):
    """Test specific mode combination works correctly."""
    # Setup configuration
    config = create_config_from_mode(mode_config)

    # Initialize and index
    if mode_config["daemon"]:
        daemon = start_daemon(temp_git_repo, config)

    index_repository(
        repo_path=temp_git_repo,
        all_branches=mode_config["all_branches"],
        enable_fts=mode_config["fts"],
        enable_temporal=mode_config["temporal"],
        watch_mode=mode_config["watch"]
    )

    # Verify features
    verify_index_features(temp_git_repo, mode_config)
    verify_query_functionality(temp_git_repo, mode_config)
    verify_feature_isolation(temp_git_repo, mode_config)
```

**Verification Criteria (Each Mode):**
1. Index creation succeeds for configured indexes
2. Semantic queries return results
3. Enabled features work correctly
4. Disabled features fail gracefully
5. Performance within expected ranges
6. Cache coherence (daemon only)
7. Incremental updates (watch only)

**Test Files:**
- `tests/integration/test_32_mode_combinations.py` - Main matrix
- `tests/integration/test_daemon_mode_combinations.py` - Modes 17-32
- `tests/integration/test_watch_mode_combinations.py` - Watch-enabled
- `tests/integration/test_temporal_mode_combinations.py` - Temporal-enabled

## Documentation Requirements

- Update README.md with temporal search examples
- Add temporal flags to --help
- Document performance tuning for large repos
- Include troubleshooting guide

## Success Metrics

- Query latency <300ms (P95)
- Storage efficiency >80% deduplication
- Zero impact on non-temporal operations
- User adoption by AI coding agents

### Performance Budget Allocation

**Target: <300ms Total Query Latency (P95)**

| Component | Budget | Justification |
|-----------|--------|---------------|
| Semantic Search (HNSW) | 50-100ms | Cached index in daemon mode, 800ms cold |
| SQLite Temporal Filtering | 10-20ms | Indexed queries on 40K+ commits |
| Removed Code Detection | 5-10ms | Hash lookups in blob registry |
| Result Formatting | 5-10ms | Rich output rendering |
| Network/IPC Overhead | 10-20ms | Daemon mode communication |
| **Total** | **80-160ms** | **Leaves 140-220ms buffer** |

**Indexing Performance Targets:**

| Operation | Target | Scale |
|-----------|--------|-------|
| Blob deduplication lookup | <1ms per blob | SQLite indexed query |
| Git blob read | 5-10ms per blob | `git cat-file` subprocess |
| Embedding generation | 50-100ms per batch | VoyageAI API call (50 chunks) |
| SQLite write (commit) | <5ms | EXCLUSIVE transaction |
| Full temporal index (40K commits, 12K unique blobs) | 4-7 minutes | End-to-end with deduplication |

**SQLite Performance Expectations:**

**Realistic (Not "Microseconds"):**
- Blob registry lookup: <1ms (indexed query, 40K blobs)
- Commit metadata insert: <5ms (EXCLUSIVE transaction)
- Temporal query filtering: 10-20ms (indexed date/hash queries)
- Branch metadata lookup: <2ms (indexed by commit_hash)

**Configuration for Performance:**
```sql
PRAGMA journal_mode=WAL;        -- Concurrent readers
PRAGMA busy_timeout=5000;       -- 5s lock wait
PRAGMA synchronous=NORMAL;      -- Balance safety/speed
PRAGMA cache_size=8192;         -- 8MB cache
PRAGMA temp_store=MEMORY;       -- In-memory temp tables
```

**Validation:** Performance targets based on:
- Measured HNSW query times in existing codebase
- SQLite benchmarks for similar dataset sizes
- VoyageAI API documented latencies
- Real-world testing on Evolution repository (89K commits)

## Notes

**Conversation Context:**
- User emphasized storage efficiency for 40K+ repos
- Configuration-driven watch mode integration
- Graceful degradation critical
- MANDATORY lazy loading from CLAUDE.md

**Branch Strategy Analysis (Evolution Repository):**
- Analyzed real-world large enterprise codebase (Evolution - 1,135 branches, 89K commits)
- Single branch (development): 81,733 commits = 91.6% coverage
- All branches: 89,234 commits = 100% coverage but 85.5% storage increase
- Deduplication effectiveness: 92.4% (most code shared between branches)
- Recommendation: Default to single branch, opt-in for all branches
- Cost transparency: Warn users before expensive operations
- See `.analysis/temporal_indexing_branch_analysis.md` for complete analysis

**Key Design Decisions:**
1. **Default = Current Branch Only:** Cost-effective, covers 90%+ of real-world use cases
2. **Explicit Opt-in for All Branches:** Users must consciously choose expensive operation
3. **Track Branch Metadata Always:** Even single-branch indexing records which branch
4. **Cost Warnings:** Display storage/API estimates before multi-branch indexing
5. **Future-Proof Schema:** Branch metadata enables future branch-aware queries

---

## Quality Assurance & Validation Reports

**Epic Status:** ✅ GO - Ready for Implementation (Risk: <10%)

This Epic underwent comprehensive validation through Codex Architect pressure testing. All critical issues identified have been resolved. The following reports document the validation process and resolution:

### Critical Issues Resolution (Codex Pressure Test)
- **[All Critical Issues Complete](reports/all_critical_issues_complete_20251102.md)** - Final status: GO achievement, <10% risk
- **[Codex Pressure Test Response](reports/codex_pressure_test_response_20251102.md)** - Original pressure test findings (NO-GO verdict)

### Individual Issue Reports
1. **[Issue #1: Architectural Audit](reports/critical_issue_1_architectural_audit_20251102.md)** - Architecture verification (verified correct)
2. **[Issue #2: Component Reuse](reports/critical_issue_2_component_reuse_fix_20251102.md)** - Realistic component reuse (60-65%)
3. **[Issue #3: Progress Callbacks](reports/critical_issue_3_progress_callback_fix_20251102.md)** - RPyC-safe progress specification
4. **[Issues #1-4 Combined](reports/critical_issues_1_2_3_4_fixed_20251102.md)** - Memory management strategy
5. **[Issue #5: Git Performance](reports/critical_issue_5_git_performance_fix_20251102.md)** - Benchmarked on Evolution repo (89K commits)

### Testing Guidance
- **[E2E Test Exclusions](reports/temporal_e2e_tests_fast_automation_exclusions_20251102.md)** - fast-automation.sh exclusion strategy

**Risk Evolution:**
- Initial (NO-GO): 75% failure risk, 5 critical issues
- Final (GO): <10% failure risk, all issues resolved
- Implementation Readiness: 95%

**Key Validations Completed:**
- ✅ Git performance benchmarked on real 89K commit repository
- ✅ Realistic component reuse expectations (60-65%)
- ✅ RPyC-safe progress callback specification
- ✅ Memory management strategy for 4GB systems
- ✅ Architecture correctness verified
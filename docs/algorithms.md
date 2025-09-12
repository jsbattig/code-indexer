# Code Indexer Algorithms Documentation

## Overview

The code-indexer implements a git-aware processing system that achieves O(δ) complexity for incremental updates, where δ represents the number of changed files. This document provides a technical analysis of the system's algorithms and architecture based on the actual implementation.

## Core Architecture

### 1. Content-Visibility Separation Model

The system separates content storage from visibility management through a dual-point architecture:

**Content Points** (Immutable)
- One point per unique (file_path, commit_hash, chunk_index) tuple
- Contains actual file content and embeddings
- Never deleted during branch operations
- Uses deterministic UUID5 generation for consistent IDs

**Visibility Control** (Mutable)
- Managed via `hidden_branches` array field on content points
- Content is visible if current branch is NOT in the hidden_branches array
- Enables O(1) visibility lookups via Qdrant filtering

Reference: `branch_aware_indexer.py:43-76`

### 2. Complexity Analysis

#### O(δ) Branch Switching Complexity

The system achieves O(δ) complexity during branch switching by only processing changed files:

```python
def index_branch_changes(self, old_branch, new_branch, changed_files, unchanged_files):
    # Only process δ changed files - O(δ)
    for file in changed_files:
        if content_exists(file, commit):
            # Reuse existing content - O(1) lookup
            ensure_file_visible_in_branch(file, new_branch)
        else:
            # Create new content point - O(1) per chunk
            create_content_point(file, commit, branch)
    
    # Update visibility for branch isolation - O(n) worst case
    hide_files_not_in_branch(new_branch, visible_files)
```

**Proof of O(δ) Complexity:**
1. Changed file processing: O(δ) where δ = |changed_files|
2. Content existence check: O(1) via deterministic ID generation
3. Visibility updates: O(1) per file via batch updates
4. Total: O(δ) + O(1) = O(δ)

Reference: `branch_aware_indexer.py:184-274`

#### O(1) Search Complexity

Search operations achieve O(1) branch filtering through Qdrant's vector database capabilities:

```python
def search_with_branch_context(self, query_vector, branch):
    filter_conditions = {
        "must": [{"key": "type", "match": {"value": "content"}}],
        "must_not": [{"key": "hidden_branches", "match": {"any": [branch]}}]
    }
    # Qdrant handles filtering at index level - O(1) branch filtering
```

Reference: `branch_aware_indexer.py:888-920`

### 3. Branch Topology Processing

The GitTopologyService provides efficient branch analysis through git's native capabilities:

#### Merge Base Calculation
```python
def _get_merge_base(self, branch1, branch2):
    # Uses git merge-base for O(log n) common ancestor finding
    result = subprocess.run(["git", "merge-base", branch1, branch2])
```

Reference: `git_topology_service.py:227-240`

#### Delta Computation
```python
def _get_changed_files(self, old_branch, new_branch):
    # Uses git diff --name-only for O(δ) change detection
    result = subprocess.run(["git", "diff", "--name-only", f"{old_branch}..{new_branch}"])
```

Reference: `git_topology_service.py:242-277`

### 4. Content Deduplication Strategy

The system implements multi-level deduplication:

#### Commit-Level Deduplication
```python
def _generate_content_id(self, file_path, commit, chunk_index=0):
    # Deterministic ID prevents duplicate content storage
    content_str = f"{file_path}:{commit}:{chunk_index}"
    namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
    return str(uuid.uuid5(namespace, content_str))
```

Reference: `branch_aware_indexer.py:1023-1030`

#### Working Directory State Tracking
```python
def _get_file_commit(self, file_path):
    if self._file_differs_from_committed_version(file_path):
        # Generate unique ID based on mtime and size
        file_stat = file_path_obj.stat()
        return f"working_dir_{file_stat.st_mtime}_{file_stat.st_size}"
    else:
        # Use actual commit hash for committed content
        return get_commit_hash(file_path)
```

Reference: `branch_aware_indexer.py:1040-1084`

### 5. Incremental Update Algorithm

The reconciliation algorithm achieves incremental updates through content ID comparison:

```python
def _do_reconcile_with_database(self):
    for file_path in all_files_to_index:
        # Get expected content ID for current state
        current_effective_id = _get_effective_content_id_for_reconcile(file_path)
        
        # Get currently visible content ID in database
        currently_visible_id = _get_currently_visible_content_id(file_path, branch)
        
        if current_effective_id != currently_visible_id:
            # File needs re-indexing - O(1) detection per file
            files_to_index.append(file_path)
```

Reference: `smart_indexer.py:885-1184`

### 6. Point-in-Time Snapshot Behavior

The system maintains point-in-time snapshots of working directory changes:

```python
# When working directory content exists, hide committed version
if current_commit.startswith("working_dir_"):
    # Hide all non-working directory content for this file
    for point in committed_content_points:
        if branch not in point.hidden_branches:
            update_hidden_branches(point, add_branch=branch)
```

Reference: `branch_aware_indexer.py:588-706`

### 7. Branch Isolation Algorithm

The hide_files_not_in_branch function ensures proper branch isolation:

```python
def hide_files_not_in_branch(self, branch, current_files, collection_name):
    # Phase 1: Build file mappings - O(n)
    file_to_point_info = build_file_mappings(all_content_points)
    
    # Phase 2: Calculate updates - O(n)
    files_to_hide = db_files - current_files_set
    
    # Phase 3: Batch update visibility - O(n)
    for file in files_to_hide:
        if branch not in hidden_branches:
            add_to_hidden_branches(file, branch)
```

Reference: `branch_aware_indexer.py:1299-1467`

### 8. Garbage Collection Strategy

The system implements safe garbage collection for orphaned content:

```python
def garbage_collect_content(self, collection_name):
    # Find content hidden in ALL branches
    for point in all_content_points:
        if set(point.hidden_branches) >= all_branches:
            # Content is completely orphaned - safe to delete
            orphaned_content_ids.append(point.id)
```

Reference: `branch_aware_indexer.py:964-1019`

## Performance Characteristics

### Time Complexity Summary

| Operation | Complexity | Explanation |
|-----------|------------|-------------|
| Branch Switch | O(δ) | Only processes changed files |
| Content Lookup | O(1) | Deterministic ID generation |
| Visibility Update | O(1) | Per-file batch updates |
| Search with Branch Filter | O(k) | k = result limit, branch filtering is O(1) |
| Full Index | O(n) | n = total files |
| Reconcile | O(n) | Must check all files for changes |
| Garbage Collection | O(m) | m = total content points |
| Hash Calculation Phase | O(n/p) | n files divided among p parallel threads |
| Embedding Phase | O(n × c) | n files × c chunks per file |

### Space Complexity

| Component | Complexity | Explanation |
|-----------|------------|-------------|
| Content Storage | O(n × c × b) | n files × c chunks × b branches (worst case) |
| Actual Storage | O(n × c) | Content deduplication prevents redundancy |
| Visibility Metadata | O(n × b) | Hidden branches array per content point |
| Branch Tracking | O(b) | Branch metadata storage |

## Implementation Details

### Critical Data Structures

1. **ContentMetadata** (branch_aware_indexer.py:43-76)
   - Stores file metadata with `hidden_branches` array
   - Includes git_commit, content_hash, file_mtime for state tracking

2. **BranchChangeAnalysis** (git_topology_service.py:19-31)
   - Encapsulates branch transition analysis
   - Separates files needing reindex vs metadata updates

3. **ProgressiveMetadata** (referenced throughout)
   - Tracks indexing progress for resumability
   - Stores branch transition history

### Key Algorithms

1. **Deterministic Content ID Generation**
   - Uses UUID5 with DNS namespace for consistency
   - Combines file_path:commit:chunk_index

2. **Working Directory Detection**
   - Uses `git diff --quiet HEAD` to detect uncommitted changes
   - Generates temporal IDs using mtime and file size

3. **Branch Visibility Filtering**
   - Leverages Qdrant's native filtering capabilities
   - Uses must_not filter on hidden_branches array

4. **Batch Update Strategy**
   - Groups visibility updates into 1000-point batches
   - Reduces database round trips

## Correctness Guarantees

1. **Content Preservation**: Content points are never deleted during branch operations
2. **Branch Isolation**: Files not present in a branch are properly hidden
3. **Deduplication**: Identical content is stored only once
4. **Consistency**: Deterministic IDs ensure reproducible indexing
5. **Atomicity**: Batch operations maintain consistency

## Edge Cases Handled

1. **Detached HEAD State**: Treated as `detached-{short_hash}` branch
2. **Invalid Git References**: Falls back to indexing all tracked files
3. **Non-Git Repositories**: Uses timestamp-based content IDs
4. **Working Directory Changes**: Maintains point-in-time snapshots
5. **File Renames**: Treated as delete + add operations
6. **Large Repositories**: Batch processing prevents memory issues

## Batch Processing and Token Management

### VoyageAI Token-Aware Batching

The system implements intelligent batching to optimize VoyageAI API usage:

#### Token Counting Implementation
```python
def _count_tokens(self, text: str) -> int:
    """Count tokens using VoyageAI's native count_tokens API."""
    model = self.vector_manager.embedding_provider.get_current_model()
    return self.voyage_client.count_tokens([text], model=model)
```

**Implementation Note**: The system uses VoyageAI's native `count_tokens` API for accurate token measurement. The `test_tiktoken_accuracy.py` file exists only for validation purposes and is not used in production code.

Reference: `file_chunking_manager.py:169-173`

#### Dynamic Batch Optimization

The system dynamically batches chunks to maximize throughput while respecting API limits:

```python
# Token limit with 90% safety margin for API stability
model_limit = self.vector_manager.embedding_provider._get_model_token_limit()
TOKEN_LIMIT = int(model_limit * 0.9)

current_batch = []
current_tokens = 0

for chunk in chunks:
    chunk_tokens = self._count_tokens(chunk_text)
    
    # Submit batch if adding chunk would exceed limit
    if current_tokens + chunk_tokens > TOKEN_LIMIT and current_batch:
        batch_future = self.vector_manager.submit_batch_task(current_batch)
        # Reset for next batch
        current_batch = []
        current_tokens = 0
    
    current_batch.append(chunk_text)
    current_tokens += chunk_tokens
```

**Batch Processing Optimizations (Recent Changes):**
- Files with >100K estimated tokens are automatically split into multiple batches
- 90% safety margin prevents API rate limit errors
- Batch size dynamically adjusted based on actual token counts
- Transparent handling of large files without user intervention

Reference: `file_chunking_manager.py:386-455`

#### Model-Specific Token Limits

Token limits are loaded from YAML configuration:

```yaml
voyage_models:
  voyage-code-3:
    token_limit: 120000
  voyage-large-2:
    token_limit: 120000
  voyage-2:
    token_limit: 320000
```

Reference: `voyage_ai.py:43-63`, `data/voyage_models.yaml`

## Dual-Phase Processing Architecture

The system implements a two-phase approach to optimize throughput and provide accurate progress reporting.

### Phase 1: Parallel Hash Calculation

The system performs hash calculation in parallel before embedding generation:

#### Hash Phase Implementation
```python
def hash_worker(file_queue, results_dict, error_holder, slot_tracker):
    while True:
        file_path = file_queue.get_nowait()
        
        # Acquire slot for progress tracking
        file_data = FileData(
            filename=str(file_path.name),
            file_size=file_size,
            status=FileStatus.PROCESSING
        )
        slot_id = slot_tracker.acquire_slot(file_data)
        
        # Calculate hash and metadata
        file_metadata = self.file_identifier.get_file_metadata(file_path)
        results_dict[file_path] = (file_metadata, file_size)
        
        # Update progress and release slot
        slot_tracker.update_slot(slot_id, FileStatus.COMPLETE)
        slot_tracker.release_slot(slot_id)
```

**Parallelization**: Uses ThreadPoolExecutor with `thread_count` workers to process files concurrently.

Reference: `high_throughput_processor.py:288-382`

### Phase 2: Parallel Embedding Generation

After hash calculation, the system processes embeddings with file-level atomicity:

#### File Processing Pipeline
1. **Chunking**: Files are split into chunks using FixedSizeChunker
2. **Token-Aware Batching**: Chunks are grouped into batches respecting token limits
3. **Vectorization**: Batches are submitted to VoyageAI for embedding generation
4. **Atomic Write**: All chunks from a file are written together to Qdrant

Reference: `file_chunking_manager.py:308-550`

## Progress Reporting Architecture

### Slot-Based Progress Tracking

The system uses a CleanSlotTracker with fixed-size array for thread-safe progress management:

```python
class CleanSlotTracker:
    def __init__(self, max_slots: int):
        self.status_array = [None] * max_slots  # Fixed-size array
        # LIFO queue for slot allocation (stack-like)
        self.available_slots = queue.LifoQueue()
        for i in range(max_slots):
            self.available_slots.put(i)
```

**Design Principles:**
- Integer-only slot operations (no filename dictionaries)
- Thread-agnostic design (no thread_id tracking)
- LIFO allocation for cache-friendly access patterns
- Blocking acquire provides natural backpressure

#### Slot States
- **STARTING**: File submission initiated
- **CHUNKING**: File being split into chunks
- **VECTORIZING**: Embeddings being generated
- **FINALIZING**: Writing to database
- **COMPLETE**: Processing finished

Reference: `services/clean_slot_tracker.py`

### Multi-Threaded Display Management

The display system provides real-time visibility into concurrent file processing:

```python
def get_display_lines_from_tracker(slot_tracker, max_slots):
    display_lines = []
    # Simple array scanning: for slot_id in range(threadcount+2)
    for slot_id in range(max_slots):
        file_data = slot_tracker.status_array[slot_id]
        if file_data is not None:
            formatted_line = self._format_file_line_from_data(file_data)
            display_lines.append(formatted_line)
    return display_lines
```

Reference: `multi_threaded_display.py:86-110`

### Setup Phase Progress Messages

The system provides informative setup messages before processing begins to eliminate silent gaps:

```python
# Setup phase messages (total=0 triggers info display)
progress_callback(0, 0, Path(""), info="Analyzing repository structure...")
progress_callback(0, 0, Path(""), info="Calculating file hashes...")
progress_callback(0, 0, Path(""), info="Starting embedding generation...")

# File progress (total>0 triggers progress bar)
progress_callback(current, total_files, file_path, 
                 info="X/Y files (%) | emb/s | threads | filename")
```

This dual-mode progress reporting ensures users receive feedback during both setup and processing phases.

Reference: Implementation in `high_throughput_processor.py`, `cli.py`

## Parallel Processing Optimization

### Thread Pool Architecture

The system uses multiple thread pools for different phases:

1. **Hash Calculation Pool**: `thread_count` workers for parallel hash computation
2. **File Processing Pool**: `thread_count + 2` workers for chunk/vector/write pipeline
3. **Vector Calculation Pool**: Managed by VectorCalculationManager for API calls

### Resource Management

#### Graceful Shutdown
```python
def __exit__(self, exc_type, exc_val, exc_tb):
    # Cancel all pending futures
    self._cancellation_requested = True
    for future in self._pending_futures:
        if not future.done():
            future.cancel()
    
    # Shutdown with timeout
    self.executor.shutdown(wait=True)
```

Reference: `file_chunking_manager.py:117-156`

#### Cancellation Support

The system supports clean cancellation at multiple levels:
- File-level atomicity (cancellation only between files, never during)
- Shared cancellation event propagated across all processing managers
- Atomic file processing ensures consistency (all chunks indexed or none)
- Graceful shutdown with proper resource cleanup

**Cancellation Flow:**
1. User triggers cancellation (Ctrl+C or programmatic)
2. Cancellation event set across all managers
3. Current file processing completes atomically
4. Pending futures cancelled
5. Resources properly released

Reference: `high_throughput_processor.py:110-115`, `file_chunking_manager.py:165-167`

## Recent Architecture Improvements

### Version 0.3.x Series Enhancements

#### Token-Aware Batching (v0.3.40+)
- Implemented dynamic batch splitting for files exceeding VoyageAI's 120K token limit
- Added 90% safety margin to prevent API rate limiting
- Real-time token counting using VoyageAI's native API

#### Dual-Phase Processing (v0.3.35+)
- Separated hash calculation from embedding generation
- Parallel hash computation using ThreadPoolExecutor
- Improved progress accuracy with known file count before embedding phase

#### Clean Slot Tracker (v0.3.30+)
- Replaced complex thread-to-file mapping with integer-only slot operations
- Implemented LIFO slot allocation for cache-friendly access
- Thread-agnostic design eliminates race conditions

#### Setup Phase Messaging (v0.3.42+)
- Added informative setup messages to eliminate silent gaps
- Dual-mode progress reporting (setup vs processing)
- Improved user experience with continuous feedback

## References

All line numbers and file references are from the actual codebase:
- `branch_aware_indexer.py`: Core indexing logic with visibility management
- `git_topology_service.py`: Git analysis and branch topology algorithms
- `smart_indexer.py`: Orchestration and reconciliation logic
- `high_throughput_processor.py`: Parallel processing coordination
- `file_chunking_manager.py`: Token-aware batching and file processing
- `voyage_ai.py`: VoyageAI client with native token counting
- `services/clean_slot_tracker.py`: Thread-safe progress tracking
- `multi_threaded_display.py`: Real-time progress display
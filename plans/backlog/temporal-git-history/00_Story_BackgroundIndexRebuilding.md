# Story 0: Background Index Rebuilding with Atomic Swap

## Story Description

**As a** developer using cidx in daemon mode or concurrent processes
**I want** index rebuilds to happen in the background without blocking queries
**So that** my search operations remain fast even while indexes are being updated

**Context:**
- Current synchronous rebuilds block queries for 5-10 seconds
- Applies to ALL index types: HNSW, ID indexes, FTS
- Must support both daemon mode (same process) and standalone mode (concurrent processes)
- File locks required for cross-process coordination

**Epic Position:** This is Story 0 - the **prerequisite foundation** for the Temporal Git History Epic. It must be implemented BEFORE Story 1 (Git History Indexing) to ensure proper index locking and atomic updates.

---

## ⚠️ CRITICAL IMPLEMENTATION INSTRUCTION

**IMPLEMENT FIRST - STOP FOR REVIEW:** When asked to "start implementing the Temporal Epic," implement ONLY this Story 0 and then STOP. Do not proceed to Story 1 without explicit approval.

**Implementation Checkpoint Workflow:**
1. Implement Story 0 completely (TDD workflow with all tests passing)
2. Run code review and manual testing
3. Commit changes
4. **STOP and wait for user review/approval**
5. Only proceed to Story 1 after user explicitly approves

**Rationale:** This story establishes the foundational locking mechanism for all index updates. The temporal indexing stories (1-7) depend on this infrastructure. User must review and validate the atomic swap and locking implementation before building temporal features on top of it.

## Acceptance Criteria

- [x] HNSW index rebuilds happen in background with atomic file swap
- [x] ID index rebuilds use same background+swap pattern
- [x] FTS index rebuilds use same background+swap pattern
- [x] Queries continue using old indexes during rebuild (stale reads)
- [x] Atomic swap happens in <2ms with exclusive lock
- [x] Entire rebuild process holds exclusive lock (serializes rebuilds)
- [x] File locks work across daemon and standalone modes
- [x] No race conditions between concurrent rebuild requests
- [x] Proper cleanup of .tmp files on crashes
- [x] Performance: Queries unaffected by ongoing rebuilds
- [x] **Cache invalidation:** In-memory index caches detect version changes after atomic swap
- [x] **Version tracking:** Metadata file changes trigger automatic cache reload
- [x] **mmap safety:** Cached mmap'd indexes properly invalidated after file swap

## Implementation Overview

### Applies To

This story provides a **unified background rebuild strategy** for ALL index types:

**Vector Search Indexes (typically rebuilt together):**
1. **HNSW Index** (`hnsw_index.bin`) - hnswlib binary format, uses mmap, ~500MB for 40K vectors
2. **ID Index** (`id_index.json`) - JSON file mapping vector IDs to internal labels, <1MB typically

**Full-Text Search Index (rebuilt independently):**
3. **FTS Index** (Tantivy directory) - Full-text search index, uses mmap, size varies by content

**Note:** While HNSW and ID index CAN be rebuilt separately using the same BackgroundIndexRebuilder pattern, they are typically rebuilt together since ID mappings must match HNSW internal labels.

### Key Architectural Decision

**Lock entire rebuild duration** (not just atomic swap):
- Simple: Only 2 states (locked/unlocked)
- Robust: No race conditions
- Testable: Easy to reason about

**Why this matters:** User's critical insight - "it will be extremely complicated to manage and bug prone" if we try to lock only during swap.

### File Structure

```
.code-indexer/index/{collection_name}/
├── hnsw_index.bin              # HNSW binary (mmap'd by hnswlib)
├── hnsw_index.bin.tmp          # Temp during rebuild (consumed by atomic swap)
├── id_index.json               # ID mapping (read into memory)
├── id_index.json.tmp           # Temp during rebuild
├── collection_meta.json        # Metadata (version signal)
├── collection_meta.json.tmp    # Temp during rebuild
├── tantivy_fts/                # FTS index directory (mmap'd by Tantivy)
├── tantivy_fts.tmp/            # Temp during rebuild
└── .index_rebuild.lock         # File lock for serialization
```

### When To Use Background Rebuild

**Use background rebuild when:**
- Daemon mode with active queries
- Watch mode detecting file changes
- Temporal indexing adding thousands of blobs
- Any scenario where blocking queries is unacceptable

**Use synchronous rebuild when:**
- Initial indexing (no queries yet)
- Forced rebuild with `--force` flag (user expects blocking)
- Small repos where rebuild takes <1 second

### Required Imports

```python
import os
import json
import fcntl
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Callable, Dict, Tuple, Any
from datetime import datetime
import numpy as np
import hnswlib
```

## Technical Implementation

### File Locking Strategy (Cross-Process)

```python
import fcntl
from pathlib import Path
from typing import Optional, Callable
import threading

class BackgroundIndexRebuilder:
    """
    Unified background index rebuilding with atomic swap for all index types.

    Uses file locks to support:
    - Daemon mode: Multiple threads in same process
    - Standalone mode: Multiple processes
    - Mixed: Daemon + concurrent standalone cidx index calls

    Locking Strategy:
    - EXCLUSIVE lock for ENTIRE rebuild (serializes all rebuild workers)
    - Prevents concurrent rebuilds from same or different processes
    - Queries DON'T need locks (read from file, OS-level atomic rename)
    """

    def __init__(self, index_dir: Path):
        self.index_dir = index_dir
        self.rebuild_lock_file = index_dir / ".index_rebuild.lock"
        self.rebuild_lock_file.touch(exist_ok=True)

    def rebuild_background(
        self,
        index_type: str,  # "hnsw", "id", "fts"
        rebuild_callback: Callable,
        completion_callback: Optional[Callable] = None
    ) -> threading.Thread:
        """
        Rebuild index in background with atomic swap.

        Args:
            index_type: Type of index ("hnsw", "id", "fts")
            rebuild_callback: Function that builds new index and returns temp file paths
            completion_callback: Called on success/failure

        Returns:
            Background thread handle

        Locking:
            Acquires EXCLUSIVE lock for entire rebuild duration (5-10s)
            Serializes all rebuild workers (same or different processes)
            Queries never blocked (no lock needed for reads)
        """

        def _rebuild_worker():
            logger = logging.getLogger(__name__)

            try:
                # === ACQUIRE EXCLUSIVE LOCK FOR ENTIRE REBUILD ===
                # This serializes ALL rebuild operations across all processes
                with open(self.rebuild_lock_file, "r") as lock_f:
                    # EXCLUSIVE lock - blocks other rebuild workers
                    # Does NOT block queries (queries don't take locks)
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)

                    logger.info(f"{index_type} rebuild: Lock acquired, building...")

                    try:
                        # Step 0: Cleanup orphaned .tmp files from previous crashes
                        # This is safe because we hold exclusive lock
                        self._cleanup_temp_files()

                        # Step 1-4: Build index (with lock held)
                        # This is 99% of rebuild time (5-10 seconds)
                        temp_files = rebuild_callback()

                        if not temp_files:
                            logger.error(f"{index_type} rebuild: Callback returned no files")
                            if completion_callback:
                                completion_callback(success=False, error="No temp files")
                            return

                        # Step 5: Atomic swap (still with lock held)
                        # This is <2ms - just rename operations
                        logger.info(f"{index_type} rebuild: Swapping files atomically...")

                        for temp_path, final_path in temp_files.items():
                            # POSIX rename is atomic - old file instantly replaced
                            # OLD FILE BEHAVIOR:
                            # - Old inode is automatically unlinked by rename
                            # - If old file is mmap'd, inode stays alive (refcounted)
                            # - OS automatically deletes inode when last reference drops
                            # - No explicit cleanup needed
                            os.rename(str(temp_path), str(final_path))

                        logger.info(f"{index_type} rebuild: Complete (lock will release)")

                        if completion_callback:
                            completion_callback(success=True)

                    except Exception as e:
                        # Cleanup temp files on failure
                        logger.error(f"{index_type} rebuild failed during build/swap: {e}")
                        self._cleanup_temp_files()
                        raise

                    finally:
                        # Lock released automatically when exiting 'with' block
                        # fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN) happens implicitly
                        pass

            except Exception as e:
                logger.error(f"{index_type} rebuild failed: {e}")
                if completion_callback:
                    completion_callback(success=False, error=str(e))

        # Start background thread
        thread = threading.Thread(target=_rebuild_worker, daemon=True)
        thread.start()
        return thread

    def _cleanup_temp_files(self):
        """
        Cleanup orphaned .tmp files from previous crashed rebuilds.

        Safe to call because:
        - Only called while holding exclusive rebuild lock
        - Serializes all rebuilds, so no concurrent tmp file creation
        - Removes only *.tmp files, never touches active indexes

        Why this is needed:
        - Crash before atomic swap leaves .tmp files on disk
        - These accumulate and waste disk space
        - Must cleanup before starting new rebuild
        """
        logger = logging.getLogger(__name__)

        try:
            # Find all .tmp files in index directory
            for tmp_file in self.index_dir.glob("*.tmp"):
                try:
                    tmp_file.unlink()
                    logger.info(f"Cleaned up orphaned temp file: {tmp_file.name}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup {tmp_file.name}: {e}")
                    # Continue cleanup even if one file fails

        except Exception as e:
            logger.warning(f"Temp file cleanup failed: {e}")
            # Don't fail rebuild if cleanup fails
```

### HNSW Index Manager Integration

```python
# In src/code_indexer/storage/hnsw_index_manager.py

class HNSWIndexManager:
    """HNSW index manager with background rebuild support."""

    def __init__(self, vector_dim: int, space: str = "cosine"):
        self.vector_dim = vector_dim
        self.space = space
        self.logger = logging.getLogger(__name__)

    def rebuild_from_vectors_background(
        self,
        collection_path: Path,
        progress_callback: Optional[Callable] = None
    ) -> threading.Thread:
        """
        Rebuild HNSW index in background (non-blocking).

        Used by:
        - Watch mode after file changes (avoids UI freeze)
        - Temporal indexing after adding 12K blobs (keeps daemon responsive)
        - Manual cidx index calls while daemon running

        Behavior:
        - Queries continue using old index during rebuild (stale reads OK)
        - New index swapped atomically when ready (<2ms lock)
        - Concurrent rebuild requests serialize (no wasted work)
        """

        def _build_index_to_temp() -> dict:
            """Build index and return {temp_path: final_path} mapping."""

            # Load all vectors (no lock needed - read-only)
            vectors_list = []
            ids_list = []

            for vector_file in sorted(collection_path.glob("vector_*.json")):
                with open(vector_file) as f:
                    data = json.load(f)
                vectors_list.append(data["vector"])
                ids_list.append(data["id"])

            if not vectors_list:
                return {}

            vectors = np.array(vectors_list, dtype=np.float32)

            # Build HNSW index in memory (no lock needed)
            index = hnswlib.Index(space=self.space, dim=self.vector_dim)
            index.init_index(
                max_elements=len(vectors),
                M=16,
                ef_construction=200
            )
            index.add_items(vectors, np.arange(len(vectors)))

            # Write to TEMPORARY files (no lock needed)
            temp_index = collection_path / "hnsw_index.bin.tmp"
            temp_meta = collection_path / "collection_meta.json.tmp"

            index.save_index(str(temp_index))

            # Update metadata in temp file
            metadata = self._load_metadata(collection_path)
            metadata["hnsw_index"] = {
                "version": 1,
                "vector_count": len(vectors),
                "is_stale": False,
                "last_rebuild": datetime.now().isoformat()
            }

            with open(temp_meta, "w") as f:
                json.dump(metadata, f, indent=2)

            # Return mapping for atomic swap
            return {
                temp_index: collection_path / "hnsw_index.bin",
                temp_meta: collection_path / "collection_meta.json"
            }

        # Use background rebuilder
        rebuilder = BackgroundIndexRebuilder(collection_path)
        return rebuilder.rebuild_background(
            index_type="HNSW",
            rebuild_callback=_build_index_to_temp,
            completion_callback=lambda success, error=None: (
                self.logger.info(f"HNSW rebuild {'succeeded' if success else f'failed: {error}'}")
            )
        )
```

### ID Index Manager Integration

```python
# In src/code_indexer/storage/id_index_manager.py

class IDIndexManager:
    """ID index manager with background rebuild support."""

    def rebuild_from_vectors_background(
        self,
        collection_path: Path
    ) -> threading.Thread:
        """
        Rebuild ID index in background (non-blocking).

        ID Index Structure:
            {
                "vec_0": 0,      # vector_id -> internal_label
                "vec_1": 1,
                "blob_abc123": 2
            }

        Note: ID index is small (< 1MB typically), so rebuild is fast (~10-50ms)
        Background rebuild still useful for consistency with other indexes
        """

        def _build_index_to_temp() -> dict:
            """Build ID index and return {temp_path: final_path} mapping."""

            # Load all vector IDs from vector_*.json files
            id_mapping = {}
            label = 0

            for vector_file in sorted(collection_path.glob("vector_*.json")):
                with open(vector_file) as f:
                    data = json.load(f)
                id_mapping[data["id"]] = label
                label += 1

            # Write to TEMPORARY file
            temp_id_index = collection_path / "id_index.json.tmp"

            with open(temp_id_index, "w") as f:
                json.dump(id_mapping, f, indent=2)

            # Update metadata in temp file
            temp_meta = collection_path / "collection_meta.json.tmp"

            # Load existing metadata (may have been updated by HNSW rebuild)
            if temp_meta.exists():
                with open(temp_meta) as f:
                    metadata = json.load(f)
            else:
                meta_file = collection_path / "collection_meta.json"
                with open(meta_file) as f:
                    metadata = json.load(f)

            metadata["id_index"] = {
                "version": 1,
                "entry_count": len(id_mapping),
                "last_rebuild": datetime.now().isoformat()
            }

            with open(temp_meta, "w") as f:
                json.dump(metadata, f, indent=2)

            # Return mapping for atomic swap
            return {
                temp_id_index: collection_path / "id_index.json",
                temp_meta: collection_path / "collection_meta.json"
            }

        # Use background rebuilder
        rebuilder = BackgroundIndexRebuilder(collection_path)
        return rebuilder.rebuild_background(
            index_type="ID",
            rebuild_callback=_build_index_to_temp,
            completion_callback=lambda success, error=None: (
                logging.getLogger(__name__).info(
                    f"ID index rebuild {'succeeded' if success else f'failed: {error}'}"
                )
            )
        )
```

### FTS Index (Tantivy) Integration

```python
# In src/code_indexer/services/tantivy_index_manager.py

class TantivyIndexManager:
    """Tantivy FTS index manager with background rebuild support."""

    def rebuild_from_documents_background(
        self,
        collection_path: Path,
        documents: List[Dict[str, Any]]
    ) -> threading.Thread:
        """
        Rebuild Tantivy FTS index in background (non-blocking).

        Tantivy Index Structure:
            tantivy_fts/
            ├── .tantivy.json        # Schema
            ├── meta.json            # Segment metadata
            └── *.{store,pos,idx}    # Segment files (mmap'd)

        Note: Tantivy uses mmap for segment files
        Cache invalidation applies here too (detect version changes)
        """

        def _build_index_to_temp() -> dict:
            """Build Tantivy index and return {temp_path: final_path} mapping."""

            # Create temporary index directory
            temp_fts_dir = collection_path / "tantivy_fts.tmp"
            temp_fts_dir.mkdir(exist_ok=True)

            # Build Tantivy index in temp directory
            import tantivy

            schema_builder = tantivy.SchemaBuilder()
            schema_builder.add_text_field("id", stored=True)
            schema_builder.add_text_field("content", stored=True)
            schema_builder.add_text_field("file_path", stored=True)
            schema = schema_builder.build()

            index = tantivy.Index(schema, path=str(temp_fts_dir))
            writer = index.writer(heap_size=50_000_000)  # 50MB heap

            # Index all documents
            for doc in documents:
                writer.add_document(tantivy.Document(
                    id=doc["id"],
                    content=doc["content"],
                    file_path=doc.get("file_path", "")
                ))

            writer.commit()

            # Update metadata in temp file
            temp_meta = collection_path / "collection_meta.json.tmp"

            if temp_meta.exists():
                with open(temp_meta) as f:
                    metadata = json.load(f)
            else:
                meta_file = collection_path / "collection_meta.json"
                with open(meta_file) as f:
                    metadata = json.load(f)

            metadata["fts_index"] = {
                "version": 1,
                "document_count": len(documents),
                "last_rebuild": datetime.now().isoformat()
            }

            with open(temp_meta, "w") as f:
                json.dump(metadata, f, indent=2)

            # Return mapping for atomic swap
            # Note: For directories, use os.rename() which works atomically
            return {
                temp_fts_dir: collection_path / "tantivy_fts",
                temp_meta: collection_path / "collection_meta.json"
            }

        # Use background rebuilder
        rebuilder = BackgroundIndexRebuilder(collection_path)
        return rebuilder.rebuild_background(
            index_type="FTS",
            rebuild_callback=_build_index_to_temp,
            completion_callback=lambda success, error=None: (
                logging.getLogger(__name__).info(
                    f"FTS index rebuild {'succeeded' if success else f'failed: {error}'}"
                )
            )
        )
```

**FTS Cache Invalidation Note:**

Tantivy indexes are directories with multiple files. The same version-based cache invalidation applies:
- Metadata file mtime changes after atomic swap
- Next query detects version change
- Tantivy reader reopened on new directory
- Old directory auto-deleted when last reference drops

### Cache Invalidation Strategy (Critical for mmap)

**Problem:** After atomic file swap, in-memory cached indexes (using mmap) still point to old file's inode.

**Solution:** Version-based cache invalidation using metadata file changes.

```python
# In src/code_indexer/storage/filesystem_vector_store.py

class FilesystemVectorStore:
    """Vector store with version-aware index caching."""

    def __init__(self):
        # Index caches with version tracking
        self._hnsw_cache: Dict[str, Tuple[Any, str]] = {}  # collection_name -> (index, version)
        self._id_index: Dict[str, Tuple[Any, str]] = {}    # collection_name -> (index, version)
        self._cache_lock = threading.Lock()

    def _get_index_version(self, collection_path: Path) -> str:
        """
        Get current index version from metadata file.

        Version = metadata file's mtime + size (unique per atomic swap)

        Returns:
            Version string like "1730572800123456789_2048"

        Why this works:
            - Atomic rename creates new metadata inode
            - New inode = new mtime + potentially new size
            - Version changes after every rebuild
        """
        meta_file = collection_path / "collection_meta.json"

        if not meta_file.exists():
            return "v0"

        # Use nanosecond precision mtime + size for uniqueness
        stat = meta_file.stat()
        return f"{stat.st_mtime_ns}_{stat.st_size}"

    def _load_hnsw_cached(
        self,
        collection_name: str,
        collection_path: Path
    ) -> Any:
        """
        Load HNSW index with version-aware caching.

        Cache hit (fast path):
            - Check version: ~0.1ms (stat syscall)
            - Return cached index: ~0.001ms (dict lookup)

        Cache miss (after rebuild):
            - Version changed
            - Load new index: ~200-300ms (mmap)
            - Update cache

        Returns:
            hnswlib.Index instance (cached or freshly loaded)
        """
        current_version = self._get_index_version(collection_path)

        with self._cache_lock:
            # Check if cached version is still valid
            if collection_name in self._hnsw_cache:
                cached_index, cached_version = self._hnsw_cache[collection_name]

                if cached_version == current_version:
                    # Cache hit - version matches
                    return cached_index
                else:
                    # Cache invalidation - version changed after rebuild
                    self.logger.info(
                        f"HNSW index version changed for '{collection_name}', "
                        f"reloading (old: {cached_version}, new: {current_version})"
                    )
                    # Note: Don't explicitly unload old index
                    # Python GC will handle mmap cleanup when old index loses all references

            # Load fresh index
            meta_file = collection_path / "collection_meta.json"
            with open(meta_file) as f:
                metadata = json.load(f)

            vector_size = metadata.get("vector_size", 1536)
            hnsw_manager = HNSWIndexManager(vector_dim=vector_size, space="cosine")

            new_index = hnsw_manager.load_index(collection_path, max_elements=100000)

            # Cache with current version
            self._hnsw_cache[collection_name] = (new_index, current_version)

            return new_index

    def _load_id_index_cached(
        self,
        collection_name: str,
        collection_path: Path
    ) -> Any:
        """
        Load ID index with version-aware caching.

        Same pattern as HNSW caching - detects version changes after rebuild.
        """
        current_version = self._get_index_version(collection_path)

        with self._cache_lock:
            if collection_name in self._id_index:
                cached_index, cached_version = self._id_index[collection_name]

                if cached_version == current_version:
                    return cached_index
                else:
                    self.logger.info(
                        f"ID index version changed for '{collection_name}', reloading"
                    )

            # Load fresh index
            from .id_index_manager import IDIndexManager
            id_manager = IDIndexManager()
            new_index = id_manager.load_index(collection_path)

            # Cache with current version
            self._id_index[collection_name] = (new_index, current_version)

            return new_index

    def search(self, query: str, ...):
        """Search with cached indexes (automatic invalidation on version change)."""

        # BEFORE: Load fresh every query (200-300ms overhead)
        # hnsw_index = hnsw_manager.load_index(collection_path)

        # AFTER: Load with caching (0.1ms when cached, 200-300ms on cache miss)
        hnsw_index = self._load_hnsw_cached(collection_name, collection_path)
        id_index = self._load_id_index_cached(collection_name, collection_path)

        # Rest of search logic...
```

**Why This Works:**

1. **Atomic Metadata Swap:**
   ```python
   # Background rebuild worker (with exclusive lock held)
   os.rename("hnsw_index.bin.tmp", "hnsw_index.bin")
   os.rename("collection_meta.json.tmp", "collection_meta.json")  # New inode created
   ```

2. **Version Detection:**
   ```python
   # Next query checks version
   old_version = "1730572800123456789_2048"  # Before swap
   new_version = "1730572850987654321_2048"  # After swap (new mtime)
   # Version mismatch triggers cache reload
   ```

3. **Race Condition Safety:**
   ```
   Timeline:
   T1: Query checks version (old) → Uses cached index (old) → Consistent stale read ✅
   T2: Atomic swap happens
   T3: Query checks version (new) → Cache miss → Loads new index → Consistent fresh read ✅
   ```

   No partial state possible - atomic rename guarantees queries see either old OR new, never corrupt.

4. **mmap Cleanup:**
   ```python
   # Old index loses references when cache entry replaced
   self._hnsw_cache[collection_name] = (new_index, new_version)
   # Python GC destroys old index object
   # hnswlib destructor unmaps old mmap region
   # OS releases old file's pages
   ```

**Performance Comparison:**

| Operation | Without Cache | With Cache (Hit) | With Cache (Miss) |
|-----------|--------------|------------------|-------------------|
| Version check | N/A | ~0.1ms | ~0.1ms |
| Index load | 200-300ms | 0.001ms | 200-300ms |
| **Total** | **200-300ms** | **~0.1ms** | **200-300ms** |
| **Speedup** | Baseline | **2000-3000x faster** | Same as baseline |

Cache hit rate after rebuild: 99.9% (only first query after rebuild misses)

### File Lifecycle and Cleanup Strategy

**Critical Question:** Do old index versions accumulate on disk?

**Answer:** NO - automatic cleanup happens through:

#### 1. Atomic Rename Auto-Cleanup (Normal Case)

```python
# Before atomic swap
Files on disk:
├─ hnsw_index.bin (inode 12345, linked, size: 500MB)
├─ hnsw_index.bin.tmp (inode 67890, linked, size: 500MB)
└─ Total disk usage: 1000MB

# Atomic swap
os.rename("hnsw_index.bin.tmp", "hnsw_index.bin")

# After atomic swap
Files on disk:
├─ hnsw_index.bin (inode 67890, linked) ← .tmp consumed by rename
├─ inode 12345 (unlinked, possibly mmap'd) ← Old version
└─ Total disk usage: 1000MB (if old inode has no references)
                     or 1000MB + old_size (temporarily, if mmap'd)

# Key points:
# 1. .tmp file DOES NOT ACCUMULATE - it becomes the new file
# 2. Old inode is automatically unlinked by rename
# 3. Old inode deleted when refcount → 0 (no mmap, no open fds)
```

**What happens to old index file?**

```python
os.rename("hnsw_index.bin.tmp", "hnsw_index.bin")

# This operation:
# 1. Links inode 67890 to name "hnsw_index.bin"
# 2. Unlinks inode 12345 from name "hnsw_index.bin"
# 3. Inode 12345 refcount: links=0, mmap_refs=?, fd_refs=?

# If inode 12345 has NO references (no mmap, no open files):
#   → OS immediately deletes inode and frees disk blocks
#   → Disk space reclaimed instantly

# If inode 12345 HAS references (cached index still mmap'd):
#   → Inode stays alive (refcounted)
#   → Disk blocks still allocated
#   → When cache invalidated, mmap closed
#   → Refcount → 0, OS deletes inode
#   → Disk space reclaimed (automatic, no manual cleanup)
```

#### 2. Orphaned .tmp File Cleanup (Crash Recovery)

**Scenario:** Rebuild crashes BEFORE atomic swap completes

```python
# Process crashes during rebuild
Files left behind:
├─ hnsw_index.bin (old version, still valid)
├─ hnsw_index.bin.tmp (partial/corrupt) ← ORPHAN
├─ collection_meta.json (old version, still valid)
└─ collection_meta.json.tmp (partial/corrupt) ← ORPHAN
```

**Cleanup Strategy:**

```python
def _cleanup_temp_files(self):
    """
    Cleanup orphaned .tmp files from previous crashes.

    Called at START of rebuild while holding exclusive lock.
    Safe because no concurrent rebuilds can create .tmp files.
    """
    for tmp_file in self.index_dir.glob("*.tmp"):
        tmp_file.unlink()  # Delete orphaned temp files

# In rebuild worker:
with fcntl.flock(rebuild_lock, LOCK_EX):
    # FIRST: Cleanup any orphaned .tmp files from previous crashes
    self._cleanup_temp_files()

    # THEN: Start fresh rebuild
    temp_files = rebuild_callback()  # Creates new .tmp files

    # FINALLY: Atomic swap
    os.rename(temp_path, final_path)  # .tmp consumed, old version auto-cleaned
```

#### 3. Disk Space Timeline

**Normal rebuild cycle:**

```
T0: Before rebuild
    ├─ hnsw_index.bin: 500MB (linked)
    └─ Total: 500MB

T1: Rebuild starts, creates .tmp
    ├─ hnsw_index.bin: 500MB (linked)
    ├─ hnsw_index.bin.tmp: 500MB (linked, building)
    └─ Total: 1000MB

T2: Atomic swap
    ├─ hnsw_index.bin: 500MB (linked, new inode)
    ├─ old inode: 500MB (unlinked, mmap'd by cached index)
    └─ Total: 1000MB (temporarily)

T3: Cache invalidated, old index destroyed
    ├─ hnsw_index.bin: 500MB (linked)
    ├─ old inode: DELETED (refcount → 0)
    └─ Total: 500MB

Peak disk usage: 2x index size (during T1-T2)
Steady state: 1x index size (T0, T3)
```

**Crash recovery cycle:**

```
T0: Rebuild crashes before swap
    ├─ hnsw_index.bin: 500MB (old version, still valid)
    ├─ hnsw_index.bin.tmp: 500MB (orphaned, may be corrupt)
    └─ Total: 1000MB ← WASTED SPACE

T1: Next rebuild starts
    ├─ Acquires exclusive lock
    ├─ Cleanup: Delete hnsw_index.bin.tmp
    └─ Total: 500MB ← SPACE RECLAIMED

T2: Rebuild completes
    ├─ Creates new .tmp (500MB)
    ├─ Atomic swap (old → unlinked, .tmp → linked)
    └─ Total: 500MB or 1000MB (if mmap'd)
```

#### 4. No Explicit Cleanup Needed for Old Versions

**Common misconception:** Need to manually delete old index after rename

**Reality:** OS handles it automatically through inode reference counting

```python
# WRONG - unnecessary manual cleanup
os.rename("hnsw_index.bin.tmp", "hnsw_index.bin")
# Old file already unlinked by rename!
# Don't need: os.unlink("old_version")  ← FILE DOESN'T EXIST ANYMORE

# RIGHT - let OS handle it
os.rename("hnsw_index.bin.tmp", "hnsw_index.bin")
# Old inode automatically cleaned when refcount → 0
# This happens when cache is invalidated
# No manual intervention needed
```

**Summary:**

| File Type | Accumulation Risk | Cleanup Method |
|-----------|------------------|----------------|
| Old index versions | ❌ NO | Auto-unlinked by rename, auto-deleted when unmapped |
| .tmp files (successful swap) | ❌ NO | Consumed by atomic rename |
| .tmp files (crash before swap) | ✅ YES | Explicit cleanup on next rebuild start |
| Metadata files | ❌ NO | Same as index files (auto-unlinked) |

**Disk Space Guarantee:**
- Steady state: 1x index size
- Peak (during rebuild): 2x index size (temporary)
- After crash: Up to 2x (orphaned .tmp) until next rebuild
- No unbounded accumulation ✅

### Concurrency Scenarios (Pressure Testing)

```python
# Scenario 1: Daemon + Watch Mode + Manual Index
def test_concurrent_rebuilds_serialize():
    """
    Test that concurrent rebuild requests serialize properly.

    Setup:
    - Process 1: Daemon running with watch mode
    - Process 2: User runs `cidx index` manually
    - Process 3: Temporal indexing triggers HNSW rebuild

    Expected:
    - Worker 1 acquires lock, rebuilds (5-10s)
    - Worker 2 blocks on lock, waits for Worker 1
    - Worker 3 blocks on lock, waits for Worker 1 & 2
    - All workers complete successfully (no race conditions)
    """

    import multiprocessing
    import time

    def rebuild_worker(worker_id):
        # Each worker tries to rebuild
        rebuilder = BackgroundIndexRebuilder(collection_path)

        start = time.time()
        thread = rebuilder.rebuild_background(
            index_type=f"Worker-{worker_id}",
            rebuild_callback=lambda: simulate_rebuild(worker_id, duration=3)
        )
        thread.join()
        elapsed = time.time() - start

        print(f"Worker {worker_id}: Completed in {elapsed:.1f}s")
        return elapsed

    # Spawn 3 concurrent workers (different processes)
    with multiprocessing.Pool(3) as pool:
        results = pool.map(rebuild_worker, [1, 2, 3])

    # Verify serialization:
    # - Worker 1: ~3s (got lock immediately)
    # - Worker 2: ~6s (waited 3s for Worker 1)
    # - Worker 3: ~9s (waited 6s for Workers 1 & 2)
    assert results[0] < 4  # Worker 1 fast
    assert results[1] > 5  # Worker 2 waited
    assert results[2] > 8  # Worker 3 waited longest


# Scenario 2: Queries During Rebuild
def test_queries_not_blocked_during_rebuild():
    """
    Test that queries continue working during rebuild.

    Setup:
    - Start HNSW rebuild (will take 5 seconds)
    - Run 100 queries concurrently

    Expected:
    - All queries complete in <500ms (using old index)
    - None blocked waiting for rebuild lock
    - Rebuild completes independently
    """

    import concurrent.futures

    # Start rebuild in background
    rebuilder = BackgroundIndexRebuilder(collection_path)
    rebuild_thread = rebuilder.rebuild_background(
        index_type="HNSW",
        rebuild_callback=lambda: simulate_rebuild_slow(duration=5)
    )

    # Run queries concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        query_futures = [
            executor.submit(run_query, f"query-{i}")
            for i in range(100)
        ]

        # Wait for all queries
        query_times = [f.result() for f in query_futures]

    # Verify queries were fast (not blocked)
    max_query_time = max(query_times)
    assert max_query_time < 0.5, f"Queries should be fast, got {max_query_time}s"

    # Wait for rebuild to complete
    rebuild_thread.join()


# Scenario 3: Crash During Rebuild
def test_crash_recovery_cleanup():
    """
    Test that .tmp files are cleaned up after crash.

    Setup:
    - Start rebuild, kill process mid-rebuild
    - Restart daemon

    Expected:
    - Old index still exists (not corrupted)
    - .tmp files either cleaned up or ignored
    - New rebuild can proceed
    """

    # Create temp files
    temp_index = collection_path / "hnsw_index.bin.tmp"
    temp_index.write_text("partial rebuild")

    # Verify old index still works
    assert (collection_path / "hnsw_index.bin").exists()

    # New rebuild should succeed (ignore or cleanup .tmp)
    rebuilder = BackgroundIndexRebuilder(collection_path)
    thread = rebuilder.rebuild_background(
        index_type="HNSW-Recovery",
        rebuild_callback=lambda: {temp_index: collection_path / "hnsw_index.bin"}
    )
    thread.join()

    # New index should be in place
    assert (collection_path / "hnsw_index.bin").exists()
```

## Test Scenarios

### Manual Testing

1. **Daemon Mode + Concurrent Index:**
   ```bash
   # Terminal 1: Start daemon
   cidx start --daemon

   # Terminal 2: Trigger rebuild
   cidx index --force

   # Terminal 3: Run queries (should be fast)
   for i in {1..100}; do
     cidx query "test" --quiet &
   done
   wait
   ```

2. **Watch Mode + Manual Rebuild:**
   ```bash
   # Terminal 1: Watch mode
   cidx start --watch

   # Terminal 2: Make file changes (triggers rebuild)
   echo "new code" > test.py

   # Terminal 3: Manual rebuild (should serialize)
   cidx index
   ```

3. **Crash Recovery:**
   ```bash
   # Start rebuild, kill mid-process
   cidx index --force &
   sleep 2
   killall cidx

   # Verify old index still works
   cidx query "test"

   # New rebuild should succeed
   cidx index --force
   ```

### Automated Tests

```python
def test_hnsw_background_rebuild():
    """Test HNSW background rebuild with queries."""
    # Create vectors
    create_test_vectors(count=1000)

    # Start rebuild
    manager = HNSWIndexManager(vector_dim=1536)
    thread = manager.rebuild_from_vectors_background(collection_path)

    # Run queries while rebuilding
    for i in range(50):
        results = run_query("test query")
        assert len(results) > 0  # Old index works

    # Wait for rebuild
    thread.join()

    # New index should work
    results = run_query("test query")
    assert len(results) > 0


def test_cross_process_serialization():
    """Test file locks work across processes."""
    # Start rebuild in process 1
    p1 = multiprocessing.Process(target=rebuild_worker, args=(1,))
    p1.start()

    time.sleep(0.1)  # Let p1 acquire lock

    # Start rebuild in process 2 (should block)
    p2 = multiprocessing.Process(target=rebuild_worker, args=(2,))
    p2.start()

    p1.join()
    p2.join()

    # Verify both completed successfully (serialized)
    assert check_rebuild_log(worker=1, success=True)
    assert check_rebuild_log(worker=2, success=True)
```

## Dependencies

- `fcntl` module for file locking (POSIX systems)
- `threading` for background workers
- Existing index managers (HNSW, ID, FTS)

## Performance Targets

- Query latency: No increase during rebuild (use stale index)
- Rebuild serialization overhead: <10ms (lock acquisition)
- Atomic swap duration: <2ms
- Crash recovery: Automatic (old index unaffected)

## Notes

**Why Serialize Rebuilds:**
- Avoids wasted work (3 concurrent rebuilds = 3x CPU/memory)
- Prevents .tmp file conflicts
- Simpler to reason about (only 2 states: locked/unlocked)
- Safer (no complex state machines)

**Why File Locks:**
- Works across processes (daemon + standalone)
- OS-level primitive (reliable)
- Auto-released on crash (no deadlocks)
- No shared memory needed

**Why Lock Entire Rebuild:**
- User's critical insight: "it will be extremely complicated to manage and bug prone"
- Lock only during swap = complex state tracking
- Lock entire rebuild = simple, robust, testable

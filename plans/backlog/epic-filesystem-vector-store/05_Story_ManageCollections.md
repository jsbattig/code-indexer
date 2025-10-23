# Story 5: Manage Collections and Clean Up Filesystem Index

**Story ID:** S05
**Epic:** Filesystem-Based Vector Database Backend
**Priority:** High
**Estimated Effort:** 3-4 days
**Implementation Order:** 6

## User Story

**As a** developer with filesystem-indexed code
**I want to** manage collections and clean up vector data
**So that** I can remove outdated indexes, switch models, and maintain repository hygiene

**Conversation Reference:** User requirement implicit in "I want it to go inside git, as the code" - git-trackable vectors require explicit cleanup management to avoid repository bloat.

## Acceptance Criteria

### Functional Requirements
1. ✅ `cidx clean` removes all vectors from current collection
2. ✅ `cidx clean --collection <name>` cleans specific collection
3. ✅ `cidx uninstall` removes entire `.code-indexer/vectors/` directory
4. ✅ Collection deletion preserves projection matrix (optional flag to remove)
5. ✅ List collections with metadata
6. ✅ Clear confirmation prompts before destructive operations
7. ✅ No container cleanup required

### Technical Requirements
1. ✅ Safe deletion with confirmation prompts
2. ✅ Atomic operations (no partial deletions)
3. ✅ Collection metadata management
4. ✅ Projection matrix preservation option
5. ✅ Git-aware cleanup recommendations
6. ✅ Storage space reclamation reporting

### Safety Requirements
1. ✅ Require explicit confirmation for destructive operations
2. ✅ Show impact before deletion (# vectors, file count, size)
3. ✅ Preserve collection structure when clearing vectors
4. ✅ No accidental deletion of all collections

## Manual Testing Steps

```bash
# Test 1: Clean current collection
cd /path/to/indexed-repo
cidx clean

# Expected output:
# ⚠️  This will remove all vectors from collection: voyage-code-3_main
#    Vectors: 852
#    Storage: 12.5 MB
# Are you sure? (y/N):
# y
# ✅ Cleared 852 vectors from voyage-code-3_main
# 📁 Collection structure preserved (projection matrix retained)

# Verify vectors removed but structure intact
ls .code-indexer/vectors/voyage-code-3_main/
# Expected: projection_matrix.npy, collection_meta.json (no vector files)

# Test 2: Clean specific collection
cidx clean --collection voyage-code-3_feature-branch

# Expected: Same confirmation flow for specific collection

# Test 3: Delete collection entirely
cidx clean --collection voyage-code-3_main --delete-collection

# Expected output:
# ⚠️  This will DELETE entire collection: voyage-code-3_main
#    Vectors: 852
#    Storage: 12.5 MB
#    This will remove projection matrix and metadata!
# Are you sure? (y/N):
# y
# ✅ Deleted collection: voyage-code-3_main

# Verify collection directory removed
ls .code-indexer/vectors/
# Expected: voyage-code-3_main/ no longer exists

# Test 4: Uninstall entire backend
cidx uninstall

# Expected output:
# ⚠️  This will remove ALL filesystem vector data:
#    Collections: 2
#    Total Vectors: 1,247
#    Storage: 15.3 MB
#    Path: /path/to/repo/.code-indexer/vectors/
#
# This operation cannot be undone!
# Are you sure? (y/N):
# y
# ✅ Removed filesystem vector storage
# 💡 Tip: Remove .code-indexer/ from git if no longer needed

# Verify directory removed
ls .code-indexer/
# Expected: vectors/ directory no longer exists

# Test 5: Clean with --force (no confirmation)
cidx clean --force

# Expected: Immediate cleanup without prompts (for scripts)

# Test 6: List collections before cleanup
cidx collections

# Expected output:
# 📚 Collections in .code-indexer/vectors/:
#   1. voyage-code-3_main
#      Vectors: 852
#      Created: 2025-01-23 10:15:00
#      Size: 12.5 MB
#
#   2. voyage-code-3_feature-branch
#      Vectors: 395
#      Created: 2025-01-23 11:30:00
#      Size: 2.8 MB

# Test 7: Abort cleanup
cidx clean
# Enter 'n' at prompt
# Expected: Operation cancelled, no changes made
```

## Technical Implementation Details

### FilesystemCollectionManager Class

```python
class FilesystemCollectionManager:
    """Manage collections in filesystem vector storage."""

    def __init__(self, base_path: Path):
        self.base_path = base_path

    def list_collections(self) -> List[Dict[str, Any]]:
        """List all collections with metadata."""
        if not self.base_path.exists():
            return []

        collections = []

        for collection_dir in self.base_path.iterdir():
            if not collection_dir.is_dir():
                continue

            meta_path = collection_dir / "collection_meta.json"
            if not meta_path.exists():
                continue

            try:
                metadata = json.loads(meta_path.read_text())
                vector_count = self._count_vectors(collection_dir.name)
                storage_size = self._calculate_collection_size(collection_dir)

                collections.append({
                    "name": collection_dir.name,
                    "vector_count": vector_count,
                    "vector_size": metadata.get("vector_size", "unknown"),
                    "created_at": metadata.get("created_at", "unknown"),
                    "storage_size": storage_size,
                    "has_projection_matrix": (collection_dir / "projection_matrix.npy").exists()
                })
            except Exception as e:
                collections.append({
                    "name": collection_dir.name,
                    "error": str(e),
                    "status": "corrupted"
                })

        return collections

    def clear_collection(
        self,
        collection_name: str,
        preserve_projection: bool = True
    ) -> Dict[str, Any]:
        """Remove all vectors but keep collection structure.

        Args:
            collection_name: Collection to clear
            preserve_projection: If True, keep projection matrix and metadata

        Returns:
            Operation result with stats
        """
        collection_path = self.base_path / collection_name

        if not collection_path.exists():
            return {
                "success": False,
                "error": f"Collection '{collection_name}' not found"
            }

        # Count vectors before deletion
        vector_count = self._count_vectors(collection_name)
        storage_size = self._calculate_collection_size(collection_path)

        # Remove all vector JSON files
        deleted_files = 0
        for json_file in collection_path.rglob("*.json"):
            if preserve_projection and json_file.name == "collection_meta.json":
                continue

            try:
                json_file.unlink()
                deleted_files += 1
            except Exception as e:
                # Log but continue
                print(f"Warning: Failed to delete {json_file}: {e}")

        # Update metadata
        if preserve_projection:
            meta_path = collection_path / "collection_meta.json"
            if meta_path.exists():
                try:
                    metadata = json.loads(meta_path.read_text())
                    metadata["vector_count"] = 0
                    metadata["cleared_at"] = datetime.utcnow().isoformat()
                    meta_path.write_text(json.dumps(metadata, indent=2))
                except Exception:
                    pass

        return {
            "success": True,
            "collection": collection_name,
            "vectors_removed": vector_count,
            "files_deleted": deleted_files,
            "storage_reclaimed": storage_size,
            "projection_preserved": preserve_projection
        }

    def delete_collection(self, collection_name: str) -> Dict[str, Any]:
        """Completely remove collection including metadata and matrix.

        Args:
            collection_name: Collection to delete

        Returns:
            Operation result
        """
        collection_path = self.base_path / collection_name

        if not collection_path.exists():
            return {
                "success": False,
                "error": f"Collection '{collection_name}' not found"
            }

        # Get stats before deletion
        vector_count = self._count_vectors(collection_name)
        storage_size = self._calculate_collection_size(collection_path)

        # Remove entire directory
        try:
            shutil.rmtree(collection_path)
            return {
                "success": True,
                "collection": collection_name,
                "vectors_removed": vector_count,
                "storage_reclaimed": storage_size
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to delete collection: {str(e)}"
            }

    def delete_all_data(self) -> Dict[str, Any]:
        """Remove entire filesystem vector storage.

        This is the equivalent of 'uninstall' for filesystem backend.

        Returns:
            Operation result with total stats
        """
        if not self.base_path.exists():
            return {
                "success": True,
                "message": "No vector data to remove"
            }

        # Get total stats
        collections = self.list_collections()
        total_vectors = sum(c.get('vector_count', 0) for c in collections)
        total_size = self._calculate_total_size()

        # Remove entire directory
        try:
            shutil.rmtree(self.base_path)
            return {
                "success": True,
                "collections_removed": len(collections),
                "total_vectors": total_vectors,
                "storage_reclaimed": total_size
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to remove vector storage: {str(e)}"
            }

    def _count_vectors(self, collection_name: str) -> int:
        """Count vectors in collection."""
        collection_path = self.base_path / collection_name

        if not collection_path.exists():
            return 0

        return sum(
            1 for f in collection_path.rglob("*.json")
            if f.name != "collection_meta.json"
        )

    def _calculate_collection_size(self, collection_path: Path) -> int:
        """Calculate storage size of collection in bytes."""
        if not collection_path.exists():
            return 0

        total_size = 0
        for file_path in collection_path.rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size

        return total_size

    def _calculate_total_size(self) -> int:
        """Calculate total storage size in bytes."""
        if not self.base_path.exists():
            return 0

        total_size = 0
        for file_path in self.base_path.rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size

        return total_size
```

### CLI Integration with Confirmation Prompts

```python
@click.command()
@click.option("--collection", help="Specific collection to clean (default: current)")
@click.option("--delete-collection", is_flag=True, help="Delete entire collection")
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def clean_command(
    collection: Optional[str],
    delete_collection: bool,
    force: bool
):
    """Clean vectors from collection."""
    config = load_config()
    backend = VectorStoreBackendFactory.create_backend(config)

    if backend.get_status()["type"] != "filesystem":
        console.print("❌ Clean command only supports filesystem backend", style="red")
        raise Exit(1)

    vector_store = backend.get_vector_store_client()
    collection_manager = vector_store.collections

    # Determine target collection
    target_collection = collection or config.collection_name

    # Get collection info
    collections = collection_manager.list_collections()
    target = next((c for c in collections if c['name'] == target_collection), None)

    if not target:
        console.print(f"❌ Collection '{target_collection}' not found", style="red")
        raise Exit(1)

## Unit Test Coverage Requirements

**Test Strategy:** Use real filesystem operations to test collection management (NO mocking)

**Test File:** `tests/unit/storage/test_collection_management.py`

**Required Tests:**

```python
class TestCollectionManagementWithRealFilesystem:
    """Test collection operations using real filesystem."""

    def test_create_collection_initializes_structure(self, tmp_path):
        """GIVEN a collection name
        WHEN create_collection() is called
        THEN directory and metadata files created on real filesystem"""
        store = FilesystemVectorStore(tmp_path, config)

        result = store.create_collection('test_coll', vector_size=1536)

        assert result is True

        # Verify actual filesystem structure
        coll_path = tmp_path / 'test_coll'
        assert coll_path.exists()
        assert coll_path.is_dir()
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
        THEN entire directory tree removed from filesystem"""
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)

        # Add 100 vectors
        points = [
            {'id': f'vec_{i}', 'vector': np.random.randn(1536).tolist(),
             'payload': {'file_path': f'file_{i}.py'}}
            for i in range(100)
        ]
        store.upsert_points_batched('test_coll', points)

        # Verify collection exists with data
        assert (tmp_path / 'test_coll').exists()
        assert store.count_points('test_coll') == 100

        # Delete collection
        result = store.delete_collection('test_coll')

        assert result is True
        assert not (tmp_path / 'test_coll').exists()  # Actually removed
        assert store.count_points('test_coll') == 0

    def test_clear_collection_preserves_structure(self, tmp_path):
        """GIVEN a collection with vectors
        WHEN clear_collection() is called
        THEN vectors deleted but collection structure preserved"""
        store = FilesystemVectorStore(tmp_path, config)
        store.create_collection('test_coll', 1536)

        # Add 50 vectors
        points = [
            {'id': f'vec_{i}', 'vector': np.random.randn(1536).tolist(),
             'payload': {'file_path': f'file_{i}.py'}}
            for i in range(50)
        ]
        store.upsert_points('test_coll', points)

        assert store.count_points('test_coll') == 50

        # Clear collection
        result = store.clear_collection('test_coll')

        assert result is True
        assert (tmp_path / 'test_coll').exists()  # Collection still exists
        assert (tmp_path / 'test_coll' / 'projection_matrix.npy').exists()  # Preserved
        assert (tmp_path / 'test_coll' / 'collection_meta.json').exists()  # Preserved
        assert store.count_points('test_coll') == 0  # Vectors removed

    def test_list_collections_returns_all_collections(self, tmp_path):
        """GIVEN multiple collections on filesystem
        WHEN list_collections() is called
        THEN all collection names returned"""
        store = FilesystemVectorStore(tmp_path, config)

        collections = ['coll_a', 'coll_b', 'coll_c']
        for coll in collections:
            store.create_collection(coll, 1536)

        result = store.list_collections()

        assert set(result) == set(collections)

    def test_cleanup_removes_all_data(self, tmp_path):
        """GIVEN multiple collections with data
        WHEN cleanup(remove_data=True) is called
        THEN all vectors and collections removed"""
        backend = FilesystemBackend(config)
        backend.initialize(config)

        store = backend.get_vector_store_client()

        # Create 3 collections with data
        for i in range(3):
            store.create_collection(f'coll_{i}', 1536)
            points = [
                {'id': f'vec_{j}', 'vector': np.random.randn(1536).tolist(),
                 'payload': {'file_path': f'file.py'}}
                for j in range(10)
            ]
            store.upsert_points(f'coll_{i}', points)

        # Verify data exists
        vectors_dir = tmp_path / ".code-indexer" / "vectors"
        assert vectors_dir.exists()
        assert len(list(vectors_dir.iterdir())) == 3

        # Cleanup
        result = backend.cleanup(remove_data=True)

        assert result is True
        assert not vectors_dir.exists()  # Actually removed from filesystem
```

**Coverage Requirements:**
- ✅ Collection creation (real directory/file creation)
- ✅ Collection deletion (actual filesystem removal)
- ✅ Collection clearing (structure preserved, vectors removed)
- ✅ Collection listing (real directory enumeration)
- ✅ Cleanup operations (verify all data removed)
- ✅ Metadata persistence

**Test Data:**
- Multiple collections (3-5)
- Various vector counts (10, 50, 100)
- Real filesystem directories in tmp_path

**Performance Assertions:**
- Collection creation: <100ms
- Collection deletion: <1s for 100 vectors
- Collection clearing: <500ms for 50 vectors
- List collections: <50ms

    # Show impact
    if delete_collection:
        console.print(f"⚠️  This will DELETE entire collection: {target_collection}", style="yellow")
        console.print(f"   Vectors: {target['vector_count']:,}")
        console.print(f"   Storage: {format_bytes(target['storage_size'])}")
        console.print("   This will remove projection matrix and metadata!")
    else:
        console.print(f"⚠️  This will remove all vectors from collection: {target_collection}", style="yellow")
        console.print(f"   Vectors: {target['vector_count']:,}")
        console.print(f"   Storage: {format_bytes(target['storage_size'])}")

    # Confirmation
    if not force:
        confirm = click.confirm("Are you sure?", default=False)
        if not confirm:
            console.print("Operation cancelled")
            return

    # Perform operation
    if delete_collection:
        result = collection_manager.delete_collection(target_collection)
    else:
        result = collection_manager.clear_collection(
            target_collection,
            preserve_projection=True
        )

    # Report results
    if result["success"]:
        if delete_collection:
            console.print(f"✅ Deleted collection: {target_collection}", style="green")
        else:
            console.print(f"✅ Cleared {result['vectors_removed']:,} vectors from {target_collection}", style="green")
            console.print("📁 Collection structure preserved (projection matrix retained)")

        console.print(f"💾 Storage reclaimed: {format_bytes(result['storage_reclaimed'])}")
    else:
        console.print(f"❌ {result['error']}", style="red")
        raise Exit(1)


@click.command()
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def uninstall_command(force: bool):
    """Remove entire filesystem vector storage."""
    config = load_config()
    backend = VectorStoreBackendFactory.create_backend(config)

    if backend.get_status()["type"] != "filesystem":
        console.print("❌ Uninstall for filesystem backend only", style="red")
        console.print("💡 For container backend, use existing uninstall command")
        raise Exit(1)

    status = backend.get_status()
    total_vectors = status.get('total_vectors', 0)
    storage_size = status.get('storage_size', 0)
    collections = status.get('collections', [])

    # Show impact
    console.print("⚠️  This will remove ALL filesystem vector data:", style="yellow")
    console.print(f"   Collections: {len(collections)}")
    console.print(f"   Total Vectors: {total_vectors:,}")
    console.print(f"   Storage: {format_bytes(storage_size)}")
    console.print(f"   Path: {status['path']}")
    console.print()
    console.print("This operation cannot be undone!", style="bold red")

    # Confirmation
    if not force:
        confirm = click.confirm("Are you sure?", default=False)
        if not confirm:
            console.print("Operation cancelled")
            return

    # Perform deletion
    vector_store = backend.get_vector_store_client()
    result = vector_store.collections.delete_all_data()

    if result["success"]:
        console.print("✅ Removed filesystem vector storage", style="green")
        console.print(f"💾 Storage reclaimed: {format_bytes(result['storage_reclaimed'])}")
        console.print()
        console.print("💡 Tip: Remove .code-indexer/ from git if no longer needed", style="dim")
        console.print("   git rm -r .code-indexer/")
        console.print("   git commit -m 'Remove vector index'")
    else:
        console.print(f"❌ {result['error']}", style="red")
        raise Exit(1)


@click.command()
def collections_command():
    """List all collections with metadata."""
    config = load_config()
    backend = VectorStoreBackendFactory.create_backend(config)

    status = backend.get_status()

    if status["type"] != "filesystem":
        console.print("❌ Collections command only supports filesystem backend", style="red")
        raise Exit(1)

    collections = status.get('collections', [])

    if not collections:
        console.print("No collections found")
        return

    console.print(f"📚 Collections in {status['path']}:", style="bold")

    for i, coll in enumerate(collections, 1):
        console.print(f"\n{i}. {coll['name']}")
        console.print(f"   Vectors: {coll['vector_count']:,}")
        console.print(f"   Created: {coll.get('created_at', 'unknown')}")
        console.print(f"   Size: {format_bytes(coll.get('storage_size', 0))}")
        console.print(f"   Projection Matrix: {'✅' if coll.get('has_projection_matrix') else '❌'}")


def format_bytes(size: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"
```

## Dependencies

### Internal Dependencies
- Story 2: Indexed vectors to clean
- Story 1: Backend abstraction layer

### External Dependencies
- Python `shutil` for directory removal
- Python `click` for confirmation prompts

## Success Metrics

1. ✅ Collections cleanable without errors
2. ✅ Confirmation prompts prevent accidental deletion
3. ✅ Storage space accurately reported and reclaimed
4. ✅ Projection matrix preservation works
5. ✅ Git repository size reduced after cleanup

## Non-Goals

- Selective vector deletion (delete specific files only)
- Automated cleanup based on age or usage
- Backup before deletion
- Undo functionality

## Follow-Up Stories

- **Story 8**: Switch Between Qdrant and Filesystem Backends (uses cleanup before switching)

## Implementation Notes

### Safety First

**Critical:** Destructive operations require confirmation by default. Only `--force` flag skips prompts (for automation scripts).

Confirmation should show:
- What will be deleted
- How many vectors affected
- Storage size impact
- Whether operation is reversible

### Projection Matrix Preservation

**By default**, `clean` preserves projection matrix and collection metadata because:
- Reindexing with same collection reuses matrix (consistency)
- Matrix generation is deterministic but slow
- Metadata useful for troubleshooting

**Delete collection entirely** when:
- Switching embedding models (different dimensions)
- Completely removing collection
- Starting fresh

### Git Integration Awareness

After `uninstall`, provide helpful git commands:
```bash
git rm -r .code-indexer/vectors/
git commit -m 'Remove filesystem vector index'
```

This helps users understand cleanup affects git-tracked files.

### Atomic Operations

Use `shutil.rmtree()` which is atomic at directory level. If operation fails partway:
- Show error message
- Report partial completion
- Recommend manual cleanup if needed

### Storage Reclamation Reporting

Show storage reclaimed to help users understand git repository size impact. This is especially important since vectors are git-tracked in filesystem backend.

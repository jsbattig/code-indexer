# Story 4: Monitor Filesystem Index Status and Health

**Story ID:** S04
**Epic:** Filesystem-Based Vector Database Backend
**Priority:** Medium
**Estimated Effort:** 2-3 days
**Implementation Order:** 5

## User Story

**As a** developer with filesystem-indexed code
**I want to** monitor the status and health of my vector index
**So that** I can verify indexing completeness and troubleshoot issues

**Conversation Reference:** User requirements for health monitoring and validation are implicit in the need for "zero-dependency" system that must be observable without external tools.

## Acceptance Criteria

### Functional Requirements
1. ✅ `cidx status` shows filesystem backend information
2. ✅ Displays collections, total vectors, and storage path
3. ✅ Lists all indexed files with timestamps
4. ✅ Validates vector dimensions match expected size
5. ✅ Shows sample vectors for debugging
6. ✅ Reports storage size and file counts
7. ✅ No container health checks required

### Technical Requirements
1. ✅ Filesystem accessibility verification
2. ✅ Collection metadata validation
3. ✅ Vector dimension consistency checks
4. ✅ Indexed file enumeration
5. ✅ Timestamp tracking for incremental indexing
6. ✅ Sample vector extraction for testing

### Health Check Criteria
1. ✅ Verify `.code-indexer/vectors/` exists and is writable
2. ✅ All collections have valid `collection_meta.json`
3. ✅ All collections have `projection_matrix.npy`
4. ✅ Vector dimensions match collection metadata
5. ✅ No corrupted JSON files

## Manual Testing Steps

```bash
# Test 1: Check status of filesystem backend
cd /path/to/indexed-repo
cidx status

# Expected output:
# 📁 Filesystem Backend
#   Path: /path/to/repo/.code-indexer/vectors
#   Collections: 2
#   Total Vectors: 1,247
#   Storage Size: 15.3 MB
#   No containers needed ✅
#
# 📚 Collections:
#   - voyage-code-3_main (852 vectors)
#   - voyage-code-3_feature-branch (395 vectors)
#
# 📊 Health: All checks passed ✅

# Test 2: List indexed files
cidx status --show-files

# Expected output:
# 📄 Indexed Files (852 files):
#   src/main.py (indexed: 2025-01-23 10:15:32)
#   src/utils.py (indexed: 2025-01-23 10:15:33)
#   tests/test_main.py (indexed: 2025-01-23 10:15:34)
#   ...

# Test 3: Validate embeddings
cidx status --validate

# Expected output:
# ✅ Validating collection: voyage-code-3_main
#   Expected dimension: 1536
#   Vectors checked: 852
#   Invalid vectors: 0
#   Status: Healthy ✅
#
# ✅ Validating collection: voyage-code-3_feature-branch
#   Expected dimension: 1536
#   Vectors checked: 395
#   Invalid vectors: 0
#   Status: Healthy ✅

# Test 4: Sample vectors (for debugging)
cidx status --sample 5

# Expected output:
# 🔬 Sample Vectors (5 from each collection):
#   Collection: voyage-code-3_main
#     1. ID: src/main.py:10-45:abc123 | Dim: 1536 | Has payload: ✅
#     2. ID: src/utils.py:5-30:def456 | Dim: 1536 | Has payload: ✅
#     3. ID: tests/test_main.py:15-60:ghi789 | Dim: 1536 | Has payload: ✅
#     ...

# Test 5: Status with corrupted collection
# Manually corrupt a JSON file
echo "invalid json" > .code-indexer/vectors/voyage-code-3_main/a3/b7/vector_test.json
cidx status --validate

# Expected output:
# ❌ Validating collection: voyage-code-3_main
#   Expected dimension: 1536
#   Vectors checked: 851
#   Invalid vectors: 1
#   Errors:
#     - vector_test.json: Invalid JSON format
#   Status: Unhealthy ❌

# Test 6: Storage breakdown
cidx status --storage-info

# Expected output:
# 💾 Storage Information:
#   Total size: 15.3 MB
#   Collections: 2
#   Average vector size: 18 KB
#   Projection matrices: 2.1 KB
#   Metadata files: 1.5 KB
```

## Technical Implementation Details

### FilesystemHealthValidation Class

```python
class FilesystemHealthValidation:
    """Health checks and validation for filesystem vector storage."""

    def __init__(self, base_path: Path):
        self.base_path = base_path

    def get_backend_status(self) -> Dict[str, Any]:
        """Get comprehensive backend status."""
        return {
            "type": "filesystem",
            "path": str(self.base_path),
            "exists": self.base_path.exists(),
            "writable": os.access(self.base_path, os.W_OK) if self.base_path.exists() else False,
            "collections": self.list_collections(),
            "total_vectors": self._count_all_vectors(),
            "storage_size": self._calculate_storage_size(),
            "health": self.perform_health_check()
        }

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
                vector_count = self._count_vectors_in_collection(collection_dir.name)

                collections.append({
                    "name": collection_dir.name,
                    "vector_count": vector_count,
                    "vector_size": metadata.get("vector_size", "unknown"),
                    "created_at": metadata.get("created_at", "unknown"),
                    "depth_factor": metadata.get("depth_factor", "unknown")
                })
            except Exception as e:
                collections.append({
                    "name": collection_dir.name,
                    "error": str(e),
                    "status": "corrupted"
                })

        return collections

    def get_all_indexed_files(
        self,
        collection_name: str
    ) -> List[Dict[str, str]]:
        """List all files indexed in collection with timestamps."""
        collection_path = self.base_path / collection_name
        indexed_files = []

        for json_file in collection_path.rglob("*.json"):
            if json_file.name == "collection_meta.json":
                continue

            try:
                data = json.loads(json_file.read_text())

                if 'file_path' in data:
                    indexed_files.append({
                        "file_path": data['file_path'],
                        "indexed_at": data.get('metadata', {}).get('indexed_at', 'unknown'),
                        "chunk_hash": data.get('chunk_hash', ''),
                        "lines": f"{data.get('start_line', 0)}-{data.get('end_line', 0)}"
                    })
            except Exception:
                continue

        # Sort by file path
        indexed_files.sort(key=lambda x: x['file_path'])

        return indexed_files

    def validate_embedding_dimensions(
        self,
        collection_name: str
    ) -> Dict[str, Any]:
        """Validate all vectors have correct dimensions."""
        collection_path = self.base_path / collection_name
        meta_path = collection_path / "collection_meta.json"

        if not meta_path.exists():
            return {
                'valid': False,
                'error': 'No collection metadata found',
                'collection': collection_name
            }

        try:
            metadata = json.loads(meta_path.read_text())
            expected_dim = metadata['vector_size']
        except Exception as e:
            return {
                'valid': False,
                'error': f'Failed to read metadata: {str(e)}',
                'collection': collection_name
            }

        invalid_vectors = []
        total_checked = 0
        json_errors = []

        for json_file in collection_path.rglob("*.json"):
            if json_file.name == "collection_meta.json":
                continue

            try:
                data = json.loads(json_file.read_text())
                total_checked += 1

                # Validate vector exists
                if 'vector' not in data:
                    invalid_vectors.append({
                        'file': json_file.name,
                        'error': 'Missing vector field'
                    })
                    continue

                # Validate dimension
                actual_dim = len(data['vector'])
                if actual_dim != expected_dim:
                    invalid_vectors.append({
                        'id': data.get('id', 'unknown'),
                        'file': json_file.name,
                        'expected': expected_dim,
                        'actual': actual_dim
                    })

            except json.JSONDecodeError as e:
                json_errors.append({
                    'file': json_file.name,
                    'error': f'Invalid JSON: {str(e)}'
                })
            except Exception as e:
                json_errors.append({
                    'file': json_file.name,
                    'error': str(e)
                })

        return {
            'valid': len(invalid_vectors) == 0 and len(json_errors) == 0,
            'collection': collection_name,
            'expected_dimension': expected_dim,
            'total_checked': total_checked,
            'invalid_count': len(invalid_vectors),
            'invalid_vectors': invalid_vectors[:10],  # First 10 for brevity
            'json_errors': json_errors[:10]
        }

    def sample_vectors(
        self,
        collection_name: str,
        sample_size: int = 5
    ) -> List[Dict[str, Any]]:
        """Get sample of vectors for debugging."""
        collection_path = self.base_path / collection_name
        samples = []

        for i, json_file in enumerate(collection_path.rglob("*.json")):
            if i >= sample_size:
                break

            if json_file.name == "collection_meta.json":
                continue

            try:
                data = json.loads(json_file.read_text())
                samples.append({
                    'id': data.get('id', 'unknown'),
                    'file_path': data.get('file_path', 'unknown'),
                    'vector_dim': len(data.get('vector', [])),
                    'has_payload': bool(data.get('payload')),
                    'indexed_at': data.get('metadata', {}).get('indexed_at', 'unknown')
                })
            except Exception as e:
                samples.append({
                    'file': json_file.name,
                    'error': str(e)
                })

        return samples

    def perform_health_check(self) -> Dict[str, Any]:
        """Comprehensive health check of filesystem storage."""
        checks = []

        # Check 1: Base path exists and writable
        checks.append({
            'name': 'Base path accessible',
            'status': self.base_path.exists() and os.access(self.base_path, os.W_OK),
            'details': f'Path: {self.base_path}'
        })

        # Check 2: Collections have metadata
        for collection_dir in self.base_path.iterdir():
            if not collection_dir.is_dir():
                continue

            meta_exists = (collection_dir / "collection_meta.json").exists()
            matrix_exists = (collection_dir / "projection_matrix.npy").exists()

            checks.append({
                'name': f'Collection: {collection_dir.name}',
                'status': meta_exists and matrix_exists,
                'details': f'Metadata: {meta_exists}, Matrix: {matrix_exists}'
            })

        all_passed = all(check['status'] for check in checks)

        return {
            'healthy': all_passed,
            'checks': checks,
            'timestamp': datetime.utcnow().isoformat()
        }

    def _count_all_vectors(self) -> int:
        """Count total vectors across all collections."""
        if not self.base_path.exists():
            return 0

        total = 0
        for collection_dir in self.base_path.iterdir():
            if collection_dir.is_dir():
                total += self._count_vectors_in_collection(collection_dir.name)

        return total

    def _count_vectors_in_collection(self, collection_name: str) -> int:
        """Count vectors in specific collection."""
        collection_path = self.base_path / collection_name

        if not collection_path.exists():
            return 0

        return sum(
            1 for f in collection_path.rglob("*.json")
            if f.name != "collection_meta.json"
        )

    def _calculate_storage_size(self) -> int:
        """Calculate total storage size in bytes."""
        if not self.base_path.exists():
            return 0

        total_size = 0
        for file_path in self.base_path.rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size

        return total_size
```

### CLI Integration

```python
@click.command()
@click.option("--show-files", is_flag=True, help="List all indexed files")
@click.option("--validate", is_flag=True, help="Validate vector dimensions")
@click.option("--sample", type=int, help="Show N sample vectors per collection")
@click.option("--storage-info", is_flag=True, help="Show storage breakdown")
def status_command(
    show_files: bool,
    validate: bool,
    sample: Optional[int],
    storage_info: bool
):
    """Show backend and indexing status."""
    config = load_config()
    backend = VectorStoreBackendFactory.create_backend(config)

    # Get backend status
    status = backend.get_status()

    if status["type"] == "filesystem":
        console.print("📁 Filesystem Backend", style="bold")
        console.print(f"  Path: {status['path']}")
        console.print(f"  Collections: {len(status['collections'])}")
        console.print(f"  Total Vectors: {status['total_vectors']:,}")
        console.print(f"  Storage Size: {format_bytes(status['storage_size'])}")
        console.print("  No containers needed ✅")

        # List collections
        if status['collections']:
            console.print("\n📚 Collections:")
            for coll in status['collections']:
                console.print(f"  - {coll['name']} ({coll['vector_count']} vectors)")

        # Health check
        health = status.get('health', {})
        if health.get('healthy'):
            console.print("\n📊 Health: All checks passed ✅")
        else:
            console.print("\n⚠️  Health: Issues detected", style="yellow")
            for check in health.get('checks', []):
                status_icon = "✅" if check['status'] else "❌"
                console.print(f"  {status_icon} {check['name']}: {check['details']}")

        # Show indexed files
        if show_files:
            health_validator = FilesystemHealthValidation(Path(status['path']))
            for coll in status['collections']:
                files = health_validator.get_all_indexed_files(coll['name'])
                console.print(f"\n📄 Indexed Files in {coll['name']} ({len(files)} files):")
                for file_info in files:
                    console.print(f"  {file_info['file_path']} (indexed: {file_info['indexed_at']})")

        # Validate dimensions
        if validate:
            health_validator = FilesystemHealthValidation(Path(status['path']))
            for coll in status['collections']:
                result = health_validator.validate_embedding_dimensions(coll['name'])
                icon = "✅" if result['valid'] else "❌"
                console.print(f"\n{icon} Validating collection: {coll['name']}")
                console.print(f"  Expected dimension: {result['expected_dimension']}")
                console.print(f"  Vectors checked: {result['total_checked']}")
                console.print(f"  Invalid vectors: {result['invalid_count']}")

                if not result['valid']:
                    console.print("  Errors:")
                    for err in result.get('json_errors', []):
                        console.print(f"    - {err['file']}: {err['error']}")

        # Sample vectors
        if sample:
            health_validator = FilesystemHealthValidation(Path(status['path']))
            console.print(f"\n🔬 Sample Vectors ({sample} from each collection):")
            for coll in status['collections']:
                samples = health_validator.sample_vectors(coll['name'], sample)
                console.print(f"  Collection: {coll['name']}")
                for i, s in enumerate(samples, 1):
                    if 'error' in s:
                        console.print(f"    {i}. Error: {s['error']}")
                    else:
                        console.print(f"    {i}. ID: {s['id']} | Dim: {s['vector_dim']} | Has payload: {'✅' if s['has_payload'] else '❌'}")
```

## Dependencies

### Internal Dependencies
- Story 2: Indexed vectors in filesystem storage
- Story 1: Backend abstraction layer

### External Dependencies
- Python `json` for parsing vector files
- Python `pathlib` for filesystem operations

## Success Metrics

1. ✅ Status command shows accurate information
2. ✅ Health checks detect corruption
3. ✅ Validation identifies dimension mismatches
4. ✅ Indexed files enumeration complete
5. ✅ Sample vectors useful for debugging

## Non-Goals

- Real-time health monitoring (CLI is stateless)
- Automatic repair of corrupted files
- Performance metrics beyond basic counts
- Integration with external monitoring systems

## Follow-Up Stories

- **Story 5**: Manage Collections and Clean Up (uses health info for cleanup decisions)

## Implementation Notes

### Health Check Philosophy

Filesystem backend has no running services, so "health" means:
- Directory structure integrity
- File format validity
- Dimension consistency
- Write accessibility

### Validation Strategy

Validation is expensive (must read all JSON files), so:
- Only run when explicitly requested with `--validate`
- Report first 10 errors to avoid overwhelming output
- Provide actionable error messages

### Storage Size Calculation

Include all files in `.code-indexer/vectors/`:
- Vector JSON files (majority of size)
- Projection matrix files
- Collection metadata files

This gives accurate git repository bloat estimate.

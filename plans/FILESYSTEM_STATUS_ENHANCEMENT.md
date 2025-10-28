# Filesystem Index File Status Enhancement

## Request
Add status checks for critical filesystem index files in `cidx status` display:

1. **Projection Matrix** (`projection_matrix.npy`) - CRITICAL
   - If missing: Index is unrecoverable, queries will fail
   - Used for dimensionality reduction in path-as-vector quantization

2. **HNSW Index** (`hnsw_index.bin`) - IMPORTANT
   - If missing: Queries fall back to brute-force search (slow but functional)
   - Used for fast approximate nearest neighbor search

3. **ID Index** - INFORMATIONAL
   - No physical file - built in-memory from vector filenames
   - Always shows "Built in-memory from filenames"

## Implementation

### Location
**File**: `src/code_indexer/cli.py`
**Section**: Filesystem vector storage status display (around line 4417)

### Current Display
```
Vector Storage     ✅ Ready      Collection: voyage-code-3
                                 Vectors: 4,444 | Files: 1,098 | Dims: ✅1024
Storage Path       📁            /path/to/.code-indexer/index
```

### Enhanced Display
```
Vector Storage     ✅ Ready      Collection: voyage-code-3
                                 Vectors: 4,444 | Files: 1,098 | Dims: ✅1024
Storage Path       📁            /path/to/.code-indexer/index
Index Files        📊            Projection Matrix: ✅ 217 KB
                                 HNSW Index: ✅ 18 MB
                                 ID Index: ℹ️ In-memory (filename-based)
```

### Code Changes

After line 4417 where `fs_details` is built, add file existence checks:

```python
# Check critical index files
collection_path = index_path / collection_name
proj_matrix = collection_path / "projection_matrix.npy"
hnsw_index = collection_path / "hnsw_index.bin"

# Build index files status
index_files_status = []

# Projection matrix (CRITICAL)
if proj_matrix.exists():
    size_kb = proj_matrix.stat().st_size / 1024
    if size_kb < 1024:
        index_files_status.append(f"Projection Matrix: ✅ {size_kb:.0f} KB")
    else:
        size_mb = size_kb / 1024
        index_files_status.append(f"Projection Matrix: ✅ {size_mb:.1f} MB")
else:
    index_files_status.append("Projection Matrix: ❌ MISSING (index unrecoverable!)")

# HNSW index (IMPORTANT)
if hnsw_index.exists():
    size_mb = hnsw_index.stat().st_size / (1024 * 1024)
    index_files_status.append(f"HNSW Index: ✅ {size_mb:.0f} MB")
else:
    index_files_status.append("HNSW Index: ⚠️ Missing (queries will be slow)")

# ID index (INFORMATIONAL)
index_files_status.append("ID Index: ℹ️ In-memory (filename-based)")

# Add to table
table.add_row("Index Files", "📊", "\n".join(index_files_status))
```

### Error Handling

If collection doesn't exist, skip index file checks (already handled by existing code).

## Expected Output

### Healthy Index
```
Index Files        📊            Projection Matrix: ✅ 217 KB
                                 HNSW Index: ✅ 18 MB  
                                 ID Index: ℹ️ In-memory (filename-based)
```

### Missing Projection Matrix (CRITICAL)
```
Index Files        📊            Projection Matrix: ❌ MISSING (index unrecoverable!)
                                 HNSW Index: ✅ 18 MB
                                 ID Index: ℹ️ In-memory (filename-based)
```

### Missing HNSW (Degraded Performance)
```
Index Files        📊            Projection Matrix: ✅ 217 KB
                                 HNSW Index: ⚠️ Missing (queries will be slow)
                                 ID Index: ℹ️ In-memory (filename-based)
```

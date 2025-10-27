# Plan: Remove Obsolete Binary/Hamming Distance Index

**Context**: With HNSW providing 300x faster queries (~20ms vs 6s), the binary/Hamming distance index is obsolete and adds unnecessary complexity.

**Goal**: Remove all binary index code, making HNSW the only vector index implementation.

---

## Impact Analysis

### Performance Comparison
| Metric | Binary Index | HNSW Index |
|--------|-------------|------------|
| Query Time | 6+ seconds | ~20ms |
| Build Time | ~5 min | ~5.5 min |
| Dependencies | None | hnswlib (already required) |
| Memory | Minimal | ~154MB for 37K vectors |
| Scalability | Poor (linear scan) | Excellent (log scale) |

**Conclusion**: No legitimate reason to keep binary index.

---

## Components to Remove

### 1. Core Files (DELETE)
- `src/code_indexer/storage/vector_index_manager.py` (entire file)
- `tests/unit/storage/test_vector_index_manager.py` (entire file)
- `tests/e2e/test_binary_index_performance.py` (entire file)

### 2. Code Sections to Remove

#### `filesystem_vector_store.py`
**Lines to delete**:
- Lines 1223-1340: Binary index lookup path (BINARY INDEX LOOKUP section)
- Lines 1341-1428: Quantized directory lookup fallback
- Lines 1429-1520: Full collection scan fallback
- All fallback logic from HNSW errors (lines 1214-1222, 1107-1115)
- `set_index_type()` method (lines 2147-2192) - no longer needed

**Imports to remove**:
- `from .vector_index_manager import VectorIndexManager` (line ~1225)

#### `cli.py`
**Lines to remove**:
- `--index-type` flag definition (lines 2093-2098)
- `index_type` parameter from `index()` function signature
- `set_index_type()` call (lines 2565-2568)
- Timing display keys: `hamming_search_ms`, `quantized_lookup_ms`, `full_scan_ms`
- Binary index timing labels (lines 660-663, 680-681)

#### `storage/__init__.py`
**Exports to remove**:
- `VectorIndexManager` export (if present)

### 3. Collection Metadata Changes

**Current metadata**:
```json
{
  "index_type": "hnsw",  // Remove this field
  "index_format": "hnsw_v1",  // Remove this field
  ...
}
```

**Simplified metadata** (HNSW is implicit):
```json
{
  "name": "collection-name",
  "vector_size": 1024,
  "created_at": "...",
  "quantization_range": {...},
  "index_version": 1,
  "index_record_size": 40,
  "hnsw_index": {...}
}
```

---

## Step-by-Step Removal Plan

### Phase 1: Delete Obsolete Files
**Goal**: Remove files that are 100% binary-index-specific

1. **Delete vector index manager**:
   ```bash
   git rm src/code_indexer/storage/vector_index_manager.py
   git rm tests/unit/storage/test_vector_index_manager.py
   git rm tests/e2e/test_binary_index_performance.py
   ```

2. **Verify no imports remain**:
   ```bash
   grep -r "VectorIndexManager" src/ tests/
   grep -r "vector_index_manager" src/ tests/
   ```

### Phase 2: Simplify filesystem_vector_store.py
**Goal**: Remove all binary index code paths and fallbacks

1. **Remove binary index search path** (lines 1223-1340):
   - Delete entire "BINARY INDEX LOOKUP (FAST PATH)" section
   - Delete VectorIndexManager import

2. **Remove quantized lookup fallback** (lines 1341-1428):
   - Delete "QUANTIZED DIRECTORY LOOKUP" section
   - This was the O(√N) fallback when binary index missing

3. **Remove full scan fallback** (lines 1429-1520):
   - Delete "FULL COLLECTION SCAN (LAST RESORT)" section
   - This was the O(N) ultimate fallback

4. **Remove HNSW fallback logic** (lines 1107-1115, 1214-1222):
   - Delete try/except that catches HNSW errors and falls back
   - If HNSW fails, query should FAIL (no silent degradation)
   - Update to: raise exception with clear error message

5. **Remove set_index_type() method** (lines 2147-2192):
   - No longer needed since only HNSW exists
   - Delete entire method

6. **Simplify collection metadata**:
   - Remove `index_type` and `index_format` fields from metadata creation (line 113-115)
   - Keep only: name, vector_size, created_at, quantization_range, index_version, hnsw_index

7. **Update search() method signature**:
   - Remove all references to `index_type` variable
   - Remove metadata check for index type (lines 1073-1078)
   - Start directly with HNSW path

### Phase 3: Simplify CLI
**Goal**: Remove index type selection, make HNSW transparent

1. **Remove --index-type flag** (cli.py lines 2093-2098):
   ```python
   # DELETE THIS:
   @click.option(
       "--index-type",
       type=click.Choice(["binary", "hnsw"], case_sensitive=False),
       default="hnsw",
       help="Type of vector index: binary (fast build, 8s queries) or hnsw (slow build, 50ms queries)",
   )
   ```

2. **Remove index_type parameter**:
   - From `index()` function signature (line 2101+)
   - From all internal calls

3. **Remove set_index_type() call** (lines 2565-2568):
   ```python
   # DELETE THIS:
   vector_store_client.set_index_type(
       collection_name, index_type.lower()
   )
   console.print(f"📊 Using {index_type} index type")
   ```

4. **Simplify timing display**:
   - Remove `hamming_search_ms` from breakdown keys (line 660)
   - Remove `quantized_lookup_ms` from breakdown keys (line 662)
   - Remove `full_scan_ms` from breakdown keys (line 663)
   - Remove corresponding labels (lines 678, 680, 681)
   - Remove dynamic index type label logic (lines 667-671) - always "HNSW index load"

5. **Simplify search_path display**:
   - Remove path_emoji entries for binary_index, quantized_lookup, full_scan (lines 710-711)
   - Only keep: hnsw_index (⚡), none (❌)

### Phase 4: Update Help Text
**Goal**: Remove references to binary index from user-facing docs

1. **Update --rebuild-index help**:
   ```python
   # BEFORE:
   help="Rebuild vector index from existing vector files (filesystem backend only)"

   # AFTER:
   help="Rebuild HNSW index from existing vector files (filesystem backend only)"
   ```

2. **Update index command examples**:
   ```python
   # REMOVE:
   code-indexer index --index-type hnsw
   code-indexer index --index-type hnsw --clear

   # KEEP (simplified):
   code-indexer index
   code-indexer index --rebuild-index
   code-indexer index --clear
   ```

### Phase 5: Update Tests
**Goal**: Remove or update tests that reference binary index

1. **Search for binary index references**:
   ```bash
   grep -r "binary.*index\|hamming\|quantized.*lookup" tests/
   ```

2. **Update filesystem vector store tests**:
   - Remove tests for binary index paths
   - Remove tests for fallback behavior
   - Keep only HNSW path tests

3. **Update integration tests**:
   - Remove `test_filesystem_vector_store_index.py` if it tests binary
   - Keep only `test_hnsw_filesystem_integration.py`

### Phase 6: Clean Up Timing Keys
**Goal**: Remove unused timing keys from codebase

1. **Search for timing key usage**:
   ```bash
   grep -r "hamming_search_ms\|quantized_lookup_ms\|full_scan_ms" src/
   ```

2. **Remove from filesystem_vector_store.py**:
   - Delete all `timing['hamming_search_ms'] = ...` assignments
   - Delete all `timing['quantized_lookup_ms'] = ...` assignments
   - Delete all `timing['full_scan_ms'] = ...` assignments

3. **Keep only HNSW timing keys**:
   - `matrix_load_ms`
   - `index_load_ms` (rename to `hnsw_index_load_ms` for clarity)
   - `hnsw_search_ms`
   - `id_index_load_ms`
   - `candidate_load_ms`
   - `staleness_detection_ms`

---

## Migration Strategy

### For Existing Users

**Option 1: Automatic Migration (Recommended)**
- On first query with new version, detect missing HNSW index
- Automatically rebuild HNSW from existing vectors
- Display: "Upgrading to HNSW index (one-time, ~5 min)..."

**Option 2: Manual Migration (Simpler)**
- Document in CHANGELOG: "Run `cidx index --rebuild-index` after upgrade"
- Fail gracefully with helpful error if HNSW index missing

**Recommendation**: Use Option 2 for simplicity.

### Error Messages

**Before** (confusing fallback):
```
Warning: HNSW index not found, falling back to binary index
Warning: Binary index not found, falling back to quantized lookup
Warning: Quantized lookup failed, falling back to full scan
Query took 6.2 seconds (full scan)
```

**After** (clear failure):
```
❌ Error: HNSW index not found for collection 'voyage-code-3'

This collection was created with an older version.
Please rebuild the index:

  cidx index --rebuild-index

This will rebuild the HNSW index from existing vectors (~5 minutes).
```

---

## Validation Checklist

### Code Validation
- [ ] No references to `VectorIndexManager` in codebase
- [ ] No references to `vector_index.bin` in code
- [ ] No `--index-type` flag in CLI
- [ ] No `index_type` in collection metadata
- [ ] No fallback paths from HNSW errors
- [ ] All timing keys simplified to HNSW-only
- [ ] All tests pass with only HNSW path

### Functional Validation
- [ ] Fresh index creation works (HNSW built automatically)
- [ ] `--rebuild-index` works (rebuilds HNSW from vectors)
- [ ] Queries use HNSW path exclusively
- [ ] Timing display shows only HNSW breakdown
- [ ] Error messages are clear when HNSW missing
- [ ] No performance regression

### Documentation Validation
- [ ] README updated (remove binary index references)
- [ ] Help text updated (remove --index-type)
- [ ] Examples updated (no binary index examples)
- [ ] CHANGELOG documents breaking change

---

## Files Affected Summary

### Deleted (3 files)
1. `src/code_indexer/storage/vector_index_manager.py`
2. `tests/unit/storage/test_vector_index_manager.py`
3. `tests/e2e/test_binary_index_performance.py`

### Modified (2 core files)
1. `src/code_indexer/storage/filesystem_vector_store.py`
   - ~500 lines deleted (binary index paths, fallbacks)
   - ~50 lines simplified (metadata, search logic)

2. `src/code_indexer/cli.py`
   - ~20 lines deleted (--index-type flag)
   - ~10 lines simplified (timing display)

### Modified (minor changes)
3. `src/code_indexer/storage/__init__.py` - Remove VectorIndexManager export
4. `tests/integration/storage/test_filesystem_vector_store_index.py` - Update or delete
5. `tests/unit/storage/test_filesystem_hnsw_integration.py` - Update if needed

**Total impact**: ~570 lines deleted, ~60 lines simplified = **~630 line reduction**

---

## Estimated Effort

| Phase | Effort | Risk |
|-------|--------|------|
| Phase 1: Delete files | 5 min | Low |
| Phase 2: Simplify filesystem_vector_store | 30 min | Medium |
| Phase 3: Simplify CLI | 15 min | Low |
| Phase 4: Update help text | 10 min | Low |
| Phase 5: Update tests | 20 min | Medium |
| Phase 6: Clean up timing | 10 min | Low |
| **Total** | **90 min** | **Low-Medium** |

---

## Success Criteria

1. **Code simplicity**: 600+ lines removed, no index type selection
2. **Performance**: Queries consistently ~20ms (no fallback degradation)
3. **UX**: Clear error messages when HNSW missing
4. **Tests**: All tests pass with HNSW-only path
5. **Migration**: Existing users can rebuild with `--rebuild-index`

---

## Follow-Up Tasks

After removal:
1. Update README with HNSW performance benefits
2. Document migration in CHANGELOG
3. Consider adding HNSW tuning parameters (M, ef_construction)
4. Monitor for any edge cases in production use

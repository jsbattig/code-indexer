# Filename-Based ID Index Loading Optimization

## Problem
Current `_load_id_index()` parses ALL JSON files to extract both point IDs and file paths:
- Evolution: 37,855 files → 7,551ms  
- Code-indexer: 4,444 files → 926ms

## Key Insight
**Point IDs are already in filenames:** `vector_POINTID.json`

We can extract IDs from filenames (345ms) instead of parsing JSON (7,551ms).

## Solution: Lazy File Path Loading

Split loading into two phases:

### Phase 1: ID Index (Fast - from filenames only)
```python
def _load_id_index(self, collection_name: str) -> Dict[str, Path]:
    """Load ID index from filenames only - no file I/O."""
    index = {}
    for json_file in collection_path.rglob("vector_*.json"):
        # Extract point ID from filename
        filename = json_file.name
        if filename.startswith("vector_") and filename.endswith(".json"):
            point_id = filename[7:-5]  # "vector_" is 7 chars, ".json" is 5 chars
            index[point_id] = json_file
    return index
```
**Performance**: 345ms (22x faster!)

### Phase 2: File Paths (Lazy - only when needed)
```python
def get_all_indexed_files(self, collection_name: str) -> List[str]:
    """Get file paths - loads lazily if not cached."""
    with self._id_index_lock:
        if collection_name not in self._id_index:
            self._id_index[collection_name] = self._load_id_index(collection_name)
        
        # Check if file paths are cached
        if collection_name not in self._file_path_cache:
            # Load file paths by parsing JSON (only if needed)
            self._file_path_cache[collection_name] = self._load_file_paths(
                collection_name, self._id_index[collection_name]
            )
        
        file_paths = self._file_path_cache[collection_name]
    
    return sorted(list(file_paths))

def _load_file_paths(self, collection_name: str, id_index: Dict[str, Path]) -> set:
    """Load file paths from JSON files."""
    file_paths = set()
    for json_file in id_index.values():
        try:
            with open(json_file) as f:
                data = json.load(f)
            file_path = data.get("payload", {}).get("path") or data.get("file_path", "")
            if file_path:
                file_paths.add(file_path)
        except:
            pass
    return file_paths
```

## Performance Impact

### For Operations That Only Need Vector Count
- **Before**: 7,551ms (parse all JSON)
- **After**: 345ms (extract from filenames)
- **Speedup**: 22x faster

### For cidx status (needs both count AND files)
- First call: 345ms (IDs) + 7,000ms (file paths) = 7,345ms
- Subsequent: Uses cache = 0ms

## Changes Required

**File**: `src/code_indexer/storage/filesystem_vector_store.py`

1. **Update `_load_id_index()`** (line ~673) - Extract IDs from filenames only, remove JSON parsing
2. **Add `_load_file_paths()` method** - New method to parse JSON for file paths
3. **Update `get_all_indexed_files()`** (line ~1903) - Call `_load_file_paths()` lazily

## Expected Results

Evolution codebase:
- **Before**: 12.6s total (7.6s ID index + 5s other)
- **After**: 5.9s total (0.3s ID index + 5s other)  
- **Improvement**: 6.7s faster (53% improvement)

Code-indexer codebase:
- **Before**: 2.6s total (0.9s ID index + 1.7s other)
- **After**: 2.0s total (0.3s ID index + 1.7s other)
- **Improvement**: 0.6s faster (23% improvement)

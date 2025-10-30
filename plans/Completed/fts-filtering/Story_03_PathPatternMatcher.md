# Story: Improve Path Filtering with PathPatternMatcher

## Story Description

**As a** developer maintaining code consistency
**I want to** use PathPatternMatcher for FTS path filtering instead of fnmatch
**So that** FTS and semantic search have identical path matching behavior

**Conversation Context:**
- User requested FTS filtering to mirror semantic search implementation
- Semantic search uses `PathPatternMatcher` class for path filtering
- FTS currently uses Python's `fnmatch` module (simple implementation)
- Need consistency across both search modes for predictable user experience

## Acceptance Criteria

- [x] FTS path filtering uses `PathPatternMatcher` instead of `fnmatch`
- [x] Pattern matching behavior identical to semantic search
- [x] All existing path filter tests continue to pass
- [x] Cross-platform path separator handling (/ and \) works correctly
- [x] Complex glob patterns work: `"**/vendor/**"`, `"*.min.js"`, `"*/tests/*"`
- [x] Performance remains <1s for typical queries
- [x] No regression in existing path filter functionality

## Technical Implementation

### Core Change

**File**: `src/code_indexer/services/tantivy_index_manager.py`

```python
# BEFORE (lines 455-459):
if path_filter:
    import fnmatch
    if not fnmatch.fnmatch(path, path_filter):
        continue

# AFTER:
if path_filter:
    from code_indexer.services.path_pattern_matcher import PathPatternMatcher
    matcher = PathPatternMatcher()
    if not matcher.matches_pattern(path, path_filter):
        continue
```

### PathPatternMatcher Overview

The existing `PathPatternMatcher` class provides:

```python
# Already exists in src/code_indexer/services/path_pattern_matcher.py
class PathPatternMatcher:
    """
    Cross-platform path pattern matcher with glob support.

    Features:
    - Normalizes path separators (/ and \)
    - Supports glob wildcards: *, **, ?, [...]
    - Case-insensitive on Windows, case-sensitive on Unix
    - Consistent behavior across platforms
    """

    def matches_pattern(self, path: str, pattern: str) -> bool:
        """
        Check if path matches glob pattern.

        Args:
            path: File path to check
            pattern: Glob pattern (e.g., "*/tests/*", "**.min.js")

        Returns:
            True if path matches pattern, False otherwise
        """
        # Implementation uses pathlib.Path.match() for robust matching
```

### Performance Optimization

To avoid creating a new `PathPatternMatcher` instance for every result, consider instance caching:

```python
def search(
    self,
    query_text: str,
    ...
    path_filter: Optional[str] = None,
    ...
):
    # ... existing search code ...

    # Create matcher once before loop (if path_filter exists)
    path_matcher = None
    if path_filter:
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher
        path_matcher = PathPatternMatcher()

    # Process results
    for score, address in search_results:
        doc = searcher.doc(address)
        path = doc.get_first("path") or ""
        # ... extract other fields ...

        # Apply language filters
        if languages:
            # ... existing language filter code ...

        # Apply path filter with cached matcher
        if path_matcher and not path_matcher.matches_pattern(path, path_filter):
            continue

        # ... rest of result processing ...
```

## Test Requirements

### Unit Tests

**File**: `tests/unit/services/test_tantivy_path_pattern_matcher.py`

```python
def test_path_matcher_simple_pattern(indexed_tantivy_store):
    """GIVEN indexed repo with structured directories
       WHEN searching with simple pattern '*/tests/*'
       THEN only files in tests directories match"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("test", path_filter="*/tests/*")

    assert len(results) > 0
    for result in results:
        assert "/tests/" in result["path"] or "\\tests\\" in result["path"]

def test_path_matcher_double_star_pattern(indexed_tantivy_store):
    """GIVEN indexed repo with nested directories
       WHEN searching with double-star pattern '**/vendor/**'
       THEN files at any depth in vendor directories match"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("package", path_filter="**/vendor/**")

    assert len(results) > 0
    for result in results:
        assert "vendor" in result["path"]

def test_path_matcher_extension_pattern(indexed_tantivy_store):
    """GIVEN indexed repo with minified files
       WHEN searching with pattern '*.min.js'
       THEN only minified JS files match"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("function", path_filter="*.min.js")

    assert len(results) > 0
    for result in results:
        assert result["path"].endswith(".min.js")

def test_path_matcher_cross_platform_separators(indexed_tantivy_store):
    """GIVEN indexed repo
       WHEN searching with pattern using forward slashes
       THEN matches work on both Unix and Windows paths"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("test", path_filter="src/tests/unit/*")

    # Should match both "src/tests/unit/test.py" and "src\\tests\\unit\\test.py"
    assert len(results) > 0

def test_path_matcher_backward_compatibility(indexed_tantivy_store):
    """GIVEN existing test suite using fnmatch patterns
       WHEN switching to PathPatternMatcher
       THEN all existing patterns still work"""
    manager = TantivyIndexManager(index_dir)

    # Test patterns that worked with fnmatch
    patterns = [
        "*/tests/*",
        "*.py",
        "**/vendor/**",
        "src/*",
        "dist/*.min.js"
    ]

    for pattern in patterns:
        results = manager.search("test", path_filter=pattern)
        # Should not raise errors, may return empty results
        assert isinstance(results, list)
```

### Integration Tests

**File**: `tests/e2e/test_fts_path_pattern_matcher.py`

```python
def test_cli_complex_glob_pattern(tmp_path):
    """Test complex glob patterns via CLI"""
    setup_nested_repo(tmp_path)

    # Test double-star pattern
    result = subprocess.run(
        ["cidx", "query", "config", "--fts", "--path-filter", "**/config/**"],
        capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 0
    assert "config" in result.stdout

def test_cli_cross_platform_paths(tmp_path):
    """Test that patterns work regardless of platform"""
    setup_test_repo(tmp_path)

    # Use forward slashes in pattern (should work on Windows too)
    result = subprocess.run(
        ["cidx", "query", "test", "--fts", "--path-filter", "src/tests/*"],
        capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 0

def test_semantic_fts_parity(tmp_path):
    """Test that FTS and semantic search match same files with same pattern"""
    setup_test_repo(tmp_path)
    pattern = "*/tests/*"

    # Get FTS results
    fts_result = subprocess.run(
        ["cidx", "query", "test", "--fts", "--path-filter", pattern, "--quiet"],
        capture_output=True, text=True, cwd=tmp_path
    )

    # Get semantic results
    semantic_result = subprocess.run(
        ["cidx", "query", "test", "--path-filter", pattern, "--quiet"],
        capture_output=True, text=True, cwd=tmp_path
    )

    # Extract file paths from both results
    fts_paths = extract_file_paths(fts_result.stdout)
    semantic_paths = extract_file_paths(semantic_result.stdout)

    # Same set of files should match
    assert fts_paths == semantic_paths
```

### Manual Test Scenarios

1. **Simple Pattern**:
   ```bash
   cidx query "test" --fts --path-filter "*/tests/*"
   # Expected: Only test directory files
   ```

2. **Double-Star Pattern**:
   ```bash
   cidx query "vendor" --fts --path-filter "**/vendor/**"
   # Expected: Files at any depth in vendor directories
   ```

3. **Extension Pattern**:
   ```bash
   cidx query "minified" --fts --path-filter "*.min.js"
   # Expected: Only .min.js files
   ```

4. **Cross-Platform Test** (on Windows):
   ```bash
   cidx query "test" --fts --path-filter "src/tests/*"
   # Expected: Matches src\tests\ files on Windows
   ```

5. **Semantic Parity**:
   ```bash
   cidx query "config" --path-filter "*/config/*" --quiet > semantic.txt
   cidx query "config" --fts --path-filter "*/config/*" --quiet > fts.txt
   diff semantic.txt fts.txt
   # Expected: Same files in both outputs
   ```

## Performance Considerations

- **Instance Creation**: Creating `PathPatternMatcher` once per search: ~0.1ms
- **Pattern Matching**: `matches_pattern()` call per result: ~0.5-1ms
- **Total Overhead**: ~1-2ms for typical queries with path filters
- **No Regression**: Same performance as fnmatch (both are O(1) per path)
- **Caching**: Reuse matcher instance across results for efficiency

## Dependencies

- Existing `PathPatternMatcher` class (`src/code_indexer/services/path_pattern_matcher.py`)
- No new dependencies required
- Python `pathlib` module (already used by PathPatternMatcher)

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Subtle matching behavior changes | Medium | Comprehensive regression testing |
| Performance degradation | Low | PathPatternMatcher as fast as fnmatch |
| Breaking existing patterns | Medium | Test suite covers all pattern types |
| Platform-specific edge cases | Low | PathPatternMatcher already handles this |

## Success Metrics

- All existing path filter tests pass
- New pattern types (double-star) work correctly
- FTS and semantic search have identical matching behavior
- Zero performance regression
- No user-reported matching discrepancies

## Notes

**Implementation Order**: Story 3 of 6. Depends on Story 2 (path filter wiring).

**Quality Improvement**: This story improves code consistency and maintainability without adding new features.

**User Impact**: Transparent to users - same patterns work, but more reliably across platforms.

**Future Proofing**: When path matching behavior needs changes, only PathPatternMatcher needs updating.

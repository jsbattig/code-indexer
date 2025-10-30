# Story: Add --exclude-path Support for FTS

## Story Description

**As a** developer searching code
**I want to** exclude specific paths from FTS results using `--exclude-path` flag
**So that** I can filter out irrelevant directories like node_modules, dist, vendor

**Conversation Context:**
- User requested feature parity with semantic search filtering
- Semantic search supports `--exclude-path` for filtering out unwanted paths
- Common use case: exclude build artifacts, dependencies, generated code
- Exclusions take precedence over inclusions (standard filtering behavior)

## Acceptance Criteria

- [x] Running `cidx query "function" --fts --exclude-path "*/node_modules/*"` excludes node_modules directory
- [x] Running `cidx query "config" --fts --exclude-path "*/tests/*" --exclude-path "*/vendor/*"` excludes multiple directories
- [x] Exclusions work with inclusions: `--path-filter "*/src/*" --exclude-path "*/src/legacy/*"` includes src but excludes src/legacy
- [x] Exclusion takes precedence over inclusion when paths conflict
- [x] Exclusions work with language filters
- [x] Exclusions work with fuzzy and case-sensitive search
- [x] Performance remains <1s even with multiple exclusions

## Technical Implementation

### CLI Changes

**File**: `src/code_indexer/cli.py`

```python
# Add new option
@click.option(
    "--exclude-path",
    type=str,
    multiple=True,
    help="Exclude paths matching pattern (can be specified multiple times, takes precedence over --path-filter)",
)
def query(
    ...
    path_filter: tuple[str, ...],
    exclude_path: tuple[str, ...],  # New parameter
    ...
):
    # FTS mode
    elif search_mode == "fts":
        try:
            tantivy_manager = TantivyIndexManager(fts_index_dir)
            tantivy_manager.initialize_index(create_new=False)
            fts_results = tantivy_manager.search(
                query_text=query,
                case_sensitive=case_sensitive,
                edit_distance=edit_distance,
                snippet_lines=snippet_lines,
                limit=limit,
                languages=list(languages) if languages else None,
                path_filters=list(path_filter) if path_filter else None,
                exclude_paths=list(exclude_path) if exclude_path else None,  # New parameter
            )
```

### Core Implementation

**File**: `src/code_indexer/services/tantivy_index_manager.py`

```python
def search(
    self,
    query_text: str,
    case_sensitive: bool = False,
    edit_distance: int = 0,
    snippet_lines: int = 5,
    limit: int = 10,
    languages: Optional[List[str]] = None,
    path_filters: Optional[List[str]] = None,
    exclude_paths: Optional[List[str]] = None,  # NEW parameter
    path_filter: Optional[str] = None,  # Deprecated
    query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search the FTS index with configurable options.

    Args:
        query_text: Search query string
        case_sensitive: Enable case-sensitive matching
        edit_distance: Fuzzy matching tolerance (0-2)
        snippet_lines: Context lines to include in snippet
        limit: Maximum number of results
        languages: Filter by programming languages
        path_filters: Include paths matching patterns (OR logic)
        exclude_paths: Exclude paths matching patterns (OR logic, takes precedence)
        path_filter: DEPRECATED - use path_filters
        query: Backwards compatibility parameter

    Returns:
        List of search results
    """
    # ... existing search code ...

    # Create matchers once before loop
    path_matcher = None
    exclude_matcher = None

    if path_filters or exclude_paths:
        from code_indexer.services.path_pattern_matcher import PathPatternMatcher
        path_matcher = PathPatternMatcher()
        exclude_matcher = PathPatternMatcher()  # Use same class instance

    # Process results
    for score, address in search_results:
        doc = searcher.doc(address)
        path = doc.get_first("path") or ""
        # ... extract other fields ...

        # Apply language filters
        if languages:
            # ... existing language filter code ...

        # CRITICAL: Apply exclusions FIRST (before inclusions)
        # Exclusions take precedence - if path matches any exclusion pattern, exclude it
        if exclude_matcher and exclude_paths:
            if any(exclude_matcher.matches_pattern(path, pattern) for pattern in exclude_paths):
                continue  # Skip this result

        # Apply inclusion path filters (match ANY pattern)
        if path_matcher and path_filters:
            if not any(path_matcher.matches_pattern(path, pattern) for pattern in path_filters):
                continue

        # ... rest of result processing ...
```

### Filter Precedence Logic

The implementation follows standard filtering precedence:

```python
# 1. EXCLUSIONS (processed first, takes precedence)
if path matches ANY exclusion pattern:
    EXCLUDE result

# 2. INCLUSIONS (processed second)
if path_filters specified:
    if path matches ANY inclusion pattern:
        INCLUDE result
    else:
        EXCLUDE result

# 3. NO FILTERS (default)
if no filters specified:
    INCLUDE result
```

**Example**:
- `--path-filter "*/src/*" --exclude-path "*/src/legacy/*"`
- File: `src/legacy/old.py`
- Result: EXCLUDED (matches inclusion but also matches exclusion)

## Test Requirements

### Unit Tests

**File**: `tests/unit/services/test_tantivy_exclude_path.py`

```python
def test_single_exclude_path(indexed_tantivy_store):
    """GIVEN indexed repo with node_modules directory
       WHEN searching with --exclude-path '*/node_modules/*'
       THEN no node_modules files are returned"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("function", exclude_paths=["*/node_modules/*"])

    assert len(results) > 0
    for result in results:
        assert "node_modules" not in result["path"]

def test_multiple_exclude_paths(indexed_tantivy_store):
    """GIVEN indexed repo with tests, vendor, and dist directories
       WHEN excluding multiple paths
       THEN none of the excluded directories appear in results"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search(
        "config",
        exclude_paths=["*/tests/*", "*/vendor/*", "*/dist/*"]
    )

    assert len(results) > 0
    for result in results:
        path = result["path"]
        assert "tests" not in path
        assert "vendor" not in path
        assert "dist" not in path

def test_exclude_with_include_path_filters(indexed_tantivy_store):
    """GIVEN indexed repo with src directory containing legacy subdirectory
       WHEN including src but excluding src/legacy
       THEN src files returned except legacy"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search(
        "function",
        path_filters=["*/src/*"],
        exclude_paths=["*/src/legacy/*"]
    )

    assert len(results) > 0
    for result in results:
        path = result["path"]
        assert "/src/" in path  # Must be in src
        assert "/legacy/" not in path  # But not in legacy

def test_exclusion_precedence_over_inclusion(indexed_tantivy_store):
    """GIVEN path that matches both inclusion and exclusion
       WHEN both filters applied
       THEN exclusion takes precedence"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search(
        "test",
        path_filters=["*/tests/*"],  # Include tests
        exclude_paths=["*/tests/slow/*"]  # But exclude tests/slow
    )

    # Should have test files
    assert len(results) > 0
    for result in results:
        path = result["path"]
        assert "/tests/" in path  # In tests directory
        assert "/slow/" not in path  # But not in slow subdirectory

def test_exclude_with_language_filter(indexed_tantivy_store):
    """GIVEN indexed repo
       WHEN combining exclusion and language filters
       THEN results match language AND do not match exclusions"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search(
        "function",
        languages=["python"],
        exclude_paths=["*/tests/*"]
    )

    assert len(results) > 0
    for result in results:
        assert result["language"] in ["py", "pyw", "pyi"]
        assert "tests" not in result["path"]

def test_no_exclusions_returns_all(indexed_tantivy_store):
    """GIVEN indexed repo
       WHEN no exclusions specified
       THEN all matching results returned"""
    manager = TantivyIndexManager(index_dir)
    results_without = manager.search("function", exclude_paths=None)
    results_with_empty = manager.search("function", exclude_paths=[])

    # Both should return results
    assert len(results_without) > 0
    assert len(results_with_empty) > 0
    # Should be same number of results
    assert len(results_without) == len(results_with_empty)
```

### Integration Tests

**File**: `tests/e2e/test_fts_exclude_path.py`

```python
def test_cli_exclude_node_modules(tmp_path):
    """Test excluding node_modules via CLI"""
    setup_repo_with_node_modules(tmp_path)

    result = subprocess.run(
        ["cidx", "query", "function", "--fts", "--exclude-path", "*/node_modules/*"],
        capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 0
    assert "node_modules" not in result.stdout

def test_cli_multiple_exclusions(tmp_path):
    """Test multiple --exclude-path flags"""
    setup_complex_repo(tmp_path)

    result = subprocess.run(
        ["cidx", "query", "config", "--fts",
         "--exclude-path", "*/tests/*",
         "--exclude-path", "*/vendor/*",
         "--exclude-path", "*.min.js"],
        capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 0
    assert "tests" not in result.stdout
    assert "vendor" not in result.stdout
    assert ".min.js" not in result.stdout

def test_cli_include_and_exclude(tmp_path):
    """Test combining inclusion and exclusion"""
    setup_complex_repo(tmp_path)

    result = subprocess.run(
        ["cidx", "query", "function", "--fts",
         "--path-filter", "*/src/*",
         "--exclude-path", "*/src/legacy/*"],
        capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 0
    assert "/src/" in result.stdout
    assert "legacy" not in result.stdout

def test_cli_exclusion_with_language(tmp_path):
    """Test exclusion combined with language filter"""
    setup_complex_repo(tmp_path)

    result = subprocess.run(
        ["cidx", "query", "test", "--fts",
         "--language", "python",
         "--exclude-path", "*/tests/*"],
        capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 0
    assert ".py" in result.stdout
    assert "tests" not in result.stdout
```

### Manual Test Scenarios

1. **Exclude Node Modules**:
   ```bash
   cidx query "function" --fts --exclude-path "*/node_modules/*"
   # Expected: No node_modules files
   ```

2. **Multiple Exclusions**:
   ```bash
   cidx query "config" --fts \
     --exclude-path "*/tests/*" \
     --exclude-path "*/vendor/*" \
     --exclude-path "*.min.js"
   # Expected: None of these patterns in results
   ```

3. **Include + Exclude**:
   ```bash
   cidx query "function" --fts \
     --path-filter "*/src/*" \
     --exclude-path "*/src/legacy/*"
   # Expected: src/ files except legacy/
   ```

4. **Precedence Test**:
   ```bash
   # Show src/legacy files exist
   cidx query "old" --fts --path-filter "*/src/legacy/*"

   # Show they're excluded when using both filters
   cidx query "old" --fts \
     --path-filter "*/src/*" \
     --exclude-path "*/src/legacy/*"
   # Expected: No legacy files despite matching inclusion
   ```

5. **With Language Filter**:
   ```bash
   cidx query "test" --fts \
     --language python \
     --exclude-path "*/tests/*"
   # Expected: Python files, but not in tests/
   ```

## Performance Considerations

- **Exclusion Check**: O(N) where N = number of exclusion patterns
- **Short-Circuit**: Stops on first matching exclusion
- **Typical Case**: 2-3 exclusions, <1ms per result
- **Expected Performance**: <1s total for typical queries

## Dependencies

- Existing `PathPatternMatcher` class
- Click's `multiple=True` option support
- Stories 1-4 (language filtering, path filtering infrastructure)

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Precedence confusion | Medium | Clear documentation, comprehensive tests |
| Performance with many exclusions | Low | Short-circuit on first match |
| Complex filter interactions | Medium | Extensive integration testing |

## Success Metrics

- All acceptance criteria passing
- Feature parity with semantic search
- Clear precedence behavior
- Zero performance regression
- Comprehensive documentation

## Notes

**Implementation Order**: Story 5 of 6. Depends on Stories 1-4 for filtering infrastructure.

**Precedence Rule**: Exclusions checked FIRST, before inclusions. This is standard behavior across filtering systems.

**Common Use Cases**:
- Exclude build artifacts: `--exclude-path "*/dist/*" --exclude-path "*/build/*"`
- Exclude dependencies: `--exclude-path "*/node_modules/*" --exclude-path "*/vendor/*"`
- Exclude tests: `--exclude-path "*/tests/*" --exclude-path "**/test_*"`

**Final Story**: Story 6 will add `--exclude-language` support, completing feature parity with semantic search.

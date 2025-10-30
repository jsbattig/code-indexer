# Story: Support Multiple Path Filters in FTS

## Story Description

**As a** developer searching code
**I want to** specify multiple `--path-filter` flags in one query
**So that** I can search across multiple directories without running separate queries

**Conversation Context:**
- User requested feature parity with semantic search filtering
- Semantic search supports multiple path filters with OR logic
- Current FTS implementation only accepts single path filter
- Multiple filters enable searches like "tests OR src" directories

## Acceptance Criteria

- [x] Running `cidx query "test" --fts --path-filter "*/tests/*" --path-filter "*/src/*"` returns files from tests OR src directories
- [x] Multiple path filters use OR logic (match ANY pattern)
- [x] Filters work with complex patterns: `--path-filter "**/config/**" --path-filter "*.config.js"`
- [x] Combined with language filter: `--language python --path-filter "*/tests/*" --path-filter "*/integration/*"`
- [x] Help text shows multiple filters supported
- [x] Performance remains <1s even with many filters
- [x] Single filter still works (backward compatibility)

## Technical Implementation

### CLI Changes

**File**: `src/code_indexer/cli.py`

```python
# BEFORE:
@click.option(
    "--path-filter",
    type=str,
    default=None,
    help="Filter FTS results by path pattern",
)

# AFTER:
@click.option(
    "--path-filter",
    type=str,
    multiple=True,  # Enable multiple values
    help="Filter FTS results by path patterns (can be specified multiple times, OR logic)",
)
def query(
    ...
    path_filter: tuple[str, ...],  # Now a tuple of strings
    ...
):
    # FTS mode (line 3799-3825)
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
                path_filters=list(path_filter) if path_filter else None,  # Convert tuple to list
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
    path_filters: Optional[List[str]] = None,  # CHANGED: plural, accepts list
    path_filter: Optional[str] = None,  # DEPRECATED: keep for backward compatibility
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
        languages: Filter by programming languages (e.g., ["python", "javascript"])
        path_filters: Filter by path patterns (e.g., ["*/tests/*", "*/src/*"]) - OR logic
        path_filter: DEPRECATED - use path_filters instead (singular for backward compatibility)
        query: Backwards compatibility parameter

    Returns:
        List of search results with path, line, column, snippet, language, score
    """
    # Handle backward compatibility
    if path_filter and not path_filters:
        path_filters = [path_filter]

    # ... existing search code ...

    # Create matcher once before loop (if path_filters exist)
    path_matcher = None
    if path_filters:
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

        # Apply path filters with OR logic (match ANY pattern)
        if path_matcher and path_filters:
            # Include result if it matches ANY of the path filters
            if not any(path_matcher.matches_pattern(path, pattern) for pattern in path_filters):
                continue

        # ... rest of result processing ...
```

### OR Logic Implementation

The key change is using `any()` for OR logic:

```python
# Single filter (implicit):
if not path_matcher.matches_pattern(path, path_filter):
    continue

# Multiple filters (explicit OR logic):
if not any(path_matcher.matches_pattern(path, pattern) for pattern in path_filters):
    continue
```

This means:
- If path matches ANY pattern → include result
- If path matches NO patterns → exclude result

## Test Requirements

### Unit Tests

**File**: `tests/unit/services/test_tantivy_multiple_path_filters.py`

```python
def test_multiple_path_filters_or_logic(indexed_tantivy_store):
    """GIVEN indexed repo with tests/ and src/ directories
       WHEN searching with multiple path filters
       THEN results match ANY of the patterns (OR logic)"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("function", path_filters=["*/tests/*", "*/src/*"])

    assert len(results) > 0
    for result in results:
        # Must match at least one pattern
        matches_tests = "/tests/" in result["path"]
        matches_src = "/src/" in result["path"]
        assert matches_tests or matches_src

def test_three_path_filters(indexed_tantivy_store):
    """GIVEN indexed repo with multiple directories
       WHEN searching with three path filters
       THEN results match any of the three patterns"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search(
        "config",
        path_filters=["*/config/*", "*.config.js", "**/settings/**"]
    )

    assert len(results) > 0
    for result in results:
        path = result["path"]
        matches_config_dir = "/config/" in path
        matches_config_file = path.endswith(".config.js")
        matches_settings = "/settings/" in path or "\\settings\\" in path
        assert matches_config_dir or matches_config_file or matches_settings

def test_multiple_path_filters_with_language(indexed_tantivy_store):
    """GIVEN indexed repo
       WHEN combining multiple path filters with language filter
       THEN results match (ANY path) AND (language)"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search(
        "test",
        path_filters=["*/tests/*", "*/integration/*"],
        languages=["python"]
    )

    assert len(results) > 0
    for result in results:
        # Must match at least one path pattern
        matches_tests = "/tests/" in result["path"]
        matches_integration = "/integration/" in result["path"]
        assert matches_tests or matches_integration

        # Must be Python
        assert result["language"] in ["py", "pyw", "pyi"]

def test_single_path_filter_backward_compat(indexed_tantivy_store):
    """GIVEN existing code using single path_filter parameter
       WHEN searching with deprecated path_filter
       THEN still works for backward compatibility"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("test", path_filter="*/tests/*")

    assert len(results) > 0
    for result in results:
        assert "/tests/" in result["path"]

def test_empty_path_filters_returns_all(indexed_tantivy_store):
    """GIVEN indexed repo
       WHEN searching with empty path_filters list
       THEN all results are returned"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("test", path_filters=[])

    assert len(results) > 0  # Should return all matches
```

### Integration Tests

**File**: `tests/e2e/test_fts_multiple_path_filters.py`

```python
def test_cli_multiple_path_filters(tmp_path):
    """Test multiple --path-filter flags via CLI"""
    setup_test_repo_structure(tmp_path)

    result = subprocess.run(
        ["cidx", "query", "function", "--fts",
         "--path-filter", "*/tests/*",
         "--path-filter", "*/src/*"],
        capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 0
    # Should have files from both tests and src
    assert "/tests/" in result.stdout or "/src/" in result.stdout

def test_cli_three_path_filters(tmp_path):
    """Test three path filters with complex patterns"""
    setup_test_repo_structure(tmp_path)

    result = subprocess.run(
        ["cidx", "query", "config", "--fts",
         "--path-filter", "*/config/*",
         "--path-filter", "*.config.js",
         "--path-filter", "**/settings/**"],
        capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 0
    # Should match at least one of the patterns
    has_config_dir = "/config/" in result.stdout
    has_config_file = ".config.js" in result.stdout
    has_settings = "settings" in result.stdout
    assert has_config_dir or has_config_file or has_settings

def test_cli_path_and_language_filters(tmp_path):
    """Test combining multiple path filters with language filter"""
    setup_test_repo_structure(tmp_path)

    result = subprocess.run(
        ["cidx", "query", "test", "--fts",
         "--path-filter", "*/tests/*",
         "--path-filter", "*/integration/*",
         "--language", "python"],
        capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 0
    assert ".py" in result.stdout
    assert ("/tests/" in result.stdout or "/integration/" in result.stdout)

def test_cli_backward_compat_single_filter(tmp_path):
    """Test that single --path-filter still works"""
    setup_test_repo_structure(tmp_path)

    result = subprocess.run(
        ["cidx", "query", "test", "--fts", "--path-filter", "*/tests/*"],
        capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 0
    assert "/tests/" in result.stdout
```

### Manual Test Scenarios

1. **Two Path Filters**:
   ```bash
   cidx query "test" --fts --path-filter "*/tests/*" --path-filter "*/src/*"
   # Expected: Files from tests OR src directories
   ```

2. **Three Complex Patterns**:
   ```bash
   cidx query "config" --fts \
     --path-filter "*/config/*" \
     --path-filter "*.config.js" \
     --path-filter "**/settings/**"
   # Expected: Matches any of the three patterns
   ```

3. **With Language Filter**:
   ```bash
   cidx query "function" --fts \
     --path-filter "*/tests/*" \
     --path-filter "*/integration/*" \
     --language python
   # Expected: Python files in tests OR integration
   ```

4. **Verify OR Logic**:
   ```bash
   # Count results for each filter individually
   cidx query "test" --fts --path-filter "*/tests/*" --quiet | wc -l
   cidx query "test" --fts --path-filter "*/src/*" --quiet | wc -l

   # Count combined (should be >= either individual count)
   cidx query "test" --fts --path-filter "*/tests/*" --path-filter "*/src/*" --quiet | wc -l
   # Expected: Combined count >= max(tests, src)
   ```

5. **Help Text**:
   ```bash
   cidx query --help | grep path-filter
   # Expected: Shows "(can be specified multiple times, OR logic)"
   ```

## Performance Considerations

- **Multiple Pattern Checks**: Using `any()` short-circuits on first match
- **Best Case**: O(1) if first pattern matches
- **Worst Case**: O(N) where N = number of patterns
- **Typical**: 2-3 patterns, <1ms overhead per result
- **Expected Performance**: <1s total for queries with multiple filters

## Dependencies

- Existing `PathPatternMatcher` class
- Click's `multiple=True` option support
- Python's `any()` built-in function

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Performance with many filters | Low | Short-circuit on first match, typically 2-3 filters |
| User confusion about OR vs AND | Medium | Clear help text and documentation |
| Breaking single-filter backward compat | High | Maintain deprecated path_filter parameter |
| Click tuple handling issues | Low | Extensive testing of CLI parameter passing |

## Success Metrics

- All acceptance criteria passing
- Backward compatibility maintained
- Zero performance regression
- Feature parity with semantic search
- Clear documentation

## Notes

**Implementation Order**: Story 4 of 6. Depends on Stories 1-3 (language filtering, path wiring, PathPatternMatcher).

**OR Logic Rationale**: OR logic matches user expectation - "show me files from tests OR src directories". AND logic would be too restrictive (file must be in BOTH directories - impossible).

**Future Enhancement**: Could add `--path-filter-mode` flag for AND/OR selection, but OR is correct default for 99% of use cases.

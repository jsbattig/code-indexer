# Story: Wire --path-filter Flag to FTS Queries

## Story Description

**As a** developer using FTS search
**I want to** filter results by path patterns using `--path-filter` flag
**So that** I can narrow search results to specific directories or file patterns

**Conversation Context:**
- User discovered `--path-filter` doesn't work with FTS (returns "No matches found")
- User requested: "can we add --language and --path-filter after the fact?"
- FTS `search()` method already accepts `path_filter` parameter (line 370)
- Basic filtering logic exists (line 455-459) using `fnmatch`
- CLI may not be wiring the flag correctly to FTS

## Acceptance Criteria

- [x] Running `cidx query "test" --fts --path-filter "*/tests/*"` returns only files in test directories
- [x] Running `cidx query "config" --fts --path-filter "*/server/*"` returns only files in server directory
- [x] Running `cidx query "util" --fts --path-filter "*.py"` returns only Python files
- [x] Path filter works correctly with fuzzy search
- [x] Path filter works correctly with case-sensitive search
- [x] Path filter works correctly combined with `--language` filter
- [x] Invalid patterns fail gracefully with clear error message
- [x] No path filter returns all results (backward compatibility)

**STATUS**: ✅ COMPLETE - All acceptance criteria met
**COMPLETION DATE**: 2025-10-29
**COMPLETION REPORT**: See `/home/jsbattig/Dev/code-indexer/STORY_02_COMPLETION_REPORT.md`

## Technical Implementation

### Verification Step

First, verify if `--path-filter` option exists in CLI:

```python
# In cli.py @query command decorators
# Check if this exists:
@click.option(
    "--path-filter",
    type=str,
    default=None,
    help="Filter results by path pattern (e.g., '*/tests/*')",
)
```

### CLI Changes (if needed)

**File**: `src/code_indexer/cli.py`

```python
# Add --path-filter option to query command if missing
@click.option(
    "--path-filter",
    type=str,
    default=None,
    help="Filter FTS results by path pattern (glob wildcards supported, e.g., '*/tests/*', '*.py')",
)
def query(
    ...
    path_filter: Optional[str] = None,  # Ensure parameter exists
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
                path_filter=path_filter,  # VERIFY: This line passes path_filter
            )
            # ... rest of code ...
```

### Tantivy Index Manager (Existing Code)

The filtering logic already exists at lines 455-459:

```python
# This code already works:
if path_filter:
    import fnmatch
    if not fnmatch.fnmatch(path, path_filter):
        continue
```

**No changes needed** to `tantivy_index_manager.py` - the filtering logic is already correct.

### Help Text Verification

Ensure `cidx query --help` shows the path-filter option:

```
--path-filter TEXT     Filter FTS results by path pattern (glob wildcards
                       supported, e.g., '*/tests/*', '*.py')
```

## Test Requirements

### Unit Tests

**File**: `tests/unit/services/test_tantivy_path_filter.py`

```python
def test_path_filter_tests_directory(indexed_tantivy_store):
    """GIVEN indexed repo with tests and src directories
       WHEN searching with --path-filter '*/tests/*'
       THEN only test files are returned"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("test", path_filter="*/tests/*")

    assert len(results) > 0
    for result in results:
        assert "/tests/" in result["path"]

def test_path_filter_file_extension(indexed_tantivy_store):
    """GIVEN indexed repo with .py and .js files
       WHEN searching with --path-filter '*.py'
       THEN only Python files are returned"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("function", path_filter="*.py")

    assert len(results) > 0
    for result in results:
        assert result["path"].endswith(".py")

def test_path_filter_with_language(indexed_tantivy_store):
    """GIVEN indexed repo
       WHEN searching with both path and language filters
       THEN results match BOTH filters"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search(
        "test",
        path_filter="*/tests/*",
        languages=["python"]
    )

    assert len(results) > 0
    for result in results:
        assert "/tests/" in result["path"]
        assert result["language"] in ["py", "pyw", "pyi"]

def test_path_filter_no_match_returns_empty(indexed_tantivy_store):
    """GIVEN indexed repo
       WHEN searching with non-matching path filter
       THEN empty results are returned"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("test", path_filter="*/nonexistent/*")

    assert len(results) == 0

def test_no_path_filter_returns_all(indexed_tantivy_store):
    """GIVEN indexed repo
       WHEN searching without path filter
       THEN all matching files are returned"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("test", path_filter=None)

    assert len(results) > 0
```

### Integration Tests

**File**: `tests/e2e/test_fts_path_filter.py`

```python
def test_cli_path_filter_tests_directory(tmp_path):
    """Test --path-filter '*/tests/*' with FTS"""
    # Setup: Create repo with tests/ and src/ directories
    setup_test_repo_with_structure(tmp_path)

    # Execute
    result = subprocess.run(
        ["cidx", "query", "function", "--fts", "--path-filter", "*/tests/*"],
        capture_output=True, text=True, cwd=tmp_path
    )

    # Verify
    assert result.returncode == 0
    assert "/tests/" in result.stdout
    assert "/src/" not in result.stdout

def test_cli_path_filter_with_language(tmp_path):
    """Test combining --path-filter and --language"""
    setup_test_repo_with_structure(tmp_path)

    result = subprocess.run(
        ["cidx", "query", "test", "--fts",
         "--path-filter", "*/tests/*",
         "--language", "python"],
        capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 0
    assert "/tests/" in result.stdout
    assert ".py" in result.stdout

def test_cli_path_filter_extension(tmp_path):
    """Test --path-filter '*.py' to filter by extension"""
    setup_test_repo_with_structure(tmp_path)

    result = subprocess.run(
        ["cidx", "query", "import", "--fts", "--path-filter", "*.py"],
        capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 0
    assert ".py" in result.stdout
    assert ".js" not in result.stdout
```

### Manual Test Scenarios

1. **Basic Path Filter**:
   ```bash
   cidx index --fts
   cidx query "test" --fts --path-filter "*/tests/*"
   # Expected: Only files in tests/ directories
   ```

2. **Extension Filter**:
   ```bash
   cidx query "function" --fts --path-filter "*.py"
   # Expected: Only *.py files
   ```

3. **Server Directory Filter**:
   ```bash
   cidx query "config" --fts --path-filter "*/server/*"
   # Expected: Only files in server/ directory
   ```

4. **Combined with Language**:
   ```bash
   cidx query "test" --fts --path-filter "*/tests/*" --language python
   # Expected: Only Python test files
   ```

5. **No Match**:
   ```bash
   cidx query "test" --fts --path-filter "*/nonexistent/*"
   # Expected: "No matches found"
   ```

6. **Help Text**:
   ```bash
   cidx query --help | grep path-filter
   # Expected: Shows --path-filter option with description
   ```

## Performance Considerations

- **Post-Search Filtering**: fnmatch adds ~1-2ms per result
- **Pattern Compilation**: fnmatch compiles pattern once per search
- **Expected Performance**: <1s total for typical queries
- **No Tantivy Impact**: Filtering done in Python after search

## Dependencies

- Python's `fnmatch` module (already imported)
- Existing FTS infrastructure
- CLI `--path-filter` option (may need to add)

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| CLI flag already exists but broken | Medium | Verify and fix parameter passing |
| fnmatch pattern syntax confusion | Low | Clear help text with examples |
| Performance with complex patterns | Low | fnmatch is optimized, <2ms overhead |
| Cross-platform path separators | Medium | fnmatch handles / and \ automatically |

## Success Metrics

- All acceptance criteria passing
- Zero performance regression
- Feature parity with semantic search path filtering
- All tests passing
- Clear help documentation

## Notes

**Implementation Order**: Story 2 of 6. Depends on Story 1 (language filtering) for combined filter testing.

**Quick Win**: Most code already exists - likely just need to verify CLI wiring.

**Next Story**: Story 3 will improve this by replacing fnmatch with PathPatternMatcher for consistency with semantic search.

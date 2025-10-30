# Story: Multi-Language Filtering for FTS Queries

## Story Description

**As a** developer using FTS search
**I want to** filter results by multiple programming languages using `--language` flag
**So that** I can narrow search results to specific languages just like semantic search

**Conversation Context:**
- User discovered `--language` filter doesn't work with FTS (returns "No matches found")
- User explicitly requested: "can we add --language and --path-filter after the fact? after all, we do filter after the fact with semantic"
- FTS already has post-search filtering infrastructure but only supports single exact language match
- Need feature parity with semantic search which maps language names to file extensions

## Acceptance Criteria

- [x] Running `cidx query "test" --fts --language python` returns Python files (py, pyw, pyi extensions)
- [x] Running `cidx query "function" --fts --language javascript` returns JavaScript files (js, jsx extensions)
- [x] Running `cidx query "class" --fts --language python --language javascript` returns Python OR JavaScript files
- [x] Language filter works correctly with fuzzy search: `cidx query "tst" --fts --fuzzy --language python`
- [x] Language filter works correctly with case-sensitive search
- [x] Unknown language returns empty results gracefully
- [x] No language filter returns all results (backward compatibility)
- [x] Performance remains <1s for typical queries with language filters

## Technical Implementation

### Entry Point (CLI)

```python
# In cli.py query command (line 3806-3814)
# BEFORE:
fts_results = tantivy_manager.search(
    query_text=query,
    case_sensitive=case_sensitive,
    edit_distance=edit_distance,
    snippet_lines=snippet_lines,
    limit=limit,
    language_filter=languages[0] if languages else None,  # Wrong: only first language
    path_filter=path_filter,
)

# AFTER:
fts_results = tantivy_manager.search(
    query_text=query,
    case_sensitive=case_sensitive,
    edit_distance=edit_distance,
    snippet_lines=snippet_lines,
    limit=limit,
    languages=list(languages) if languages else None,  # Correct: pass all languages
    path_filter=path_filter,
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
    languages: Optional[List[str]] = None,  # CHANGED: was language_filter: Optional[str]
    path_filter: Optional[str] = None,
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
        path_filter: Filter by path pattern (e.g., "*/tests/*")
        query: Backwards compatibility parameter

    Returns:
        List of search results with path, line, column, snippet, language, score
    """
    # ... existing code until line 451 ...

    # REPLACE lines 451-459 with improved language filtering:

    # Apply language filters (OR logic across extensions from all languages)
    if languages:
        from code_indexer.services.language_mapper import LanguageMapper
        mapper = LanguageMapper()

        # Build set of allowed extensions from all specified languages
        allowed_extensions = set()
        for lang in languages:
            extensions = mapper.get_extensions(lang)
            if extensions:  # Only add if language is recognized
                allowed_extensions.update(extensions)

        # Filter: language extension must be in allowed set
        # Note: language is already parsed from facet format (line 449)
        if allowed_extensions and language not in allowed_extensions:
            continue

    # Apply path filter (keep existing logic for now)
    if path_filter:
        import fnmatch
        if not fnmatch.fnmatch(path, path_filter):
            continue

    # ... rest of existing code ...
```

### Language Mapping

The implementation reuses the existing `LanguageMapper` class that semantic search uses:

```python
# Already exists in src/code_indexer/services/language_mapper.py
class LanguageMapper:
    def get_extensions(self, language: str) -> Set[str]:
        """
        Map language name to file extensions.

        Examples:
            "python" → {"py", "pyw", "pyi"}
            "javascript" → {"js", "jsx"}
            "typescript" → {"ts", "tsx"}
        """
        # Existing implementation
```

### Backward Compatibility

Maintain deprecated `language_filter` parameter for backward compatibility:

```python
def search(
    self,
    query_text: str,
    ...
    languages: Optional[List[str]] = None,
    language_filter: Optional[str] = None,  # DEPRECATED
    ...
):
    # Handle deprecated parameter
    if language_filter and not languages:
        languages = [language_filter]
```

## Test Requirements

### Unit Tests

**File**: `tests/unit/services/test_tantivy_language_filter.py`

```python
def test_single_language_filter_python(indexed_tantivy_store):
    """GIVEN indexed repo with Python, JavaScript, TypeScript files
       WHEN searching with --language python
       THEN only Python files (py, pyw, pyi) are returned"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("test", languages=["python"])

    assert len(results) > 0
    for result in results:
        assert result["language"] in ["py", "pyw", "pyi"]

def test_multiple_language_filter(indexed_tantivy_store):
    """GIVEN indexed repo with multiple languages
       WHEN searching with --language python --language javascript
       THEN Python OR JavaScript files are returned"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("function", languages=["python", "javascript"])

    assert len(results) > 0
    languages_found = {r["language"] for r in results}
    assert languages_found.issubset({"py", "pyw", "pyi", "js", "jsx"})

def test_language_filter_with_fuzzy(indexed_tantivy_store):
    """GIVEN indexed repo
       WHEN searching with fuzzy and language filter
       THEN filtered fuzzy results are returned"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("tst", languages=["python"], edit_distance=1)

    assert len(results) > 0
    for result in results:
        assert result["language"] in ["py", "pyw", "pyi"]

def test_unknown_language_returns_empty(indexed_tantivy_store):
    """GIVEN indexed repo
       WHEN searching with unknown language
       THEN empty results are returned"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("test", languages=["fake-lang"])

    assert len(results) == 0

def test_no_language_filter_returns_all(indexed_tantivy_store):
    """GIVEN indexed repo
       WHEN searching without language filter
       THEN all matching files are returned"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("test", languages=None)

    assert len(results) > 0
    # Should have multiple languages
    languages_found = {r["language"] for r in results}
    assert len(languages_found) > 1
```

### Integration Tests

**File**: `tests/e2e/test_fts_language_filter.py`

```python
def test_cli_language_filter_python(tmp_path):
    """Test --language python flag with FTS"""
    # Setup: Index repo with Python and JavaScript files
    setup_test_repo(tmp_path)

    # Execute: Query with language filter
    result = subprocess.run(
        ["cidx", "query", "function", "--fts", "--language", "python"],
        capture_output=True, text=True
    )

    # Verify: Only Python files in output
    assert result.returncode == 0
    assert ".py" in result.stdout
    assert ".js" not in result.stdout

def test_cli_multiple_languages(tmp_path):
    """Test multiple --language flags with FTS"""
    setup_test_repo(tmp_path)

    result = subprocess.run(
        ["cidx", "query", "class", "--fts", "--language", "python", "--language", "javascript"],
        capture_output=True, text=True
    )

    assert result.returncode == 0
    # Should have both Python and JavaScript files
    assert ".py" in result.stdout or ".js" in result.stdout
```

### Manual Test Scenarios

1. **Basic Language Filter**:
   ```bash
   cidx index --fts
   cidx query "authentication" --fts --language python
   # Expected: Only Python files (*.py, *.pyw, *.pyi)
   ```

2. **Multiple Languages**:
   ```bash
   cidx query "config" --fts --language python --language javascript
   # Expected: Python OR JavaScript files
   ```

3. **Language + Fuzzy**:
   ```bash
   cidx query "cofig" --fts --fuzzy --language python
   # Expected: Python files matching "config" with 1-char typo
   ```

4. **Unknown Language**:
   ```bash
   cidx query "test" --fts --language fake-lang
   # Expected: "No matches found"
   ```

5. **No Filter (Baseline)**:
   ```bash
   cidx query "import" --fts --limit 10
   # Expected: All languages returned
   ```

## Performance Considerations

- **Post-Search Filtering**: Filtering happens after Tantivy search, adding ~1-5ms overhead
- **LanguageMapper Lookup**: Extension lookup is O(1) hash table operation
- **Set Membership Check**: `language in allowed_extensions` is O(1)
- **Expected Performance**: <1s total for typical queries with language filters
- **No Impact on Tantivy**: Filtering is done in Python, not Tantivy query

## Dependencies

- Existing `LanguageMapper` class (`src/code_indexer/services/language_mapper.py`)
- Existing FTS infrastructure (`TantivyIndexManager`)
- Tantivy index must be created with language field (already exists)

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking backward compatibility | High | Maintain `language_filter` as deprecated parameter |
| Performance degradation | Low | Post-search filtering is very fast (<5ms) |
| Unknown language edge cases | Low | Return empty results gracefully, no errors |
| CLI parameter confusion | Low | Clear help text, consistent with semantic search |

## Success Metrics

- All acceptance criteria passing
- Zero performance regression (<1s queries)
- Feature parity with semantic search language filtering
- All unit and integration tests passing
- Manual testing confirms expected behavior

## Notes

**Implementation Order**: This is Story 1 of 6 for FTS filtering. Must be implemented first as it establishes the filtering pattern for subsequent stories.

**Semantic Search Parity**: This implementation mirrors exactly how semantic search handles language filtering (post-search filtering with LanguageMapper).

**Future Enhancement**: Could potentially use Tantivy's facet filtering for better performance, but post-search filtering is simpler and already fast enough.

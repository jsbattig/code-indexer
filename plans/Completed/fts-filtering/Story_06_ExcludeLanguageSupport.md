# Story: Add --exclude-language Support for FTS

## Story Description

**As a** developer searching code
**I want to** exclude specific programming languages from FTS results using `--exclude-language` flag
**So that** I can filter out languages irrelevant to my search (e.g., exclude JavaScript when debugging Python)

**Conversation Context:**
- User requested feature parity with semantic search filtering
- Semantic search supports `--exclude-language` for filtering out unwanted languages
- Final piece completing FTS filtering feature parity
- Exclusions take precedence over inclusions (consistent with exclude-path)

## Acceptance Criteria

- [x] Running `cidx query "function" --fts --exclude-language javascript` excludes JavaScript files (js, jsx)
- [x] Running `cidx query "test" --fts --exclude-language python --exclude-language javascript` excludes multiple languages
- [x] Exclusions work with inclusions: `--language python --exclude-language python` returns empty results (exclusion wins)
- [x] Exclusion takes precedence over inclusion when languages conflict
- [x] Exclusions work with path filters
- [x] Exclusions work with fuzzy and case-sensitive search
- [x] Performance remains <1s even with multiple language exclusions

## Technical Implementation

### CLI Changes

**File**: `src/code_indexer/cli.py`

```python
# Add new option
@click.option(
    "--exclude-language",
    type=str,
    multiple=True,
    help="Exclude programming languages (can be specified multiple times, takes precedence over --language)",
)
def query(
    ...
    languages: tuple[str, ...],
    exclude_language: tuple[str, ...],  # New parameter
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
                exclude_paths=list(exclude_path) if exclude_path else None,
                exclude_languages=list(exclude_language) if exclude_language else None,  # New parameter
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
    exclude_paths: Optional[List[str]] = None,
    exclude_languages: Optional[List[str]] = None,  # NEW parameter
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
        languages: Include programming languages (OR logic)
        path_filters: Include paths matching patterns (OR logic)
        exclude_paths: Exclude paths matching patterns (OR logic, takes precedence)
        exclude_languages: Exclude programming languages (OR logic, takes precedence)
        path_filter: DEPRECATED
        query: Backwards compatibility parameter

    Returns:
        List of search results
    """
    # ... existing search code ...

    # Build allowed and excluded extension sets once before loop
    allowed_extensions = set()
    excluded_extensions = set()

    if languages or exclude_languages:
        from code_indexer.services.language_mapper import LanguageMapper
        mapper = LanguageMapper()

        # Build allowed extensions from included languages
        if languages:
            for lang in languages:
                extensions = mapper.get_extensions(lang)
                if extensions:
                    allowed_extensions.update(extensions)

        # Build excluded extensions from excluded languages
        if exclude_languages:
            for lang in exclude_languages:
                extensions = mapper.get_extensions(lang)
                if extensions:
                    excluded_extensions.update(extensions)

    # Process results
    for score, address in search_results:
        doc = searcher.doc(address)
        path = doc.get_first("path") or ""
        language = doc.get_first("language")
        # ... extract other fields ...

        # Parse language from facet format
        if language:
            language = str(language).strip("/")

        # CRITICAL: Apply language exclusions FIRST (before inclusions)
        # Exclusions take precedence
        if excluded_extensions and language in excluded_extensions:
            continue  # Skip this result

        # Apply language inclusions
        if allowed_extensions and language not in allowed_extensions:
            continue

        # Apply path exclusions (takes precedence)
        if exclude_matcher and exclude_paths:
            if any(exclude_matcher.matches_pattern(path, pattern) for pattern in exclude_paths):
                continue

        # Apply path inclusions
        if path_matcher and path_filters:
            if not any(path_matcher.matches_pattern(path, pattern) for pattern in path_filters):
                continue

        # ... rest of result processing ...
```

### Filter Precedence Logic

Complete filtering order:

```python
# 1. LANGUAGE EXCLUSIONS (processed first)
if language matches ANY excluded extension:
    EXCLUDE result

# 2. LANGUAGE INCLUSIONS (processed second)
if included languages specified:
    if language matches ANY allowed extension:
        PROCEED to path filters
    else:
        EXCLUDE result

# 3. PATH EXCLUSIONS (processed third)
if path matches ANY exclusion pattern:
    EXCLUDE result

# 4. PATH INCLUSIONS (processed fourth)
if path_filters specified:
    if path matches ANY inclusion pattern:
        INCLUDE result
    else:
        EXCLUDE result

# 5. NO FILTERS (default)
if no filters specified:
    INCLUDE result
```

**Example**:
- `--language python --exclude-language python`
- Result: EXCLUDED (exclusion takes precedence)

## Test Requirements

### Unit Tests

**File**: `tests/unit/services/test_tantivy_exclude_language.py`

```python
def test_single_exclude_language(indexed_tantivy_store):
    """GIVEN indexed repo with Python and JavaScript files
       WHEN searching with --exclude-language javascript
       THEN no JavaScript files are returned"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("function", exclude_languages=["javascript"])

    assert len(results) > 0
    for result in results:
        assert result["language"] not in ["js", "jsx"]

def test_multiple_exclude_languages(indexed_tantivy_store):
    """GIVEN indexed repo with multiple languages
       WHEN excluding multiple languages
       THEN none of the excluded languages appear"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search(
        "config",
        exclude_languages=["javascript", "typescript"]
    )

    assert len(results) > 0
    for result in results:
        lang = result["language"]
        assert lang not in ["js", "jsx", "ts", "tsx"]

def test_exclude_with_include_language(indexed_tantivy_store):
    """GIVEN indexed repo with Python, JavaScript, TypeScript
       WHEN including Python and JavaScript but excluding JavaScript
       THEN only Python files returned (exclusion takes precedence)"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search(
        "function",
        languages=["python", "javascript"],
        exclude_languages=["javascript"]
    )

    assert len(results) > 0
    for result in results:
        # Should only have Python
        assert result["language"] in ["py", "pyw", "pyi"]
        # Should NOT have JavaScript
        assert result["language"] not in ["js", "jsx"]

def test_exclusion_precedence_over_inclusion(indexed_tantivy_store):
    """GIVEN same language in both include and exclude
       WHEN both filters applied
       THEN exclusion takes precedence (returns empty)"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search(
        "test",
        languages=["python"],  # Include Python
        exclude_languages=["python"]  # But exclude Python
    )

    # Should return empty - exclusion wins
    assert len(results) == 0

def test_exclude_language_with_path_filter(indexed_tantivy_store):
    """GIVEN indexed repo
       WHEN combining language exclusion and path filters
       THEN results match path filters AND do not match excluded languages"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search(
        "function",
        path_filters=["*/src/*"],
        exclude_languages=["javascript"]
    )

    assert len(results) > 0
    for result in results:
        assert "/src/" in result["path"]
        assert result["language"] not in ["js", "jsx"]

def test_all_filters_combined(indexed_tantivy_store):
    """GIVEN indexed repo
       WHEN using all filter types together
       THEN results match all filter criteria"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search(
        "test",
        languages=["python", "go"],  # Include Python and Go
        path_filters=["*/tests/*", "*/src/*"],  # Include tests or src
        exclude_paths=["*/tests/slow/*"],  # Exclude slow tests
        exclude_languages=["go"]  # But exclude Go (so only Python)
    )

    assert len(results) > 0
    for result in results:
        # Must be Python (Go excluded)
        assert result["language"] in ["py", "pyw", "pyi"]
        # Must be in tests or src
        assert "/tests/" in result["path"] or "/src/" in result["path"]
        # Must NOT be in slow tests
        assert "/slow/" not in result["path"]

def test_no_exclusions_returns_all_languages(indexed_tantivy_store):
    """GIVEN indexed repo
       WHEN no language exclusions specified
       THEN all languages returned"""
    manager = TantivyIndexManager(index_dir)
    results = manager.search("function", exclude_languages=None)

    assert len(results) > 0
    # Should have multiple languages
    languages_found = {r["language"] for r in results}
    assert len(languages_found) > 1
```

### Integration Tests

**File**: `tests/e2e/test_fts_exclude_language.py`

```python
def test_cli_exclude_javascript(tmp_path):
    """Test excluding JavaScript via CLI"""
    setup_multi_language_repo(tmp_path)

    result = subprocess.run(
        ["cidx", "query", "function", "--fts", "--exclude-language", "javascript"],
        capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 0
    assert ".js" not in result.stdout
    assert ".jsx" not in result.stdout

def test_cli_multiple_language_exclusions(tmp_path):
    """Test multiple --exclude-language flags"""
    setup_multi_language_repo(tmp_path)

    result = subprocess.run(
        ["cidx", "query", "config", "--fts",
         "--exclude-language", "javascript",
         "--exclude-language", "typescript"],
        capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 0
    assert ".js" not in result.stdout
    assert ".ts" not in result.stdout

def test_cli_include_and_exclude_language(tmp_path):
    """Test combining language inclusion and exclusion"""
    setup_multi_language_repo(tmp_path)

    result = subprocess.run(
        ["cidx", "query", "function", "--fts",
         "--language", "python",
         "--language", "javascript",
         "--exclude-language", "javascript"],
        capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 0
    assert ".py" in result.stdout  # Python included
    assert ".js" not in result.stdout  # JavaScript excluded

def test_cli_all_filters_combined(tmp_path):
    """Test all filter types working together"""
    setup_complex_repo(tmp_path)

    result = subprocess.run(
        ["cidx", "query", "test", "--fts",
         "--language", "python",
         "--path-filter", "*/tests/*",
         "--exclude-path", "*/tests/slow/*",
         "--exclude-language", "javascript"],
        capture_output=True, text=True, cwd=tmp_path
    )

    assert result.returncode == 0
    assert ".py" in result.stdout
    assert "/tests/" in result.stdout
    assert "slow" not in result.stdout
    assert ".js" not in result.stdout
```

### Manual Test Scenarios

1. **Exclude JavaScript**:
   ```bash
   cidx query "function" --fts --exclude-language javascript
   # Expected: No .js or .jsx files
   ```

2. **Multiple Exclusions**:
   ```bash
   cidx query "config" --fts \
     --exclude-language javascript \
     --exclude-language typescript
   # Expected: No JS or TS files
   ```

3. **Include + Exclude (Precedence)**:
   ```bash
   cidx query "test" --fts \
     --language python \
     --language javascript \
     --exclude-language javascript
   # Expected: Only Python files (exclusion wins)
   ```

4. **With Path Filters**:
   ```bash
   cidx query "function" --fts \
     --path-filter "*/src/*" \
     --exclude-language javascript
   # Expected: src/ files, but not JavaScript
   ```

5. **All Filters Combined**:
   ```bash
   cidx query "test" --fts \
     --language python \
     --language go \
     --path-filter "*/tests/*" \
     --exclude-path "*/tests/slow/*" \
     --exclude-language go
   # Expected: Only Python test files, excluding slow tests
   ```

6. **Help Text**:
   ```bash
   cidx query --help | grep exclude-language
   # Expected: Shows --exclude-language option with description
   ```

## Performance Considerations

- **Set Operations**: Building extension sets is O(N) where N = number of languages (typically 1-3)
- **Set Membership**: Checking `language in excluded_extensions` is O(1)
- **Combined Filters**: All filters process in <5ms total per result
- **Expected Performance**: <1s for typical queries with all filters

## Dependencies

- Existing `LanguageMapper` class
- Click's `multiple=True` option support
- Stories 1-5 (all filtering infrastructure)

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Precedence confusion | Medium | Clear documentation, comprehensive tests |
| Performance with many filters | Low | Set operations are O(1), short-circuit on exclusions |
| Complex filter interactions | Medium | Extensive integration testing with all filters |

## Success Metrics

- All acceptance criteria passing
- Complete feature parity with semantic search
- All 6 stories complete and working together
- Zero performance regression
- Comprehensive documentation

## Notes

**Implementation Order**: Story 6 of 6 - FINAL story completing FTS filtering feature parity.

**Precedence Summary** (final implementation):
1. Language exclusions (FIRST)
2. Language inclusions (SECOND)
3. Path exclusions (THIRD)
4. Path inclusions (FOURTH)

**Feature Parity Achieved**: After this story, FTS will support:
- ✅ `--language` (multiple, OR logic)
- ✅ `--path-filter` (multiple, OR logic)
- ✅ `--exclude-path` (multiple, OR logic, precedence)
- ✅ `--exclude-language` (multiple, OR logic, precedence)

All filters work together seamlessly, matching semantic search behavior exactly.

**Common Use Cases**:
- Focus on backend: `--language python --language go --exclude-language javascript`
- Exclude generated code: `--exclude-path "**/generated/**" --exclude-path "*.pb.go"`
- Debug specific area: `--path-filter "*/src/auth/*" --exclude-language typescript`

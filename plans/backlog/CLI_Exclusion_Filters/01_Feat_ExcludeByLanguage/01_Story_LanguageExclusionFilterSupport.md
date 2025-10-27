# Story: Language Exclusion Filter Support

## Summary
Implement complete language exclusion functionality for the `cidx query` command, including the `--exclude-language` CLI flag, filter construction logic, and comprehensive test coverage (30+ unit tests).

**Conversation Context**: User requested ability to "exclude all JavaScript files when searching for database implementations" with requirement for "30+ unit tests, TDD approach, 100% coverage target"

## Description

### User Story
As a developer searching a polyglot codebase, I want to exclude specific programming languages from my search results so that I can focus on implementations in the languages I care about, and I need confidence that this feature works correctly through extensive test coverage.

### Technical Context
The backend already supports `must_not` conditions after recent fixes. This story implements the complete user-facing functionality including CLI interface, filter construction, and comprehensive testing to ensure correctness across all scenarios.

**From Investigation**: "Backend already supports must_not conditions after today's fix to filesystem_vector_store.py" and "30+ unit tests for filesystem store filter parsing... TDD approach - write tests first... 100% coverage target for new code paths"

## Acceptance Criteria

### Functional Requirements
1. ✅ Add `--exclude-language` option to query command with `multiple=True`
2. ✅ Accept standard language names (python, javascript, typescript, etc.)
3. ✅ Support multiple exclusions in a single command
4. ✅ Map language names to file extensions using `LANGUAGE_MAPPER`
5. ✅ Generate proper `must_not` filter conditions
6. ✅ Work correctly with both Qdrant and filesystem backends

### CLI Examples
```bash
# Single exclusion
cidx query "database" --exclude-language javascript

# Multiple exclusions
cidx query "auth" --exclude-language javascript --exclude-language typescript

# With other filters
cidx query "config" --language python --exclude-language javascript --min-score 0.7
```

### Filter Output
```python
# For: --exclude-language javascript
{
    "must_not": [
        {"field": "metadata.language", "match": {"value": "js"}},
        {"field": "metadata.language", "match": {"value": "mjs"}},
        {"field": "metadata.language", "match": {"value": "cjs"}}
    ]
}
```

### Test Coverage Requirements
1. ✅ Minimum 15 tests for language exclusion (part of 30+ total epic requirement)
2. ✅ TDD approach - tests written before implementation
3. ✅ 100% code coverage for new code paths
4. ✅ Tests for both storage backends
5. ✅ Edge cases and error scenarios covered
6. ✅ Performance validation included

## Technical Implementation

### 1. Add CLI Option
**File**: `src/code_indexer/cli.py` (around line 3195)
```python
@click.option(
    '--exclude-language',
    'exclude_languages',
    multiple=True,
    help='Exclude files of specified language(s) from search results. '
         'Can be specified multiple times. Example: --exclude-language javascript --exclude-language css'
)
```

### 2. Extend Filter Construction
**Location**: `cli.py` lines 3234-3256
```python
# Add logic to build 'must_not' conditions

if exclude_languages:
    must_not_conditions = []
    for lang in exclude_languages:
        lang_lower = lang.lower()
        if lang_lower in LANGUAGE_MAPPER:
            extensions = LANGUAGE_MAPPER[lang_lower]
            for ext in extensions:
                must_not_conditions.append({
                    "field": "metadata.language",
                    "match": {"value": ext}
                })
        else:
            # Handle unknown language
            console.print(f"[yellow]Warning: Unknown language '{lang}'[/yellow]")

    if must_not_conditions:
        if filters is None:
            filters = {}
        filters["must_not"] = must_not_conditions
```

### 3. Update Function Signature
Add `exclude_languages` parameter to the query function and pass it through to search operations.

## Test Requirements

### Test Categories
1. **Basic Functionality**: Single and multiple exclusions
2. **Language Mapping**: Extension resolution and aliases
3. **Filter Construction**: Proper must_not structure
4. **Integration**: Combined with other filters
5. **Error Handling**: Invalid inputs and edge cases
6. **Performance**: No significant overhead
7. **Backend Compatibility**: Both Qdrant and filesystem stores

### 1. Filesystem Store Tests
**File**: `tests/unit/storage/test_filesystem_vector_store_exclusions.py`

```python
import pytest
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

class TestFilesystemLanguageExclusions:
    """Test language exclusion filters for filesystem vector store."""

    def test_single_language_exclusion(self, vector_store):
        """Test excluding a single language."""
        filters = {
            "must_not": [
                {"field": "metadata.language", "match": {"value": "js"}}
            ]
        }
        # Verify filter parsing and application

    def test_multiple_language_exclusions(self, vector_store):
        """Test excluding multiple languages."""
        filters = {
            "must_not": [
                {"field": "metadata.language", "match": {"value": "js"}},
                {"field": "metadata.language", "match": {"value": "py"}}
            ]
        }
        # Verify all exclusions are applied

    def test_language_exclusion_with_inclusion(self, vector_store):
        """Test combining must and must_not for languages."""
        filters = {
            "must": [
                {"field": "metadata.language", "match": {"value": "py"}}
            ],
            "must_not": [
                {"field": "metadata.language", "match": {"value": "js"}}
            ]
        }
        # Verify precedence and combination
```

### 2. CLI Filter Construction Tests
**File**: `tests/unit/test_cli_exclusion_filters.py`

```python
class TestCLILanguageExclusions:
    """Test CLI filter construction for language exclusions."""

    def test_exclude_language_flag_parsing(self):
        """Test --exclude-language flag is parsed correctly."""
        # Test single flag
        # Test multiple flags
        # Test with other options

    def test_language_mapper_integration(self):
        """Test language names are mapped to extensions."""
        # javascript -> js, mjs, cjs
        # python -> py, pyw, pyi
        # typescript -> ts, tsx

    def test_filter_structure_generation(self):
        """Test correct filter structure is generated."""
        # Verify must_not conditions
        # Verify field names
        # Verify value format

    def test_unknown_language_handling(self):
        """Test handling of invalid language names."""
        # Should warn but not fail
        # Should skip unknown languages
```

### 3. Integration Tests
**File**: `tests/integration/test_language_exclusion_e2e.py`

```python
class TestLanguageExclusionE2E:
    """End-to-end tests for language exclusion."""

    def test_exclude_javascript_from_results(self, indexed_repo):
        """Test that JavaScript files are actually excluded."""
        # Index mixed language repo
        # Query with --exclude-language javascript
        # Verify no .js files in results

    def test_multiple_exclusions_e2e(self, indexed_repo):
        """Test multiple language exclusions work together."""
        # Exclude javascript, css, html
        # Verify only Python files returned

    def test_exclusion_with_qdrant_backend(self, qdrant_client):
        """Test exclusions work with Qdrant backend."""
        # Same tests but with Qdrant

    def test_exclusion_with_filesystem_backend(self, filesystem_store):
        """Test exclusions work with filesystem backend."""
        # Same tests but with filesystem store
```

### 4. Performance Tests
**File**: `tests/performance/test_exclusion_filter_performance.py`

```python
class TestExclusionFilterPerformance:
    """Performance tests for exclusion filters."""

    def test_filter_construction_overhead(self):
        """Measure overhead of building exclusion filters."""
        # Time with no exclusions
        # Time with 1 exclusion
        # Time with 10 exclusions
        # Assert < 2ms overhead

    def test_query_performance_with_exclusions(self):
        """Test query performance isn't degraded."""
        # Large dataset query without exclusions
        # Same query with exclusions
        # Assert < 5% performance difference
```

### 5. Edge Cases and Error Scenarios
**File**: `tests/unit/test_exclusion_edge_cases.py`

```python
class TestExclusionEdgeCases:
    """Test edge cases for exclusion filters."""

    def test_exclude_all_languages(self):
        """Test when all files are excluded."""
        # Should return empty results
        # Should not error

    def test_duplicate_exclusions(self):
        """Test same language excluded multiple times."""
        # --exclude-language python --exclude-language python
        # Should handle gracefully

    def test_case_sensitivity(self):
        """Test language names are case-insensitive."""
        # JavaScript, javascript, JAVASCRIPT
        # All should work

    def test_empty_exclusion_list(self):
        """Test with no exclusions specified."""
        # Should work as before
        # Backward compatibility
```

### Minimum Test Count
- **Filesystem Store Tests**: 3 tests
- **CLI Filter Construction Tests**: 4 tests
- **Integration Tests**: 4 tests
- **Performance Tests**: 2 tests
- **Edge Cases**: 4 tests
- **Total**: 17 tests (exceeds 15 minimum)

## Manual Testing

### Manual Test Script
```bash
# Create test files
echo "# Python database" > test.py
echo "// JS database" > test.js
echo "/* CSS styles */" > test.css

# Index them
cidx index

# Test single exclusion
cidx query "database" --exclude-language javascript
# Should only show test.py

# Test multiple exclusions
cidx query "database" --exclude-language javascript --exclude-language css
# Should only show test.py

# Test with inclusions
cidx query "database" --language python --exclude-language javascript
# Should only show test.py
```

## Implementation Steps

1. **Step 1**: Write all test cases with expected behavior (TDD)
2. **Step 2**: Add `--exclude-language` option to query command
3. **Step 3**: Add `exclude_languages` parameter to function signature
4. **Step 4**: Implement language to extension mapping logic
5. **Step 5**: Build `must_not` conditions array
6. **Step 6**: Merge with existing filter structure
7. **Step 7**: Pass filters to search backends
8. **Step 8**: Add warning for unknown languages
9. **Step 9**: Update help text with examples
10. **Step 10**: Run tests and iterate until all pass

## Code Locations

- **CLI Option Definition**: `cli.py:3195` (query command decorator)
- **Filter Construction**: `cli.py:3234-3256`
- **Language Mapper**: Already defined in codebase
- **Search Calls**: Where filters are passed to backends
- **Test Files**: Various locations as specified above

## Validation Metrics

### Coverage Requirements
- Line Coverage: 100% for new code
- Branch Coverage: 100% for new code
- Edge Cases: All identified scenarios tested

### Performance Requirements
- Filter construction: < 2ms overhead
- Query execution: < 5% slower with exclusions
- Memory usage: No significant increase

## Definition of Done

- [ ] All test cases written (TDD approach)
- [ ] CLI flag implementation complete
- [ ] Language mapper integration complete
- [ ] Filter construction includes `must_not` conditions
- [ ] 15+ unit tests written and passing
- [ ] Integration tests for both backends passing
- [ ] Performance tests passing
- [ ] Edge case tests passing
- [ ] 100% code coverage achieved
- [ ] Help text updated with examples
- [ ] Manual testing performed
- [ ] Code follows project style guidelines
- [ ] No performance regression
- [ ] Code reviewed
- [ ] fast-automation.sh passing

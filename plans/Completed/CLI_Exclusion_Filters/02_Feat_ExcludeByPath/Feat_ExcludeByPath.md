# Feature: Exclude by Path

## Overview

This feature adds the `--exclude-path` flag to the `cidx query` command, enabling users to exclude files matching specific path patterns from semantic search results. The feature uses glob patterns with `fnmatch` for flexible path matching.

**Conversation Context**: "I want to exclude files by path pattern: `cidx query 'database' --exclude-path '*/tests/*'`"

## Business Value

### Problem Statement
When searching codebases, certain directories like tests, vendor files, or cache directories often pollute search results with irrelevant matches. Users need a way to filter out these paths to focus on production code.

### Expected Outcome
Users can exclude entire directory trees or files matching patterns, significantly improving search relevance by removing test files, generated code, and other noise from results.

## Functional Requirements

### CLI Interface
```bash
# Single path exclusion
cidx query "database connection" --exclude-path "*/tests/*"

# Multiple path exclusions
cidx query "config" --exclude-path "*/tests/*" --exclude-path "*/__pycache__/*"

# Complex patterns
cidx query "api" --exclude-path "*/node_modules/*" --exclude-path "*/vendor/*" --exclude-path "*.min.js"

# Combined with other filters
cidx query "auth" --language python --exclude-path "*/tests/*" --exclude-language javascript
```

### Pattern Matching
- Use glob patterns with `fnmatch` (already implemented)
- Support wildcards: `*` (any characters), `?` (single character)
- Path separators work cross-platform
- Case-sensitive matching (configurable)

**From Investigation**: "Pattern matching with fnmatch already implemented for path filters"

## Technical Design

### Implementation Location
**File**: `src/code_indexer/cli.py`
- **Flag Addition**: Query command decorator (~line 3195)
- **Filter Construction**: Lines 3234-3256 (extend existing logic)

### Filter Structure
```python
# Path exclusion filter structure
filters = {
    "must_not": [
        {"field": "metadata.file_path", "match": {"value": "*/tests/*"}},
        {"field": "metadata.file_path", "match": {"value": "*/__pycache__/*"}}
    ]
}

# Combined with language filters
filters = {
    "must": [...],
    "must_not": [
        {"field": "metadata.file_path", "match": {"value": "*/tests/*"}},
        {"field": "metadata.language", "match": {"value": "js"}}
    ]
}
```

### Pattern Processing
```python
# Process exclude patterns
for pattern in exclude_paths:
    # Normalize path separators for cross-platform
    normalized_pattern = pattern.replace('\\', '/')
    must_not_conditions.append({
        "field": "metadata.file_path",
        "match": {"value": normalized_pattern}
    })
```

## User Stories

### Story 1: Path Exclusion Filter Support
Implement complete path exclusion functionality including CLI flag with glob patterns, cross-platform path handling, and comprehensive test coverage (15+ tests as part of the 30+ epic requirement).

**File**: `01_Story_PathExclusionFilterSupport.md`

**Summary**: This story consolidates CLI implementation, pattern matching, and test coverage into a single, manually-testable user-facing feature that developers can use end-to-end.

## Acceptance Criteria

### Functional Criteria
1. ✅ `--exclude-path` flag accepts glob patterns
2. ✅ Multiple `--exclude-path` flags can be specified
3. ✅ Patterns match using `fnmatch` rules
4. ✅ Path exclusions work with both storage backends
5. ✅ Can be combined with language exclusions
6. ✅ Cross-platform path separator handling

### Pattern Matching Criteria
1. ✅ `*/tests/*` excludes all test directories
2. ✅ `*.min.js` excludes minified JavaScript files
3. ✅ `src/*/temp_*` excludes temporary files in src subdirectories
4. ✅ Absolute and relative paths both work
5. ✅ Case sensitivity handled appropriately

### Test Coverage Criteria
1. ✅ Minimum 15 tests for path exclusion
2. ✅ Pattern matching validation
3. ✅ Cross-platform path handling tested
4. ✅ Edge cases and boundary conditions covered
5. ✅ Performance benchmarks included
6. ✅ Integration with both backends tested

## Implementation Notes

### Key Considerations
1. **Pattern Normalization**: Handle Windows/Unix path differences
2. **Performance**: Pattern matching should be efficient
3. **Clear Examples**: Help text must show common patterns
4. **Backend Compatibility**: Both stores must handle patterns

### Common Use Cases
```bash
# Exclude test files
--exclude-path "*/tests/*" --exclude-path "*/test_*.py"

# Exclude build artifacts
--exclude-path "*/build/*" --exclude-path "*/dist/*" --exclude-path "*.pyc"

# Exclude dependency directories
--exclude-path "*/node_modules/*" --exclude-path "*/vendor/*" --exclude-path "*/.venv/*"

# Exclude temporary files
--exclude-path "*/__pycache__/*" --exclude-path "*.tmp" --exclude-path "*~"
```

## Dependencies

### Internal Dependencies
- Pattern matching with `fnmatch`
- Filter construction logic in `cli.py`
- Click framework for CLI options

### External Dependencies
None - uses existing infrastructure

## Performance Considerations

### Pattern Matching Overhead
- Each file path checked against all patterns
- Use efficient pattern compilation if possible
- Consider caching compiled patterns

### Optimization Opportunities
- Pre-compile patterns once
- Short-circuit on first match
- Order patterns by likelihood

## Conversation References

- **User Requirement**: "exclude files by path pattern"
- **Example Given**: "--exclude-path '*/tests/*'"
- **Multiple Patterns**: "--exclude-path '*/tests/*' --exclude-path '*/__pycache__/*'"
- **Backend Support**: "Pattern matching with fnmatch already implemented"

## Definition of Done

- [ ] Story 1 (Path Exclusion Filter Support) complete:
  - [ ] `--exclude-path` flag implemented in CLI
  - [ ] Pattern matching logic integrated
  - [ ] Filter construction includes path conditions
  - [ ] 15+ unit tests written and passing
  - [ ] Integration tests with real file structures passing
  - [ ] Performance tests passing
  - [ ] Cross-platform tests passing
  - [ ] Edge case tests passing
  - [ ] 100% code coverage achieved
  - [ ] Help text updated with pattern examples
  - [ ] Manual testing performed
  - [ ] Cross-platform testing completed
  - [ ] Performance impact measured (<5ms)
  - [ ] Code review completed
  - [ ] fast-automation.sh passing
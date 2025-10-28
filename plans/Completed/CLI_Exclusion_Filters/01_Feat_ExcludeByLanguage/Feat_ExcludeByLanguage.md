# Feature: Exclude by Language

## Overview

This feature adds the `--exclude-language` flag to the `cidx query` command, enabling users to exclude files of specific programming languages from semantic search results. The feature leverages the existing `must_not` support in both storage backends.

**Conversation Context**: "I want to exclude files from my semantic search. For example, exclude all JavaScript files: `cidx query 'database' --exclude-language javascript`"

## Business Value

### Problem Statement
When searching for implementations in polyglot codebases, users often get results from languages they don't care about. For example, when searching for Python database implementations, JavaScript and CSS files add noise to the results.

### Expected Outcome
Users can precisely filter out unwanted languages, improving search relevance and reducing cognitive load when reviewing results.

## Functional Requirements

### CLI Interface
```bash
# Single language exclusion
cidx query "database implementation" --exclude-language javascript

# Multiple language exclusions (using Click's multiple=True)
cidx query "authentication" --exclude-language javascript --exclude-language typescript --exclude-language css

# Combined with inclusion filters
cidx query "config parsing" --language python --exclude-language javascript
```

### Language Mapping
The feature must use the existing `LANGUAGE_MAPPER` to handle language aliases:
- `python` → `["py", "pyw", "pyi"]`
- `javascript` → `["js", "mjs", "cjs"]`
- `typescript` → `["ts", "tsx"]`

**From Investigation**: "Language mapper already handles multi-extension languages"

## Technical Design

### Implementation Location
**File**: `src/code_indexer/cli.py`
- **Flag Addition**: Query command decorator (~line 3195)
- **Filter Construction**: Lines 3234-3256 (extend existing logic)

### Filter Structure
```python
# Current structure (must only)
filters = {
    "must": [
        {"field": "metadata.language", "match": {"value": "py"}}
    ]
}

# New structure (with must_not)
filters = {
    "must": [...],
    "must_not": [
        {"field": "metadata.language", "match": {"value": "js"}},
        {"field": "metadata.language", "match": {"value": "mjs"}},
        {"field": "metadata.language", "match": {"value": "cjs"}}
    ]
}
```

### Click Implementation
```python
@click.option(
    '--exclude-language',
    multiple=True,
    help='Exclude files of specified language(s) from results'
)
```

## User Stories

### Story 1: Language Exclusion Filter Support
Implement complete language exclusion functionality including CLI flag, filter construction, and comprehensive test coverage (15+ tests as part of the 30+ epic requirement).

**File**: `01_Story_LanguageExclusionFilterSupport.md`

**Summary**: This story consolidates CLI implementation and test coverage into a single, manually-testable user-facing feature that developers can use end-to-end.

## Acceptance Criteria

### Functional Criteria
1. ✅ `--exclude-language` flag accepts single language name
2. ✅ Multiple `--exclude-language` flags can be specified
3. ✅ Language aliases are properly expanded (javascript → js, mjs, cjs)
4. ✅ Exclusions work with both Qdrant and filesystem backends
5. ✅ Exclusions can be combined with `--language` inclusion filters
6. ✅ Invalid language names produce clear error messages

### Technical Criteria
1. ✅ Filter structure includes `must_not` conditions when exclusions present
2. ✅ Language mapper is used for all language resolution
3. ✅ No performance regression (< 2ms overhead)
4. ✅ Backward compatibility maintained (existing queries work unchanged)

### Test Coverage Criteria
1. ✅ Minimum 15 tests for language exclusion
2. ✅ TDD approach - tests written before implementation
3. ✅ 100% code coverage for new code paths
4. ✅ Tests for both storage backends
5. ✅ Edge cases and error scenarios covered
6. ✅ Performance validation included

## Implementation Notes

### Key Considerations
1. **Language Mapper Integration**: Must use existing `LANGUAGE_MAPPER` for consistency
2. **Error Messages**: Clear feedback for invalid language names
3. **Performance**: Filter construction should be efficient
4. **Documentation**: Update help text to show examples

### Code References
- **Language Mapper**: Already implemented in codebase
- **Filter Builder**: Lines 3234-3256 in `cli.py`
- **Backend Interfaces**: Both `QdrantClient` and `FilesystemVectorStore` support `must_not`

## Dependencies

### Internal Dependencies
- Existing `LANGUAGE_MAPPER` dictionary
- Filter construction logic in `cli.py`
- Click framework for CLI options

### External Dependencies
None - uses existing infrastructure

## Conversation References

- **User Requirement**: "exclude all JavaScript files when searching"
- **Multiple Exclusions**: "exclude-language javascript --exclude-language html --exclude-language css"
- **Backend Support**: "Backend already supports must_not conditions"
- **Design Decision**: "Use Click's multiple=True"

## Definition of Done

- [ ] Story 1 (Language Exclusion Filter Support) complete:
  - [ ] `--exclude-language` flag implemented in CLI
  - [ ] Language mapper integration complete
  - [ ] Filter construction includes `must_not` conditions
  - [ ] 15+ unit tests written and passing
  - [ ] Integration tests for both backends
  - [ ] Performance tests passing
  - [ ] Edge case tests passing
  - [ ] 100% code coverage achieved
  - [ ] Help text updated with examples
  - [ ] Manual testing performed
  - [ ] Code review completed
  - [ ] fast-automation.sh passing
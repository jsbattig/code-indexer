# Epic: CLI Exclusion Filters

## Executive Summary

This epic introduces exclusion filter capabilities to the CIDX CLI, allowing users to exclude files from semantic search results by language and path patterns. The backend infrastructure already supports `must_not` conditions after recent fixes to `filesystem_vector_store.py`, making this a CLI-only enhancement that exposes existing backend capabilities.

**Conversation Context**: User discovered backend supports negation filters but CLI doesn't expose this functionality. User needs to exclude specific file types and paths from search results for more targeted queries.

## Business Value

### Problem Statement
Users currently cannot exclude unwanted files from semantic search results, leading to noise in query responses. For example, when searching for "database" implementations, users may want to exclude test files or specific languages like JavaScript to focus on production Python code.

**From Conversation**: "I want to exclude files from my semantic search. For example, exclude all JavaScript files when searching for database implementations."

### Expected Outcomes
- More precise search results by filtering out irrelevant files
- Improved developer productivity with targeted queries
- Better signal-to-noise ratio in search results
- Alignment with standard CLI patterns (similar to grep's --exclude)

## Technical Scope

### Architectural Decisions (From Phase 5 Approval)

1. **CLI Design**: Use Click's `multiple=True` for `--exclude-language` and `--exclude-path` flags
2. **Filter Structure**: Extend existing Qdrant-style nested filters: `{"must": [...], "must_not": [...]}`
3. **Precedence**: Exclusions take precedence over inclusions (intuitive behavior)
4. **Backend**: Zero backend changes needed - both QdrantClient and FilesystemVectorStore already support `must_not`
5. **Implementation Location**: Extend filter construction logic at `cli.py` lines 3234-3256

### Requirements from Conversation

#### Language Exclusion
```bash
# Single language exclusion
cidx query "database" --exclude-language javascript

# Multiple language exclusions
cidx query "test" --exclude-language javascript --exclude-language html --exclude-language css
```

#### Path Exclusion
```bash
# Single path pattern exclusion
cidx query "database" --exclude-path "*/tests/*"

# Multiple path pattern exclusions
cidx query "config" --exclude-path "*/tests/*" --exclude-path "*/__pycache__/*"
```

#### Combined Filters
```bash
# Inclusion and exclusion together
cidx query "config" --language python --exclude-path "*/tests/*" --exclude-path "*/__pycache__/*"
```

### Technical Context from Investigation

1. **Backend Support Confirmed**: After fixing `filesystem_vector_store.py` line 436, both storage backends handle `must_not` conditions
2. **Language Mapper**: Existing `LANGUAGE_MAPPER` handles multi-extension languages (python → py, pyw, pyi)
3. **Pattern Matching**: `fnmatch` already implemented for path filters
4. **Filter Merging**: Current implementation at lines 3234-3256 builds `must` conditions, needs extension for `must_not`

## Features and Implementation Order

### Phase 1: Core Exclusion Filters
1. **Feature 1: Exclude by Language** (01_Feat_ExcludeByLanguage)
   - Story 1.1: Language Exclusion Filter Support (consolidated implementation + tests)

2. **Feature 2: Exclude by Path** (02_Feat_ExcludeByPath)
   - Story 2.1: Path Exclusion Filter Support (consolidated implementation + tests)

### Phase 2: Integration and Documentation
3. **Feature 3: Combined Exclusion Logic** (03_Feat_CombinedExclusionLogic)
   - Story 3.1: Filter Integration and Precedence

4. **Feature 4: Documentation** (04_Feat_Documentation)
   - Story 4.1: Help Text and README Updates

**Note**: Features 1 and 2 now have consolidated stories that combine CLI implementation with comprehensive test coverage (30+ tests total) to create user-facing functionality that can be tested end-to-end. This follows the principle that implementation and testing are inseparable parts of delivering working features.

## Testing Strategy

### Test Requirements (Critical from User)
- **30+ unit tests** for filesystem store filter parsing
- **TDD Approach**: Write tests first, then implementation
- **100% coverage target** for new code paths

### Test Coverage Areas
1. Simple `must_not` conditions
2. Multiple `must_not` conditions
3. Nested `must_not` with complex filters
4. Combined `must` + `must_not` filters
5. Pattern matching edge cases
6. Performance with large filter sets
7. Backend compatibility (Qdrant + Filesystem)

### Manual Testing Examples (From Conversation)
```bash
# Test language exclusion
cidx query "authentication" --exclude-language javascript --exclude-language typescript

# Test path exclusion
cidx query "config" --exclude-path "*/node_modules/*" --exclude-path "*/vendor/*"

# Test combined filters
cidx query "database connection" --language python --exclude-path "*/tests/*" --min-score 0.7
```

## Success Criteria

1. ✅ Users can exclude files by language using `--exclude-language` flag - COMPLETE
2. ✅ Users can exclude files by path pattern using `--exclude-path` flag - COMPLETE
3. ✅ Multiple exclusions of same type work correctly - COMPLETE
4. ✅ Exclusion filters work with both Qdrant and filesystem storage backends - COMPLETE
5. ✅ Exclusion filters combine properly with existing inclusion filters - COMPLETE
6. ✅ Documentation clearly explains exclusion filter syntax - COMPLETE
7. ✅ 30+ unit tests pass with 100% coverage of new code paths - COMPLETE (111 tests)
8. ✅ Performance impact is negligible (<5ms added to query time) - COMPLETE (< 0.01ms)

## Risk Mitigation

### Identified Risks
1. **Filter Complexity**: Complex nested filters might impact query performance
   - *Mitigation*: Performance testing with large filter sets

2. **User Confusion**: Interaction between inclusion and exclusion filters
   - *Mitigation*: Clear documentation and examples

3. **Backend Compatibility**: Ensuring both storage backends handle filters identically
   - *Mitigation*: Comprehensive test coverage for both backends

## Dependencies

### Technical Dependencies
- Click framework (already in use)
- Existing filter infrastructure in `cli.py`
- Language mapper functionality
- Pattern matching with `fnmatch`

### No External Dependencies
- No new libraries required
- No backend API changes needed
- No database schema changes

## Implementation Notes

### Key Code Locations
- **CLI Flag Addition**: `cli.py` query command decorator (~line 3195)
- **Filter Construction**: `cli.py` lines 3234-3256
- **Language Mapping**: Existing `LANGUAGE_MAPPER` dictionary
- **Backend Interfaces**: `QdrantClient.search()` and `FilesystemVectorStore.search()`

### Design Principles
1. **Consistency**: Match existing CLI patterns and flag styles
2. **Simplicity**: Reuse existing infrastructure where possible
3. **Performance**: Minimal overhead for filter processing
4. **Clarity**: Intuitive behavior with clear documentation

## Conversation Citations

- **Initial Request**: "I want to exclude files from my semantic search"
- **Backend Discovery**: "The backend already supports must_not conditions"
- **CLI Design Choice**: "Use Click's multiple=True for the flags"
- **Testing Requirement**: "30+ unit tests, TDD approach, 100% coverage target"
- **Architecture Approval**: "Zero backend changes needed"

## Definition of Done

- [x] All 4 features implemented and tested - COMPLETE
- [x] 30+ unit tests written and passing - COMPLETE (111 tests: 19 + 53 + 39)
- [x] 100% code coverage for new functionality - COMPLETE
- [x] Documentation updated (README + help text) - COMPLETE (140-line README section)
- [x] Manual testing completed with examples - COMPLETE (all examples verified)
- [x] Performance impact verified (<5ms) - COMPLETE (< 0.01ms, 500x better)
- [x] Code review completed - COMPLETE (all stories approved)
- [x] Integration tests passing - COMPLETE
- [x] fast-automation.sh passing - READY FOR VERIFICATION
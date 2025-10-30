# FTS Filtering Feature Set

## Overview

This directory contains 6 stories that implement complete filtering support for Full-Text Search (FTS), achieving feature parity with semantic search filtering.

**User Request**: "can we add --language and --path-filter after the fact? after all, we do filter after the fact with semantic"

**Status**: Ready for implementation (all stories defined with acceptance criteria)

## Stories

### Story 1: Multi-Language Filtering
**File**: `Story_01_MultiLanguageFiltering.md`
**Purpose**: Fix language filtering to map language names to file extensions (e.g., "python" → py, pyw, pyi)
**Priority**: HIGH (foundational - enables all other filtering)
**Implementation**: Replace single exact match with LanguageMapper-based extension matching
**Dependencies**: None

### Story 2: Wire --path-filter Flag to FTS
**File**: `Story_02_PathFilterWiring.md`
**Purpose**: Ensure --path-filter flag is properly connected and working in FTS
**Priority**: MEDIUM (quick win - likely just verification)
**Implementation**: Verify CLI flag exists and wiring to TantivyIndexManager is correct
**Dependencies**: None

### Story 3: Improve Path Filtering with PathPatternMatcher
**File**: `Story_03_PathPatternMatcher.md`
**Purpose**: Replace fnmatch with PathPatternMatcher for consistency with semantic search
**Priority**: MEDIUM (quality improvement)
**Implementation**: Replace fnmatch calls with PathPatternMatcher.matches_pattern()
**Dependencies**: Story 2

### Story 4: Support Multiple Path Filters
**File**: `Story_04_MultiplePathFilters.md`
**Purpose**: Allow multiple --path-filter flags with OR logic
**Priority**: MEDIUM (feature parity)
**Implementation**: Change path_filter to path_filters (list), use any() for OR logic
**Dependencies**: Stories 1-3

### Story 5: Add --exclude-path Support
**File**: `Story_05_ExcludePathSupport.md`
**Purpose**: Add --exclude-path flag to filter out unwanted directories
**Priority**: HIGH (common use case - exclude node_modules, vendor, dist)
**Implementation**: Add exclude_paths parameter, check exclusions BEFORE inclusions
**Dependencies**: Stories 1-4

### Story 6: Add --exclude-language Support
**File**: `Story_06_ExcludeLanguageSupport.md`
**Purpose**: Add --exclude-language flag to filter out unwanted languages
**Priority**: MEDIUM (completes feature parity)
**Implementation**: Add exclude_languages parameter, build excluded extensions set
**Dependencies**: Stories 1-5

## Implementation Order

**Phase 1** (Foundation):
1. Story 1: Multi-Language Filtering
2. Story 2: Wire --path-filter Flag

**Phase 2** (Quality):
3. Story 3: PathPatternMatcher

**Phase 3** (Feature Parity):
4. Story 4: Multiple Path Filters
5. Story 5: Exclude Path Support
6. Story 6: Exclude Language Support

## Technical Architecture

### Post-Search Filtering Approach

All filtering is done **after** Tantivy search completes, matching semantic search implementation:

```python
# Tantivy returns raw results
search_results = searcher.search(tantivy_query, limit).hits

# Apply filters in Python
for score, address in search_results:
    doc = searcher.doc(address)
    path = doc.get_first("path")
    language = doc.get_first("language")

    # 1. Language exclusions (FIRST - takes precedence)
    if language in excluded_extensions:
        continue

    # 2. Language inclusions (SECOND)
    if languages and language not in allowed_extensions:
        continue

    # 3. Path exclusions (THIRD - takes precedence)
    if any(matcher.matches_pattern(path, pattern) for pattern in exclude_paths):
        continue

    # 4. Path inclusions (FOURTH)
    if path_filters and not any(matcher.matches_pattern(path, pattern) for pattern in path_filters):
        continue

    # Include result
    results.append(result)
```

### Filter Precedence Rules

1. **Exclusions take precedence over inclusions** (standard filtering behavior)
2. **OR logic within filter type** (match ANY pattern/language)
3. **AND logic across filter types** (must pass ALL filter types)

### Reused Components

- `LanguageMapper` (maps language names → file extensions)
- `PathPatternMatcher` (cross-platform glob pattern matching)
- Existing FTS infrastructure (TantivyIndexManager)

## Performance Impact

- **Post-search filtering overhead**: ~1-5ms per result
- **Set operations**: O(1) for language extension lookup
- **Pattern matching**: O(1) with short-circuit on first match
- **Total overhead**: <10ms for typical queries
- **Expected performance**: Still <1s for queries with all filters

## Feature Parity Matrix

After all 6 stories implemented:

| Feature | Semantic Search | FTS (Before) | FTS (After) |
|---------|----------------|--------------|-------------|
| `--language` (single) | ✅ | ❌ | ✅ |
| `--language` (multiple) | ✅ | ❌ | ✅ |
| `--path-filter` (single) | ✅ | ⚠️ (buggy) | ✅ |
| `--path-filter` (multiple) | ✅ | ❌ | ✅ |
| `--exclude-path` | ✅ | ❌ | ✅ |
| `--exclude-language` | ✅ | ❌ | ✅ |
| PathPatternMatcher | ✅ | ❌ (uses fnmatch) | ✅ |
| Filter precedence | ✅ | N/A | ✅ |

**Result**: Complete feature parity achieved ✅

## Testing Strategy

Each story includes:
- **Unit Tests**: Testing filtering logic in isolation
- **Integration Tests**: Testing CLI flag parsing and E2E workflows
- **Manual Test Scenarios**: Real-world usage validation

**Test Coverage**:
- Individual filter types
- Filter combinations
- Edge cases (empty filters, unknown languages, invalid patterns)
- Precedence rules
- Backward compatibility
- Performance validation

## Success Metrics

- ✅ All 6 stories implemented with passing tests
- ✅ Feature parity with semantic search achieved
- ✅ Zero performance regression (<1s queries)
- ✅ Backward compatibility maintained
- ✅ Clear documentation and help text

## Common Use Cases

### Focus on Backend Code
```bash
cidx query "authentication" --fts \
  --language python --language go \
  --exclude-language javascript
```

### Search Tests Only
```bash
cidx query "test fixtures" --fts \
  --path-filter "*/tests/*" \
  --path-filter "*/integration/*"
```

### Exclude Build Artifacts
```bash
cidx query "config" --fts \
  --exclude-path "*/node_modules/*" \
  --exclude-path "*/dist/*" \
  --exclude-path "*/vendor/*"
```

### Complex Multi-Filter Query
```bash
cidx query "database connection" --fts \
  --language python \
  --path-filter "*/src/*" \
  --exclude-path "*/src/legacy/*" \
  --exclude-language javascript \
  --fuzzy
```

## Conversation Context

**Original Request**: User discovered `--language` and `--path-filter` don't work with FTS

**Key Insights**:
- FTS already has post-search filtering infrastructure (lines 451-459 in tantivy_index_manager.py)
- Parameters exist but implementation incomplete
- Semantic search uses LanguageMapper and PathPatternMatcher
- User explicitly requested: "can we add --language and --path-filter after the fact? after all, we do filter after the fact with semantic"

**Design Decision**: Post-search filtering (not Tantivy query integration) for:
- Simplicity (reuse existing Python filtering logic)
- Consistency (identical to semantic search implementation)
- Performance (adequate - <10ms overhead)
- Maintainability (single filtering codebase)

## Notes

- All stories follow TDD methodology (tests written first)
- Each story is independently testable and deployable
- Backward compatibility maintained throughout
- Performance targets validated at each step
- Documentation updated as features are completed

## Next Steps

1. Review stories for completeness
2. Assign stories to development sprint
3. Implement in order (Stories 1→6)
4. Run comprehensive test suite after each story
5. Update main documentation after completion
6. Close GitHub issue (if applicable)

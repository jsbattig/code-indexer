# Story: Filter Integration and Precedence

## Summary
Implement the core logic for combining inclusion and exclusion filters with proper precedence rules, ensuring exclusions override inclusions and all filter types work together seamlessly.

**Conversation Context**: "Exclusions take precedence over inclusions (intuitive behavior)" - Phase 5 architectural decision

## Description

### User Story
As a developer, I want to combine multiple inclusion and exclusion filters in a single query so that I can precisely target the files I want to search with complex criteria.

### Technical Context
This story integrates the separate language and path exclusion features into a cohesive filtering system that handles all combinations correctly. The implementation extends the existing filter construction at `cli.py` lines 3234-3256.

## Acceptance Criteria

### Functional Requirements
1. ✅ Combine language inclusions with path exclusions
2. ✅ Combine path inclusions with language exclusions
3. ✅ Handle multiple inclusions and exclusions together
4. ✅ Exclusions always override inclusions
5. ✅ Validate and warn about contradictory filters
6. ✅ Maintain backward compatibility

### Filter Combination Examples
```bash
# Language + Path combination
cidx query "database" --language python --exclude-path "*/tests/*"
# Result: Python files only, excluding test directories

# Multiple of each type
cidx query "api" \
    --language python --language go \
    --exclude-path "*/tests/*" --exclude-path "*/vendor/*" \
    --exclude-language javascript

# Contradictory (should warn)
cidx query "code" --language python --exclude-language python
# Warning: All Python files will be excluded due to conflicting filters

# Overlapping paths
cidx query "config" --path "*/src/*" --exclude-path "*/src/tests/*"
# Result: Files in src/ except src/tests/
```

## Technical Implementation

### 1. Unified Filter Builder
**File**: `src/code_indexer/cli.py`
```python
def build_search_filters(
    languages: Optional[List[str]] = None,
    paths: Optional[List[str]] = None,
    exclude_languages: Optional[List[str]] = None,
    exclude_paths: Optional[List[str]] = None,
    min_score: Optional[float] = None
) -> Optional[Dict]:
    """
    Build unified filter structure for search.

    Precedence: Exclusions override inclusions.
    """
    filters = {}
    must_conditions = []
    must_not_conditions = []

    # Build inclusion conditions
    if languages:
        for lang in languages:
            lang_lower = lang.lower()
            if lang_lower in LANGUAGE_MAPPER:
                for ext in LANGUAGE_MAPPER[lang_lower]:
                    must_conditions.append({
                        "field": "metadata.language",
                        "match": {"value": ext}
                    })

    if paths:
        for path_pattern in paths:
            normalized = path_pattern.replace('\\', '/')
            must_conditions.append({
                "field": "metadata.file_path",
                "match": {"value": normalized}
            })

    # Build exclusion conditions (higher precedence)
    if exclude_languages:
        for lang in exclude_languages:
            lang_lower = lang.lower()
            if lang_lower in LANGUAGE_MAPPER:
                for ext in LANGUAGE_MAPPER[lang_lower]:
                    must_not_conditions.append({
                        "field": "metadata.language",
                        "match": {"value": ext}
                    })

    if exclude_paths:
        for path_pattern in exclude_paths:
            normalized = path_pattern.replace('\\', '/')
            must_not_conditions.append({
                "field": "metadata.file_path",
                "match": {"value": normalized}
            })

    # Add score filter if specified
    if min_score is not None:
        must_conditions.append({
            "field": "score",
            "range": {"gte": min_score}
        })

    # Combine conditions
    if must_conditions:
        filters["must"] = must_conditions
    if must_not_conditions:
        filters["must_not"] = must_not_conditions

    # Validate for conflicts
    validate_filter_conflicts(filters, languages, exclude_languages)

    return filters if filters else None
```

### 2. Conflict Detection
```python
def validate_filter_conflicts(
    filters: Dict,
    languages: Optional[List[str]],
    exclude_languages: Optional[List[str]]
) -> None:
    """Detect and warn about conflicting filters."""

    # Check for language conflicts
    if languages and exclude_languages:
        conflicts = set(languages) & set(exclude_languages)
        if conflicts:
            console.print(
                f"[yellow]Warning: Conflicting language filters: {conflicts}. "
                "These languages will be excluded.[/yellow]"
            )

    # Check for overly broad exclusions
    if filters.get("must_not") and not filters.get("must"):
        console.print(
            "[yellow]Warning: Only exclusion filters specified. "
            "This may exclude most or all files.[/yellow]"
        )

    # Log final filter structure for debugging
    logger.debug(f"Final search filters: {json.dumps(filters, indent=2)}")
```

### 3. Integration Point
**Location**: `cli.py` query command (~line 3234)
```python
# Replace existing filter construction with unified builder
filters = build_search_filters(
    languages=languages,
    paths=paths,
    exclude_languages=exclude_languages,
    exclude_paths=exclude_paths,
    min_score=min_score
)

# Pass to search backend
results = search_service.search(
    query=query,
    filters=filters,
    limit=limit
)
```

## Test Requirements

### Unit Tests
1. **test_language_and_path_combination**: Both inclusion types
2. **test_inclusion_exclusion_precedence**: Exclusions override
3. **test_multiple_filter_types**: All four types together
4. **test_conflicting_filters_warning**: Detect conflicts
5. **test_empty_filter_handling**: No filters specified
6. **test_exclusion_only_filters**: Only must_not conditions
7. **test_complex_filter_merging**: Many conditions

### Integration Tests
```python
def test_complex_filter_integration():
    """Test complex filter combinations end-to-end."""
    # Setup test repository with various file types
    # Run query with complex filters
    # Verify correct files returned

def test_precedence_rules_e2e():
    """Verify exclusions override inclusions."""
    # Create file that matches both inclusion and exclusion
    # Verify it's excluded

def test_filter_performance_impact():
    """Measure performance with complex filters."""
    # Time queries with increasing filter complexity
    # Verify acceptable performance
```

## Implementation Steps

1. **Step 1**: Create unified `build_search_filters` function
2. **Step 2**: Implement conflict detection logic
3. **Step 3**: Add validation warnings for contradictions
4. **Step 4**: Replace existing filter construction
5. **Step 5**: Test all combinations work correctly
6. **Step 6**: Add debug logging for filter structure
7. **Step 7**: Performance testing with complex filters
8. **Step 8**: Update documentation with examples

## Validation Checklist

- [x] All filter types can be combined
- [x] Exclusions override inclusions
- [x] Conflicts are detected and warned
- [x] Empty filters handled correctly
- [x] Backward compatibility maintained
- [x] Debug logging shows filter structure
- [x] Performance acceptable (<5ms overhead)
- [x] Both backends handle combined filters

## Edge Cases

### Conflicting Filters
```bash
# Same language included and excluded
cidx query "test" --language python --exclude-language python
# Warning issued, no Python files returned

# Overlapping path patterns
cidx query "api" --path "*/src/*" --exclude-path "*/src/vendor/*"
# src/vendor excluded, rest of src/ included
```

### Extreme Cases
```bash
# Exclude everything
cidx query "test" --exclude-path "*"
# Warning: This will exclude all files

# Very narrow inclusion
cidx query "test" --path "*/specific/file.py" --language python
# Only matches if exact file exists
```

## Performance Considerations

### Filter Complexity
- O(n*m) where n = files, m = filter conditions
- Backend optimizations may improve this
- Consider filter ordering for early termination

### Benchmarks
- Simple query: <100ms
- 10 filter conditions: <150ms
- 50 filter conditions: <300ms
- Performance degradation should be linear

## Definition of Done

- [x] Unified filter builder implemented
- [x] Conflict detection working
- [x] All combinations tested
- [x] Performance benchmarks met
- [x] Warnings for edge cases
- [x] Debug logging added
- [ ] Documentation updated (Story 4.1)
- [x] Code reviewed
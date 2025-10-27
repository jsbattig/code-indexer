# Feature: Combined Exclusion Logic

## Overview

This feature implements the integration logic for combining multiple exclusion and inclusion filters, ensuring they work together correctly with proper precedence rules. It handles the complex interaction between `must` and `must_not` conditions.

**Conversation Context**: "Combined filters: `cidx query 'config' --language python --exclude-path '*/tests/*' --exclude-path '*/__pycache__/*'`"

## Business Value

### Problem Statement
Users need to combine multiple filter types (inclusion and exclusion) to create precise queries. The interaction between these filters must be intuitive and predictable, with exclusions taking precedence over inclusions.

### Expected Outcome
Users can create sophisticated filter combinations that precisely target the code they want to search, dramatically improving search relevance in complex codebases.

## Functional Requirements

### Filter Combinations
```bash
# Language inclusion + path exclusion
cidx query "database" --language python --exclude-path "*/tests/*"

# Path inclusion + language exclusion
cidx query "config" --path "*/src/*" --exclude-language javascript

# Multiple inclusions and exclusions
cidx query "api" \
    --language python \
    --path "*/src/*" \
    --exclude-path "*/tests/*" \
    --exclude-path "*/__pycache__/*" \
    --exclude-language javascript

# All filter types combined
cidx query "authentication" \
    --language python \
    --path "*/src/*" \
    --min-score 0.7 \
    --exclude-language javascript \
    --exclude-path "*/tests/*" \
    --limit 20
```

### Precedence Rules
**From Phase 5**: "Exclusions take precedence over inclusions (intuitive behavior)"

1. **Exclusions override inclusions**: If a file matches both inclusion and exclusion, it's excluded
2. **All exclusions are applied**: File must avoid ALL exclusion patterns
3. **Any inclusion matches**: File needs to match ANY inclusion pattern (if specified)

## Technical Design

### Filter Structure
```python
# Complete filter structure with all conditions
filters = {
    "must": [
        # Inclusion conditions (ANY match required)
        {"field": "metadata.language", "match": {"value": "py"}},
        {"field": "metadata.file_path", "match": {"value": "*/src/*"}}
    ],
    "must_not": [
        # Exclusion conditions (ALL must not match)
        {"field": "metadata.language", "match": {"value": "js"}},
        {"field": "metadata.file_path", "match": {"value": "*/tests/*"}}
    ]
}
```

### Filter Merging Logic
```python
def build_combined_filters(
    languages: List[str],
    paths: List[str],
    exclude_languages: List[str],
    exclude_paths: List[str]
) -> Dict:
    """Build combined filter structure."""
    filters = {}

    # Build inclusion conditions (must)
    must_conditions = []
    if languages:
        for lang in languages:
            # Add language inclusion conditions
            must_conditions.extend(build_language_filters(lang))
    if paths:
        for path in paths:
            # Add path inclusion conditions
            must_conditions.append(build_path_filter(path))

    # Build exclusion conditions (must_not)
    must_not_conditions = []
    if exclude_languages:
        for lang in exclude_languages:
            # Add language exclusion conditions
            must_not_conditions.extend(build_language_filters(lang))
    if exclude_paths:
        for path in exclude_paths:
            # Add path exclusion conditions
            must_not_conditions.append(build_path_filter(path))

    # Combine filters
    if must_conditions:
        filters["must"] = must_conditions
    if must_not_conditions:
        filters["must_not"] = must_not_conditions

    return filters if filters else None
```

## Acceptance Criteria

### Functional Criteria
1. ✅ Inclusion and exclusion filters can be combined
2. ✅ Exclusions take precedence over inclusions
3. ✅ Multiple filter types work together
4. ✅ Filter structure is valid for both backends
5. ✅ Empty filter combinations handled correctly
6. ✅ Performance remains acceptable with complex filters

### Behavioral Criteria
1. ✅ File excluded if matches ANY exclusion pattern
2. ✅ File included only if matches inclusion AND no exclusions
3. ✅ No filters means all files included
4. ✅ Only exclusions means exclude from all files
5. ✅ Conflicting filters resolved by exclusion precedence

## Test Requirements

### Test Scenarios
1. **Language inclusion + path exclusion**
2. **Path inclusion + language exclusion**
3. **Multiple inclusions + multiple exclusions**
4. **Conflicting filters (same file included and excluded)**
5. **Empty combinations**
6. **Only exclusions**
7. **Only inclusions**
8. **All filter types combined**

### Edge Cases
1. **Overlapping patterns**: `--path "*/src/*" --exclude-path "*/src/tests/*"`
2. **Contradictory filters**: `--language python --exclude-language python`
3. **Wide exclusions**: Excluding most files
4. **Narrow inclusions**: Very specific inclusion patterns

## Implementation Notes

### Key Considerations
1. **Filter Order**: Order of conditions shouldn't affect results
2. **Efficiency**: Minimize redundant conditions
3. **Clarity**: Clear logging of applied filters
4. **Validation**: Detect and warn about contradictory filters

### Implementation Location
**File**: `src/code_indexer/cli.py`
**Location**: Filter construction logic (lines 3234-3256)

### Pseudocode
```python
# Main filter construction
def construct_query_filters(params):
    filters = {}

    # Process inclusions
    if params.languages or params.paths:
        filters["must"] = []
        # Add inclusion conditions

    # Process exclusions
    if params.exclude_languages or params.exclude_paths:
        filters["must_not"] = []
        # Add exclusion conditions

    # Validate for conflicts
    validate_filter_combinations(filters)

    # Log final filter structure
    logger.debug(f"Final filters: {filters}")

    return filters
```

## Performance Considerations

### Filter Complexity Impact
- Each additional filter adds processing overhead
- Backend-specific optimizations may apply
- Consider filter ordering for efficiency

### Optimization Strategies
1. **Early termination**: Stop checking once excluded
2. **Filter caching**: Cache compiled patterns
3. **Backend hints**: Pass optimization hints to storage

## Conversation References

- **Combined Example**: "language python --exclude-path '*/tests/*' --exclude-path '*/__pycache__/*'"
- **Precedence Rule**: "Exclusions take precedence over inclusions"
- **Architecture Decision**: "Extend filter construction logic at cli.py lines 3234-3256"

## Definition of Done

- [ ] Filter merging logic implemented
- [ ] Precedence rules enforced
- [ ] Conflict detection and warnings
- [ ] All combinations tested
- [ ] Performance impact measured
- [ ] Documentation updated
- [ ] Code reviewed
- [ ] Integration tests passing
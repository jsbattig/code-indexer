# Story: Remove Qdrant Container Backend

## Story ID
`STORY-QDRANT-BACKEND-001`

## Parent Feature
`FEAT-QDRANT-REMOVAL-001`

## Title
Remove Qdrant Container Backend Infrastructure

## Status
PLANNED

## Priority
HIGH

## Story Points
5

## Assignee
TBD

## Story Summary

As a maintainer of code-indexer, I want to completely remove the Qdrant container backend infrastructure so that the codebase is simplified to use only the FilesystemVectorStore backend, reducing maintenance burden and eliminating confusion from dual backend systems.

## Acceptance Criteria

### Required Outcomes
1. **Backend Removal**
   - [ ] Delete src/code_indexer/vector_store/qdrant_container_backend.py (203 lines)
   - [ ] Remove QdrantClient service references from codebase

2. **Factory Simplification**
   - [ ] Update backend_factory.py to only return FilesystemBackend
   - [ ] Remove Qdrant backend type from factory logic
   - [ ] Ensure factory raises clear error for legacy "qdrant" backend requests

3. **Configuration Cleanup**
   - [ ] Remove QdrantConfig class from models.py
   - [ ] Remove qdrant_config field from ProjectConfig
   - [ ] Add validation to reject Qdrant configuration attempts

4. **Import Cleanup**
   - [ ] Remove Qdrant imports from 19+ server modules
   - [ ] Verify no unused imports remain with linting

5. **Test Removal**
   - [ ] Delete all test_qdrant_*.py files
   - [ ] Remove Qdrant-related test fixtures
   - [ ] Update test configuration to exclude Qdrant

6. **Manual Testing**
   - [ ] Verify init command works without Qdrant
   - [ ] Verify index command works without Qdrant
   - [ ] Verify query command works without Qdrant
   - [ ] Confirm error message appears for legacy Qdrant config

## Technical Details

### Implementation Steps

1. **Analyze Dependencies** (30 min)
   ```bash
   # Find all Qdrant imports
   grep -r "qdrant" src/ --include="*.py"
   grep -r "Qdrant" src/ --include="*.py"

   # List server modules with imports
   grep -r "from.*qdrant" src/code_indexer/server/
   ```

2. **Remove Backend Implementation** (1 hour)
   ```bash
   # Delete the backend file
   rm src/code_indexer/vector_store/qdrant_container_backend.py

   # Update __init__.py if needed
   # Remove from vector_store/__init__.py exports
   ```

3. **Update Backend Factory** (1 hour)
   ```python
   # In backend_factory.py, simplify to:
   def create_backend(...) -> VectorStoreBackend:
       if backend_type and backend_type != "filesystem":
           raise ValueError(
               f"Backend type '{backend_type}' is no longer supported. "
               "Code-indexer v8.0+ only supports filesystem backend. "
               "Please re-index your codebase."
           )
       return FilesystemBackend(...)
   ```

4. **Clean Configuration** (1 hour)
   ```python
   # In models.py, remove:
   # - QdrantConfig class
   # - qdrant_config: Optional[QdrantConfig] field
   # - Qdrant-related validators
   ```

5. **Server Module Cleanup** (2 hours)
   ```bash
   # For each server module with Qdrant imports:
   # 1. Remove import statements
   # 2. Remove any Qdrant-specific logic
   # 3. Verify module still compiles
   ```

6. **Test Cleanup** (1 hour)
   ```bash
   # Find and remove Qdrant tests
   find tests/ -name "*qdrant*.py" -delete

   # Remove from test configurations
   # Update conftest.py fixtures
   ```

### Files to Modify

**Delete:**
- src/code_indexer/vector_store/qdrant_container_backend.py
- tests/unit/vector_store/test_qdrant_container_backend.py
- tests/integration/qdrant/
- Any test_qdrant_*.py files

**Modify:**
- src/code_indexer/vector_store/backend_factory.py
- src/code_indexer/configuration/models.py
- src/code_indexer/server/ (19+ files with imports)
- tests/conftest.py (remove Qdrant fixtures)

### Error Handling

```python
# Add to backend_factory.py
def validate_no_qdrant_config(config):
    """Detect and reject legacy Qdrant configurations."""
    if hasattr(config, 'qdrant_config') and config.qdrant_config:
        raise ValueError(
            "Qdrant backend is no longer supported in v8.0+.\n"
            "Please remove qdrant_config from your configuration and re-index using filesystem backend.\n"
            "See migration guide: docs/migration-to-v8.md"
        )
```

## Test Requirements

### Unit Tests
- Test backend_factory returns FilesystemBackend only
- Test error raised for legacy "qdrant" backend type
- Test configuration validation rejects Qdrant config

### Integration Tests
- Test full init/index/query flow without Qdrant
- Test server starts without Qdrant dependencies
- Verify no Qdrant imports in server modules

### Manual Testing Checklist
1. [ ] Run `cidx init` in new project
2. [ ] Run `cidx index` successfully
3. [ ] Run `cidx query "test"` successfully
4. [ ] Attempt legacy config with qdrant_config - verify error
5. [ ] Run `./fast-automation.sh` - all tests pass
6. [ ] Check `./lint.sh` - no import errors

## Dependencies

### Blocked By
- None (can start immediately)

### Blocks
- Container infrastructure removal (some container code supports Qdrant)

## Definition of Done

1. [ ] All Qdrant code removed from codebase
2. [ ] Backend factory simplified to filesystem-only
3. [ ] Configuration rejects Qdrant settings with clear error
4. [ ] All server modules cleaned of Qdrant imports
5. [ ] All Qdrant tests removed
6. [ ] fast-automation.sh passes
7. [ ] Lint check passes
8. [ ] Manual testing confirms functionality
9. [ ] Code reviewed and approved

## Notes

### Conversation Context
From user request: "Remove legacy cruft related to deprecated infrastructure (Qdrant containers)"

### Key Risks
- Server modules may have hidden Qdrant dependencies
- Some tests may indirectly depend on Qdrant mocks
- Configuration migration needs clear messaging

### Implementation Tips
- Start with a comprehensive grep to find all references
- Test after each major deletion to catch breaks early
- Keep error messages helpful for users upgrading

## Time Tracking

### Estimates
- Analysis: 30 minutes
- Implementation: 5 hours
- Testing: 2 hours
- Code Review: 1 hour
- **Total**: 8.5 hours

### Actual
- Start Date: TBD
- End Date: TBD
- Actual Hours: TBD

## Revision History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2025-11-19 | 1.0 | System | Initial story creation |
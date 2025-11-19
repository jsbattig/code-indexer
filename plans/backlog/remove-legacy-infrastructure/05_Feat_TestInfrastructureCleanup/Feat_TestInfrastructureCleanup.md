# Feature: Test Infrastructure Cleanup

## Feature ID
`FEAT-TEST-CLEANUP-001`

## Parent Epic
`EPIC-LEGACY-REMOVAL-001`

## Title
Remove Container-Related Test Infrastructure

## Status
PLANNED

## Priority
MEDIUM

## Feature Owner
TBD

## Feature Summary

Remove all test infrastructure related to deprecated functionality including container management tests, Qdrant backend tests, and Ollama provider tests. This eliminates approximately 135 test files and ~6,000 lines of test code, significantly reducing test execution time and maintenance burden while ensuring the remaining tests provide comprehensive coverage of the production filesystem backend.

## Business Value

### Benefits
- Reduces test suite execution time by ~30%
- Eliminates ~6,000 lines of test code maintenance
- Simplifies test infrastructure and fixtures
- Faster CI/CD pipeline execution
- Clearer test coverage focus

### Impact
- **Development**: Faster test feedback loops
- **CI/CD**: Reduced pipeline execution time
- **Maintenance**: Less test code to maintain

## Technical Requirements

### Functional Requirements
1. Delete tests/integration/docker/ directory (~10 files)
2. Delete container manager E2E tests
3. Remove all Qdrant-specific tests
4. Remove all Ollama-specific tests
5. Remove deprecated test fixtures
6. Update test configuration files

### Non-Functional Requirements
- Maintain test coverage for filesystem backend
- Ensure no test dependencies remain
- fast-automation.sh must pass
- Test execution time should decrease

### Technical Constraints
- Must preserve core functionality tests
- Cannot reduce coverage of production features
- Must maintain test structure integrity

## Scope

### Included
- Container-related test removal
- Qdrant backend test removal
- Ollama provider test removal
- Test fixture cleanup
- Test configuration updates
- Pytest configuration cleanup

### Excluded
- Core functionality test modifications
- Test framework changes
- New test additions

## Dependencies

### Technical Dependencies
- Tests may import removed modules
- Test fixtures may reference deprecated components
- conftest.py may have legacy fixtures

### Feature Dependencies
- Must complete after Features 1-3 (code removal)
- Can run parallel with Feature 4

## Architecture & Design

### Test Directories to Remove
```
tests/
├── integration/
│   └── docker/                    # DELETE (entire directory)
├── e2e/
│   └── infrastructure/
│       └── test_container_*.py    # DELETE
├── unit/
│   ├── vector_store/
│   │   └── test_qdrant_*.py      # DELETE
│   └── embeddings/
│       └── test_ollama*.py       # DELETE
```

### Test Statistics
- Container tests: ~50 files
- Qdrant tests: ~35 files
- Ollama tests: ~10 files
- Related fixtures: ~40 files
- **Total**: ~135 files, ~6,000 lines

## Implementation Approach

### Phase 1: Test Discovery
- Identify all deprecated tests
- Map test dependencies
- Document fixture usage

### Phase 2: Test Removal
- Delete test directories
- Remove individual test files
- Clean up fixtures

### Phase 3: Configuration Cleanup
- Update pytest.ini
- Clean conftest.py
- Update test marks

### Phase 4: Validation
- Run fast-automation.sh
- Verify coverage metrics
- Check execution time

## Stories

### Story 1: Remove Container-Related Tests
- Delete deprecated test files
- Clean up test fixtures
- Update test configuration
- **Estimated Effort**: 2 days

## Acceptance Criteria

1. All container-related tests removed
2. All Qdrant backend tests removed
3. All Ollama provider tests removed
4. Test fixtures cleaned up
5. conftest.py updated
6. fast-automation.sh passes
7. Test execution time reduced
8. No import errors in remaining tests

## Test Strategy

### Coverage Validation
- Ensure filesystem backend coverage maintained
- Verify core functionality tests remain
- Check critical path coverage

### Execution Validation
- Run fast-automation.sh
- Measure execution time improvement
- Verify no broken imports

## Risks & Mitigations

### Risk 1: Removing Valid Tests
- **Impact**: HIGH
- **Mitigation**: Careful review of each test

### Risk 2: Breaking Test Dependencies
- **Impact**: MEDIUM
- **Mitigation**: Run tests after each removal batch

## Notes

### Conversation Context
- Part of removing "legacy cruft"
- Focus on reducing test burden
- ~150+ tests for deprecated functionality

### Implementation Order
- Fifth phase after code removal
- Can partially parallel with config cleanup
- Must complete before documentation

## Revision History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2025-11-19 | 1.0 | System | Initial feature specification |
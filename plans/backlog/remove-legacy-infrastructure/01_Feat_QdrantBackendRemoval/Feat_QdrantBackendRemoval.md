# Feature: Qdrant Backend Infrastructure Removal

## Feature ID
`FEAT-QDRANT-REMOVAL-001`

## Parent Epic
`EPIC-LEGACY-REMOVAL-001`

## Title
Remove Qdrant Container Backend Infrastructure

## Status
PLANNED

## Priority
HIGH (Critical Path)

## Feature Owner
TBD

## Feature Summary

Complete removal of the Qdrant container backend infrastructure including QdrantContainerBackend class, QdrantClient service integration, configuration fields, and all associated test infrastructure. This feature eliminates the deprecated vector storage backend that requires container orchestration, simplifying the codebase to focus exclusively on the FilesystemVectorStore backend.

## Business Value

### Benefits
- Eliminates 2,326+ lines of unused backend code
- Removes complexity of dual backend paradigms
- Reduces testing burden from Qdrant-specific tests
- Simplifies backend_factory to single implementation
- Removes confusion for new developers

### Impact
- **Development**: Faster build times, simpler debugging
- **Operations**: No container orchestration requirements
- **Testing**: Reduced test execution time

## Technical Requirements

### Functional Requirements
1. Delete QdrantContainerBackend class (203 lines)
2. Remove QdrantClient service integration
3. Update backend_factory to only return FilesystemBackend
4. Remove all Qdrant-specific configuration fields
5. Delete all Qdrant-specific tests
6. Update server modules that import Qdrant (19+ modules)

### Non-Functional Requirements
- Zero runtime errors from missing Qdrant imports
- Clear error messages if legacy Qdrant config detected
- No performance degradation in FilesystemBackend
- All remaining tests must pass

### Technical Constraints
- Must preserve VectorStoreBackend abstraction interface
- Cannot break existing FilesystemBackend functionality
- Must handle server module dependencies gracefully

## Scope

### Included
- src/code_indexer/vector_store/qdrant_container_backend.py deletion
- src/code_indexer/vector_store/backend_factory.py simplification
- Configuration schema updates to remove QdrantConfig
- Server module import cleanup (19+ files)
- Qdrant-specific test removal
- Error handling for legacy configurations

### Excluded
- FilesystemBackend modifications (except import cleanup)
- VectorStoreBackend interface changes
- Migration tools (users must re-index)

## Dependencies

### Technical Dependencies
- backend_factory used by multiple modules
- Server components have 19+ Qdrant imports
- Configuration system references QdrantConfig

### Feature Dependencies
- None (can be implemented first)

## Architecture & Design

### Components to Remove
```
src/code_indexer/
├── vector_store/
│   └── qdrant_container_backend.py  # DELETE (203 lines)
├── configuration/
│   └── models.py                    # MODIFY (remove QdrantConfig)
└── server/                          # MODIFY (19+ files with imports)
```

### Key Changes
1. **backend_factory.py**: Remove Qdrant case, always return FilesystemBackend
2. **Configuration**: Remove QdrantConfig class and fields
3. **Server modules**: Remove unused Qdrant imports
4. **Tests**: Delete all test_qdrant_*.py files

### Error Handling Strategy
- Detect legacy Qdrant configuration on startup
- Provide clear migration message
- Fail fast with actionable error

## Implementation Approach

### Phase 1: Analysis
- Identify all Qdrant import locations
- Map server module dependencies
- Document configuration touchpoints

### Phase 2: Removal
- Delete qdrant_container_backend.py
- Update backend_factory.py
- Clean server module imports

### Phase 3: Configuration Cleanup
- Remove QdrantConfig from models.py
- Update configuration validation
- Add legacy config detection

### Phase 4: Test Cleanup
- Delete Qdrant-specific tests
- Update integration tests
- Verify fast-automation.sh

## Stories

### Story 1: Remove Qdrant Container Backend
- Delete backend implementation
- Update factory and imports
- Remove configuration
- Clean up tests
- **Estimated Effort**: 3 days

## Acceptance Criteria

1. No references to QdrantContainerBackend in codebase
2. No references to QdrantClient in codebase
3. backend_factory.py only returns FilesystemBackend
4. No QdrantConfig in configuration schema
5. All Qdrant-specific tests removed
6. Server modules have no unused Qdrant imports
7. Clear error message for legacy Qdrant configurations
8. fast-automation.sh passes without Qdrant tests

## Test Strategy

### Test Coverage
- Verify FilesystemBackend still works
- Test legacy config error handling
- Validate server functionality without Qdrant
- End-to-end init/index/query testing

### Test Execution
1. Unit tests for backend_factory changes
2. Integration tests for configuration validation
3. E2E tests for complete workflow
4. Manual testing of error messages

## Risks & Mitigations

### Risk 1: Server Module Breakage
- **Impact**: HIGH
- **Mitigation**: Careful analysis of 19+ importing modules

### Risk 2: Hidden Qdrant Dependencies
- **Impact**: MEDIUM
- **Mitigation**: Comprehensive grep search before removal

## Notes

### Conversation Context
- User explicitly wants Qdrant removed as "legacy cruft"
- Focus on FilesystemVectorStore as only backend
- Part of larger legacy infrastructure removal

### Implementation Order
- Second phase after Ollama removal (lower risk)
- Before container infrastructure removal
- Critical path for simplification

## Revision History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2025-11-19 | 1.0 | System | Initial feature specification |
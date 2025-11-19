# Feature: Container Management Infrastructure Removal

## Feature ID
`FEAT-CONTAINER-REMOVAL-001`

## Parent Epic
`EPIC-LEGACY-REMOVAL-001`

## Title
Remove Container Management Infrastructure

## Status
PLANNED

## Priority
HIGH (Critical Path)

## Feature Owner
TBD

## Feature Summary

Complete removal of Docker and Podman container management infrastructure including DockerManager, ContainerManager, global port registry, and all associated container orchestration code. This eliminates ~1,800 lines of complex container management logic that was originally built to support the deprecated Qdrant backend, simplifying the codebase to its container-free filesystem architecture.

## Business Value

### Benefits
- Eliminates ~1,800 lines of container orchestration code
- Removes Docker/Podman runtime dependencies
- Simplifies deployment (no container requirements)
- Reduces operational complexity significantly
- Eliminates port management and conflicts

### Impact
- **Development**: No container runtime required for development
- **Operations**: Simplified deployment without orchestration
- **Testing**: Faster test execution without container overhead

## Technical Requirements

### Functional Requirements
1. Delete DockerManager class (~1,200 lines)
2. Delete ContainerManager class (~600 lines)
3. Remove global_port_registry (~403 lines)
4. Remove container-related CLI commands or adapt for daemon-only
5. Remove all container-related imports
6. Update any modules depending on container infrastructure

### Non-Functional Requirements
- No runtime errors from missing container imports
- Clear messaging if container commands attempted
- Preserve daemon functionality (non-container based)
- All remaining tests must pass

### Technical Constraints
- Must preserve daemon mode (uses Unix sockets, not containers)
- Cannot break existing filesystem backend operations
- Must handle CLI command transitions gracefully

## Scope

### Included
- src/code_indexer/infrastructure/docker_manager.py deletion
- src/code_indexer/infrastructure/container_manager.py deletion
- src/code_indexer/infrastructure/global_port_registry.py deletion
- CLI command updates (start/stop/restart adaptation)
- Container-related test removal
- Import cleanup across codebase

### Excluded
- Daemon mode changes (RPyC-based, not container)
- FilesystemBackend modifications
- Core indexing logic changes

## Dependencies

### Technical Dependencies
- CLI commands may reference container operations
- Some modules import container managers
- Configuration may have container settings

### Feature Dependencies
- Should complete after Qdrant removal (Qdrant uses containers)

## Architecture & Design

### Components to Remove
```
src/code_indexer/
├── infrastructure/
│   ├── docker_manager.py       # DELETE (~1,200 lines)
│   ├── container_manager.py    # DELETE (~600 lines)
│   └── global_port_registry.py # DELETE (~403 lines)
├── cli.py                      # MODIFY (remove/adapt commands)
└── configuration/
    └── models.py               # MODIFY (remove container config)
```

### Key Changes
1. **CLI Commands**: Adapt start/stop/restart for daemon-only operation
2. **Configuration**: Remove ProjectContainersConfig class
3. **Infrastructure**: Complete removal of container modules
4. **Tests**: Delete container-specific test suites

### Command Migration Strategy
- `cidx start` → Start daemon (if enabled), no containers
- `cidx stop` → Stop daemon (if running), no containers
- `cidx restart` → Restart daemon (if running), no containers

## Implementation Approach

### Phase 1: Analysis
- Map all container manager imports
- Identify CLI command dependencies
- Document configuration touchpoints

### Phase 2: Removal
- Delete infrastructure modules
- Update CLI commands
- Remove configuration classes

### Phase 3: Import Cleanup
- Remove unused imports
- Update module dependencies
- Fix any broken references

### Phase 4: Test Cleanup
- Delete container tests
- Update integration tests
- Verify fast-automation.sh

## Stories

### Story 1: Remove Container Infrastructure
- Delete container management modules
- Update CLI commands
- Remove configuration
- Clean up tests
- **Estimated Effort**: 3 days

## Acceptance Criteria

1. No DockerManager class in codebase
2. No ContainerManager class in codebase
3. No global_port_registry module
4. CLI commands work without container operations
5. No container-related configuration remains
6. All container-specific tests removed
7. Clear messages for legacy container operations
8. fast-automation.sh passes without container tests

## Test Strategy

### Test Coverage
- Verify daemon mode still works (non-container)
- Test CLI commands function correctly
- Validate no container operations attempted
- End-to-end workflow testing

### Test Execution
1. Unit tests for CLI command changes
2. Integration tests for daemon mode
3. E2E tests for complete workflow
4. Manual testing of command transitions

## Risks & Mitigations

### Risk 1: CLI Command Confusion
- **Impact**: MEDIUM
- **Mitigation**: Clear help text and error messages

### Risk 2: Hidden Container Dependencies
- **Impact**: HIGH
- **Mitigation**: Comprehensive dependency analysis first

## Notes

### Conversation Context
- User wants container management removed as "legacy cruft"
- Focus on simplified, container-free architecture
- Part of larger legacy infrastructure removal

### Implementation Order
- Third phase after Qdrant removal
- Highest risk due to extensive integration
- Critical for operational simplification

## Revision History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2025-11-19 | 1.0 | System | Initial feature specification |
# Epic: Remove Legacy Infrastructure

## Epic ID
`EPIC-LEGACY-REMOVAL-001`

## Title
Remove Legacy Infrastructure (Qdrant, Containers, Ollama)

## Status
PLANNED

## Priority
HIGH

## Epic Owner
TBD

## Stakeholders
- Development Team (primary)
- DevOps Team (secondary)
- Product Management (informed)

## Target Release
v8.0.0

## Epic Summary

Remove all legacy infrastructure code related to deprecated backends and container management from the code-indexer codebase. This includes complete removal of Qdrant container backend, Docker/Podman container management, and Ollama embedding provider support. The codebase will be simplified to focus exclusively on the production FilesystemVectorStore backend, reducing maintenance burden and eliminating confusion from dual backend systems.

## Business Context

### Problem Statement
The code-indexer codebase contains significant legacy cruft from deprecated infrastructure approaches that are no longer used in production. This includes ~15,000+ lines of code for container management, Qdrant backend support, and Ollama integration that create maintenance burden, confuse new developers, and complicate the testing infrastructure.

### Business Value
- **Reduced Maintenance Costs**: Eliminate ~15,000+ lines of unused code requiring maintenance
- **Improved Developer Velocity**: Simpler codebase with single backend paradigm
- **Reduced Testing Time**: Remove ~135 test files for deprecated functionality
- **Lower Operational Complexity**: No container orchestration or multi-backend confusion
- **Clearer Architecture**: Single, focused filesystem-based approach

### Success Metrics
- Zero code references to Qdrant management, container management, or Ollama
- All remaining tests pass (fast-automation.sh)
- Test suite execution time reduced by ~30%
- Documentation accurately reflects simplified architecture
- No regression in core query functionality

## User Stories & Requirements

### Primary Users
- **Maintainers**: Need cleaner codebase without legacy burden
- **Developers**: Need simplified architecture without confusing dual-backend systems
- **New Contributors**: Need clear, single-paradigm codebase

### Key Requirements
1. Complete removal of Qdrant backend infrastructure
2. Complete removal of container management code
3. Complete removal of Ollama embedding provider
4. Preservation of FilesystemVectorStore functionality
5. Clear error messages for users attempting legacy configurations
6. Updated documentation reflecting simplified architecture

## Technical Scope

### Included
- QdrantContainerBackend removal (2,326 lines)
- DockerManager/ContainerManager removal (~1,800 lines)
- OllamaClient removal (191 lines)
- Container-related test removal (~6,000 lines)
- Configuration schema simplification
- CLI command cleanup
- Documentation updates

### Excluded
- FilesystemVectorStore modifications (except import cleanup)
- VoyageAI embedding provider changes
- Core query functionality changes
- MCP/REST API functional changes

### Dependencies
- No external dependencies
- Internal dependency on VectorStoreBackend abstraction preservation

## Architecture & Design

### Current State
- Dual backend system (Filesystem + Qdrant)
- Container orchestration for Qdrant
- Multiple embedding providers (VoyageAI + Ollama)
- Complex configuration with legacy fields
- 135+ test files including deprecated functionality

### Target State
- Single backend (FilesystemVectorStore only)
- No container dependencies
- Single embedding provider (VoyageAI only)
- Simplified configuration schema
- Streamlined test suite

### Key Architectural Decisions
- **No Migration Path**: Incompatible storage paradigms require users to re-index
- **Fail-Fast Strategy**: Clear error messages for legacy configuration attempts
- **Complete Removal**: No stub implementations or compatibility layers
- **Version Bump**: v8.0.0 to signal breaking changes
- **Backend Abstraction Preserved**: Keep VectorStoreBackend interface for future extensibility

## Implementation Plan

### Phase 1: Ollama Removal (Lowest Risk)
- Remove ollama.py and OllamaClient
- Update embedding_factory
- Remove Ollama tests
- **Estimated Effort**: 2 days

### Phase 2: Qdrant Backend Removal (Medium Risk)
- Remove QdrantContainerBackend
- Update backend_factory
- Update server modules (19+ imports)
- Remove Qdrant tests
- **Estimated Effort**: 3 days

### Phase 3: Container Infrastructure Removal (Highest Risk)
- Remove DockerManager and ContainerManager
- Remove global_port_registry
- Update CLI commands
- Remove container tests
- **Estimated Effort**: 3 days

### Phase 4: Configuration & CLI Cleanup
- Remove deprecated config classes
- Simplify CLI help and commands
- Add legacy config error handling
- **Estimated Effort**: 2 days

### Phase 5: Test Infrastructure Cleanup
- Remove 135+ deprecated test files
- Update test configurations
- Verify fast-automation.sh
- **Estimated Effort**: 2 days

### Phase 6: Documentation Updates
- Update README.md
- Update CLAUDE.md
- Update architecture docs
- Add migration guide
- **Estimated Effort**: 1 day

**Total Estimated Effort**: 13 days

## Features

### F1: Qdrant Backend Infrastructure Removal
- **Priority**: HIGH
- **Description**: Complete removal of Qdrant container backend and related infrastructure
- **Stories**: 1 story

### F2: Container Management Infrastructure Removal
- **Priority**: HIGH
- **Description**: Complete removal of Docker/Podman container management code
- **Stories**: 1 story

### F3: Ollama Embedding Provider Removal
- **Priority**: HIGH
- **Description**: Complete removal of Ollama embedding provider support
- **Stories**: 1 story

### F4: Configuration & CLI Cleanup
- **Priority**: MEDIUM
- **Description**: Simplification of configuration schema and CLI commands
- **Stories**: 1 story

### F5: Test Infrastructure Cleanup
- **Priority**: MEDIUM
- **Description**: Removal of deprecated test infrastructure
- **Stories**: 1 story

### F6: Documentation Updates
- **Priority**: LOW
- **Description**: Update all documentation to reflect simplified architecture
- **Stories**: 1 story

## Risks & Mitigations

### Risk 1: Hidden Dependencies
- **Impact**: HIGH
- **Probability**: MEDIUM
- **Mitigation**: Comprehensive grep/ast analysis before removal, phased approach

### Risk 2: User Disruption
- **Impact**: MEDIUM
- **Probability**: HIGH
- **Mitigation**: Clear v8.0.0 version bump, migration guide, error messages

### Risk 3: Test Coverage Gaps
- **Impact**: MEDIUM
- **Probability**: LOW
- **Mitigation**: Verify core functionality tests remain, add missing coverage

## Acceptance Criteria

1. All Qdrant-related code removed from codebase
2. All container management code removed from codebase
3. All Ollama-related code removed from codebase
4. fast-automation.sh passes with all remaining tests
5. No imports of removed modules remain
6. Documentation accurately describes simplified architecture
7. Clear error messages for legacy configuration attempts
8. CHANGELOG.md includes breaking changes notice
9. Version bumped to v8.0.0

## Notes

### Conversation Context
- User explicitly requested removal of "legacy cruft" related to Qdrant containers and Ollama
- Focus on production FilesystemVectorStore backend only
- Emphasis on reducing maintenance burden and simplifying codebase

### Implementation Notes
- Start with Ollama (least dependencies)
- Qdrant removal requires updating 19+ importing modules
- Container removal is highest risk due to extensive integration
- No backward compatibility required (breaking change release)

## Revision History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2025-11-19 | 1.0 | System | Initial epic creation based on conversation context |
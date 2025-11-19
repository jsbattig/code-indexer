# Feature: Configuration & CLI Cleanup

## Feature ID
`FEAT-CONFIG-CLEANUP-001`

## Parent Epic
`EPIC-LEGACY-REMOVAL-001`

## Title
Clean Up Configuration Schema and CLI Commands

## Status
PLANNED

## Priority
MEDIUM

## Feature Owner
TBD

## Feature Summary

Simplify the configuration schema and CLI interface by removing all legacy configuration classes, deprecated command options, and container-related settings. Add clear error messages and migration guidance for users attempting to use removed features. This creates a cleaner, more maintainable configuration system focused on the filesystem backend.

## Business Value

### Benefits
- Simplified configuration with fewer confusing options
- Clearer CLI interface without deprecated commands
- Better user experience with helpful error messages
- Reduced configuration validation complexity
- Easier onboarding for new users

### Impact
- **Development**: Simpler configuration to maintain
- **Operations**: Fewer configuration errors
- **Users**: Clearer upgrade path with good messaging

## Technical Requirements

### Functional Requirements
1. Remove QdrantConfig class from configuration
2. Remove OllamaConfig class from configuration
3. Remove ProjectContainersConfig class
4. Remove container-related CLI commands/options
5. Add validation for legacy configurations
6. Provide clear migration error messages

### Non-Functional Requirements
- Backward compatibility detection with clear errors
- Helpful migration guidance in error messages
- Clean CLI help output
- Configuration validation must be comprehensive

### Technical Constraints
- Must preserve valid configuration options
- Cannot break existing filesystem backend configs
- Must maintain configuration file compatibility

## Scope

### Included
- Configuration model cleanup (models.py)
- CLI command and option removal
- Legacy configuration detection
- Migration error messages
- CLI help text updates
- Configuration validation updates

### Excluded
- Core configuration structure changes
- YAML/JSON parsing modifications
- New configuration features

## Dependencies

### Technical Dependencies
- Depends on prior removal of Qdrant, Ollama, Containers
- Configuration validation throughout codebase
- CLI command structure

### Feature Dependencies
- Must complete after Features 1-3 (infrastructure removal)

## Architecture & Design

### Components to Modify
```
src/code_indexer/
├── configuration/
│   ├── models.py              # Remove legacy classes
│   └── validator.py           # Add legacy detection
├── cli.py                     # Remove deprecated options
└── commands/                  # Update command help
```

### Configuration Classes to Remove
- QdrantConfig
- OllamaConfig
- ProjectContainersConfig
- Related validator functions

### CLI Changes
- Remove `--backend qdrant` option
- Remove `--embedding-provider ollama` option
- Remove container-specific flags
- Simplify start/stop/restart commands

## Implementation Approach

### Phase 1: Configuration Cleanup
- Remove legacy config classes
- Update model validators
- Add legacy detection

### Phase 2: CLI Simplification
- Remove deprecated options
- Update command help text
- Clean up command logic

### Phase 3: Error Handling
- Add migration validators
- Create helpful error messages
- Test user experience

### Phase 4: Documentation
- Update CLI help
- Create migration guide
- Update examples

## Stories

### Story 1: Clean Up Configuration Schema and CLI
- Remove legacy configuration classes
- Update CLI commands and options
- Add migration error handling
- **Estimated Effort**: 2 days

## Acceptance Criteria

1. No legacy configuration classes in models.py
2. CLI has no deprecated options
3. Clear error messages for legacy configs
4. Migration guidance in error output
5. Clean CLI help text
6. Configuration validation works correctly
7. fast-automation.sh passes
8. User experience tested and documented

## Test Strategy

### Test Coverage
- Configuration validation tests
- CLI command tests
- Legacy detection tests
- Error message validation

### Test Execution
1. Unit tests for configuration models
2. Integration tests for CLI commands
3. E2E tests for user workflows
4. Manual testing of error scenarios

## Risks & Mitigations

### Risk 1: Breaking Valid Configs
- **Impact**: HIGH
- **Mitigation**: Careful validation, extensive testing

### Risk 2: Poor Migration Experience
- **Impact**: MEDIUM
- **Mitigation**: Clear error messages, migration guide

## Notes

### Conversation Context
- Part of removing "legacy cruft" from codebase
- Focus on simplification and clarity
- Must happen after infrastructure removal

### Implementation Order
- Fourth phase after infrastructure removal
- Medium priority (depends on 1-3)
- Focus on user experience

## Revision History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2025-11-19 | 1.0 | System | Initial feature specification |
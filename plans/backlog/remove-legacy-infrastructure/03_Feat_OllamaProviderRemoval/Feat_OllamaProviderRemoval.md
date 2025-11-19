# Feature: Ollama Embedding Provider Removal

## Feature ID
`FEAT-OLLAMA-REMOVAL-001`

## Parent Epic
`EPIC-LEGACY-REMOVAL-001`

## Title
Remove Ollama Embedding Provider Support

## Status
PLANNED

## Priority
HIGH (Critical Path)

## Feature Owner
TBD

## Feature Summary

Complete removal of the Ollama embedding provider infrastructure including OllamaClient, OllamaConfig, and all associated integration code. This eliminates the experimental, non-production embedding provider that is too slow for practical use, focusing the codebase exclusively on the production-ready VoyageAI embedding provider.

## Business Value

### Benefits
- Eliminates 192 lines of unused embedding provider code
- Removes confusion about which provider to use
- Simplifies embedding_factory to single provider
- Reduces testing burden from Ollama-specific tests
- Clarifies production vs experimental features

### Impact
- **Development**: Clearer embedding provider strategy
- **Operations**: No Ollama server management required
- **Performance**: Focus on optimizing single provider

## Technical Requirements

### Functional Requirements
1. Delete ollama.py embedding provider (192 lines)
2. Remove OllamaClient class and integration
3. Remove OllamaConfig from configuration
4. Update embedding_factory to only support VoyageAI
5. Remove Ollama from CLI options
6. Delete all Ollama-specific tests

### Non-Functional Requirements
- Zero runtime errors from missing Ollama imports
- Clear error messages if Ollama provider requested
- No degradation in VoyageAI provider functionality
- All remaining tests must pass

### Technical Constraints
- Must preserve EmbeddingProvider abstraction interface
- Cannot break existing VoyageAI functionality
- Must handle provider selection gracefully

## Scope

### Included
- src/code_indexer/embeddings/ollama.py deletion
- src/code_indexer/embeddings/embedding_factory.py simplification
- Configuration schema updates to remove OllamaConfig
- CLI option removal for Ollama provider
- Ollama-specific test removal
- Error handling for legacy Ollama requests

### Excluded
- VoyageAI provider modifications
- EmbeddingProvider interface changes
- Token counting optimizations

## Dependencies

### Technical Dependencies
- embedding_factory used by indexing pipeline
- Configuration system references OllamaConfig
- CLI has provider selection options

### Feature Dependencies
- None (lowest risk, can be implemented first)

## Architecture & Design

### Components to Remove
```
src/code_indexer/
├── embeddings/
│   └── ollama.py                    # DELETE (192 lines)
├── configuration/
│   └── models.py                    # MODIFY (remove OllamaConfig)
├── embeddings/
│   └── embedding_factory.py        # MODIFY (remove Ollama case)
└── cli.py                          # MODIFY (remove --ollama option)
```

### Key Changes
1. **embedding_factory.py**: Remove Ollama case, only return VoyageAI
2. **Configuration**: Remove OllamaConfig class and fields
3. **CLI**: Remove provider selection for Ollama
4. **Tests**: Delete all test_ollama_*.py files

### Error Handling Strategy
- Detect legacy Ollama configuration
- Provide clear migration message
- Default to VoyageAI with notification

## Implementation Approach

### Phase 1: Analysis
- Identify all Ollama references
- Map embedding_factory usage
- Document CLI option locations

### Phase 2: Removal
- Delete ollama.py
- Update embedding_factory.py
- Clean configuration schema

### Phase 3: CLI Updates
- Remove Ollama provider option
- Update help text
- Add legacy detection

### Phase 4: Test Cleanup
- Delete Ollama-specific tests
- Update integration tests
- Verify fast-automation.sh

## Stories

### Story 1: Remove Ollama Embedding Provider
- Delete provider implementation
- Update factory and configuration
- Remove CLI options
- Clean up tests
- **Estimated Effort**: 2 days

## Acceptance Criteria

1. No references to OllamaClient in codebase
2. No references to OllamaConfig in codebase
3. embedding_factory.py only supports VoyageAI
4. CLI has no Ollama provider option
5. All Ollama-specific tests removed
6. Clear error message for Ollama provider requests
7. fast-automation.sh passes without Ollama tests
8. VoyageAI provider works correctly

## Test Strategy

### Test Coverage
- Verify VoyageAI provider still works
- Test legacy Ollama request handling
- Validate embedding pipeline functionality
- End-to-end indexing with VoyageAI only

### Test Execution
1. Unit tests for embedding_factory changes
2. Integration tests for indexing pipeline
3. E2E tests for complete workflow
4. Manual testing of provider selection

## Risks & Mitigations

### Risk 1: Hidden Ollama Dependencies
- **Impact**: LOW
- **Mitigation**: Simple grep search sufficient

### Risk 2: User Confusion
- **Impact**: LOW
- **Mitigation**: Clear documentation and messages

## Notes

### Conversation Context
- User explicitly wants Ollama removed as "legacy cruft"
- Ollama noted as "NOT for production - too slow"
- Focus on VoyageAI as only production provider

### Implementation Order
- First phase (lowest risk)
- Simplest removal with least dependencies
- Good starting point for legacy cleanup

## Revision History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2025-11-19 | 1.0 | System | Initial feature specification |
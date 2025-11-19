# Story: Remove Ollama Embedding Provider

## Story ID
`STORY-OLLAMA-PROVIDER-001`

## Parent Feature
`FEAT-OLLAMA-REMOVAL-001`

## Title
Remove Ollama Embedding Provider Support

## Status
PLANNED

## Priority
HIGH

## Story Points
3

## Assignee
TBD

## Story Summary

As a maintainer of code-indexer, I want to completely remove the Ollama embedding provider so that the codebase focuses exclusively on the production-ready VoyageAI provider, eliminating the experimental and too-slow Ollama integration that adds no production value.

## Acceptance Criteria

### Required Outcomes
1. **Provider Removal**
   - [ ] Delete src/code_indexer/embeddings/ollama.py (192 lines)
   - [ ] Remove OllamaClient class completely

2. **Factory Simplification**
   - [ ] Update embedding_factory.py to only support VoyageAI
   - [ ] Remove Ollama provider type from factory logic
   - [ ] Ensure factory raises clear error for "ollama" provider requests

3. **Configuration Cleanup**
   - [ ] Remove OllamaConfig class from models.py
   - [ ] Remove ollama_config field from configuration
   - [ ] Add validation to reject Ollama configuration

4. **CLI Updates**
   - [ ] Remove `--embedding-provider ollama` option
   - [ ] Update help text to show VoyageAI as only option
   - [ ] Remove any Ollama-specific CLI parameters

5. **Test Removal**
   - [ ] Delete all test_ollama_*.py files
   - [ ] Remove Ollama-related test fixtures
   - [ ] Update test configuration

6. **Manual Testing**
   - [ ] Verify VoyageAI provider works correctly
   - [ ] Verify error for legacy Ollama requests
   - [ ] Confirm full indexing pipeline works
   - [ ] Test embedding generation with VoyageAI

## Technical Details

### Implementation Steps

1. **Analyze Dependencies** (15 min)
   ```bash
   # Find all Ollama references
   grep -r "ollama" src/ --include="*.py" -i
   grep -r "Ollama" src/ --include="*.py"

   # Check embedding_factory usage
   grep -r "embedding_factory" src/ --include="*.py"
   ```

2. **Remove Provider Implementation** (30 min)
   ```bash
   # Delete the provider file
   rm src/code_indexer/embeddings/ollama.py

   # Update __init__.py if needed
   # Remove from embeddings/__init__.py exports
   ```

3. **Update Embedding Factory** (45 min)
   ```python
   # In embedding_factory.py, simplify to:
   def create_embedding_provider(...) -> EmbeddingProvider:
       if provider_type and provider_type != "voyageai":
           raise ValueError(
               f"Embedding provider '{provider_type}' is no longer supported. "
               "Code-indexer v8.0+ only supports VoyageAI embeddings. "
               "Please update your configuration to use VoyageAI."
           )
       return VoyageAIProvider(...)
   ```

4. **Clean Configuration** (30 min)
   ```python
   # In models.py, remove:
   # - OllamaConfig class
   # - ollama_config: Optional[OllamaConfig] field
   # - Ollama-related validators

   # Add validation:
   def validate_no_ollama_config(config):
       if hasattr(config, 'ollama_config') and config.ollama_config:
           raise ValueError(
               "Ollama embedding provider is no longer supported in v8.0+.\n"
               "Please use VoyageAI for production embeddings.\n"
               "Update your configuration to remove ollama_config."
           )
   ```

5. **Update CLI** (30 min)
   ```python
   # In cli.py, remove:
   # - --embedding-provider option (or make VoyageAI-only)
   # - Any Ollama-specific parameters

   # Update help text:
   @click.option(
       '--embedding-provider',
       type=click.Choice(['voyageai']),
       default='voyageai',
       help='Embedding provider (VoyageAI only in v8.0+)'
   )
   ```

6. **Test Cleanup** (30 min)
   ```bash
   # Find and remove Ollama tests
   find tests/ -name "*ollama*.py" -delete

   # Remove from test configurations
   grep -r "ollama" tests/ --include="*.py" -i
   ```

### Files to Modify

**Delete:**
- src/code_indexer/embeddings/ollama.py
- tests/unit/embeddings/test_ollama.py
- Any other test_ollama_*.py files

**Modify:**
- src/code_indexer/embeddings/embedding_factory.py
- src/code_indexer/configuration/models.py
- src/code_indexer/cli.py
- src/code_indexer/embeddings/__init__.py
- tests/conftest.py (remove Ollama fixtures)

### Error Handling

```python
# Add to embedding_factory.py
def validate_provider_type(provider_type: str):
    """Validate embedding provider type."""
    valid_providers = ['voyageai']
    if provider_type not in valid_providers:
        raise ValueError(
            f"Invalid embedding provider: '{provider_type}'.\n"
            f"Valid options: {', '.join(valid_providers)}\n"
            "Note: Ollama support was removed in v8.0+ due to performance issues."
        )
```

## Test Requirements

### Unit Tests
- Test embedding_factory returns VoyageAI only
- Test error raised for "ollama" provider type
- Test configuration validation rejects Ollama config

### Integration Tests
- Test full indexing with VoyageAI provider
- Test embedding generation pipeline
- Verify no Ollama imports remain

### Manual Testing Checklist
1. [ ] Run `cidx init` - uses VoyageAI by default
2. [ ] Run `cidx index` - embeddings generated with VoyageAI
3. [ ] Run `cidx query "test"` - search works with VoyageAI embeddings
4. [ ] Attempt `--embedding-provider ollama` - verify error
5. [ ] Attempt config with ollama_config - verify rejection
6. [ ] Run `./fast-automation.sh` - all tests pass
7. [ ] Check `./lint.sh` - no import errors

## Dependencies

### Blocked By
- None (can start immediately - lowest risk)

### Blocks
- None (independent of other removals)

## Definition of Done

1. [ ] All Ollama code removed from codebase
2. [ ] Embedding factory simplified to VoyageAI-only
3. [ ] Configuration rejects Ollama settings
4. [ ] CLI updated to remove Ollama options
5. [ ] All Ollama tests removed
6. [ ] VoyageAI provider verified working
7. [ ] fast-automation.sh passes
8. [ ] Lint check passes
9. [ ] Manual testing confirms functionality
10. [ ] Code reviewed and approved

## Notes

### Conversation Context
From user request: "Remove legacy cruft" including Ollama
From CLAUDE.md: "Ollama (EXPERIMENTAL) - NOT for production - Too slow"

### Key Advantages of Starting Here
- Lowest risk removal (minimal dependencies)
- Clear boundaries (single provider file)
- Simple factory update
- Good warm-up for larger removals

### Implementation Tips
- This is the easiest removal - start here
- Test VoyageAI thoroughly after changes
- Update any documentation mentioning Ollama
- Clear error messages for migration

## Time Tracking

### Estimates
- Analysis: 15 minutes
- Implementation: 2.5 hours
- Testing: 1.5 hours
- Code Review: 30 minutes
- **Total**: 4.5 hours

### Actual
- Start Date: TBD
- End Date: TBD
- Actual Hours: TBD

## Revision History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2025-11-19 | 1.0 | System | Initial story creation |
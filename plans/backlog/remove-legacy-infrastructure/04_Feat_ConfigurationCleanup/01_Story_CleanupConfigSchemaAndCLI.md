# Story: Clean Up Configuration Schema and CLI

## Story ID
`STORY-CONFIG-CLI-001`

## Parent Feature
`FEAT-CONFIG-CLEANUP-001`

## Title
Clean Up Configuration Schema and CLI Commands

## Status
PLANNED

## Priority
MEDIUM

## Story Points
5

## Assignee
TBD

## Story Summary

As a user of code-indexer, I want the configuration and CLI to be simplified without legacy options so that I have a clear, unambiguous interface focused on the filesystem backend, with helpful error messages if I try to use deprecated features.

## Acceptance Criteria

### Required Outcomes
1. **Configuration Schema Cleanup**
   - [ ] Remove QdrantConfig class from models.py
   - [ ] Remove OllamaConfig class from models.py
   - [ ] Remove ProjectContainersConfig class from models.py
   - [ ] Remove related configuration fields from ProjectConfig
   - [ ] Remove associated validator functions

2. **CLI Option Removal**
   - [ ] Remove `--backend` option or restrict to filesystem only
   - [ ] Remove `--embedding-provider` option or restrict to voyageai only
   - [ ] Remove container-related flags from all commands
   - [ ] Update all command help text

3. **Legacy Detection**
   - [ ] Add validator to detect Qdrant configuration
   - [ ] Add validator to detect Ollama configuration
   - [ ] Add validator to detect container configuration
   - [ ] Provide specific migration message for each

4. **Error Messages**
   - [ ] Clear message for deprecated backend attempts
   - [ ] Clear message for deprecated provider attempts
   - [ ] Clear message for container operations
   - [ ] Include version info and migration guide reference

5. **Command Updates**
   - [ ] Simplify `cidx start` for daemon-only
   - [ ] Simplify `cidx stop` for daemon-only
   - [ ] Simplify `cidx restart` for daemon-only
   - [ ] Remove any container-specific subcommands

6. **Manual Testing**
   - [ ] Test all legacy config rejection paths
   - [ ] Verify clean CLI help output
   - [ ] Confirm simplified commands work
   - [ ] Check error message clarity

## Technical Details

### Implementation Steps

1. **Analyze Current Configuration** (30 min)
   ```python
   # In models.py, identify all classes to remove:
   # - QdrantConfig
   # - OllamaConfig
   # - ProjectContainersConfig
   # - Any related nested configs
   ```

2. **Remove Configuration Classes** (1 hour)
   ```python
   # In models.py, remove classes and update ProjectConfig:
   class ProjectConfig(BaseModel):
       # Remove these fields:
       # qdrant_config: Optional[QdrantConfig] = None
       # ollama_config: Optional[OllamaConfig] = None
       # containers_config: Optional[ProjectContainersConfig] = None

       # Keep only:
       project_root: Path
       backend_type: str = "filesystem"  # Make filesystem-only
       embedding_provider: str = "voyageai"  # Make voyageai-only
       # ... other valid fields
   ```

3. **Add Legacy Validators** (1 hour)
   ```python
   # In validator.py or models.py:
   def validate_configuration(config_dict: Dict) -> None:
       """Validate configuration and reject legacy options."""

       if 'qdrant_config' in config_dict:
           raise ValueError(
               "Qdrant backend configuration detected.\n"
               "Qdrant support was removed in v8.0.0.\n"
               "Please remove 'qdrant_config' and use the filesystem backend.\n"
               "See migration guide: docs/migration-to-v8.md"
           )

       if 'ollama_config' in config_dict:
           raise ValueError(
               "Ollama provider configuration detected.\n"
               "Ollama support was removed in v8.0.0.\n"
               "Please remove 'ollama_config' and use VoyageAI.\n"
               "See migration guide: docs/migration-to-v8.md"
           )

       if 'containers_config' in config_dict:
           raise ValueError(
               "Container configuration detected.\n"
               "Container support was removed in v8.0.0.\n"
               "Code-indexer now runs container-free.\n"
               "Please remove 'containers_config' from your configuration."
           )

       if config_dict.get('backend_type') not in [None, 'filesystem']:
           raise ValueError(
               f"Invalid backend type: '{config_dict['backend_type']}'.\n"
               "Only 'filesystem' backend is supported in v8.0.0+.\n"
               "Please update your configuration."
           )
   ```

4. **Update CLI Options** (2 hours)
   ```python
   # In cli.py, update options:

   # Remove or restrict backend option:
   @click.option(
       '--backend',
       type=click.Choice(['filesystem']),
       default='filesystem',
       help='Storage backend (filesystem only in v8.0+)'
   )

   # Remove or restrict provider option:
   @click.option(
       '--embedding-provider',
       type=click.Choice(['voyageai']),
       default='voyageai',
       help='Embedding provider (VoyageAI only in v8.0+)'
   )

   # Simplify commands:
   @cli.command()
   @click.pass_context
   def start(ctx):
       """Start the daemon service."""
       config = ctx.obj['config']
       if not config.daemon_config.enabled:
           console.print("[red]Daemon mode is not enabled.[/red]")
           console.print("Enable with: cidx config --daemon")
           return
       # Simple daemon start logic, no container references
   ```

5. **Clean Command Help** (30 min)
   ```python
   # Update all command docstrings:
   """Start the daemon service.

   The daemon runs in the background to cache indexes for faster queries.
   No containers are used - runs as a local process.
   """
   ```

6. **Test Configuration Loading** (1 hour)
   ```python
   # Add tests for legacy rejection:
   def test_reject_qdrant_config():
       config = {"qdrant_config": {...}}
       with pytest.raises(ValueError, match="Qdrant support was removed"):
           validate_configuration(config)
   ```

### Files to Modify

**Primary Changes:**
- src/code_indexer/configuration/models.py (remove classes)
- src/code_indexer/configuration/validator.py (add legacy detection)
- src/code_indexer/cli.py (simplify options and commands)

**Secondary Changes:**
- src/code_indexer/commands/*.py (update any command modules)
- tests/unit/configuration/test_models.py (remove legacy tests)
- tests/unit/cli/test_cli.py (update CLI tests)

### Migration Messages

```python
MIGRATION_MESSAGES = {
    'qdrant': """
    Qdrant backend is no longer supported (removed in v8.0.0).

    Migration steps:
    1. Remove 'qdrant_config' from your configuration
    2. Set 'backend_type: filesystem' (or remove, it's the default)
    3. Re-index your codebase: cidx index

    For more information: https://github.com/your-repo/docs/migration-to-v8.md
    """,

    'ollama': """
    Ollama embedding provider is no longer supported (removed in v8.0.0).

    Migration steps:
    1. Remove 'ollama_config' from your configuration
    2. Set 'embedding_provider: voyageai' (or remove, it's the default)
    3. Set up VoyageAI API key: export VOYAGE_API_KEY=your-key
    4. Re-index your codebase: cidx index

    For more information: https://github.com/your-repo/docs/migration-to-v8.md
    """,

    'containers': """
    Container support has been removed (v8.0.0).
    Code-indexer now runs container-free using the filesystem backend.

    Migration steps:
    1. Remove 'containers_config' from your configuration
    2. Stop any running containers
    3. Use daemon mode for background operation: cidx config --daemon

    For more information: https://github.com/your-repo/docs/migration-to-v8.md
    """
}
```

## Test Requirements

### Unit Tests
- Test configuration validation rejects legacy configs
- Test CLI options are restricted correctly
- Test error messages are clear and helpful
- Test valid configurations still work

### Integration Tests
- Test full configuration loading with validation
- Test CLI commands with simplified options
- Test daemon mode without containers

### Manual Testing Checklist
1. [ ] Create config with qdrant_config - verify error
2. [ ] Create config with ollama_config - verify error
3. [ ] Create config with containers_config - verify error
4. [ ] Try `--backend qdrant` - verify error/restriction
5. [ ] Try `--embedding-provider ollama` - verify error/restriction
6. [ ] Run `cidx --help` - verify clean output
7. [ ] Run `cidx start --help` - verify updated help
8. [ ] Test valid filesystem configuration - works correctly
9. [ ] Run `./fast-automation.sh` - all tests pass

## Dependencies

### Blocked By
- Qdrant removal (Feature 1)
- Container removal (Feature 2)
- Ollama removal (Feature 3)

### Blocks
- Documentation updates (need final CLI interface)

## Definition of Done

1. [ ] All legacy configuration classes removed
2. [ ] CLI options simplified/restricted
3. [ ] Legacy configuration validators implemented
4. [ ] Clear migration messages for all legacy features
5. [ ] Command help text updated
6. [ ] All tests updated and passing
7. [ ] fast-automation.sh passes
8. [ ] Manual testing completed
9. [ ] Code reviewed and approved

## Notes

### Conversation Context
Simplifying configuration after removing legacy infrastructure.
Focus on clear user experience during migration.

### Key Considerations
- Error messages are critical for user experience
- Must not break valid existing configurations
- Migration guide needs to be comprehensive

### Implementation Tips
- Test each validator thoroughly
- Make error messages actionable
- Consider adding a --migrate flag for future

## Time Tracking

### Estimates
- Analysis: 30 minutes
- Implementation: 5 hours
- Testing: 2 hours
- Code Review: 30 minutes
- **Total**: 8 hours

### Actual
- Start Date: TBD
- End Date: TBD
- Actual Hours: TBD

## Revision History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2025-11-19 | 1.0 | System | Initial story creation |
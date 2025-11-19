# Story: Remove Container Management Infrastructure

## Story ID
`STORY-CONTAINER-INFRA-001`

## Parent Feature
`FEAT-CONTAINER-REMOVAL-001`

## Title
Remove Docker and Podman Container Management Infrastructure

## Status
PLANNED

## Priority
HIGH

## Story Points
8

## Assignee
TBD

## Story Summary

As a maintainer of code-indexer, I want to completely remove the Docker and Podman container management infrastructure so that the codebase no longer has container runtime dependencies, simplifying deployment and reducing operational complexity to focus on the container-free filesystem backend.

## Acceptance Criteria

### Required Outcomes
1. **Infrastructure Removal**
   - [ ] Delete src/code_indexer/infrastructure/docker_manager.py (~1,200 lines)
   - [ ] Delete src/code_indexer/infrastructure/container_manager.py (~600 lines)
   - [ ] Delete src/code_indexer/infrastructure/global_port_registry.py (~403 lines)

2. **CLI Command Updates**
   - [ ] Adapt `cidx start` to only start daemon (no containers)
   - [ ] Adapt `cidx stop` to only stop daemon (no containers)
   - [ ] Adapt `cidx restart` to only restart daemon (no containers)
   - [ ] Update help text to remove container references

3. **Configuration Cleanup**
   - [ ] Remove ProjectContainersConfig class from models.py
   - [ ] Remove container-related configuration fields
   - [ ] Add validation to reject container configuration attempts

4. **Import Cleanup**
   - [ ] Remove all DockerManager imports (9+ modules)
   - [ ] Remove all ContainerManager imports
   - [ ] Remove port registry imports
   - [ ] Verify no unused imports with linting

5. **Test Removal**
   - [ ] Delete tests/integration/docker/ directory (~10 files)
   - [ ] Delete tests/e2e/infrastructure/test_container_manager_e2e.py
   - [ ] Remove container-related test fixtures
   - [ ] Update test configuration

6. **Manual Testing**
   - [ ] Verify daemon start/stop works without containers
   - [ ] Verify no container operations are attempted
   - [ ] Confirm error messages for legacy container configs
   - [ ] Test full init/index/query workflow

## Technical Details

### Implementation Steps

1. **Analyze Dependencies** (1 hour)
   ```bash
   # Find all container manager imports
   grep -r "DockerManager" src/ --include="*.py"
   grep -r "ContainerManager" src/ --include="*.py"
   grep -r "global_port_registry" src/ --include="*.py"

   # Find CLI command references
   grep -r "container" src/code_indexer/cli.py
   ```

2. **Remove Infrastructure Modules** (2 hours)
   ```bash
   # Delete the infrastructure files
   rm src/code_indexer/infrastructure/docker_manager.py
   rm src/code_indexer/infrastructure/container_manager.py
   rm src/code_indexer/infrastructure/global_port_registry.py

   # Update __init__.py
   # Remove from infrastructure/__init__.py exports
   ```

3. **Update CLI Commands** (2 hours)
   ```python
   # In cli.py, update commands:
   @cli.command()
   def start(ctx):
       """Start the daemon (no containers)."""
       if not ctx.obj['config'].daemon_config.enabled:
           console.print("[red]Daemon mode not enabled[/red]")
           return
       # Start daemon logic only, no container references

   @cli.command()
   def stop(ctx):
       """Stop the daemon (no containers)."""
       # Stop daemon logic only

   @cli.command()
   def restart(ctx):
       """Restart the daemon (no containers)."""
       # Restart daemon logic only
   ```

4. **Clean Configuration** (1 hour)
   ```python
   # In models.py, remove:
   # - ProjectContainersConfig class
   # - containers_config field
   # - Container-related validators

   # Add legacy detection:
   def validate_no_container_config(config):
       if hasattr(config, 'containers_config'):
           raise ValueError(
               "Container management is no longer supported in v8.0+.\n"
               "Code-indexer now runs container-free.\n"
               "Please remove containers_config from your configuration."
           )
   ```

5. **Module Import Cleanup** (2 hours)
   ```bash
   # For each module with container imports:
   # 1. Remove import statements
   # 2. Remove container-specific logic
   # 3. Update to use daemon-only operations
   ```

6. **Test Cleanup** (1 hour)
   ```bash
   # Remove container tests
   rm -rf tests/integration/docker/
   rm tests/e2e/infrastructure/test_container_manager_e2e.py

   # Find and remove other container tests
   grep -r "container\|docker\|podman" tests/ --include="*.py"
   ```

### Files to Modify

**Delete:**
- src/code_indexer/infrastructure/docker_manager.py
- src/code_indexer/infrastructure/container_manager.py
- src/code_indexer/infrastructure/global_port_registry.py
- tests/integration/docker/ (entire directory)
- tests/e2e/infrastructure/test_container_manager_e2e.py

**Modify:**
- src/code_indexer/cli.py (update commands)
- src/code_indexer/configuration/models.py (remove container config)
- src/code_indexer/infrastructure/__init__.py (remove exports)
- Any modules with container imports (9+ files)

### Error Handling

```python
# Add to CLI commands
def check_no_container_operations():
    """Ensure no container operations are attempted."""
    console.print(
        "[yellow]Note: Container support has been removed in v8.0+.[/yellow]\n"
        "Code-indexer now runs container-free using filesystem backend."
    )
```

## Test Requirements

### Unit Tests
- Test CLI commands work without container operations
- Test configuration rejects container settings
- Test daemon operations work independently

### Integration Tests
- Test full workflow without containers
- Test daemon start/stop/restart
- Verify no container runtime dependencies

### Manual Testing Checklist
1. [ ] Run `cidx config --daemon` to enable daemon
2. [ ] Run `cidx start` - daemon starts, no containers
3. [ ] Run `cidx stop` - daemon stops cleanly
4. [ ] Run `cidx restart` - daemon restarts properly
5. [ ] Run full init/index/query workflow
6. [ ] Attempt legacy container config - verify error
7. [ ] Run `./fast-automation.sh` - all tests pass
8. [ ] Check `./lint.sh` - no import errors

## Dependencies

### Blocked By
- Qdrant removal (Qdrant uses container infrastructure)

### Blocks
- Configuration cleanup (needs container config removed first)

## Definition of Done

1. [ ] All container management code removed
2. [ ] CLI commands updated for daemon-only operation
3. [ ] Configuration rejects container settings
4. [ ] All container imports removed
5. [ ] All container tests deleted
6. [ ] fast-automation.sh passes
7. [ ] Lint check passes
8. [ ] Manual testing confirms functionality
9. [ ] Code reviewed and approved

## Notes

### Conversation Context
From user request: "Remove legacy cruft related to deprecated infrastructure (Qdrant containers)"
Emphasis on eliminating container management complexity.

### Key Risks
- CLI commands heavily integrated with containers
- Some modules may have deep container dependencies
- User confusion about command behavior changes

### Implementation Tips
- Start with comprehensive import analysis
- Update CLI help text clearly
- Provide migration guidance in error messages
- Test daemon mode thoroughly after changes

## Time Tracking

### Estimates
- Analysis: 1 hour
- Implementation: 7 hours
- Testing: 3 hours
- Code Review: 1 hour
- **Total**: 12 hours

### Actual
- Start Date: TBD
- End Date: TBD
- Actual Hours: TBD

## Revision History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2025-11-19 | 1.0 | System | Initial story creation |
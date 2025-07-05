# EPIC: Local Storage and Copy-on-Write Clone Support

## Overview
Enable project-local Qdrant storage and support for copy-on-write (CoW) cloning of indexed projects, allowing fast project duplication with independent vector collections.

## Business Value
- **Fast Project Cloning**: Near-instantaneous duplication of indexed projects
- **True Project Isolation**: Each project becomes fully self-contained
- **Offline Capability**: Projects work without global services
- **Backup Simplicity**: Copy entire project folder to backup everything
- **Development Safety**: No risk of affecting other projects during development

## Technical Goals
- Support `--local-storage` flag for project-local Qdrant storage
- Enable CoW cloning with data consistency guarantees
- Maintain backward compatibility with existing global storage
- Support force-flush operations for data consistency
- Update fix-config for local collection management

## Architecture Decisions

### **FINAL ARCHITECTURE: Single Container with Home Folder Mounting and Symlinks**

After extensive analysis, we chose a **single container approach** with home folder mounting and internal symlinks for optimal simplicity and compatibility.

### Storage Architecture
- **Current**: Global Docker named volumes (`qdrant_data:/qdrant/storage`)
- **New**: Home folder mounting (`~/:/qdrant/home`) with internal symlinks
- **Container Storage**: Single storage directory (`/qdrant/storage`) that symlinks to current project
- **Project Data**: Stored in `.code-indexer/qdrant-data` within each project folder
- **Compatibility**: Automatic migration from global to local storage

### Container Strategy
- **Single Container**: One Qdrant instance per machine (maintains current architecture)
- **Home Folder Access**: Mount entire `~` directory for universal project access
- **Symlink Management**: Container startup script creates symlinks to current project's storage
- **Dynamic Switching**: Change symlink target without container recreation

### Migration Strategy
- **Automatic Detection**: Realtime migration checking on every Qdrant operation
- **Transparent Migration**: All commands automatically trigger migration if needed
- **State Tracking**: Persistent migration state to avoid repeated checks
- **Safe Migration**: Backup creation before moving collections

### Collection Management
- **Physical Isolation**: Each project's collections stored in project folder
- **Symlink Routing**: Container symlinks `/qdrant/storage` to active project
- **Project Switching**: Update symlink + restart Qdrant process (not container)
- **Data Portability**: Collections travel with project folders

---

## Stories

### Story 1: Force-Flush Command
**As a developer**, I want to force Qdrant to flush all RAM data to disk so that I can ensure data consistency before cloning operations.

#### Acceptance Criteria
- [ ] `cidx force-flush` command flushes all collections to disk
- [ ] `cidx force-flush --collection <name>` flushes specific collection
- [ ] Command uses Qdrant snapshot API to force flush
- [ ] Temporary snapshots are automatically cleaned up
- [ ] Command reports success/failure status
- [ ] Works with both global and local storage modes

#### Technical Implementation
- Add `force_flush_to_disk()` method to QdrantClient
- Use Qdrant snapshot creation API to trigger flush
- Implement cleanup of temporary snapshots
- Add CLI command following existing patterns

#### Definition of Done
- [ ] Unit tests for flush functionality
- [ ] Integration tests with real Qdrant instance
- [ ] CLI help documentation updated
- [ ] README updated with force-flush usage

---

### Story 2: Home Folder Mounting and Smart Start
**As a developer**, I want the start command to automatically set up home folder mounting so that all projects are accessible without manual configuration.

#### Acceptance Criteria
- [ ] `cidx start` automatically mounts home folder (`~/:/qdrant/home`)
- [ ] Container can access any project within home directory
- [ ] Automatic migration from old container configuration
- [ ] Creates `.code-indexer/qdrant-data/` directory structure for local projects
- [ ] Symlink setup for current project's storage
- [ ] Backward compatible with existing projects

#### Technical Implementation
- Modify DockerManager to use home folder mounting
- Add container configuration migration detection
- Implement symlink management in container startup
- Create project detection and symlink routing
- Add migration safety mechanisms

#### Definition of Done
- [ ] `cidx start` works with home folder mounting
- [ ] All projects within home directory are accessible
- [ ] Migration from old configuration is automatic
- [ ] Symlinks route to correct project storage
- [ ] Integration tests cover home folder mounting

---

### Story 3: Fix-Config with Automatic Migration
**As a developer**, I want fix-config to automatically migrate collections from global to local storage and handle cloned projects seamlessly.

#### Acceptance Criteria
- [ ] `cidx fix-config` detects old global storage collections
- [ ] Automatically migrates collections to local project storage
- [ ] Updates container symlinks for new project location
- [ ] Preserves all collection data during migration
- [ ] Works for both fresh projects and CoW clones
- [ ] Provides migration confirmation and safety backups

#### Technical Implementation
- Add migration detection logic for global storage collections
- Implement safe collection migration with backups
- Update symlink management for new project locations
- Add migration verification and rollback capabilities
- Enhance fix-config with CLI migration options

#### Definition of Done
- [ ] fix-config migrates global collections automatically
- [ ] Collections remain accessible after migration
- [ ] Migration includes safety backups and verification
- [ ] Integration tests cover migration scenarios
- [ ] Documentation updated with migration workflow

---

### Story 4: Copy-on-Write Clone Workflow
**As a developer**, I want a documented workflow for CoW cloning so that I can quickly duplicate indexed projects.

#### Acceptance Criteria
- [ ] Documented workflow for safe CoW cloning
- [ ] Includes pause-flush-clone-resume steps
- [ ] Works with btrfs, ZFS, and other CoW filesystems
- [ ] Verifies data consistency before and after clone
- [ ] Provides example scripts and commands
- [ ] Includes troubleshooting guidance

#### Technical Implementation
- Document complete workflow in README
- Create example scripts for different filesystems
- Add verification commands for data consistency
- Include troubleshooting section for common issues

#### Definition of Done
- [ ] Complete workflow documented in README
- [ ] Example scripts provided and tested
- [ ] Troubleshooting guide covers common scenarios
- [ ] Workflow validated on multiple filesystems

---

### Story 5: Realtime Migration Middleware
**As a developer**, I want automatic migration checking on every command so that backward compatibility is seamless regardless of which command I run first.

#### Acceptance Criteria
- [ ] All Qdrant-dependent commands check migration status automatically
- [ ] Migration happens transparently on first command that needs it
- [ ] Migration state is tracked to avoid repeated checks
- [ ] User sees informative migration progress messages
- [ ] Migration failures are handled gracefully with rollback
- [ ] No command requires manual migration setup

#### Technical Implementation
- Create MigrationMiddleware for automatic migration checking
- Add @requires_qdrant_access decorator to all relevant commands
- Implement migration state tracking with persistent storage
- Add migration detection for both container and project levels
- Create safe migration workflows with backup and verification

#### Definition of Done
- [ ] All commands automatically trigger migration when needed
- [ ] Migration state is tracked persistently
- [ ] Migration is transparent to user workflow
- [ ] Comprehensive error handling and rollback mechanisms
- [ ] Integration tests cover all migration scenarios

---

### Story 6: Test Infrastructure Updates
**As a developer**, I want the test infrastructure to work with both storage modes so that collection cleanup and management continues to work properly.

#### Acceptance Criteria
- [ ] Collection registration works with local storage
- [ ] Test cleanup handles both global and local collections
- [ ] `--clear` command works with both storage modes
- [ ] `clear-data` command handles local storage
- [ ] Test isolation maintained between storage modes

#### Technical Implementation
- Update collection registration to detect storage mode
- Enhance cleanup mechanisms for local storage
- Update clear commands to handle both modes
- Ensure test isolation between modes
- Add test coverage for mixed mode scenarios

#### Definition of Done
- [ ] All tests pass with both storage modes
- [ ] Test cleanup leaves no orphaned data
- [ ] Clear commands work correctly
- [ ] Test suite covers mixed mode scenarios

---

### Story 7: Collection Management Review
**As a developer**, I want comprehensive collection management that works consistently across both storage modes.

#### Acceptance Criteria
- [ ] Collection listing works with both storage modes
- [ ] Collection deletion handles both modes correctly
- [ ] Status command shows correct storage mode
- [ ] Health checks work with local storage
- [ ] Collection statistics accurate for both modes

#### Technical Implementation
- Update collection discovery for local storage
- Enhance deletion mechanisms for local collections
- Update status reporting to show storage mode
- Modify health checks for local storage
- Ensure consistent behavior across modes

#### Definition of Done
- [ ] All collection management commands work with both modes
- [ ] Status reporting is accurate and helpful
- [ ] Health checks validate both storage modes
- [ ] Documentation covers all management scenarios

---

### Story 8: End-to-End CoW Clone Workflow Test
**As a developer**, I want a comprehensive e2e test that verifies the complete CoW clone workflow with the new home folder mounting and symlink architecture.

#### Acceptance Criteria
- [ ] Test creates a project and triggers automatic migration
- [ ] Test performs initial indexing with home folder mounting
- [ ] Test starts watch mode and detects file changes
- [ ] Test verifies incremental indexing works correctly
- [ ] Test performs safe CoW clone workflow (pause-flush-clone-resume)
- [ ] Test validates cloned project works with fix-config migration
- [ ] Test verifies both projects can query same content using symlinks
- [ ] Test confirms local collections are isolated in project folders
- [ ] Test validates single container serves both projects
- [ ] Test ensures symlink routing works correctly

#### Technical Implementation
Create comprehensive e2e test: `test_cow_clone_workflow_e2e.py`

#### Test Scenario Flow
```python
async def test_complete_cow_clone_workflow():
    # Phase 1: Create and Initialize Original Project
    original_repo = create_test_repo("original-project")
    add_test_files(original_repo, ["file1.py", "file2.py"])
    
    # Initialize project (will auto-migrate to local storage)
    await run_command(f"cidx init", cwd=original_repo)
    
    # Phase 2: Initial Indexing and Verification
    await run_command("cidx index", cwd=original_repo)
    
    # Query 1: Verify file1.py content
    query1_result = await run_command('cidx query "function definition"', cwd=original_repo)
    assert "file1.py" in query1_result
    
    # Query 2: Verify file2.py content  
    query2_result = await run_command('cidx query "class implementation"', cwd=original_repo)
    assert "file2.py" in query2_result
    
    # Phase 3: Watch Mode and Incremental Changes
    watch_process = await start_watch_mode(original_repo)
    
    # Make a change to file1.py
    modify_file(original_repo / "file1.py", "# Updated function definition")
    await wait_for_watch_processing(2)
    
    # Verify change is indexed
    query1_updated = await run_command('cidx query "Updated function"', cwd=original_repo)
    assert "file1.py" in query1_updated
    
    # Phase 4: Prepare for CoW Clone
    await stop_watch_mode(watch_process)
    
    # Force flush to ensure consistency
    await run_command("cidx force-flush", cwd=original_repo)
    
    # Phase 5: CoW Clone Operation
    cloned_repo = Path("cloned-project")
    await cow_clone_directory(original_repo, cloned_repo)
    
    # Phase 6: Resume Original and Configure Clone
    await start_watch_mode(original_repo)  # Resume original watch
    await run_command("cidx fix-config", cwd=cloned_repo)
    
    # Phase 7: Verify Clone Independence
    # Query same content in both projects
    original_query1 = await run_command('cidx query "function definition"', cwd=original_repo)
    cloned_query1 = await run_command('cidx query "function definition"', cwd=cloned_repo)
    
    original_query2 = await run_command('cidx query "Updated function"', cwd=original_repo)
    cloned_query2 = await run_command('cidx query "Updated function"', cwd=cloned_repo)
    
    # Both should return same results
    assert original_query1 == cloned_query1
    assert original_query2 == cloned_query2
    
    # Phase 8: Verify Local Collection Usage
    original_config = read_config(original_repo / ".code-indexer/config.json")
    cloned_config = read_config(cloned_repo / ".code-indexer/config.json")
    
    # Should both use same container (single container architecture)
    assert original_config.get("container_mode") == "shared"
    assert cloned_config.get("container_mode") == "shared"
    
    # Should both use local storage
    assert original_config["storage_mode"] == "local"
    assert cloned_config["storage_mode"] == "local"
    
    # Verify local qdrant-data directories exist
    assert (original_repo / ".code-indexer/qdrant-data").exists()
    assert (cloned_repo / ".code-indexer/qdrant-data").exists()
    
    # Phase 9: Test Independent Operations
    # Make different changes to each project
    modify_file(original_repo / "file1.py", "# Original specific change")
    modify_file(cloned_repo / "file1.py", "# Cloned specific change")
    
    # Start watch on both (should use same container with symlink routing)
    original_watch = await start_watch_mode(original_repo)
    cloned_watch = await start_watch_mode(cloned_repo)
    
    await wait_for_watch_processing(3)
    
    # Verify isolation - each project should see only its own changes
    original_specific = await run_command('cidx query "Original specific"', cwd=original_repo)
    cloned_specific = await run_command('cidx query "Cloned specific"', cwd=cloned_repo)
    
    assert "file1.py" in original_specific
    assert "file1.py" in cloned_specific
    
    # Cross-check isolation
    original_no_clone = await run_command('cidx query "Cloned specific"', cwd=original_repo)
    cloned_no_original = await run_command('cidx query "Original specific"', cwd=cloned_repo)
    
    assert "file1.py" not in original_no_clone
    assert "file1.py" not in cloned_no_original
    
    # Phase 10: Cleanup
    await stop_watch_mode(original_watch)
    await stop_watch_mode(cloned_watch)
    
    # Verify clean shutdown of shared container
    await run_command("cidx stop", cwd=original_repo)  # Should stop shared container
```

#### Definition of Done
- [ ] E2E test covers complete workflow from creation to isolated operation
- [ ] Test verifies data consistency through CoW clone process
- [ ] Test validates independent project operation
- [ ] Test confirms local collection usage and isolation
- [ ] Test ensures no port conflicts or resource contention
- [ ] Test runs reliably in CI/CD environment
- [ ] Test includes comprehensive assertions and error handling
- [ ] Test cleanup leaves no orphaned resources

---

### Story 9: Realtime Migration Detection and State Tracking
**As a developer**, I want the system to track migration state persistently so that migration checks are efficient and don't repeat unnecessarily.

#### Acceptance Criteria
- [ ] Migration state is tracked in persistent storage
- [ ] Container migration status is detected automatically
- [ ] Project migration status is detected per project
- [ ] Migration checks are optimized to avoid repeated work
- [ ] Migration state survives application restarts
- [ ] Clear migration state management and debugging tools

#### Technical Implementation
- Create MigrationStateTracker class for persistent state management
- Add migration detection logic for containers and projects
- Implement efficient caching and state validation
- Add CLI commands for migration state inspection and reset
- Create comprehensive migration logging and debugging

#### Definition of Done
- [ ] Migration state is tracked persistently across sessions
- [ ] Migration checks are efficient and don't repeat
- [ ] Clear debugging tools for migration state issues
- [ ] Comprehensive test coverage for migration state scenarios
- [ ] Documentation for migration state management

---

## Technical Risks and Mitigation

### Risk: Data Consistency During CoW Clone
**Mitigation**: Implement force-flush command and document proper pause-flush-clone-resume workflow

### Risk: Symlink Management Complexity
**Mitigation**: Use robust symlink management with container restart fallbacks and health checks

### Risk: Home Folder Permission Issues
**Mitigation**: Implement proper user ID mapping and permission handling for Docker/Podman

### Risk: Migration State Corruption
**Mitigation**: Add migration state validation, backup mechanisms, and recovery procedures

### Risk: Container Restart Requirements
**Mitigation**: Minimize container restarts by using symlink updates and process management

## Dependencies
- Qdrant snapshot API for force-flush functionality
- Copy-on-write capable filesystem (btrfs, ZFS, etc.)
- Docker/Podman for container management with home folder access
- Symlink support within containers
- Existing git-aware indexing system

## Success Metrics
- [ ] CoW clone workflow completes in <10 seconds regardless of collection size
- [ ] All existing functionality works unchanged with automatic migration
- [ ] Single container architecture maintained with full project isolation
- [ ] Migration is transparent and automatic for all commands
- [ ] Home folder mounting provides universal project access
- [ ] Test suite passes with comprehensive migration coverage

## Implementation Priority

### **Updated Implementation Phases**
1. **Phase 1**: Realtime Migration Middleware (enables transparent migration)
2. **Phase 2**: Home Folder Mounting and Smart Start (core infrastructure)
3. **Phase 3**: Force-flush command (enables CoW workflow)
4. **Phase 4**: Fix-config with Automatic Migration (clone support)
5. **Phase 5**: Migration State Tracking (optimization and debugging)
6. **Phase 6**: Test infrastructure updates (quality assurance)
7. **Phase 7**: Documentation and workflow guides (adoption)

### **Critical Path**
The **realtime migration middleware** is now the critical first step, as it enables all other components to work transparently with existing projects while providing automatic migration to the new architecture.
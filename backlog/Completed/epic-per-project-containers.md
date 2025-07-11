# Epic: Per-Project Container Architecture

## Epic Overview
**As a** developer working on multiple projects  
**I want** each project to have its own isolated container environment  
**So that** I can avoid ownership issues, port conflicts, and ensure true project isolation

## Business Value
- Eliminates dangerous filesystem ownership changes
- Enables multiple projects to run simultaneously 
- Provides true project isolation
- Simplifies container management per project
- Removes complex CoW symlink architecture

## Implementation Status: ✅ COMPLETED
All stories in this epic have been successfully implemented. The per-project container architecture is now fully operational.

---

## Story 1: Project-Aware Container Naming ✅ COMPLETED
**As a** developer  
**I want** each project to have uniquely named containers  
**So that** multiple projects can coexist without conflicts

### Acceptance Criteria
- [x] Generate container names using folder path hash (e.g., `cidx-a1b2c3-qdrant`)
- [x] Store generated names in `.code-indexer/config.json` under `project_containers` field
- [x] Container names include: `cidx-{hash}-qdrant`, `cidx-{hash}-ollama`, `cidx-{hash}-data-cleaner`
- [x] Hash is deterministic based on project root path
- [x] Names are valid Docker/Podman container names (alphanumeric + hyphens)

### Technical Implementation
✅ Implemented in `docker_manager.py`:
- SHA256 hash of project path (8 chars): `_generate_project_hash()`
- Container naming: `_generate_container_names()`
- Config storage in `project_containers` field

```json
// In .code-indexer/config.json
{
  "project_containers": {
    "project_hash": "a1b2c3d4",
    "qdrant_name": "cidx-a1b2c3d4-qdrant",
    "ollama_name": "cidx-a1b2c3d4-ollama", 
    "data_cleaner_name": "cidx-a1b2c3d4-data-cleaner"
  }
}
```

### Definition of Done
- Container names generated and stored in config ✅
- Multiple projects can generate different names ✅
- Names persist across sessions ✅

---

## Story 2: Dynamic Port Management ✅ COMPLETED
**As a** developer  
**I want** each project to automatically find and use free ports  
**So that** I can run multiple projects simultaneously without port conflicts

### Acceptance Criteria
- [x] Auto-detect free ports starting from base ports (6333 for Qdrant, 11434 for Ollama)
- [x] Store assigned ports in `.code-indexer/config.json` under `project_ports` field
- [x] Scan for available ports in incremental ranges (6333, 6334, 6335...)
- [x] Validate ports are actually free before assignment
- [x] All cidx operations use stored ports for API calls

### Technical Implementation
```json
// In .code-indexer/config.json
{
  "project_ports": {
    "qdrant_port": 6334,
    "ollama_port": 11435,
    "data_cleaner_port": 8081
  }
}
```

### Port Allocation Logic
✅ Implemented in `docker_manager.py`:
- `_allocate_free_ports()`: Deterministic allocation based on project hash
- `_is_port_available()`: Validates port availability
- Collision detection with retry logic
- Ports become permanent once containers are created

### Definition of Done
- Ports automatically allocated and stored ✅
- Multiple projects get different port assignments ✅
- All operations use project-specific ports ✅

---

## Story 3: Project-Specific Data Storage ✅ COMPLETED
**As a** developer  
**I want** Qdrant data stored within my project directory  
**So that** project data stays with the project and doesn't interfere with other projects

### Acceptance Criteria
- [x] Qdrant metadata stored in `.code-indexer/qdrant/` within each project
- [x] Collections stored in `.code-indexer/qdrant/collections/` within each project
- [x] Ollama models shared globally in `~/.ollama/` (not per-project)
- [x] No symlinks or CoW complexity needed
- [x] Each project is completely self-contained for vector data

### Mount Configuration
✅ Implemented volume mounts:
```yaml
# Qdrant container mounts
volumes:
  - "{project_root}/.code-indexer/qdrant:/qdrant/storage:U"  # Project-specific storage

# Ollama container mounts  
volumes:
  - "~/.ollama_storage:/root/.ollama"  # Global shared models
```

### Definition of Done
- Vector data isolated per project ✅
- No cross-project data contamination ✅
- Projects can be moved/copied with their data ✅

---

## Story 4: Project-Aware Start Command ✅ COMPLETED
**As a** developer  
**I want** the start command to be project-aware  
**So that** it manages the correct containers for my current project

### Acceptance Criteria
- [x] `start` command detects current project by walking up directory tree
- [x] Uses project-specific container names and ports from config
- [x] Creates containers if they don't exist for this project
- [x] Starts existing containers if they're stopped
- [x] Updates config with port assignments during first start
- [x] Validates container health using project-specific ports

### Behavioral Changes
✅ All implemented:
- Uses `ConfigManager.create_with_backtrack()` to find project root
- No global container assumptions - all project-specific
- `--indexing-root` not required (uses current directory)
- Generates project-specific docker-compose files

### Definition of Done
- Start works from any directory within a project ✅
- Uses correct project containers ✅
- No interference with other project containers ✅

---

## Story 5: Project-Aware Status Command ✅ COMPLETED
**As a** developer  
**I want** the status command to show my current project's status  
**So that** I can see the health of containers relevant to my work

### Acceptance Criteria
- [x] Status shows project-specific container states
- [x] Displays project-specific ports in use
- [x] Shows project-specific collection information
- [x] Indicates if containers exist for current project
- [x] Shows Qdrant storage location (project-local)

### Status Output Example
✅ Actual implementation shows:
- Codebase path and config location
- Git information (branch, commit)
- Project ID for collections
- Container status with project-specific names
- Collection details and statistics
- Service health with actual ports

### Definition of Done
- Status is project-specific ✅
- Shows relevant container information ✅
- Clear indication of project isolation ✅

---

## Story 6: Enhanced Uninstall with --wipe-all ✅ COMPLETED
**As a** developer  
**I want** to be able to remove all cidx containers across all projects  
**So that** I can completely clean my system when needed

### Acceptance Criteria
- [x] `uninstall --wipe-all` discovers all cidx containers system-wide
- [x] Removes containers matching pattern `cidx-*-*` 
- [x] Removes all associated volumes and data
- [x] Removes global Ollama models
- [x] Provides summary of what was removed
- [x] Requires confirmation before proceeding

### Container Discovery
✅ Implemented features:
- Removes ALL container images (not just project-specific)
- Cleans `~/.qdrant_collections`, `~/.code-indexer-data`, `~/.code-indexer-compose`
- Performs aggressive container engine prune
- May require sudo for permission-protected files

### Definition of Done
- Can clean entire system of cidx containers ✅
- Safe confirmation process ✅
- Clear reporting of removed items ✅

---

## Story 7: Enhanced fix-config Command ✅ COMPLETED
**As a** developer  
**I want** the fix-config command to repair and update project configurations  
**So that** my project works correctly after moves or config corruption

### Acceptance Criteria
- [x] Validates and corrects `codebase_dir` path
- [x] Updates project name to match directory
- [x] Updates git branch/commit information
- [x] Removes invalid file paths from metadata
- [x] Fixes common JSON syntax errors

### Implementation Details
✅ Current implementation:
- Creates backups before making changes
- Repairs JSON syntax (trailing commas, unquoted keys)
- Updates path references to current location
- Note: Does NOT regenerate container names/hashes when moved
  (containers remain tied to original hash)

### Definition of Done
- Config repairs work correctly ✅
- JSON syntax errors are fixed ✅
- Path references updated ✅
- Container name regeneration on move: ❌ Not implemented

---

## Epic Definition of Done
- [x] All stories completed with acceptance criteria met
- [x] Multiple projects can run simultaneously 
- [x] No filesystem ownership issues
- [x] True project isolation achieved
- [x] Backwards compatibility maintained where possible
- [x] Documentation updated
- [x] Tests pass for multi-project scenarios

## Breaking Changes
- Container names will change (migration needed)
- Port assignments will change (stored in config)
- Global shared containers no longer exist
- Each project becomes self-contained

## Migration Path
1. Backup existing projects
2. Run `uninstall --wipe-all` to clean system
3. Re-run `start` in each project to create new containers
4. Re-index projects as needed

## Outstanding Enhancement
While the core per-project container architecture is complete, one potential enhancement remains:
- **Container name regeneration on project move**: Currently, when a project is moved to a new location, it keeps its original container names/hash. An enhancement could regenerate these based on the new path, but this would require container migration logic.
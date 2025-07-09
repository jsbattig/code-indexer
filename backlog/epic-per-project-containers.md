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

---

## Story 1: Project-Aware Container Naming
**As a** developer  
**I want** each project to have uniquely named containers  
**So that** multiple projects can coexist without conflicts

### Acceptance Criteria
- [ ] Generate container names using folder path hash (e.g., `cidx-a1b2c3-qdrant`)
- [ ] Store generated names in `.code-indexer/config.json` under `project_containers` field
- [ ] Container names include: `cidx-{hash}-qdrant`, `cidx-{hash}-ollama`, `cidx-{hash}-data-cleaner`
- [ ] Hash is deterministic based on project root path
- [ ] Names are valid Docker/Podman container names (alphanumeric + hyphens)

### Technical Implementation
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
- Container names generated and stored in config
- Multiple projects can generate different names
- Names persist across sessions

---

## Story 2: Dynamic Port Management
**As a** developer  
**I want** each project to automatically find and use free ports  
**So that** I can run multiple projects simultaneously without port conflicts

### Acceptance Criteria
- [ ] Auto-detect free ports starting from base ports (6333 for Qdrant, 11434 for Ollama)
- [ ] Store assigned ports in `.code-indexer/config.json` under `project_ports` field
- [ ] Scan for available ports in incremental ranges (6333, 6334, 6335...)
- [ ] Validate ports are actually free before assignment
- [ ] All cidx operations use stored ports for API calls

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
- Qdrant: Start at 6333, increment until free port found
- Ollama: Start at 11434, increment until free port found  
- Data Cleaner: Start at 8080, increment until free port found

### Definition of Done
- Ports automatically allocated and stored
- Multiple projects get different port assignments
- All operations use project-specific ports

---

## Story 3: Project-Specific Data Storage
**As a** developer  
**I want** Qdrant data stored within my project directory  
**So that** project data stays with the project and doesn't interfere with other projects

### Acceptance Criteria
- [ ] Qdrant metadata stored in `.code-indexer/qdrant/` within each project
- [ ] Collections stored in `.code-indexer/qdrant/collections/` within each project
- [ ] Ollama models shared globally in `~/.ollama/` (not per-project)
- [ ] No symlinks or CoW complexity needed
- [ ] Each project is completely self-contained for vector data

### Mount Configuration
```yaml
# Qdrant container mounts
volumes:
  - "./.code-indexer/qdrant:/qdrant/storage:U"  # Project-specific storage

# Ollama container mounts  
volumes:
  - "ollama_models:/root/.ollama"  # Global shared models
```

### Definition of Done
- Vector data isolated per project
- No cross-project data contamination
- Projects can be moved/copied with their data

---

## Story 4: Project-Aware Start Command
**As a** developer  
**I want** the start command to be project-aware  
**So that** it manages the correct containers for my current project

### Acceptance Criteria
- [ ] `start` command detects current project by walking up directory tree
- [ ] Uses project-specific container names and ports from config
- [ ] Creates containers if they don't exist for this project
- [ ] Starts existing containers if they're stopped
- [ ] Updates config with port assignments during first start
- [ ] Validates container health using project-specific ports

### Behavioral Changes
- Remove global container assumptions
- Remove `--indexing-root` requirement (use current project)
- Check for project-specific containers by name
- Create project-specific docker-compose configuration

### Definition of Done
- Start works from any directory within a project
- Uses correct project containers
- No interference with other project containers

---

## Story 5: Project-Aware Status Command
**As a** developer  
**I want** the status command to show my current project's status  
**So that** I can see the health of containers relevant to my work

### Acceptance Criteria
- [ ] Status shows project-specific container states
- [ ] Displays project-specific ports in use
- [ ] Shows project-specific collection information
- [ ] Indicates if containers exist for current project
- [ ] Shows Qdrant storage location (project-local)

### Status Output Example
```
📊 Code Indexer Status (Project: my-app)
┌─────────────────────┬──────────────┬──────────────────────┐
│ Component           │ Status       │ Details              │
├─────────────────────┼──────────────┼──────────────────────┤
│ Project Containers  │ ✅ Running   │ Hash: a1b2c3d4       │
│ Qdrant (6334)      │ ✅ Ready     │ Local storage        │
│ Ollama (11435)     │ ✅ Ready     │ Shared models        │
│ Data Cleaner (8081)│ ✅ Ready     │ Project cleanup      │
└─────────────────────┴──────────────┴──────────────────────┘
```

### Definition of Done
- Status is project-specific
- Shows relevant container information
- Clear indication of project isolation

---

## Story 6: Enhanced Uninstall with --wipe-all
**As a** developer  
**I want** to be able to remove all cidx containers across all projects  
**So that** I can completely clean my system when needed

### Acceptance Criteria
- [ ] `uninstall --wipe-all` discovers all cidx containers system-wide
- [ ] Removes containers matching pattern `cidx-*-*` 
- [ ] Removes all associated volumes and data
- [ ] Removes global Ollama models
- [ ] Provides summary of what was removed
- [ ] Requires confirmation before proceeding

### Container Discovery
- Scan for containers with prefix `cidx-`
- Group by project hash for reporting
- Remove associated volumes and networks

### Definition of Done
- Can clean entire system of cidx containers
- Safe confirmation process
- Clear reporting of removed items

---

## Story 7: Enhanced fix-config Command
**As a** developer  
**I want** the fix-config command to update container names when I move projects  
**So that** container names reflect the new project location

### Acceptance Criteria
- [ ] Detect when project path has changed
- [ ] Regenerate project hash based on new path
- [ ] Update container names in config
- [ ] Handle case where containers exist with old names
- [ ] Provide option to migrate or recreate containers

### Migration Strategy
- Compare stored path hash vs current path hash
- If different, regenerate container names
- Option to rename existing containers or recreate
- Update all references in config

### Definition of Done
- Projects work correctly after being moved/copied
- Container names stay consistent with location
- Graceful handling of existing containers

---

## Epic Definition of Done
- [ ] All stories completed with acceptance criteria met
- [ ] Multiple projects can run simultaneously 
- [ ] No filesystem ownership issues
- [ ] True project isolation achieved
- [ ] Backwards compatibility maintained where possible
- [ ] Documentation updated
- [ ] Tests pass for multi-project scenarios

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
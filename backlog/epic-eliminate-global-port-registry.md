# Epic: Eliminate Global Port Registry System

**Epic ID**: GPR-ELIMINATION  
**Created**: 2025-01-23  
**Priority**: High  
**Type**: Breaking Change (v3.0.0)  
**Status**: Planning - Audit Completed  
**Effort Estimate**: 8-10 weeks  

---

## Executive Summary

**COMPLETE ELIMINATION** of the global port registry system (`/var/lib/code-indexer/port-registry`) and replacement with container-native port management. This is a **BREAKING CHANGE** requiring version bump to v3.0.0 with **NO BACKWARDS COMPATIBILITY**.

### Problem Statement

The current global port registry system creates major barriers:
- **macOS Incompatibility**: `/var/lib/` path doesn't exist, requires sudo
- **Complex Installation**: Requires admin privileges for setup
- **Maintenance Overhead**: 403+ lines of complex port coordination code
- **Linux-Only Design**: Hardcoded Linux filesystem assumptions
- **Scalability Limits**: Fixed port ranges limit concurrent projects

### Solution Approach

Replace with **container-runtime native port management**:
- Use Docker/Podman dynamic port allocation 
- Eliminate all system-level directory dependencies
- Remove admin privilege requirements
- Simplify codebase by ~2500 lines
- Enable unlimited concurrent projects

---

## Impact Analysis

### Code Deletion Summary
- **403 lines**: `global_port_registry.py` (entire file deleted)
- **88 references**: setup-global-registry command removal
- **6 test files**: Port registry specific tests deleted
- **Config schema**: ProjectPortsConfig class removed
- **CLI commands**: setup-global-registry eliminated

### Breaking Changes
1. **Configuration Format**: `project_ports` field removed from config
2. **CLI Commands**: `setup-global-registry` command deleted
3. **Installation Process**: No sudo/admin setup required
4. **Port Behavior**: Dynamic ports instead of predictable ranges
5. **API Changes**: All port registry methods removed

---

## Technical Architecture

### Current System (TO BE DELETED)
```
/var/lib/code-indexer/port-registry/
├── active-projects/           # Symlink coordination
├── port-allocations.json     # Port tracking
└── registry.log              # Registry maintenance log

GlobalPortRegistry class:
- find_available_port_for_service()
- register_project_allocation()
- scan_and_cleanup_registry()
- Port range management: 6333-7333, 11434-12434, 8091-9091
```

### New System (CONTAINER-NATIVE)
```python
class ContainerPortManager:
    def start_services(self, services: List[str]) -> Dict[str, ServiceInfo]:
        """Start services with container-native port allocation."""
        results = {}
        for service in services:
            # Method 1: Docker dynamic allocation
            container_id = self._start_with_dynamic_port(service)
            port = self._discover_assigned_port(container_id)
            results[service] = ServiceInfo(container_id, port)
        return results
    
    def _start_with_dynamic_port(self, service: str) -> str:
        """Start container letting runtime assign port."""
        if self.runtime == "docker":
            # Docker: Use -p 0:internal_port
            cmd = ["docker", "run", "-d", "-p", "0:6333", f"{service}:latest"]
        else:  # podman
            # Podman: Use --publish with range
            cmd = ["podman", "run", "-d", "-p", "32768-65535:6333", f"{service}:latest"]
        return subprocess.check_output(cmd).decode().strip()
    
    def _discover_assigned_port(self, container_id: str) -> int:
        """Discover port assigned by container runtime."""
        cmd = [self.runtime, "port", container_id, "6333"]
        output = subprocess.check_output(cmd).decode().strip()
        # Parse "0.0.0.0:45678" -> 45678
        return int(output.split(':')[-1])
```

### Container Runtime Compatibility

**Docker Approach**:
```bash
# Dynamic port allocation
docker run -d -p 0:6333 qdrant/qdrant
# Runtime assigns available port from ephemeral range
docker port <container_id> 6333  # Returns: 0.0.0.0:42389
```

**Podman Approach** (CRITICAL DIFFERENCE):
```bash
# Podman doesn't support -p 0:port syntax
# Must use port range specification
podman run -d -p 32768-65535:6333 qdrant/qdrant
# OR use podman's automatic port assignment
podman run -d --publish-all qdrant/qdrant
```

---

## User Stories

### Story 1: Remove Global Port Registry Infrastructure
**Priority**: Critical  
**Effort**: 3 days  

**Objective**: Complete elimination of port registry system

**Tasks**:
- [ ] Delete `src/code_indexer/services/global_port_registry.py` (403 lines)
- [ ] Remove `GlobalPortRegistry` imports from all files
- [ ] Delete `PortRegistryError` and `PortExhaustionError` classes
- [ ] Remove registry initialization from DockerManager
- [ ] Update all error handling to remove registry exceptions

**Acceptance Criteria**:
- [ ] Zero references to `GlobalPortRegistry` in codebase
- [ ] All imports compile without registry dependencies
- [ ] No `/var/lib/code-indexer` path references remain
- [ ] Error handling gracefully handles missing registry

**Files Modified**:
- `src/code_indexer/services/docker_manager.py` (remove registry init)
- `src/code_indexer/cli.py` (remove registry setup)

### Story 2: Implement Container-Native Port Manager  
**Priority**: Critical  
**Effort**: 5 days  

**Objective**: New port management using container runtime capabilities

**Tasks**:
- [ ] Create `ContainerPortManager` class
- [ ] Implement Docker dynamic port allocation (`-p 0:port`)
- [ ] Implement Podman port range allocation (`-p range:port`)
- [ ] Add port discovery via container inspection
- [ ] Implement service URL generation after startup
- [ ] Add retry logic for container startup timing
- [ ] Cache discovered ports for performance

**Technical Specifications**:
```python
class ContainerPortManager:
    def __init__(self, runtime: str):
        self.runtime = runtime  # "docker" or "podman"
        self.port_cache: Dict[str, int] = {}
    
    def allocate_service_port(self, project_hash: str, service: str) -> int:
        """Allocate port for service using container runtime."""
        container_name = f"cidx-{project_hash}-{service}"
        
        # Check if container already exists
        if self._container_exists(container_name):
            return self._get_existing_port(container_name)
        
        # Start new container with dynamic port
        container_id = self._start_container_with_dynamic_port(service, container_name)
        
        # Wait for container to be ready and discover port
        port = self._wait_for_port_discovery(container_id)
        
        # Cache for performance
        self.port_cache[container_name] = port
        
        return port
```

**Acceptance Criteria**:
- [ ] Works with both Docker and Podman
- [ ] Port discovery within 10 seconds of container start
- [ ] Handles container startup failures gracefully
- [ ] Supports all required services (Qdrant, Ollama, Data-cleaner)
- [ ] Caches port information for performance

### Story 3: Update Configuration System
**Priority**: Critical  
**Effort**: 2 days  

**Objective**: Remove port-related configuration and dependencies

**Tasks**:
- [ ] Delete `ProjectPortsConfig` class from `config.py:173-180`
- [ ] Remove `project_ports` field from main Config class (line 323)
- [ ] Update config validation to not expect port fields
- [ ] Add optional `preferred_ports` configuration for user preferences
- [ ] Update config loading to handle missing port fields gracefully

**Configuration Schema Changes**:
```python
# REMOVED (Breaking Change)
class ProjectPortsConfig(BaseModel):
    qdrant_port: Optional[int] = None
    ollama_port: Optional[int] = None  
    data_cleaner_port: Optional[int] = None

# REMOVED from main Config class
project_ports: ProjectPortsConfig = Field(default_factory=ProjectPortsConfig)

# NEW (Optional)
class PreferredPortsConfig(BaseModel):
    """Optional port preferences for users who need predictable ports."""
    qdrant_port: Optional[int] = Field(
        default=None, 
        description="Preferred port for Qdrant (will attempt but may fallback)"
    )
    ollama_port: Optional[int] = Field(
        default=None,
        description="Preferred port for Ollama (will attempt but may fallback)" 
    )
```

**Acceptance Criteria**:
- [ ] Config loads without port fields
- [ ] No validation errors for missing project_ports
- [ ] Existing configs with port fields load gracefully (ignored)
- [ ] New optional preferred_ports configuration available

### Story 4: Refactor Docker Manager  
**Priority**: Critical  
**Effort**: 4 days  

**Objective**: Replace port allocation with container-native discovery

**Tasks**:
- [ ] Completely rewrite `allocate_project_ports()` method
- [ ] Remove all `port_registry` dependencies from DockerManager
- [ ] Update `ensure_project_configuration()` for new port system
- [ ] Add container port discovery methods
- [ ] Update service health checks to use discovered ports
- [ ] Modify container startup to use dynamic ports

**Implementation Pattern**:
```python
class DockerManager:
    def __init__(self):
        # REMOVED: self.port_registry = GlobalPortRegistry()
        self.port_manager = ContainerPortManager(self._detect_runtime())
    
    def allocate_project_ports(self, project_root: Path) -> Dict[str, int]:
        """NEW: Container-native port allocation."""
        project_hash = self._calculate_project_hash(project_root)
        required_services = self.get_required_services()
        
        ports = {}
        for service in required_services:
            port = self.port_manager.allocate_service_port(project_hash, service)
            ports[f"{service}_port"] = port
        
        return ports
```

**Acceptance Criteria**:
- [ ] No `GlobalPortRegistry` references in DockerManager
- [ ] Service startup uses container-native ports
- [ ] Health checks work with discovered ports
- [ ] Multi-project isolation maintained
- [ ] Container cleanup works with new port system

### Story 5: Remove CLI Registry Commands
**Priority**: High  
**Effort**: 2 days  

**Objective**: Eliminate all setup-global-registry CLI functionality

**Tasks**:
- [ ] Delete `setup-global-registry` command from cli.py
- [ ] Remove `--setup-global-registry` flags from all commands
- [ ] Update CLI help text to remove registry references
- [ ] Remove registry-specific error messages
- [ ] Update installation documentation

**Commands Affected** (88 references):
- `cidx setup-global-registry` - DELETED
- `cidx init --setup-global-registry` - Flag removed
- All help text references - Updated
- Error messages mentioning registry setup - Removed

**Acceptance Criteria**:
- [ ] `cidx setup-global-registry` command not found
- [ ] No `--setup-global-registry` flags in help output
- [ ] Installation process requires no admin privileges
- [ ] Help text updated to reflect new port system

### Story 6: Create Container Port Discovery Tests
**Priority**: High  
**Effort**: 3 days  

**Objective**: Comprehensive test suite for new port system

**Tasks**:
- [ ] Delete existing port registry tests (6 test files)
- [ ] Create `test_container_port_manager.py` 
- [ ] Add Docker/Podman compatibility tests
- [ ] Test multi-project port isolation
- [ ] Test container startup and discovery timing
- [ ] Add performance tests for port caching

**Test Files to DELETE**:
- `tests/test_global_port_registry.py`
- `tests/test_setup_global_registry_e2e.py`
- `tests/test_broken_softlink_cleanup.py`
- `tests/test_fix_config_port_regeneration.py`
- `tests/test_fix_config_port_bug_specific.py`
- `tests/test_per_project_containers.py` (port registry portions)

**New Test Structure**:
```python
class TestContainerPortManager:
    def test_docker_dynamic_port_allocation(self):
        """Test Docker -p 0:port allocation works."""
    
    def test_podman_port_range_allocation(self):
        """Test Podman port range allocation works."""
    
    def test_port_discovery_timing(self):
        """Test port discovery within acceptable time limits."""
    
    def test_multi_project_isolation(self):
        """Test multiple projects get different ports."""
    
    def test_container_restart_port_consistency(self):
        """Test containers get same ports after restart."""
```

**Acceptance Criteria**:
- [ ] All old port registry tests removed
- [ ] New tests pass on both Docker and Podman
- [ ] Multi-project scenarios tested
- [ ] Performance requirements validated (<10s port discovery)

---

## Implementation Timeline

### Phase 1: Foundation (Week 1-2)
- **Week 1**: Delete port registry infrastructure (Stories 1, 3)
- **Week 2**: Implement container-native port manager (Story 2)

### Phase 2: Integration (Week 3-4)
- **Week 3**: Refactor DockerManager integration (Story 4)  
- **Week 4**: Remove CLI commands and update help (Story 5)

### Phase 3: Testing (Week 5-6)
- **Week 5**: Create new test suite (Story 6)
- **Week 6**: Cross-platform validation and bug fixes

### Phase 4: Documentation (Week 7)
- Update all documentation for new port system
- Create migration guide for breaking changes
- Update installation instructions

### Phase 5: Release Preparation (Week 8)
- Final testing and validation
- Release notes for v3.0.0
- Beta testing with community

---

## Breaking Changes Documentation

### Version Compatibility
- **Current**: v2.16.0.0 (uses global port registry)
- **Target**: v3.0.0 (container-native ports)
- **Migration**: None - clean break, fresh installations only

### User Impact
1. **Installation Simplified**: No more `cidx setup-global-registry` required
2. **Configuration Changes**: Existing configs still work (port fields ignored)
3. **Port Behavior**: Ports are dynamic, not predictable
4. **System Requirements**: No admin/sudo privileges needed

### Breaking API Changes
```python
# REMOVED APIs (Breaking Changes)
GlobalPortRegistry class - DELETED
PortRegistryError exception - DELETED
PortExhaustionError exception - DELETED

# Config schema changes
Config.project_ports field - DELETED
ProjectPortsConfig class - DELETED

# CLI commands
cidx setup-global-registry - DELETED
--setup-global-registry flag - DELETED
```

---

## Risk Assessment

### High-Risk Areas
1. **Container Runtime Differences**: Docker vs Podman port allocation syntax
2. **Timing Issues**: Race conditions during container startup
3. **Performance Impact**: Port discovery adds 5-10 seconds per service startup
4. **Enterprise Compatibility**: Fixed port requirements for firewall rules

### Risk Mitigation
1. **Runtime Abstraction**: Separate logic for Docker vs Podman port handling
2. **Retry Logic**: Robust error handling and retries for startup timing
3. **Caching**: In-memory port cache to avoid repeated discovery
4. **Documentation**: Clear communication of behavioral changes

### Rollback Strategy
- **No rollback path** - breaking change by design
- Version 2.x remains available for users needing registry system
- Clear deprecation timeline for v2.x support

---

## Success Criteria

### Functional Requirements
- [ ] All services start without admin privileges
- [ ] Docker and Podman both supported
- [ ] Multi-project isolation maintained  
- [ ] Port discovery within 10 seconds
- [ ] No /var/lib directory dependencies

### Quality Requirements
- [ ] Zero references to global port registry in codebase
- [ ] All tests pass on Linux and macOS
- [ ] Installation process simplified
- [ ] Code reduction of ~2500 lines achieved

### Performance Requirements
- [ ] Container startup time unchanged (<30 seconds)
- [ ] Port discovery cached for repeated access
- [ ] Support for 50+ concurrent projects
- [ ] Memory usage reduced (no registry maintenance)

---

## Dependencies and Prerequisites

### External Dependencies
- Docker 20.0+ or Podman 3.0+ with port allocation support
- Container images support dynamic port binding
- No system-level directory access required

### Internal Dependencies
- Updated config schema validation
- Modified Docker/Podman detection logic
- New error handling for container startup failures

---

## Monitoring and Rollout

### Rollout Strategy
1. **Alpha Release**: Internal testing with dynamic ports
2. **Beta Release**: Community testing with documentation
3. **Full Release**: v3.0.0 with complete registry elimination

### Key Metrics
- Installation success rate (target: 95%+ without admin privileges)
- Container startup time (target: <30 seconds)
- Port discovery time (target: <10 seconds)  
- Multi-project isolation (target: 100% no conflicts)

### Monitoring Points
- Container runtime detection accuracy
- Port allocation failure rates
- Service startup success rates
- Performance impact measurements

---

## Conclusion

This epic represents a **fundamental architectural shift** from system-level port coordination to container-native port management. While it's a breaking change requiring v3.0.0, it eliminates the primary barrier to cross-platform support and significantly simplifies the installation experience.

The elimination of 2500+ lines of complex port registry code in favor of leveraging container runtime native capabilities aligns with the principle of using proven, tested infrastructure rather than reimplementing it.

**Next Steps**: Review and approve this epic, then begin implementation starting with Phase 1 (Foundation) tasks.

---

**Epic Status**: Ready for Implementation  
**Last Updated**: 2025-01-23  
**Reviewers**: Architecture Team, DevOps Team  
**Stakeholders**: All code-indexer users (breaking change impact)
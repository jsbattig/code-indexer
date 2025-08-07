# EPIC: Replace Global Port Registry with Container-Native Port Management

## Epic ID: CIDX-3000
## Version: 3.0.0 (BREAKING CHANGE)
## Status: SPECIFICATION
## Created: 2025-08-07

---

## EXECUTIVE SUMMARY

Complete elimination of the global port registry system (`/var/lib/code-indexer/port-registry`) in favor of container runtime native dynamic port allocation. This represents a fundamental architectural shift from centralized port coordination to runtime-discovered port management.

### Key Benefits
- **Zero admin privileges required** - No sudo/root access needed
- **Platform uniformity** - Identical behavior on Linux/macOS/Windows
- **Simplified installation** - No setup-global-registry step
- **Reduced complexity** - 400+ lines of registry code eliminated
- **Better isolation** - Container runtime handles port conflicts automatically
- **Self-healing** - No broken softlinks or registry corruption

### Breaking Changes
- Config format changes (project_ports field removed)
- CLI commands removed (setup-global-registry)
- Port predictability changes (dynamic vs fixed)
- No migration path from v2.x configurations

---

## ARCHITECTURAL DESIGN

### Current Architecture (TO BE REMOVED)
```
┌─────────────────────────────────────────────┐
│           Global Port Registry              │
│      /var/lib/code-indexer/port-registry    │
│                                              │
│  ┌─────────────────────────────────────┐    │
│  │  registry.json (global port map)    │    │
│  └─────────────────────────────────────┘    │
│  ┌─────────────────────────────────────┐    │
│  │  projects/ (softlinks to configs)   │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
                      ↓
        ┌──────────────────────────┐
        │    Project Config        │
        │  .code-indexer/config.json│
        │    project_ports: {...}  │
        └──────────────────────────┘
```

### New Architecture (CONTAINER-NATIVE)
```
┌─────────────────────────────────────────────┐
│         Container Runtime Manager           │
│                                              │
│  1. Start container with -p 0:internal_port │
│  2. Runtime assigns available port          │
│  3. Inspect container for assigned port     │
│  4. Cache in memory for session             │
└─────────────────────────────────────────────┘
                      ↓
        ┌──────────────────────────┐
        │  Runtime Port Discovery   │
        │  docker/podman inspect    │
        │  No persistent storage    │
        └──────────────────────────┘
```

---

## USER STORIES

### STORY 1: Remove Global Port Registry Infrastructure
**ID:** CIDX-3001  
**Priority:** P0 - Critical  
**Size:** L (Large)  
**Dependencies:** None

#### Description
As a developer, I want all global port registry code removed so that the system uses container-native port management without requiring admin privileges.

#### Acceptance Criteria
- [ ] `/src/code_indexer/services/global_port_registry.py` completely deleted (403 lines)
- [ ] All imports of `GlobalPortRegistry` removed from codebase
- [ ] `PortRegistryError` and `PortExhaustionError` exceptions removed
- [ ] No references to `/var/lib/code-indexer/port-registry` remain
- [ ] No softlink management code remains
- [ ] All port registry utility functions removed

#### Technical Tasks
```python
# Files to DELETE entirely:
- src/code_indexer/services/global_port_registry.py
- tests/test_global_port_registry.py
- tests/test_setup_global_registry_e2e.py
- tests/test_broken_softlink_cleanup.py

# Imports to REMOVE:
- from code_indexer.services.global_port_registry import GlobalPortRegistry
- from code_indexer.services.global_port_registry import PortRegistryError
- from code_indexer.services.global_port_registry import PortExhaustionError
```

---

### STORY 2: Implement Container-Native Port Manager
**ID:** CIDX-3002  
**Priority:** P0 - Critical  
**Size:** XL (Extra Large)  
**Dependencies:** CIDX-3001

#### Description
As a developer, I want container runtime to handle all port allocation dynamically so that port conflicts are impossible and no central coordination is needed.

#### Acceptance Criteria
- [ ] New `ContainerNativePortManager` class implemented
- [ ] Dynamic port allocation using `-p 0:internal_port` syntax
- [ ] Port discovery via `docker/podman inspect` 
- [ ] Retry logic for container startup timing
- [ ] Support for both Docker and Podman runtimes
- [ ] In-memory caching of discovered ports per session
- [ ] Graceful fallback if inspection fails

#### Technical Specification
```python
class ContainerNativePortManager:
    """
    Manages container ports using runtime dynamic allocation.
    No persistent storage, no global coordination required.
    """
    
    def __init__(self, runtime: str = "podman"):
        self.runtime = runtime
        self.discovered_ports: Dict[str, int] = {}
        self.container_mapping: Dict[str, str] = {}
    
    def start_service_with_dynamic_port(
        self, 
        service_name: str,
        internal_port: int,
        image: str,
        env_vars: Dict[str, str] = None,
        volumes: List[str] = None
    ) -> ServiceInfo:
        """
        Start a container with dynamic port allocation.
        
        Process:
        1. Start container with -p 0:internal_port
        2. Wait for container to be running
        3. Inspect container to get assigned port
        4. Cache the port for this session
        """
        # Generate unique container name
        container_name = self._generate_container_name(service_name)
        
        # Build docker/podman run command with dynamic port
        cmd = [
            self.runtime, "run", "-d",
            "--name", container_name,
            "-p", f"0:{internal_port}",  # Dynamic allocation
        ]
        
        if env_vars:
            for key, value in env_vars.items():
                cmd.extend(["-e", f"{key}={value}"])
        
        if volumes:
            for volume in volumes:
                cmd.extend(["-v", volume])
        
        cmd.append(image)
        
        # Start container
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise ContainerStartError(f"Failed to start {service_name}: {result.stderr}")
        
        container_id = result.stdout.strip()
        
        # Discover assigned port
        assigned_port = self._discover_assigned_port(
            container_id, 
            internal_port,
            max_retries=10,
            retry_delay=0.5
        )
        
        # Cache for session
        self.discovered_ports[service_name] = assigned_port
        self.container_mapping[service_name] = container_id
        
        return ServiceInfo(
            name=service_name,
            container_id=container_id,
            port=assigned_port,
            url=f"http://localhost:{assigned_port}"
        )
    
    def _discover_assigned_port(
        self, 
        container_id: str, 
        internal_port: int,
        max_retries: int = 10,
        retry_delay: float = 0.5
    ) -> int:
        """
        Discover the dynamically assigned port using container inspection.
        """
        for attempt in range(max_retries):
            try:
                # Inspect container for port mapping
                cmd = [
                    self.runtime, "inspect",
                    "--format",
                    f"{{{{(index (index .NetworkSettings.Ports \"{internal_port}/tcp\") 0).HostPort}}}}",
                    container_id
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                
                if result.returncode == 0 and result.stdout.strip():
                    port = int(result.stdout.strip())
                    if port > 0:
                        return port
                
                # Container might still be starting
                time.sleep(retry_delay)
                
            except (subprocess.TimeoutExpired, ValueError) as e:
                if attempt == max_retries - 1:
                    raise PortDiscoveryError(
                        f"Failed to discover port for container {container_id}: {e}"
                    )
                time.sleep(retry_delay)
        
        raise PortDiscoveryError(f"Port discovery timeout for container {container_id}")
    
    def get_service_url(self, service_name: str) -> str:
        """Get the URL for a running service."""
        if service_name not in self.discovered_ports:
            raise ServiceNotFoundError(f"Service {service_name} not running")
        
        port = self.discovered_ports[service_name]
        return f"http://localhost:{port}"
    
    def cleanup_service(self, service_name: str) -> None:
        """Stop and remove a service container."""
        if service_name in self.container_mapping:
            container_id = self.container_mapping[service_name]
            subprocess.run([self.runtime, "stop", container_id], capture_output=True)
            subprocess.run([self.runtime, "rm", container_id], capture_output=True)
            
            del self.discovered_ports[service_name]
            del self.container_mapping[service_name]
```

---

### STORY 3: Update Configuration System
**ID:** CIDX-3003  
**Priority:** P0 - Critical  
**Size:** M (Medium)  
**Dependencies:** CIDX-3001

#### Description
As a developer, I want the configuration system updated to remove all port registry dependencies while maintaining backwards compatibility for reading (but not writing) old configs.

#### Acceptance Criteria
- [ ] `ProjectPortsConfig` class removed from config.py
- [ ] `project_ports` field removed from Config class
- [ ] Config validation updated to ignore legacy port fields
- [ ] New optional `preferred_ports` field for user hints (non-binding)
- [ ] Config migration on first run (strips port fields)
- [ ] No persistence of port assignments in config

#### Technical Changes
```python
# REMOVE from config.py (lines 173-180):
class ProjectPortsConfig(BaseModel):
    """Configuration for project-specific port assignments."""
    qdrant_port: Optional[int] = Field(default=None, description="Qdrant service port")
    ollama_port: Optional[int] = Field(default=None, description="Ollama service port")
    data_cleaner_port: Optional[int] = Field(default=None, description="Data cleaner service port")

# REMOVE from Config class (line 323):
project_ports: ProjectPortsConfig = Field(default_factory=ProjectPortsConfig)

# ADD to Config class (optional):
preferred_ports: Optional[Dict[str, int]] = Field(
    default=None,
    description="User port preferences (hints only, not guaranteed)"
)

# ADD config migration logic:
def migrate_config_v2_to_v3(config_data: dict) -> dict:
    """Strip port registry fields from v2 configs."""
    if "project_ports" in config_data:
        del config_data["project_ports"]
    
    # Add version marker
    config_data["config_version"] = "3.0.0"
    
    return config_data
```

---

### STORY 4: Refactor Docker Manager Port Handling
**ID:** CIDX-3004  
**Priority:** P0 - Critical  
**Size:** L (Large)  
**Dependencies:** CIDX-3002, CIDX-3003

#### Description
As a developer, I want the Docker manager to use container-native port management so that all port allocation is handled by the runtime without central coordination.

#### Acceptance Criteria
- [ ] `allocate_project_ports()` method completely rewritten
- [ ] `ensure_project_configuration()` updated to remove port persistence
- [ ] `get_project_ports()` removed or repurposed for discovery
- [ ] Port registry initialization removed from `__init__`
- [ ] All registry cleanup code removed
- [ ] Docker Compose generation updated for dynamic ports

#### Implementation
```python
class DockerManager:
    def __init__(self, config: Config, console: Console = None):
        # REMOVE: self.port_registry = GlobalPortRegistry()
        self.port_manager = ContainerNativePortManager(
            runtime=self._detect_runtime()
        )
        # ... rest of init
    
    def start_services(self, services: List[str]) -> Dict[str, ServiceInfo]:
        """
        Start services with dynamic port allocation.
        No port pre-allocation, no persistence, pure runtime discovery.
        """
        started_services = {}
        
        for service in services:
            service_config = self._get_service_config(service)
            
            # Start with dynamic port
            service_info = self.port_manager.start_service_with_dynamic_port(
                service_name=service,
                internal_port=service_config.internal_port,
                image=service_config.image,
                env_vars=service_config.env_vars,
                volumes=service_config.volumes
            )
            
            started_services[service] = service_info
            
            # Update console with discovered port
            self.console.print(
                f"✅ Started {service} on port {service_info.port}",
                style="green"
            )
        
        return started_services
    
    def generate_compose_file(self) -> None:
        """
        Generate docker-compose.yml with dynamic port syntax.
        """
        compose_content = {
            "version": "3.8",
            "services": {}
        }
        
        for service in self.get_required_services():
            service_def = {
                "image": self._get_service_image(service),
                "container_name": f"{self.project_name}_{service}",
                "ports": [
                    f"0:{self._get_internal_port(service)}"  # Dynamic allocation
                ],
                "environment": self._get_service_env(service),
                "volumes": self._get_service_volumes(service),
                "restart": "unless-stopped"
            }
            
            compose_content["services"][service] = service_def
        
        # Write compose file
        with open(self.compose_file, "w") as f:
            yaml.dump(compose_content, f, default_flow_style=False)
```

---

### STORY 5: Remove CLI Registry Commands
**ID:** CIDX-3005  
**Priority:** P0 - Critical  
**Size:** M (Medium)  
**Dependencies:** CIDX-3001

#### Description
As a user, I want the CLI simplified by removing all global registry commands since port management is now automatic.

#### Acceptance Criteria
- [ ] `setup-global-registry` command completely removed
- [ ] `--setup-global-registry` flag removed from init command
- [ ] `_setup_global_registry()` function removed
- [ ] All registry-related help text removed
- [ ] Error messages updated to remove registry references
- [ ] Installation documentation updated

#### CLI Changes
```python
# REMOVE from cli.py:

# Lines 97-150 (entire _setup_global_registry function)
def _setup_global_registry(quiet: bool = False, test_access: bool = False) -> None:
    # ENTIRE FUNCTION DELETED

# Lines 712-715 (setup-global-registry flag)
@click.option(
    "--setup-global-registry",
    # OPTION DELETED
)

# Lines 798-800 (registry setup in init)
if setup_global_registry:
    _setup_global_registry(quiet=False, test_access=True)
    # BLOCK DELETED

# Lines 4587-4650 (entire setup-global-registry command)
@cli.command("setup-global-registry")
# ENTIRE COMMAND DELETED

# UPDATE help text:
# Remove all mentions of:
# - "sudo cidx setup-global-registry"
# - "cidx init --setup-global-registry"
# - "global port registry"
# - "/var/lib/code-indexer/port-registry"
```

---

### STORY 6: Create Container Port Discovery Tests
**ID:** CIDX-3006  
**Priority:** P1 - High  
**Size:** L (Large)  
**Dependencies:** CIDX-3002, CIDX-3004

#### Description
As a developer, I want comprehensive tests for container-native port management to ensure reliability across Docker and Podman runtimes.

#### Acceptance Criteria
- [ ] Unit tests for ContainerNativePortManager
- [ ] Integration tests for dynamic port allocation
- [ ] Docker compatibility tests
- [ ] Podman compatibility tests
- [ ] Multi-project isolation tests
- [ ] Port discovery retry logic tests
- [ ] Failure recovery tests

#### Test Implementation
```python
# tests/test_container_native_ports.py

class TestContainerNativePorts:
    """Test suite for container-native port management."""
    
    def test_dynamic_port_allocation(self):
        """Test that containers start with dynamically allocated ports."""
        manager = ContainerNativePortManager()
        
        # Start service with dynamic port
        service_info = manager.start_service_with_dynamic_port(
            service_name="test_qdrant",
            internal_port=6333,
            image="qdrant/qdrant:latest"
        )
        
        # Verify port was allocated
        assert service_info.port > 0
        assert service_info.port != 6333  # Should be different from internal
        
        # Verify service is accessible
        response = requests.get(f"{service_info.url}/health", timeout=5)
        assert response.status_code == 200
        
        # Cleanup
        manager.cleanup_service("test_qdrant")
    
    def test_port_discovery_retry(self):
        """Test that port discovery retries on slow container startup."""
        manager = ContainerNativePortManager()
        
        # Mock slow container startup
        with patch.object(manager, '_discover_assigned_port') as mock_discover:
            mock_discover.side_effect = [
                PortDiscoveryError("Not ready"),
                PortDiscoveryError("Still starting"),
                12345  # Success on third try
            ]
            
            service_info = manager.start_service_with_dynamic_port(
                service_name="slow_service",
                internal_port=8080,
                image="nginx:latest"
            )
            
            assert service_info.port == 12345
            assert mock_discover.call_count == 3
    
    def test_multi_project_isolation(self):
        """Test that multiple projects can run simultaneously."""
        manager1 = ContainerNativePortManager()
        manager2 = ContainerNativePortManager()
        
        # Start same service for two different projects
        service1 = manager1.start_service_with_dynamic_port(
            service_name="project1_qdrant",
            internal_port=6333,
            image="qdrant/qdrant:latest"
        )
        
        service2 = manager2.start_service_with_dynamic_port(
            service_name="project2_qdrant",
            internal_port=6333,
            image="qdrant/qdrant:latest"
        )
        
        # Verify different ports allocated
        assert service1.port != service2.port
        
        # Verify both services accessible
        assert requests.get(f"{service1.url}/health").status_code == 200
        assert requests.get(f"{service2.url}/health").status_code == 200
        
        # Cleanup
        manager1.cleanup_service("project1_qdrant")
        manager2.cleanup_service("project2_qdrant")
    
    @pytest.mark.parametrize("runtime", ["docker", "podman"])
    def test_runtime_compatibility(self, runtime):
        """Test compatibility with both Docker and Podman."""
        if not shutil.which(runtime):
            pytest.skip(f"{runtime} not available")
        
        manager = ContainerNativePortManager(runtime=runtime)
        
        service_info = manager.start_service_with_dynamic_port(
            service_name=f"test_{runtime}",
            internal_port=80,
            image="nginx:alpine"
        )
        
        assert service_info.port > 0
        assert requests.get(f"{service_info.url}/").status_code == 200
        
        manager.cleanup_service(f"test_{runtime}")
```

#### Tests to DELETE
```python
# Files to completely remove:
- tests/test_global_port_registry.py
- tests/test_setup_global_registry_e2e.py  
- tests/test_broken_softlink_cleanup.py
- tests/test_fix_config_port_regeneration.py
- tests/test_fix_config_port_bug_specific.py

# Test sections to remove from other files:
- Any test methods checking project_ports in config
- Any test methods verifying registry behavior
- Any test setup using --setup-global-registry
```

---

## IMPLEMENTATION PHASES

### Phase 1: Foundation (Week 1)
1. Create feature branch `feature/container-native-ports`
2. Implement ContainerNativePortManager class
3. Write comprehensive unit tests
4. Verify Docker/Podman compatibility

### Phase 2: Integration (Week 2)
1. Update DockerManager to use new port manager
2. Remove global registry code
3. Update configuration system
4. Migrate existing tests

### Phase 3: CLI Updates (Week 3)
1. Remove registry commands from CLI
2. Update all help text and documentation
3. Update error messages
4. Test installation flow

### Phase 4: Testing & Validation (Week 4)
1. Full regression testing
2. Multi-project isolation testing
3. Performance benchmarking
4. Documentation updates

### Phase 5: Release (Week 5)
1. Create v3.0.0 release branch
2. Update version numbers
3. Write migration guide
4. Release notes and changelog

---

## TECHNICAL DECISIONS & RATIONALE

### Decision 1: No Migration Path
**Choice:** Clean break, no automated migration from v2.x  
**Rationale:**
- Port assignments are ephemeral by nature
- Migration code adds complexity for one-time use
- Users can simply reinitialize projects
- Avoids carrying legacy compatibility code

**Alternatives Considered:**
1. Automated migration tool - Rejected: Complexity outweighs benefit
2. Compatibility layer - Rejected: Maintains unwanted complexity
3. Gradual deprecation - Rejected: Prolongs confusion

### Decision 2: Dynamic Ports Only
**Choice:** Use `-p 0:internal_port` exclusively  
**Rationale:**
- Container runtime handles all conflict resolution
- Zero coordination required between projects
- Impossible to have port conflicts
- Simplifies entire codebase

**Alternatives Considered:**
1. User-specified ports with fallback - Rejected: Reintroduces coordination need
2. Port ranges - Rejected: Still requires tracking
3. Hybrid approach - Rejected: Unnecessary complexity

### Decision 3: No Port Persistence
**Choice:** Ports discovered at runtime, never saved  
**Rationale:**
- Matches container ephemeral philosophy
- Eliminates stale port information
- Reduces configuration complexity
- Forces proper service discovery

**Alternatives Considered:**
1. Cache ports in config - Rejected: Creates staleness issues
2. Memory-only cache - Accepted: For session performance
3. Database storage - Rejected: Overkill for ephemeral data

### Decision 4: Container Inspection for Discovery
**Choice:** Use `docker/podman inspect` for port discovery  
**Rationale:**
- Native to container runtime
- Always accurate
- Works identically across platforms
- No external dependencies

**Alternatives Considered:**
1. Parse docker ps output - Rejected: Fragile parsing
2. Network scanning - Rejected: Security/performance concerns
3. Container labels - Rejected: Requires container cooperation

---

## RISK ASSESSMENT & MITIGATION

### Risk 1: Container Startup Timing
**Risk:** Port discovery fails if container hasn't fully started  
**Impact:** High  
**Probability:** Medium  
**Mitigation:**
- Implement retry logic with exponential backoff
- Add health check verification
- Provide clear error messages
- Default timeout of 30 seconds

### Risk 2: Runtime Compatibility
**Risk:** Docker and Podman behave differently  
**Impact:** High  
**Probability:** Low  
**Mitigation:**
- Extensive testing on both runtimes
- Abstract runtime differences in manager class
- CI/CD testing on both platforms
- Clear documentation of supported versions

### Risk 3: User Confusion
**Risk:** Breaking changes confuse existing users  
**Impact:** Medium  
**Probability:** High  
**Mitigation:**
- Clear migration documentation
- Prominent breaking change notices
- Version bump to 3.0.0 (semantic versioning)
- Deprecation warnings in 2.x releases

### Risk 4: Performance Impact
**Risk:** Dynamic discovery slower than static assignment  
**Impact:** Low  
**Probability:** Medium  
**Mitigation:**
- In-memory caching per session
- Parallel service startup
- Optimize inspection commands
- Benchmark against v2.x

---

## SUCCESS METRICS

### Objective Metrics
- **Code Reduction:** 400+ lines removed from global registry
- **Test Coverage:** >90% for new port management code
- **Startup Time:** <30 seconds for all services
- **Port Discovery:** <5 seconds per container
- **Zero Admin Privileges:** No sudo required anywhere

### Subjective Metrics
- **Installation Simplicity:** One-step process
- **Error Clarity:** Clear messages for all failure modes
- **Documentation Quality:** Comprehensive migration guide
- **User Satisfaction:** Measured via feedback

---

## DOCUMENTATION REQUIREMENTS

### User Documentation
1. **Migration Guide** - Step-by-step from v2.x to v3.0
2. **Breaking Changes** - Complete list with impacts
3. **Installation Guide** - Updated for simplified process
4. **Troubleshooting** - Common issues and solutions

### Developer Documentation
1. **Architecture Diagram** - New port management flow
2. **API Reference** - ContainerNativePortManager class
3. **Testing Guide** - How to test port allocation
4. **Contributing Guide** - Updated for new architecture

### README Updates
```markdown
## Installation (v3.0.0+)

The installation process has been greatly simplified in v3.0:

```bash
# Install code-indexer
pip install code-indexer==3.0.0

# Initialize your project (no sudo required!)
cidx init

# Start services (ports allocated automatically)
cidx start
```

### Breaking Changes from v2.x

Version 3.0 introduces automatic port management:
- No `setup-global-registry` command needed
- No sudo/admin privileges required  
- Ports are dynamically allocated by container runtime
- No port configuration in config files

To upgrade from v2.x:
1. Stop all running services: `cidx stop`
2. Upgrade: `pip install --upgrade code-indexer==3.0.0`
3. Reinitialize: `cidx init`
4. Start services: `cidx start`
```

---

## APPENDIX A: File Deletion List

### Complete File Deletions
```
src/code_indexer/services/global_port_registry.py (403 lines)
tests/test_global_port_registry.py
tests/test_setup_global_registry_e2e.py
tests/test_broken_softlink_cleanup.py
tests/test_fix_config_port_regeneration.py
tests/test_fix_config_port_bug_specific.py
```

### Partial File Modifications
```
src/code_indexer/config.py
  - Remove: ProjectPortsConfig class (lines 173-180)
  - Remove: project_ports field (line 323)

src/code_indexer/cli.py
  - Remove: _setup_global_registry function
  - Remove: setup-global-registry command
  - Remove: --setup-global-registry flag
  - Update: All help text mentioning registry

src/code_indexer/services/docker_manager.py
  - Remove: GlobalPortRegistry import
  - Remove: self.port_registry initialization
  - Rewrite: allocate_project_ports method
  - Rewrite: ensure_project_configuration method
  - Remove: Registry-related error handling
```

---

## APPENDIX B: New File Additions

### Core Implementation
```
src/code_indexer/services/container_port_manager.py (~300 lines)
  - ContainerNativePortManager class
  - Port discovery logic
  - Service lifecycle management
  - Runtime abstraction layer
```

### Test Files
```
tests/test_container_native_ports.py (~400 lines)
  - Unit tests for port manager
  - Integration tests
  - Runtime compatibility tests
  - Multi-project isolation tests
```

---

## APPENDIX C: Configuration Examples

### Old Config Format (v2.x)
```json
{
  "version": "2.16.0",
  "project_ports": {
    "qdrant_port": 36338,
    "ollama_port": 41148,
    "data_cleaner_port": 38095
  },
  "embedder": {
    "type": "ollama",
    "model": "nomic-embed-text"
  }
}
```

### New Config Format (v3.0)
```json
{
  "version": "3.0.0",
  "embedder": {
    "type": "ollama",
    "model": "nomic-embed-text"
  },
  "preferred_ports": {
    "qdrant": 6333,
    "ollama": 11434
  }
}
```
Note: `preferred_ports` is optional and serves only as hints. Actual ports are always dynamically allocated.

---

## APPROVAL & SIGN-OFF

### Stakeholder Approval
- [ ] Product Owner
- [ ] Technical Lead  
- [ ] QA Lead
- [ ] Documentation Team
- [ ] DevOps Team

### Pre-Implementation Checklist
- [ ] Epic approved by stakeholders
- [ ] Breaking changes communicated
- [ ] CI/CD pipeline updated for v3.0
- [ ] Rollback plan documented
- [ ] Performance benchmarks established

### Post-Implementation Checklist
- [ ] All tests passing
- [ ] Documentation complete
- [ ] Migration guide published
- [ ] v2.x deprecation notices added
- [ ] v3.0.0 released

---

## END OF SPECIFICATION

This epic represents a fundamental architectural shift that will significantly simplify the code-indexer installation and usage experience while eliminating an entire class of port-related issues. The removal of 400+ lines of registry code and 10+ test files will make the codebase more maintainable and easier to understand.

**Estimated Total Effort:** 5 weeks  
**Estimated Code Impact:** -2000 lines (net reduction)  
**Risk Level:** High (breaking change)  
**Business Value:** High (simplified UX, reduced support)
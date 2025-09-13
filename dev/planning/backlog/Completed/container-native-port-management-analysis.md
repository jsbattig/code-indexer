# Container-Native Port Management Analysis
## Alternative to Global Port Registry System

*Date: 2025-08-07*  
*Status: Technical Research & Feasibility Assessment*

---

## Executive Summary

This document analyzes the feasibility of replacing code-indexer's current global port registry system (`/var/lib/code-indexer/port-registry`) with container runtime native port auto-assignment capabilities. The analysis examines both Docker and Podman's dynamic port allocation features, service discovery patterns, and implementation strategies that could eliminate the need for a centralized port registry while maintaining multi-project isolation.

**Key Finding**: Container-native port management is technically feasible and could significantly simplify the architecture while maintaining all current functionality. The primary trade-off is between explicit port control (current system) and dynamic discovery complexity (proposed system).

---

## Current Architecture Analysis

### Global Port Registry System

The current implementation uses a centralized registry at `/var/lib/code-indexer/port-registry` with the following characteristics:

```python
# Current port allocation strategy
port_ranges = {
    "qdrant": (6333, 7333),      # 1000 port range
    "ollama": (11434, 12434),     # 1000 port range  
    "data_cleaner": (8091, 9091), # 1000 port range
}
```

**Key Components:**
1. **GlobalPortRegistry class**: Manages system-wide port allocation
2. **Soft links**: Track active projects via symlinks to `.code-indexer` directories
3. **Atomic operations**: Port allocation without file locking
4. **Self-healing**: Automatic cleanup of broken links when projects deleted
5. **Project hashing**: Uses SHA256 hash of project path for unique identification

**Current Strengths:**
- Prevents port conflicts across all projects
- Supports up to 1000 concurrent projects per service
- Predictable port assignments
- Direct port access without discovery overhead
- Works identically on Docker and Podman

**Current Weaknesses:**
- Requires privileged setup (`/var/lib` access)
- Complex synchronization logic
- Manual port management overhead
- Potential for registry corruption
- macOS compatibility issues with `/var/lib` paths

---

## Container Runtime Capabilities

### Docker Dynamic Port Allocation

#### Automatic Port Assignment (`-P` flag)

```bash
# Current approach (explicit ports)
docker run -d -p 6333:6333 qdrant/qdrant
docker run -d -p 11434:11434 ollama/ollama

# Dynamic allocation approach
docker run -d -P qdrant/qdrant           # Auto-assigns all exposed ports
docker run -d -p 0:6333 qdrant/qdrant    # Auto-assigns specific port
docker run -d --publish :6333 qdrant/qdrant  # Shorthand for auto-assignment
```

**Port Discovery:**
```bash
# Get assigned ports programmatically
docker inspect --format='{{json .NetworkSettings.Ports}}' container_id
docker port container_name
docker inspect --format='{{(index (index .NetworkSettings.Ports "6333/tcp") 0).HostPort}}' container_id
```

**Default Range**: Ephemeral ports typically 32768-60999 (configurable via kernel parameters)

#### Docker Compose Dynamic Ports

```yaml
version: '3.8'
services:
  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333"  # Dynamic host port, fixed container port
      
  ollama:
    image: ollama/ollama
    ports:
      - "11434"  # Dynamic host port
```

### Podman Dynamic Port Allocation

#### Rootless Considerations (2024 Updates)

**Key Changes in Podman 5.0:**
- `pasta` is now default networking (replaced slirp4netns)
- Full IPv6 support
- Better security architecture
- Some inter-container communication limitations

**Port Restrictions:**
- Cannot bind to ports < 1024 without CAP_NET_BIND_SERVICE
- Configurable via `sysctl net.ipv4.ip_unprivileged_port_start`

**Dynamic Assignment:**
```bash
# Similar to Docker
podman run -dt --rm -P qdrant/qdrant
podman port container_name
```

### Container-to-Container Communication

#### Service Discovery Without Port Exposure

**Docker Compose Networks:**
```yaml
version: '3.8'
services:
  qdrant:
    image: qdrant/qdrant
    networks:
      - cidx-network
    # No ports exposed to host
    
  ollama:
    image: ollama/ollama  
    networks:
      - cidx-network
    # No ports exposed to host
    
  app:
    image: code-indexer
    networks:
      - cidx-network
    environment:
      - QDRANT_URL=http://qdrant:6333  # Internal DNS resolution
      - OLLAMA_URL=http://ollama:11434  # Service name as hostname

networks:
  cidx-network:
    driver: bridge
    internal: false  # Allow external connectivity
```

**Key Insight**: Containers on the same network can communicate using service names without any port publishing to the host. This eliminates port conflicts entirely for internal services.

---

## Implementation Patterns

### Pattern 1: Full Dynamic Allocation with Discovery

```python
class ContainerNativePortManager:
    """Replace GlobalPortRegistry with runtime discovery."""
    
    def start_services(self, project_hash: str):
        """Start services with dynamic ports."""
        # Start containers with dynamic allocation
        qdrant_id = self._run_container(
            name=f"cidx-{project_hash}-qdrant",
            image="qdrant/qdrant",
            ports={6333: None}  # None = dynamic allocation
        )
        
        # Discover assigned port
        qdrant_port = self._get_assigned_port(qdrant_id, 6333)
        
        # Store in project config for later access
        self._update_project_config({
            "qdrant_port": qdrant_port,
            "qdrant_container": qdrant_id
        })
        
    def _get_assigned_port(self, container_id: str, internal_port: int) -> int:
        """Discover dynamically assigned port."""
        cmd = [
            "docker", "inspect", 
            f"--format={{{{(index (index .NetworkSettings.Ports \"{internal_port}/tcp\") 0).HostPort}}}}",
            container_id
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return int(result.stdout.strip())
```

### Pattern 2: Internal Network with Gateway Service

```python
class InternalNetworkManager:
    """Use internal networks with single gateway."""
    
    def create_project_network(self, project_hash: str):
        """Create isolated project network."""
        network_name = f"cidx-{project_hash}-net"
        
        # Create internal network
        subprocess.run([
            "docker", "network", "create",
            "--driver", "bridge",
            "--internal",  # No external access
            network_name
        ])
        
        # Start services on internal network
        self._start_internal_services(network_name)
        
        # Start gateway with dynamic port
        gateway_port = self._start_gateway(network_name)
        
        return {
            "network": network_name,
            "gateway_port": gateway_port,
            # Internal services accessed via gateway
            "qdrant_url": f"http://localhost:{gateway_port}/qdrant",
            "ollama_url": f"http://localhost:{gateway_port}/ollama"
        }
```

### Pattern 3: Hybrid Approach (Recommended)

```python
class HybridPortManager:
    """Combine dynamic allocation with predictable discovery."""
    
    def __init__(self):
        # Use high port ranges to avoid conflicts
        self.port_hints = {
            "qdrant": 36333,     # Preferred starting point
            "ollama": 41434,     # Preferred starting point
            "data_cleaner": 38091 # Preferred starting point
        }
        
    def allocate_port(self, service: str, project_hash: str) -> int:
        """Try preferred port, fall back to dynamic."""
        preferred = self.port_hints[service] + self._hash_offset(project_hash)
        
        if self._is_port_free(preferred):
            return preferred
        else:
            # Let Docker/Podman assign dynamically
            return 0  # Signal for dynamic allocation
            
    def start_with_discovery(self, service: str, project_hash: str):
        """Start container with smart port allocation."""
        port_hint = self.allocate_port(service, project_hash)
        
        if port_hint > 0:
            # Use specific port
            ports = {f"{port_hint}:6333"}
        else:
            # Use dynamic allocation
            ports = {"6333"}  # No host port specified
            
        container_id = self._run_container(service, ports)
        actual_port = self._discover_port(container_id)
        
        # Update project config with actual port
        self._persist_port_mapping(service, actual_port)
```

---

## Comparison Matrix

| Aspect | Current Global Registry | Container-Native Dynamic | Hybrid Approach |
|--------|-------------------------|-------------------------|-----------------|
| **Setup Complexity** | High (requires `/var/lib` access) | Low (no special permissions) | Low |
| **Port Predictability** | High (deterministic) | Low (ephemeral) | Medium |
| **Discovery Overhead** | None (direct access) | High (inspect required) | Low (cached) |
| **Multi-Project Support** | Excellent (1000 projects) | Unlimited | Unlimited |
| **Port Conflict Resolution** | Automatic (registry) | Automatic (runtime) | Automatic |
| **macOS Compatibility** | Poor (`/var/lib` issues) | Excellent | Excellent |
| **Docker/Podman Parity** | Full | Partial (pasta limitations) | Full |
| **Service Communication** | External ports required | Internal network option | Both options |
| **Recovery from Crashes** | Registry cleanup needed | Automatic | Automatic |
| **Configuration Persistence** | Registry + project config | Project config only | Project config only |

---

## Migration Strategy

### Phase 1: Parallel Implementation (2-3 days)
1. Implement `ContainerNativePortManager` alongside existing `GlobalPortRegistry`
2. Add `--use-dynamic-ports` flag to CLI
3. Update health checks to support port discovery
4. Maintain backward compatibility

### Phase 2: Testing & Validation (3-4 days)
1. Test dynamic allocation with multiple projects
2. Validate Podman rootless scenarios
3. Stress test with port exhaustion scenarios
4. Benchmark discovery overhead

### Phase 3: Gradual Migration (1 week)
1. Default new projects to dynamic allocation
2. Provide migration tool for existing projects
3. Update documentation
4. Deprecate global registry (keep for compatibility)

### Phase 4: Complete Transition (Future)
1. Remove global registry code
2. Simplify configuration model
3. Update all tests
4. Remove `/var/lib` setup requirements

---

## Technical Implementation Details

### Service Discovery Implementation

```python
class ServiceDiscovery:
    """Container service discovery utilities."""
    
    @staticmethod
    def get_container_port(container_name: str, internal_port: int, 
                          runtime: str = "docker") -> Optional[int]:
        """Get the host port mapped to container's internal port."""
        try:
            # Use JSON output for reliable parsing
            cmd = [
                runtime, "inspect",
                "--format={{json .NetworkSettings.Ports}}",
                container_name
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                ports = json.loads(result.stdout)
                port_key = f"{internal_port}/tcp"
                
                if port_key in ports and ports[port_key]:
                    # First mapping, first host port
                    return int(ports[port_key][0]["HostPort"])
        except (subprocess.SubprocessError, json.JSONDecodeError, KeyError):
            pass
            
        return None
    
    @staticmethod  
    def wait_for_port_assignment(container_name: str, internal_port: int,
                                 timeout: int = 10) -> Optional[int]:
        """Wait for container to get port assigned."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            port = ServiceDiscovery.get_container_port(container_name, internal_port)
            if port:
                return port
            time.sleep(0.5)
            
        return None
```

### Configuration Persistence

```python
class DynamicPortConfig:
    """Persist dynamic port mappings in project config."""
    
    def __init__(self, project_root: Path):
        self.config_file = project_root / ".code-indexer" / "dynamic-ports.json"
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        
    def save_port_mapping(self, service: str, port: int, container_id: str):
        """Save discovered port mapping."""
        config = self._load_config()
        
        config[service] = {
            "port": port,
            "container_id": container_id,
            "discovered_at": time.time()
        }
        
        self._save_config(config)
        
    def get_service_port(self, service: str) -> Optional[int]:
        """Retrieve saved port for service."""
        config = self._load_config()
        
        if service in config:
            # Verify container still exists
            if self._container_exists(config[service]["container_id"]):
                return config[service]["port"]
            else:
                # Container gone, remove stale entry
                del config[service]
                self._save_config(config)
                
        return None
```

### Health Check Adaptation

```python
class DynamicHealthChecker:
    """Health checks with dynamic port discovery."""
    
    def check_service_health(self, service: str, project_hash: str) -> bool:
        """Check service health with dynamic port discovery."""
        # Try to get port from saved config first
        port_config = DynamicPortConfig(self._get_project_root())
        port = port_config.get_service_port(service)
        
        if not port:
            # Discover from running container
            container_name = f"cidx-{project_hash}-{service}"
            internal_port = self.SERVICE_PORTS[service]
            port = ServiceDiscovery.get_container_port(container_name, internal_port)
            
            if port:
                # Cache for next time
                container_id = self._get_container_id(container_name)
                port_config.save_port_mapping(service, port, container_id)
                
        if port:
            return self._check_port_health(port, service)
            
        return False
```

---

## Real-World Constraints & Solutions

### Constraint 1: Podman Rootless Limitations
**Issue**: Cannot bind to ports < 1024  
**Solution**: Use high port ranges (30000+) for all services

### Constraint 2: Docker Desktop on macOS
**Issue**: Different networking model than Linux  
**Solution**: Rely on Docker's port forwarding, avoid direct network access

### Constraint 3: Multi-Project Isolation
**Issue**: Must maintain complete isolation between projects  
**Solution**: Use project-specific network namespaces with unique names

### Constraint 4: Performance Impact
**Issue**: Discovery adds latency vs direct port access  
**Solution**: Cache discovered ports in project config, refresh only on container restart

### Constraint 5: Backward Compatibility
**Issue**: Existing projects use global registry  
**Solution**: Dual-mode operation during transition period

---

## Recommendation

**Recommended Approach: Hybrid Implementation**

1. **Short Term (1-2 weeks)**:
   - Implement dynamic port allocation as optional feature
   - Use container-native discovery with caching
   - Maintain global registry for compatibility
   - Test thoroughly on both Docker and Podman

2. **Medium Term (1-2 months)**:
   - Default to dynamic allocation for new projects
   - Provide migration tools for existing projects
   - Deprecate but don't remove global registry

3. **Long Term (3-6 months)**:
   - Complete transition to container-native approach
   - Remove global registry entirely
   - Simplify codebase significantly

**Key Benefits of Migration:**
- Eliminates `/var/lib` permission requirements
- Improves macOS compatibility
- Reduces code complexity
- Leverages container runtime capabilities
- Removes port exhaustion limits
- Simplifies deployment and setup

**Primary Risk:**
- Added complexity in service discovery
- Potential performance impact (mitigated by caching)
- Podman networking differences require careful handling

---

## Code Examples & Prototypes

### Complete Working Example: Dynamic Port Manager

```python
#!/usr/bin/env python3
"""
Prototype: Container-native dynamic port management for code-indexer
"""

import json
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional, Tuple
import hashlib


class DynamicPortManager:
    """Manage containers with dynamic port allocation."""
    
    def __init__(self, project_root: Path, runtime: str = "docker"):
        self.project_root = project_root
        self.runtime = runtime  # docker or podman
        self.config_dir = project_root / ".code-indexer"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.port_cache_file = self.config_dir / "port-cache.json"
        self.project_hash = self._calculate_project_hash()
        
    def _calculate_project_hash(self) -> str:
        """Generate unique hash for project."""
        canonical_path = str(self.project_root.resolve())
        return hashlib.sha256(canonical_path.encode()).hexdigest()[:8]
        
    def start_service(self, service: str, image: str, 
                     internal_port: int) -> Tuple[str, int]:
        """Start a service with dynamic port allocation."""
        container_name = f"cidx-{self.project_hash}-{service}"
        
        # Check if already running
        if self._container_exists(container_name):
            print(f"Container {container_name} already exists")
            port = self._get_container_port(container_name, internal_port)
            if port:
                return container_name, port
                
        # Start with dynamic port
        cmd = [
            self.runtime, "run", "-d",
            "--name", container_name,
            "-p", f"{internal_port}",  # Dynamic host port
            image
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to start {service}: {result.stderr}")
            
        # Wait for port assignment
        port = self._wait_for_port(container_name, internal_port)
        if not port:
            raise RuntimeError(f"Port not assigned for {service}")
            
        # Cache the port
        self._cache_port(service, port, container_name)
        
        print(f"Started {service} on port {port}")
        return container_name, port
        
    def _container_exists(self, name: str) -> bool:
        """Check if container exists."""
        cmd = [self.runtime, "ps", "-a", "--format", "{{.Names}}"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return name in result.stdout.split('\n')
        
    def _get_container_port(self, container: str, internal: int) -> Optional[int]:
        """Get host port for container's internal port."""
        cmd = [
            self.runtime, "inspect",
            "--format={{json .NetworkSettings.Ports}}",
            container
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            ports = json.loads(result.stdout)
            port_key = f"{internal}/tcp"
            
            if port_key in ports and ports[port_key]:
                return int(ports[port_key][0]["HostPort"])
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
            pass
            
        return None
        
    def _wait_for_port(self, container: str, internal: int, 
                      timeout: int = 10) -> Optional[int]:
        """Wait for dynamic port assignment."""
        start = time.time()
        
        while time.time() - start < timeout:
            port = self._get_container_port(container, internal)
            if port:
                return port
            time.sleep(0.5)
            
        return None
        
    def _cache_port(self, service: str, port: int, container: str):
        """Cache port mapping for quick access."""
        cache = {}
        if self.port_cache_file.exists():
            with open(self.port_cache_file) as f:
                cache = json.load(f)
                
        cache[service] = {
            "port": port,
            "container": container,
            "timestamp": time.time()
        }
        
        with open(self.port_cache_file, 'w') as f:
            json.dump(cache, f, indent=2)
            
    def get_service_url(self, service: str, internal_port: int) -> Optional[str]:
        """Get service URL, using cache if available."""
        # Check cache first
        if self.port_cache_file.exists():
            with open(self.port_cache_file) as f:
                cache = json.load(f)
                if service in cache:
                    container = cache[service]["container"]
                    if self._container_exists(container):
                        return f"http://localhost:{cache[service]['port']}"
                        
        # Try to discover from running container
        container_name = f"cidx-{self.project_hash}-{service}"
        port = self._get_container_port(container_name, internal_port)
        
        if port:
            self._cache_port(service, port, container_name)
            return f"http://localhost:{port}"
            
        return None
        
    def stop_all_services(self):
        """Stop all project containers."""
        prefix = f"cidx-{self.project_hash}-"
        
        cmd = [self.runtime, "ps", "-a", "--format", "{{.Names}}"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        for container in result.stdout.split('\n'):
            if container.startswith(prefix):
                print(f"Stopping {container}")
                subprocess.run([self.runtime, "stop", container])
                subprocess.run([self.runtime, "rm", container])
                
        # Clear cache
        if self.port_cache_file.exists():
            self.port_cache_file.unlink()


# Example usage
if __name__ == "__main__":
    manager = DynamicPortManager(Path.cwd())
    
    # Start services with dynamic ports
    _, qdrant_port = manager.start_service(
        "qdrant", "qdrant/qdrant:latest", 6333
    )
    
    _, ollama_port = manager.start_service(
        "ollama", "ollama/ollama:latest", 11434
    )
    
    # Get service URLs
    print(f"Qdrant URL: {manager.get_service_url('qdrant', 6333)}")
    print(f"Ollama URL: {manager.get_service_url('ollama', 11434)}")
    
    # Clean up
    # manager.stop_all_services()
```

---

## Conclusion

Replacing the global port registry with container-native dynamic port allocation is not only feasible but offers significant advantages in terms of simplicity, compatibility, and maintainability. The recommended hybrid approach provides a smooth migration path while maintaining all current functionality.

The key insight is that modern container runtimes already solve the port allocation problem effectively. By leveraging these native capabilities instead of reimplementing them, code-indexer can become more robust, portable, and easier to deploy across different environments.

**Next Steps:**
1. Review and approve the recommended approach
2. Create detailed implementation plan
3. Develop prototype with feature flag
4. Test on Docker and Podman
5. Plan phased migration

This transition would mark a significant architectural improvement, eliminating one of the main deployment friction points while maintaining the multi-project isolation that makes code-indexer powerful.
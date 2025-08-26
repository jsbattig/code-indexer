# macOS Support Architecture Analysis

**Epic**: Cross-Platform Support - macOS Implementation  
**Created**: 2025-01-23  
**Priority**: Medium  
**Effort Estimate**: 3-4 weeks (not 2-3 days)  
**Status**: Analysis Complete - Ready for Planning

---

## Executive Summary

Adding macOS support to code-indexer requires significant architectural changes to address platform-specific filesystem, container runtime, and security model differences. The current Linux-focused implementation has hardcoded assumptions that prevent straightforward porting. **A robust implementation requires 3-4 weeks minimum**, not the initially estimated 2-3 days.

### Key Findings

- **Global Registry Path**: Hardcoded `/var/lib/code-indexer/port-registry` incompatible with macOS
- **Container Runtime**: Docker Desktop behavior differs from native Linux containers
- **Security Model**: macOS permission patterns require different approach
- **File System**: Volume mounting, permissions, and path conventions differ

### Recommendation

**Option A**: User-Space Only Implementation (Recommended)  
**Option B**: Full System Integration (High complexity)  
**Option C**: Wait for container-native coordination

---

## Technical Analysis

### Current Architecture Issues

#### 1. **Global Port Registry** (CRITICAL)
**File**: `src/code_indexer/services/global_port_registry.py:69`  
**Problem**: Hardcoded path `/var/lib/code-indexer/port-registry`
```python
# Current (Linux-only)
registry_location = Path("/var/lib/code-indexer/port-registry")

# Required (cross-platform)
def _get_registry_path(self) -> Path:
    if platform.system() == "Darwin":
        return Path.home() / "Library/Application Support/code-indexer/port-registry"
    else:
        return Path("/var/lib/code-indexer/port-registry")
```

#### 2. **Container Runtime Assumptions** (HIGH)
**Files**: `src/code_indexer/services/docker_manager.py`  
**Issues**:
- Docker Desktop runs in VM (different networking)
- Volume mount behavior differences
- Socket location variations
- Permission models differ

#### 3. **Permission Model** (HIGH)
**Files**: `src/code_indexer/cli.py:124-168`  
**Problems**:
- Multiple `sudo` calls incompatible with macOS security
- `chmod 777/666` triggers security warnings
- No consideration for System Integrity Protection (SIP)

### Platform Compatibility Matrix

| Component | Linux | macOS Intel | macOS ARM64 | Implementation Required |
|-----------|-------|-------------|-------------|-------------------------|
| Python 3.9+ | ✅ | ✅ | ✅ | None |
| Container Runtime | ✅ | ⚠️ | ⚠️ | Docker Desktop detection |
| Global Registry | ✅ | ❌ | ❌ | Path abstraction layer |
| File Permissions | ✅ | ❌ | ❌ | macOS ACLs or user-space |
| Volume Mounting | ✅ | ⚠️ | ⚠️ | Path translation |

---

## Implementation Options

### Option A: User-Space Only (RECOMMENDED)

**Effort**: 1.5-2 weeks  
**Risk**: Low  
**Maintenance**: Low  

**Strategy**: Move global registry to user-space, eliminating sudo requirements.

```python
class PlatformPaths:
    @staticmethod
    def get_registry_path() -> Path:
        if platform.system() == "Darwin":
            return Path.home() / "Library/Application Support/code-indexer"
        elif platform.system() == "Linux":
            return Path.home() / ".local/share/code-indexer"
        else:
            raise UnsupportedPlatformError()
```

**Advantages**:
- No admin privileges required
- Follows platform conventions
- Simpler security model
- Backwards compatible

**Trade-offs**:
- User-level coordination only
- Multiple users on same machine need coordination

### Option B: Full System Integration

**Effort**: 3-4 weeks  
**Risk**: High  
**Maintenance**: High  

**Strategy**: Implement full platform abstraction with system-level registry.

**Required Components**:
1. Platform detection framework
2. macOS authorization services integration
3. Container runtime abstraction layer
4. Path translation system
5. Permission management system

**Implementation Pattern**:
```python
class PlatformStrategy(ABC):
    @abstractmethod
    def get_registry_path(self) -> Path:
        pass
    
    @abstractmethod
    def setup_permissions(self, path: Path) -> None:
        pass
    
    @abstractmethod
    def get_container_runtime(self) -> ContainerRuntime:
        pass

class MacOSStrategy(PlatformStrategy):
    def get_registry_path(self) -> Path:
        return Path("/Library/Application Support/code-indexer/port-registry")
    
    def setup_permissions(self, path: Path) -> None:
        # Use macOS authorization services
        self._request_admin_privileges()
        path.mkdir(parents=True, mode=0o755)
```

### Option C: Container-Native Coordination

**Effort**: 2-3 weeks  
**Risk**: Medium  
**Maintenance**: Low  

**Strategy**: Eliminate global registry, use container orchestration for coordination.

```python
class ContainerCoordinator:
    def allocate_ports(self, services: List[str]) -> Dict[str, int]:
        # Let Docker/Podman handle dynamic port allocation
        return {service: 0 for service in services}  # 0 = dynamic
```

**Advantages**:
- Platform-agnostic
- Leverages existing container features
- No file system dependencies

**Trade-offs**:
- More complex service discovery
- Requires container runtime changes

---

## macOS Version Support Matrix

### Recommended Support

**Target**: macOS 10.15 (Catalina) and later

| macOS Version | Docker Desktop | Python 3.9+ | Market Share | Support Level |
|---------------|----------------|--------------|--------------|---------------|
| 15.x (Sequoia) | ✅ | ✅ | 70.54% | Full |
| 14.x (Sonoma) | ✅ | ✅ | ~15% | Full |
| 13.x (Ventura) | ✅ | ✅ | ~8% | Full |
| 12.x (Monterey) | ✅ | ✅ | ~5% | Basic |
| 11.x (Big Sur) | ✅ | ✅ | ~2% | Basic |
| 10.15 (Catalina) | ⚠️ | ✅ | <1% | Minimal |

**Rationale**:
- Covers 98%+ of active macOS users
- Docker Desktop minimum requirement: macOS 10.15
- Python 3.9+ compatibility across all versions

### Container Runtime Recommendations

1. **Colima** (Preferred): Lightweight, excellent Apple Silicon support
2. **Docker Desktop** (Standard): Full compatibility, resource intensive
3. **Podman Desktop** (Security): Rootless, slower on Apple Silicon

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1)
- [ ] Create platform abstraction layer
- [ ] Implement cross-platform path resolution
- [ ] Add container runtime detection
- [ ] Basic macOS path support

**Key Files to Modify**:
- `src/code_indexer/services/global_port_registry.py`
- `src/code_indexer/cli.py` (setup commands)
- `src/code_indexer/config.py` (path resolution)

### Phase 2: macOS Integration (Week 2)
- [ ] macOS-specific registry implementation
- [ ] Docker Desktop compatibility layer
- [ ] Permission model adaptation
- [ ] Volume mount translation

**New Files to Create**:
- `src/code_indexer/utils/platform.py`
- `src/code_indexer/platform/macos.py`
- `src/code_indexer/platform/linux.py`

### Phase 3: Testing & Validation (Week 3)
- [ ] Cross-platform unit tests
- [ ] macOS integration testing
- [ ] Container runtime compatibility tests
- [ ] Regression testing for Linux

**Test Infrastructure**:
- GitHub Actions macOS runners
- Docker Desktop test matrix
- Multi-architecture testing (Intel/ARM64)

### Phase 4: Polish & Documentation (Week 4)
- [ ] Bug fixes from testing
- [ ] macOS-specific documentation
- [ ] Installation guides
- [ ] CI/CD pipeline updates

---

## Risk Assessment

### High-Risk Areas

#### 🔴 **Data Loss Risk**
**Issue**: Different volume mount behaviors could corrupt data  
**Mitigation**: Extensive integration testing, data backup validation

#### 🔴 **Permission Escalation**
**Issue**: macOS security model differs from Linux  
**Mitigation**: Use user-space approach (Option A), avoid system-wide changes

#### 🔴 **Performance Degradation**
**Issue**: Docker Desktop VM overhead not accounted for  
**Mitigation**: Performance benchmarking, optimization for container workloads

### Medium-Risk Areas

#### 🟡 **Container Runtime Detection**
**Issue**: Multiple runtimes available, different behaviors  
**Mitigation**: Priority-based detection, explicit runtime selection

#### 🟡 **Network Configuration**
**Issue**: Docker Desktop networking differs from Linux  
**Mitigation**: Container-to-container communication, avoid host networking

### Low-Risk Areas

#### 🟢 **Python Compatibility**
Most Python code is cross-platform compatible

#### 🟢 **Core Indexing Logic**
Semantic processing algorithms are platform-agnostic

---

## Testing Strategy

### Test Categories

1. **Unit Tests**: Platform-specific logic isolation
2. **Integration Tests**: Full workflow on each platform
3. **Compatibility Tests**: Multiple container runtimes
4. **Performance Tests**: Resource usage comparison

### Test Matrix

```yaml
# .github/workflows/test-matrix.yml
strategy:
  matrix:
    os: [ubuntu-latest, macos-13, macos-14]
    python-version: ['3.9', '3.12']
    container-runtime: [docker, podman]
    exclude:
      - os: macos-13
        container-runtime: podman  # Limited support
```

### Key Test Scenarios

- [ ] Cross-platform registry coordination
- [ ] Docker Desktop vs Colima compatibility  
- [ ] Intel vs Apple Silicon behavior
- [ ] Volume mounting permissions
- [ ] Port allocation conflicts
- [ ] Multi-user scenarios

---

## Resource Requirements

### Development Environment
- macOS development machine (Intel + ARM64 testing)
- Docker Desktop license (if needed for commercial use)
- GitHub Actions macOS runners

### CI/CD Infrastructure
- macOS runners for automated testing
- Multi-architecture container builds
- Performance benchmarking setup

### Documentation Updates
- Platform-specific installation guides
- Container runtime selection guide
- macOS troubleshooting documentation

---

## Long-term Considerations

### Maintenance Overhead
- **Year 1**: 30% additional maintenance overhead
- **Year 2**: Platform-specific optimizations required
- **Year 3**: Consider platform-specific distributions

### Technology Evolution
- Apple Silicon adoption (increasing)
- Docker Desktop alternatives (growing)
- Container runtime standardization
- macOS security model changes

### Community Impact
- Large macOS developer community
- Potential for increased adoption
- Support burden from platform-specific issues

---

## Conclusion

Adding macOS support to code-indexer is **technically feasible** but requires **significant architectural investment**. The recommended approach is **Option A: User-Space Only** implementation, providing a **2-week development timeline** for a robust, maintainable solution.

### Key Success Factors

1. **Proper Platform Abstraction**: Don't bolt-on macOS support
2. **Comprehensive Testing**: Multi-platform, multi-runtime validation
3. **User-Centric Design**: Follow macOS conventions and expectations
4. **Gradual Rollout**: Beta testing with macOS community

### Decision Points

- **Go/No-Go**: Commit to 3-4 weeks of focused development
- **Approach Selection**: User-space vs system-level implementation
- **Support Scope**: Which macOS versions and container runtimes
- **Resource Allocation**: Development, testing, and ongoing maintenance

The analysis shows this is a worthwhile investment for expanding the user base, but requires proper planning and execution to avoid technical debt and support burden.

---

**Next Steps**: Review this analysis, select implementation approach, and create detailed user stories for the chosen option.
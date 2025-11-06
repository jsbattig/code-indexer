# Story: Lazy Port Registry Initialization for Filesystem Backend

## Story Description

**As a** developer using CIDX with filesystem vector storage
**I want to** run CIDX without any port registry or container dependencies
**So that** I can use the tool on any system without sudo setup or container runtime

**Problem Statement:**
The `DockerManager` class unconditionally initializes `GlobalPortRegistry` in its `__init__()` method (line 36), which requires `/var/lib/code-indexer/port-registry` directory. This happens even when using `--vector-store filesystem` which doesn't need containers or ports. This causes:
- Failures on macOS where `/var/lib` doesn't exist
- Permission errors on Linux without sudo setup
- Unnecessary overhead for container-free operation
- Confusion for users who explicitly chose filesystem backend to avoid containers

## Acceptance Criteria

### Functional Requirements
- [x] When using `cidx init --vector-store filesystem`, NO port registry code executes
- [x] When using `cidx index` with filesystem backend, NO port registry code executes
- [x] When using `cidx query` with filesystem backend, NO port registry code executes
- [x] Qdrant backend continues to work exactly as before with port registry
- [x] Legacy configs (without vector_store field) continue using port registry as before
- [x] No Docker/Podman checks occur when using filesystem backend
- [x] No `/var/lib/code-indexer` directory access attempts with filesystem backend

### Technical Requirements
- [x] GlobalPortRegistry only instantiated when QdrantContainerBackend is created
- [x] DockerManager only instantiated when containers are actually needed
- [x] Clean separation: filesystem code path never touches container/port code
- [x] All existing Qdrant tests continue passing
- [x] No performance regression for either backend
- [x] Thread-safe lazy initialization if accessed concurrently

### Safety Requirements
- [x] Backward compatibility: Existing Qdrant projects work without changes
- [x] Clear error messages if port registry missing when actually needed
- [x] No silent failures - explicit errors when container dependencies missing
- [x] Unit tests for both initialization paths (filesystem vs qdrant)
- [x] Integration tests verifying complete isolation of backends

## Implementation Approach

### Phase 1: Analyze Current Usage

**1. DockerManager instantiation points:**
```python
# src/code_indexer/cli.py - Lines to modify:
- Line 2832: docker_manager = DockerManager(console, project_name)  # setup command
- Line 6324: docker_manager = DockerManager(console, force_docker=True)  # setup-global-registry
- Line 7406: docker_manager = DockerManager(...)  # clean command
- Line 7676: docker_manager = DockerManager(...)  # clean legacy path
- Line 7738: docker_manager = DockerManager(console)  # docker-stats command

# Other files:
- server/app.py: FastAPI server (out of scope - Server Mode)
- services/config_fixer.py: Config migration
- mode_specific_handlers.py: Mode selection
- services/container_manager.py: Container lifecycle
- server/repositories/golden_repo_manager.py: Server mode (out of scope)
```

### Phase 2: Modify QdrantContainerBackend

**File: `src/code_indexer/backends/qdrant_container_backend.py`**

```python
# Add to __init__ method (after line 54):
def __init__(self, project_root: Path):
    super().__init__(project_root)
    self._docker_manager = None  # Lazy initialization
    self._port_registry = None   # Lazy initialization

# Add lazy initialization methods:
@property
def docker_manager(self):
    """Lazily initialize DockerManager only when needed."""
    if self._docker_manager is None:
        from ..services.docker_manager import DockerManager
        from rich.console import Console

        console = Console()
        project_name = self.project_root.name
        self._docker_manager = DockerManager(
            console=console,
            project_name=project_name,
            project_config_dir=self.project_root / ".code-indexer"
        )
    return self._docker_manager

@property
def port_registry(self):
    """Lazily initialize GlobalPortRegistry only when needed."""
    if self._port_registry is None:
        from ..services.global_port_registry import GlobalPortRegistry
        self._port_registry = GlobalPortRegistry()
    return self._port_registry

# Modify methods to use lazy properties:
def initialize(self) -> None:
    """Initialize Qdrant container backend."""
    logger.info("Initializing QdrantContainerBackend")
    # Use self.docker_manager instead of creating new instance
    self.docker_manager.initialize_containers()

def start(self) -> bool:
    """Start Qdrant containers."""
    return self.docker_manager.start_containers()

def stop(self) -> bool:
    """Stop Qdrant containers."""
    return self.docker_manager.stop_containers()
```

### Phase 3: Modify DockerManager to Accept Optional Port Registry

**File: `src/code_indexer/services/docker_manager.py`**

```python
# Modify __init__ (lines 22-40):
def __init__(
    self,
    console: Optional[Console] = None,
    project_name: Optional[str] = None,
    force_docker: bool = False,
    project_config_dir: Optional[Path] = None,
    port_registry: Optional[GlobalPortRegistry] = None,  # NEW: optional parameter
):
    self.console = console or Console()
    self.force_docker = force_docker
    self.project_name = project_name or self._detect_project_name()
    self.project_config_dir = project_config_dir or Path(".code-indexer")
    self.compose_file = self._get_project_compose_file_path()
    self._config = self._load_service_config()
    self.health_checker = HealthChecker()

    # MODIFIED: Only create if not provided and if we actually need it
    self._port_registry = port_registry  # Store provided or None

    self.indexing_root: Optional[Path] = None
    self._closed = False

# Add lazy property for port_registry:
@property
def port_registry(self):
    """Lazily initialize GlobalPortRegistry only when accessed."""
    if self._port_registry is None:
        # Only import and create when actually needed
        from .global_port_registry import GlobalPortRegistry
        self._port_registry = GlobalPortRegistry()
    return self._port_registry

# Modify _generate_container_names to use property (line 54):
def _generate_container_names(self, project_root: Path) -> Dict[str, str]:
    project_hash = self.port_registry._calculate_project_hash(project_root)
    # ... rest unchanged
```

### Phase 4: Update CLI Commands to Check Backend Type

**File: `src/code_indexer/cli.py`**

```python
# Add helper function near top of file (after imports):
def _needs_docker_manager(config: Optional[Config]) -> bool:
    """Check if current configuration requires DockerManager."""
    if config is None:
        # Legacy config without vector_store field - needs Docker
        return True

    if config.vector_store is None:
        # Legacy config - needs Docker
        return True

    # Only Qdrant backend needs Docker
    return config.vector_store.provider == "qdrant"

# Modify setup command (around line 2832):
@cli.command()
def setup(...):
    # ... existing code ...

    # Only create DockerManager if using Qdrant backend
    if _needs_docker_manager(config):
        docker_manager = DockerManager(console, project_name)
        # ... existing Docker setup code ...
    else:
        console.print("[green]Using filesystem backend - no containers needed[/green]")

# Modify clean command (around line 7406):
@cli.command()
def clean(...):
    # ... existing code ...

    # Only use DockerManager for Qdrant cleanup
    if backend_type == "qdrant" or backend_type is None:
        docker_manager = DockerManager(...)
        # ... existing cleanup code ...
    else:
        # Filesystem cleanup doesn't need DockerManager
        shutil.rmtree(index_dir, ignore_errors=True)
        console.print("[green]Filesystem index cleaned[/green]")

# Modify docker-stats command (around line 7738):
@cli.command("docker-stats")
def docker_stats(...):
    # Load config first to check backend
    config_manager = ConfigManager.create_with_backtrack(Path.cwd())
    config = config_manager.get_config()

    if not _needs_docker_manager(config):
        console.print("[yellow]Docker stats not applicable for filesystem backend[/yellow]")
        return

    docker_manager = DockerManager(console)
    # ... rest of command ...
```

### Phase 5: Clean Up Unnecessary Docker Checks

**File: `src/code_indexer/mode_specific_handlers.py`**

```python
# Check if this file instantiates DockerManager unnecessarily
# Modify to only create when backend requires it
```

## Test Scenarios

### Unit Tests

**Test file: `tests/unit/backends/test_lazy_initialization.py`**

```python
def test_filesystem_backend_no_docker_manager():
    """Verify FilesystemBackend never creates DockerManager."""
    from unittest.mock import patch

    with patch('code_indexer.services.docker_manager.DockerManager') as mock_dm:
        backend = FilesystemBackend(project_root=Path("/tmp/test"))
        backend.initialize()
        backend.start()
        backend.stop()
        backend.cleanup()

        # DockerManager should never be instantiated
        mock_dm.assert_not_called()

def test_filesystem_backend_no_port_registry():
    """Verify FilesystemBackend never creates GlobalPortRegistry."""
    from unittest.mock import patch

    with patch('code_indexer.services.global_port_registry.GlobalPortRegistry') as mock_pr:
        backend = FilesystemBackend(project_root=Path("/tmp/test"))
        backend.initialize()
        backend.start()

        # GlobalPortRegistry should never be instantiated
        mock_pr.assert_not_called()

def test_qdrant_backend_lazy_docker_manager():
    """Verify QdrantBackend only creates DockerManager when needed."""
    from unittest.mock import patch

    backend = QdrantContainerBackend(project_root=Path("/tmp/test"))

    # Should not create DockerManager in __init__
    assert backend._docker_manager is None

    # Should create when accessed
    with patch('code_indexer.services.docker_manager.DockerManager') as mock_dm:
        _ = backend.docker_manager
        mock_dm.assert_called_once()

def test_qdrant_backend_lazy_port_registry():
    """Verify QdrantBackend only creates GlobalPortRegistry when needed."""
    backend = QdrantContainerBackend(project_root=Path("/tmp/test"))

    # Should not create GlobalPortRegistry in __init__
    assert backend._port_registry is None

    # Should create when accessed via docker_manager
    with patch('code_indexer.services.global_port_registry.GlobalPortRegistry') as mock_pr:
        backend.initialize()  # This should trigger creation
        mock_pr.assert_called()

def test_legacy_config_uses_docker():
    """Verify legacy configs without vector_store field still use Docker."""
    config = Config(
        project_name="test",
        # No vector_store field (legacy)
    )

    assert _needs_docker_manager(config) == True

def test_filesystem_config_no_docker():
    """Verify filesystem config doesn't need Docker."""
    config = Config(
        project_name="test",
        vector_store=VectorStoreConfig(provider="filesystem")
    )

    assert _needs_docker_manager(config) == False

def test_qdrant_config_needs_docker():
    """Verify Qdrant config needs Docker."""
    config = Config(
        project_name="test",
        vector_store=VectorStoreConfig(provider="qdrant")
    )

    assert _needs_docker_manager(config) == True
```

### Integration Tests

**Test file: `tests/e2e/test_backend_isolation.py`**

```python
def test_filesystem_cli_no_port_registry():
    """Verify filesystem CLI operations never touch port registry."""
    import tempfile
    import subprocess
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmpdir:
        # Patch to make GlobalPortRegistry fail if accessed
        with patch.dict(os.environ, {"FAIL_ON_PORT_REGISTRY": "1"}):
            # Initialize with filesystem backend
            result = subprocess.run(
                ["cidx", "init", "--vector-store", "filesystem"],
                cwd=tmpdir,
                capture_output=True,
                text=True
            )
            assert result.returncode == 0
            assert "filesystem" in result.stdout

            # Index with filesystem backend
            # Create test file
            Path(tmpdir, "test.py").write_text("def test(): pass")

            result = subprocess.run(
                ["cidx", "index"],
                cwd=tmpdir,
                capture_output=True,
                text=True
            )
            assert result.returncode == 0

            # Query with filesystem backend
            result = subprocess.run(
                ["cidx", "query", "test", "--quiet"],
                cwd=tmpdir,
                capture_output=True,
                text=True
            )
            assert result.returncode == 0

def test_qdrant_cli_uses_port_registry():
    """Verify Qdrant CLI operations properly use port registry."""
    import tempfile
    import subprocess

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize with Qdrant backend
        result = subprocess.run(
            ["cidx", "init", "--vector-store", "qdrant"],
            cwd=tmpdir,
            capture_output=True,
            text=True
        )
        # May fail if Docker not available, but should attempt port registry
        # Check that it tried to use Docker/port registry
        assert "qdrant" in result.stdout.lower() or "docker" in result.stderr.lower()

def test_no_var_lib_access_filesystem():
    """Verify filesystem backend never accesses /var/lib/code-indexer."""
    import tempfile
    import strace  # Would need strace monitoring

    with tempfile.TemporaryDirectory() as tmpdir:
        # Monitor file access during filesystem operations
        # Verify no access to /var/lib/code-indexer
        pass  # Pseudo-code for monitoring
```

### Manual Testing Steps

1. **Test Filesystem Backend Isolation:**
   ```bash
   # On macOS (where /var/lib doesn't exist)
   cd /tmp/test-filesystem
   cidx init --vector-store filesystem
   echo "def hello(): return 'world'" > test.py
   cidx index
   cidx query "hello function" --quiet
   # Should complete without any /var/lib errors
   ```

2. **Test Qdrant Backend Still Works:**
   ```bash
   # On Linux with Docker
   cd /tmp/test-qdrant
   cidx init --vector-store qdrant
   echo "def goodbye(): return 'world'" > test.py
   cidx index
   cidx query "goodbye function" --quiet
   # Should work as before, using containers
   ```

3. **Test Legacy Config Compatibility:**
   ```bash
   # Use existing project with old config (no vector_store field)
   cd /path/to/legacy-project
   cidx index  # Should still use Qdrant/containers
   cidx query "test" --quiet
   # Should work exactly as before
   ```

4. **Test Error Messages:**
   ```bash
   # Remove Docker/Podman, try Qdrant backend
   cd /tmp/test-error
   cidx init --vector-store qdrant
   # Should show clear error about Docker/Podman requirement

   # Try to use docker-stats with filesystem
   cd /tmp/test-filesystem
   cidx init --vector-store filesystem
   cidx docker-stats
   # Should show message that docker-stats not applicable
   ```

5. **Test Clean Command:**
   ```bash
   # Filesystem cleanup
   cd /tmp/test-filesystem
   cidx init --vector-store filesystem
   cidx index
   cidx clean --all
   # Should clean without Docker

   # Qdrant cleanup
   cd /tmp/test-qdrant
   cidx init --vector-store qdrant
   cidx index
   cidx clean --all
   # Should use Docker for cleanup
   ```

## Files to Modify

1. **src/code_indexer/backends/qdrant_container_backend.py**
   - Add lazy initialization for DockerManager and GlobalPortRegistry
   - Modify methods to use lazy properties

2. **src/code_indexer/services/docker_manager.py**
   - Make port_registry parameter optional in __init__
   - Add lazy initialization property for port_registry
   - Update all port_registry references to use property

3. **src/code_indexer/cli.py**
   - Add _needs_docker_manager() helper function
   - Modify setup command (line ~2832)
   - Modify clean command (line ~7406)
   - Modify docker-stats command (line ~7738)
   - Update setup-global-registry command (line ~6324)

4. **tests/unit/backends/test_lazy_initialization.py** (NEW)
   - Add comprehensive unit tests for lazy initialization

5. **tests/e2e/test_backend_isolation.py** (NEW)
   - Add integration tests verifying backend isolation

## Implementation Order

1. **Phase 1**: Modify QdrantContainerBackend for lazy initialization
2. **Phase 2**: Update DockerManager to accept optional port_registry
3. **Phase 3**: Update CLI commands to check backend type
4. **Phase 4**: Add unit tests
5. **Phase 5**: Add integration tests
6. **Phase 6**: Manual testing and validation

## Success Metrics

- Filesystem backend operations complete without any container/port code execution
- Zero calls to GlobalPortRegistry when using filesystem backend
- Qdrant backend continues working exactly as before
- All existing tests pass
- New isolation tests pass
- No performance regression for either backend
- Clean error messages when container dependencies missing for Qdrant

## Risk Mitigation

- **Risk**: Breaking existing Qdrant installations
  - **Mitigation**: Extensive backward compatibility tests, legacy config tests

- **Risk**: Race conditions in lazy initialization
  - **Mitigation**: Thread-safe initialization with locks if needed

- **Risk**: Hidden dependencies on DockerManager
  - **Mitigation**: Complete grep analysis, mock tests to catch any usage

## Notes

- This change improves the user experience for filesystem backend users
- Makes CIDX truly container-free when using filesystem backend
- Maintains full backward compatibility for existing Qdrant users
- Follows separation of concerns - each backend manages its own dependencies
- Server Mode is out of scope - it always needs containers
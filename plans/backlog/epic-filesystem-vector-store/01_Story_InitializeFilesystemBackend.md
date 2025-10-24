# Story 1: Initialize Filesystem Backend for Container-Free Indexing

**Story ID:** S01
**Epic:** Filesystem-Based Vector Database Backend
**Priority:** High
**Estimated Effort:** 3-5 days
**Implementation Order:** 2 (after POC)

## User Story

**As a** developer working in a container-restricted environment
**I want to** initialize code-indexer with a filesystem-based vector storage backend
**So that** I can set up semantic search without requiring Docker/Podman containers

**Conversation Reference:** "abstract the qdrant db provider behind an abstraction layer, and create a similar one for our new db, and drop it in based on a --flag on init commands" - User explicitly requested backend abstraction with initialization flag.

## Acceptance Criteria

### Functional Requirements
1. ✅ `cidx init` (no flag) creates filesystem backend configuration (DEFAULT BEHAVIOR)
2. ✅ `cidx init --vector-store filesystem` explicitly creates filesystem backend (same as default)
3. ✅ `cidx init --vector-store qdrant` opts into Qdrant backend with containers
4. ✅ Creates `.code-indexer/index/` directory structure for filesystem backend
5. ✅ Generates configuration file without port allocations for filesystem
6. ✅ Backend abstraction layer supports both Qdrant and filesystem backends
7. ✅ Existing projects with Qdrant config continue to work (no breaking changes)

### Technical Requirements
1. ✅ VectorStoreBackend abstract interface defined with methods:
   - `initialize()`, `start()`, `stop()`, `get_status()`, `cleanup()`
   - `get_vector_store_client()`, `health_check()`, `get_service_info()`
2. ✅ FilesystemBackend implements VectorStoreBackend interface
3. ✅ QdrantContainerBackend wraps existing Docker/Qdrant functionality
4. ✅ VectorStoreBackendFactory creates appropriate backend from config
5. ✅ Configuration schema includes `vector_store.provider` field
6. ✅ **Backward compatibility:** If `vector_store.provider` not in config, assume `"qdrant"`
   - Old configs (created before filesystem support) default to Qdrant
   - Ensures existing installations continue working without changes

### Command Behavior Matrix

**User Requirement:** "you will need to ensure we have a matrix/table created in a story to specific exactly how commands that are qdrant bound/docker bound needs to behave in the context of filesystem db"

| Command | Filesystem Backend | Qdrant Backend | Notes |
|---------|-------------------|----------------|-------|
| `cidx init` | Creates `.code-indexer/vectors/` | Creates config, allocates ports | Default changed to filesystem |
| `cidx start` | ✅ Succeeds immediately (no-op) | Starts Docker containers | Filesystem: logs "No services to start" |
| `cidx stop` | ✅ Succeeds immediately (no-op) | Stops Docker containers | Filesystem: logs "No services to stop" |
| `cidx status` | Shows filesystem stats (files, size) | Shows container status, Qdrant stats | Different info, same structure |
| `cidx index` | Writes to `.code-indexer/vectors/` | Writes to Qdrant containers | Identical interface |
| `cidx query` | Reads from filesystem | Reads from Qdrant | Identical interface |
| `cidx clean` | Deletes collection directory | Deletes Qdrant collection | Identical behavior |
| `cidx uninstall` | Removes `.code-indexer/vectors/` | Stops/removes containers | Cleans up backend |
| `cidx optimize` | ✅ Succeeds immediately (no-op) | Triggers Qdrant optimization | Filesystem: logs "No optimization needed" |
| `cidx force-flush` | ✅ Succeeds immediately (no-op) | Forces Qdrant flush | Filesystem: logs "Already on disk" |

**Transparent Success Pattern:**
- Docker/Qdrant-specific commands succeed silently when using filesystem backend
- No errors, no warnings (unless --verbose)
- Optional informational message: "Filesystem backend - no X needed"
- User workflow unaffected by backend choice

### User Experience
1. Clear feedback during initialization showing filesystem backend selection
2. No port allocation or container checks for filesystem backend
3. Informative message showing vector storage location
4. Error messages if directory creation fails

## Manual Testing Steps

```bash
# Test 1: Default initialization (filesystem - NO containers)
cd /tmp/test-project-default
git init
cidx init

# Expected output:
# ✅ Filesystem backend initialized (default)
# 📁 Vectors will be stored in .code-indexer/index/
# ℹ️  No containers required - ready to index
# ✅ Project initialized

# Verify directory structure created
ls -la .code-indexer/
# Expected: index/ directory exists, NO container ports in config

# Test 2: Verify default configuration
cat .code-indexer/config.json
# Expected: "vector_store": {"provider": "filesystem", "path": ".code-indexer/index"}

# Test 3: Explicitly request filesystem (same as default)
cd /tmp/test-project-filesystem
git init
cidx init --vector-store filesystem

# Expected: Same as Test 1 (explicit flag redundant with default)

# Test 4: Opt-in to Qdrant (requires explicit flag)
cd /tmp/test-project-qdrant
git init
cidx init --vector-store qdrant

# Expected output:
# ℹ️  Using Qdrant container backend
# 🐳 Checking Docker/Podman availability...
# 📋 Allocating ports for containers...
# ✅ Qdrant backend initialized

# Test 5: Verify existing projects unaffected
cd /existing/project/with/qdrant
cidx status
# Expected: Uses Qdrant backend (config already specifies provider)
```

## Technical Implementation Details

### Backend Abstraction Architecture

**Conversation Reference:** "you need to investigate all operations we do with qdrant, and literally every operation we do, maps to a feature" - Backend abstraction must support all existing Qdrant operations.

```python
# VectorStoreBackend interface (abstract)
class VectorStoreBackend(ABC):
    @abstractmethod
    def initialize(self, config: Dict) -> bool:
        """Initialize backend (create structures, pull images, etc)."""
        pass

    @abstractmethod
    def start(self) -> bool:
        """Start backend services."""
        pass

    @abstractmethod
    def stop(self) -> bool:
        """Stop backend services."""
        pass

    @abstractmethod
    def get_vector_store_client(self) -> Any:
        """Return QdrantClient or FilesystemVectorStore."""
        pass

# FilesystemBackend implementation
class FilesystemBackend(VectorStoreBackend):
    def initialize(self, config: Dict) -> bool:
        """Create .code-indexer/index/ directory."""
        self.base_path = Path(config.codebase_dir) / ".code-indexer" / "index"
        self.base_path.mkdir(parents=True, exist_ok=True)
        return True

    def start(self) -> bool:
        """No-op - filesystem always ready."""
        return True

# QdrantContainerBackend implementation
class QdrantContainerBackend(VectorStoreBackend):
    def initialize(self, config: Dict) -> bool:
        """Setup containers, ports, networks."""
        return self.docker_manager.setup_project_containers()

    def start(self) -> bool:
        """Start Qdrant and data-cleaner containers."""
        return self.docker_manager.start_containers()
```

### Backend Factory with Backward Compatibility

```python
class VectorStoreBackendFactory:
    """Factory for creating appropriate backend with backward compatibility."""

    @staticmethod
    def create_backend(config: Config) -> VectorStoreBackend:
        """Create backend based on configuration.

        Backward compatibility: If vector_store.provider not in config,
        assume 'qdrant' (old configs created before filesystem support).
        """
        # Get provider from config, default to 'qdrant' for old configs
        if hasattr(config, 'vector_store') and config.vector_store:
            provider = config.vector_store.get('provider', 'qdrant')
        else:
            # Old config without vector_store section → Qdrant
            provider = 'qdrant'

        if provider == 'filesystem':
            return FilesystemBackend(config)
        elif provider == 'qdrant':
            docker_manager = DockerManager(config)
            return QdrantContainerBackend(docker_manager, config)
        else:
            raise ValueError(f"Unknown backend provider: {provider}")
```

### Configuration Schema Changes

```python
@dataclass
class VectorStoreConfig:
    provider: str = "filesystem"  # "qdrant" or "filesystem" (default: filesystem)
    filesystem_path: Optional[str] = ".code-indexer/index"  # Updated location
    depth_factor: int = 4  # From POC results
    reduced_dimensions: int = 64
    quantization_bits: int = 2
```

**Note:** New configs default to "filesystem", but missing provider field defaults to "qdrant" for backward compatibility.

**Directory Location:** All filesystem-based indexes stored in `.code-indexer/index/` subdirectory within the indexed repository.

### CLI Integration

```python
@click.command()
@click.option(
    "--vector-store",
    type=click.Choice(["qdrant", "filesystem"]),
    default="qdrant",
    help="Vector storage backend (qdrant=containers, filesystem=no containers)"
)
def init_command(vector_store: str, **kwargs):
    """Initialize project with selected backend."""
    # Create backend via factory
    backend = VectorStoreBackendFactory.create_backend(
        vector_store_provider=vector_store
    )

    # Initialize backend
    if not backend.initialize(config):
        console.print("❌ Failed to initialize backend", style="red")
        raise Exit(1)
```

## Dependencies

### Internal Dependencies
- Configuration management system
- CLI command infrastructure
- Existing Docker/Qdrant integration code (to be wrapped)

### External Dependencies
- Python `pathlib` for directory operations
- No container dependencies for filesystem backend

## Success Metrics

1. ✅ Filesystem backend initializes without errors
2. ✅ Directory structure created at `.code-indexer/vectors/`
3. ✅ Configuration persisted correctly
4. ✅ Backward compatibility maintained (Qdrant still works)
5. ✅ Zero container dependencies when using filesystem backend

## Non-Goals

- Migration tools from Qdrant to filesystem (user will destroy/reinit/reindex)
- Performance optimization (handled in Story 2)
- Multi-backend support (one backend per project)
- Runtime backend switching (must reinit to switch)

## Follow-Up Stories

- **Story 2**: Index Code to Filesystem Without Containers (uses this initialization)
- **Story 6**: Seamless Start and Stop Operations (uses backend abstraction)
- **Story 8**: Switch Between Qdrant and Filesystem Backends (builds on this foundation)

## Unit Test Coverage Requirements

**Test Strategy:** Use real filesystem operations with tmp_path fixtures (NO mocking)

**Test File:** `tests/unit/backends/test_filesystem_backend.py`

**Required Tests:**

```python
class TestFilesystemBackendInitialization:
    """Test backend initialization without mocking filesystem."""

    def test_initialize_creates_directory_structure(self, tmp_path):
        """GIVEN a config with filesystem backend
        WHEN initialize() is called
        THEN .code-indexer/vectors/ directory is created"""
        config = Config(codebase_dir=tmp_path, vector_store={'provider': 'filesystem'})
        backend = FilesystemBackend(config)

        result = backend.initialize(config)

        assert result is True
        assert (tmp_path / ".code-indexer" / "vectors").exists()
        assert (tmp_path / ".code-indexer" / "vectors").is_dir()

    def test_start_returns_true_immediately(self, tmp_path):
        """GIVEN a filesystem backend
        WHEN start() is called
        THEN it returns True in <10ms (no services to start)"""
        backend = FilesystemBackend(config)

        start_time = time.perf_counter()
        result = backend.start()
        duration = time.perf_counter() - start_time

        assert result is True
        assert duration < 0.01  # <10ms

    def test_health_check_validates_write_access(self, tmp_path):
        """GIVEN a filesystem backend
        WHEN health_check() is called
        THEN it verifies directory exists and is writable"""
        backend = FilesystemBackend(config)
        backend.initialize(config)

        assert backend.health_check() is True

        # Make directory read-only
        vectors_dir = tmp_path / ".code-indexer" / "vectors"
        os.chmod(vectors_dir, 0o444)

        assert backend.health_check() is False

    def test_default_backend_is_filesystem(self):
        """GIVEN config without explicit vector_store provider
        WHEN BackendFactory.create_backend() is called
        THEN FilesystemBackend is created (default)"""
        config_default = Config()  # No vector_store specified

        backend = VectorStoreBackendFactory.create_backend(config_default)

        assert isinstance(backend, FilesystemBackend)

    def test_backend_factory_creates_correct_backend(self):
        """GIVEN config with provider='filesystem' or 'qdrant'
        WHEN BackendFactory.create_backend() is called
        THEN appropriate backend is created"""
        config_fs = Config(vector_store={'provider': 'filesystem'})
        config_qd = Config(vector_store={'provider': 'qdrant'})

        backend_fs = VectorStoreBackendFactory.create_backend(config_fs)
        backend_qd = VectorStoreBackendFactory.create_backend(config_qd)

        assert isinstance(backend_fs, FilesystemBackend)
        assert isinstance(backend_qd, QdrantContainerBackend)

    def test_explicit_filesystem_same_as_default(self):
        """GIVEN two configs: one with 'filesystem', one default
        WHEN creating backends
        THEN both create FilesystemBackend"""
        config_explicit = Config(vector_store={'provider': 'filesystem'})
        config_default = Config()  # Defaults to filesystem

        backend_explicit = VectorStoreBackendFactory.create_backend(config_explicit)
        backend_default = VectorStoreBackendFactory.create_backend(config_default)

        assert type(backend_explicit) == type(backend_default)
        assert isinstance(backend_explicit, FilesystemBackend)

    def test_legacy_config_without_provider_defaults_to_qdrant(self, tmp_path):
        """GIVEN old config file without vector_store.provider field
        WHEN loading config and creating backend
        THEN Qdrant backend is created (backward compatibility)"""
        # Simulate old config file (no vector_store section)
        old_config = {
            'codebase_dir': str(tmp_path),
            'embedding_provider': 'voyage-ai',
            'qdrant': {
                'host': 'http://localhost:6333',
                'collection_base_name': 'code_index'
            }
            # NO vector_store field - old config
        }

        config_path = tmp_path / '.code-indexer' / 'config.json'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(old_config, f)

        # Load and create backend
        config = Config.from_file(config_path)
        backend = VectorStoreBackendFactory.create_backend(config)

        # Should default to Qdrant for backward compatibility
        assert isinstance(backend, QdrantContainerBackend)

class TestCommandBehaviorWithFilesystemBackend:
    """Test Docker/Qdrant-specific command behavior with filesystem backend."""

    def test_start_command_succeeds_immediately(self, tmp_path):
        """GIVEN filesystem backend
        WHEN start() is called
        THEN succeeds immediately with no-op"""
        backend = FilesystemBackend(config)

        start_time = time.perf_counter()
        result = backend.start()
        duration = time.perf_counter() - start_time

        assert result is True
        assert duration < 0.01  # Immediate

    def test_stop_command_succeeds_immediately(self, tmp_path):
        """GIVEN filesystem backend
        WHEN stop() is called
        THEN succeeds immediately with no-op"""
        backend = FilesystemBackend(config)

        result = backend.stop()

        assert result is True  # Transparent success

    def test_optimize_command_behavior(self, tmp_path):
        """GIVEN filesystem backend
        WHEN optimize operation requested
        THEN succeeds immediately (no optimization needed)"""
        store = FilesystemVectorStore(tmp_path, config)

        # optimize_collection should succeed as no-op
        result = store.optimize_collection('test_coll')

        assert result is True

    def test_force_flush_command_behavior(self, tmp_path):
        """GIVEN filesystem backend
        WHEN force_flush operation requested
        THEN succeeds immediately (already on disk)"""
        store = FilesystemVectorStore(tmp_path, config)

        result = store.force_flush_to_disk('test_coll')

        assert result is True

    def test_get_vector_store_client_returns_filesystem_store(self, tmp_path):
        """GIVEN a FilesystemBackend
        WHEN get_vector_store_client() is called
        THEN FilesystemVectorStore instance is returned"""
        backend = FilesystemBackend(config)
        backend.initialize(config)

        client = backend.get_vector_store_client()

        assert isinstance(client, FilesystemVectorStore)
        assert client.base_path == tmp_path / ".code-indexer" / "vectors"

    def test_cleanup_removes_vectors_directory(self, tmp_path):
        """GIVEN initialized filesystem backend with data
        WHEN cleanup(remove_data=True) is called
        THEN .code-indexer/vectors/ is removed"""
        backend = FilesystemBackend(config)
        backend.initialize(config)

        # Create some test data
        vectors_dir = tmp_path / ".code-indexer" / "vectors"
        (vectors_dir / "test_file.json").write_text("{}")

        result = backend.cleanup(remove_data=True)

        assert result is True
        assert not vectors_dir.exists()
```

**Coverage Requirements:**
- ✅ Directory creation (real filesystem)
- ✅ Start/stop operations (timing validation)
- ✅ Health checks (write permission validation)
- ✅ Backend factory selection
- ✅ Client creation
- ✅ Cleanup operations (actual removal)

**Test Data:**
- Use pytest tmp_path fixtures for isolated test directories
- No mocking of pathlib or os operations
- Real directory creation and removal

**Performance Assertions:**
- start() completes in <10ms (no services)
- initialize() completes in <100ms

## Implementation Notes

### Default Backend Behavior

**USER REQUIREMENT:** "make sure we specify that if the user doesn't specify the db storage subsystem, we default to filesystem, only if the user asks for qdrant, we use qdrant"

**Default Behavior:**
- `cidx init` → **Defaults to FILESYSTEM backend** (no --vector-store flag needed)
- `cidx init --vector-store qdrant` → Explicitly use Qdrant with containers
- `cidx init --vector-store filesystem` → Explicitly use filesystem (redundant with default)

**Configuration:**
```python
@click.option(
    "--vector-store",
    type=click.Choice(["qdrant", "filesystem"]),
    default="filesystem",  # DEFAULT CHANGED: filesystem is now default
    help="Vector storage backend (default: filesystem - no containers)"
)
```

**Rationale:**
- Filesystem backend eliminates container dependencies (simpler setup)
- Users explicitly opt-in to Qdrant when they want container-based storage
- New users get zero-dependency experience by default

**Migration for Existing Users:**
- Existing projects with Qdrant continue working (config already specifies provider)
- Only NEW projects default to filesystem
- No breaking changes to existing installations

### Technical Implementation

**Critical Design Decision:** No port allocation for filesystem backend. The existing port registry code should be skipped entirely when `vector_store.provider == "filesystem"`.

**Directory Placement:** All filesystem-based vector indexes stored in `.code-indexer/index/` subdirectory within the indexed repository. This keeps the index data organized separately from configuration files while remaining in the same .code-indexer structure.

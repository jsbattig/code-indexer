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
1. ✅ `cidx init --vector-store filesystem` creates filesystem backend configuration
2. ✅ Creates `.code-indexer/vectors/` directory structure
3. ✅ Generates configuration file without port allocations
4. ✅ Backend abstraction layer supports both Qdrant and filesystem backends
5. ✅ `cidx init --vector-store qdrant` continues to work as before (backward compatibility)

### Technical Requirements
1. ✅ VectorStoreBackend abstract interface defined with methods:
   - `initialize()`, `start()`, `stop()`, `get_status()`, `cleanup()`
   - `get_vector_store_client()`, `health_check()`, `get_service_info()`
2. ✅ FilesystemBackend implements VectorStoreBackend interface
3. ✅ QdrantContainerBackend wraps existing Docker/Qdrant functionality
4. ✅ VectorStoreBackendFactory creates appropriate backend from config
5. ✅ Configuration schema includes `vector_store.provider` field

### User Experience
1. Clear feedback during initialization showing filesystem backend selection
2. No port allocation or container checks for filesystem backend
3. Informative message showing vector storage location
4. Error messages if directory creation fails

## Manual Testing Steps

```bash
# Test 1: Initialize with filesystem backend
cd /tmp/test-project
git init
cidx init --vector-store filesystem

# Expected output:
# ✅ Filesystem backend initialized
# 📁 Vectors will be stored in .code-indexer/vectors/
# ✅ Project initialized

# Verify directory structure created
ls -la .code-indexer/
# Expected: vectors/ directory exists, no container ports in config

# Test 2: Verify configuration
cat .code-indexer/config.json
# Expected: "vector_store": {"provider": "filesystem", "path": ".code-indexer/vectors"}

# Test 3: Initialize with Qdrant (backward compatibility)
cd /tmp/test-project-qdrant
git init
cidx init --vector-store qdrant

# Expected: Traditional container-based initialization with port allocation

# Test 4: Default behavior (should remain Qdrant for backward compatibility)
cd /tmp/test-project-default
git init
cidx init

# Expected: Qdrant backend (existing behavior preserved)
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
        """Create .code-indexer/vectors/ directory."""
        self.base_path = Path(config.codebase_dir) / ".code-indexer" / "vectors"
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

### Configuration Schema Changes

```python
@dataclass
class VectorStoreConfig:
    provider: str = "qdrant"  # "qdrant" or "filesystem"
    filesystem_path: Optional[str] = ".code-indexer/vectors"
    depth_factor: int = 4  # From POC results
    reduced_dimensions: int = 64
    quantization_bits: int = 2
```

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

## Implementation Notes

**Critical Design Decision:** No port allocation for filesystem backend. The existing port registry code should be skipped entirely when `vector_store.provider == "filesystem"`.

**Backward Compatibility:** Default behavior remains Qdrant to ensure existing workflows continue working without changes.

**Directory Placement:** All vectors stored in `.code-indexer/vectors/` to keep alongside existing config files.

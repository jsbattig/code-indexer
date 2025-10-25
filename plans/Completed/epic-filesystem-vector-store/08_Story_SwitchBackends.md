# Story 8: Switch Between Qdrant and Filesystem Backends

**Story ID:** S08
**Epic:** Filesystem-Based Vector Database Backend
**Priority:** High
**Estimated Effort:** 2-3 days
**Implementation Order:** 9 (final story)

## User Story

**As a** developer evaluating different vector storage options
**I want to** switch between Qdrant and filesystem backends
**So that** I can choose the backend that best fits my workflow and constraints

**Conversation Reference:** "abstract the qdrant db provider behind an abstraction layer, and create a similar one for our new db, and drop it in based on a --flag on init commands" + "I don't want any migration tools, to use this new system, we will destroy, re-init and reindex" - User explicitly requested switchable backends with clean-slate approach.

## Acceptance Criteria

### Functional Requirements
1. ✅ Can switch from Qdrant to filesystem backend (destroy, reinit, reindex)
2. ✅ Can switch from filesystem to Qdrant backend (destroy, reinit, reindex)
3. ✅ Switching preserves codebase, only changes vector storage
4. ✅ Clear documentation of switching process
5. ✅ Warning messages about data loss during switch
6. ✅ No automatic migration tools (user decision to destroy/reindex)

### Technical Requirements
1. ✅ Clean removal of old backend data
2. ✅ Proper initialization of new backend
3. ✅ Configuration update to reflect new backend
4. ✅ No leftover artifacts from previous backend
5. ✅ Git history considerations for filesystem→Qdrant

### Safety Requirements
1. ✅ Explicit confirmation before destroying vector data
2. ✅ Clear messaging about data loss implications
3. ✅ Instructions for preserving old data if needed
4. ✅ No accidental backend mixing

## Manual Testing Steps

```bash
# Test 1: Switch from Qdrant to Filesystem
cd /path/to/qdrant-project
cidx status
# Expected: Shows Qdrant containers running

# Document current state
cidx status > /tmp/before_switch.txt

# Clean up Qdrant backend
cidx uninstall

# Expected output:
# ⚠️  This will remove ALL Qdrant data and containers
#    Collections: 2
#    Total Vectors: 1,247
# Are you sure? (y/N): y
# ✅ Removed Qdrant containers and data

# Reinitialize with filesystem backend
cidx init --vector-store filesystem

# Expected output:
# ✅ Filesystem backend initialized
# 📁 Vectors will be stored in .code-indexer/vectors/
# ✅ Project initialized

# Reindex
cidx index

# Expected: Fresh indexing to filesystem
# ⏳ Indexing files: [====>  ] 30/100 (30%)...
# ✅ Indexed 100 files, 523 vectors to filesystem

# Verify switch complete
cidx status
# Expected: Shows filesystem backend with fresh vectors

# Test 2: Switch from Filesystem to Qdrant
cd /path/to/filesystem-project
cidx status
# Expected: Shows filesystem backend

# Clean up filesystem backend
cidx uninstall

# Expected output:
# ⚠️  This will remove ALL filesystem vector data:
#    Collections: 1
#    Total Vectors: 523
#    Storage: 6.2 MB
# Are you sure? (y/N): y
# ✅ Removed filesystem vector storage
# 💡 Tip: Remove .code-indexer/vectors/ from git if no longer needed

# Note: User may want to commit removal
git rm -r .code-indexer/vectors/
git commit -m "Switch from filesystem to Qdrant backend"

# Reinitialize with Qdrant
cidx init --vector-store qdrant

# Expected: Traditional Qdrant setup
# ⏳ Pulling Qdrant image...
# ⏳ Setting up containers...
# ✅ Qdrant backend initialized

cidx start
cidx index

# Expected: Fresh indexing to Qdrant
# ✅ Indexed 100 files, 523 vectors to Qdrant

# Test 3: Preserve old data before switch
cd /path/to/project
# Create backup before switching
cp -r .code-indexer/vectors/ /tmp/vectors_backup_$(date +%Y%m%d)

# Then proceed with switch
cidx uninstall
cidx init --vector-store filesystem
# ...

# Test 4: Backend comparison workflow
cd /tmp/test-backends
git clone https://github.com/user/repo.git qdrant-test
git clone https://github.com/user/repo.git filesystem-test

# Setup Qdrant version
cd qdrant-test
cidx init --vector-store qdrant
time cidx index
cidx query "authentication" > /tmp/qdrant-results.txt

# Setup filesystem version
cd ../filesystem-test
cidx init --vector-store filesystem
time cidx index
cidx query "authentication" > /tmp/filesystem-results.txt

# Compare results
diff /tmp/qdrant-results.txt /tmp/filesystem-results.txt
# Expected: Semantic results may differ slightly due to quantization

# Test 5: Abort switch
cd /path/to/project
cidx uninstall
# Enter 'n' at confirmation
# Expected: Operation cancelled, backend unchanged

# Test 6: Switch with --force (scripted)
# For automation/CI scenarios
cidx uninstall --force  # No confirmation
cidx init --vector-store filesystem
cidx index
# Expected: Smooth automated switch
```

## Technical Implementation Details

### Backend Switching Workflow

```python
class BackendSwitcher:
    """Manage switching between vector storage backends."""

    def __init__(self, config_path: Path):
        self.config_path = config_path

    def switch_backend(
        self,
        current_backend: VectorStoreBackend,
        new_backend_type: str,
        preserve_config: bool = True
    ) -> Dict[str, Any]:
        """Switch from current backend to new backend type.

        Args:
            current_backend: Currently active backend
            new_backend_type: Target backend ("qdrant" or "filesystem")
            preserve_config: Keep non-backend config settings

        Returns:
            Switch operation result
        """
        # Step 1: Validate switch
        current_type = current_backend.get_status()["type"]

        if current_type == new_backend_type:
            return {
                "success": False,
                "error": f"Already using {new_backend_type} backend"
            }

        # Step 2: Get current state for reporting
        current_status = current_backend.get_status()

        # Step 3: Clean up current backend
        cleanup_result = current_backend.cleanup(remove_data=True)

        if not cleanup_result:
            return {
                "success": False,
                "error": "Failed to clean up current backend"
            }

        # Step 4: Update configuration
        self._update_backend_config(new_backend_type, preserve_config)

        # Step 5: Initialize new backend
        new_config = ConfigManager.load_from_file(self.config_path)
        new_backend = VectorStoreBackendFactory.create_backend(new_config)

        init_result = new_backend.initialize(new_config)

        if not init_result:
            return {
                "success": False,
                "error": "Failed to initialize new backend"
            }

        return {
            "success": True,
            "switched_from": current_type,
            "switched_to": new_backend_type,
            "old_backend_status": current_status,
            "requires_reindex": True
        }

    def _update_backend_config(
        self,
        new_backend_type: str,
        preserve_config: bool
    ):
        """Update configuration file with new backend."""
        config = ConfigManager.load_from_file(self.config_path)

        if preserve_config:
            # Keep existing settings, only change backend
            config.vector_store["provider"] = new_backend_type
        else:
            # Full reset to defaults for new backend
            config = self._create_default_config_for_backend(new_backend_type)

        ConfigManager.save_to_file(config, self.config_path)

    def _create_default_config_for_backend(
        self,
        backend_type: str
    ) -> Config:
        """Create default configuration for backend type."""
        if backend_type == "filesystem":
            return Config(
                vector_store={
                    "provider": "filesystem",
                    "path": ".code-indexer/vectors",
                    "depth_factor": 4,
                    "reduced_dimensions": 64,
                    "quantization_bits": 2
                }
            )
        elif backend_type == "qdrant":
            return Config(
                vector_store={
                    "provider": "qdrant",
                    "host": "http://localhost",
                    "port": self._allocate_port(),
                    "collection_base_name": "code_index"
                }
            )
        else:
            raise ValueError(f"Unknown backend type: {backend_type}")
```

### CLI Switch Command (Helper)

```python
@click.command()
@click.argument(
    "target_backend",
    type=click.Choice(["qdrant", "filesystem"])
)
@click.option("--force", is_flag=True, help="Skip confirmation prompts")
def switch_backend_command(target_backend: str, force: bool):
    """Switch vector storage backend (destroys existing data).

    This is a convenience command that wraps: uninstall → init → index
    """
    config = load_config()
    current_backend = VectorStoreBackendFactory.create_backend(config)
    current_type = current_backend.get_status()["type"]

    # Check if already using target backend
    if current_type == target_backend:
        console.print(f"Already using {target_backend} backend", style="yellow")
        return

    # Show impact
    console.print(f"🔄 Switching from {current_type} to {target_backend} backend", style="bold")
    console.print()
    console.print("⚠️  This process will:", style="yellow")
    console.print("   1. Destroy all existing vector data")
    console.print("   2. Reinitialize with new backend")
    console.print("   3. Require full reindexing")
    console.print()

    # Get current stats
    status = current_backend.get_status()
    if 'total_vectors' in status:
        console.print(f"Current data to be deleted:")
        console.print(f"   Vectors: {status['total_vectors']:,}")

        if 'storage_size' in status:
            console.print(f"   Storage: {format_bytes(status['storage_size'])}")

    console.print()

    # Confirmation
    if not force:
        console.print("💡 Tip: Create backup before switching if needed:", style="dim")
        console.print("   cp -r .code-indexer/ /tmp/backup_$(date +%Y%m%d)", style="dim")
        console.print()

        confirm = click.confirm("Proceed with backend switch?", default=False)
        if not confirm:
            console.print("Operation cancelled")
            return

    # Step 1: Uninstall current backend
    console.print(f"\n1️⃣ Removing {current_type} backend...")
    cleanup_result = current_backend.cleanup(remove_data=True)

    if not cleanup_result:
        console.print("❌ Failed to remove current backend", style="red")
        raise Exit(1)

    console.print(f"✅ Removed {current_type} backend")

    # Git tip for filesystem→qdrant switch
    if current_type == "filesystem":
        console.print()
        console.print("💡 Tip: Commit removal of filesystem vectors:", style="dim")
        console.print("   git rm -r .code-indexer/vectors/", style="dim")
        console.print("   git commit -m 'Switch to Qdrant backend'", style="dim")

    # Step 2: Initialize new backend
    console.print(f"\n2️⃣ Initializing {target_backend} backend...")

    # This would call existing init command
    ctx = click.get_current_context()
    ctx.invoke(init_command, vector_store=target_backend)

    # Step 3: Remind about reindexing
    console.print(f"\n3️⃣ Backend switch complete!", style="green")
    console.print()
    console.print("⚠️  Next step: Reindex your codebase", style="yellow")
    console.print("   cidx index")
    console.print()
    console.print("💡 You may also need to start services:", style="dim")

    if target_backend == "qdrant":
        console.print("   cidx start", style="dim")
```

### Documentation Helper

```python
def show_backend_comparison():
    """Display comparison table of backends for decision-making."""
    console.print("📊 Backend Comparison", style="bold")
    console.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Feature")
    table.add_column("Qdrant")
    table.add_column("Filesystem")

    table.add_row(
        "Container Required",
        "✅ Yes (Docker/Podman)",
        "❌ No"
    )
    table.add_row(
        "Git Trackable",
        "❌ No",
        "✅ Yes"
    )
    table.add_row(
        "Query Performance",
        "⚡ <100ms",
        "⚡ <1s (40K vectors)"
    )
    table.add_row(
        "RAM Overhead",
        "~200-500MB (per project)",
        "~50MB (during query only)"
    )
    table.add_row(
        "Setup Complexity",
        "Medium (containers, ports)",
        "Low (directory only)"
    )
    table.add_row(
        "Best For",
        "Production, multiple projects",
        "Laptops, container-free, git-tracked"
    )

    console.print(table)
    console.print()
    console.print("💡 Recommendation:", style="bold")
    console.print("   - Use Qdrant if: Running multiple projects, need fastest queries")
    console.print("   - Use Filesystem if: Container-restricted, want git-tracked indexes")


@click.command()
def backend_info_command():
    """Show information about available backends."""
    show_backend_comparison()

    console.print("\n🔄 Switching Backends", style="bold")
    console.print()
    console.print("To switch backends:")
    console.print("  1. cidx uninstall              # Remove current backend")
    console.print("  2. cidx init --vector-store X  # Initialize new backend")
    console.print("  3. cidx index                  # Reindex codebase")
    console.print()
    console.print("Or use convenience command:")
    console.print("  cidx switch-backend filesystem")
```

## Dependencies

### Internal Dependencies
- All previous stories (S01-S07)
- ConfigManager for configuration updates
- All backend implementations (Qdrant, Filesystem)

### External Dependencies
- None (uses existing CLI infrastructure)

## Unit Test Coverage Requirements

**Test Strategy:** Test backend switching workflow with real filesystem operations

**Test File:** `tests/unit/backends/test_backend_switching.py`

**Required Tests:**

```python
class TestBackendSwitching:
    """Test switching between Qdrant and Filesystem backends."""

    def test_switch_from_filesystem_to_qdrant(self, tmp_path):
        """GIVEN filesystem backend with indexed data
        WHEN switching to Qdrant backend
        THEN old filesystem data removed, Qdrant initialized"""
        # Start with filesystem
        config_fs = Config(vector_store={'provider': 'filesystem'})
        backend_fs = FilesystemBackend(config_fs)
        backend_fs.initialize(config_fs)

        store_fs = backend_fs.get_vector_store_client()
        store_fs.create_collection('test_coll', 1536)

        # Add vectors
        points = [
            {'id': f'vec_{i}', 'vector': np.random.randn(1536).tolist(),
             'payload': {'file_path': f'file_{i}.py'}}
            for i in range(10)
        ]
        store_fs.upsert_points('test_coll', points)

        # Verify filesystem data exists
        assert store_fs.count_points('test_coll') == 10

        # Switch to Qdrant (cleanup filesystem)
        backend_fs.cleanup(remove_data=True)

        # Verify filesystem data removed
        vectors_dir = tmp_path / ".code-indexer" / "vectors"
        assert not vectors_dir.exists()

        # Initialize Qdrant backend (mock containers for unit test)
        config_qd = Config(vector_store={'provider': 'qdrant'})
        backend_qd = QdrantContainerBackend(Mock(), config_qd)
        # (Full Qdrant test would require containers - test structure only)

    def test_switch_from_qdrant_to_filesystem(self, tmp_path):
        """GIVEN Qdrant backend
        WHEN switching to filesystem backend
        THEN containers cleaned up, filesystem initialized"""
        # Mock Qdrant backend
        mock_docker = Mock()
        config_qd = Config(vector_store={'provider': 'qdrant'})
        backend_qd = QdrantContainerBackend(mock_docker, config_qd)

        # Cleanup Qdrant
        backend_qd.cleanup(remove_data=True)
        mock_docker.cleanup.assert_called_once()

        # Initialize filesystem
        config_fs = Config(vector_store={'provider': 'filesystem'}, codebase_dir=tmp_path)
        backend_fs = FilesystemBackend(config_fs)
        result = backend_fs.initialize(config_fs)

        assert result is True
        assert (tmp_path / ".code-indexer" / "vectors").exists()

    def test_config_updated_reflects_new_backend(self, tmp_path):
        """GIVEN config file
        WHEN backend is switched
        THEN config file reflects new provider"""
        config_path = tmp_path / ".code-indexer" / "config.json"

        # Write initial config (filesystem)
        initial_config = {
            'vector_store': {'provider': 'filesystem'},
            'codebase_dir': str(tmp_path)
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(initial_config, f)

        # Load and verify
        with open(config_path) as f:
            loaded = json.load(f)
        assert loaded['vector_store']['provider'] == 'filesystem'

        # Update to Qdrant
        updated_config = {
            'vector_store': {'provider': 'qdrant'},
            'codebase_dir': str(tmp_path)
        }
        with open(config_path, 'w') as f:
            json.dump(updated_config, f)

        # Verify update
        with open(config_path) as f:
            loaded = json.load(f)
        assert loaded['vector_store']['provider'] == 'qdrant'

    def test_no_leftover_artifacts_after_switch(self, tmp_path):
        """GIVEN filesystem backend with data
        WHEN switching and cleaning up
        THEN no filesystem artifacts remain"""
        backend = FilesystemBackend(config)
        backend.initialize(config)

        store = backend.get_vector_store_client()
        store.create_collection('test_coll', 1536)

        # Add data
        points = [
            {'id': 'vec_1', 'vector': np.random.randn(1536).tolist(),
             'payload': {'file_path': 'file.py'}}
        ]
        store.upsert_points('test_coll', points)

        # Cleanup
        backend.cleanup(remove_data=True)

        # Verify complete removal
        vectors_dir = tmp_path / ".code-indexer" / "vectors"
        assert not vectors_dir.exists()

        # No JSON files left
        leftover_files = list(tmp_path.rglob('*.json'))
        vector_files = [f for f in leftover_files if 'vectors' in str(f)]
        assert len(vector_files) == 0
```

**Coverage Requirements:**
- ✅ Filesystem → Qdrant switching
- ✅ Qdrant → Filesystem switching
- ✅ Configuration updates
- ✅ Data cleanup verification
- ✅ No leftover artifacts

**Test Data:**
- Real filesystem for FilesystemBackend tests
- Mock DockerManager for QdrantBackend tests
- Configuration files with actual JSON

**Performance Assertions:**
- Backend switching workflow: <2s total
- Cleanup: <1s for 100 vectors

## Success Metrics

1. ✅ Can switch from Qdrant → Filesystem without errors
2. ✅ Can switch from Filesystem → Qdrant without errors
3. ✅ No leftover artifacts after switch
4. ✅ Configuration correctly updated
5. ✅ Users understand data loss implications
6. ✅ Git history considerations documented

## Non-Goals

- Automatic data migration between backends
- Preserving vectors during switch
- Incremental migration
- Dual backend operation
- Performance benchmarking automation

## Follow-Up Stories

- None (this is final story in epic)

## Implementation Notes

### Critical User Expectation

**Conversation Reference:** "I don't want any migration tools, to use this new system, we will destroy, re-init and reindex"

User explicitly **does not want** automatic migration. Switching = clean slate approach:
1. Destroy old backend data
2. Initialize new backend
3. Reindex from source code

This is simpler, more reliable, and matches user's stated preference.

### Why No Migration Tools?

Migration complexity:
- Different vector quantization (filesystem uses 2-bit, Qdrant uses 4-byte floats)
- Different storage formats (JSON vs Qdrant binary)
- Different path structures (quantized paths vs Qdrant IDs)
- Risk of corruption during migration

**Clean slate is safer and simpler.**

### Git History Considerations

**Filesystem → Qdrant:**
- `.code-indexer/vectors/` goes away (may be large)
- Recommend: `git rm -r .code-indexer/vectors/`
- Commit removal to clean git history

**Qdrant → Filesystem:**
- `.code-indexer/vectors/` appears (will be large)
- Consider: Add to `.gitignore` if don't want tracked
- Or: Commit to git for version control benefits

### Configuration Preservation

**Preserve non-backend settings:**
- Embedding provider
- Model selection
- Branch configuration
- File ignore patterns

**Reset backend-specific settings:**
- Ports (Qdrant only)
- Paths (Filesystem only)
- Quantization parameters (Filesystem only)

### Backend Decision Criteria

Help users choose by documenting:

**Choose Qdrant if:**
- Running many projects (shared containers)
- Need absolute fastest queries (<100ms)
- Have Docker/Podman available
- Production deployment

**Choose Filesystem if:**
- Laptop/personal development
- Container-restricted environment
- Want git-tracked vectors
- Single project focus
- Minimal infrastructure

### Rollback Strategy

If switch fails:
1. Old backend already cleaned (no automatic rollback)
2. User can manually restore from backup if created
3. Or: Reinitialize old backend and reindex

**Document backup strategy:**
```bash
# Before switching
cp -r .code-indexer/ /tmp/backup_$(date +%Y%m%d)

# If need to rollback
rm -rf .code-indexer/
cp -r /tmp/backup_YYYYMMDD/ .code-indexer/
```

### Testing Strategy

Test both directions:
- Qdrant → Filesystem
- Filesystem → Qdrant

Verify:
- Old backend completely removed
- New backend fully functional
- Configuration correct
- Reindexing works
- Queries return results

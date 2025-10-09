# Story: Auto-Discovery of Sub-Repositories

## Story ID: STORY-1.2
## Feature: FEAT-001 (Proxy Mode Initialization)
## Priority: P0 - Must Have
## Size: Medium

## User Story
**As a** developer initializing proxy mode
**I want to** automatically discover all indexed sub-repositories
**So that** I don't have to manually configure each repository path

## Conversation Context
**Citation**: "you discover then all subfolders with .code-indexer and list them in the config"

**Citation**: "Check for existence only."

**Citation**: "The only thing our proxy needs to know is the subfolder with config, that's it, don't copy ports or an other info."

**Citation**: "RElative path"

## Acceptance Criteria
- [ ] Discovery scans all subdirectories recursively from proxy root
- [ ] Identifies folders containing `.code-indexer/` directory
- [ ] Stores discovered paths as relative paths in configuration
- [ ] Discovery checks only for directory existence, not configuration validity
- [ ] Does NOT copy ports or other configuration details from sub-repositories
- [ ] Discovery runs automatically during `cidx init --proxy-mode` execution
- [ ] Configuration file updated with discovered repository list

## Technical Implementation

### 1. Repository Discovery Engine
```python
# proxy/repository_discovery.py
class RepositoryDiscovery:
    """Discover indexed sub-repositories within proxy root"""

    def __init__(self, proxy_root: Path):
        self.proxy_root = proxy_root
        self.proxy_config_dir = proxy_root / '.code-indexer'

    def discover_repositories(self) -> List[str]:
        """
        Scan subdirectories recursively for .code-indexer folders.
        Returns list of relative paths from proxy root.
        """
        discovered = []

        # Walk directory tree
        for path in self.proxy_root.rglob('.code-indexer'):
            # Skip the proxy's own config directory
            if path == self.proxy_config_dir:
                continue

            # Verify it's a directory (not a file)
            if not path.is_dir():
                continue

            # Calculate relative path from proxy root to repository
            repo_path = path.parent.relative_to(self.proxy_root)
            discovered.append(str(repo_path))

        # Sort for consistent ordering
        discovered.sort()
        return discovered
```

### 2. Existence-Only Validation
```python
def _is_valid_repository(self, config_dir: Path) -> bool:
    """
    Check if directory is a valid repository for proxy management.
    Only checks existence - no configuration validation.
    """
    # Existence check only - as per conversation
    return config_dir.exists() and config_dir.is_dir()
```

### 3. Relative Path Storage
```python
def _store_relative_path(self, absolute_path: Path) -> str:
    """
    Convert absolute path to relative path from proxy root.
    Ensures portability of proxy configuration.
    """
    try:
        relative = absolute_path.relative_to(self.proxy_root)
        return str(relative)
    except ValueError:
        # Path is not under proxy root - skip it
        logger.warning(f"Skipping path outside proxy root: {absolute_path}")
        return None
```

### 4. Integration with Proxy Initialization
```python
# proxy/proxy_initializer.py
class ProxyInitializer:
    def initialize(self) -> None:
        """Initialize proxy configuration with auto-discovery"""
        # Create configuration directory
        self.config_dir.mkdir(parents=True, exist_ok=False)

        # Auto-discover repositories
        discovery = RepositoryDiscovery(self.root_path)
        discovered_repos = discovery.discover_repositories()

        # Create configuration with discovered repositories
        config = {
            "proxy_mode": True,
            "discovered_repos": discovered_repos,
            "version": "1.0.0",
            "created_at": datetime.now().isoformat()
        }

        # Save configuration
        config_file = self.config_dir / 'config.json'
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

        logger.info(f"Discovered {len(discovered_repos)} repositories")
```

### 5. Discovery Output and Reporting
```python
def report_discovery(self, repositories: List[str]) -> None:
    """Report discovered repositories to user"""
    if not repositories:
        print("No indexed repositories found in subdirectories")
        return

    print(f"Discovered {len(repositories)} indexed repositories:")
    for repo in repositories:
        print(f"  - {repo}")
```

### 6. Symbolic Link Handling
```python
def discover_repositories(self) -> List[str]:
    """
    Discover repositories with symbolic link awareness.
    Follow symlinks but avoid circular references.
    """
    discovered = []
    visited = set()

    for path in self.proxy_root.rglob('.code-indexer'):
        # Resolve to handle symlinks
        try:
            resolved = path.resolve()

            # Skip if already visited (circular symlink protection)
            if resolved in visited:
                continue
            visited.add(resolved)

            # Skip proxy's own config
            if path == self.proxy_config_dir:
                continue

            # Only directories
            if not path.is_dir():
                continue

            # Store relative path from proxy root
            repo_path = path.parent.relative_to(self.proxy_root)
            discovered.append(str(repo_path))

        except (OSError, ValueError) as e:
            logger.warning(f"Skipping path {path}: {e}")
            continue

    discovered.sort()
    return discovered
```

## Testing Scenarios

### Unit Tests
1. **Test basic discovery**
   ```python
   def test_discover_single_repository():
       # Setup
       proxy_root = tmp_path / "proxy"
       proxy_root.mkdir()
       repo1 = proxy_root / "repo1" / ".code-indexer"
       repo1.mkdir(parents=True)

       # Execute
       discovery = RepositoryDiscovery(proxy_root)
       results = discovery.discover_repositories()

       # Verify
       assert results == ["repo1"]
   ```

2. **Test nested repository discovery**
   ```python
   def test_discover_nested_repositories():
       # Setup
       proxy_root = tmp_path / "proxy"
       (proxy_root / "services/auth/.code-indexer").mkdir(parents=True)
       (proxy_root / "services/user/.code-indexer").mkdir(parents=True)
       (proxy_root / "frontend/.code-indexer").mkdir(parents=True)

       # Execute
       discovery = RepositoryDiscovery(proxy_root)
       results = discovery.discover_repositories()

       # Verify
       assert results == [
           "frontend",
           "services/auth",
           "services/user"
       ]
   ```

3. **Test relative path storage**
   ```python
   def test_relative_path_storage():
       proxy_root = Path("/home/dev/projects")
       repo_path = Path("/home/dev/projects/backend/auth")

       expected = "backend/auth"
       result = _store_relative_path(repo_path, proxy_root)

       assert result == expected
   ```

4. **Test exclusion of proxy's own config**
   ```python
   def test_exclude_proxy_config():
       proxy_root = tmp_path / "proxy"
       proxy_root.mkdir()
       (proxy_root / ".code-indexer").mkdir()
       (proxy_root / "repo1/.code-indexer").mkdir(parents=True)

       discovery = RepositoryDiscovery(proxy_root)
       results = discovery.discover_repositories()

       # Should NOT include proxy's own .code-indexer
       assert results == ["repo1"]
   ```

### Integration Tests
1. **Test discovery with various structures**
   ```bash
   # Setup complex directory structure
   mkdir -p proxy-root/{backend,frontend,tests}/{service1,service2}

   # Create .code-indexer in some directories
   mkdir -p proxy-root/backend/service1/.code-indexer
   mkdir -p proxy-root/backend/service2/.code-indexer
   mkdir -p proxy-root/frontend/service1/.code-indexer

   # Initialize proxy
   cd proxy-root
   cidx init --proxy-mode

   # Verify configuration
   cat .code-indexer/config.json
   # Should list: backend/service1, backend/service2, frontend/service1
   ```

2. **Test discovery with symbolic links**
   - Create symlinked repositories
   - Verify symlinks are followed
   - Ensure no circular reference issues

3. **Test empty directory handling**
   ```python
   def test_discovery_no_repositories():
       proxy_root = tmp_path / "empty-proxy"
       proxy_root.mkdir()

       discovery = RepositoryDiscovery(proxy_root)
       results = discovery.discover_repositories()

       assert results == []
   ```

### Edge Cases
1. **Hidden directories**
   - Repositories in `.hidden` folders
   - Repositories named with leading dots

2. **Deep nesting**
   - Repositories at deep directory levels (10+ levels)
   - Performance with large directory trees

3. **Mixed content**
   - Directories with both `.code-indexer` files and directories
   - Invalid `.code-indexer` entries (files, broken symlinks)

## Error Handling

### Error Cases
1. **Permission Denied**
   - Behavior: Skip inaccessible directories, continue discovery
   - Logging: Warning level with path information
   - **No failure**: Continue with accessible repositories

2. **Circular Symlinks**
   - Behavior: Track visited paths, skip circular references
   - Logging: Debug level notification
   - **Graceful handling**: Prevent infinite loops

3. **Invalid Paths**
   - Behavior: Catch and log ValueError/OSError
   - Logging: Warning with specific error details
   - **Continue processing**: One bad path doesn't stop discovery

## Performance Considerations

### Optimization Strategies
1. **Efficient Directory Traversal**
   - Use `rglob()` with specific pattern: `.code-indexer`
   - Avoid full directory listing when possible
   - Early termination on excluded paths

2. **Large Directory Trees**
   - Stream results rather than collecting all first
   - Consider discovery timeout for extremely large trees
   - Report progress for long-running discoveries

3. **Caching**
   - Discovery runs once during initialization
   - Results cached in configuration file
   - No runtime performance impact

## Dependencies
- `pathlib.Path` for path operations
- `os.walk` or `Path.rglob()` for directory traversal
- `json` for configuration storage
- Logging framework for diagnostics

## Security Considerations
- Validate paths stay within proxy root
- Handle symbolic links safely
- Check permissions before access
- Prevent directory traversal attacks

## Documentation Updates
- Explain auto-discovery behavior in README
- Document relative path storage strategy
- Provide troubleshooting for missing repositories
- Include examples of expected directory structures

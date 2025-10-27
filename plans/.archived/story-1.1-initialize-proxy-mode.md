# Story: Initialize Proxy Mode

## Story ID: STORY-1.1
## Feature: FEAT-001 (Proxy Mode Initialization)
## Priority: P0 - Must Have
## Size: Medium

## User Story
**As a** developer working with multiple repositories
**I want to** initialize a parent directory as a proxy configuration
**So that** I can manage multiple indexed projects from a single location

## Conversation Context
**Citation**: "I was thinking we do 'init' --proxy-down to initialize it as a proxy folder. you create the .code-indexer folder, as we do with others, and you create the config file, as we do when running in server mode, but you configure it as a proxy"

## Acceptance Criteria
- [ ] Command `cidx init --proxy-mode` successfully creates proxy configuration
- [ ] `.code-indexer/` directory created at command execution location
- [ ] Configuration file contains `"proxy_mode": true` flag
- [ ] Configuration structure similar to server mode but with proxy-specific fields
- [ ] Command fails gracefully if directory already initialized
- [ ] Command prevents proxy creation within existing proxy directory
- [ ] Success message confirms proxy initialization

## Technical Implementation

### 1. Command Line Interface
```python
# cli.py modifications
@click.command()
@click.option('--proxy-mode', is_flag=True, help='Initialize as proxy for multiple repositories')
def init(proxy_mode: bool):
    """Initialize code indexer configuration"""
    if proxy_mode:
        return init_proxy_mode()
    else:
        return init_regular_mode()
```

### 2. Proxy Initialization Logic
```python
# proxy/proxy_initializer.py
class ProxyInitializer:
    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.config_dir = root_path / '.code-indexer'

    def initialize(self) -> None:
        """Initialize proxy configuration"""
        # Check for existing initialization
        if self.config_dir.exists():
            raise ProxyAlreadyInitializedError()

        # Check for parent proxy (prohibited)
        if self._is_under_proxy():
            raise NestedProxyError()

        # Create configuration directory
        self.config_dir.mkdir(parents=True, exist_ok=False)

        # Discover repositories
        repos = self._discover_repositories()

        # Create configuration
        config = self._create_proxy_config(repos)

        # Save configuration
        self._save_config(config)
```

### 3. Configuration Structure
```python
def _create_proxy_config(self, repositories: List[str]) -> dict:
    """Create proxy configuration structure"""
    return {
        "proxy_mode": True,
        "discovered_repos": repositories,
        "version": "1.0.0",
        "created_at": datetime.now().isoformat()
    }
```

### 4. Nested Proxy Detection
```python
def _is_under_proxy(self) -> bool:
    """Check if current directory is under proxy management"""
    current = self.root_path.parent
    while current != current.parent:
        config_file = current / '.code-indexer' / 'config.json'
        if config_file.exists():
            with open(config_file) as f:
                config = json.load(f)
                if config.get('proxy_mode', False):
                    return True
        current = current.parent
    return False
```

### 5. Repository Discovery
```python
def _discover_repositories(self) -> List[str]:
    """Discover all indexed sub-repositories"""
    repos = []
    for path in self.root_path.rglob('.code-indexer'):
        if path.is_dir() and path != self.config_dir:
            # Store relative path from proxy root
            relative_path = path.parent.relative_to(self.root_path)
            repos.append(str(relative_path))

    # Sort for consistent ordering
    repos.sort()
    return repos
```

**Citation**: "you discover then all subfolders with .code-indexer and list them in the config"

## Testing Scenarios

### Unit Tests
1. **Test proxy mode flag parsing**
   - Verify `--proxy-mode` flag correctly identified
   - Ensure flag absence leads to regular initialization

2. **Test configuration creation**
   - Verify correct JSON structure
   - Ensure `proxy_mode: true` present
   - Check repository list format

3. **Test nested proxy detection**
   - Create parent proxy, attempt child proxy (should fail)
   - Create regular repo under proxy (should succeed)

### Integration Tests
1. **Test full initialization workflow**
   ```bash
   mkdir test-proxy
   cd test-proxy
   mkdir -p repo1/.code-indexer
   mkdir -p repo2/.code-indexer
   cidx init --proxy-mode
   # Verify configuration created with both repos
   ```

2. **Test discovery with various structures**
   - Nested repositories (repo/subrepo)
   - Hidden directories (.repo)
   - Symbolic links

## Error Handling

### Error Cases
1. **Already Initialized**
   - Message: "Directory already initialized. Use --force to reinitialize."
   - Exit code: 1

2. **Nested Proxy Attempt**
   - Message: "Cannot create proxy within existing proxy directory at {parent_path}"
   - Exit code: 1
   - **Citation**: "Prohibit nesting for now."

3. **Permission Denied**
   - Message: "Permission denied creating configuration directory"
   - Exit code: 1

## Dependencies
- `PathLib` for path operations
- `json` for configuration serialization
- `click` for command-line interface
- Existing ConfigManager utilities

## Performance Considerations
- Repository discovery should handle large directory trees efficiently
- Use `rglob` with pattern matching vs manual traversal
- Cache discovery results during initialization

## Documentation Updates
- Update `--help` text for init command
- Add proxy mode section to README
- Include examples in user guide

## Rollback Plan
- If initialization fails, remove any created directories
- Ensure atomic operation (all or nothing)
- Clear error messages for troubleshooting
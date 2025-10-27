# Story: Proxy Configuration Management

## Story ID: STORY-1.3
## Feature: FEAT-001 (Proxy Mode Initialization)
## Priority: P0 - Must Have
## Size: Small

## User Story
**As a** developer using proxy mode
**I want to** view and edit the list of managed repositories
**So that** I can customize which projects are included in proxy operations

## Conversation Context
**Citation**: "you create the config file, as we do when running in server mode, but you configure it as a proxy"

**Citation**: "RElative path"

**Citation**: "The only thing our proxy needs to know is the subfolder with config, that's it, don't copy ports or an other info."

## Acceptance Criteria
- [ ] Configuration file is human-readable JSON format
- [ ] Repository list stored in `discovered_repos` array
- [ ] All paths stored as relative paths from proxy root
- [ ] Configuration file can be manually edited without breaking functionality
- [ ] Configuration changes take effect immediately on next command
- [ ] No port or service configuration copied from sub-repositories
- [ ] Configuration structure documented and clear

## Technical Implementation

### 1. Configuration File Structure
```python
# proxy/proxy_config.py
@dataclass
class ProxyConfig:
    """Proxy configuration data structure"""
    proxy_mode: bool
    discovered_repos: List[str]
    version: str
    created_at: str

    @classmethod
    def from_file(cls, config_path: Path) -> 'ProxyConfig':
        """Load configuration from JSON file"""
        with open(config_path, 'r') as f:
            data = json.load(f)

        return cls(
            proxy_mode=data.get('proxy_mode', False),
            discovered_repos=data.get('discovered_repos', []),
            version=data.get('version', '1.0.0'),
            created_at=data.get('created_at', '')
        )

    def to_file(self, config_path: Path) -> None:
        """Save configuration to JSON file with formatting"""
        config_data = {
            'proxy_mode': self.proxy_mode,
            'discovered_repos': self.discovered_repos,
            'version': self.version,
            'created_at': self.created_at
        }

        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
```

### 2. Example Configuration File
```json
{
  "proxy_mode": true,
  "discovered_repos": [
    "backend/auth-service",
    "backend/user-service",
    "frontend/web-app",
    "shared/common-lib"
  ],
  "version": "1.0.0",
  "created_at": "2025-10-08T10:30:00"
}
```

### 3. Configuration Loader with Validation
```python
# proxy/config_loader.py
class ProxyConfigLoader:
    """Load and validate proxy configuration"""

    def __init__(self, proxy_root: Path):
        self.proxy_root = proxy_root
        self.config_file = proxy_root / '.code-indexer' / 'config.json'

    def load(self) -> ProxyConfig:
        """Load configuration with validation"""
        if not self.config_file.exists():
            raise ProxyConfigNotFoundError(f"No proxy configuration at {self.proxy_root}")

        try:
            config = ProxyConfig.from_file(self.config_file)
            self._validate_config(config)
            return config
        except json.JSONDecodeError as e:
            raise ProxyConfigInvalidError(f"Invalid JSON in configuration: {e}")

    def _validate_config(self, config: ProxyConfig) -> None:
        """Validate configuration structure"""
        if not config.proxy_mode:
            raise ProxyConfigInvalidError("Configuration missing proxy_mode flag")

        if not isinstance(config.discovered_repos, list):
            raise ProxyConfigInvalidError("discovered_repos must be a list")

        # Validate all paths are relative
        for repo_path in config.discovered_repos:
            if Path(repo_path).is_absolute():
                raise ProxyConfigInvalidError(
                    f"Repository path must be relative: {repo_path}"
                )
```

### 4. Manual Edit Support
```python
def reload_configuration(self) -> ProxyConfig:
    """
    Reload configuration from disk.
    Supports manual edits to configuration file.
    """
    try:
        config = self.load()
        logger.info(f"Configuration reloaded with {len(config.discovered_repos)} repositories")
        return config
    except ProxyConfigInvalidError as e:
        logger.error(f"Configuration reload failed: {e}")
        raise
```

### 5. Configuration Update Operations
```python
class ProxyConfigManager:
    """Manage proxy configuration updates"""

    def add_repository(self, repo_path: str) -> None:
        """Add a repository to the configuration"""
        config = self.loader.load()

        # Ensure relative path
        if Path(repo_path).is_absolute():
            repo_path = str(Path(repo_path).relative_to(self.proxy_root))

        # Add if not already present
        if repo_path not in config.discovered_repos:
            config.discovered_repos.append(repo_path)
            config.discovered_repos.sort()
            config.to_file(self.config_file)

    def remove_repository(self, repo_path: str) -> None:
        """Remove a repository from the configuration"""
        config = self.loader.load()

        if repo_path in config.discovered_repos:
            config.discovered_repos.remove(repo_path)
            config.to_file(self.config_file)
```

### 6. Configuration Display
```python
def display_configuration(self) -> None:
    """Display current proxy configuration to user"""
    config = self.loader.load()

    print(f"Proxy Mode: {config.proxy_mode}")
    print(f"Configuration Version: {config.version}")
    print(f"Created: {config.created_at}")
    print(f"\nManaged Repositories ({len(config.discovered_repos)}):")

    if config.discovered_repos:
        for repo in config.discovered_repos:
            full_path = self.proxy_root / repo
            status = "✓" if (full_path / '.code-indexer').exists() else "✗"
            print(f"  {status} {repo}")
    else:
        print("  (no repositories configured)")
```

## Testing Scenarios

### Unit Tests
1. **Test configuration file creation**
   ```python
   def test_create_proxy_config():
       config = ProxyConfig(
           proxy_mode=True,
           discovered_repos=["repo1", "repo2"],
           version="1.0.0",
           created_at="2025-10-08T10:00:00"
       )

       config_file = tmp_path / "config.json"
       config.to_file(config_file)

       # Verify file created
       assert config_file.exists()

       # Verify JSON is valid and human-readable
       loaded = ProxyConfig.from_file(config_file)
       assert loaded.discovered_repos == ["repo1", "repo2"]
   ```

2. **Test relative path enforcement**
   ```python
   def test_reject_absolute_paths():
       config_data = {
           "proxy_mode": True,
           "discovered_repos": ["/absolute/path/repo"],
           "version": "1.0.0"
       }

       with pytest.raises(ProxyConfigInvalidError):
           loader._validate_config(ProxyConfig(**config_data))
   ```

3. **Test manual edit support**
   ```python
   def test_manual_config_edit():
       # Create initial config
       config = ProxyConfig(
           proxy_mode=True,
           discovered_repos=["repo1"],
           version="1.0.0",
           created_at="2025-10-08"
       )
       config.to_file(config_file)

       # Manually edit the file
       with open(config_file, 'r') as f:
           data = json.load(f)
       data['discovered_repos'].append("repo2")
       with open(config_file, 'w') as f:
           json.dump(data, f, indent=2)

       # Reload and verify
       loader = ProxyConfigLoader(proxy_root)
       reloaded = loader.load()
       assert reloaded.discovered_repos == ["repo1", "repo2"]
   ```

4. **Test configuration validation**
   ```python
   def test_validate_config_structure():
       # Missing proxy_mode
       invalid_config = {"discovered_repos": []}
       with pytest.raises(ProxyConfigInvalidError):
           loader._validate_config(ProxyConfig(**invalid_config))

       # Invalid repos type
       invalid_config = {"proxy_mode": True, "discovered_repos": "not-a-list"}
       with pytest.raises(ProxyConfigInvalidError):
           loader._validate_config(ProxyConfig(**invalid_config))
   ```

### Integration Tests
1. **Test end-to-end configuration workflow**
   ```bash
   # Initialize proxy
   cd test-proxy
   cidx init --proxy-mode

   # Verify configuration created
   cat .code-indexer/config.json

   # Manually edit configuration
   # Add "new-repo" to discovered_repos array

   # Run command to verify edit recognized
   cidx status
   # Should include new-repo in output
   ```

2. **Test configuration persistence**
   - Create configuration
   - Run multiple commands
   - Verify configuration remains consistent

3. **Test invalid configuration handling**
   - Manually corrupt JSON
   - Attempt to run command
   - Verify clear error message

### Edge Cases
1. **Empty repository list**
   ```json
   {
     "proxy_mode": true,
     "discovered_repos": [],
     "version": "1.0.0"
   }
   ```

2. **Very long repository list**
   - 100+ repositories
   - Test performance and formatting

3. **Special characters in paths**
   - Spaces, unicode, special chars
   - Ensure proper escaping

## Error Handling

### Error Cases
1. **Corrupted JSON**
   - Message: "Invalid JSON in configuration file: {error_detail}"
   - Exit code: 1
   - **Recovery**: User must fix JSON manually

2. **Missing Configuration**
   - Message: "No proxy configuration found at {path}"
   - Exit code: 1
   - **Action**: Suggest running `cidx init --proxy-mode`

3. **Invalid Structure**
   - Message: "Configuration file has invalid structure: {details}"
   - Exit code: 1
   - **Recovery**: Provide schema documentation

4. **Absolute Paths**
   - Message: "Repository paths must be relative: {absolute_path}"
   - Exit code: 1
   - **Action**: Convert to relative path or reject

## Performance Considerations
- Configuration loaded once per command execution
- JSON parsing is fast for reasonable file sizes
- No performance impact from manual edits
- Consider caching for long-running operations

## Dependencies
- `json` module for serialization
- `pathlib.Path` for path operations
- `dataclasses` for type safety
- Logging framework

## Security Considerations
- Validate JSON before parsing
- Reject absolute paths to prevent directory traversal
- Check file permissions before reading
- Sanitize user-provided repository paths

## Documentation Updates
- Document configuration file format
- Provide examples of manual edits
- Explain relative path requirement
- Include troubleshooting section for common issues

## Rollback Plan
- Configuration file is standalone JSON
- Easy to restore from backup
- No database migrations needed
- Manual edits can be undone by editing file

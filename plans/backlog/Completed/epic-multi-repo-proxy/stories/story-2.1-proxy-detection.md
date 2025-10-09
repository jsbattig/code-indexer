# Story: Automatic Proxy Mode Detection

## Story ID: STORY-2.1
## Feature: FEAT-002 (Command Forwarding Engine)
## Priority: P0 - Must Have
## Size: Small

## User Story
**As a** developer working in a proxy-managed directory
**I want to** have commands automatically detect proxy mode
**So that** I don't need special flags for every command

## Conversation Context
**Citation**: "Auto detect. In fact, you apply the same topmost .code-indexer folder found logic we use for other commands (as git). you will find our multi-repo folder, and use that one."

**Citation**: "Auto-detect proxy mode: If config has 'proxy_mode': true, activate proxying"

**Citation**: "No special flags needed: `cidx query 'auth'` automatically proxies if in/under proxy root"

## Acceptance Criteria
- [ ] Commands detect proxy mode without any special flags
- [ ] Detection walks up directory tree to find `.code-indexer/` config
- [ ] Proxy mode activates only when `"proxy_mode": true` found
- [ ] Regular mode continues when no proxy configuration exists
- [ ] Detection uses same upward search pattern as git
- [ ] Commands work from any subdirectory under proxy root

## Technical Implementation

### 1. Configuration Discovery Enhancement
```python
# config/config_manager.py modifications
class ConfigManager:
    @classmethod
    def detect_mode(cls, start_path: Path = None) -> Tuple[Path, str]:
        """
        Detect configuration mode (regular/proxy) by walking up directory tree.
        Returns: (config_path, mode)
        """
        current = Path(start_path or os.getcwd()).resolve()

        while current != current.parent:
            config_dir = current / '.code-indexer'
            config_file = config_dir / 'config.json'

            if config_file.exists():
                with open(config_file) as f:
                    config = json.load(f)

                if config.get('proxy_mode', False):
                    return current, 'proxy'
                else:
                    return current, 'regular'

            current = current.parent

        return None, None
```

### 2. Command Wrapper for Auto-Detection
```python
# cli/command_wrapper.py
class CommandWrapper:
    """Wraps commands to auto-detect and handle proxy mode"""

    def __init__(self, command_name: str):
        self.command_name = command_name

    def execute(self, *args, **kwargs):
        """Execute command with proxy detection"""
        config_path, mode = ConfigManager.detect_mode()

        if mode == 'proxy':
            return self._execute_proxy_mode(config_path, *args, **kwargs)
        else:
            return self._execute_regular_mode(*args, **kwargs)

    def _execute_proxy_mode(self, proxy_root: Path, *args, **kwargs):
        """Execute command in proxy mode"""
        if self.command_name not in PROXIED_COMMANDS:
            raise UnsupportedProxyCommandError(self.command_name)

        proxy_executor = ProxyCommandExecutor(proxy_root)
        return proxy_executor.execute(self.command_name, *args, **kwargs)

    def _execute_regular_mode(self, *args, **kwargs):
        """Execute command in regular mode"""
        # Original command execution
        return original_command_handlers[self.command_name](*args, **kwargs)
```

### 3. CLI Integration
```python
# cli.py modifications
@click.command()
@click.argument('query')
@click.option('--limit', default=10)
def query(query: str, limit: int):
    """Search indexed codebase"""
    wrapper = CommandWrapper('query')
    return wrapper.execute(query=query, limit=limit)

# Apply to all proxiable commands
for command in ['query', 'status', 'start', 'stop', 'uninstall', 'fix-config', 'watch']:
    # Wrap command with auto-detection
    cli.add_command(wrap_with_proxy_detection(command))
```

### 4. Upward Directory Search Logic
```python
def find_config_root(start_path: Path = None) -> Optional[Path]:
    """
    Find the topmost .code-indexer configuration directory.
    Mimics git's upward search behavior.
    """
    current = Path(start_path or os.getcwd()).resolve()
    config_root = None

    # Search upward for any .code-indexer directory
    while current != current.parent:
        config_dir = current / '.code-indexer'
        if config_dir.exists() and config_dir.is_dir():
            config_root = current
            # Continue searching for higher-level configs
            # (topmost wins, like git)

        current = current.parent

    return config_root
```

### 5. Mode Detection Cache
```python
class ModeDetectionCache:
    """Cache mode detection to avoid repeated file I/O"""

    def __init__(self):
        self._cache = {}
        self._cache_ttl = 5  # seconds

    def get_mode(self, path: Path) -> Tuple[Optional[Path], Optional[str]]:
        cache_key = str(path.resolve())

        if cache_key in self._cache:
            cached_time, result = self._cache[cache_key]
            if time.time() - cached_time < self._cache_ttl:
                return result

        # Perform detection
        result = ConfigManager.detect_mode(path)
        self._cache[cache_key] = (time.time(), result)
        return result
```

## Testing Scenarios

### Unit Tests
1. **Test upward directory traversal**
   - Create nested directory structure
   - Place config at various levels
   - Verify correct config found from different starting points

2. **Test proxy mode detection**
   - Config with `"proxy_mode": true` → proxy mode
   - Config without proxy_mode → regular mode
   - No config → None mode

3. **Test topmost config selection**
   - Multiple configs in hierarchy
   - Verify topmost is selected (like git)

### Integration Tests
1. **Test command execution from subdirectories**
   ```bash
   # Setup
   mkdir -p proxy-root/sub1/sub2
   cd proxy-root
   cidx init --proxy-mode

   # Test from various locations
   cd sub1/sub2
   cidx status  # Should detect proxy mode
   cidx query "test"  # Should execute in proxy mode
   ```

2. **Test mode switching**
   - Regular repo under proxy directory
   - Proxy commands from proxy root
   - Regular commands from regular repo

## Error Handling

### Error Cases
1. **No Configuration Found**
   - Behavior: Fall back to regular mode
   - Message: "No .code-indexer configuration found"

2. **Corrupted Configuration**
   - Behavior: Report error, don't execute
   - Message: "Invalid configuration at {path}: {error}"

3. **Permission Issues**
   - Behavior: Report error
   - Message: "Cannot read configuration: Permission denied"

## Performance Considerations
- Cache mode detection results for repeated commands
- Minimize file I/O during detection
- Use efficient path traversal algorithms
- Consider memoization for frequently accessed paths

## Dependencies
- `pathlib.Path` for path operations
- `json` for configuration parsing
- Existing ConfigManager infrastructure
- OS-level file system access

## Security Considerations
- Validate configuration files before parsing
- Handle symbolic links appropriately
- Check file permissions before reading
- Prevent directory traversal attacks

## Documentation Updates
- Document auto-detection behavior
- Explain precedence rules for nested configs
- Provide troubleshooting guide for detection issues
- Include examples of various directory structures
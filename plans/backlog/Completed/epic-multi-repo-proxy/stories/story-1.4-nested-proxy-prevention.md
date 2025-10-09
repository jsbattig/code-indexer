# Story: Nested Proxy Prevention

## Story ID: STORY-1.4
## Feature: FEAT-001 (Proxy Mode Initialization)
## Priority: P0 - Must Have
## Size: Small

## User Story
**As a** system administrator
**I want to** prevent creation of nested proxy configurations
**So that** the system maintains predictable behavior and avoids complexity

## Conversation Context
**Citation**: "Prohibit nesting for now."

**Citation**: "I was thinking we do 'init' --proxy-down to initialize it as a proxy folder. you create the .code-indexer folder, as we do with others, and you create the config file, as we do when running in server mode, but you configure it as a proxy"

**Citation**: "there may be legit reasons for this... like this folder! you may create a subfolder to test somethjing" (referring to regular init, NOT proxy init)

## Acceptance Criteria
- [x] `cidx init --proxy-mode` fails if executed within existing proxy directory
- [x] Initialization walks up directory tree to detect parent proxy configurations
- [x] Clear error message identifies the conflicting parent proxy location
- [x] Regular `cidx init` (without --proxy-mode) still allowed within proxy-managed folders
- [x] Nested proxy detection only applies to proxy initialization, not regular initialization
- [x] Detection uses same upward search pattern as other configuration discovery

## Technical Implementation

### 1. Nested Proxy Detection
```python
# proxy/nested_proxy_validator.py
class NestedProxyValidator:
    """Validate proxy initialization constraints"""

    def __init__(self, target_path: Path):
        self.target_path = target_path.resolve()

    def check_for_parent_proxy(self) -> Optional[Path]:
        """
        Walk up directory tree to find parent proxy configuration.
        Returns path to parent proxy if found, None otherwise.
        """
        current = self.target_path.parent

        while current != current.parent:
            config_file = current / '.code-indexer' / 'config.json'

            if config_file.exists():
                try:
                    with open(config_file, 'r') as f:
                        config = json.load(f)

                    # Check if this is a proxy configuration
                    if config.get('proxy_mode', False):
                        return current

                except (json.JSONDecodeError, IOError):
                    # Skip invalid/unreadable configs
                    pass

            current = current.parent

        return None

    def validate_proxy_initialization(self) -> None:
        """
        Validate that proxy can be initialized at target path.
        Raises NestedProxyError if parent proxy detected.
        """
        parent_proxy = self.check_for_parent_proxy()

        if parent_proxy:
            raise NestedProxyError(
                f"Cannot create proxy within existing proxy directory.\n"
                f"Parent proxy found at: {parent_proxy}\n"
                f"Nested proxy configurations are not supported."
            )
```

### 2. Integration with Proxy Initialization
```python
# proxy/proxy_initializer.py
class ProxyInitializer:
    def initialize(self) -> None:
        """Initialize proxy configuration with nesting validation"""
        # Check for existing initialization
        if self.config_dir.exists():
            raise ProxyAlreadyInitializedError(
                f"Directory already initialized at {self.root_path}"
            )

        # CRITICAL: Check for parent proxy (prohibit nesting)
        validator = NestedProxyValidator(self.root_path)
        validator.validate_proxy_initialization()

        # Proceed with initialization
        self.config_dir.mkdir(parents=True, exist_ok=False)

        # Auto-discover repositories
        discovery = RepositoryDiscovery(self.root_path)
        discovered_repos = discovery.discover_repositories()

        # Create configuration
        config = self._create_proxy_config(discovered_repos)
        self._save_config(config)
```

### 3. Regular Init Allowance
```python
# cli.py
@click.command()
@click.option('--proxy-mode', is_flag=True, help='Initialize as proxy for multiple repositories')
def init(proxy_mode: bool):
    """Initialize code indexer configuration"""
    if proxy_mode:
        # Proxy mode: enforce no nesting
        return init_proxy_mode()
    else:
        # Regular mode: allow nested repositories
        return init_regular_mode()

def init_proxy_mode():
    """Initialize in proxy mode with nesting validation"""
    initializer = ProxyInitializer(Path.cwd())

    try:
        initializer.initialize()
        click.echo("✓ Proxy configuration initialized successfully")
    except NestedProxyError as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)

def init_regular_mode():
    """Initialize in regular mode (no nesting restriction)"""
    # Regular initialization - no parent proxy check
    # Allows legitimate nested indexed folders
    initializer = RegularInitializer(Path.cwd())
    initializer.initialize()
```

### 4. Error Messages and Reporting
```python
class NestedProxyError(Exception):
    """Raised when attempting to create nested proxy configuration"""

    def __init__(self, parent_proxy_path: Path):
        self.parent_proxy_path = parent_proxy_path
        super().__init__(
            f"Cannot create proxy configuration.\n"
            f"A parent proxy already exists at: {parent_proxy_path}\n"
            f"\n"
            f"Nested proxy configurations are not supported.\n"
            f"Options:\n"
            f"  1. Initialize as regular repository (cidx init)\n"
            f"  2. Add this location to parent proxy configuration\n"
            f"  3. Initialize proxy in a different location\n"
        )
```

### 5. Upward Directory Search
```python
def find_parent_configs(start_path: Path) -> List[Tuple[Path, dict]]:
    """
    Find all parent .code-indexer configurations.
    Useful for debugging and understanding configuration hierarchy.
    """
    configs = []
    current = start_path.parent

    while current != current.parent:
        config_file = current / '.code-indexer' / 'config.json'

        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                configs.append((current, config))
            except:
                pass

        current = current.parent

    return configs
```

### 6. Validation Helper
```python
def is_under_proxy(path: Path) -> Tuple[bool, Optional[Path]]:
    """
    Check if path is under a proxy-managed directory.
    Returns (is_under_proxy, proxy_root_path)
    """
    validator = NestedProxyValidator(path)
    parent_proxy = validator.check_for_parent_proxy()

    if parent_proxy:
        return (True, parent_proxy)
    else:
        return (False, None)
```

## Testing Scenarios

### Unit Tests
1. **Test parent proxy detection**
   ```python
   def test_detect_parent_proxy():
       # Setup
       proxy_root = tmp_path / "proxy"
       proxy_root.mkdir()
       config_dir = proxy_root / ".code-indexer"
       config_dir.mkdir()

       config_file = config_dir / "config.json"
       with open(config_file, 'w') as f:
           json.dump({"proxy_mode": True}, f)

       # Test
       child_path = proxy_root / "subfolder" / "child"
       child_path.mkdir(parents=True)

       validator = NestedProxyValidator(child_path)
       parent = validator.check_for_parent_proxy()

       assert parent == proxy_root
   ```

2. **Test no parent proxy**
   ```python
   def test_no_parent_proxy():
       isolated_path = tmp_path / "isolated"
       isolated_path.mkdir()

       validator = NestedProxyValidator(isolated_path)
       parent = validator.check_for_parent_proxy()

       assert parent is None
   ```

3. **Test nested proxy prevention**
   ```python
   def test_prevent_nested_proxy():
       # Create parent proxy
       proxy_root = tmp_path / "proxy"
       proxy_root.mkdir()
       ProxyInitializer(proxy_root).initialize()

       # Attempt nested proxy
       child_path = proxy_root / "child"
       child_path.mkdir()

       with pytest.raises(NestedProxyError):
           ProxyInitializer(child_path).initialize()
   ```

4. **Test regular init still allowed**
   ```python
   def test_regular_init_under_proxy():
       # Create parent proxy
       proxy_root = tmp_path / "proxy"
       proxy_root.mkdir()
       ProxyInitializer(proxy_root).initialize()

       # Regular init in child (should succeed)
       child_path = proxy_root / "repo1"
       child_path.mkdir()

       # This should NOT raise NestedProxyError
       RegularInitializer(child_path).initialize()
       assert (child_path / ".code-indexer").exists()
   ```

### Integration Tests
1. **Test full nested proxy rejection workflow**
   ```bash
   # Create parent proxy
   mkdir parent-proxy
   cd parent-proxy
   cidx init --proxy-mode

   # Attempt nested proxy (should fail)
   mkdir child-proxy
   cd child-proxy
   cidx init --proxy-mode
   # Expected: Error message with parent proxy location

   # Regular init should still work
   mkdir regular-repo
   cd regular-repo
   cidx init
   # Expected: Success
   ```

2. **Test deep nesting detection**
   - Create proxy at level 0
   - Attempt proxy creation at level 5 deep
   - Verify detection works at any depth

3. **Test sibling proxy allowance**
   ```bash
   mkdir workspace
   cd workspace
   mkdir proxy1 proxy2

   cd proxy1
   cidx init --proxy-mode  # Should succeed

   cd ../proxy2
   cidx init --proxy-mode  # Should succeed (sibling, not nested)
   ```

### Edge Cases
1. **Symbolic links**
   - Parent proxy accessed via symlink
   - Verify detection works through symlinks

2. **Permission issues**
   - Unreadable parent configuration
   - Graceful handling of access errors

3. **Corrupted parent config**
   - Parent has `.code-indexer` but invalid JSON
   - Should skip and continue searching upward

## Error Handling

### Error Cases
1. **Nested Proxy Attempt**
   - Message: Clear explanation with parent proxy location
   - Exit code: 1
   - **Guidance**: Provide alternatives (regular init, add to parent, different location)

2. **Unreadable Parent Config**
   - Behavior: Log warning, skip that config, continue search
   - **No failure**: Corrupted config shouldn't block initialization

3. **Permission Denied Reading Parent**
   - Behavior: Log warning, skip directory
   - **Continue**: Don't fail initialization due to permission issues elsewhere

## Performance Considerations
- Directory traversal is bounded by filesystem depth
- Early termination when parent proxy found
- Cached during single initialization operation
- Minimal performance impact (one-time check)

## Dependencies
- `pathlib.Path` for path operations
- `json` for configuration parsing
- Existing exception hierarchy
- Logging framework

## Security Considerations
- Validate paths before reading
- Handle symlinks appropriately
- Check permissions before file access
- Prevent directory traversal attacks

## Documentation Updates
- Document nesting restriction clearly
- Explain rationale (avoid complexity)
- Provide examples of valid configurations
- Include troubleshooting for nesting errors
- Clarify regular init is still allowed

## Future Considerations
- May support nesting in future versions
- Current restriction simplifies implementation
- User feedback will guide future decisions
- Architecture supports enabling nesting later if needed

# Story 2.2: Repository Daemon Configuration

## Story Overview

**Story Points:** 3 (1 day)
**Priority:** HIGH
**Dependencies:** Story 2.1 (Daemon service must exist)
**Risk:** Low

**As a** CIDX user
**I want** to configure daemon mode per repository with simple commands
**So that** I can enable performance optimization without manual daemon management

## User Experience Design

### Configuration Flow

```bash
# Initial setup - user opts into daemon mode
$ cidx init --daemon
ℹ️ Initializing CIDX repository...
✓ Configuration created at .code-indexer/config.json
✓ Daemon mode enabled (60 minute cache TTL)
ℹ️ Daemon will auto-start on first query

# Check configuration
$ cidx config --show
Repository Configuration:
  Daemon Mode: Enabled
  Cache TTL: 60 minutes
  Socket Type: Unix
  Auto-start: Yes

# Modify configuration
$ cidx config --daemon-ttl 120
✓ Cache TTL updated to 120 minutes

# Disable daemon mode
$ cidx config --no-daemon
✓ Daemon mode disabled
ℹ️ Queries will run in standalone mode
```

## Technical Requirements

### Configuration Schema

```json
{
  "version": "2.0.0",
  "project": {
    "name": "my-project",
    "root": "/path/to/project"
  },
  "daemon": {
    "enabled": true,
    "ttl_minutes": 60,
    "socket_type": "unix",
    "socket_path": null,
    "tcp_port": null,
    "auto_start": true,
    "max_retries": 3,
    "retry_delay_ms": 100
  },
  "embedding": {
    "provider": "voyageai",
    "model": "voyage-code-2"
  }
}
```

### Configuration Management

```python
# config_manager.py (additions)
class ConfigManager:
    DAEMON_DEFAULTS = {
        "enabled": False,
        "ttl_minutes": 60,
        "socket_type": "unix",
        "socket_path": None,  # Auto-generated if None
        "tcp_port": None,      # Auto-assigned if None
        "auto_start": True,
        "max_retries": 3,
        "retry_delay_ms": 100
    }

    def enable_daemon(self, ttl_minutes=60):
        """Enable daemon mode for repository."""
        config = self.get_config()

        # Add daemon configuration
        config["daemon"] = {
            **self.DAEMON_DEFAULTS,
            "enabled": True,
            "ttl_minutes": ttl_minutes
        }

        # Auto-generate socket path if unix
        if config["daemon"]["socket_type"] == "unix":
            project_hash = self._get_project_hash()
            config["daemon"]["socket_path"] = (
                f"/tmp/cidx-daemon-{project_hash}.sock"
            )

        self.save_config(config)
        return config

    def disable_daemon(self):
        """Disable daemon mode."""
        config = self.get_config()
        config["daemon"]["enabled"] = False
        self.save_config(config)
        return config

    def update_daemon_ttl(self, ttl_minutes):
        """Update cache TTL."""
        config = self.get_config()
        if "daemon" not in config:
            raise ConfigError("Daemon not configured")

        config["daemon"]["ttl_minutes"] = ttl_minutes
        self.save_config(config)
        return config

    def get_daemon_config(self):
        """Get daemon configuration with defaults."""
        config = self.get_config()

        if "daemon" not in config:
            return {**self.DAEMON_DEFAULTS, "enabled": False}

        return {**self.DAEMON_DEFAULTS, **config.get("daemon", {})}

    def _get_project_hash(self):
        """Generate unique project hash for socket naming."""
        project_path = Path(self.config_path).parent.resolve()
        return hashlib.md5(str(project_path).encode()).hexdigest()[:8]
```

### CLI Integration

```python
# cli.py (additions)
@app.command()
def init(
    path: Path = Argument(Path.cwd()),
    daemon: bool = Option(False, "--daemon", help="Enable daemon mode"),
    daemon_ttl: int = Option(60, "--daemon-ttl", help="Cache TTL in minutes")
):
    """Initialize CIDX repository."""
    config_manager = ConfigManager(path)

    # Create base configuration
    config = config_manager.initialize()

    # Enable daemon if requested
    if daemon:
        config = config_manager.enable_daemon(ttl_minutes=daemon_ttl)
        console.print(f"✓ Daemon mode enabled ({daemon_ttl} minute cache TTL)")
        console.print("ℹ️ Daemon will auto-start on first query")
    else:
        console.print("ℹ️ Running in standalone mode (use --daemon to enable)")

    return config

@app.command()
def config(
    show: bool = Option(False, "--show", help="Show configuration"),
    daemon: Optional[bool] = Option(None, "--daemon/--no-daemon"),
    daemon_ttl: Optional[int] = Option(None, "--daemon-ttl"),
    socket_type: Optional[str] = Option(None, "--socket-type", help="unix or tcp")
):
    """Manage repository configuration."""
    config_manager = ConfigManager.create_with_backtrack()

    if show:
        config = config_manager.get_config()
        daemon_config = config.get("daemon", {})

        console.print("[bold]Repository Configuration:[/bold]")
        console.print(f"  Daemon Mode: {'Enabled' if daemon_config.get('enabled') else 'Disabled'}")

        if daemon_config.get("enabled"):
            console.print(f"  Cache TTL: {daemon_config.get('ttl_minutes', 60)} minutes")
            console.print(f"  Socket Type: {daemon_config.get('socket_type', 'unix')}")
            console.print(f"  Auto-start: {'Yes' if daemon_config.get('auto_start', True) else 'No'}")

        return

    # Handle configuration updates
    if daemon is not None:
        if daemon:
            config_manager.enable_daemon()
            console.print("✓ Daemon mode enabled")
        else:
            config_manager.disable_daemon()
            console.print("✓ Daemon mode disabled")

    if daemon_ttl is not None:
        config_manager.update_daemon_ttl(daemon_ttl)
        console.print(f"✓ Cache TTL updated to {daemon_ttl} minutes")

    if socket_type is not None:
        config_manager.update_daemon_socket_type(socket_type)
        console.print(f"✓ Socket type updated to {socket_type}")
```

### Runtime Configuration Detection

```python
# daemon_client.py
class DaemonClient:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.daemon_config = config_manager.get_daemon_config()

    def should_use_daemon(self) -> bool:
        """Determine if daemon should be used."""
        return self.daemon_config.get("enabled", False)

    def get_connection_params(self) -> Dict:
        """Get daemon connection parameters."""
        if self.daemon_config["socket_type"] == "unix":
            socket_path = self.daemon_config.get("socket_path")
            if not socket_path:
                # Auto-generate if not specified
                project_hash = self.config_manager._get_project_hash()
                socket_path = f"/tmp/cidx-daemon-{project_hash}.sock"

            return {
                "type": "unix",
                "path": socket_path
            }
        else:  # tcp
            port = self.daemon_config.get("tcp_port")
            if not port:
                # Auto-assign port based on project
                port = 9000 + (hash(str(self.config_manager.config_path)) % 1000)

            return {
                "type": "tcp",
                "host": "localhost",
                "port": port
            }

    def should_auto_start(self) -> bool:
        """Check if daemon should auto-start."""
        return self.daemon_config.get("auto_start", True)
```

## Acceptance Criteria

### Functional Requirements
- [ ] `cidx init --daemon` creates config with daemon enabled
- [ ] `cidx config --show` displays daemon configuration
- [ ] `cidx config --daemon-ttl N` updates cache TTL
- [ ] `cidx config --no-daemon` disables daemon mode
- [ ] Configuration persisted in .code-indexer/config.json
- [ ] Socket path auto-generated based on project
- [ ] Runtime detection of daemon configuration

### Configuration Validation
- [ ] TTL must be positive integer (1-10080 minutes)
- [ ] Socket type must be "unix" or "tcp"
- [ ] TCP port must be valid (1024-65535)
- [ ] Invalid config rejected with clear error

### Backward Compatibility
- [ ] Existing configs without daemon section work
- [ ] Default to standalone mode if not configured
- [ ] Version migration for old configs

## Implementation Tasks

### Task 1: Schema Definition (2 hours)
- [ ] Define daemon configuration schema
- [ ] Add to config version 2.0.0
- [ ] Document all fields

### Task 2: ConfigManager Updates (3 hours)
- [ ] Add daemon management methods
- [ ] Implement auto-generation logic
- [ ] Add validation methods

### Task 3: CLI Commands (2 hours)
- [ ] Update init command with --daemon
- [ ] Implement config command
- [ ] Add help documentation

### Task 4: Runtime Detection (1 hour)
- [ ] Create DaemonClient class
- [ ] Add configuration detection
- [ ] Implement connection params

### Task 5: Testing (2 hours)
- [ ] Unit tests for configuration
- [ ] CLI command tests
- [ ] Integration tests

## Testing Strategy

### Unit Tests

```python
def test_enable_daemon():
    """Test enabling daemon mode."""
    config_manager = ConfigManager(temp_dir)
    config = config_manager.enable_daemon(ttl_minutes=120)

    assert config["daemon"]["enabled"] is True
    assert config["daemon"]["ttl_minutes"] == 120
    assert config["daemon"]["socket_path"] is not None

def test_daemon_config_defaults():
    """Test default daemon configuration."""
    config_manager = ConfigManager(temp_dir)
    daemon_config = config_manager.get_daemon_config()

    assert daemon_config["enabled"] is False
    assert daemon_config["ttl_minutes"] == 60
    assert daemon_config["auto_start"] is True

def test_socket_path_generation():
    """Test unique socket path per project."""
    config1 = ConfigManager("/project1").enable_daemon()
    config2 = ConfigManager("/project2").enable_daemon()

    assert config1["daemon"]["socket_path"] != config2["daemon"]["socket_path"]
```

### CLI Tests

```python
def test_init_with_daemon():
    """Test cidx init --daemon."""
    result = runner.invoke(app, ["init", "--daemon", "--daemon-ttl", "120"])
    assert "Daemon mode enabled" in result.stdout
    assert "120 minute cache TTL" in result.stdout

def test_config_show():
    """Test cidx config --show."""
    runner.invoke(app, ["init", "--daemon"])
    result = runner.invoke(app, ["config", "--show"])

    assert "Daemon Mode: Enabled" in result.stdout
    assert "Cache TTL: 60 minutes" in result.stdout
```

### Integration Tests

```python
def test_daemon_detection():
    """Test runtime daemon detection."""
    # Setup with daemon
    config_manager = ConfigManager(temp_dir)
    config_manager.enable_daemon()

    # Check detection
    client = DaemonClient(config_manager)
    assert client.should_use_daemon() is True
    assert client.should_auto_start() is True

    # Disable and check again
    config_manager.disable_daemon()
    client = DaemonClient(config_manager)
    assert client.should_use_daemon() is False
```

## Manual Testing Checklist

- [ ] Run `cidx init --daemon` in new project
- [ ] Verify config.json contains daemon section
- [ ] Run `cidx config --show` and verify output
- [ ] Update TTL with `cidx config --daemon-ttl 120`
- [ ] Disable with `cidx config --no-daemon`
- [ ] Re-enable and verify persistence
- [ ] Test with multiple projects (different configs)

## Migration Strategy

### Version 1.x to 2.0 Migration

```python
def migrate_config_v1_to_v2(old_config: Dict) -> Dict:
    """Migrate version 1.x config to 2.0."""
    new_config = {
        "version": "2.0.0",
        "project": old_config.get("project", {}),
        "embedding": old_config.get("embedding", {}),
        "daemon": {
            "enabled": False,  # Disabled by default
            **ConfigManager.DAEMON_DEFAULTS
        }
    }

    # Preserve any custom settings
    for key, value in old_config.items():
        if key not in ["version", "project", "embedding"]:
            new_config[key] = value

    return new_config
```

## Documentation Updates

### README.md Addition

```markdown
## Daemon Mode (Performance Optimization)

CIDX supports a daemon mode that dramatically improves query performance by
caching indexes in memory and eliminating Python startup overhead.

### Enabling Daemon Mode

```bash
# Enable during initialization
cidx init --daemon

# Or enable for existing repository
cidx config --daemon

# Customize cache TTL (default 60 minutes)
cidx config --daemon-ttl 120
```

### Performance Impact

- Standalone mode: ~3.09s per query
- Daemon mode (cold): ~1.5s per query
- Daemon mode (warm): ~0.9s per query

The daemon starts automatically on the first query and runs in the background.
Cached indexes are kept in memory for the configured TTL period.
```

## Definition of Done

- [ ] Configuration schema defined and documented
- [ ] ConfigManager supports daemon configuration
- [ ] CLI commands implemented (init, config)
- [ ] Runtime detection working
- [ ] All tests passing
- [ ] Migration strategy implemented
- [ ] Documentation updated
- [ ] Code reviewed and approved

## References

**Conversation Context:**
- "`cidx init --daemon` stores config in .code-indexer/config.json"
- "Runtime daemon detection and configuration management"
- "Default 60-minute TTL (configurable per project)"
- "Automatic daemon startup on first query if configured"
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
✓ Daemon mode enabled (10 minute cache TTL)
ℹ️ Daemon will auto-start on first query

# Check configuration
$ cidx config --show
Repository Configuration:
  Daemon Mode: Enabled
  Cache TTL: 10 minutes
  Auto-start: Yes
  Auto-shutdown: Yes

# Modify configuration
$ cidx config --daemon-ttl 20
✓ Cache TTL updated to 20 minutes

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
    "ttl_minutes": 10,
    "auto_shutdown_on_idle": true,
    "max_retries": 4,
    "retry_delays_ms": [100, 500, 1000, 2000],
    "eviction_check_interval_seconds": 60
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
        "ttl_minutes": 10,
        "auto_shutdown_on_idle": True,
        "max_retries": 4,
        "retry_delays_ms": [100, 500, 1000, 2000],
        "eviction_check_interval_seconds": 60
    }

    def enable_daemon(self, ttl_minutes=10):
        """Enable daemon mode for repository."""
        config = self.get_config()

        # Add daemon configuration
        config["daemon"] = {
            **self.DAEMON_DEFAULTS,
            "enabled": True,
            "ttl_minutes": ttl_minutes
        }

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

    def get_socket_path(self) -> Path:
        """Calculate socket path from config location."""
        # Socket always lives at .code-indexer/daemon.sock
        return self.config_path.parent / "daemon.sock"
```

### CLI Integration

```python
# cli.py (additions)
@app.command()
def init(
    path: Path = Argument(Path.cwd()),
    daemon: bool = Option(False, "--daemon", help="Enable daemon mode"),
    daemon_ttl: int = Option(10, "--daemon-ttl", help="Cache TTL in minutes")
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
    auto_shutdown: Optional[bool] = Option(None, "--auto-shutdown/--no-auto-shutdown")
):
    """Manage repository configuration."""
    config_manager = ConfigManager.create_with_backtrack()

    if show:
        config = config_manager.get_config()
        daemon_config = config.get("daemon", {})

        console.print("[bold]Repository Configuration:[/bold]")
        console.print(f"  Daemon Mode: {'Enabled' if daemon_config.get('enabled') else 'Disabled'}")

        if daemon_config.get("enabled"):
            console.print(f"  Cache TTL: {daemon_config.get('ttl_minutes', 10)} minutes")
            console.print(f"  Auto-start: Yes")  # Always true
            console.print(f"  Auto-shutdown: {'Yes' if daemon_config.get('auto_shutdown_on_idle', True) else 'No'}")
            console.print(f"  Socket: .code-indexer/daemon.sock")

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

    if auto_shutdown is not None:
        config_manager.update_daemon_auto_shutdown(auto_shutdown)
        console.print(f"✓ Auto-shutdown {'enabled' if auto_shutdown else 'disabled'}")
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

    def get_socket_path(self) -> Path:
        """Get daemon socket path."""
        # Always at .code-indexer/daemon.sock
        return self.config_manager.get_socket_path()

    def get_retry_delays(self) -> List[float]:
        """Get retry delays in seconds."""
        delays_ms = self.daemon_config.get("retry_delays_ms", [100, 500, 1000, 2000])
        return [d / 1000.0 for d in delays_ms]

    def get_max_retries(self) -> int:
        """Get maximum retry attempts."""
        return self.daemon_config.get("max_retries", 4)

    def should_auto_shutdown(self) -> bool:
        """Check if daemon should auto-shutdown on idle."""
        return self.daemon_config.get("auto_shutdown_on_idle", True)
```

## Acceptance Criteria

### Functional Requirements
- [ ] `cidx init --daemon` creates config with daemon enabled
- [ ] `cidx config --show` displays daemon configuration
- [ ] `cidx config --daemon-ttl N` updates cache TTL
- [ ] `cidx config --no-daemon` disables daemon mode
- [ ] Configuration persisted in .code-indexer/config.json
- [ ] Socket path always at .code-indexer/daemon.sock
- [ ] Runtime detection of daemon configuration
- [ ] Retry delays configurable via array

### Configuration Validation
- [ ] TTL must be positive integer (1-1440 minutes)
- [ ] Retry delays must be positive integers
- [ ] Max retries must be 0-10
- [ ] Invalid config rejected with clear error

### Backward Compatibility
- [ ] Existing configs without daemon section work
- [ ] Default to standalone mode if not configured
- [ ] Version migration for old configs
- [ ] Old socket/tcp fields ignored if present

## Implementation Tasks

### Task 1: Schema Definition (2 hours)
- [ ] Define daemon configuration schema
- [ ] Remove deprecated fields (socket_type, socket_path, tcp_port)
- [ ] Add new fields (retry_delays_ms, eviction_check_interval_seconds)
- [ ] Document all fields

### Task 2: ConfigManager Updates (3 hours)
- [ ] Add daemon management methods
- [ ] Implement socket path calculation
- [ ] Add validation methods
- [ ] Update defaults (10 min TTL, exponential backoff)

### Task 3: CLI Commands (2 hours)
- [ ] Update init command with --daemon
- [ ] Implement config command
- [ ] Add auto-shutdown toggle
- [ ] Add help documentation

### Task 4: Runtime Detection (1 hour)
- [ ] Create DaemonClient class
- [ ] Add configuration detection
- [ ] Implement retry delay parsing
- [ ] Socket path resolution

### Task 5: Testing (2 hours)
- [ ] Unit tests for configuration
- [ ] CLI command tests
- [ ] Integration tests
- [ ] Migration tests

## Testing Strategy

### Unit Tests

```python
def test_enable_daemon():
    """Test enabling daemon mode."""
    config_manager = ConfigManager(temp_dir)
    config = config_manager.enable_daemon(ttl_minutes=20)

    assert config["daemon"]["enabled"] is True
    assert config["daemon"]["ttl_minutes"] == 20
    assert config["daemon"]["auto_shutdown_on_idle"] is True

def test_daemon_config_defaults():
    """Test default daemon configuration."""
    config_manager = ConfigManager(temp_dir)
    daemon_config = config_manager.get_daemon_config()

    assert daemon_config["enabled"] is False
    assert daemon_config["ttl_minutes"] == 10
    assert daemon_config["auto_shutdown_on_idle"] is True
    assert daemon_config["max_retries"] == 4
    assert daemon_config["retry_delays_ms"] == [100, 500, 1000, 2000]

def test_socket_path_calculation():
    """Test socket path is always at .code-indexer/daemon.sock."""
    config_manager = ConfigManager("/project")
    socket_path = config_manager.get_socket_path()

    assert socket_path == Path("/project/.code-indexer/daemon.sock")
```

### CLI Tests

```python
def test_init_with_daemon():
    """Test cidx init --daemon."""
    result = runner.invoke(app, ["init", "--daemon", "--daemon-ttl", "20"])
    assert "Daemon mode enabled" in result.stdout
    assert "20 minute cache TTL" in result.stdout

def test_config_show():
    """Test cidx config --show."""
    runner.invoke(app, ["init", "--daemon"])
    result = runner.invoke(app, ["config", "--show"])

    assert "Daemon Mode: Enabled" in result.stdout
    assert "Cache TTL: 10 minutes" in result.stdout
    assert "Socket: .code-indexer/daemon.sock" in result.stdout

def test_config_update_ttl():
    """Test updating TTL."""
    runner.invoke(app, ["init", "--daemon"])
    result = runner.invoke(app, ["config", "--daemon-ttl", "30"])

    assert "Cache TTL updated to 30 minutes" in result.stdout
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
    assert client.get_socket_path().name == "daemon.sock"

    # Disable and check again
    config_manager.disable_daemon()
    client = DaemonClient(config_manager)
    assert client.should_use_daemon() is False

def test_retry_delays():
    """Test retry delay configuration."""
    config_manager = ConfigManager(temp_dir)
    config_manager.enable_daemon()

    client = DaemonClient(config_manager)
    delays = client.get_retry_delays()

    assert delays == [0.1, 0.5, 1.0, 2.0]  # Converted to seconds
    assert client.get_max_retries() == 4
```

## Manual Testing Checklist

- [ ] Run `cidx init --daemon` in new project
- [ ] Verify config.json contains daemon section
- [ ] Check socket path is .code-indexer/daemon.sock
- [ ] Run `cidx config --show` and verify output
- [ ] Update TTL with `cidx config --daemon-ttl 20`
- [ ] Disable with `cidx config --no-daemon`
- [ ] Re-enable and verify persistence
- [ ] Test auto-shutdown toggle

## Migration Strategy

### Version 1.x to 2.0 Migration

```python
def migrate_config_v1_to_v2(old_config: Dict) -> Dict:
    """Migrate version 1.x config to 2.0."""
    new_config = {
        "version": "2.0.0",
        "project": old_config.get("project", {}),
        "embedding": old_config.get("embedding", {}),
        "daemon": ConfigManager.DAEMON_DEFAULTS.copy()
    }

    # If old config had daemon section, migrate it
    if "daemon" in old_config:
        old_daemon = old_config["daemon"]

        # Migrate enabled flag
        new_config["daemon"]["enabled"] = old_daemon.get("enabled", False)

        # Update TTL default from 60 to 10
        old_ttl = old_daemon.get("ttl_minutes", 60)
        new_config["daemon"]["ttl_minutes"] = 10 if old_ttl == 60 else old_ttl

        # Remove deprecated fields
        # socket_type, socket_path, tcp_port are no longer used

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

# Customize cache TTL (default 10 minutes)
cidx config --daemon-ttl 20

# Toggle auto-shutdown
cidx config --auto-shutdown
```

### Performance Impact

- Standalone mode: ~3.09s per query
- Daemon mode (cold): ~1.5s per query
- Daemon mode (warm): ~0.9s per query
- FTS queries: ~100ms (95% improvement)

The daemon starts automatically on the first query and runs in the background.
Each repository has its own daemon process with a socket at `.code-indexer/daemon.sock`.

### Configuration

```json
{
  "daemon": {
    "enabled": true,
    "ttl_minutes": 10,
    "auto_shutdown_on_idle": true,
    "max_retries": 4,
    "retry_delays_ms": [100, 500, 1000, 2000],
    "eviction_check_interval_seconds": 60
  }
}
```
```

## Definition of Done

- [ ] Configuration schema defined and documented
- [ ] ConfigManager supports daemon configuration
- [ ] CLI commands implemented (init, config)
- [ ] Runtime detection working
- [ ] Socket path calculation correct
- [ ] All tests passing
- [ ] Migration strategy implemented
- [ ] Documentation updated
- [ ] Code reviewed and approved

## References

**Conversation Context:**
- "Socket at .code-indexer/daemon.sock"
- "10-minute TTL default"
- "Auto-shutdown on idle"
- "Retry with exponential backoff [100, 500, 1000, 2000]ms"
- "60-second eviction check interval"
- "Remove socket_type, socket_path, tcp_port fields"
- "One daemon per repository"
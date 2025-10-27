# Story 2.3: Client Delegation with Async Import Warming

## Story Overview

**Story Points:** 5 (2 days)
**Priority:** HIGH
**Dependencies:** Stories 2.1, 2.2 (Daemon and config must exist)
**Risk:** Medium

**As a** CIDX user with daemon mode enabled
**I want** the CLI to automatically delegate to the daemon with minimal overhead
**So that** my queries start in 50ms instead of 1.86s without any manual intervention

## Technical Design

### Architecture Overview

```
User runs: cidx query "authentication"
           ▼
┌─────────────────────────────────────┐
│     Lightweight CLI Entry (~50ms)    │
│                                      │
│  1. Parse args (minimal imports)    │
│  2. Detect daemon config             │
│  3. Fork: Async import warming      │
│  4. Connect to daemon via RPyC      │
│  5. Delegate query                  │
│  6. Stream results back             │
└─────────────────────────────────────┘
           │
           ├─[If daemon available]──────► Daemon executes query
           │
           └─[If daemon unavailable]────► Fallback to standalone
                                           (with console message)
```

### Lightweight Client Implementation

```python
# cli_light.py - Minimal import footprint
import sys
import os
import time
from pathlib import Path
from typing import Optional

# Defer heavy imports
rich = None
typer = None
rpyc = None

def lazy_import_rich():
    """Import Rich only when needed."""
    global rich
    if rich is None:
        from rich.console import Console
        from rich.progress import Progress, SpinnerColumn, TextColumn
        rich = type('rich', (), {
            'Console': Console,
            'Progress': Progress,
            'SpinnerColumn': SpinnerColumn,
            'TextColumn': TextColumn
        })()
    return rich

class LightweightCLI:
    def __init__(self):
        self.start_time = time.perf_counter()
        self.daemon_client = None
        self.console = None  # Lazy load

    def query(self, query_text: str, **kwargs) -> int:
        """Execute query with daemon delegation."""
        # Step 1: Quick config check (no heavy imports)
        daemon_config = self._check_daemon_config()

        if daemon_config and daemon_config.get("enabled"):
            return self._query_via_daemon(query_text, daemon_config, **kwargs)
        else:
            return self._query_standalone(query_text, **kwargs)

    def _check_daemon_config(self) -> Optional[dict]:
        """Quick config check without full ConfigManager."""
        config_path = self._find_config_file()
        if not config_path:
            return None

        try:
            import json
            with open(config_path) as f:
                config = json.load(f)
                return config.get("daemon")
        except:
            return None

    def _find_config_file(self) -> Optional[Path]:
        """Walk up directory tree looking for .code-indexer/config.json."""
        current = Path.cwd()
        while current != current.parent:
            config_path = current / ".code-indexer" / "config.json"
            if config_path.exists():
                return config_path
            current = current.parent
        return None

    def _query_via_daemon(self, query: str, daemon_config: dict, **kwargs):
        """Delegate query to daemon with async import warming."""
        # Step 2: Start async import warming
        import threading

        imports_done = threading.Event()

        def warm_imports():
            """Load heavy imports in background."""
            global rich, typer
            lazy_import_rich()
            if typer is None:
                import typer as _typer
                typer = _typer
            imports_done.set()

        import_thread = threading.Thread(target=warm_imports, daemon=True)
        import_thread.start()

        # Step 3: Connect to daemon (parallel with imports)
        try:
            connection = self._connect_to_daemon(daemon_config)
        except Exception as e:
            # Fallback with message
            self._report_fallback(e)
            import_thread.join(timeout=1)  # Wait for imports
            return self._query_standalone(query, **kwargs)

        # Step 4: Execute query via daemon
        try:
            start_query = time.perf_counter()
            result = connection.root.query(
                project_path=Path.cwd(),
                query=query,
                limit=kwargs.get('limit', 10)
            )
            query_time = time.perf_counter() - start_query

            # Step 5: Display results (imports should be ready)
            imports_done.wait(timeout=1)
            self._display_results(result, query_time)

            connection.close()
            return 0

        except Exception as e:
            self._report_error(e)
            connection.close()
            return 1

    def _connect_to_daemon(self, daemon_config: dict):
        """Establish RPyC connection to daemon."""
        global rpyc
        if rpyc is None:
            import rpyc as _rpyc
            rpyc = _rpyc

        # Auto-start daemon if configured
        if daemon_config.get("auto_start", True):
            self._ensure_daemon_running(daemon_config)

        # Connect with retries
        max_retries = daemon_config.get("max_retries", 3)
        retry_delay = daemon_config.get("retry_delay_ms", 100) / 1000

        for attempt in range(max_retries):
            try:
                if daemon_config.get("socket_type") == "unix":
                    socket_path = daemon_config.get("socket_path")
                    return rpyc.connect_unix(socket_path)
                else:
                    port = daemon_config.get("tcp_port", 9876)
                    return rpyc.connect("localhost", port)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(retry_delay)

    def _ensure_daemon_running(self, daemon_config: dict):
        """Start daemon if not running."""
        pid_file = Path(f"/tmp/cidx-daemon-{self._get_project_hash()}.pid")

        # Check if daemon already running
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text())
                os.kill(pid, 0)  # Check if process exists
                return  # Daemon is running
            except (OSError, ValueError):
                # Stale PID file
                pid_file.unlink(missing_ok=True)

        # Start daemon in background
        import subprocess
        import sys

        daemon_cmd = [
            sys.executable, "-m", "code_indexer.daemon",
            "--config", str(self._find_config_file())
        ]

        # Start daemon process
        process = subprocess.Popen(
            daemon_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        # Write PID file
        pid_file.write_text(str(process.pid))

        # Give daemon time to start
        time.sleep(0.5)

    def _query_standalone(self, query: str, **kwargs):
        """Fallback to standalone execution."""
        # Import full CLI (expensive)
        from code_indexer.cli import app
        import typer

        # Execute via full CLI
        return typer.run(app, ["query", query])

    def _report_fallback(self, error: Exception):
        """Report fallback to console."""
        if not self.console:
            r = lazy_import_rich()
            self.console = r.Console(stderr=True)

        self.console.print(
            f"[yellow]ℹ️ Daemon unavailable, using standalone mode[/yellow]",
            f"[dim](Error: {error})[/dim]"
        )
        self.console.print(
            "[dim]Tip: Check daemon with 'cidx daemon status'[/dim]"
        )

    def _display_results(self, results: dict, query_time: float):
        """Display query results."""
        if not self.console:
            r = lazy_import_rich()
            self.console = r.Console()

        total_time = time.perf_counter() - self.start_time

        # Display timing
        self.console.print(
            f"[green]✓[/green] Query completed in {query_time:.3f}s "
            f"(total: {total_time:.3f}s)"
        )

        # Display results
        for i, result in enumerate(results.get("results", []), 1):
            self.console.print(f"{i}. {result['file']}:{result['line']}")
            self.console.print(f"   {result['content'][:100]}...")

    def _get_project_hash(self) -> str:
        """Get project hash for daemon identification."""
        import hashlib
        project_path = Path.cwd().resolve()
        return hashlib.md5(str(project_path).encode()).hexdigest()[:8]
```

### Graceful Fallback Mechanism

```python
# fallback_handler.py
class FallbackHandler:
    """Handle daemon failures gracefully."""

    def __init__(self, console):
        self.console = console
        self.fallback_count = 0

    def handle_connection_error(self, error: Exception) -> bool:
        """Handle daemon connection errors."""
        self.fallback_count += 1

        if isinstance(error, FileNotFoundError):
            # Socket doesn't exist
            self.console.print(
                "[yellow]Daemon not running, falling back to standalone mode[/yellow]"
            )
        elif isinstance(error, ConnectionRefusedError):
            # Daemon not accepting connections
            self.console.print(
                "[yellow]Daemon not responding, falling back to standalone mode[/yellow]"
            )
        elif isinstance(error, TimeoutError):
            # Connection timeout
            self.console.print(
                "[yellow]Daemon timeout, falling back to standalone mode[/yellow]"
            )
        else:
            # Unknown error
            self.console.print(
                f"[yellow]Daemon error: {error}, using standalone mode[/yellow]"
            )

        # Provide helpful tips on first fallback
        if self.fallback_count == 1:
            self.console.print(
                "[dim]Tip: Enable daemon with 'cidx config --daemon' for 3x faster queries[/dim]"
            )

        return True  # Continue with fallback

    def handle_query_error(self, error: Exception) -> bool:
        """Handle errors during daemon query execution."""
        if "cache" in str(error).lower():
            self.console.print(
                "[yellow]Cache error in daemon, retrying with fresh load[/yellow]"
            )
            return True

        # Other errors should propagate
        return False
```

## Acceptance Criteria

### Functional Requirements
- [ ] CLI detects daemon configuration automatically
- [ ] Daemon auto-starts if configured and not running
- [ ] Query delegated to daemon when available
- [ ] Fallback to standalone when daemon unavailable
- [ ] Console messages explain fallback reason
- [ ] Results displayed identically in both modes

### Performance Requirements
- [ ] Daemon mode startup: <50ms to first RPC call
- [ ] Import warming completes during RPC execution
- [ ] Total daemon query: <1.0s (warm cache)
- [ ] Fallback adds <100ms overhead

### Reliability Requirements
- [ ] Graceful handling of daemon crashes
- [ ] Clean fallback on connection failures
- [ ] No data loss during fallback
- [ ] Clear error messages for users

## Implementation Tasks

### Task 1: Lightweight CLI Entry (Day 1 Morning)
- [ ] Create minimal cli_light.py
- [ ] Implement lazy import pattern
- [ ] Add quick config detection
- [ ] Measure startup time

### Task 2: Daemon Connection (Day 1 Afternoon)
- [ ] Implement RPyC connection logic
- [ ] Add retry mechanism
- [ ] Handle socket types (unix/tcp)
- [ ] Test connection scenarios

### Task 3: Auto-start Logic (Day 1 Afternoon)
- [ ] Detect if daemon running (PID file)
- [ ] Start daemon subprocess if needed
- [ ] Handle startup race conditions
- [ ] Test auto-start behavior

### Task 4: Async Import Warming (Day 2 Morning)
- [ ] Implement background import thread
- [ ] Coordinate with RPC execution
- [ ] Ensure imports ready for display
- [ ] Measure time savings

### Task 5: Fallback Mechanism (Day 2 Afternoon)
- [ ] Implement graceful fallback
- [ ] Add console messaging
- [ ] Provide helpful tips
- [ ] Test fallback scenarios

## Testing Strategy

### Unit Tests

```python
def test_daemon_detection():
    """Test daemon configuration detection."""
    # Create config with daemon enabled
    config = {"daemon": {"enabled": True}}
    write_config(config)

    cli = LightweightCLI()
    daemon_config = cli._check_daemon_config()

    assert daemon_config["enabled"] is True

def test_auto_start():
    """Test daemon auto-start."""
    cli = LightweightCLI()
    daemon_config = {"auto_start": True, "socket_type": "unix"}

    # Ensure daemon not running
    kill_any_daemon()

    # Should start daemon
    cli._ensure_daemon_running(daemon_config)

    # Verify daemon started
    assert is_daemon_running()

def test_fallback_on_connection_error():
    """Test fallback when daemon unavailable."""
    cli = LightweightCLI()

    # Simulate connection failure
    with patch("rpyc.connect_unix") as mock_connect:
        mock_connect.side_effect = ConnectionRefusedError()

        result = cli.query("test query")

        # Should fallback to standalone
        assert result == 0  # Success via fallback
```

### Integration Tests

```python
def test_end_to_end_daemon_query():
    """Test complete daemon query flow."""
    # Setup daemon
    start_test_daemon()

    # Run query via CLI
    result = subprocess.run(
        ["cidx", "query", "authentication"],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0
    assert "Query completed in" in result.stdout
    assert result.stdout.count("ms") > 0  # Fast execution

def test_import_warming_timing():
    """Test that imports warm during RPC."""
    cli = LightweightCLI()

    # Measure with warming
    start = time.perf_counter()
    cli._query_via_daemon("test", {"enabled": True})
    warm_time = time.perf_counter() - start

    # Should be faster than serial import + query
    assert warm_time < 1.0  # Target: <1s total
```

### Performance Tests

```python
def benchmark_startup_time():
    """Measure CLI startup overhead."""
    times = []

    for _ in range(10):
        start = time.perf_counter()

        # Just import and check config
        cli = LightweightCLI()
        cli._check_daemon_config()

        times.append(time.perf_counter() - start)

    avg_time = sum(times) / len(times)
    print(f"Average startup: {avg_time*1000:.1f}ms")
    assert avg_time < 0.050  # <50ms target
```

## Manual Testing Checklist

- [ ] Enable daemon mode with `cidx config --daemon`
- [ ] Run first query - verify daemon auto-starts
- [ ] Run second query - verify uses running daemon
- [ ] Kill daemon process manually
- [ ] Run query - verify auto-restart
- [ ] Disable daemon with `cidx config --no-daemon`
- [ ] Run query - verify standalone execution
- [ ] Create network issues (firewall, etc)
- [ ] Verify graceful fallback with messages

## Error Scenarios

### Scenario 1: Daemon Not Running
- **Detection:** PID file missing or stale
- **Action:** Auto-start daemon
- **Fallback:** If start fails, use standalone

### Scenario 2: Connection Refused
- **Detection:** RPyC connection error
- **Action:** Retry with backoff
- **Fallback:** After retries, use standalone

### Scenario 3: Daemon Crash During Query
- **Detection:** RPyC exception during call
- **Action:** Log error, close connection
- **Fallback:** Complete query in standalone

### Scenario 4: Import Warming Timeout
- **Detection:** Import thread doesn't complete
- **Action:** Continue without some imports
- **Fallback:** Load remaining imports synchronously

## Definition of Done

- [ ] Lightweight CLI with minimal imports
- [ ] Daemon auto-detection and connection
- [ ] Auto-start functionality working
- [ ] Async import warming implemented
- [ ] Graceful fallback with messaging
- [ ] All tests passing
- [ ] Performance targets met (<50ms startup)
- [ ] Documentation updated
- [ ] Code reviewed and approved

## References

**Conversation Context:**
- "Lightweight CLI detects daemon mode, delegates via RPyC (~50ms)"
- "Rich imports in parallel during RPC wait (300ms saved)"
- "Graceful fallback with error messages"
- "Automatic daemon startup on first query"
- "Never fail query due to daemon issues"
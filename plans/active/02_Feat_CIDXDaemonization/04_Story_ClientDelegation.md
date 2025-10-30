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
│  4. Connect to daemon via socket    │
│  5. Delegate query                  │
│  6. Stream results back             │
└─────────────────────────────────────┘
           │
           ├─[If daemon available]──────► Daemon executes query
           │
           └─[If daemon unavailable]────► Crash recovery (2 attempts)
                                          └─► Fallback to standalone
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
        self.restart_attempts = 0

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

    def _get_socket_path(self, config_path: Path) -> Path:
        """Calculate socket path from config location."""
        return config_path.parent / "daemon.sock"

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

        # Step 3: Connect to daemon with crash recovery
        config_path = self._find_config_file()
        socket_path = self._get_socket_path(config_path)

        try:
            connection = self._connect_to_daemon(socket_path, daemon_config)
        except Exception as e:
            # Crash recovery: Try to restart daemon (2 attempts)
            if self.restart_attempts < 2:
                self.restart_attempts += 1
                self._report_crash_recovery(e, self.restart_attempts)

                # Cleanup stale socket and restart daemon
                self._cleanup_stale_socket(socket_path)
                self._start_daemon(config_path)
                time.sleep(0.5)  # Give daemon time to start

                # Retry connection
                return self._query_via_daemon(query, daemon_config, **kwargs)
            else:
                # Exhausted restart attempts, fallback
                self._report_fallback(e)
                import_thread.join(timeout=1)
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

    def _connect_to_daemon(self, socket_path: Path, daemon_config: dict):
        """Establish RPyC connection to daemon with exponential backoff."""
        global rpyc
        if rpyc is None:
            import rpyc as _rpyc
            rpyc = _rpyc

        # Auto-start daemon if not running
        if not socket_path.exists():
            self._ensure_daemon_running(socket_path.parent / "config.json")

        # Connect with exponential backoff
        retry_delays = daemon_config.get("retry_delays_ms", [100, 500, 1000, 2000])
        retry_delays = [d / 1000.0 for d in retry_delays]  # Convert to seconds

        for attempt, delay in enumerate(retry_delays):
            try:
                return rpyc.connect_unix(str(socket_path))
            except Exception as e:
                if attempt == len(retry_delays) - 1:
                    raise
                time.sleep(delay)

    def _ensure_daemon_running(self, config_path: Path):
        """Start daemon if not running (socket binding handles race)."""
        socket_path = config_path.parent / "daemon.sock"

        # Check if socket exists (daemon likely running)
        if socket_path.exists():
            # Try to connect to verify it's alive
            try:
                import socket
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(str(socket_path))
                sock.close()
                return  # Daemon is running
            except:
                # Socket exists but daemon not responding
                self._cleanup_stale_socket(socket_path)

        # Start daemon in background
        self._start_daemon(config_path)

    def _start_daemon(self, config_path: Path):
        """Start daemon process (socket binding prevents duplicates)."""
        import subprocess
        import sys

        daemon_cmd = [
            sys.executable, "-m", "code_indexer.daemon",
            "--config", str(config_path)
        ]

        # Start daemon process
        subprocess.Popen(
            daemon_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        # Give daemon time to bind socket
        time.sleep(0.5)

    def _cleanup_stale_socket(self, socket_path: Path):
        """Remove stale socket file."""
        try:
            socket_path.unlink()
        except:
            pass  # Socket might not exist

    def _query_standalone(self, query: str, **kwargs):
        """Fallback to standalone execution."""
        # Import full CLI (expensive)
        from code_indexer.cli import app
        import typer

        # Execute via full CLI
        return typer.run(app, ["query", query])

    def _report_crash_recovery(self, error: Exception, attempt: int):
        """Report crash recovery attempt."""
        if not self.console:
            r = lazy_import_rich()
            self.console = r.Console(stderr=True)

        self.console.print(
            f"[yellow]⚠️ Daemon crashed, attempting restart ({attempt}/2)[/yellow]",
            f"[dim](Error: {error})[/dim]"
        )

    def _report_fallback(self, error: Exception):
        """Report fallback to console."""
        if not self.console:
            r = lazy_import_rich()
            self.console = r.Console(stderr=True)

        self.console.print(
            f"[yellow]ℹ️ Daemon unavailable after 2 restart attempts, using standalone mode[/yellow]",
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
```

### FTS and Hybrid Query Support

```python
# cli_light.py (continued)
    def _query_fts_via_daemon(self, query: str, daemon_config: dict, **kwargs):
        """Delegate FTS query to daemon."""
        config_path = self._find_config_file()
        socket_path = self._get_socket_path(config_path)

        connection = self._connect_with_recovery(socket_path, daemon_config)

        try:
            result = connection.root.query_fts(
                project_path=str(Path.cwd()),
                query=query,
                **kwargs  # Pass all FTS parameters
            )
            self._display_results(result, time.perf_counter() - self.start_time)
            connection.close()
            return 0
        except Exception as e:
            self._report_error(e)
            connection.close()
            return 1

    def _query_hybrid_via_daemon(self, query: str, daemon_config: dict, **kwargs):
        """Delegate hybrid search to daemon."""
        config_path = self._find_config_file()
        socket_path = self._get_socket_path(config_path)

        connection = self._connect_with_recovery(socket_path, daemon_config)

        try:
            result = connection.root.query_hybrid(
                project_path=str(Path.cwd()),
                query=query,
                **kwargs
            )
            self._display_hybrid_results(result)
            connection.close()
            return 0
        except Exception as e:
            self._report_error(e)
            connection.close()
            return 1

    def _connect_with_recovery(self, socket_path: Path, daemon_config: dict):
        """Connect with crash recovery (2 restart attempts)."""
        for attempt in range(3):  # Initial + 2 restarts
            try:
                return self._connect_to_daemon(socket_path, daemon_config)
            except Exception as e:
                if attempt < 2:
                    self._report_crash_recovery(e, attempt + 1)
                    self._cleanup_stale_socket(socket_path)
                    self._start_daemon(socket_path.parent / "config.json")
                    time.sleep(0.5)
                else:
                    raise
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
- [ ] FTS queries delegated to daemon
- [ ] Hybrid queries delegated to daemon
- [ ] Crash recovery with 2 restart attempts
- [ ] Fallback to standalone after recovery exhausted
- [ ] Console messages explain fallback reason
- [ ] Results displayed identically in both modes
- [ ] Socket path calculated from config location

### Performance Requirements
- [ ] Daemon mode startup: <50ms to first RPC call
- [ ] Import warming completes during RPC execution
- [ ] Total daemon query: <1.0s (warm cache)
- [ ] FTS query: <100ms (warm cache)
- [ ] Fallback adds <100ms overhead
- [ ] Exponential backoff on retries

### Reliability Requirements
- [ ] Graceful handling of daemon crashes
- [ ] 2 automatic restart attempts
- [ ] Clean fallback on connection failures
- [ ] No data loss during fallback
- [ ] Clear error messages for users
- [ ] Stale socket cleanup

## Implementation Tasks

### Task 1: Lightweight CLI Entry (Day 1 Morning)
- [ ] Create minimal cli_light.py
- [ ] Implement lazy import pattern
- [ ] Add quick config detection
- [ ] Calculate socket path from config
- [ ] Measure startup time

### Task 2: Daemon Connection (Day 1 Afternoon)
- [ ] Implement RPyC Unix socket connection
- [ ] Add exponential backoff retry [100, 500, 1000, 2000]ms
- [ ] Handle socket at .code-indexer/daemon.sock
- [ ] Test connection scenarios
- [ ] Implement crash detection

### Task 3: Crash Recovery (Day 1 Afternoon)
- [ ] Detect daemon crashes
- [ ] Cleanup stale sockets
- [ ] Restart daemon (2 attempts max)
- [ ] Track restart attempts
- [ ] Test recovery scenarios

### Task 4: Async Import Warming (Day 2 Morning)
- [ ] Implement background import thread
- [ ] Coordinate with RPC execution
- [ ] Ensure imports ready for display
- [ ] Measure time savings

### Task 5: FTS/Hybrid Support (Day 2 Afternoon)
- [ ] Add FTS query delegation
- [ ] Add hybrid query delegation
- [ ] Route based on query type
- [ ] Test all query modes

## Testing Strategy

### Unit Tests

```python
def test_socket_path_calculation():
    """Test socket path from config location."""
    cli = LightweightCLI()
    config_path = Path("/project/.code-indexer/config.json")
    socket_path = cli._get_socket_path(config_path)

    assert socket_path == Path("/project/.code-indexer/daemon.sock")

def test_crash_recovery():
    """Test daemon crash recovery (2 attempts)."""
    cli = LightweightCLI()

    with patch.object(cli, "_connect_to_daemon") as mock_connect:
        # Simulate crashes then success
        mock_connect.side_effect = [
            ConnectionError("Daemon crashed"),
            ConnectionError("Still crashed"),
            Mock()  # Success on third attempt
        ]

        result = cli._connect_with_recovery(Path("/sock"), {})

        assert cli.restart_attempts == 2
        assert result is not None

def test_exponential_backoff():
    """Test retry with exponential backoff."""
    cli = LightweightCLI()
    daemon_config = {
        "retry_delays_ms": [100, 500, 1000, 2000]
    }

    with patch("rpyc.connect_unix") as mock_connect:
        mock_connect.side_effect = [
            ConnectionError(),
            ConnectionError(),
            ConnectionError(),
            Mock()  # Success on 4th attempt
        ]

        with patch("time.sleep") as mock_sleep:
            cli._connect_to_daemon(Path("/sock"), daemon_config)

            # Verify exponential backoff
            assert mock_sleep.call_count == 3
            assert mock_sleep.call_args_list[0][0][0] == 0.1
            assert mock_sleep.call_args_list[1][0][0] == 0.5
            assert mock_sleep.call_args_list[2][0][0] == 1.0
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

def test_crash_recovery_e2e():
    """Test crash recovery in real scenario."""
    # Start daemon
    daemon_pid = start_test_daemon()

    # Kill daemon to simulate crash
    os.kill(daemon_pid, 9)

    # Query should recover
    result = subprocess.run(
        ["cidx", "query", "test"],
        capture_output=True,
        text=True
    )

    assert "attempting restart (1/2)" in result.stderr
    assert result.returncode == 0

def test_fts_delegation():
    """Test FTS query delegation."""
    start_test_daemon()

    result = subprocess.run(
        ["cidx", "query", "function", "--fts"],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0
    # FTS queries should be very fast
    assert any(x in result.stdout for x in ["ms", "0.0", "0.1"])
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
- [ ] Check socket at .code-indexer/daemon.sock
- [ ] Run second query - verify uses running daemon
- [ ] Kill daemon process manually
- [ ] Run query - verify auto-restart (1/2)
- [ ] Kill daemon again
- [ ] Run query - verify auto-restart (2/2)
- [ ] Kill daemon third time
- [ ] Run query - verify fallback to standalone
- [ ] Test FTS query delegation
- [ ] Test hybrid query delegation

## Error Scenarios

### Scenario 1: Daemon Not Running
- **Detection:** Socket doesn't exist
- **Action:** Auto-start daemon
- **Fallback:** If start fails, use standalone

### Scenario 2: Connection Refused
- **Detection:** RPyC connection error
- **Action:** Exponential backoff retry
- **Fallback:** After 4 retries, restart daemon

### Scenario 3: Daemon Crash During Query
- **Detection:** RPyC exception during call
- **Action:** Restart daemon (up to 2 times)
- **Fallback:** After 2 restarts, use standalone

### Scenario 4: Stale Socket
- **Detection:** Socket exists but no daemon
- **Action:** Remove socket, start fresh daemon
- **Fallback:** If cleanup fails, use standalone

## Definition of Done

- [ ] Lightweight CLI with minimal imports
- [ ] Daemon auto-detection via config
- [ ] Socket path calculation from config
- [ ] Auto-start functionality working
- [ ] Crash recovery with 2 restart attempts
- [ ] Exponential backoff on retries
- [ ] FTS query delegation implemented
- [ ] Hybrid query delegation implemented
- [ ] Async import warming implemented
- [ ] Graceful fallback with messaging
- [ ] All tests passing
- [ ] Performance targets met (<50ms startup)
- [ ] Documentation updated
- [ ] Code reviewed and approved

## References

**Conversation Context:**
- "Socket at .code-indexer/daemon.sock"
- "Socket binding as atomic lock"
- "2 restart attempts before fallback"
- "Exponential backoff [100, 500, 1000, 2000]ms"
- "No PID files needed"
- "Multi-client concurrent support"
- "FTS query delegation"
- "Crash recovery mechanism"
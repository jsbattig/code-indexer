# Story 2.4: Progress Callbacks via RPyC for Indexing

## Story Overview

**Story Points:** 3 (1 day)
**Priority:** HIGH
**Dependencies:** Stories 2.1, 2.3 (Daemon and client must exist)
**Risk:** Low

**As a** CIDX user performing indexing operations
**I want** to see real-time progress in my terminal when indexing via daemon
**So that** I know the operation is progressing and not stuck

## Technical Challenge

### Problem Statement
When indexing runs in the daemon process:
- Progress happens in daemon's memory space
- Client terminal needs real-time updates
- Rich progress bar must render in client terminal
- RPyC must transparently route callbacks

### Solution Architecture

```
┌──────────────────────┐         ┌────────────────────────┐
│   Client Terminal    │  RPyC   │    Daemon Process      │
│                      │◄────────│                        │
│  Rich Progress Bar   │         │  SmartIndexer          │
│  ▓▓▓▓▓▓░░░░ 60%     │         │    ├─> Index files     │
│  600/1000 files      │         │    └─> Call callback   │
│  Current: foo.py     │         │         ▼              │
│                      │◄────────│  Callback(progress)    │
└──────────────────────┘         └────────────────────────┘
```

## Implementation Design

### Client-Side Progress Handler

```python
# cli_progress.py
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.console import Console
import rpyc

class ClientProgressHandler:
    """Handle progress updates from daemon."""

    def __init__(self, console: Console = None):
        self.console = console or Console()
        self.progress = None
        self.task_id = None

    def create_progress_callback(self):
        """Create callback that daemon will invoke."""
        # Create Rich progress bar
        self.progress = Progress(
            SpinnerColumn(),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            "•",
            TextColumn("[progress.description]{task.description}"),
            "•",
            TextColumn("{task.fields[status]}"),
            console=self.console,
            refresh_per_second=10
        )

        # Start progress context
        self.progress.start()
        self.task_id = self.progress.add_task(
            "Indexing", total=100, status="Starting..."
        )

        # Create callback function for daemon
        def progress_callback(current: int, total: int, file_path: str, info: str = ""):
            """Callback that daemon will call via RPyC."""
            if total == 0:
                # Info message (setup phase)
                self.progress.update(
                    self.task_id,
                    description=f"ℹ️ {info}",
                    status=""
                )
            else:
                # Progress update
                percentage = (current / total) * 100
                self.progress.update(
                    self.task_id,
                    completed=percentage,
                    description=f"{current}/{total} files",
                    status=info or file_path.name
                )

            # Check for completion
            if current == total and total > 0:
                self.complete()

        # Mark as RPyC callback
        return rpyc.async_(progress_callback)

    def complete(self):
        """Mark progress as complete."""
        if self.progress and self.task_id:
            self.progress.update(
                self.task_id,
                completed=100,
                description="Indexing complete",
                status="✓"
            )
            self.progress.stop()

    def error(self, error_msg: str):
        """Handle indexing error."""
        if self.progress and self.task_id:
            self.progress.update(
                self.task_id,
                description=f"[red]Error: {error_msg}[/red]",
                status="✗"
            )
            self.progress.stop()
```

### Daemon-Side Callback Integration

```python
# daemon_service.py (additions)
class CIDXDaemonService(rpyc.Service):

    def exposed_index(self, project_path, callback=None, force_reindex=False, **kwargs):
        """Perform indexing with optional progress callback."""
        project_path = Path(project_path).resolve()

        try:
            # Get or create cache entry
            with self.cache_lock:
                if str(project_path) not in self.cache:
                    self.cache[str(project_path)] = self.CacheEntry(project_path)
                entry = self.cache[str(project_path)]

            # Serialized indexing with write lock
            with entry.write_lock:
                # Create SmartIndexer
                config_manager = ConfigManager.create_with_backtrack(project_path)
                indexer = SmartIndexer(config_manager)

                # Wrap callback for safe RPC calls
                safe_callback = self._wrap_callback(callback) if callback else None

                # Perform indexing with callback
                stats = indexer.run_smart_indexing(
                    force_reindex=force_reindex,
                    progress_callback=safe_callback
                )

                # Invalidate cache after indexing
                entry.hnsw_index = None
                entry.id_mapping = None
                entry.last_accessed = datetime.now()

                return {
                    "status": "success",
                    "stats": stats,
                    "project": str(project_path)
                }

        except Exception as e:
            logger.error(f"Indexing failed: {e}")
            if callback:
                try:
                    callback(0, 0, "", info=f"Error: {e}")
                except:
                    pass  # Callback error shouldn't crash indexing
            raise

    def _wrap_callback(self, callback):
        """Wrap client callback for safe RPC calls."""
        def safe_callback(current, total, file_path, info=""):
            try:
                # Convert Path to string for RPC
                if isinstance(file_path, Path):
                    file_path = str(file_path)

                # Call client callback via RPC
                callback(current, total, file_path, info)

            except Exception as e:
                # Log but don't crash on callback errors
                logger.debug(f"Progress callback error: {e}")

        return safe_callback
```

### Client-Side Index Command

```python
# cli_light.py (additions)
class LightweightCLI:

    def index(self, force_reindex: bool = False, **kwargs) -> int:
        """Execute indexing with progress display."""
        # Check daemon config
        daemon_config = self._check_daemon_config()

        if daemon_config and daemon_config.get("enabled"):
            return self._index_via_daemon(force_reindex, daemon_config, **kwargs)
        else:
            return self._index_standalone(force_reindex, **kwargs)

    def _index_via_daemon(self, force_reindex: bool, daemon_config: dict, **kwargs):
        """Delegate indexing to daemon with progress streaming."""
        try:
            # Connect to daemon
            connection = self._connect_to_daemon(daemon_config)

            # Create progress handler
            progress_handler = ClientProgressHandler(self.console)
            callback = progress_handler.create_progress_callback()

            # Execute indexing with callback
            try:
                result = connection.root.index(
                    project_path=Path.cwd(),
                    callback=callback,
                    force_reindex=force_reindex
                )

                # Display results
                self.console.print(
                    f"[green]✓[/green] Indexed {result['stats']['files_processed']} files"
                )
                return 0

            except Exception as e:
                progress_handler.error(str(e))
                raise

            finally:
                connection.close()

        except Exception as e:
            self._report_fallback(e)
            return self._index_standalone(force_reindex, **kwargs)
```

### RPyC Configuration for Callbacks

```python
# daemon_launcher.py
import rpyc
from rpyc.utils.server import ThreadedServer

def start_daemon_server(config):
    """Start RPyC daemon with proper callback configuration."""

    # Configure for callback support
    config = {
        'allow_public_attrs': True,
        'allow_pickle': False,  # Security
        'allow_getattr': True,
        'allow_setattr': False,
        'allow_delattr': False,
        'allow_exposed_attrs': True,
        'allow_all_attrs': False,
        'instantiate_custom_exceptions': True,
        'import_custom_exceptions': True
    }

    # Create and start server
    server = ThreadedServer(
        CIDXDaemonService,
        port=config.get('port', 18861),
        protocol_config=config
    )

    server.start()
```

## Acceptance Criteria

### Functional Requirements
- [ ] Progress bar displays in client terminal during daemon indexing
- [ ] Real-time updates as files are processed
- [ ] Shows current file, count, percentage, and speed
- [ ] Info messages during setup phase displayed
- [ ] Error messages displayed on failure
- [ ] Progress completes cleanly on success

### Technical Requirements
- [ ] RPyC transparently routes callbacks
- [ ] No serialization errors with Path objects
- [ ] Callback errors don't crash indexing
- [ ] Progress updates at appropriate frequency
- [ ] Memory-efficient callback mechanism

### Visual Requirements
- [ ] Consistent with standalone progress display
- [ ] Smooth updates (no flickering)
- [ ] Clear status indicators
- [ ] Proper cleanup on completion/error

## Implementation Tasks

### Task 1: Client Progress Handler (2 hours)
- [ ] Create ClientProgressHandler class
- [ ] Implement Rich progress bar setup
- [ ] Add callback creation method
- [ ] Handle completion and errors

### Task 2: Daemon Callback Integration (2 hours)
- [ ] Update exposed_index method
- [ ] Add callback wrapping for safety
- [ ] Ensure Path→string conversion
- [ ] Handle callback errors gracefully

### Task 3: RPyC Configuration (1 hour)
- [ ] Configure for callback support
- [ ] Test async callback routing
- [ ] Verify no serialization issues

### Task 4: Client Index Command (2 hours)
- [ ] Add index command to lightweight CLI
- [ ] Integrate progress handler
- [ ] Handle daemon delegation
- [ ] Implement fallback

### Task 5: Testing (1 hour)
- [ ] Test progress display
- [ ] Verify callback routing
- [ ] Test error scenarios
- [ ] Performance validation

## Testing Strategy

### Unit Tests

```python
def test_progress_callback_creation():
    """Test progress callback creation."""
    handler = ClientProgressHandler()
    callback = handler.create_progress_callback()

    # Should be RPyC async callback
    assert hasattr(callback, '__call__')
    assert hasattr(callback, 'async_')

def test_callback_wrapping():
    """Test daemon callback wrapping."""
    service = CIDXDaemonService()

    called = []
    def mock_callback(c, t, f, i=""):
        called.append((c, t, f, i))

    wrapped = service._wrap_callback(mock_callback)
    wrapped(1, 10, Path("/test/file.py"), "Processing")

    assert called[0] == (1, 10, "/test/file.py", "Processing")

def test_callback_error_handling():
    """Test callback errors don't crash indexing."""
    service = CIDXDaemonService()

    def bad_callback(c, t, f, i=""):
        raise ValueError("Callback error")

    wrapped = service._wrap_callback(bad_callback)

    # Should not raise
    wrapped(1, 10, "/test/file.py", "Processing")
```

### Integration Tests

```python
def test_daemon_indexing_with_progress():
    """Test full indexing via daemon with progress."""
    # Start daemon
    daemon = start_test_daemon()

    # Create test project
    create_test_project()

    # Run indexing with progress capture
    output = subprocess.run(
        ["cidx", "index"],
        capture_output=True,
        text=True
    )

    # Verify progress displayed
    assert "Indexing" in output.stdout
    assert "%" in output.stdout
    assert "files" in output.stdout
    assert "✓" in output.stdout  # Completion

def test_progress_during_large_indexing():
    """Test progress updates during large operation."""
    # Create project with 1000 files
    create_large_test_project(1000)

    # Track progress updates
    updates = []

    def track_progress(c, t, f, i=""):
        updates.append((c, t))

    # Index with tracking
    daemon_index_with_callback(track_progress)

    # Should have multiple updates
    assert len(updates) > 10
    assert updates[-1][0] == updates[-1][1]  # Complete
```

### Manual Testing Script

```bash
#!/bin/bash
# test_progress.sh

# Create test project with many files
mkdir -p /tmp/test-progress
cd /tmp/test-progress
for i in {1..500}; do
    echo "test content $i" > "file_$i.py"
done

# Initialize with daemon
cidx init --daemon

# Run indexing and observe progress
echo "=== Indexing with daemon progress ==="
cidx index

# Verify progress displayed correctly
echo "Did you see:"
echo "  - Progress bar?"
echo "  - File count updates?"
echo "  - Percentage updates?"
echo "  - Current file names?"
echo "  - Completion message?"
```

## Edge Cases

### Case 1: Client Disconnect During Indexing
- **Issue:** Client terminates, callback becomes invalid
- **Solution:** Daemon catches callback errors, continues indexing
- **Test:** Kill client during indexing, verify daemon completes

### Case 2: Very Fast Indexing
- **Issue:** Progress completes before display starts
- **Solution:** Always show at least initial and final state
- **Test:** Index single file, verify clean display

### Case 3: Slow Network Connection
- **Issue:** Callback latency affects progress smoothness
- **Solution:** Async callbacks, don't block on display
- **Test:** Add network delay, verify indexing speed unaffected

### Case 4: Terminal Resize During Progress
- **Issue:** Progress bar layout breaks
- **Solution:** Rich handles resize events
- **Test:** Resize terminal during indexing

## Performance Considerations

### Callback Frequency
- Balance between smooth updates and overhead
- Default: Update every 10 files or 100ms
- Configurable via environment variable

### Memory Usage
- Callbacks should not accumulate state
- Each update replaces previous
- No buffering of progress history

### Network Overhead
- Minimal data per callback (~100 bytes)
- Async to prevent blocking
- Batch updates if needed

## Definition of Done

- [ ] Progress callbacks work via RPyC
- [ ] Real-time updates in client terminal
- [ ] Visual consistency with standalone mode
- [ ] All error scenarios handled
- [ ] No performance degradation
- [ ] All tests passing
- [ ] Documentation updated
- [ ] Code reviewed and approved

## References

**Conversation Context:**
- "Client creates Rich progress bar, passes callback to daemon"
- "RPyC transparently routes callback to client terminal"
- "Existing SmartIndexer callback pattern unchanged"
- "Progress streaming via RPyC callbacks"
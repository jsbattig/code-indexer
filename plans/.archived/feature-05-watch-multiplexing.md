# Feature: Watch Command Multiplexing

## Feature ID: FEAT-005
## Epic: EPIC-001 (Multi-Repository Proxy Configuration Support)
## Status: Specification
## Priority: P2 (Enhancement)

## Overview

Implement support for the `watch` command in proxy mode, spawning multiple parallel watch processes and multiplexing their output streams into a single unified stdout. Handle signal propagation to ensure clean termination of all child processes.

## User Stories

### Story 5.1: Parallel Watch Processes
**As a** developer monitoring multiple repositories
**I want to** run watch on all repositories simultaneously
**So that** I can see real-time changes across all projects

### Story 5.2: Unified Output Stream
**As a** developer viewing watch output
**I want to** see all repository changes in one terminal
**So that** I don't need multiple terminal windows

### Story 5.3: Clean Process Termination
**As a** developer stopping watch mode
**I want to** Ctrl-C to terminate all watch processes
**So that** I can cleanly exit without orphaned processes

### Story 5.4: Repository Identification
**As a** developer viewing multiplexed output
**I want to** clearly see which repository generated each message
**So that** I can understand where changes are occurring

## Technical Requirements

### Process Management
- Spawn watch subprocess for each repository
- Run all watch processes in parallel
- Maintain process handles for lifecycle management
- Track process states (running, terminated, failed)

### Output Multiplexing
- Capture stdout/stderr from each subprocess
- Interleave output into single stream
- Preserve output ordering within each repository
- Add repository prefixes to disambiguate sources

**Citation**: "multiple into single stdout."

### Signal Handling
- Intercept Ctrl-C (SIGINT) in parent process
- Propagate termination signal to all child processes
- Wait for clean shutdown of all processes
- Handle partial termination gracefully

**Citation**: "Ctrl-C propagates to all child processes"

### Output Format
```
[backend/auth-service] Watching for changes...
[backend/user-service] Watching for changes...
[frontend/web-app] Watching for changes...
[backend/auth-service] File changed: src/auth/login.py
[backend/auth-service] Re-indexing modified files...
[frontend/web-app] File changed: src/components/Login.vue
[backend/auth-service] Indexing complete (2 files)
[frontend/web-app] Re-indexing modified files...
```

## Acceptance Criteria

### Story 5.1: Parallel Execution
- [ ] Watch processes start simultaneously for all repositories
- [ ] Each repository runs its own watch instance
- [ ] Processes run independently without blocking
- [ ] Failed watch in one repo doesn't affect others

### Story 5.2: Output Multiplexing
- [ ] All watch output appears in single terminal
- [ ] Output is properly interleaved as it arrives
- [ ] No output is lost or corrupted
- [ ] Line buffering prevents partial line mixing

### Story 5.3: Signal Propagation
- [ ] Ctrl-C terminates all watch processes
- [ ] No orphaned processes remain after termination
- [ ] Clean shutdown message displayed
- [ ] Exit code reflects termination status

### Story 5.4: Output Clarity
- [ ] Each output line prefixed with repository identifier
- [ ] Prefixes are consistent and readable
- [ ] Color coding for different repositories (if terminal supports)
- [ ] Clear visual separation between repositories

## Implementation Notes

### Process Architecture
```python
class WatchMultiplexer:
    def __init__(self, repositories: List[str]):
        self.processes = {}
        self.output_queue = Queue()
        self.running = True

    def start_watch_processes(self):
        """Spawn watch process for each repository"""
        for repo in self.repositories:
            proc = subprocess.Popen(
                ['cidx', 'watch'],
                cwd=repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1  # Line buffered
            )
            self.processes[repo] = proc
            # Start output reader thread
            threading.Thread(
                target=self._read_output,
                args=(repo, proc)
            ).start()

    def _read_output(self, repo: str, process):
        """Read output from process and queue with prefix"""
        for line in process.stdout:
            if line:
                self.output_queue.put(f"[{repo}] {line}")
```

### Signal Handler Implementation
```python
def handle_interrupt(signum, frame):
    """Handle Ctrl-C by terminating all child processes"""
    print("\nStopping all watch processes...")
    for repo, proc in self.processes.items():
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()  # Force kill if graceful shutdown fails
    sys.exit(0)

signal.signal(signal.SIGINT, handle_interrupt)
```

### Output Streaming
- Use line-buffered I/O to prevent partial line mixing
- Queue-based collection from multiple threads
- Single writer thread to stdout
- Timestamp preservation for accurate ordering

## Dependencies
- Threading or asyncio for concurrent I/O
- Queue for thread-safe output collection
- Signal module for interrupt handling
- Subprocess module with proper pipe handling

## Testing Requirements

### Unit Tests
- Process spawning for multiple repositories
- Output queue management
- Signal handler registration
- Line prefix formatting

### Integration Tests
- Full watch multiplexing with real repositories
- Ctrl-C termination with process cleanup
- Output interleaving with concurrent changes
- Error handling for failed watch processes

### Stress Tests
- Large number of repositories (10+)
- High-frequency output from multiple sources
- Rapid start/stop cycles
- Network interruption handling

## Performance Considerations

### Resource Management
- Limit number of concurrent watch processes
- Monitor memory usage with many repositories
- Efficient queue processing for high output volume
- CPU usage optimization for idle watching

### Output Buffering
- Balance between responsiveness and efficiency
- Line buffering to prevent garbled output
- Queue size limits to prevent memory bloat
- Periodic queue flushing

## Error Handling

### Process Failures
- Individual watch failure doesn't stop others
- Clear error indication for failed repositories
- Attempt restart for transient failures
- Report which repositories are actively watching

### Output Issues
- Handle broken pipe gracefully
- Buffer overflow protection
- Unicode handling for international content
- Terminal compatibility checks

## User Experience

### Visual Design
- Clear repository identification
- Optional color coding for easier scanning
- Progress indicators for indexing operations
- Status summary line showing active watchers

### Interaction Model
- Single Ctrl-C stops everything
- Clear startup messages
- Shutdown confirmation
- Help text for watch mode features

## Example Usage

### Starting Watch Mode
```bash
$ cidx watch

Starting watch mode for 3 repositories...
[backend/auth-service] Watch started - monitoring for changes
[backend/user-service] Watch started - monitoring for changes
[frontend/web-app] Watch started - monitoring for changes

Press Ctrl-C to stop all watchers...
```

### During Operation
```bash
[backend/auth-service] Change detected: src/models/user.py
[backend/auth-service] Re-indexing 1 file...
[frontend/web-app] Change detected: src/api/auth.js
[frontend/web-app] Re-indexing 1 file...
[backend/auth-service] Indexing complete
[backend/user-service] Change detected: src/services/user_service.py
[frontend/web-app] Indexing complete
[backend/user-service] Re-indexing 1 file...
[backend/user-service] Indexing complete
```

### Termination
```bash
^C
Stopping all watch processes...
[backend/auth-service] Watch terminated
[backend/user-service] Watch terminated
[frontend/web-app] Watch terminated
All watchers stopped successfully.
```
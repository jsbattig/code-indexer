# Story: Clean Process Termination

## Story ID: STORY-5.3
## Feature: FEAT-005 (Watch Command Multiplexing)
## Priority: P2 - Enhancement
## Size: Small

## User Story
**As a** developer stopping watch mode
**I want to** Ctrl-C to terminate all watch processes
**So that** I can cleanly exit without orphaned processes

## Conversation Context
**Citation**: "Ctrl-C propagates to all child processes"

**Context**: The conversation specified that when the user presses Ctrl-C to stop watch mode, the termination signal must propagate to all child watch processes, ensuring clean shutdown without leaving orphaned processes running in the background.

## Acceptance Criteria
- [ ] Ctrl-C terminates all watch processes gracefully
- [ ] No orphaned processes remain after termination
- [ ] Clean shutdown message displayed to user
- [ ] Exit code reflects termination status (0 for clean shutdown)
- [ ] Signal propagation happens within 5 seconds
- [ ] Forced termination if graceful shutdown fails
- [ ] Final output queue is drained before exit

## Technical Implementation

### 1. Signal Handler for Ctrl-C
```python
# proxy/signal_handler.py
import signal
import sys
from typing import Dict
import subprocess

class WatchSignalHandler:
    """Handle Ctrl-C signal for watch multiplexing"""

    def __init__(self, processes: Dict[str, subprocess.Popen]):
        self.processes = processes
        self.terminating = False

    def setup_signal_handler(self):
        """Register signal handler for SIGINT (Ctrl-C)"""
        signal.signal(signal.SIGINT, self._handle_interrupt)

    def _handle_interrupt(self, signum, frame):
        """
        Handle Ctrl-C interrupt signal.

        Propagates termination to all child processes.
        """
        if self.terminating:
            # Already terminating, force exit
            print("\nForce terminating...")
            sys.exit(1)

        self.terminating = True
        print("\nStopping all watch processes...")

        # Terminate all child processes
        self._terminate_all_processes()

        # Clean exit
        sys.exit(0)

    def _terminate_all_processes(self):
        """Terminate all watch processes gracefully"""
        for repo, process in self.processes.items():
            try:
                # Send SIGTERM for graceful shutdown
                process.terminate()
            except Exception as e:
                print(f"Error terminating {repo}: {e}")

        # Wait for all processes to exit
        self._wait_for_termination(timeout=5.0)

    def _wait_for_termination(self, timeout: float):
        """
        Wait for all processes to terminate gracefully.

        If timeout expires, forcefully kill remaining processes.
        """
        import time
        start_time = time.time()

        for repo, process in self.processes.items():
            remaining_time = timeout - (time.time() - start_time)

            if remaining_time <= 0:
                # Timeout expired, kill forcefully
                self._force_kill_remaining()
                break

            try:
                process.wait(timeout=remaining_time)
                print(f"[{repo}] Watch terminated")
            except subprocess.TimeoutExpired:
                # Process didn't terminate gracefully
                process.kill()
                print(f"[{repo}] Watch forcefully killed")

    def _force_kill_remaining(self):
        """Forcefully kill any remaining processes"""
        for repo, process in self.processes.items():
            if process.poll() is None:
                # Process still running
                process.kill()
                print(f"[{repo}] Watch forcefully killed")
```

### 2. Orphan Process Prevention
```python
class OrphanPrevention:
    """Ensure no orphaned processes remain after termination"""

    def __init__(self, processes: Dict[str, subprocess.Popen]):
        self.processes = processes

    def ensure_clean_termination(self):
        """
        Ensure all processes are terminated and no orphans remain.

        Returns list of any processes that couldn't be terminated.
        """
        orphans = []

        for repo, process in self.processes.items():
            if not self._verify_termination(process):
                orphans.append(repo)

        if orphans:
            print(f"WARNING: Possible orphaned processes: {orphans}")

        return orphans

    def _verify_termination(self, process: subprocess.Popen) -> bool:
        """Verify that process has actually terminated"""
        # Check if process has exited
        return process.poll() is not None

    def kill_all_descendants(self, parent_pid: int):
        """
        Kill all descendant processes of parent.

        Ensures no child processes survive parent termination.
        """
        import psutil

        try:
            parent = psutil.Process(parent_pid)
            children = parent.children(recursive=True)

            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass

            # Wait for termination
            gone, alive = psutil.wait_procs(children, timeout=3)

            # Force kill any remaining
            for proc in alive:
                try:
                    proc.kill()
                except psutil.NoSuchProcess:
                    pass

        except psutil.NoSuchProcess:
            # Parent process already terminated
            pass
```

### 3. Graceful Shutdown Sequence
```python
class GracefulShutdown:
    """Manage graceful shutdown sequence"""

    def __init__(
        self,
        processes: Dict[str, subprocess.Popen],
        output_multiplexer
    ):
        self.processes = processes
        self.multiplexer = output_multiplexer

    def shutdown_sequence(self):
        """
        Execute graceful shutdown sequence.

        Steps:
        1. Signal all processes to terminate
        2. Stop output multiplexing
        3. Drain remaining output queue
        4. Wait for process termination
        5. Report final status
        """
        print("\nInitiating shutdown sequence...")

        # Step 1: Signal termination
        self._signal_termination()

        # Step 2: Stop multiplexing
        self.multiplexer.stop_multiplexing()

        # Step 3: Drain output queue
        self._drain_output_queue()

        # Step 4: Wait for termination
        terminated = self._wait_for_all_processes()

        # Step 5: Report status
        self._report_shutdown_status(terminated)

    def _signal_termination(self):
        """Send termination signal to all processes"""
        for process in self.processes.values():
            try:
                process.terminate()
            except Exception:
                pass

    def _drain_output_queue(self):
        """Drain any remaining output from queue"""
        import time
        timeout = time.time() + 2.0  # 2 second timeout

        while time.time() < timeout:
            if self.multiplexer.output_queue.empty():
                break
            time.sleep(0.1)

    def _wait_for_all_processes(self) -> List[str]:
        """Wait for all processes to terminate, return list of terminated"""
        terminated = []

        for repo, process in self.processes.items():
            try:
                process.wait(timeout=3.0)
                terminated.append(repo)
            except subprocess.TimeoutExpired:
                process.kill()
                terminated.append(repo)

        return terminated

    def _report_shutdown_status(self, terminated: List[str]):
        """Report final shutdown status"""
        print(f"\nShutdown complete: {len(terminated)} watchers stopped")
```

### 4. Exit Code Management
```python
class ExitCodeManager:
    """Manage exit codes for watch termination"""

    EXIT_CLEAN_SHUTDOWN = 0
    EXIT_FORCED_KILL = 1
    EXIT_PARTIAL_SHUTDOWN = 2

    def determine_exit_code(
        self,
        requested_shutdown: bool,
        all_terminated: bool,
        forced_kills: int
    ) -> int:
        """
        Determine appropriate exit code.

        Args:
            requested_shutdown: Was shutdown requested by user (Ctrl-C)?
            all_terminated: Did all processes terminate?
            forced_kills: Number of processes forcefully killed

        Returns:
            Appropriate exit code
        """
        if requested_shutdown and all_terminated and forced_kills == 0:
            # Clean user-requested shutdown
            return self.EXIT_CLEAN_SHUTDOWN

        if forced_kills > 0:
            # Some processes required force kill
            return self.EXIT_FORCED_KILL

        if not all_terminated:
            # Some processes didn't terminate
            return self.EXIT_PARTIAL_SHUTDOWN

        return self.EXIT_CLEAN_SHUTDOWN
```

### 5. Final Message Display
```python
class ShutdownMessageFormatter:
    """Format shutdown messages for user"""

    def format_shutdown_message(
        self,
        terminated_count: int,
        total_count: int,
        forced_count: int
    ) -> str:
        """
        Format final shutdown message.

        Shows:
        - How many processes terminated
        - How many required force kill
        - Overall status
        """
        lines = []

        if terminated_count == total_count and forced_count == 0:
            lines.append("✓ All watchers stopped successfully")
        elif terminated_count == total_count:
            lines.append(f"⚠ All watchers stopped ({forced_count} forcefully killed)")
        else:
            lines.append(f"⚠ Partial shutdown: {terminated_count}/{total_count} stopped")

        return '\n'.join(lines)
```

## Testing Scenarios

### Unit Tests
1. **Test signal handler registration**
   ```python
   handler = WatchSignalHandler({})
   handler.setup_signal_handler()
   # Verify SIGINT handler registered
   assert signal.getsignal(signal.SIGINT) == handler._handle_interrupt
   ```

2. **Test process termination**
   - Mock subprocess.Popen
   - Call terminate on all processes
   - Verify terminate() called on each
   - Check wait() called with timeout

3. **Test forced kill fallback**
   - Mock process that doesn't terminate
   - Simulate timeout on wait()
   - Verify kill() called after timeout

### Integration Tests
1. **Test Ctrl-C handling**
   ```bash
   # Start watch
   cidx watch &
   WATCH_PID=$!

   # Wait for startup
   sleep 2

   # Send SIGINT (Ctrl-C)
   kill -INT $WATCH_PID

   # Wait for termination
   wait $WATCH_PID
   EXIT_CODE=$?

   # Verify clean exit (code 0)
   assert [ $EXIT_CODE -eq 0 ]

   # Verify no orphaned processes
   ps aux | grep "cidx watch" | grep -v grep
   # Should return empty
   ```

2. **Test no orphans remain**
   - Start watch with multiple repos
   - Send SIGINT
   - Check process list for any cidx processes
   - Verify all watch processes terminated

## Error Handling

### Termination Failures
- Log processes that don't terminate
- Attempt force kill after timeout
- Report which processes required force kill
- Provide process IDs for manual cleanup

### Signal Handler Errors
- Catch exceptions in signal handler
- Don't crash on termination errors
- Log all termination attempts
- Ensure exit happens even with errors

## Performance Considerations

### Termination Speed
- 5-second timeout for graceful termination
- Immediate force kill after timeout
- Parallel process termination
- Quick signal propagation

### Resource Cleanup
- Close file handles properly
- Release system resources
- Clean up temporary files
- Remove locks and semaphores

## Dependencies
- `signal` for signal handling
- `subprocess` for process management
- `sys` for exit codes
- Optional `psutil` for orphan prevention

## Documentation Updates
- Document Ctrl-C behavior
- Explain graceful shutdown sequence
- Provide troubleshooting for stuck processes
- Include process cleanup verification

## Example Output

### Clean Shutdown
```bash
$ cidx watch

Starting watch mode for 3 repositories...
[backend/auth-service] Watch started
[backend/user-service] Watch started
[frontend/web-app] Watch started

Press Ctrl-C to stop all watchers...

[backend/auth-service] File changed: src/auth.py
^C
Stopping all watch processes...
[backend/auth-service] Watch terminated
[backend/user-service] Watch terminated
[frontend/web-app] Watch terminated

✓ All watchers stopped successfully
```

### Forced Termination
```bash
^C
Stopping all watch processes...
[backend/auth-service] Watch terminated
[backend/user-service] Watch forcefully killed
[frontend/web-app] Watch terminated

⚠ All watchers stopped (1 forcefully killed)
```

## User Experience Principles
- Immediate response to Ctrl-C
- Clear shutdown progress
- Final confirmation message
- No silent failures
- Clean system state after exit

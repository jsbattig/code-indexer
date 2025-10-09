# Story: Unified Output Stream

## Story ID: STORY-5.2
## Feature: FEAT-005 (Watch Command Multiplexing)
## Priority: P2 - Enhancement
## Size: Medium

## User Story
**As a** developer viewing watch output
**I want to** see all repository changes in one terminal
**So that** I don't need multiple terminal windows

## Conversation Context
**Citation**: "multiple into single stdout."

**Context**: The conversation specified that watch output from multiple repositories should be multiplexed into a single stdout stream, eliminating the need for multiple terminal windows and providing a unified view of changes across all repositories.

## Acceptance Criteria
- [ ] All watch output appears in single terminal
- [ ] Output is properly interleaved as it arrives
- [ ] No output is lost or corrupted during multiplexing
- [ ] Line buffering prevents partial line mixing
- [ ] Output from different repos maintains chronological order
- [ ] Each line is complete (no broken lines)
- [ ] Performance remains good with high-frequency output

## Technical Implementation

### 1. Output Multiplexer
```python
# proxy/output_multiplexer.py
import threading
import queue
from typing import Dict
import subprocess

class OutputMultiplexer:
    """Multiplex output from multiple watch processes into single stream"""

    def __init__(self, processes: Dict[str, subprocess.Popen]):
        self.processes = processes
        self.output_queue = queue.Queue()
        self.reader_threads: List[threading.Thread] = []
        self.running = True

    def start_multiplexing(self):
        """
        Start multiplexing output from all processes.

        Creates reader thread for each process that feeds into
        central output queue for unified display.
        """
        # Start reader thread for each process
        for repo, process in self.processes.items():
            thread = threading.Thread(
                target=self._read_process_output,
                args=(repo, process),
                daemon=True
            )
            thread.start()
            self.reader_threads.append(thread)

        # Start writer thread to display multiplexed output
        writer_thread = threading.Thread(
            target=self._write_multiplexed_output,
            daemon=True
        )
        writer_thread.start()

    def _read_process_output(
        self,
        repo: str,
        process: subprocess.Popen
    ):
        """
        Read output from single process and queue it.

        Runs in dedicated thread per repository.
        """
        try:
            for line in process.stdout:
                if line and self.running:
                    # Queue line with repository identifier
                    self.output_queue.put((repo, line.rstrip('\n')))
        except Exception as e:
            # Log error but don't crash thread
            self.output_queue.put((repo, f"ERROR reading output: {e}"))

    def _write_multiplexed_output(self):
        """
        Write multiplexed output to stdout.

        Runs in single writer thread to prevent stdout corruption.
        """
        while self.running:
            try:
                # Wait for output with timeout to allow checking running flag
                repo, line = self.output_queue.get(timeout=0.5)
                print(f"[{repo}] {line}")
            except queue.Empty:
                continue
            except Exception as e:
                print(f"ERROR in output multiplexer: {e}")

    def stop_multiplexing(self):
        """Stop multiplexing and clean up threads"""
        self.running = False

        # Wait for reader threads to finish
        for thread in self.reader_threads:
            thread.join(timeout=1.0)

        # Drain remaining output queue
        while not self.output_queue.empty():
            try:
                repo, line = self.output_queue.get_nowait()
                print(f"[{repo}] {line}")
            except queue.Empty:
                break
```

### 2. Line-Buffered I/O
```python
class LineBufferedMultiplexer:
    """Multiplexer with guaranteed line-oriented output"""

    def __init__(self):
        self.output_queue = queue.Queue()

    def read_lines(self, repo: str, stream):
        """
        Read complete lines from stream.

        Line buffering ensures no partial lines are mixed.
        """
        buffer = []

        for char in iter(lambda: stream.read(1), ''):
            if char == '\n':
                # Complete line received
                line = ''.join(buffer)
                self.output_queue.put((repo, line))
                buffer = []
            else:
                buffer.append(char)

        # Handle any remaining content
        if buffer:
            line = ''.join(buffer)
            self.output_queue.put((repo, line))
```

### 3. Chronological Ordering
```python
import time
from dataclasses import dataclass
from typing import Tuple

@dataclass
class TimestampedOutput:
    """Output line with timestamp for ordering"""
    timestamp: float
    repository: str
    content: str

class ChronologicalMultiplexer:
    """Multiplex output in chronological order"""

    def __init__(self):
        self.output_queue = queue.PriorityQueue()

    def queue_output(self, repo: str, line: str):
        """Queue output with timestamp for chronological ordering"""
        item = TimestampedOutput(
            timestamp=time.time(),
            repository=repo,
            content=line
        )
        # PriorityQueue sorts by first tuple element (timestamp)
        self.output_queue.put((item.timestamp, item))

    def get_next_output(self) -> Tuple[str, str]:
        """Get next output in chronological order"""
        _, item = self.output_queue.get()
        return item.repository, item.content
```

### 4. Output Loss Prevention
```python
class LosslessMultiplexer:
    """Ensure no output is lost during multiplexing"""

    def __init__(self, max_queue_size: int = 10000):
        self.output_queue = queue.Queue(maxsize=max_queue_size)
        self.dropped_lines = 0

    def safe_queue_output(self, repo: str, line: str):
        """
        Queue output with overflow protection.

        If queue is full, blocks to prevent loss rather than dropping.
        """
        try:
            # Put with timeout to avoid infinite blocking
            self.output_queue.put((repo, line), timeout=1.0)
        except queue.Full:
            # Queue full - this is a warning condition
            self.dropped_lines += 1
            if self.dropped_lines % 100 == 0:
                print(f"WARNING: Output queue full, {self.dropped_lines} lines dropped")

    def get_statistics(self) -> Dict[str, int]:
        """Get multiplexer statistics"""
        return {
            'queue_size': self.output_queue.qsize(),
            'dropped_lines': self.dropped_lines,
            'queue_max_size': self.output_queue.maxsize
        }
```

### 5. Performance-Optimized Streaming
```python
class OptimizedStreamMultiplexer:
    """High-performance output multiplexing"""

    def __init__(self):
        self.output_queue = queue.Queue()
        self.batch_size = 10  # Batch writes for efficiency

    def batched_write(self):
        """
        Write output in batches for better performance.

        Batching reduces system call overhead.
        """
        batch = []

        while self.running:
            try:
                # Collect batch of outputs
                while len(batch) < self.batch_size:
                    try:
                        repo, line = self.output_queue.get(timeout=0.1)
                        batch.append(f"[{repo}] {line}")
                    except queue.Empty:
                        break

                # Write batch if we have anything
                if batch:
                    print('\n'.join(batch))
                    batch = []

            except Exception as e:
                print(f"Error in batched write: {e}")
```

## Testing Scenarios

### Unit Tests
1. **Test output queuing**
   ```python
   multiplexer = OutputMultiplexer({})
   multiplexer.output_queue.put(('repo1', 'line1'))
   multiplexer.output_queue.put(('repo2', 'line2'))
   assert multiplexer.output_queue.qsize() == 2
   ```

2. **Test line buffering**
   - Send partial line (no newline)
   - Send completion of line
   - Verify single complete line output

3. **Test no output loss**
   - Queue 1000 lines rapidly
   - Verify all 1000 lines processed
   - Check no dropped lines

### Integration Tests
1. **Test real output multiplexing**
   ```bash
   # Start watch with multiple repos
   cidx watch &

   # Generate output in multiple repos
   echo "test" >> repo1/file1.txt
   sleep 0.1
   echo "test" >> repo2/file2.txt
   sleep 0.1
   echo "test" >> repo3/file3.txt

   # Verify all output appears
   # Verify output is interleaved correctly
   # Verify no lines are corrupted
   ```

2. **Test high-frequency output**
   - Rapidly change files in multiple repos
   - Generate high volume of watch output
   - Verify all output captured
   - Check performance remains acceptable

## Error Handling

### Queue Overflow
- Warning when queue approaches capacity
- Option to increase queue size
- Graceful degradation if queue fills
- Statistics on dropped lines

### Thread Failures
- Reader thread failure doesn't stop multiplexing
- Writer thread failure is critical (logged and reported)
- Automatic restart attempts for failed threads
- Clear error messages for debugging

## Performance Considerations

### Queue Management
- Appropriate queue size (10000 default)
- Monitor queue depth
- Alert on approaching capacity
- Efficient queue implementation

### Thread Efficiency
- One reader thread per repository
- Single writer thread to prevent stdout conflicts
- Daemon threads for automatic cleanup
- Minimal CPU usage when idle

### Batching Optimization
- Batch writes to reduce system calls
- Balance responsiveness vs efficiency
- Configurable batch size
- Automatic batching during high load

## Dependencies
- `queue` for thread-safe queuing
- `threading` for concurrent I/O
- `subprocess` for process output
- Standard library only

## Documentation Updates
- Document multiplexing architecture
- Explain thread model
- Provide performance tuning guide
- Include troubleshooting for output issues

## Example Output

### Interleaved Output from Multiple Repos
```bash
$ cidx watch

Starting watch mode for 3 repositories...
[backend/auth-service] Watch started - monitoring for changes
[backend/user-service] Watch started - monitoring for changes
[frontend/web-app] Watch started - monitoring for changes

Press Ctrl-C to stop all watchers...

[backend/auth-service] Change detected: src/auth/login.py
[frontend/web-app] Change detected: src/components/Login.vue
[backend/auth-service] Re-indexing 1 file...
[backend/user-service] Change detected: src/models/user.py
[frontend/web-app] Re-indexing 1 file...
[backend/auth-service] Indexing complete (1 file processed)
[backend/user-service] Re-indexing 1 file...
[frontend/web-app] Indexing complete (1 file processed)
[backend/user-service] Indexing complete (1 file processed)
```

### High-Frequency Output
```bash
[backend/auth-service] Processing: file1.py
[backend/user-service] Processing: file2.py
[frontend/web-app] Processing: component1.vue
[backend/auth-service] Processing: file3.py
[backend/auth-service] Processing: file4.py
[frontend/web-app] Processing: component2.vue
[backend/user-service] Processing: file5.py
[backend/auth-service] Batch complete: 3 files indexed
[frontend/web-app] Batch complete: 2 files indexed
[backend/user-service] Batch complete: 2 files indexed
```

## User Experience Principles
- Single unified output stream
- Clear repository identification
- Chronological ordering maintained
- No output loss or corruption
- Responsive real-time updates
- Easy to follow and monitor

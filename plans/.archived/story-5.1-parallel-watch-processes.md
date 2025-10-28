# Story: Parallel Watch Processes

## Story ID: STORY-5.1
## Feature: FEAT-005 (Watch Command Multiplexing)
## Priority: P2 - Enhancement
## Size: Medium

## User Story
**As a** developer monitoring multiple repositories
**I want to** run watch on all repositories simultaneously
**So that** I can see real-time changes across all projects

## Conversation Context
**Citation**: "Parallel for all, except start, stop and uninstall to prevent potential resource spikes and resource contention or race conditions."

**Context**: The conversation established that the watch command should execute in parallel across repositories (like query and status), allowing developers to monitor file changes in all repositories simultaneously from a single terminal.

## Acceptance Criteria
- [ ] Watch processes start simultaneously for all repositories
- [ ] Each repository runs its own independent watch instance
- [ ] Processes run independently without blocking each other
- [ ] Failed watch in one repository doesn't affect others
- [ ] All watch processes spawn before any monitoring begins
- [ ] Process handles maintained for lifecycle management
- [ ] Resource usage is reasonable for multiple watchers

## Technical Implementation

### 1. Parallel Watch Process Manager
```python
# proxy/watch_manager.py
import subprocess
import threading
from typing import Dict, List
from pathlib import Path

class ParallelWatchManager:
    """Manage multiple parallel watch processes"""

    def __init__(self, repositories: List[str]):
        self.repositories = repositories
        self.processes: Dict[str, subprocess.Popen] = {}
        self.running = True

    def start_all_watchers(self):
        """
        Start watch process for each repository in parallel.

        Spawns all processes before entering monitoring loop.
        """
        print(f"Starting watch mode for {len(self.repositories)} repositories...")

        # Spawn all processes
        for repo in self.repositories:
            try:
                process = self._start_watch_process(repo)
                self.processes[repo] = process
                print(f"[{repo}] Watch started - monitoring for changes")
            except Exception as e:
                print(f"[{repo}] Failed to start watch: {e}")
                # Continue with other repositories
                continue

        if not self.processes:
            raise RuntimeError("Failed to start any watch processes")

        print(f"\nPress Ctrl-C to stop all watchers...\n")

    def _start_watch_process(self, repo_path: str) -> subprocess.Popen:
        """
        Start single watch process for repository.

        Returns:
            Popen object for process management
        """
        cmd = ['cidx', 'watch']

        process = subprocess.Popen(
            cmd,
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1  # Line buffered
        )

        return process

    def stop_all_watchers(self):
        """Stop all watch processes gracefully"""
        print("\nStopping all watch processes...")

        for repo, process in self.processes.items():
            try:
                process.terminate()
                process.wait(timeout=5)
                print(f"[{repo}] Watch terminated")
            except subprocess.TimeoutExpired:
                process.kill()
                print(f"[{repo}] Watch forcefully killed")
            except Exception as e:
                print(f"[{repo}] Error stopping watch: {e}")

        self.processes.clear()

    def check_process_health(self):
        """Check if all processes are still running"""
        dead_processes = []

        for repo, process in self.processes.items():
            if process.poll() is not None:
                # Process has terminated
                dead_processes.append(repo)

        return dead_processes
```

### 2. Process Lifecycle Management
```python
class WatchProcessLifecycle:
    """Manage lifecycle of watch processes"""

    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}

    def spawn_process(
        self,
        repo_path: str,
        command: List[str]
    ) -> subprocess.Popen:
        """
        Spawn watch process with proper configuration.

        Args:
            repo_path: Repository to watch
            command: Command to execute

        Returns:
            Popen process object
        """
        process = subprocess.Popen(
            command,
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # Line buffered for immediate output
            universal_newlines=True
        )

        self.processes[repo_path] = process
        return process

    def is_process_alive(self, repo_path: str) -> bool:
        """Check if watch process is still alive"""
        process = self.processes.get(repo_path)
        if not process:
            return False

        return process.poll() is None

    def get_exit_code(self, repo_path: str) -> Optional[int]:
        """Get exit code of terminated process"""
        process = self.processes.get(repo_path)
        if not process:
            return None

        return process.poll()

    def terminate_process(
        self,
        repo_path: str,
        timeout: float = 5.0
    ) -> bool:
        """
        Gracefully terminate watch process.

        Returns:
            True if successfully terminated, False otherwise
        """
        process = self.processes.get(repo_path)
        if not process:
            return False

        try:
            process.terminate()
            process.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            process.kill()
            return False
```

### 3. Independent Process Isolation
```python
class IsolatedWatchExecutor:
    """Execute watch processes with complete isolation"""

    def execute_isolated(
        self,
        repositories: List[str]
    ) -> List[subprocess.Popen]:
        """
        Execute watch for each repository in complete isolation.

        Each process:
        - Has its own stdin/stdout/stderr
        - Runs in its own working directory
        - Maintains independent state
        - Can fail without affecting others
        """
        processes = []

        for repo in repositories:
            try:
                # Each process completely independent
                process = subprocess.Popen(
                    ['cidx', 'watch'],
                    cwd=repo,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,  # No stdin needed
                    text=True,
                    bufsize=1
                )
                processes.append(process)

            except Exception as e:
                # Failure in one doesn't stop others
                print(f"Failed to start watch in {repo}: {e}")
                continue

        return processes
```

### 4. Resource Management
```python
class WatchResourceManager:
    """Manage system resources for multiple watchers"""

    MAX_CONCURRENT_WATCHERS = 20  # Reasonable limit

    def validate_resource_limits(self, repo_count: int) -> bool:
        """Validate that resource limits allow watching all repos"""
        if repo_count > self.MAX_CONCURRENT_WATCHERS:
            print(f"Warning: {repo_count} repositories exceeds recommended limit "
                  f"of {self.MAX_CONCURRENT_WATCHERS}")
            print("Watch performance may be degraded")
            return False
        return True

    def estimate_resource_usage(self, repo_count: int) -> Dict[str, str]:
        """Estimate resource usage for watch operations"""
        # Rough estimates per watch process
        memory_per_watch = 50  # MB
        cpu_per_watch = 2  # percent

        return {
            'estimated_memory': f"{repo_count * memory_per_watch} MB",
            'estimated_cpu': f"{repo_count * cpu_per_watch}%",
            'process_count': str(repo_count)
        }
```

### 5. Health Monitoring
```python
class WatchHealthMonitor:
    """Monitor health of watch processes"""

    def __init__(self, processes: Dict[str, subprocess.Popen]):
        self.processes = processes
        self.failed_repos: List[str] = []

    def monitor_health(self) -> List[str]:
        """
        Check health of all watch processes.

        Returns:
            List of repositories with failed watch processes
        """
        failed = []

        for repo, process in self.processes.items():
            if process.poll() is not None:
                # Process has terminated unexpectedly
                failed.append(repo)

        return failed

    def report_failures(self, failed_repos: List[str]):
        """Report watch process failures"""
        if not failed_repos:
            return

        print("\nWatch process failures detected:")
        for repo in failed_repos:
            exit_code = self.processes[repo].poll()
            print(f"  • {repo} (exit code: {exit_code})")
```

## Testing Scenarios

### Unit Tests
1. **Test parallel process spawning**
   - Mock subprocess.Popen
   - Spawn processes for 3 repositories
   - Verify all processes started
   - Check process count matches repository count

2. **Test process isolation**
   - Simulate failure in one process
   - Verify other processes unaffected
   - Check failed process doesn't crash others

3. **Test resource limits**
   - Test with 1 repository (should work)
   - Test with 20 repositories (at limit)
   - Test with 25 repositories (over limit, should warn)

### Integration Tests
1. **Test real parallel watch**
   ```bash
   # Setup multiple test repositories
   mkdir -p test-proxy/{repo1,repo2,repo3}
   cd test-proxy/repo1 && cidx init && cidx start
   cd ../repo2 && cidx init && cidx start
   cd ../repo3 && cidx init && cidx start
   cd .. && cidx init --proxy-mode

   # Start watch (in background for testing)
   timeout 10 cidx watch &

   # Make changes in multiple repos simultaneously
   echo "change" >> repo1/test.txt
   echo "change" >> repo2/test.txt
   echo "change" >> repo3/test.txt

   # Verify all changes detected
   ```

2. **Test failure isolation**
   - Start watch on 3 repositories
   - Kill watch process for one repository manually
   - Verify other two continue working
   - Check error reported for failed repository

## Error Handling

### Process Spawn Failures
- Log spawn failure with details
- Continue spawning other processes
- Report which repositories failed
- Provide guidance for troubleshooting

### Early Process Termination
- Detect when process dies unexpectedly
- Report termination to user
- Continue monitoring other processes
- Option to restart failed watchers

## Performance Considerations

### Process Count Limits
- Recommend maximum 20 concurrent watchers
- Warn when exceeding recommended limit
- Monitor system resource usage
- Allow user override with warning

### Memory Usage
- Each watch process ~50MB memory
- Monitor total memory consumption
- Provide resource usage estimates
- Suggest reducing watch scope if needed

## Dependencies
- `subprocess` for process management
- `threading` for concurrent I/O
- `typing` for type hints
- Standard library only

## Documentation Updates
- Document parallel watch behavior
- Explain resource requirements
- Provide performance recommendations
- Include troubleshooting guide

## Example Output

### Successful Parallel Start
```bash
$ cidx watch

Starting watch mode for 3 repositories...
[backend/auth-service] Watch started - monitoring for changes
[backend/user-service] Watch started - monitoring for changes
[frontend/web-app] Watch started - monitoring for changes

Press Ctrl-C to stop all watchers...
```

### Start with Partial Failure
```bash
$ cidx watch

Starting watch mode for 3 repositories...
[backend/auth-service] Watch started - monitoring for changes
[backend/user-service] Failed to start watch: Qdrant service not running
[frontend/web-app] Watch started - monitoring for changes

Press Ctrl-C to stop all watchers...

Watch running in 2 of 3 repositories.
```

## User Experience Principles
- Clear indication of watch status
- Immediate feedback for each repository
- Failed repositories don't block working ones
- Resource usage is transparent
- Easy to monitor and control

# Story: Sequential Command Execution

## Story ID: STORY-2.3
## Feature: FEAT-002 (Command Forwarding Engine)
## Priority: P0 - Must Have
## Size: Small

## User Story
**As a** developer managing container lifecycle
**I want to** have resource-intensive commands execute sequentially
**So that** I avoid resource contention and race conditions

## Conversation Context
**Citation**: "Parallel for all, except start, stop and uninstall to prevent potential resource spikes and resource contention or race conditions."

**Context**: The conversation explicitly identified that container lifecycle commands (start, stop, uninstall) must execute one repository at a time to avoid resource contention, port conflicts, and race conditions that could occur when multiple containers start simultaneously.

## Acceptance Criteria
- [ ] `start` command processes repositories one at a time
- [ ] `stop` command executes sequentially
- [ ] `uninstall` runs one repository at a time
- [ ] Each command completes before next begins
- [ ] Order follows configuration list sequence
- [ ] Progress indication shows current repository
- [ ] Failed repository doesn't prevent processing remaining repos

## Technical Implementation

### 1. Sequential Execution Engine
```python
# proxy/sequential_executor.py
from typing import List, Dict
from pathlib import Path
import subprocess

class SequentialCommandExecutor:
    """Execute commands across repositories sequentially"""

    def __init__(self, repositories: List[str]):
        self.repositories = repositories

    def execute_sequential(
        self,
        command: str,
        args: List[str]
    ) -> Dict[str, tuple]:
        """
        Execute command sequentially across all repositories.

        Args:
            command: CIDX command to execute (start/stop/uninstall)
            args: Command arguments

        Returns:
            Dictionary mapping repo_path -> (stdout, stderr, exit_code)
        """
        results = {}

        for i, repo in enumerate(self.repositories, 1):
            print(f"[{i}/{len(self.repositories)}] Processing {repo}...")

            stdout, stderr, exit_code = self._execute_single(repo, command, args)
            results[repo] = (stdout, stderr, exit_code)

            # Report result immediately
            if exit_code == 0:
                print(f"  ✓ {repo}: Success")
            else:
                print(f"  ✗ {repo}: Failed")

        return results

    def _execute_single(
        self,
        repo_path: str,
        command: str,
        args: List[str]
    ) -> tuple:
        """Execute command in single repository"""
        cmd = ['cidx', command] + args

        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout for container operations
        )

        return result.stdout, result.stderr, result.returncode
```

### 2. Command Classification
```python
# proxy/command_config.py
# Hardcoded sequential commands (as per conversation)
SEQUENTIAL_COMMANDS = ['start', 'stop', 'uninstall']

def is_sequential_command(command: str) -> bool:
    """Check if command should execute sequentially"""
    return command in SEQUENTIAL_COMMANDS
```

### 3. Progress Reporting
```python
class SequentialProgressReporter:
    """Provide progress feedback during sequential execution"""

    def __init__(self, total_repos: int):
        self.total = total_repos
        self.current = 0

    def start_repo(self, repo_path: str):
        """Report starting repository processing"""
        self.current += 1
        print(f"\n[{self.current}/{self.total}] {repo_path}")

    def repo_complete(self, success: bool, message: str = None):
        """Report repository completion"""
        if success:
            print(f"  ✓ Complete")
        else:
            print(f"  ✗ Failed: {message}")

    def summary(self, success_count: int, failure_count: int):
        """Print final summary"""
        print(f"\n{'='*50}")
        print(f"Summary: {success_count} succeeded, {failure_count} failed")
        print(f"{'='*50}")
```

### 4. Error Continuity
```python
def execute_with_error_continuity(self, repositories: List[str], command: str):
    """Execute sequentially, continuing despite individual failures"""
    results = {
        'succeeded': [],
        'failed': []
    }

    for repo in repositories:
        try:
            stdout, stderr, code = self._execute_single(repo, command, [])
            if code == 0:
                results['succeeded'].append(repo)
            else:
                results['failed'].append((repo, stderr))
        except Exception as e:
            results['failed'].append((repo, str(e)))

    return results
```

### 5. Repository Ordering
```python
def get_execution_order(self, repositories: List[str], command: str) -> List[str]:
    """
    Determine execution order for sequential commands.
    Follows configuration list order.
    """
    # For now, use configuration order as-is
    # Future enhancement: allow dependency-based ordering
    return repositories
```

## Testing Scenarios

### Unit Tests
1. **Test sequential execution order**
   - Mock subprocess calls
   - Verify repos processed one at a time
   - Check order matches configuration

2. **Test progress reporting**
   - Capture stdout during execution
   - Verify progress messages appear
   - Check counter increments correctly

3. **Test error continuity**
   - Simulate failure in second repo
   - Verify third repo still executes
   - Check both failures reported

### Integration Tests
1. **Test real sequential start**
   ```bash
   # Setup multiple repositories
   mkdir -p test-proxy/{repo1,repo2,repo3}
   cd test-proxy/repo1 && cidx init
   cd ../repo2 && cidx init
   cd ../repo3 && cidx init
   cd .. && cidx init --proxy-mode

   # Start all repositories sequentially
   cidx start
   # Should see [1/3], [2/3], [3/3] progress
   ```

2. **Test stop command order**
   - Start multiple repositories
   - Execute stop command
   - Verify sequential shutdown
   - Check no orphaned containers

3. **Test uninstall sequence**
   - Multiple active repositories
   - Execute uninstall
   - Verify complete cleanup per repo
   - Check no cross-repo interference

## Error Handling

### Individual Repository Failures
1. **Container Startup Failure**
   - Capture error message
   - Continue with next repository
   - Include in final error report
   - **Citation**: "Partial success OK."

2. **Port Conflict During Start**
   - Report which repository failed
   - Suggest checking port allocation
   - Don't block remaining repositories

3. **Permission Errors**
   - Clear error message
   - Hint to check Docker/Podman permissions
   - Continue sequential processing

## Performance Considerations

### Timeout Configuration
- Longer timeout (10 minutes) for container operations
- Account for image pull time on first start
- Allow Docker daemon initialization time
- Configurable per-command timeouts

### Resource Pacing
- Brief delay between repositories optional
- Prevent cascading resource issues
- Allow system to stabilize between ops
- Monitor resource usage patterns

### Early Termination Option
- Allow Ctrl-C to stop sequential processing
- Clean up current operation before exit
- Report partial completion status
- Leave already-processed repos in final state

## Dependencies
- `subprocess` for command execution
- `typing` for type hints
- Existing ConfigManager for repository list
- Progress reporting utilities

## Security Considerations
- Validate repository paths before execution
- Prevent command injection
- Handle subprocess output safely
- Limit execution time with timeouts

## Documentation Updates
- Document sequential execution behavior
- Explain why start/stop/uninstall are sequential
- Provide timing expectations
- Include troubleshooting for slow execution

## Example Output

### Start Command (Sequential)
```bash
$ cidx start

Starting services in 3 repositories...

[1/3] backend/auth-service
  Starting Qdrant container...
  Starting Ollama container...
  ✓ Complete

[2/3] backend/user-service
  Starting Qdrant container...
  Starting Ollama container...
  ✓ Complete

[3/3] frontend/web-app
  Starting Qdrant container...
  Starting Ollama container...
  ✓ Complete

==================================================
Summary: 3 succeeded, 0 failed
==================================================
```

### Stop Command with Partial Failure
```bash
$ cidx stop

Stopping services in 3 repositories...

[1/3] backend/auth-service
  ✓ Complete

[2/3] backend/user-service
  ✗ Failed: Container not found

[3/3] frontend/web-app
  ✓ Complete

==================================================
Summary: 2 succeeded, 1 failed
==================================================
```

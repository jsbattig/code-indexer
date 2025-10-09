# Story: Parallel Command Execution

## Story ID: STORY-2.2
## Feature: FEAT-002 (Command Forwarding Engine)
## Priority: P0 - Must Have
## Size: Medium

## User Story
**As a** developer querying multiple repositories
**I want to** have read-only commands execute in parallel
**So that** I get faster results across all projects

## Conversation Context
**Citation**: "Parallel for all, except start, stop and uninstall to prevent potential resource spikes and resource contention or race conditions."

**Context**: The conversation established that read-only commands (query, status, watch, fix-config) should execute concurrently across repositories to maximize performance, while avoiding resource contention that could occur with container lifecycle commands.

## Acceptance Criteria
- [ ] `query` command executes simultaneously across all repositories
- [ ] `status` command runs in parallel for all repos
- [ ] `watch` command spawns parallel processes
- [ ] `fix-config` executes concurrently
- [ ] Results are collected from all parallel executions without blocking
- [ ] Thread pool size is reasonable (e.g., min(repo_count, 10))
- [ ] Output collection handles concurrent completion

## Technical Implementation

### 1. Parallel Execution Engine
```python
# proxy/parallel_executor.py
import concurrent.futures
from typing import List, Dict
from pathlib import Path

class ParallelCommandExecutor:
    """Execute commands across multiple repositories in parallel"""

    MAX_WORKERS = 10  # Prevent system overload

    def __init__(self, repositories: List[str]):
        self.repositories = repositories

    def execute_parallel(
        self,
        command: str,
        args: List[str]
    ) -> Dict[str, tuple]:
        """
        Execute command in parallel across all repositories.

        Args:
            command: CIDX command to execute
            args: Command arguments

        Returns:
            Dictionary mapping repo_path -> (stdout, stderr, exit_code)
        """
        worker_count = min(len(self.repositories), self.MAX_WORKERS)
        results = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            # Submit all tasks
            future_to_repo = {
                executor.submit(self._execute_single, repo, command, args): repo
                for repo in self.repositories
            }

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_repo):
                repo = future_to_repo[future]
                try:
                    stdout, stderr, exit_code = future.result()
                    results[repo] = (stdout, stderr, exit_code)
                except Exception as exc:
                    results[repo] = ('', str(exc), -1)

        return results

    def _execute_single(
        self,
        repo_path: str,
        command: str,
        args: List[str]
    ) -> tuple:
        """Execute command in single repository"""
        import subprocess

        cmd = ['cidx', command] + args

        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        return result.stdout, result.stderr, result.returncode
```

### 2. Command Classification
```python
# proxy/command_config.py
# Hardcoded parallel commands (as per conversation)
PARALLEL_COMMANDS = ['query', 'status', 'watch', 'fix-config']

def is_parallel_command(command: str) -> bool:
    """Check if command should execute in parallel"""
    return command in PARALLEL_COMMANDS
```

### 3. Result Aggregation
```python
class ParallelResultAggregator:
    """Aggregate results from parallel execution"""

    def aggregate(self, results: Dict[str, tuple]) -> tuple:
        """
        Aggregate parallel results into final output.

        Returns:
            (combined_output, overall_exit_code)
        """
        all_outputs = []
        exit_codes = []

        for repo, (stdout, stderr, code) in results.items():
            if stdout:
                all_outputs.append(stdout)
            if stderr:
                all_outputs.append(f"ERROR in {repo}: {stderr}")
            exit_codes.append(code)

        # Overall exit code: 0 if all success, 2 if partial, 1 if all failed
        if all(code == 0 for code in exit_codes):
            overall_code = 0
        elif any(code == 0 for code in exit_codes):
            overall_code = 2  # Partial success
        else:
            overall_code = 1  # Complete failure

        return '\n'.join(all_outputs), overall_code
```

### 4. Timeout Handling
```python
def execute_with_timeout(self, repo: str, command: str, timeout: int = 300):
    """Execute with configurable timeout"""
    try:
        return self._execute_single(repo, command, [], timeout=timeout)
    except subprocess.TimeoutExpired:
        return ('', f'Command timed out after {timeout}s', -1)
```

### 5. Resource Management
```python
class ResourceAwareExecutor:
    """Executor that respects system resource limits"""

    def calculate_worker_count(self, repo_count: int) -> int:
        """Calculate optimal worker count"""
        # Never exceed MAX_WORKERS
        max_allowed = self.MAX_WORKERS

        # For small repo counts, use all repos
        if repo_count <= 4:
            return repo_count

        # For larger counts, cap at MAX_WORKERS
        return min(repo_count, max_allowed)
```

## Testing Scenarios

### Unit Tests
1. **Test parallel execution logic**
   - Mock subprocess execution
   - Verify concurrent execution
   - Check result collection

2. **Test worker count calculation**
   - Small repository count (2-3) → use all
   - Large repository count (15+) → cap at MAX_WORKERS
   - Verify resource constraints respected

3. **Test timeout handling**
   - Simulate hung subprocess
   - Verify timeout expiration
   - Check error message format

### Integration Tests
1. **Test real parallel execution**
   ```bash
   # Setup multiple test repositories
   mkdir -p test-proxy/{repo1,repo2,repo3}
   cd test-proxy/repo1 && cidx init && cidx start
   cd ../repo2 && cidx init && cidx start
   cd ../repo3 && cidx init && cidx start
   cd .. && cidx init --proxy-mode

   # Time parallel query
   time cidx query "test"
   # Should complete much faster than sequential
   ```

2. **Test concurrent result collection**
   - Repositories completing at different times
   - Verify all results collected
   - Check output ordering

3. **Test error isolation**
   - One repository fails
   - Others complete successfully
   - Partial success reported correctly

## Error Handling

### Execution Errors
1. **Repository Access Failure**
   - Message: "Cannot access repository {repo_path}"
   - Continue with other repositories
   - Include in error report

2. **Subprocess Failure**
   - Capture stderr output
   - Include in error collection
   - Don't crash entire operation

3. **Timeout Expiration**
   - Kill hung subprocess
   - Report timeout error
   - Continue with other repos

## Performance Considerations

### Thread Pool Sizing
- Maximum 10 concurrent workers to prevent system overload
- For small repo counts (<4), use one thread per repo
- Monitor memory usage during execution
- Consider CPU count in worker calculation

### Output Collection Efficiency
- Stream-based collection to prevent memory bloat
- Avoid storing all results in memory simultaneously
- Process and display results as they arrive for query command

### Timeout Configuration
- Default 5-minute timeout per repository
- Configurable timeout for different command types
- Aggressive timeout for non-critical commands

## Dependencies
- `concurrent.futures` for thread pool execution
- `subprocess` for command execution
- `typing` for type hints
- Existing ConfigManager for repository list

## Security Considerations
- Validate repository paths before execution
- Prevent command injection in arguments
- Limit resource consumption with MAX_WORKERS
- Handle malicious subprocess output safely

## Documentation Updates
- Document parallel execution behavior
- Explain timeout configuration
- Provide performance benchmarks
- Include troubleshooting for concurrent issues

# Story: Partial Success Execution

## Story ID: STORY-4.1
## Feature: FEAT-004 (Error Handling and Partial Success)
## Priority: P1 - Essential
## Size: Medium

## User Story
**As a** developer running proxy commands
**I want to** have commands continue despite individual repository failures
**So that** one broken repository doesn't block all operations

## Conversation Context
**Citation**: "Partial success OK. if there;s any failure on any repo, you will show in the stdout an error message for that repo"

**Context**: The conversation established that proxy operations should adopt a partial success model where failures in individual repositories don't prevent the command from completing execution on remaining repositories. This ensures operational continuity and maximizes useful work completion.

## Acceptance Criteria
- [ ] Commands continue after individual repository failures
- [ ] Successful repositories complete their operations fully
- [ ] Final exit code indicates partial success (exit code 2)
- [ ] Both successes and failures are reported in output
- [ ] Failed repositories don't prevent subsequent processing
- [ ] Success count and failure count displayed in summary
- [ ] Exit code 0 only when ALL repositories succeed

## Technical Implementation

### 1. Partial Success Execution Model
```python
# proxy/partial_success_executor.py
from typing import List, Dict, NamedTuple
from enum import Enum

class ExecutionResult(NamedTuple):
    """Result of command execution in a single repository"""
    repo_path: str
    success: bool
    stdout: str
    stderr: str
    exit_code: int

class ExecutionStatus(Enum):
    """Overall execution status"""
    COMPLETE_SUCCESS = 0
    COMPLETE_FAILURE = 1
    PARTIAL_SUCCESS = 2

class PartialSuccessExecutor:
    """Execute commands with partial success support"""

    def __init__(self):
        self.results: List[ExecutionResult] = []

    def execute_with_continuity(
        self,
        repositories: List[str],
        command: str,
        args: List[str],
        parallel: bool = False
    ) -> tuple[List[ExecutionResult], ExecutionStatus]:
        """
        Execute command across repositories, continuing on failures.

        Args:
            repositories: List of repository paths
            command: Command to execute
            args: Command arguments
            parallel: Whether to execute in parallel

        Returns:
            Tuple of (results, overall_status)
        """
        results = []

        if parallel:
            results = self._execute_parallel_with_continuity(
                repositories, command, args
            )
        else:
            results = self._execute_sequential_with_continuity(
                repositories, command, args
            )

        # Determine overall status
        status = self._determine_status(results)

        return results, status

    def _execute_sequential_with_continuity(
        self,
        repositories: List[str],
        command: str,
        args: List[str]
    ) -> List[ExecutionResult]:
        """Execute sequentially, continuing despite failures"""
        results = []

        for repo in repositories:
            try:
                stdout, stderr, exit_code = self._execute_single(
                    repo, command, args
                )
                success = (exit_code == 0)

                result = ExecutionResult(
                    repo_path=repo,
                    success=success,
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=exit_code
                )
                results.append(result)

            except Exception as e:
                # Even exceptions don't stop execution
                result = ExecutionResult(
                    repo_path=repo,
                    success=False,
                    stdout='',
                    stderr=str(e),
                    exit_code=-1
                )
                results.append(result)

        return results

    def _determine_status(
        self,
        results: List[ExecutionResult]
    ) -> ExecutionStatus:
        """Determine overall execution status"""
        if not results:
            return ExecutionStatus.COMPLETE_FAILURE

        success_count = sum(1 for r in results if r.success)
        total_count = len(results)

        if success_count == total_count:
            return ExecutionStatus.COMPLETE_SUCCESS
        elif success_count == 0:
            return ExecutionStatus.COMPLETE_FAILURE
        else:
            return ExecutionStatus.PARTIAL_SUCCESS
```

### 2. Result Tracking
```python
class ResultTracker:
    """Track and categorize execution results"""

    def __init__(self):
        self.succeeded: List[ExecutionResult] = []
        self.failed: List[ExecutionResult] = []

    def add_result(self, result: ExecutionResult):
        """Add result to appropriate category"""
        if result.success:
            self.succeeded.append(result)
        else:
            self.failed.append(result)

    def get_summary(self) -> Dict[str, int]:
        """Get execution summary statistics"""
        return {
            'total': len(self.succeeded) + len(self.failed),
            'succeeded': len(self.succeeded),
            'failed': len(self.failed),
            'success_rate': len(self.succeeded) / max(1, len(self.succeeded) + len(self.failed))
        }

    def has_failures(self) -> bool:
        """Check if any failures occurred"""
        return len(self.failed) > 0

    def has_successes(self) -> bool:
        """Check if any successes occurred"""
        return len(self.succeeded) > 0
```

### 3. Exit Code Determination
```python
def determine_exit_code(results: List[ExecutionResult]) -> int:
    """
    Determine appropriate exit code based on results.

    Exit Codes:
        0: Complete success (all repositories succeeded)
        1: Complete failure (all repositories failed)
        2: Partial success (some succeeded, some failed)
    """
    if not results:
        return 1  # No results = failure

    success_count = sum(1 for r in results if r.success)
    total_count = len(results)

    if success_count == total_count:
        return 0  # All succeeded
    elif success_count == 0:
        return 1  # All failed
    else:
        return 2  # Partial success
```

### 4. Summary Reporting
```python
class SummaryReporter:
    """Generate execution summary reports"""

    def generate_summary(
        self,
        results: List[ExecutionResult]
    ) -> str:
        """Generate human-readable summary"""
        success_count = sum(1 for r in results if r.success)
        failure_count = len(results) - success_count

        lines = [
            "\n" + "=" * 60,
            "EXECUTION SUMMARY",
            "=" * 60,
            f"Total repositories: {len(results)}",
            f"Succeeded: {success_count}",
            f"Failed: {failure_count}",
        ]

        # List failed repositories
        if failure_count > 0:
            lines.append("\nFailed repositories:")
            for result in results:
                if not result.success:
                    lines.append(f"  • {result.repo_path}")

        # Exit code indication
        exit_code = determine_exit_code(results)
        if exit_code == 0:
            lines.append("\nStatus: COMPLETE SUCCESS")
        elif exit_code == 1:
            lines.append("\nStatus: COMPLETE FAILURE")
        else:
            lines.append("\nStatus: PARTIAL SUCCESS")

        lines.append("=" * 60)

        return '\n'.join(lines)
```

### 5. Error Isolation
```python
class ErrorIsolation:
    """Isolate errors to prevent cascade failures"""

    @staticmethod
    def execute_isolated(func, *args, **kwargs):
        """Execute function with error isolation"""
        try:
            return func(*args, **kwargs), None
        except Exception as e:
            return None, str(e)

    @staticmethod
    def safe_execute(repo: str, command: str, args: List[str]):
        """Execute with full error isolation"""
        try:
            result = subprocess.run(
                ['cidx', command] + args,
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=300
            )
            return ExecutionResult(
                repo_path=repo,
                success=(result.returncode == 0),
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                repo_path=repo,
                success=False,
                stdout='',
                stderr='Command timed out after 300 seconds',
                exit_code=-1
            )
        except Exception as e:
            return ExecutionResult(
                repo_path=repo,
                success=False,
                stdout='',
                stderr=f'Unexpected error: {str(e)}',
                exit_code=-1
            )
```

## Testing Scenarios

### Unit Tests
1. **Test partial success detection**
   ```python
   results = [
       ExecutionResult('repo1', True, 'ok', '', 0),
       ExecutionResult('repo2', False, '', 'error', 1),
       ExecutionResult('repo3', True, 'ok', '', 0),
   ]
   assert determine_exit_code(results) == 2  # Partial success
   ```

2. **Test complete success detection**
   ```python
   results = [
       ExecutionResult('repo1', True, 'ok', '', 0),
       ExecutionResult('repo2', True, 'ok', '', 0),
   ]
   assert determine_exit_code(results) == 0  # Complete success
   ```

3. **Test complete failure detection**
   ```python
   results = [
       ExecutionResult('repo1', False, '', 'error', 1),
       ExecutionResult('repo2', False, '', 'error', 1),
   ]
   assert determine_exit_code(results) == 1  # Complete failure
   ```

### Integration Tests
1. **Test continued execution after failure**
   ```bash
   # Setup: 3 repos, middle one will fail
   cd test-proxy
   cidx init --proxy-mode

   # Stop middle repo to cause failure
   cd repo2 && cidx stop && cd ..

   # Query should continue despite repo2 failure
   cidx query "test"
   # Should see results from repo1 and repo3
   # Should see error for repo2
   # Exit code should be 2 (partial success)
   ```

2. **Test summary reporting**
   - Execute command with mixed results
   - Verify summary shows correct counts
   - Check failed repositories listed
   - Confirm exit code matches status

## Error Handling

### Exception Handling
- Catch all exceptions during execution
- Convert exceptions to ExecutionResult
- Never let exception crash entire operation
- Log full stack trace for debugging

### Timeout Handling
- Individual repository timeouts don't block others
- Timeout treated as failure for that repository
- Continue with remaining repositories
- Report timeout in failure summary

## Performance Considerations
- Error handling shouldn't significantly slow execution
- Parallel execution maintains continuity
- Memory-efficient result collection
- Early exit option for critical failures (optional)

## Dependencies
- `subprocess` for command execution
- `typing` for type hints
- `enum` for status enumeration
- Logging framework for error tracking

## Documentation Updates
- Document partial success semantics
- Explain exit code meanings
- Provide examples of mixed results
- Include troubleshooting guide

## Example Output

### Query with Partial Success
```bash
$ cidx query "authentication"

Searching 3 repositories...

✓ backend/auth-service
  Score: 0.92 | src/auth/jwt.py:45

✗ backend/user-service
  Error: Cannot connect to Qdrant service

✓ frontend/web-app
  Score: 0.85 | src/api/auth.js:23

============================================================
EXECUTION SUMMARY
============================================================
Total repositories: 3
Succeeded: 2
Failed: 1

Failed repositories:
  • backend/user-service

Status: PARTIAL SUCCESS
============================================================

Exit code: 2
```

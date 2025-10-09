# Feature: Error Handling and Partial Success

## Feature ID: FEAT-004
## Epic: EPIC-001 (Multi-Repository Proxy Configuration Support)
## Status: Specification
## Priority: P1 (Essential)

## Overview

Implement robust error handling that allows proxy operations to continue despite failures in individual repositories. Provide clear, actionable error messages that guide users to resolve issues while maintaining partial success semantics.

## User Stories

### Story 4.1: Partial Success Execution
**As a** developer running proxy commands
**I want to** have commands continue despite individual repository failures
**So that** one broken repository doesn't block all operations

### Story 4.2: Clear Error Reporting
**As a** developer troubleshooting failures
**I want to** see clear error messages identifying failed repositories
**So that** I know exactly where problems occurred

### Story 4.3: Actionable Error Guidance
**As a** developer encountering search failures
**I want to** receive hints about alternative approaches
**So that** I can work around issues effectively

### Story 4.4: Error Context Preservation
**As a** developer debugging issues
**I want to** see the actual error details from failed commands
**So that** I can understand and fix the root cause

## Technical Requirements

### Partial Success Model
- Continue executing on remaining repositories after failure
- Collect both successful results and errors
- Report final status indicating partial success
- Never let one failure crash the entire operation

**Citation**: "Partial success OK. if there;s any failure on any repo, you will show in the stdout an error message for that repo"

### Error Message Format
- Clearly identify which repository failed
- Include the specific command that failed
- Show actual error output from subprocess
- Provide actionable hints for resolution

**Citation**: "clearly stating so and hinting claude code to use grep or other means to search in that repo"

### Error Categories
1. **Repository Access Errors**: Directory not found, permissions
2. **Command Execution Errors**: Command not found, invalid arguments
3. **Container/Service Errors**: Docker/Podman not running, ports in use
4. **Configuration Errors**: Invalid or missing configuration
5. **Timeout Errors**: Commands taking too long

### Error Collection Strategy
```python
class ErrorCollector:
    def __init__(self):
        self.errors = []
        self.succeeded = []

    def record_success(self, repo_path: str, output: str):
        self.succeeded.append({'repo': repo_path, 'output': output})

    def record_failure(self, repo_path: str, error: str, hint: str = None):
        self.errors.append({
            'repo': repo_path,
            'error': error,
            'hint': hint or self._generate_hint(error)
        })
```

## Acceptance Criteria

### Story 4.1: Partial Success
- [ ] Commands continue after individual repository failures
- [ ] Successful repositories complete their operations
- [ ] Final exit code indicates partial success (non-zero)
- [ ] Both successes and failures are reported

### Story 4.2: Error Identification
- [ ] Failed repository path clearly shown in error message
- [ ] Error appears in stdout (not just stderr)
- [ ] Multiple failures each get their own error block
- [ ] Error messages are visually distinct from success output

### Story 4.3: Actionable Hints
- [ ] Query failures suggest using grep or manual search
- [ ] Container errors suggest checking Docker/Podman
- [ ] Configuration errors suggest running fix-config
- [ ] Hints are contextual to the error type

### Story 4.4: Error Details
- [ ] Original error message from subprocess is preserved
- [ ] Exit codes are captured and reported
- [ ] Stack traces included when available
- [ ] Timestamp included for debugging

## Implementation Notes

### Error Display Format
```
==================================================
ERROR: Repository 'backend/auth-service' failed
==================================================
Command: cidx query "authentication" --limit 10
Error: No Qdrant service found at port 6333
Exit Code: 1

Hint: Use 'grep -r "authentication"' to search this repository manually,
      or navigate to the repository and run 'cidx status' to check services.

Original Error:
  ConnectionError: Cannot connect to Qdrant at localhost:6333
  Service may not be running or port may be incorrect
==================================================
```

### Hint Generation Logic
```python
def generate_hint(error: str, command: str) -> str:
    if command == 'query':
        return "Use 'grep' or other search tools to search this repository manually"
    elif command in ['start', 'stop']:
        return "Navigate to the repository and check container status with 'docker ps'"
    elif 'config' in error.lower():
        return "Run 'cidx fix-config' in the affected repository"
    else:
        return "Navigate to the repository and run the command directly"
```

### Exit Code Strategy
- 0: Complete success (all repositories succeeded)
- 1: Complete failure (all repositories failed)
- 2: Partial success (some succeeded, some failed)
- 3: Invalid command or configuration error

## Dependencies
- Subprocess error handling
- Logging framework for error details
- Output formatting utilities
- Error classification logic

## Testing Requirements

### Unit Tests
- Error collection and categorization
- Hint generation for different error types
- Exit code determination
- Error message formatting

### Integration Tests
- Partial success with mixed results
- Multiple repository failures
- Various error types (network, permissions, timeout)
- Error message visibility in output

### Error Scenarios
- Repository directory doesn't exist
- No configuration in repository
- Container services not running
- Network timeouts
- Permission denied errors
- Invalid command arguments

## Performance Considerations

### Error Collection
- Avoid memory bloat with large error messages
- Truncate extremely long error outputs
- Aggregate similar errors when possible

### Timeout Handling
- Implement reasonable timeouts for hung commands
- Allow timeout configuration per command type
- Kill subprocess cleanly on timeout

## User Experience

### Error Visibility
- Errors should be impossible to miss
- Use visual separators (lines, colors if terminal supports)
- Summarize errors at the end of output

### Progressive Disclosure
- Show summary first, details on demand
- Critical information in error summary
- Full stack traces in verbose mode

### Recovery Guidance
- Every error should suggest next steps
- Common issues should have specific solutions
- Link to documentation for complex issues

## Examples

### Query Command with Partial Failure
```bash
$ cidx query "authentication"

Searching in 3 repositories...

backend/user-service:
  Score: 0.92 | src/auth/jwt.py:45
    def verify_token(token: str) -> bool:

ERROR: backend/auth-service failed
  Cannot connect to Qdrant service
  Hint: Use 'grep -r "authentication"' in that repository

frontend/web-app:
  Score: 0.85 | src/api/auth.js:23
    async function authenticate(credentials) {

Summary: 2 succeeded, 1 failed
```

### Start Command with Sequential Failures
```bash
$ cidx start

Starting services in 3 repositories...

✓ backend/user-service: Services started successfully
✗ backend/auth-service: Port 6333 already in use
  Hint: Check for conflicting services with 'docker ps'
✓ frontend/web-app: Services started successfully

Summary: 2 succeeded, 1 failed
Exit code: 2 (partial success)
```
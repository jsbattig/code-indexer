# Story: Clear Error Reporting

## Story ID: STORY-4.2
## Feature: FEAT-004 (Error Handling and Partial Success)
## Priority: P1 - Essential
## Size: Small

## User Story
**As a** developer troubleshooting failures
**I want to** see clear error messages identifying failed repositories
**So that** I know exactly where problems occurred

## Conversation Context
**Citation**: "Partial success OK. if there;s any failure on any repo, you will show in the stdout an error message for that repo"

**Context**: The conversation emphasized that error messages must appear in stdout (not just stderr) and must clearly identify which repository failed. This ensures developers can immediately understand the scope and location of failures without parsing complex log outputs.

## Acceptance Criteria
- [ ] Failed repository path clearly shown in error message
- [ ] Error appears in stdout (not just stderr)
- [ ] Multiple failures each get their own error block
- [ ] Error messages are visually distinct from success output
- [ ] Repository name appears at start of error block
- [ ] Error messages use clear visual separators
- [ ] Errors are chronologically ordered with successes

## Technical Implementation

### 1. Error Message Formatter
```python
# proxy/error_formatter.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class ErrorMessage:
    """Structured error message"""
    repository: str
    command: str
    error_text: str
    exit_code: int
    hint: Optional[str] = None

class ErrorMessageFormatter:
    """Format error messages for clear display"""

    ERROR_SEPARATOR = "=" * 60
    ERROR_PREFIX = "✗"
    SUCCESS_PREFIX = "✓"

    def format_error(self, error: ErrorMessage) -> str:
        """
        Format single error message with clear visual structure.

        Output format:
        ============================================================
        ✗ FAILED: repository/path
        ============================================================
        Command: cidx query "test"
        Error: Cannot connect to Qdrant service
        Exit code: 1
        ============================================================
        """
        lines = [
            self.ERROR_SEPARATOR,
            f"{self.ERROR_PREFIX} FAILED: {error.repository}",
            self.ERROR_SEPARATOR,
            f"Command: cidx {error.command}",
            f"Error: {error.error_text}",
            f"Exit code: {error.exit_code}",
        ]

        if error.hint:
            lines.extend([
                "",
                f"Hint: {error.hint}"
            ])

        lines.append(self.ERROR_SEPARATOR)

        return '\n'.join(lines)

    def format_inline_error(self, repository: str, error_text: str) -> str:
        """
        Format compact error for inline display.

        Output format:
        ✗ repository/path: Error message
        """
        return f"{self.ERROR_PREFIX} {repository}: {error_text}"

    def format_success(self, repository: str, message: str = "") -> str:
        """
        Format success message.

        Output format:
        ✓ repository/path: Success message
        """
        suffix = f": {message}" if message else ""
        return f"{self.SUCCESS_PREFIX} {repository}{suffix}"
```

### 2. Stdout Error Display
```python
class StdoutErrorReporter:
    """Report errors to stdout as specified in conversation"""

    def __init__(self):
        self.formatter = ErrorMessageFormatter()

    def report_error(self, error: ErrorMessage):
        """Report error to stdout (not stderr)"""
        # IMPORTANT: Print to stdout, not stderr
        print(self.formatter.format_error(error))

    def report_inline_error(self, repository: str, error: str):
        """Report compact error inline with other output"""
        print(self.formatter.format_inline_error(repository, error))

    def report_success(self, repository: str, message: str = ""):
        """Report success for contrast with errors"""
        print(self.formatter.format_success(repository, message))
```

### 3. Visual Distinction
```python
class VisuallyDistinctReporter:
    """Ensure errors are visually distinct from success output"""

    def __init__(self, use_color: bool = True):
        self.use_color = use_color
        self.formatter = ErrorMessageFormatter()

    def report_result(self, result: ExecutionResult):
        """Report result with appropriate visual styling"""
        if result.success:
            self._report_success(result)
        else:
            self._report_error(result)

    def _report_error(self, result: ExecutionResult):
        """Report error with visual emphasis"""
        if self.use_color:
            # Red color for errors if terminal supports it
            print(f"\033[91m{self.formatter.ERROR_PREFIX}\033[0m {result.repo_path}")
            print(f"  Error: {result.stderr}")
        else:
            print(f"{self.formatter.ERROR_PREFIX} {result.repo_path}")
            print(f"  Error: {result.stderr}")

    def _report_success(self, result: ExecutionResult):
        """Report success with subtle styling"""
        if self.use_color:
            # Green color for success if terminal supports it
            print(f"\033[92m{self.formatter.SUCCESS_PREFIX}\033[0m {result.repo_path}")
        else:
            print(f"{self.formatter.SUCCESS_PREFIX} {result.repo_path}")
```

### 4. Multiple Error Handling
```python
class MultipleErrorReporter:
    """Handle reporting of multiple errors clearly"""

    def __init__(self):
        self.formatter = ErrorMessageFormatter()
        self.errors: List[ErrorMessage] = []

    def add_error(self, error: ErrorMessage):
        """Add error to collection"""
        self.errors.append(error)

    def report_all_errors(self):
        """Report all collected errors with clear separation"""
        if not self.errors:
            return

        print("\n" + "=" * 60)
        print(f"ERRORS ENCOUNTERED ({len(self.errors)} total)")
        print("=" * 60 + "\n")

        for i, error in enumerate(self.errors, 1):
            print(f"Error {i} of {len(self.errors)}:")
            print(self.formatter.format_error(error))
            if i < len(self.errors):
                print()  # Blank line between errors
```

### 5. Chronological Error Display
```python
class ChronologicalReporter:
    """Report results in chronological order as they occur"""

    def __init__(self):
        self.formatter = ErrorMessageFormatter()

    def report_as_completed(self, result: ExecutionResult):
        """Report result immediately as it completes"""
        if result.success:
            print(self.formatter.format_success(
                result.repo_path,
                "Complete"
            ))
        else:
            # Error reported inline, then detailed at end
            print(self.formatter.format_inline_error(
                result.repo_path,
                result.stderr
            ))
```

## Testing Scenarios

### Unit Tests
1. **Test error message formatting**
   ```python
   error = ErrorMessage(
       repository="backend/auth-service",
       command="query 'test'",
       error_text="Cannot connect to Qdrant",
       exit_code=1
   )
   formatted = formatter.format_error(error)
   assert "FAILED: backend/auth-service" in formatted
   assert "Cannot connect to Qdrant" in formatted
   ```

2. **Test stdout output (not stderr)**
   - Capture stdout and stderr separately
   - Verify errors written to stdout
   - Confirm stderr is empty or minimal

3. **Test multiple error display**
   - Add 3 different errors
   - Format all errors
   - Verify clear separation between them

### Integration Tests
1. **Test visual distinction**
   ```bash
   # Execute command with mixed results
   cidx query "test"
   # Visually verify ✗ appears for errors
   # Visually verify ✓ appears for successes
   # Confirm errors stand out from successes
   ```

2. **Test chronological ordering**
   - Sequential command execution
   - Verify errors appear in execution order
   - Check inline errors appear immediately
   - Confirm detailed errors at end

## Error Handling

### Output Formatting Errors
- Handle very long error messages (truncate if needed)
- Manage Unicode characters gracefully
- Handle terminal width constraints
- Deal with color support detection

### Repository Path Display
- Show full path for clarity
- Handle long paths gracefully
- Support relative path display option
- Consistent path formatting

## Performance Considerations
- Minimal overhead for error formatting
- Immediate output for real-time feedback
- Buffering considerations for performance
- Memory-efficient error collection

## Dependencies
- `dataclasses` for error structure
- `typing` for type hints
- Optional `colorama` for cross-platform colors
- Standard output streams

## Documentation Updates
- Document error message format
- Explain stdout vs stderr usage
- Provide error message examples
- Include visual design rationale

## Example Error Output

### Single Error (Detailed Format)
```bash
============================================================
✗ FAILED: backend/auth-service
============================================================
Command: cidx query "authentication"
Error: Cannot connect to Qdrant service at port 6333
Exit code: 1

Hint: Run 'cidx status' in this repository to check services
============================================================
```

### Multiple Errors with Successes (Inline Format)
```bash
$ cidx query "authentication"

Searching 3 repositories...

✓ backend/user-service
  Score: 0.92 | src/auth/jwt.py:45

✗ backend/auth-service: Cannot connect to Qdrant service

✓ frontend/web-app
  Score: 0.85 | src/api/auth.js:23

============================================================
ERRORS ENCOUNTERED (1 total)
============================================================

Error 1 of 1:
============================================================
✗ FAILED: backend/auth-service
============================================================
Command: cidx query "authentication"
Error: Cannot connect to Qdrant service at port 6333
Exit code: 1
============================================================
```

### Sequential Command with Multiple Failures
```bash
$ cidx start

Starting services in 3 repositories...

[1/3] backend/auth-service
  ✓ Services started successfully

[2/3] backend/user-service
  ✗ Port 6333 already in use

[3/3] frontend/web-app
  ✗ Docker daemon not accessible

============================================================
ERRORS ENCOUNTERED (2 total)
============================================================

Error 1 of 2:
============================================================
✗ FAILED: backend/user-service
============================================================
Command: cidx start
Error: Port 6333 already in use
Exit code: 1

Hint: Check for conflicting services with 'docker ps'
============================================================

Error 2 of 2:
============================================================
✗ FAILED: frontend/web-app
============================================================
Command: cidx start
Error: Cannot connect to Docker daemon
Exit code: 1

Hint: Ensure Docker is running
============================================================
```

## User Experience Principles
- Errors are immediately visible
- No need to scroll or search for failures
- Clear repository identification
- Actionable information provided
- Visual hierarchy guides attention

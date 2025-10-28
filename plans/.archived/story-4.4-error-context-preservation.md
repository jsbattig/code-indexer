# Story: Error Context Preservation

## Story ID: STORY-4.4
## Feature: FEAT-004 (Error Handling and Partial Success)
## Priority: P1 - Essential
## Size: Small

## User Story
**As a** developer debugging issues
**I want to** see the actual error details from failed commands
**So that** I can understand and fix the root cause

## Conversation Context
**Citation**: "Partial success OK. if there;s any failure on any repo, you will show in the stdout an error message for that repo"

**Context**: The conversation implied that error reporting should preserve the original error context from subprocess execution, including stderr output, exit codes, and any other diagnostic information. This enables effective debugging by providing full visibility into what actually went wrong.

## Acceptance Criteria
- [ ] Original error message from subprocess is preserved completely
- [ ] Exit codes are captured and reported for each repository
- [ ] Stack traces included when available and relevant
- [ ] Stderr output is captured and displayed
- [ ] Stdout from failed command is available if needed
- [ ] Error context includes command that was executed
- [ ] Timestamp included for debugging concurrent operations

## Technical Implementation

### 1. Comprehensive Error Context Capture
```python
# proxy/error_context.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class ErrorContext:
    """Complete error context from command execution"""
    repository: str
    command: str
    args: List[str]
    exit_code: int
    stdout: str
    stderr: str
    timestamp: datetime
    execution_time: float  # seconds
    exception: Optional[Exception] = None

    def get_full_command(self) -> str:
        """Get the complete command that was executed"""
        return f"cidx {self.command} {' '.join(self.args)}"

    def has_stderr(self) -> bool:
        """Check if stderr contains content"""
        return bool(self.stderr and self.stderr.strip())

    def has_stdout(self) -> bool:
        """Check if stdout contains content"""
        return bool(self.stdout and self.stdout.strip())

    def get_primary_error(self) -> str:
        """Get the primary error message (stderr preferred)"""
        if self.has_stderr():
            return self.stderr.strip()
        elif self.exception:
            return str(self.exception)
        elif self.has_stdout():
            return self.stdout.strip()
        else:
            return f"Command exited with code {self.exit_code}"
```

### 2. Context Preservation During Execution
```python
class ContextPreservingExecutor:
    """Execute commands while preserving full error context"""

    def execute_with_context(
        self,
        repository: str,
        command: str,
        args: List[str]
    ) -> ErrorContext:
        """
        Execute command and capture complete context.

        Returns ErrorContext with all diagnostic information.
        """
        import subprocess
        import time

        start_time = time.time()
        timestamp = datetime.now()

        try:
            result = subprocess.run(
                ['cidx', command] + args,
                cwd=repository,
                capture_output=True,
                text=True,
                timeout=300
            )

            execution_time = time.time() - start_time

            return ErrorContext(
                repository=repository,
                command=command,
                args=args,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                timestamp=timestamp,
                execution_time=execution_time,
                exception=None
            )

        except subprocess.TimeoutExpired as e:
            execution_time = time.time() - start_time
            return ErrorContext(
                repository=repository,
                command=command,
                args=args,
                exit_code=-1,
                stdout=e.stdout.decode() if e.stdout else '',
                stderr=e.stderr.decode() if e.stderr else '',
                timestamp=timestamp,
                execution_time=execution_time,
                exception=e
            )

        except Exception as e:
            execution_time = time.time() - start_time
            return ErrorContext(
                repository=repository,
                command=command,
                args=args,
                exit_code=-1,
                stdout='',
                stderr=str(e),
                timestamp=timestamp,
                execution_time=execution_time,
                exception=e
            )
```

### 3. Error Context Formatting
```python
class ErrorContextFormatter:
    """Format error context for display"""

    def format_full_context(self, context: ErrorContext) -> str:
        """
        Format complete error context for debugging.

        Output includes:
        - Repository and command
        - Exit code
        - Timestamp and execution time
        - Stderr output
        - Stdout if relevant
        - Exception details if present
        """
        lines = [
            "=" * 60,
            f"ERROR DETAILS: {context.repository}",
            "=" * 60,
            f"Command: {context.get_full_command()}",
            f"Exit Code: {context.exit_code}",
            f"Timestamp: {context.timestamp.isoformat()}",
            f"Execution Time: {context.execution_time:.2f}s",
        ]

        # Stderr (primary error source)
        if context.has_stderr():
            lines.extend([
                "",
                "Standard Error:",
                "-" * 60,
                context.stderr.strip(),
                "-" * 60
            ])

        # Stdout (if contains error information)
        if context.has_stdout() and context.exit_code != 0:
            lines.extend([
                "",
                "Standard Output:",
                "-" * 60,
                context.stdout.strip(),
                "-" * 60
            ])

        # Exception details
        if context.exception:
            lines.extend([
                "",
                "Exception Details:",
                "-" * 60,
                f"Type: {type(context.exception).__name__}",
                f"Message: {str(context.exception)}",
                "-" * 60
            ])

        lines.append("=" * 60)

        return '\n'.join(lines)

    def format_compact_context(self, context: ErrorContext) -> str:
        """Format minimal error context for inline display"""
        error_msg = context.get_primary_error()
        return f"{context.repository}: {error_msg} (exit {context.exit_code})"
```

### 4. Stack Trace Preservation
```python
class StackTracePreserver:
    """Preserve and format stack traces from errors"""

    def extract_stack_trace(self, stderr: str) -> Optional[str]:
        """Extract Python stack trace from stderr"""
        import re

        # Look for Python traceback pattern
        traceback_pattern = r'Traceback \(most recent call last\):.*?(?=\n\S|\Z)'
        match = re.search(traceback_pattern, stderr, re.DOTALL)

        if match:
            return match.group(0)

        return None

    def format_stack_trace(self, stack_trace: str) -> str:
        """Format stack trace for display"""
        return f"""
Stack Trace:
{'='*60}
{stack_trace}
{'='*60}
"""
```

### 5. Context Aggregation
```python
class ErrorContextAggregator:
    """Aggregate error contexts from multiple repositories"""

    def __init__(self):
        self.contexts: List[ErrorContext] = []

    def add_context(self, context: ErrorContext):
        """Add error context to collection"""
        self.contexts.append(context)

    def get_contexts_by_error_type(self) -> Dict[str, List[ErrorContext]]:
        """Group contexts by error type for analysis"""
        from collections import defaultdict

        grouped = defaultdict(list)

        for context in self.contexts:
            error_type = self._categorize_error(context)
            grouped[error_type].append(context)

        return dict(grouped)

    def _categorize_error(self, context: ErrorContext) -> str:
        """Categorize error based on content"""
        error_msg = context.get_primary_error().lower()

        if 'qdrant' in error_msg or 'connect' in error_msg:
            return 'connection_error'
        elif 'port' in error_msg:
            return 'port_conflict'
        elif 'permission' in error_msg:
            return 'permission_error'
        elif 'timeout' in error_msg:
            return 'timeout_error'
        else:
            return 'unknown_error'

    def generate_summary_report(self) -> str:
        """Generate summary report of all errors"""
        grouped = self.get_contexts_by_error_type()

        lines = [
            "=" * 60,
            "ERROR SUMMARY REPORT",
            "=" * 60,
            f"Total Errors: {len(self.contexts)}",
            ""
        ]

        for error_type, contexts in grouped.items():
            lines.append(f"{error_type}: {len(contexts)} occurrence(s)")
            for ctx in contexts:
                lines.append(f"  • {ctx.repository} (exit {ctx.exit_code})")

        return '\n'.join(lines)
```

## Testing Scenarios

### Unit Tests
1. **Test context capture**
   ```python
   context = executor.execute_with_context(
       repository='test-repo',
       command='query',
       args=['test']
   )
   assert context.repository == 'test-repo'
   assert context.command == 'query'
   assert context.exit_code is not None
   assert context.timestamp is not None
   ```

2. **Test stderr preservation**
   - Execute command that produces stderr
   - Verify stderr captured completely
   - Check stderr included in formatted output

3. **Test exit code capture**
   - Execute successful command (exit 0)
   - Execute failed command (exit 1)
   - Verify correct exit codes captured

### Integration Tests
1. **Test full context in error display**
   ```bash
   # Cause error in repository
   cd repo1 && cidx stop && cd ..

   # Execute proxy command
   cidx query "test" 2>&1 | tee output.txt

   # Verify output contains:
   # - Repository name
   # - Exit code
   # - Stderr content
   # - Timestamp
   grep "Exit Code:" output.txt
   grep "Standard Error:" output.txt
   ```

2. **Test exception context preservation**
   - Simulate timeout exception
   - Verify exception details captured
   - Check exception included in output

## Error Handling

### Encoding Issues
- Handle non-UTF8 stderr output
- Gracefully handle binary data in output
- Convert encoding errors to readable messages

### Large Output Handling
- Truncate extremely large stderr (>10KB)
- Preserve beginning and end of large output
- Indicate truncation in output

## Performance Considerations
- Minimal overhead for context capture
- Efficient string handling for large outputs
- Lazy formatting of detailed context
- Memory-efficient context storage

## Dependencies
- `subprocess` for command execution
- `datetime` for timestamps
- `typing` for type hints
- `dataclasses` for context structure

## Documentation Updates
- Document error context structure
- Explain what information is captured
- Provide examples of formatted output
- Include debugging guidance

## Example Output

### Full Error Context Display
```
============================================================
ERROR DETAILS: backend/auth-service
============================================================
Command: cidx query "authentication" --limit 10
Exit Code: 1
Timestamp: 2025-10-08T14:23:45.123456
Execution Time: 2.34s

Standard Error:
------------------------------------------------------------
Error: Cannot connect to Qdrant service at localhost:6333
Connection refused (Connection error)

Qdrant client initialization failed.
Please ensure Qdrant service is running:
  cidx start
------------------------------------------------------------

============================================================
```

### Error Context with Exception
```
============================================================
ERROR DETAILS: backend/user-service
============================================================
Command: cidx start
Exit Code: -1
Timestamp: 2025-10-08T14:25:12.789012
Execution Time: 300.00s

Standard Error:
------------------------------------------------------------
Command timed out after 300 seconds
------------------------------------------------------------

Exception Details:
------------------------------------------------------------
Type: TimeoutExpired
Message: Command '['cidx', 'start']' timed out after 300 seconds
------------------------------------------------------------

============================================================
```

### Aggregated Error Summary
```
============================================================
ERROR SUMMARY REPORT
============================================================
Total Errors: 3

connection_error: 2 occurrence(s)
  • backend/auth-service (exit 1)
  • frontend/web-app (exit 1)

timeout_error: 1 occurrence(s)
  • backend/user-service (exit -1)
============================================================
```

## User Experience Principles
- Complete diagnostic information available
- No information loss from subprocess execution
- Debugging-friendly output format
- Timestamps enable correlation analysis
- Exit codes guide troubleshooting

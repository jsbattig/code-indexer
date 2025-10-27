# Story 4.3: Timeout Management

## Story Description

As a CIDX CLI user, I need proper timeout handling for long-running sync operations, with the ability to extend timeouts when progress is being made and gracefully cancel operations that exceed limits.

## Technical Specification

### Timeout Management System

```pseudocode
class TimeoutManager:
    def __init__(defaultTimeout: seconds = 300):
        self.timeout = defaultTimeout
        self.startTime = now()
        self.extensions = 0
        self.maxExtensions = 3

    def checkTimeout() -> TimeoutStatus:
        elapsed = now() - self.startTime
        remaining = self.timeout - elapsed

        if remaining <= 0:
            return EXPIRED
        elif remaining <= 30:
            return WARNING
        else:
            return OK

    def requestExtension(progress: JobProgress) -> bool:
        if self.extensions >= self.maxExtensions:
            return false

        if progress.isActive():
            self.timeout += 120  # Add 2 minutes
            self.extensions++
            return true

        return false

class TimeoutStatus:
    OK          # Plenty of time remaining
    WARNING     # <30 seconds remaining
    EXPIRED     # Timeout exceeded
```

### Graceful Cancellation

```pseudocode
class CancellationHandler:
    def setupSignalHandlers():
        signal(SIGINT, handleInterrupt)    # Ctrl+C
        signal(SIGTERM, handleTerminate)   # Kill signal

    def handleInterrupt():
        if confirmCancellation():
            cancelJob()
            cleanup()
            exit(130)
        else:
            resumeOperation()

    def cancelJob(jobId: string):
        # Attempt graceful cancellation
        response = api.post("/api/jobs/{jobId}/cancel")

        # Wait for confirmation (max 5 seconds)
        waitForCancellation(jobId, timeout=5)

        # Force cleanup if needed
        forceCleanup()
```

## Acceptance Criteria

### Timeout Enforcement
```gherkin
Given a sync operation with timeout
When the timeout is reached
Then the system should:
  - Detect timeout condition
  - Attempt graceful cancellation
  - Send cancel request to server
  - Wait for job to stop
  - Clean up resources
And exit with timeout error
```

### User Interaction
```gherkin
Given a long-running sync operation
When timeout is approaching (30s left)
Then the system should:
  - Display timeout warning
  - Show current progress
  - Offer to extend timeout
  - Accept user input (y/n)
  - Process decision accordingly
And continue or cancel based on response
```

### Graceful Cancellation
```gherkin
Given a user presses Ctrl+C
When handling the interrupt
Then the system should:
  - Catch the signal immediately
  - Prompt for confirmation
  - If confirmed, cancel server job
  - Clean up local resources
  - Exit with code 130
And ensure no orphaned processes
```

### Cleanup Procedures
```gherkin
Given a sync operation is cancelled
When performing cleanup
Then the system should:
  - Close network connections
  - Save partial progress info
  - Clear temporary files
  - Reset terminal state
  - Log cancellation reason
And leave system in clean state
```

### Extension Logic
```gherkin
Given timeout warning is shown
When user requests extension
Then the system should:
  - Check if extensions available (max 3)
  - Verify job is making progress
  - Add 2 minutes to timeout
  - Update display with new timeout
  - Continue polling
And track extension count
```

## Completion Checklist

- [ ] Timeout enforcement
  - [ ] Timer implementation
  - [ ] Timeout detection
  - [ ] Warning at 30 seconds
  - [ ] Automatic cancellation
- [ ] User interaction
  - [ ] Warning display
  - [ ] Input handling
  - [ ] Extension prompt
  - [ ] Decision processing
- [ ] Graceful cancellation
  - [ ] Signal handlers
  - [ ] Confirmation prompt
  - [ ] Server cancellation
  - [ ] Local cleanup
- [ ] Cleanup procedures
  - [ ] Resource release
  - [ ] State saving
  - [ ] File cleanup
  - [ ] Terminal reset

## Test Scenarios

### Happy Path
1. Quick sync → Completes before timeout → Success
2. Warning shown → User extends → Completes in extension
3. Ctrl+C pressed → User cancels → Clean exit
4. Auto-extension → Progress detected → Extended silently

### Error Cases
1. Timeout reached → No extension → Cancelled cleanly
2. Max extensions → Cannot extend → Timeout enforced
3. Server unresponsive → Force cancel → Local cleanup
4. Cleanup fails → Error logged → Best effort exit

### Edge Cases
1. Instant timeout (0s) → Immediate cancel
2. Very long timeout → Works correctly
3. Multiple Ctrl+C → Handled gracefully
4. Terminal closed → Cleanup via signal

## Performance Requirements

- Timeout check: <1ms overhead
- Signal handling: <100ms response
- Cancellation request: <5 seconds
- Cleanup completion: <2 seconds
- Terminal restore: Immediate

## User Prompts

### Timeout Warning
```
⚠️  Timeout Warning: 30 seconds remaining

Current progress: 78% complete
Estimated time to complete: 45 seconds

Would you like to extend the timeout by 2 minutes? (y/n): _
```

### Cancellation Confirmation
```
🛑 Interrupt received!

Current sync progress: 45% complete
Do you want to cancel the sync operation? (y/n): _

Note: You can resume sync later by running 'cidx sync' again
```

### Extension Granted
```
✓ Timeout extended by 2 minutes
  New timeout: 7 minutes total
  Extensions remaining: 2
  Current progress: 78%
```

### Timeout Reached
```
⏱️ Timeout reached after 5 minutes

Attempting to cancel sync operation...
✓ Sync cancelled successfully

Summary:
  • Progress achieved: 67%
  • Files processed: 234/350
  • You can resume by running 'cidx sync' again
```

## Signal Handling

| Signal | Action | Exit Code |
|--------|--------|-----------|
| SIGINT (Ctrl+C) | Prompt for confirmation | 130 |
| SIGTERM | Immediate graceful cancel | 143 |
| SIGQUIT | Force quit, minimal cleanup | 131 |
| SIGHUP | Save state and exit | 129 |

## Cleanup Checklist

```pseudocode
CleanupProcedure:
    1. Cancel server job (if running)
    2. Close API connections
    3. Save progress state to ~/.cidx/interrupted/
    4. Clear progress bar from terminal
    5. Reset terminal to normal mode
    6. Delete temporary files
    7. Log cancellation details
    8. Update job history
    9. Release file locks
    10. Exit with appropriate code
```

## State Preservation

```json
// ~/.cidx/interrupted/last_sync.json
{
  "jobId": "abc-123-def",
  "timestamp": "2024-01-15T10:30:00Z",
  "progress": 67,
  "phase": "INDEXING",
  "filesProcessed": 234,
  "totalFiles": 350,
  "reason": "user_cancelled",
  "resumable": true
}
```

## Definition of Done

- [ ] Timeout detection accurate to second
- [ ] Warning shown at 30 seconds
- [ ] Extension mechanism working
- [ ] Signal handlers installed
- [ ] Graceful cancellation functional
- [ ] Cleanup comprehensive
- [ ] State preserved for resume
- [ ] Unit tests >90% coverage
- [ ] Integration tests with signals
- [ ] Performance requirements met
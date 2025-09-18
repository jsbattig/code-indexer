# Story 4.2: Polling Loop Engine

## Story Description

As a CIDX CLI implementation, I need a robust polling engine that checks job status at regular intervals, handles network issues gracefully, and provides smooth progress updates while avoiding overwhelming the server.

## Technical Specification

### Polling Loop Architecture

```pseudocode
class PollingEngine:
    def pollUntilComplete(jobId: string, timeout: int) -> JobResult:
        startTime = now()
        lastProgress = 0
        stallCount = 0
        backoffMs = 1000  # Start with 1 second

        while (now() - startTime < timeout):
            try:
                status = checkJobStatus(jobId)

                if status.isComplete():
                    return status.result

                if status.progress == lastProgress:
                    stallCount++
                    if stallCount > 30:  # 30 seconds no progress
                        handleStalled(jobId)
                else:
                    stallCount = 0
                    lastProgress = status.progress

                updateProgressDisplay(status)
                sleep(calculateBackoff(backoffMs, status))

            catch NetworkError:
                backoffMs = min(backoffMs * 2, 10000)  # Max 10s
                handleNetworkError(backoffMs)

        throw TimeoutError()

class JobStatus:
    jobId: string
    status: RUNNING | COMPLETED | FAILED | CANCELLED
    progress: int (0-100)
    phase: string
    message: string
    error: string
    metadata: dict
```

### Adaptive Polling Strategy

```pseudocode
class AdaptivePoller:
    def calculateInterval(progress: int, phase: string) -> milliseconds:
        # Fast polling during active phases
        if phase in ["GIT_SYNC", "INDEXING"]:
            return 1000  # 1 second

        # Slower during waiting phases
        if phase == "QUEUED":
            return 2000  # 2 seconds

        # Adaptive based on progress rate
        if progressRate > 5_percent_per_second:
            return 500   # 500ms for fast progress
        else:
            return 1500  # 1.5s for slow progress

    def shouldBackoff(errorCount: int) -> milliseconds:
        # Exponential backoff on errors
        return min(1000 * (2 ** errorCount), 30000)
```

## Acceptance Criteria

### Status Checking
```gherkin
Given a running sync job
When polling for status
Then the engine should:
  - Query /api/jobs/{id}/status endpoint
  - Parse response into JobStatus
  - Handle all status values correctly
  - Extract progress percentage
  - Update local state
And continue until completion
```

### Backoff Strategy
```gherkin
Given various network conditions
When implementing backoff
Then the engine should:
  - Start with 1 second intervals
  - Increase on network errors (2x)
  - Decrease on successful responses
  - Respect maximum interval (10s)
  - Adapt to progress rate
And minimize server load
```

### Progress Handling
```gherkin
Given status updates from server
When displaying progress
Then the engine should:
  - Update progress bar smoothly
  - Show current phase description
  - Display percentage complete
  - Show estimated time remaining
  - Indicate stalled conditions
And refresh at appropriate rate
```

### Completion Detection
```gherkin
Given a job status check
When the job completes
Then the engine should:
  - Detect COMPLETED status
  - Detect FAILED status
  - Detect CANCELLED status
  - Retrieve final results
  - Stop polling immediately
And return appropriate result
```

### Stall Detection
```gherkin
Given a job showing no progress
When detecting stalls
Then the engine should:
  - Track progress over time
  - Detect no change for 30 seconds
  - Warn user about potential stall
  - Offer options (wait/cancel)
  - Continue or abort based on choice
And handle gracefully
```

## Completion Checklist

- [ ] Status checking
  - [ ] API endpoint integration
  - [ ] Response parsing
  - [ ] Status interpretation
  - [ ] Error handling
- [ ] Backoff strategy
  - [ ] Exponential backoff
  - [ ] Adaptive intervals
  - [ ] Maximum limits
  - [ ] Recovery logic
- [ ] Progress handling
  - [ ] Progress bar updates
  - [ ] Phase descriptions
  - [ ] Time estimation
  - [ ] Smooth rendering
- [ ] Completion detection
  - [ ] All status types
  - [ ] Result extraction
  - [ ] Clean termination
  - [ ] Resource cleanup

## Test Scenarios

### Happy Path
1. Fast progress → 1s polls → Smooth updates → Complete
2. Slow progress → Adaptive polling → Efficient → Complete
3. Multi-phase → Phase transitions → Clear status → Complete
4. Quick completion → Immediate detection → Fast exit

### Error Cases
1. Network flaky → Backoff increases → Recovers → Continues
2. Server 500 → Retry with backoff → Eventually succeeds
3. Job fails → Detected quickly → Error returned
4. Timeout reached → Clean exit → Timeout error

### Edge Cases
1. Progress jumps → Handle gracefully → No visual glitches
2. Progress reverses → Show actual → Handle confusion
3. Very slow job → Keep polling → Patient waiting
4. Instant complete → One poll → Immediate return

## Performance Requirements

- Polling interval: 1 second nominal
- Network timeout: 5 seconds per request
- Backoff maximum: 10 seconds
- Progress render: 60 FPS smooth
- CPU usage: <5% while polling

## Progress Display States

### Active Progress
```
📊 Syncing: Git pull operations
   ▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░ 45% | 2.3 MB/s | ETA: 23s
```

### Stalled Warning
```
⚠️  Progress stalled for 30 seconds
   ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░ 62% | Waiting...
   Press 'c' to cancel or any key to continue waiting
```

### Phase Transitions
```
✓ Git sync completed
📊 Indexing: Processing changed files
   ▓▓▓░░░░░░░░░░░░░░░░░ 15% | 45 files/s | ETA: 1m 20s
```

## Network Error Handling

| Error Type | Initial Backoff | Max Backoff | Action |
|------------|----------------|-------------|--------|
| Connection timeout | 2s | 30s | Retry with backoff |
| 500 Server Error | 2s | 10s | Retry with backoff |
| 503 Service Unavailable | 5s | 30s | Retry with backoff |
| 401 Unauthorized | N/A | N/A | Refresh token, retry once |
| 404 Job Not Found | N/A | N/A | Fail immediately |

## Stall Detection Logic

```pseudocode
StallDetector:
    noProgressSeconds = 0
    lastProgress = 0

    def check(currentProgress):
        if currentProgress == lastProgress:
            noProgressSeconds++
            if noProgressSeconds == 15:
                showWarning("Progress slow...")
            if noProgressSeconds == 30:
                result = promptUser("Continue?")
                if not result:
                    cancelJob()
        else:
            noProgressSeconds = 0
            lastProgress = currentProgress
```

## Definition of Done

- [ ] Polling loop engine implemented
- [ ] Adaptive intervals working
- [ ] Backoff strategy tested
- [ ] Progress updates smooth
- [ ] Stall detection functional
- [ ] Network errors handled
- [ ] All status types detected
- [ ] Unit tests >90% coverage
- [ ] Integration tests with delays
- [ ] Performance requirements met
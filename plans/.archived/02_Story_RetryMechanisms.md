# Story 6.2: Retry Mechanisms

## Story Description

As a CIDX reliability system, I need intelligent retry mechanisms with exponential backoff, circuit breakers, and success tracking to automatically recover from transient failures while preventing cascade failures and resource exhaustion.

## Technical Specification

### Retry Strategy Implementation

```pseudocode
class RetryManager:
    def __init__(config: RetryConfig):
        self.maxRetries = config.maxRetries
        self.baseDelay = config.baseDelayMs
        self.maxDelay = config.maxDelayMs
        self.jitterFactor = config.jitterFactor
        self.circuitBreaker = CircuitBreaker(config)

    def executeWithRetry(operation: Callable, context: Context) -> Result:
        attempts = 0
        lastError = None

        while attempts < self.maxRetries:
            if self.circuitBreaker.isOpen():
                throw CircuitOpenError()

            try:
                result = operation()
                self.circuitBreaker.recordSuccess()
                return result

            catch error as TransientError:
                attempts++
                lastError = error
                self.circuitBreaker.recordFailure()

                if attempts < self.maxRetries:
                    delay = calculateBackoff(attempts)
                    sleep(delay)
                    notifyRetry(attempts, delay)

        throw MaxRetriesExceeded(lastError)

    def calculateBackoff(attempt: int) -> milliseconds:
        # Exponential backoff with jitter
        exponentialDelay = self.baseDelay * (2 ** attempt)
        boundedDelay = min(exponentialDelay, self.maxDelay)
        jitter = random(0, boundedDelay * self.jitterFactor)
        return boundedDelay + jitter
```

### Circuit Breaker Pattern

```pseudocode
class CircuitBreaker:
    states = CLOSED | OPEN | HALF_OPEN

    def __init__(config: CircuitConfig):
        self.failureThreshold = config.failureThreshold
        self.successThreshold = config.successThreshold
        self.timeout = config.timeoutMs
        self.state = CLOSED
        self.failures = 0
        self.successes = 0
        self.lastFailureTime = None

    def isOpen() -> bool:
        if self.state == OPEN:
            if (now() - self.lastFailureTime) > self.timeout:
                self.state = HALF_OPEN
                return false
            return true
        return false

    def recordSuccess():
        self.failures = 0
        if self.state == HALF_OPEN:
            self.successes++
            if self.successes >= self.successThreshold:
                self.state = CLOSED
                self.successes = 0

    def recordFailure():
        self.failures++
        self.lastFailureTime = now()
        if self.failures >= self.failureThreshold:
            self.state = OPEN
```

## Acceptance Criteria

### Exponential Backoff
```gherkin
Given a transient failure occurs
When implementing retry with backoff
Then the system should:
  - Start with base delay (1 second)
  - Double delay each retry
  - Cap at maximum delay (30 seconds)
  - Add random jitter (0-25%)
  - Prevent thundering herd
And space retries appropriately
```

### Circuit Breaker
```gherkin
Given repeated failures occur
When circuit breaker activates
Then the system should:
  - Open after 5 consecutive failures
  - Stop attempts when open
  - Wait timeout period (60 seconds)
  - Enter half-open state
  - Close after 3 successes
And prevent cascade failures
```

### Retry Limits
```gherkin
Given retry configuration
When executing with retries
Then the system should enforce:
  - Maximum retry count (3 default)
  - Total timeout limit (5 minutes)
  - Per-operation timeout (30 seconds)
  - Category-specific limits
  - User-configurable overrides
And respect all limits
```

### Success Tracking
```gherkin
Given retry operations
When tracking success metrics
Then the system should record:
  - Success on first attempt
  - Success after retries
  - Failure after all retries
  - Average retry count
  - Circuit breaker triggers
And provide visibility
```

### Selective Retry
```gherkin
Given different error types
When determining retry eligibility
Then the system should:
  - Retry network timeouts
  - Retry rate limit errors
  - NOT retry auth failures
  - NOT retry validation errors
  - NOT retry fatal errors
And apply correct logic
```

## Completion Checklist

- [ ] Exponential backoff
  - [ ] Backoff calculation
  - [ ] Jitter implementation
  - [ ] Delay boundaries
  - [ ] Configuration options
- [ ] Circuit breaker
  - [ ] State machine
  - [ ] Failure tracking
  - [ ] Timeout handling
  - [ ] Half-open logic
- [ ] Retry limits
  - [ ] Counter implementation
  - [ ] Timeout enforcement
  - [ ] Category limits
  - [ ] Override mechanism
- [ ] Success tracking
  - [ ] Metrics collection
  - [ ] Success rates
  - [ ] Retry statistics
  - [ ] Reporting interface

## Test Scenarios

### Happy Path
1. First attempt fails → Retry succeeds → Operation completes
2. Two failures → Third attempt works → Success logged
3. Circuit closed → Operations normal → High success rate
4. Backoff works → Delays increase → Eventually succeeds

### Error Cases
1. All retries fail → Max retries error → User notified
2. Circuit opens → Fast fail → Prevents overload
3. Timeout exceeded → Abort retries → Timeout error
4. Non-retryable error → No retry → Immediate failure

### Edge Cases
1. Retry during shutdown → Graceful abort → Clean exit
2. Clock skew → Handle time jumps → Correct delays
3. Zero retry config → Single attempt → No retries
4. Infinite retry request → Capped at max → Prevents hang

## Performance Requirements

- Retry decision: <1ms
- Backoff calculation: <0.1ms
- Circuit breaker check: <0.5ms
- Metrics update: <2ms
- Memory per retry context: <10KB

## Retry Configuration

```yaml
retry:
  default:
    maxRetries: 3
    baseDelayMs: 1000
    maxDelayMs: 30000
    jitterFactor: 0.25
    timeoutMs: 300000  # 5 minutes

  categories:
    network:
      maxRetries: 5
      baseDelayMs: 2000
      maxDelayMs: 60000

    embedding:
      maxRetries: 3
      baseDelayMs: 5000
      maxDelayMs: 30000

    git:
      maxRetries: 2
      baseDelayMs: 1000
      maxDelayMs: 10000

circuitBreaker:
  failureThreshold: 5
  successThreshold: 3
  timeoutMs: 60000  # 1 minute
  halfOpenTests: 3
```

## Retry Status Display

### Active Retry
```
⏳ Operation failed, retrying...
   Attempt 2 of 3
   Next retry in 4 seconds

   [▓▓▓▓▓▓░░░░░░░░░░░░░░] 4s
```

### Circuit Breaker Open
```
⚡ Circuit breaker activated
   Too many failures detected (5 in 30 seconds)
   Service will be checked again in 45 seconds

   Consider:
   • Checking service status
   • Reviewing network connectivity
   • Waiting before manual retry
```

### Max Retries Reached
```
❌ Operation failed after 3 attempts

Last error: Connection timeout (NET-001)
Total time spent: 37 seconds

Retry summary:
  Attempt 1: Failed - Connection timeout
  Attempt 2: Failed - Connection timeout
  Attempt 3: Failed - Connection timeout

Suggested actions:
  • Check network connectivity
  • Verify server is accessible
  • Try again in a few minutes
```

## Backoff Calculation Examples

| Attempt | Base Delay | Exponential | Capped | Jitter (0-25%) | Final Delay |
|---------|------------|-------------|---------|----------------|-------------|
| 1 | 1s | 2s | 2s | 0.3s | 2.3s |
| 2 | 1s | 4s | 4s | 0.7s | 4.7s |
| 3 | 1s | 8s | 8s | 1.2s | 9.2s |
| 4 | 1s | 16s | 16s | 2.8s | 18.8s |
| 5 | 1s | 32s | 30s | 4.5s | 30s (max) |

## Retry Decision Matrix

| Error Type | Retryable | Strategy | Max Attempts |
|------------|-----------|----------|--------------|
| Network timeout | Yes | Exponential backoff | 5 |
| Rate limit | Yes | Linear backoff | 3 |
| Server 500 | Yes | Exponential backoff | 3 |
| Auth failure | No | N/A | 0 |
| Validation error | No | N/A | 0 |
| Not found (404) | No | N/A | 0 |
| Conflict (409) | No | N/A | 0 |

## Definition of Done

- [ ] Exponential backoff implemented
- [ ] Jitter prevents thundering herd
- [ ] Circuit breaker pattern working
- [ ] Retry limits enforced
- [ ] Success metrics tracked
- [ ] Selective retry logic correct
- [ ] Configuration system flexible
- [ ] Unit tests >90% coverage
- [ ] Integration tests verify behavior
- [ ] Performance requirements met
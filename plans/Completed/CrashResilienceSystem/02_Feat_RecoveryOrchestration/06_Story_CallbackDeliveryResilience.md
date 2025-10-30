# Story 6: Callback Delivery Resilience

## User Story
**As a** system integrator
**I want** webhook callbacks to be delivered reliably despite crashes with structured logging
**So that** external systems always receive notifications and delivery operations are fully automated

## Business Value
Ensures external system integrations remain reliable by guaranteeing webhook delivery even when the server crashes during or after job completion. Fully automated retry with comprehensive structured logging maintains trust in the notification system and prevents missed critical events.

## Current State Analysis

**CURRENT BEHAVIOR**:
- **Callback Execution**: Fire-and-forget in `JobCallbackExecutor`
  - Location: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobCallbackExecutor.cs`
  - Single attempt only, no retry mechanism
- **NO QUEUING**: Callbacks not queued, executed immediately
- **NO PERSISTENCE**: No callback queue file exists
- **NO RETRY**: Failed callbacks are lost forever
- **CRASH IMPACT**: Callbacks lost if crash occurs before or during delivery

**CURRENT CALLBACK MODEL**:
```csharp
// JobCallback model (/claude-batch-server/src/ClaudeBatchServer.Core/Models/JobCallback.cs)
public class JobCallback
{
    public string Url { get; set; }
    public string Method { get; set; } = "POST";
    public Dictionary<string, string> Headers { get; set; }
    public string? Body { get; set; }
    // NO delivery status tracking
    // NO retry count
    // NO timestamp tracking
}
```

**CURRENT EXECUTION FLOW**:
```csharp
// JobCallbackExecutor.cs - simplified
public async Task ExecuteCallbacksAsync(Job job)
{
    foreach (var callback in job.Callbacks)
    {
        try
        {
            // Single HTTP request, no retry
            await _httpClient.SendAsync(request);
            // Success or failure - callback lost either way
        }
        catch (Exception ex)
        {
            // Log error, callback lost
        }
    }
}
```

**IMPLEMENTATION REQUIRED**:
- **CREATE** `callbacks.queue.json` file format
- **BUILD** `CallbackQueuePersistenceService` - NEW CLASS
- **BUILD** Callback queue persistence before execution
- **BUILD** Retry mechanism with exponential backoff (30s, 2min, 10min)
- **BUILD** Callback execution status tracking (Gap #9)
- **BUILD** Recovery logic to resume pending callbacks on startup
- **MODIFY** `JobCallbackExecutor` to use persistent queue instead of fire-and-forget

**INTEGRATION POINTS**:
1. Job completion handler - Enqueue callbacks instead of immediate execution
2. `JobCallbackExecutor` - Dequeue and execute with retry
3. Startup orchestration (Story 3) - Resume pending callbacks on startup
4. Callback status tracking - Update delivery status in queue file

**FILES TO MODIFY**:
- `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobCallbackExecutor.cs` (add queue-based execution)
- Create new `/claude-batch-server/src/ClaudeBatchServer.Core/Services/CallbackQueuePersistenceService.cs`

**CALLBACK QUEUE FILE LOCATION**:
- `/var/lib/claude-batch-server/claude-code-server-workspace/callbacks.queue.json`

**EFFORT**: 2-3 days

## Technical Approach
Implement durable webhook queue that persists pending callbacks to file (`callbacks.queue.json`), automatically retries failed deliveries with exponential backoff (30s, 2min, 10min), survives server crashes, and logs all operations to startup log.

### Components
- `CallbackQueue`: Persistent callback storage (file-based)
- `DeliveryService`: Automatic reliable delivery engine
- `RetryScheduler`: Exponential backoff logic (30s, 2min, 10min)
- `StartupLogger`: Structured logging of callback operations

## Acceptance Criteria

```gherkin
# ========================================
# CATEGORY: File-Based Queue Structure
# ========================================

Scenario: Callback queue file creation
  Given callback needs to be queued
  When CallbackQueue initializes
  Then queue file created at {workspace}/callbacks.queue.json
  And file contains: callbacks array with entries
  And atomic write operation used

Scenario: Callback entry format
  Given job completes and triggers webhook
  When callback is queued
  Then entry contains: callbackId (UUID), jobId, url, payload, timestamp, attempts, status
  And status = "pending"
  And attempts = 0
  And timestamp in ISO 8601 UTC format

Scenario: Multiple callbacks in queue
  Given 5 jobs complete and trigger callbacks
  When all callbacks queued
  Then callbacks.queue.json contains 5 entries
  And each entry has unique callbackId
  And queue persisted atomically

Scenario: Callback queue file atomic write
  Given callback queue updated
  When file is written
  Then data written to callbacks.queue.json.tmp first
  And FileStream.FlushAsync() called
  And file renamed to callbacks.queue.json atomically
  And corruption prevention ensured

# ========================================
# CATEGORY: Exponential Backoff Timing (30s, 2min, 10min)
# ========================================

Scenario: First delivery attempt (immediate)
  Given callback queued
  When delivery service processes queue
  Then first delivery attempt executes immediately
  And no delay before attempt 1

Scenario: Second delivery attempt after 30 seconds
  Given first attempt fails
  When retry is scheduled
  Then second attempt executes after 30 second delay
  And delay calculated correctly

Scenario: Third delivery attempt after 2 minutes
  Given second attempt fails
  When retry is scheduled
  Then third attempt executes after 2 minute delay (120 seconds)
  And cumulative delay: 30s + 2min = 2.5min

Scenario: Fourth delivery attempt after 10 minutes
  Given third attempt fails
  When retry is scheduled
  Then fourth attempt executes after 10 minute delay (600 seconds)
  And cumulative delay: 30s + 2min + 10min = 12.5min

Scenario: Exponential backoff calculation
  Given callback with attempts = N
  When next retry delay calculated
  Then delay = [30s, 2min, 10min][N-1]
  And exact timing enforced

Scenario: Retry timing boundary enforcement
  Given callback retry scheduled
  When delay timer expires
  Then delivery executes immediately
  And timing precision within 1 second

# ========================================
# CATEGORY: Retry Exhaustion (3 Attempts)
# ========================================

Scenario: Successful delivery on first attempt
  Given callback queued
  When delivery executes
  And HTTP 200 response received
  Then callback status = "completed"
  And callback removed from queue
  And no retries needed

Scenario: Successful delivery on second attempt
  Given first attempt fails
  And second attempt succeeds
  When delivery completes
  Then callback status = "completed"
  And callback removed from queue
  And attempts = 2

Scenario: Retry exhaustion after 3 attempts
  Given callback fails on attempt 1, 2, and 3
  When third attempt fails
  Then callback status = "failed"
  And callback moved to failed_callbacks.json
  And callback removed from active queue
  And error logged with full context

Scenario: Retry limit configuration
  Given retry policy maxRetries = 3
  When callback processed
  Then exactly 3 attempts made (1 initial + 2 retries)
  And no fourth attempt

Scenario: Failed callback tracking
  Given callback exhausted retries
  When moved to failed queue
  Then failed_callbacks.json contains: callbackId, jobId, url, attempts, lastError, failedAt
  And admin notification sent

# ========================================
# CATEGORY: Callback Execution Status Tracking
# ========================================

Scenario: Pending callback status
  Given callback queued
  When status checked
  Then status = "pending"
  And attempts = 0
  And nextRetryAt = null

Scenario: In-flight callback status
  Given callback currently being delivered
  When status checked
  Then status = "in_flight"
  And attempts incremented
  And timestamp updated

Scenario: Completed callback status
  Given callback delivered successfully
  When status checked
  Then status = "completed"
  And completedAt timestamp set
  And callback removed from active queue

Scenario: Failed callback status
  Given callback exhausted retries
  When status checked
  Then status = "failed"
  And attempts = 3
  And lastError contains error details

Scenario: Retry-pending callback status
  Given callback failed and waiting for retry
  When status checked
  Then status = "pending"
  And attempts incremented
  And nextRetryAt timestamp set (30s, 2min, or 10min in future)

# ========================================
# CATEGORY: Queue File Corruption Recovery
# ========================================

Scenario: Malformed JSON in queue file
  Given callbacks.queue.json contains invalid JSON
  When CallbackQueue loads file
  Then JsonException thrown
  And corruption detected
  And queue file backed up to callbacks.queue.json.corrupted.{timestamp}
  And empty queue initialized

Scenario: Truncated queue file
  Given callbacks.queue.json is truncated (incomplete JSON)
  When queue loads
  Then deserialization fails
  And corruption handling triggered
  And corrupted file backed up
  And fresh queue initialized

Scenario: Missing required fields in callback entry
  Given callback entry missing "url" field
  When queue processes entry
  Then validation fails
  And entry skipped with warning logged
  And processing continues with next entry

Scenario: Invalid data types in callback entry
  Given callback entry has "attempts": "not_a_number"
  When deserialization occurs
  Then JsonException thrown
  And entry skipped
  And warning logged

Scenario: Empty queue file
  Given callbacks.queue.json exists with 0 bytes
  When queue loads
  Then deserialization fails
  And empty queue initialized
  And system continues normally

# ========================================
# CATEGORY: Concurrent Callback Execution
# ========================================

Scenario: Concurrent delivery of multiple callbacks
  Given 10 callbacks in queue
  When delivery service processes queue
  Then callbacks delivered in parallel (up to concurrency limit)
  And each delivery has independent HTTP client
  And no interference between deliveries

Scenario: Queue file update serialization
  Given multiple callbacks completing simultaneously
  When queue file updated
  Then updates serialized (SemaphoreSlim lock)
  And file integrity maintained
  And no corruption occurs

Scenario: Callback processing with lock
  Given callback being processed
  When queue modification attempted
  Then SemaphoreSlim lock prevents concurrent access
  And queue consistency ensured

Scenario: Concurrent delivery failure handling
  Given 5 callbacks fail simultaneously
  When retry scheduling occurs
  Then all retries scheduled correctly
  And queue file updated atomically
  And no race conditions

# ========================================
# CATEGORY: Persistence Across Crashes
# ========================================

Scenario: Callback recovery on startup
  Given 5 pending callbacks in queue file
  And server crashed before delivery
  When server restarts
  Then CallbackQueue loads callbacks.queue.json
  And all 5 callbacks recovered
  And delivery attempts resume

Scenario: In-flight callback recovery
  Given callback marked "in_flight" when server crashed
  When server restarts
  Then callback reverted to "pending"
  And delivery reattempted
  And no duplicate delivery (idempotency)

Scenario: Retry timing preservation
  Given callback has nextRetryAt = 5 minutes in future
  And server crashes
  When server restarts
  Then nextRetryAt preserved
  And delivery waits until correct time
  And backoff timing respected

Scenario: Queue file persistence guarantee
  Given callback queued
  When server crashes immediately
  Then callback persisted to disk (atomic write)
  And recovery loads callback on restart

# ========================================
# CATEGORY: Error Scenarios
# ========================================

Scenario: HTTP connection timeout
  Given callback delivery attempted
  And HTTP request times out (30 second timeout)
  When timeout occurs
  Then delivery marked as failed attempt
  And retry scheduled with exponential backoff
  And error logged: "Connection timeout"

Scenario: HTTP 5xx server error
  Given callback delivery attempted
  And server returns HTTP 503
  When response received
  Then delivery marked as failed attempt
  And retry scheduled
  And error logged with status code

Scenario: HTTP 4xx client error (non-retryable)
  Given callback delivery attempted
  And server returns HTTP 400 (bad request)
  When response received
  Then delivery marked as permanent failure
  And no retry scheduled
  And callback moved to failed queue immediately

Scenario: DNS resolution failure
  Given callback URL has invalid domain
  When delivery attempted
  Then DNS resolution fails
  And delivery marked as failed attempt
  And retry scheduled

Scenario: Network unreachable
  Given network connectivity lost
  When delivery attempted
  Then connection error thrown
  And delivery marked as failed attempt
  And retry scheduled

Scenario: Disk full during queue write
  Given disk space exhausted
  When queue file update attempted
  Then IOException thrown
  And error logged
  And delivery continues (queue update non-critical)

# ========================================
# CATEGORY: Edge Cases
# ========================================

Scenario: Callback with empty payload
  Given callback has empty payload {}
  When delivery attempted
  Then HTTP POST with empty JSON body
  And delivery proceeds normally

Scenario: Callback with large payload (>1MB)
  Given callback payload is 2MB JSON
  When delivery attempted
  Then delivery proceeds normally
  And HTTP client handles large body

Scenario: Callback with special characters in URL
  Given callback URL contains query parameters with special chars
  When delivery attempted
  Then URL properly encoded
  And delivery succeeds

Scenario: Callback to localhost
  Given callback URL is http://localhost:8080/webhook
  When delivery attempted
  Then delivery allowed (no localhost blocking)
  And request sent normally

Scenario: Callback with custom headers
  Given callback configured with custom headers
  When delivery attempted
  Then headers included in HTTP request
  And delivery proceeds

# ========================================
# CATEGORY: Idempotency and Duplicate Prevention
# ========================================

Scenario: Duplicate prevention with callbackId
  Given callback has unique callbackId
  When delivery succeeds
  Then callbackId tracked in delivered_callbacks.json
  And future duplicate callbackId rejected

Scenario: Idempotent retry after crash
  Given callback delivered successfully
  And server crashes before queue update
  When server restarts
  Then callback reattempted
  And webhook endpoint receives duplicate
  And endpoint handles idempotency (application-level)

Scenario: Callback deduplication check
  Given callback with callbackId already delivered
  When duplicate callback queued
  Then duplicate detected
  And callback skipped
  And warning logged

# ========================================
# CATEGORY: High-Volume Scenarios
# ========================================

Scenario: Queue with 100 pending callbacks
  Given 100 callbacks in queue
  When delivery service processes queue
  Then all callbacks processed
  And delivery completes within 5 minutes
  And queue file remains under 1MB

Scenario: Burst of 50 callbacks
  Given 50 jobs complete simultaneously
  When all trigger callbacks
  Then all 50 callbacks queued atomically
  And queue file updated correctly
  And no callbacks lost

Scenario: Callback delivery at 10/second rate
  Given callbacks delivered at high rate
  When delivery executes
  Then HTTP clients handle concurrency
  And queue updates serialized
  And system remains stable

# ========================================
# CATEGORY: Observability and Logging
# ========================================

Scenario: Callback recovery logging on startup
  Given callback recovery completes
  When startup log is written
  Then entry contains: component="CallbackDelivery"
  And operation="callback_recovery_completed"
  And pending_callbacks_recovered count
  And callbacks_delivered count
  And callbacks_failed count
  And delivery_attempts_total
  And retry_backoff_used array

Scenario: Callback queuing logging
  Given callback queued
  When operation completes
  Then info logged: "Callback queued: {callbackId}, jobId: {jobId}"
  And callback URL logged
  And queue size logged

Scenario: Delivery attempt logging
  Given callback delivery attempted
  When attempt executes
  Then info logged: "Callback delivery attempt {N}: {callbackId}"
  And attempt number logged
  And URL logged
  And response status logged

Scenario: Retry scheduling logging
  Given callback retry scheduled
  When scheduling occurs
  Then info logged: "Callback retry scheduled: {callbackId}, nextRetry: {timestamp}, delay: {duration}"
  And backoff timing logged

Scenario: Delivery success logging
  Given callback delivered successfully
  When delivery completes
  Then info logged: "Callback delivered successfully: {callbackId}, attempts: {N}"
  And total attempts logged
  And response status logged

Scenario: Delivery failure logging
  Given callback exhausted retries
  When failure recorded
  Then error logged: "Callback delivery failed after {N} attempts: {callbackId}"
  And error details logged
  And last HTTP status logged
  And failure reason logged
```

## Manual E2E Test Plan

**Prerequisites**:
- Claude Server with webhooks configured
- Webhook endpoint (webhook.site)
- Admin token

**Test Steps**:

1. **Configure Webhook**:
   ```bash
   WEBHOOK_URL="https://webhook.site/unique-id"

   curl -X POST https://localhost/api/admin/webhooks \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "url": "'$WEBHOOK_URL'",
       "events": ["job.completed"],
       "retryPolicy": {"maxRetries": 5}
     }'
   ```
   **Expected**: Webhook configured
   **Verify**: Configuration saved

2. **Create Jobs to Trigger Webhooks**:
   ```bash
   for i in {1..3}; do
     curl -X POST https://localhost/api/jobs \
       -H "Authorization: Bearer $USER_TOKEN" \
       -H "Content-Type: application/json" \
       -d '{"prompt": "Quick task", "repository": "test-repo"}'
   done
   ```
   **Expected**: Jobs complete, webhooks queued
   **Verify**: Pending deliveries

3. **Crash Before Delivery**:
   ```bash
   # Check pending webhooks
   curl https://localhost/api/admin/webhooks/pending \
     -H "Authorization: Bearer $ADMIN_TOKEN"

   # Crash server
   curl -X POST https://localhost/api/admin/test/crash \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -d '{"type": "immediate"}'
   ```
   **Expected**: Server crashes with pending webhooks
   **Verify**: Webhooks not delivered

4. **Restart and Verify Recovery**:
   ```bash
   sudo systemctl start claude-batch-server

   # Check webhook recovery
   curl https://localhost/api/admin/webhooks/recovered \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```
   **Expected**: Webhooks recovered
   **Verify**: Delivery resuming

5. **Monitor Delivery**:
   ```bash
   # Check webhook.site for deliveries
   curl "$WEBHOOK_URL/requests"

   # Check server-side status
   curl https://localhost/api/admin/webhooks/delivery-log \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```
   **Expected**: Webhooks delivered
   **Verify**: No duplicates

**Success Criteria**:
- ✅ Webhooks persisted durably
- ✅ Recovery after crash works
- ✅ Delivery retry logic functional
- ✅ No duplicate deliveries
- ✅ Tracking provides visibility

## Observability Requirements

**Structured Logging** (all logged to startup log and application log):
- Webhook queuing (job completion triggers)
- Automatic delivery attempts
- Automatic retry scheduling with exponential backoff
- Recovery operations on startup
- Delivery success/failure with error context

**Logged Data Fields (Startup Log)**:
```json
{
  "component": "CallbackDelivery",
  "operation": "callback_recovery_completed",
  "timestamp": "2025-10-15T10:00:30.123Z",
  "pending_callbacks_recovered": 5,
  "callbacks_delivered": 4,
  "callbacks_failed": 1,
  "delivery_attempts_total": 12,
  "retry_backoff_used": ["30s", "2min", "10min"]
}
```

**Metrics** (logged to structured log):
- Webhooks queued/delivered (success rate >95%)
- Delivery success rate (target: >99% with retries)
- Average retry count
- Recovery frequency
- Failed delivery reasons

## Definition of Done
- [ ] Implementation complete with TDD
- [ ] Manual E2E test executed successfully by Claude Code
- [ ] Webhook persistence works via callbacks.queue.json
- [ ] Automatic recovery delivers webhooks
- [ ] No duplicates sent (idempotency checks)
- [ ] Exponential backoff works (30s, 2min, 10min)
- [ ] Structured logging provides complete visibility
- [ ] Code reviewed and approved
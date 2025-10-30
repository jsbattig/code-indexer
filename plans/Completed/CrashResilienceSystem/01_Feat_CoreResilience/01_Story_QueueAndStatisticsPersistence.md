# Story 1: Queue and Statistics Persistence with Automated Recovery

## User Story
**As a** system administrator
**I want** queue state and resource statistics persisted durably with automated recovery and comprehensive logging
**So that** no jobs are lost during crashes, capacity planning data survives restarts, and I can review all recovery operations through startup logs

## Business Value
Ensures business continuity by preserving all queued jobs and critical resource usage history across system crashes, preventing work loss and maintaining service reliability. Accurate capacity planning continues uninterrupted. Fully automated recovery with structured logging provides complete visibility without manual intervention.

## Current State Analysis

**CURRENT BEHAVIOR**:
- **Queue**: In-memory only using `ConcurrentQueue<Guid> _jobQueue`
  - Location: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobService.cs` line 44
  - Enqueue operation: `JobService.EnqueueJobAsync()` line 129
  - Dequeue operation: Background worker in `JobService` line 426
- **Statistics**: Throttled persistence with 2-second minimum interval
  - Location: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/ResourceMonitoring/Statistics/ResourceStatisticsService.cs` line 19
  - `MinPersistInterval = TimeSpan.FromSeconds(2)` - creates data loss window
  - Save method: `SaveAsync()` lines 147-155 with direct file writes (UNSAFE)
- **PERSISTENCE**: None for queue, throttled for statistics
- **CRASH IMPACT**: All queued jobs lost, recent statistics updates (within 2-second window) lost

**DATA STRUCTURES**:
```csharp
// Queue (in-memory only - NO PERSISTENCE)
private readonly ConcurrentQueue<Guid> _jobQueue = new();

// Statistics (throttled saves - DATA LOSS WINDOW)
private static readonly TimeSpan MinPersistInterval = TimeSpan.FromSeconds(2);
private DateTime _lastPersistTime = DateTime.MinValue;
```

**IMPLEMENTATION REQUIRED**:
- **BUILD** `QueuePersistenceService` - NEW CLASS
- **BUILD** `WriteAheadLogger` - NEW CLASS (file-based, NOT database)
- **BUILD** `QueueRecoveryEngine` - NEW CLASS
- **BUILD** `StatisticsPersistenceService` - NEW CLASS (or enhance existing)
- **MODIFY** `JobService.InitializeAsync()` to call recovery on startup (lines 101-180)
- **MODIFY** `JobService.EnqueueJobAsync()` to log to WAL (line 129)
- **MODIFY** Background worker to log dequeue operations to WAL (line 426)
- **DECISION** on statistics: Remove throttling OR accept 2-second data loss window

**INTEGRATION POINTS**:
1. `JobService.EnqueueJobAsync()` - Hook WAL write after in-memory enqueue
2. `JobService` background worker - Hook WAL write after in-memory dequeue
3. `JobService.InitializeAsync()` - Add queue recovery before worker starts
4. `ResourceStatisticsService.RecordJobCompletion()` - Make immediate or document throttling

**FILES TO MODIFY**:
- `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobService.cs`
- `/claude-batch-server/src/ClaudeBatchServer.Core/Services/ResourceMonitoring/Statistics/ResourceStatisticsService.cs`

**TRAFFIC PROFILE**: VERY low traffic server (few jobs per minute maximum)

**EFFORT**: 3-4 days (WAL implementation straightforward for low traffic, focus on recovery not performance)

## Technical Approach
Implement unified durable persistence for queue state and resource statistics using write-ahead logging for queue operations, real-time statistics persistence on every change, atomic state updates, and fully automated recovery on every startup. Both subsystems share atomic file operation patterns and comprehensive structured logging.

### Components
- `QueuePersistenceService`: Durable queue storage with atomic file operations
- `WriteAheadLogger`: File-based transaction log for queue ops (NOT database)
- `QueueRecoveryEngine`: Fully automated queue state restoration logic
- `StatisticsPersistenceService`: Real-time statistics persistence on every change
- `StatisticsRecoveryService`: Statistics load and validation on startup
- `StartupLogger`: Structured logging of all recovery operations
- `AtomicFileWriter`: Temp-file + rename pattern for corruption prevention (shared)

## Part A: Queue Persistence with Write-Ahead Logging

### Write-Ahead Log (WAL) Specification

**CRITICAL**: WAL is **FILE-BASED**, not database. Ensures in-memory changes are written to disk quasi-realtime.

**WAL File Structure**:
- **Location**: `/var/lib/claude-batch-server/claude-code-server-workspace/queue.wal`
- **Format**: Append-only text file, one operation per line
- **Entry Format**: JSON lines (JSONL)
  ```json
  {"timestamp":"2025-10-15T10:30:00.123Z","op":"enqueue","jobId":"abc123","data":{...}}
  {"timestamp":"2025-10-15T10:30:05.456Z","op":"dequeue","jobId":"abc123"}
  {"timestamp":"2025-10-15T10:30:10.789Z","op":"status_change","jobId":"def456","from":"queued","to":"running"}
  ```

**Queue Operations Logged**:
- `enqueue`: Job added to queue (includes full job JSON)
- `dequeue`: Job removed from queue
- `status_change`: Job status transition
- `position_update`: Queue position changes

**Write Pattern**:
- **Timing**: Immediately after in-memory state change (quasi-realtime)
- **Mechanism**: Append to WAL file using atomic operations
- **Flush**: After each write (ensure data on disk)
- **Performance**: <5ms per operation

**Checkpoint Strategy** (Simplified for Low Traffic):
- **Trigger**: Every 100 operations OR every 5 minutes (whichever first)
- **Action**: Write complete queue snapshot to `queue-snapshot.json`
- **WAL Truncation**: After successful checkpoint, truncate WAL file
- **Recovery**: Read last snapshot + replay WAL entries since checkpoint
- **Rationale**: Low traffic (few jobs/minute) means checkpoints happen infrequently anyway

**WAL Rotation** (Simplified):
- **Size Limit**: 10MB maximum WAL file size (sufficient for low traffic)
- **Action**: Force checkpoint when limit reached
- **Reality**: Will likely never hit limit with low traffic

**Example WAL Lifecycle**:
```
Time 0:00 - Queue starts, WAL empty
Time 0:01 - Job enqueued → WAL: 1 entry
Time 0:02 - Job enqueued → WAL: 2 entries
...
Time 0:30 - 30 seconds elapsed OR 1000 ops → CHECKPOINT
          - Write queue-snapshot.json (complete state)
          - Truncate queue.wal (WAL now empty)
          - Continue operations
Time 0:31 - Job enqueued → WAL: 1 entry (fresh WAL)
```

**Recovery Algorithm**:
```csharp
async Task RecoverQueue()
{
    // STEP 1: Load last checkpoint
    var snapshot = await LoadSnapshot("queue-snapshot.json");
    var queue = new Queue<Job>(snapshot.Jobs);

    // STEP 2: Replay WAL entries since checkpoint
    var walEntries = await ReadWAL("queue.wal");
    foreach (var entry in walEntries)
    {
        switch (entry.Op)
        {
            case "enqueue":
                queue.Enqueue(entry.Data);
                break;
            case "dequeue":
                queue.Dequeue();
                break;
            case "status_change":
                UpdateJobStatus(queue, entry.JobId, entry.To);
                break;
        }
    }

    // STEP 3: Restore in-memory state
    _inMemoryQueue = queue;
}
```

## Part B: Resource Statistics Persistence

### Real-Time Persistence Specification

**CRITICAL**: Statistics are persisted **immediately** when they change in RAM (not periodic/batched).

**Trigger Points** (when to save):
- Job completes → Resource usage recorded → **SAVE IMMEDIATELY**
- P90 calculated → New P90 value → **SAVE IMMEDIATELY**
- Resource allocation changes → New allocation data → **SAVE IMMEDIATELY**
- Any modification to `ResourceStatisticsData` → **SAVE IMMEDIATELY**

**File Location**: `/var/lib/claude-batch-server/claude-code-server-workspace/statistics.json`

**File Format**:
```json
{
  "version": "1.0",
  "lastUpdated": "2025-10-15T10:30:45.123Z",
  "statistics": {
    "totalJobsProcessed": 1523,
    "resourceUsageHistory": [
      {
        "timestamp": "2025-10-15T10:00:00Z",
        "cpu": 45.2,
        "memory": 2048,
        "duration": 120
      }
    ],
    "p90Estimates": {
      "cpu": 78.5,
      "memory": 4096,
      "duration": 300
    },
    "capacityMetrics": {
      "maxConcurrent": 10,
      "averageQueueTime": 45
    }
  }
}
```

**Hook into ResourceStatisticsService**:
```csharp
// In ResourceStatisticsService.cs
public async Task RecordJobCompletion(Job job, ResourceUsage usage)
{
    await _lock.WaitAsync(); // Serialize statistics updates
    try
    {
        // Update in-memory statistics
        _statistics.TotalJobsProcessed++;
        _statistics.ResourceUsageHistory.Add(usage);
        _statistics.RecalculateP90();

        // IMMEDIATELY persist to disk (within lock)
        await _persistenceService.SaveStatisticsAsync(_statistics);
    }
    finally
    {
        _lock.Release();
    }
}
```

### Serialization - Concurrent Access

**Question**: Can multiple threads modify statistics simultaneously?

**Analysis**:
- Job completion handlers run concurrently (multiple jobs finishing)
- Each modifies `ResourceStatisticsData`
- Concurrent writes possible → **NEED SERIALIZATION**

**Solution**: Per-statistics lock (SemaphoreSlim)

```csharp
public class ResourceStatisticsService
{
    private readonly ResourceStatisticsData _statistics;
    private readonly SemaphoreSlim _lock = new(1, 1);
    private readonly StatisticsPersistenceService _persistenceService;

    public async Task RecordJobCompletion(Job job, ResourceUsage usage)
    {
        await _lock.WaitAsync(); // Serialize statistics updates
        try
        {
            // Update in-memory statistics
            _statistics.TotalJobsProcessed++;
            _statistics.ResourceUsageHistory.Add(usage);
            _statistics.RecalculateP90();

            // IMMEDIATELY persist to disk (within lock)
            await _persistenceService.SaveStatisticsAsync(_statistics);
        }
        finally
        {
            _lock.Release();
        }
    }
}
```

**Result**:
- Only one thread modifies statistics at a time
- Statistics file write serialized automatically
- No race conditions, no corruption

### Statistics Recovery Logic

**On Startup**:
```csharp
async Task RecoverStatistics()
{
    var filePath = Path.Combine(_workspace, "statistics.json");

    if (!File.Exists(filePath))
    {
        _logger.LogInformation("No persisted statistics found, starting fresh");
        return new ResourceStatisticsData();
    }

    try
    {
        var json = await File.ReadAllTextAsync(filePath);
        var stats = JsonSerializer.Deserialize<ResourceStatisticsData>(json);

        _logger.LogInformation("Recovered statistics: {JobCount} jobs processed, P90 CPU: {P90}",
            stats.TotalJobsProcessed, stats.P90Estimates.Cpu);

        return stats;
    }
    catch (Exception ex)
    {
        _logger.LogError(ex, "Failed to recover statistics, starting fresh");

        // If corruption detected, backup the corrupted file
        File.Move(filePath, $"{filePath}.corrupted.{DateTime.UtcNow:yyyyMMddHHmmss}");

        return new ResourceStatisticsData();
    }
}
```

## Shared Infrastructure: Atomic File Operations

All file writes MUST use the temp-file + atomic-rename pattern to prevent corruption:

**Pattern**:
1. Write data to temporary file: `{filename}.tmp`
2. Flush buffers to ensure data on physical disk
3. Atomic rename: `{filename}.tmp` → `{filename}` (overwrites existing)
4. Cleanup: Remove orphaned `.tmp` files on startup

**Implementation Requirements**:
- Apply to: Queue snapshot, statistics, ALL persistent data
- Filesystem guarantees: Leverage OS atomic rename (Linux `rename()`, Windows `MoveFileEx`)
- Error handling: If crash before rename, old file remains valid; if crash after, new file is valid
- Performance: Negligible overhead (<5ms per write including flush)

**Code Example**:
```csharp
public async Task SaveAsync<T>(string filename, T data)
{
    var finalPath = Path.Combine(_workspace, filename);
    var tempPath = finalPath + ".tmp";

    try
    {
        // STEP 1: Write to temp file
        var jsonContent = JsonSerializer.Serialize(data, ...);
        await File.WriteAllTextAsync(tempPath, jsonContent);

        // STEP 2: Flush to disk (critical for crash safety)
        using (var fs = new FileStream(tempPath, FileMode.Open, FileAccess.Read))
        {
            await fs.FlushAsync();
        }

        // STEP 3: Atomic rename (file now visible with complete data)
        File.Move(tempPath, finalPath, overwrite: true);
    }
    catch
    {
        if (File.Exists(tempPath)) File.Delete(tempPath);
        throw;
    }
}
```

**Recovery Considerations**:
- On startup: Delete all orphaned `*.tmp` files (incomplete writes from crash)
- Validation: Files are either complete or don't exist (never partial)
- No locking needed for queue files: Queue serialization prevents concurrent writes
- Statistics locking: SemaphoreSlim ensures serialized statistics writes

## Acceptance Criteria

```gherkin
# ========================================
# CATEGORY: Atomic File Operations
# ========================================

Scenario: Temp file creation for queue snapshot
  Given a queue snapshot write is initiated
  When the temp file is created
  Then the file is created with .tmp extension
  And the file path is {workspace}/queue-snapshot.json.tmp
  And the file is writable

Scenario: Temp file flush to disk before rename
  Given queue snapshot data written to temp file
  When the flush operation is executed
  Then FileStream.FlushAsync() completes successfully
  And data is physically written to disk
  And OS buffer cache is synced

Scenario: Atomic rename from temp to final file
  Given temp file contains complete queue snapshot
  When File.Move(tempPath, finalPath, overwrite: true) is called
  Then rename operation is atomic (OS-level guarantee)
  And final file appears with complete data
  And old final file (if exists) is replaced atomically

Scenario: Cleanup on write failure before rename
  Given temp file write fails with exception
  When exception handler executes
  Then temp file is deleted
  And final file remains unchanged (old state preserved)
  And exception is propagated to caller

Scenario: Orphaned temp file cleanup on startup
  Given orphaned .tmp files exist from previous crash
  When startup cleanup runs
  Then all *.tmp files in workspace are deleted
  And only valid state files remain

Scenario: Concurrent temp file operations
  Given multiple threads write different files simultaneously
  When each uses unique .tmp filename
  Then no file conflicts occur
  And each atomic rename succeeds independently

# ========================================
# CATEGORY: Write-Ahead Log (WAL) Operations
# ========================================

Scenario: WAL append with immediate flush
  Given an enqueue operation modifies queue state
  When WAL entry is written
  Then entry is appended to queue.wal
  And FileStream.FlushAsync() is called
  And write completes within 5ms
  And entry is persisted to disk

Scenario: WAL checkpoint trigger after 100 operations (low-traffic threshold)
  Given WAL contains 999 entries
  When the 1000th operation is logged
  Then checkpoint is triggered automatically
  And complete queue snapshot written to queue-snapshot.json
  And WAL file is truncated (emptied)
  And sequence number continuity preserved

Scenario: WAL checkpoint trigger after 5 minutes (low-traffic interval)
  Given WAL contains 50 entries
  And 30 seconds elapsed since last checkpoint
  When the next operation is logged
  Then checkpoint is triggered automatically
  And WAL contains only operations since checkpoint

Scenario: WAL checkpoint sequence number continuity
  Given WAL checkpoint at operation 5000
  When checkpoint snapshot is written
  Then snapshot contains sequence numbers 1-5000
  And next WAL entry has sequence number 5001
  And no sequence gaps exist

Scenario: WAL replay after crash
  Given queue-snapshot.json exists (last checkpoint)
  And queue.wal contains 15 entries since checkpoint
  When recovery executes
  Then snapshot loaded first
  And all 15 WAL entries replayed in order
  And final queue state matches expected state

Scenario: WAL rotation at 10MB size limit (low-traffic sufficient)
  Given WAL file size reaches 99MB
  When next operation would exceed 100MB
  Then checkpoint forced immediately
  And WAL renamed to queue.wal.old
  And new empty WAL created
  And old WAL kept until checkpoint completes

Scenario: WAL recovery from corrupted snapshot
  Given queue-snapshot.json is corrupted (invalid JSON)
  And queue.wal contains complete operation history
  When recovery executes
  Then snapshot corruption detected
  And WAL reconstruction initiated
  And queue rebuilt from WAL entries only
  And recovery succeeds

# ========================================
# CATEGORY: Concurrency and Serialization
# ========================================

Scenario: Statistics SemaphoreSlim lock acquisition
  Given ResourceStatisticsService with SemaphoreSlim(1,1)
  When RecordJobCompletion() is called
  Then SemaphoreSlim.WaitAsync() is called
  And only one thread enters critical section
  And lock is held during entire update + persist

Scenario: Statistics SemaphoreSlim lock release
  Given statistics update completes successfully
  When finally block executes
  Then SemaphoreSlim.Release() is called
  And lock is available for next thread

Scenario: Statistics concurrent access serialization
  Given 10 jobs complete simultaneously
  When all threads call RecordJobCompletion()
  Then updates execute serially (one at a time)
  And no race conditions occur
  And statistics.json reflects all 10 updates
  And file is never corrupted

Scenario: Statistics lock timeout handling
  Given a thread holds statistics lock
  And lock is held for >30 seconds (abnormal)
  When another thread calls WaitAsync()
  Then lock acquisition waits (no timeout configured)
  And operation eventually succeeds when lock released
  And no deadlock occurs

Scenario: Queue serialization without explicit lock
  Given queue operations execute on single thread
  When enqueue/dequeue operations occur
  Then no explicit locking needed
  And WAL writes are inherently serialized
  And checkpoint operations are serialized

# ========================================
# CATEGORY: Corruption Handling
# ========================================

Scenario: Malformed JSON in queue snapshot
  Given queue-snapshot.json contains invalid JSON syntax
  When recovery attempts to load snapshot
  Then JsonException is caught
  And WAL reconstruction initiated
  And queue rebuilt from WAL entries
  And corrupted file backed up with timestamp

Scenario: Truncated statistics file
  Given statistics.json is truncated (incomplete JSON)
  When StatisticsRecoveryService loads file
  Then deserialization fails
  And corruption detected
  And corrupted file moved to statistics.json.corrupted.{timestamp}
  And fresh statistics object initialized

Scenario: Missing required fields in WAL entry
  Given WAL entry JSON missing "jobId" field
  When WAL replay processes entry
  Then entry validation fails
  And entry is skipped with warning logged
  And replay continues with next entry
  And partial recovery succeeds

Scenario: Invalid data types in statistics
  Given statistics.json has "totalJobsProcessed": "invalid_string"
  When deserialization occurs
  Then JsonException thrown
  And corruption handling triggered
  And statistics start fresh

Scenario: Empty WAL file
  Given queue.wal exists but is empty (0 bytes)
  When recovery loads WAL
  Then no entries to replay
  And snapshot alone used for recovery
  And recovery succeeds

Scenario: Empty statistics file
  Given statistics.json exists but is empty (0 bytes)
  When StatisticsRecoveryService loads file
  Then deserialization fails
  And corruption detected
  And fresh statistics initialized

# ========================================
# CATEGORY: Error Scenarios
# ========================================

Scenario: Disk full during queue snapshot write
  Given disk space exhausted
  When queue snapshot write is attempted
  Then IOException thrown
  And temp file write fails
  And temp file cleaned up
  And old snapshot file remains valid

Scenario: Permission denied on WAL file write
  Given queue.wal has incorrect permissions (read-only)
  When WAL append is attempted
  Then UnauthorizedAccessException thrown
  And operation fails
  And error logged with full context

Scenario: Network filesystem timeout during flush
  Given workspace on network filesystem (NFS)
  And network latency causes timeout
  When FileStream.FlushAsync() is called
  Then IOException thrown after timeout
  And operation retried or fails
  And partial data not visible

Scenario: Statistics file locked by external process
  Given statistics.json locked by backup process
  When save operation attempts to write
  Then IOException thrown (file in use)
  And retry mechanism activates
  And save eventually succeeds when lock released

# ========================================
# CATEGORY: Edge Cases
# ========================================

Scenario: Empty queue recovery
  Given queue-snapshot.json exists with empty job array
  When recovery executes
  Then queue initialized with 0 jobs
  And recovery completes successfully
  And system operational

Scenario: Queue with 20 jobs (realistic low-traffic dataset)
  Given queue contains 20 pending jobs
  When checkpoint is triggered
  Then snapshot serialization completes quickly (<100ms)
  And all 20 jobs serialized with correct order
  And recovery can restore all jobs

Scenario: Job with special characters in prompt
  Given job prompt contains unicode, quotes, newlines
  When job is serialized to WAL
  Then JSON escaping handles special characters
  And deserialization reconstructs exact prompt
  And no data corruption occurs

Scenario: Statistics with zero data points
  Given statistics initialized fresh (no jobs processed)
  When statistics are saved
  Then totalJobsProcessed = 0
  And resourceUsageHistory = []
  And P90 estimates are null or default values
  And save succeeds

Scenario: WAL with single entry
  Given WAL contains only 1 operation
  When recovery replays WAL
  Then single operation applied correctly
  And replay succeeds

Scenario: Boundary condition - checkpoint at exactly 100 ops (low-traffic threshold)
  Given WAL contains exactly 1000 entries
  When 1000th entry is written
  Then checkpoint triggered
  And WAL truncated
  And snapshot contains all 1000 operations

Scenario: Boundary condition - checkpoint at exactly 5 minutes
  Given last checkpoint occurred 29.999 seconds ago
  When time reaches 30.000 seconds
  Then checkpoint triggered
  And timer reset to 0

# ========================================
# CATEGORY: Queue Operations
# ========================================

Scenario: Queue order preservation with sequence numbers
  Given 50 jobs enqueued in specific order
  When jobs are serialized to snapshot
  Then sequence numbers assigned: 1, 2, 3...50
  And recovery restores exact order using sequence numbers
  And FIFO order maintained

Scenario: Queue dequeue operation WAL logging
  Given queue has 5 jobs
  When job is dequeued
  Then WAL entry logged: {"op":"dequeue","jobId":"..."}
  And WAL flushed to disk
  And in-memory queue updated

Scenario: Queue status change WAL logging
  Given job transitions from "queued" to "running"
  When status update occurs
  Then WAL entry logged: {"op":"status_change","jobId":"...","from":"queued","to":"running"}
  And transition captured in WAL

# ========================================
# CATEGORY: Statistics Operations
# ========================================

Scenario: Statistics immediate persistence on job completion
  Given job completes with resource usage data
  When RecordJobCompletion() is called
  Then in-memory statistics updated
  And StatisticsPersistenceService.SaveStatisticsAsync() called
  And file written within 10ms
  And write completes before method returns

Scenario: Statistics P90 calculation persistence
  Given 100 jobs completed
  When P90 is recalculated
  Then new P90 values computed
  And statistics.json updated immediately
  And P90 values persisted

Scenario: Statistics recovery with valid data
  Given statistics.json exists with valid data
  When StatisticsRecoveryService loads file
  Then totalJobsProcessed loaded
  And P90 estimates loaded
  And capacity metrics loaded
  And in-memory statistics initialized

# ========================================
# CATEGORY: Startup and Recovery
# ========================================

Scenario: Normal startup with existing snapshot
  Given queue-snapshot.json exists
  And queue.wal contains 5 entries since checkpoint
  When server starts
  Then snapshot loaded
  And 5 WAL entries replayed
  And queue state fully restored
  And recovery completes within 10 seconds

Scenario: First startup with no persisted state
  Given no queue-snapshot.json exists
  And no queue.wal exists
  When server starts
  Then empty queue initialized
  And new WAL created
  And system operational

Scenario: Startup log entry for queue recovery
  Given queue recovery completes
  When startup log is written
  Then entry contains: component="QueueRecovery"
  And jobs_recovered count
  And recovery_method ("snapshot" or "wal-reconstruction")
  And wal_entries_replayed count
  And duration_ms

Scenario: Startup log entry for statistics recovery
  Given statistics recovery completes
  When startup log is written
  Then entry contains: component="StatisticsRecovery"
  And total_jobs_processed
  And p90_cpu, p90_memory_mb, p90_duration_seconds
  And recovery_status ("success" or "corrupted_fallback_to_fresh")

# ========================================
# CATEGORY: High-Volume Scenarios
# ========================================

Scenario: Queue operations at low-traffic rate (few per minute)
  Given queue receives 3-5 operations per minute (realistic low traffic)
  When each operation logs to WAL
  Then all operations complete quickly (<10ms each)
  And WAL file size remains small (<1MB typical)
  And no operations lost

Scenario: Concurrent statistics updates from 3-5 jobs (realistic concurrency)
  Given 10 jobs complete simultaneously
  When all call RecordJobCompletion()
  Then serialization prevents race conditions
  And all 10 updates persisted
  And file integrity maintained
  And totalJobsProcessed incremented by 10

# ========================================
# CATEGORY: Observability
# ========================================

Scenario: WAL write latency logging
  Given WAL write operation executes
  When operation completes
  Then latency logged (debug level)
  And latency <5ms target verified

Scenario: Statistics save latency logging
  Given statistics save operation executes
  When operation completes
  Then latency logged (debug level)
  And latency <10ms target verified

Scenario: Recovery duration logging
  Given recovery completes
  When startup log entry written
  Then duration_ms field populated
  And duration <10 seconds for 1000 jobs verified
```

## Manual E2E Test Plan

**Prerequisites**:
- Claude Server running
- Admin authentication token
- Test jobs ready to execute

**Test Steps**:

### Test 1: Queue Persistence Across Crash

```bash
# Queue multiple jobs
for i in {1..20}; do
  curl -X POST https://localhost/api/jobs \
    -H "Authorization: Bearer $USER_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"prompt\": \"Job $i\", \"repository\": \"test-repo\"}"
done

# Verify queued
QUEUED=$(curl -s https://localhost/api/jobs \
  -H "Authorization: Bearer $USER_TOKEN" | jq '.[] | select(.status=="queued") | .id' | wc -l)
echo "Queued before crash: $QUEUED"

# Crash server immediately
sudo pkill -9 -f "ClaudeBatchServer.Api"

# Restart server
sudo systemctl start claude-batch-server
sleep 10

# Verify all jobs restored
RECOVERED=$(curl -s https://localhost/api/jobs \
  -H "Authorization: Bearer $USER_TOKEN" | jq '.[] | select(.status=="queued") | .id' | wc -l)
echo "Recovered after crash: $RECOVERED"

# Check startup log
curl -s https://localhost/api/admin/startup-log \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.operations[] | select(.component=="QueueRecovery")'
```
**Expected**: All 20 jobs recovered, startup log shows queue recovery operation
**Verify**: Job count matches, recovery duration logged

### Test 2: Statistics Persistence Across Crash

```bash
# Note statistics before crash
BEFORE=$(cat /var/lib/claude-batch-server/workspace/statistics.json | jq '.statistics.totalJobsProcessed')
echo "Jobs processed before crash: $BEFORE"

# Run a job to update statistics
JOB_ID=$(curl -s -X POST https://localhost/api/jobs \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Stats test","repository":"test-repo"}' | jq -r '.jobId')

curl -X POST "https://localhost/api/jobs/$JOB_ID/start" -H "Authorization: Bearer $USER_TOKEN"

# Wait for completion
while true; do
  STATUS=$(curl -s "https://localhost/api/jobs/$JOB_ID" -H "Authorization: Bearer $USER_TOKEN" | jq -r '.status')
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then break; fi
  sleep 5
done

# Verify statistics updated immediately
UPDATED=$(cat /var/lib/claude-batch-server/workspace/statistics.json | jq '.statistics.totalJobsProcessed')
echo "Jobs processed after job: $UPDATED"

# Crash server
sudo pkill -9 -f "ClaudeBatchServer.Api"

# Restart server
sudo systemctl start claude-batch-server
sleep 10

# Verify statistics recovered
AFTER=$(cat /var/lib/claude-batch-server/workspace/statistics.json | jq '.statistics.totalJobsProcessed')
echo "Jobs processed after recovery: $AFTER"

# Check startup log for statistics recovery
curl -s https://localhost/api/admin/startup-log \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.operations[] | select(.component=="StatisticsRecovery")'
```
**Expected**: Statistics preserved across crash, count incremented correctly
**Verify**: Total jobs processed matches, startup log shows statistics recovery

### Test 3: WAL Recovery After Corruption

```bash
# Stop server
sudo systemctl stop claude-batch-server

# Corrupt queue snapshot file
echo "corrupted data" | sudo tee /var/lib/claude-batch-server/workspace/queue-snapshot.json

# Restart server (WAL recovery should kick in)
sudo systemctl start claude-batch-server
sleep 10

# Check startup log for WAL recovery
curl -s https://localhost/api/admin/startup-log \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.operations[] | select(.component=="QueueRecovery") | .recovery_method'
```
**Expected**: "wal-reconstruction" shown in startup log
**Verify**: WAL used for recovery, jobs still intact

### Test 4: Concurrent Statistics Updates

```bash
# Start 10 jobs concurrently
for i in {1..10}; do
  curl -s -X POST https://localhost/api/jobs \
    -H "Authorization: Bearer $USER_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"prompt\":\"Concurrent $i\",\"repository\":\"test-repo\"}" | jq -r '.jobId' &
done
wait

# Start all created jobs
JOBS=$(curl -s https://localhost/api/jobs?status=created \
  -H "Authorization: Bearer $USER_TOKEN" | jq -r '.jobs[].jobId')

for JOB in $JOBS; do
  curl -X POST "https://localhost/api/jobs/$JOB/start" -H "Authorization: Bearer $USER_TOKEN" &
done
wait

# Wait for all to complete
while true; do
  RUNNING=$(curl -s https://localhost/api/jobs?status=running \
    -H "Authorization: Bearer $USER_TOKEN" | jq '.jobs | length')
  if [ "$RUNNING" = "0" ]; then break; fi
  sleep 5
done

# Verify statistics integrity (no corruption from concurrent access)
cat /var/lib/claude-batch-server/workspace/statistics.json | jq '.statistics'
```
**Expected**: All 10 jobs recorded correctly, no file corruption
**Verify**: Statistics file valid JSON, totalJobsProcessed incremented by 10

### Test 5: High-Volume Persistence

```bash
# Generate high load
for i in {1..100}; do
  curl -X POST https://localhost/api/jobs \
    -H "Authorization: Bearer $USER_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"prompt": "Load test", "repository": "test-repo"}'
done

# Crash immediately after
sudo pkill -9 -f "ClaudeBatchServer.Api"

# Restart and check all jobs recovered
sudo systemctl start claude-batch-server
sleep 10

RECOVERED=$(curl -s https://localhost/api/jobs \
  -H "Authorization: Bearer $USER_TOKEN" | jq '.[] | select(.status=="queued") | .id' | wc -l)
echo "High-load recovery: $RECOVERED jobs"
```
**Expected**: 100+ jobs recovered despite crash during high load
**Verify**: All jobs present, WAL handled high throughput

**Success Criteria**:
- ✅ Queue state fully persisted with WAL
- ✅ Statistics saved immediately on every change
- ✅ Recovery restores all queue and statistics data automatically
- ✅ Order preservation maintained for queue
- ✅ WAL provides backup recovery for queue
- ✅ Concurrent statistics updates handled safely
- ✅ Startup log provides complete visibility
- ✅ No manual intervention needed

## Observability Requirements

**Structured Logging** (all logged to startup log and application log):
- Queue persistence operations (WAL writes, checkpoints)
- Statistics file writes (debug level, real-time)
- Recovery start with timestamp
- Recovery progress (jobs recovered, statistics loaded)
- Recovery completion with durations
- Corruption detection with fallback method
- WAL statistics (size, entries, checkpoint frequency)
- Save failures (error level with full context)
- Error conditions with full context

**Startup Log Entry - Queue Recovery**:
```json
{
  "component": "QueueRecovery",
  "operation": "recovery_completed",
  "timestamp": "2025-10-15T10:00:30.123Z",
  "duration_ms": 1234,
  "jobs_recovered": 50,
  "recovery_method": "snapshot" | "wal-reconstruction",
  "errors": [],
  "wal_entries_replayed": 15
}
```

**Startup Log Entry - Statistics Recovery**:
```json
{
  "component": "StatisticsRecovery",
  "operation": "statistics_loaded",
  "timestamp": "2025-10-15T10:00:31.456Z",
  "total_jobs_processed": 1523,
  "p90_cpu": 78.5,
  "p90_memory_mb": 4096,
  "p90_duration_seconds": 300,
  "file_size_bytes": 45678,
  "recovery_status": "success" | "corrupted_fallback_to_fresh"
}
```

**Metrics** (logged to structured log):
- Queue operation latency (<10ms target)
- Statistics save latency (<10ms target)
- WAL write throughput
- Recovery duration (<10 seconds for 1000 jobs)
- Jobs recovered per second
- Save success rate (>99.9% for both queue and statistics)
- Corruption incidents (with automatic WAL fallback)
- Concurrent update contention (statistics lock wait time)

## Definition of Done
- [ ] Implementation complete with TDD
- [ ] Manual E2E test executed successfully by Claude Code
- [ ] Queue persistence fully functional with WAL
- [ ] Statistics persistence working with real-time saves
- [ ] Recovery restores complete queue and statistics state automatically
- [ ] Serialization lock prevents statistics concurrent access issues
- [ ] Structured logging provides complete visibility for both subsystems
- [ ] WAL backup recovery works
- [ ] Statistics survive crashes without data loss
- [ ] Corruption handled gracefully for both queue and statistics
- [ ] Code reviewed and approved

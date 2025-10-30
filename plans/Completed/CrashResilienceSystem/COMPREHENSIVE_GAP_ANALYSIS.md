# Crash Resilience Epic - Comprehensive Gap Analysis

**Date**: 2025-10-16
**Scope**: Complete codebase review for crash/restart vulnerabilities
**Method**: Deep code analysis of all services, state management, and persistence layers

---

## Gap #1: In-Memory Job Queue Not Persisted

**What Gets Lost/Corrupted**: The job queue order (`_jobQueue` ConcurrentQueue in JobService)

**Current Code**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobService.cs:44`
```csharp
private readonly ConcurrentQueue<Guid> _jobQueue = new();
```

**Impact**:
- On crash, queued jobs are loaded from persistence (line 129) but queue ORDER is rebuilt in arbitrary fashion
- Jobs that were queued get re-queued, but not in original order
- FIFO ordering guarantee is LOST on restart
- Jobs at position 1 might become position 10 after restart

**Epic Coverage**: Problem #1 addresses queue STATE but not queue ORDER preservation

**Recommendation**:
- Persist queue order with sequence numbers in job metadata
- Add `QueuedAt` timestamp and `QueueSequence` integer to Job model
- Reconstruct queue in correct order during `InitializeAsync()` using `OrderBy(j => j.QueueSequence)`

**Priority**: HIGH

---

## Gap #2: Repository Lock State Not Persisted

**What Gets Lost/Corrupted**: All repository locks (`_repositoryLocks` in RepositoryLockManager)

**Current Code**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/RepositoryLockManager.cs:13-14`
```csharp
private readonly ConcurrentDictionary<string, RepositoryLockInfo> _repositoryLocks = new();
private readonly ConcurrentDictionary<string, QueuedOperationCollection> _waitingOperations = new();
```

**Impact**:
- On crash during repository operation (git clone, CIDX indexing), lock is LOST
- No recovery mechanism knows the operation was in progress
- Repository remains in intermediate state (partial clone, partial index)
- Subsequent operations may start without cleanup, causing corruption
- Jobs waiting for the repository are never notified

**Epic Coverage**: Problem #6 addresses lock STALE detection but not lock PERSISTENCE

**Recommendation**:
- Persist lock files: `/workspace/locks/{repositoryName}.lock`
- Write JSON with: `{lockHolder, operationType, acquiredAt, processId, operationId}`
- On startup, scan lock directory and restore locks with stale detection
- Implement lock recovery: if process dead, mark operation as failed and cleanup

**Priority**: CRITICAL

---

## Gap #3: Repository Waiting Queue Lost on Crash

**What Gets Lost/Corrupted**: Jobs waiting for locked repositories (`_waitingOperations`)

**Current Code**: Same as Gap #2 - `_waitingOperations` is in-memory only

**Impact**:
- Jobs waiting for repository locks are forgotten on crash
- These jobs remain in `QueuedForResume` or `BatchedWaiting` status forever
- No automatic recovery to re-queue these jobs
- Manual intervention required to restart lost jobs

**Epic Coverage**: Not addressed by any of the 14 problems

**Recommendation**:
- Store waiting operations in job metadata: `job.RepositoryWaitInfo = {repositoryName, queuedAt, queuePosition}`
- On startup, rebuild waiting queues from jobs in waiting states
- Integrate with lock recovery to re-trigger notifications

**Priority**: HIGH

---

## Gap #4: Active Batch State Not Persisted

**What Gets Lost/Corrupted**: Job batching state (`_activeBatches` in JobBatchingService)

**Current Code**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobBatchingService.cs:13`
```csharp
private readonly ConcurrentDictionary<string, JobBatch> _activeBatches = new();
```

**Impact**:
- On crash, batch relationships are lost
- Jobs that were batched together for repository preparation are treated independently
- Efficiency optimization is completely lost - every job triggers fresh preparation
- No way to know which jobs were waiting for same batch

**Epic Coverage**: Not addressed

**Recommendation**:
- Add batch ID to Job model: `job.BatchId`
- Persist batch state to `/workspace/batches/{repositoryName}.batch.json`
- On startup, rebuild batches from jobs with same BatchId
- Mark batch phase based on job statuses

**Priority**: MEDIUM (efficiency optimization, not correctness issue)

---

## Gap #5: Resource Statistics Lost on Crash

**What Gets Lost/Corrupted**: Historical resource usage data (`_statistics` in ResourceStatisticsService)

**Current Code**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/ResourceMonitoring/Statistics/ResourceStatisticsService.cs:13`
```csharp
private readonly ConcurrentDictionary<string, ResourceStatisticsData> _statistics;
```

**Impact**:
- Resource estimates (P90 memory, CPU, execution time) are LOST
- Queue decision engine makes poor decisions due to lack of historical data
- Resource monitoring system starts "cold" after every restart
- Jobs may be rejected/delayed unnecessarily due to missing estimates

**Epic Coverage**: Problem #11 addresses statistics persistence, BUT implementation uses throttled writes (line 146-155)

**Current Implementation Issue**:
- `TryPersistThrottled()` has 2-second minimum interval
- If crash occurs between persist calls, last 2+ seconds of data is LOST
- This is acceptable for most scenarios, but epic should document this trade-off

**Recommendation**:
- Current implementation is ADEQUATE for statistics (2-second loss acceptable)
- Document the throttling behavior as accepted risk
- Consider flush on shutdown signal for graceful stops

**Priority**: LOW (already addressed, just needs documentation)

---

## Gap #6: Repository Monitoring State Not Persisted

**What Gets Lost/Corrupted**: Repository status, metrics, activities, alerts (RepositoryMonitoringService)

**Current Code**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/RepositoryMonitoringService.cs:15-18`
```csharp
private readonly ConcurrentDictionary<string, RepositoryOperationStatus> _repositoryStatuses = new();
private readonly ConcurrentDictionary<string, RepositoryMetrics> _repositoryMetrics = new();
private readonly ConcurrentDictionary<string, ConcurrentQueue<RepositoryActivity>> _repositoryActivities = new();
private readonly List<RepositoryAlert> _activeAlerts = new();
```

**Impact**:
- On crash, repository health status is LOST
- Active alerts are forgotten (long-running operations, high failure rates)
- Repository metrics history is lost (success rates, operation durations)
- System has no visibility into problems that existed before crash

**Epic Coverage**: Not addressed

**Recommendation**:
- Persist repository monitoring snapshot to `/workspace/monitoring/repository-monitoring.json`
- Write on every monitoring cycle (already runs every 10 seconds)
- On startup, load last snapshot to restore visibility
- This is primarily observability, not critical for correctness

**Priority**: LOW (observability issue, not correctness issue)

---

## Gap #7: Full-Text Search State Lost on Crash

**What Gets Lost/Corrupted**: Active searches and results (`_activeSearches`, `_searchResults` in FullTextSearchService)

**Current Code**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/FullTextSearchService.cs:20-21`
```csharp
private readonly ConcurrentDictionary<string, SearchOperation> _activeSearches;
private readonly ConcurrentDictionary<string, SearchProgressResponse> _searchResults;
```

**Impact**:
- On crash, active searches are terminated without notification
- Search results are lost (users must re-run searches)
- Search operation IDs become invalid
- Users experience confusing "search not found" errors

**Epic Coverage**: Not addressed

**Recommendation**:
- Mark this as OUT OF SCOPE - searches are transient operations
- Users expect to re-run searches if server restarts
- No persistence needed - acceptable loss

**Priority**: N/A (out of scope)

---

## Gap #8: AgentEngine Configuration Not Reloadable

**What Gets Lost/Corrupted**: Engine configuration loaded once at startup (`_engines` in AgentEngineService)

**Current Code**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/AgentEngineService.cs:14-20`
```csharp
private readonly Dictionary<string, AgentEngine> _engines;

public AgentEngineService(ILogger<AgentEngineService> logger, IConfiguration configuration)
{
    _engines = LoadEnginesFromConfiguration();
}
```

**Impact**:
- Configuration changes require full server restart
- Cannot add/remove/modify engines without downtime
- Running jobs continue with old configuration until restart
- This is NOT a crash issue, it's a runtime config limitation

**Epic Coverage**: Problem #5 mentions runtime configuration, but this is about CONFIG RELOAD not crash recovery

**Recommendation**:
- OUT OF SCOPE for crash resilience
- This is a separate feature: hot-reload of agent engine configuration
- Not related to crash/restart recovery

**Priority**: N/A (not a crash resilience issue)

---

## Gap #9: Callback Delivery Not Guaranteed After Crash

**What Gets Lost/Corrupted**: Callback execution state (JobCallbackExecutor has no persistence)

**Current Code**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobCallbackExecutor.cs`
- Callbacks stored in `job.Callbacks` (persisted)
- But callback EXECUTION STATUS is not tracked

**Impact**:
- If crash occurs after job completes but before callback executes, callback is LOST
- Job status is "completed" but callback never fired
- No retry mechanism for failed callbacks
- Callback delivery is best-effort, not guaranteed

**Epic Coverage**: Problem #10 addresses callback persistence, but NOT execution tracking

**Recommendation**:
- Add callback execution tracking to Job model:
  ```csharp
  public class JobCallback {
      public string Url { get; set; }
      public CallbackStatus Status { get; set; } // Pending, Sent, Failed
      public DateTime? SentAt { get; set; }
      public int RetryCount { get; set; }
  }
  ```
- Persist callback status after execution
- On startup, re-send callbacks in "Pending" status
- Implement retry logic with exponential backoff

**Priority**: HIGH (data loss issue - callbacks are critical for integrations)

---

## Gap #10: Job Metadata Atomic Write Not Guaranteed

**What Gets Lost/Corrupted**: Job metadata file corruption during write

**Current Code**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobPersistenceService.cs:50-69`
```csharp
public async Task SaveJobAsync(Job job)
{
    var filePath = GetJobFilePath(job.Id);
    var jsonContent = JsonSerializer.Serialize(job, AppJsonSerializerContext.Default.Job);
    await File.WriteAllTextAsync(filePath, jsonContent);
}
```

**Impact**:
- Direct write to job file - if crash during write, file is CORRUPTED
- JSON is partially written, unreadable on restart
- Job is LOST permanently (cannot be loaded)
- No recovery mechanism for corrupted job files

**Epic Coverage**: Problem #2 addresses this but current implementation DOES NOT use atomic operations

**Recommendation**:
- Implement write-temp-rename pattern:
  ```csharp
  var tempPath = $"{filePath}.tmp";
  await File.WriteAllTextAsync(tempPath, jsonContent);
  File.Move(tempPath, filePath, overwrite: true);
  ```
- This ensures atomic replacement - file is either old or new, never corrupt

**Priority**: CRITICAL

---

## Gap #11: Repository Settings File Not Atomic

**What Gets Lost/Corrupted**: Repository settings file corruption

**Current Code**: Multiple locations write to `.claude-batch-settings.json` without atomic operations
- RepositoryRegistrationService.cs:174, 220, 339
- All use direct `File.WriteAllTextAsync()`

**Impact**:
- Same as Gap #10 - file corruption on crash during write
- Repository metadata lost (GitUrl, CidxAware, Branch, CloneStatus)
- Repository becomes unusable - cannot determine configuration

**Epic Coverage**: Problem #2 mentions atomic operations but not enforced in repository settings

**Recommendation**:
- Create helper method for atomic file writes
- Use write-temp-rename pattern for all config files
- Consider JSON schema validation on read to detect corruption

**Priority**: CRITICAL

---

## Gap #12: CoW Workspace Cleanup Not Transactional

**What Gets Lost/Corrupted**: Orphaned CoW workspaces after crash during cleanup

**Current Code**: Cleanup happens in multiple places without transaction:
- Job completion triggers workspace cleanup
- If crash during cleanup, partial delete leaves corrupt workspace

**Impact**:
- Disk space leak - partial workspaces remain
- Cannot reuse workspace path (conflicts with future jobs)
- Orphaned Docker containers/networks from CIDX
- Manual cleanup required to recover disk space

**Epic Coverage**: Problem #5 addresses orphaned resource cleanup, but not TRANSACTIONAL cleanup

**Recommendation**:
- Mark workspace for cleanup with marker file: `{workspace}/.cleanup-pending`
- On startup, scan for cleanup markers and complete cleanup
- Only remove marker after successful cleanup
- This makes cleanup resumable after crash

**Priority**: MEDIUM (disk space issue, not correctness)

---

## Gap #13: CIDX Container State Lost on Crash

**What Gets Lost/Corrupted**: Running CIDX Docker containers and networks

**Current Code**: CIDX operations spawn Docker containers but container state is not tracked

**Impact**:
- On crash, Docker containers continue running (orphaned)
- Network namespaces remain allocated
- Disk space consumed by dangling volumes
- Port conflicts on restart if containers still bound

**Epic Coverage**: Problem #5 mentions Docker cleanup but no tracking of WHICH containers belong to WHICH jobs

**Recommendation**:
- Track CIDX container IDs in job metadata: `job.CidxContainerIds = [...]`
- Persist container IDs immediately after `cidx start`
- On startup, use tracked IDs for cleanup instead of blind discovery
- This makes cleanup precise instead of heuristic

**Priority**: MEDIUM (resource leak, covered by existing orphan cleanup)

---

## Gap #14: Git Pull Operation Not Resumable

**What Gets Lost/Corrupted**: Incomplete git pull on source repository

**Current Code**: Git operations are one-shot, no resume capability

**Impact**:
- If crash during git pull, repository is in DIRTY state
- Partial fetch leaves repo with incomplete objects
- Next job may fail due to corrupt git state
- Requires force cleanup and re-clone

**Epic Coverage**: Problem #12 originally covered git failures but moved to "operational resilience"

**Recommendation**:
- Mark as OUT OF SCOPE for crash resilience
- This is operational resilience (network failures, not crashes)
- Git operations should detect dirty state and retry/reset
- Not a crash-specific issue

**Priority**: N/A (operational resilience, not crash resilience)

---

## Gap #15: Staged Files Lost on Crash During Job Creation

**What Gets Lost/Corrupted**: Uploaded files in staging directory before CoW clone

**Current Code**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobPersistenceService.cs:184-191`
```csharp
public string GetJobStagingPath(Guid jobId)
{
    var stagingRootPath = Path.Combine(Path.GetDirectoryName(_jobsPath) ?? "/workspace", "staging");
    Directory.CreateDirectory(stagingRootPath);
    return Path.Combine(stagingRootPath, jobId.ToString());
}
```

**Impact**:
- Files uploaded before job starts are stored in staging
- If crash before CoW clone, staged files are LOST
- Job starts without required files
- Users must re-upload files

**Epic Coverage**: Not addressed

**Recommendation**:
- Staged files are tracked in job metadata: `job.UploadedFiles`
- On startup, scan staging directories for orphaned files
- Match staging directories to jobs and preserve or cleanup
- Consider staging cleanup policy (keep for 24 hours for recovery)

**Priority**: MEDIUM (user data loss, but recoverable by re-upload)

---

## Gap #16: Session Context Files Not Crash-Resilient

**What Gets Lost/Corrupted**: Markdown session files during write operations

**Current Code**: Adaptor implementations write session markdown files directly
- ClaudeCodeExecutor, GeminiAdaptor, etc. write to `{sessionId}.md`
- No atomic write guarantees

**Impact**:
- If crash during session file write, file is CORRUPTED
- Session history is lost or unreadable
- Resume operations fail due to missing context
- Job cannot be resumed - requires restart from beginning

**Epic Coverage**: Not addressed (session files assumed durable)

**Recommendation**:
- Use atomic write pattern for session markdown files
- Write to `{sessionId}.md.tmp` then rename
- ContextLifecycleManager should use atomic operations
- Add checksum validation on session file reads

**Priority**: HIGH (impacts resume functionality)

---

## Gap #17: Lock Files Implementation Missing

**What Gets Lost/Corrupted**: Epic mentions lock files but implementation does NOT exist

**Current Code**: RepositoryLockManager is in-memory only - no file-based locks

**Impact**:
- This is a GAP between epic design and implementation
- Story 1.3 and 1.4 describe lock file implementation
- Current code does not implement persistent locks
- This is a NEW work item, not a code review finding

**Epic Coverage**: Problem #6 ASSUMES lock files exist, but they DON'T

**Recommendation**:
- Implement lock file system as described in Story 1.3
- Create `/workspace/locks/{repositoryName}.lock` files
- Write lock metadata (holder, operation, timestamp, PID, operationId)
- Implement lock recovery on startup with stale detection

**Priority**: CRITICAL (foundational for epic implementation)

---

## Gap #18: Job Process ID Tracking Unreliable

**What Gets Lost/Corrupted**: Process ID stored in `job.ClaudeProcessId`

**Current Code**: `/claude-batch-server/src/ClaudeBatchServer.Core/Models/Job.cs:32`
```csharp
public int? ClaudeProcessId { get; set; }
```

**Impact**:
- PID can be reused by OS after process death
- Stored PID might point to different process after restart
- Epic problem #4 acknowledges this but Job model still stores PID
- Heartbeat-based detection is plan, but PID is still stored

**Epic Coverage**: Problem #4 (PID Unreliability) - acknowledged but not removed from data model

**Recommendation**:
- Keep PID for debugging/observability but DON'T use for recovery decisions
- Add comment warning: `// WARNING: PID unreliable, use heartbeat files for recovery`
- Ensure heartbeat-based recovery ignores PID field
- Consider deprecating field in future

**Priority**: LOW (addressed by heartbeat design, just needs cleanup)

---

## Gap #19: No Startup Corruption Detection

**What Gets Lost/Corrupted**: Silent failures during startup recovery

**Current Code**: JobService.InitializeAsync() loads jobs but doesn't validate integrity

**Impact**:
- Corrupted job files are skipped with warning (line 122)
- No report of HOW MANY jobs were corrupted
- No alert if significant data loss occurred
- Operators have no visibility into recovery problems

**Epic Coverage**: Problem #8 (Recovery Visibility) mentions single startup log, but no corruption metrics

**Recommendation**:
- Track corruption metrics during startup:
  ```csharp
  var metrics = new StartupRecoveryMetrics {
      TotalJobFiles = X,
      SuccessfullyLoaded = Y,
      CorruptedSkipped = Z,
      OrphanedResources = W
  };
  ```
- Log comprehensive startup summary
- Expose via `/monitoring/startup-recovery` endpoint
- Alert if corruption rate exceeds threshold (>5%)

**Priority**: MEDIUM (observability for recovery validation)

---

## Gap #20: Job Queue Concurrency Limiter State

**What Gets Lost/Corrupted**: Current concurrency count (`_concurrencyLimiter` in JobService)

**Current Code**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobService.cs:45`
```csharp
private readonly SemaphoreSlim _concurrencyLimiter;
```

**Impact**:
- On crash, semaphore count is reset to max (line 95)
- Running jobs that held semaphore slots are counted as dead
- This is CORRECT behavior - allows restarting jobs to acquire slots
- NOT a gap, current implementation is correct

**Epic Coverage**: Not applicable (implementation is correct)

**Priority**: N/A (no issue found)

---

## SUMMARY OF FINDINGS

### CRITICAL Gaps (Must Fix)
1. **Gap #2**: Repository locks not persisted → corruption on crash during repo operations
2. **Gap #10**: Job metadata not atomic → permanent job loss on crash during save
3. **Gap #11**: Repository settings not atomic → repository unusable after crash
4. **Gap #17**: Lock files not implemented → epic foundation missing

### HIGH Priority Gaps
1. **Gap #1**: Job queue order not preserved → FIFO guarantee violated
2. **Gap #3**: Repository waiting queues lost → jobs stuck forever
3. **Gap #9**: Callback execution not tracked → callbacks lost on crash
4. **Gap #16**: Session files not atomic → resume operations fail

### MEDIUM Priority Gaps
1. **Gap #4**: Batch state not persisted → efficiency loss (not correctness)
2. **Gap #12**: Workspace cleanup not transactional → disk space leaks
3. **Gap #13**: CIDX containers not tracked → resource leaks
4. **Gap #15**: Staged files cleanup policy → user data loss
5. **Gap #19**: No corruption detection → poor observability

### LOW Priority / Documentation
1. **Gap #5**: Statistics throttling needs documentation (already acceptable)
2. **Gap #6**: Repository monitoring state (observability only)
3. **Gap #18**: PID field needs deprecation comment

### OUT OF SCOPE
1. **Gap #7**: Full-text search state (transient by design)
2. **Gap #8**: Agent engine config reload (not crash-related)
3. **Gap #14**: Git pull resume (operational resilience)

---

## EPIC ENHANCEMENT RECOMMENDATIONS

The epic covers the RIGHT PROBLEMS but implementation has gaps:

1. **Add Story 1.5**: Job Queue Order Persistence (Gap #1)
2. **Add Story 1.6**: Repository Waiting Queue Recovery (Gap #3)
3. **Enhance Story 1.3**: Implement lock file system (Gap #17) - currently missing
4. **Enhance Story 2.2**: Add atomic write pattern for all metadata (Gaps #10, #11, #16)
5. **Add Story 2.4**: Callback Execution Tracking (Gap #9)
6. **Enhance Story 3.3**: Add startup corruption detection and metrics (Gap #19)

Total: 20 gaps found, 13 require fixes, 3 are documentation, 4 are out-of-scope.

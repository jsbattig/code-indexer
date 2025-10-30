# Gap Remediation Proposals - Complete Action Plan

**Date**: 2025-10-16
**Source**: Codex Architect Comprehensive Gap Analysis
**Scope**: Specific remediation proposals for all 20 identified gaps

---

## CRITICAL GAPS (4) - Immediate Action Required

### Gap #2: Repository Locks Not Persisted

**Current State**: In-memory only `ConcurrentDictionary<string, RepositoryLockInfo>`

**Proposed Solution**:
```csharp
// New service: RepositoryLockPersistenceService
public class RepositoryLockPersistenceService
{
    private readonly string _locksDirectory;

    public async Task PersistLockAsync(string repositoryName, RepositoryLockInfo lockInfo)
    {
        var lockPath = Path.Combine(_locksDirectory, $"{repositoryName}.lock.json");
        var lockData = new PersistedLock
        {
            LockHolder = lockInfo.LockHolder,
            OperationType = lockInfo.OperationType,
            AcquiredAt = lockInfo.AcquiredAt,
            ProcessId = Environment.ProcessId,
            OperationId = lockInfo.OperationId
        };

        // Use atomic write (temp + rename)
        await _atomicWriter.WriteJsonAsync(lockPath, lockData);
    }

    public async Task<Dictionary<string, RepositoryLockInfo>> RecoverLocksAsync()
    {
        var recovered = new Dictionary<string, RepositoryLockInfo>();

        foreach (var lockFile in Directory.GetFiles(_locksDirectory, "*.lock.json"))
        {
            try
            {
                var lockData = await LoadLockAsync(lockFile);

                // Check staleness: is process still alive?
                if (IsProcessAlive(lockData.ProcessId))
                {
                    // Lock still valid, restore it
                    recovered[lockData.RepositoryName] = ToRuntimeLock(lockData);
                }
                else
                {
                    // Stale lock, log and remove
                    _logger.LogWarning("Stale lock detected for {Repo}, removing", lockData.RepositoryName);
                    File.Delete(lockFile);
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Corrupted lock file: {File}", lockFile);
                // Corrupted lock → mark repo unavailable (degraded mode)
            }
        }

        return recovered;
    }
}
```

**Integration Points**:
- `RepositoryLockManager.AcquireLockAsync()` → persist after acquiring
- `RepositoryLockManager.ReleaseLockAsync()` → delete lock file
- `Startup.cs` → call `RecoverLocksAsync()` during initialization

**Story Assignment**: Enhance Story 4 (Lock Persistence)

**Effort**: 2-3 days

---

### Gap #10: Job Metadata Not Atomic

**Current State**: Direct `File.WriteAllTextAsync()` causes corruption on crash

**Proposed Solution**:
```csharp
// Create shared utility: AtomicFileWriter.cs
public class AtomicFileWriter
{
    public async Task WriteJsonAsync<T>(string filePath, T data)
    {
        var tempPath = $"{filePath}.tmp";

        try
        {
            // Step 1: Write to temp file
            var json = JsonSerializer.Serialize(data, _jsonOptions);
            await File.WriteAllTextAsync(tempPath, json);

            // Step 2: Flush to disk (critical!)
            using (var fs = new FileStream(tempPath, FileMode.Open, FileAccess.Read))
            {
                await fs.FlushAsync();
            }

            // Step 3: Atomic rename (OS guarantees atomicity)
            File.Move(tempPath, filePath, overwrite: true);
        }
        catch (Exception ex)
        {
            // Cleanup temp file on error
            if (File.Exists(tempPath))
                File.Delete(tempPath);
            throw;
        }
    }
}
```

**Retrofit Locations**:
1. `JobPersistenceService.SaveJobAsync()` - line 50
2. `JobPersistenceService.SaveJobStatusAsync()` - line 76
3. Any other job file writes

**Integration**:
```csharp
// OLD (vulnerable):
await File.WriteAllTextAsync(filePath, jsonContent);

// NEW (crash-safe):
await _atomicWriter.WriteJsonAsync(filePath, job);
```

**Story Assignment**: Create NEW Story 0 (Atomic File Operations Infrastructure)

**Effort**: 1-2 days (implement + retrofit all locations)

---

### Gap #11: Repository Settings Not Atomic

**Current State**: `.claude-batch-settings.json` written directly in 3 locations

**Proposed Solution**:
Use same `AtomicFileWriter` from Gap #10

**Retrofit Locations**:
1. `RepositoryRegistrationService.cs:174` - `RegisterRepositoryAsync()`
2. `RepositoryRegistrationService.cs:220` - `UpdateRepositorySettingsAsync()`
3. `RepositoryRegistrationService.cs:339` - `UpdateCloneStatusAsync()`

**Implementation**:
```csharp
// OLD:
await File.WriteAllTextAsync(settingsPath, json);

// NEW:
await _atomicWriter.WriteJsonAsync(settingsPath, settings);
```

**Story Assignment**: Part of Story 0 (Atomic File Operations Infrastructure)

**Effort**: 4 hours (retrofit 3 locations)

---

### Gap #17: Lock Files Implementation Missing

**Current State**: Epic Story 4 describes lock files, but ZERO implementation exists

**Proposed Solution**:
This is NOT a gap fix - this is **NEW feature implementation**

**What Story 4 Currently Says**:
"Lock Persistence with Automated Recovery - Repository lock durability, automatic stale lock detection"

**What Actually Exists**:
`RepositoryLockManager` with in-memory `ConcurrentDictionary` only

**Proposed Approach**:
Implement Gap #2 solution (above) as the FULL Story 4 implementation

**Story Assignment**: Story 4 is actually NEW WORK, not just recovery logic

**Effort**: 3-4 days (implement lock file system from scratch)

**Dependencies**: Requires Story 0 (AtomicFileWriter) first

---

## HIGH PRIORITY GAPS (4) - Address After Critical

### Gap #1: Job Queue Order Not Preserved

**Current State**: `_jobQueue` ConcurrentQueue rebuilt in arbitrary order on restart

**Proposed Solution**:
```csharp
// Add to Job model:
public class Job
{
    // Existing fields...
    public DateTime? QueuedAt { get; set; }
    public long QueueSequence { get; set; } // Auto-increment
}

// In JobService:
private long _queueSequenceCounter = 0;

public async Task<JobSubmissionResult> EnqueueJobAsync(Job job)
{
    // Assign sequence number
    job.QueuedAt = DateTime.UtcNow;
    job.QueueSequence = Interlocked.Increment(ref _queueSequenceCounter);

    // Persist with sequence number
    await _persistenceService.SaveJobAsync(job);

    // Add to in-memory queue
    _jobQueue.Enqueue(job.Id);
}

// Recovery in InitializeAsync():
public async Task InitializeAsync()
{
    var jobs = await _persistenceService.LoadAllJobsAsync();

    // Reconstruct queue in CORRECT ORDER using sequence
    var queuedJobs = jobs
        .Where(j => j.Status == JobStatus.Queued)
        .OrderBy(j => j.QueueSequence) // ← KEY: preserve order
        .ToList();

    foreach (var job in queuedJobs)
    {
        _jobQueue.Enqueue(job.Id);
    }

    // Restore sequence counter to max
    _queueSequenceCounter = jobs.Max(j => j.QueueSequence);
}
```

**Story Assignment**: Create NEW Story 1.5 (Queue Order Preservation)

**Effort**: 1 day

---

### Gap #3: Repository Waiting Queues Lost

**Current State**: `_waitingOperations` in-memory only, jobs stuck forever on crash

**Proposed Solution**:
```csharp
// Add to Job model:
public class Job
{
    // Existing fields...
    public RepositoryWaitInfo? RepositoryWaitInfo { get; set; }
}

public class RepositoryWaitInfo
{
    public string RepositoryName { get; set; }
    public DateTime QueuedAt { get; set; }
    public int QueuePosition { get; set; }
}

// In RepositoryLockManager:
public async Task AddToWaitingQueueAsync(string repositoryName, Guid jobId)
{
    // Add to in-memory queue
    _waitingOperations.GetOrAdd(repositoryName, _ => new QueuedOperationCollection())
        .Enqueue(jobId);

    // Persist wait state in job metadata
    var job = await _jobService.GetJobAsync(jobId);
    job.RepositoryWaitInfo = new RepositoryWaitInfo
    {
        RepositoryName = repositoryName,
        QueuedAt = DateTime.UtcNow,
        QueuePosition = _waitingOperations[repositoryName].Count
    };
    await _jobService.SaveJobAsync(job);
}

// Recovery in Startup:
public async Task RecoverWaitingQueuesAsync()
{
    var jobs = await _jobService.GetAllJobsAsync();

    // Find jobs that were waiting for repositories
    var waitingJobs = jobs
        .Where(j => j.RepositoryWaitInfo != null)
        .OrderBy(j => j.RepositoryWaitInfo.QueuedAt)
        .GroupBy(j => j.RepositoryWaitInfo.RepositoryName);

    foreach (var group in waitingJobs)
    {
        var repositoryName = group.Key;
        var queue = new QueuedOperationCollection();

        foreach (var job in group)
        {
            queue.Enqueue(job.Id);
        }

        _waitingOperations[repositoryName] = queue;

        // Check if lock is now available and notify
        if (!_repositoryLocks.ContainsKey(repositoryName))
        {
            await ProcessWaitingQueueAsync(repositoryName);
        }
    }
}
```

**Story Assignment**: Create NEW Story 1.6 (Repository Waiting Queue Recovery)

**Effort**: 2 days

---

### Gap #9: Callback Execution Not Tracked

**Current State**: Callbacks stored in `job.Callbacks` but execution status not tracked

**Proposed Solution**:
```csharp
// Enhance JobCallback model:
public class JobCallback
{
    public string Url { get; set; }
    public string Event { get; set; }

    // NEW: Execution tracking
    public CallbackStatus Status { get; set; } = CallbackStatus.Pending;
    public DateTime? SentAt { get; set; }
    public DateTime? CompletedAt { get; set; }
    public int RetryCount { get; set; }
    public int MaxRetries { get; set; } = 3;
    public string? LastError { get; set; }
}

public enum CallbackStatus
{
    Pending,      // Not sent yet
    Sending,      // Currently sending
    Sent,         // Successfully delivered
    Failed,       // Permanent failure (retries exhausted)
    Retrying      // Temporary failure, will retry
}

// In JobCallbackExecutor:
public async Task ExecuteCallbacksAsync(Job job)
{
    foreach (var callback in job.Callbacks.Where(c => c.Status == CallbackStatus.Pending))
    {
        try
        {
            // Mark as sending
            callback.Status = CallbackStatus.Sending;
            callback.SentAt = DateTime.UtcNow;
            await _jobService.SaveJobAsync(job); // Persist immediately

            // Attempt delivery
            var response = await _httpClient.PostAsJsonAsync(callback.Url, new {
                jobId = job.Id,
                status = job.Status,
                event = callback.Event
            });

            response.EnsureSuccessStatusCode();

            // Success
            callback.Status = CallbackStatus.Sent;
            callback.CompletedAt = DateTime.UtcNow;
            await _jobService.SaveJobAsync(job);
        }
        catch (Exception ex)
        {
            callback.RetryCount++;
            callback.LastError = ex.Message;

            if (callback.RetryCount >= callback.MaxRetries)
            {
                callback.Status = CallbackStatus.Failed;
                _logger.LogError(ex, "Callback permanently failed after {Retries} retries", callback.MaxRetries);
            }
            else
            {
                callback.Status = CallbackStatus.Retrying;
                _logger.LogWarning(ex, "Callback failed, will retry ({Count}/{Max})", callback.RetryCount, callback.MaxRetries);
            }

            await _jobService.SaveJobAsync(job);
        }
    }
}

// Recovery in Startup:
public async Task RecoverPendingCallbacksAsync()
{
    var jobs = await _jobService.GetAllJobsAsync();

    // Find callbacks that need delivery or retry
    var pendingCallbacks = jobs
        .Where(j => j.Callbacks.Any(c =>
            c.Status == CallbackStatus.Pending ||
            c.Status == CallbackStatus.Sending || // Was interrupted
            c.Status == CallbackStatus.Retrying))
        .ToList();

    foreach (var job in pendingCallbacks)
    {
        // Reset "Sending" back to "Pending" (interrupted by crash)
        foreach (var callback in job.Callbacks.Where(c => c.Status == CallbackStatus.Sending))
        {
            callback.Status = CallbackStatus.Pending;
        }

        // Schedule callback delivery
        await _callbackExecutor.ExecuteCallbacksAsync(job);
    }
}
```

**Story Assignment**: Enhance Story 6 (Callback Delivery Resilience)

**Effort**: 2 days

---

### Gap #16: Session Files Not Atomic

**Current State**: Adaptor implementations write markdown directly

**Proposed Solution**:
```csharp
// In ContextLifecycleManager:
public class ContextLifecycleManager
{
    private readonly AtomicFileWriter _atomicWriter;

    public async Task SaveSessionContextAsync(Guid sessionId, string content)
    {
        var sessionPath = GetSessionPath(sessionId);

        // Use atomic write
        await _atomicWriter.WriteTextAsync(sessionPath, content);

        // Add checksum for integrity validation
        var checksumPath = $"{sessionPath}.sha256";
        var checksum = ComputeSha256(content);
        await File.WriteAllTextAsync(checksumPath, checksum);
    }

    public async Task<string> LoadSessionContextAsync(Guid sessionId)
    {
        var sessionPath = GetSessionPath(sessionId);
        var checksumPath = $"{sessionPath}.sha256";

        if (!File.Exists(sessionPath))
            throw new FileNotFoundException($"Session file not found: {sessionId}");

        var content = await File.ReadAllTextAsync(sessionPath);

        // Verify checksum if available
        if (File.Exists(checksumPath))
        {
            var expectedChecksum = await File.ReadAllTextAsync(checksumPath);
            var actualChecksum = ComputeSha256(content);

            if (actualChecksum != expectedChecksum)
            {
                _logger.LogError("Session file corrupted: {SessionId}", sessionId);
                throw new InvalidDataException($"Session file corrupted: {sessionId}");
            }
        }

        return content;
    }
}
```

**Retrofit Locations**:
- All adaptor implementations (ClaudeCodeExecutor, GeminiAdaptor, etc.)
- ContextLifecycleManager session file operations

**Story Assignment**: Part of Story 0 (Atomic File Operations Infrastructure)

**Effort**: 1 day (retrofit all adaptors)

---

## MEDIUM PRIORITY GAPS (5) - Address Incrementally

### Gap #4: Active Batch State Not Persisted

**Current State**: `_activeBatches` in-memory only

**Proposed Solution**:
```csharp
// Add to Job model:
public class Job
{
    public Guid? BatchId { get; set; }
    public BatchPhase? BatchPhase { get; set; }
}

public enum BatchPhase
{
    Waiting,         // Waiting for batch to form
    Preparing,       // Repository preparation in progress
    Ready,           // Repository ready, batch can proceed
    Executing        // Jobs executing
}

// Persist batch files:
public async Task PersistBatchAsync(string repositoryName, JobBatch batch)
{
    var batchPath = Path.Combine(_batchesDirectory, $"{repositoryName}.batch.json");
    await _atomicWriter.WriteJsonAsync(batchPath, batch);
}

// Recovery:
public async Task RecoverBatchesAsync()
{
    var jobs = await _jobService.GetAllJobsAsync();

    var batchedJobs = jobs
        .Where(j => j.BatchId.HasValue)
        .GroupBy(j => j.BatchId.Value);

    foreach (var group in batchedJobs)
    {
        var batch = ReconstructBatch(group.ToList());
        _activeBatches[batch.RepositoryName] = batch;
    }
}
```

**Story Assignment**: Create NEW Story 1.7 (Batch State Recovery)

**Effort**: 1-2 days

**Priority**: MEDIUM (efficiency optimization, not correctness)

---

### Gap #12: CoW Workspace Cleanup Not Transactional

**Current State**: Crash during cleanup leaves partial workspaces

**Proposed Solution**:
```csharp
// Mark workspace for cleanup:
public async Task MarkWorkspaceForCleanupAsync(string workspacePath)
{
    var markerPath = Path.Combine(workspacePath, ".cleanup-pending");
    await File.WriteAllTextAsync(markerPath, DateTime.UtcNow.ToString("O"));
}

// Resume cleanup on startup:
public async Task ResumeCleanupOperationsAsync()
{
    var workspaces = Directory.GetDirectories(_workspaceRoot);

    foreach (var workspace in workspaces)
    {
        var markerPath = Path.Combine(workspace, ".cleanup-pending");

        if (File.Exists(markerPath))
        {
            _logger.LogInformation("Resuming cleanup for: {Workspace}", workspace);

            try
            {
                // Complete cleanup
                await CleanupWorkspaceAsync(workspace);

                // Success - workspace deleted, marker gone too
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Cleanup failed: {Workspace}", workspace);
                // Leave marker, will retry next startup
            }
        }
    }
}

// Modify cleanup workflow:
public async Task CleanupJobWorkspaceAsync(Guid jobId)
{
    var workspacePath = GetWorkspacePath(jobId);

    // Step 1: Mark for cleanup (atomic, crash-safe)
    await MarkWorkspaceForCleanupAsync(workspacePath);

    // Step 2: Perform cleanup
    await CleanupWorkspaceAsync(workspacePath);
    // Note: If crash here, marker remains and cleanup resumes on startup
}
```

**Story Assignment**: Enhance Story 5 (Orphan Detection)

**Effort**: 1 day

---

### Gap #13: CIDX Container State Lost

**Current State**: No tracking of which containers belong to which jobs

**Proposed Solution**:
```csharp
// Add to Job model:
public class Job
{
    public List<string> CidxContainerIds { get; set; } = new();
    public List<string> CidxNetworkIds { get; set; } = new();
}

// Track containers when created:
public async Task StartCidxIndexingAsync(Job job)
{
    var process = await StartCidxProcessAsync(job);

    // Extract container ID from cidx output
    var containerId = ExtractContainerIdFromOutput(process.StandardOutput);

    // Persist immediately
    job.CidxContainerIds.Add(containerId);
    await _jobService.SaveJobAsync(job);
}

// Cleanup using tracked IDs:
public async Task CleanupJobResourcesAsync(Guid jobId)
{
    var job = await _jobService.GetJobAsync(jobId);

    // Precise cleanup using tracked IDs
    foreach (var containerId in job.CidxContainerIds)
    {
        await StopDockerContainerAsync(containerId);
        await RemoveDockerContainerAsync(containerId);
    }

    foreach (var networkId in job.CidxNetworkIds)
    {
        await RemoveDockerNetworkAsync(networkId);
    }
}
```

**Story Assignment**: Enhance Story 5 (Orphan Detection)

**Effort**: 1 day

---

### Gap #15: Staged Files Lost on Crash

**Current State**: Files in staging directory lost if crash before CoW clone

**Proposed Solution**:
```csharp
// Staged files already tracked in Job.UploadedFiles
// Add cleanup policy:

public async Task RecoverStagedFilesAsync()
{
    var stagingRoot = Path.Combine(_workspaceRoot, "staging");
    var stagingDirs = Directory.GetDirectories(stagingRoot);

    foreach (var stagingDir in stagingDirs)
    {
        var jobId = Guid.Parse(Path.GetFileName(stagingDir));
        var job = await _jobService.GetJobAsync(jobId);

        if (job == null)
        {
            // Job doesn't exist, cleanup staging
            if (Directory.GetCreationTimeUtc(stagingDir) < DateTime.UtcNow.AddHours(-24))
            {
                _logger.LogInformation("Cleaning up orphaned staging dir: {JobId}", jobId);
                Directory.Delete(stagingDir, recursive: true);
            }
        }
        else if (job.Status != JobStatus.Created)
        {
            // Job has started, staging no longer needed
            Directory.Delete(stagingDir, recursive: true);
        }
        // else: job still in Created status, preserve staging files
    }
}
```

**Story Assignment**: Enhance Story 5 (Orphan Detection)

**Effort**: 4 hours

---

### Gap #19: No Startup Corruption Detection

**Current State**: Corrupted files skipped silently, no metrics

**Proposed Solution**:
```csharp
// Track corruption during startup:
public class StartupRecoveryMetrics
{
    public int TotalJobFiles { get; set; }
    public int SuccessfullyLoaded { get; set; }
    public int CorruptedSkipped { get; set; }
    public List<string> CorruptedFiles { get; set; } = new();

    public int TotalRepositories { get; set; }
    public int RepositoriesRecovered { get; set; }
    public int RepositoriesCorrupted { get; set; }

    public int OrphanedWorkspaces { get; set; }
    public int OrphanedContainers { get; set; }

    public double CorruptionRate => TotalJobFiles > 0
        ? (double)CorruptedSkipped / TotalJobFiles
        : 0;
}

// In JobService.InitializeAsync():
public async Task<StartupRecoveryMetrics> InitializeAsync()
{
    var metrics = new StartupRecoveryMetrics();
    var jobFiles = Directory.GetFiles(_jobsPath, "*.job.json");
    metrics.TotalJobFiles = jobFiles.Length;

    foreach (var file in jobFiles)
    {
        try
        {
            var job = await LoadJobAsync(file);
            _jobs[job.Id] = job;
            metrics.SuccessfullyLoaded++;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Corrupted job file: {File}", file);
            metrics.CorruptedSkipped++;
            metrics.CorruptedFiles.Add(file);
        }
    }

    // Alert if corruption rate exceeds threshold
    if (metrics.CorruptionRate > 0.05) // 5% threshold
    {
        _logger.LogCritical("HIGH CORRUPTION RATE: {Rate:P} of job files corrupted!",
            metrics.CorruptionRate);
    }

    return metrics;
}

// Expose via API:
[HttpGet("/api/admin/startup-recovery-metrics")]
public IActionResult GetStartupRecoveryMetrics()
{
    return Ok(_startupMetrics);
}
```

**Story Assignment**: Enhance Story 3 (Startup Recovery Orchestration)

**Effort**: 1 day

---

## LOW PRIORITY / DOCUMENTATION (3)

### Gap #5: Statistics Throttling Documentation

**Current State**: Statistics persisted with 2-second throttle, not documented

**Proposed Solution**:
```markdown
# Known Limitation: Statistics Persistence Throttling

The ResourceStatisticsService uses throttled persistence (2-second minimum interval)
to prevent excessive disk I/O during high job throughput.

**Trade-off**: If crash occurs between persist calls, up to 2 seconds of statistics
data may be lost.

**Risk Assessment**: ACCEPTABLE
- Statistics are for capacity planning, not transactional data
- 2-second loss is negligible for long-term trends
- Worst case: P90 estimates slightly outdated after restart

**Mitigation**: Consider flush on graceful shutdown signals (SIGTERM)
```

**Story Assignment**: Documentation update in Story 1

**Effort**: 1 hour

---

### Gap #6: Repository Monitoring State Documentation

**Current State**: Monitoring state lost on restart (metrics, alerts)

**Proposed Solution**:
Mark as **OUT OF SCOPE** - observability data, not critical state

**Rationale**:
- Repository monitoring rebuilds from live operations within seconds
- Historical alerts are logged, not actionable after restart
- Metrics start fresh, no correctness impact

**Story Assignment**: None (document as known limitation)

**Effort**: N/A

---

### Gap #18: PID Field Deprecation

**Current State**: `Job.ClaudeProcessId` still exists but shouldn't be used

**Proposed Solution**:
```csharp
public class Job
{
    /// <summary>
    /// WARNING: Process IDs are UNRELIABLE for recovery.
    /// PIDs can be reused by OS after process death.
    /// DO NOT use for recovery decisions - use heartbeat files instead.
    /// This field is kept for debugging/observability only.
    /// </summary>
    [Obsolete("Use heartbeat-based detection instead")]
    public int? ClaudeProcessId { get; set; }
}
```

**Story Assignment**: Part of Story 2 (Job Reattachment)

**Effort**: 15 minutes

---

## OUT OF SCOPE (4)

### Gap #7: Full-Text Search State

**Decision**: OUT OF SCOPE - searches are transient by design

**Rationale**: Users expect to re-run searches after restart

---

### Gap #8: Agent Engine Config Reload

**Decision**: OUT OF SCOPE - not crash-related, separate feature

**Rationale**: Hot-reload is operational feature, not crash resilience

---

### Gap #14: Git Pull Resume

**Decision**: OUT OF SCOPE - moved to Operational Resilience epic

**Rationale**: Network/git server failures, not server crash issues

---

### Gap #20: Job Queue Concurrency Limiter

**Decision**: NO ACTION REQUIRED - current implementation is correct

**Rationale**: Semaphore reset on restart is correct behavior

---

## IMPLEMENTATION ROADMAP

### Phase 0: Foundation (1-2 days) 🔴 CRITICAL
**NEW Story 0: Atomic File Operations Infrastructure**
- Create `AtomicFileWriter` utility class
- Retrofit JobPersistenceService (Gap #10)
- Retrofit RepositoryRegistrationService (Gap #11)
- Retrofit ContextLifecycleManager (Gap #16)
- Add corruption detection to all file reads

**Deliverable**: Zero risk of file corruption on crash

---

### Phase 1: Epic Stories 1-6 (2-3 weeks)
Following original epic structure, now building on solid foundation:

**Week 1**:
- Story 1: Queue and Statistics Persistence
- Story 2: Job Reattachment (with Gap #18 deprecation)

**Week 2**:
- Story 3: Startup Recovery Orchestration (with Gap #19 metrics)
- Story 4: Lock Persistence (NEW implementation for Gap #2, #17)

**Week 3**:
- Story 5: Orphan Detection (with Gaps #12, #13, #15)
- Story 6: Callback Resilience (with Gap #9 tracking)

---

### Phase 2: Additional Stories (1 week)
**Story 1.5**: Queue Order Preservation (Gap #1)
**Story 1.6**: Repository Waiting Queue Recovery (Gap #3)
**Story 1.7**: Batch State Recovery (Gap #4) - optional

---

## SUMMARY

**Total Gaps**: 20 identified
- **Critical**: 4 (MUST fix before epic)
- **High**: 4 (integrate into epic stories)
- **Medium**: 5 (address incrementally)
- **Low**: 3 (documentation only)
- **Out of Scope**: 4 (correct exclusions)

**New Work Required**:
- Story 0: Atomic File Operations (NEW, foundational)
- Story 1.5: Queue Order Preservation (NEW)
- Story 1.6: Waiting Queue Recovery (NEW)
- Story 4: Lock file implementation (epic assumed exists, but doesn't)

**Epic Enhancements**:
- Story 1: Add Gap #5 documentation
- Story 2: Add Gap #18 deprecation
- Story 3: Add Gap #19 corruption metrics
- Story 5: Add Gaps #12, #13, #15 (cleanup improvements)
- Story 6: Add Gap #9 execution tracking

**Total Effort Estimate**: 4-5 weeks
- Phase 0: 1-2 days (critical foundation)
- Phase 1: 2-3 weeks (epic implementation)
- Phase 2: 1 week (additional stories)

**Priority Order**:
1. Story 0 (BLOCKS everything else)
2. Stories 1-6 (core epic)
3. Stories 1.5, 1.6 (high-value additions)
4. Story 1.7 (nice-to-have optimization)

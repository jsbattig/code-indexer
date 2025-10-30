# Crash Resilience Epic - Complete Enhancements Summary

## Overview

This document summarizes ALL enhancements made to the Crash Resilience Epic based on thorough review against the codebase and user architectural decisions. The epic was reviewed by the elite-codex-architect agent and refined through multiple clarification rounds with the user.

**Date**: 2025-10-15
**Review Status**: Complete and validated against codebase
**Implementation Ready**: Yes

---

## Critical Architectural Clarifications

### 1. Recovery Happens on EVERY Startup ⚡ CRITICAL

**FUNDAMENTAL PRINCIPLE**: State restoration executes on **EVERY SERVER STARTUP**, not just after crashes.

**Problem**: The epic originally framed recovery as crash-specific ("Crash Detection: System identifies unexpected termination"), implying it only runs after failures.

**User Requirement**: "for clarity, the recovery needs to happens ALWAYS, every time the server start it needs to restore state"

**Changes Made to Epic File**:

1. **Executive Summary** (Lines 3-13):
   - FROM: "crash resilience system that ensures Claude Server can recover from any failure scenario"
   - TO: "state persistence and recovery system that ensures Claude Server restores all operational state on every startup, whether after a clean shutdown, crash, or restart"

2. **Recovery Flow** (Lines 47-57):
   - Renamed from "Recovery Flow" to "**Startup State Restoration Flow**"
   - Added CRITICAL note: "This recovery flow executes on EVERY SERVER STARTUP (not just after crashes)"
   - Changed step 1 from "Crash Detection" to "Startup Initialization"

3. **Success Criteria** (Lines 104-110):
   - FROM: "Zero data loss during crashes"
   - TO: "Zero data loss across any server restart (clean shutdown, crash, or restart)"

4. **Technical Considerations** (Lines 112-119):
   - Added first bullet: "**Every Startup**: State restoration executes on EVERY server startup, not just after crashes"

**Impact**: Eliminates ambiguity. Clear that recovery is a normal startup operation, not an exceptional case.

---

### 2. Heartbeat-Based Job Monitoring (Zero PID Dependency) ⚡ CRITICAL

**FUNDAMENTAL PRINCIPLE**: Job reattachment uses heartbeat/sentinel files. PIDs are completely eliminated.

**Problem**: Original Story 1.2 had incomplete heartbeat specification and still referenced PIDs in test plans.

**User Feedback**: "for job reattachment, we can't rely on PID, on a prior version of this epic, we said we will use a heartbeat/sentinel file and completely remove dependency on PID"

**Changes Made** (Story 1.2 - Complete Rewrite):

1. **Sentinel File Specification**:
```json
{
  "jobId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "lastHeartbeat": "2025-10-15T10:30:45.123Z",
  "workspacePath": "/var/lib/claude-batch-server/workspace/jobs/{jobId}",
  "sessionId": "abc123def456",
  "agentEngine": "claude-code",
  "startedAt": "2025-10-15T10:00:00.000Z"
}
```

2. **Heartbeat Requirements**:
   - Write interval: Every 30 seconds
   - File location: `{workspace}/jobs/{jobId}/.sentinel.json`
   - Write mechanism: Atomic file operations (temp + rename)

3. **Staleness Detection**:
   - **Fresh**: <2 minutes old → Job actively running
   - **Stale**: 2-10 minutes old → Job possibly hung, investigate
   - **Dead**: >10 minutes old → Job crashed, mark failed

4. **Recovery Detection**:
   - After crash, watch for heartbeat resumption
   - 5-minute grace period for job processes to continue
   - If heartbeat resumes, job survived crash (reattach)
   - If heartbeat dead after 5 minutes, job crashed (mark failed)

5. **Admin APIs Added** (8 new endpoints):
   - `GET /api/admin/jobs/heartbeats` - All job heartbeats
   - `GET /api/admin/jobs/{jobId}/heartbeat` - Specific job heartbeat
   - `GET /api/admin/jobs/heartbeats/stale` - Stale jobs (2-10 min)
   - `GET /api/admin/jobs/heartbeats/dead` - Dead jobs (>10 min)
   - `GET /api/admin/jobs/heartbeats/stats` - Heartbeat statistics
   - `POST /api/admin/jobs/{jobId}/force-reattach` - Manual reattachment
   - `POST /api/admin/jobs/{jobId}/mark-failed` - Manual failure marking
   - `GET /api/admin/jobs/recovery-status` - Post-crash recovery status

6. **Test Plans Updated**:
   - Removed ALL PID references
   - Added heartbeat-based validation steps
   - Added staleness detection testing
   - Added recovery detection testing

**Created**: `STORY_1.2_HEARTBEAT_SPECIFICATION.md` (200+ lines complete architecture)

**Impact**: Reliable job monitoring that survives server restarts. Zero dependency on unreliable PIDs.

---

### 3. File-Based Write-Ahead Log (WAL) ⚡ CRITICAL

**FUNDAMENTAL PRINCIPLE**: WAL is file-based (NOT database). Ensures in-memory changes written to disk quasi-realtime.

**Problem**: Story 1.1 mentioned "Database schema for queue persistence" which was ambiguous about WAL technology.

**User Decision**: "WAL: file based, we are not changing that in favor of a DB. the concept is ensure we write to disk what we store in mem cuasi realtime"

**Changes Made** (Story 1.1 - Added 80-line WAL Specification):

1. **WAL File Structure**:
   - **Location**: `{workspace}/queue.wal`
   - **Format**: Append-only text file, one operation per line
   - **Entry Format**: JSON lines (JSONL)
   ```json
   {"timestamp":"2025-10-15T10:30:00.123Z","op":"enqueue","jobId":"abc123","data":{...}}
   {"timestamp":"2025-10-15T10:30:05.456Z","op":"dequeue","jobId":"abc123"}
   {"timestamp":"2025-10-15T10:30:10.789Z","op":"status_change","jobId":"def456","from":"queued","to":"running"}
   ```

2. **Queue Operations Logged**:
   - `enqueue`: Job added (includes full job JSON)
   - `dequeue`: Job removed
   - `status_change`: Job status transition
   - `position_update`: Queue position changes

3. **Write Pattern**:
   - **Timing**: Immediately after in-memory state change (quasi-realtime)
   - **Mechanism**: Append to WAL file using atomic operations
   - **Flush**: After each write (ensure data on disk)
   - **Performance**: <5ms per operation

4. **Checkpoint Strategy**:
   - **Trigger**: Every 1000 operations OR every 30 seconds (whichever first)
   - **Action**: Write complete queue snapshot to `queue-snapshot.json`
   - **WAL Truncation**: After successful checkpoint, truncate WAL file
   - **Recovery**: Read last snapshot + replay WAL entries since checkpoint

5. **WAL Rotation**:
   - **Size Limit**: 100MB maximum WAL file size
   - **Action**: Force checkpoint when limit reached
   - **Safety**: Keep previous WAL as `.wal.old` until new checkpoint completes

6. **Recovery Algorithm**:
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
            case "enqueue": queue.Enqueue(entry.Data); break;
            case "dequeue": queue.Dequeue(); break;
            case "status_change": UpdateJobStatus(queue, entry.JobId, entry.To); break;
        }
    }

    // STEP 3: Restore in-memory state
    _inMemoryQueue = queue;
}
```

**Impact**: Durable queue state with minimal performance overhead. No database dependency.

---

### 4. Real-Time Statistics Persistence ⚡ CRITICAL

**FUNDAMENTAL PRINCIPLE**: Statistics saved immediately when they change in RAM (not periodic/batched).

**Problem**: ResourceStatisticsService exists with save/load methods but they're NEVER called automatically. Resource usage history and P90 estimates lost on every crash.

**User Decision**: "Fix this. make sure stats are saved as soon as they change in RAM. check of serialization is needed."

**Changes Made** (NEW Story 1.5 Created - 320 lines):

**Story**: "Resource Statistics Persistence"

1. **Real-Time Persistence Specification**:
   - Save **immediately** when statistics change in RAM
   - NOT periodic, NOT batched
   - Trigger points: job completion, P90 calculation, any modification to ResourceStatisticsData

2. **File Format**:
```json
{
  "version": "1.0",
  "lastUpdated": "2025-10-15T10:30:45.123Z",
  "statistics": {
    "totalJobsProcessed": 1523,
    "resourceUsageHistory": [...],
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

3. **Write Pattern (Atomic Operations)**:
```csharp
public async Task SaveStatisticsAsync(ResourceStatisticsData stats)
{
    var finalPath = Path.Combine(_workspace, "statistics.json");
    var tempPath = finalPath + ".tmp";

    try
    {
        var json = JsonSerializer.Serialize(stats, ...);

        // Write to temp file
        await File.WriteAllTextAsync(tempPath, json);

        // Flush to disk (critical)
        using (var fs = new FileStream(tempPath, FileMode.Open, FileAccess.Read))
        {
            await fs.FlushAsync();
        }

        // Atomic rename
        File.Move(tempPath, finalPath, overwrite: true);
    }
    catch (Exception ex)
    {
        _logger.LogError(ex, "Failed to save statistics");
        if (File.Exists(tempPath)) File.Delete(tempPath);
        // Don't throw - statistics save failure shouldn't crash system
    }
}
```

4. **Serialization Required (Concurrent Access)**:
```csharp
public class ResourceStatisticsService
{
    private readonly ResourceStatisticsData _statistics;
    private readonly SemaphoreSlim _lock = new(1, 1); // Serialize statistics updates
    private readonly StatisticsPersistenceService _persistenceService;

    public async Task RecordJobCompletion(Job job, ResourceUsage usage)
    {
        await _lock.WaitAsync(); // Only one thread modifies statistics at a time
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

**Rationale for Serialization**:
- Job completion handlers run concurrently (multiple jobs finishing)
- Each modifies ResourceStatisticsData
- Concurrent writes possible → **NEED SERIALIZATION**
- SemaphoreSlim ensures only one thread modifies + persists at a time

5. **Recovery Logic**:
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

        // Backup corrupted file
        File.Move(filePath, $"{filePath}.corrupted.{DateTime.UtcNow:yyyyMMddHHmmss}");

        return new ResourceStatisticsData();
    }
}
```

**Impact**: Prevents statistics data loss across restarts. Maintains accurate capacity planning and resource allocation decisions.

---

### 5. Git Operation Retry with Exponential Backoff ⚡ CRITICAL

**FUNDAMENTAL PRINCIPLE**: Git clone/pull operations retry automatically on transient failures.

**Problem**: Git operations can fail due to transient network issues. Current behavior requires manual repository re-registration.

**User Decision**: "introduce automated git retry for pull and clone with exponential backoff, 3 retries, start with 5 seconds wait"

**Changes Made** (NEW Story 2.6 Created - 280 lines):

**Story**: "Git Operation Retry Logic"

1. **Retry Configuration**:
   - **Max attempts**: 3
   - **Backoff delays**: 5 seconds, 15 seconds, 45 seconds (exponential: 5, 5×3, 5×9)
   - **Total max time**: 65 seconds (5 + 15 + 45)

2. **Operations Covered**:
   - `git clone` (repository registration)
   - `git pull` (job pre-execution update)
   - `git fetch` (if used)

3. **Retryable Errors** (network/transient):
   - Connection timeout
   - Connection refused
   - Host unreachable
   - Temporary failure in name resolution
   - Network is unreachable
   - Operation timed out
   - Could not resolve host
   - Failed to connect to

4. **Non-Retryable Errors** (permanent):
   - Authentication failed
   - Repository not found (404)
   - Permission denied
   - Invalid credentials
   - Branch does not exist
   - Fatal: repository corrupted

5. **Implementation**:
```csharp
public class GitRetryService
{
    private readonly ILogger<GitRetryService> _logger;
    private readonly int[] _backoffDelaysSeconds = { 5, 15, 45 };
    private const int MaxAttempts = 3;

    public async Task<GitResult> CloneWithRetryAsync(string repoUrl, string targetPath)
    {
        for (int attempt = 0; attempt < MaxAttempts; attempt++)
        {
            try
            {
                _logger.LogInformation("Git clone attempt {Attempt}/{Max} for {RepoUrl}",
                    attempt + 1, MaxAttempts, repoUrl);

                var result = await ExecuteGitCloneAsync(repoUrl, targetPath);

                _logger.LogInformation("Git clone succeeded on attempt {Attempt}", attempt + 1);
                return result;
            }
            catch (GitException ex) when (IsRetryable(ex))
            {
                if (attempt < MaxAttempts - 1) // Not last attempt
                {
                    var delay = _backoffDelaysSeconds[attempt];
                    _logger.LogWarning("Git clone failed (attempt {Attempt}/{Max}), " +
                        "retrying in {Delay}s: {Error}",
                        attempt + 1, MaxAttempts, delay, ex.Message);

                    await Task.Delay(delay * 1000);
                }
                else
                {
                    _logger.LogError("Git clone failed after {MaxAttempts} attempts: {Error}",
                        MaxAttempts, ex.Message);
                    throw new GitPermanentFailureException(
                        $"Git clone failed after {MaxAttempts} retry attempts", ex);
                }
            }
            catch (GitException ex) when (!IsRetryable(ex))
            {
                _logger.LogError("Git clone failed with non-retryable error (attempt {Attempt}): {Error}",
                    attempt + 1, ex.Message);
                throw; // Don't retry permanent failures
            }
        }

        throw new InvalidOperationException("Retry loop exited unexpectedly");
    }

    private bool IsRetryable(GitException ex)
    {
        var message = ex.Message.ToLowerInvariant();

        // Retryable: Network/transient errors
        var retryablePatterns = new[]
        {
            "timeout", "connection refused", "unreachable",
            "temporary failure", "could not resolve host",
            "failed to connect", "network is unreachable",
            "operation timed out"
        };

        if (retryablePatterns.Any(pattern => message.Contains(pattern)))
            return true;

        // Non-retryable: Permanent errors
        var permanentPatterns = new[]
        {
            "authentication failed", "repository not found",
            "permission denied", "invalid credentials",
            "fatal", "does not exist"
        };

        if (permanentPatterns.Any(pattern => message.Contains(pattern)))
            return false;

        // Default: assume retryable if unclear
        return true;
    }
}
```

6. **Integration Points**:

**RepositoryService.cs**:
```csharp
public async Task<Repository> RegisterRepositoryAsync(RegisterRepositoryRequest request)
{
    // ... validation ...

    try
    {
        // Use retry service instead of direct git clone
        await _gitRetryService.CloneWithRetryAsync(request.GitUrl, targetPath);
    }
    catch (GitPermanentFailureException ex)
    {
        repository.CloneStatus = "failed";
        repository.CloneError = ex.Message;
        await _repositoryPersistence.SaveAsync(repository);
        throw;
    }
}
```

**JobService.cs**:
```csharp
private async Task GitPullForJobAsync(Job job)
{
    try
    {
        // Use retry service instead of direct git pull
        var result = await _gitRetryService.PullWithRetryAsync(job.Repository.Path);
        job.GitPullStatus = "completed";
    }
    catch (GitPermanentFailureException ex)
    {
        job.Status = JobStatus.Failed;
        job.Output = $"Git pull failed after retries: {ex.Message}";
        throw;
    }
}
```

**Impact**: Improves system reliability by handling transient git failures automatically, reducing manual intervention.

---

### 6. Dependency Enforcement with Topological Sort ⚡ CRITICAL

**FUNDAMENTAL PRINCIPLE**: Recovery phases MUST execute in strict dependency order to prevent race conditions.

**Problem**: Story 2.3 listed recovery phases but didn't specify HOW to enforce dependencies.

**User Feedback**: "This is critical and needs to be specific"

**Changes Made** (Story 2.3 - Added 140-line Dependency Enforcement Section):

1. **Dependency Graph**:
```
Story 1.1: Queue Persistence Recovery
    ↓
Story 2.1: Lock Persistence Recovery  +  Story 1.2: Job Reattachment
    ↓
Story 1.3: Cleanup Resumption
    ↓
Story 2.2: Orphan Detection  +  Story 1.4: Startup Detection
    ↓
Story 2.4: Webhook Delivery Resilience
```

2. **Enforcement Mechanism**: Topological Sort

**Why Topological Sort?**
- Automatically determines correct execution order from dependencies
- Detects circular dependencies (fail fast at startup)
- Allows parallel execution of independent phases
- Clear, verifiable ordering algorithm

3. **Implementation**:
```csharp
public class RecoveryOrchestrator
{
    private readonly ILogger<RecoveryOrchestrator> _logger;

    public class RecoveryPhase
    {
        public string Name { get; set; }
        public Func<CancellationToken, Task<bool>> Execute { get; set; }
        public List<string> DependsOn { get; set; } = new();
        public bool Critical { get; set; } // If fails, abort recovery
        public bool AllowDegradedMode { get; set; } // Continue without this phase
    }

    public async Task<RecoveryResult> ExecuteRecoverySequenceAsync(CancellationToken ct)
    {
        var phases = new List<RecoveryPhase>
        {
            new()
            {
                Name = "Queue",
                Execute = RecoverQueueAsync,
                DependsOn = new(), // No dependencies
                Critical = true // Must succeed
            },
            new()
            {
                Name = "Locks",
                Execute = RecoverLocksAsync,
                DependsOn = new() { "Queue" },
                Critical = false, // Can continue in degraded mode
                AllowDegradedMode = true
            },
            new()
            {
                Name = "Jobs",
                Execute = RecoverJobsAsync,
                DependsOn = new() { "Queue" },
                Critical = true // Must succeed to reattach jobs
            },
            new()
            {
                Name = "Cleanup",
                Execute = RecoverCleanupAsync,
                DependsOn = new() { "Locks", "Jobs" },
                Critical = false,
                AllowDegradedMode = true
            },
            new()
            {
                Name = "Orphans",
                Execute = RecoverOrphansAsync,
                DependsOn = new() { "Cleanup" },
                Critical = false,
                AllowDegradedMode = true
            },
            new()
            {
                Name = "Startup",
                Execute = RecoverStartupAsync,
                DependsOn = new() { "Cleanup" },
                Critical = false,
                AllowDegradedMode = true
            },
            new()
            {
                Name = "Webhooks",
                Execute = RecoverWebhooksAsync,
                DependsOn = new() { "Jobs" }, // Can run after jobs reattached
                Critical = false,
                AllowDegradedMode = true
            }
        };

        // Topological sort to get execution order
        var sortedPhases = TopologicalSort(phases);

        var result = new RecoveryResult { TotalPhases = sortedPhases.Count };

        foreach (var phase in sortedPhases)
        {
            _logger.LogInformation("Starting recovery phase: {PhaseName}", phase.Name);
            result.CurrentPhase = phase.Name;

            try
            {
                var success = await phase.Execute(ct);

                if (success)
                {
                    result.CompletedPhases.Add(phase.Name);
                    _logger.LogInformation("Recovery phase completed: {PhaseName}", phase.Name);
                }
                else if (phase.Critical)
                {
                    _logger.LogError("CRITICAL recovery phase failed: {PhaseName}", phase.Name);
                    result.FailedPhase = phase.Name;
                    result.Success = false;
                    return result; // ABORT - critical phase failed
                }
                else if (!phase.AllowDegradedMode)
                {
                    _logger.LogError("Recovery phase failed: {PhaseName}", phase.Name);
                    result.FailedPhase = phase.Name;
                    result.Success = false;
                    return result;
                }
                else
                {
                    _logger.LogWarning("Non-critical recovery phase failed, continuing in degraded mode: {PhaseName}",
                        phase.Name);
                    result.SkippedPhases.Add(phase.Name);
                    result.DegradedMode = true;
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Exception in recovery phase: {PhaseName}", phase.Name);

                if (phase.Critical)
                {
                    result.FailedPhase = phase.Name;
                    result.Success = false;
                    return result; // ABORT
                }
                else
                {
                    _logger.LogWarning("Continuing despite exception in non-critical phase: {PhaseName}",
                        phase.Name);
                    result.SkippedPhases.Add(phase.Name);
                    result.DegradedMode = true;
                }
            }
        }

        result.Success = true;
        _logger.LogInformation("Recovery sequence completed. Degraded mode: {DegradedMode}",
            result.DegradedMode);

        return result;
    }

    private List<RecoveryPhase> TopologicalSort(List<RecoveryPhase> phases)
    {
        var sorted = new List<RecoveryPhase>();
        var visited = new HashSet<string>();
        var visiting = new HashSet<string>();

        void Visit(RecoveryPhase phase)
        {
            if (visited.Contains(phase.Name))
                return;

            if (visiting.Contains(phase.Name))
                throw new InvalidOperationException(
                    $"Circular dependency detected involving phase: {phase.Name}");

            visiting.Add(phase.Name);

            // Visit dependencies first
            foreach (var depName in phase.DependsOn)
            {
                var dep = phases.FirstOrDefault(p => p.Name == depName);
                if (dep == null)
                    throw new InvalidOperationException(
                        $"Phase {phase.Name} depends on unknown phase: {depName}");

                Visit(dep);
            }

            visiting.Remove(phase.Name);
            visited.Add(phase.Name);
            sorted.Add(phase);
        }

        foreach (var phase in phases)
        {
            Visit(phase);
        }

        return sorted;
    }
}

public class RecoveryResult
{
    public bool Success { get; set; }
    public int TotalPhases { get; set; }
    public string? CurrentPhase { get; set; }
    public List<string> CompletedPhases { get; set; } = new();
    public List<string> SkippedPhases { get; set; } = new();
    public string? FailedPhase { get; set; }
    public bool DegradedMode { get; set; }
}
```

4. **Critical Phase Failure Behavior**:
   - **Queue Recovery Fails** → ABORT entire recovery (system unusable)
   - **Job Reattachment Fails** → ABORT (can't recover running jobs)
   - **Lock Recovery Fails** → Continue in degraded mode (warn admins)
   - **Cleanup/Orphans Fail** → Continue in degraded mode (manual cleanup later)

5. **Degraded Mode**:
   - System operational but some features unavailable
   - Locks may be inconsistent → Manual lock management required
   - Orphans not cleaned → Manual cleanup required later
   - Clear alerts to administrators about degraded state

**Impact**: Prevents race conditions and data corruption by enforcing strict execution order based on dependencies.

---

### 7. Atomic File Operations (No Serialization Locks Needed)

**FUNDAMENTAL PRINCIPLE**: All file writes use temp+rename pattern. Queue provides serialization.

**Problem**: Concern about race conditions when cancel operations and job processing both write to same file.

**User Clarification Workflow**:
1. User: "I'm good with that explanation, but you need to serialize all job persistency for that to work"
2. Me: "oh, this writes are to individual job files ? then we don't need serialization, aren't the current job the only ones writing? unless cancel operation comes... then we need serialization"
3. User: "actually cancel busts the entire workspace... but probably should be serialized, or already has some kind of locking?"
4. Me: Traced code flow through CancelJobAsync() and ProcessJobAsync()
5. Me: Found that cancel sets "Cancelling" status and re-queues job
6. Me: ProcessJobAsync checks status at start and handles cancellation
7. Me: Queue is single-threaded, provides natural serialization
8. User: "you got it. write the enhancements"

**Changes Made** (Story 1.1 - Added Atomic File Operations Specification):

1. **Pattern**:
   - Write data to temporary file: `{filename}.tmp`
   - Flush buffers to ensure data on physical disk
   - Atomic rename: `{filename}.tmp` → `{filename}` (overwrites existing)
   - Cleanup: Remove orphaned `.tmp` files on startup

2. **Implementation Requirements**:
   - Apply to: Job files (`*.job.json`), queue state, lock state, statistics, ALL persistent data
   - Filesystem guarantees: Leverage OS atomic rename (Linux `rename()`, Windows `MoveFileEx`)
   - Error handling: If crash before rename, old file remains valid; if crash after, new file is valid
   - Performance: Negligible overhead (<5ms per write including flush)

3. **Code Example**:
```csharp
public async Task SaveJobAsync(Job job)
{
    var finalPath = GetJobFilePath(job.Id);
    var tempPath = finalPath + ".tmp";

    try
    {
        // STEP 1: Write to temp file
        var jsonContent = JsonSerializer.Serialize(job, ...);
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

4. **Recovery Considerations**:
   - On startup: Delete all orphaned `*.tmp` files (incomplete writes from crash)
   - Validation: Job files are either complete or don't exist (never partial)
   - No locking needed: Queue serialization prevents concurrent writes to same file

5. **Why No Serialization Locks Needed**:
   - Each job writes to individual file: `{jobId}.job.json`
   - Queue processing is single-threaded (serialized by queue)
   - Cancel operations set `Cancelling` status and re-queue job
   - ProcessJobAsync checks status at start, handles cancellation
   - No concurrent writes to same file possible
   - **Conclusion**: Queue architecture already provides serialization

**Impact**: Prevents partial write corruption during crashes. No race conditions possible due to queue serialization.

---

## Summary of Changes

### Epic File Modified

**File**: `Epic_CrashResilienceSystem.md`

**Changes**:
1. Executive summary rewritten (state persistence on every startup, not just crash resilience)
2. Recovery flow renamed to "Startup State Restoration Flow" with CRITICAL note
3. Success criteria updated to cover all restart scenarios (clean shutdown, crash, restart)
4. Technical considerations updated with every-startup requirement

### Story Files Enhanced

1. **Story 1.1**: `01_Story_QueuePersistenceRecovery.md`
   - **Added**: 80-line file-based WAL specification (JSONL format, checkpoint strategy, recovery algorithm)
   - **Added**: Atomic file operations specification (temp+rename pattern)
   - **Lines Changed**: ~150 lines added

2. **Story 1.2**: `02_Story_JobReattachmentMonitoring.md`
   - **Complete Rewrite**: Eliminated ALL PID dependency
   - **Added**: Comprehensive sentinel file specification (JSON format)
   - **Added**: Heartbeat requirements (30-second interval, staleness detection)
   - **Added**: 8 new admin APIs for heartbeat monitoring
   - **Added**: Recovery detection after crash (5-minute grace period)
   - **Lines Changed**: ~200 lines rewritten

3. **Story 2.3**: `03_Story_StartupRecoveryDashboard.md`
   - **Added**: 140-line dependency enforcement section
   - **Added**: Topological sort algorithm implementation
   - **Added**: Critical vs. non-critical phase behavior
   - **Added**: Degraded mode specification
   - **Lines Changed**: ~150 lines added

### New Stories Created

1. **Story 1.5**: `05_Story_ResourceStatisticsPersistence.md`
   - **New Story**: Complete specification (320 lines)
   - **Scope**: Real-time statistics persistence with SemaphoreSlim serialization
   - **Added**: Atomic file operations for statistics.json
   - **Added**: File format, recovery logic, manual E2E test plan

2. **Story 2.6**: `05_Story_GitOperationRetry.md`
   - **New Story**: Complete specification (280 lines)
   - **Scope**: Git retry with exponential backoff (3 attempts: 5s, 15s, 45s)
   - **Added**: Error classification (retryable vs. non-retryable)
   - **Added**: Integration points in RepositoryService and JobService
   - **Added**: Manual E2E test plan

### Documentation Created

1. **STORY_1.2_HEARTBEAT_SPECIFICATION.md**
   - **New Document**: Complete heartbeat architecture (200+ lines)
   - **Content**: Sentinel file format, heartbeat writing mechanism, staleness detection, recovery detection, 8 API specifications

2. **EPIC_ENHANCEMENTS_SUMMARY.md** (this file)
   - **New Document**: Comprehensive summary of all enhancements

---

## Implementation Impact

### Story Count Update

**Original**: 8 stories across 2 features
**Updated**: 10 stories across 2 features

**Feature 01_Feat_CoreResilience**: 5 stories (was 4)
1. Queue Persistence with Recovery API
2. Job Reattachment with Monitoring API
3. Resumable Cleanup with State API
4. Aborted Startup Detection with Retry API
5. **Resource Statistics Persistence** (NEW)

**Feature 02_Feat_RecoveryOrchestration**: 5 stories (was 4)
1. Lock Persistence with Inspection API
2. Orphan Detection with Cleanup API
3. Startup Recovery Sequence with Admin Dashboard
4. Callback Delivery Resilience
5. **Git Operation Retry Logic** (NEW)

### Estimated Implementation Complexity Increase

- **Story 1.1** (Queue Persistence): +30% complexity (WAL implementation + atomic writes)
- **Story 1.2** (Job Reattachment): +50% complexity (heartbeat monitoring + staleness detection)
- **Story 1.5** (Statistics Persistence): +15% complexity (new story, smaller scope)
- **Story 2.3** (Recovery Orchestration): +40% complexity (topological sort + degraded mode)
- **Story 2.6** (Git Retry): +15% complexity (new story, smaller scope)

**Overall Epic Complexity**: +25% increase (justified by completeness and reliability gains)

---

## Validation Status

### Epic Completeness

✅ **Every startup recovery**: Clearly specified throughout epic
✅ **Heartbeat monitoring**: Complete specification with zero PID dependency
✅ **File-based WAL**: Comprehensive specification with recovery algorithm
✅ **Statistics persistence**: Real-time save with serialization
✅ **Git retry**: Exponential backoff with error classification
✅ **Dependency enforcement**: Topological sort with complete implementation
✅ **Atomic file operations**: Temp+rename pattern specified

### Code Alignment

✅ **Queue serialization**: Verified in codebase (no explicit locks needed)
✅ **Cancel operations**: Verified status-based handling (no race conditions)
✅ **Statistics service**: Verified save/load methods exist (need hooking)
✅ **Git operations**: Verified in RepositoryService and JobService

---

## Next Steps

### Implementation Priority

**Phase 1: Foundation** (Required for all recovery)
1. Implement AtomicFileWriter component
2. Apply to ALL file persistence operations
3. Add orphaned `.tmp` cleanup on startup

**Phase 2: Core Recovery** (Original stories with enhancements)
1. Story 1.1: Queue Persistence (with WAL + atomic writes)
2. Story 1.2: Job Reattachment (with heartbeat monitoring)
3. Story 1.3: Resumable Cleanup
4. Story 2.1: Lock Persistence
5. Story 2.3: Recovery Orchestration (with topological sort)

**Phase 3: Enhanced Recovery** (New stories)
1. Story 1.5: Resource Statistics Persistence
2. Story 2.6: Git Operation Retry

**Phase 4: Advanced Features**
1. Story 1.4: Aborted Startup Detection
2. Story 2.2: Orphan Detection
3. Story 2.4: Callback Delivery Resilience

---

## Reference Documents

- **Epic**: `Epic_CrashResilienceSystem.md`
- **Gap Analysis**: `EPIC_GAP_ANALYSIS_ENHANCED.md` (Codex architect findings)
- **Heartbeat Spec**: `STORY_1.2_HEARTBEAT_SPECIFICATION.md`
- **All Stories**: `01_Feat_CoreResilience/` and `02_Feat_RecoveryOrchestration/`

---

**Last Updated**: 2025-10-15
**Review Status**: Complete and validated against codebase
**Implementation Ready**: Yes

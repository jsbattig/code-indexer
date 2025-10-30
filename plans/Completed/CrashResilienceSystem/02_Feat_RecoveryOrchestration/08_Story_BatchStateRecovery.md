# Story 8: Batch State Recovery (Optional)

## ⚠️ OPTIONAL STORY - EFFICIENCY OPTIMIZATION ONLY

**This story is OPTIONAL and should only be implemented AFTER all required stories (0-7) are complete and stable.**

This story improves repository preparation efficiency by restoring job batching relationships after crashes. It does NOT affect correctness - jobs will execute correctly without this story, just potentially slower due to redundant repository preparation operations.

## User Story
**As a** system administrator
**I want** job batching relationships preserved across crashes
**So that** repository preparation efficiency is maintained after restart without redundant operations

## Business Value
Optimizes resource usage by preventing redundant git pull and CIDX indexing operations after crashes. When multiple jobs for the same repository are queued, batching allows repository preparation (git pull, CIDX indexing) to run once and benefit all waiting jobs. Without this optimization, crashes cause batch relationships to be lost, resulting in repeated preparation operations that waste time and resources.

**Impact**: Pure efficiency optimization
- **With batching**: 10 jobs for same repo → 1 git pull, 1 CIDX index
- **Without batching (lost on crash)**: 10 jobs → 10 git pulls, 10 CIDX indexes
- **Correctness**: Unaffected - jobs still complete correctly either way

## Current State Analysis

**CRITICAL FINDING: Batching Infrastructure EXISTS But NOT INTEGRATED**

**CURRENT BEHAVIOR**:
- **JobBatchingService EXISTS** (fully implemented, in-memory)
  - Location: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobBatchingService.cs`
  - DI registered: `/claude-batch-server/src/ClaudeBatchServer.Api/Program.cs` line 223
  - **BUT COMPLETELY DISCONNECTED** - not called anywhere in job execution flow
- **JobBatch model EXISTS**
  - Location: `/claude-batch-server/src/ClaudeBatchServer.Core/Models/RepositoryLockInfo.cs` lines 25-33
  - Data structure: `List<Guid> PendingJobs` (flat list, NOT leader/members pattern)
  - In-memory only: `ConcurrentDictionary<string, JobBatch> _activeBatches`
- **JobStatus.BatchedWaiting EXISTS** (line 144 Job.cs) but never set
- **NO INTEGRATION**: Batching service exists but job execution doesn't use it
- **NO PERSISTENCE**: All in-memory, lost on crash
- **NO BatchId ON JOB MODEL**: Job.cs has no BatchId or IsBatchLeader fields

**BATCHING CONCEPT**:
```
Scenario: 5 jobs queued for repo-A
- Job 1 starts: Status = GitPulling (performs git pull)
- Jobs 2-5: Status = BatchedWaiting (wait for Job 1's git pull to complete)
- Job 1 completes git pull: All 5 jobs benefit from shared preparation
- Result: 1 git pull instead of 5
```

**CRASH IMPACT WITHOUT STORY 8**:
```
Before crash:
- Job 1: GitPulling (batch leader)
- Jobs 2-5: BatchedWaiting (batch members)

After crash (WITHOUT recovery):
- Jobs 2-5: Status reset, batch relationship lost
- Each job performs individual git pull
- Result: 5 git pulls instead of 1 (efficiency loss, NOT correctness issue)
```

**IMPLEMENTATION REQUIRED** (if this story is pursued):

**CRITICAL: This is Integration + Persistence, NOT just persistence**

**Phase 1: Integration (Batching Currently Unused)**
- **INTEGRATE** JobBatchingService into job execution flow
- **MODIFY** JobService to call RegisterJobForBatchingAsync before preparation
- **MODIFY** Job execution to check batch status and wait if BatchedWaiting
- **SET** job.Status = BatchedWaiting for batch members
- **COORDINATE** git pull completion across batch

**Phase 2: Job Model Enhancement**
- **ADD** `BatchId` field to Job model (currently missing)
- **DECIDE** if `IsBatchLeader` needed OR use existing `PendingJobs[0]` as leader
- **MATCH** actual JobBatch structure (flat list, not explicit leader/members)

**Phase 3: Persistence**
- **ADD** persistence layer to existing JobBatchingService
- **CREATE** batch state file: `batch-state.json`
- **USE** AtomicFileWriter from Story 0
- **PERSIST** on batch creation, member addition, phase changes

**Phase 4: Recovery**
- **LOAD** batch state on startup
- **RESTORE** BatchId on jobs
- **REBUILD** _activeBatches dictionary
- **RESUME** preparation where it left off

**EFFORT**: 3-4 days (complex - integration + persistence, not just persistence)

## Technical Approach
Add `BatchId` field to Job model to track batch membership. Persist batch state file containing batch leader, batch members, and preparation progress. On recovery, rebuild batch relationships and resume shared repository preparation where it left off.

### Components
- `BatchStatePersistenceService`: Durable batch state storage
- `BatchRecoveryEngine`: Rebuild batch relationships on startup
- Job model enhancement (add `BatchId` field)
- Integration with repository preparation logic
- Integration with Story 3 (Startup Recovery Orchestration)

## Job Model Enhancement

### Add BatchId Field

**File**: `/claude-batch-server/src/ClaudeBatchServer.Core/Models/Job.cs`

**Addition** (after line ~57):
```csharp
// Batch tracking for repository preparation efficiency
public Guid? BatchId { get; set; }
public bool IsBatchLeader { get; set; } = false;
```

**Purpose**:
- `BatchId`: Groups jobs sharing repository preparation (null if not batched)
- `IsBatchLeader`: Marks which job performs preparation for the batch

**Example**:
```
Job 1: BatchId = batch-abc, IsBatchLeader = true  (performs git pull)
Job 2: BatchId = batch-abc, IsBatchLeader = false (waits for Job 1)
Job 3: BatchId = batch-abc, IsBatchLeader = false (waits for Job 1)
```

## Batch State File Specification

### File Structure

**File Location**: `/var/lib/claude-batch-server/claude-code-server-workspace/batch-state.json`

**File Format**:
```json
{
  "version": "1.0",
  "lastUpdated": "2025-10-21T16:00:00.000Z",
  "batches": {
    "batch-abc-123": {
      "batchId": "batch-abc-123",
      "repositoryName": "repo-A",
      "leaderJobId": "job-111",
      "memberJobIds": ["job-222", "job-333", "job-444"],
      "createdAt": "2025-10-21T15:55:00.000Z",
      "preparationStatus": {
        "gitPullStatus": "in_progress",
        "gitPullStartedAt": "2025-10-21T15:55:05.000Z",
        "cidxStatus": "not_started"
      }
    },
    "batch-def-456": {
      "batchId": "batch-def-456",
      "repositoryName": "repo-B",
      "leaderJobId": "job-555",
      "memberJobIds": ["job-666"],
      "createdAt": "2025-10-21T15:58:00.000Z",
      "preparationStatus": {
        "gitPullStatus": "completed",
        "gitPullCompletedAt": "2025-10-21T15:58:30.000Z",
        "cidxStatus": "in_progress",
        "cidxStartedAt": "2025-10-21T15:58:31.000Z"
      }
    }
  }
}
```

**Key Properties**:
- Tracks batch membership (leader + members)
- Records preparation progress (git pull, CIDX status)
- Enables resuming preparation where it left off

## Acceptance Criteria

```gherkin
# ========================================
# CATEGORY: Job Model Enhancement
# ========================================

Scenario: BatchId field added to Job model
  Given Job model at /claude-batch-server/src/ClaudeBatchServer.Core/Models/Job.cs
  When BatchId field added
  Then property is Guid? (nullable)
  And property is null for non-batched jobs
  And property is set to shared GUID for batched jobs

Scenario: IsBatchLeader field added
  Given Job model
  When IsBatchLeader field added
  Then property is bool with default = false
  And only one job per batch has IsBatchLeader = true
  And leader job performs repository preparation for all members

# ========================================
# CATEGORY: Batch State Persistence
# ========================================

Scenario: Persist batch on creation
  Given 3 jobs queued for repo-A
  When batch created with job-1 as leader, jobs 2-3 as members
  Then batch-state.json updated atomically
  And batch entry contains leaderJobId = job-1
  And memberJobIds = [job-2, job-3]
  And preparationStatus shows initial state

Scenario: Persist preparation progress
  Given batch exists with git pull in progress
  When git pull completes
  Then batch-state.json updated
  And preparationStatus.gitPullStatus = "completed"
  And preparationStatus.gitPullCompletedAt timestamp recorded

Scenario: Remove batch on completion
  Given batch with all jobs completed
  When last job finishes
  Then batch removed from batch-state.json
  And file updated atomically

# ========================================
# CATEGORY: Batch Recovery on Startup
# ========================================

Scenario: Recover incomplete batch
  Given batch-state.json shows:
    - Batch batch-abc for repo-A
    - Leader: job-1, Members: [job-2, job-3]
    - gitPullStatus: "in_progress"
  When system restarts
  Then batch relationships restored
  And job-1.BatchId = batch-abc, IsBatchLeader = true
  And job-2.BatchId = batch-abc, IsBatchLeader = false
  And job-3.BatchId = batch-abc, IsBatchLeader = false

Scenario: Resume preparation where it left off
  Given batch recovered with gitPullStatus = "completed", cidxStatus = "not_started"
  When batch recovery completes
  Then git pull step skipped (already done)
  And CIDX indexing resumed
  And all batch members benefit from completed git pull

Scenario: Handle missing leader job
  Given batch-state.json shows batch with leader job-1
  And job-1 was deleted or corrupted
  When recovery runs
  Then batch disbanded (cannot proceed without leader)
  And member jobs converted to individual execution
  And warning logged

Scenario: Handle missing member jobs
  Given batch with leader + 3 members
  And 1 member job was deleted
  When recovery runs
  Then batch continues with remaining members
  And deleted job removed from memberJobIds
  And preparation proceeds normally

# ========================================
# CATEGORY: Efficiency Validation
# ========================================

Scenario: Verify batching saves redundant git pulls
  Given 10 jobs queued for repo-A
  When batch created and executed
  Then git pull performed exactly 1 time
  And all 10 jobs use same git pull result
  And 9 redundant git pulls avoided

Scenario: Verify recovery maintains efficiency
  Given batch with 10 jobs, git pull 50% complete
  When crash occurs and system restarts
  Then batch relationship restored
  And git pull resumes from checkpoint
  And redundant git pulls still avoided

# ========================================
# CATEGORY: Integration with Other Stories
# ========================================

Scenario: Integration with Story 0 (Atomic Writes)
  Given batch state file update
  When persistence triggered
  Then AtomicFileWriter.WriteAtomicallyAsync() used
  And crash during write doesn't corrupt file

Scenario: Integration with Story 3 (Orchestration)
  Given startup recovery sequence
  When batch recovery phase executes
  Then runs after Job Reattachment (Story 2)
  And runs before job execution resumes
  And dependency order enforced by orchestrator

# ========================================
# CATEGORY: Testing Requirements
# ========================================

Scenario: Crash simulation - batch mid-preparation
  Given batch with leader performing git pull
  When server crashes via Process.Kill()
  And server restarts
  Then batch relationship restored
  And git pull resumed or restarted
  And all members still benefit from shared preparation

Scenario: Performance test - batching overhead
  Given 100 jobs for 10 different repositories
  When batches created and persisted
  Then persistence overhead <100ms total
  And minimal impact on job execution time
```

## Implementation Details

### BatchStatePersistenceService Class

**Location**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/BatchStatePersistenceService.cs`

```csharp
namespace ClaudeBatchServer.Core.Services;

/// <summary>
/// Persists job batching state for repository preparation efficiency optimization.
/// OPTIONAL SERVICE - improves performance but not required for correctness.
/// </summary>
public class BatchStatePersistenceService
{
    private readonly string _filePath;
    private readonly SemaphoreSlim _writeLock = new(1, 1);
    private readonly ILogger<BatchStatePersistenceService> _logger;

    public BatchStatePersistenceService(ILogger<BatchStatePersistenceService> logger)
    {
        _logger = logger;
        _filePath = "/var/lib/claude-batch-server/claude-code-server-workspace/batch-state.json";
    }

    /// <summary>
    /// Persists all active batches to disk.
    /// </summary>
    public async Task SaveBatchesAsync(Dictionary<Guid, BatchInfo> batches)
    {
        await _writeLock.WaitAsync();
        try
        {
            var snapshot = new BatchStateSnapshot
            {
                Version = "1.0",
                LastUpdated = DateTime.UtcNow,
                Batches = batches
            };

            // Use atomic write from Story 0
            await AtomicFileWriter.WriteAtomicallyAsync(_filePath, snapshot);

            _logger.LogDebug("Batch state persisted: {Count} active batches", batches.Count);
        }
        finally
        {
            _writeLock.Release();
        }
    }

    /// <summary>
    /// Loads batch state from disk for recovery.
    /// </summary>
    public async Task<Dictionary<Guid, BatchInfo>> LoadBatchesAsync()
    {
        if (!File.Exists(_filePath))
        {
            _logger.LogInformation("No batch state file found, starting without batches");
            return new Dictionary<Guid, BatchInfo>();
        }

        try
        {
            var json = await File.ReadAllTextAsync(_filePath);
            var snapshot = JsonSerializer.Deserialize<BatchStateSnapshot>(json);

            _logger.LogInformation("Batch state recovered: {Count} batches",
                snapshot.Batches.Count);

            return snapshot.Batches;
        }
        catch (JsonException ex)
        {
            _logger.LogError(ex, "Corrupted batch state file, skipping batch recovery");
            return new Dictionary<Guid, BatchInfo>();
        }
    }
}

public class BatchStateSnapshot
{
    public string Version { get; set; } = "1.0";
    public DateTime LastUpdated { get; set; }
    public Dictionary<Guid, BatchInfo> Batches { get; set; } = new();
}

public class BatchInfo
{
    public Guid BatchId { get; set; }
    public string RepositoryName { get; set; } = string.Empty;
    public Guid LeaderJobId { get; set; }
    public List<Guid> MemberJobIds { get; set; } = new();
    public DateTime CreatedAt { get; set; }
    public BatchPreparationStatus PreparationStatus { get; set; } = new();
}

public class BatchPreparationStatus
{
    public string GitPullStatus { get; set; } = "not_started";
    public DateTime? GitPullStartedAt { get; set; }
    public DateTime? GitPullCompletedAt { get; set; }
    public string CidxStatus { get; set; } = "not_started";
    public DateTime? CidxStartedAt { get; set; }
    public DateTime? CidxCompletedAt { get; set; }
}
```

## Integration Points

### Repository Preparation Logic

**Concept**: When repository preparation starts, create batch and persist:

```csharp
// In repository preparation service
public async Task PrepareRepositoryWithBatching(string repositoryName, List<Job> jobsForRepo)
{
    // Create batch
    var batchId = Guid.NewGuid();
    var leaderJob = jobsForRepo.First();
    var memberJobs = jobsForRepo.Skip(1).ToList();

    // Set BatchId on all jobs
    leaderJob.BatchId = batchId;
    leaderJob.IsBatchLeader = true;
    foreach (var member in memberJobs)
    {
        member.BatchId = batchId;
        member.IsBatchLeader = false;
        member.Status = JobStatus.BatchedWaiting;
    }

    // Persist batch state
    var batchInfo = new BatchInfo
    {
        BatchId = batchId,
        RepositoryName = repositoryName,
        LeaderJobId = leaderJob.Id,
        MemberJobIds = memberJobs.Select(j => j.Id).ToList(),
        CreatedAt = DateTime.UtcNow
    };
    await _batchPersistence.SaveBatchAsync(batchInfo);

    // Leader performs preparation, members wait
    await leaderJob.PerformGitPull();
    await leaderJob.PerformCidxIndexing();

    // Notify all members that preparation complete
    foreach (var member in memberJobs)
    {
        member.Status = JobStatus.Running;
    }

    // Remove batch (no longer needed)
    await _batchPersistence.RemoveBatchAsync(batchId);
}
```

### Recovery Logic

**Concept**: Rebuild batches and resume preparation:

```csharp
public async Task RecoverBatchesAsync()
{
    var batches = await _batchPersistence.LoadBatchesAsync();

    foreach (var batch in batches.Values)
    {
        // Load leader and member jobs
        var leaderJob = await _jobService.GetJobAsync(batch.LeaderJobId);
        var memberJobs = await LoadMemberJobsAsync(batch.MemberJobIds);

        if (leaderJob == null)
        {
            // Cannot recover without leader - disband batch
            _logger.LogWarning("Batch {BatchId} leader missing, disbanding",
                batch.BatchId);
            continue;
        }

        // Restore batch relationships
        leaderJob.BatchId = batch.BatchId;
        leaderJob.IsBatchLeader = true;
        foreach (var member in memberJobs)
        {
            member.BatchId = batch.BatchId;
            member.IsBatchLeader = false;
        }

        // Resume preparation from where it left off
        if (batch.PreparationStatus.GitPullStatus != "completed")
        {
            await leaderJob.PerformGitPull();
        }

        if (batch.PreparationStatus.CidxStatus != "completed")
        {
            await leaderJob.PerformCidxIndexing();
        }

        // Proceed with execution
    }
}
```

## Testing Strategy

### Unit Tests
- `BatchStatePersistenceService.SaveBatchesAsync()` - serialization
- `BatchStatePersistenceService.LoadBatchesAsync()` - deserialization
- Batch creation logic
- Batch recovery logic

### Integration Tests
- Create batch, persist, recover
- Batch with preparation progress checkpoint
- Missing leader/member handling

### Crash Simulation Tests
- Crash during git pull (batch mid-preparation)
- Verify batch restored and preparation resumed
- Verify efficiency maintained (no redundant git pulls)

### Performance Tests
- 100 batches persistence time
- Recovery time for large batch state

## Manual E2E Test Plan

### Test 1: Batch Recovery Efficiency
1. Queue 10 jobs for same repository
2. Verify batch created (9 jobs in BatchedWaiting)
3. Kill server during git pull
4. Restart server
5. Verify batch recovered
6. Verify git pull resumes (not restarted from scratch)
7. Verify all 10 jobs complete using shared preparation

### Test 2: Batch Without Recovery (Baseline)
1. Queue 10 jobs for same repository
2. Kill server before batch recovery implemented
3. Restart server
4. Observe: Each job performs individual git pull (10 git pulls)
5. Implement Story 8
6. Repeat test
7. Observe: Only 1 git pull (efficiency improved)

## Success Criteria

- ✅ `BatchId` field added to Job model
- ✅ Batch state persisted on batch creation/updates
- ✅ Atomic write operations prevent corruption
- ✅ Recovery rebuilds batch relationships correctly
- ✅ Preparation resumes where it left off
- ✅ Efficiency improvement measurable (N jobs → 1 git pull)
- ✅ Crash simulation tests pass
- ✅ Zero warnings in build

## Dependencies

**Blocks**: None
**Blocked By**:
- Story 0 (Atomic File Operations) - uses AtomicFileWriter
- Story 3 (Startup Orchestration) - recovery sequence management
- Stories 1-7 must be COMPLETE and STABLE before implementing Story 8

**Shared Components**: Uses AtomicFileWriter from Story 0

## Estimated Effort

**Realistic Estimate**: 1-2 days (if pursued)

**Breakdown**:
- Day 1: Add BatchId to Job model, create BatchStatePersistenceService, basic persistence
- Day 2: Integration with repository preparation logic, recovery logic, testing

**Risk**: Low-medium
- Model change requires database migration (if using DB)
- Integration with existing repository preparation logic may be complex
- NOT critical path - can be deferred indefinitely

## IMPLEMENTATION DECISION

**Recommendation**: **DEFER** until Stories 0-7 are complete, stable, and deployed to production.

**Rationale**:
1. **Not critical**: Jobs execute correctly without batching, just slower
2. **Risk vs reward**: Adds complexity for efficiency gain that may not be significant in practice
3. **Priority**: Core crash resilience (Stories 0-7) is more important than efficiency optimization
4. **Validation needed**: Measure actual efficiency impact in production before implementing

**Alternative Approach**:
- Monitor production after Stories 0-7 deployed
- Measure frequency of batching opportunities (how often multiple jobs for same repo?)
- If batching opportunities are rare (<10% of jobs), Story 8 may not be worth implementing
- If frequent (>30% of jobs), revisit Story 8 implementation

**Decision Point**: Defer implementation decision until production data available.

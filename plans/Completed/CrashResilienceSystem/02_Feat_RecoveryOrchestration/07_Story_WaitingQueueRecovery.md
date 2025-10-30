# Story 7: Repository Waiting Queue Recovery

## User Story
**As a** system administrator
**I want** jobs waiting for locked repositories to persist and recover across crashes
**So that** queued jobs automatically resume waiting after restart without being stuck forever

## Business Value
Prevents jobs from being permanently stuck when crashes occur while waiting for repository access. Without this, jobs in "waiting" state are lost on crash and never resume, requiring manual intervention. Ensures fair queue processing continues across restarts, maintaining job execution order and preventing resource starvation.

## Current State Analysis

**CURRENT BEHAVIOR**:
- Waiting operations stored in-memory only: `ConcurrentDictionary<string, QueuedOperationCollection> _waitingOperations`
  - Location: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/RepositoryLockManager.cs` line 14
  - Contains jobs queued for locked repositories
  - Supports both single-repository and composite (multi-repository) operations
- **NO PERSISTENCE**: Waiting queues lost on crash
- **CRASH IMPACT**: Jobs waiting for repositories are lost forever, must be manually restarted

**DATA STRUCTURES**:
```csharp
// QueuedOperation model (/claude-batch-server/src/ClaudeBatchServer.Core/Models/RepositoryLockInfo.cs)
public class QueuedOperation
{
    public Guid JobId { get; set; }
    public string Username { get; set; }
    public string OperationType { get; set; }
    public DateTime QueuedAt { get; set; }
    public int QueuePosition { get; set; }
    public TimeSpan? EstimatedWaitTime { get; set; }
}

// QueuedOperationCollection - optimized collection with O(1) operations
```

**OPERATIONS USING WAITING QUEUES**:
- `RegisterWaitingOperation()` - Adds job to wait queue for single repository (line 153)
- `RegisterCompositeWaitingOperation()` - Adds job to wait queue for multiple repositories (line 298)
- `RemoveWaitingOperation()` - Removes job from queue (line 180)
- `NotifyWaitingOperations()` - Triggers callback when repository becomes available (line 239)

**IMPLEMENTATION REQUIRED**:
- **CREATE** `WaitingQueuePersistenceService` - NEW CLASS
- **CREATE** waiting queue file format: `waiting-queues.json`
- **MODIFY** `RepositoryLockManager` to persist on queue changes
- **BUILD** Recovery logic to rebuild `_waitingOperations` on startup
- **BUILD** Integration with lock recovery (Story 4) for automatic re-notification

**INTEGRATION POINTS**:
1. Hook into `RegisterWaitingOperation()` - persist after enqueue
2. Hook into `RegisterCompositeWaitingOperation()` - persist after enqueue
3. Hook into `RemoveWaitingOperation()` - persist after dequeue
4. Hook into `NotifyWaitingOperations()` - clear persistence after notification succeeds
5. Add recovery method called from startup orchestration

**EFFORT**: 2 days

## Technical Approach
Persist waiting queue state to disk in structured JSON format preserving queue order, position tracking, and composite operation relationships. On startup, rebuild in-memory `_waitingOperations` dictionary from persisted state. Integrate with lock recovery to automatically re-trigger notifications when locks become available.

### Components
- `WaitingQueuePersistenceService`: Durable waiting queue storage
- `WaitingQueueRecoveryEngine`: Rebuild waiting queues on startup
- Integration with `RepositoryLockManager` (hooks on queue modifications)
- Integration with Story 3 (Startup Recovery Orchestration)
- Integration with Story 4 (Lock Persistence Recovery)

## File Format Specification

### Waiting Queue File Structure

**File Location**: `/var/lib/claude-batch-server/claude-code-server-workspace/waiting-queues.json`

**File Format**:
```json
{
  "version": "1.0",
  "lastUpdated": "2025-10-21T15:30:45.123Z",
  "waitingQueues": {
    "repo-A": {
      "repositoryName": "repo-A",
      "isComposite": false,
      "operations": [
        {
          "jobId": "job-123",
          "username": "alice",
          "operationType": "CLONE",
          "queuedAt": "2025-10-21T15:25:00.000Z",
          "queuePosition": 1,
          "estimatedWaitTime": "00:02:30"
        },
        {
          "jobId": "job-456",
          "username": "bob",
          "operationType": "PULL",
          "queuedAt": "2025-10-21T15:27:00.000Z",
          "queuePosition": 2,
          "estimatedWaitTime": "00:05:00"
        }
      ]
    },
    "COMPOSITE#repo-B+repo-C": {
      "compositeKey": "COMPOSITE#repo-B+repo-C",
      "isComposite": true,
      "repositories": ["repo-B", "repo-C"],
      "operations": [
        {
          "jobId": "job-789",
          "username": "charlie",
          "operationType": "COMPOSITE_JOB_EXECUTION",
          "queuedAt": "2025-10-21T15:28:00.000Z",
          "queuePosition": 1,
          "estimatedWaitTime": null
        }
      ]
    }
  }
}
```

**Key Properties**:
- Preserves queue order (operations array maintains insertion order)
- Tracks queue positions (1-based indexing)
- Distinguishes single-repository vs composite operations
- Includes all QueuedOperation fields for complete recovery

## Acceptance Criteria

```gherkin
# ========================================
# CATEGORY: Persistence on Queue Modifications
# ========================================

Scenario: Persist on RegisterWaitingOperation
  Given job "job-123" cannot acquire lock for "repo-A"
  When RegisterWaitingOperation("repo-A", job-123, "CLONE", "alice") called
  Then waiting queue persisted to /var/lib/claude-batch-server/claude-code-server-workspace/waiting-queues.json
  And file contains repo-A queue with 1 operation
  And operation has jobId=job-123, queuePosition=1
  And atomic write pattern used (temp + rename)

Scenario: Persist on queue growth
  Given repo-A queue has 1 waiting operation
  When second job "job-456" added to queue
  Then waiting queue file updated atomically
  And repo-A queue shows 2 operations
  And queue positions are [1, 2]
  And original job retains position 1

Scenario: Persist on RemoveWaitingOperation
  Given repo-A queue has 3 waiting operations
  When RemoveWaitingOperation("repo-A", job-456) called
  Then waiting queue file updated atomically
  And repo-A queue shows 2 operations
  And queue positions recalculated: [1, 2]

Scenario: Persist on NotifyWaitingOperations success
  Given repo-A queue has 2 waiting operations
  When lock released and callback succeeds
  Then repo-A queue removed from waiting-queues.json
  And file updated atomically
  And only other repository queues remain

Scenario: Persist composite operations
  Given job "job-789" waiting for repos [repo-B, repo-C]
  When RegisterCompositeWaitingOperation() called
  Then composite key "COMPOSITE#repo-B+repo-C" added to file
  And isComposite=true flag set
  And repositories array = ["repo-B", "repo-C"]

# ========================================
# CATEGORY: Recovery on Startup
# ========================================

Scenario: Rebuild waiting queues from file
  Given waiting-queues.json contains:
    - repo-A: 2 operations
    - COMPOSITE#repo-B+repo-C: 1 operation
  When system starts and recovery runs
  Then _waitingOperations dictionary rebuilt
  And _waitingOperations["repo-A"] contains 2 QueuedOperation objects
  And _waitingOperations["COMPOSITE#repo-B+repo-C"] contains 1 operation
  And queue positions match persisted values

Scenario: Recovery preserves queue order
  Given waiting-queues.json shows operations queued at:
    - job-123: 15:25:00 (position 1)
    - job-456: 15:27:00 (position 2)
    - job-789: 15:29:00 (position 3)
  When recovery rebuilds queue
  Then queue order is [job-123, job-456, job-789]
  And positions are [1, 2, 3]
  And FIFO order maintained

Scenario: Recovery with no waiting queues
  Given waiting-queues.json is empty or doesn't exist
  When system starts
  Then _waitingOperations initialized as empty dictionary
  And no errors logged
  And system operational

Scenario: Recovery with corrupted waiting queue file
  Given waiting-queues.json contains invalid JSON
  When recovery runs
  Then error logged with full context
  And _waitingOperations initialized as empty dictionary
  And system continues in degraded mode (warning logged)
  And corrupted file backed up to waiting-queues.json.corrupted.{timestamp}

# ========================================
# CATEGORY: Integration with Lock Recovery
# ========================================

Scenario: Re-trigger notifications after lock recovery
  Given waiting-queues.json shows job-123 waiting for repo-A
  And lock recovery determines repo-A is NOT locked (stale lock cleared)
  When waiting queue recovery completes
  Then NotifyWaitingOperations("repo-A") triggered automatically
  And job-123 callback invoked
  And job-123 can proceed with execution

Scenario: Preserve waiting status when lock persists
  Given waiting-queues.json shows job-456 waiting for repo-B
  And lock recovery determines repo-B IS locked (lock still valid)
  When waiting queue recovery completes
  Then job-456 remains in waiting queue
  And NO notification triggered (lock still held)
  And job-456 waits for lock release event

Scenario: Composite operation with partial lock recovery
  Given composite operation waiting for [repo-C, repo-D]
  And lock recovery shows repo-C locked, repo-D unlocked
  When recovery completes
  Then composite operation remains in waiting queue
  And waits for ALL locks to become available
  And notification only when ALL repositories unlocked

# ========================================
# CATEGORY: Concurrent Access Handling
# ========================================

Scenario: Serialize queue updates with lock
  Given multiple jobs trying to queue for repo-A simultaneously
  When RegisterWaitingOperation() called concurrently
  Then existing _lockObject serializes access
  And file writes are sequential (no corruption)
  And all operations successfully queued

Scenario: Persistence within lock scope
  Given RegisterWaitingOperation() execution
  When queue updated in-memory within lock
  Then file persistence happens WITHIN same lock
  And no race condition between memory and disk state
  And atomic consistency maintained

# ========================================
# CATEGORY: Error Handling
# ========================================

Scenario: Disk full during persistence
  Given waiting queue update triggered
  And disk has no space
  When file write attempted
  Then IOException thrown
  And in-memory queue update rolled back
  And error logged with full context
  And system continues (in-memory state preserved)

Scenario: Permission denied during persistence
  Given waiting queue update triggered
  And service user lacks write permissions
  When file write attempted
  Then UnauthorizedAccessException thrown
  And in-memory queue update rolled back
  And error logged with full context

Scenario: Recovery failure handling
  Given waiting-queues.json cannot be read
  When recovery runs
  Then error logged
  And _waitingOperations initialized as empty
  And startup continues in degraded mode
  And operator alerted via startup log

# ========================================
# CATEGORY: Queue Position Tracking
# ========================================

Scenario: Queue positions after recovery
  Given persisted queue shows positions [1, 2, 3]
  When recovery rebuilds queue
  Then QueuedOperation.QueuePosition values are [1, 2, 3]
  And GetJobQueuePosition() API returns correct values
  And positions visible to clients

Scenario: Position recalculation after removal during runtime
  Given queue [job-A(1), job-B(2), job-C(3)]
  When job-B removed
  Then positions recalculated: [job-A(1), job-C(2)]
  And file persisted with updated positions
  And positions remain correct after crash/recovery

# ========================================
# CATEGORY: Testing Requirements
# ========================================

Scenario: Crash simulation - job waiting for lock
  Given job-123 queued for repo-A
  When server crashes via Process.Kill()
  And server restarts
  Then job-123 still in waiting queue
  And queue position preserved
  And job-123 receives notification when repo-A unlocked

Scenario: Stress test - 100 concurrent queues
  Given 100 repositories with waiting operations
  When all queues updated concurrently
  Then all updates persisted correctly
  And no data loss
  And file remains valid JSON

Scenario: Recovery time - 1000 waiting operations
  Given waiting-queues.json contains 1000 operations across 50 repositories
  When recovery runs
  Then all operations rebuilt in <5 seconds
  And all queue positions correct
  And system ready for notifications
```

## Implementation Details

### WaitingQueuePersistenceService Class

**Location**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/WaitingQueuePersistenceService.cs`

```csharp
namespace ClaudeBatchServer.Core.Services;

/// <summary>
/// Persists repository waiting queues to disk for crash recovery.
/// </summary>
public class WaitingQueuePersistenceService
{
    private readonly string _filePath;
    private readonly SemaphoreSlim _writeLock = new(1, 1);
    private readonly ILogger<WaitingQueuePersistenceService> _logger;

    public WaitingQueuePersistenceService(ILogger<WaitingQueuePersistenceService> logger)
    {
        _logger = logger;
        _filePath = "/var/lib/claude-batch-server/claude-code-server-workspace/waiting-queues.json";
    }

    /// <summary>
    /// Persists current waiting queues to disk atomically.
    /// </summary>
    public async Task SaveWaitingQueuesAsync(
        ConcurrentDictionary<string, QueuedOperationCollection> waitingOperations)
    {
        await _writeLock.WaitAsync();
        try
        {
            var snapshot = new WaitingQueuesSnapshot
            {
                Version = "1.0",
                LastUpdated = DateTime.UtcNow,
                WaitingQueues = new Dictionary<string, QueueSnapshot>()
            };

            foreach (var kvp in waitingOperations)
            {
                var queueSnapshot = new QueueSnapshot
                {
                    Key = kvp.Key,
                    IsComposite = kvp.Key.StartsWith("COMPOSITE#"),
                    Operations = kvp.Value.ToArray().ToList()
                };

                if (queueSnapshot.IsComposite)
                {
                    queueSnapshot.Repositories = ExtractRepositoriesFromCompositeKey(kvp.Key);
                }

                snapshot.WaitingQueues[kvp.Key] = queueSnapshot;
            }

            // Use atomic write from Story 0
            await AtomicFileWriter.WriteAtomicallyAsync(_filePath, snapshot);

            _logger.LogDebug("Waiting queues persisted: {Count} queues",
                snapshot.WaitingQueues.Count);
        }
        finally
        {
            _writeLock.Release();
        }
    }

    /// <summary>
    /// Loads waiting queues from disk for recovery.
    /// </summary>
    public async Task<ConcurrentDictionary<string, QueuedOperationCollection>> LoadWaitingQueuesAsync()
    {
        if (!File.Exists(_filePath))
        {
            _logger.LogInformation("No waiting queues file found, starting with empty queues");
            return new ConcurrentDictionary<string, QueuedOperationCollection>();
        }

        try
        {
            var json = await File.ReadAllTextAsync(_filePath);
            var snapshot = JsonSerializer.Deserialize<WaitingQueuesSnapshot>(json);

            var queues = new ConcurrentDictionary<string, QueuedOperationCollection>();

            foreach (var kvp in snapshot.WaitingQueues)
            {
                var collection = new QueuedOperationCollection();
                foreach (var op in kvp.Value.Operations)
                {
                    collection.Enqueue(op);
                }
                queues[kvp.Key] = collection;
            }

            _logger.LogInformation("Waiting queues recovered: {Count} queues with {TotalOps} total operations",
                queues.Count,
                snapshot.WaitingQueues.Sum(q => q.Value.Operations.Count));

            return queues;
        }
        catch (JsonException ex)
        {
            _logger.LogError(ex, "Corrupted waiting queue file, backing up and starting fresh");

            // Backup corrupted file
            var backupPath = $"{_filePath}.corrupted.{DateTime.UtcNow:yyyyMMddHHmmss}";
            File.Move(_filePath, backupPath);

            return new ConcurrentDictionary<string, QueuedOperationCollection>();
        }
    }

    private List<string> ExtractRepositoriesFromCompositeKey(string compositeKey)
    {
        // "COMPOSITE#repo-A+repo-B" -> ["repo-A", "repo-B"]
        var reposPart = compositeKey.Replace("COMPOSITE#", "");
        return reposPart.Split('+').ToList();
    }
}

public class WaitingQueuesSnapshot
{
    public string Version { get; set; } = "1.0";
    public DateTime LastUpdated { get; set; }
    public Dictionary<string, QueueSnapshot> WaitingQueues { get; set; } = new();
}

public class QueueSnapshot
{
    public string Key { get; set; } = string.Empty;
    public bool IsComposite { get; set; }
    public List<string> Repositories { get; set; } = new();
    public List<QueuedOperation> Operations { get; set; } = new();
}
```

### RepositoryLockManager Integration

**File**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/RepositoryLockManager.cs`

**Modifications**:

1. Add field for persistence service:
```csharp
private readonly WaitingQueuePersistenceService _persistenceService;
```

2. Modify `RegisterWaitingOperation()` (line ~153):
```csharp
public void RegisterWaitingOperation(string repositoryName, Guid jobId, string operationType, string username)
{
    // ... existing code ...

    lock (_lockObject)
    {
        var queue = _waitingOperations.GetOrAdd(repositoryName, _ => new QueuedOperationCollection());
        queue.Enqueue(queuedOperation);
        UpdateQueuePositions(repositoryName);

        // PERSIST AFTER UPDATE
        _ = Task.Run(async () =>
        {
            try
            {
                await _persistenceService.SaveWaitingQueuesAsync(_waitingOperations);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to persist waiting queues after enqueue");
            }
        });

        _logger.LogInformation("Operation queued for repository {RepositoryName}: {OperationType} by {Username} (JobId: {JobId})",
            repositoryName, operationType, username, jobId);
    }
}
```

3. Modify `RemoveWaitingOperation()` (line ~180):
```csharp
public void RemoveWaitingOperation(string repositoryName, Guid jobId)
{
    // ... existing code ...

    lock (_lockObject)
    {
        if (_waitingOperations.TryGetValue(repositoryName, out var queue))
        {
            var removed = queue.Remove(jobId);

            if (removed)
            {
                UpdateQueuePositions(repositoryName);

                // PERSIST AFTER REMOVAL
                _ = Task.Run(async () =>
                {
                    try
                    {
                        await _persistenceService.SaveWaitingQueuesAsync(_waitingOperations);
                    }
                    catch (Exception ex)
                    {
                        _logger.LogError(ex, "Failed to persist waiting queues after removal");
                    }
                });

                _logger.LogInformation("Removed waiting operation for JobId {JobId} from repository {RepositoryName} queue",
                    jobId, repositoryName);
            }
        }
    }
}
```

4. Add recovery method:
```csharp
/// <summary>
/// Recovers waiting queues from persistence on startup.
/// Called by Startup Recovery Orchestration (Story 3).
/// </summary>
public async Task RecoverWaitingQueuesAsync()
{
    lock (_lockObject)
    {
        // Load from disk
        _waitingOperations = await _persistenceService.LoadWaitingQueuesAsync();

        _logger.LogInformation("Waiting queues recovered: {Count} queues",
            _waitingOperations.Count);

        // For each queue, check if repository is now available
        foreach (var queueKey in _waitingOperations.Keys)
        {
            if (!queueKey.StartsWith("COMPOSITE#"))
            {
                // Single repository queue
                if (!IsRepositoryLocked(queueKey))
                {
                    // Repository available, trigger notifications
                    NotifyWaitingOperations(queueKey);
                }
            }
            else
            {
                // Composite queue - check if all repositories available
                var repos = ExtractRepositoriesFromCompositeKey(queueKey);
                if (repos.All(r => !IsRepositoryLocked(r)))
                {
                    NotifyWaitingOperations(queueKey);
                }
            }
        }
    }
}
```

## Integration with Startup Recovery Orchestration

### Dependency Declaration

**In Story 3 Orchestration**:
```csharp
// Waiting Queue Recovery depends on:
// - Lock Recovery (Story 4) - must know which locks exist before re-triggering notifications

var waitingQueuePhase = new RecoveryPhase
{
    Name = "WaitingQueueRecovery",
    Dependencies = new[] { "LockRecovery" },
    Execute = async () =>
    {
        await _repositoryLockManager.RecoverWaitingQueuesAsync();
    }
};
```

## Testing Strategy

### Unit Tests
- `WaitingQueuePersistenceService.SaveWaitingQueuesAsync()` - serialization correctness
- `WaitingQueuePersistenceService.LoadWaitingQueuesAsync()` - deserialization and recovery
- Composite key extraction
- Corrupted file handling

### Integration Tests
- `RepositoryLockManager.RegisterWaitingOperation()` - persistence triggered
- `RepositoryLockManager.RemoveWaitingOperation()` - persistence updated
- `RepositoryLockManager.RecoverWaitingQueuesAsync()` - full recovery flow
- Integration with lock recovery

### Crash Simulation Tests
- Crash with 50 waiting operations across 10 repositories
- Verify all operations recovered
- Verify queue positions preserved
- Verify notifications triggered when locks available

### Performance Tests
- 1000 waiting operations recovery time (<5 seconds)
- Concurrent queue updates (100 simultaneous)
- File size with large queues

## Manual E2E Test Plan

### Test 1: Single Repository Waiting Queue Recovery
1. Create job for locked repo-A (lock held by another job)
2. Verify job queued via `GetQueuedOperations("repo-A")`
3. Kill server via Process.Kill()
4. Restart server
5. Verify job still in queue via API
6. Release lock on repo-A
7. Verify job notified and begins execution

### Test 2: Composite Operation Waiting Queue Recovery
1. Create job requiring [repo-B, repo-C]
2. Lock repo-B with another operation
3. Verify job queued for composite key
4. Kill server
5. Restart server
6. Verify job still waiting
7. Release repo-B lock
8. Verify job notified and acquires both locks

### Test 3: Multiple Queues Recovery
1. Create 10 jobs waiting for 5 different repositories
2. Verify all queued correctly
3. Kill server
4. Restart server
5. Verify all 10 jobs recovered in correct queues
6. Verify queue positions preserved

## Success Criteria

- ✅ Waiting queues persisted on every queue modification
- ✅ Atomic write operations prevent corruption
- ✅ Recovery rebuilds all queues correctly
- ✅ Queue order and positions preserved
- ✅ Integration with lock recovery triggers notifications
- ✅ Composite operations handled correctly
- ✅ Crash simulation tests pass (50 operations recovered)
- ✅ Performance: 1000 operations recover in <5 seconds
- ✅ Zero warnings in build

## Dependencies

**Blocks**: None
**Blocked By**:
- Story 0 (Atomic File Operations) - uses AtomicFileWriter
- Story 4 (Lock Persistence) - integration for re-triggering notifications
- Story 3 (Startup Orchestration) - recovery sequence management

**Shared Components**: Uses AtomicFileWriter from Story 0

## Estimated Effort

**Realistic Estimate**: 2 days

**Breakdown**:
- Day 1: Create WaitingQueuePersistenceService, file format, basic persistence
- Day 2: Integration with RepositoryLockManager, recovery logic, testing

**Risk**: Medium - straightforward persistence with well-defined integration points

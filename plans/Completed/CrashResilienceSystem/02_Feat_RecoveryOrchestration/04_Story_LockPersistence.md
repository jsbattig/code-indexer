# Story 4: Lock Persistence IMPLEMENTATION with Automated Recovery

## ⚠️ CRITICAL CLARIFICATION: This is NEW IMPLEMENTATION, NOT just recovery

**Lock files DO NOT EXIST in the current codebase.** This story requires implementing the entire lock file persistence system from scratch, not just recovering existing locks.

## User Story
**As a** system administrator
**I want** repository locks persisted to disk with automated recovery and structured logging
**So that** lock state survives crashes and automatic stale lock detection prevents abandoned locks

## Business Value
Maintains repository access control integrity across system failures by persisting lock state, preventing concurrent access conflicts after recovery. Fully automated stale lock detection and cleanup ensures system health without manual intervention. Comprehensive structured logging provides complete visibility.

## Current State Analysis

**CURRENT BEHAVIOR**:
- **Locks**: In-memory ONLY using `ConcurrentDictionary<string, RepositoryLockInfo>`
  - Location: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/RepositoryLockManager.cs` line 13
  - Lock acquisition: `AcquireRepositoryLockAsync()` line 24
  - Lock release: `ReleaseRepositoryLockAsync()` line 61
- **NO LOCK FILES**: Lock files do not exist anywhere in the codebase
- **NO PERSISTENCE**: All lock state lost on crash
- **CRASH IMPACT**: All locks lost, concurrent operations can corrupt repositories after restart

**CURRENT LOCK DATA STRUCTURE**:
```csharp
// RepositoryLockManager.cs line 13 - IN-MEMORY ONLY
private readonly ConcurrentDictionary<string, RepositoryLockInfo> _repositoryLocks = new();

// RepositoryLockInfo model (/claude-batch-server/src/ClaudeBatchServer.Core/Models/RepositoryLockInfo.cs)
public class RepositoryLockInfo
{
    public string RepositoryName { get; set; }
    public string LockHolder { get; set; }      // job-{id}
    public string OperationType { get; set; }   // CLONE, PULL, etc.
    public DateTime AcquiredAt { get; set; }
    public CancellationToken CancellationToken { get; set; }
    public Guid OperationId { get; set; }
    public string ProcessId { get; set; }
}
```

**IMPLEMENTATION REQUIRED** (NET NEW):
- **CREATE** `/locks/` directory under workspace
- **BUILD** `LockPersistenceService` - NEW CLASS
- **BUILD** Lock file creation on `TryAdd` to `_repositoryLocks`
- **BUILD** Lock file deletion on `TryRemove` from `_repositoryLocks`
- **BUILD** Lock file format: `{repository}.lock.json` with complete metadata
- **BUILD** Stale lock detection (10-minute timeout based on timestamp)
- **BUILD** Recovery logic to restore locks on startup
- **MODIFY** `RepositoryLockManager.AcquireRepositoryLockAsync()` to persist on success
- **MODIFY** `RepositoryLockManager.ReleaseRepositoryLockAsync()` to delete file on release

**INTEGRATION POINTS**:
1. `RepositoryLockManager.AcquireRepositoryLockAsync()` (line 24) - Add file write after `TryAdd`
2. `RepositoryLockManager.ReleaseRepositoryLockAsync()` (line 61) - Add file delete after `TryRemove`
3. `RepositoryLockManager` constructor - Add recovery method call
4. Startup orchestration (Story 3) - Integrate lock recovery phase

**FILES TO MODIFY**:
- `/claude-batch-server/src/ClaudeBatchServer.Core/Services/RepositoryLockManager.cs` (add persistence hooks)
- Create new `/claude-batch-server/src/ClaudeBatchServer.Core/Services/LockPersistenceService.cs`

**LOCK FILE LOCATIONS**:
- `/var/lib/claude-batch-server/claude-code-server-workspace/locks/{repository}.lock.json`

**EFFORT**: 5-6 days (complete new implementation, not just recovery)

## Technical Approach
Implement durable lock storage that persists all repository locks to disk, enables automatic recovery of lock state after crashes, automatically detects and clears stale locks from terminated processes. All operations logged to startup log.

### Components
- `LockPersistenceService`: Durable lock storage
- `LockRecoveryEngine`: Automated lock state restoration with degraded mode support
- `StaleDetector`: Automatic identification and cleanup of abandoned locks
- `StartupLogger`: Structured logging of all lock operations

## Acceptance Criteria

```gherkin
# ========================================
# CATEGORY: Lock File Creation and Structure
# ========================================

Scenario: Lock file creation on repository acquisition
  Given job acquires lock on repository "test-repo"
  When lock is granted
  Then lock file created at /var/lib/claude-batch-server/claude-code-server-workspace/locks/test-repo.lock.json
  And file contains: repositoryName, holder (jobId), operation, timestamp, pid, operationId
  And atomic write operation used (temp + rename)

Scenario: Lock file location and naming
  Given repository named "my-project"
  When lock is acquired
  Then lock file path is /var/lib/claude-batch-server/claude-code-server-workspace/locks/my-project.lock.json
  And filename matches repository name exactly
  And .lock.json extension used

Scenario: Lock metadata completeness
  Given job "job-123" acquires lock for "clone" operation
  And process PID is 5678
  When lock file is written
  Then holder = "job-123"
  And operation = "clone"
  And timestamp in ISO 8601 UTC format
  And pid = 5678
  And operationId is unique UUID

Scenario: Lock file atomic write
  Given lock acquisition granted
  When lock file is written
  Then data written to test-repo.lock.json.tmp first
  And FileStream.FlushAsync() called
  And file renamed to test-repo.lock.json atomically
  And corruption prevention ensured

# ========================================
# CATEGORY: Stale Lock Detection (10-Minute Timeout)
# ========================================

Scenario: Fresh lock detection (<10 minutes old)
  Given lock file timestamp is 5 minutes old
  When stale detection runs
  Then lock classified as "fresh"
  And lock remains active
  And no cleanup triggered

Scenario: Stale lock detection (>10 minutes old)
  Given lock file timestamp is 15 minutes old
  When stale detection runs
  Then lock classified as "stale"
  And automatic cleanup initiated
  And lock file removed
  And repository becomes available

Scenario: Boundary condition - exactly 10 minutes
  Given lock file timestamp is exactly 600 seconds old
  When stale detection runs
  Then lock classified as "stale" (inclusive boundary)
  And cleanup triggered

Scenario: Stale lock with terminated process
  Given lock file contains PID 12345
  And process 12345 no longer exists
  When stale detection runs
  Then process lookup fails
  And lock immediately marked stale (regardless of time)
  And cleanup executes

Scenario: Stale lock with active process
  Given lock file timestamp is 15 minutes old
  And process still exists and running
  When stale detection runs
  Then lock still marked stale (timeout takes precedence)
  And warning logged (process may be hung)
  And cleanup proceeds

# ========================================
# CATEGORY: Lock Recovery on Startup
# ========================================

Scenario: Successful lock recovery for all locks
  Given 5 lock files exist in /workspace/locks/
  And all locks have valid JSON format
  When lock recovery executes
  Then all 5 locks loaded into memory
  And lock ownership preserved
  And timeout values maintained
  And repositories remain protected

Scenario: Lock recovery with mixed validity
  Given 3 valid lock files exist
  And 2 corrupted lock files exist
  When lock recovery executes
  Then 3 valid locks recovered successfully
  And 2 corrupted locks trigger degraded mode
  And corrupted repositories marked "unavailable"
  And system continues with partial functionality

Scenario: Empty locks directory
  Given no lock files exist
  When lock recovery executes
  Then recovery completes successfully
  And no locks loaded
  And all repositories available

Scenario: Lock file permissions error
  Given lock file exists but is unreadable
  When lock recovery attempts to read
  Then UnauthorizedAccessException thrown
  And lock marked as corrupted
  And repository marked "unavailable"
  And error logged with file path

# ========================================
# CATEGORY: Corruption Handling and Degraded Mode
# ========================================

Scenario: Malformed JSON in lock file
  Given lock file contains invalid JSON syntax
  When lock recovery loads file
  Then JsonException thrown
  And corruption detected
  And lock file backed up to {filename}.corrupted.{timestamp}
  And repository marked "unavailable"
  And degraded mode triggered

Scenario: Missing required fields in lock file
  Given lock file JSON missing "holder" field
  When lock recovery validates file
  Then validation fails
  And lock marked as corrupted
  And repository marked "unavailable"
  And error logged with missing field

Scenario: Invalid data types in lock file
  Given lock file has "pid": "not_a_number"
  When deserialization occurs
  Then JsonException thrown
  And corruption handling triggered
  And repository marked "unavailable"

Scenario: Empty lock file
  Given lock file exists with 0 bytes
  When lock recovery reads file
  Then deserialization fails
  And corruption detected
  And repository marked "unavailable"

Scenario: Corrupted lock file backup
  Given lock file corrupted
  When backup is created
  Then file moved to {repositoryName}.lock.json.corrupted.{yyyyMMddHHmmss}
  And original file removed
  And backup preserved for investigation

Scenario: Degraded mode per-repository isolation
  Given repo-A lock is corrupted
  And repo-B and repo-C locks are valid
  When recovery completes
  Then ONLY repo-A marked "unavailable"
  And repo-B and repo-C fully functional
  And lock enforcement remains enabled system-wide
  And degraded_mode = true
  And corrupted_resources = ["lock:repo-A"]

# ========================================
# CATEGORY: Lock Enforcement System-Wide
# ========================================

Scenario: Lock enforcement enabled despite degraded mode
  Given 1 lock corrupted (degraded mode active)
  When job attempts to acquire lock on different repository
  Then lock enforcement still active
  And lock acquisition follows normal rules
  And corrupted repository does not affect others

Scenario: Job targeting unavailable repository
  Given repo-A marked "unavailable" due to corruption
  When job attempts to acquire lock on repo-A
  Then lock acquisition rejected
  And error returned: "Repository unavailable due to corrupted lock state"
  And job fails with clear error message

Scenario: Lock release for available repository
  Given repo-B lock recovered successfully
  And job holds lock on repo-B
  When job releases lock
  Then lock file removed atomically
  And repository becomes available
  And normal operation continues

# ========================================
# CATEGORY: Atomic Lock Operations
# ========================================

Scenario: Atomic lock acquire
  Given repository is available
  When job acquires lock
  Then lock file written atomically (temp + rename)
  And lock immediately effective
  And concurrent acquisitions blocked

Scenario: Atomic lock release
  Given job holds lock
  When job releases lock
  Then lock file deleted
  And deletion is atomic operation
  And repository immediately available

Scenario: Lock acquire failure rollback
  Given lock acquisition initiated
  And file write fails with IOException
  When exception occurs
  Then temp file cleaned up
  And lock NOT granted
  And repository remains in previous state

# ========================================
# CATEGORY: Concurrency and Serialization
# ========================================

Scenario: Concurrent lock acquisitions on different repositories
  Given 5 jobs attempt lock acquisitions simultaneously
  And each targets different repository
  When acquisitions execute
  Then all succeed
  And no conflicts occur
  And each lock file written correctly

Scenario: Concurrent lock acquisitions on same repository
  Given 2 jobs attempt lock acquisition on "test-repo"
  When acquisitions execute simultaneously
  Then one job succeeds (first to acquire)
  And other job blocked (lock already held)
  And lock enforcement prevents concurrent access

Scenario: Lock file write serialization per repository
  Given lock operations on single repository
  When multiple operations attempted
  Then operations serialized
  And file integrity maintained

# ========================================
# CATEGORY: Error Scenarios
# ========================================

Scenario: Disk full during lock file write
  Given disk space exhausted
  When lock acquisition attempts write
  Then IOException thrown
  And lock NOT granted
  And temp file cleaned up
  And repository remains available

Scenario: Permission denied on locks directory
  Given /workspace/locks/ directory is read-only
  When lock file write attempted
  Then UnauthorizedAccessException thrown
  And lock NOT granted
  And error logged with full context

Scenario: Network filesystem timeout
  Given workspace on network filesystem (NFS)
  And network timeout occurs
  When lock file write attempted
  Then timeout exception thrown
  And retry mechanism activates
  And operation eventually succeeds or fails cleanly

Scenario: Lock file locked by external process
  Given lock file locked by backup process
  When lock release attempts deletion
  Then IOException thrown (file in use)
  And retry mechanism activates
  And eventual release when file available

# ========================================
# CATEGORY: Edge Cases
# ========================================

Scenario: Lock with special characters in repository name
  Given repository named "test-repo_v2.0-beta"
  When lock is acquired
  Then lock file name properly escaped
  And file created successfully
  And recovery can read file

Scenario: Lock file with future timestamp
  Given lock file timestamp is 5 minutes in future
  When stale detection runs
  Then clock skew detected
  And warning logged
  And lock treated as fresh (conservative)

Scenario: Lock file with very old timestamp
  Given lock file timestamp is 30 days old
  When stale detection runs
  Then lock immediately marked stale
  And cleanup executes
  And repository becomes available

Scenario: Multiple lock files for same repository
  Given test-repo.lock.json exists
  And test-repo.lock.json.tmp exists (orphaned)
  When recovery scans directory
  Then .tmp file deleted (orphaned temp file cleanup)
  And primary lock file processed normally

# ========================================
# CATEGORY: High-Volume Scenarios
# ========================================

Scenario: Recovery with 100 lock files
  Given 100 lock files exist
  When lock recovery executes
  Then all locks processed within 5 seconds
  And all valid locks restored
  And corrupted locks handled gracefully

Scenario: Stale detection with 50 locks
  Given 50 lock files exist
  And 10 are stale (>10 minutes old)
  When stale detection runs
  Then 10 stale locks identified
  And cleanup executes for all 10
  And 40 fresh locks remain active

# ========================================
# CATEGORY: Observability and Logging
# ========================================

Scenario: Lock recovery logging on startup
  Given lock recovery completes
  When startup log is written
  Then entry contains: component="LockRecovery"
  And operation="lock_recovery_completed"
  And locks_found count
  And locks_recovered count
  And stale_locks_cleared count
  And corrupted_locks count
  And corrupted_repositories array
  And degraded_mode boolean
  And lock_enforcement_enabled = true

Scenario: Stale lock cleanup logging
  Given stale lock detected
  When cleanup executes
  Then warning logged with repository name
  And lock age logged
  And PID logged
  And cleanup result logged

Scenario: Corruption detection logging
  Given corrupted lock file detected
  When corruption handling runs
  Then error logged with: repository name, file path, error details
  And backup file path logged
  And degraded mode trigger logged

Scenario: Lock acquisition logging
  Given lock acquired
  When operation completes
  Then info logged with: repository, jobId, operation, timestamp
  And lock file path logged

Scenario: Lock release logging
  Given lock released
  When operation completes
  Then info logged with: repository, jobId, duration held
  And release result logged
```

## Manual E2E Test Plan

**Prerequisites**:
- Claude Server with repositories
- Multiple active jobs
- Admin token

**Test Steps**:

1. **Create Repository Locks**:
   ```bash
   # Start jobs to create locks
   for repo in repo1 repo2 repo3; do
     JOB_ID=$(curl -X POST https://localhost/api/jobs \
       -H "Authorization: Bearer $USER_TOKEN" \
       -H "Content-Type: application/json" \
       -d "{\"prompt\": \"Task\", \"repository\": \"$repo\"}" | jq -r '.jobId')

     curl -X POST "https://localhost/api/jobs/$JOB_ID/start" \
       -H "Authorization: Bearer $USER_TOKEN"
   done

   # Verify locks exist in workspace
   sudo ls -lah /var/lib/claude-batch-server/workspace/locks/
   ```
   **Expected**: 3 lock files created
   **Verify**: repo1.lock.json, repo2.lock.json, repo3.lock.json exist

2. **Crash and Monitor Recovery**:
   ```bash
   # Crash server
   sudo pkill -9 -f "ClaudeBatchServer.Api"

   # Restart
   sudo systemctl start claude-batch-server
   sleep 10

   # Check startup log for lock recovery
   curl -s https://localhost/api/admin/startup-log \
     -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.operations[] | select(.component=="LockRecovery")'
   ```
   **Expected**: Startup log shows 3 locks recovered
   **Verify**: Lock recovery logged with success status

3. **Test Automatic Stale Lock Detection**:
   ```bash
   # Stop all running jobs (simulates stale locks)
   for pid in $(ps aux | grep claude-code | grep -v grep | awk '{print $2}'); do
     sudo kill -9 $pid
   done

   # Wait for heartbeat staleness (>10 minutes)
   # OR manually backdate lock files to simulate staleness
   for lock in /var/lib/claude-batch-server/workspace/locks/*.lock.json; do
     sudo jq '.acquiredAt = "'$(date -u -d '15 minutes ago' +%Y-%m-%dT%H:%M:%S.000Z)'"' \
       "$lock" > /tmp/lock-stale.json
     sudo mv /tmp/lock-stale.json "$lock"
   done

   # Restart to trigger stale detection
   sudo systemctl restart claude-batch-server
   sleep 10

   # Check startup log
   curl -s https://localhost/api/admin/startup-log \
     -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.operations[] | select(.component=="LockRecovery") | .stale_locks_cleared'
   ```
   **Expected**: Stale locks automatically detected and cleared
   **Verify**: Startup log shows stale lock cleanup

4. **Test Degraded Mode (Corrupted Lock)**:
   ```bash
   # Stop server
   sudo systemctl stop claude-batch-server

   # Corrupt one lock file
   echo "CORRUPTED DATA" | sudo tee /var/lib/claude-batch-server/workspace/locks/repo1.lock.json

   # Restart
   sudo systemctl start claude-batch-server
   sleep 10

   # Check startup log for degraded mode
   curl -s https://localhost/api/admin/startup-log \
     -H "Authorization: Bearer $ADMIN_TOKEN" | jq '{degraded_mode, corrupted_resources}'
   ```
   **Expected**: Degraded mode = true, repo1 marked unavailable
   **Verify**: Other repos (repo2, repo3) still functional, lock enforcement still enabled

**Success Criteria**:
- ✅ Locks persisted durably
- ✅ Recovery restores lock state automatically
- ✅ Stale detection works automatically
- ✅ Startup log provides complete visibility
- ✅ Degraded mode marks corrupted resources, keeps system operational

## Observability Requirements

**Structured Logging** (all logged to startup log):
- Lock persistence operations (atomic file writes)
- Automatic recovery actions with lock validation
- Automatic stale detection and cleanup
- Degraded mode triggers (corrupted lock files)
- Repository unavailability marking

**Logged Data Fields**:
```json
{
  "component": "LockRecovery",
  "operation": "lock_recovery_completed",
  "timestamp": "2025-10-15T10:00:30.123Z",
  "duration_ms": 234,
  "locks_found": 5,
  "locks_recovered": 4,
  "stale_locks_cleared": 1,
  "corrupted_locks": 1,
  "corrupted_repositories": ["repo-B"],
  "degraded_mode": true,
  "lock_enforcement_enabled": true
}
```

**Metrics** (logged to structured log):
- Locks persisted/recovered (success rate >99%)
- Stale lock frequency (automatic cleanup)
- Corrupted lock frequency
- Recovery success rate
- Degraded mode instances

## Definition of Done
- [ ] Implementation complete with TDD
- [ ] Manual E2E test executed successfully by Claude Code
- [ ] Lock persistence works reliably with atomic operations
- [ ] Recovery restores all valid locks automatically
- [ ] Stale locks detected and cleared automatically
- [ ] Degraded mode marks corrupted resources correctly
- [ ] Structured logging provides complete visibility
- [ ] Code reviewed and approved
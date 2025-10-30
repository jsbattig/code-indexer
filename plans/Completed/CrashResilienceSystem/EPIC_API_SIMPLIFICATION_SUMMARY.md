# Epic API Simplification - Complete Summary

## User's Final Architectural Decisions

This document summarizes the critical simplification decisions made during epic review.

## Decision 1: Remove Story 1.3 (Cleanup Resumption)

**User Decision**: "Don't do this. this is extremely hard to control. remove this."

**Action Taken**:
- REMOVED Story 1.3 completely (Resumable Cleanup with State API)
- Deleted file: `03_Story_ResumableCleanupState.md`
- Renumbered: Story 1.4 → 1.3, Story 1.5 → 1.4

**Rationale**:
- Multi-phase checkpointed cleanup too complex
- State machine for cleanup phases (cidx → docker → filesystem) adds complexity
- Hard to guarantee correctness when resuming mid-cleanup
- Better approach: Accept interrupted cleanup = orphaned resources → Orphan detection (Story 2.2) cleans them up later

**Impact**:
- Story count: 10 → 9 stories
- Orphan detection becomes MORE important
- Cleanup remains synchronous (simple, no state management)

---

## Decision 2: API Simplification (36 → 1 API)

**User Decision**: "Overkill. Recovery should be completely automated, no APIs, log error conditions, recovery should be resilient preferring starting up and leave a log trail of recovery operations fail. At most add ONE API that returns a log of the recovery operation in json format"

**Before**: 36 admin APIs
- 26 inspection APIs (queue status, job heartbeats, lock inspection, etc.)
- 10 manual intervention APIs (repair queue, force-reattach, skip cleanup, etc.)

**After**: 1 API
- ✅ `GET /api/admin/startup-log` - Returns JSON array of startup operations

**Philosophy**: Fully automated recovery with comprehensive structured logging. Visibility via single startup log API.

**API Removal by Story**:

### Story 1.1 - Queue Persistence
**Removed**:
- `GET /api/admin/recovery/queue/status`
- `GET /api/admin/recovery/queue/metrics`
- `GET /api/admin/queue/snapshot`
- `POST /api/admin/recovery/queue/repair`
- `GET /api/admin/recovery/queue/wal-status`

**Replacement**: Structured logging to startup log

### Story 1.2 - Job Reattachment
**Removed**:
- `GET /api/admin/recovery/jobs/status`
- `GET /api/admin/recovery/jobs/sentinels`
- `GET /api/admin/recovery/jobs/heartbeats`
- `GET /api/admin/recovery/jobs/metrics`
- `GET /api/admin/recovery/jobs/failed`
- `GET /api/admin/recovery/jobs/stale`
- `POST /api/admin/recovery/jobs/resume`
- `GET /api/admin/jobs/{id}/health`

**Replacement**: Structured logging to startup log

### Story 1.3 (formerly 1.4) - Aborted Startup Detection
**Removed**:
- `GET /api/admin/recovery/startup/status`
- `GET /api/admin/recovery/startup/cleanup-log`
- `POST /api/admin/recovery/startup/retry`
- `GET /api/admin/recovery/startup/history`

**Replacement**: Structured logging to startup log

### Story 1.4 (formerly 1.5) - Resource Statistics
**Removed**: None (this story had no APIs, only file-based persistence)

### Story 2.1 - Lock Persistence
**Removed**:
- `GET /api/admin/recovery/locks`
- `GET /api/admin/recovery/locks/{repo}/status`
- `POST /api/admin/recovery/locks/{repo}/release`
- `GET /api/admin/recovery/locks/stale`
- `POST /api/admin/recovery/locks/clear-stale`

**Replacement**: Structured logging to startup log

### Story 2.2 - Orphan Detection
**Removed**:
- `GET /api/admin/recovery/orphans/scan`
- `GET /api/admin/recovery/orphans/candidates`
- `POST /api/admin/recovery/orphans/cleanup`
- `GET /api/admin/recovery/orphans/log`

**Replacement**: Structured logging to startup log

### Story 2.3 - Startup Recovery Sequence
**Removed**:
- `GET /api/admin/recovery/status`
- `GET /api/admin/recovery/phases`
- `GET /api/admin/recovery/dashboard-data`
- `GET /api/admin/recovery/metrics`
- `POST /api/admin/recovery/skip-phase`

**ADDED (only API in entire epic)**:
- ✅ `GET /api/admin/startup-log` - Single API for all recovery visibility

**Replacement**: Startup log API + comprehensive structured logging

### Story 2.4 - Callback Delivery
**Removed**:
- `GET /api/admin/recovery/webhooks/pending`
- `GET /api/admin/recovery/webhooks/recovered`
- `GET /api/admin/recovery/webhooks/delivery-log`
- `POST /api/admin/recovery/webhooks/retry`

**Replacement**: Structured logging to startup log

### Story 2.5 (formerly 2.6) - Git Retry
**Removed**: None (this story had no APIs initially)

---

## Decision 3: Degraded Mode Redefinition

**User Decision**: "No features can be disabled, that's a hard error. by favor operation I mean, if a repo or job is corrupted, that becomes unusable, but the system needs to start intact."

**OLD Definition (WRONG)**:
- Lock recovery fails → Lock enforcement disabled system-wide
- System operational but lock feature turned off
- Multiple jobs can access same repository

**NEW Definition (CORRECT)**:
- Lock recovery fails → Specific corrupted lock marked unusable
- Lock enforcement remains enabled system-wide
- Corrupted lock's repository marked "unavailable" (cannot be used)
- All OTHER locks work normally

**Example Scenario**:
```
Startup:
1. Queue Recovery → Success ✅ (15 jobs restored)
2. Job Reattachment → Success ✅ (3 jobs reattached)
3. Lock Recovery → Partial Success ⚠️
   - repo-A lock recovered ✅
   - repo-B lock CORRUPTED ❌ → Mark repo-B "unavailable"
   - repo-C lock recovered ✅
4. System starts: Fully operational with ALL features enabled
5. Degraded state: repo-B unavailable (jobs targeting repo-B will fail with "repository unavailable")
```

**Critical Phases** (redefined):
- **Critical** (fail = ABORT startup): Queue recovery, Job reattachment
- **Non-critical** (fail = mark resource corrupted, continue): Individual locks, individual jobs, individual cleanup operations

**Implementation Pattern**:
```csharp
// Lock Recovery
foreach (var lockFile in lockFiles)
{
    try
    {
        var lock = await LoadLockAsync(lockFile);
        _locks.Add(lock); // Success
    }
    catch (Exception ex)
    {
        _logger.LogWarning("Lock file corrupted: {File}, marking repository unavailable", lockFile);
        var repoName = ExtractRepoName(lockFile);
        _unavailableRepos.Add(repoName); // Mark specific repo unavailable
        result.CorruptedResources.Add($"lock:{repoName}");
        result.DegradedMode = true; // System operational, specific resource unusable
    }
}
```

**Degraded Mode Indicators**:
- `DegradedMode = true` (system operational, some resources corrupted)
- `CorruptedResources = ["lock:repo-B", "job:abc123"]` (list of unusable resources)
- Startup log shows: "Lock recovery completed with 1 corrupted lock, repository repo-B marked unavailable"

**User Benefit**:
- System ALWAYS starts (unless Queue/Jobs completely fail)
- ALL features remain enabled (lock enforcement, cleanup, orphan detection)
- Specific corrupted resources marked unavailable
- Admins can fix corrupted resources while system runs

**NO Feature Disabling**: Lock enforcement never turned off, cleanup never skipped, orphan detection never disabled. Only specific corrupted resources become unusable.

---

## Decision 4: Webhook Storage Confirmed

**User Decision**: "Yes, that's good."

**Implementation**:
- **File**: `{workspace}/callbacks.queue.json`
- **Format**: Pending webhooks with retry state
- **Write pattern**: Atomic file operations (temp+rename)
- **Recovery**: Load pending callbacks on startup, resume delivery
- **Retry**: Exponential backoff (30s, 2min, 10min) for failed deliveries

---

## Decision 5: Output Capture Clarification (Story 1.2)

**User Feedback**: "Make sure the spec is clear we can't run the process and try to capture stdout. the only way this works is by dumping the output to a predictable filename."

**Critical Addition to Story 1.2**:

**NO stdout/stderr capture**: Job processes run as background processes. We CANNOT capture stdout/stderr directly.

**How Job Output Works**:
1. AgentExecutor launches adaptor binary (e.g., claude-as-claude) as background process
2. Adaptor binary writes conversation to `{workspace}/jobs/{jobId}/{sessionId}.md`
3. ContextLifecycleManager copies completed markdown to central repository
4. Conversation API reads markdown from workspace or central repository

**State Reconstruction**: Read `{sessionId}.md` files, NOT stdout/stderr

---

## Updated Epic Scope

### Feature 01_Feat_CoreResilience (4 stories, was 5)
1. **Story 1.1**: Queue Persistence with Automated Recovery
2. **Story 1.2**: Job Reattachment with Automated Monitoring
3. **Story 1.3**: Aborted Startup Detection with Automated Retry (renumbered from 1.4)
4. **Story 1.4**: Resource Statistics Persistence (renumbered from 1.5)

### Feature 02_Feat_RecoveryOrchestration (5 stories, unchanged)
1. **Story 2.1**: Lock Persistence with Automated Recovery
2. **Story 2.2**: Orphan Detection with Automated Cleanup
3. **Story 2.3**: Startup Recovery Sequence with Startup Log API
4. **Story 2.4**: Callback Delivery Resilience
5. **Story 2.5**: Git Operation Retry Logic (renumbered from 2.6)

**Total Stories**: 9 stories (was 10)
**Total APIs**: 1 API (was 36)
**API Reduction**: 97%

---

## Updated Problem Coverage

### Problems REMOVED from Epic:
- ❌ **Problem #5**: Interrupted Cleanup = Resource Leaks

**New Approach**: Accept that crashed cleanups leak resources. Story 2.2 (Orphan Detection) periodically scans and cleans orphaned Docker containers, directories, cidx indexes.

**Trade-off**:
- **Simpler**: No complex cleanup state machine
- **Acceptable**: Orphans cleaned up eventually by periodic scanning
- **User acceptable**: User deemed cleanup resumption "extremely hard to control"

### Problems Addressed by Epic (14 remaining):
1. Queue State Loss on Crash → Story 1.1
2. Job Metadata Corruption → Story 1.1
3. Running Jobs Lost After Crash → Story 1.2
4. PID Unreliability Across Restarts → Story 1.2
5. ~~Interrupted Cleanup = Resource Leaks~~ → ❌ REMOVED (handled by Story 2.2)
6. Repository Lock Loss on Crash → Story 2.1
7. Orphaned Resources Accumulate → Story 2.2
8. Aborted Startup State Persists → Story 1.3 (renumbered)
9. No Recovery Visibility → Story 2.3
10. Race Conditions in Recovery → Story 2.3
11. Lost Webhook Notifications → Story 2.4
12. Statistics Data Loss → Story 1.4 (renumbered)
13. Git Transient Failure = Manual Re-registration → Story 2.5 (renumbered)
14. Degraded Mode Not Supported → Story 2.3 (redefined as corrupted resource marking)
15. No Manual Recovery Intervention → Addressed by removing ALL manual APIs

**Total Problems Addressed**: 14 problems across 9 stories

---

## Structured Logging Standard

All stories now use structured logging with this pattern:

```json
{
  "component": "QueueRecovery" | "JobReattachment" | "LockRecovery" | "OrphanDetection" | "CallbackDelivery" | "GitRetry",
  "operation": "recovery_completed" | "reattachment_completed" | "cleanup_completed" | etc,
  "timestamp": "2025-10-15T10:00:30.123Z",
  "duration_ms": 1234,
  "success_count": 50,
  "failure_count": 2,
  "errors": [
    {
      "resource": "lock:repo-B",
      "reason": "corrupted_file",
      "action": "marked_unavailable"
    }
  ],
  "degraded_mode": false,
  "corrupted_resources": []
}
```

**Startup Log API Returns**:
```json
{
  "startup_timestamp": "2025-10-15T10:00:00.000Z",
  "operations": [
    { /* QueueRecovery operation */ },
    { /* JobReattachment operation */ },
    { /* LockRecovery operation */ },
    { /* OrphanDetection operation */ },
    { /* CallbackDelivery operation */ }
  ],
  "total_duration_ms": 5678,
  "degraded_mode": true,
  "corrupted_resources": ["lock:repo-B"],
  "summary": "System operational with 1 corrupted resource"
}
```

---

## Implementation Checklist

- [x] Remove Story 1.3 file
- [x] Renumber stories (1.4→1.3, 1.5→1.4, 2.6→2.5)
- [x] Update Story 1.1 to remove manual APIs
- [x] Update Story 1.2 to remove manual APIs + add NO stdout/stderr spec
- [ ] Update Story 1.3 to remove manual APIs
- [ ] Update Story 1.4 (no changes needed - no APIs)
- [ ] Update Story 2.1 to remove manual APIs
- [ ] Update Story 2.2 to remove manual APIs
- [ ] Update Story 2.3 to redefine degraded mode + add single startup log API
- [ ] Update Story 2.4 to remove manual APIs
- [ ] Update Story 2.5 (no changes needed - no APIs initially)
- [ ] Update Epic file with new story count (9 stories)
- [ ] Update problem coverage table (14 problems addressed)

---

## Success Metrics

- **Zero data loss**: All state preserved across any restart (clean, crash, restart)
- **Automatic recovery**: Complete state restoration without manual intervention
- **60-second recovery**: Full recovery within 60 seconds on every startup
- **Complete visibility**: Single startup log API provides full observability
- **No manual intervention needed**: 100% automated recovery
- **Resource protection**: Orphan detection handles leaked resources
- **Graceful degradation**: System operational with corrupted resource marking
- **97% API reduction**: 36 APIs → 1 API (startup log only)

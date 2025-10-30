# Epic: Crash Resilience System

## Executive Summary

Implement a comprehensive crash resilience system that ensures Claude Server can recover from any failure scenario without data loss or manual intervention. This system provides atomic file operations infrastructure, queue and statistics persistence, job reattachment, automated startup recovery orchestration, lock persistence implementation, orphan detection, repository waiting queue recovery, and callback delivery resilience with complete visibility through a single startup log API.

**Evolution**: Initially 9 stories, consolidated to 6 following elite architect review, now expanded to 8 stories (7 required + 1 optional) based on comprehensive code review that identified 20 gaps with 4 CRITICAL gaps requiring immediate remediation.

## Current State vs Implementation Requirements

**CRITICAL CONTEXT**: This epic specifies NET NEW crash resilience functionality. The current codebase has MINIMAL crash recovery capabilities.

### What Currently Exists (Baseline)
- ✅ In-memory job queue (`ConcurrentQueue<Guid>`) - NO PERSISTENCE
- ✅ In-memory repository locks (`ConcurrentDictionary`) - NO PERSISTENCE
- ✅ Job metadata files (`.job.json`) - Direct writes, NO ATOMIC OPERATIONS
- ✅ Basic `RecoverCrashedJobsAsync` method - Limited functionality, no heartbeat
- ✅ Statistics service with 2-second throttled saves - NOT IMMEDIATE
- ✅ Fire-and-forget callbacks - NO RETRY, NO QUEUE
- ✅ Simple linear initialization - NO ORCHESTRATION, NO DEPENDENCY MANAGEMENT

### What Must Be Implemented (This Epic)
- ❌ Queue persistence (WAL-based) - **BUILD FROM SCRATCH**
- ❌ Lock persistence (file-based) - **BUILD FROM SCRATCH** (lock files don't exist!)
- ❌ Atomic file operations (temp+rename) - **RETROFIT ALL WRITES**
- ❌ Heartbeat/sentinel file system - **BUILD FROM SCRATCH** (or enhance existing recovery)
- ❌ Callback queue with retry - **BUILD FROM SCRATCH**
- ❌ Startup orchestration - **BUILD FROM SCRATCH**
- ❌ Orphan detection - **BUILD FROM SCRATCH**
- ❌ Waiting queue recovery - **BUILD FROM SCRATCH**
- ❌ Degraded mode handling - **BUILD FROM SCRATCH**

**IMPLEMENTATION SCOPE**: Approximately 80% net-new code, 20% retrofitting existing code with atomic operations.

**ABSOLUTE PATHS USED**: All file references use absolute path `/var/lib/claude-batch-server/claude-code-server-workspace/` (never relative `{workspace}`).

## Business Value

- **Zero Data Loss**: All queue state, statistics, and job progress preserved across crashes
- **Automatic Recovery**: System self-heals from crashes without ANY manual intervention
- **Service Continuity**: Jobs continue from last checkpoint after recovery
- **Operational Visibility**: Complete insight into recovery operations via single API
- **Reduced Downtime**: Fast recovery (<60 seconds) with minimal service interruption
- **Resource Health**: Automated orphan detection prevents resource exhaustion
- **Integration Reliability**: Webhook delivery guaranteed despite crashes
- **File Corruption Prevention**: Atomic write operations prevent catastrophic data loss
- **Queue Order Preservation**: FIFO guarantees maintained across restarts

## Architecture Overview

### Core Components

```
┌─────────────────────────────────────────────────────────┐
│                 Persistence Layer                         │
│  ┌──────────────┐  ┌────────────┐  ┌────────────────┐   │
│  │Queue & Stats │  │    Lock     │  │   Callback     │   │
│  │  (WAL-based) │  │ Persistence │  │     Queue      │   │
│  └──────────────┘  └────────────┘  └────────────────┘   │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│          Recovery Orchestration (Every Startup)          │
│  ┌──────────────┐  ┌────────────┐  ┌────────────────┐   │
│  │   Aborted    │  │     Job     │  │    Orphan      │   │
│  │   Startup    │  │ Reattachment│  │   Detection    │   │
│  │   Detection  │  │  (Heartbeat)│  │   (Cleanup)    │   │
│  └──────────────┘  └────────────┘  └────────────────┘   │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│              Observability Layer (Simplified)            │
│                                                           │
│         GET /api/admin/startup-log (ONLY API)            │
│         - Current startup operations                      │
│         - Historical startup logs (last 10)               │
│         - Degraded mode status                            │
│         - Corrupted resources list                        │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

### Startup State Restoration Flow (Runs EVERY Startup)

**CRITICAL**: Recovery happens on EVERY startup (not just crashes). This ensures consistent system initialization regardless of shutdown type.

1. **Aborted Startup Detection**: Check for incomplete prior startup, cleanup partial state, retry failed components
2. **Queue & Statistics Recovery**: Restore queue state via WAL, load statistics from disk
3. **Parallel Recovery**: Lock persistence + Job reattachment (via heartbeat monitoring)
4. **Orphan Detection**: Scan for abandoned resources, automatic cleanup with safety checks
5. **Callback Delivery**: Resume pending webhook deliveries with exponential backoff
6. **Service Operational**: System fully restored, startup log updated

## Consolidation & Gap Analysis History

### Evolution Journey: 9 → 6 → 8 Stories

**Initial Design**: 9 stories (over-engineered with artificial separation)

**First Consolidation** (Elite Architect Review): 6 stories
- ✅ Stories 1.1 + 1.4 → Story 1 (Queue and Statistics unified)
- ✅ Stories 2.3 + 1.3 → Story 3 (Orchestration with Aborted Startup)
- ✅ Story 2.5 → Moved to Operational Resilience epic
- ❌ Story 1.3 → Removed (Cleanup Resumption - too complex)

**Comprehensive Gap Analysis**: 20 gaps identified by Codex architect
- **CRITICAL Gaps**: 4 (file corruption, lock implementation missing)
- **HIGH Priority**: 4 (queue order, waiting queues, callbacks, sessions)
- **MEDIUM Priority**: 5 (batch state, cleanup, containers, staging, metrics)
- **Out of Scope**: 4 (search, config reload, git operations, concurrency)

**Final Structure**: 8 stories (7 required + 1 optional)
- **Story 0 (NEW)**: Atomic File Operations Infrastructure - FOUNDATIONAL
- **Stories 1-6**: Original epic stories with gap enhancements
- **Story 7 (NEW)**: Repository Waiting Queue Recovery
- **Story 8 (NEW)**: Batch State Recovery - OPTIONAL

**API Simplification**: 36 APIs → 1 API (97% reduction)

## Features

### Feature 01: Core Resilience (3 stories)
Fundamental persistence and recovery mechanisms including atomic operations, queue state, statistics, and job reattachment.

**Stories**:
0. **[NEW] Atomic File Operations Infrastructure** - FOUNDATIONAL: Implement write-temp-rename pattern for ALL file operations, preventing corruption on crash. Retrofit existing JobPersistenceService, RepositoryRegistrationService, and ContextLifecycleManager. This MUST be completed first as all other stories depend on it. (Addresses CRITICAL Gaps #10, #11, #16)

1. **Queue and Statistics Persistence with Automated Recovery** - Unified durable state management with WAL for queue, real-time persistence for statistics, queue order preservation via sequence numbers, fully automated recovery. Enhanced to include queue order preservation (Gap #1) and documentation of statistics throttling behavior (Gap #5).

2. **Job Reattachment with Automated Monitoring** - Heartbeat-based job recovery (zero PID dependency), sentinel file monitoring, automatic stale job detection. Enhanced to deprecate PID field with warning comments (Gap #18).

### Feature 02: Recovery Orchestration (5 stories + 1 optional)
Advanced recovery orchestration with lock implementation, aborted startup detection, orphan detection, waiting queue recovery, callback resilience, and comprehensive observability.

**Stories**:
3. **Startup Recovery Orchestration with Monitoring** - Master orchestrator with topological sort dependency enforcement, aborted startup detection, automatic retry with exponential backoff, degraded mode (corrupted resource marking), single startup log API. Enhanced with corruption detection metrics and alerts (Gap #19).

4. **Lock Persistence Implementation** - **CLARIFICATION: This is NEW IMPLEMENTATION, not just recovery**. Lock files do not currently exist in the codebase (Gap #17). Must implement complete lock file system: create `/workspace/locks/{repositoryName}.lock.json` files, write lock metadata (holder, operation, timestamp, PID, operationId), persist on acquire, delete on release, recover on startup with stale detection. (Addresses CRITICAL Gap #2 and Gap #17)

5. **Orphan Detection with Automated Cleanup** - Comprehensive orphan scanning (job directories, Docker containers, cidx indexes), safety validation, automatic cleanup. Enhanced with transactional cleanup using marker files (Gap #12), precise CIDX container tracking (Gap #13), and staged file recovery policy (Gap #15).

6. **Callback Delivery Resilience** - File-based webhook queue (`callbacks.queue.json`), automatic retry with exponential backoff (30s, 2min, 10min), crash-resilient delivery. Enhanced with callback execution tracking and status persistence (Gap #9).

7. **[NEW] Repository Waiting Queue Recovery** - Jobs waiting for locked repositories are currently lost on crash (Gap #3). Must persist waiting queue state in job metadata with RepositoryWaitInfo, rebuild queues on startup from jobs in waiting states, integrate with lock recovery for automatic re-notification.

8. **[NEW - OPTIONAL] Batch State Recovery** - Restore job batching relationships after crash for efficiency optimization (Gap #4). Add BatchId to Job model, persist batch state files, rebuild batches on startup. This is an optimization for repository preparation efficiency, not required for correctness.

## Implementation Order

**CRITICAL**: Story 0 MUST be implemented first - it prevents catastrophic data loss happening TODAY.

**Recommended Sequence** (updated based on gap analysis dependencies):

1. **Story 0**: Atomic File Operations Infrastructure (BLOCKS EVERYTHING - prevents corruption) - **3-4 days** (REALISTIC)
2. **Story 1**: Queue and Statistics Persistence (foundation for all recovery) - **3-4 days** (REALISTIC for low-traffic server)
3. **Story 2**: Job Reattachment (process recovery via heartbeat) - **3-4 days** (REALISTIC - Option A)
4. **Story 3**: Startup Recovery Orchestration (orchestrates stories 1 & 2, adds aborted startup detection) - **3 days**
5. **Story 4**: Lock Persistence Implementation (NEW implementation from scratch) - **5-6 days** (REALISTIC - building entire system)
6. **Story 5**: Orphan Detection (cleanup leaked resources) - **2 days**
7. **Story 6**: Callback Resilience (notification reliability) - **2-3 days** (REALISTIC)
8. **Story 7**: Repository Waiting Queue Recovery (prevents jobs stuck forever) - **2 days**
9. **Story 8**: [OPTIONAL] Batch State Recovery (efficiency optimization only) - **1-2 days**

**Total Effort (REALISTIC for low-traffic server)**: 25-30 days for required stories (Stories 0-7), plus 1-2 days if Story 8 is included

**Original Estimate**: 18-21 days (OPTIMISTIC - underestimated complexity)
**Revised Estimate**: 25-30 days (REALISTIC - accounts for low-traffic patterns, simpler WAL checkpoints)

**Breakdown by Complexity**:
- **High Complexity** (5-6 days each): Story 4 (complete lock system build from scratch)
- **Medium Complexity** (3-4 days each): Stories 0, 1, 2, 3, 6 (New infrastructure, simplified for low traffic)
- **Low Complexity** (2 days each): Stories 5, 7 (Focused, well-defined scope)

## Problems Addressed (18 Total)

All crash resilience problems addressed with 8-story structure (expanded from original 14 based on gap analysis):

1. **Queue State Loss** → Story 1 (WAL-based persistence)
2. **Job Metadata Corruption** → Story 0 (atomic file operations - NEW STORY)
3. **Running Jobs Lost** → Story 2 (heartbeat reattachment)
4. **PID Unreliability** → Story 2 (zero PID dependency, field deprecated)
5. **Orphaned Resources** → Story 5 (automatic detection & cleanup with tracking)
6. **Lock Loss** → Story 4 (NEW lock persistence implementation - not just recovery)
7. **Aborted Startup** → Story 3 (aborted startup detection absorbed)
8. **No Recovery Visibility** → Story 3 (single startup log API with corruption metrics)
9. **Wrong Recovery Order** → Story 3 (dependency-based execution order prevents data loss)
10. **Lost Webhooks** → Story 6 (durable callback queue with execution tracking)
11. **Statistics Loss** → Story 1 (real-time persistence with documented throttling)
12. **Git Failures** → Moved to Operational Resilience epic
13. **Degraded Mode** → Story 3 (redefined: corrupted resource marking, NOT feature disabling)
14. **No Manual Intervention** → ALL stories (fully automated, 36 APIs → 1 API)
15. **[NEW] File Corruption on Crash** → Story 0 (atomic write operations for ALL files - Gaps #10, #11, #16)
16. **[NEW] Repository Waiting Queues Lost** → Story 7 (persist and recover waiting jobs - Gap #3)
17. **[NEW] Queue Order Not Preserved** → Story 1 (sequence numbers for FIFO guarantee - Gap #1)
18. **[NEW] Callback Execution Not Tracked** → Story 6 (track delivery status - Gap #9)

## Success Criteria

- ✅ Zero data loss during crashes (queue, statistics, locks, callbacks, session files)
- ✅ Automatic recovery without ANY manual intervention (no manual APIs)
- ✅ Jobs continue from last checkpoint via heartbeat reattachment
- ✅ Complete visibility via single startup log API with corruption metrics
- ✅ Recovery completes within 60 seconds
- ✅ Degraded mode marks corrupted resources (does NOT disable features)
- ✅ Orphaned resources automatically cleaned with precise tracking
- ✅ Webhook delivery guaranteed with retry and execution tracking
- ✅ Aborted startups detected and recovered
- ✅ All file writes are atomic (no partial corruption possible)
- ✅ Queue order preserved across restarts (FIFO guarantee)
- ✅ Jobs waiting for repositories recovered and re-queued
- ✅ Lock files implemented and persisted (not just in-memory)

## Technical Principles

### Automated Recovery Philosophy
- **Zero Manual Intervention**: No inspection APIs, no manual controls, no dashboards
- **Single API**: `GET /api/admin/startup-log` provides complete visibility
- **Structured Logging**: All operations logged with complete context
- **Fail Safely**: Critical failures abort startup (queue), non-critical continue with degraded mode

### Degraded Mode (Redefined)
**CRITICAL**: Degraded mode does NOT mean features are disabled.

- **OLD (WRONG)**: Lock recovery fails → Lock enforcement disabled system-wide
- **NEW (CORRECT)**: Lock recovery fails for repo-B → ONLY repo-B marked "unavailable", ALL other locks work, lock enforcement remains enabled

**Example**: Lock file corrupted for repo-B → repo-B becomes unavailable, repos A/C/D fully functional, ALL features remain enabled

### Atomic Operations
- **Pattern**: Write to temp file → flush → atomic rename
- **Applied to**: Queue snapshots, statistics, locks, callbacks
- **Guarantee**: Files contain either complete old state or complete new state (never partial)

### Dependency Enforcement
- **Mechanism**: Topological sort determines execution order from declared dependencies
- **Purpose**: Prevents data loss from wrong execution order (e.g., orphan detection deleting workspaces before job reattachment completes)
- **Parallel Execution**: Independent phases (Locks + Jobs) run concurrently when no dependencies exist
- **Circular Detection**: Fail fast at startup if circular dependencies detected
- **Example**: Job Reattachment must complete before Orphan Detection runs, otherwise orphan scan might delete workspaces of jobs being reattached

## Token Efficiency Metrics

**Original Design**: 28 micro-task stories across 9 features
- Estimated agent calls: ~70-85 (multiple passes per story)
- Token overhead: ~600K tokens in agent coordination

**First Consolidation**: 9 stories across 2 features (from 28 → 9)
- Estimated agent calls: ~18-20
- Token overhead: ~180K tokens
- **Efficiency Gain**: 68% story reduction, ~70% token savings

**Final Consolidation**: 6 stories across 2 features (from 9 → 6)
- Estimated agent calls: ~12-15
- Token overhead: ~120K tokens
- **Efficiency Gain**: 79% story reduction vs original, ~80% token savings

## Reference Documentation

- `ARCHITECT_STORY_CONSOLIDATION_RECOMMENDATION.md` - Elite architect's 6-story analysis
- `EPIC_SIMPLIFICATION_COMPLETE.md` - Complete API simplification (36 → 1)
- `EPIC_API_SIMPLIFICATION_SUMMARY.md` - API reduction details
- `SESSION_CONSOLIDATION_SUMMARY.md` - Consolidation work summary
- `STORY_1.2_HEARTBEAT_SPECIFICATION.md` - Heartbeat monitoring specification

## Out of Scope (Moved to Other Epics)

- **Git Operation Retry**: Relocated to `/plans/backlog/OperationalResilience/Story_GitOperationRetry.md`
  - Reason: Not crash recovery, belongs in operational resilience
  - Exponential backoff: 5s, 15s, 45s (3 retries)

## Testing Requirements

All stories require:
- ✅ **TDD Implementation**: Test-first development
- ✅ **Manual E2E Testing**: Claude Code executes manual test plans
- ✅ **Crash Simulation**: Verify recovery from unexpected termination
- ✅ **Corruption Handling**: Test recovery from corrupted state files
- ✅ **Degraded Mode**: Verify partial recovery continues system operation
- ✅ **Zero Warnings Policy**: Clean build before completion

## Final Structure

**8 Stories Total** (7 required + 1 optional):
- **Feature 01 (Core Resilience)**: 3 stories
  - Story 0: Atomic File Operations (NEW - FOUNDATIONAL)
  - Story 1: Queue+Statistics Persistence
  - Story 2: Job Reattachment
- **Feature 02 (Recovery Orchestration)**: 5 stories
  - Story 3: Startup Recovery Orchestration
  - Story 4: Lock Persistence Implementation (NEW WORK - not just recovery)
  - Story 5: Orphan Detection
  - Story 6: Callback Resilience
  - Story 7: Repository Waiting Queue Recovery (NEW)
  - Story 8: Batch State Recovery (NEW - OPTIONAL)

**Clean Architectural Boundaries**:
- Foundation first (Story 0 prevents corruption)
- No artificial separation (Queue and Statistics unified)
- No over-engineering (Cleanup Resumption removed)
- No unrelated concerns (Git Retry moved out)
- Each story addresses specific gap findings

## Gap Analysis References

**Comprehensive Analysis Documents**:
- `COMPREHENSIVE_GAP_ANALYSIS.md` - 20 gaps identified by Codex architect review
- `GAP_REMEDIATION_PROPOSALS.md` - Detailed solutions for all gaps

**Gap Priority Summary**:
- **CRITICAL**: 4 gaps requiring immediate fix (Gaps #2, #10, #11, #17)
- **HIGH**: 4 gaps integrated into stories (Gaps #1, #3, #9, #16)
- **MEDIUM**: 5 gaps addressed incrementally (Gaps #4, #12, #13, #15, #19)
- **OUT OF SCOPE**: 4 gaps excluded from epic (Gaps #7, #8, #14, #20)

## Key Changes from Gap Analysis

**New Stories Added**:
- **Story 0**: Atomic File Operations Infrastructure - CRITICAL foundation preventing file corruption
- **Story 7**: Repository Waiting Queue Recovery - Jobs waiting for locks were lost
- **Story 8**: Batch State Recovery (optional) - Efficiency optimization

**Story Clarifications**:
- **Story 4**: Now explicitly "Lock Persistence IMPLEMENTATION" not just recovery - lock files don't exist yet!

**Story Enhancements**:
- **Story 1**: Added queue order preservation (sequence numbers), documented throttling
- **Story 2**: Added PID field deprecation warning
- **Story 3**: Added corruption detection metrics and alerts
- **Story 5**: Added transactional cleanup, CIDX tracking, staging recovery
- **Story 6**: Added callback execution status tracking

---

**Epic Status**: Ready for Implementation (with Story 0 as MANDATORY first step)
**Story Count**: 8 stories (expanded from 6 after gap analysis)
**Required Stories**: 7 (Story 8 is optional efficiency optimization)
**API Surface**: 1 API (reduced from 36)
**Automation Level**: 100% (zero manual intervention)
**Effort Estimate**: 5-6 weeks total (REALISTIC for low-traffic server)
- Story 0: 3-4 days (critical foundation - must be perfect)
- Stories 1-3: 9-12 days (medium complexity - WAL simplified for low traffic)
- Story 4: 5-6 days (high complexity - complete lock system build)
- Stories 5-7: 6-7 days (medium complexity - cleanup, callbacks, waiting queues)
- Story 8: 1-2 days (optional - defer until Stories 0-7 complete)

**Original Estimate**: 4-5 weeks (OPTIMISTIC)
**Revised Estimate**: 5-6 weeks (REALISTIC for low-traffic patterns)

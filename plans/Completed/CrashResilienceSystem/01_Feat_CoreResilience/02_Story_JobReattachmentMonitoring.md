# Story 2: Job Reattachment with Heartbeat Monitoring

## User Story
**As a** system administrator
**I want** running jobs to reattach after crashes using heartbeat monitoring with automated staleness detection
**So that** active work continues without loss and I can track job health in real-time

## Business Value
Prevents loss of in-progress work by automatically reattaching to running job processes after crashes, ensuring business operations continue with minimal disruption while providing complete visibility into reattachment operations and job health.

## Current State Analysis

**CURRENT BEHAVIOR**:
- **Recovery Method**: `RecoverCrashedJobsAsync()` exists
  - Location: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobService.cs` line 148
  - Current implementation details are minimal
- **NO SENTINEL FILES**: No `.sentinel.json` files tracking running jobs
- **NO HEARTBEAT MECHANISM**: No periodic heartbeat updates
- **CRASH IMPACT**: Cannot distinguish between crashed jobs vs legitimately running jobs after restart

**EXISTING RECOVERY MECHANISM**:
```csharp
// JobService.cs line 148
public async Task RecoverCrashedJobsAsync()
{
    // Existing logic (undefined behavior)
    // NO heartbeat detection
    // NO sentinel file monitoring
}
```

**IMPLEMENTATION REQUIRED**:

**CONFIRMED APPROACH**: Build heartbeat-based monitoring system for running adaptors

- **BUILD** `SentinelFileMonitor` - NEW CLASS
- **BUILD** `.sentinel.json` file creation/update system for EACH running adaptor
- **BUILD** 30-second heartbeat update mechanism (background thread per adaptor)
- **BUILD** Stale detection logic:
  - **Fresh**: <2 minutes old (job actively running)
  - **Stale**: 2-10 minutes old (warning, investigate)
  - **Dead**: >10 minutes old (crashed, needs cleanup)
- **REPLACE** existing `RecoverCrashedJobsAsync()` logic with heartbeat-based recovery
- **SCOPE**: Applies to ALL adaptors (claude-code, gemini, opencode, aider, codex, q)

**INTEGRATION POINTS**:
1. `ClaudeCodeExecutor.ExecuteAsync()` - Create sentinel file on job start
2. Background heartbeat updater - Update sentinel every 30 seconds
3. `JobService.InitializeAsync()` - Scan sentinel files on startup, detect stale
4. Recovery logic - Reattach fresh jobs, clean up dead jobs

**FILES TO MODIFY**:
- `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobService.cs` (recovery logic)
- `/claude-batch-server/src/ClaudeBatchServer.Core/Executors/ClaudeCodeExecutor.cs` (sentinel creation for claude-code adaptor)
- `/claude-batch-server/src/ClaudeBatchServer.Core/Executors/GeminiCodeExecutor.cs` (sentinel creation for gemini adaptor)
- `/claude-batch-server/src/ClaudeBatchServer.Core/Executors/OpenCodeExecutor.cs` (sentinel creation for opencode adaptor)
- `/claude-batch-server/src/ClaudeBatchServer.Core/Executors/AiderCodeExecutor.cs` (sentinel creation for aider adaptor)
- `/claude-batch-server/src/ClaudeBatchServer.Core/Executors/CodexExecutor.cs` (sentinel creation for codex adaptor)
- `/claude-batch-server/src/ClaudeBatchServer.Core/Executors/QExecutor.cs` (sentinel creation for q adaptor)
- Create new `/claude-batch-server/src/ClaudeBatchServer.Core/Services/SentinelFileMonitor.cs`
- Create new `/claude-batch-server/src/ClaudeBatchServer.Core/Services/HeartbeatUpdater.cs`

**SENTINEL FILE LOCATIONS**:
- `/var/lib/claude-batch-server/claude-code-server-workspace/jobs/{jobId}/.sentinel.json`
- One sentinel file per running adaptor (all adaptors use same format)

**EFFORT**: 3-4 days

## ⚠️ CRITICAL REQUIREMENT: Duplexed Output File Mechanism

**THE 70% OF THE BATTLE** - This is the foundation that makes reattachment actually work.

### The Core Mechanism (Simple & Elegant)

**Adaptor Side (ALL 6 adaptors):**
- Write output to **BOTH** stdout (debugging) AND deterministic file
- File: `{workspace}/jobs/{jobId}/{sessionId}.output` (plain text)
- Filename: Derived from session ID (already passed to adaptor)
- Continuous append with flush throughout execution
- NO new flags needed - KISS

**Server Side:**
- Monitor sentinel file: job alive/dead
- Read output file when needed: partial or final results
- **NO stdout capture dependency**
- **NO process attachment magic**

**Reattachment Flow:**
```
1. Server crashes
2. Server restarts
3. Check sentinel: "Job X still running"
4. Read {sessionId}.output: Get partial results
5. Monitor sentinel for deletion
6. Sentinel deleted → job done → read final output from file
```

**Why This Matters:**
- Can't capture stdout from already-running process (parent died)
- CAN read from file anytime (file persists)
- Simple, crash-resilient, works for all adaptors

**Scope:** ALL 6 adaptors must implement (claude-as-claude, gemini-as-claude, opencode-as-claude, aider-as-claude, codex-as-claude, q-as-claude)

## Technical Approach
Implement heartbeat-based sentinel file monitoring to track ALL running adaptors (claude-code, gemini, opencode, aider, codex, q). Each running adaptor creates and continuously updates a `.sentinel.json` file with timestamps. On startup, scan all sentinel files to detect fresh jobs (actively running), stale jobs (investigate), and dead jobs (crashed, cleanup required).

**CRITICAL ADDITION:** Each adaptor writes output to BOTH stdout AND `{sessionId}.output` file. Server reads output from file (not stdout capture), enabling true reattachment after crashes without process handle requirements.

### Components
- `SentinelFileMonitor`: Heartbeat-based job tracking via sentinel files
- `HeartbeatUpdater`: Background thread updating sentinel files every 30 seconds
- `JobReattachmentService`: Reattach fresh jobs detected on startup
- `StaleJobDetector`: Classify jobs by heartbeat age (fresh/stale/dead)
- `StateReconstructor`: Rebuild job context from workspace and session files

### Heartbeat Monitoring Design

**Per-Adaptor Sentinel Files**:
- Each running adaptor maintains its own `.sentinel.json` file
- File location: `/var/lib/claude-batch-server/claude-code-server-workspace/jobs/{jobId}/.sentinel.json`
- Format: `{"jobId": "...", "lastHeartbeat": "2025-10-21T16:30:00.000Z", "adaptorEngine": "claude-code", "pid": 12345}`
- Updated every 30 seconds by background thread

**Staleness Classification**:
- **Fresh** (<2 min): Job actively running, no action needed
- **Stale** (2-10 min): Warning state, investigate but don't cleanup
- **Dead** (>10 min): Crashed, safe to cleanup

**Recovery Flow on Startup**:
1. Scan `/var/lib/claude-batch-server/claude-code-server-workspace/jobs/` for all `.sentinel.json` files
2. For each sentinel: Calculate heartbeat age, classify as fresh/stale/dead
3. **Fresh jobs**: Reattach (update in-memory state, mark as running)
4. **Stale jobs**: Log warning, leave running (may still be alive)
5. **Dead jobs**: Cleanup workspace, mark job as failed, free resources

## Acceptance Criteria

```gherkin
# ========================================
# CATEGORY: Duplexed Output File (CRITICAL - THE 70%)
# ========================================

Scenario: Adaptor creates output file on session start
  Given adaptor begins execution with session ID
  When adaptor initializes
  Then {sessionId}.output file created in workspace
  And file opened in append mode
  And file handle kept open for continuous writing

Scenario: Dual write to stdout and output file
  Given adaptor produces output
  When any content is generated
  Then content written to stdout (unchanged - for debugging)
  And SAME content appended to {sessionId}.output file
  And file flushed after each write (crash-safe)

Scenario: Output file uses deterministic naming
  Given session ID "abc-123-def-456"
  When output file created
  Then filename is "abc-123-def-456.output"
  And located in job workspace directory
  And no randomization or timestamps in filename

Scenario: Server reads output file for partial results
  Given job running with partial output in file
  When server needs current output
  Then reads {sessionId}.output file
  And gets all output generated so far
  And NO stdout capture needed

Scenario: Reattachment reads output file
  Given server crashes and restarts
  And sentinel shows job still running
  When reattachment occurs
  Then server reads {sessionId}.output for partial results
  And resumes monitoring sentinel for completion
  And NO process handle or stdout reconnection needed

Scenario: Final results from output file
  Given job completes and sentinel deleted
  When server detects completion
  Then reads final output from {sessionId}.output
  And uses file content for markdown generation
  And stdout capture NOT involved

Scenario: All adaptors implement duplexed output
  Given ANY of the 6 adaptors (claude/gemini/opencode/aider/codex/q)
  When adaptor executes
  Then ALL write to {sessionId}.output file
  And ALL use identical plain text format
  And ALL flush on write for crash safety

# ========================================
# CATEGORY: Heartbeat Timing and Intervals
# ========================================

Scenario: Heartbeat creation with 30-second interval
  Given a job starts execution
  When sentinel file is created
  Then heartbeat timestamp initialized to current UTC time
  And update interval set to 30 seconds
  And sentinel file written to /var/lib/claude-batch-server/claude-code-server-workspace/jobs/{jobId}/.sentinel.json

Scenario: Heartbeat update every 30 seconds
  Given job is actively running
  When 30 seconds elapse since last heartbeat
  Then sentinel file timestamp updated to current UTC time
  And file written atomically (temp + rename)
  And update completes within 100ms

Scenario: Fresh heartbeat detection (<2 minutes old)
  Given sentinel file timestamp is 1 minute old
  When heartbeat staleness check runs
  Then job classified as "fresh"
  And job considered actively running
  And no intervention needed

Scenario: Stale heartbeat detection (2-10 minutes old)
  Given sentinel file timestamp is 5 minutes old
  When heartbeat staleness check runs
  Then job classified as "stale"
  And job marked for investigation
  And warning logged

Scenario: Dead heartbeat detection (>10 minutes old)
  Given sentinel file timestamp is 15 minutes old
  When heartbeat staleness check runs
  Then job classified as "dead"
  And job marked as crashed
  And cleanup initiated
  And error logged with full context

Scenario: Heartbeat timing boundary - exactly 2 minutes
  Given sentinel file timestamp is exactly 120 seconds old
  When staleness check runs
  Then job classified as "stale" (inclusive boundary)
  And investigation triggered

Scenario: Heartbeat timing boundary - exactly 10 minutes
  Given sentinel file timestamp is exactly 600 seconds old
  When staleness check runs
  Then job classified as "dead" (inclusive boundary)
  And cleanup initiated

# ========================================
# CATEGORY: Sentinel File Operations
# ========================================

Scenario: Sentinel file creation on job start
  Given job execution begins
  When JobReattachmentService initializes
  Then sentinel file created at {workspace}/jobs/{jobId}/.sentinel.json
  And file contains: jobId, pid, startTime, lastHeartbeat
  And atomic write operation used

Scenario: Sentinel file update with process information
  Given job is running with PID 12345
  When sentinel file is updated
  Then file contains current PID: 12345
  And file contains hostname
  And file contains Claude Code CLI version
  And lastHeartbeat timestamp updated

Scenario: Sentinel file corruption detection
  Given sentinel file exists with invalid JSON
  When reattachment service reads file
  Then corruption detected
  And job marked as "unknown state"
  And error logged with file path
  And manual intervention flagged

Scenario: Missing sentinel file during recovery
  Given job workspace exists
  And sentinel file is missing
  When recovery scans for jobs
  Then job marked as "orphaned"
  And workspace flagged for cleanup
  And orphan detection handles cleanup

Scenario: Sentinel file atomic write with temp file
  Given heartbeat update is triggered
  When sentinel file is written
  Then data written to .sentinel.json.tmp first
  And FileStream.FlushAsync() called
  And file renamed to .sentinel.json atomically
  And old file replaced

Scenario: Sentinel file permissions
  Given sentinel file is created
  When file permissions are set
  Then file readable by server process
  And file writable by server process
  And file not world-readable (security)

# ========================================
# CATEGORY: Concurrent Heartbeat Updates
# ========================================

Scenario: Multiple jobs updating heartbeats simultaneously
  Given 10 jobs are running concurrently
  When all jobs update heartbeats at 30-second intervals
  Then each job writes to separate sentinel file
  And no file conflicts occur
  And all updates complete successfully

Scenario: Heartbeat update serialization per job
  Given single job updating heartbeat
  When multiple threads attempt update simultaneously
  Then updates serialized (only one write at a time)
  And file integrity maintained
  And no corruption occurs

Scenario: Heartbeat update during file system contention
  Given file system under heavy I/O load
  When heartbeat update attempts write
  Then operation retries on transient failures
  And eventually succeeds or fails cleanly
  And timeout prevents indefinite hang (5 second timeout)

# ========================================
# CATEGORY: Process Reattachment Logic
# ========================================

Scenario: Successful process reattachment
  Given server restarts with 3 running jobs
  When reattachment service discovers sentinel files
  Then processes found via PID lookup
  And process ownership verified (correct user)
  And jobs marked as "reattached"
  And execution monitoring resumed

Scenario: Process ownership verification
  Given sentinel file contains PID 12345
  When process lookup executes
  Then process user compared to expected job user
  And process command line verified (contains "claude")
  And ownership match required for reattachment

Scenario: Process not found (terminated)
  Given sentinel file contains PID 12345
  And process no longer exists
  When reattachment attempts process lookup
  Then process not found
  And job marked as "crashed"
  And cleanup scheduled

Scenario: Process exists but different user
  Given sentinel file contains PID 12345
  And process exists but owned by different user
  When ownership verification runs
  Then ownership mismatch detected
  And job marked as "security violation"
  And error logged with details
  And manual review required

Scenario: Zombie process detection
  Given process exists as zombie (defunct)
  When reattachment checks process state
  Then zombie state detected
  And job marked as "terminated"
  And cleanup initiated

# ========================================
# CATEGORY: Edge Cases
# ========================================

Scenario: Empty workspace directory
  Given job workspace directory exists
  And workspace contains no files
  When recovery scans workspace
  Then workspace marked as orphaned
  And cleanup scheduled
  And no reattachment attempted

Scenario: Corrupted sentinel file with missing fields
  Given sentinel file missing "pid" field
  When file is parsed
  Then validation fails
  And job marked as "corrupted"
  And manual investigation required

Scenario: Sentinel file with future timestamp
  Given sentinel file lastHeartbeat is 5 minutes in future
  When staleness check runs
  Then clock skew detected
  And warning logged
  And job marked as "stale" (conservative classification)

Scenario: Sentinel file with very old timestamp (months old)
  Given sentinel file lastHeartbeat is 30 days old
  When staleness check runs
  Then job classified as "dead"
  And cleanup initiated immediately

Scenario: Multiple sentinel files in single workspace
  Given job workspace contains 2 sentinel files
  When recovery scans directory
  Then conflict detected
  And most recent file used
  And warning logged

# ========================================
# CATEGORY: State Reconstruction
# ========================================

Scenario: Full conversation history reconstruction
  Given job has been running for 2 hours
  And context repository contains session markdown
  When reattachment reconstructs state
  Then full conversation history loaded
  And all exchanges available via API
  And context preserved

Scenario: Workspace file accessibility after reattachment
  Given job created files in workspace
  When reattachment completes
  Then workspace files remain accessible
  And file permissions preserved
  And API can retrieve files

Scenario: Execution continuation from checkpoint
  Given job crashed mid-execution
  When manual resume is triggered
  Then execution resumes from last checkpoint
  And prior work not repeated
  And context injected into resume session

# ========================================
# CATEGORY: Error Handling
# ========================================

Scenario: File system permission error reading sentinel
  Given sentinel file exists
  And file has incorrect permissions (unreadable)
  When reattachment attempts to read
  Then UnauthorizedAccessException thrown
  And job marked as "permission error"
  And admin notification sent

Scenario: Disk full during heartbeat update
  Given disk space exhausted
  When heartbeat update attempts write
  Then IOException thrown
  And update fails
  And error logged
  And job continues (non-critical failure)

Scenario: Network file system timeout
  Given workspace on network filesystem (NFS)
  And network timeout occurs during read
  When sentinel file read is attempted
  Then timeout exception thrown
  And retry mechanism activates
  And operation eventually succeeds or fails cleanly

# ========================================
# CATEGORY: Monitoring API Integration
# ========================================

Scenario: Reattachment status API response
  Given reattachment is in progress
  When GET /api/admin/recovery/jobs/status is called
  Then response contains array of jobs
  And each job shows: jobId, status, pid, lastHeartbeat
  And reattachment progress indicated

Scenario: Sentinel file listing API
  Given 5 jobs with sentinel files
  When GET /api/admin/recovery/jobs/sentinels is called
  Then all 5 sentinel files listed
  And each shows: jobId, pid, workspace path, lastHeartbeat age

Scenario: Reattachment metrics API
  Given reattachment completed for 3 jobs
  When GET /api/admin/recovery/jobs/metrics is called
  Then metrics show: total jobs, success count, failure count
  And average reattachment time displayed
  And success rate calculated

Scenario: Failed reattachment listing API
  Given 2 jobs failed reattachment
  When GET /api/admin/recovery/jobs/failed is called
  Then both failed jobs listed
  And failure reasons shown
  And manual resume options presented

# ========================================
# CATEGORY: Cleanup and Notification
# ========================================

Scenario: Crashed job cleanup scheduling
  Given job process terminated (PID not found)
  When job marked as crashed
  Then cleanup scheduled automatically
  And orphan detection will handle workspace
  And admin notification sent

Scenario: Administrator notification on dead job
  Given job heartbeat is >10 minutes old
  When job marked as dead
  Then notification logged to admin log
  And startup log entry created
  And email notification sent (if configured)

Scenario: Manual resume capability
  Given job marked as crashed
  When admin triggers manual resume via API
  Then new job created with resume prompt
  And prior context injected
  And execution starts from checkpoint

# ========================================
# CATEGORY: High-Volume Scenarios
# ========================================

Scenario: Reattachment with 100 running jobs
  Given 100 jobs running when server crashes
  When reattachment service starts
  Then all 100 jobs detected within 30 seconds
  And reattachment processes jobs in parallel
  And all successful reattachments complete within 60 seconds

Scenario: Heartbeat updates under high load
  Given 50 jobs updating heartbeats simultaneously
  When all jobs hit 30-second interval
  Then all heartbeat updates complete
  And no file corruption occurs
  And all updates finish within 5 seconds

# ========================================
# CATEGORY: Observability
# ========================================

Scenario: Reattachment logging on startup
  Given reattachment completes
  When startup log is written
  Then entry contains: component="JobReattachment"
  And jobs_detected count
  And jobs_reattached count
  And jobs_failed count
  And duration_ms

Scenario: Heartbeat staleness logging
  Given stale job detected
  When classification occurs
  Then warning logged with job details
  And staleness duration logged
  And PID and workspace path included

Scenario: Process discovery logging
  Given process lookup executes
  When process found or not found
  Then result logged with PID
  And process command line logged
  And process owner logged
```

## Manual E2E Test Plan

**Prerequisites**:
- Claude Server with running jobs
- Admin authentication token
- Long-running test jobs active

**Test Steps**:

1. **Start Long-Running Jobs**:
   ```bash
   # Start multiple long jobs
   for i in {1..3}; do
     curl -X POST https://localhost/api/jobs \
       -H "Authorization: Bearer $USER_TOKEN" \
       -H "Content-Type: application/json" \
       -d "{\"prompt\": \"Long task $i - count to 10000 slowly\", \"repository\": \"test-repo\"}" &
   done
   wait

   # Get job IDs and verify running
   curl https://localhost/api/jobs?status=running \
     -H "Authorization: Bearer $USER_TOKEN" | jq '.jobs[].id'
   ```
   **Expected**: 3 jobs running
   **Verify**: Jobs actively processing

2. **Check Sentinel Files**:
   ```bash
   curl https://localhost/api/admin/recovery/jobs/sentinels \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```
   **Expected**: Sentinel files for each job
   **Verify**: PIDs and paths shown

3. **Simulate Crash**:
   ```bash
   # Crash server but keep jobs running
   curl -X POST https://localhost/api/admin/test/crash \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"type": "server-only", "keepJobs": true}'
   ```
   **Expected**: Server stops, jobs continue
   **Verify**: Job processes still active

4. **Restart and Monitor Reattachment**:
   ```bash
   # Start server
   sudo systemctl start claude-batch-server

   # Monitor reattachment
   for i in {1..10}; do
     curl https://localhost/api/admin/recovery/jobs/status \
       -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.'
     sleep 3
   done
   ```
   **Expected**: Jobs detected and reattaching
   **Verify**: Progress shown for each job

5. **Verify Job Continuity**:
   ```bash
   # Check job still progressing
   JOB_ID=$(curl -s https://localhost/api/jobs?status=running \
     -H "Authorization: Bearer $USER_TOKEN" | jq -r '.jobs[0].id')

   curl "https://localhost/api/jobs/$JOB_ID/conversation" \
     -H "Authorization: Bearer $USER_TOKEN" | jq '.exchanges | length'
   ```
   **Expected**: Conversation continues growing
   **Verify**: New exchanges added post-recovery

6. **Check Reattachment Metrics**:
   ```bash
   curl https://localhost/api/admin/recovery/jobs/metrics \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```
   **Expected**: Reattachment statistics
   **Verify**: Success rate, timing data

7. **Test Failed Reattachment**:
   ```bash
   # Kill a job process manually
   JOB_PID=$(curl -s https://localhost/api/admin/recovery/jobs/sentinels \
     -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.sentinels[0].pid')

   sudo kill -9 $JOB_PID

   # Trigger reattachment check
   curl -X POST https://localhost/api/admin/recovery/jobs/check \
     -H "Authorization: Bearer $ADMIN_TOKEN"

   # Check status
   curl https://localhost/api/admin/recovery/jobs/failed \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```
   **Expected**: Dead job detected
   **Verify**: Marked for cleanup

8. **Manual Resume Failed Job**:
   ```bash
   curl -X POST https://localhost/api/admin/recovery/jobs/resume \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"jobId": "'$JOB_ID'", "fromCheckpoint": true}'
   ```
   **Expected**: Job resumed from checkpoint
   **Verify**: Continues from last state

9. **Monitor Dashboard**:
   ```bash
   curl https://localhost/api/admin/recovery/jobs/dashboard \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```
   **Expected**: Complete reattachment view
   **Verify**: All metrics and status visible

**Success Criteria**:
- ✅ Running jobs detected after crash
- ✅ Successful reattachment achieved
- ✅ Job context fully preserved
- ✅ Failed jobs handled gracefully
- ✅ Monitoring APIs functional
- ✅ Manual resume capabilities work

## Observability Requirements

**APIs**:
- `GET /api/admin/recovery/jobs/status` - Reattachment progress
- `GET /api/admin/recovery/jobs/sentinels` - Sentinel file list
- `GET /api/admin/recovery/jobs/metrics` - Success metrics
- `GET /api/admin/recovery/jobs/failed` - Failed reattachments
- `POST /api/admin/recovery/jobs/resume` - Manual resume

**Logging**:
- Job detection on startup
- Reattachment attempts
- Process discovery results
- State reconstruction
- Failure reasons

**Metrics**:
- Jobs detected post-crash
- Reattachment success rate
- Time to reattach
- Failed reattachment count
- Manual interventions

## Dependencies

**Blocks**:
- Story 5 (Orphan Detection) - Must know which jobs are alive vs crashed before cleaning up orphans

**Blocked By**:
- Story 0 (Atomic File Operations) - Sentinel files must use atomic write operations to prevent corruption

**Shared Components**:
- Uses `AtomicFileWriter` from Story 0 for sentinel file updates
- Integrates with Story 3 (Startup Orchestration) for recovery sequence

**Integration Requirements**:
- Must complete BEFORE Story 5 (Orphan Detection) to prevent deleting workspaces of running jobs
- Heartbeat data used by Story 3 (Orchestration) to determine recovery order

## Definition of Done
- [ ] Implementation complete with TDD
- [ ] Manual E2E test executed successfully by Claude Code
- [ ] Heartbeat monitoring works for ALL adaptors (claude-code, gemini, opencode, aider, codex, q)
- [ ] Job reattachment works reliably after crash
- [ ] Context preservation verified
- [ ] Staleness detection correctly classifies fresh/stale/dead jobs
- [ ] Sentinel files use atomic writes (no corruption possible)
- [ ] Monitoring APIs provide visibility
- [ ] Failed jobs handled properly
- [ ] Code reviewed and approved
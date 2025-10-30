# Story 5: Orphan Detection with Automated Cleanup

## User Story
**As a** system administrator
**I want** orphaned resources automatically detected and cleaned with structured logging
**So that** abandoned resources don't accumulate and cleanup operations are fully automated

## Business Value
Maintains system health by automatically detecting and cleaning orphaned resources left behind by crashes or failed operations, preventing resource exhaustion and storage bloat. Fully automated cleanup with comprehensive structured logging ensures system health without manual intervention.

## Current State Analysis

**CURRENT BEHAVIOR**:
- **NO ORPHAN DETECTION**: No automated orphan detection exists
- **Manual Cleanup**: Requires manual script execution
  - Script: `/home/jsbattig/Dev/claude-server/scripts/cleanup-workspace.sh`
  - Manual intervention required after crashes
- **Resource Leakage**: Orphaned resources accumulate over time
- **CRASH IMPACT**: Disk space exhaustion, Docker resource leakage, stale lock files

**ORPHAN TYPES**:
1. **Job Directories**: `/var/lib/claude-batch-server/claude-code-server-workspace/jobs/{jobId}/` without corresponding job metadata
2. **Docker Containers**: CIDX containers for non-existent jobs (prefix: `cidx-`)
3. **Docker Networks**: CIDX networks for non-existent jobs
4. **CIDX Indexes**: Stale CIDX index directories in repositories
5. **Lock Files**: Stale lock files from crashed jobs (after Story 4 implemented)
6. **Staged Files**: Files in `.staging/` directories from interrupted operations

**IMPLEMENTATION REQUIRED**:
- **BUILD** `OrphanScanner` - NEW CLASS (scan all resource types)
- **BUILD** `SafetyValidator` - NEW CLASS (validate safe to delete)
- **BUILD** `CleanupExecutor` - NEW CLASS (perform cleanup operations)
- **BUILD** Transactional cleanup using marker files (Gap #12)
- **BUILD** Precise CIDX container tracking (Gap #13)
- **BUILD** Staging file recovery policy (Gap #15)
- **INTEGRATE** with startup orchestration (Story 3)

**INTEGRATION POINTS**:
1. Startup orchestration (Story 3) - Run orphan detection after job reattachment
2. Job metadata check - Query `JobService` to validate job exists
3. Docker API - List/remove containers and networks
4. CIDX cleanup - Call `cidx stop/uninstall --force-docker`
5. File system - Scan and remove orphaned directories

**FILES TO CREATE**:
- `/claude-batch-server/src/ClaudeBatchServer.Core/Services/OrphanScanner.cs`
- `/claude-batch-server/src/ClaudeBatchServer.Core/Services/SafetyValidator.cs`
- `/claude-batch-server/src/ClaudeBatchServer.Core/Services/CleanupExecutor.cs`

**SCANNING LOCATIONS**:
- `/var/lib/claude-batch-server/claude-code-server-workspace/jobs/` (job directories)
- `/var/lib/claude-batch-server/claude-code-server-workspace/locks/` (lock files - after Story 4)
- Docker containers: `docker ps -a --filter "name=cidx-"`
- Docker networks: `docker network ls --filter "name=cidx-"`

**EFFORT**: 2 days

## Technical Approach
Implement comprehensive orphan detection that automatically scans for abandoned job directories, unused Docker resources, stale lock files on every startup. Automatic cleanup with safety checks prevents data loss. All operations logged to startup log.

### Components
- `OrphanScanner`: Automatic resource detection engine
- `SafetyValidator`: Automatic cleanup safety checks
- `CleanupExecutor`: Automatic resource removal
- `StartupLogger`: Structured logging of orphan detection and cleanup

## Acceptance Criteria

```gherkin
# ========================================
# CATEGORY: Safety Validation - Active Job Protection
# ========================================

Scenario: Active job workspace protection
  Given job workspace exists with .sentinel.json file
  And sentinel heartbeat is fresh (<2 minutes old)
  When orphan detection scans directory
  Then job classified as "active"
  And workspace NOT marked for cleanup
  And job protected from deletion

Scenario: Inactive job workspace identification
  Given job workspace exists
  And NO .sentinel.json file present
  When orphan detection scans directory
  Then job classified as "orphaned"
  And workspace marked for cleanup
  And cleanup candidate identified

Scenario: Stale heartbeat workspace identification
  Given job workspace exists with .sentinel.json
  And sentinel heartbeat is stale (>10 minutes old)
  When orphan detection scans directory
  Then job classified as "orphaned"
  And workspace marked for cleanup

Scenario: Fresh heartbeat prevents cleanup
  Given job workspace with fresh heartbeat (1 minute old)
  When orphan detection runs
  Then workspace classified as "active"
  And NO cleanup attempted
  And job continues running safely

Scenario: Multiple workspace scan with mixed states
  Given 10 workspaces exist
  And 3 have fresh heartbeats (active)
  And 7 have no sentinels (orphaned)
  When orphan detection scans all
  Then 3 protected from cleanup
  And 7 marked for cleanup
  And no false positives

# ========================================
# CATEGORY: False Positive Prevention
# ========================================

Scenario: Double-check before cleanup
  Given workspace identified as orphaned
  When cleanup is about to execute
  Then final heartbeat check performed
  And if heartbeat fresh, cleanup aborted
  And workspace reclassified as "active"

Scenario: Process existence verification
  Given workspace marked for cleanup
  And .sentinel.json contains PID 12345
  When final validation runs
  Then process 12345 lookup executed
  And if process exists, cleanup aborted
  And workspace protected

Scenario: Time window for process reattachment
  Given orphaned workspace detected
  When cleanup scheduled
  Then 30-second delay before execution
  And reattachment service has opportunity to reconnect
  And reduces false positive risk

Scenario: Workspace creation timestamp check
  Given workspace created 5 minutes ago
  And no sentinel file yet (job still initializing)
  When orphan detection runs
  Then workspace too new to be orphan
  And cleanup NOT attempted
  And grace period respected (10 minutes)

# ========================================
# CATEGORY: Docker Container Detection and Cleanup
# ========================================

Scenario: CIDX container detection for orphaned job
  Given orphaned job workspace contains cidx index
  When Docker container scan runs
  Then cidx containers for job identified
  And containers tagged with job ID
  And cleanup candidates added to list

Scenario: CIDX container cleanup execution
  Given orphaned job has 2 cidx containers
  When cleanup executes
  Then docker stop command executed for both
  And docker rm command executed for both
  And containers removed successfully

Scenario: Docker network cleanup
  Given orphaned job created Docker networks
  When container cleanup completes
  Then associated networks identified
  And docker network rm executed
  And networks removed

Scenario: Docker volume cleanup
  Given orphaned job created volumes
  When cleanup executes
  Then volumes identified
  And docker volume rm executed
  And volumes removed

Scenario: Docker cleanup failure handling
  Given cidx container stuck in removing state
  When docker rm fails
  Then error logged with container ID
  And cleanup continues with remaining resources
  And failed container logged for manual review

Scenario: Active job container protection
  Given job is active (fresh heartbeat)
  And job has cidx containers
  When Docker scan runs
  Then containers NOT marked for cleanup
  And containers remain running

# ========================================
# CATEGORY: CIDX Index Cleanup
# ========================================

Scenario: CIDX index file identification
  Given orphaned workspace contains .cidx directory
  When CIDX scan runs
  Then index files identified
  And index metadata read
  And cleanup candidate added

Scenario: CIDX index cleanup execution
  Given orphaned workspace has CIDX index
  When cleanup executes
  Then cidx uninstall --force-docker command executed
  And index fully removed
  And disk space reclaimed

Scenario: CIDX cleanup with active containers
  Given orphaned CIDX index
  And containers still running
  When cidx uninstall executes
  Then containers stopped first
  And index removed
  And cleanup completes

Scenario: CIDX cleanup failure recovery
  Given cidx uninstall fails with error
  When cleanup error occurs
  Then error logged with full context
  And fallback: manual file deletion attempted
  And .cidx directory removed recursively

# ========================================
# CATEGORY: Staged File Recovery Policy
# ========================================

Scenario: Staged changes preservation
  Given orphaned workspace has uncommitted changes
  And git status shows staged files
  When cleanup executes
  Then staged changes archived to backup location
  And backup tagged with job ID and timestamp
  And files preserved for recovery

Scenario: Unstaged changes handling
  Given orphaned workspace has unstaged changes
  When cleanup executes
  Then unstaged changes archived
  And git diff output saved
  And changes recoverable

Scenario: Clean workspace cleanup
  Given orphaned workspace with no uncommitted changes
  When cleanup executes
  Then full directory removal
  And no archival needed

Scenario: Partial clone state handling
  Given workspace has incomplete git clone
  When cleanup executes
  Then partial clone detected
  And no staged file recovery attempted
  And full removal executed

# ========================================
# CATEGORY: Transactional Cleanup with Marker Files
# ========================================

Scenario: Cleanup marker creation before deletion
  Given orphaned workspace identified
  When cleanup begins
  Then marker file created: {workspace}/.cleanup_in_progress
  And marker contains: timestamp, cleanup_id, resource_list
  And atomic write operation used

Scenario: Cleanup completion and marker removal
  Given cleanup executes successfully
  When all resources removed
  Then .cleanup_in_progress marker deleted
  And cleanup transaction complete

Scenario: Interrupted cleanup detection
  Given .cleanup_in_progress marker exists from prior crash
  When orphan detection runs on next startup
  Then interrupted cleanup detected
  And cleanup resumed from marker state
  And remaining resources cleaned

Scenario: Cleanup marker with resource tracking
  Given marker tracks: workspace, 2 containers, 1 network, cidx index
  When cleanup executes
  Then each resource marked complete in marker file
  And partial progress tracked
  And resumable on interruption

# ========================================
# CATEGORY: Error Scenarios
# ========================================

Scenario: Disk full during archive operation
  Given staged files being archived
  And disk space exhausted
  When archive write fails
  Then IOException thrown
  And workspace cleanup continues without archive
  And error logged (non-critical failure)

Scenario: Permission denied on workspace deletion
  Given orphaned workspace has incorrect permissions
  When cleanup attempts deletion
  Then UnauthorizedAccessException thrown
  And error logged with workspace path
  And cleanup continues with remaining resources
  And failed workspace logged for manual intervention

Scenario: Docker daemon unavailable
  Given Docker daemon not running
  When container cleanup attempted
  Then connection error thrown
  And error logged
  And cleanup continues with file system resources
  And containers logged for manual cleanup

Scenario: Network filesystem timeout
  Given workspace on network filesystem (NFS)
  And network timeout occurs
  When cleanup attempts deletion
  Then timeout exception thrown
  And retry mechanism activates
  And eventual cleanup success or failure

# ========================================
# CATEGORY: Edge Cases
# ========================================

Scenario: Empty workspace directory
  Given orphaned workspace directory exists
  And directory contains no files
  When cleanup scans directory
  Then workspace marked for removal
  And simple directory deletion executed

Scenario: Workspace with symlinks
  Given orphaned workspace contains symlinks
  When cleanup executes
  Then symlinks removed (not followed)
  And target files remain intact
  And no data loss outside workspace

Scenario: Workspace with very large files (>10GB)
  Given orphaned workspace contains large files
  When cleanup executes
  Then cleanup proceeds normally
  And progress logged periodically
  And eventual completion

Scenario: Workspace with thousands of small files
  Given orphaned workspace has 50000 files
  When cleanup executes
  Then batch deletion used
  And progress logged
  And cleanup completes within reasonable time

Scenario: Orphan with special characters in path
  Given workspace path contains spaces and special chars
  When cleanup executes
  Then path properly escaped
  And deletion succeeds

# ========================================
# CATEGORY: High-Volume Scenarios
# ========================================

Scenario: Orphan detection with 100 workspaces
  Given 100 workspaces exist
  And 20 are orphaned
  When orphan detection runs
  Then all workspaces scanned within 30 seconds
  And 20 orphans identified correctly
  And no false positives

Scenario: Concurrent cleanup of 10 orphans
  Given 10 orphaned workspaces detected
  When cleanup executes
  Then cleanups execute in parallel (implementation-dependent)
  And all complete successfully
  And total time < 60 seconds

Scenario: Docker cleanup with 50 cidx containers
  Given 50 orphaned cidx containers
  When Docker cleanup runs
  Then all containers stopped
  And all containers removed
  And cleanup completes within 2 minutes

# ========================================
# CATEGORY: Observability and Logging
# ========================================

Scenario: Orphan detection logging on startup
  Given orphan detection completes
  When startup log is written
  Then entry contains: component="OrphanDetection"
  And operation="orphan_cleanup_completed"
  And orphans_detected count
  And orphan_directories_cleaned count
  And docker_containers_cleaned count
  And cidx_indexes_cleaned count
  And cleanup_failures count
  And disk_space_reclaimed_mb

Scenario: Safety check logging
  Given safety validation runs
  When active job protected from cleanup
  Then info logged: "Active job protected from cleanup: {jobId}"
  And heartbeat age logged
  And PID logged

Scenario: Cleanup progress logging
  Given cleanup in progress
  When resources removed
  Then progress logged for each resource type
  And "Removing workspace: {path}" logged
  And "Stopping container: {containerId}" logged
  And "Cleaning CIDX index: {path}" logged

Scenario: Cleanup failure logging
  Given cleanup fails for specific resource
  When error occurs
  Then error logged with full context
  And resource type logged
  And resource identifier logged
  And error details logged
  And manual intervention note added

Scenario: Cleanup summary logging
  Given cleanup completes
  When summary generated
  Then total resources processed logged
  And successful cleanups logged
  And failed cleanups logged
  And disk space reclaimed logged
  And duration logged
```

## Manual E2E Test Plan

**Prerequisites**:
- Claude Server with orphaned resources
- Admin token

**Test Steps**:

1. **Create Orphaned Resources**:
   ```bash
   # Start a job
   JOB_ID=$(curl -X POST https://localhost/api/jobs \
     -H "Authorization: Bearer $USER_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"prompt": "Test", "repository": "test-repo"}' | jq -r '.jobId')

   curl -X POST "https://localhost/api/jobs/$JOB_ID/start" \
     -H "Authorization: Bearer $USER_TOKEN"

   # Kill job process to create orphans
   sleep 10
   sudo pkill -9 -f claude-code

   # Verify orphaned workspace directory exists
   sudo ls -lah /var/lib/claude-batch-server/workspace/jobs/$JOB_ID/
   ```
   **Expected**: Orphaned job directory exists
   **Verify**: Directory contains job files but no active process

2. **Restart and Monitor Orphan Detection**:
   ```bash
   # Restart server (triggers orphan scan)
   sudo systemctl restart claude-batch-server
   sleep 10

   # Check startup log for orphan detection
   curl -s https://localhost/api/admin/startup-log \
     -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.operations[] | select(.component=="OrphanDetection")'
   ```
   **Expected**: Startup log shows orphans detected and cleaned
   **Verify**: Orphaned job directory identified, Docker containers cleaned, cidx indexes cleaned

3. **Verify Automatic Cleanup**:
   ```bash
   # Check orphaned directory removed
   sudo ls -lah /var/lib/claude-batch-server/workspace/jobs/$JOB_ID/
   ```
   **Expected**: Directory removed or cleaned
   **Verify**: Orphaned resources no longer exist

4. **Check Docker Cleanup**:
   ```bash
   # Verify cidx containers cleaned up
   docker ps -a | grep cidx
   ```
   **Expected**: No orphaned cidx containers
   **Verify**: Only active job containers remain

**Success Criteria**:
- ✅ Orphans detected accurately on startup
- ✅ Safety validation prevents active job cleanup
- ✅ Automatic cleanup removes orphaned resources
- ✅ Startup log provides complete visibility
- ✅ System continues operating if cleanup fails partially

## Observability Requirements

**Structured Logging** (all logged to startup log):
- Orphan detection results (directories, Docker containers, cidx indexes)
- Safety check outcomes (active vs orphaned resource determination)
- Automatic cleanup operations
- Resource removal confirmations
- Cleanup failures with error context

**Logged Data Fields**:
```json
{
  "component": "OrphanDetection",
  "operation": "orphan_cleanup_completed",
  "timestamp": "2025-10-15T10:00:30.123Z",
  "duration_ms": 3456,
  "orphans_detected": 5,
  "orphan_directories_cleaned": 3,
  "docker_containers_cleaned": 2,
  "cidx_indexes_cleaned": 2,
  "cleanup_failures": 0,
  "disk_space_reclaimed_mb": 450
}
```

**Metrics** (logged to structured log):
- Orphans detected per startup scan
- Automatic cleanup success rate (>95%)
- Resources reclaimed (disk space, containers)
- Scan duration (<30 seconds for 1000 jobs)
- Safety check accuracy (0% false positives)

## Definition of Done
- [ ] Implementation complete with TDD
- [ ] Manual E2E test executed successfully by Claude Code
- [ ] Orphan detection accurate with safety checks
- [ ] Automatic cleanup removes orphaned resources
- [ ] Safety checks prevent active job data loss
- [ ] Structured logging provides complete visibility
- [ ] Code reviewed and approved
# Story 3: Startup Recovery Orchestration with Monitoring

## User Story
**As a** system administrator
**I want** orchestrated recovery on every startup with aborted startup detection, automated retry, structured logging, and single API visibility
**So that** all recovery operations execute in order automatically, failed startups are detected and retried, and I can review all operations through the startup log

## Business Value
Ensures reliable system recovery through a well-orchestrated sequence of recovery operations, preventing race conditions and dependency failures. Detects incomplete startups and automatically cleans up partial state with retry logic. Fully automated recovery with comprehensive structured logging provides complete visibility without manual intervention. Single startup log API provides complete recovery history.

## Current State Analysis

**CURRENT BEHAVIOR**:
- **Initialization**: Simple linear initialization in `JobService.InitializeAsync()`
  - Location: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobService.cs` lines 101-180
  - Sequence: Load repositories → Load jobs → Recover crashed jobs
- **NO DEPENDENCY MANAGEMENT**: Operations run in fixed order, no topological sort
- **NO ORCHESTRATION**: No master orchestrator coordinating recovery
- **NO DEGRADED MODE**: No corrupted resource marking, no graceful degradation
- **NO ABORTED STARTUP DETECTION**: No markers tracking incomplete prior startups

**CURRENT INITIALIZATION FLOW**:
```csharp
// JobService.InitializeAsync() - lines 101-180
public async Task InitializeAsync()
{
    // Step 1: Load repositories (simple file read)
    await LoadRepositoriesAsync();

    // Step 2: Load jobs from disk
    await LoadJobsAsync();

    // Step 3: Recover crashed jobs (undefined behavior)
    await RecoverCrashedJobsAsync();

    // Step 4: Start background worker
    StartBackgroundWorker();

    // NO dependency tracking
    // NO retry logic
    // NO degraded mode
    // NO structured logging
}
```

**IMPLEMENTATION REQUIRED**:
- **BUILD** `RecoveryOrchestrator` - NEW CLASS (master coordinator)
- **BUILD** `DependencyResolver` - NEW CLASS (topological sort engine)
- **BUILD** `StartupDetector` - NEW CLASS (aborted startup detection)
- **BUILD** `PartialStateCleanup` - NEW CLASS (cleanup incomplete state)
- **BUILD** `RetryOrchestrator` - NEW CLASS (exponential backoff retry)
- **BUILD** `StartupLogger` - NEW CLASS (structured logging to file)
- **BUILD** `StartupLogAPI` - NEW CONTROLLER (single API endpoint)
- **MODIFY** `Program.cs` startup sequence to use orchestrator
- **REPLACE** linear initialization with dependency-based execution

**INTEGRATION POINTS**:
1. `Program.cs` Main() - Replace startup sequence with orchestrator
2. Recovery phases to orchestrate:
   - Aborted Startup Detection (new)
   - Queue & Statistics Recovery (Story 1)
   - Job Reattachment (Story 2)
   - Lock Persistence Recovery (Story 4)
   - Orphan Detection (Story 5)
   - Callback Delivery Resume (Story 6)
   - Waiting Queue Recovery (Story 7)
3. Startup log file: `/var/lib/claude-batch-server/claude-code-server-workspace/startup-log.json`
4. Startup marker file: `/var/lib/claude-batch-server/claude-code-server-workspace/.startup-in-progress`

**FILES TO MODIFY**:
- `/claude-batch-server/src/ClaudeBatchServer.Api/Program.cs` (startup orchestration)
- `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobService.cs` (remove linear init)
- Create new `/claude-batch-server/src/ClaudeBatchServer.Core/Services/RecoveryOrchestrator.cs`
- Create new `/claude-batch-server/src/ClaudeBatchServer.Api/Controllers/StartupLogController.cs`

**EFFORT**: 3 days

## Technical Approach
Implement orchestrated recovery sequence that coordinates all recovery operations in dependency order on EVERY startup. Fully automated execution with structured logging to startup log. Single API endpoint returns complete startup operation history. Degraded mode marks specific corrupted resources as unavailable while keeping ALL features enabled.

### Components
- `RecoveryOrchestrator`: Sequence coordinator with topological sort
- `DependencyResolver`: Automatic operation ordering based on dependencies
- `StartupDetector`: Aborted startup identification and marker tracking
- `PartialStateCleanup`: Remove incomplete initialization automatically
- `RetryOrchestrator`: Automated component retry logic with exponential backoff
- `StartupLogger`: Structured logging of all recovery and startup operations
- `StartupLogAPI`: Single API endpoint returning recovery history (`GET /api/admin/startup-log`)

### Part A: Aborted Startup Detection

**CRITICAL**: Detect incomplete startups from prior interrupted initialization attempts. Automatically clean up partial state and retry failed components.

**Startup Marker Mechanism**:
- **Marker File**: `{workspace}/.startup_marker.json`
- **Created**: At the beginning of every startup sequence
- **Updated**: After each recovery phase completes successfully
- **Removed**: When startup sequence completes fully
- **Detection**: If marker exists on next startup → prior startup was aborted

**Marker File Format**:
```json
{
  "startup_id": "uuid-v4",
  "started_at": "2025-10-15T10:00:00.000Z",
  "phases_completed": ["Queue", "Jobs"],
  "current_phase": "Locks"
}
```

**Abort Detection Algorithm**:
```csharp
async Task<bool> DetectAbortedStartup()
{
    var markerPath = Path.Combine(_workspace, ".startup_marker.json");

    if (!File.Exists(markerPath))
        return false; // No prior startup

    // Prior startup didn't complete
    var marker = await LoadMarker(markerPath);

    _logger.LogWarning("Aborted startup detected from {StartupId}, interrupted at phase: {Phase}",
        marker.StartupId, marker.CurrentPhase);

    // Cleanup partial state
    await CleanupPartialState(marker.PhasesCompleted, marker.CurrentPhase);

    // Remove old marker
    File.Delete(markerPath);

    return true;
}
```

**Partial State Cleanup**:
- Identify which phases completed vs interrupted
- Roll back interrupted phase (e.g., incomplete database migration)
- Preserve completed phases (e.g., queue recovery already succeeded)
- Allow retry on subsequent startup

**Automatic Retry Logic**:
```csharp
async Task<bool> RetryComponent(string componentName, int maxRetries = 3)
{
    for (int attempt = 1; attempt <= maxRetries; attempt++)
    {
        _logger.LogInformation("Retrying component {Component}, attempt {Attempt}/{Max}",
            componentName, attempt, maxRetries);

        // Exponential backoff: 1s, 2s, 4s
        if (attempt > 1)
            await Task.Delay(TimeSpan.FromSeconds(Math.Pow(2, attempt - 1)));

        try
        {
            var success = await ExecuteComponent(componentName);
            if (success)
            {
                _logger.LogInformation("Component {Component} retry succeeded", componentName);
                return true;
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Component {Component} retry attempt {Attempt} failed",
                componentName, attempt);
        }
    }

    _logger.LogError("Component {Component} retry exhausted after {Max} attempts",
        componentName, maxRetries);
    return false;
}
```

### Part B: Dependency Enforcement - CRITICAL SPECIFICATION

**CRITICAL**: Recovery phases MUST execute in strict dependency order to prevent race conditions and data corruption.

**Dependency Graph**:
```
Story 1: Queue and Statistics Persistence Recovery
    ↓
Story 4: Lock Persistence Recovery  +  Story 2: Job Reattachment
    ↓
Story 5: Orphan Detection
    ↓
Story 6: Webhook Delivery Resilience
```

**Enforcement Mechanism**: Topological Sort

**Why Topological Sort?**
- Automatically determines correct execution order from dependencies
- Detects circular dependencies (fail fast at startup)
- Allows parallel execution of independent phases
- Clear, verifiable ordering algorithm

**Implementation**:
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
        // STEP 0: Detect aborted startup
        var abortedStartup = await _startupDetector.DetectAbortedStartup();
        if (abortedStartup)
        {
            _logger.LogWarning("Aborted startup detected, partial state cleaned");
        }

        // STEP 1: Create startup marker
        await _startupDetector.CreateStartupMarker();

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
                Name = "Orphans",
                Execute = RecoverOrphansAsync,
                DependsOn = new() { "Locks", "Jobs" },
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

        // STEP FINAL: Remove startup marker (startup completed successfully)
        await _startupDetector.RemoveStartupMarker();

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

**Critical Phase Failure Behavior**:
- **Queue Recovery Fails COMPLETELY** → ABORT entire recovery (system unusable)
- **Job Reattachment Fails COMPLETELY** → ABORT (can't recover running jobs)
- **Lock Recovery Fails PARTIALLY** → Mark corrupted locks' repositories as unavailable, continue
- **Orphan Detection/Cleanup Fails** → Log errors, continue (orphans remain, will retry next startup)

**Degraded Mode - REDEFINED**:

**CRITICAL**: Degraded mode does NOT mean features are disabled. It means specific corrupted resources are marked unavailable while ALL features remain enabled.

**OLD Definition (WRONG)**:
- Lock recovery fails → Lock enforcement disabled system-wide
- System operational but lock feature turned off

**NEW Definition (CORRECT)**:
- Lock recovery fails for repo-B → ONLY repo-B marked "unavailable"
- Lock enforcement remains ENABLED system-wide
- ALL other locks work normally
- Jobs targeting repo-B will fail with "repository unavailable"
- Admins can fix corrupted repo-B lock file while system runs

**Example Scenario**:
```
Startup Recovery:
1. Queue Recovery → Success ✅ (15 jobs restored)
2. Job Reattachment → Success ✅ (3 jobs reattached)
3. Lock Recovery → Partial Success ⚠️
   - repo-A lock recovered ✅
   - repo-B lock CORRUPTED ❌ → Mark repo-B "unavailable"
   - repo-C lock recovered ✅
4. Orphan Detection → Success ✅ (5 orphans cleaned)
5. System starts: Fully operational with ALL features enabled
6. Degraded state: repo-B unavailable, all other resources functional
```

**NO Feature Disabling**:
- Lock enforcement: ALWAYS enabled
- Orphan detection: ALWAYS enabled
- Cleanup: ALWAYS enabled
- Only specific corrupted resources become unusable

## Acceptance Criteria

```gherkin
# ========================================
# CATEGORY: Topological Sort Correctness
# ========================================

Scenario: Topological sort with linear dependencies
  Given phases: Queue → Locks → Orphans → Callbacks
  When TopologicalSort() is called
  Then execution order is: [Queue, Locks, Orphans, Callbacks]
  And dependencies respected
  And no phase executes before its dependencies

Scenario: Topological sort with parallel-capable phases
  Given phases: Queue → (Locks + Jobs) → Orphans
  And Locks and Jobs both depend only on Queue
  When TopologicalSort() is called
  Then execution order allows: [Queue, Locks, Jobs, Orphans] or [Queue, Jobs, Locks, Orphans]
  And both Locks and Jobs execute after Queue
  And Orphans executes after both Locks and Jobs

Scenario: Topological sort with diamond dependencies
  Given phases: A → (B + C) → D
  And D depends on both B and C
  When TopologicalSort() is called
  Then A executes first
  And B and C execute after A
  And D executes after both B and C complete

Scenario: Topological sort with no dependencies
  Given phases: A, B, C with no dependencies
  When TopologicalSort() is called
  Then any execution order is valid
  And all phases can execute in parallel

Scenario: Circular dependency detection
  Given phases: A → B → C → A (circular)
  When TopologicalSort() is called
  Then InvalidOperationException thrown
  And error message contains "Circular dependency detected"
  And phase name included in error
  And startup aborts

Scenario: Unknown dependency reference
  Given phase "Orphans" depends on "UnknownPhase"
  And "UnknownPhase" does not exist
  When TopologicalSort() is called
  Then InvalidOperationException thrown
  And error message contains "depends on unknown phase: UnknownPhase"
  And startup aborts

# ========================================
# CATEGORY: Aborted Startup Detection
# ========================================

Scenario: Startup marker creation at initialization
  Given server starts
  When startup sequence begins
  Then marker file created at {workspace}/.startup_marker.json
  And file contains: startup_id (UUID), started_at (timestamp), phases_completed (empty array), current_phase (null)
  And atomic write operation used

Scenario: Marker update after phase completion
  Given startup marker exists
  And Queue recovery phase completes
  When marker is updated
  Then phases_completed array contains "Queue"
  And current_phase updated to next phase name
  And file written atomically

Scenario: Marker removal on successful startup
  Given all recovery phases complete successfully
  When startup sequence finishes
  Then .startup_marker.json file deleted
  And clean startup state confirmed

Scenario: Aborted startup detection on next start
  Given .startup_marker.json exists from previous startup
  When next startup begins
  Then DetectAbortedStartup() returns true
  And marker file loaded and parsed
  And interrupted phase identified from current_phase
  And warning logged with startup_id and interrupted phase

Scenario: Partial state cleanup after abort detection
  Given aborted startup detected
  And marker shows phases_completed: ["Queue", "Locks"]
  And current_phase: "Jobs"
  When CleanupPartialState() executes
  Then Queue and Locks states preserved (completed phases)
  And Jobs phase rolled back (interrupted phase)
  And system ready for fresh recovery attempt

Scenario: Normal startup with no prior marker
  Given no .startup_marker.json exists
  When DetectAbortedStartup() is called
  Then returns false
  And no cleanup needed
  And startup proceeds normally

# ========================================
# CATEGORY: Automatic Retry Logic
# ========================================

Scenario: Retry component with exponential backoff
  Given component "Locks" fails on first attempt
  When RetryComponent() is called with maxRetries=3
  Then attempt 1 executes immediately
  And attempt 2 executes after 1 second delay
  And attempt 3 executes after 2 seconds delay
  And attempt 4 executes after 4 seconds delay (if needed)

Scenario: Successful retry on second attempt
  Given component fails on attempt 1
  And succeeds on attempt 2
  When RetryComponent() executes
  Then retry loop exits after attempt 2
  And success logged
  And method returns true

Scenario: Retry exhaustion after 3 attempts
  Given component fails on all 3 attempts
  When RetryComponent() executes
  Then all 3 attempts executed with backoff
  And error logged: "Component retry exhausted after 3 attempts"
  And method returns false

Scenario: Retry with exception handling
  Given component throws exception on attempt 1
  And succeeds on attempt 2
  When RetryComponent() executes
  Then exception caught and logged
  And retry continues to attempt 2
  And eventual success returned

# ========================================
# CATEGORY: Degraded Mode Transitions
# ========================================

Scenario: Degraded mode for corrupted lock file
  Given Lock recovery phase executes
  And repo-B lock file is corrupted
  When lock recovery processes repo-B
  Then repo-B marked "unavailable" in degraded resources list
  And ALL other locks recover successfully
  And phase completes with partial success
  And DegradedMode flag set to true
  And lock enforcement remains enabled system-wide

Scenario: Degraded mode with multiple corrupted resources
  Given Lock recovery finds 2 corrupted locks
  And Orphan detection fails for 1 resource
  When recovery completes
  Then degraded_mode = true
  And corrupted_resources = ["lock:repo-A", "lock:repo-B", "orphan:job-xyz"]
  And all features remain enabled
  And only specific resources marked unavailable

Scenario: No degraded mode when all phases succeed
  Given all recovery phases complete successfully
  When recovery finishes
  Then DegradedMode flag remains false
  And corrupted_resources list is empty
  And system fully operational

Scenario: Critical phase failure prevents degraded mode
  Given Queue recovery fails completely
  When recovery attempts to continue
  Then startup aborts immediately
  And degraded mode NOT entered (system unusable)
  And error logged with full context

# ========================================
# CATEGORY: Startup Log API Format
# ========================================

Scenario: Startup log API response structure
  Given recovery completes
  When GET /api/admin/startup-log is called
  Then response contains: current_startup object
  And current_startup contains: startup_timestamp, total_duration_ms, degraded_mode, corrupted_resources, operations array
  And operations array contains entry for each phase
  And startup_history array contains previous startups

Scenario: Startup log operation entry format
  Given Queue recovery completes
  When operation logged
  Then entry contains: component="QueueRecovery"
  And operation="recovery_completed"
  And timestamp in ISO 8601 format
  And duration_ms as number
  And status="success"|"partial_success"|"failed"
  And phase-specific fields (e.g., jobs_recovered)

Scenario: Startup log degraded mode indicators
  Given degraded mode triggered
  When startup log API response generated
  Then degraded_mode field = true
  And corrupted_resources array populated
  And each resource formatted as "{type}:{identifier}"
  And affected operations show partial_success status

# ========================================
# CATEGORY: Dependency Enforcement
# ========================================

Scenario: Queue must execute before Locks
  Given recovery phases defined
  And Locks depends on Queue
  When orchestration executes
  Then Queue executes first
  And Locks waits for Queue completion
  And Locks only executes after Queue succeeds

Scenario: Parallel execution of independent phases
  Given Locks and Jobs both depend on Queue
  And neither depends on the other
  When orchestration executes
  Then Locks and Jobs can execute in parallel
  And both wait only for Queue

Scenario: Orphan detection waits for prerequisites
  Given Orphans depends on Locks and Jobs
  When orchestration executes
  Then Orphans executes only after both Locks AND Jobs complete
  And executes regardless of which completes first

Scenario: Dependency failure halts dependent phases
  Given Orphans depends on Jobs
  And Jobs phase fails (non-critical, degraded mode)
  When orchestration continues
  Then Orphans phase still executes (Jobs marked degraded but not blocking)
  And system continues with degraded state

# ========================================
# CATEGORY: Critical vs Non-Critical Phases
# ========================================

Scenario: Critical phase success
  Given Queue recovery phase marked Critical=true
  And Queue recovery succeeds
  When orchestration continues
  Then next phases execute normally
  And no degraded mode triggered

Scenario: Critical phase failure aborts startup
  Given Queue recovery phase marked Critical=true
  And Queue recovery fails completely
  When orchestration processes failure
  Then startup ABORTS immediately
  And remaining phases NOT executed
  And error logged with full context
  And system does not start

Scenario: Non-critical phase failure with AllowDegradedMode=true
  Given Lock recovery marked Critical=false, AllowDegradedMode=true
  And Lock recovery fails
  When orchestration processes failure
  Then warning logged
  And phase added to SkippedPhases list
  And DegradedMode flag set to true
  And orchestration continues with next phase

Scenario: Non-critical phase failure without AllowDegradedMode
  Given Orphan detection marked Critical=false, AllowDegradedMode=false
  And Orphan detection fails
  When orchestration processes failure
  Then error logged
  And FailedPhase set to "Orphans"
  And startup aborts (non-critical but not degraded-capable)

# ========================================
# CATEGORY: Error Scenarios
# ========================================

Scenario: Exception during phase execution
  Given Lock recovery throws exception
  And Locks marked Critical=false, AllowDegradedMode=true
  When exception caught
  Then exception logged with stack trace
  And phase marked as skipped
  And degraded mode entered
  And orchestration continues

Scenario: Exception during critical phase
  Given Queue recovery throws exception
  And Queue marked Critical=true
  When exception caught
  Then exception logged
  And startup aborts immediately
  And system does not start

Scenario: File system error during marker write
  Given marker file update fails with IOException
  When marker update attempted
  Then error logged
  And startup continues (non-critical operation)
  And abort detection may not work next startup (degraded tracking)

# ========================================
# CATEGORY: Edge Cases
# ========================================

Scenario: Empty phases list
  Given no recovery phases defined
  When ExecuteRecoverySequenceAsync() is called
  Then topological sort returns empty list
  And no phases executed
  And recovery completes immediately
  And Success=true

Scenario: Single phase with no dependencies
  Given only Queue phase defined
  When orchestration executes
  Then Queue executes
  And topological sort trivial
  And recovery completes successfully

Scenario: All phases skip (degraded mode)
  Given all non-critical phases fail
  And all allow degraded mode
  When orchestration completes
  Then DegradedMode=true
  And SkippedPhases contains all phase names
  And CompletedPhases empty (except critical phases)
  And Success=true (system starts in degraded state)

Scenario: Marker file with future timestamp
  Given .startup_marker.json has started_at in future
  When abort detection runs
  Then clock skew detected
  And warning logged
  And marker treated as aborted (conservative)

# ========================================
# CATEGORY: High-Volume Scenarios
# ========================================

Scenario: Recovery with 100 phases
  Given 100 recovery phases defined with complex dependencies
  When TopologicalSort() executes
  Then sort completes within 1 second
  And correct dependency order determined
  And all phases execute in order

Scenario: Parallel execution of 10 independent phases
  Given 10 phases with no mutual dependencies
  When orchestration executes
  Then phases execute in parallel (implementation-dependent)
  And all complete successfully
  And total time less than sequential execution

# ========================================
# CATEGORY: Observability
# ========================================

Scenario: Startup marker logging
  Given marker created/updated/removed
  When operations execute
  Then marker creation logged with startup_id
  And updates logged with completed phase
  And removal logged on successful startup

Scenario: Abort detection logging
  Given aborted startup detected
  When detection occurs
  Then warning logged with: prior startup_id, interrupted phase, phases completed
  And cleanup actions logged
  And retry attempts logged

Scenario: Phase execution logging
  Given phase starts execution
  When phase runs
  Then "Starting recovery phase: {PhaseName}" logged
  And phase completion logged with duration
  And errors logged with full context

Scenario: Degraded mode logging
  Given degraded mode triggered
  When phase fails with AllowDegradedMode=true
  Then warning logged: "Non-critical recovery phase failed, continuing in degraded mode: {PhaseName}"
  And corrupted resources logged
  And feature availability logged

Scenario: Recovery result logging
  Given recovery completes
  When final result logged
  Then "Recovery sequence completed. Degraded mode: {true|false}" logged
  And CompletedPhases list logged
  And SkippedPhases list logged
  And total duration logged
```

## Manual E2E Test Plan

**Prerequisites**:
- Claude Server
- Admin authentication
- Test data with potential for degraded mode

**Test Steps**:

1. **Test Aborted Startup Detection**:
   ```bash
   # Start server
   sudo systemctl start claude-batch-server &
   sleep 2

   # Kill during startup (simulate crash during initialization)
   sudo pkill -9 -f "ClaudeBatchServer.Api"

   # Restart server
   sudo systemctl start claude-batch-server
   sleep 10

   # Check startup log for abort detection
   curl -s https://localhost/api/admin/startup-log \
     -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.operations[] | select(.component=="StartupDetection")'
   ```
   **Expected**: Startup log shows aborted startup detected, cleanup performed, retry attempts
   **Verify**: Shows interrupted components, cleanup actions, retry attempts, recovery success

2. **Test Automatic Component Retry**:
   ```bash
   # Check retry operations in startup log
   curl -s https://localhost/api/admin/startup-log \
     -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.operations[] | select(.operation=="retry_completed")'
   ```
   **Expected**: Components retried automatically with exponential backoff
   **Verify**: Retry attempts logged with delays (1s, 2s, 4s), success/failure status

3. **Test Normal Startup Recovery**:
   ```bash
   # Restart server to trigger recovery
   sudo systemctl restart claude-batch-server
   sleep 10

   # Get startup log
   curl -s https://localhost/api/admin/startup-log \
     -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.'
   ```
   **Expected**: Complete startup log with all recovery operations
   **Verify**: All components present, dependency order respected, timestamps logged

4. **Verify Recovery Sequence Order**:
   ```bash
   # Extract component execution order
   curl -s https://localhost/api/admin/startup-log \
     -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.operations[].component'
   ```
   **Expected**: Order shows topological sort: Queue → (Locks + Jobs) → Orphans → Callbacks
   **Verify**: Dependencies respected, no race conditions

5. **Test Degraded Mode (Corrupted Lock)**:
   ```bash
   # Stop server
   sudo systemctl stop claude-batch-server

   # Corrupt a lock file
   echo "CORRUPTED" | sudo tee /var/lib/claude-batch-server/workspace/locks/test-repo.lock.json

   # Restart
   sudo systemctl start claude-batch-server
   sleep 10

   # Check degraded mode in startup log
   curl -s https://localhost/api/admin/startup-log \
     -H "Authorization: Bearer $ADMIN_TOKEN" | jq '{degraded_mode, corrupted_resources, lock_enforcement_enabled}'
   ```
   **Expected**: degraded_mode=true, corrupted_resources=["lock:test-repo"], lock_enforcement_enabled=true
   **Verify**: test-repo unavailable, all other repos functional, lock enforcement still enabled

6. **Test Critical Failure Abort**:
   ```bash
   # Stop server
   sudo systemctl stop claude-batch-server

   # Corrupt queue snapshot completely
   echo "INVALID JSON" | sudo tee /var/lib/claude-batch-server/workspace/queue-snapshot.json

   # Delete WAL too (force complete failure)
   sudo rm -f /var/lib/claude-batch-server/workspace/queue.wal

   # Try to start (should fail)
   sudo systemctl start claude-batch-server
   sleep 5

   # Check if server started
   sudo systemctl status claude-batch-server
   ```
   **Expected**: Server fails to start (queue recovery critical)
   **Verify**: Startup aborted, error logged, safe failure

7. **Check Startup Log Retention**:
   ```bash
   # Restart multiple times
   for i in {1..3}; do
     sudo systemctl restart claude-batch-server
     sleep 10
   done

   # Check how many startup logs retained
   curl -s https://localhost/api/admin/startup-log \
     -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.startup_history | length'
   ```
   **Expected**: Multiple startup logs retained (default: last 10)
   **Verify**: Historical startup data preserved

**Success Criteria**:
- ✅ Aborted startups detected automatically
- ✅ Partial state cleaned up automatically
- ✅ Retry mechanism works automatically with exponential backoff
- ✅ Recovery sequence automatically orchestrated
- ✅ Dependencies respected via topological sort
- ✅ Startup log API provides complete visibility
- ✅ Degraded mode marks corrupted resources correctly
- ✅ Critical failures abort startup safely
- ✅ NO manual intervention needed

## Observability Requirements

**SINGLE API** (ONLY API in entire epic):
- `GET /api/admin/startup-log` - Complete startup operation history

**API Response Format**:
```json
{
  "current_startup": {
    "startup_timestamp": "2025-10-15T10:00:00.000Z",
    "total_duration_ms": 5678,
    "degraded_mode": true,
    "corrupted_resources": ["lock:repo-B"],
    "operations": [
      {
        "component": "QueueRecovery",
        "operation": "recovery_completed",
        "timestamp": "2025-10-15T10:00:01.123Z",
        "duration_ms": 1234,
        "status": "success",
        "jobs_recovered": 15
      },
      {
        "component": "LockRecovery",
        "operation": "lock_recovery_completed",
        "timestamp": "2025-10-15T10:00:02.456Z",
        "duration_ms": 234,
        "status": "partial_success",
        "locks_recovered": 4,
        "corrupted_locks": 1,
        "corrupted_repositories": ["repo-B"]
      }
    ]
  },
  "startup_history": [
    { /* Previous startup log */ },
    { /* Previous startup log */ }
  ]
}
```

**Structured Logging**:
- Startup marker creation and validation
- Abort detection with interrupted component identification
- Cleanup operations (partial state removal)
- Automatic retry attempts with exponential backoff
- Success/failure status for each component
- All recovery operations logged to startup log
- Topological sort execution order
- Dependency resolution results
- Degraded mode triggers
- Corrupted resource marking

**Metrics** (logged to structured log):
- Total recovery time (<60 seconds target)
- Phase durations
- Success/failure rates
- Degraded mode frequency
- Corrupted resource count

## Definition of Done
- [ ] Implementation complete with TDD
- [ ] Manual E2E test executed successfully by Claude Code
- [ ] Aborted startup detection works reliably
- [ ] Partial state cleanup removes incomplete initialization automatically
- [ ] Automatic retry functional with exponential backoff
- [ ] Recovery sequence works correctly via topological sort
- [ ] Single startup log API provides complete visibility
- [ ] Degraded mode correctly marks corrupted resources
- [ ] NO feature disabling occurs
- [ ] Code reviewed and approved

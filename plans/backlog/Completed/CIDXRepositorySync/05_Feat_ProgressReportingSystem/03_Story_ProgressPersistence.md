# Story 5.3: Progress Persistence

## Story Description

As a CIDX system maintaining sync history, I need to persist progress information across sessions, enabling resume capabilities for interrupted syncs and providing historical metrics for performance optimization.

## Technical Specification

### Persistence Model

```pseudocode
class ProgressPersistence:
    def __init__(projectId: string):
        self.dbPath = ~/.cidx/progress/{projectId}.db
        self.currentSync = None
        self.history = []

    def saveProgress(syncProgress: SyncProgress):
        # Real-time progress updates
        record = ProgressRecord {
            jobId: syncProgress.jobId
            timestamp: now()
            phase: syncProgress.currentPhase
            overallProgress: syncProgress.percent
            phaseProgress: syncProgress.phasePercent
            filesProcessed: syncProgress.filesProcessed
            totalFiles: syncProgress.totalFiles
            rate: syncProgress.currentRate
            checkpointData: syncProgress.checkpoint
        }

        # Save to SQLite
        db.insert("progress_updates", record)

        # Update checkpoint for resume
        if syncProgress.percent % 5 == 0:  # Every 5%
            saveCheckpoint(record)

class ProgressCheckpoint:
    jobId: string
    timestamp: timestamp
    gitCommit: string
    filesIndexed: List<FilePath>
    filesPending: List<FilePath>
    phase: SyncPhase
    metadata: dict
```

### Resume Capability

```pseudocode
class ResumeManager:
    def checkResumable(projectId: string) -> ResumeInfo:
        lastSync = getLastIncompleteSync(projectId)

        if not lastSync:
            return None

        if lastSync.age > 24_hours:
            return None  # Too old

        return ResumeInfo {
            jobId: lastSync.jobId
            progress: lastSync.progress
            phase: lastSync.phase
            filesRemaining: lastSync.filesPending
            estimatedTime: calculateRemainingTime()
            canResume: validateCheckpoint()
        }

    def resumeSync(checkpoint: ProgressCheckpoint):
        # Skip completed work
        skipCompletedPhases(checkpoint.phase)
        skipProcessedFiles(checkpoint.filesIndexed)

        # Continue from checkpoint
        startFromPhase(checkpoint.phase)
        processFiles(checkpoint.filesPending)
```

## Acceptance Criteria

### State Saving
```gherkin
Given an active sync operation
When progress updates occur
Then the system should:
  - Save progress every second
  - Create checkpoints every 5%
  - Store phase information
  - Record file lists
  - Track timing metrics
And persist to local database
```

### Resume Capability
```gherkin
Given an interrupted sync operation
When user runs sync again
Then the system should:
  - Detect incomplete sync
  - Offer to resume
  - Skip completed work
  - Continue from checkpoint
  - Merge with new changes
And complete efficiently
```

### History Tracking
```gherkin
Given completed sync operations
When storing historical data
Then the system should track:
  - Start and end times
  - Total duration per phase
  - Files processed count
  - Data volumes
  - Success/failure status
And maintain 30-day history
```

### Metrics Storage
```gherkin
Given sync performance data
When calculating metrics
Then the system should store:
  - Average phase durations
  - Processing rates
  - Success rates
  - Common failure points
  - Resource usage
And use for optimization
```

### Cleanup Operations
```gherkin
Given accumulated progress data
When performing maintenance
Then the system should:
  - Delete old checkpoints (>7 days)
  - Archive completed syncs
  - Compress historical data
  - Limit database size
  - Vacuum database monthly
And maintain performance
```

## Completion Checklist

- [ ] State saving
  - [ ] SQLite schema
  - [ ] Progress recording
  - [ ] Checkpoint creation
  - [ ] Transaction safety
- [ ] Resume capability
  - [ ] Incomplete detection
  - [ ] Resume prompt
  - [ ] State restoration
  - [ ] Work skipping
- [ ] History tracking
  - [ ] Sync records
  - [ ] Phase metrics
  - [ ] Performance data
  - [ ] Retention policy
- [ ] Metrics storage
  - [ ] Aggregation logic
  - [ ] Statistical analysis
  - [ ] Trend detection
  - [ ] Report generation

## Test Scenarios

### Happy Path
1. Normal sync → Progress saved → History recorded
2. Interrupt sync → Resume offered → Continues correctly
3. View history → Metrics shown → Accurate data
4. Auto-cleanup → Old data removed → Size maintained

### Error Cases
1. Database corrupt → Recreate database → Continue sync
2. Checkpoint invalid → Full sync required → User informed
3. Disk full → Cleanup attempted → Space recovered
4. Resume fails → Start fresh → Old state cleared

### Edge Cases
1. Multiple interrupts → Latest checkpoint → Resume once
2. Concurrent syncs → Separate tracking → No conflicts
3. Clock change → Handle timestamps → Correct ordering
4. Database locked → Retry with backoff → Eventually succeed

## Performance Requirements

- Save progress: <10ms
- Create checkpoint: <50ms
- Load checkpoint: <100ms
- Query history: <200ms
- Database size: <50MB per project

## Database Schema

```sql
-- Progress updates table
CREATE TABLE progress_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    phase TEXT NOT NULL,
    overall_progress INTEGER,
    phase_progress INTEGER,
    files_processed INTEGER,
    total_files INTEGER,
    rate REAL,
    checkpoint_data JSON,
    INDEX idx_job_id (job_id),
    INDEX idx_timestamp (timestamp)
);

-- Sync history table
CREATE TABLE sync_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,
    project_id TEXT NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    status TEXT,
    total_duration INTEGER,
    phase_durations JSON,
    files_changed INTEGER,
    files_indexed INTEGER,
    errors JSON,
    INDEX idx_project_id (project_id),
    INDEX idx_start_time (start_time)
);

-- Checkpoints table
CREATE TABLE checkpoints (
    job_id TEXT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    git_commit TEXT,
    phase TEXT,
    files_completed JSON,
    files_pending JSON,
    metadata JSON,
    INDEX idx_created_at (created_at)
);
```

## Resume Prompt

```
📎 Incomplete sync detected!

Previous sync was 67% complete when interrupted 15 minutes ago
  • Phase: Indexing Files
  • Files processed: 234/350
  • Estimated time to complete: 2 minutes

Would you like to:
  [R]esume from checkpoint (recommended)
  [S]tart fresh sync
  [V]iew details
  [C]ancel

Choice: _
```

## Historical Metrics Display

```
📊 Sync Performance History (Last 7 days)

Average Duration by Phase:
  • Git Fetch:    45s (↓ 12% improvement)
  • Git Merge:    8s  (stable)
  • Indexing:     2m 30s (↑ 5% slower)
  • Validation:   15s (stable)

Success Rate: 94% (47/50 syncs)
Average Total Time: 3m 38s
Peak Usage: Monday 10am-12pm

Recent Syncs:
  2024-01-15 10:30  ✓  3m 12s  1,234 files
  2024-01-15 08:45  ✓  2m 58s    987 files
  2024-01-14 16:20  ✗  Failed   Network timeout
  2024-01-14 14:10  ✓  4m 05s  1,456 files
```

## Checkpoint Data Structure

```json
{
  "jobId": "abc-123-def",
  "timestamp": "2024-01-15T10:30:45Z",
  "gitCommit": "a1b2c3d4",
  "phase": {
    "name": "Indexing Files",
    "progress": 67,
    "startTime": "2024-01-15T10:28:00Z"
  },
  "files": {
    "completed": ["src/main.py", "src/utils.py"],
    "pending": ["src/api.py", "tests/test_main.py"],
    "skipped": ["docs/image.png"]
  },
  "metrics": {
    "rate": 45.2,
    "memoryUsage": 234567890,
    "cpuPercent": 65
  }
}
```

## Definition of Done

- [ ] Progress persistence to SQLite
- [ ] Checkpoint creation every 5%
- [ ] Resume detection and prompting
- [ ] Work skipping from checkpoint
- [ ] Historical data retention
- [ ] Metrics aggregation working
- [ ] Database cleanup automated
- [ ] Unit tests >90% coverage
- [ ] Integration tests verify resume
- [ ] Performance requirements met
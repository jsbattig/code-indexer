# Story 1.2: Job Persistence Layer

## Story Description

As a CIDX server operator, I need a reliable persistence layer for job state that survives server restarts and enables job recovery, so that long-running sync operations can resume after interruptions.

## Technical Specification

### Database Schema

```sql
-- SQLite schema for job persistence
CREATE TABLE sync_jobs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER DEFAULT 0,
    phase TEXT,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    metadata JSON,
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
);

CREATE TABLE job_checkpoints (
    job_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    checkpoint_data JSON,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (job_id, phase),
    FOREIGN KEY (job_id) REFERENCES sync_jobs(id)
);
```

### Persistence Operations

```pseudocode
class JobPersistence:
    saveJob(job: SyncJob) -> bool
    loadJob(jobId: string) -> SyncJob
    updateJobStatus(jobId: string, status: JobStatus) -> bool
    updateJobProgress(jobId: string, progress: int, phase: string) -> bool
    queryJobs(filter: JobFilter) -> List[SyncJob]
    deleteExpiredJobs(olderThan: timestamp) -> int
    saveCheckpoint(jobId: string, phase: string, data: dict) -> bool
    loadCheckpoint(jobId: string, phase: string) -> dict
```

## Acceptance Criteria

### SQLite Database Schema
```gherkin
Given the CIDX server is starting
When the persistence layer initializes
Then the SQLite database should be created if not exists
And the sync_jobs table should be created with proper schema
And the job_checkpoints table should be created
And proper indexes should be established
And WAL mode should be enabled for concurrency
```

### CRUD Operations
```gherkin
Given a job persistence layer is initialized
When I perform CRUD operations:
  - Create: saveJob() stores new job
  - Read: loadJob() retrieves existing job
  - Update: updateJobStatus() modifies state
  - Delete: deleteExpiredJobs() removes old jobs
Then all operations should complete successfully
And data integrity should be maintained
And concurrent operations should not conflict
```

### Query Capabilities
```gherkin
Given multiple jobs exist in the database
When I query with filters:
  - By user_id: Returns only that user's jobs
  - By status: Returns jobs in specific states
  - By date range: Returns jobs within timeframe
  - With pagination: Returns limited results
Then the correct filtered results should be returned
And queries should complete in <100ms
```

### Cleanup Routines
```gherkin
Given jobs older than 7 days exist
When the cleanup routine runs
Then expired jobs should be deleted
And associated checkpoints should be removed
And active jobs should not be affected
And cleanup should log number of removed jobs
```

### Checkpoint Management
```gherkin
Given a running sync job
When a checkpoint is saved for a phase
Then the checkpoint data should be persisted
And previous checkpoints for that phase should be replaced
And the job should be resumable from that checkpoint
```

## Completion Checklist

- [ ] SQLite database schema
  - [ ] sync_jobs table creation
  - [ ] job_checkpoints table creation
  - [ ] Index optimization
  - [ ] WAL mode configuration
- [ ] CRUD operations
  - [ ] Create job records
  - [ ] Read job by ID
  - [ ] Update job fields
  - [ ] Delete expired jobs
- [ ] Query capabilities
  - [ ] Filter by user_id
  - [ ] Filter by status
  - [ ] Date range queries
  - [ ] Pagination support
- [ ] Cleanup routines
  - [ ] Scheduled cleanup task
  - [ ] Configurable retention period
  - [ ] Cascade delete checkpoints
  - [ ] Cleanup logging

## Test Scenarios

### Happy Path
1. Save new job → Job persisted to database
2. Load job by ID → Complete job data returned
3. Update job progress → Changes reflected in DB
4. Query user jobs → Filtered results returned
5. Run cleanup → Old jobs removed

### Error Cases
1. Save duplicate job ID → Constraint violation handled
2. Load non-existent job → Returns null/not found
3. Database connection lost → Graceful error handling
4. Corrupt database → Recovery attempted

### Edge Cases
1. Concurrent updates to same job → Last write wins
2. Database file permissions issue → Clear error message
3. Disk full during write → Transaction rolled back
4. Query with no results → Empty list returned

## Performance Requirements

- Single job save/load: <10ms
- Query 100 jobs: <100ms  
- Cleanup 1000 expired jobs: <1 second
- Database size: <100MB for 10,000 jobs
- Connection pool: 5-10 connections

## Definition of Done

- [ ] SQLite database with proper schema created
- [ ] All CRUD operations implemented and tested
- [ ] Query filters working with indexes
- [ ] Cleanup routine removes expired jobs
- [ ] Checkpoint save/load functionality complete
- [ ] Transaction support for data integrity
- [ ] Unit tests >90% coverage
- [ ] Integration tests verify persistence
- [ ] Performance benchmarks met
- [ ] Database migrations supported
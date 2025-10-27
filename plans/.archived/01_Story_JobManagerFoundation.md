# Story 1.1: Job Manager Foundation

## Story Description

As a CIDX server administrator, I need a robust job management system that creates, tracks, and manages sync jobs with unique identifiers and state transitions, so that multiple users can run concurrent sync operations reliably.

## Technical Specification

### Job Data Model

```pseudocode
SyncJob {
    id: UUID
    userId: string
    projectId: string
    status: JobStatus
    progress: integer (0-100)
    phase: SyncPhase
    createdAt: timestamp
    startedAt: timestamp
    completedAt: timestamp
    error: string
    metadata: dict
}

JobStatus: CREATED | QUEUED | RUNNING | COMPLETED | FAILED | CANCELLED
SyncPhase: INIT | GIT_SYNC | INDEXING | FINALIZING
```

### API Contracts

```pseudocode
POST /api/sync
Request: {
    projectId: string
    options: {
        fullReindex: boolean
        branch: string
    }
}
Response: {
    jobId: UUID
    status: "created"
}

GET /api/jobs/{jobId}/status
Response: {
    jobId: UUID
    status: JobStatus
    progress: integer
    phase: SyncPhase
    message: string
    error: string (if failed)
}
```

## Acceptance Criteria

### Job Creation
```gherkin
Given I am an authenticated user with a linked repository
When I initiate a sync operation
Then a new job should be created with a unique UUID
And the job should be associated with my user ID
And the job should have status "CREATED"
And I should receive the job ID in the response
```

### State Transition Management
```gherkin
Given a sync job exists in "CREATED" state
When the job begins execution
Then the status should transition to "RUNNING"
And the startedAt timestamp should be recorded
And the transition should be atomic
And no invalid state transitions should be allowed
```

### Job Metadata Storage
```gherkin
Given I create a sync job with options
When the job is stored
Then all metadata should be preserved:
  - User ID and Project ID
  - Creation timestamp
  - Sync options (fullReindex, branch)
  - Initial status and progress
And the metadata should be queryable
```

### User Association Tracking
```gherkin
Given multiple users are using the system
When I query for my jobs
Then I should only see jobs associated with my user ID
And I should not see other users' jobs
And the association should be enforced at API level
```

### Job Retrieval
```gherkin
Given a job with ID "abc-123" exists
When I request GET /api/jobs/abc-123/status
Then I should receive the current job state
And the response should include:
  - Current status and progress
  - Current phase if running
  - Error message if failed
  - Completion time if finished
```

## Completion Checklist

- [ ] Job creation with unique IDs
  - [ ] UUID generation implementation
  - [ ] Job object initialization
  - [ ] Initial state setting
- [ ] State transition management  
  - [ ] State machine implementation
  - [ ] Atomic transitions
  - [ ] Invalid transition prevention
- [ ] Job metadata storage
  - [ ] Complete data model
  - [ ] Persistence layer integration
  - [ ] Metadata validation
- [ ] User association tracking
  - [ ] User ID validation
  - [ ] Access control checks
  - [ ] Query filtering by user

## Test Scenarios

### Happy Path
1. Create job → Returns job ID
2. Query job → Shows CREATED status
3. Job starts → Status becomes RUNNING
4. Job completes → Status becomes COMPLETED

### Error Cases
1. Create job without auth → 401 Unauthorized
2. Query non-existent job → 404 Not Found
3. Query another user's job → 403 Forbidden
4. Invalid state transition → State unchanged

### Edge Cases
1. Concurrent job creation → Unique IDs generated
2. Rapid status queries → Consistent state returned
3. Server restart during job → State preserved

## Definition of Done

- [ ] Job manager creates jobs with unique UUIDs
- [ ] State transitions follow defined state machine
- [ ] All job metadata is stored and retrievable
- [ ] User associations are enforced
- [ ] API endpoints return expected responses
- [ ] Unit tests achieve >90% coverage
- [ ] Integration tests verify end-to-end flow
- [ ] Performance: Job creation <50ms
- [ ] No memory leaks during extended operation
# Story 1.3: Concurrent Job Control

## Story Description

As a CIDX platform administrator, I need to control concurrent job execution with per-user limits and resource management, so that the system remains responsive and fair for all users while preventing resource exhaustion.

## Technical Specification

### Concurrency Model

```pseudocode
class ConcurrencyController:
    MAX_JOBS_PER_USER = 3
    MAX_TOTAL_JOBS = 50
    
    activeSlots: Map<userId, Set<jobId>>
    jobQueue: PriorityQueue<QueuedJob>
    resourceLimits: ResourceLimits
    
    acquireSlot(userId: string, jobId: string) -> bool
    releaseSlot(userId: string, jobId: string) -> void
    checkLimits(userId: string) -> LimitStatus
    getQueuePosition(jobId: string) -> int
    promoteQueuedJobs() -> List<string>

class QueuedJob:
    jobId: string
    userId: string
    priority: int
    queuedAt: timestamp
    estimatedStartTime: timestamp
```

### Resource Management

```pseudocode
ResourceLimits {
    maxConcurrentGitOps: 5
    maxConcurrentIndexing: 10
    maxMemoryPerJob: 512MB
    maxCPUPerJob: 2 cores
    maxJobDuration: 5 minutes
}

ResourceMonitor {
    checkSystemResources() -> ResourceStatus
    allocateJobResources(jobId) -> ResourceAllocation
    releaseJobResources(jobId) -> void
    enforceResourceLimits(jobId) -> void
}
```

## Acceptance Criteria

### Per-User Job Limits
```gherkin
Given a user has 3 active sync jobs
When the user attempts to start a 4th job
Then the job should be queued, not started immediately
And the user should receive queue position information
And the job should start when a slot becomes available
```

### Resource Slot Management
```gherkin
Given the system has resource limits configured
When a job requests execution:
  - Check user's active job count
  - Check system total job count
  - Check available system resources
Then a slot should be allocated if all limits allow
And the job should be queued if any limit is exceeded
And slots should be released when jobs complete
```

### Queue Position Tracking
```gherkin
Given multiple jobs are queued
When I query my job's queue position
Then I should receive:
  - Current position in queue (e.g., 3 of 10)
  - Estimated wait time based on average job duration
  - Number of jobs ahead by priority
And the position should update as jobs complete
```

### Priority Handling
```gherkin
Given jobs with different priority levels are queued
When a slot becomes available
Then higher priority jobs should be promoted first
And jobs with same priority should use FIFO ordering
And premium users should have higher default priority
```

### Resource Monitoring
```gherkin
Given jobs are consuming system resources
When resource usage is monitored:
  - Track memory usage per job
  - Track CPU usage per job
  - Monitor job duration
Then jobs exceeding limits should be terminated
And resources should be properly released
And system should maintain responsiveness
```

## Completion Checklist

- [ ] Per-user job limits
  - [ ] Configure max jobs per user
  - [ ] Track active jobs by user
  - [ ] Enforce limits on job creation
  - [ ] Queue excess jobs
- [ ] Resource slot management
  - [ ] Implement slot allocation
  - [ ] Atomic slot acquisition
  - [ ] Proper slot release
  - [ ] Prevent slot leaks
- [ ] Queue position tracking
  - [ ] Maintain job queue
  - [ ] Calculate queue positions
  - [ ] Estimate wait times
  - [ ] Update positions dynamically
- [ ] Priority handling
  - [ ] Priority queue implementation
  - [ ] Configurable priority levels
  - [ ] Fair scheduling algorithm
  - [ ] Premium user benefits

## Test Scenarios

### Happy Path
1. User starts job with available slot → Job runs immediately
2. User at limit starts job → Job queued with position
3. Job completes → Slot released, queued job promoted
4. High priority job queued → Jumps ahead in queue

### Error Cases
1. System at max capacity → All new jobs queued
2. Job exceeds time limit → Job terminated, slot released
3. Job exceeds memory limit → Job terminated with error
4. Slot leak detected → Automatic cleanup triggered

### Edge Cases
1. All users at limit → Fair queue ordering maintained
2. Mass job completion → Multiple promotions handled
3. Priority inversion → Prevented by algorithm
4. Resource starvation → Prevented by limits

## Performance Requirements

- Slot acquisition: <10ms
- Queue position calculation: <5ms
- Job promotion: <50ms
- Resource check interval: 1 second
- Maximum queue size: 1000 jobs

## Resource Limits Configuration

```yaml
concurrency:
  per_user:
    max_active_jobs: 3
    max_queued_jobs: 10
  system:
    max_total_jobs: 50
    max_git_operations: 5
    max_indexing_jobs: 10
  resources:
    max_memory_per_job: 512MB
    max_cpu_per_job: 2
    max_job_duration: 300s
  queue:
    max_size: 1000
    default_priority: 5
    premium_priority: 8
```

## Definition of Done

- [ ] Per-user job limits enforced
- [ ] System resource limits enforced
- [ ] Job queue with priority support
- [ ] Queue position tracking accurate
- [ ] Resource monitoring active
- [ ] Automatic cleanup of stuck jobs
- [ ] Fair scheduling algorithm
- [ ] Unit tests >90% coverage
- [ ] Load tests verify limits
- [ ] No resource leaks under load
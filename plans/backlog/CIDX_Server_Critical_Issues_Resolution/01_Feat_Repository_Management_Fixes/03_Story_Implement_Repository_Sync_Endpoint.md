# Story: Implement Repository Sync Endpoint

## User Story
As a **repository maintainer**, I want to **manually trigger repository synchronization** so that **I can update the index after making code changes without waiting for automatic sync**.

## Problem Context
The POST /api/repositories/{repo_id}/sync endpoint is missing, preventing users from manually triggering repository re-indexing. Users must rely on automatic sync or recreate repositories to update indexes.

## Acceptance Criteria

### Scenario 1: Trigger Successful Sync
```gherkin
Given I am authenticated as a repository owner
  And repository "repo-123" exists with outdated index
  And 10 files have been modified since last sync
When I send POST request to "/api/repositories/repo-123/sync"
Then the response status should be 202 Accepted
  And the response should contain sync job ID
  And the response should contain status "queued"
  And a background sync job should be created
  And the repository status should change to "syncing"
```

### Scenario 2: Sync Already in Progress
```gherkin
Given I am authenticated as a repository owner
  And repository "repo-456" is currently being synced
When I send POST request to "/api/repositories/repo-456/sync"
Then the response status should be 409 Conflict
  And the response should contain message "Sync already in progress"
  And the response should contain current sync job ID
  And the response should contain sync progress percentage
```

### Scenario 3: Force Sync with Options
```gherkin
Given I am authenticated as a repository owner
  And repository "repo-789" has a completed index
When I send POST request to "/api/repositories/repo-789/sync" with body:
  """
  {
    "force": true,
    "full_reindex": true,
    "branches": ["main", "develop"]
  }
  """
Then the response status should be 202 Accepted
  And existing index should be cleared
  And full re-indexing should start for specified branches
  And the response should contain estimated completion time
```

### Scenario 4: Incremental Sync
```gherkin
Given I am authenticated as a repository owner
  And repository "repo-inc" has 1000 indexed files
  And 5 files have been added and 3 files modified
When I send POST request to "/api/repositories/repo-inc/sync"
Then the response status should be 202 Accepted
  And only the 8 changed files should be processed
  And existing unchanged embeddings should be preserved
  And sync should complete faster than full reindex
```

### Scenario 5: Sync with Git Pull
```gherkin
Given I am authenticated as a repository owner
  And repository "repo-git" is connected to remote origin
  And remote has new commits
When I send POST request to "/api/repositories/repo-git/sync" with body:
  """
  {
    "pull_remote": true,
    "remote": "origin",
    "branch": "main"
  }
  """
Then the response status should be 202 Accepted
  And git pull should be executed first
  And new files from remote should be indexed
  And the response should contain pulled commit count
```

## Technical Implementation Details

### API Request/Response Schema

#### Request Body (Optional)
```json
{
  "force": false,
  "full_reindex": false,
  "incremental": true,
  "pull_remote": false,
  "remote": "origin",
  "branches": ["current"],
  "ignore_patterns": ["*.pyc"],
  "progress_webhook": "https://example.com/webhook"
}
```

#### Response Body
```json
{
  "job_id": "sync-job-uuid",
  "status": "queued|running|completed|failed",
  "repository_id": "repo-123",
  "created_at": "2024-01-15T10:30:00Z",
  "estimated_completion": "2024-01-15T10:35:00Z",
  "progress": {
    "percentage": 0,
    "files_processed": 0,
    "files_total": 100,
    "current_file": null
  },
  "options": {
    "force": false,
    "full_reindex": false,
    "incremental": true
  }
}
```

### Pseudocode Implementation
```
@router.post("/api/repositories/{repo_id}/sync")
async function sync_repository(
    repo_id: str,
    sync_options: SyncOptions,
    background_tasks: BackgroundTasks,
    current_user: User
):
    // Validate repository access
    repository = await repository_service.get_by_id(repo_id)
    if not repository:
        raise HTTPException(404, "Repository not found")
    
    if not has_write_access(current_user, repository):
        raise HTTPException(403, "Access denied")
    
    // Check for existing sync job
    existing_job = await get_active_sync_job(repo_id)
    if existing_job and not sync_options.force:
        return JSONResponse(
            status_code=409,
            content={
                "error": "Sync already in progress",
                "job_id": existing_job.id,
                "progress": existing_job.progress
            }
        )
    
    // Cancel existing job if force flag set
    if existing_job and sync_options.force:
        await cancel_sync_job(existing_job.id)
    
    // Create sync job
    job = create_sync_job(repository, sync_options, current_user)
    
    // Queue background task
    background_tasks.add_task(
        execute_sync_job,
        job_id=job.id,
        repository=repository,
        options=sync_options
    )
    
    // Return accepted response
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job.id,
            "status": "queued",
            "repository_id": repo_id,
            "created_at": job.created_at,
            "estimated_completion": estimate_completion_time(repository, sync_options),
            "progress": {
                "percentage": 0,
                "files_processed": 0,
                "files_total": await count_files_to_sync(repository, sync_options),
                "current_file": None
            },
            "options": sync_options.dict()
        }
    )

async function execute_sync_job(job_id: str, repository: Repository, options: SyncOptions):
    try:
        // Update job status
        await update_job_status(job_id, "running")
        
        // Pull from remote if requested
        if options.pull_remote:
            await git_pull(repository.path, options.remote, options.branches)
        
        // Determine sync strategy
        if options.full_reindex:
            await full_reindex(repository, job_id, options)
        elif options.incremental:
            await incremental_sync(repository, job_id, options)
        else:
            await smart_sync(repository, job_id, options)
        
        // Update job status
        await update_job_status(job_id, "completed")
        
        // Trigger webhook if configured
        if options.progress_webhook:
            await notify_webhook(options.progress_webhook, job_id, "completed")
            
    except Exception as e:
        await update_job_status(job_id, "failed", error=str(e))
        logger.error(f"Sync job {job_id} failed", exc_info=e)
        raise

async function incremental_sync(repository: Repository, job_id: str, options: SyncOptions):
    // Get list of changed files
    changed_files = await detect_changed_files(repository)
    
    total_files = len(changed_files)
    processed = 0
    
    for file_path in changed_files:
        // Process file
        await process_file(repository, file_path)
        
        // Update progress
        processed += 1
        progress = (processed / total_files) * 100
        await update_job_progress(job_id, progress, processed, total_files, file_path)
        
        // Check for cancellation
        if await is_job_cancelled(job_id):
            break
```

## Testing Requirements

### Unit Tests
- [ ] Test sync job creation
- [ ] Test conflict detection for concurrent syncs
- [ ] Test force sync cancellation logic
- [ ] Test incremental vs full reindex logic
- [ ] Test progress calculation

### Integration Tests
- [ ] Test with real git repository
- [ ] Test with background task execution
- [ ] Test webhook notifications
- [ ] Test job cancellation during sync

### E2E Tests
- [ ] Test complete sync workflow
- [ ] Test sync with large repository
- [ ] Test concurrent sync attempts
- [ ] Test sync progress tracking

## Definition of Done
- [x] POST /api/repositories/{repo_id}/sync endpoint implemented
- [x] Returns 202 Accepted with job details
- [x] Background sync job executes successfully
- [x] Incremental sync optimizes for changed files only
- [x] Force flag allows cancelling existing sync
- [x] Progress tracking updates in real-time
- [x] Unit test coverage > 90%
- [x] Integration tests pass
- [x] E2E tests pass
- [x] API documentation updated
- [x] Manual test case created and passes

## Performance Criteria
- Sync initiation response time < 500ms
- Incremental sync 10x faster than full reindex
- Support repositories up to 100,000 files
- Progress updates every 1 second minimum
- Concurrent sync support for different repositories

## Monitoring Requirements
- Log sync job creation and completion
- Track sync duration metrics
- Monitor sync failure rates
- Alert on stuck sync jobs (> 1 hour)
- Track incremental vs full sync ratio
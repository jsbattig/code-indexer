# Story: Fix Repository Deletion Error

## User Story
As a **repository owner**, I want to **delete repositories without errors** so that **I can cleanly remove unwanted repositories and free up system resources**.

## Problem Context
Repository deletion currently fails with HTTP 500 "Internal Server Error" and logs show "broken pipe" errors. This prevents users from managing their repository lifecycle and causes resource leaks.

### Current Error Behavior
```
DELETE /api/repositories/{repo_id}
Response: 500 Internal Server Error
Logs: BrokenPipeError: [Errno 32] Broken pipe
```

## Acceptance Criteria

### Scenario 1: Successful Repository Deletion
```gherkin
Given I am authenticated as a user with a repository
  And the repository exists with ID "test-repo-123"
  And the repository has indexed files and embeddings
When I send DELETE request to "/api/repositories/test-repo-123"
Then the response status should be 204 No Content
  And the repository should not exist in the database
  And the repository files should be removed from disk
  And the Qdrant collection should be deleted
  And no error logs should be generated
```

### Scenario 2: Delete Non-Existent Repository
```gherkin
Given I am authenticated as a user
  And no repository exists with ID "non-existent-repo"
When I send DELETE request to "/api/repositories/non-existent-repo"
Then the response status should be 404 Not Found
  And the response should contain error message "Repository not found"
```

### Scenario 3: Delete Repository with Active Connections
```gherkin
Given I am authenticated as a user with a repository
  And the repository has an active indexing job running
When I send DELETE request to the repository
Then the indexing job should be cancelled gracefully
  And the repository should be marked for deletion
  And deletion should complete after job cancellation
  And the response status should be 204 No Content
```

### Scenario 4: Handle Partial Deletion Failure
```gherkin
Given I am authenticated as a user with a repository
  And the Qdrant service is temporarily unavailable
When I send DELETE request to the repository
Then the database record should be rolled back
  And the file system should not be modified
  And the response status should be 503 Service Unavailable
  And the response should contain error message about service availability
  And the repository should remain fully functional
```

### Scenario 5: Concurrent Deletion Attempts
```gherkin
Given I am authenticated as a user with a repository
  And another user is simultaneously trying to delete the same repository
When both DELETE requests are sent concurrently
Then only one deletion should succeed with 204 No Content
  And the other should receive 404 Not Found or 409 Conflict
  And no partial deletions should occur
  And no resource leaks should occur
```

## Technical Implementation Details

### Pseudocode for Fix
```
function delete_repository(repo_id, user_id):
    transaction = begin_database_transaction()
    try:
        // Verify ownership and existence
        repository = get_repository_with_lock(repo_id, user_id)
        if not repository:
            return 404, "Repository not found"
        
        // Cancel any active jobs
        cancel_active_jobs(repo_id)
        
        // Mark repository as deleting
        repository.status = "deleting"
        transaction.save(repository)
        
        // Delete in correct order
        try:
            // 1. Delete Qdrant collection
            delete_qdrant_collection(repository.collection_name)
        catch QdrantError as e:
            transaction.rollback()
            return 503, "Vector database unavailable"
        
        try:
            // 2. Delete file system data
            delete_repository_files(repository.path)
        catch FileSystemError as e:
            transaction.rollback()
            restore_qdrant_collection(repository.collection_name)
            return 500, "Failed to delete repository files"
        
        // 3. Delete database record
        transaction.delete(repository)
        transaction.commit()
        
        return 204, None
        
    catch Exception as e:
        transaction.rollback()
        log_error("Repository deletion failed", repo_id, e)
        return 500, "Internal server error"
    finally:
        // Ensure all resources are cleaned up
        close_all_connections(repo_id)
        release_locks(repo_id)
```

### Resource Cleanup Implementation
```
function cleanup_repository_resources(repo_id):
    resources_to_cleanup = [
        close_file_handles,
        close_database_connections,
        cancel_background_tasks,
        clear_cache_entries,
        release_file_locks
    ]
    
    for cleanup_func in resources_to_cleanup:
        try:
            cleanup_func(repo_id)
        catch Exception as e:
            log_warning(f"Failed to cleanup {cleanup_func.__name__}", e)
            // Continue with other cleanups
```

## Testing Requirements

### Unit Tests
- [ ] Test transaction rollback on Qdrant failure
- [ ] Test transaction rollback on file system failure
- [ ] Test proper resource cleanup in finally block
- [ ] Test concurrent deletion handling
- [ ] Test job cancellation logic

### Integration Tests
- [ ] Test full deletion flow with real database
- [ ] Test deletion with active Qdrant connections
- [ ] Test deletion of large repository (>1000 files)
- [ ] Test deletion during active indexing

### E2E Tests
- [ ] Execute manual test case TC_REPO_004
- [ ] Test deletion through UI workflow
- [ ] Test deletion through CLI command
- [ ] Test deletion impact on shared resources

## Definition of Done
- [x] DELETE endpoint returns 204 on success
- [x] No "broken pipe" errors in logs
- [x] All resources properly cleaned up
- [x] Database transactions properly managed
- [x] Manual test TC_REPO_004 passes
- [x] Unit test coverage > 90%
- [x] Integration tests pass
- [x] E2E tests pass
- [x] No memory leaks detected
- [x] Documentation updated

## Performance Criteria
- Deletion completes in < 5 seconds for standard repositories
- No timeout errors for repositories up to 10,000 files
- Memory usage remains stable during deletion
- CPU usage < 50% during deletion operation

## Error Handling Matrix
| Error Condition | HTTP Status | User Message | System Action |
|----------------|-------------|--------------|---------------|
| Repository not found | 404 | "Repository not found" | Log warning |
| Not authorized | 403 | "Not authorized to delete" | Log security event |
| Qdrant unavailable | 503 | "Service temporarily unavailable" | Rollback, retry queue |
| File system error | 500 | "Failed to delete repository" | Rollback, alert admin |
| Concurrent deletion | 409 | "Repository operation in progress" | Return immediately |
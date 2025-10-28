# Story: Implement Repository Details Endpoint

## User Story
As a **repository user**, I want to **retrieve detailed information about a specific repository** so that **I can view its configuration, status, and indexing metrics**.

## Problem Context
The GET /api/repositories/{repo_id} endpoint is currently missing, preventing users from retrieving detailed information about specific repositories. This is a fundamental CRUD operation that should be available.

## Acceptance Criteria

### Scenario 1: Retrieve Existing Repository Details
```gherkin
Given I am authenticated as a user
  And I have access to repository with ID "repo-123"
  And the repository has been indexed with 500 files
When I send GET request to "/api/repositories/repo-123"
Then the response status should be 200 OK
  And the response should contain repository name
  And the response should contain repository path
  And the response should contain creation timestamp
  And the response should contain last sync timestamp
  And the response should contain file count of 500
  And the response should contain index status
  And the response should contain repository size in bytes
  And the response should contain current branch information
```

### Scenario 2: Retrieve Non-Existent Repository
```gherkin
Given I am authenticated as a user
When I send GET request to "/api/repositories/non-existent-id"
Then the response status should be 404 Not Found
  And the response should contain error message "Repository not found"
```

### Scenario 3: Unauthorized Repository Access
```gherkin
Given I am authenticated as user "alice"
  And repository "repo-456" is owned by user "bob"
  And I do not have read permissions for "repo-456"
When I send GET request to "/api/repositories/repo-456"
Then the response status should be 403 Forbidden
  And the response should contain error message "Access denied"
```

### Scenario 4: Repository with Active Indexing
```gherkin
Given I am authenticated as a user
  And repository "repo-789" is currently being indexed
  And indexing is 45% complete
When I send GET request to "/api/repositories/repo-789"
Then the response status should be 200 OK
  And the response should contain indexing status "in_progress"
  And the response should contain indexing progress of 45
  And the response should contain estimated completion time
```

### Scenario 5: Repository with Multiple Branches
```gherkin
Given I am authenticated as a user
  And repository "repo-multi" has branches ["main", "develop", "feature-x"]
  And current branch is "develop"
When I send GET request to "/api/repositories/repo-multi"
Then the response status should be 200 OK
  And the response should contain all branch names
  And the response should indicate "develop" as current branch
  And the response should contain index status for each branch
```

## Technical Implementation Details

### API Response Schema
```json
{
  "id": "string",
  "name": "string",
  "path": "string",
  "owner_id": "string",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T14:45:00Z",
  "last_sync_at": "2024-01-15T14:45:00Z",
  "status": "indexed|indexing|error|pending",
  "indexing_progress": 0-100,
  "statistics": {
    "total_files": 500,
    "indexed_files": 500,
    "total_size_bytes": 10485760,
    "embeddings_count": 1500,
    "languages": ["python", "javascript", "markdown"]
  },
  "git_info": {
    "current_branch": "main",
    "branches": ["main", "develop", "feature-x"],
    "last_commit": "abc123def",
    "remote_url": "https://github.com/user/repo.git"
  },
  "configuration": {
    "ignore_patterns": ["*.pyc", "__pycache__"],
    "chunk_size": 1000,
    "overlap": 200,
    "embedding_model": "text-embedding-3-small"
  },
  "errors": []
}
```

### Pseudocode Implementation
```
@router.get("/api/repositories/{repo_id}")
async function get_repository_details(repo_id: str, current_user: User):
    // Validate repository exists
    repository = await repository_service.get_by_id(repo_id)
    if not repository:
        raise HTTPException(404, "Repository not found")
    
    // Check access permissions
    if not has_read_access(current_user, repository):
        raise HTTPException(403, "Access denied")
    
    // Gather repository statistics
    stats = await gather_repository_stats(repository)
    
    // Get git information
    git_info = await get_git_info(repository.path)
    
    // Check indexing status
    indexing_status = await get_indexing_status(repo_id)
    
    // Build response
    response = {
        "id": repository.id,
        "name": repository.name,
        "path": repository.path,
        "owner_id": repository.owner_id,
        "created_at": repository.created_at,
        "updated_at": repository.updated_at,
        "last_sync_at": repository.last_sync_at,
        "status": indexing_status.status,
        "indexing_progress": indexing_status.progress,
        "statistics": stats,
        "git_info": git_info,
        "configuration": repository.configuration,
        "errors": repository.errors or []
    }
    
    return response

async function gather_repository_stats(repository):
    // Query database for file counts
    file_count = await db.query(
        "SELECT COUNT(*) FROM files WHERE repo_id = ?",
        repository.id
    )
    
    // Query Qdrant for embedding counts
    embedding_count = await qdrant.count(repository.collection_name)
    
    // Calculate repository size
    total_size = await calculate_directory_size(repository.path)
    
    // Detect languages
    languages = await detect_languages(repository.id)
    
    return {
        "total_files": file_count,
        "indexed_files": repository.indexed_files,
        "total_size_bytes": total_size,
        "embeddings_count": embedding_count,
        "languages": languages
    }
```

## Testing Requirements

### Unit Tests
- [ ] Test successful repository detail retrieval
- [ ] Test 404 response for non-existent repository
- [ ] Test 403 response for unauthorized access
- [ ] Test statistics calculation logic
- [ ] Test git information extraction

### Integration Tests
- [ ] Test with real database queries
- [ ] Test with Qdrant collection queries
- [ ] Test with file system operations
- [ ] Test with concurrent requests

### E2E Tests
- [ ] Test through API client
- [ ] Test response time under load
- [ ] Test with repositories of various sizes
- [ ] Test during active indexing

## Definition of Done
- [x] GET /api/repositories/{repo_id} endpoint implemented
- [x] Returns 200 with complete repository details
- [x] Returns 404 for non-existent repositories
- [x] Returns 403 for unauthorized access
- [x] Response time < 200ms for standard queries
- [x] All statistics accurately calculated
- [x] Unit test coverage > 90%
- [x] Integration tests pass
- [x] API documentation updated
- [x] Manual test case created and passes

## Performance Criteria
- Response time < 200ms for repositories under 1000 files
- Response time < 500ms for repositories under 10000 files
- Concurrent request handling without degradation
- Efficient database queries with proper indexing

## Security Considerations
- Validate user has read access to repository
- Do not expose sensitive file paths to unauthorized users
- Sanitize repository paths in responses
- Log access attempts for audit trail
# Story: Implement Missing Endpoints

## User Story
As an **API user**, I want **access to all documented API endpoints** so that **I can fully utilize the CIDX server capabilities**.

## Problem Context
Several critical endpoints are documented but not implemented, limiting the functionality available through the API. Users resort to workarounds or direct database access.

## Acceptance Criteria

### Scenario 1: Repository Statistics Endpoint
```gherkin
Given I have a repository with indexed content
When I send GET request to "/api/repositories/{repo_id}/stats"
Then the response should include:
  - Total file count
  - Indexed file count
  - Total repository size
  - Embedding count
  - Language distribution
  - Last sync timestamp
  - Index health score
```

### Scenario 2: File Listing Endpoint
```gherkin
Given I have a repository with files
When I send GET request to "/api/repositories/{repo_id}/files"
  With query parameters for pagination and filtering
Then the response should return paginated file list
  And support filtering by path pattern
  And support filtering by language
  And include file metadata (size, modified date)
```

### Scenario 3: Semantic Search Endpoint
```gherkin
Given I have an indexed repository
When I send POST request to "/api/repositories/{repo_id}/search"
  With query "authentication logic"
Then the response should return relevant code snippets
  And results should be ranked by relevance
  And include file path and line numbers
  And support result limit parameter
```

### Scenario 4: Health Check Endpoint
```gherkin
Given the CIDX server is running
When I send GET request to "/api/system/health"
Then the response should include:
  - Server status (healthy/degraded/unhealthy)
  - Database connectivity status
  - Qdrant connectivity status
  - Disk space availability
  - Memory usage
  - Active job count
```

## Technical Implementation Details

### Repository Statistics Implementation
```
@router.get("/api/repositories/{repo_id}/stats")
async function get_repository_stats(
    repo_id: str,
    current_user: User = Depends(get_current_user)
):
    repository = await get_repository_with_access_check(repo_id, current_user)
    
    stats = {
        "repository_id": repo_id,
        "files": {
            "total": await count_total_files(repository.path),
            "indexed": await count_indexed_files(repo_id),
            "by_language": await get_language_distribution(repo_id)
        },
        "storage": {
            "repository_size_bytes": get_directory_size(repository.path),
            "index_size_bytes": await get_index_size(repo_id),
            "embedding_count": await get_embedding_count(repo_id)
        },
        "activity": {
            "created_at": repository.created_at,
            "last_sync_at": repository.last_sync_at,
            "last_accessed_at": repository.last_accessed_at,
            "sync_count": repository.sync_count
        },
        "health": {
            "score": calculate_health_score(repository),
            "issues": detect_health_issues(repository)
        }
    }
    
    return stats
```

### Semantic Search Implementation
```
@router.post("/api/repositories/{repo_id}/search")
async function semantic_search(
    repo_id: str,
    search_request: SearchRequest,
    current_user: User = Depends(get_current_user)
):
    repository = await get_repository_with_access_check(repo_id, current_user)
    
    // Get embeddings for query
    query_embedding = await generate_embedding(search_request.query)
    
    // Search in Qdrant
    results = await qdrant_client.search(
        collection_name=repository.collection_name,
        query_vector=query_embedding,
        limit=search_request.limit or 10,
        with_payload=True
    )
    
    // Format results
    formatted_results = []
    for result in results:
        formatted_results.append({
            "score": result.score,
            "file_path": result.payload["file_path"],
            "line_start": result.payload["line_start"],
            "line_end": result.payload["line_end"],
            "content": result.payload["content"],
            "language": result.payload["language"]
        })
    
    return {
        "query": search_request.query,
        "results": formatted_results,
        "total": len(formatted_results)
    }
```

## Definition of Done
- [ ] All missing endpoints implemented
- [ ] Endpoints follow REST conventions
- [ ] Request/response schemas defined
- [ ] Input validation complete
- [ ] Error handling consistent
- [ ] Performance optimized
- [ ] Unit tests written
- [ ] Integration tests pass
- [ ] API documentation updated
- [ ] Manual testing complete
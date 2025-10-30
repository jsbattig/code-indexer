# Story: Temporal Query Parameters via API

## Story Overview

**User Story:**
As a developer or AI agent querying via API
I want to use temporal parameters in semantic search requests
So that I can find code from specific time periods or commits programmatically

**Conversation Context:**
- User requirement: "make sure we have user story(ies) to add support to the API server, to register a golden repo with the temporary git index"
- User correction: "don't have a max, let the user decide how many results" - Applied to evolution_limit

**Success Criteria:**
- `/api/query` endpoint accepts temporal query parameters
- Internal service calls provide performance
- Graceful fallback when temporal index missing
- User-controlled limits with no arbitrary maximums

## Acceptance Criteria

### API Integration
- [ ] POST `/api/query` accepts temporal parameters: `time_range`, `at_commit`, `include_removed`, `show_evolution`, `evolution_limit`
- [ ] Time-range filtering: `time_range: "2023-01-01..2024-01-01"` returns only code from that period
- [ ] Point-in-time query: `at_commit: "abc123"` returns code state at that specific commit
- [ ] Include removed: `include_removed: true` includes deleted code in results
- [ ] Evolution display: `show_evolution: true` includes commit history and diffs in response
- [ ] Evolution limit: `evolution_limit: 5` limits evolution entries (user-controlled, NO arbitrary max)

### Response Enhancement
- [ ] Response includes temporal metadata: `first_seen`, `last_seen`, `commit_count`, `commits` array
- [ ] Uses internal service calls to `TemporalSearchService` (NOT subprocess - follows SemanticSearchService pattern)
- [ ] Graceful fallback: If temporal index missing, returns current code with warning in response metadata
- [ ] Error handling: Clear messages for invalid date formats, unknown commits, missing indexes
- [ ] Performance: <500ms query time for temporal queries on 40K+ commit repos

## Technical Implementation

### Integration Point
`SemanticSearchService.search_repository_path()`

### Model Extension
```python
class SemanticSearchRequest(BaseModel):
    query: str
    limit: int = 10
    include_source: bool = False

    # Temporal parameters
    time_range: Optional[str] = Field(None, description="Time range filter (e.g., '2024-01-01..2024-12-31')")
    at_commit: Optional[str] = Field(None, description="Query at specific commit hash or ref")
    include_removed: bool = Field(False, description="Include files removed from current HEAD")
    show_evolution: bool = Field(False, description="Show code evolution timeline with diffs")
    evolution_limit: Optional[int] = Field(None, ge=1, description="Limit evolution entries (user-controlled)")

class SearchResultItem(BaseModel):
    file_path: str
    score: float
    code_snippet: str
    language: Optional[str] = None

    # Temporal context (if temporal query)
    temporal_context: Optional[TemporalContext] = None

class TemporalContext(BaseModel):
    first_seen: str  # ISO date
    last_seen: str   # ISO date
    appearance_count: int
    is_removed: Optional[bool] = None
    commits: List[CommitInfo]
    evolution: Optional[List[EvolutionEntry]] = None  # If show_evolution=true
```

### Query Execution (Internal Service Calls)
```python
# In SemanticSearchService.search_repository_path()
def search_repository_path(self, repo_path: str, search_request: SemanticSearchRequest):
    # Load repository-specific configuration
    config_manager = ConfigManager.create_with_backtrack(Path(repo_path))
    config = config_manager.get_config()

    # Check for temporal parameters
    has_temporal_params = any([
        search_request.time_range,
        search_request.at_commit,
        search_request.show_evolution
    ])

    if has_temporal_params:
        # Validate temporal index exists
        temporal_db = Path(repo_path) / ".code-indexer/index/temporal/commits.db"

        if not temporal_db.exists():
            # Graceful fallback - perform regular search with warning
            logger.warning(f"Temporal index not found for {repo_path}, falling back to regular search")
            regular_results = self._perform_semantic_search(repo_path, search_request.query,
                                                           search_request.limit, search_request.include_source)
            return SemanticSearchResponse(
                query=search_request.query,
                results=regular_results,
                total=len(regular_results),
                warning="Temporal index not available. Showing results from current code only. "
                        "Build temporal index with 'cidx index --index-commits' to enable temporal queries."
            )

        # Use internal service calls to TemporalSearchService
        from ...services.temporal_search_service import TemporalSearchService
        from ...services.vector_store_factory import VectorStoreFactory

        # Create vector store instance
        vector_store = VectorStoreFactory.create(config)

        # Create temporal service
        temporal_service = TemporalSearchService(config_manager, vector_store)

        # Execute temporal query...
```

## Manual Test Plan

### Test Case 1: Time-Range Query
1. Execute time-range query:
   ```bash
   curl -X POST http://localhost:8000/api/query \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "query": "authentication function",
       "repository_alias": "test-repo",
       "time_range": "2023-01-01..2024-01-01",
       "limit": 10
     }'
   ```
2. Verify: Results only include code that existed during 2023
3. Check temporal_context includes first_seen/last_seen dates
4. Confirm dates fall within specified range

### Test Case 2: Point-in-Time Query
1. Execute point-in-time query:
   ```bash
   curl -X POST http://localhost:8000/api/query \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "query": "login handler",
       "repository_alias": "test-repo",
       "at_commit": "abc123",
       "limit": 10
     }'
   ```
2. Verify: Results show code state at commit abc123
3. Check temporal_metadata shows query_type: "point_in_time"
4. Confirm no results from commits after abc123

### Test Case 3: Include Removed Code
1. Execute query with removed code:
   ```bash
   curl -X POST http://localhost:8000/api/query \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "query": "deprecated function",
       "repository_alias": "test-repo",
       "time_range": "2020-01-01..2025-01-01",
       "include_removed": true,
       "limit": 10
     }'
   ```
2. Verify: Results include deleted code with `is_removed: true`
3. Check file_path shows files no longer in HEAD
4. Confirm last_seen date before current date

### Test Case 4: Evolution Display
1. Execute query with evolution:
   ```bash
   curl -X POST http://localhost:8000/api/query \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "query": "user authentication",
       "repository_alias": "test-repo",
       "show_evolution": true,
       "evolution_limit": 5,
       "limit": 5
     }'
   ```
2. Verify: Response includes evolution timeline
3. Check evolution entries ≤ 5 (user-controlled limit)
4. Confirm diffs show code changes over time

### Test Case 5: Missing Temporal Index (Graceful Fallback)
1. Query repository without temporal index
2. Verify: Returns current code results
3. Check warning message present
4. Confirm suggestion to build temporal index

### Test Case 6: Error Cases
1. Invalid date format: `time_range: "2023-1-1..2024-1-1"`
   - Verify: HTTP 400 with format example
2. Invalid range separator: `time_range: "2023-01-01-2024-01-01"`
   - Verify: HTTP 400 with correct format
3. Unknown commit: `at_commit: "nonexistent"`
   - Verify: HTTP 404 with helpful message
4. End date before start: `time_range: "2024-01-01..2023-01-01"`
   - Verify: HTTP 400 with validation error

## Error Scenarios

### Input Validation
- Invalid date format → HTTP 400 with clear validation message
- Unknown commit → HTTP 404 with suggestion to check commit hash
- Malformed time_range → HTTP 400 with format example
- End date before start date → HTTP 400 validation error

### Runtime Handling
- Missing temporal index → HTTP 200 with warning, returns current code
- SQLite database locked → Retry with exponential backoff
- Large evolution data → User controls via evolution_limit

### Recovery
- Graceful fallback always available
- Clear error messages guide resolution
- No silent failures

## Performance Considerations

### Optimization Strategies
- Use internal service calls (NOT subprocess) for query performance
- SQLite WAL mode handles concurrent reads automatically
- FilesystemVectorStore reuses existing vectors via blob deduplication
- Evolution limit user-controlled to manage response payload size

### Performance Targets
- Semantic search: ~200ms
- Temporal filtering: ~50ms
- Total target: <500ms for 40K+ repos

## Dependencies

### Required Components
- Story 1 of Feature 04 must complete first (temporal index must exist)
- CLI `TemporalSearchService` implementation (Features 01-03)
- Existing `SemanticSearchService` architecture
- `ConfigManager`, `FilesystemVectorStore`, `EmbeddingProviderFactory`

### Configuration
- Repository-specific config in `.code-indexer/config.json`
- Temporal index in `.code-indexer/index/temporal/`

## Implementation Order

1. Extend API models with temporal fields
2. Implement temporal parameter detection
3. Add graceful fallback logic
4. Integrate TemporalSearchService calls
5. Format temporal response data
6. Add error handling
7. Performance testing
8. Documentation update

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Performance impact | High | Internal service calls, SQLite optimization |
| Large payloads | Medium | User-controlled evolution_limit |
| Complex queries | Low | Clear documentation and examples |

## Notes

**Critical Design Decisions:**
- Internal service calls for performance (not subprocess)
- User-controlled limits (no arbitrary maximums per conversation)
- Graceful degradation is mandatory
- SQLite handles concurrency automatically (no explicit locking)

**Conversation Citation:**
- User requirement: API temporal support following FTS pattern
- User correction: "don't have a max, let the user decide how many results"
- This applies to evolution_limit parameter
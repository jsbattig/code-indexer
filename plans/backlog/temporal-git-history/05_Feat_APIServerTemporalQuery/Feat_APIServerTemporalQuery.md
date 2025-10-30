# Feature: API Server Temporal Query Support

## Feature Overview

**Problem Statement:**
API users cannot leverage temporal search capabilities. Need to extend `/api/query` endpoint to support temporal query parameters, following the pattern established by SemanticSearchService for internal service calls.

**Conversation Context:**
User requirement: "make sure we have user story(ies) to add support to the API server, to register a golden repo with the temporary git index. we recently added support for fts index, to CLI and to the API server, this should follow a similar pattern."

**Target Users:**
- Developers querying via API
- AI coding agents requiring historical code context
- Teams analyzing code evolution programmatically

**Success Criteria:**
- `/api/query` endpoint supports temporal parameters
- Time-range and point-in-time queries work via API
- Evolution data available in API responses
- Performance <500ms for temporal queries
- Graceful fallback when temporal index missing

## Stories

### 01_Story_TemporalQueryParametersViaAPI
**Purpose:** Enable temporal search via API with time-range, point-in-time, and evolution queries
**Description:** As a developer or AI agent querying via API, I want to use temporal parameters in semantic search requests, so that I can find code from specific time periods or commits programmatically.

## Technical Architecture

### Integration Pattern

**Key Architecture Decision:**
- Use INTERNAL service calls to `TemporalSearchService` (NOT subprocess)
- Follows `SemanticSearchService` pattern for performance
- Direct service integration, not CLI invocation

### API Model Extensions

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

class TemporalContext(BaseModel):
    first_seen: str  # ISO date
    last_seen: str   # ISO date
    appearance_count: int
    is_removed: Optional[bool] = None
    commits: List[CommitInfo]
    evolution: Optional[List[EvolutionEntry]] = None  # If show_evolution=true
```

### Query Flow Architecture

**Integration Point:** `SemanticSearchService.search_repository_path()`

**Query Execution Flow:**
1. Check for temporal parameters in request
2. Validate temporal index exists (graceful fallback if missing)
3. Create `TemporalSearchService` instance with internal calls
4. Execute temporal query with filters
5. Add evolution data if requested
6. Format response with temporal metadata

**Critical Design Decisions:**
- Internal service calls for performance (no subprocess)
- User-controlled evolution_limit (NO arbitrary max)
- Graceful fallback to regular search with warning
- SQLite WAL mode handles concurrency automatically

## Implementation Guidelines

### Critical Requirements

1. **Internal Service Pattern:**
   - Use `TemporalSearchService` directly
   - No subprocess calls for queries
   - Follow `SemanticSearchService` architecture

2. **User Control:**
   - Evolution limit completely user-defined
   - No arbitrary maximums
   - All temporal parameters optional

3. **Graceful Degradation:**
   - Missing temporal index → regular search + warning
   - Clear error messages for invalid parameters
   - Never fail silently

4. **Performance:**
   - <500ms query time target
   - Reuse existing vectors via blob dedup
   - SQLite optimizations for concurrent reads

### Response Format

```json
{
  "query": "authentication function",
  "results": [
    {
      "file_path": "src/auth/login.py",
      "score": 0.89,
      "code_snippet": "def authenticate_user(username, password):",
      "language": "python",
      "temporal_context": {
        "first_seen": "2023-01-15T10:30:00Z",
        "last_seen": "2024-06-20T14:45:00Z",
        "appearance_count": 45,
        "is_removed": false,
        "commits": [
          {
            "hash": "abc123",
            "date": "2024-06-20T14:45:00Z",
            "message": "Refactor authentication logic",
            "author": "John Doe"
          }
        ],
        "evolution": [
          {
            "commit_hash": "def456",
            "commit_date": "2023-01-15T10:30:00Z",
            "author": "Jane Smith",
            "message": "Initial authentication implementation",
            "diff": "@@ -0,0 +1,15 @@\n+def authenticate_user..."
          }
        ]
      }
    }
  ],
  "total": 10,
  "temporal_metadata": {
    "query_type": "time_range",
    "time_range": ["2023-01-01", "2024-12-31"],
    "temporal_index_available": true
  },
  "warning": null
}
```

## Acceptance Criteria

### Functional Requirements
- [ ] POST `/api/query` accepts temporal parameters
- [ ] Time-range filtering works correctly
- [ ] Point-in-time queries return historical state
- [ ] Include_removed shows deleted code
- [ ] Evolution data includes diffs when requested
- [ ] Graceful fallback with warning when index missing

### Quality Requirements
- [ ] Performance <500ms for temporal queries
- [ ] Clear error messages for invalid inputs
- [ ] No arbitrary limits on evolution entries
- [ ] Backward compatible (existing queries unchanged)

## Testing Strategy

### Manual Test Scenarios
1. Time-range query and verify date filtering
2. Point-in-time query at specific commit
3. Query with include_removed for deleted code
4. Evolution display with configurable limit
5. Missing temporal index graceful fallback
6. Invalid parameter error handling

### Error Scenarios
- Invalid date format → HTTP 400
- Unknown commit → HTTP 404
- Missing temporal index → HTTP 200 with warning
- Malformed time_range → HTTP 400

## Dependencies

- Feature 04 Story 1 (temporal index must exist)
- CLI `TemporalSearchService` implementation
- Existing `SemanticSearchService` architecture
- `ConfigManager`, `FilesystemVectorStore`

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Performance degradation | High | Internal service calls, SQLite optimization |
| Large response payloads | Medium | User-controlled evolution_limit |
| Missing temporal index | Low | Graceful fallback with warning |

## Success Metrics

- Temporal queries work via API
- Performance within target (<500ms)
- Clear documentation and error messages
- User adoption for historical analysis

## Notes

**Conversation Citations:**
- User requirement for API temporal support
- Follow FTS pattern for API integration
- User correction: "don't have a max, let the user decide how many results"

**Architecture Decision:**
- Query operations use internal service calls (performance)
- Registration uses subprocess (consistency)
- This hybrid approach optimizes for each use case
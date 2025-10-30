# Feature: API Server Temporal Registration

## Feature Overview

**Problem Statement:**
Missing API server integration for temporal git history indexing during golden repo registration. Feature gap between CLI and server deployments requires parity following FTS integration pattern established in codebase.

**Conversation Context:**
User requirement: "make sure we have user story(ies) to add support to the API server, to register a golden repo with the temporary git index. we recently added support for fts index, to CLI and to the API server, this should follow a similar pattern."

**Target Users:**
- API server administrators registering golden repositories
- Multi-user CIDX server deployments
- AI coding agents requiring temporal search capabilities via API

**Success Criteria:**
- API endpoints support registering golden repos with `enable_temporal` configuration
- Golden repo registration workflow runs temporal indexing conditionally
- Configuration persists temporal settings for golden repos
- Feature parity with CLI temporal capabilities
- Temporal options (max_commits, since_date) configurable via API

## Stories

### 01_Story_GoldenRepoRegistrationWithTemporal
**Purpose:** Enable golden repository registration with temporal indexing via API
**Description:** As a CIDX server administrator, I want to register golden repositories with temporal indexing enabled via API, so that users can query code history across time without manual CLI indexing.

## Technical Architecture

### Integration Points

**GoldenRepoManager Integration:**
- Modify `_execute_post_clone_workflow()` to accept temporal parameters
- Add temporal indexing step after standard indexing
- Follow subprocess workflow pattern (consistency with FTS)

**API Model Extensions:**
```python
class AddGoldenRepoRequest(BaseModel):
    repo_url: str
    alias: str
    default_branch: str = "main"
    description: Optional[str] = None
    enable_temporal: bool = Field(default=False, description="Enable temporal git history indexing")
    temporal_options: Optional[TemporalIndexOptions] = None

class TemporalIndexOptions(BaseModel):
    max_commits: Optional[int] = Field(default=None, description="Limit commits to index (None = all)")
    since_date: Optional[str] = Field(default=None, description="Index commits since date (ISO format YYYY-MM-DD)")
```

### Workflow Architecture

**Registration Flow:**
1. POST `/api/admin/golden-repos` with temporal parameters
2. Clone repository (existing flow)
3. Execute post-clone workflow:
   - `cidx init --embedding-provider voyage-ai`
   - `cidx start --force-docker`
   - `cidx status --force-docker`
   - `cidx index` (standard indexing)
   - `cidx index --index-commits [options]` (if temporal enabled)
   - `cidx stop --force-docker`
4. Persist temporal configuration in metadata
5. Return job ID for async monitoring

**Critical Design Decisions:**
- NO timeout specifications (background job manager handles duration naturally)
- Subprocess pattern for consistency with existing workflow
- Temporal indexing conditional on flag
- Graceful failure handling with clear error messages

### Configuration Persistence

**Golden Repo Metadata** (`~/.cidx-server/data/golden-repos/{alias}/metadata.json`):
```json
{
  "alias": "my-repo",
  "repo_url": "https://github.com/example/repo.git",
  "default_branch": "main",
  "enable_temporal": true,
  "temporal_options": {
    "max_commits": null,
    "since_date": null
  },
  "last_indexed_commit": "abc123def",
  "temporal_index_status": "completed"
}
```

## Implementation Guidelines

### Critical Requirements

1. **Follow FTS Pattern:**
   - Use subprocess workflow for indexing
   - Async background job execution
   - Job status monitoring via API

2. **Configuration Management:**
   - Persist temporal settings in metadata
   - Support both new and refresh operations
   - Maintain backward compatibility

3. **Error Handling:**
   - Graceful failure if temporal indexing fails
   - Clear error messages in job results
   - No silent failures

4. **No Arbitrary Limits:**
   - NO timeout specifications
   - User controls max_commits and since_date
   - Index all commits by default

### API Endpoints

**Modified Endpoints:**
- `POST /api/admin/golden-repos` - Accept temporal parameters
- `GET /api/admin/golden-repos/{alias}` - Return temporal status

**Request/Response Format:**
```json
// Request
{
  "repo_url": "https://github.com/example/repo.git",
  "alias": "test-repo",
  "enable_temporal": true,
  "temporal_options": {
    "max_commits": 1000,
    "since_date": "2023-01-01"
  }
}

// Response includes temporal status
{
  "alias": "test-repo",
  "enable_temporal": true,
  "temporal_index_status": "completed",
  "last_indexed_commit": "abc123"
}
```

## Acceptance Criteria

### Functional Requirements
- [ ] API accepts enable_temporal flag in registration request
- [ ] API accepts temporal_options with max_commits and since_date
- [ ] Workflow executes temporal indexing when enabled
- [ ] Temporal configuration persisted in metadata
- [ ] GET endpoint returns temporal status
- [ ] Works with both new registrations and refreshes

### Quality Requirements
- [ ] Graceful error handling with clear messages
- [ ] No timeout specifications (background job handles)
- [ ] Subprocess pattern consistent with FTS
- [ ] All tests passing

## Testing Strategy

### Manual Test Scenarios
1. Register with temporal enabled and verify index creation
2. Register with max_commits limit and verify constraint
3. Register with since_date and verify date filtering
4. Refresh existing repo with temporal
5. Query temporal status via GET endpoint
6. Handle failure scenarios gracefully

### Error Scenarios
- Temporal indexing fails → Job shows error
- Invalid temporal_options → HTTP 400
- Repository has no commits → Accept gracefully

## Dependencies

- Epic Features 01-03 (CLI temporal implementation)
- Existing GoldenRepoManager
- Background job manager
- CLI temporal indexing commands

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Long indexing time | Medium | No timeout, async jobs, user controls limits |
| Invalid parameters | Low | Validation in API models |
| Storage growth | Medium | User controls with max_commits/since_date |

## Success Metrics

- Golden repos registered with temporal indexing
- Temporal queries work on API-registered repos
- No performance regression in registration
- Clear error messages on failures

## Notes

**Conversation Citations:**
- User requirement for API server temporal support
- Follow FTS integration pattern
- No arbitrary timeouts or limits
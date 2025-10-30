# Story: Golden Repository Registration with Temporal Indexing

## Story Overview

**User Story:**
As a CIDX server administrator
I want to register golden repositories with temporal indexing enabled via API
So that users can query code history across time without manual CLI indexing

**Conversation Context:**
User requirement: "make sure we have user story(ies) to add support to the API server, to register a golden repo with the temporary git index. we recently added support for fts index, to CLI and to the API server, this should follow a similar pattern."

**Success Criteria:**
- POST `/api/admin/golden-repos` accepts `enable_temporal` field
- Temporal indexing executes during registration workflow
- Configuration persists in golden repo metadata
- Error handling provides clear feedback

## Acceptance Criteria

### API Integration
- [ ] POST `/api/admin/golden-repos` accepts `enable_temporal: bool` field in request body
- [ ] POST `/api/admin/golden-repos` accepts optional `temporal_options` with `max_commits` and `since_date` constraints
- [ ] When `enable_temporal=true`, workflow executes `cidx index --index-commits` after standard indexing (subprocess pattern)
- [ ] Workflow passes `--max-commits` and `--since-date` flags if provided in temporal_options
- [ ] NO timeout specifications - background job manager handles duration naturally
- [ ] Temporal configuration persisted in golden repo metadata
- [ ] GET `/api/admin/golden-repos/{alias}` returns temporal status (enabled/disabled, last indexed commit)

### Storage & Validation
- [ ] Temporal index files exist at `.code-indexer/index/temporal/commits.db` in golden repo after completion
- [ ] Registration fails gracefully if temporal indexing fails (with clear error message in job result)
- [ ] Works with both new registrations and repo refreshes

## Technical Implementation

### Integration Point
`GoldenRepoManager._execute_post_clone_workflow()`

### Model Extension
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

### Workflow Modification
```python
def _execute_post_clone_workflow(
    self, clone_path: str, force_init: bool = False,
    enable_temporal: bool = False, temporal_options: Optional[Dict] = None
) -> None:
    # Build index command
    index_command = ["cidx", "index"]
    if enable_temporal:
        index_command.append("--index-commits")
        if temporal_options:
            if temporal_options.get("max_commits"):
                index_command.extend(["--max-commits", str(temporal_options["max_commits"])])
            if temporal_options.get("since_date"):
                index_command.extend(["--since-date", temporal_options["since_date"]])

    workflow_commands = [
        ["cidx", "init", "--embedding-provider", "voyage-ai"] + (["--force"] if force_init else []),
        ["cidx", "start", "--force-docker"],
        ["cidx", "status", "--force-docker"],
        index_command,  # Modified with temporal flags
        ["cidx", "stop", "--force-docker"],
    ]

    # Execute workflow - NO timeout specifications, let background job handle
    for command in workflow_commands:
        result = subprocess.run(command, cwd=clone_path, capture_output=True, text=True)
        # Error handling logic...
```

### Configuration Persistence
Store temporal configuration in golden repo metadata JSON at `~/.cidx-server/data/golden-repos/{alias}/metadata.json`:
```json
{
  "alias": "my-repo",
  "enable_temporal": true,
  "temporal_options": {
    "max_commits": null,
    "since_date": null
  },
  "last_indexed_commit": "abc123def"
}
```

## Manual Test Plan

### Test Case 1: Register with Temporal Enabled
1. Register golden repo with temporal enabled:
   ```bash
   curl -X POST http://localhost:8000/api/admin/golden-repos \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "repo_url": "https://github.com/example/repo.git",
       "alias": "test-repo",
       "enable_temporal": true,
       "temporal_options": {"max_commits": 1000}
     }'
   ```
2. Poll job status: `GET /api/jobs/{job_id}` until status = "completed"
3. Verify temporal database exists:
   ```bash
   ls ~/.cidx-server/data/golden-repos/test-repo/.code-indexer/index/temporal/commits.db
   ```
4. Query temporal data via API to confirm indexing worked
5. Get repo metadata: `GET /api/admin/golden-repos/test-repo` - verify `enable_temporal: true`

### Test Case 2: Register with Since Date
1. Register with since_date constraint:
   ```bash
   curl -X POST http://localhost:8000/api/admin/golden-repos \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "repo_url": "https://github.com/example/repo.git",
       "alias": "recent-repo",
       "enable_temporal": true,
       "temporal_options": {"since_date": "2024-01-01"}
     }'
   ```
2. Verify only commits after 2024-01-01 are indexed

### Test Case 3: Refresh with Temporal
1. Register repo without temporal
2. Refresh with temporal enabled
3. Verify temporal index created on refresh

### Test Case 4: Handle Empty Repository
1. Register empty repository with temporal
2. Verify graceful handling (no error, empty temporal index)

### Test Case 5: Error Handling
1. Simulate temporal indexing failure (e.g., disk full)
2. Verify job shows error with clear message
3. Verify standard index still exists

## Error Scenarios

### Invalid Parameters
- Invalid temporal_options → HTTP 400 with validation error
- Invalid date format → HTTP 400 with format example
- Negative max_commits → HTTP 400 validation error

### Runtime Errors
- Temporal indexing fails → Job status shows error with clear message
- Repository has no commits → Accept gracefully, create empty temporal index
- Disk space issues → Clear error in job result

### Recovery
- Failed temporal indexing doesn't affect standard index
- Can retry with different parameters
- Clear guidance in error messages

## Dependencies

### Required Components
- Existing `GoldenRepoManager` and `_execute_post_clone_workflow()`
- Background job manager for async execution
- CLI temporal indexing (Features 01-03 of epic)

### Configuration
- Project-specific config in `.code-indexer/config.json`
- Golden repo metadata in `~/.cidx-server/data/golden-repos/{alias}/metadata.json`

## Implementation Order

1. Extend API models with temporal fields
2. Modify `_execute_post_clone_workflow()` to handle temporal
3. Update metadata persistence
4. Add temporal status to GET endpoint
5. Implement error handling
6. Add integration tests
7. Manual testing
8. Documentation update

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Long indexing time | High | No timeout, background jobs, user limits |
| Large storage usage | Medium | User controls via max_commits/since_date |
| API breaking change | Low | Fields are optional, backward compatible |

## Notes

**Critical Design Decisions:**
- NO timeout specifications (per conversation requirement)
- Subprocess pattern for consistency with existing workflow
- User-controlled limits, no arbitrary maximums
- Graceful degradation on errors

**Conversation Citation:**
User explicitly requested: "make sure we have user story(ies) to add support to the API server, to register a golden repo with the temporary git index"
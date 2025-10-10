# Feature: Composite Repository Management

## Feature Overview
Implement management operations for composite repositories, including proper error handling for unsupported operations and support for allowed operations like status, details, and file listing.

## Business Context
**Constraints**: "Commands limited to what's already supported within cidx for composite repos" [Phase 1]
**Edge Cases**: "Commands supported in the API that are not supported for composite repos at the CLI level" [Phase 3]

## Technical Design

### Command Support Matrix (from CLI analysis)
**Supported Operations**:
- query ✅ (Feature 2)
- status ✅ (via execute_proxy_command)
- start/stop ✅ (via execute_proxy_command)
- uninstall ✅ (via execute_proxy_command)
- Repository details ✅ (aggregate from subrepos)
- File listing ✅ (filesystem walk)

**Unsupported Operations (Return 400)**:
- branch switch ❌ "Branch Switch, Branch List and Sync I'm ok with 400" [Phase 5]
- branch list ❌
- sync ❌
- index ❌ (blocked in CLI)
- reconcile ❌ (blocked in CLI)

### Error Response Pattern
```python
def _check_composite_and_reject(repo_path: Path, operation: str):
    """Helper to check and reject unsupported composite operations"""
    if _is_composite_repository(repo_path):
        raise HTTPException(
            status_code=400,
            detail=f"Operation '{operation}' is not supported for composite repositories. "
                   f"Composite repos do not support: branch operations, sync, index, or reconcile."
        )
```

## User Stories

### Story 1: Block Unsupported Operations
Return appropriate 400 errors for operations not supported in composite mode.

### Story 2: Repository Details
Aggregate and return information from all component repositories.

### Story 3: File Listing
Support file listing across all component repositories.

### Story 4: Deactivation
Clean deactivation and cleanup of composite repositories.

## Acceptance Criteria
- Unsupported operations return 400 with clear error message
- Repository details shows all component repo information
- File listing walks all subdirectories
- Status/start/stop operations work via CLI integration
- Deactivation cleans up all resources properly

## Implementation Notes
**User Decisions**:
- "Branch Switch, Branch List and Sync I'm ok with 400" [Phase 5]
- "Repo details, let's return the info of all subrepos" [Phase 5]
- "file list, why can't we support it? it's a folder.... why can't you list all files?" [Phase 5]

## Dependencies
- CLI's execute_proxy_command for status/start/stop
- ProxyConfigManager for repository information
- Existing error handling patterns

## Testing Requirements
- Verify 400 errors for all unsupported operations
- Test aggregated repository details
- Confirm file listing includes all subrepos
- Validate clean deactivation
- Test status command integration
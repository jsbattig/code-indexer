# Story: Block Unsupported Operations

## Story Description
Implement proper 400 error responses for all operations that are not supported on composite repositories, based on CLI's command validation logic.

## Business Context
**User Decision**: "Branch Switch, Branch List and Sync I'm ok with 400" [Phase 5]
**Edge Case Handling**: "Commands supported in the API that are not supported for composite repos at the CLI level" [Phase 3]

## Technical Implementation

### Validation Helper
```python
class CompositeRepoValidator:
    """Validates operations on composite repositories"""

    UNSUPPORTED_OPERATIONS = {
        'branch_switch': 'Branch operations are not supported for composite repositories',
        'branch_list': 'Branch operations are not supported for composite repositories',
        'sync': 'Sync is not supported for composite repositories',
        'index': 'Indexing must be done on individual golden repositories',
        'reconcile': 'Reconciliation is not supported for composite repositories',
        'init': 'Composite repositories cannot be initialized'
    }

    @staticmethod
    def check_operation(repo_path: Path, operation: str):
        """Raise 400 if operation not supported on composite repo"""
        config_file = repo_path / ".code-indexer" / "config.json"

        if config_file.exists():
            config = json.loads(config_file.read_text())
            if config.get("proxy_mode", False):
                if operation in CompositeRepoValidator.UNSUPPORTED_OPERATIONS:
                    raise HTTPException(
                        status_code=400,
                        detail=CompositeRepoValidator.UNSUPPORTED_OPERATIONS[operation]
                    )
```

### API Endpoint Guards
```python
# Branch switch endpoint
@router.put("/api/repos/{user_alias}/branch")
async def switch_branch(user_alias: str, request: SwitchBranchRequest):
    repo = activated_repo_manager.get_repository(user_alias)
    if not repo:
        raise HTTPException(404, "Repository not found")

    # Check if composite and reject
    CompositeRepoValidator.check_operation(repo.path, 'branch_switch')

    # Existing single-repo logic continues...


# Sync endpoint
@router.put("/api/repos/{user_alias}/sync")
async def sync_repository(user_alias: str):
    repo = activated_repo_manager.get_repository(user_alias)
    if not repo:
        raise HTTPException(404, "Repository not found")

    # Check if composite and reject
    CompositeRepoValidator.check_operation(repo.path, 'sync')

    # Existing single-repo logic continues...


# Branch list endpoint
@router.get("/api/repositories/{repo_id}/branches")
async def list_branches(repo_id: str):
    repo = activated_repo_manager.get_repository(repo_id)
    if not repo:
        raise HTTPException(404, "Repository not found")

    # Check if composite and reject
    CompositeRepoValidator.check_operation(repo.path, 'branch_list')

    # Existing single-repo logic continues...
```

### Error Response Format
```json
{
  "detail": "Branch operations are not supported for composite repositories"
}
```

## Acceptance Criteria
- [x] Branch switch returns 400 for composite repos
- [x] Branch list returns 400 for composite repos
- [x] Sync returns 400 for composite repos
- [x] Error messages clearly explain limitation
- [x] Single-repo operations continue to work
- [x] Validation happens before any operation attempt

## Test Scenarios
1. **Branch Switch Block**: POST to branch endpoint returns 400
2. **Branch List Block**: GET branches endpoint returns 400
3. **Sync Block**: PUT sync endpoint returns 400
4. **Clear Messages**: Error messages explain why operation blocked
5. **Single Repo Unchanged**: All operations work on single repos

## Implementation Notes
- Based on CLI's command_validator.py logic
- Early validation before attempting operations
- Consistent error messages across all blocked operations
- HTTP 400 indicates client error (unsupported operation)

## Dependencies
- Existing API endpoint structure
- CLI's command validation patterns
- HTTPException for proper error responses

## Estimated Effort
~20 lines for validator class and endpoint guards
# Story: Implement List Branches Endpoint

## User Story
As a **repository user**, I want to **list all available branches in my repository** so that **I can see branch status and choose which branch to work with**.

## Problem Context
The GET /api/repositories/{repo_id}/branches endpoint returns 405 Method Not Allowed. Users cannot discover available branches through the API.

## Acceptance Criteria

### Scenario 1: List Branches for Repository
```gherkin
Given I am authenticated and have repository "repo-123"
  And the repository has branches ["main", "develop", "feature-x"]
  And "main" is the current branch
When I send GET request to "/api/repositories/repo-123/branches"
Then the response status should be 200 OK
  And the response should list all 3 branches
  And "main" should be marked as current
  And each branch should show last commit info
  And each branch should show index status
```

### Scenario 2: List Branches with Index Status
```gherkin
Given repository has branches with different index states:
  | Branch | Status | Files Indexed |
  | main | indexed | 100 |
  | develop | indexing | 45/90 |
  | feature-x | not_indexed | 0 |
When I send GET request to list branches
Then each branch should show accurate index status
  And indexing progress should be shown for in-progress branches
```

### Scenario 3: Remote Branch Information
```gherkin
Given repository has remote tracking branches
When I send GET request with "?include_remote=true"
Then response should include remote branches
  And response should show ahead/behind counts
  And response should indicate tracking relationships
```

## Technical Implementation Details

### API Response Schema
```json
{
  "branches": [
    {
      "name": "main",
      "is_current": true,
      "last_commit": {
        "sha": "abc123",
        "message": "Latest commit",
        "author": "John Doe",
        "date": "2024-01-15T10:00:00Z"
      },
      "index_status": {
        "status": "indexed",
        "files_indexed": 100,
        "last_indexed": "2024-01-15T09:00:00Z"
      },
      "remote_tracking": {
        "remote": "origin/main",
        "ahead": 0,
        "behind": 2
      }
    }
  ],
  "total": 3,
  "current_branch": "main"
}
```

### Implementation
```
@router.get("/api/repositories/{repo_id}/branches")
async function list_branches(
    repo_id: str,
    include_remote: bool = False,
    current_user: User = Depends(get_current_user)
):
    repository = await get_repository_with_access_check(repo_id, current_user)
    
    git_repo = git.Repo(repository.path)
    branches = []
    
    for branch in git_repo.branches:
        branch_info = {
            "name": branch.name,
            "is_current": branch == git_repo.active_branch,
            "last_commit": get_commit_info(branch.commit),
            "index_status": await get_branch_index_status(repo_id, branch.name)
        }
        
        if include_remote and branch.tracking_branch():
            branch_info["remote_tracking"] = get_tracking_info(branch)
        
        branches.append(branch_info)
    
    return {
        "branches": branches,
        "total": len(branches),
        "current_branch": git_repo.active_branch.name
    }
```

## Definition of Done
- [ ] GET /api/repositories/{repo_id}/branches implemented
- [ ] Returns 200 OK with branch list
- [ ] Shows current branch indicator
- [ ] Shows index status per branch
- [ ] Shows commit information
- [ ] Optional remote branch info
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] API documentation updated
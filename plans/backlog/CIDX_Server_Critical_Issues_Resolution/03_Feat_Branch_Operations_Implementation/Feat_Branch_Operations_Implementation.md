# Feature: Branch Operations Implementation

## Feature Overview
This feature implements missing branch management APIs that currently return 405 Method Not Allowed, enabling users to list, switch, create, and manage Git branches through the CIDX server.

## Problem Statement
- GET /api/repositories/{repo_id}/branches returns 405 Method Not Allowed
- POST /api/repositories/{repo_id}/branches returns 405 Method Not Allowed
- No ability to switch branches via API
- No branch-specific indexing status
- Missing branch comparison functionality

## Technical Architecture

### Affected Components
```
Branch API Layer
├── GET /api/repositories/{repo_id}/branches [NOT IMPLEMENTED]
├── POST /api/repositories/{repo_id}/branches [NOT IMPLEMENTED]
├── PUT /api/repositories/{repo_id}/branches/current [MISSING]
├── DELETE /api/repositories/{repo_id}/branches/{branch} [MISSING]
└── GET /api/repositories/{repo_id}/branches/diff [MISSING]

Git Service Layer
├── list_branches() [NOT IMPLEMENTED]
├── create_branch() [NOT IMPLEMENTED]
├── switch_branch() [NOT IMPLEMENTED]
├── delete_branch() [NOT IMPLEMENTED]
└── compare_branches() [NOT IMPLEMENTED]
```

### Design Decisions
1. **GitPython Integration**: Use GitPython for Git operations
2. **Branch Isolation**: Separate index collections per branch
3. **Async Operations**: Long-running operations in background
4. **Conflict Resolution**: Handle merge conflicts gracefully
5. **History Tracking**: Maintain branch switch history

## Dependencies
- GitPython for repository operations
- AsyncIO for background operations
- Qdrant for branch-specific collections
- Database for branch metadata
- File locking for concurrent access

## Story List

1. **01_Story_Implement_List_Branches_Endpoint** - GET endpoint to list all branches
2. **02_Story_Implement_Create_Branch_Endpoint** - POST endpoint to create new branches
3. **03_Story_Implement_Switch_Branch_Endpoint** - PUT endpoint to switch current branch
4. **04_Story_Add_Branch_Comparison_Endpoint** - GET endpoint to compare branches

## Integration Points
- Git repository management
- Qdrant collection per branch
- File system for working directory
- Background job system
- WebSocket for real-time updates

## Testing Requirements
- Unit tests for Git operations
- Integration tests with real repositories
- Concurrent operation tests
- Branch conflict scenarios
- Performance with many branches

## Success Criteria
- [ ] List branches endpoint returns all branches
- [ ] Create branch endpoint creates and indexes new branch
- [ ] Switch branch updates working directory
- [ ] Branch comparison shows differences
- [ ] No 405 errors on branch endpoints
- [ ] Manual test case TC_BRANCH_001 passes
- [ ] Concurrent branch operations handled safely

## Risk Considerations
- **Data Loss**: Switching branches might lose uncommitted changes
- **Index Corruption**: Branch operations might corrupt indexes
- **Concurrent Access**: Multiple users modifying same repository
- **Large Repositories**: Performance with many branches/files

## Performance Requirements
- List branches < 100ms
- Create branch < 5 seconds
- Switch branch < 10 seconds for most repositories
- Support repositories with 100+ branches
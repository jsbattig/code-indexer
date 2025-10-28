# Feature: Composite Repository Activation

## Feature Overview
Extend the server's repository activation capability to support composite repositories - activating multiple golden repositories as a single queryable unit, matching CLI proxy mode functionality.

## Business Context
**User Need**: "User activated a composite repo before starting a coding task, and keeps it activated during it's activity" [Phase 2]

**Core Requirement**: "Activation of composite activated repo and ability to query it" [Phase 2]

## Technical Design

### Reused CLI Components
- `ProxyInitializer` - Creates proxy-mode config.json
- `ProxyConfigManager` - Manages discovered repositories
- CoW cloning mechanism - Efficient repository duplication

### Server Extensions Required (~100 lines)
```python
# ActivatedRepoManager changes:
def activate_repository(
    self,
    golden_repo_alias: Optional[str] = None,
    golden_repo_aliases: Optional[List[str]] = None,  # NEW
    user_alias: Optional[str] = None
) -> ActivatedRepository:
    if golden_repo_aliases:
        return self._do_activate_composite_repository(golden_repo_aliases, user_alias)
    # ... existing single-repo logic
```

### Filesystem Structure
```
~/.cidx-server/data/activated-repos/<username>/<composite_alias>/
├── .code-indexer/
│   └── config.json          # {"proxy_mode": true, "discovered_repos": [...]}
├── repo1/                   # CoW clone from golden-repos/repo1
├── repo2/                   # CoW clone from golden-repos/repo2
└── repo3/                   # CoW clone from golden-repos/repo3
```

## User Stories

### Story 1: Extend Activation API
Accept array of golden repository aliases in activation request.

### Story 2: Create Composite Structure
Build proper filesystem layout using ProxyInitializer.

### Story 3: Metadata Management
Track composite repository state and component relationships.

## Acceptance Criteria
- API accepts `golden_repo_aliases` parameter with array of repository names
- Creates composite repository with proxy_mode configuration
- Each component repository is CoW cloned as subdirectory
- ProxyConfigManager can discover and validate all repositories
- Activation returns metadata indicating composite nature

## Implementation Notes
**Maximum Reuse**: "reuse EVERYTHING you can, already implemented in the context of the CLI under the hood classes" [Phase 6]

- Use ProxyInitializer.create_proxy_config() directly
- Use ProxyConfigManager.refresh_repositories() for discovery
- Leverage existing CoW cloning from single-repo activation

## Dependencies
- ProxyInitializer from CLI codebase
- ProxyConfigManager from CLI codebase
- Existing golden repository infrastructure

## Testing Requirements
- Verify activation with 2, 3, and 5 repositories
- Confirm proxy_mode flag is set correctly
- Validate discovered_repos list matches input
- Ensure CoW cloning works for all component repos
- Test error handling for invalid golden repo aliases
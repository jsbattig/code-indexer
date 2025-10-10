# Story: Create Composite Structure

## Story Description
Implement the core composite repository creation logic that builds the proper filesystem structure using CLI's ProxyInitializer and CoW clones each component repository.

## Business Context
**Core Need**: Create a composite repository structure that matches CLI proxy mode layout
**Reuse Mandate**: "reuse EVERYTHING you can, already implemented in the context of the CLI" [Phase 6]

## Technical Implementation

### Composite Activation Method
```python
def _do_activate_composite_repository(
    self,
    golden_repo_aliases: List[str],
    user_alias: Optional[str] = None
) -> ActivatedRepository:
    # 1. Generate composite alias
    if not user_alias:
        user_alias = f"composite_{'_'.join(golden_repo_aliases[:3])}"

    # 2. Create base directory
    composite_path = self._get_user_repo_path(user_alias)
    composite_path.mkdir(parents=True, exist_ok=True)

    # 3. Use ProxyInitializer to create config
    from ...proxy.proxy_initializer import ProxyInitializer
    proxy_init = ProxyInitializer()
    proxy_init.create_proxy_config(
        root_dir=composite_path,
        force=True
    )

    # 4. CoW clone each golden repo as subdirectory
    for alias in golden_repo_aliases:
        golden_repo = self.golden_repo_manager.get_repository(alias)
        if not golden_repo:
            raise ValueError(f"Golden repository '{alias}' not found")

        subrepo_path = composite_path / alias
        self._cow_clone_repository(
            source_path=golden_repo.path,
            target_path=subrepo_path
        )

    # 5. Refresh discovered repositories
    from ...proxy.proxy_config_manager import ProxyConfigManager
    proxy_config = ProxyConfigManager(composite_path)
    proxy_config.refresh_repositories()

    # 6. Create metadata
    return self._create_composite_metadata(
        composite_path, golden_repo_aliases, user_alias
    )
```

### Expected Filesystem Result
```
~/.cidx-server/data/activated-repos/<username>/<composite_alias>/
├── .code-indexer/
│   └── config.json
│       {
│           "proxy_mode": true,
│           "discovered_repos": ["repo1", "repo2", "repo3"]
│       }
├── repo1/
│   ├── .git/
│   ├── .code-indexer/
│   │   └── [indexed Qdrant data]
│   └── [source files]
├── repo2/
│   ├── .git/
│   ├── .code-indexer/
│   └── [source files]
└── repo3/
    ├── .git/
    ├── .code-indexer/
    └── [source files]
```

### CoW Clone Reuse
```python
def _cow_clone_repository(self, source_path: Path, target_path: Path):
    # Reuse existing CoW clone logic from single-repo activation
    subprocess.run(
        ["git", "clone", "--local", str(source_path), str(target_path)],
        check=True,
        capture_output=True
    )
```

## Acceptance Criteria
- [x] Creates composite directory with user_alias name
- [x] ProxyInitializer creates .code-indexer/config.json with proxy_mode=true
- [x] Each golden repo is CoW cloned as subdirectory
- [x] ProxyConfigManager discovers all cloned repositories
- [x] discovered_repos list in config matches cloned repos
- [x] All component repos retain their .code-indexer/ indexed data

## Test Scenarios
1. **Structure Validation**: Verify correct directory layout
2. **Config Creation**: Confirm proxy_mode flag and discovered_repos
3. **CoW Verification**: Check that repos share objects with golden
4. **Discovery**: ProxyConfigManager finds all component repos
5. **Index Preservation**: Each repo's Qdrant data is accessible

## Implementation Notes
- ProxyInitializer and ProxyConfigManager are imported from CLI code
- No reimplementation - direct usage of CLI components
- CoW cloning preserves indexed data from golden repos
- Discovery happens automatically via ProxyConfigManager.refresh_repositories()

## Dependencies
- ProxyInitializer from src/code_indexer/proxy/proxy_initializer.py
- ProxyConfigManager from src/code_indexer/proxy/proxy_config_manager.py
- Existing CoW clone mechanism from single-repo activation

## Estimated Effort
~50 lines of code for orchestration logic
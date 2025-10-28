# Story: Metadata Management

## Story Description
Implement metadata tracking and state management for composite repositories, ensuring proper identification and lifecycle tracking.

## Business Context
**Need**: Track composite repository state to enable proper query routing and management
**User Flow**: "User activated a composite repo before starting a coding task, and keeps it activated during it's activity" [Phase 2]

## Technical Implementation

### Composite Metadata Structure
```python
class ActivatedRepository(BaseModel):
    user_alias: str
    username: str
    path: Path
    activated_at: datetime
    last_accessed: datetime
    is_composite: bool = False           # NEW field
    golden_repo_aliases: List[str] = []  # NEW field
    discovered_repos: List[str] = []     # NEW field from config
```

### Metadata Creation Method
```python
def _create_composite_metadata(
    self,
    composite_path: Path,
    golden_repo_aliases: List[str],
    user_alias: str
) -> ActivatedRepository:
    # Load proxy config to get discovered repos
    from ...proxy.proxy_config_manager import ProxyConfigManager
    proxy_config = ProxyConfigManager(composite_path)

    metadata = ActivatedRepository(
        user_alias=user_alias,
        username=self.username,
        path=composite_path,
        activated_at=datetime.utcnow(),
        last_accessed=datetime.utcnow(),
        is_composite=True,
        golden_repo_aliases=golden_repo_aliases,
        discovered_repos=proxy_config.get_discovered_repos()
    )

    # Save metadata
    metadata_file = composite_path / ".cidx_metadata.json"
    metadata_file.write_text(metadata.json(indent=2))

    return metadata
```

### Metadata Loading Enhancement
```python
def get_repository(self, user_alias: str) -> Optional[ActivatedRepository]:
    repo_path = self._get_user_repo_path(user_alias)
    if not repo_path.exists():
        return None

    metadata_file = repo_path / ".cidx_metadata.json"
    if metadata_file.exists():
        metadata = ActivatedRepository.parse_file(metadata_file)

        # For composite repos, refresh discovered_repos from config
        if metadata.is_composite:
            proxy_config = ProxyConfigManager(repo_path)
            metadata.discovered_repos = proxy_config.get_discovered_repos()

        return metadata

    # Fallback for legacy repos without metadata
    return self._create_legacy_metadata(repo_path)
```

### State Tracking
```python
def list_repositories(self) -> List[ActivatedRepository]:
    repos = []
    user_dir = self.base_path / self.username

    for repo_dir in user_dir.iterdir():
        if repo_dir.is_dir():
            metadata = self.get_repository(repo_dir.name)
            if metadata:
                repos.append(metadata)

    # Sort by last_accessed, composite repos shown with indicator
    return sorted(repos, key=lambda r: r.last_accessed, reverse=True)
```

## Acceptance Criteria
- [x] Composite repos have is_composite=true flag
- [x] Golden repo aliases are tracked in metadata
- [x] Discovered repos list is populated from proxy config
- [x] Metadata file is created in composite repo root
- [x] List operation shows composite repos with proper indicator
- [x] Get operation loads and refreshes composite metadata

## Test Scenarios
1. **Metadata Creation**: Verify all fields populated correctly
2. **Persistence**: Metadata survives server restart
3. **Discovery Refresh**: discovered_repos updates when repos added/removed
4. **List Display**: Composite repos shown distinctly in listing
5. **Legacy Compatibility**: Single repos continue to work

## Implementation Notes
- Extends existing ActivatedRepository model
- Metadata stored as JSON in repository root
- discovered_repos dynamically refreshed from proxy config
- Backward compatible with existing single-repo metadata

## Dependencies
- ProxyConfigManager for reading discovered repositories
- Existing ActivatedRepository model
- Existing metadata persistence patterns

## Estimated Effort
~20 lines for metadata extensions and tracking
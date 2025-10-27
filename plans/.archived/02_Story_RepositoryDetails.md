# Story: Repository Details

## Story Description
Implement repository details endpoint for composite repositories that aggregates and returns information from all component repositories.

## Business Context
**User Decision**: "Repo details, let's return the info of all subrepos" [Phase 5]
**Need**: Provide visibility into all component repositories within a composite activation

## Technical Implementation

### Composite Details Response
```python
class CompositeRepositoryDetails(BaseModel):
    """Details for a composite repository"""
    user_alias: str
    is_composite: bool = True
    activated_at: datetime
    last_accessed: datetime
    component_repositories: List[ComponentRepoInfo]
    total_files: int
    total_size_mb: float

class ComponentRepoInfo(BaseModel):
    """Information about each component repository"""
    name: str
    path: str
    has_index: bool
    collection_exists: bool
    indexed_files: int
    last_indexed: Optional[datetime]
    size_mb: float
```

### Details Endpoint Enhancement
```python
@router.get("/api/repositories/{repo_id}")
async def get_repository_details(repo_id: str):
    repo = activated_repo_manager.get_repository(repo_id)
    if not repo:
        raise HTTPException(404, "Repository not found")

    if repo.is_composite:
        return _get_composite_details(repo)
    else:
        return _get_single_repo_details(repo)  # Existing logic


def _get_composite_details(repo: ActivatedRepository) -> CompositeRepositoryDetails:
    """Aggregate details from all component repositories"""

    component_info = []
    total_files = 0
    total_size = 0

    # Use ProxyConfigManager to get component repos
    from ...proxy.proxy_config_manager import ProxyConfigManager
    proxy_config = ProxyConfigManager(repo.path)

    for repo_name in proxy_config.get_discovered_repos():
        subrepo_path = repo.path / repo_name
        info = _analyze_component_repo(subrepo_path, repo_name)
        component_info.append(info)
        total_files += info.indexed_files
        total_size += info.size_mb

    return CompositeRepositoryDetails(
        user_alias=repo.user_alias,
        is_composite=True,
        activated_at=repo.activated_at,
        last_accessed=repo.last_accessed,
        component_repositories=component_info,
        total_files=total_files,
        total_size_mb=total_size
    )


def _analyze_component_repo(repo_path: Path, name: str) -> ComponentRepoInfo:
    """Analyze a single component repository"""

    # Check for index
    index_dir = repo_path / ".code-indexer"
    has_index = index_dir.exists()

    # Get file count and size
    file_count = 0
    total_size = 0
    if has_index:
        metadata_file = index_dir / "metadata.json"
        if metadata_file.exists():
            metadata = json.loads(metadata_file.read_text())
            file_count = metadata.get("indexed_files", 0)

    # Calculate repo size
    for item in repo_path.rglob("*"):
        if item.is_file():
            total_size += item.stat().st_size

    return ComponentRepoInfo(
        name=name,
        path=str(repo_path),
        has_index=has_index,
        collection_exists=has_index,  # Simplified check
        indexed_files=file_count,
        last_indexed=None,  # Could read from metadata
        size_mb=total_size / (1024 * 1024)
    )
```

### Example Response
```json
{
  "user_alias": "my-composite-project",
  "is_composite": true,
  "activated_at": "2024-01-15T10:00:00Z",
  "last_accessed": "2024-01-15T14:30:00Z",
  "component_repositories": [
    {
      "name": "backend-api",
      "path": "~/.cidx-server/data/activated-repos/user/my-composite-project/backend-api",
      "has_index": true,
      "collection_exists": true,
      "indexed_files": 245,
      "size_mb": 12.5
    },
    {
      "name": "frontend-app",
      "path": "~/.cidx-server/data/activated-repos/user/my-composite-project/frontend-app",
      "has_index": true,
      "collection_exists": true,
      "indexed_files": 189,
      "size_mb": 8.3
    }
  ],
  "total_files": 434,
  "total_size_mb": 20.8
}
```

## Acceptance Criteria
- [x] Returns aggregated details for composite repos
- [x] Shows information for each component repository
- [x] Calculates total files and size across all components
- [x] Identifies which components have indexes
- [x] Single-repo details endpoint unchanged

## Test Scenarios
1. **Aggregation**: Details include all component repos
2. **Metrics**: File counts and sizes calculated correctly
3. **Index Status**: Correctly identifies indexed vs non-indexed
4. **Empty Components**: Handles repos with no files gracefully
5. **Single Repo**: Existing details work unchanged

## Implementation Notes
- Reuse ProxyConfigManager for repository discovery
- Aggregate metrics across all components
- Provide visibility into each component's state
- Keep existing single-repo logic intact

## Dependencies
- ProxyConfigManager for component discovery
- Existing repository metadata structures
- Filesystem utilities for size calculation

## Estimated Effort
~40 lines for aggregation and detail collection
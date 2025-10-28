# Story: File Listing

## Story Description
Implement file listing capability for composite repositories by walking the filesystem across all component repositories.

## Business Context
**User Requirement**: "file list, why can't we support it? it's a folder.... why can't you list all files?" [Phase 5]
**Logic**: Composite repository is just a directory structure - file listing should work naturally

## Technical Implementation

### File List Endpoint Support
```python
@router.get("/api/repositories/{repo_id}/files")
async def list_files(
    repo_id: str,
    path: str = "",
    recursive: bool = False
):
    repo = activated_repo_manager.get_repository(repo_id)
    if not repo:
        raise HTTPException(404, "Repository not found")

    if repo.is_composite:
        return _list_composite_files(repo, path, recursive)
    else:
        return _list_single_repo_files(repo, path, recursive)  # Existing


def _list_composite_files(
    repo: ActivatedRepository,
    path: str = "",
    recursive: bool = False
) -> List[FileInfo]:
    """List files across all component repositories"""

    files = []

    # Get component repos
    from ...proxy.proxy_config_manager import ProxyConfigManager
    proxy_config = ProxyConfigManager(repo.path)

    for repo_name in proxy_config.get_discovered_repos():
        subrepo_path = repo.path / repo_name
        target_path = subrepo_path / path if path else subrepo_path

        if not target_path.exists():
            continue

        # Walk the component repository
        repo_files = _walk_directory(
            target_path,
            repo_name,
            recursive
        )
        files.extend(repo_files)

    # Sort by path for consistent output
    return sorted(files, key=lambda f: f.full_path)
```

### Directory Walker
```python
def _walk_directory(
    directory: Path,
    repo_prefix: str,
    recursive: bool
) -> List[FileInfo]:
    """Walk directory and collect file information"""

    files = []

    if recursive:
        # Recursive walk
        for item in directory.rglob("*"):
            if item.is_file():
                # Skip git and index directories
                if ".git" in item.parts or ".code-indexer" in item.parts:
                    continue

                relative_path = item.relative_to(directory.parent)
                files.append(FileInfo(
                    full_path=f"{repo_prefix}/{relative_path}",
                    name=item.name,
                    size=item.stat().st_size,
                    modified=datetime.fromtimestamp(item.stat().st_mtime),
                    is_directory=False,
                    component_repo=repo_prefix
                ))
    else:
        # Single level listing
        for item in directory.iterdir():
            relative_path = item.relative_to(directory.parent)

            files.append(FileInfo(
                full_path=f"{repo_prefix}/{relative_path}",
                name=item.name,
                size=item.stat().st_size if item.is_file() else 0,
                modified=datetime.fromtimestamp(item.stat().st_mtime),
                is_directory=item.is_dir(),
                component_repo=repo_prefix
            ))

    return files
```

### Response Model
```python
class FileInfo(BaseModel):
    """File information for listing"""
    full_path: str           # e.g., "backend-api/src/main.py"
    name: str               # e.g., "main.py"
    size: int               # bytes
    modified: datetime
    is_directory: bool
    component_repo: str     # Which subrepo this file belongs to
```

### Example Response
```json
{
  "files": [
    {
      "full_path": "backend-api/src/main.py",
      "name": "main.py",
      "size": 2456,
      "modified": "2024-01-15T10:00:00Z",
      "is_directory": false,
      "component_repo": "backend-api"
    },
    {
      "full_path": "frontend-app/src/App.jsx",
      "name": "App.jsx",
      "size": 1890,
      "modified": "2024-01-15T11:30:00Z",
      "is_directory": false,
      "component_repo": "frontend-app"
    }
  ]
}
```

## Acceptance Criteria
- [x] Lists files from all component repositories
- [x] Supports both recursive and non-recursive listing
- [x] Files show which component repo they belong to
- [x] Paths are relative to component repository
- [x] Excludes .git and .code-indexer directories
- [x] Single-repo file listing unchanged

## Test Scenarios
1. **Multi-Repo Listing**: Files from all components included
2. **Recursive Walk**: Deep directory traversal works
3. **Path Filtering**: Can list specific subdirectories
4. **Exclusions**: Git and index directories not included
5. **Sorting**: Files sorted consistently by path

## Implementation Notes
- Simple filesystem walking - no complex logic needed
- Component repository prefix in paths for clarity
- Reuse existing file listing patterns where possible
- Performance: Consider pagination for large repos

## Dependencies
- ProxyConfigManager for repository discovery
- Standard filesystem operations
- Existing file listing patterns

## Estimated Effort
~30 lines for filesystem walking and aggregation
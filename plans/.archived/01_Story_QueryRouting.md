# Story: Query Routing

## Story Description
Implement detection of composite repositories and proper routing to multi-repository query handler, ensuring seamless query execution for both single and composite repos.

## Business Context
**Need**: Automatically detect and handle queries differently for composite repositories
**Constraint**: Must maintain backward compatibility with single-repo queries

## Technical Implementation

### Config Detection Method
```python
class SemanticQueryManager:
    def _is_composite_repository(self, repo_path: Path) -> bool:
        """Check if repository is in proxy mode (composite)"""
        config_file = repo_path / ".code-indexer" / "config.json"
        if config_file.exists():
            config = json.loads(config_file.read_text())
            return config.get("proxy_mode", False)
        return False
```

### Query Endpoint Enhancement
```python
@router.post("/api/query")
async def semantic_query(request: QueryRequest):
    results = []

    for repo in request.repositories:
        repo_path = activated_repo_manager.get_repository_path(
            request.username, repo
        )

        if not repo_path:
            continue

        # Route based on repository type
        if query_manager._is_composite_repository(repo_path):
            # Composite query path
            repo_results = await query_manager.search_composite(
                repo_path=repo_path,
                query=request.query,
                limit=request.limit,
                min_score=request.min_score
            )
        else:
            # Existing single-repo path
            repo_results = await query_manager.search_single(
                repo_path=repo_path,
                query=request.query,
                limit=request.limit,
                min_score=request.min_score
            )

        results.extend(repo_results)

    return QueryResponse(results=results)
```

### Manager Method Split
```python
class SemanticQueryManager:
    async def search(self, repo_path: Path, query: str, **kwargs):
        """Main entry point - routes to appropriate handler"""
        if self._is_composite_repository(repo_path):
            return await self.search_composite(repo_path, query, **kwargs)
        return await self.search_single(repo_path, query, **kwargs)

    async def search_single(self, repo_path: Path, query: str, **kwargs):
        """Existing single-repo logic (unchanged)"""
        # Current implementation remains here

    async def search_composite(self, repo_path: Path, query: str, **kwargs):
        """New composite query handler"""
        # Will call CLI's _execute_query in next story
        pass
```

## Acceptance Criteria
- [x] Correctly identifies composite repos via proxy_mode flag
- [x] Routes composite queries to new handler
- [x] Routes single-repo queries to existing handler
- [x] No changes to single-repo query behavior
- [x] Maintains same API interface for both types

## Test Scenarios
1. **Detection**: Verify proxy_mode flag detection works
2. **Single Routing**: Single repos use existing path
3. **Composite Routing**: Composite repos use new path
4. **Missing Config**: Handles missing config gracefully
5. **Mixed Queries**: Can query both types in same request

## Implementation Notes
- Detection based on proxy_mode flag in config.json
- Clean separation between single and composite paths
- Existing single-repo logic remains untouched
- Prepares structure for CLI integration in next story

## Dependencies
- Existing SemanticQueryManager
- Repository configuration structure
- Activated repository metadata

## Estimated Effort
~15 lines for routing logic and detection
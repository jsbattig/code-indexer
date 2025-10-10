# Feature: Multi-Repository Query Execution

## Feature Overview
Execute semantic queries across all component repositories in a composite activation, leveraging CLI's existing parallel query infrastructure for maximum reuse.

## Business Context
**Core Requirement**: "ability to query it" [Phase 2]
**Success Criteria**: "ultimate acceptance criteria is that you can activate a repo, and run queries on it and you confirm matches from multiple underlying repos are coming back, in the right order" [Phase 3]

## Technical Design

### Reused CLI Components
- `cli_integration._execute_query()` - Complete parallel query logic
- `QueryResultAggregator` - Result merging and scoring
- `ProxyConfigManager` - Repository discovery
- Parallel execution infrastructure

### Server Extensions Required (~50 lines)
```python
# SemanticQueryManager changes:
async def search(self, repo_path: Path, query: str, **kwargs):
    config = self._load_config(repo_path)

    if config.get("proxy_mode"):
        # Use CLI's _execute_query directly
        from ...cli_integration import _execute_query
        results = _execute_query(
            root_dir=repo_path,
            query=query,
            limit=kwargs.get('limit', 10),
            quiet=True
        )
        return self._format_composite_results(results)

    # Existing single-repo logic
```

### Query Flow
1. Detect proxy_mode in repository config
2. Call CLI's _execute_query() directly
3. Parallel execution across all discovered repos
4. Aggregation with global score sorting
5. Format results for API response

## User Stories

### Story 1: Query Routing
Detect composite repositories and route to appropriate query handler.

### Story 2: Parallel Execution
Reuse CLI's _execute_query() for multi-repo parallel search.

### Story 3: Result Aggregation
Merge and order results from multiple repositories correctly.

## Acceptance Criteria
- Queries to composite repos use CLI's _execute_query()
- Results come from all component repositories
- Results are ordered by global relevance score
- Repository source is identified in each result
- Performance matches CLI proxy mode execution

## Implementation Notes
**Maximum Reuse Directive**: "reuse EVERYTHING you can, already implemented in the context of the CLI" [Phase 6]

- NO reimplementation of parallel query logic
- Direct usage of _execute_query() function
- Leverage existing QueryResultAggregator
- Thin wrapper for API formatting only

## Dependencies
- cli_integration._execute_query() function
- QueryResultAggregator class
- ProxyConfigManager for repository discovery

## Testing Requirements
- Verify results include matches from all repos
- Confirm global score ordering
- Test with overlapping and unique results
- Validate performance matches CLI
- Edge case: Empty results from some repos
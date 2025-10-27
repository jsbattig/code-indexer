# Story: Reuse CLI Execute Query

## Story Description
Directly integrate CLI's _execute_query() function for parallel multi-repository search execution, maximizing code reuse per the architectural mandate.

## Business Context
**Reuse Mandate**: "reuse EVERYTHING you can, already implemented in the context of the CLI under the hood classes, and don't re-implement in the server context" [Phase 6]
**Goal**: Zero reimplementation of parallel query logic

## Technical Implementation

### Direct CLI Integration
```python
class SemanticQueryManager:
    async def search_composite(
        self,
        repo_path: Path,
        query: str,
        limit: int = 10,
        min_score: float = 0.0,
        **kwargs
    ):
        """Execute composite query using CLI's _execute_query"""

        # Import CLI's query function
        from code_indexer.cli_integration import _execute_query

        # Call CLI function directly (it handles everything)
        cli_results = _execute_query(
            root_dir=repo_path,
            query=query,
            limit=limit,
            language=kwargs.get('language'),
            path_pattern=kwargs.get('path'),
            min_score=min_score,
            accuracy=kwargs.get('accuracy', 'balanced'),
            quiet=True  # Always quiet for parsing
        )

        # Parse CLI output to API format
        return self._parse_cli_results(cli_results, repo_path)
```

### Result Parser
```python
def _parse_cli_results(self, cli_output: str, repo_path: Path) -> List[QueryResult]:
    """Convert CLI output to API response format"""
    results = []
    current_repo = None

    for line in cli_output.strip().split('\n'):
        if not line:
            continue

        # CLI format: [repo_name] score: 0.95 - path/to/file.py
        if line.startswith('['):
            repo_match = re.match(r'\[([^\]]+)\] score: ([\d.]+) - (.+)', line)
            if repo_match:
                repo_name, score, file_path = repo_match.groups()
                results.append(QueryResult(
                    repository=repo_name,
                    file_path=file_path,
                    score=float(score),
                    content=None,  # Content fetched separately if needed
                    source_repo=repo_name  # Track which subrepo
                ))

    return results
```

### What _execute_query Does (No Reimplementation Needed)
```python
# From cli_integration.py - WE DON'T REIMPLEMENT THIS:
def _execute_query(root_dir, query, limit, ...):
    # 1. Loads ProxyConfigManager
    # 2. Gets all discovered repositories
    # 3. Creates thread pool for parallel execution
    # 4. Runs query on each repo in parallel
    # 5. Aggregates results with QueryResultAggregator
    # 6. Sorts by global score
    # 7. Formats output
    # ALL OF THIS IS ALREADY DONE - WE JUST CALL IT
```

## Acceptance Criteria
- [x] Directly calls cli_integration._execute_query()
- [x] NO reimplementation of parallel logic
- [x] Results properly parsed from CLI output
- [x] All query parameters passed through
- [x] Maintains exact CLI behavior

## Test Scenarios
1. **Integration**: Verify _execute_query is called correctly
2. **Parameter Pass-through**: All parameters reach CLI function
3. **Result Parsing**: CLI output correctly converted to API format
4. **Parallel Execution**: Confirm parallel execution happens
5. **Error Handling**: CLI errors properly surfaced

## Implementation Notes
**Critical**: This is a THIN wrapper around CLI functionality
- We do NOT reimplement parallel execution
- We do NOT reimplement repository discovery
- We do NOT reimplement result aggregation
- We ONLY parse the CLI output to API format

The entire parallel query infrastructure already exists in the CLI and we reuse it completely.

## Dependencies
- cli_integration._execute_query() function (direct import)
- CLI's complete query infrastructure
- No new query logic implementation

## Estimated Effort
~20 lines for CLI integration and result parsing
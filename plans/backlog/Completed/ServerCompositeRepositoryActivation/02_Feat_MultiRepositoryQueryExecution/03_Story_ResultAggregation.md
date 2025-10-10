# Story: Result Aggregation

## Story Description
Ensure proper result ordering and formatting from multi-repository queries, leveraging CLI's QueryResultAggregator for consistent behavior.

## Business Context
**Success Criteria**: "confirm matches from multiple underlying repos are coming back, in the right order" [Phase 3]
**Requirement**: Results must be globally sorted by relevance score across all repositories

## Technical Implementation

### Result Format Enhancement
```python
class CompositeQueryResult(BaseModel):
    """Extended result for composite queries"""
    repository: str        # User alias of composite repo
    source_repo: str      # Which component repo this came from
    file_path: str
    score: float
    content: Optional[str]
    line_number: Optional[int]

    class Config:
        schema_extra = {
            "example": {
                "repository": "my-composite-project",
                "source_repo": "backend-api",  # Component repo identifier
                "file_path": "src/auth/login.py",
                "score": 0.95,
                "content": "def authenticate_user(..."
            }
        }
```

### Aggregation Verification
```python
class SemanticQueryManager:
    def _format_composite_results(
        self,
        cli_results: str,
        composite_alias: str,
        repo_path: Path
    ) -> List[CompositeQueryResult]:
        """Format aggregated results from CLI output"""

        # The CLI already aggregated and sorted by global score
        # We just parse and enhance with metadata
        results = []

        # Get component repo mapping
        proxy_config = ProxyConfigManager(repo_path)
        discovered_repos = proxy_config.get_discovered_repos()

        for line in cli_results.strip().split('\n'):
            if not line:
                continue

            # Parse CLI format: [repo_name] score: 0.95 - path/to/file.py
            match = re.match(r'\[([^\]]+)\] score: ([\d.]+) - (.+)', line)
            if match:
                source_repo, score, file_path = match.groups()

                results.append(CompositeQueryResult(
                    repository=composite_alias,
                    source_repo=source_repo,
                    file_path=file_path,
                    score=float(score),
                    content=self._get_snippet(repo_path / source_repo / file_path)
                ))

        # Results are ALREADY sorted by CLI's QueryResultAggregator
        # DO NOT RE-SORT - maintain CLI's ordering
        return results
```

### Global Score Ordering (Already Done by CLI)
```python
# From CLI's QueryResultAggregator (WE DON'T REIMPLEMENT):
class QueryResultAggregator:
    def aggregate_results(self, all_results):
        # 1. Combines results from all repos
        # 2. Sorts by score descending (global ordering)
        # 3. Applies limit
        # 4. Returns ordered list
        # THIS IS ALREADY DONE BY _execute_query()
```

### Response Structure
```json
{
  "results": [
    {
      "repository": "my-fullstack-app",
      "source_repo": "backend",
      "file_path": "src/auth/jwt.py",
      "score": 0.98
    },
    {
      "repository": "my-fullstack-app",
      "source_repo": "frontend",
      "file_path": "src/api/auth.js",
      "score": 0.94
    },
    {
      "repository": "my-fullstack-app",
      "source_repo": "backend",
      "file_path": "src/models/user.py",
      "score": 0.87
    }
  ]
}
```

## Acceptance Criteria
- [x] Results include source_repo identifier for each match
- [x] Global ordering by score is preserved from CLI
- [x] Results from all component repos are included
- [x] Repository field shows composite alias
- [x] No re-sorting of CLI's already-aggregated results

## Test Scenarios
1. **Multi-Source**: Results from 3+ different component repos
2. **Score Ordering**: Verify global score ordering maintained
3. **Source Attribution**: Each result correctly identifies source repo
4. **Empty Components**: Handle repos with no matching results
5. **Score Distribution**: Mixed scores properly interleaved

## Implementation Notes
- CLI's QueryResultAggregator already handles all aggregation
- We only parse and format for API response
- DO NOT re-implement sorting or aggregation logic
- Preserve exact ordering from CLI output

## Dependencies
- CLI's QueryResultAggregator (via _execute_query)
- ProxyConfigManager for repository mapping
- Existing result formatting patterns

## Estimated Effort
~15 lines for result formatting and metadata enhancement
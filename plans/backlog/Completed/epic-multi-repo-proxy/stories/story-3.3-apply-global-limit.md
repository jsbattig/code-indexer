# Story: Apply Global Limit to Merged Results

## Story ID: STORY-3.3
## Feature: FEAT-003 (Query Result Aggregation)
## Priority: P0 - Must Have
## Size: Small

## User Story
**As a** developer limiting search results
**I want to** `--limit` to apply to the final merged results
**So that** I get the top N results across all repositories

## Conversation Context
**Citation**: "--limit 10 means 10 total! so you will do --limit 10 on each subrepo, but only present the top 10 on the final result"

**Citation**: "Interleaved by score I think it's better so we keep the order of most relevant results on top."

## Acceptance Criteria
- [ ] `--limit N` parameter forwards same value to each repository query
- [ ] Each repository executes with `--limit N` to get its top results
- [ ] After merging and sorting, limit N applied to final result set
- [ ] Final output shows exactly N results total (or fewer if insufficient matches)
- [ ] `--limit 10` returns 10 total results, NOT 10 per repository
- [ ] No limit (or limit=0) returns all merged results
- [ ] Limit applied AFTER sorting by score, ensuring top N by relevance

## Technical Implementation

### 1. Limit Parameter Forwarding
```python
# proxy/proxy_query_executor.py
class ProxyQueryExecutor:
    """Execute queries with proper limit semantics"""

    def execute_query(
        self,
        query: str,
        limit: int = 10,
        **kwargs
    ) -> List[QueryResult]:
        """
        Execute query across repositories with global limit semantics.

        Args:
            query: Search query string
            limit: TOTAL number of results to return (not per-repo)

        Returns:
            Top N results across all repositories, sorted by score
        """
        # Step 1: Execute with same limit on each repository
        # This ensures we get top candidates from each repo
        repository_outputs = self._execute_on_repositories(
            query=query,
            limit=limit,  # Same limit for all repos
            **kwargs
        )

        # Step 2: Parse results from each repository
        repository_results = self._parse_all_outputs(repository_outputs)

        # Step 3: Merge and sort all results by score
        merger = QueryResultMerger()
        merged_results = merger.merge_and_sort(repository_results)

        # Step 4: Apply global limit to final merged set
        if limit and limit > 0:
            return merged_results[:limit]
        else:
            return merged_results
```

### 2. Per-Repository Query Execution
```python
def _execute_on_repositories(
    self,
    query: str,
    limit: int,
    **kwargs
) -> Dict[str, str]:
    """
    Execute query on each repository with the specified limit.

    Args:
        query: Search query
        limit: Limit to pass to each repository

    Returns:
        Map of repo_path -> query output
    """
    repository_outputs = {}

    for repo_path in self.config.discovered_repos:
        try:
            # Build command with limit
            cmd = self._build_query_command(
                repo_path=repo_path,
                query=query,
                limit=limit,
                **kwargs
            )

            # Execute query
            output = self._execute_command(cmd, cwd=repo_path)
            repository_outputs[repo_path] = output

        except Exception as e:
            logger.error(f"Query failed for {repo_path}: {e}")
            repository_outputs[repo_path] = None

    return repository_outputs
```

### 3. Command Builder with Limit
```python
def _build_query_command(
    self,
    repo_path: str,
    query: str,
    limit: int,
    **kwargs
) -> List[str]:
    """Build cidx query command with limit parameter"""
    cmd = ['cidx', 'query', query]

    # Add limit parameter
    if limit and limit > 0:
        cmd.extend(['--limit', str(limit)])

    # Add other options
    if kwargs.get('quiet'):
        cmd.append('--quiet')
    if kwargs.get('language'):
        cmd.extend(['--language', kwargs['language']])
    if kwargs.get('path'):
        cmd.extend(['--path', kwargs['path']])

    return cmd
```

### 4. Global Limit Application
```python
class GlobalLimitApplicator:
    """Apply global limit to merged results"""

    @staticmethod
    def apply_limit(
        results: List[QueryResult],
        limit: Optional[int]
    ) -> List[QueryResult]:
        """
        Apply global limit to final result set.

        Args:
            results: Merged and sorted results
            limit: Maximum number of results (None = no limit)

        Returns:
            Top N results or all results if limit is None
        """
        if limit is None or limit <= 0:
            return results

        return results[:limit]
```

### 5. Limit Validation
```python
def validate_limit(limit: Optional[int]) -> int:
    """
    Validate and normalize limit parameter.

    Args:
        limit: User-provided limit value

    Returns:
        Validated limit (default 10 if None)

    Raises:
        ValueError: If limit is negative
    """
    if limit is None:
        return 10  # Default limit

    if limit < 0:
        raise ValueError(f"Limit must be non-negative, got {limit}")

    if limit == 0:
        return None  # No limit

    return limit
```

### 6. Result Count Reporting
```python
def report_result_counts(
    repository_counts: Dict[str, int],
    final_count: int,
    limit: int
) -> None:
    """
    Report result counts for transparency.

    Example output:
        Found 45 total matches across 3 repositories:
          - backend/auth: 20 matches
          - backend/user: 15 matches
          - frontend/web: 10 matches

        Showing top 10 results (by relevance score)
    """
    total_matches = sum(repository_counts.values())

    print(f"Found {total_matches} total matches across {len(repository_counts)} repositories:")
    for repo_path, count in sorted(repository_counts.items()):
        print(f"  - {repo_path}: {count} matches")

    print(f"\nShowing top {final_count} results (by relevance score)")
```

## Testing Scenarios

### Unit Tests
1. **Test limit forwarding**
   ```python
   def test_limit_forwarded_to_repos():
       executor = ProxyQueryExecutor(proxy_root)

       # Mock command execution
       with patch.object(executor, '_execute_command') as mock_exec:
           executor.execute_query("test", limit=10)

           # Verify each repo got --limit 10
           for call in mock_exec.call_args_list:
               cmd = call[0][0]
               assert '--limit' in cmd
               assert '10' in cmd
   ```

2. **Test global limit application**
   ```python
   def test_apply_global_limit():
       # Create 30 results (10 from each of 3 repos)
       results = create_test_results(repo_count=3, per_repo=10)

       merger = QueryResultMerger()
       merged = merger.merge_and_sort(results)

       # Apply limit of 10
       limited = GlobalLimitApplicator.apply_limit(merged, limit=10)

       # Should have exactly 10 results
       assert len(limited) == 10

       # Should be top 10 by score
       assert all(limited[i].score >= limited[i+1].score for i in range(9))
   ```

3. **Test no limit**
   ```python
   def test_no_limit():
       results = create_test_results(repo_count=3, per_repo=10)

       merger = QueryResultMerger()
       merged = merger.merge_and_sort(results)

       # Apply no limit (None or 0)
       unlimited = GlobalLimitApplicator.apply_limit(merged, limit=None)

       # Should return all results
       assert len(unlimited) == 30
   ```

4. **Test limit exceeds available results**
   ```python
   def test_limit_exceeds_results():
       # Only 5 total results
       results = create_test_results(repo_count=2, per_repo=2)
       merged = QueryResultMerger().merge_and_sort(results)

       # Request 10 results
       limited = GlobalLimitApplicator.apply_limit(merged, limit=10)

       # Should return only available results (4)
       assert len(limited) == 4
   ```

### Integration Tests
1. **Test full query workflow with limit**
   ```python
   def test_full_query_with_limit():
       # Setup proxy with 3 repos
       proxy_root = setup_test_proxy_with_repos(3)

       # Index each repo with different content
       index_test_content(proxy_root)

       # Execute query with limit
       executor = ProxyQueryExecutor(proxy_root)
       results = executor.execute_query("function", limit=10)

       # Verify exactly 10 results returned
       assert len(results) == 10

       # Verify results sorted by score
       for i in range(len(results) - 1):
           assert results[i].score >= results[i + 1].score
   ```

2. **Test limit semantics**
   ```bash
   # Setup: 3 repos with 20 matches each
   # Total: 60 potential matches

   # Query with --limit 10
   cidx query "authentication" --limit 10

   # Expected: Exactly 10 results
   # From: Mix of all 3 repos (interleaved by score)
   # Not: 10 from each repo (30 total)
   ```

3. **Test limit parameter variations**
   - `--limit 1`: Single result
   - `--limit 10`: Default behavior
   - `--limit 100`: Large limit
   - No `--limit`: Use default (10)
   - `--limit 0`: Return all results

### Edge Cases
1. **Zero limit**
   ```python
   def test_zero_limit():
       results = create_test_results(repo_count=2, per_repo=5)
       merged = QueryResultMerger().merge_and_sort(results)

       # Limit of 0 means no limit
       unlimited = GlobalLimitApplicator.apply_limit(merged, limit=0)
       assert len(unlimited) == 10
   ```

2. **Negative limit**
   ```python
   def test_negative_limit():
       with pytest.raises(ValueError):
           validate_limit(-1)
   ```

3. **All repositories return no results**
   ```python
   def test_all_repos_empty():
       executor = ProxyQueryExecutor(proxy_root)
       results = executor.execute_query("nonexistent", limit=10)

       assert results == []
   ```

## Error Handling

### Error Cases
1. **Invalid Limit Value**
   - Message: "Limit must be non-negative integer"
   - Exit code: 1
   - **Validation**: Check before execution

2. **Insufficient Results**
   - Behavior: Return available results (don't error)
   - Message: "Showing X results (requested Y)"
   - **Graceful**: Don't fail if fewer matches than limit

## Performance Considerations

### Optimization Strategies
1. **Per-Repository Limit**
   - Each repo executes with same limit
   - Reduces unnecessary result collection
   - Balances breadth of search with performance

2. **Early Termination**
   - Could optimize by dynamically adjusting per-repo limits
   - Future enhancement: adaptive limit allocation

3. **Memory Efficiency**
   - Only keep top N in memory during merge
   - Use heap for very large result sets
   - Current approach fine for typical limits (<1000)

### Trade-offs
```
Strategy: Pass limit to each repo
  Pros:
    - Ensures each repo contributes top candidates
    - Balanced representation across repos
    - Simple implementation

  Cons:
    - May collect more results than needed
    - Example: 3 repos × limit 10 = 30 results parsed, 10 returned

  Alternative: Total budget allocation
    - Divide limit among repos
    - More complex logic
    - May miss high-scoring results from some repos
```

## Dependencies
- Query result parser
- Result merger and sorter
- Command execution infrastructure
- Logging framework

## Documentation Updates
- Document limit semantics clearly
- Explain difference from per-repo limits
- Provide examples showing behavior
- Include performance considerations
- Clarify default limit value

## Future Enhancements
- Adaptive per-repository limit allocation
- Configurable limit strategies (balanced vs optimized)
- Result count estimation before full execution
- Streaming results for very large limits

# Story: Merge and Sort Query Results by Score

## Story ID: STORY-3.2
## Feature: FEAT-003 (Query Result Aggregation)
## Priority: P0 - Must Have
## Size: Medium

## User Story
**As a** developer viewing search results
**I want to** see results sorted by relevance regardless of repository
**So that** the most relevant matches appear first

## Conversation Context
**Citation**: "Interleaved by score I think it's better so we keep the order of most relevant results on top. After all, we provide full path, so 'repo' doesn't matter."

**Citation**: "--limit 10 means 10 total! so you will do --limit 10 on each subrepo, but only present the top 10 on the final result"

## Acceptance Criteria
- [ ] Results from all repositories merged into single collection
- [ ] Merged results sorted by score in descending order (highest first)
- [ ] Repository source does NOT affect sort order - only relevance score matters
- [ ] Results are interleaved by score, not grouped by repository
- [ ] Ties in score maintain stable ordering (preserve original order from parsing)
- [ ] Sorting happens AFTER collecting all results from all repositories
- [ ] Full paths preserved to identify result origin

## Technical Implementation

### 1. Result Merger and Sorter
```python
# proxy/query_result_merger.py
@dataclass
class QueryResult:
    score: float
    file_path: str
    line_number: Optional[int]
    context: Optional[str]
    repository: str
    match_type: str

class QueryResultMerger:
    """Merge and sort query results from multiple repositories"""

    def merge_and_sort(
        self,
        repository_results: Dict[str, List[QueryResult]]
    ) -> List[QueryResult]:
        """
        Merge results from all repositories and sort by score.

        Args:
            repository_results: Map of repo_path -> list of QueryResult objects

        Returns:
            Single sorted list with results interleaved by score
        """
        # Collect all results from all repositories
        all_results = []
        for repo_path, results in repository_results.items():
            all_results.extend(results)

        # Sort by score descending (highest scores first)
        # Use stable sort to preserve order for equal scores
        all_results.sort(key=lambda r: r.score, reverse=True)

        return all_results
```

### 2. Score-Based Interleaving
```python
def interleave_by_score(
    repository_results: Dict[str, List[QueryResult]]
) -> List[QueryResult]:
    """
    Interleave results from multiple repositories based on score.
    This produces a unified result set ordered by relevance.

    Example:
        Repo A: [0.95, 0.85, 0.75]
        Repo B: [0.92, 0.88, 0.70]
        Result: [0.95(A), 0.92(B), 0.88(B), 0.85(A), 0.75(A), 0.70(B)]
    """
    all_results = []

    # Collect all results
    for repo_path, results in repository_results.items():
        for result in results:
            all_results.append(result)

    # Sort by score (descending)
    all_results.sort(key=lambda r: r.score, reverse=True)

    return all_results
```

### 3. Integration with Query Executor
```python
# proxy/proxy_query_executor.py
class ProxyQueryExecutor:
    """Execute queries across multiple repositories with result merging"""

    def execute_query(
        self,
        query: str,
        limit: int = 10,
        **kwargs
    ) -> List[QueryResult]:
        """
        Execute query across all managed repositories.
        Returns merged and sorted results.
        """
        # Execute query on each repository
        repository_outputs = self._execute_on_repositories(
            query=query,
            limit=limit,
            **kwargs
        )

        # Parse results from each repository
        parser = QueryResultParser()
        repository_results = {}

        for repo_path, output in repository_outputs.items():
            if output and not self._is_error(output):
                results = parser.parse_repository_output(output, repo_path)
                repository_results[repo_path] = results

        # Merge and sort by score
        merger = QueryResultMerger()
        merged_results = merger.merge_and_sort(repository_results)

        # Apply global limit (top N across all repos)
        return merged_results[:limit] if limit else merged_results
```

### 4. Stable Sort for Ties
```python
def sort_with_stable_ties(results: List[QueryResult]) -> List[QueryResult]:
    """
    Sort results by score with stable ordering for ties.
    Results with equal scores maintain their original order.
    """
    # Python's sort is stable by default
    results.sort(key=lambda r: r.score, reverse=True)
    return results
```

### 5. Repository-Agnostic Sorting
```python
def verify_repository_agnostic_sort(results: List[QueryResult]) -> bool:
    """
    Verify that sorting is based only on score, not repository.
    Returns True if results are properly sorted by score only.
    """
    for i in range(len(results) - 1):
        current_score = results[i].score
        next_score = results[i + 1].score

        # Scores should be in descending order
        if current_score < next_score:
            return False

    return True
```

### 6. Result Quality Validation
```python
class ResultValidator:
    """Validate merged and sorted results"""

    @staticmethod
    def validate_sort_order(results: List[QueryResult]) -> None:
        """Ensure results are properly sorted by score"""
        for i in range(len(results) - 1):
            if results[i].score < results[i + 1].score:
                raise ResultSortError(
                    f"Results not properly sorted at index {i}: "
                    f"{results[i].score} < {results[i + 1].score}"
                )

    @staticmethod
    def validate_interleaving(results: List[QueryResult]) -> bool:
        """
        Check if results are properly interleaved (not grouped by repo).
        Returns True if at least one repository transition exists in top results.
        """
        if len(results) < 2:
            return True

        # Check if repositories change in the result list
        repos_seen = set()
        for result in results[:10]:  # Check top 10
            repos_seen.add(result.repository)

        # Proper interleaving means multiple repos in top results
        return len(repos_seen) > 1 or len(results) < 10
```

## Testing Scenarios

### Unit Tests
1. **Test basic merge and sort**
   ```python
   def test_merge_and_sort_by_score():
       repo_a_results = [
           QueryResult(score=0.95, file_path="a/file1.py", repository="repo-a"),
           QueryResult(score=0.75, file_path="a/file2.py", repository="repo-a"),
       ]
       repo_b_results = [
           QueryResult(score=0.92, file_path="b/file1.py", repository="repo-b"),
           QueryResult(score=0.70, file_path="b/file2.py", repository="repo-b"),
       ]

       merger = QueryResultMerger()
       merged = merger.merge_and_sort({
           "repo-a": repo_a_results,
           "repo-b": repo_b_results
       })

       # Verify score order: 0.95, 0.92, 0.75, 0.70
       assert merged[0].score == 0.95
       assert merged[1].score == 0.92
       assert merged[2].score == 0.75
       assert merged[3].score == 0.70

       # Verify interleaving (A, B, A, B pattern)
       assert merged[0].repository == "repo-a"
       assert merged[1].repository == "repo-b"
   ```

2. **Test repository-agnostic sorting**
   ```python
   def test_repository_agnostic_sort():
       # Create results where repo-b has highest score
       results = {
           "repo-a": [QueryResult(score=0.80, file_path="a.py", repository="repo-a")],
           "repo-b": [QueryResult(score=0.95, file_path="b.py", repository="repo-b")],
           "repo-c": [QueryResult(score=0.85, file_path="c.py", repository="repo-c")]
       }

       merger = QueryResultMerger()
       merged = merger.merge_and_sort(results)

       # Top result should be from repo-b (highest score)
       assert merged[0].repository == "repo-b"
       assert merged[0].score == 0.95
   ```

3. **Test stable sort for ties**
   ```python
   def test_stable_sort_ties():
       results = {
           "repo-a": [
               QueryResult(score=0.90, file_path="a1.py", repository="repo-a"),
               QueryResult(score=0.90, file_path="a2.py", repository="repo-a"),
           ],
           "repo-b": [
               QueryResult(score=0.90, file_path="b1.py", repository="repo-b"),
           ]
       }

       merger = QueryResultMerger()
       merged = merger.merge_and_sort(results)

       # All have same score - should maintain original order
       assert all(r.score == 0.90 for r in merged)
       # Original order preserved
       assert merged[0].file_path == "a1.py"
       assert merged[1].file_path == "a2.py"
       assert merged[2].file_path == "b1.py"
   ```

4. **Test single repository**
   ```python
   def test_single_repository_merge():
       results = {
           "repo-a": [
               QueryResult(score=0.95, file_path="file1.py", repository="repo-a"),
               QueryResult(score=0.85, file_path="file2.py", repository="repo-a"),
           ]
       }

       merger = QueryResultMerger()
       merged = merger.merge_and_sort(results)

       assert len(merged) == 2
       assert merged[0].score == 0.95
       assert merged[1].score == 0.85
   ```

### Integration Tests
1. **Test full query execution with merging**
   ```python
   def test_proxy_query_with_merge():
       # Setup proxy with multiple repos
       proxy_root = setup_test_proxy()

       # Execute query
       executor = ProxyQueryExecutor(proxy_root)
       results = executor.execute_query("authentication", limit=10)

       # Verify results sorted by score
       for i in range(len(results) - 1):
           assert results[i].score >= results[i + 1].score

       # Verify total limit applied
       assert len(results) <= 10
   ```

2. **Test interleaving with real data**
   - Index multiple repositories with different content
   - Execute query that matches across repos
   - Verify results interleaved by score, not grouped by repo

3. **Test large result sets**
   - 100+ results from each of 5 repositories
   - Verify efficient sorting
   - Confirm correct top-N selection

### Edge Cases
1. **Empty repository results**
   ```python
   def test_merge_with_empty_repos():
       results = {
           "repo-a": [QueryResult(score=0.95, file_path="a.py", repository="repo-a")],
           "repo-b": [],  # No results
           "repo-c": [QueryResult(score=0.85, file_path="c.py", repository="repo-c")]
       }

       merger = QueryResultMerger()
       merged = merger.merge_and_sort(results)

       assert len(merged) == 2
   ```

2. **All repositories empty**
   ```python
   def test_merge_all_empty():
       results = {"repo-a": [], "repo-b": [], "repo-c": []}

       merger = QueryResultMerger()
       merged = merger.merge_and_sort(results)

       assert merged == []
   ```

3. **Identical scores across all results**
   - All results have score 0.90
   - Verify stable sort maintains order
   - Check no repository bias introduced

## Error Handling

### Error Cases
1. **Invalid Score Values**
   - Behavior: Skip results with invalid scores
   - Logging: Warning with details
   - **Continue**: Don't fail entire merge

2. **Missing Repository Field**
   - Behavior: Use "unknown" as repository
   - Logging: Warning about missing field
   - **Preserve result**: Don't discard

3. **Sort Validation Failure**
   - Behavior: Log error, return unsorted
   - **Fallback**: Better to return results than fail

## Performance Considerations

### Optimization Strategies
1. **Efficient Sorting**
   - Python's Timsort is O(n log n)
   - Optimal for partially sorted data
   - Stable sort with no overhead

2. **Memory Management**
   - Stream processing for very large result sets
   - Consider generator-based merging for 1000+ results
   - Limit memory footprint

3. **Early Termination**
   - If only top 10 needed, consider heap-based selection
   - For small limits, heap might be faster than full sort

### Performance Benchmarks
```python
def benchmark_merge_performance():
    # Test with varying sizes
    sizes = [10, 100, 1000, 10000]
    repo_counts = [2, 5, 10, 20]

    for size in sizes:
        for repo_count in repo_counts:
            # Generate test data
            results = generate_test_results(size, repo_count)

            # Measure merge time
            start = time.time()
            merged = merger.merge_and_sort(results)
            elapsed = time.time() - start

            print(f"Size: {size}, Repos: {repo_count}, Time: {elapsed:.3f}s")
```

## Dependencies
- `dataclasses` for QueryResult structure
- Python's built-in `sort()` for stable sorting
- Logging framework for diagnostics
- Type hints for clarity

## Documentation Updates
- Document interleaving behavior
- Explain score-based sorting
- Provide examples of merged output
- Include performance characteristics
- Clarify repository-agnostic approach

## Future Enhancements
- Consider secondary sort by file path for ties
- Add configurable sort strategies (by repo, by path, etc.)
- Support sorting by other metadata (recency, file type)
- Implement custom scoring algorithms

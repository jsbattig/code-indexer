# Story: Preserve Repository Context in Results

## Story ID: STORY-3.4
## Feature: FEAT-003 (Query Result Aggregation)
## Priority: P0 - Must Have
## Size: Small

## User Story
**As a** developer reviewing search results
**I want to** see which repository each result comes from
**So that** I can navigate to the correct project

## Conversation Context
**Citation**: "After all, we provide full path, so 'repo' doesn't matter."

**Citation**: "Interleaved by score I think it's better so we keep the order of most relevant results on top. After all, we provide full path, so 'repo' doesn't matter."

## Acceptance Criteria
- [ ] Each result displays which repository it originated from
- [ ] File paths include repository identifier in the path
- [ ] Repository information clearly visible in output
- [ ] Full paths allow navigation to correct file location
- [ ] Repository context preserved through parsing, merging, and sorting
- [ ] Output format distinguishes between repositories visually
- [ ] Paths are absolute or relative to proxy root (not relative to repo root)

## Technical Implementation

### 1. Repository Context in Data Structure
```python
# proxy/query_result.py
@dataclass
class QueryResult:
    """Query result with repository context"""
    score: float
    file_path: str              # Path relative to repository root
    line_number: Optional[int]
    context: Optional[str]
    repository: str             # Repository path (relative to proxy root)
    match_type: str

    @property
    def full_path(self) -> str:
        """
        Full path from proxy root.
        Combines repository path with file path.
        """
        return str(Path(self.repository) / self.file_path)

    def format_for_display(self) -> str:
        """
        Format result for user display with repository context.

        Example output:
            Score: 0.95 | backend/auth-service/src/auth/login.py:45
        """
        path_with_line = f"{self.full_path}:{self.line_number}" if self.line_number else self.full_path
        return f"Score: {self.score:.2f} | {path_with_line}"
```

### 2. Path Qualification During Parsing
```python
# proxy/query_result_parser.py
class QueryResultParser:
    """Parse query results and preserve repository context"""

    def parse_repository_output(
        self,
        output: str,
        repo_path: str
    ) -> List[QueryResult]:
        """
        Parse query output and associate with repository.

        Args:
            output: Raw query output from repository
            repo_path: Repository path (relative to proxy root)

        Returns:
            List of QueryResult objects with repository field set
        """
        results = []

        for line in output.split('\n'):
            if match := self._parse_result_line(line):
                result = QueryResult(
                    score=match['score'],
                    file_path=match['file_path'],  # Relative to repo
                    line_number=match.get('line_number'),
                    context=match.get('context'),
                    repository=repo_path,  # Preserve repository context
                    match_type=match.get('match_type', 'unknown')
                )
                results.append(result)

        return results
```

### 3. Result Formatting with Repository Info
```python
# proxy/result_formatter.py
class ResultFormatter:
    """Format query results with repository context"""

    def format_results(
        self,
        results: List[QueryResult],
        show_context: bool = True
    ) -> str:
        """
        Format results for console output with repository information.

        Args:
            results: List of QueryResult objects
            show_context: Whether to include code context

        Returns:
            Formatted string for display
        """
        output_lines = []

        for result in results:
            # Main result line with full path
            output_lines.append(result.format_for_display())

            # Optional context
            if show_context and result.context:
                context_lines = result.context.split('\n')
                for context_line in context_lines:
                    output_lines.append(f"  {context_line}")

            # Add blank line between results
            output_lines.append("")

        return '\n'.join(output_lines)
```

### 4. Repository Identification in Output
```python
def format_with_repository_header(
    results: List[QueryResult]
) -> str:
    """
    Format results grouped by repository with headers.

    Example output:
        === backend/auth-service ===
        Score: 0.95 | backend/auth-service/src/auth/login.py:45
        Score: 0.85 | backend/auth-service/src/models/user.py:23

        === frontend/web-app ===
        Score: 0.92 | frontend/web-app/src/api/auth.js:12
    """
    output_lines = []
    current_repo = None

    for result in results:
        # Add repository header when changing repos
        if result.repository != current_repo:
            if current_repo is not None:
                output_lines.append("")  # Blank line between repos
            output_lines.append(f"=== {result.repository} ===")
            current_repo = result.repository

        # Add result
        output_lines.append(result.format_for_display())

        if result.context:
            for line in result.context.split('\n'):
                output_lines.append(f"  {line}")

    return '\n'.join(output_lines)
```

### 5. Full Path Construction
```python
class PathQualifier:
    """Qualify paths with repository information"""

    def __init__(self, proxy_root: Path):
        self.proxy_root = proxy_root

    def qualify_result_path(
        self,
        result: QueryResult
    ) -> str:
        """
        Construct full path from proxy root.

        Args:
            result: QueryResult with repository and file_path

        Returns:
            Full path that can be used to open file
        """
        return str(self.proxy_root / result.repository / result.file_path)

    def create_absolute_path(
        self,
        result: QueryResult
    ) -> Path:
        """
        Create absolute filesystem path for result.

        Returns:
            Absolute path to file
        """
        return (self.proxy_root / result.repository / result.file_path).resolve()
```

### 6. Repository Context Preservation
```python
def preserve_context_through_pipeline(
    repository_outputs: Dict[str, str]
) -> List[QueryResult]:
    """
    Process results through full pipeline while preserving context.

    Pipeline stages:
    1. Parse (associate with repository)
    2. Merge (combine all repositories)
    3. Sort (by score)
    4. Format (with full paths)

    Repository context maintained throughout.
    """
    parser = QueryResultParser()
    merger = QueryResultMerger()

    # Stage 1: Parse with repository association
    repository_results = {}
    for repo_path, output in repository_outputs.items():
        results = parser.parse_repository_output(output, repo_path)
        repository_results[repo_path] = results
        # Each result now has 'repository' field set

    # Stage 2: Merge (preserves repository field)
    merged = merger.merge_and_sort(repository_results)

    # Stage 3: Sort (repository field unchanged)
    # Already sorted by merger

    # Stage 4: Results retain full repository context
    return merged
```

## Testing Scenarios

### Unit Tests
1. **Test repository context preservation**
   ```python
   def test_preserve_repository_context():
       parser = QueryResultParser()
       output = "Score: 0.95 | src/auth.py:45"
       repo_path = "backend/auth-service"

       results = parser.parse_repository_output(output, repo_path)

       assert len(results) == 1
       assert results[0].repository == "backend/auth-service"
       assert results[0].file_path == "src/auth.py"
   ```

2. **Test full path construction**
   ```python
   def test_full_path_construction():
       result = QueryResult(
           score=0.95,
           file_path="src/auth.py",
           line_number=45,
           context=None,
           repository="backend/auth-service",
           match_type="code"
       )

       assert result.full_path == "backend/auth-service/src/auth.py"
   ```

3. **Test path qualification**
   ```python
   def test_path_qualification():
       proxy_root = Path("/home/dev/projects")
       qualifier = PathQualifier(proxy_root)

       result = QueryResult(
           score=0.95,
           file_path="src/auth.py",
           repository="backend/auth",
           ...
       )

       full_path = qualifier.qualify_result_path(result)
       assert full_path == "/home/dev/projects/backend/auth/src/auth.py"
   ```

4. **Test context preservation through merge**
   ```python
   def test_context_preserved_through_merge():
       results_a = [
           QueryResult(score=0.95, file_path="a.py", repository="repo-a", ...)
       ]
       results_b = [
           QueryResult(score=0.85, file_path="b.py", repository="repo-b", ...)
       ]

       merger = QueryResultMerger()
       merged = merger.merge_and_sort({
           "repo-a": results_a,
           "repo-b": results_b
       })

       # Verify repository context preserved
       assert merged[0].repository == "repo-a"
       assert merged[1].repository == "repo-b"
   ```

### Integration Tests
1. **Test full workflow with repository context**
   ```python
   def test_full_workflow_preserves_context():
       # Setup proxy with multiple repos
       proxy_root = setup_test_proxy()

       # Execute query
       executor = ProxyQueryExecutor(proxy_root)
       results = executor.execute_query("authentication", limit=10)

       # Verify all results have repository context
       for result in results:
           assert result.repository is not None
           assert result.repository != ""
           assert result.full_path.startswith(result.repository)
   ```

2. **Test output formatting**
   ```bash
   # Execute query in proxy mode
   cd proxy-root
   cidx query "authentication" --limit 10

   # Expected output:
   # Score: 0.95 | backend/auth-service/src/auth/login.py:45
   #   def authenticate_user(username, password):
   #
   # Score: 0.92 | frontend/web-app/src/api/auth.js:23
   #   async function login(credentials) {

   # Verify paths include repository prefix
   ```

3. **Test file navigation from results**
   - Parse output to extract full paths
   - Verify paths exist on filesystem
   - Open files using extracted paths

### Edge Cases
1. **Nested repository paths**
   ```python
   def test_nested_repo_paths():
       result = QueryResult(
           repository="services/backend/auth",
           file_path="src/login.py",
           ...
       )

       expected = "services/backend/auth/src/login.py"
       assert result.full_path == expected
   ```

2. **Repository with special characters**
   ```python
   def test_special_chars_in_repo():
       result = QueryResult(
           repository="my-project-2.0/backend",
           file_path="src/auth.py",
           ...
       )

       # Should handle hyphens, dots, etc.
       assert result.full_path == "my-project-2.0/backend/src/auth.py"
   ```

3. **Empty repository name**
   ```python
   def test_empty_repository():
       result = QueryResult(
           repository="",
           file_path="src/auth.py",
           ...
       )

       # Should handle gracefully
       assert result.full_path == "src/auth.py"
   ```

## Error Handling

### Error Cases
1. **Missing Repository Field**
   - Behavior: Use "unknown" as fallback
   - Logging: Warning about missing repository
   - **Continue**: Don't fail result

2. **Invalid Path Construction**
   - Behavior: Log error, return original path
   - **Graceful degradation**: Show what we can

3. **Repository Not Found**
   - Behavior: Include in results anyway
   - Note: Result may have incorrect path
   - **User visibility**: Let user see the issue

## Performance Considerations
- Path construction is lightweight (string concatenation)
- No filesystem access during formatting
- Repository field adds minimal memory overhead
- Path qualification done on-demand, not pre-computed

## Dependencies
- `pathlib.Path` for path operations
- `dataclasses` for QueryResult structure
- String formatting utilities
- Logging framework

## Documentation Updates
- Document full path format
- Explain repository context preservation
- Provide examples of output format
- Include navigation instructions
- Clarify path resolution rules

## Future Enhancements
- Clickable paths in terminal output
- Repository-specific color coding
- Configurable path format (absolute vs relative)
- IDE integration for direct file opening

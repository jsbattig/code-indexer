# Story: Parse Individual Repository Query Results

## Story ID: STORY-3.1
## Feature: FEAT-003 (Query Result Aggregation)
## Priority: P0 - Must Have
## Size: Medium

## User Story
**As a** developer searching across repositories
**I want to** have query results parsed from each repository
**So that** they can be properly merged and sorted

## Conversation Context
**Citation**: "Interleaved by score I think it's better so we keep the order of most relevant results on top. After all, we provide full path, so 'repo' doesn't matter."

**Citation**: "--limit 10 means 10 total! so you will do --limit 10 on each subrepo, but only present the top 10 on the final result"

**Citation**: "Parse individual results from each repo's output. Extract matches with scores and paths"

## Acceptance Criteria
- [ ] Successfully parse query output from each repository
- [ ] Extract score, file path, and match context from output
- [ ] Handle both `--quiet` and verbose output formats
- [ ] Preserve all metadata from original results
- [ ] Gracefully handle malformed or incomplete output
- [ ] Maintain repository association with each result

## Technical Implementation

### 1. Query Output Parser
```python
# proxy/query_result_parser.py
@dataclass
class QueryResult:
    score: float
    file_path: str
    line_number: Optional[int]
    context: Optional[str]
    repository: str
    match_type: str  # 'code', 'comment', 'string', etc.

class QueryResultParser:
    """Parse CIDX query output into structured results"""

    # Expected output patterns
    RESULT_PATTERN = r'Score:\s*([\d.]+)\s*\|\s*(.+?)(?::(\d+))?'
    CONTEXT_PATTERN = r'^\s{2,}(.+)$'

    def parse_repository_output(self, output: str, repo_path: str) -> List[QueryResult]:
        """
        Parse query results from a single repository's output.

        Args:
            output: Raw stdout from cidx query command
            repo_path: Path to repository (for result association)

        Returns:
            List of parsed QueryResult objects
        """
        results = []
        lines = output.strip().split('\n')
        i = 0

        while i < len(lines):
            line = lines[i]

            # Try to match result line
            match = re.match(self.RESULT_PATTERN, line)
            if match:
                score = float(match.group(1))
                file_path = match.group(2)
                line_number = int(match.group(3)) if match.group(3) else None

                # Look for context on next lines
                context_lines = []
                j = i + 1
                while j < len(lines) and re.match(self.CONTEXT_PATTERN, lines[j]):
                    context_lines.append(lines[j].strip())
                    j += 1

                result = QueryResult(
                    score=score,
                    file_path=file_path,
                    line_number=line_number,
                    context='\n'.join(context_lines) if context_lines else None,
                    repository=repo_path,
                    match_type=self._infer_match_type(file_path)
                )
                results.append(result)
                i = j
            else:
                i += 1

        return results
```

### 2. Output Format Handlers
```python
class OutputFormatHandler:
    """Handle different output formats (quiet vs verbose)"""

    @staticmethod
    def detect_format(output: str) -> str:
        """Detect output format based on content patterns"""
        if 'Score:' in output and '|' in output:
            return 'standard'
        elif output.strip() and not 'Error' in output:
            return 'quiet'
        else:
            return 'unknown'

    @staticmethod
    def parse_quiet_format(output: str, repo_path: str) -> List[QueryResult]:
        """Parse --quiet format output"""
        results = []
        for line in output.strip().split('\n'):
            if line and not line.startswith('#'):
                # Quiet format: score | path
                parts = line.split('|', 1)
                if len(parts) == 2:
                    try:
                        score = float(parts[0].strip())
                        file_path = parts[1].strip()
                        results.append(QueryResult(
                            score=score,
                            file_path=file_path,
                            line_number=None,
                            context=None,
                            repository=repo_path,
                            match_type='unknown'
                        ))
                    except ValueError:
                        continue
        return results
```

### 3. Result Aggregator
```python
class QueryResultAggregator:
    """Aggregate and sort results from multiple repositories"""

    def __init__(self):
        self.parser = QueryResultParser()

    def aggregate_results(
        self,
        repository_outputs: Dict[str, str],
        limit: int = 10
    ) -> List[QueryResult]:
        """
        Aggregate results from all repositories and apply limit.

        Args:
            repository_outputs: Map of repo_path -> query output
            limit: Maximum number of results to return

        Returns:
            Sorted and limited list of QueryResult objects
        """
        all_results = []

        for repo_path, output in repository_outputs.items():
            if output and not self._is_error_output(output):
                results = self.parser.parse_repository_output(output, repo_path)
                all_results.extend(results)

        # Sort by score (descending)
        all_results.sort(key=lambda x: x.score, reverse=True)

        # Apply limit
        return all_results[:limit] if limit else all_results

    def _is_error_output(self, output: str) -> bool:
        """Check if output indicates an error"""
        error_indicators = [
            'Error:',
            'Failed to',
            'Cannot connect',
            'No such file',
            'Permission denied'
        ]
        return any(indicator in output for indicator in error_indicators)
```

### 4. Repository Path Resolution
```python
def qualify_result_paths(results: List[QueryResult]) -> List[QueryResult]:
    """
    Qualify file paths with repository information.

    Transforms:
        src/auth.py -> backend/auth-service/src/auth.py
    """
    for result in results:
        if not result.file_path.startswith(result.repository):
            result.file_path = str(Path(result.repository) / result.file_path)
    return results
```

### 5. Error Recovery
```python
class RobustParser:
    """Parser with error recovery for malformed output"""

    def parse_with_fallback(self, output: str, repo_path: str) -> List[QueryResult]:
        """Try multiple parsing strategies"""
        try:
            # Try standard parsing
            return self.parser.parse_repository_output(output, repo_path)
        except Exception as e:
            logger.warning(f"Standard parsing failed: {e}")

            try:
                # Try quiet format
                return OutputFormatHandler.parse_quiet_format(output, repo_path)
            except Exception as e2:
                logger.warning(f"Quiet parsing failed: {e2}")

                # Last resort: extract any score-like patterns
                return self._emergency_parse(output, repo_path)

    def _emergency_parse(self, output: str, repo_path: str) -> List[QueryResult]:
        """Emergency parsing for severely malformed output"""
        results = []
        # Look for any line with a decimal number that might be a score
        pattern = r'(0?\.\d+|\d\.\d+).*?([/\w\-_.]+\.\w+)'
        for match in re.finditer(pattern, output):
            try:
                score = float(match.group(1))
                file_path = match.group(2)
                if 0.0 <= score <= 1.0:  # Sanity check for score
                    results.append(QueryResult(
                        score=score,
                        file_path=file_path,
                        line_number=None,
                        context=None,
                        repository=repo_path,
                        match_type='unknown'
                    ))
            except:
                continue
        return results
```

## Testing Scenarios

### Unit Tests
1. **Test standard output parsing**
   ```python
   output = """
   Score: 0.95 | src/auth/login.py:45
     def authenticate_user(username, password):
       # Authenticate against database

   Score: 0.87 | src/models/user.py:12
     class User(BaseModel):
   """
   results = parser.parse_repository_output(output, "backend")
   assert len(results) == 2
   assert results[0].score == 0.95
   ```

2. **Test quiet format parsing**
   ```python
   quiet_output = """
   0.95 | src/auth/login.py
   0.87 | src/models/user.py
   """
   results = parser.parse_quiet_format(quiet_output, "backend")
   assert len(results) == 2
   ```

3. **Test malformed output handling**
   - Missing scores
   - Incomplete lines
   - Mixed formats
   - Unicode characters

### Integration Tests
1. **Test with real CIDX output**
   - Execute actual query commands
   - Parse real output formats
   - Verify all fields extracted correctly

2. **Test aggregation with multiple repositories**
   - Different output formats per repo
   - Some repos with errors
   - Large result sets

## Error Handling

### Parsing Errors
- Log warning but continue processing
- Skip unparseable lines
- Report parsing statistics in debug mode
- Never crash on malformed input

### Missing Data
- Handle missing context gracefully
- Default line numbers to None
- Preserve partial results

## Performance Considerations
- Use compiled regex patterns
- Stream processing for large outputs
- Efficient sorting algorithms
- Memory-efficient data structures

## Dependencies
- `re` module for pattern matching
- `dataclasses` for result structure
- Logging framework for debugging
- Type hints for clarity

## Documentation Updates
- Document expected output formats
- Provide parsing examples
- Explain fallback strategies
- Include troubleshooting guide
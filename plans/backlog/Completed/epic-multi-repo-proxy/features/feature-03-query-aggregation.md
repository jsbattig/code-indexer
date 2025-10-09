# Feature: Query Result Aggregation

## Feature ID: FEAT-003
## Epic: EPIC-001 (Multi-Repository Proxy Configuration Support)
## Status: Specification
## Priority: P0 (Core Feature)

## Overview

Implement intelligent aggregation of semantic search results from multiple repositories. Unlike other commands that simply concatenate output, the query command requires parsing, merging, and re-sorting results by relevance score to provide a unified search experience.

## User Stories

### Story 3.1: Parse Individual Repository Results
**As a** developer searching across repositories
**I want to** have query results parsed from each repository
**So that** they can be properly merged and sorted

### Story 3.2: Merge and Sort by Score
**As a** developer viewing search results
**I want to** see results sorted by relevance regardless of repository
**So that** the most relevant matches appear first

### Story 3.3: Apply Global Limit
**As a** developer limiting search results
**I want to** `--limit` to apply to the final merged results
**So that** I get the top N results across all repositories

### Story 3.4: Preserve Repository Context
**As a** developer reviewing search results
**I want to** see which repository each result comes from
**So that** I can navigate to the correct project

## Technical Requirements

### Query Result Parsing
- Parse stdout from each repository's query command
- Extract match records with scores and file paths
- Handle various output formats gracefully
- Preserve all metadata from original results

### Merging Strategy
1. Execute query with same `--limit N` on each repository
2. Collect all results from all repositories
3. Parse individual scores and paths
4. Combine into single result set
5. Sort by score (descending)
6. Apply limit to final merged set

**Citation**: "--limit 10 means 10 total! so you will do --limit 10 on each subrepo, but only present the top 10 on the final result"

### Score-Based Interleaving
- Results ordered by relevance score, not repository
- Highest scoring matches appear first regardless of source
- Repository information preserved but not used for sorting

**Citation**: "Interleaved by score I think it's better so we keep the order of most relevant results on top. After all, we provide full path, so 'repo' doesn't matter."

### Output Format
- Display repository-qualified paths
- Maintain consistent score formatting
- Show clear result boundaries
- Preserve original formatting where possible

## Acceptance Criteria

### Story 3.1: Result Parsing
- [ ] Successfully parse query output from each repository
- [ ] Extract score, file path, and match context
- [ ] Handle both `--quiet` and verbose output formats
- [ ] Gracefully handle malformed output

### Story 3.2: Score-Based Sorting
- [ ] All results merged into single collection
- [ ] Results sorted by score in descending order
- [ ] Repository source doesn't affect sort order
- [ ] Ties in score maintain stable ordering

### Story 3.3: Limit Application
- [ ] `--limit N` forwards same limit to each repository
- [ ] Final output shows exactly N results (or fewer if insufficient matches)
- [ ] Top N results selected after merging and sorting
- [ ] Limit of 10 returns 10 total results, not 10 per repo

### Story 3.4: Repository Context
- [ ] Each result shows which repository it came from
- [ ] File paths include repository identifier
- [ ] Repository information clearly visible
- [ ] Full path allows navigation to correct location

## Implementation Notes

### Result Parser Design
```python
class QueryResultParser:
    def parse_repository_output(self, output: str, repo_path: str):
        """Parse query results from a single repository"""
        results = []
        for line in output.split('\n'):
            if match := self._parse_result_line(line):
                match['repository'] = repo_path
                results.append(match)
        return results

    def merge_and_sort(self, all_results: List[Dict]):
        """Merge results from all repositories and sort by score"""
        merged = []
        for repo_results in all_results:
            merged.extend(repo_results)

        # Sort by score descending
        merged.sort(key=lambda x: x['score'], reverse=True)
        return merged
```

### Query Execution Flow
1. Determine user's limit parameter (default if not specified)
2. Execute query command on each repository with same limit
3. Collect stdout from each execution
4. Parse results from each repository
5. Merge all parsed results
6. Sort by relevance score
7. Apply limit to get top N
8. Format and display final results

### Expected Output Format
```
Score: 0.95 | backend/auth-service/src/auth/login.py:45
  def authenticate_user(username, password):

Score: 0.92 | frontend/web-app/src/api/auth.js:23
  async function login(credentials) {

Score: 0.88 | backend/user-service/src/models/user.py:67
  class UserAuthentication(BaseModel):
```

## Dependencies
- Query command output parser
- Result formatting utilities
- Subprocess execution for queries
- Score comparison logic

## Testing Requirements

### Unit Tests
- Result line parsing with various formats
- Score extraction and validation
- Merging logic with multiple result sets
- Sorting algorithm correctness
- Limit application logic

### Integration Tests
- Multi-repository query execution
- Result aggregation with real query outputs
- Limit parameter handling (1, 10, 100, unlimited)
- Empty result handling
- Partial failure scenarios

### Edge Cases
- Repositories with no matches
- Identical scores across repositories
- Malformed output from some repositories
- Very large result sets
- Unicode and special characters in paths

## Performance Considerations

### Memory Management
- Stream processing for large result sets
- Efficient sorting algorithms for many matches
- Avoid holding entire output in memory if possible

### Query Optimization
- Consider capping per-repository limits for efficiency
- Balance between coverage and performance
- Lazy evaluation where possible

## Error Handling

### Parsing Failures
- Skip malformed result lines
- Log parsing errors for debugging
- Continue processing valid results
- Report repositories with parsing issues

### Empty Results
- Handle repositories returning no matches
- Display appropriate message if no results found
- Indicate which repositories were searched

### Output Formatting
- Graceful degradation for unparseable output
- Fallback to raw output if parsing fails completely
- Clear indication of formatting issues
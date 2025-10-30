# Feature: FTS Query Engine

## Summary

Provide a powerful full-text search query engine with fuzzy matching, case sensitivity control, and configurable result presentation that operates on the Tantivy index with sub-5ms latency.

## Problem Statement

Users need fast, flexible text search capabilities beyond semantic understanding. They require exact text matching with typo tolerance, case control, and adjustable context snippets to efficiently find specific code patterns and debug issues.

## Success Criteria

1. **Query Performance:** <5ms P99 latency for text searches
2. **Fuzzy Matching:** Configurable edit distance for typo tolerance
3. **Case Flexibility:** Support both case-sensitive and case-insensitive searches
4. **Context Control:** Adjustable snippet lines (0 to N)
5. **Result Quality:** Exact line/column positions with relevant context

## Scope

### In Scope
- Text search query execution on Tantivy index
- Fuzzy matching with Levenshtein distance
- Case sensitivity control flags
- Configurable snippet extraction
- Result formatting similar to semantic search
- Non-blocking query execution

### Out of Scope
- Index creation (handled by FTS Index Infrastructure)
- Real-time updates (handled by FTS Index Infrastructure)
- API endpoints (handled by Hybrid Search Integration)
- Score merging with semantic results

## Technical Design

### Query Engine Architecture
```python
class FTSQueryEngine:
    def __init__(self, index_path: Path):
        self.index = Index.open(str(index_path))
        self.searcher = self.index.searcher()

    def search(
        self,
        query_text: str,
        case_sensitive: bool = False,
        edit_distance: int = 0,
        snippet_lines: int = 5,
        limit: int = 10,
        language_filter: Optional[str] = None,
        path_filter: Optional[str] = None
    ) -> List[FTSResult]:
        """Execute FTS query with configurable options"""
        pass
```

### Fuzzy Matching Implementation
```python
def build_fuzzy_query(text: str, edit_distance: int) -> Query:
    """Build Tantivy query with fuzzy matching"""
    if edit_distance == 0:
        # Exact match
        return TermQuery(Term.from_field_text("content", text))
    else:
        # Fuzzy match with Levenshtein distance
        return FuzzyTermQuery(
            Term.from_field_text("content", text),
            distance=edit_distance,
            prefix=True  # Optimize with prefix matching
        )
```

### Case Sensitivity Handling
```python
def handle_case_sensitivity(query: str, case_sensitive: bool) -> str:
    """Process query based on case sensitivity setting"""
    if case_sensitive:
        # Use content_raw field for exact case matching
        field = "content_raw"
    else:
        # Use tokenized content field (lowercase normalized)
        field = "content"
        query = query.lower()
    return field, query
```

### Snippet Extraction
```python
class SnippetExtractor:
    def extract(
        self,
        content: str,
        match_position: int,
        snippet_lines: int
    ) -> str:
        """Extract configurable context around match"""
        if snippet_lines == 0:
            return ""  # List mode, no snippet

        lines = content.split('\n')
        match_line = self._position_to_line(match_position, lines)

        start_line = max(0, match_line - snippet_lines)
        end_line = min(len(lines), match_line + snippet_lines + 1)

        snippet = lines[start_line:end_line]
        return '\n'.join(snippet)
```

### Result Formatting
```python
class FTSResultFormatter:
    def format(self, results: List[FTSResult]) -> str:
        """Format results similar to semantic search output"""
        formatted = []
        for i, result in enumerate(results, 1):
            formatted.append(
                f"{i}. {result.path}:{result.line}:{result.column}\n"
                f"   Language: {result.language}\n"
                f"   Match: {result.match_text}\n"
            )
            if result.snippet:
                formatted.append(f"   Context:\n{result.snippet}\n")
        return '\n'.join(formatted)
```

## Stories

| Story # | Title | Priority | Effort |
|---------|-------|----------|--------|
| 01 | Full-Text Search with Configurable Options | MVP | Large |
| 02 | Hybrid Search Execution | Medium | Medium |

## CLI Integration

```bash
# Default semantic search (unchanged)
cidx query "authentication"

# Full-text search
cidx query "authenticate_user" --fts

# Case-sensitive search
cidx query "AuthUser" --fts --case-sensitive

# Fuzzy matching with edit distance 2
cidx query "authentcate" --fts --edit-distance 2

# Minimal output (no snippets)
cidx query "login" --fts --snippet-lines 0

# Extended context
cidx query "error" --fts --snippet-lines 10

# Combined with filters
cidx query "parse" --fts --language python --path-filter "*/tests/*"
```

## Dependencies

- Tantivy index from FTS Index Infrastructure
- Existing result formatting from semantic search
- Language detection from existing codebase
- Path filtering logic from semantic search

## Acceptance Criteria

1. **Query Execution:**
   - Queries complete in <5ms for 40K file codebases
   - Results ranked by relevance
   - Exact match positions provided

2. **Configuration Options:**
   - All flags properly integrated via Click
   - Default values match specification
   - Options combinable without conflicts

3. **Result Quality:**
   - Accurate line/column positions
   - Snippets properly extracted
   - Formatting consistent with semantic search

4. **Error Handling:**
   - Graceful failure if FTS index missing
   - Clear error messages for invalid queries
   - Helpful suggestions for typos

## Conversation References

- **Query Performance:** "<5ms query latency"
- **Fuzzy Matching:** "Levenshtein distance fuzzy matching"
- **Case Control:** "Case sensitivity control"
- **Snippet Configuration:** "Adjustable snippets (0 to N lines context, default ~5)"
- **Result Format:** "results formatted like semantic search"
# Feature: Hybrid Search Integration

## Summary

Extend CIDX Server API and CLI to fully support FTS and hybrid search capabilities, providing programmatic access to all search modes with complete feature parity.

## Problem Statement

API consumers and CLI users need comprehensive access to FTS and hybrid search capabilities. The server must expose all search modes through RESTful endpoints while the CLI requires updated documentation and command syntax to reflect new capabilities.

## Success Criteria

1. **API Feature Parity:** All CLI search options available via API
2. **Backwards Compatibility:** Existing API endpoints continue working unchanged
3. **Documentation Updates:** CLI help text and teach-ai templates reflect FTS options
4. **Error Handling:** Clear API responses when FTS index unavailable
5. **Performance:** API latency comparable to CLI execution

## Scope

### In Scope
- RESTful API endpoints for FTS and hybrid search
- API parameter validation and routing
- CLI documentation and help text updates
- Teach-ai template updates for CIDX syntax
- Server stability when FTS index missing
- Structured API response formats

### Out of Scope
- WebSocket/streaming search results
- GraphQL API
- Authentication/authorization
- Rate limiting
- Caching layer

## Technical Design

### API Endpoint Structure
```
POST /api/search
{
  "query": "search term",
  "mode": "semantic" | "fts" | "hybrid",  // default: "semantic"
  "options": {
    // Common options
    "limit": 10,
    "language": "python",
    "path_filter": "*/tests/*",

    // FTS-specific options
    "case_sensitive": false,
    "edit_distance": 0,
    "snippet_lines": 5,

    // Semantic-specific options
    "min_score": 0.5,
    "accuracy": "balanced"
  }
}
```

### Response Format
```json
{
  "search_mode": "hybrid",
  "query": "authenticate",
  "fts_results": [
    {
      "path": "src/auth/login.py",
      "line": 42,
      "column": 15,
      "match_text": "authenticate_user",
      "snippet": "...",
      "language": "python"
    }
  ],
  "semantic_results": [
    {
      "path": "src/security/auth.py",
      "score": 0.892,
      "snippet": "...",
      "language": "python"
    }
  ],
  "metadata": {
    "fts_available": true,
    "semantic_available": true,
    "execution_time_ms": 12,
    "total_matches": 25
  }
}
```

### API Implementation
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

class SearchRequest(BaseModel):
    query: str
    mode: Literal["semantic", "fts", "hybrid"] = "semantic"
    options: SearchOptions

class SearchOptions(BaseModel):
    # Common
    limit: int = 10
    language: Optional[str] = None
    path_filter: Optional[str] = None

    # FTS-specific
    case_sensitive: bool = False
    edit_distance: int = 0
    snippet_lines: int = 5

    # Semantic-specific
    min_score: float = 0.0
    accuracy: str = "balanced"

@app.post("/api/search")
async def search_endpoint(request: SearchRequest):
    """Unified search endpoint supporting all modes"""

    # Check index availability
    fts_available = fts_index_exists()
    semantic_available = semantic_index_exists()

    # Validate requested mode
    if request.mode == "fts" and not fts_available:
        raise HTTPException(
            status_code=400,
            detail="FTS index not available. Build with 'cidx index --fts'"
        )

    if request.mode == "semantic" and not semantic_available:
        raise HTTPException(
            status_code=400,
            detail="Semantic index not available. Build with 'cidx index'"
        )

    if request.mode == "hybrid":
        if not semantic_available:
            raise HTTPException(
                status_code=400,
                detail="Semantic index required for hybrid search"
            )
        if not fts_available:
            # Graceful degradation
            logger.warning("FTS unavailable, degrading to semantic-only")
            request.mode = "semantic"

    # Execute search based on mode
    results = await execute_search(request)

    return {
        "search_mode": request.mode,
        "query": request.query,
        **results,
        "metadata": {
            "fts_available": fts_available,
            "semantic_available": semantic_available,
            "execution_time_ms": results.execution_time,
            "total_matches": results.total_count
        }
    }
```

### CLI Documentation Updates
```python
# Update cli.py help text
@click.command()
@click.option(
    '--fts',
    is_flag=True,
    help='Use full-text search for exact text matching instead of semantic search'
)
@click.option(
    '--semantic',
    is_flag=True,
    help='Explicitly use semantic search (default) or combine with --fts for hybrid'
)
@click.option(
    '--case-sensitive',
    is_flag=True,
    help='[FTS only] Enable case-sensitive text matching'
)
@click.option(
    '--edit-distance',
    type=int,
    default=0,
    help='[FTS only] Set fuzzy match tolerance (0-3 characters)'
)
@click.option(
    '--snippet-lines',
    type=int,
    default=5,
    help='[FTS only] Number of context lines to show (0 for list only)'
)
def query(query_text: str, **options):
    """
    Search code using semantic understanding or full-text matching.

    Examples:
      cidx query "authentication"           # Semantic search (default)
      cidx query "auth_user" --fts         # Exact text search
      cidx query "login" --fts --semantic  # Hybrid search (both modes)
      cidx query "Parse" --fts --case-sensitive  # Case-sensitive text
      cidx query "authnticate" --fts --edit-distance 2  # Fuzzy matching
    """
    pass
```

## Stories

| Story # | Title | Priority | Effort |
|---------|-------|----------|--------|
| 01 | Server API Extension | Medium | Medium |
| 02 | CLI Command Updates | Low | Small |

## Dependencies

- FastAPI framework for API endpoints
- Pydantic for request/response validation
- Existing search engines (FTS and semantic)
- Click framework for CLI

## Acceptance Criteria

1. **API Functionality:**
   - All search modes accessible via API
   - Proper request validation
   - Clear error responses
   - Structured JSON responses

2. **CLI Updates:**
   - Help text reflects all new options
   - Examples show various search modes
   - Teach-ai templates updated

3. **Error Handling:**
   - Graceful degradation when index missing
   - Clear error messages
   - HTTP status codes appropriate

4. **Performance:**
   - API latency <50ms overhead
   - Concurrent request handling
   - Efficient result serialization

## Conversation References

- **API Support:** "Server API Extension (Medium) - Text search endpoints, all search flags, hybrid search support"
- **CLI Updates:** "CLI Command Updates (Low) - Update teach-ai syntax, add text search flags, documentation"
- **Error Handling:** "server stable when FTS index missing"
- **Search Modes:** "API accepts search_mode parameter ('semantic' default, 'fts', 'hybrid')"
- **Parameter Support:** "FTS parameters supported (case_sensitive, fuzzy, edit_distance, snippet_lines)"
# Story: Server API Full-Text Search Support

## Summary

As an API consumer integrating CIDX server, I want to perform FTS and hybrid searches via API, so that I can programmatically search code with all available search modes.

## Acceptance Criteria

1. **Search Mode Parameter:**
   - API accepts `search_mode` parameter with values: "semantic" (default), "fts", "hybrid"
   - Mode properly routes to appropriate search engine
   - Invalid mode returns 400 Bad Request

2. **FTS Parameters Support:**
   - `case_sensitive` boolean for case control
   - `fuzzy` boolean for fuzzy matching shorthand
   - `edit_distance` integer (0-3) for typo tolerance
   - `snippet_lines` integer for context control
   - Parameters validated and passed to FTS engine

3. **Common Parameters:**
   - `limit` applies to both search types
   - `language` filter works for both
   - `path_filter` pattern matching for both
   - Parameters properly propagated to engines

4. **Error Handling:**
   - Clear 400 error if FTS index not built
   - Helpful error message suggesting `cidx index --fts`
   - Graceful degradation for hybrid when FTS missing

5. **Response Structure:**
   - Hybrid mode returns structured response with separate arrays
   - `fts_results` array with text search matches
   - `semantic_results` array with semantic matches
   - Metadata includes index availability status

6. **Server Stability:**
   - Server remains stable when FTS index missing
   - No crashes or undefined behavior
   - Proper concurrent request handling
   - Memory usage bounded

## Technical Implementation Details

### API Route Definition
```python
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Literal

router = APIRouter(prefix="/api/v1")

@router.post("/search")
async def search(
    query: str = Query(..., description="Search query text"),
    mode: Literal["semantic", "fts", "hybrid"] = Query("semantic"),
    limit: int = Query(10, ge=1, le=100),
    language: Optional[str] = Query(None),
    path_filter: Optional[str] = Query(None),
    # FTS-specific
    case_sensitive: bool = Query(False),
    fuzzy: bool = Query(False),
    edit_distance: int = Query(0, ge=0, le=3),
    snippet_lines: int = Query(5, ge=0, le=50),
    # Semantic-specific
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    accuracy: Literal["low", "balanced", "high"] = Query("balanced")
) -> SearchResponse:
    """
    Unified search endpoint supporting semantic, FTS, and hybrid modes.

    - **semantic**: Concept-based search using embeddings
    - **fts**: Exact text matching with optional fuzzy tolerance
    - **hybrid**: Both search types executed in parallel
    """
    # Implementation below
    pass
```

### Request Validation
```python
class SearchValidator:
    @staticmethod
    def validate_search_request(
        mode: str,
        fts_available: bool,
        semantic_available: bool
    ) -> str:
        """Validate and potentially adjust search mode"""

        if mode == "fts" and not fts_available:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "FTS index not available",
                    "suggestion": "Build FTS index with 'cidx index --fts'",
                    "available_modes": ["semantic"] if semantic_available else []
                }
            )

        if mode == "semantic" and not semantic_available:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Semantic index not available",
                    "suggestion": "Build semantic index with 'cidx index'",
                    "available_modes": ["fts"] if fts_available else []
                }
            )

        if mode == "hybrid":
            if not semantic_available:
                raise HTTPException(
                    status_code=400,
                    detail="Semantic index required for hybrid search"
                )
            if not fts_available:
                # Graceful degradation with warning
                logger.warning("FTS unavailable, degrading hybrid to semantic-only")
                return "semantic"

        return mode
```

### Search Execution
```python
class SearchService:
    async def execute_search(
        self,
        query: str,
        mode: str,
        options: dict
    ) -> dict:
        """Execute search based on validated mode"""

        start_time = time.time()

        if mode == "hybrid":
            # Parallel execution
            fts_task = self._execute_fts(query, options)
            semantic_task = self._execute_semantic(query, options)

            fts_results, semantic_results = await asyncio.gather(
                fts_task,
                semantic_task,
                return_exceptions=True
            )

            # Handle exceptions
            if isinstance(fts_results, Exception):
                fts_results = []
                logger.error(f"FTS search failed: {fts_results}")

            if isinstance(semantic_results, Exception):
                semantic_results = []
                logger.error(f"Semantic search failed: {semantic_results}")

            results = {
                "fts_results": fts_results,
                "semantic_results": semantic_results
            }

        elif mode == "fts":
            results = {
                "fts_results": await self._execute_fts(query, options),
                "semantic_results": []
            }

        else:  # semantic
            results = {
                "fts_results": [],
                "semantic_results": await self._execute_semantic(query, options)
            }

        execution_time = int((time.time() - start_time) * 1000)

        return {
            **results,
            "execution_time_ms": execution_time
        }
```

### Response Formatting
```python
from pydantic import BaseModel

class FTSResult(BaseModel):
    path: str
    line: int
    column: int
    match_text: str
    snippet: Optional[str]
    language: Optional[str]

class SemanticResult(BaseModel):
    path: str
    score: float
    snippet: Optional[str]
    language: Optional[str]

class SearchMetadata(BaseModel):
    fts_available: bool
    semantic_available: bool
    execution_time_ms: int
    total_matches: int
    actual_mode: str  # Mode actually used (after degradation)

class SearchResponse(BaseModel):
    search_mode: str  # Requested mode
    query: str
    fts_results: List[FTSResult]
    semantic_results: List[SemanticResult]
    metadata: SearchMetadata
```

### Error Response Format
```python
class ErrorResponse(BaseModel):
    error: str
    detail: str
    suggestion: Optional[str]
    available_modes: List[str]

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail.get("error"),
            detail=exc.detail.get("detail", str(exc.detail)),
            suggestion=exc.detail.get("suggestion"),
            available_modes=exc.detail.get("available_modes", [])
        ).dict()
    )
```

## Test Scenarios

1. **Basic API Test:**
   ```bash
   curl -X POST http://localhost:8080/api/v1/search \
     -H "Content-Type: application/json" \
     -d '{"query": "authenticate", "mode": "fts"}'
   ```
   - Verify FTS results returned
   - Check response structure

2. **Hybrid Mode Test:**
   ```bash
   curl -X POST http://localhost:8080/api/v1/search \
     -H "Content-Type: application/json" \
     -d '{"query": "login", "mode": "hybrid", "limit": 5}'
   ```
   - Verify both result arrays populated
   - Check limit applied to both

3. **Missing Index Test:**
   - Remove FTS index
   - Send FTS mode request
   - Verify 400 error with helpful message
   - Try hybrid mode
   - Verify degradation to semantic

4. **Parameter Validation Test:**
   - Send invalid edit_distance (5)
   - Verify validation error
   - Send invalid mode ("invalid")
   - Verify 400 error

5. **Concurrent Request Test:**
   - Send 10 simultaneous hybrid searches
   - Verify all complete successfully
   - Check server stability

6. **Performance Test:**
   - Measure API latency for each mode
   - Compare to CLI execution time
   - Verify <50ms API overhead

## OpenAPI Documentation

```yaml
paths:
  /api/v1/search:
    post:
      summary: Unified code search
      description: Search code using semantic, full-text, or hybrid modes
      parameters:
        - name: query
          in: query
          required: true
          schema:
            type: string
          description: Search query text
        - name: mode
          in: query
          schema:
            type: string
            enum: [semantic, fts, hybrid]
            default: semantic
          description: Search mode selection
        - name: case_sensitive
          in: query
          schema:
            type: boolean
            default: false
          description: FTS case sensitivity
        - name: edit_distance
          in: query
          schema:
            type: integer
            minimum: 0
            maximum: 3
            default: 0
          description: FTS fuzzy tolerance
      responses:
        200:
          description: Search results
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SearchResponse'
        400:
          description: Invalid request or missing index
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
```

## Dependencies

- FastAPI framework
- Pydantic for validation
- Existing search engines
- AsyncIO for parallel execution

## Effort Estimate

- **Development:** 2-3 days
- **Testing:** 1.5 days
- **Documentation:** 0.5 days
- **Total:** ~4 days

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| API complexity | Medium | Clear documentation, examples |
| Version compatibility | High | Versioned API (/v1/) |
| Performance under load | Medium | Connection pooling, caching |
| Security concerns | Low | Input validation, sanitization |

## Conversation References

- **API Requirement:** "API accepts search_mode parameter ('semantic' default, 'fts', 'hybrid')"
- **FTS Parameters:** "FTS parameters supported (case_sensitive, fuzzy, edit_distance, snippet_lines)"
- **Error Handling:** "clear error if FTS index not built"
- **Hybrid Response:** "hybrid returns structured response with separate arrays"
- **Filters:** "all semantic filters work with FTS"
- **Stability:** "server stable when FTS index missing"
# MCP Tool Documentation Improvements

Based on Claude.ai feedback evaluation, this document proposes concrete improvements to the MCP tool descriptions for parallel query capabilities.

## Feedback Summary

**What's Clear:**
- Basic multi-repo syntax (array formats)
- Aggregation modes (global vs per_repo)
- Response format options (flat vs grouped)
- Wildcard patterns

**Needs Improvement:**
1. Performance implications buried - should be more prominent
2. Pagination with cached chunks not connected to parallel queries
3. Optimal usage patterns missing (WHEN to use, not just WHAT)
4. Tool coverage inconsistency - unclear which tools support multi-repo
5. Cached content workflow unclear

## Answers to Specific Questions

### Q1: Caching Behavior

**Answer**: Cache handles are **per-result, not per-repo**. Each individual search result that exceeds the preview size threshold (default 2000 chars) gets its own unique cache_handle.

```
Example: Parallel search across 3 repos returns:
- repo1: result_A (large) -> cache_handle_A, result_B (small) -> cache_handle: null
- repo2: result_C (large) -> cache_handle_C
- repo3: result_D (small) -> cache_handle: null

-> Call get_cached_content(cache_handle_A) and get_cached_content(cache_handle_C) separately
```

### Q2: Limit Distribution

**Answer**: With `aggregation_mode='per_repo'`, limits are distributed with **integer division + remainder**:

```python
per_repo_limit = limit // num_repos
remainder = limit % num_repos
# First 'remainder' repos get +1 result
```

Example: `limit=10` with 3 repos -> **4, 3, 3** (10 total, not ~30)

### Q3: Error Handling

**Answer**: **Partial results** are returned. Failed repos appear in the `errors` field:

```json
{
  "results": {"repo1": [...], "repo2": [...]},
  "errors": {"repo3": "Repository not found or timeout"}
}
```

---

## Proposed Changes

### Change 1: Add Multi-Repository Quick Reference to search_code

**Current** (buried in middle of description):
```
PERFORMANCE NOTE: Searching 5+ repos increases token usage proportionally.
```

**Proposed** (add new section at TOP of description):
```
MULTI-REPOSITORY SEARCH GUIDE:

PERFORMANCE: Parallel queries consume tokens proportionally.
- 3 repos × limit=10 = up to 30 results (global mode) or exactly 10 distributed (per_repo mode)
- Start with limit=3-5 for exploratory multi-repo searches
- Each large result gets its own cache_handle for pagination

WHEN TO USE PARALLEL QUERIES:
- Microservices: Find patterns across service boundaries
- Comparison: Compare implementations (use aggregation_mode='per_repo')
- Discovery: Find best matches anywhere (use aggregation_mode='global')
- Impact analysis: Find all repos using a specific pattern/library

LIMIT BEHAVIOR:
- aggregation_mode='global': Top N results by score across ALL repos (may be uneven distribution)
- aggregation_mode='per_repo': N results distributed evenly (limit/num_repos per repo, remainder to first repos)
  Example: limit=10 with 3 repos -> 4, 3, 3 results (NOT 10 per repo)

CACHING WITH PARALLEL QUERIES:
- Large results (>2000 chars) return preview + cache_handle
- Each result has its own cache_handle (not per-repo)
- Use get_cached_content(handle, page=N) to retrieve full content
- Small results return full content directly

ERROR HANDLING:
- Partial results supported: successful repos return results even if others fail
- Check 'errors' field for per-repo failures
- Response format: {"results": {...}, "errors": {"failed_repo": "reason"}}
```

### Change 2: Update aggregation_mode Parameter Description

**Current**:
```
"description": "Result aggregation for multi-repo searches. 'global' (default): Top N results by score across ALL repos - best for finding absolute best matches anywhere. 'per_repo': Distributes N results evenly across repos - best for comparing implementations or ensuring representation from each repo. Example: limit=10 with 3 repos in 'global' mode might return 7 from repo1, 3 from repo2, 0 from repo3. In 'per_repo' mode returns ~3 from each."
```

**Proposed**:
```
"description": "Result aggregation for multi-repo searches. 'global' (default): Top N results by score across ALL repos - best for finding absolute best matches anywhere. 'per_repo': Distributes N results evenly across repos - best for comparing implementations or ensuring representation from each repo. LIMIT MATH: limit=10 with 3 repos in 'global' mode might return 7+3+0=10 total. In 'per_repo' mode returns 4+3+3=10 total (integer division with remainder to first repos). NOTE: per_repo mode does NOT multiply the limit."
```

### Change 3: Update get_cached_content Tool Description

**Current**:
```
"description": "TL;DR: Retrieve cached content by handle with pagination support. USE CASE: Fetch full content when search results return truncated previews with cache_handle..."
```

**Proposed**:
```
"description": """TL;DR: Retrieve cached content by handle with pagination support.

USE CASE: Fetch full content when search results return truncated previews with cache_handle.

WORKS WITH PARALLEL QUERIES: When multi-repo search returns results with cache_handles, each result has its own independent handle. Call this tool separately for each handle you want to expand.

WORKFLOW:
1. search_code returns results with has_more=true and cache_handle
2. Call get_cached_content(handle, page=0) to get first chunk
3. If response has_more=true, call with page=1, page=2, etc.
4. Repeat until has_more=false

CACHE SCOPE: Cache handles are per-result, not per-repo. A multi-repo search returning 5 large results creates 5 independent cache handles.

CACHE EXPIRY: Handles expire after 15 minutes (configurable). If expired, re-run the search.

PAGINATION: Content split into pages (default 5000 chars/page). Response includes: content, page, total_pages, has_more."""
```

### Change 4: Add Tool Coverage Table to tools.py Header

Add new section after the permission system documentation:

```python
# =============================================================================
# MULTI-REPOSITORY SUPPORT MATRIX
# =============================================================================
"""
TOOLS SUPPORTING MULTI-REPO PARALLEL QUERIES:

| Tool              | Multi-Repo | Aggregation | Response Format | Cache Handles |
|-------------------|------------|-------------|-----------------|---------------|
| search_code       | Yes        | Yes         | Yes             | Yes           |
| regex_search      | Yes        | Yes         | Yes             | Yes           |
| git_log           | Yes        | Yes         | Yes             | No            |
| git_search_commits| Yes        | Yes         | Yes             | No            |
| list_files        | Yes        | Yes         | Yes             | No            |
| browse_directory  | No*        | No          | No              | No            |
| get_file_content  | No         | No          | No              | Yes**         |

* browse_directory: Single repo only, use list_files for multi-repo file listing
** get_file_content: Returns cache_handle for large files (pagination support)

MULTI-REPO SYNTAX (for supported tools):
- Single repo: repository_alias='backend-global'
- Multiple repos: repository_alias=['repo1-global', 'repo2-global']
- Wildcard: repository_alias='*-global' or 'prefix-*-global'

AGGREGATION MODES (for supported tools):
- 'global': Top N by score across all repos (may be uneven distribution)
- 'per_repo': N distributed evenly (limit/repos per repo, remainder to first)

RESPONSE FORMATS (for supported tools):
- 'flat': Single array with source_repo field on each result
- 'grouped': Results organized by repository: {"repo1": [...], "repo2": [...]}
"""
```

### Change 5: Add Consistent Performance Warning to All Multi-Repo Tools

Add to regex_search, git_log, git_search_commits, list_files tool descriptions:

```
MULTI-REPO PERFORMANCE: Parallel queries consume resources proportionally. With 5 repos, expect ~5x token usage. Start with limit=3-5 for exploratory searches. Failed repos return partial results in 'errors' field.
```

### Change 6: Update limit Parameter Description (All Multi-Repo Tools)

**Current** (search_code):
```
"description": "Maximum number of results. IMPORTANT: Start with limit=5 to conserve context tokens..."
```

**Proposed**:
```
"description": "Maximum number of results. IMPORTANT: Start with limit=5 to conserve context tokens. MULTI-REPO BEHAVIOR: In 'global' mode, returns top N across all repos. In 'per_repo' mode, distributes N across repos (limit/repos each, NOT limit per repo). Example: limit=10 with 3 repos in per_repo mode returns ~3-4 results per repo (10 total), not 30."
```

---

## Implementation Priority

1. **HIGH**: Update search_code description with Multi-Repository Guide section
2. **HIGH**: Update get_cached_content to clarify parallel query workflow
3. **MEDIUM**: Add Tool Coverage Matrix to tools.py header
4. **MEDIUM**: Update aggregation_mode parameter description with limit math
5. **LOW**: Add performance warnings to other multi-repo tools
6. **LOW**: Update limit parameter descriptions

---

## Validation Checklist

After implementing changes, verify:
- [ ] search_code description clearly explains caching with parallel queries
- [ ] get_cached_content workflow is connected to search results
- [ ] Tool coverage matrix accurately reflects implementation
- [ ] Limit distribution math is documented with concrete examples
- [ ] Performance implications are prominent (not buried)
- [ ] Error handling (partial results) is documented

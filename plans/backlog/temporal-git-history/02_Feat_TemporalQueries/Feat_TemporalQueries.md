# Feature: Temporal Queries

## Feature Overview

**Purpose:** Enable semantic search across git history with temporal filters, allowing users to find code at specific points in time or within date ranges.

**User Value:** AI agents and developers can search for code that existed at any point in the repository's history, understand when patterns were introduced or removed, and debug issues by examining code state at specific commits.

## User Stories

### Story 1: Time-Range Filtering
**Priority:** P0 (Core functionality)
**Effort:** M (Medium)
**Description:** Query code within a specific date range, finding all matches that existed during that time period.

### Story 2: Point-in-Time Query
**Priority:** P0 (Core functionality)
**Effort:** M (Medium)
**Description:** Query code state at a specific commit, seeing exactly what code existed at that point in history.

## Technical Design

### Components

**TemporalSearchService** (`src/code_indexer/services/temporal_search_service.py`):
```python
class TemporalSearchService:
    def __init__(self, semantic_service: SemanticSearchService,
                 config_manager: ConfigManager):
        self.semantic_service = semantic_service
        self.config_manager = config_manager
        self.db_path = Path(".code-indexer/index/temporal/commits.db")

    def query_temporal(
        self,
        query: str,
        time_range: Optional[Tuple[str, str]] = None,
        at_commit: Optional[str] = None,
        include_removed: bool = False,
        limit: int = 10,
        min_score: float = 0.5
    ) -> TemporalSearchResults:
        """Execute temporal semantic search"""

    def _filter_by_time_range(
        self,
        semantic_results: List[SearchResult],
        start_date: str,
        end_date: str,
        include_removed: bool
    ) -> List[TemporalSearchResult]:
        """Filter results by time range using SQLite"""

    def _filter_by_commit(
        self,
        semantic_results: List[SearchResult],
        commit_hash: str
    ) -> List[TemporalSearchResult]:
        """Filter results to specific commit state"""

    def _enhance_with_temporal_context(
        self,
        results: List[SearchResult]
    ) -> List[TemporalSearchResult]:
        """Add temporal metadata to results"""
```

### Query Flow Architecture

**Two-Phase Query Design:**
```python
def query_temporal(self, query: str, time_range: Optional[Tuple[str, str]], ...):
    # Phase 1: Semantic Search (unchanged)
    semantic_results = self.semantic_service.search(
        query=query,
        limit=limit * 3,  # Over-fetch for filtering
        min_score=min_score
    )

    # Phase 2: Temporal Filtering
    if time_range:
        temporal_results = self._filter_by_time_range(
            semantic_results,
            start_date=time_range[0],
            end_date=time_range[1],
            include_removed=include_removed
        )
    elif at_commit:
        temporal_results = self._filter_by_commit(
            semantic_results,
            commit_hash=at_commit
        )
    else:
        # No temporal filter, but enhance with context
        temporal_results = self._enhance_with_temporal_context(
            semantic_results
        )

    return TemporalSearchResults(
        results=temporal_results[:limit],
        query=query,
        filter_type="time_range" if time_range else "at_commit" if at_commit else None,
        filter_value=time_range or at_commit
    )
```

### SQLite Filtering Implementation

**Time-Range Filter:**
```python
def _filter_by_time_range(self, semantic_results, start_date, end_date,
                          include_removed):
    """Filter by date range using SQLite"""
    import sqlite3  # Lazy import

    # Convert dates to timestamps
    start_ts = self._parse_date(start_date)
    end_ts = self._parse_date(end_date)

    conn = sqlite3.connect(self.db_path)

    filtered = []
    for result in semantic_results:
        blob_hash = result.metadata.get("blob_hash")
        if not blob_hash:
            continue

        # Query: Find commits where this blob existed in the time range
        query = """
            SELECT DISTINCT c.hash, c.date, c.message, t.file_path
            FROM commits c
            JOIN trees t ON c.hash = t.commit_hash
            WHERE t.blob_hash = ?
              AND c.date >= ?
              AND c.date <= ?
            ORDER BY c.date DESC
        """

        cursor = conn.execute(query, (blob_hash, start_ts, end_ts))
        commit_rows = cursor.fetchall()

        if commit_rows:
            # Check if blob still exists (for include_removed logic)
            if not include_removed:
                # Check if blob exists in HEAD
                head_exists = self._blob_exists_in_head(blob_hash)
                if not head_exists:
                    continue  # Skip removed code unless requested

            # Create temporal result
            temporal_result = TemporalSearchResult(
                **result.dict(),
                temporal_context={
                    "first_seen": commit_rows[-1][1],  # Earliest date
                    "last_seen": commit_rows[0][1],     # Latest date
                    "commit_count": len(commit_rows),
                    "commits": [
                        {
                            "hash": row[0],
                            "date": row[1],
                            "message": row[2][:100]  # First 100 chars
                        }
                        for row in commit_rows[:5]  # Top 5 commits
                    ]
                }
            )
            filtered.append(temporal_result)

    conn.close()
    return filtered
```

**Point-in-Time Filter:**
```python
def _filter_by_commit(self, semantic_results, commit_hash):
    """Filter to specific commit state"""
    import sqlite3  # Lazy import

    # Resolve short hash to full hash if needed
    full_hash = self._resolve_commit_hash(commit_hash)

    conn = sqlite3.connect(self.db_path)

    # Get commit info
    commit_info = conn.execute(
        "SELECT date, message FROM commits WHERE hash = ?",
        (full_hash,)
    ).fetchone()

    if not commit_info:
        raise ValueError(f"Commit {commit_hash} not found in temporal index")

    filtered = []
    for result in semantic_results:
        blob_hash = result.metadata.get("blob_hash")
        if not blob_hash:
            continue

        # Check if blob existed at this commit
        exists = conn.execute("""
            SELECT file_path FROM trees
            WHERE commit_hash = ? AND blob_hash = ?
        """, (full_hash, blob_hash)).fetchone()

        if exists:
            temporal_result = TemporalSearchResult(
                **result.dict(),
                temporal_context={
                    "at_commit": full_hash,
                    "commit_date": commit_info[0],
                    "commit_message": commit_info[1],
                    "file_path_at_commit": exists[0]
                }
            )
            filtered.append(temporal_result)

    conn.close()
    return filtered
```

### CLI Integration

```python
# In cli.py query command
@click.option("--time-range",
              help="Filter by date range (e.g., 2023-01-01..2024-01-01)")
@click.option("--at-commit",
              help="Query at specific commit (hash)")
@click.option("--include-removed", is_flag=True,
              help="Include code that has been removed")
def query(..., time_range, at_commit, include_removed):
    # Check for temporal index
    temporal_path = Path(".code-indexer/index/temporal/commits.db")
    if (time_range or at_commit) and not temporal_path.exists():
        console.print("[yellow]⚠️ Temporal index not found. "
                     "Run 'cidx index --index-commits' first.[/yellow]")
        console.print("[dim]Falling back to current code search...[/dim]")
        # Continue with regular search
    elif time_range or at_commit:
        # Lazy import
        from src.code_indexer.services.temporal_search_service import (
            TemporalSearchService
        )
        temporal_service = TemporalSearchService(semantic_service, config_manager)

        # Parse time range
        if time_range:
            if ".." in time_range:
                start, end = time_range.split("..")
            else:
                raise ValueError("Time range format: YYYY-MM-DD..YYYY-MM-DD")

            results = temporal_service.query_temporal(
                query=query_text,
                time_range=(start, end),
                include_removed=include_removed,
                limit=limit,
                min_score=min_score
            )
        else:
            results = temporal_service.query_temporal(
                query=query_text,
                at_commit=at_commit,
                limit=limit,
                min_score=min_score
            )

        # Display with temporal context
        formatter.display_temporal_results(results)
```

### Error Handling

```python
class TemporalSearchService:
    def query_temporal(self, ...):
        try:
            # Check if temporal index exists
            if not self.db_path.exists():
                logger.warning("Temporal index not found")
                # Fall back to regular search
                return self._fallback_to_regular_search(query, limit, min_score)

            # Execute temporal query
            # ... implementation ...

        except sqlite3.DatabaseError as e:
            logger.error(f"Database error: {e}")
            return self._fallback_to_regular_search(query, limit, min_score)

        except Exception as e:
            logger.error(f"Temporal search error: {e}")
            # Include error in results for programmatic handling
            return TemporalSearchResults(
                results=[],
                error=str(e),
                fallback_used=True
            )

    def _fallback_to_regular_search(self, query, limit, min_score):
        """Graceful fallback to space-only search"""
        regular_results = self.semantic_service.search(query, limit, min_score)
        return TemporalSearchResults(
            results=[TemporalSearchResult(**r.dict()) for r in regular_results],
            query=query,
            warning="Temporal index unavailable, showing current code only"
        )
```

## Acceptance Criteria

### Story 1: Time-Range Filtering
- [ ] Query with `--time-range 2023-01-01..2024-01-01` filters correctly
- [ ] Shows only code that existed during the time range
- [ ] `--include-removed` flag includes deleted code
- [ ] Results show temporal context (first seen, last seen, commits)
- [ ] Graceful fallback if temporal index missing
- [ ] Clear warning messages for degraded mode

### Story 2: Point-in-Time Query
- [ ] Query with `--at-commit abc123` shows code at that commit
- [ ] Works with both short and full commit hashes
- [ ] Results annotated with commit date and message
- [ ] Error if commit not found in temporal index
- [ ] Shows file paths as they existed at that commit

## Testing Requirements

### Manual Tests

**Time-Range Query:**
```bash
# Index temporal data
cidx index --index-commits

# Query last year's code
cidx query "authentication" --time-range 2023-01-01..2023-12-31

# Include removed code
cidx query "deprecated function" --time-range 2020-01-01..2024-01-01 --include-removed

# Test error handling
cidx query "test" --time-range invalid..format
# Should show error about date format
```

**Point-in-Time Query:**
```bash
# Get a commit hash
git log --oneline | head -5

# Query at specific commit
cidx query "api endpoint" --at-commit abc123def

# Test with short hash
cidx query "database" --at-commit abc123

# Test error handling
cidx query "test" --at-commit nonexistent
# Should show commit not found error
```

### Automated Tests
```python
def test_time_range_filtering():
    """Test temporal filtering by date range"""
    # Setup temporal index with test data
    # ...

    temporal_service = TemporalSearchService(semantic_service, config_manager)

    # Query with time range
    results = temporal_service.query_temporal(
        query="test function",
        time_range=("2023-01-01", "2023-12-31")
    )

    # Verify filtering
    for result in results.results:
        assert result.temporal_context["first_seen"] >= parse_date("2023-01-01")
        assert result.temporal_context["last_seen"] <= parse_date("2023-12-31")

def test_graceful_fallback():
    """Test fallback when temporal index missing"""
    # Remove temporal index
    temporal_db = Path(".code-indexer/index/temporal/commits.db")
    if temporal_db.exists():
        temporal_db.unlink()

    temporal_service = TemporalSearchService(semantic_service, config_manager)

    # Should fallback gracefully
    results = temporal_service.query_temporal(
        query="test",
        time_range=("2023-01-01", "2023-12-31")
    )

    assert results.warning == "Temporal index unavailable, showing current code only"
    assert len(results.results) > 0  # Should still return results
```

## Performance Considerations

- Over-fetch semantic results (3x limit) for filtering headroom
- Use SQLite indexes for efficient temporal filtering
- Cache database connections in long-running processes
- Limit temporal context to top 5 commits per result

## Dependencies

- SQLite temporal index from Feature 1
- Existing SemanticSearchService
- Date parsing utilities
- Git CLI for commit resolution

## Notes

**Conversation Requirements:**
- <300ms query performance target
- Graceful degradation when index missing
- Clear error messages with suggested actions
- Works with --include-removed for deleted code
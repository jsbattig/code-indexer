# Story: Time-Range Filtering

## Story Description

**As a** AI coding agent analyzing code evolution
**I want to** search for code within specific date ranges
**So that** I can understand what code existed during certain time periods and track pattern changes

**Conversation Context:**
- User specified need for semantic temporal queries across full git history
- Query performance target <300ms on 40K+ repos
- Include ability to find removed code with --include-removed flag

## Acceptance Criteria

- [ ] Query with `cidx query "pattern" --time-range 2023-01-01..2024-01-01` filters by date
- [ ] Semantic search on HNSW index followed by SQLite date filtering
- [ ] Results show only code that existed during the specified time range
- [ ] Works with `--include-removed` flag to show deleted code
- [ ] Results include temporal context (first seen, last seen, commit count)
- [ ] Error handling: Show warning if temporal index missing, fall back to space-only search
- [ ] Performance: Total query time <300ms for typical searches
- [ ] Clear date format validation with helpful error messages

## Technical Implementation

### CLI Entry Point
```python
# In cli.py query command
@click.option("--time-range",
              help="Filter results by date range (format: YYYY-MM-DD..YYYY-MM-DD)")
@click.option("--include-removed", is_flag=True,
              help="Include code that has been removed from the repository")
def query(query_text, time_range, include_removed, ...):
    if time_range:
        # Validate format
        if ".." not in time_range:
            console.print("[red]Error: Time range must be in format "
                         "YYYY-MM-DD..YYYY-MM-DD[/red]")
            return

        start_date, end_date = time_range.split("..")

        # Validate dates
        try:
            from datetime import datetime
            datetime.strptime(start_date, "%Y-%m-%d")
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            console.print("[red]Error: Invalid date format. "
                         "Use YYYY-MM-DD[/red]")
            return

        # Check for temporal index
        if not Path(".code-indexer/index/temporal/commits.db").exists():
            console.print("[yellow]⚠️ Temporal index not found. "
                         "Run 'cidx index --index-commits' to enable "
                         "temporal search.[/yellow]")
            console.print("[dim]Showing results from current code only...[/dim]\n")
            # Continue with regular search
        else:
            # Use temporal search
            from src.code_indexer.services.temporal_search_service import (
                TemporalSearchService
            )
            temporal_service = TemporalSearchService(semantic_service,
                                                    config_manager)
            results = temporal_service.query_temporal(
                query=query_text,
                time_range=(start_date, end_date),
                include_removed=include_removed,
                limit=limit,
                min_score=min_score
            )
            # Display temporal results
            formatter.display_temporal_results(results)
            return

    # Regular search continues...
```

### Temporal Search Implementation
```python
class TemporalSearchService:
    def query_temporal(self, query: str,
                      time_range: Optional[Tuple[str, str]] = None,
                      include_removed: bool = False, ...) -> TemporalSearchResults:
        """Execute temporal semantic search with date filtering"""

        # Phase 1: Semantic search (unchanged, uses existing HNSW)
        start_time = time.time()
        semantic_results = self.semantic_service.search(
            query=query,
            limit=limit * 5,  # Over-fetch for filtering headroom
            min_score=min_score
        )
        semantic_time = time.time() - start_time

        if not semantic_results:
            return TemporalSearchResults(
                results=[],
                query=query,
                filter_type="time_range",
                filter_value=time_range,
                performance={
                    "semantic_search_ms": semantic_time * 1000,
                    "temporal_filter_ms": 0
                }
            )

        # Phase 2: Temporal filtering via SQLite
        filter_start = time.time()
        temporal_results = self._filter_by_time_range(
            semantic_results,
            start_date=time_range[0],
            end_date=time_range[1],
            include_removed=include_removed
        )
        filter_time = time.time() - filter_start

        # Sort by relevance score
        temporal_results.sort(key=lambda r: r.score, reverse=True)

        return TemporalSearchResults(
            results=temporal_results[:limit],
            query=query,
            filter_type="time_range",
            filter_value=time_range,
            total_found=len(temporal_results),
            performance={
                "semantic_search_ms": semantic_time * 1000,
                "temporal_filter_ms": filter_time * 1000,
                "total_ms": (semantic_time + filter_time) * 1000
            }
        )
```

### Helper Methods
```python
def _get_head_file_blobs(self) -> Set[Tuple[str, str]]:
    """
    Get current HEAD file-blob mappings (Issue #11 fix).

    Returns:
        Set of (file_path, blob_hash) tuples for all files at HEAD

    Why tuples instead of just blob hashes:
        Same blob can appear in multiple files. To detect "removed code",
        we need to check if a specific FILE has been removed, not just if
        the blob content exists SOMEWHERE in the repo.

    Example:
        HEAD state:
          src/auth.py → blob abc123
          lib/utils.py → blob abc123  (same content)

        Historical state:
          src/auth.py → blob abc123  (later removed)
          src/login.py → blob def456

        Query finds "src/auth.py" with blob abc123.
        - Wrong logic: Check if abc123 exists → YES (in lib/utils.py) → NOT removed ❌
        - Correct logic: Check if (src/auth.py, abc123) exists → NO → IS removed ✅
    """
    import subprocess
    file_blobs = set()

    try:
        # Get git ls-tree for current HEAD
        # Format: <mode> <type> <hash>\t<file>
        result = subprocess.run(
            ["git", "ls-tree", "-r", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            # Parse line: "100644 blob abc123def\tpath/to/file.py"
            parts = line.split("\t")
            if len(parts) != 2:
                continue

            meta, file_path = parts
            meta_parts = meta.split()
            if len(meta_parts) != 3:
                continue

            mode, obj_type, blob_hash = meta_parts

            if obj_type == "blob":
                file_blobs.add((file_path, blob_hash))

    except subprocess.CalledProcessError as e:
        self.logger.error(f"Failed to get HEAD file-blob mappings: {e}")
        # Return empty set - will treat all code as removed (safe fallback)

    return file_blobs
```

### SQLite Filtering Logic
```python
def _filter_by_time_range(self, semantic_results: List[SearchResult],
                          start_date: str, end_date: str,
                          include_removed: bool) -> List[TemporalSearchResult]:
    """Filter semantic results by date range using SQLite"""
    import sqlite3  # Lazy import

    # Convert dates to Unix timestamps
    from datetime import datetime
    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
    end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())

    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row  # Enable column access by name

    filtered_results = []

    # Batch query for performance
    blob_hashes = [r.metadata.get("blob_hash") for r in semantic_results
                   if r.metadata.get("blob_hash")]

    if not blob_hashes:
        return []

    # Build query with placeholders
    placeholders = ",".join(["?"] * len(blob_hashes))
    query = f"""
        SELECT
            t.blob_hash,
            t.file_path,
            c.hash as commit_hash,
            c.date as commit_date,
            c.message as commit_message,
            c.author_name,
            MIN(c.date) OVER (PARTITION BY t.blob_hash) as first_seen,
            MAX(c.date) OVER (PARTITION BY t.blob_hash) as last_seen,
            COUNT(*) OVER (PARTITION BY t.blob_hash) as appearance_count
        FROM trees t
        JOIN commits c ON t.commit_hash = c.hash
        WHERE t.blob_hash IN ({placeholders})
          AND c.date >= ?
          AND c.date <= ?
        ORDER BY t.blob_hash, c.date DESC
    """

    params = blob_hashes + [start_ts, end_ts]
    cursor = conn.execute(query, params)

    # Group results by blob
    blob_data = {}
    for row in cursor:
        blob_hash = row["blob_hash"]
        if blob_hash not in blob_data:
            blob_data[blob_hash] = {
                "first_seen": row["first_seen"],
                "last_seen": row["last_seen"],
                "appearance_count": row["appearance_count"],
                "commits": []
            }

        # Add commit info (limit to top 5)
        if len(blob_data[blob_hash]["commits"]) < 5:
            blob_data[blob_hash]["commits"].append({
                "hash": row["commit_hash"][:8],  # Short hash
                "date": datetime.fromtimestamp(row["commit_date"]).isoformat(),
                "message": row["commit_message"][:100] if row["commit_message"] else "",
                "author": row["author_name"]
            })

    # === REMOVED CODE DETECTION (Issue #11) ===
    # CRITICAL: Check (file_path, blob_hash) tuple, NOT just blob_hash
    # Same blob in different file should NOT prevent "removed" detection
    if not include_removed:
        # Get current HEAD (file_path, blob_hash) tuples
        head_file_blobs = self._get_head_file_blobs()

    # Build temporal results
    for result in semantic_results:
        blob_hash = result.metadata.get("blob_hash")
        file_path = result.file_path

        if blob_hash in blob_data:
            # CRITICAL: Check tuple (file_path, blob_hash), not just blob_hash
            # Example why this matters:
            #   src/auth.py blob abc123 - removed
            #   lib/utils.py blob abc123 - still exists (same content, different file)
            # Without tuple check: Would incorrectly say src/auth.py NOT removed
            is_removed = False
            if not include_removed:
                file_blob_tuple = (file_path, blob_hash)
                if file_blob_tuple not in head_file_blobs:
                    # This specific file+blob combination removed
                    continue  # Skip unless include_removed
                is_removed = False
            else:
                # When include_removed=True, check if this specific file+blob exists
                file_blob_tuple = (file_path, blob_hash)
                is_removed = file_blob_tuple not in head_file_blobs

            temporal_data = blob_data[blob_hash]

            # Create enhanced result
            temporal_result = TemporalSearchResult(
                file_path=result.file_path,
                chunk_index=result.chunk_index,
                content=result.content,
                score=result.score,
                metadata=result.metadata,
                temporal_context={
                    "time_range": f"{start_date} to {end_date}",
                    "first_seen": datetime.fromtimestamp(
                        temporal_data["first_seen"]).strftime("%Y-%m-%d"),
                    "last_seen": datetime.fromtimestamp(
                        temporal_data["last_seen"]).strftime("%Y-%m-%d"),
                    "appearance_count": temporal_data["appearance_count"],
                    "is_removed": is_removed,
                    "commits": temporal_data["commits"]
                }
            )
            filtered_results.append(temporal_result)

    conn.close()
    return filtered_results
```

### Result Display
```python
# In output/temporal_formatter.py
def display_temporal_results(self, results: TemporalSearchResults):
    """Display temporal search results with context"""

    if results.warning:
        console.print(f"[yellow]⚠️ {results.warning}[/yellow]\n")

    if not results.results:
        console.print("[yellow]No results found in the specified time range[/yellow]")
        return

    # Display filter info
    if results.filter_type == "time_range":
        start, end = results.filter_value
        console.print(f"[bold]Temporal Search:[/bold] {start} to {end}")
        console.print(f"[dim]Query: {results.query}[/dim]")
        console.print(f"[dim]Found: {results.total_found} results[/dim]\n")

    # Display each result
    for i, result in enumerate(results.results, 1):
        # File and score
        console.print(f"[cyan]{i}. {result.file_path}[/cyan] "
                     f"(score: {result.score:.3f})")

        # Temporal context
        ctx = result.temporal_context
        console.print(f"   [dim]First seen: {ctx['first_seen']} | "
                     f"Last seen: {ctx['last_seen']} | "
                     f"Appearances: {ctx['appearance_count']}[/dim]")

        if ctx.get("is_removed"):
            console.print("   [red]⚠️ This code has been removed[/red]")

        # Show top commits
        if ctx.get("commits"):
            console.print("   [dim]Recent commits:[/dim]")
            for commit in ctx["commits"][:2]:  # Show top 2
                msg = commit["message"][:60] + "..." if len(commit["message"]) > 60 else commit["message"]
                console.print(f"     • {commit['hash']}: {msg}")

        # Code preview
        console.print(f"\n[dim]{result.content[:200]}...[/dim]\n")

    # Performance info
    if results.performance:
        perf = results.performance
        console.print(f"\n[dim]Performance: semantic {perf['semantic_search_ms']:.0f}ms + "
                     f"temporal {perf['temporal_filter_ms']:.0f}ms = "
                     f"{perf['total_ms']:.0f}ms total[/dim]")
```

## Test Scenarios

### Manual Test Plan

1. **Setup Test Repository:**
   ```bash
   cd /tmp/test-repo
   git init

   # Create commits across time
   for i in {1..10}; do
     echo "function oldFunction$i() { return $i; }" > old$i.js
     git add old$i.js
     GIT_COMMITTER_DATE="2023-0$i-01 12:00:00" \
     git commit --date="2023-0$i-01 12:00:00" -m "Add old function $i"
   done

   # Remove some functions
   git rm old1.js old2.js
   git commit -m "Remove old functions"

   # Index with temporal
   cidx init
   cidx index
   cidx index --index-commits
   ```

2. **Test Time-Range Query:**
   ```bash
   # Query specific time range
   cidx query "oldFunction" --time-range 2023-01-01..2023-06-30
   # Should show functions 1-6

   cidx query "oldFunction" --time-range 2023-07-01..2023-12-31
   # Should show functions 7-10
   ```

3. **Test Include-Removed:**
   ```bash
   # Without flag (default)
   cidx query "oldFunction1" --time-range 2023-01-01..2023-12-31
   # Should NOT show oldFunction1 (removed)

   # With flag
   cidx query "oldFunction1" --time-range 2023-01-01..2023-12-31 --include-removed
   # Should show oldFunction1 with "removed" indicator
   ```

4. **Test Performance:**
   ```bash
   # On large repo (code-indexer)
   time cidx query "authentication" --time-range 2023-01-01..2024-01-01
   # Should complete in <300ms
   ```

5. **Test Error Handling:**
   ```bash
   # Invalid date format
   cidx query "test" --time-range 2023-1-1..2024-1-1
   # Should show format error

   # Invalid range format
   cidx query "test" --time-range 2023-01-01-2024-01-01
   # Should show ".." separator error

   # Missing temporal index
   rm -rf .code-indexer/index/temporal/
   cidx query "test" --time-range 2023-01-01..2024-01-01
   # Should show warning and fall back to regular search
   ```

### Automated Tests
```python
def test_time_range_filtering():
    """Test filtering by date range"""
    with temp_git_repo() as repo_path:
        # Create commits with specific dates
        create_commit_with_date(repo_path, "2023-03-15", "old code")
        create_commit_with_date(repo_path, "2023-06-15", "mid code")
        create_commit_with_date(repo_path, "2023-09-15", "new code")

        # Index temporal
        temporal = TemporalIndexer(config_manager, vector_store)
        temporal.index_commits()

        # Query with range
        service = TemporalSearchService(semantic_service, config_manager)
        results = service.query_temporal(
            query="code",
            time_range=("2023-01-01", "2023-06-30")
        )

        # Should only find old and mid code
        assert len(results.results) == 2
        assert all("old" in r.content or "mid" in r.content
                  for r in results.results)

def test_include_removed_flag():
    """Test include-removed functionality"""
    with temp_git_repo() as repo_path:
        # Create and remove file
        create_file(repo_path, "removed.py", "def removed_function(): pass")
        git_commit(repo_path, "Add function")
        git_rm(repo_path, "removed.py")
        git_commit(repo_path, "Remove function")

        # Index
        temporal = TemporalIndexer(config_manager, vector_store)
        temporal.index_commits()

        service = TemporalSearchService(semantic_service, config_manager)

        # Without flag - should not find
        results1 = service.query_temporal(
            query="removed_function",
            time_range=("2020-01-01", "2025-01-01"),
            include_removed=False
        )
        assert len(results1.results) == 0

        # With flag - should find
        results2 = service.query_temporal(
            query="removed_function",
            time_range=("2020-01-01", "2025-01-01"),
            include_removed=True
        )
        assert len(results2.results) == 1
        assert results2.results[0].temporal_context["is_removed"] == True

def test_performance_target():
    """Test <300ms query performance"""
    # Use existing large index
    service = TemporalSearchService(semantic_service, config_manager)

    start = time.time()
    results = service.query_temporal(
        query="common pattern",
        time_range=("2023-01-01", "2024-01-01")
    )
    elapsed = (time.time() - start) * 1000

    assert elapsed < 300, f"Query took {elapsed}ms, target is <300ms"
    assert results.performance["total_ms"] < 300

def test_removed_code_detection_with_duplicate_blobs():
    """
    Test removed code detection when same blob exists in different files (Issue #11).

    Critical scenario:
      - File src/auth.py with blob abc123 was removed
      - File lib/utils.py with SAME blob abc123 still exists (duplicate content)
      - Query should correctly identify src/auth.py as removed
    """
    with temp_git_repo() as repo_path:
        # Commit 1: Create two files with SAME content
        shared_content = "function authenticate() { return true; }"

        Path("src/auth.py").write_text(shared_content)
        Path("lib/utils.py").write_text(shared_content)
        git_add_commit("Add auth files with duplicate content")

        # Index temporal
        temporal = TemporalIndexer(config_manager, vector_store)
        temporal.index_commits()

        # Get blob hashes - should be identical
        blob1 = subprocess.run(
            ["git", "hash-object", "src/auth.py"],
            capture_output=True, text=True
        ).stdout.strip()

        blob2 = subprocess.run(
            ["git", "hash-object", "lib/utils.py"],
            capture_output=True, text=True
        ).stdout.strip()

        assert blob1 == blob2, "Blobs should be identical (same content)"

        # Commit 2: Remove src/auth.py (but lib/utils.py with same blob still exists)
        subprocess.run(["git", "rm", "src/auth.py"], check=True)
        git_add_commit("Remove src/auth.py")

        # Re-index
        temporal.index_commits(incremental=True)

        # Query for the content WITHOUT include_removed
        service = TemporalSearchService(semantic_service, config_manager)
        results = service.query_temporal(
            query="authenticate function",
            time_range=("2020-01-01", "2025-01-01"),
            include_removed=False  # Should NOT include removed files
        )

        # CRITICAL ASSERTION: Should ONLY find lib/utils.py, NOT src/auth.py
        # Because src/auth.py was removed even though same blob exists in lib/utils.py
        file_paths = [r.file_path for r in results.results]
        assert "lib/utils.py" in file_paths, "lib/utils.py should be found"
        assert "src/auth.py" not in file_paths, "src/auth.py should NOT be found (removed)"

        # Now WITH include_removed - should find BOTH
        results_with_removed = service.query_temporal(
            query="authenticate function",
            time_range=("2020-01-01", "2025-01-01"),
            include_removed=True
        )

        file_paths_all = [r.file_path for r in results_with_removed.results]
        assert "lib/utils.py" in file_paths_all
        assert "src/auth.py" in file_paths_all

        # Verify is_removed flag correct
        for result in results_with_removed.results:
            if result.file_path == "src/auth.py":
                assert result.temporal_context["is_removed"] == True
            elif result.file_path == "lib/utils.py":
                assert result.temporal_context["is_removed"] == False
```

### Daemon Mode Integration Tests

**CRITICAL:** Time-range filtering must work in both standalone and daemon modes with proper cache coordination (Story 0 integration).

```python
def test_time_range_filtering_daemon_mode():
    """
    Test time-range filtering in daemon mode with cached indexes.

    Scenario:
    - Daemon running with cached HNSW and ID indexes
    - Execute time-range filtered queries
    - Verify cache used efficiently
    - Verify results identical to standalone mode
    """
    daemon_process = start_cidx_daemon(repo_path)

    try:
        # Warm up cache
        run_query("warmup query")  # Loads HNSW into cache

        # Execute time-range query
        start_time = time.time()
        results = query_temporal(
            query="authentication code",
            time_range=("2024-01-01", "2024-12-31")
        )
        query_time = time.time() - start_time

        # Verify results
        assert len(results) > 0
        assert query_time < 0.3  # Fast (using cached index)

        # Verify all results within date range
        for result in results:
            commit_date = result["first_seen_date"]
            assert "2024-01-01" <= commit_date <= "2024-12-31"

    finally:
        daemon_process.terminate()


def test_time_range_daemon_concurrent_queries():
    """
    Test concurrent time-range queries in daemon mode.

    Scenario:
    - Multiple clients query different date ranges simultaneously
    - All queries use shared cached indexes
    - No race conditions or result corruption
    - All queries return correct date-filtered results
    """
    daemon_process = start_cidx_daemon(repo_path)

    try:
        import concurrent.futures

        def run_concurrent_time_range_query(year):
            results = query_temporal(
                query="function",
                time_range=(f"{year}-01-01", f"{year}-12-31")
            )
            # Verify results match year
            for r in results:
                assert r["first_seen_date"].startswith(str(year))
            return len(results)

        # Run queries for different years concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(run_concurrent_time_range_query, year)
                for year in [2020, 2021, 2022, 2023, 2024]
            ]

            result_counts = [f.result() for f in futures]

        # Verify all queries succeeded
        assert all(count >= 0 for count in result_counts)

    finally:
        daemon_process.terminate()


def test_time_range_daemon_after_background_rebuild():
    """
    Test time-range queries after Story 0 background HNSW rebuild.

    Scenario:
    - Daemon running with active time-range queries
    - Background HNSW rebuild triggered (temporal indexing added new blobs)
    - Continue querying during rebuild (stale reads OK)
    - Verify cache invalidation after rebuild
    - Verify queries use new index with new temporal blobs
    """
    daemon_process = start_cidx_daemon(repo_path)

    try:
        # Initial query (old index)
        old_results = query_temporal(
            query="test",
            time_range=("2024-01-01", "2024-12-31")
        )

        # Trigger background rebuild (simulates adding historical blobs)
        trigger_background_hnsw_rebuild(repo_path)

        # Query during rebuild (should use old cached index)
        during_results = query_temporal(
            query="test",
            time_range=("2024-01-01", "2024-12-31")
        )
        # Stale reads OK during rebuild
        assert len(during_results) == len(old_results)

        # Wait for rebuild completion
        wait_for_rebuild_completion()

        # Query after rebuild (should detect version change, load new index)
        new_results = query_temporal(
            query="test",
            time_range=("2024-01-01", "2024-12-31")
        )

        # Results still correct (may include new historical blobs)
        assert len(new_results) >= len(old_results)
        # All results still in date range
        for result in new_results:
            commit_date = result["first_seen_date"]
            assert "2024-01-01" <= commit_date <= "2024-12-31"

    finally:
        daemon_process.terminate()


def test_time_range_daemon_cache_invalidation():
    """
    Test cache invalidation when temporal index updated.

    Scenario:
    - Daemon running with cached indexes
    - Run incremental temporal indexing (adds new commits)
    - Verify cache invalidated
    - Verify new commits appear in time-range queries
    """
    daemon_process = start_cidx_daemon(repo_path)

    try:
        # Query before incremental indexing
        old_results = query_temporal(
            query="new code",
            time_range=("2024-01-01", "2024-12-31")
        )
        old_count = len(old_results)

        # Add new commits and run incremental indexing
        create_new_commit(repo_path, "new code feature", "2024-06-15")
        run_incremental_temporal_indexing(repo_path)

        # Query after incremental indexing
        new_results = query_temporal(
            query="new code",
            time_range=("2024-01-01", "2024-12-31")
        )

        # Should find new commit
        assert len(new_results) > old_count

        # Verify new commit in results
        new_commit_found = any(
            "new code feature" in r["content"]
            for r in new_results
        )
        assert new_commit_found

    finally:
        daemon_process.terminate()
```

## Error Scenarios

1. **Invalid Date Format:**
   - Error: "Invalid date format. Use YYYY-MM-DD"
   - Example: "2023-1-1" or "01/01/2023"

2. **Invalid Range Separator:**
   - Error: "Time range must use '..' separator"
   - Example: "2023-01-01-2024-01-01"

3. **End Date Before Start:**
   - Error: "End date must be after start date"
   - Validate and show clear message

4. **Temporal Index Missing:**
   - Warning: "Temporal index not found. Run 'cidx index --index-commits'"
   - Fall back to regular search

5. **Database Corruption:**
   - Error: "Temporal database corrupted"
   - Suggest re-indexing

## Performance Considerations

- Over-fetch semantic results (5x limit) for filtering
- Use compound SQLite indexes for fast date range queries
- Batch blob lookups instead of individual queries
- Limit commit details to top 5 per result
- Target: <200ms semantic + <50ms temporal = <250ms total

## Dependencies

- TemporalIndexer (must run first)
- SQLite temporal database
- Existing SemanticSearchService
- Date parsing utilities

## Notes

**Conversation Requirements:**
- Query performance <300ms on 40K+ repos
- Graceful fallback to space-only search
- Include-removed flag for deleted code
- Clear error messages with actions
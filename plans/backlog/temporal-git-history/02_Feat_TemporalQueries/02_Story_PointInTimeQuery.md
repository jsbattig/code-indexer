# Story: Point-in-Time Query

## Story Description

**As a** developer debugging a regression
**I want to** search for code as it existed at a specific commit
**So that** I can understand the exact state of the codebase at that point in history

**Conversation Context:**
- User specified need to query at specific commits
- Support both short and full commit hashes
- Clear error handling when commit not found

## Acceptance Criteria

- [ ] Query with `cidx query "pattern" --at-commit abc123def` searches at that commit
- [ ] Works with both short (6+ chars) and full (40 char) commit hashes
- [ ] Results show only code that existed at that specific commit
- [ ] Results annotated with "State at commit abc123 (2023-05-15)"
- [ ] Shows file paths as they existed at that commit (handles renames)
- [ ] Error handling: Show warning if commit not found, fall back to space-only search
- [ ] Performance: Total query time <300ms
- [ ] Integration with existing semantic search infrastructure

## Technical Implementation

### CLI Entry Point
```python
# In cli.py query command
@click.option("--at-commit",
              help="Query code state at specific commit (hash)")
def query(query_text, at_commit, ...):
    if at_commit:
        # Check for temporal index
        temporal_db = Path(".code-indexer/index/temporal/commits.db")
        if not temporal_db.exists():
            console.print("[yellow]⚠️ Temporal index not found. "
                         "Run 'cidx index --index-commits' to enable "
                         "point-in-time queries.[/yellow]")
            console.print("[dim]Showing results from current code only...[/dim]\n")
            # Fall back to regular search
        else:
            # Lazy import
            from src.code_indexer.services.temporal_search_service import (
                TemporalSearchService
            )

            temporal_service = TemporalSearchService(semantic_service,
                                                    config_manager)

            try:
                results = temporal_service.query_temporal(
                    query=query_text,
                    at_commit=at_commit,
                    limit=limit,
                    min_score=min_score
                )
                formatter.display_temporal_results(results)
            except CommitNotFoundError as e:
                console.print(f"[red]Error: {e}[/red]")
                console.print("[dim]Falling back to current code search...[/dim]")
                # Fall back to regular search
            return

    # Regular search continues...
```

### Point-in-Time Query Implementation
```python
class TemporalSearchService:
    def _filter_by_commit(self, semantic_results: List[SearchResult],
                         commit_hash: str) -> List[TemporalSearchResult]:
        """Filter results to specific commit state"""
        import sqlite3  # Lazy import

        # Resolve commit hash (short to full)
        full_hash = self._resolve_commit_hash(commit_hash)
        if not full_hash:
            raise CommitNotFoundError(
                f"Commit '{commit_hash}' not found in temporal index. "
                f"The index may need updating with 'cidx index --index-commits'."
            )

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # Get commit metadata
        commit_info = conn.execute(
            "SELECT hash, date, author_name, message FROM commits WHERE hash = ?",
            (full_hash,)
        ).fetchone()

        if not commit_info:
            # Commit exists in git but not in temporal index
            raise CommitNotFoundError(
                f"Commit '{commit_hash}' exists but is not in temporal index. "
                f"Run 'cidx index --index-commits' to update."
            )

        # Get all blobs that existed at this commit
        commit_tree = conn.execute("""
            SELECT blob_hash, file_path
            FROM trees
            WHERE commit_hash = ?
        """, (full_hash,)).fetchall()

        # Create lookup map
        commit_blobs = {row["blob_hash"]: row["file_path"]
                       for row in commit_tree}

        # Filter semantic results
        filtered_results = []
        for result in semantic_results:
            blob_hash = result.metadata.get("blob_hash")
            if not blob_hash:
                continue

            # Check if blob existed at this commit
            if blob_hash in commit_blobs:
                # Get file path at that commit (may differ from current)
                historical_path = commit_blobs[blob_hash]

                # Create temporal result
                from datetime import datetime
                commit_date = datetime.fromtimestamp(commit_info["date"])

                temporal_result = TemporalSearchResult(
                    file_path=historical_path,  # Use historical path
                    chunk_index=result.chunk_index,
                    content=result.content,
                    score=result.score,
                    metadata={
                        **result.metadata,
                        "original_path": result.file_path  # Keep current path too
                    },
                    temporal_context={
                        "at_commit": {
                            "hash": commit_info["hash"][:8],  # Short hash
                            "full_hash": commit_info["hash"],
                            "date": commit_date.strftime("%Y-%m-%d %H:%M:%S"),
                            "author": commit_info["author_name"],
                            "message": commit_info["message"][:200]
                                      if commit_info["message"] else ""
                        },
                        "file_path_at_commit": historical_path,
                        "query_type": "point_in_time"
                    }
                )
                filtered_results.append(temporal_result)

        conn.close()

        # Sort by score
        filtered_results.sort(key=lambda r: r.score, reverse=True)

        return filtered_results

    def _resolve_commit_hash(self, commit_hash: str) -> Optional[str]:
        """Resolve short hash to full hash"""
        import sqlite3

        # Already full hash
        if len(commit_hash) == 40:
            return commit_hash

        # Short hash - find in database
        if len(commit_hash) < 6:
            raise ValueError("Commit hash must be at least 6 characters")

        conn = sqlite3.connect(self.db_path)

        # Search for matching commits
        pattern = f"{commit_hash}%"
        matches = conn.execute(
            "SELECT hash FROM commits WHERE hash LIKE ? LIMIT 2",
            (pattern,)
        ).fetchall()

        conn.close()

        if len(matches) == 0:
            return None
        elif len(matches) > 1:
            raise ValueError(
                f"Ambiguous short hash '{commit_hash}'. "
                f"Please provide more characters."
            )

        return matches[0][0]
```

### Result Display
```python
# In output/temporal_formatter.py
def display_point_in_time_results(self, results: TemporalSearchResults):
    """Display point-in-time query results"""

    if not results.results:
        console.print("[yellow]No results found at the specified commit[/yellow]")
        return

    # Display commit context
    if results.results and results.results[0].temporal_context.get("at_commit"):
        commit_info = results.results[0].temporal_context["at_commit"]
        console.print(Panel(
            f"[bold]State at commit:[/bold] {commit_info['hash']} "
            f"({commit_info['date']})\n"
            f"[dim]Author:[/dim] {commit_info['author']}\n"
            f"[dim]Message:[/dim] {commit_info['message'][:100]}...",
            title="📍 Point-in-Time Query",
            border_style="cyan"
        ))
        console.print()

    # Display results
    for i, result in enumerate(results.results, 1):
        # File path (show if renamed)
        historical_path = result.file_path
        current_path = result.metadata.get("original_path")

        if current_path and current_path != historical_path:
            console.print(f"[cyan]{i}. {historical_path}[/cyan] "
                         f"[dim](now: {current_path})[/dim] "
                         f"(score: {result.score:.3f})")
        else:
            console.print(f"[cyan]{i}. {historical_path}[/cyan] "
                         f"(score: {result.score:.3f})")

        # Code preview
        lines = result.content.split("\n")
        preview = "\n".join(lines[:5])
        if len(lines) > 5:
            preview += "\n..."

        console.print(Syntax(preview, "python", theme="monokai",
                            line_numbers=True))
        console.print()
```

### Code Retrieval from Git
```python
def retrieve_historical_code(self, blob_hash: str, commit_hash: str) -> str:
    """Retrieve actual code from git blob"""
    try:
        # Get code from git
        result = subprocess.run(
            ["git", "cat-file", "blob", blob_hash],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError:
        # Blob might not exist locally, try from commit tree
        result = subprocess.run(
            ["git", "show", f"{commit_hash}:{file_path}"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return result.stdout
        else:
            return "[Code not available - blob not found]"
```

## Test Scenarios

### Manual Test Plan

1. **Setup Test Repository:**
   ```bash
   cd /tmp/test-repo
   git init

   # Create file and make changes
   echo "function original() { return 1; }" > code.js
   git add code.js
   git commit -m "Initial version"
   COMMIT1=$(git rev-parse HEAD)

   echo "function modified() { return 2; }" >> code.js
   git add code.js
   git commit -m "Add modified function"
   COMMIT2=$(git rev-parse HEAD)

   # Rename file
   git mv code.js renamed.js
   git commit -m "Rename file"
   COMMIT3=$(git rev-parse HEAD)

   # Index
   cidx init
   cidx index
   cidx index --index-commits
   ```

2. **Test Full Hash Query:**
   ```bash
   cidx query "original" --at-commit $COMMIT1
   # Should show only original function

   cidx query "modified" --at-commit $COMMIT1
   # Should show no results (didn't exist yet)

   cidx query "modified" --at-commit $COMMIT2
   # Should show modified function in code.js
   ```

3. **Test Short Hash Query:**
   ```bash
   # Get short hashes
   SHORT1=$(echo $COMMIT1 | cut -c1-7)

   cidx query "original" --at-commit $SHORT1
   # Should work with short hash
   ```

4. **Test File Rename Handling:**
   ```bash
   cidx query "original" --at-commit $COMMIT3
   # Should show file as "renamed.js" but note it was "code.js"
   ```

5. **Test Error Cases:**
   ```bash
   # Non-existent commit
   cidx query "test" --at-commit nonexistent
   # Error: Commit 'nonexistent' not found

   # Ambiguous short hash
   cidx query "test" --at-commit a
   # Error: Commit hash must be at least 6 characters

   # Missing temporal index
   rm -rf .code-indexer/index/temporal/
   cidx query "test" --at-commit $COMMIT1
   # Warning: Temporal index not found, falling back
   ```

### Automated Tests
```python
def test_point_in_time_query():
    """Test querying at specific commit"""
    with temp_git_repo() as repo_path:
        # Create commits
        create_file(repo_path, "test.py", "def old_func(): pass")
        commit1 = git_commit(repo_path, "Add old function")

        create_file(repo_path, "test.py", "def new_func(): pass")
        commit2 = git_commit(repo_path, "Replace with new function")

        # Index
        temporal = TemporalIndexer(config_manager, vector_store)
        temporal.index_commits()

        service = TemporalSearchService(semantic_service, config_manager)

        # Query at first commit - should find old_func
        results1 = service.query_temporal(
            query="old_func",
            at_commit=commit1
        )
        assert len(results1.results) == 1
        assert "old_func" in results1.results[0].content

        # Query at first commit - should NOT find new_func
        results2 = service.query_temporal(
            query="new_func",
            at_commit=commit1
        )
        assert len(results2.results) == 0

        # Query at second commit - should find new_func
        results3 = service.query_temporal(
            query="new_func",
            at_commit=commit2
        )
        assert len(results3.results) == 1

def test_short_hash_resolution():
    """Test short commit hash resolution"""
    with temp_git_repo() as repo_path:
        # Create commit
        create_file(repo_path, "test.py", "code")
        full_hash = git_commit(repo_path, "Test")
        short_hash = full_hash[:7]

        # Index
        temporal = TemporalIndexer(config_manager, vector_store)
        temporal.index_commits()

        service = TemporalSearchService(semantic_service, config_manager)

        # Should work with short hash
        results = service.query_temporal(
            query="code",
            at_commit=short_hash
        )
        assert len(results.results) > 0
        assert results.results[0].temporal_context["at_commit"]["full_hash"] == full_hash

def test_file_rename_tracking():
    """Test handling of file renames"""
    with temp_git_repo() as repo_path:
        # Create file
        create_file(repo_path, "old_name.py", "def func(): pass")
        commit1 = git_commit(repo_path, "Create file")

        # Rename file
        subprocess.run(["git", "mv", "old_name.py", "new_name.py"],
                      cwd=repo_path)
        commit2 = git_commit(repo_path, "Rename file")

        # Index
        temporal = TemporalIndexer(config_manager, vector_store)
        temporal.index_commits()

        service = TemporalSearchService(semantic_service, config_manager)

        # Query at first commit - should show old name
        results1 = service.query_temporal(
            query="func",
            at_commit=commit1
        )
        assert results1.results[0].file_path == "old_name.py"

        # Query at second commit - should show new name
        results2 = service.query_temporal(
            query="func",
            at_commit=commit2
        )
        assert results2.results[0].file_path == "new_name.py"

def test_commit_not_found_error():
    """Test error handling for non-existent commits"""
    service = TemporalSearchService(semantic_service, config_manager)

    with pytest.raises(CommitNotFoundError) as exc:
        service.query_temporal(
            query="test",
            at_commit="nonexistent123"
        )

    assert "not found in temporal index" in str(exc.value)
```

## Error Scenarios

1. **Commit Not Found:**
   - Error: "Commit 'xyz' not found in temporal index"
   - Suggest running `cidx index --index-commits`

2. **Ambiguous Short Hash:**
   - Error: "Ambiguous short hash 'abc'. Please provide more characters."
   - User needs longer hash

3. **Hash Too Short:**
   - Error: "Commit hash must be at least 6 characters"
   - Enforce minimum length

4. **Temporal Index Missing:**
   - Warning: "Temporal index not found"
   - Fall back to current code search

5. **Commit Not in Index:**
   - Error: "Commit exists but not in temporal index"
   - Suggest re-indexing

## Performance Considerations

- Resolve commit hash once and cache
- Use indexed blob_hash lookup (O(1) with index)
- Limit results to requested limit (don't over-process)
- Target: <200ms semantic + <50ms commit filter = <250ms total

## Dependencies

- TemporalIndexer with completed index
- SQLite temporal database
- Git CLI for hash resolution
- Existing semantic search

## Notes

**Conversation Requirements:**
- Support short and full commit hashes
- Show file paths as they existed at commit
- Clear errors with suggested actions
- <300ms performance target
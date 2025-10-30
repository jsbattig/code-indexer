# Story: Evolution Display with Commit Context

## Story Description

**As a** developer investigating code history
**I want to** see the complete evolution timeline of code with commit messages and diffs
**So that** I can understand how and why code changed over time

**Conversation Context:**
- User specified need for code evolution visualization with commit messages and diffs
- Display timeline graph, full messages, actual code chunks, visual diffs
- Extract and highlight commit insights (security, performance, WHY/WHAT/HOW)
- Include summary statistics

## Acceptance Criteria

- [ ] Query with `cidx query "pattern" --show-evolution --show-code` displays evolution
- [ ] Evolution timeline graph shows all commits where blob appeared
- [ ] Full commit messages displayed for each version
- [ ] Actual code chunks shown from each version with line numbers
- [ ] Visual diffs displayed between versions (+ green for added, - red for removed)
- [ ] Commit insights extracted and highlighted (security, performance, bugfix, etc.)
- [ ] Summary displayed: timeline span, total changes, evolution path
- [ ] File renames tracked and displayed in timeline
- [ ] Performance: Evolution display completes in <500ms additional time

## Technical Implementation

### Evolution Display Command Flow
```python
# CLI integration for --show-evolution
@click.option("--show-evolution", is_flag=True,
              help="Display complete code evolution timeline")
@click.option("--show-code", is_flag=True,
              help="Include actual code from each version")
@click.option("--context-lines", type=int, default=3,
              help="Context lines for diffs (default: 3)")
def query(query_text, show_evolution, show_code, context_lines, ...):
    # Execute semantic search first
    results = search_service.search(query_text, limit=limit, min_score=min_score)

    if not results:
        console.print("[yellow]No results found[/yellow]")
        return

    # Display regular results first
    formatter.display_results(results)

    # Then show evolution if requested
    if show_evolution:
        # Check temporal index
        if not Path(".code-indexer/index/temporal/commits.db").exists():
            console.print("\n[yellow]⚠️ Evolution display requires temporal index. "
                         "Run 'cidx index --index-commits' first.[/yellow]")
            return

        # Lazy imports
        from src.code_indexer.services.temporal_search_service import (
            TemporalSearchService
        )
        from src.code_indexer.output.temporal_formatter import (
            TemporalFormatter
        )

        temporal_service = TemporalSearchService(semantic_service, config_manager)
        evolution_formatter = TemporalFormatter()

        console.print("\n[bold cyan]━━━ Code Evolution ━━━[/bold cyan]\n")

        # Show evolution for top results
        for i, result in enumerate(results[:3], 1):  # Limit to top 3
            blob_hash = result.metadata.get("blob_hash")
            if not blob_hash:
                continue

            console.print(f"[bold]Result {i}: {result.file_path}[/bold]")

            # Get evolution data
            evolution = temporal_service.get_code_evolution(
                blob_hash=blob_hash,
                show_code=show_code,
                max_versions=10
            )

            # Display timeline
            evolution_formatter.display_evolution_timeline(evolution)

            # Display diffs if requested
            if show_code and len(evolution.versions) > 1:
                evolution_formatter.display_code_diffs(
                    evolution,
                    max_diffs=3,
                    context_lines=context_lines
                )

            console.print("\n" + "─" * 80 + "\n")
```

### Evolution Data Retrieval
```python
class TemporalSearchService:
    def get_code_evolution(self, blob_hash: str,
                           show_code: bool = True,
                           max_versions: int = 10) -> CodeEvolution:
        """Retrieve complete evolution history for a blob"""
        import sqlite3  # Lazy import
        import subprocess

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # Get all commits with this blob
        query = """
            SELECT DISTINCT
                c.hash,
                c.date,
                c.author_name,
                c.author_email,
                c.message,
                c.parent_hashes,
                t.file_path
            FROM commits c
            JOIN trees t ON c.hash = t.commit_hash
            WHERE t.blob_hash = ?
            ORDER BY c.date ASC
        """

        cursor = conn.execute(query, (blob_hash,))
        commit_rows = cursor.fetchall()

        if not commit_rows:
            return CodeEvolution(
                query=self.last_query,
                chunk_identifier=blob_hash[:8],
                versions=[],
                total_commits=0
            )

        # Build version list
        versions = []
        unique_authors = set()

        for row in commit_rows[:max_versions]:
            # Retrieve code if requested
            code_content = ""
            if show_code:
                try:
                    # Use git cat-file to get blob content
                    result = subprocess.run(
                        ["git", "cat-file", "blob", blob_hash],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    code_content = result.stdout
                except subprocess.CalledProcessError:
                    code_content = "[Code retrieval failed]"

            version = CodeVersion(
                commit_hash=row["hash"],
                commit_date=datetime.fromtimestamp(row["date"]),
                author=row["author_name"],
                author_email=row["author_email"],
                message=row["message"] or "",
                parent_hashes=row["parent_hashes"],
                code=code_content,
                file_path=row["file_path"],
                blob_hash=blob_hash
            )
            versions.append(version)
            unique_authors.add(row["author_name"])

        # Extract insights from commit messages
        insights = []
        for version in versions:
            insight = self._extract_commit_insights(
                version.message,
                version.commit_hash
            )
            if insight:
                insights.append(insight)

        conn.close()

        return CodeEvolution(
            query=self.last_query,
            chunk_identifier=blob_hash[:8],
            versions=versions,
            total_commits=len(commit_rows),
            first_appearance=versions[0].commit_date if versions else None,
            last_modification=versions[-1].commit_date if versions else None,
            authors=list(unique_authors),
            insights=insights
        )
```

### Timeline Display Implementation
```python
class TemporalFormatter:
    def display_evolution_timeline(self, evolution: CodeEvolution):
        """Display evolution as interactive timeline"""
        from rich.tree import Tree
        from rich.panel import Panel

        if not evolution.versions:
            self.console.print("[yellow]No evolution history found[/yellow]")
            return

        # Create tree structure
        tree = Tree(
            f"[bold cyan]📚 Evolution of {evolution.chunk_identifier}[/bold cyan] "
            f"({evolution.total_commits} commits)"
        )

        # Track file renames
        prev_path = None

        for i, version in enumerate(evolution.versions):
            # Format date
            date_str = version.commit_date.strftime("%Y-%m-%d %H:%M")

            # Create commit node
            commit_node = tree.add(
                f"[cyan]{version.commit_hash[:8]}[/cyan] "
                f"[blue]{date_str}[/blue] "
                f"[yellow]{version.author}[/yellow]"
            )

            # Add commit message (first line + continuation indicator)
            message_lines = version.message.strip().split('\n')
            first_line = message_lines[0][:80]
            if len(message_lines) > 1 or len(message_lines[0]) > 80:
                first_line += "..."

            msg_node = commit_node.add(f"💬 {first_line}")

            # Show full message if it has structure
            if len(message_lines) > 1 and any(
                keyword in version.message
                for keyword in ["WHY:", "WHAT:", "HOW:"]
            ):
                for line in message_lines[1:4]:  # Show up to 3 more lines
                    if line.strip():
                        msg_node.add(f"[dim]{line[:100]}[/dim]")

            # Check for file rename
            if prev_path and prev_path != version.file_path:
                commit_node.add(
                    f"[yellow]📁 Renamed: {prev_path} → {version.file_path}[/yellow]"
                )
            prev_path = version.file_path

            # Add insights if found
            for insight in evolution.insights:
                if insight.commit_hash == version.commit_hash:
                    icon = self._get_insight_icon(insight.type)
                    commit_node.add(
                        f"{icon} [magenta]{insight.type.upper()}:[/magenta] "
                        f"{insight.description[:80]}"
                    )

        self.console.print(tree)

        # Display summary panel
        self._display_evolution_summary(evolution)

    def _get_insight_icon(self, insight_type: str) -> str:
        """Get icon for insight type"""
        icons = {
            "security": "🔒",
            "performance": "⚡",
            "bugfix": "🐛",
            "feature": "✨",
            "refactor": "♻️"
        }
        return icons.get(insight_type, "💡")
```

### Diff Display Implementation
```python
def display_code_diffs(self, evolution: CodeEvolution,
                       max_diffs: int = 3,
                       context_lines: int = 3):
    """Display diffs between consecutive versions"""
    import difflib  # Lazy import

    if len(evolution.versions) < 2:
        return

    self.console.print("\n[bold]📝 Code Changes:[/bold]\n")

    # Show diffs between consecutive versions
    for i in range(min(max_diffs, len(evolution.versions) - 1)):
        old_version = evolution.versions[i]
        new_version = evolution.versions[i + 1]

        # Header
        self.console.print(Panel(
            f"[cyan]{old_version.commit_hash[:8]}[/cyan] → "
            f"[cyan]{new_version.commit_hash[:8]}[/cyan]\n"
            f"[dim]{old_version.commit_date.strftime('%Y-%m-%d')} → "
            f"{new_version.commit_date.strftime('%Y-%m-%d')}[/dim]",
            title="Diff",
            border_style="blue"
        ))

        # Generate unified diff
        old_lines = old_version.code.splitlines(keepends=True)
        new_lines = new_version.code.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"{old_version.file_path}@{old_version.commit_hash[:8]}",
            tofile=f"{new_version.file_path}@{new_version.commit_hash[:8]}",
            lineterm='',
            n=context_lines
        )

        # Display with syntax highlighting
        diff_text = []
        for line in diff:
            if line.startswith('+++') or line.startswith('---'):
                diff_text.append(f"[bold blue]{line}[/bold blue]")
            elif line.startswith('@@'):
                diff_text.append(f"[cyan]{line}[/cyan]")
            elif line.startswith('+'):
                diff_text.append(f"[green]{line}[/green]")
            elif line.startswith('-'):
                diff_text.append(f"[red]{line}[/red]")
            else:
                diff_text.append(f"[dim]{line}[/dim]")

        for line in diff_text:
            self.console.print(line, end='')

        self.console.print("\n")
```

### Commit Insight Extraction
```python
def _extract_commit_insights(self, message: str,
                            commit_hash: str) -> Optional[CommitInsight]:
    """Extract structured insights from commit messages"""
    import re

    # Define pattern categories
    patterns = {
        "security": {
            "keywords": ["security", "vulnerability", "CVE", "exploit",
                        "injection", "XSS", "CSRF", "auth", "permission"],
            "regex": r"(?i)(fix|patch|secure|prevent).*(vulnerabil|exploit|inject)"
        },
        "performance": {
            "keywords": ["performance", "optimize", "speed", "faster",
                        "cache", "memory", "latency", "throughput"],
            "regex": r"(?i)(optimi|improve|enhance|speed|accelerate).*(performance|speed|memory)"
        },
        "bugfix": {
            "keywords": ["fix", "bug", "issue", "error", "crash",
                       "exception", "resolve", "correct"],
            "regex": r"(?i)(fix|solve|resolve|correct).*(bug|issue|error|crash)"
        },
        "feature": {
            "keywords": ["add", "implement", "feature", "support",
                       "introduce", "new", "enhance"],
            "regex": r"(?i)(add|implement|introduce|create).*(feature|support|function)"
        },
        "refactor": {
            "keywords": ["refactor", "cleanup", "reorganize",
                        "simplify", "extract", "rename", "restructure"],
            "regex": r"(?i)(refactor|clean|reorganiz|simplif|extract)"
        }
    }

    message_lower = message.lower()
    best_match = None
    best_score = 0

    # Check each pattern category
    for insight_type, pattern_data in patterns.items():
        score = 0

        # Check keywords
        found_keywords = []
        for keyword in pattern_data["keywords"]:
            if keyword in message_lower:
                found_keywords.append(keyword)
                score += 1

        # Check regex
        if re.search(pattern_data["regex"], message):
            score += 2

        # Keep best match
        if score > best_score:
            best_score = score
            best_match = (insight_type, found_keywords)

    if best_match and best_score >= 1:
        insight_type, keywords = best_match

        # Extract structured parts (WHY/WHAT/HOW)
        description = self._extract_structured_description(message)
        if not description:
            # Use first line as description
            description = message.split('\n')[0][:150]

        return CommitInsight(
            type=insight_type,
            description=description,
            commit_hash=commit_hash,
            keywords=keywords
        )

    return None

def _extract_structured_description(self, message: str) -> Optional[str]:
    """Extract WHY/WHAT/HOW from commit message"""
    import re

    # Look for structured format
    why_match = re.search(r"WHY:\s*(.+?)(?:WHAT:|HOW:|$)",
                         message, re.MULTILINE | re.DOTALL)
    what_match = re.search(r"WHAT:\s*(.+?)(?:WHY:|HOW:|$)",
                          message, re.MULTILINE | re.DOTALL)
    how_match = re.search(r"HOW:\s*(.+?)(?:WHY:|WHAT:|$)",
                         message, re.MULTILINE | re.DOTALL)

    parts = []
    if why_match:
        parts.append(f"WHY: {why_match.group(1).strip()[:50]}")
    if what_match:
        parts.append(f"WHAT: {what_match.group(1).strip()[:50]}")
    if how_match and len(parts) < 2:  # Limit length
        parts.append(f"HOW: {how_match.group(1).strip()[:50]}")

    if parts:
        return " | ".join(parts)

    return None
```

### Summary Statistics Display
```python
def _display_evolution_summary(self, evolution: CodeEvolution):
    """Display evolution summary statistics"""
    from rich.table import Table
    from rich.panel import Panel

    if not evolution.versions:
        return

    # Calculate statistics
    time_span = evolution.last_modification - evolution.first_appearance
    days_active = time_span.days

    # Create summary table
    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("📅 Timeline",
                 f"{evolution.first_appearance.strftime('%Y-%m-%d')} → "
                 f"{evolution.last_modification.strftime('%Y-%m-%d')} "
                 f"({days_active} days)")

    table.add_row("📊 Total Changes", str(evolution.total_commits))

    table.add_row("👥 Contributors",
                 ", ".join(evolution.authors[:3]) +
                 (f" +{len(evolution.authors)-3} more" if len(evolution.authors) > 3 else ""))

    # Insight summary
    if evolution.insights:
        insight_counts = {}
        for insight in evolution.insights:
            insight_counts[insight.type] = insight_counts.get(insight.type, 0) + 1

        insight_summary = ", ".join(
            f"{self._get_insight_icon(k)} {k}:{v}"
            for k, v in sorted(insight_counts.items())
        )
        table.add_row("💡 Insights", insight_summary)

    # File rename tracking
    unique_paths = set(v.file_path for v in evolution.versions)
    if len(unique_paths) > 1:
        table.add_row("📁 File Paths",
                     f"{len(unique_paths)} different paths (renamed)")

    self.console.print(Panel(table, title="Summary", border_style="green"))
```

## Test Scenarios

### Manual Test Plan

1. **Create Rich Test History:**
   ```bash
   cd /tmp/test-evolution
   git init

   # V1: Initial implementation
   cat > calculator.py << 'EOF'
   def add(a, b):
       return a + b
   EOF
   git add calculator.py
   git commit -m "Add basic addition function"

   # V2: Bug fix
   cat > calculator.py << 'EOF'
   def add(a, b):
       # Fixed: Handle None values
       if a is None or b is None:
           return 0
       return a + b
   EOF
   git add calculator.py
   git commit -m "Fix: Handle None values in addition

   WHY: Function crashed when None was passed
   WHAT: Add None checking before addition
   HOW: Return 0 for None inputs"

   # V3: Performance
   cat > calculator.py << 'EOF'
   from functools import lru_cache

   @lru_cache(maxsize=128)
   def add(a, b):
       # Cached for performance
       if a is None or b is None:
           return 0
       return a + b
   EOF
   git add calculator.py
   git commit -m "Performance: Add caching to addition function

   Improves performance by 50% for repeated calculations"

   # V4: Rename file
   git mv calculator.py math_utils.py
   git commit -m "Refactor: Rename calculator to math_utils"

   # Index
   cidx init
   cidx index
   cidx index --index-commits
   ```

2. **Test Evolution Display:**
   ```bash
   # Basic evolution
   cidx query "add function" --show-evolution
   # Should show timeline tree with 4 commits
   # Should highlight insights: FIX, PERFORMANCE, REFACTOR

   # With code
   cidx query "add function" --show-evolution --show-code
   # Should show actual code from each version
   # Should show diffs between versions

   # Custom context lines
   cidx query "add function" --show-evolution --show-code --context-lines 5
   # Should show more context in diffs
   ```

3. **Verify Insights:**
   - Look for 🐛 BUGFIX icon and description
   - Look for ⚡ PERFORMANCE icon and description
   - Look for ♻️ REFACTOR icon and description
   - Check WHY/WHAT/HOW extraction in descriptions

4. **Verify File Rename:**
   - Should show "📁 Renamed: calculator.py → math_utils.py"
   - Summary should show "2 different paths (renamed)"

### Automated Tests
```python
def test_evolution_display_with_insights():
    """Test complete evolution display with insights"""
    with temp_git_repo() as repo_path:
        # Create evolution with different commit types
        commits = [
            ("Initial", "def func(): return 1", "Add initial function"),
            ("Security", "def func(): return hash(1)",
             "Security: Fix vulnerability\n\nWHY: Exposed sensitive data"),
            ("Performance", "@cache\ndef func(): return hash(1)",
             "Performance: Add caching for 10x speedup"),
        ]

        for name, code, msg in commits:
            create_file(repo_path, "test.py", code)
            git_commit(repo_path, msg)

        # Index and get evolution
        temporal = TemporalIndexer(config_manager, vector_store)
        temporal.index_commits()

        service = TemporalSearchService(semantic_service, config_manager)
        results = service.search("func")
        evolution = service.get_code_evolution(
            results[0].metadata["blob_hash"],
            show_code=True
        )

        # Verify evolution
        assert len(evolution.versions) == 3
        assert len(evolution.insights) >= 2  # Security and Performance

        # Check insight types
        insight_types = [i.type for i in evolution.insights]
        assert "security" in insight_types
        assert "performance" in insight_types

        # Verify WHY extraction
        security_insight = next(i for i in evolution.insights
                              if i.type == "security")
        assert "WHY:" in security_insight.description

def test_diff_generation_display():
    """Test diff display between versions"""
    formatter = TemporalFormatter()

    # Create evolution with changes
    evolution = CodeEvolution(
        query="test",
        chunk_identifier="abc123",
        versions=[
            CodeVersion(
                commit_hash="commit1",
                commit_date=datetime.now(),
                author="Dev1",
                message="Initial",
                code="def func():\n    return 1\n",
                file_path="test.py",
                blob_hash="blob1"
            ),
            CodeVersion(
                commit_hash="commit2",
                commit_date=datetime.now(),
                author="Dev2",
                message="Update",
                code="def func():\n    # Fixed\n    return 2\n",
                file_path="test.py",
                blob_hash="blob2"
            )
        ],
        total_commits=2
    )

    # Capture diff output
    with capture_console_output() as output:
        formatter.display_code_diffs(evolution, max_diffs=1)

    diff_output = output.getvalue()
    assert "-    return 1" in diff_output  # Removed line
    assert "+    # Fixed" in diff_output   # Added line
    assert "+    return 2" in diff_output  # Added line

def test_file_rename_tracking():
    """Test file rename display in evolution"""
    with temp_git_repo() as repo_path:
        # Create and rename file
        create_file(repo_path, "old.py", "code")
        commit1 = git_commit(repo_path, "Create")

        subprocess.run(["git", "mv", "old.py", "new.py"], cwd=repo_path)
        commit2 = git_commit(repo_path, "Rename")

        # Index and get evolution
        temporal = TemporalIndexer(config_manager, vector_store)
        temporal.index_commits()

        # ... get evolution ...

        # Verify rename detected
        assert evolution.versions[0].file_path == "old.py"
        assert evolution.versions[1].file_path == "new.py"

        # Test display
        formatter = TemporalFormatter()
        with capture_console_output() as output:
            formatter.display_evolution_timeline(evolution)

        output_text = output.getvalue()
        assert "Renamed: old.py → new.py" in output_text
```

## Error Scenarios

1. **No Temporal Index:**
   - Warning: "Evolution display requires temporal index"
   - Show regular search results only

2. **No Evolution History:**
   - Message: "No evolution history found for this code"
   - Might be new code or index incomplete

3. **Code Retrieval Failure:**
   - Show "[Code retrieval failed]" placeholder
   - Continue with other data

4. **Very Long Evolution (>100 commits):**
   - Truncate to latest 10 versions
   - Show: "Displaying latest 10 of 123 commits"

5. **Large Diffs:**
   - Truncate very large diffs
   - Show: "Diff truncated (>500 lines)"

## Performance Considerations

- Lazy load git blob content only when --show-code used
- Limit evolution display to top 3 search results
- Cache commit message parsing results
- Batch SQLite queries for all blobs
- Target: <500ms additional overhead for evolution display

## Dependencies

- Temporal index with commit data
- Git CLI for blob content retrieval
- difflib for diff generation (lazy import)
- Rich library for visualization
- SQLite database queries

## Notes

**Conversation Requirements:**
- Complete evolution timeline with all commits
- Full commit messages displayed
- Visual diffs with color coding
- Insight extraction and highlighting
- Summary statistics
- File rename tracking
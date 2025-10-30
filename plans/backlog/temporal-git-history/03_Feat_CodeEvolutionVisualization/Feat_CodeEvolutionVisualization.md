# Feature: Code Evolution Visualization

## Feature Overview

**Purpose:** Display how code has evolved over time with visual diffs, commit messages, and insights to help developers understand the complete history and context of code changes.

**User Value:** Developers and AI agents can see the full evolution timeline of code patterns, understand why changes were made through commit messages, visualize diffs between versions, and extract insights about security fixes, performance improvements, and architectural decisions.

## User Stories

### Story 1: Evolution Display with Commit Context
**Priority:** P0 (Key differentiator)
**Effort:** L (Large)
**Description:** Display code evolution timeline with commit messages, visual diffs, and extracted insights when users query with --show-evolution flag.

## Technical Design

### Components

**TemporalFormatter** (`src/code_indexer/output/temporal_formatter.py`):
```python
class TemporalFormatter:
    def __init__(self):
        self.console = Console()
        self.theme = Theme({
            "added": "green",
            "removed": "red",
            "modified": "yellow",
            "commit": "cyan",
            "date": "blue",
            "insight": "magenta"
        })

    def display_evolution(self, evolution_data: CodeEvolution):
        """Display complete code evolution with timeline and diffs"""

    def _display_evolution_graph(self, commits: List[CommitInfo]):
        """Display commit timeline as Rich Tree"""

    def _display_code_version(self, version: CodeVersion):
        """Display single code version with commit context"""

    def _display_diff(self, old_code: str, new_code: str):
        """Display visual diff between versions"""

    def _extract_commit_insights(self, message: str) -> CommitInsights:
        """Parse commit message for insights"""

    def _format_commit_summary(self, evolution: CodeEvolution) -> str:
        """Create evolution summary statistics"""
```

### Evolution Data Structures

```python
@dataclass
class CodeVersion:
    """Single version of code with metadata"""
    commit_hash: str
    commit_date: datetime
    author: str
    message: str
    code: str
    file_path: str
    blob_hash: str

@dataclass
class CodeEvolution:
    """Complete evolution of a code chunk"""
    query: str
    chunk_identifier: str
    versions: List[CodeVersion]
    total_commits: int
    first_appearance: datetime
    last_modification: datetime
    authors: List[str]
    insights: List[CommitInsight]

@dataclass
class CommitInsight:
    """Extracted insight from commit message"""
    type: str  # "security", "performance", "bugfix", "feature", "refactor"
    description: str
    commit_hash: str
    keywords: List[str]
```

### Integration with Temporal Search

```python
class TemporalSearchService:
    def get_code_evolution(self, blob_hash: str,
                           show_code: bool = True,
                           max_versions: int = 10) -> CodeEvolution:
        """Get complete evolution timeline for a blob"""
        import sqlite3  # Lazy import

        conn = sqlite3.connect(self.db_path)

        # Get all commits where blob appeared
        query = """
            SELECT DISTINCT
                c.hash, c.date, c.author_name, c.message,
                t.file_path
            FROM commits c
            JOIN trees t ON c.hash = t.commit_hash
            WHERE t.blob_hash = ?
            ORDER BY c.date ASC
        """

        cursor = conn.execute(query, (blob_hash,))
        commits = cursor.fetchall()

        versions = []
        for commit in commits[:max_versions]:
            # Get code if requested
            code = ""
            if show_code:
                code = self._retrieve_blob_content(blob_hash, commit[0])

            version = CodeVersion(
                commit_hash=commit[0],
                commit_date=datetime.fromtimestamp(commit[1]),
                author=commit[2],
                message=commit[3],
                code=code,
                file_path=commit[4],
                blob_hash=blob_hash
            )
            versions.append(version)

        # Extract insights from all commit messages
        insights = []
        for version in versions:
            insight = self._extract_commit_insights(version.message)
            if insight:
                insights.append(insight)

        conn.close()

        return CodeEvolution(
            query=self.last_query,
            chunk_identifier=blob_hash[:8],
            versions=versions,
            total_commits=len(commits),
            first_appearance=versions[0].commit_date if versions else None,
            last_modification=versions[-1].commit_date if versions else None,
            authors=list(set(v.author for v in versions)),
            insights=insights
        )
```

### Visual Diff Implementation

```python
def _display_diff(self, old_code: str, new_code: str,
                 context_lines: int = 3):
    """Display visual diff between code versions"""
    import difflib  # Lazy import

    # Generate unified diff
    old_lines = old_code.splitlines(keepends=True)
    new_lines = new_code.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        lineterm='',
        n=context_lines
    )

    # Display with colors
    for line in diff:
        if line.startswith('+++') or line.startswith('---'):
            self.console.print(line, style="bold blue")
        elif line.startswith('@@'):
            self.console.print(line, style="cyan")
        elif line.startswith('+'):
            self.console.print(line, style="green")
        elif line.startswith('-'):
            self.console.print(line, style="red")
        else:
            self.console.print(line, style="dim")
```

### Commit Insight Extraction

```python
def _extract_commit_insights(self, message: str) -> Optional[CommitInsight]:
    """Extract insights from commit message patterns"""

    # Security patterns
    security_keywords = ["security", "vulnerability", "CVE", "exploit",
                        "injection", "XSS", "CSRF", "auth"]

    # Performance patterns
    perf_keywords = ["performance", "optimize", "speed", "faster",
                     "cache", "memory", "bottleneck"]

    # Bug fix patterns
    bug_keywords = ["fix", "bug", "issue", "error", "crash",
                   "exception", "resolve"]

    # Feature patterns
    feature_keywords = ["add", "implement", "feature", "support",
                       "introduce", "new"]

    # Refactor patterns
    refactor_keywords = ["refactor", "cleanup", "reorganize",
                        "simplify", "extract", "rename"]

    message_lower = message.lower()

    # Check patterns
    for keyword_set, insight_type in [
        (security_keywords, "security"),
        (perf_keywords, "performance"),
        (bug_keywords, "bugfix"),
        (feature_keywords, "feature"),
        (refactor_keywords, "refactor")
    ]:
        found_keywords = [kw for kw in keyword_set if kw in message_lower]
        if found_keywords:
            # Extract WHY/WHAT/HOW if present
            why_match = re.search(r"WHY:\s*(.+?)(?:WHAT:|HOW:|$)",
                                 message, re.MULTILINE | re.DOTALL)
            what_match = re.search(r"WHAT:\s*(.+?)(?:WHY:|HOW:|$)",
                                  message, re.MULTILINE | re.DOTALL)

            description = message[:200]
            if why_match:
                description = f"WHY: {why_match.group(1).strip()[:100]}"
            elif what_match:
                description = f"WHAT: {what_match.group(1).strip()[:100]}"

            return CommitInsight(
                type=insight_type,
                description=description,
                commit_hash=self.current_commit_hash,
                keywords=found_keywords
            )

    return None
```

### Evolution Timeline Display

```python
def _display_evolution_graph(self, evolution: CodeEvolution):
    """Display commit timeline as Rich Tree"""
    from rich.tree import Tree
    from rich.table import Table
    from rich.panel import Panel

    # Create timeline tree
    tree = Tree(f"[bold]Code Evolution:[/bold] {evolution.chunk_identifier}")

    for i, version in enumerate(evolution.versions):
        # Format commit node
        commit_label = (
            f"[cyan]{version.commit_hash[:8]}[/cyan] "
            f"[blue]{version.commit_date.strftime('%Y-%m-%d')}[/blue] "
            f"[dim]{version.author}[/dim]"
        )

        node = tree.add(commit_label)

        # Add commit message
        msg_lines = version.message.split('\n')
        msg_preview = msg_lines[0][:80]
        if len(msg_lines) > 1 or len(msg_lines[0]) > 80:
            msg_preview += "..."

        node.add(f"[dim]{msg_preview}[/dim]")

        # Add insights if found
        for insight in evolution.insights:
            if insight.commit_hash == version.commit_hash:
                insight_label = f"[magenta]💡 {insight.type.upper()}:[/magenta] "
                node.add(f"{insight_label}{insight.description[:60]}")

        # Add file path if changed
        if i > 0 and version.file_path != evolution.versions[i-1].file_path:
            node.add(f"[yellow]📁 Renamed to: {version.file_path}[/yellow]")

    self.console.print(tree)

    # Display summary statistics
    summary = Table(title="Evolution Summary", show_header=False)
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", style="white")

    summary.add_row("Timeline Span",
                   f"{evolution.first_appearance.strftime('%Y-%m-%d')} → "
                   f"{evolution.last_modification.strftime('%Y-%m-%d')}")
    summary.add_row("Total Changes", str(evolution.total_commits))
    summary.add_row("Contributors", ", ".join(evolution.authors[:3]))

    if evolution.insights:
        insight_summary = {}
        for insight in evolution.insights:
            insight_summary[insight.type] = insight_summary.get(insight.type, 0) + 1
        summary.add_row("Insights",
                       ", ".join(f"{k}: {v}" for k, v in insight_summary.items()))

    self.console.print(summary)
```

### CLI Integration

```python
# In cli.py query command
@click.option("--show-evolution", is_flag=True,
              help="Show complete evolution timeline for results")
@click.option("--show-code", is_flag=True,
              help="Display actual code from each version")
@click.option("--context-lines", type=int, default=3,
              help="Number of context lines in diffs")
def query(..., show_evolution, show_code, context_lines):
    if show_evolution:
        # Check temporal index exists
        if not Path(".code-indexer/index/temporal/commits.db").exists():
            console.print("[yellow]⚠️ --show-evolution requires temporal index. "
                         "Run 'cidx index --index-commits' first.[/yellow]")
            show_evolution = False

    # Execute search (temporal or regular)
    results = search_service.search(query_text, ...)

    if show_evolution and results:
        # Lazy imports
        from src.code_indexer.services.temporal_search_service import (
            TemporalSearchService
        )
        from src.code_indexer.output.temporal_formatter import (
            TemporalFormatter
        )

        temporal_service = TemporalSearchService(semantic_service, config_manager)
        formatter = TemporalFormatter()

        for result in results[:5]:  # Limit to top 5 for readability
            blob_hash = result.metadata.get("blob_hash")
            if blob_hash:
                evolution = temporal_service.get_code_evolution(
                    blob_hash=blob_hash,
                    show_code=show_code,
                    max_versions=10
                )

                # Display evolution
                formatter.display_evolution(evolution)

                # Show diffs if requested
                if show_code and len(evolution.versions) > 1:
                    console.print("\n[bold]Code Changes:[/bold]")
                    for i in range(1, min(3, len(evolution.versions))):  # Top 3 diffs
                        old = evolution.versions[i-1]
                        new = evolution.versions[i]
                        console.print(f"\n[dim]Diff: {old.commit_hash[:8]} → "
                                    f"{new.commit_hash[:8]}[/dim]")
                        formatter._display_diff(old.code, new.code, context_lines)
```

## Acceptance Criteria

### Story 1: Evolution Display with Commit Context
- [ ] Query with `--show-evolution` displays timeline graph of all commits
- [ ] Shows full commit messages for each version
- [ ] `--show-code` displays actual code chunks from each version
- [ ] Visual diffs shown between versions (green +, red -)
- [ ] Extracts and highlights commit insights (security, performance, etc.)
- [ ] Displays summary: timeline span, total changes, contributors
- [ ] Handles file renames in evolution display
- [ ] Performance: Evolution display adds <500ms to query time

## Testing Requirements

### Manual Test Plan

1. **Create Test Evolution:**
   ```bash
   cd /tmp/test-evolution
   git init

   # Version 1: Initial implementation
   cat > auth.py << 'EOF'
   def authenticate(username, password):
       # Simple auth
       return username == "admin" and password == "password"
   EOF
   git add auth.py
   git commit -m "Add basic authentication"

   # Version 2: Security fix
   cat > auth.py << 'EOF'
   def authenticate(username, password):
       # Fixed: Use hashed passwords
       import hashlib
       hashed = hashlib.sha256(password.encode()).hexdigest()
       return check_database(username, hashed)
   EOF
   git add auth.py
   git commit -m "SECURITY: Fix plaintext password vulnerability

   WHY: Plaintext passwords are a security risk
   WHAT: Implement SHA256 hashing for passwords
   HOW: Use hashlib to hash before comparison"

   # Version 3: Performance improvement
   cat > auth.py << 'EOF'
   @lru_cache(maxsize=100)
   def authenticate(username, password):
       # Cached for performance
       import hashlib
       hashed = hashlib.sha256(password.encode()).hexdigest()
       return check_database(username, hashed)
   EOF
   git add auth.py
   git commit -m "PERFORMANCE: Add caching to authentication

   Reduces database queries by 80% for repeated auth attempts"

   # Index
   cidx init
   cidx index
   cidx index --index-commits
   ```

2. **Test Evolution Display:**
   ```bash
   # Basic evolution
   cidx query "authenticate" --show-evolution
   # Should show timeline tree with 3 commits

   # With code display
   cidx query "authenticate" --show-evolution --show-code
   # Should show code from each version

   # With diffs
   cidx query "authenticate" --show-evolution --show-code --context-lines 5
   # Should show diffs between versions
   ```

3. **Test Insight Extraction:**
   ```bash
   # Should highlight SECURITY and PERFORMANCE insights
   cidx query "authenticate" --show-evolution
   # Look for: "💡 SECURITY: Fix plaintext password..."
   # Look for: "💡 PERFORMANCE: Add caching..."
   ```

4. **Test File Renames:**
   ```bash
   git mv auth.py authentication.py
   git commit -m "Rename auth module"
   cidx index --index-commits

   cidx query "authenticate" --show-evolution
   # Should show: "📁 Renamed to: authentication.py"
   ```

### Automated Tests
```python
def test_evolution_display():
    """Test code evolution visualization"""
    with temp_git_repo() as repo_path:
        # Create evolution
        versions = [
            ("v1", "def func(): return 1"),
            ("v2", "def func(): return 2  # Fixed bug"),
            ("v3", "def func():\n    # Optimized\n    return 2")
        ]

        for version, code in versions:
            create_file(repo_path, "test.py", code)
            git_commit(repo_path, f"Update to {version}")

        # Index
        temporal = TemporalIndexer(config_manager, vector_store)
        temporal.index_commits()

        # Get evolution
        service = TemporalSearchService(semantic_service, config_manager)
        results = service.search("func")
        blob_hash = results[0].metadata["blob_hash"]

        evolution = service.get_code_evolution(blob_hash, show_code=True)

        # Verify evolution data
        assert len(evolution.versions) == 3
        assert evolution.total_commits == 3
        assert all(v.code for v in evolution.versions)

def test_commit_insight_extraction():
    """Test extracting insights from commit messages"""
    formatter = TemporalFormatter()

    # Test security insight
    security_msg = "Fix SQL injection vulnerability in user login"
    insight = formatter._extract_commit_insights(security_msg)
    assert insight.type == "security"
    assert "injection" in insight.keywords

    # Test performance insight
    perf_msg = "Optimize database queries for faster response"
    insight = formatter._extract_commit_insights(perf_msg)
    assert insight.type == "performance"
    assert "optimize" in insight.keywords

    # Test WHY/WHAT extraction
    structured_msg = """Fix authentication bug

    WHY: Users couldn't log in with valid credentials
    WHAT: Fixed token validation logic
    HOW: Check expiry before validation"""

    insight = formatter._extract_commit_insights(structured_msg)
    assert "WHY:" in insight.description

def test_diff_generation():
    """Test visual diff display"""
    formatter = TemporalFormatter()

    old_code = "def func():\n    return 1\n"
    new_code = "def func():\n    # Fixed\n    return 2\n"

    # Capture output
    with capture_console_output() as output:
        formatter._display_diff(old_code, new_code)

    diff_output = output.getvalue()
    assert "-    return 1" in diff_output
    assert "+    # Fixed" in diff_output
    assert "+    return 2" in diff_output
```

## Error Scenarios

1. **No Evolution Data:**
   - Message: "No historical data available for this code"
   - Show current version only

2. **Large Evolution (>100 commits):**
   - Truncate to most recent 10 versions
   - Show message: "Showing latest 10 of 100+ versions"

3. **Code Retrieval Failure:**
   - Show placeholder: "[Code not available]"
   - Continue with other versions

4. **Temporal Index Missing:**
   - Warning: "--show-evolution requires temporal index"
   - Degrade to regular search

## Performance Considerations

- Lazy load evolution data only when requested
- Limit default display to 10 versions
- Cache blob content retrieval
- Show progress for long evolution queries
- Target: <500ms additional overhead

## Dependencies

- Temporal indexing complete
- SQLite database with commit data
- difflib for diff generation (lazy)
- Rich for visualization
- Git CLI for blob retrieval

## Notes

**Conversation Requirements:**
- Display evolution timeline with all commits
- Show full commit messages
- Extract and highlight insights
- Visual diffs with color coding
- Summary statistics
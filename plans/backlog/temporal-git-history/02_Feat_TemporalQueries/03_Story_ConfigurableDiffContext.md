# Story: Configurable Diff Context with Enhanced Semantic Search

## Story Description

**As an** AI coding agent analyzing code evolution
**I want to** configure the amount of surrounding context included in indexed git diffs
**So that** I can balance storage efficiency with semantic search quality for better code history analysis

**Conversation Context:**
- User identified that git diff context lines (`-U` flag) significantly impact semantic search quality
- Default git behavior shows 3 lines of context, but 5 lines provides better results
- More context = better embeddings (function signatures, class structure, related methods visible)
- Storage trade-off: `-U5` adds 40% more storage vs `-U3` but dramatically improves search results
- User wants this configurable with sensible defaults

## Acceptance Criteria

```gherkin
Given I want to optimize semantic search quality
When I run temporal indexing with default settings
Then diffs should be stored with 5 lines of context (U5) by default
And embeddings should capture function signatures and surrounding methods
And search quality should be significantly better than U3 default

Given I want to customize diff context for my use case
When I run cidx index --index-commits --diff-context 10
Then diffs should be stored with 10 lines of context
And search results should include even more surrounding code context
And storage should increase proportionally

Given I want minimal storage usage
When I run cidx index --index-commits --diff-context 0
Then diffs should store only changed lines (no context)
And storage should be minimized
And search quality should be reduced but functional

Given I want to see current diff context configuration
When I run cidx config --show
Then output should display current diff-context setting
And show default value if not configured

Given I want to make diff context a permanent setting
When I run cidx config --diff-context 5
Then setting should be saved to .code-indexer/config.yaml
And future indexing operations should use this value
And I should not need to specify --diff-context on every index command

Given I have an existing temporal index with U3 context
When I re-index with cidx index --index-commits --diff-context 5 --force
Then existing diffs should be regenerated with 5-line context
And embeddings should be recalculated
And search quality should improve immediately

Given invalid diff context value provided
When I run cidx index --index-commits --diff-context -1
Then command should fail with clear error message
And suggest valid range (0-20 recommended)
And prevent indexing with invalid configuration
```

## Implementation Status

**Status**: ⏳ PENDING

**Implementation Date**: Not started

**Completion Percentage**: 0%

## Algorithm

```
Diff Context Configuration System:

Configuration Schema:
  diff_context:
    temporal_indexing: 5  # Default for git diff generation
    min_value: 0          # No context (compact)
    max_value: 50         # Reasonable upper limit
    recommended_range: [3, 10]

Temporal Diff Scanner Enhancement:
  __init__(codebase_dir, config_manager):
    self.codebase_dir = codebase_dir
    self.config_manager = config_manager
    self.diff_context_lines = config_manager.get(
      "diff_context.temporal_indexing",
      default=5  # Sensible default
    )

  get_diffs_for_commit(commit_hash):
    FOR each modified file in commit:
      # Generate diff with configured context
      diff_result = subprocess.run([
        "git", "show",
        f"-U{self.diff_context_lines}",  # Configured context
        commit_hash,
        "--", file_path
      ])

      # Parse and store diff content
      diff_content = extract_diff_content(diff_result.stdout)

      RETURN DiffInfo(
        file_path=file_path,
        diff_content=diff_content,  # Contains U{N} context
        ...
      )

CLI Integration:
  cidx index --index-commits --diff-context N:
    VALIDATE N in [0, 50]
    IF invalid: RAISE error with valid range
    SET temporary config override
    INVOKE TemporalIndexer with config
    RETURN success

  cidx config --diff-context N:
    VALIDATE N in [0, 50]
    IF invalid: RAISE error
    SAVE to .code-indexer/config.yaml
    PERSIST for future operations
    RETURN success with confirmation

  cidx config --show:
    LOAD config from .code-indexer/config.yaml
    DISPLAY all settings including diff_context
    HIGHLIGHT non-default values
    RETURN formatted output

Validation Logic:
  validate_diff_context(value):
    IF value < 0 OR value > 50:
      RAISE ConfigError(
        f"Invalid diff-context {value}. "
        f"Valid range: 0-50 (recommended: 3-10). "
        f"0=no context, 3=default git, 5=recommended, 10=maximum context"
      )

    IF value > 20:
      WARN "Large context values (>20) significantly increase storage. "
           "Recommended range: 3-10 lines"

    RETURN valid

Re-indexing with New Context:
  cidx index --index-commits --diff-context N --force:
    CLEAR existing temporal index
    RECONFIGURE TemporalDiffScanner with new N
    RE-SCAN all commits
    REGENERATE all diffs with new context
    RECOMPUTE embeddings
    REBUILD vector index
    RETURN success

Configuration Precedence:
  1. CLI argument --diff-context N (highest priority)
  2. .code-indexer/config.yaml setting
  3. Default value: 5 (lowest priority)
```

## Technical Implementation

### Configuration Schema Enhancement

```yaml
# .code-indexer/config.yaml
diff_context:
  temporal_indexing: 5  # Default context lines for temporal diffs
  # Valid range: 0-50
  # 0 = no context (compact)
  # 3 = git default
  # 5 = recommended (balance of quality and storage)
  # 10 = maximum context for best search quality
```

### TemporalDiffScanner Enhancement

```python
# src/code_indexer/services/temporal/temporal_diff_scanner.py

class TemporalDiffScanner:
    """Scans git commits and extracts diff information with configurable context."""

    def __init__(self, codebase_dir: Path, config_manager: ConfigManager):
        self.codebase_dir = codebase_dir
        self.config_manager = config_manager

        # Get configured diff context (default: 5)
        self.diff_context_lines = config_manager.get(
            "diff_context.temporal_indexing",
            default=5
        )

        self.logger = logging.getLogger(__name__)
        self.logger.info(
            f"TemporalDiffScanner initialized with {self.diff_context_lines} "
            f"lines of diff context"
        )

    def get_diffs_for_commit(self, commit_hash: str) -> List[DiffInfo]:
        """
        Get diffs for all files changed in a commit with configured context.

        Context lines controlled by self.diff_context_lines:
        - 0: No context (only changed lines)
        - 3: Git default
        - 5: Recommended (better embeddings)
        - 10+: Maximum context (function signatures, class structure)
        """
        # ... existing status parsing logic ...

        elif status == "M":  # Modified file
            is_binary = self._is_binary_file(file_path)

            if is_binary:
                diff_content = f"Binary file modified: {file_path}"
                diff_type = "binary"
            else:
                # Get diff with configured context lines
                content_result = subprocess.run(
                    [
                        "git", "show",
                        f"-U{self.diff_context_lines}",  # Configurable context
                        commit_hash,
                        "--", file_path
                    ],
                    cwd=self.codebase_dir,
                    capture_output=True,
                    text=True
                )

                if "Binary files differ" in content_result.stdout:
                    diff_content = f"Binary file modified: {file_path}"
                    diff_type = "binary"
                else:
                    # Extract diff (includes context lines)
                    lines = content_result.stdout.split("\n")
                    diff_lines = []
                    in_diff = False
                    for line in lines:
                        if line.startswith("@@"):
                            in_diff = True
                        if in_diff:
                            diff_lines.append(line)

                    diff_content = "\n".join(diff_lines)
                    diff_type = "modified"

            diffs.append(DiffInfo(
                file_path=file_path,
                diff_type=diff_type,
                commit_hash=commit_hash,
                diff_content=diff_content,  # Contains U{N} context
                old_path=""
            ))

        # ... rest of implementation ...
```

### CLI Integration

```python
# src/code_indexer/cli.py

@cli.command(name="index")
@click.option(
    "--index-commits",
    is_flag=True,
    help="Index git commit history for temporal queries"
)
@click.option(
    "--diff-context",
    type=int,
    default=None,  # None = use config/default
    help="Number of context lines for git diffs (0-50, default: 5). "
         "Higher values improve search quality but increase storage. "
         "Recommended: 5 (balance), 10 (best quality), 0 (minimal storage)"
)
@click.option(
    "--force",
    is_flag=True,
    help="Force re-indexing even if index exists"
)
def index_command(
    index_commits: bool,
    diff_context: Optional[int],
    force: bool,
    ...
):
    """Index codebase for semantic search"""

    config_manager = ConfigManager(config_path)

    # Validate and apply diff-context if provided
    if diff_context is not None:
        _validate_diff_context(diff_context)

        # Temporary override for this operation
        config_manager.set_temporary(
            "diff_context.temporal_indexing",
            diff_context
        )

        if diff_context > 10:
            console.print(
                f"[yellow]⚠️ Using {diff_context} context lines. "
                f"This will significantly increase storage.[/yellow]"
            )

    if index_commits:
        # Clear existing index if --force
        if force:
            temporal_index_path = config_path / "index" / "temporal"
            if temporal_index_path.exists():
                console.print("[yellow]Clearing existing temporal index...[/yellow]")
                shutil.rmtree(temporal_index_path)

        # Initialize temporal indexer with configured diff context
        from .services.temporal.temporal_indexer import TemporalIndexer

        temporal_indexer = TemporalIndexer(
            config_manager=config_manager,
            vector_store=vector_store
        )

        console.print(
            f"[dim]Using {config_manager.get('diff_context.temporal_indexing', 5)} "
            f"lines of diff context[/dim]"
        )

        temporal_indexer.index_commits()
        console.print("[green]✓[/green] Temporal indexing complete")


@cli.group(name="config")
def config_group():
    """Manage CIDX configuration"""
    pass


@config_group.command(name="set-diff-context")
@click.argument("context_lines", type=int)
def set_diff_context(context_lines: int):
    """
    Set default diff context for temporal indexing.

    Examples:
      cidx config set-diff-context 5    # Recommended balance
      cidx config set-diff-context 10   # Maximum quality
      cidx config set-diff-context 0    # Minimal storage
    """
    config_path = Path(".code-indexer")

    if not config_path.exists():
        console.print("[red]Error: Not a CIDX project. Run 'cidx init' first.[/red]")
        return

    # Validate
    _validate_diff_context(context_lines)

    # Save to config
    config_manager = ConfigManager(config_path)
    config_manager.set("diff_context.temporal_indexing", context_lines)
    config_manager.save()

    console.print(
        f"[green]✓[/green] Diff context set to {context_lines} lines\n"
    )

    if context_lines == 0:
        console.print("[dim]Minimal context: Compact storage, reduced search quality[/dim]")
    elif context_lines == 5:
        console.print("[dim]Recommended: Good balance of quality and storage[/dim]")
    elif context_lines >= 10:
        console.print("[dim]Maximum context: Best search quality, larger storage[/dim]")


@config_group.command(name="show")
def show_config():
    """Display current CIDX configuration"""
    config_path = Path(".code-indexer")

    if not config_path.exists():
        console.print("[red]Error: Not a CIDX project. Run 'cidx init' first.[/red]")
        return

    config_manager = ConfigManager(config_path)

    console.print("[bold]CIDX Configuration:[/bold]\n")

    # Show diff context
    diff_context = config_manager.get("diff_context.temporal_indexing", 5)
    is_default = diff_context == 5

    console.print(f"[cyan]Diff Context:[/cyan] {diff_context} lines", end="")
    if is_default:
        console.print(" [dim](default)[/dim]")
    else:
        console.print(" [yellow](custom)[/yellow]")

    # Show other settings...


def _validate_diff_context(value: int) -> None:
    """Validate diff context value and provide helpful errors."""
    if value < 0:
        console.print(
            f"[red]Error: Invalid diff-context {value}. "
            f"Value must be 0 or greater.[/red]\n"
            f"[dim]Recommended values:[/dim]\n"
            f"  0  = No context (minimal storage)\n"
            f"  3  = Git default\n"
            f"  5  = Recommended (balance)\n"
            f"  10 = Maximum quality\n"
        )
        raise click.Abort()

    if value > 50:
        console.print(
            f"[red]Error: Invalid diff-context {value}. "
            f"Maximum allowed is 50.[/red]\n"
            f"[yellow]Large context values dramatically increase storage.[/yellow]\n"
            f"[dim]Consider using 5-10 for best balance.[/dim]"
        )
        raise click.Abort()

    if value > 20:
        console.print(
            f"[yellow]⚠️ Warning: Context value {value} is very large.[/yellow]\n"
            f"[dim]This will significantly increase storage requirements.\n"
            f"Recommended range: 3-10 lines[/dim]\n"
        )
```

### Configuration Manager Enhancement

```python
# src/code_indexer/config/config_manager.py

class ConfigManager:
    """Manages CIDX configuration with temporary overrides."""

    def __init__(self, config_path: Path):
        self.config_path = config_path / "config.yaml"
        self.config = self._load_config()
        self.temporary_overrides = {}  # For --flag overrides

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value with temporary override support.

        Precedence:
        1. Temporary override (from CLI flag)
        2. Saved config
        3. Default value
        """
        # Check temporary override first
        if key in self.temporary_overrides:
            return self.temporary_overrides[key]

        # Navigate nested keys (e.g., "diff_context.temporal_indexing")
        keys = key.split(".")
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value if value is not None else default

    def set_temporary(self, key: str, value: Any) -> None:
        """Set temporary override (not persisted)."""
        self.temporary_overrides[key] = value

    def set(self, key: str, value: Any) -> None:
        """Set configuration value (requires save() to persist)."""
        keys = key.split(".")
        config = self.config

        # Navigate/create nested structure
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def save(self) -> None:
        """Persist configuration to disk."""
        import yaml

        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.config_path, "w") as f:
            yaml.dump(self.config, f, default_flow_style=False)
```

## Test Scenarios

### Unit Tests

```python
# tests/unit/services/temporal/test_temporal_diff_scanner_configurable_context.py

def test_default_diff_context():
    """Test default diff context is 5 lines."""
    config = ConfigManager(temp_config_path)
    scanner = TemporalDiffScanner(repo_path, config)

    assert scanner.diff_context_lines == 5


def test_custom_diff_context():
    """Test configuring custom diff context."""
    config = ConfigManager(temp_config_path)
    config.set("diff_context.temporal_indexing", 10)

    scanner = TemporalDiffScanner(repo_path, config)

    assert scanner.diff_context_lines == 10


def test_diff_generation_with_u5_context():
    """Test git diff generated with -U5 flag."""
    config = ConfigManager(temp_config_path)
    config.set("diff_context.temporal_indexing", 5)

    scanner = TemporalDiffScanner(repo_path, config)

    with patch("subprocess.run") as mock_run:
        scanner.get_diffs_for_commit("abc123")

        # Verify git show called with -U5
        mock_run.assert_any_call(
            ["git", "show", "-U5", "abc123", "--", ANY],
            cwd=repo_path,
            capture_output=True,
            text=True
        )


def test_diff_generation_with_u0_minimal_context():
    """Test minimal context (U0) for compact storage."""
    config = ConfigManager(temp_config_path)
    config.set("diff_context.temporal_indexing", 0)

    scanner = TemporalDiffScanner(repo_path, config)

    with patch("subprocess.run") as mock_run:
        scanner.get_diffs_for_commit("abc123")

        # Verify git show called with -U0
        mock_run.assert_any_call(
            ["git", "show", "-U0", "abc123", "--", ANY],
            cwd=repo_path,
            capture_output=True,
            text=True
        )


def test_validate_diff_context_valid_values():
    """Test validation accepts valid context values."""
    # Valid values should not raise
    _validate_diff_context(0)
    _validate_diff_context(3)
    _validate_diff_context(5)
    _validate_diff_context(10)
    _validate_diff_context(20)
    _validate_diff_context(50)


def test_validate_diff_context_invalid_negative():
    """Test validation rejects negative values."""
    with pytest.raises(click.Abort):
        _validate_diff_context(-1)


def test_validate_diff_context_invalid_too_large():
    """Test validation rejects values over 50."""
    with pytest.raises(click.Abort):
        _validate_diff_context(51)


def test_validate_diff_context_warns_on_large_values():
    """Test validation warns for values over 20."""
    with patch("console.print") as mock_print:
        _validate_diff_context(25)

        # Should print warning
        assert any("Warning" in str(call) for call in mock_print.call_args_list)


def test_config_precedence_cli_override():
    """Test CLI flag overrides config file setting."""
    config = ConfigManager(temp_config_path)
    config.set("diff_context.temporal_indexing", 3)
    config.save()

    # CLI override
    config.set_temporary("diff_context.temporal_indexing", 10)

    # Temporary should win
    assert config.get("diff_context.temporal_indexing") == 10


def test_config_persistence():
    """Test config setting persisted to disk."""
    config = ConfigManager(temp_config_path)
    config.set("diff_context.temporal_indexing", 7)
    config.save()

    # Reload from disk
    config2 = ConfigManager(temp_config_path)
    assert config2.get("diff_context.temporal_indexing") == 7
```

### E2E Tests

```python
# tests/e2e/temporal/test_configurable_diff_context_e2e.py

def test_indexing_with_default_diff_context(temp_repo):
    """Test temporal indexing uses U5 by default."""
    # Run indexing without --diff-context flag
    result = run_cli(["cidx", "index", "--index-commits"])

    assert result.exit_code == 0
    assert "Using 5 lines of diff context" in result.output


def test_indexing_with_custom_diff_context(temp_repo):
    """Test temporal indexing with custom context via CLI flag."""
    # Run with custom context
    result = run_cli([
        "cidx", "index",
        "--index-commits",
        "--diff-context", "10"
    ])

    assert result.exit_code == 0
    assert "Using 10 lines of diff context" in result.output


def test_config_set_diff_context(temp_repo):
    """Test setting diff context via config command."""
    result = run_cli(["cidx", "config", "set-diff-context", "8"])

    assert result.exit_code == 0
    assert "Diff context set to 8 lines" in result.output

    # Verify persisted
    config_file = Path(".code-indexer/config.yaml")
    assert config_file.exists()

    import yaml
    with open(config_file) as f:
        config = yaml.safe_load(f)

    assert config["diff_context"]["temporal_indexing"] == 8


def test_config_show_displays_diff_context(temp_repo):
    """Test config show command displays diff context."""
    # Set custom value
    run_cli(["cidx", "config", "set-diff-context", "7"])

    # Show config
    result = run_cli(["cidx", "config", "show"])

    assert result.exit_code == 0
    assert "Diff Context: 7 lines" in result.output
    assert "(custom)" in result.output  # Not default


def test_search_quality_improvement_with_u5_vs_u0(temp_repo_with_function_change):
    """
    Test that U5 context provides better search results than U0.

    Scenario:
    - Commit modifies function body
    - U5 includes function signature in diff
    - U0 only includes changed lines
    - Search for "function signature" finds U5, not U0
    """
    # Index with U0 (minimal context)
    run_cli([
        "cidx", "index",
        "--index-commits",
        "--diff-context", "0"
    ])

    # Query for function signature
    result_u0 = run_cli([
        "cidx", "query",
        "function authenticate",
        "--time-range", "2024-01-01..2024-12-31"
    ])

    # Re-index with U5 (recommended context)
    run_cli([
        "cidx", "index",
        "--index-commits",
        "--diff-context", "5",
        "--force"
    ])

    result_u5 = run_cli([
        "cidx", "query",
        "function authenticate",
        "--time-range", "2024-01-01..2024-12-31"
    ])

    # U5 should find more relevant results
    # (U0 might miss if function signature not in changed lines)
    assert len(result_u5.results) >= len(result_u0.results)

    # U5 results should have better scores (more context for embeddings)
    if result_u5.results and result_u0.results:
        assert result_u5.results[0].score >= result_u0.results[0].score


def test_force_reindex_with_new_context(temp_repo):
    """Test --force re-indexes with new context."""
    # Initial index with U3
    run_cli([
        "cidx", "index",
        "--index-commits",
        "--diff-context", "3"
    ])

    original_index_time = Path(".code-indexer/index/temporal/commits.db").stat().st_mtime

    time.sleep(1)  # Ensure different timestamp

    # Force re-index with U5
    result = run_cli([
        "cidx", "index",
        "--index-commits",
        "--diff-context", "5",
        "--force"
    ])

    assert result.exit_code == 0
    assert "Clearing existing temporal index" in result.output

    # Verify index regenerated
    new_index_time = Path(".code-indexer/index/temporal/commits.db").stat().st_mtime
    assert new_index_time > original_index_time


def test_invalid_diff_context_rejected(temp_repo):
    """Test invalid context values rejected with clear errors."""
    # Negative value
    result1 = run_cli([
        "cidx", "index",
        "--index-commits",
        "--diff-context", "-5"
    ])

    assert result1.exit_code != 0
    assert "Error: Invalid diff-context" in result1.output
    assert "must be 0 or greater" in result1.output

    # Too large
    result2 = run_cli([
        "cidx", "index",
        "--index-commits",
        "--diff-context", "100"
    ])

    assert result2.exit_code != 0
    assert "Error: Invalid diff-context" in result2.output
    assert "Maximum allowed is 50" in result2.output


def test_large_context_warning(temp_repo):
    """Test warning displayed for large context values."""
    result = run_cli([
        "cidx", "index",
        "--index-commits",
        "--diff-context", "25"
    ])

    assert result.exit_code == 0
    assert "Warning: Context value 25 is very large" in result.output
    assert "significantly increase storage" in result.output
```

### Manual Test Plan

1. **Default Behavior Test:**
   ```bash
   cd /tmp/test-repo
   cidx init
   cidx index --index-commits
   # Should show "Using 5 lines of diff context"

   # Query and verify results show function signatures
   cidx query "authentication" --time-range 2024-01-01..2024-12-31
   ```

2. **Custom Context via CLI:**
   ```bash
   # Use maximum context for best quality
   cidx index --index-commits --diff-context 10 --force

   # Query should show more surrounding code
   cidx query "login function" --time-range 2024-01-01..2024-12-31
   # Results should include class definitions, imports, etc.
   ```

3. **Minimal Context for Storage:**
   ```bash
   # Use no context for compact storage
   cidx index --index-commits --diff-context 0 --force

   # Query still works but with less context
   cidx query "authentication" --time-range 2024-01-01..2024-12-31
   # Results show only changed lines
   ```

4. **Persistent Configuration:**
   ```bash
   # Set default for project
   cidx config set-diff-context 7

   # Verify saved
   cidx config show
   # Should show "Diff Context: 7 lines (custom)"

   # Index without flag (should use 7)
   cidx index --index-commits
   # Should show "Using 7 lines of diff context"
   ```

5. **Search Quality Comparison:**
   ```bash
   # Create test repo with function changes
   cd /tmp/comparison-test
   # ... create commits with function modifications ...

   # Index with U0
   cidx index --index-commits --diff-context 0
   cidx query "function definition" > results_u0.txt

   # Re-index with U5
   cidx index --index-commits --diff-context 5 --force
   cidx query "function definition" > results_u5.txt

   # Compare result counts and scores
   # U5 should have better relevance scores
   ```

6. **Error Handling:**
   ```bash
   # Try invalid values
   cidx config set-diff-context -1
   # Should fail: "Value must be 0 or greater"

   cidx config set-diff-context 100
   # Should fail: "Maximum allowed is 50"

   cidx index --index-commits --diff-context 30
   # Should warn: "Context value 30 is very large"
   # But should succeed
   ```

## Performance Considerations

- **Storage Impact**: U5 adds ~40% more storage vs U3, but U10 adds ~140%
- **Indexing Time**: Diff generation time negligible compared to embedding computation
- **Query Performance**: No impact on query speed (context in stored diffs, not query path)
- **Embedding Quality**: More context = significantly better embeddings = better search results

**Recommended Values:**
- **U5** (default): Best balance - 40% more storage, dramatically better results
- **U3**: Git default - adequate but misses important context
- **U10**: Maximum quality - for critical codebases where search quality is paramount
- **U0**: Compact - for storage-constrained environments, reduced search quality

## Dependencies

- TemporalDiffScanner (enhancement required)
- ConfigManager (enhancement for nested config and temporary overrides)
- CLI command enhancements (--diff-context flag, config subcommands)
- TemporalIndexer (uses TemporalDiffScanner)

## Notes

**Design Decisions:**
- Default to U5 instead of U3 (git default) because semantic search benefits significantly outweigh storage cost
- Maximum of 50 lines (reasonable upper bound - beyond this is diminishing returns)
- CLI flag overrides config file for flexibility
- Clear warnings for large values to guide users toward sensible settings
- Force re-indexing required to change context (ensures index consistency)

**Future Enhancements:**
- Adaptive context based on change type (large refactors get more context)
- Per-language context recommendations (Python might benefit from more context than JSON)
- Storage analytics showing context vs. quality trade-offs

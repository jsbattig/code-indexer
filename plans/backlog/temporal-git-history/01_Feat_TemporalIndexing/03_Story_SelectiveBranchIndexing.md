# Story: Selective Branch Indexing with Pattern Matching

## Story Description

**As a** developer managing a large repository with hundreds of branches
**I want** to selectively index specific branches or branch patterns
**So that** I can control cost and storage while still accessing relevant historical context

**Conversation Context:**
- User emphasized: "We need to focus on 'current' branch and if the user passes a param indexes ALL branches or a set of branches"
- Default behavior: Index current branch only (91%+ commit coverage, cost-effective)
- Opt-in for complete history: `--all-branches` flag with cost warnings
- Advanced use case: `--branches "pattern1,pattern2"` for selective indexing

## Acceptance Criteria

- [ ] Default: `cidx index --index-commits` indexes current branch only
- [ ] Complete history: `cidx index --index-commits --all-branches` with confirmation prompt
- [ ] Selective patterns: `cidx index --index-commits --branches "main,develop,feature/*,bugfix/*"`
- [ ] Branch pattern matching supports glob syntax (*, ?, [])
- [ ] Cost estimation displayed before indexing with confirmation: "Index X additional commits? (~Y MB storage, ~$Z API cost) [y/N]"
- [ ] Branch metadata tracked for all indexed commits in `commit_branches` table
- [ ] Validation: Warn if no branches match pattern
- [ ] Configuration: Store `indexed_branches` in temporal_meta.json
- [ ] Incremental: Re-running with different patterns adds new branches (doesn't delete old)
- [ ] Error handling: Invalid patterns show helpful error messages

## Technical Implementation

### CLI Flag Design

```python
# In cli.py index command
@click.option(
    '--index-commits',
    is_flag=True,
    help='Index git commit history for temporal search (default: current branch only)'
)
@click.option(
    '--all-branches',
    is_flag=True,
    help='Index ALL branches (expensive, requires confirmation). Use with --index-commits.'
)
@click.option(
    '--branches',
    type=str,
    help='Comma-separated branch patterns to index (e.g., "main,develop,feature/*"). Use with --index-commits.'
)
def index(index_commits: bool, all_branches: bool, branches: Optional[str], ...):
    """Index repository with optional temporal indexing"""

    # Validation: Cannot combine --all-branches and --branches
    if all_branches and branches:
        raise click.UsageError(
            "--all-branches and --branches are mutually exclusive. "
            "Use --all-branches for all branches, or --branches 'pattern' for specific ones."
        )

    # Determine branch strategy
    if index_commits:
        if all_branches:
            branch_strategy = BranchStrategy.ALL_BRANCHES
            branch_patterns = None
        elif branches:
            branch_strategy = BranchStrategy.PATTERNS
            branch_patterns = [p.strip() for p in branches.split(',')]
        else:
            branch_strategy = BranchStrategy.CURRENT_ONLY
            branch_patterns = None

        # Delegate to temporal indexer
        temporal_indexer.index_commits(
            branch_strategy=branch_strategy,
            branch_patterns=branch_patterns,
            show_cost_warning=True
        )
```

### Branch Strategy Enum

```python
# In services/temporal_indexer.py
from enum import Enum

class BranchStrategy(Enum):
    """Strategy for selecting which branches to index"""
    CURRENT_ONLY = "current"      # Default: HEAD branch only
    ALL_BRANCHES = "all"           # Complete history: all branches
    PATTERNS = "patterns"          # Selective: glob patterns
```

### Branch Pattern Matching

```python
import fnmatch
from typing import List, Set

class BranchPatternMatcher:
    """Matches branch names against glob patterns"""

    def __init__(self, patterns: List[str]):
        """
        Args:
            patterns: List of glob patterns (e.g., ["main", "feature/*", "bugfix/*"])
        """
        self.patterns = patterns

    def matches(self, branch_name: str) -> bool:
        """Check if branch matches any pattern"""
        for pattern in self.patterns:
            if fnmatch.fnmatch(branch_name, pattern):
                return True
        return False

    def filter_branches(self, all_branches: List[str]) -> List[str]:
        """Filter branch list to only matching branches"""
        return [b for b in all_branches if self.matches(b)]

    def validate_patterns(self, all_branches: List[str]) -> tuple[bool, str]:
        """
        Validate that patterns match at least one branch.

        Returns:
            (valid, message): True if valid, error message if not
        """
        matched = self.filter_branches(all_branches)
        if not matched:
            return False, (
                f"No branches match patterns: {', '.join(self.patterns)}\n"
                f"Available branches: {', '.join(all_branches[:10])}..."
            )
        return True, f"Matched {len(matched)} branches"
```

### Branch Discovery

```python
class TemporalIndexer:
    def _get_branches_to_index(
        self,
        strategy: BranchStrategy,
        patterns: Optional[List[str]] = None
    ) -> List[str]:
        """
        Determine which branches to index based on strategy.

        Returns:
            List of branch names to index
        """
        if strategy == BranchStrategy.CURRENT_ONLY:
            # Get current branch only
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                check=True
            )
            current_branch = result.stdout.strip()
            return [current_branch]

        elif strategy == BranchStrategy.ALL_BRANCHES:
            # Get all branches (local + remote)
            result = subprocess.run(
                ["git", "branch", "-a", "--format=%(refname:short)"],
                capture_output=True,
                text=True,
                check=True
            )
            all_branches = [
                b.strip() for b in result.stdout.split('\n')
                if b.strip() and not b.startswith('origin/HEAD')
            ]
            # Remove duplicates (local branches appear as both "main" and "origin/main")
            return list(set(all_branches))

        elif strategy == BranchStrategy.PATTERNS:
            # Get all branches, then filter by patterns
            result = subprocess.run(
                ["git", "branch", "-a", "--format=%(refname:short)"],
                capture_output=True,
                text=True,
                check=True
            )
            all_branches = [b.strip() for b in result.stdout.split('\n') if b.strip()]

            # Pattern matching
            matcher = BranchPatternMatcher(patterns)

            # Validate patterns match at least one branch
            valid, message = matcher.validate_patterns(all_branches)
            if not valid:
                raise ValueError(message)

            matched = matcher.filter_branches(all_branches)
            self.logger.info(f"Branch patterns {patterns} matched {len(matched)} branches")
            return matched

        else:
            raise ValueError(f"Unknown branch strategy: {strategy}")
```

### Cost Estimation

```python
class CostEstimator:
    """Estimates storage and API costs for branch indexing"""

    # VoyageAI pricing (as of 2024)
    COST_PER_MILLION_TOKENS = 0.12  # voyage-code-2
    AVG_TOKENS_PER_FILE = 500
    AVG_CHUNKS_PER_FILE = 3

    def estimate_branch_indexing_cost(
        self,
        branches: List[str],
        current_branch: str
    ) -> dict:
        """
        Estimate cost of indexing specific branches.

        Returns:
            {
                'additional_commits': int,
                'additional_blobs': int,
                'storage_mb': float,
                'api_cost_usd': float,
                'total_commits': int
            }
        """
        # Get commits for current branch
        current_commits = self._get_commit_count(current_branch)

        # Get commits for all requested branches
        all_commits_set = set()
        for branch in branches:
            commits = self._get_commits_for_branch(branch)
            all_commits_set.update(commits)

        total_commits = len(all_commits_set)
        additional_commits = total_commits - current_commits

        # Estimate blobs (rough: avg 150 files per commit, 92% dedup)
        additional_blobs = int(additional_commits * 150 * 0.08)  # Only 8% new after dedup

        # Storage: JSON vectors + SQLite metadata
        storage_mb = additional_blobs * self.AVG_CHUNKS_PER_FILE * 2.5  # ~2.5KB per chunk

        # API cost
        total_tokens = additional_blobs * self.AVG_TOKENS_PER_FILE
        api_cost_usd = (total_tokens / 1_000_000) * self.COST_PER_MILLION_TOKENS

        return {
            'additional_commits': additional_commits,
            'additional_blobs': additional_blobs,
            'storage_mb': round(storage_mb, 1),
            'api_cost_usd': round(api_cost_usd, 2),
            'total_commits': total_commits
        }

    def _get_commit_count(self, branch: str) -> int:
        """Get total commits in branch"""
        result = subprocess.run(
            ["git", "rev-list", "--count", branch],
            capture_output=True,
            text=True,
            check=True
        )
        return int(result.stdout.strip())

    def _get_commits_for_branch(self, branch: str) -> Set[str]:
        """Get all commit hashes in branch"""
        result = subprocess.run(
            ["git", "rev-list", branch],
            capture_output=True,
            text=True,
            check=True
        )
        return set(result.stdout.strip().split('\n'))
```

### Cost Warning Display

```python
def show_cost_warning_and_confirm(
    branches: List[str],
    strategy: BranchStrategy,
    estimator: CostEstimator
) -> bool:
    """
    Show cost estimate and get user confirmation.

    Returns:
        True if user confirms, False otherwise
    """
    if strategy == BranchStrategy.CURRENT_ONLY:
        # No warning for default single-branch
        return True

    # Get current branch
    current_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True
    ).stdout.strip()

    # Estimate cost
    cost = estimator.estimate_branch_indexing_cost(branches, current_branch)

    # Display warning
    console = Console()
    console.print("\n[bold yellow]⚠️  Multi-Branch Indexing Cost Estimate[/bold yellow]\n")
    console.print(f"Branches to index: [cyan]{len(branches)}[/cyan]")
    console.print(f"Additional commits: [cyan]{cost['additional_commits']:,}[/cyan]")
    console.print(f"Estimated new blobs: [cyan]{cost['additional_blobs']:,}[/cyan]")
    console.print(f"Storage increase: [cyan]~{cost['storage_mb']} MB[/cyan]")
    console.print(f"API cost estimate: [cyan]~${cost['api_cost_usd']}[/cyan]")
    console.print()

    # Confirmation prompt
    response = click.confirm(
        "Proceed with multi-branch indexing?",
        default=False
    )

    if not response:
        console.print("[yellow]Multi-branch indexing cancelled.[/yellow]")
        return False

    return True
```

### Updated TemporalIndexer.index_commits

```python
class TemporalIndexer:
    def index_commits(
        self,
        branch_strategy: BranchStrategy = BranchStrategy.CURRENT_ONLY,
        branch_patterns: Optional[List[str]] = None,
        max_commits: Optional[int] = None,
        since_date: Optional[str] = None,
        show_cost_warning: bool = True,
        incremental: bool = True,
        progress_callback: Optional[Callable] = None
    ) -> IndexingResult:
        """
        Index git commit history with branch selection.

        Args:
            branch_strategy: Which branches to index (current/all/patterns)
            branch_patterns: Glob patterns if strategy=PATTERNS
            max_commits: Limit number of commits (optional)
            since_date: Only index commits after date (optional)
            show_cost_warning: Show cost estimate for multi-branch (default True)
            incremental: Skip already-indexed commits (default True)
            progress_callback: Progress updates
        """
        # 1. Determine which branches to index
        branches = self._get_branches_to_index(branch_strategy, branch_patterns)
        self.logger.info(f"Indexing {len(branches)} branches: {branches}")

        # 2. Cost warning and confirmation (multi-branch only)
        if show_cost_warning:
            estimator = CostEstimator()
            if not show_cost_warning_and_confirm(branches, branch_strategy, estimator):
                return IndexingResult(
                    success=False,
                    message="Indexing cancelled by user"
                )

        # 3. Get all unique commits across selected branches
        all_commits_set = set()
        branch_commit_map = {}  # commit_hash -> [branch_names]

        for branch in branches:
            commits = self._get_commits_for_branch(branch, max_commits, since_date)
            branch_commit_map.setdefault(branch, [])
            for commit_hash in commits:
                all_commits_set.add(commit_hash)
                if commit_hash not in branch_commit_map:
                    branch_commit_map[commit_hash] = []
                branch_commit_map[commit_hash].append(branch)

        # 4. Filter out already-indexed commits (if incremental)
        if incremental:
            already_indexed = self._get_indexed_commits()
            new_commits = all_commits_set - already_indexed
            if not new_commits:
                return IndexingResult(
                    success=True,
                    total_commits=0,
                    message="No new commits to index"
                )
        else:
            new_commits = all_commits_set

        # 5. Process commits (existing logic from Story 1)
        # ... [blob discovery, deduplication, vectorization] ...

        # 6. Store branch metadata for each commit
        for commit_hash in new_commits:
            commit_branches = branch_commit_map.get(commit_hash, [])
            self._store_commit_branch_metadata(
                commit_hash=commit_hash,
                branches=commit_branches,
                is_head=(commit_hash == self._get_head_commit())
            )

        # 7. Update temporal metadata
        self._update_temporal_metadata(
            indexed_branches=branches,
            branch_strategy=branch_strategy.value,
            branch_patterns=branch_patterns
        )

        return IndexingResult(
            success=True,
            total_commits=len(new_commits),
            message=f"Indexed {len(new_commits)} commits across {len(branches)} branches"
        )

    def _store_commit_branch_metadata(
        self,
        commit_hash: str,
        branches: List[str],
        is_head: bool
    ):
        """Store which branches contain this commit"""
        with self.commits_db.connection() as conn:
            for branch_name in branches:
                conn.execute("""
                    INSERT OR REPLACE INTO commit_branches
                    (commit_hash, branch_name, is_head, indexed_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    commit_hash,
                    branch_name,
                    1 if is_head else 0,
                    int(time.time())
                ))
            conn.commit()
```

### Metadata Storage

```python
def _update_temporal_metadata(
    self,
    indexed_branches: List[str],
    branch_strategy: str,
    branch_patterns: Optional[List[str]]
):
    """Update temporal_meta.json with branch indexing info"""
    meta_path = Path(".code-indexer/index/temporal/temporal_meta.json")

    # Load existing metadata
    meta = {}
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)

    # Update branch information (cumulative - add new branches)
    existing_branches = set(meta.get("indexed_branches", []))
    existing_branches.update(indexed_branches)

    meta.update({
        "indexed_branches": sorted(list(existing_branches)),
        "branch_strategy": branch_strategy,
        "branch_patterns": branch_patterns,
        "last_branch_update": int(time.time())
    })

    # Save
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)
```

## Test Scenarios

### Test 1: Default Single-Branch Indexing
**Setup:** Fresh repo with 100 commits on main, 3 feature branches
**Action:** `cidx index --index-commits`
**Expected:**
- Only main branch indexed
- No cost warning shown
- temporal_meta.json: `indexed_branches: ["main"]`, `branch_strategy: "current"`

### Test 2: All-Branches with Cost Warning
**Setup:** Repo with 1000 commits on main, 50 feature branches, 200 additional commits
**Action:** `cidx index --index-commits --all-branches`
**Expected:**
- Cost estimate shown: "~200 additional commits, ~$2.50"
- User prompted for confirmation [y/N]
- If yes: All 51 branches indexed
- temporal_meta.json: `indexed_branches: [all 51 branches]`, `branch_strategy: "all"`

### Test 3: Pattern Matching - Valid Patterns
**Setup:** Branches: main, develop, feature/auth, feature/ui, bugfix/login
**Action:** `cidx index --index-commits --branches "main,feature/*"`
**Expected:**
- Matched branches: main, feature/auth, feature/ui (3 total)
- Cost estimate for additional commits in feature/* branches
- temporal_meta.json: `branch_patterns: ["main", "feature/*"]`

### Test 4: Pattern Matching - No Matches
**Setup:** Branches: main, develop
**Action:** `cidx index --index-commits --branches "feature/*,bugfix/*"`
**Expected:**
- Error: "No branches match patterns: feature/\*, bugfix/\*"
- Helpful message: "Available branches: main, develop"
- No indexing performed

### Test 5: Incremental with New Branch
**Setup:**
- Previously indexed: main (100 commits)
- New branch: develop (120 commits, 20 new)
**Action:** `cidx index --index-commits --branches "main,develop"`
**Expected:**
- Only 20 new commits indexed
- Progress: "Processing 20 new commits..."
- temporal_meta.json: `indexed_branches: ["main", "develop"]`

### Test 6: Conflicting Flags Error
**Action:** `cidx index --index-commits --all-branches --branches "main"`
**Expected:**
- Error: "--all-branches and --branches are mutually exclusive"
- Clear usage guidance shown

### Test 7: Daemon Mode Integration
**Setup:** daemon.enabled: true, repo with multiple branches
**Action:** `cidx index --index-commits --all-branches` (via daemon)
**Expected:**
- Cost warning displayed in CLI (not daemon)
- Confirmation prompt in CLI
- If confirmed: Delegation to daemon with branch_strategy
- Progress streamed back correctly
- temporal_meta.json updated in daemon context

## Configuration

```json
// .code-indexer/config.json
{
  "temporal": {
    "enabled": true,
    "indexed_mode": "patterns",  // "current" | "all" | "patterns"
    "indexed_branches": ["main", "develop", "feature/auth"],
    "branch_patterns": ["main", "develop", "feature/*"]
  }
}
```

## Daemon Mode Testing

### Test 8: Daemon Mode Cost Warning Flow
**Setup:** daemon.enabled: true
**Action:** CLI: `cidx index --index-commits --all-branches`
**Expected:**
1. CLI shows cost estimate (not daemon)
2. CLI prompts user for confirmation
3. If yes: CLI delegates to daemon with `all_branches=True`
4. Daemon executes indexing (no user interaction)
5. Progress streamed back to CLI
6. Cache invalidated automatically

### Test 9: Daemon Mode Pattern Validation
**Setup:** daemon.enabled: true
**Action:** CLI: `cidx index --index-commits --branches "invalid/*"`
**Expected:**
1. CLI validates patterns BEFORE delegating
2. If no matches: Error shown in CLI, no delegation
3. If matches: Delegation proceeds normally

## API Server Integration

When implementing Feature 04 (API Server Registration), the `temporal_options` parameter should support:

```json
{
  "temporal_options": {
    "branch_strategy": "patterns",  // "current" | "all" | "patterns"
    "branch_patterns": ["main", "develop", "release/*"],
    "max_commits": null,
    "since_date": null
  }
}
```

The server should:
1. Validate patterns match at least one branch
2. Estimate cost and store in job metadata
3. Execute indexing asynchronously (long-running)
4. Store indexed branch info in golden repo config

## Dependencies

- Story 1 (GitHistoryIndexingWithBlobDedup): Branch metadata table, blob registry
- fnmatch module: Standard library glob pattern matching
- CostEstimator: New class for estimation logic
- Click confirmation prompts: User interaction

## Notes

**Key User Requirements:**
- "Focus on 'current' branch" → Default single-branch indexing
- "if the user passes a param indexes ALL branches" → Explicit --all-branches flag
- "or a set of branches" → Pattern matching with --branches

**Cost Control:**
- Cost warnings prevent accidental expensive operations
- Default behavior optimized for 91%+ coverage at minimal cost
- Advanced users can opt-in to complete history

**Incremental Design:**
- Re-running with different patterns ADDS branches (doesn't replace)
- Deduplication ensures no wasted vectorization
- Metadata tracks complete indexing history

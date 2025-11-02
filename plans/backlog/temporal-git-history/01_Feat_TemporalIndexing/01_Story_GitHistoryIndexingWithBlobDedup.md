# Story: Git History Indexing with Blob Deduplication and Branch Metadata

## Story Description

**As a** AI coding agent
**I want to** index a repository's git history with storage deduplication and branch awareness
**So that** I can search across historical code cost-effectively while preserving branch context

**Conversation Context:**
- User specified need for semantic search across git history to find removed code
- Emphasized storage efficiency via git blob deduplication (92%+ savings achieved)
- Required to handle 40K+ commit repositories efficiently
- Analysis of Evolution repo (1,135 branches, 89K commits) showed single-branch indexing covers 91.6% of commits
- Default to current branch only, opt-in for all branches to avoid 85% storage increase

## Acceptance Criteria

### Core Functionality (Both Modes)
- [ ] Running `cidx index --index-commits` indexes current branch only (default behavior)
- [ ] Running `cidx index --index-commits --all-branches` indexes all branches
- [ ] Creates SQLite database at `.code-indexer/index/temporal/commits.db` with commit graph
- [ ] Creates `commit_branches` table tracking which branches each commit appears in
- [ ] Builds blob registry at `.code-indexer/index/temporal/blob_registry.db` (SQLite) mapping blob_hash → point_ids
- [ ] Reuses existing vectors for blobs already in HEAD (deduplication)
- [ ] Only embeds new blobs not present in current HEAD
- [ ] Stores temporal metadata including branch information in `.code-indexer/index/temporal/temporal_meta.json`

### Daemon Mode Functionality
- [ ] Temporal indexing works when `daemon.enabled: true` in config
- [ ] CLI automatically delegates to daemon via `_index_via_daemon(index_commits=True)`
- [ ] Daemon's `exposed_index_blocking()` handles temporal indexing via TemporalIndexer
- [ ] Progress callbacks stream from daemon to CLI in real-time
- [ ] Cache invalidated before temporal indexing starts (daemon mode)
- [ ] Graceful fallback to standalone mode if daemon unavailable
- [ ] All flags (`--all-branches`, `--max-commits`, `--since-date`) passed through delegation

### User Experience
- [ ] Shows progress during indexing: "Indexing commits: 500/5000 (10%) [development branch]"
- [ ] Displays cost warning before indexing all branches: "⚠️ Indexing 715 branches will use ~514MB storage and cost ~$4.74"
- [ ] Requires user confirmation (y/N) for --all-branches in large repos (>50 branches)
- [ ] Shows final statistics: branches indexed, commits per branch, deduplication ratio

### Performance
- [ ] Achieves >92% storage savings through blob deduplication
- [ ] Handles large repositories (40K+ commits, 1000+ branches) without running out of memory
- [ ] Single-branch indexing is fast (similar to current indexing performance)

## Technical Architecture (CRITICAL - Read First)

### What We Index: Full Blob Versions, NOT Diffs

**CRITICAL DECISION:** We index **complete file versions (blobs)** at each point in git history, NOT diffs.

```
✅ CORRECT: Index full blob content
Commit abc123: user.py (blob def456)
→ Index complete file with full class User, all methods, imports, context

❌ WRONG: Index diffs
Commit abc123: user.py diff
→ Would only index: "+ def greet(): ..." (no context, can't do semantic search)
```

**Rationale:**
1. **Semantic search requires full context** - Users query "authentication with JWT" needs complete class implementation
2. **Users want complete implementations** - "Find removed auth code" must return full working code, not fragments
3. **Git stores blobs efficiently** - Git handles compression/deduplication internally
4. **Better deduplication** - Same file content = same blob hash = reuse existing vectors

**Example Query:** "function that handles JWT authentication"
- Full blob approach: Finds complete `AuthManager` class with all context ✅
- Diff approach: Only finds "+ jwt.decode()" line without context ❌

### Component Architecture and Reuse Strategy

**Pipeline Reuse (85% of workspace indexing code):**

```
Workspace Indexing (Current HEAD):
  Disk Files → FileIdentifier → FixedSizeChunker.chunk_file()
    → VectorCalculationManager → FilesystemVectorStore

Git History Indexing (This Story):
  Git Blobs → GitBlobReader → FixedSizeChunker.chunk_text()
    → VectorCalculationManager → FilesystemVectorStore
           ↑                         ↑
        SAME COMPONENTS REUSED (85%)
```

**✅ Reused Components (No Changes):**
- `VectorCalculationManager` - Parallel embedding generation (VoyageAI API)
- `FilesystemVectorStore` - JSON vector storage (already has blob_hash field)
- Threading patterns (`ThreadPoolExecutor`, `CleanSlotTracker`)
- Progress callback mechanism

**⚙️ Modified Components (Minor Changes):**
- `FixedSizeChunker` - Add `chunk_text(text, source)` method for pre-loaded text

**🆕 New Git-Specific Components:**

1. **TemporalBlobScanner** - Discovers blobs in git history
   ```python
   def get_blobs_for_commit(commit_hash: str) -> List[BlobInfo]:
       """Uses: git ls-tree -r <commit_hash>"""
       # Returns: [(file_path, blob_hash, size), ...]
   ```

2. **GitBlobReader** - Reads blob content from git object store
   ```python
   def read_blob_content(blob_hash: str) -> str:
       """Uses: git cat-file blob <blob_hash>"""
       # Returns: Full file content as string
   ```

3. **HistoricalBlobProcessor** - Parallel blob processing (analogous to HighThroughputProcessor)
   ```python
   def process_blobs_high_throughput(blobs: List[BlobInfo]) -> Stats:
       """
       Orchestrates: blob → read → chunk → vector → store
       Reuses: VectorCalculationManager + FilesystemVectorStore
       """
   ```

### Deduplication Flow (92% Vector Reuse)

**Key Insight:** Most blobs across history already have vectors from HEAD indexing.

```python
# For each commit (e.g., 150 blobs per commit)
for commit in commits:
    # Step 1: Get all blobs in commit
    all_blobs = scanner.get_blobs_for_commit(commit.hash)  # 150 blobs

    # Step 2: Check blob registry (SQLite lookup, microseconds)
    new_blobs = []
    for blob in all_blobs:
        if not blob_registry.has_blob(blob.blob_hash):  # Fast SQLite query
            new_blobs.append(blob)  # Only ~12 blobs are new (92% dedup)

    # Step 3: Process ONLY new blobs (skip 138 existing)
    if new_blobs:
        # Use HistoricalBlobProcessor (reuses VectorCalculationManager)
        blob_processor.process_blobs_high_throughput(
            new_blobs,  # Only 12 blobs instead of 150
            vector_thread_count=8
        )

    # Step 4: Link commit → all blobs (new + reused) in SQLite
    store_commit_metadata(commit, all_blobs)
```

**Result:** 150 blobs → 12 embeddings → 92% savings

### Performance Expectations (42K files, 10GB repo)

**First Run:**
- Estimated 150,000 unique blobs across history
- 92% deduplication (most files unchanged across commits)
- Only ~12,000 new blobs need embedding
- 8 parallel threads with VoyageAI batch processing
- **Time: 4-7 minutes** (similar to workspace indexing)

**Incremental (New Commits):**
- Only process blobs from new commits
- High deduplication (most files unchanged)
- **Time: <1 minute**

**Bottlenecks:**
1. Git blob extraction (`git cat-file`) - slower than disk reads but parallelized
2. VoyageAI API calls - same as workspace (token-aware batching, 120K limit)
3. SQLite blob registry lookups - microseconds (indexed)

---

## Technical Implementation

### Entry Point (CLI)
```python
# In cli.py index command
@click.option("--index-commits", is_flag=True,
              help="Index git commit history for temporal search (current branch only)")
@click.option("--all-branches", is_flag=True,
              help="Index all branches (requires --index-commits, may increase storage significantly)")
@click.option("--max-commits", type=int,
              help="Maximum number of commits to index per branch (default: all)")
@click.option("--since-date",
              help="Index commits since date (YYYY-MM-DD)")
def index(..., index_commits, all_branches, max_commits, since_date):
    if index_commits:
        # Lazy import for performance
        from src.code_indexer.services.temporal_indexer import TemporalIndexer

        temporal_indexer = TemporalIndexer(config_manager, vector_store)

        # Cost estimation and warning for all-branches
        if all_branches:
            cost_estimate = temporal_indexer.estimate_all_branches_cost()
            console.print(Panel(
                f"⚠️  [yellow]Indexing all branches will:[/yellow]\n"
                f"  • Process {cost_estimate.additional_commits:,} additional commits\n"
                f"  • Create {cost_estimate.additional_blobs:,} new embeddings\n"
                f"  • Use {cost_estimate.storage_mb:.1f} MB additional storage\n"
                f"  • Cost ~${cost_estimate.api_cost:.2f} in VoyageAI API calls",
                title="Cost Warning",
                border_style="yellow"
            ))

            if cost_estimate.total_branches > 50:
                if not click.confirm("Continue with all-branches indexing?", default=False):
                    console.print("[yellow]Cancelled. Using single-branch mode.[/yellow]")
                    all_branches = False

        result = temporal_indexer.index_commits(
            all_branches=all_branches,
            max_commits=max_commits,
            since_date=since_date
        )
```

### Core Implementation (TemporalIndexer Orchestration)

**CRITICAL:** TemporalIndexer orchestrates the flow but delegates actual blob processing to HistoricalBlobProcessor.

```python
class TemporalIndexer:
    def __init__(self, config_manager, vector_store):
        self.config = config_manager.get_config()
        self.vector_store = vector_store
        self.db_path = Path(".code-indexer/index/temporal/commits.db")

        # Initialize git-specific components
        self.blob_scanner = TemporalBlobScanner(self.config.codebase_dir)
        self.blob_reader = GitBlobReader(self.config.codebase_dir)

        # Initialize blob registry
        self.blob_registry = BlobRegistry(
            Path(".code-indexer/index/temporal/blob_registry.db")
        )

        # Initialize blob processor (reuses VectorCalculationManager)
        from .embedding_factory import EmbeddingProviderFactory
        embedding_provider = EmbeddingProviderFactory.create(config=self.config)

        self.blob_processor = HistoricalBlobProcessor(
            config=self.config,
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            blob_registry=self.blob_registry
        )

    def index_commits(self, all_branches: bool = False,
                      max_commits: Optional[int] = None,
                      since_date: Optional[str] = None,
                      progress_callback: Optional[Callable] = None) -> IndexingResult:
        """Index git history with blob deduplication and branch tracking.

        This method orchestrates but DELEGATES blob processing to
        HistoricalBlobProcessor (which reuses VectorCalculationManager).
        """

        # Step 1: Build blob registry from existing vectors (SQLite)
        self.blob_registry.build_from_vector_store(self.vector_store)

        # Step 2: Get commit history from git (with branch info)
        commits = self._get_commit_history(all_branches, max_commits, since_date)
        current_branch = self._get_current_branch()

        # Step 3: Process each commit
        total_blobs_processed = 0
        total_vectors_created = 0

        for i, commit in enumerate(commits):
            # 3a. Discover all blobs in this commit (git ls-tree)
            all_blobs = self.blob_scanner.get_blobs_for_commit(commit.hash)

            # 3b. Filter to ONLY new blobs (deduplication check)
            new_blobs = []
            for blob_info in all_blobs:
                if not self.blob_registry.has_blob(blob_info.blob_hash):
                    new_blobs.append(blob_info)

            # 3c. Process new blobs using HistoricalBlobProcessor
            #     (This reuses VectorCalculationManager + FilesystemVectorStore)
            if new_blobs:
                stats = self.blob_processor.process_blobs_high_throughput(
                    new_blobs,
                    vector_thread_count=8,
                    progress_callback=progress_callback
                )
                total_vectors_created += stats.vectors_created

            total_blobs_processed += len(all_blobs)

            # 3d. Store commit metadata in SQLite (links commit → blobs)
            self._store_commit_tree(commit, all_blobs)

            # Progress with branch info
            if progress_callback:
                branch_info = f" [{current_branch}]" if not all_branches else ""
                progress_callback(
                    i + 1,
                    len(commits),
                    Path(f"commit {commit.hash[:8]}"),
                    info=f"{i+1}/{len(commits)} commits{branch_info}"
                )

        # Step 4: Store commit data and branch metadata in SQLite
        self._store_branch_metadata(commits, all_branches, current_branch)

        # Step 5: Save temporal metadata with branch info
        branch_stats = self._calculate_branch_statistics(commits, all_branches)
        self._save_temporal_metadata(
            last_commit=commits[-1].hash,
            total_commits=len(commits),
            total_blobs=total_blobs_processed,
            new_blobs=total_vectors_created // 3,  # Approx (3 chunks/file avg)
            branch_stats=branch_stats,
            indexing_mode='all-branches' if all_branches else 'single-branch'
        )

        return IndexingResult(
            total_commits=len(commits),
            unique_blobs=total_blobs_processed,
            new_blobs_indexed=total_vectors_created // 3,
            deduplication_ratio=1 - (total_vectors_created / (total_blobs_processed * 3)),
            branches_indexed=branch_stats.branches,
            commits_per_branch=branch_stats.per_branch_counts
        )
```

### New Component: TemporalBlobScanner

```python
@dataclass
class BlobInfo:
    """Information about a blob in git history."""
    blob_hash: str      # Git's blob hash (for deduplication)
    file_path: str      # Relative path in repo
    commit_hash: str    # Which commit this blob appears in
    size: int           # Blob size in bytes

class TemporalBlobScanner:
    """Discovers blobs in git history."""

    def __init__(self, codebase_dir: Path):
        self.codebase_dir = codebase_dir

    def get_blobs_for_commit(self, commit_hash: str) -> List[BlobInfo]:
        """Get all blobs in a commit's tree.

        Uses: git ls-tree -r -l <commit_hash>
        """
        cmd = ["git", "ls-tree", "-r", "-l", commit_hash]
        result = subprocess.run(
            cmd,
            cwd=self.codebase_dir,
            capture_output=True,
            text=True,
            check=True
        )

        blobs = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            # Format: <mode> <type> <hash> <size>\t<path>
            # Example: 100644 blob abc123def456 1234\tsrc/module.py
            parts = line.split()
            if len(parts) >= 4 and parts[1] == "blob":
                blob_hash = parts[2]
                size = int(parts[3])
                file_path = line.split("\t", 1)[1]

                blobs.append(BlobInfo(
                    blob_hash=blob_hash,
                    file_path=file_path,
                    commit_hash=commit_hash,
                    size=size
                ))

        return blobs
```

### New Component: GitBlobReader

```python
class GitBlobReader:
    """Reads blob content from git object store."""

    def __init__(self, codebase_dir: Path):
        self.codebase_dir = codebase_dir

    def read_blob_content(self, blob_hash: str) -> str:
        """Extract blob content as text.

        Uses: git cat-file blob <blob_hash>
        """
        cmd = ["git", "cat-file", "blob", blob_hash]
        result = subprocess.run(
            cmd,
            cwd=self.codebase_dir,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise ValueError(f"Failed to read blob {blob_hash}: {result.stderr}")

        return result.stdout
```

### New Component: HistoricalBlobProcessor

**CRITICAL:** This component reuses VectorCalculationManager and FilesystemVectorStore.

```python
class HistoricalBlobProcessor:
    """Processes historical git blobs with parallel vectorization.

    Similar to HighThroughputProcessor but for git blobs instead of disk files.
    Reuses: VectorCalculationManager + FilesystemVectorStore
    """

    def __init__(self, config, embedding_provider, vector_store, blob_registry):
        self.config = config
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.blob_registry = blob_registry
        self.blob_reader = GitBlobReader(config.codebase_dir)
        self.chunker = FixedSizeChunker()  # Will use chunk_text() method

    def process_blobs_high_throughput(
        self,
        blobs: List[BlobInfo],
        vector_thread_count: int,
        progress_callback: Optional[Callable] = None
    ) -> BlobProcessingStats:
        """Process blobs with parallel vectorization.

        Uses SAME architecture as HighThroughputProcessor:
        - VectorCalculationManager for parallel embeddings
        - FilesystemVectorStore for vector storage
        - ThreadPoolExecutor for parallel blob processing
        """
        stats = BlobProcessingStats()

        # ✅ REUSE VectorCalculationManager (unchanged)
        with VectorCalculationManager(
            self.embedding_provider, vector_thread_count
        ) as vector_manager:

            # Parallel blob processing
            with ThreadPoolExecutor(max_workers=vector_thread_count) as executor:
                futures = []
                for blob_info in blobs:
                    future = executor.submit(
                        self._process_single_blob,
                        blob_info,
                        vector_manager
                    )
                    futures.append((future, blob_info))

                # Collect results as they complete
                for i, (future, blob_info) in enumerate(futures):
                    try:
                        result = future.result()
                        stats.blobs_processed += 1
                        stats.vectors_created += result.chunks_processed

                        # Progress callback
                        if progress_callback:
                            progress_callback(
                                i + 1,
                                len(blobs),
                                Path(blob_info.file_path),
                                info=f"{i+1}/{len(blobs)} blobs"
                            )
                    except Exception as e:
                        logger.error(f"Failed to process blob {blob_info.blob_hash}: {e}")
                        stats.failed_blobs += 1

        return stats

    def _process_single_blob(
        self,
        blob_info: BlobInfo,
        vector_manager: VectorCalculationManager
    ) -> BlobProcessingResult:
        """Process single blob: read → chunk → vector → store → register."""

        # Step 1: Read blob content from git
        content = self.blob_reader.read_blob_content(blob_info.blob_hash)

        # Step 2: Chunk the content (REUSE FixedSizeChunker with new method)
        chunks = self.chunker.chunk_text(content, blob_info.file_path)

        if not chunks:
            return BlobProcessingResult(success=True, chunks_processed=0)

        # Step 3: Submit chunks for vectorization (REUSE VectorCalculationManager)
        chunk_texts = [chunk["text"] for chunk in chunks]
        vector_futures = vector_manager.submit_chunks_batch(chunk_texts)

        # Step 4: Wait for all vectors
        vectors = [f.result() for f in vector_futures]

        # Step 5: Create points and write to store
        points = []
        point_ids = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            # Create metadata (blob_hash is key for deduplication)
            metadata = {
                'blob_hash': blob_info.blob_hash,
                'file_path': blob_info.file_path,
                'commit_hash': blob_info.commit_hash,
                'chunk_index': i,
                'chunk_text': chunk["text"][:500],  # Preview
                'project_id': self.config.project_id,
            }

            # Generate point ID (using blob_hash for deduplication)
            point_id = f"{self.config.project_id}:{blob_info.blob_hash}:{i}"
            point_ids.append(point_id)

            point = {
                'id': point_id,
                'vector': vector,
                'payload': metadata
            }
            points.append(point)

        # ✅ REUSE FilesystemVectorStore (unchanged)
        self.vector_store.upsert_points(points)

        # Step 6: Register blob → point_ids in registry (SQLite)
        for point_id in point_ids:
            self.blob_registry.register(blob_info.blob_hash, point_id)

        return BlobProcessingResult(
            success=True,
            blob_info=blob_info,
            chunks_processed=len(chunks)
        )
```

### Blob Registry Building (SQLite)
```python
def _build_blob_registry(self) -> str:
    """Scan FilesystemVectorStore and build SQLite blob registry.

    Returns path to blob_registry.db file.

    For large repos (40K+ files, 10GB+ with history), SQLite is required
    for performance. JSON would be 100MB+ and too slow for lookups.
    """
    import sqlite3

    registry_path = Path(".code-indexer/index/temporal/blob_registry.db")
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    # Create SQLite database
    conn = sqlite3.connect(registry_path)

    # Create table with index for fast lookups
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blob_registry (
            blob_hash TEXT NOT NULL,
            point_id TEXT NOT NULL,
            PRIMARY KEY (blob_hash, point_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_blob_hash ON blob_registry(blob_hash)")

    # Performance tuning for bulk inserts
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=10000")

    # Scan all vector JSON files in FilesystemVectorStore
    collection_path = self.vector_store.collection_path
    batch = []
    batch_size = 1000

    for json_path in collection_path.glob("**/*.json"):
        with open(json_path) as f:
            point_data = json.load(f)
            blob_hash = point_data.get("payload", {}).get("blob_hash")
            if blob_hash:
                batch.append((blob_hash, point_data["id"]))

                # Batch insert for performance
                if len(batch) >= batch_size:
                    conn.executemany(
                        "INSERT OR IGNORE INTO blob_registry (blob_hash, point_id) VALUES (?, ?)",
                        batch
                    )
                    conn.commit()
                    batch = []

    # Insert remaining
    if batch:
        conn.executemany(
            "INSERT OR IGNORE INTO blob_registry (blob_hash, point_id) VALUES (?, ?)",
            batch
        )
        conn.commit()

    conn.close()
    return str(registry_path)

def _lookup_blob_vectors(self, blob_hash: str) -> List[str]:
    """Look up existing vector point IDs for a blob hash.

    Fast indexed lookup in SQLite (microseconds).
    """
    import sqlite3

    registry_path = Path(".code-indexer/index/temporal/blob_registry.db")
    if not registry_path.exists():
        return []

    conn = sqlite3.connect(registry_path)
    results = conn.execute(
        "SELECT point_id FROM blob_registry WHERE blob_hash = ?",
        (blob_hash,)
    ).fetchall()
    conn.close()

    return [r[0] for r in results]
```

### SQLite Storage
```python
def _initialize_database(self):
    """Create SQLite tables with proper indexes"""
    import sqlite3  # Lazy import

    conn = sqlite3.connect(self.db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commits (
            hash TEXT PRIMARY KEY,
            date INTEGER NOT NULL,
            author_name TEXT,
            author_email TEXT,
            message TEXT,
            parent_hashes TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS trees (
            commit_hash TEXT NOT NULL,
            file_path TEXT NOT NULL,
            blob_hash TEXT NOT NULL,
            PRIMARY KEY (commit_hash, file_path),
            FOREIGN KEY (commit_hash) REFERENCES commits(hash)
        )
    """)

    # NEW: Branch metadata table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commit_branches (
            commit_hash TEXT NOT NULL,
            branch_name TEXT NOT NULL,
            is_head INTEGER DEFAULT 0,
            indexed_at INTEGER NOT NULL,
            PRIMARY KEY (commit_hash, branch_name),
            FOREIGN KEY (commit_hash) REFERENCES commits(hash)
        )
    """)

    # Performance indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trees_blob_commit ON trees(blob_hash, commit_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_commits_date_hash ON commits(date, hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trees_commit ON trees(commit_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_commit_branches_hash ON commit_branches(commit_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_commit_branches_name ON commit_branches(branch_name)")

    # Performance tuning
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA cache_size=8192")

    conn.commit()
    return conn

def _store_branch_metadata(self, commits: List[CommitInfo],
                            all_branches: bool,
                            current_branch: str):
    """Store branch metadata for each commit"""
    import sqlite3
    import time

    conn = sqlite3.connect(self.db_path)
    timestamp = int(time.time())

    for commit in commits:
        if all_branches:
            # Get all branches containing this commit
            branches = self._get_branches_for_commit(commit.hash)
        else:
            # Single branch mode: only record current branch
            branches = [current_branch]

        # Check if this commit is HEAD of current branch
        is_head = (commit.hash == self._get_branch_head(current_branch))

        # Insert branch records
        for branch in branches:
            conn.execute("""
                INSERT OR IGNORE INTO commit_branches
                (commit_hash, branch_name, is_head, indexed_at)
                VALUES (?, ?, ?, ?)
            """, (commit.hash, branch, 1 if is_head and branch == current_branch else 0, timestamp))

    conn.commit()
    conn.close()
```

### Git Integration
```python
def _get_commit_history(self, all_branches: bool,
                       max_commits: Optional[int],
                       since_date: Optional[str]) -> List[CommitInfo]:
    """Get commit history from git with branch awareness"""

    # Build git log command
    cmd = ["git", "log", "--format=%H|%at|%an|%ae|%P", "--reverse"]

    # Add --all flag only if indexing all branches
    if all_branches:
        cmd.append("--all")

    if since_date:
        cmd.extend(["--since", since_date])

    if max_commits:
        cmd.extend(["-n", str(max_commits)])

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    commits = []
    for line in result.stdout.strip().split("\n"):
        if line:
            parts = line.split("|")
            commits.append(CommitInfo(
                hash=parts[0],
                timestamp=int(parts[1]),
                author_name=parts[2],
                author_email=parts[3],
                parent_hashes=parts[4]
            ))

    return commits

def _get_current_branch(self) -> str:
    """Get name of current branch"""
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip() or "HEAD"

def _get_branches_for_commit(self, commit_hash: str) -> List[str]:
    """Get all branches containing a specific commit"""
    result = subprocess.run(
        ["git", "branch", "--contains", commit_hash, "--format=%(refname:short)"],
        capture_output=True,
        text=True
    )
    branches = [b.strip() for b in result.stdout.split("\n") if b.strip()]
    return branches if branches else ["unknown"]

def _get_branch_head(self, branch_name: str) -> str:
    """Get HEAD commit hash of a branch"""
    result = subprocess.run(
        ["git", "rev-parse", branch_name],
        capture_output=True,
        text=True
    )
    return result.stdout.strip()

def _get_commit_tree(self, commit_hash: str) -> List[TreeEntry]:
    """Get file tree for a commit"""
    cmd = ["git", "ls-tree", "-r", commit_hash]
    result = subprocess.run(cmd, capture_output=True, text=True)

    entries = []
    for line in result.stdout.strip().split("\n"):
        if line:
            # Format: mode type hash<tab>path
            parts = line.split("\t")
            mode_type_hash = parts[0].split(" ")
            if mode_type_hash[1] == "blob":  # Only care about files
                entries.append(TreeEntry(
                    path=parts[1],
                    blob_hash=mode_type_hash[2]
                ))

    return entries

def estimate_all_branches_cost(self) -> CostEstimate:
    """Estimate cost of indexing all branches"""
    import subprocess

    # Count current branch commits
    current_commits = int(subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        capture_output=True, text=True
    ).stdout.strip())

    # Count all branches commits
    all_commits = int(subprocess.run(
        ["git", "rev-list", "--all", "--count"],
        capture_output=True, text=True
    ).stdout.strip())

    # Count total branches
    total_branches = len(subprocess.run(
        ["git", "branch", "-a"],
        capture_output=True, text=True
    ).stdout.strip().split("\n"))

    additional_commits = all_commits - current_commits

    # Estimate additional blobs (assume 80% of objects are blobs, 10% are new)
    additional_blobs = int(additional_commits * 15 * 0.8 * 0.1)  # 15 files/commit avg

    # Calculate storage
    embedding_size = 1536 * 4  # float32
    storage_mb = (additional_blobs * embedding_size) / (1024 * 1024)

    # Calculate API cost (VoyageAI voyage-code-2)
    tokens_per_blob = 500
    api_cost = (additional_blobs * tokens_per_blob / 1000) * 0.00013

    return CostEstimate(
        total_branches=total_branches,
        additional_commits=additional_commits,
        additional_blobs=additional_blobs,
        storage_mb=storage_mb,
        api_cost=api_cost
    )
```

## Test Scenarios

### Manual Test Plan

#### Test 1: Single Branch Indexing (Default)
1. **Setup:**
   - Use code-indexer repository
   - Ensure clean state: `rm -rf .code-indexer/index/temporal/`
   - Run regular indexing first: `cidx index`

2. **Execute Single-Branch Temporal Indexing:**
   ```bash
   cidx index --index-commits
   # Should show: "Indexing commits: X/Y (%) [development]"
   ```

3. **Verify Database Created:**
   ```bash
   sqlite3 .code-indexer/index/temporal/commits.db ".tables"
   # Should show: commits trees commit_branches

   sqlite3 .code-indexer/index/temporal/commits.db "SELECT COUNT(*) FROM commits"
   # Should show commit count for current branch

   sqlite3 .code-indexer/index/temporal/commits.db "SELECT DISTINCT branch_name FROM commit_branches"
   # Should show only current branch (e.g., "development")
   ```

4. **Verify Blob Registry (SQLite):**
   ```bash
   sqlite3 .code-indexer/index/temporal/blob_registry.db "SELECT COUNT(DISTINCT blob_hash) FROM blob_registry"
   # Should show number of unique blobs

   sqlite3 .code-indexer/index/temporal/blob_registry.db "SELECT COUNT(*) FROM blob_registry"
   # Should show total blob_hash → point_id mappings
   ```

5. **Check Deduplication and Branch Stats:**
   ```bash
   cat .code-indexer/index/temporal/temporal_meta.json | jq '.deduplication_ratio'
   # Should be > 0.92 (92%)

   cat .code-indexer/index/temporal/temporal_meta.json | jq '.indexing_mode'
   # Should show: "single-branch"

   cat .code-indexer/index/temporal/temporal_meta.json | jq '.indexed_branches'
   # Should show: ["development"] or similar
   ```

#### Test 2: All Branches Indexing
1. **Execute All-Branches Indexing:**
   ```bash
   cidx index --index-commits --all-branches
   # Should show cost warning dialog
   # After confirmation, should show: "Indexing commits: X/Y (%)"
   ```

2. **Verify All Branches Tracked:**
   ```bash
   sqlite3 .code-indexer/index/temporal/commits.db \
     "SELECT COUNT(DISTINCT branch_name) FROM commit_branches"
   # Should show number matching total branches in repo

   sqlite3 .code-indexer/index/temporal/commits.db \
     "SELECT branch_name, COUNT(*) FROM commit_branches GROUP BY branch_name LIMIT 10"
   # Should show commit counts per branch
   ```

3. **Verify Metadata:**
   ```bash
   cat .code-indexer/index/temporal/temporal_meta.json | jq '.indexing_mode'
   # Should show: "all-branches"
   ```

#### Test 3: Cost Warning
1. **Test Cost Estimation (on large repo):**
   ```bash
   # On Evolution repo or similar large repo
   cidx index --index-commits --all-branches
   # Should display warning with:
   #   - Number of additional commits
   #   - Storage estimate in MB
   #   - API cost estimate in dollars
   #   - Confirmation prompt (y/N)
   ```

2. **Test Cancellation:**
   - Answer 'N' to confirmation
   - Verify it falls back to single-branch mode

#### Test 4: Limits and Filters
1. **Test with Max Commits:**
   ```bash
   cidx index --index-commits --max-commits 100
   # Should index only 100 commits from current branch
   ```

2. **Test with Date Filter:**
   ```bash
   cidx index --index-commits --since-date 2024-01-01
   # Should index only commits since specified date
   ```

3. **Test Combined Flags:**
   ```bash
   cidx index --index-commits --all-branches --since-date 2024-01-01
   # Should index all branches but only recent commits
   ```

#### Test 5: Daemon Mode (CRITICAL)
1. **Enable Daemon Mode:**
   ```bash
   cidx config --daemon
   cidx start  # Manually start daemon for testing
   ```

2. **Execute Temporal Indexing in Daemon Mode:**
   ```bash
   # Verify daemon is running
   cidx status
   # Should show: "Daemon Running: true"

   # Execute temporal indexing (should delegate to daemon)
   cidx index --index-commits
   # Should show identical progress bar as standalone mode
   # Progress should stream in real-time
   ```

3. **Verify Cache Invalidation:**
   ```bash
   # Query before temporal indexing
   cidx query "test query"  # Warms up cache

   # Run temporal indexing
   cidx index --index-commits

   # Query after temporal indexing
   cidx query "historical code"  # Should include new historical vectors
   # Verify new vectors are searchable (cache was invalidated)
   ```

4. **Test All-Branches in Daemon Mode:**
   ```bash
   cidx index --index-commits --all-branches
   # Should show cost warning
   # Progress should stream from daemon
   # Daemon should remain responsive
   ```

5. **Test Fallback to Standalone:**
   ```bash
   # Stop daemon
   cidx stop

   # Try temporal indexing (should fall back to standalone)
   cidx index --index-commits
   # Should execute in standalone mode without errors
   # Progress bar should display correctly
   ```

6. **Verify UX Parity:**
   - Compare standalone vs daemon mode side-by-side
   - Progress bar format should be identical
   - Timing information should be accurate
   - File processing display should match
   - Final statistics should match

### Automated Tests

#### Unit Tests (Mode-Agnostic)
```python
def test_git_history_indexing_with_deduplication():
    """Test complete temporal indexing with blob deduplication (standalone)"""
    # Setup test repo with history
    with temp_git_repo() as repo_path:
        # Create commits
        create_test_commits(repo_path, count=10)

        # Run regular indexing
        indexer = SmartIndexer(config_manager)
        indexer.index_directory(repo_path)

        # Run temporal indexing
        temporal = TemporalIndexer(config_manager, vector_store)
        result = temporal.index_commits()

        # Verify results
        assert result.total_commits == 10
        assert result.deduplication_ratio > 0.5  # Some files unchanged

        # Check database
        conn = sqlite3.connect(".code-indexer/index/temporal/commits.db")
        commit_count = conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
        assert commit_count == 10

        # Check blob registry (SQLite)
        conn = sqlite3.connect(".code-indexer/index/temporal/blob_registry.db")
        blob_count = conn.execute("SELECT COUNT(DISTINCT blob_hash) FROM blob_registry").fetchone()[0]
        assert blob_count > 0
        conn.close()
```

#### Integration Tests (Daemon Mode)
```python
def test_temporal_indexing_daemon_delegation():
    """Test temporal indexing delegates correctly to daemon"""
    with temp_git_repo() as repo_path:
        # Enable daemon mode
        config_manager = ConfigManager(repo_path)
        config_manager.enable_daemon()

        # Start daemon
        start_daemon_command()
        time.sleep(1)  # Wait for daemon startup

        try:
            # Execute via CLI (should delegate to daemon)
            result = runner.invoke(cli, ['index', '--index-commits'])

            # Verify success
            assert result.exit_code == 0
            assert Path('.code-indexer/index/temporal/commits.db').exists()

            # Verify output contains progress
            assert 'Indexing commits' in result.output or 'commits processed' in result.output
        finally:
            # Cleanup
            stop_daemon_command()

def test_temporal_indexing_daemon_cache_invalidation():
    """Test daemon cache is invalidated after temporal indexing"""
    with temp_git_repo() as repo_path:
        # Setup with daemon
        config_manager = ConfigManager(repo_path)
        config_manager.enable_daemon()
        start_daemon_command()
        time.sleep(1)

        try:
            # Run regular indexing first
            runner.invoke(cli, ['index'])

            # Warm up cache with query
            result1 = runner.invoke(cli, ['query', 'test'])
            assert result1.exit_code == 0

            # Get daemon status (cache should be warm)
            status1 = get_daemon_status()
            assert status1['semantic_cached'] == True

            # Run temporal indexing
            result2 = runner.invoke(cli, ['index', '--index-commits'])
            assert result2.exit_code == 0

            # Verify cache was invalidated
            status2 = get_daemon_status()
            assert status2['semantic_cached'] == False  # Cache cleared

            # Query should work with new historical vectors
            result3 = runner.invoke(cli, ['query', 'historical code'])
            assert result3.exit_code == 0
        finally:
            stop_daemon_command()

def test_temporal_indexing_progress_streaming():
    """Test progress callbacks stream from daemon to client"""
    with temp_git_repo() as repo_path:
        create_test_commits(repo_path, count=50)  # Enough for observable progress

        config_manager = ConfigManager(repo_path)
        config_manager.enable_daemon()
        start_daemon_command()
        time.sleep(1)

        try:
            # Track progress callback invocations
            progress_updates = []

            # Mock progress handler to capture callbacks
            with patch('code_indexer.cli_progress_handler.ClientProgressHandler') as mock_handler:
                mock_callback = Mock()
                mock_callback.side_effect = lambda *args, **kwargs: progress_updates.append((args, kwargs))
                mock_handler.return_value.create_progress_callback.return_value = mock_callback

                # Execute temporal indexing
                result = runner.invoke(cli, ['index', '--index-commits'])
                assert result.exit_code == 0

            # Verify progress updates were received
            assert len(progress_updates) > 0
            # Verify incremental progress (not just start and end)
            assert len(progress_updates) > 5
        finally:
            stop_daemon_command()

def test_temporal_indexing_fallback_to_standalone():
    """Test graceful fallback when daemon unavailable"""
    with temp_git_repo() as repo_path:
        # Enable daemon config but don't start daemon
        config_manager = ConfigManager(repo_path)
        config_manager.enable_daemon()

        # Execute should fall back to standalone
        result = runner.invoke(cli, ['index', '--index-commits'])

        # Verify success (fallback worked)
        assert result.exit_code == 0
        assert Path('.code-indexer/index/temporal/commits.db').exists()
```

## Error Scenarios

1. **No git repository:**
   - Error: "Not a git repository"
   - Action: Display clear error message

2. **Shallow clone:**
   - Warning: "Shallow clone detected. Run 'git fetch --unshallow' for full history"
   - Action: Continue with available commits

3. **Large repository (>100K commits):**
   - Warning: "Repository has 150,000 commits. Consider using --max-commits"
   - Action: Continue but show progress

4. **Disk space issues:**
   - Error: "Insufficient disk space for temporal index"
   - Action: Cleanup partial index, show required space

## Performance Considerations

- **Single-branch mode (default):** Fast indexing, similar to current performance
- **All-branches mode:** Significant increase in processing time but excellent deduplication
- Batch SQLite inserts in transactions of 1000 rows (commits AND branch metadata)
- Use WAL mode for concurrent reads during indexing
- Build blob registry incrementally to avoid memory issues
- Show progress every 100 commits with branch context
- Allow cancellation with Ctrl+C (cleanup partial state)
- Cost estimation runs quickly (uses git commands only, no indexing)

## Dependencies

- Git CLI (version 2.0+)
- sqlite3 Python module (lazy loaded)
- Existing FilesystemVectorStore
- Existing HighThroughputProcessor for embedding
- Existing daemon mode infrastructure (cli_daemon_delegation.py, daemon/service.py)
- RPyC for daemon communication (already installed for daemon mode)

## Notes

**Conversation Requirements:**
- Default to current branch only (cost-effective, 91%+ commit coverage)
- Opt-in for all branches via explicit `--all-branches` flag
- 92%+ storage savings target via blob deduplication
- Must handle 40K+ commit repositories with 1000+ branches
- Progress reporting during long operations with branch context
- Cost transparency: warn users before expensive operations

**Branch Strategy Analysis:**
- Evolution repository analysis (1,135 branches, 89K commits) informed design decisions
- Single branch indexing: 81,733 commits = 91.6% coverage
- All branches indexing: 89,234 commits = 100% coverage but 85.5% storage increase
- Git blob deduplication: 92.4% of blobs shared between branches
- See `.analysis/temporal_indexing_branch_analysis.md` for complete analysis

**Design Decisions:**
1. **Default = Single Branch:** Cost-effective, excellent coverage for most use cases
2. **Explicit Opt-in:** Users must consciously choose `--all-branches` to avoid surprise costs
3. **Branch Metadata Always:** Even single-branch mode tracks which branch (future-proof)
4. **Cost Warnings:** Display storage and API cost estimates before multi-branch indexing
5. **Confirmation Required:** Large repos (>50 branches) require user confirmation for --all-branches
6. **Mode-Agnostic Design:** TemporalIndexer works identically in standalone and daemon modes
7. **Automatic Delegation:** Daemon mode enabled → automatic delegation via CLI (zero config)
8. **Cache Coherence:** Daemon automatically invalidates cache before/after temporal indexing
9. **UX Parity:** Progress bar displays identically in both modes via RPC callback streaming
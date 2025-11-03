"""TemporalIndexer - Orchestrates git history indexing with blob deduplication."""
import json
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Callable

from ...config import ConfigManager
from ...indexing.fixed_size_chunker import FixedSizeChunker
from ...services.vector_calculation_manager import VectorCalculationManager
from ...storage.filesystem_vector_store import FilesystemVectorStore

from .models import CommitInfo, BlobInfo
from .temporal_blob_scanner import TemporalBlobScanner
from .git_blob_reader import GitBlobReader
from .blob_registry import BlobRegistry


@dataclass
class IndexingResult:
    """Result of temporal indexing operation."""
    total_commits: int
    unique_blobs: int
    new_blobs_indexed: int
    deduplication_ratio: float
    branches_indexed: List[str]
    commits_per_branch: dict


class TemporalIndexer:
    """Orchestrates git history indexing with blob deduplication.

    This class coordinates the temporal indexing workflow:
    1. Build blob registry from existing vectors (deduplication)
    2. Get commit history from git
    3. For each commit, discover blobs and process only new ones
    4. Store commit metadata and blob vectors
    """

    def __init__(self, config_manager: ConfigManager, vector_store: FilesystemVectorStore):
        """Initialize temporal indexer.

        Args:
            config_manager: Configuration manager
            vector_store: Filesystem vector store for storage
        """
        self.config_manager = config_manager
        self.config = config_manager.get_config()
        self.vector_store = vector_store

        # Use vector store's project_root as the codebase directory
        self.codebase_dir = vector_store.project_root

        # Initialize temporal directories relative to project root
        self.temporal_dir = self.codebase_dir / ".code-indexer/index/temporal"
        self.temporal_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.blob_scanner = TemporalBlobScanner(self.codebase_dir)
        self.blob_reader = GitBlobReader(self.codebase_dir)
        self.blob_registry = BlobRegistry(self.temporal_dir / "blob_registry.db")
        self.chunker = FixedSizeChunker(self.config)

        # Initialize commits database
        self.commits_db_path = self.temporal_dir / "commits.db"
        self._initialize_commits_database()

    def _initialize_commits_database(self):
        """Create commits database with proper schema."""
        conn = sqlite3.connect(str(self.commits_db_path), timeout=5.0)

        # Create commits table
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

        # Create trees table (commit -> blobs mapping)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trees (
                commit_hash TEXT NOT NULL,
                file_path TEXT NOT NULL,
                blob_hash TEXT NOT NULL,
                PRIMARY KEY (commit_hash, file_path),
                FOREIGN KEY (commit_hash) REFERENCES commits(hash)
            )
        """)

        # Create commit_branches table (commit -> branches mapping)
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

        # Create indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trees_blob_commit ON trees(blob_hash, commit_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_commits_date_hash ON commits(date, hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trees_commit ON trees(commit_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_commit_branches_hash ON commit_branches(commit_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_commit_branches_name ON commit_branches(branch_name)")

        # Performance tuning
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA cache_size=8192")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")

        conn.commit()
        conn.close()

    def index_commits(
        self,
        all_branches: bool = False,
        max_commits: Optional[int] = None,
        since_date: Optional[str] = None,
        progress_callback: Optional[Callable] = None
    ) -> IndexingResult:
        """Index git commit history with blob deduplication.

        Args:
            all_branches: If True, index all branches; if False, current branch only
            max_commits: Maximum number of commits to index per branch
            since_date: Index commits since this date (YYYY-MM-DD)
            progress_callback: Progress callback function

        Returns:
            IndexingResult with statistics
        """
        # Step 1: Get commit history
        commits = self._get_commit_history(all_branches, max_commits, since_date)
        if not commits:
            return IndexingResult(
                total_commits=0,
                unique_blobs=0,
                new_blobs_indexed=0,
                deduplication_ratio=1.0,
                branches_indexed=[],
                commits_per_branch={}
            )

        current_branch = self._get_current_branch()

        # Step 2: Build blob registry from existing vectors
        # (In a real implementation, this would scan vector store)
        # For now, we assume empty registry for new temporal indexing

        # Step 3: Process each commit
        total_blobs_processed = 0
        total_vectors_created = 0

        # Import embedding provider
        from ...services.embedding_factory import EmbeddingProviderFactory
        embedding_provider = EmbeddingProviderFactory.create(config=self.config)

        # Use VectorCalculationManager for parallel processing
        vector_thread_count = self.config.voyage_ai.parallel_requests if hasattr(self.config, 'voyage_ai') else 4

        with VectorCalculationManager(embedding_provider, vector_thread_count) as vector_manager:
            for i, commit in enumerate(commits):
                # 3a. Discover all blobs in this commit
                all_blobs = self.blob_scanner.get_blobs_for_commit(commit.hash)

                # 3b. Filter to only new blobs (deduplication)
                new_blobs = [
                    blob for blob in all_blobs
                    if not self.blob_registry.has_blob(blob.blob_hash)
                ]

                # 3c. Process new blobs
                if new_blobs:
                    for blob_info in new_blobs:
                        try:
                            # Read blob content
                            content = self.blob_reader.read_blob_content(blob_info.blob_hash)

                            # Chunk the content
                            chunks = self.chunker.chunk_text(content, Path(blob_info.file_path))

                            if chunks:
                                # Submit chunks for embedding
                                chunk_texts = [chunk["text"] for chunk in chunks]
                                future = vector_manager.submit_batch_task(chunk_texts, {"blob_hash": blob_info.blob_hash})
                                result = future.result(timeout=300)

                                if not result.error and result.embeddings:
                                    # Create points and store in vector store
                                    points = []
                                    for j, (chunk, embedding) in enumerate(zip(chunks, result.embeddings)):
                                        point_id = f"{self.config.project_id}:{blob_info.blob_hash}:{j}"

                                        payload = {
                                            'blob_hash': blob_info.blob_hash,
                                            'file_path': blob_info.file_path,
                                            'commit_hash': commit.hash,
                                            'chunk_index': j,
                                            'chunk_text': chunk["text"][:500],
                                            'project_id': self.config.project_id,
                                            'line_start': chunk.get('line_start', 0),
                                            'line_end': chunk.get('line_end', 0),
                                        }

                                        point = {
                                            'id': point_id,
                                            'vector': list(embedding),
                                            'payload': payload
                                        }
                                        points.append(point)

                                        # Register in blob registry
                                        self.blob_registry.register(blob_info.blob_hash, point_id)

                                    # Store in vector store
                                    self.vector_store.upsert_points(points)
                                    total_vectors_created += len(points)

                        except Exception as e:
                            # Log error but continue processing
                            print(f"Error processing blob {blob_info.blob_hash}: {e}")

                total_blobs_processed += len(all_blobs)

                # 3d. Store commit metadata
                self._store_commit_tree(commit, all_blobs)

                # 3e. Store branch metadata
                self._store_commit_branch_metadata(commit.hash, all_branches, current_branch)

                # Progress callback
                if progress_callback:
                    branch_info = f" [{current_branch}]" if not all_branches else ""
                    progress_callback(
                        i + 1,
                        len(commits),
                        Path(f"commit {commit.hash[:8]}"),
                        info=f"{i+1}/{len(commits)} commits{branch_info}"
                    )

        # Step 4: Save temporal metadata
        dedup_ratio = 1.0 - (total_vectors_created / (total_blobs_processed * 3)) if total_blobs_processed > 0 else 1.0

        branches_indexed = [current_branch] if not all_branches else self._get_all_indexed_branches()

        self._save_temporal_metadata(
            last_commit=commits[-1].hash,
            total_commits=len(commits),
            total_blobs=total_blobs_processed,
            new_blobs=total_vectors_created // 3,  # Approx
            branch_stats={"branches": branches_indexed, "per_branch_counts": {}},
            indexing_mode='all-branches' if all_branches else 'single-branch'
        )

        return IndexingResult(
            total_commits=len(commits),
            unique_blobs=total_blobs_processed,
            new_blobs_indexed=total_vectors_created // 3,
            deduplication_ratio=dedup_ratio,
            branches_indexed=branches_indexed,
            commits_per_branch={}
        )

    def _get_commit_history(
        self,
        all_branches: bool,
        max_commits: Optional[int],
        since_date: Optional[str]
    ) -> List[CommitInfo]:
        """Get commit history from git."""
        cmd = ["git", "log", "--format=%H|%at|%an|%ae|%s|%P", "--reverse"]

        if all_branches:
            cmd.append("--all")

        if since_date:
            cmd.extend(["--since", since_date])

        if max_commits:
            cmd.extend(["-n", str(max_commits)])

        result = subprocess.run(
            cmd,
            cwd=self.codebase_dir,
            capture_output=True,
            text=True,
            check=True
        )

        commits = []
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split("|")
                if len(parts) >= 6:
                    commits.append(CommitInfo(
                        hash=parts[0],
                        timestamp=int(parts[1]),
                        author_name=parts[2],
                        author_email=parts[3],
                        message=parts[4],
                        parent_hashes=parts[5]
                    ))

        return commits

    def _get_current_branch(self) -> str:
        """Get current branch name."""
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.codebase_dir,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip() or "HEAD"

    def _get_all_indexed_branches(self) -> List[str]:
        """Get all indexed branches from database."""
        conn = sqlite3.connect(str(self.commits_db_path))
        cursor = conn.execute("SELECT DISTINCT branch_name FROM commit_branches")
        branches = [row[0] for row in cursor.fetchall()]
        conn.close()
        return branches

    def _store_commit_tree(self, commit: CommitInfo, blobs: List[BlobInfo]):
        """Store commit and its tree in database."""
        conn = sqlite3.connect(str(self.commits_db_path))

        # Insert commit
        conn.execute("""
            INSERT OR REPLACE INTO commits
            (hash, date, author_name, author_email, message, parent_hashes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            commit.hash,
            commit.timestamp,
            commit.author_name,
            commit.author_email,
            commit.message,
            commit.parent_hashes
        ))

        # Insert tree entries
        for blob in blobs:
            conn.execute("""
                INSERT OR REPLACE INTO trees
                (commit_hash, file_path, blob_hash)
                VALUES (?, ?, ?)
            """, (commit.hash, blob.file_path, blob.blob_hash))

        conn.commit()
        conn.close()

    def _store_commit_branch_metadata(
        self,
        commit_hash: str,
        all_branches_mode: bool,
        current_branch: str
    ):
        """Store branch metadata for commit."""
        timestamp = int(time.time())

        # Determine branches
        if all_branches_mode:
            result = subprocess.run(
                ["git", "branch", "--contains", commit_hash, "--format=%(refname:short)"],
                cwd=self.codebase_dir,
                capture_output=True,
                text=True,
                check=True
            )
            branches = [b.strip() for b in result.stdout.split('\n') if b.strip()]
        else:
            branches = [current_branch]

        # Check if HEAD
        head_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.codebase_dir,
            capture_output=True,
            text=True,
            check=True
        ).stdout.strip()
        is_head = (commit_hash == head_hash)

        # Store in database
        conn = sqlite3.connect(str(self.commits_db_path))
        for branch in branches:
            conn.execute("""
                INSERT OR REPLACE INTO commit_branches
                (commit_hash, branch_name, is_head, indexed_at)
                VALUES (?, ?, ?, ?)
            """, (
                commit_hash,
                branch,
                1 if is_head and branch == current_branch else 0,
                timestamp
            ))
        conn.commit()
        conn.close()

    def _save_temporal_metadata(
        self,
        last_commit: str,
        total_commits: int,
        total_blobs: int,
        new_blobs: int,
        branch_stats: dict,
        indexing_mode: str
    ):
        """Save temporal indexing metadata to JSON."""
        metadata = {
            "last_commit": last_commit,
            "total_commits": total_commits,
            "total_blobs": total_blobs,
            "new_blobs_indexed": new_blobs,
            "deduplication_ratio": 1.0 - (new_blobs / total_blobs) if total_blobs > 0 else 1.0,
            "indexed_branches": branch_stats["branches"],
            "indexing_mode": indexing_mode,
            "indexed_at": datetime.now().isoformat()
        }

        metadata_path = self.temporal_dir / "temporal_meta.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

    def close(self):
        """Clean up resources."""
        if self.blob_registry:
            self.blob_registry.close()

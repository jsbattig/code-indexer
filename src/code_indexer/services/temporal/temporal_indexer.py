"""TemporalIndexer - Index git history with commit message search.

BREAKING CHANGE (Story 2.1 Reimplementation): Payload structure changed.
Users MUST re-index with: cidx index --index-commits --force
Changes: Added 'type' field, removed 'chunk_text' storage, added commit message indexing.
"""

import json
import logging
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty
from typing import List, Optional, Callable

from ...config import ConfigManager
from ...indexing.fixed_size_chunker import FixedSizeChunker
from ...services.vector_calculation_manager import VectorCalculationManager
from ...services.file_identifier import FileIdentifier
from ...storage.filesystem_vector_store import FilesystemVectorStore

from .models import CommitInfo
from .temporal_diff_scanner import TemporalDiffScanner
from .temporal_progressive_metadata import TemporalProgressiveMetadata

logger = logging.getLogger(__name__)


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

    # Temporal collection name - must match TemporalSearchService
    TEMPORAL_COLLECTION_NAME = "code-indexer-temporal"

    def __init__(
        self, config_manager: ConfigManager, vector_store: FilesystemVectorStore
    ):
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

        # Initialize FileIdentifier for project_id lookup
        self.file_identifier = FileIdentifier(self.codebase_dir, self.config)

        # Initialize temporal directories relative to project root
        self.temporal_dir = self.codebase_dir / ".code-indexer/index/temporal"
        self.temporal_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.diff_scanner = TemporalDiffScanner(self.codebase_dir)
        self.chunker = FixedSizeChunker(self.config)

        # Initialize blob registry for deduplication
        self.indexed_blobs: set[str] = set()

        # Initialize progressive metadata tracker for resume capability
        self.progressive_metadata = TemporalProgressiveMetadata(self.temporal_dir)

        # Ensure temporal vector collection exists
        self._ensure_temporal_collection()

    def load_completed_commits(self):
        """Load completed commits from progressive metadata."""
        # Initialize progressive metadata if not already done
        if not hasattr(self, "progressive_metadata"):
            self.progressive_metadata = TemporalProgressiveMetadata(self.temporal_dir)
        return self.progressive_metadata.load_completed()

    def _ensure_temporal_collection(self):
        """Ensure temporal vector collection exists.

        Creates the temporal collection if it doesn't exist. Dimensions vary by model.
        """
        from ...services.embedding_factory import EmbeddingProviderFactory

        provider_info = EmbeddingProviderFactory.get_provider_model_info(self.config)
        vector_size = provider_info.get(
            "dimensions", 1024
        )  # Default to voyage-code-3 dims

        # Check if collection exists, create if not
        if not self.vector_store.collection_exists(self.TEMPORAL_COLLECTION_NAME):
            logger.info(
                f"Creating temporal collection '{self.TEMPORAL_COLLECTION_NAME}' with dimension={vector_size}"
            )
            self.vector_store.create_collection(
                self.TEMPORAL_COLLECTION_NAME, vector_size
            )

    def index_commits(
        self,
        all_branches: bool = False,
        max_commits: Optional[int] = None,
        since_date: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
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
                commits_per_branch={},
            )

        # Step 1.5: Filter out already completed commits (Bug #8 fix)
        completed_commits = self.load_completed_commits()
        if completed_commits:
            original_count = len(commits)
            commits = [c for c in commits if c.hash not in completed_commits]
            logger.info(
                f"Filtered {original_count - len(commits)} already completed commits, {len(commits)} remaining"
            )

        # Check if all commits were filtered out (Bug #9 fix - list index out of range)
        if not commits:
            return IndexingResult(
                total_commits=0,
                unique_blobs=0,
                new_blobs_indexed=0,
                deduplication_ratio=1.0,
                branches_indexed=[],
                commits_per_branch={},
            )

        # Initialize incremental HNSW tracking for the temporal collection
        # This enables change tracking for efficient HNSW index updates
        self.vector_store.begin_indexing(self.TEMPORAL_COLLECTION_NAME)

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
        vector_thread_count = (
            self.config.voyage_ai.parallel_requests
            if hasattr(self.config, "voyage_ai")
            else 4
        )

        with VectorCalculationManager(
            embedding_provider, vector_thread_count
        ) as vector_manager:
            # Use parallel processing instead of sequential loop
            total_blobs_processed, total_vectors_created = (
                self._process_commits_parallel(
                    commits, embedding_provider, vector_manager, progress_callback
                )
            )

        # Step 4: Save temporal metadata
        dedup_ratio = (
            1.0 - (total_vectors_created / (total_blobs_processed * 3))
            if total_blobs_processed > 0
            else 1.0
        )

        # TODO: Get branches from git instead of database
        branches_indexed = [current_branch]  # Temporary fix - no SQLite

        self._save_temporal_metadata(
            last_commit=commits[-1].hash,
            total_commits=len(commits),
            total_blobs=total_blobs_processed,
            new_blobs=total_vectors_created // 3,  # Approx
            branch_stats={"branches": branches_indexed, "per_branch_counts": {}},
            indexing_mode="all-branches" if all_branches else "single-branch",
        )

        return IndexingResult(
            total_commits=len(commits),
            unique_blobs=total_blobs_processed,
            new_blobs_indexed=total_vectors_created // 3,
            deduplication_ratio=dedup_ratio,
            branches_indexed=branches_indexed,
            commits_per_branch={},
        )

    def _load_last_indexed_commit(self) -> Optional[str]:
        """Load last indexed commit from temporal_meta.json.

        Returns:
            Last indexed commit hash if available, None otherwise.
        """
        metadata_path = self.temporal_dir / "temporal_meta.json"
        if not metadata_path.exists():
            return None

        try:
            with open(metadata_path) as f:
                metadata = json.load(f)
            last_commit = metadata.get("last_commit")
            return last_commit if isinstance(last_commit, str) else None
        except (json.JSONDecodeError, IOError):
            logger.warning(f"Failed to load temporal metadata from {metadata_path}")
            return None

    def _get_commit_history(
        self, all_branches: bool, max_commits: Optional[int], since_date: Optional[str]
    ) -> List[CommitInfo]:
        """Get commit history from git."""
        # Load last indexed commit for incremental indexing
        last_indexed_commit = self._load_last_indexed_commit()

        cmd = ["git", "log", "--format=%H|%at|%an|%ae|%s|%P", "--reverse"]

        # If we have a last indexed commit, only get commits after it
        if last_indexed_commit:
            # Use commit range to get only new commits
            cmd.insert(2, f"{last_indexed_commit}..HEAD")
            logger.info(
                f"Incremental indexing: Getting commits after {last_indexed_commit[:8]}"
            )

        if all_branches:
            cmd.append("--all")

        if since_date:
            cmd.extend(["--since", since_date])

        if max_commits:
            cmd.extend(["-n", str(max_commits)])

        result = subprocess.run(
            cmd, cwd=self.codebase_dir, capture_output=True, text=True, check=True
        )

        commits = []
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split("|")
                if len(parts) >= 6:
                    commits.append(
                        CommitInfo(
                            hash=parts[0],
                            timestamp=int(parts[1]),
                            author_name=parts[2],
                            author_email=parts[3],
                            message=parts[4],
                            parent_hashes=parts[5],
                        )
                    )

        return commits

    def _get_current_branch(self) -> str:
        """Get current branch name."""
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.codebase_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or "HEAD"

    def _process_commits_parallel(
        self, commits, embedding_provider, vector_manager, progress_callback=None
    ):
        """Process commits in parallel using queue-based architecture."""
        import traceback  # For comprehensive error logging with stack traces

        # Import CleanSlotTracker and related classes
        from ..clean_slot_tracker import CleanSlotTracker, FileStatus, FileData

        # Load existing point IDs to avoid duplicate processing
        existing_ids = self.vector_store.load_id_index(self.TEMPORAL_COLLECTION_NAME)
        logger.info(
            f"Loaded {len(existing_ids)} existing temporal points for deduplication"
        )

        # Get thread count from config
        thread_count = (
            getattr(self.config.voyage_ai, "parallel_requests", 8)
            if hasattr(self.config, "voyage_ai")
            else 8
        )

        # Create slot tracker with max_slots = thread_count (not thread_count + 2)
        commit_slot_tracker = CleanSlotTracker(max_slots=thread_count)

        # Initialize with correct pattern - show actual total, not 0
        if progress_callback:
            try:
                progress_callback(
                    0,
                    len(commits),  # Actual total for progress bar
                    Path(""),
                    info=f"0/{len(commits)} commits (0%) | 0.0 commits/s | {thread_count} threads | 📝 ???????? - initializing",
                    concurrent_files=commit_slot_tracker.get_concurrent_files_data(),
                    slot_tracker=commit_slot_tracker,
                )
            except TypeError:
                # Fallback for old signature without slot_tracker
                progress_callback(
                    0,
                    len(commits),  # Actual total for progress bar
                    Path(""),
                    info=f"0/{len(commits)} commits (0%) | 0.0 commits/s | {thread_count} threads | 📝 ???????? - initializing",
                )

        # Track progress with thread-safe shared state
        completed_count = [0]  # Mutable list for thread-safe updates
        last_completed_commit = [None]  # Track last completed commit hash
        last_completed_file = [None]  # Track last completed file
        progress_lock = threading.Lock()
        start_time = time.time()

        # Create queue and add commits
        commit_queue = Queue()
        for commit in commits:
            commit_queue.put(commit)

        def worker():
            """Worker function to process commits from queue."""
            while True:
                try:
                    commit = commit_queue.get_nowait()
                except Empty:
                    break

                # Initialize slot_id outside the loop
                slot_id = None

                try:
                    # Get diffs
                    diffs = self.diff_scanner.get_diffs_for_commit(commit.hash)

                    # Track last file processed for THIS commit (local to this worker)
                    last_file_for_commit = Path(".")  # Default if no diffs

                    # If no diffs, acquire a slot just to show we processed the commit
                    if not diffs:
                        slot_id = commit_slot_tracker.acquire_slot(
                            FileData(
                                filename=f"{commit.hash[:8]} - no changes",
                                file_size=0,
                                status=FileStatus.COMPLETE,
                            )
                        )

                    # Process each diff
                    for diff_info in diffs:
                        # Option A: Release previous slot and acquire new one for each file
                        if slot_id is not None:
                            commit_slot_tracker.release_slot(slot_id)

                        # Acquire new slot with current file information
                        current_filename = (
                            f"{commit.hash[:8]} - {Path(diff_info.file_path).name}"
                        )
                        slot_id = commit_slot_tracker.acquire_slot(
                            FileData(
                                filename=current_filename,
                                file_size=len(diff_info.diff_content),  # Diff content size in bytes
                                status=FileStatus.CHUNKING,
                            )
                        )

                        # Update last file for THIS commit (local variable)
                        last_file_for_commit = Path(diff_info.file_path)
                        # Skip binary and renamed files (metadata only)
                        if diff_info.diff_type in ["binary", "renamed"]:
                            continue

                        # Skip if blob already indexed (deduplication)
                        if (
                            diff_info.blob_hash
                            and diff_info.blob_hash in self.indexed_blobs
                        ):
                            continue

                        # Chunk the diff content
                        chunks = self.chunker.chunk_text(
                            diff_info.diff_content, Path(diff_info.file_path)
                        )

                        if chunks:
                            # BUG #7 FIX: Check point existence BEFORE making API calls
                            # Build point IDs first to check existence
                            project_id = self.file_identifier._get_project_id()
                            chunks_to_process = []
                            chunk_indices_to_process = []

                            for j, chunk in enumerate(chunks):
                                point_id = f"{project_id}:diff:{commit.hash}:{diff_info.file_path}:{j}"

                                # Skip if point already exists
                                if point_id not in existing_ids:
                                    chunks_to_process.append(chunk)
                                    chunk_indices_to_process.append(j)

                            # Only make API call if there are new chunks to process
                            if not chunks_to_process:
                                # All chunks already exist, skip vectorization entirely
                                continue

                            # Get embeddings for NEW chunks only
                            commit_slot_tracker.update_slot(
                                slot_id, FileStatus.VECTORIZING
                            )
                            chunk_texts = [chunk["text"] for chunk in chunks_to_process]
                            future = vector_manager.submit_batch_task(chunk_texts, {})
                            result = future.result(timeout=300)

                            if result.embeddings:
                                # Finalize (store)
                                commit_slot_tracker.update_slot(
                                    slot_id, FileStatus.FINALIZING
                                )
                                # Create points with correct payload structure
                                points = []

                                # Use chunks_to_process and original indices for correct mapping
                                for chunk, embedding, original_index in zip(
                                    chunks_to_process,
                                    result.embeddings,
                                    chunk_indices_to_process,
                                ):
                                    point_id = f"{project_id}:diff:{commit.hash}:{diff_info.file_path}:{original_index}"

                                    # Convert timestamp to date
                                    from datetime import datetime

                                    commit_date = datetime.fromtimestamp(
                                        commit.timestamp
                                    ).strftime("%Y-%m-%d")

                                    # Extract language and file extension for filter compatibility
                                    # MUST match regular indexing pattern from file_chunking_manager.py
                                    file_path_obj = Path(diff_info.file_path)
                                    file_extension = (
                                        file_path_obj.suffix.lstrip(".") or "txt"
                                    )  # Remove dot, same as regular indexing
                                    language = (
                                        file_path_obj.suffix.lstrip(".") or "txt"
                                    )  # Same format for consistency

                                    # Base payload structure
                                    payload = {
                                        "type": "commit_diff",
                                        "diff_type": diff_info.diff_type,
                                        "commit_hash": commit.hash,
                                        "commit_timestamp": commit.timestamp,
                                        "commit_date": commit_date,
                                        "commit_message": (
                                            commit.message[:200]
                                            if commit.message
                                            else ""
                                        ),
                                        "author_name": commit.author_name,
                                        "author_email": commit.author_email,
                                        "path": diff_info.file_path,  # FIX Bug #1: Use "path" for git-aware storage
                                        "chunk_index": original_index,  # Use original index, not enumerated j
                                        "char_start": chunk.get("char_start", 0),
                                        "char_end": chunk.get("char_end", 0),
                                        "project_id": project_id,
                                        "content": chunk.get(
                                            "text", ""
                                        ),  # Store diff chunk text
                                        "language": language,  # Add language for filter compatibility
                                        "file_extension": file_extension,  # Add file_extension for filter compatibility
                                    }

                                    # Storage optimization: added/deleted files use pointer-based storage
                                    if diff_info.diff_type in ["added", "deleted"]:
                                        payload["reconstruct_from_git"] = True

                                        # Add parent commit for deleted files (enables reconstruction)
                                        if (
                                            diff_info.diff_type == "deleted"
                                            and diff_info.parent_commit_hash
                                        ):
                                            payload["parent_commit_hash"] = (
                                                diff_info.parent_commit_hash
                                            )

                                    point = {
                                        "id": point_id,
                                        "vector": list(embedding),
                                        "payload": payload,
                                    }
                                    points.append(point)

                                # Filter out existing points before upserting
                                new_points = [
                                    point
                                    for point in points
                                    if point["id"] not in existing_ids
                                ]

                                # Only upsert new points
                                if new_points:
                                    self.vector_store.upsert_points(
                                        collection_name=self.TEMPORAL_COLLECTION_NAME,
                                        points=new_points,
                                    )
                                    # Add new points to existing_ids to avoid duplicates within this run
                                    for point in new_points:
                                        existing_ids.add(point["id"])

                                    # Add blob hash to registry after successful indexing
                                    if diff_info.blob_hash:
                                        self.indexed_blobs.add(diff_info.blob_hash)

                    # Mark complete
                    commit_slot_tracker.update_slot(slot_id, FileStatus.COMPLETE)

                    # Save completed commit to progressive metadata (Bug #8 fix)
                    self.progressive_metadata.save_completed(commit.hash)

                    # Update progress counter and shared state ATOMICALLY
                    with progress_lock:
                        completed_count[0] += 1
                        current = completed_count[0]

                        # Update shared state with last completed work
                        last_completed_commit[0] = commit.hash
                        last_completed_file[0] = last_file_for_commit

                        # Call progress callback if provided (inside lock for thread safety)
                        if progress_callback:
                            total = len(commits)
                            elapsed = time.time() - start_time
                            commits_per_sec = current / max(elapsed, 0.1)
                            pct = (100 * current) // total
                            # Get thread count
                            thread_count = (
                                getattr(self.config.voyage_ai, "parallel_requests", 8)
                                if hasattr(self.config, "voyage_ai")
                                else 8
                            )

                            # Use shared state for display (100ms lag acceptable per spec)
                            commit_hash = (
                                last_completed_commit[0][:8]
                                if last_completed_commit[0]
                                else "????????"
                            )
                            file_name = (
                                last_completed_file[0].name
                                if last_completed_file[0]
                                and last_completed_file[0] != Path(".")
                                else "initializing"
                            )

                            # Get concurrent files snapshot
                            import copy

                            concurrent_files = copy.deepcopy(
                                commit_slot_tracker.get_concurrent_files_data()
                            )

                            # Format with ALL Story 1 AC requirements including 📝 emoji
                            info = f"{current}/{total} commits ({pct}%) | {commits_per_sec:.1f} commits/s | {thread_count} threads | 📝 {commit_hash} - {file_name}"

                            # Call with new kwargs for slot-based tracking (backward compatible)
                            try:
                                progress_callback(
                                    current,
                                    total,
                                    last_completed_file[0] or Path("."),
                                    info=info,
                                    concurrent_files=concurrent_files,  # Tree view data
                                    slot_tracker=commit_slot_tracker,  # For live updates
                                )
                            except TypeError:
                                # Fallback for old signature without slot_tracker/concurrent_files
                                progress_callback(
                                    current,
                                    total,
                                    last_completed_file[0] or Path("."),
                                    info=info,
                                )

                finally:
                    # Release slot
                    commit_slot_tracker.release_slot(slot_id)

                commit_queue.task_done()

        # Get thread count from config (default 8)
        thread_count = (
            getattr(self.config.voyage_ai, "parallel_requests", 8)
            if hasattr(self.config, "voyage_ai")
            else 8
        )

        # Use ThreadPoolExecutor for parallel processing with multiple workers
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            # Submit multiple workers
            futures = [executor.submit(worker) for _ in range(thread_count)]

            # Wait for all workers to complete
            for future in as_completed(futures):
                future.result()  # Wait for completion

        # Return actual totals
        total_vectors_created = completed_count[0] * 3  # Approximate vectors per commit
        return len(commits), total_vectors_created

    def _index_commit_message(
        self, commit: CommitInfo, project_id: str, vector_manager
    ):
        """Index commit message as searchable entity.

        Commit messages are chunked using same logic as files and indexed
        as separate vector points. This allows searching by commit message.

        Args:
            commit: Commit object with hash, message, timestamp, author info
            project_id: Project identifier
            vector_manager: VectorCalculationManager for embedding generation
        """
        commit_msg = commit.message or ""
        if not commit_msg.strip():
            return  # Skip empty messages

        # Use chunker (FixedSizeChunker) to chunk commit message
        # Treat commit message like a markdown file for chunking
        chunks = self.chunker.chunk_text(
            commit_msg, Path(f"[commit:{commit.hash[:7]}]")
        )

        if not chunks:
            return

        # Get embeddings for commit message chunks
        chunk_texts = [chunk["text"] for chunk in chunks]

        try:
            # Use same vector manager as file chunks
            future = vector_manager.submit_batch_task(
                chunk_texts, {"commit_hash": commit.hash}
            )
            result = future.result(timeout=300)

            if not result.error and result.embeddings:
                points = []
                for j, (chunk, embedding) in enumerate(zip(chunks, result.embeddings)):
                    point_id = f"{project_id}:commit:{commit.hash}:{j}"

                    # Note: chunks from FixedSizeChunker use char_start/char_end, not line_start/line_end
                    payload = {
                        "type": "commit_message",  # Distinguish from file chunks
                        "commit_hash": commit.hash,
                        "chunk_index": j,
                        "char_start": chunk.get("char_start", 0),
                        "char_end": chunk.get("char_end", len(commit_msg)),
                        "project_id": project_id,
                    }

                    point = {
                        "id": point_id,
                        "vector": list(embedding),
                        "payload": payload,
                    }
                    points.append(point)

                # Store in temporal collection (NOT default collection)
                self.vector_store.upsert_points(
                    collection_name=self.TEMPORAL_COLLECTION_NAME, points=points
                )

        except Exception as e:
            logger.error(f"Error indexing commit message {commit.hash[:7]}: {e}")

    def _save_temporal_metadata(
        self,
        last_commit: str,
        total_commits: int,
        total_blobs: int,
        new_blobs: int,
        branch_stats: dict,
        indexing_mode: str,
    ):
        """Save temporal indexing metadata to JSON."""
        metadata = {
            "last_commit": last_commit,
            "total_commits": total_commits,
            "total_blobs": total_blobs,
            "new_blobs_indexed": new_blobs,
            "deduplication_ratio": (
                1.0 - (new_blobs / total_blobs) if total_blobs > 0 else 1.0
            ),
            "indexed_branches": branch_stats["branches"],
            "indexing_mode": indexing_mode,
            "indexed_at": datetime.now().isoformat(),
        }

        metadata_path = self.temporal_dir / "temporal_meta.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

    def close(self):
        """Clean up resources and finalize HNSW index."""
        # Build HNSW index for temporal collection
        logger.info("Building HNSW index for temporal collection...")
        self.vector_store.end_indexing(collection_name=self.TEMPORAL_COLLECTION_NAME)

        # No blob registry to close in diff-based indexing

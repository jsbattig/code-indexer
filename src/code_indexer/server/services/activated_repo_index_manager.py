"""
Activated Repository Index Manager for CIDX Server.

Manages manual re-indexing operations for activated repositories,
supporting semantic, FTS, temporal, and SCIP indexes.
"""

import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable

from ..repositories.background_jobs import BackgroundJobManager
from ..repositories.activated_repo_manager import ActivatedRepoManager


class IndexingError(Exception):
    """Exception raised when indexing operations fail."""

    pass


logger = logging.getLogger(__name__)


class ActivatedRepoIndexManager:
    """
    Manages manual re-indexing operations for activated repositories.

    Provides on-demand index updates for semantic, FTS, temporal, and SCIP
    indexes after file modifications or for maintenance purposes.
    """

    # Valid index types
    VALID_INDEX_TYPES = ["semantic", "fts", "temporal", "scip"]

    # Timeout constants
    INDEXING_TIMEOUT_SECONDS = 3600  # 1 hour for semantic/FTS/temporal
    SCIP_TIMEOUT_SECONDS = 600  # 10 minutes for SCIP

    # Status detection constants
    STALE_THRESHOLD_DAYS = 7  # Temporal index stale after 7 days
    BYTES_PER_MB = 1024 * 1024  # Bytes to megabytes conversion

    # Concurrent job prevention
    MAX_JOBS_TO_CHECK = 100  # Maximum jobs to check for concurrency conflicts

    def __init__(
        self,
        data_dir: Optional[str] = None,
        background_job_manager: Optional[BackgroundJobManager] = None,
        activated_repo_manager: Optional[ActivatedRepoManager] = None,
    ):
        """
        Initialize activated repository index manager.

        Args:
            data_dir: Data directory path (defaults to ~/.cidx-server/data)
            background_job_manager: Background job manager instance
            activated_repo_manager: Activated repository manager instance
        """
        if data_dir:
            self.data_dir = data_dir
        else:
            home_dir = Path.home()
            self.data_dir = str(home_dir / ".cidx-server" / "data")

        self.logger = logging.getLogger(__name__)

        # Set dependencies
        self.background_job_manager = background_job_manager or BackgroundJobManager()
        self.activated_repo_manager = activated_repo_manager or ActivatedRepoManager(
            self.data_dir
        )

    def trigger_reindex(
        self,
        repo_alias: str,
        index_types: List[str],
        clear: bool,
        username: str,
    ) -> str:
        """
        Trigger manual re-indexing job for activated repository.

        Args:
            repo_alias: Repository alias to reindex
            index_types: List of index types to rebuild (semantic, fts, temporal, scip)
            clear: If True, rebuild from scratch; if False, incremental update
            username: Username requesting reindex

        Returns:
            Job ID for tracking progress

        Raises:
            ValueError: If index_types contains invalid types or is empty
            FileNotFoundError: If repository not found
        """
        # Validate index_types
        if not index_types:
            raise ValueError("At least one index type required")

        invalid_types = [t for t in index_types if t not in self.VALID_INDEX_TYPES]
        if invalid_types:
            raise ValueError(
                f"Invalid index type(s): {', '.join(invalid_types)}. "
                f"Valid types: {', '.join(self.VALID_INDEX_TYPES)}"
            )

        # Validate repository exists
        try:
            repo_path = self.activated_repo_manager.get_activated_repo_path(
                username, repo_alias
            )
        except Exception as e:
            if "not found" in str(e).lower():
                raise FileNotFoundError(
                    f"Repository '{repo_alias}' not found for user '{username}'"
                )
            raise

        # Security: Validate path doesn't escape data directory
        repo_path_obj = Path(repo_path).resolve()
        data_dir_obj = Path(self.data_dir).resolve()
        try:
            repo_path_obj.relative_to(data_dir_obj)
        except ValueError:
            raise ValueError(
                "Security violation: Repository path escapes data directory"
            )

        if not os.path.exists(repo_path):
            raise FileNotFoundError(f"Repository directory not found: {repo_path}")

        # Check for concurrent reindex jobs to prevent resource conflicts
        # Note: BackgroundJobManager doesn't store job parameters, so we check per-user, not per-repo
        running_jobs = self.background_job_manager.list_jobs(
            username=username,
            status_filter="running",
            limit=self.MAX_JOBS_TO_CHECK,
        )
        pending_jobs = self.background_job_manager.list_jobs(
            username=username,
            status_filter="pending",
            limit=self.MAX_JOBS_TO_CHECK,
        )

        # Defensive dict access
        running_jobs_list = running_jobs.get("jobs", [])
        pending_jobs_list = pending_jobs.get("jobs", [])
        all_active_jobs = running_jobs_list + pending_jobs_list

        # Check if any active job is a reindex operation
        for job in all_active_jobs:
            if job.get("operation_type") == "reindex":
                raise ValueError(
                    f"Another reindex job is already running/pending (job {job.get('job_id')}). "
                    f"Please wait for it to complete before starting a new reindex."
                )

        # Submit background job
        # BackgroundJobManager accepts *args/**kwargs despite signature showing Callable[[], Dict[str, Any]]
        # The implementation uses inspect.signature() to detect and inject progress_callback parameter
        job_id = self.background_job_manager.submit_job(  # type: ignore[arg-type]
            "reindex",
            self._execute_indexing_job,
            repo_alias=repo_alias,
            repo_path=repo_path,
            index_types=index_types,
            clear=clear,
            submitter_username=username,
        )

        self.logger.info(
            f"Reindex job {job_id} submitted for repository '{repo_alias}' "
            f"(types: {index_types}, clear: {clear})"
        )

        return job_id

    def get_index_status(
        self,
        repo_alias: str,
        username: str,
    ) -> Dict[str, Any]:
        """
        Get indexing status for all index types.

        Args:
            repo_alias: Repository alias
            username: Username requesting status

        Returns:
            Dictionary with status for each index type

        Raises:
            FileNotFoundError: If repository not found
        """
        # Get repository path
        try:
            repo_path_str = self.activated_repo_manager.get_activated_repo_path(
                username, repo_alias
            )
        except Exception as e:
            if "not found" in str(e).lower():
                raise FileNotFoundError(
                    f"Repository '{repo_alias}' not found for user '{username}'"
                )
            raise

        repo_path = Path(repo_path_str)

        if not repo_path.exists():
            raise FileNotFoundError(f"Repository directory not found: {repo_path}")

        # Get status for each index type
        status = {
            "semantic": self._get_semantic_status(repo_path),
            "fts": self._get_fts_status(repo_path),
            "temporal": self._get_temporal_status(repo_path),
            "scip": self._get_scip_status(repo_path),
        }

        return status

    def _execute_indexing_job(
        self,
        repo_alias: str,
        repo_path: str,
        index_types: List[str],
        clear: bool,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Execute indexing job for specified index types.

        Args:
            repo_alias: Repository alias
            repo_path: Repository filesystem path
            index_types: List of index types to rebuild
            clear: Rebuild from scratch vs incremental
            progress_callback: Optional progress callback (0-100)

        Returns:
            Result dictionary with success status and details
        """

        def update_progress(percent: int, message: str = "") -> None:
            """Helper to update progress with logging."""
            if progress_callback:
                progress_callback(percent)
            if message:
                self.logger.info(f"Reindex progress ({percent}%): {message}")

        try:
            update_progress(
                10,
                f"Starting reindex for '{repo_alias}' (types: {index_types}, clear: {clear})",
            )

            # Execute each index type and collect results
            results = self._execute_all_index_types(
                repo_path, index_types, clear, update_progress
            )

            # Determine overall success
            all_success = all(r.get("success", False) for r in results.values())
            failed_types = [
                t for t, r in results.items() if not r.get("success", False)
            ]

            if all_success:
                message = f"Successfully reindexed all types: {', '.join(index_types)}"
            else:
                message = f"Reindex completed with failures: {', '.join(failed_types)}"

            update_progress(100, message)

            return {
                "success": all_success,
                "message": message,
                "results": results,
                "failed_types": failed_types if failed_types else None,
            }

        except Exception as e:
            error_msg = f"Failed to execute reindex job for '{repo_alias}': {str(e)}"
            self.logger.error(error_msg)

            if progress_callback:
                progress_callback(0)  # Reset progress to indicate failure

            return {
                "success": False,
                "message": error_msg,
                "results": {},
                "error": str(e),
            }

    def _execute_all_index_types(
        self,
        repo_path: str,
        index_types: List[str],
        clear: bool,
        update_progress: Callable,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Execute indexing for all requested index types.

        Args:
            repo_path: Repository path
            index_types: List of index types to process
            clear: Clear flag
            update_progress: Progress callback function

        Returns:
            Dictionary mapping index type to result
        """
        results = {}
        total_types = len(index_types)

        for idx, index_type in enumerate(index_types):
            base_progress = 10 + int((idx / total_types) * 80)
            next_progress = 10 + int(((idx + 1) / total_types) * 80)

            update_progress(
                base_progress, f"Processing {index_type} index ({idx+1}/{total_types})"
            )

            try:
                result = self._execute_single_index_type(repo_path, index_type, clear)
                results[index_type] = result

                if not result.get("success", False):
                    error_msg = result.get("error", "Unknown error")
                    self.logger.error(f"Failed to index {index_type}: {error_msg}")
            except Exception as e:
                error_msg = f"Exception during {index_type} indexing: {str(e)}"
                self.logger.error(error_msg)
                results[index_type] = {"success": False, "error": error_msg}

            update_progress(next_progress, f"Completed {index_type} index")

        return results

    def _execute_single_index_type(
        self, repo_path: str, index_type: str, clear: bool
    ) -> Dict[str, Any]:
        """
        Execute indexing for a single index type.

        Args:
            repo_path: Repository path
            index_type: Index type to process
            clear: Clear flag

        Returns:
            Result dictionary
        """
        if index_type == "semantic":
            return self._execute_semantic_indexing(repo_path, clear)
        elif index_type == "fts":
            return self._execute_fts_indexing(repo_path, clear)
        elif index_type == "temporal":
            return self._execute_temporal_indexing(repo_path, clear)
        elif index_type == "scip":
            return self._execute_scip_indexing(repo_path, clear)
        else:
            return {"success": False, "error": f"Unknown index type: {index_type}"}

    def _execute_semantic_indexing(
        self, repo_path: str, clear: bool
    ) -> Dict[str, Any]:
        """Execute semantic indexing using SmartIndexer."""
        try:
            repo_path_obj = Path(repo_path)
            index_dir = repo_path_obj / ".code-indexer" / "index"

            # Clear index if requested
            if clear and index_dir.exists():
                self.logger.info(f"Clearing semantic index: {index_dir}")
                shutil.rmtree(index_dir)

            # Run cidx index command
            result = subprocess.run(
                ["cidx", "index"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=self.INDEXING_TIMEOUT_SECONDS,
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Semantic indexing failed: {result.stderr}",
                }

            return {"success": True, "message": "Semantic indexing completed"}

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Semantic indexing timed out"}
        except Exception as e:
            return {"success": False, "error": f"Semantic indexing error: {str(e)}"}

    def _execute_fts_indexing(self, repo_path: str, clear: bool) -> Dict[str, Any]:
        """Execute FTS indexing using TantivyIndexManager."""
        try:
            args = ["cidx", "index", "--fts"]
            if clear:
                args.append("--clear")

            result = subprocess.run(
                args,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=self.INDEXING_TIMEOUT_SECONDS,
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"FTS indexing failed: {result.stderr}",
                }

            return {"success": True, "message": "FTS indexing completed"}

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "FTS indexing timed out"}
        except Exception as e:
            return {"success": False, "error": f"FTS indexing error: {str(e)}"}

    def _execute_temporal_indexing(
        self, repo_path: str, clear: bool
    ) -> Dict[str, Any]:
        """Execute temporal indexing using GitCommitIndexer."""
        try:
            args = ["cidx", "index", "--index-commits"]
            if clear:
                args.append("--clear")

            result = subprocess.run(
                args,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=self.INDEXING_TIMEOUT_SECONDS,
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Temporal indexing failed: {result.stderr}",
                }

            return {"success": True, "message": "Temporal indexing completed"}

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Temporal indexing timed out"}
        except Exception as e:
            return {"success": False, "error": f"Temporal indexing error: {str(e)}"}

    def _execute_scip_indexing(self, repo_path: str, clear: bool) -> Dict[str, Any]:
        """Execute SCIP indexing using cidx scip generate."""
        try:
            args = ["cidx", "scip", "generate", "--project", repo_path]
            if clear:
                args.append("--clear")

            result = subprocess.run(
                args,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=self.SCIP_TIMEOUT_SECONDS,
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"SCIP generation failed: {result.stderr}",
                }

            return {"success": True, "message": "SCIP generation completed"}

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "SCIP generation timed out"}
        except Exception as e:
            return {"success": False, "error": f"SCIP generation error: {str(e)}"}

    def _get_semantic_status(self, repo_path: Path) -> Dict[str, Any]:
        """Get semantic index status."""
        index_dir = repo_path / ".code-indexer" / "index"

        if not index_dir.exists():
            return {"status": "not_indexed"}

        metadata_file = index_dir / "metadata.json"
        if not metadata_file.exists():
            return {"status": "not_indexed"}

        try:
            with open(metadata_file) as f:
                metadata = json.load(f)

            # Calculate index size
            index_size_bytes = sum(
                f.stat().st_size for f in index_dir.rglob("*") if f.is_file()
            )
            index_size_mb = round(index_size_bytes / self.BYTES_PER_MB, 2)

            return {
                "last_indexed": metadata.get("last_indexed"),
                "file_count": metadata.get("file_count", 0),
                "index_size_mb": index_size_mb,
                "status": "up_to_date",
            }
        except Exception as e:
            self.logger.warning(f"Failed to read semantic index metadata: {e}")
            return {"status": "not_indexed"}

    def _get_fts_status(self, repo_path: Path) -> Dict[str, Any]:
        """Get FTS index status."""
        fts_dir = repo_path / ".code-indexer" / "tantivy"

        if not fts_dir.exists():
            return {"status": "not_indexed"}

        try:
            # Count document files (rough approximation)
            doc_count = sum(1 for _ in fts_dir.rglob("*.store"))

            # Get last modified time
            latest_file = max(
                (f for f in fts_dir.rglob("*") if f.is_file()),
                key=lambda f: f.stat().st_mtime,
                default=None,
            )

            if latest_file:
                last_updated = datetime.fromtimestamp(
                    latest_file.stat().st_mtime, tz=timezone.utc
                ).isoformat()
            else:
                last_updated = None

            return {
                "last_updated": last_updated,
                "document_count": doc_count,
                "index_health": "healthy",
                "status": "up_to_date",
            }
        except Exception as e:
            self.logger.warning(f"Failed to read FTS index status: {e}")
            return {"status": "not_indexed"}

    def _get_temporal_status(self, repo_path: Path) -> Dict[str, Any]:
        """Get temporal index status."""
        temporal_dir = (
            repo_path / ".code-indexer" / "index" / "code-indexer-temporal"
        )

        if not temporal_dir.exists():
            return {"status": "not_indexed"}

        metadata_file = temporal_dir / "metadata.json"
        if not metadata_file.exists():
            return {"status": "not_indexed"}

        try:
            with open(metadata_file) as f:
                metadata = json.load(f)

            last_indexed = metadata.get("last_indexed")
            commit_count = metadata.get("commit_count", 0)

            # Check if stale
            status = "up_to_date"
            if last_indexed:
                last_indexed_dt = datetime.fromisoformat(last_indexed)
                age_days = (datetime.now(timezone.utc) - last_indexed_dt).days
                if age_days > self.STALE_THRESHOLD_DAYS:
                    status = "stale"

            return {
                "last_indexed": last_indexed,
                "commit_count": commit_count,
                "date_range": metadata.get("date_range"),
                "status": status,
            }
        except Exception as e:
            self.logger.warning(f"Failed to read temporal index metadata: {e}")
            return {"status": "not_indexed"}

    def _get_scip_status(self, repo_path: Path) -> Dict[str, Any]:
        """Get SCIP index status."""
        scip_dir = repo_path / ".code-indexer" / "scip"

        if not scip_dir.exists():
            return {"status": "not_indexed", "project_count": 0}

        # Check for .scip.db files
        scip_files = list(scip_dir.glob("*.scip.db"))

        if not scip_files:
            return {"status": "not_indexed", "project_count": 0}

        try:
            # Get last generated time from most recent file
            latest_file = max(scip_files, key=lambda f: f.stat().st_mtime)
            last_generated = datetime.fromtimestamp(
                latest_file.stat().st_mtime, tz=timezone.utc
            ).isoformat()

            # Count projects and extract names
            project_count = len(scip_files)
            projects = [f.stem.replace(".scip", "") for f in scip_files]

            return {
                "status": "SUCCESS",
                "project_count": project_count,
                "last_generated": last_generated,
                "projects": projects,
            }
        except Exception as e:
            self.logger.warning(f"Failed to read SCIP index status: {e}")
            return {"status": "FAILED", "project_count": 0, "error": str(e)}

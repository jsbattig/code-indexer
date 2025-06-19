"""
Progressive metadata manager for resumable indexing operations.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone


class ProgressiveMetadata:
    """Manages progressive metadata for resumable indexing."""

    def __init__(self, metadata_path: Path):
        self.metadata_path = metadata_path
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> Dict[str, Any]:
        """Load existing metadata or create empty structure."""
        if self.metadata_path.exists():
            try:
                with open(self.metadata_path, "r") as f:
                    loaded_data = json.load(f)
                    if isinstance(loaded_data, dict):
                        return loaded_data
            except (json.JSONDecodeError, IOError):
                # Corrupt metadata, start fresh
                pass

        return {
            "status": "not_started",
            "last_index_timestamp": 0.0,
            "indexed_at": None,
            "git_available": False,
            "project_id": None,
            "current_branch": None,
            "current_commit": None,
            "embedding_provider": None,
            "embedding_model": None,
            "files_processed": 0,
            "chunks_indexed": 0,
            "failed_files": 0,
            # New fields for true resumability
            "total_files_to_index": 0,
            "files_to_index": [],  # List of all files that need indexing
            "completed_files": [],  # List of files that have been successfully indexed
            "failed_file_paths": [],  # List of files that failed indexing
            "current_file_index": 0,  # Index of current file being processed
        }

    def _save_metadata(self):
        """Save metadata to disk."""
        # Ensure parent directory exists
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.metadata_path, "w") as f:
            json.dump(self.metadata, f, indent=2)

    def start_indexing(
        self, provider_name: str, model_name: str, git_status: Dict[str, Any]
    ):
        """Mark the start of an indexing operation."""
        self.metadata.update(
            {
                "status": "in_progress",
                "indexed_at": datetime.now(timezone.utc).isoformat(),
                "embedding_provider": provider_name,
                "embedding_model": model_name,
                "git_available": git_status.get("git_available", False),
                "project_id": git_status.get("project_id"),
                "current_branch": git_status.get("current_branch"),
                "current_commit": git_status.get("current_commit"),
                "files_processed": 0,
                "chunks_indexed": 0,
                "failed_files": 0,
            }
        )
        self._save_metadata()

    def update_progress(
        self, files_processed: int = 0, chunks_added: int = 0, failed_files: int = 0
    ):
        """Update progress counters and timestamp after each file."""
        current_timestamp = time.time()

        self.metadata["last_index_timestamp"] = current_timestamp
        self.metadata["files_processed"] += files_processed
        self.metadata["chunks_indexed"] += chunks_added
        self.metadata["failed_files"] += failed_files

        # Save after every update for resumability
        self._save_metadata()

    def complete_indexing(self):
        """Mark indexing as completed."""
        self.metadata["status"] = "completed"
        self.metadata["indexed_at"] = datetime.now(timezone.utc).isoformat()
        self._save_metadata()

    def fail_indexing(self, error_message: Optional[str] = None):
        """Mark indexing as failed."""
        self.metadata["status"] = "failed"
        if error_message:
            self.metadata["error_message"] = error_message
        self._save_metadata()

    def get_resume_timestamp(self, safety_buffer_seconds: int = 60) -> float:
        """Get timestamp for resuming indexing with safety buffer.

        Args:
            safety_buffer_seconds: Number of seconds to go back for safety (default: 60)

        Returns:
            Timestamp to resume from, or 0.0 if full index needed
        """
        if self.metadata["status"] not in ["in_progress", "completed"]:
            return 0.0

        last_timestamp = self.metadata.get("last_index_timestamp", 0.0)
        if not isinstance(last_timestamp, (int, float)) or last_timestamp == 0.0:
            return 0.0

        # Apply safety buffer - go back N seconds to catch any files we might have missed
        return max(0.0, float(last_timestamp) - safety_buffer_seconds)

    def should_force_full_index(
        self,
        current_provider: str,
        current_model: str,
        current_git_status: Dict[str, Any],
    ) -> bool:
        """Check if we need to force a full index due to configuration changes."""

        # Check if embedding provider or model changed
        if (
            self.metadata.get("embedding_provider") != current_provider
            or self.metadata.get("embedding_model") != current_model
        ):
            return True

        # Check if git availability changed
        if self.metadata.get("git_available") != current_git_status.get(
            "git_available", False
        ):
            return True

        # Check if project changed (different directory or git repo)
        if self.metadata.get("project_id") != current_git_status.get("project_id"):
            return True

        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get current indexing statistics."""
        can_resume_interrupted = (
            self.metadata.get("status") == "in_progress"
            and len(self.metadata.get("files_to_index", [])) > 0
            and self.metadata.get("current_file_index", 0)
            < len(self.metadata.get("files_to_index", []))
        )
        can_resume_incremental = (
            self.metadata.get("status") in ["in_progress", "completed"]
            and self.metadata.get("last_index_timestamp", 0) > 0
        )

        return {
            "status": self.metadata.get("status", "not_started"),
            "last_indexed": self.metadata.get("indexed_at"),
            "files_processed": self.metadata.get("files_processed", 0),
            "chunks_indexed": self.metadata.get("chunks_indexed", 0),
            "failed_files": self.metadata.get("failed_files", 0),
            "embedding_provider": self.metadata.get("embedding_provider"),
            "embedding_model": self.metadata.get("embedding_model"),
            "project_id": self.metadata.get("project_id"),
            "current_branch": self.metadata.get("current_branch"),
            "can_resume": can_resume_incremental,
            "can_resume_interrupted": can_resume_interrupted,
            "total_files_to_index": self.metadata.get("total_files_to_index", 0),
            "current_file_index": self.metadata.get("current_file_index", 0),
            "remaining_files": max(
                0,
                self.metadata.get("total_files_to_index", 0)
                - self.metadata.get("current_file_index", 0),
            ),
        }

    def clear(self):
        """Clear all metadata (for fresh start)."""
        self.metadata = {
            "status": "not_started",
            "last_index_timestamp": 0.0,
            "indexed_at": None,
            "git_available": False,
            "project_id": None,
            "current_branch": None,
            "current_commit": None,
            "embedding_provider": None,
            "embedding_model": None,
            "files_processed": 0,
            "chunks_indexed": 0,
            "failed_files": 0,
            # Reset resumability fields
            "total_files_to_index": 0,
            "files_to_index": [],
            "completed_files": [],
            "failed_file_paths": [],
            "current_file_index": 0,
        }
        self._save_metadata()

    def set_files_to_index(self, file_paths: list) -> None:
        """Set the complete list of files to be indexed for resumability."""
        # Convert Path objects to strings for JSON serialization
        file_strings = [str(path) for path in file_paths]

        self.metadata["files_to_index"] = file_strings
        self.metadata["total_files_to_index"] = len(file_strings)
        self.metadata["current_file_index"] = 0
        self.metadata["completed_files"] = []
        self.metadata["failed_file_paths"] = []
        self._save_metadata()

    def get_remaining_files(self) -> List[str]:
        """Get the list of files that still need to be processed."""
        current_index = self.metadata.get("current_file_index", 0)
        files_to_index = self.metadata.get("files_to_index", [])

        if current_index < len(files_to_index):
            return list(files_to_index[current_index:])
        return []

    def mark_file_completed(self, file_path: str, chunks_count: int = 0) -> None:
        """Mark a file as successfully processed."""
        completed_files = self.metadata.get("completed_files", [])
        if str(file_path) not in completed_files:
            completed_files.append(str(file_path))
            self.metadata["completed_files"] = completed_files

        # Advance the current file index
        self.metadata["current_file_index"] = (
            self.metadata.get("current_file_index", 0) + 1
        )

        # Update overall progress
        self.metadata["files_processed"] = len(completed_files)
        self.metadata["chunks_indexed"] = (
            self.metadata.get("chunks_indexed", 0) + chunks_count
        )
        self.metadata["last_index_timestamp"] = time.time()

        self._save_metadata()

    def mark_file_failed(self, file_path: str, error: str = "") -> None:
        """Mark a file as failed during processing."""
        failed_files = self.metadata.get("failed_file_paths", [])
        file_str = str(file_path)

        if file_str not in failed_files:
            failed_files.append(file_str)
            self.metadata["failed_file_paths"] = failed_files

        # Advance the current file index even for failed files
        self.metadata["current_file_index"] = (
            self.metadata.get("current_file_index", 0) + 1
        )

        # Update failed files count
        self.metadata["failed_files"] = len(failed_files)

        self._save_metadata()

    def can_resume_interrupted_operation(self) -> bool:
        """Check if there's an interrupted indexing operation that can be resumed."""
        return (
            self.metadata.get("status") == "in_progress"
            and len(self.metadata.get("files_to_index", [])) > 0
            and self.metadata.get("current_file_index", 0)
            < len(self.metadata.get("files_to_index", []))
        )

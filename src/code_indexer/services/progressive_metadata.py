"""
Progressive metadata manager for resumable indexing operations.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
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
            "can_resume": self.metadata.get("status") in ["in_progress", "completed"]
            and self.metadata.get("last_index_timestamp", 0) > 0,
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
        }
        self._save_metadata()

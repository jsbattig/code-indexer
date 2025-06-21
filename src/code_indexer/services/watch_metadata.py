"""
Watch metadata management for persistent state across watch sessions.

Provides resumable watch functionality with timestamp tracking, git state monitoring,
and crash recovery capabilities.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timezone
from dataclasses import dataclass, asdict


@dataclass
class WatchMetadata:
    """Persistent metadata for resumable watch operations."""

    # Timestamp tracking
    last_sync_timestamp: float = 0.0
    watch_started_at: Optional[str] = None

    # Git state tracking
    current_branch: Optional[str] = None
    current_commit: Optional[str] = None
    git_available: bool = False

    # Indexing state
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    collection_name: Optional[str] = None

    # Recovery state
    files_being_processed: Optional[List[str]] = None
    processing_interrupted: bool = False
    last_error: Optional[str] = None

    # Statistics
    total_files_processed: int = 0
    total_indexing_cycles: int = 0
    total_branch_changes_detected: int = 0

    def __post_init__(self):
        """Initialize default values."""
        if self.files_being_processed is None:
            self.files_being_processed = []

    @classmethod
    def load_from_disk(cls, metadata_path: Path) -> "WatchMetadata":
        """Load watch metadata from disk or create new instance."""
        if metadata_path.exists():
            try:
                with open(metadata_path, "r") as f:
                    data = json.load(f)
                    return cls(**data)
            except (json.JSONDecodeError, IOError, TypeError) as e:
                # Corrupt metadata, start fresh but log the issue
                print(f"Warning: Corrupt watch metadata, starting fresh: {e}")

        return cls()

    def save_to_disk(self, metadata_path: Path):
        """Save watch metadata to disk."""
        # Ensure parent directory exists
        metadata_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict and save
        with open(metadata_path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    def start_watch_session(
        self,
        provider_name: str,
        model_name: str,
        git_status: Dict[str, Any],
        collection_name: str,
    ):
        """Mark the start of a watch session."""
        self.watch_started_at = datetime.now(timezone.utc).isoformat()
        self.embedding_provider = provider_name
        self.embedding_model = model_name
        self.collection_name = collection_name

        # Update git state
        self.git_available = git_status.get("git_available", False)
        self.current_branch = git_status.get("current_branch")
        self.current_commit = git_status.get("current_commit")

        # Reset processing state
        self.files_being_processed = []
        self.processing_interrupted = False
        self.last_error = None

    def update_after_sync_cycle(self, files_processed: int = 0):
        """Update metadata after a successful sync cycle."""
        self.last_sync_timestamp = time.time()
        self.total_files_processed += files_processed
        self.total_indexing_cycles += 1

        # Clear processing state
        self.files_being_processed = []
        self.processing_interrupted = False
        self.last_error = None

    def update_git_state(self, new_branch: str, new_commit: str):
        """Update git state when branch/commit changes."""
        if new_branch != self.current_branch:
            self.total_branch_changes_detected += 1

        self.current_branch = new_branch
        self.current_commit = new_commit

    def mark_processing_start(self, files_to_process: List[str]):
        """Mark the start of file processing for crash recovery."""
        self.files_being_processed = files_to_process.copy()
        self.processing_interrupted = False

    def mark_processing_interrupted(self, error: Optional[str] = None):
        """Mark processing as interrupted for recovery."""
        self.processing_interrupted = True
        self.last_error = error

    def should_reprocess_file(self, file_path: Path) -> bool:
        """Check if file should be reprocessed based on timestamps."""
        if not file_path.exists():
            return False

        file_mtime = file_path.stat().st_mtime
        return file_mtime > self.last_sync_timestamp

    def get_recovery_files(self) -> List[str]:
        """Get list of files that need recovery processing."""
        if not self.processing_interrupted:
            return []

        return self.files_being_processed.copy() if self.files_being_processed else []

    def is_provider_changed(self, provider_name: str, model_name: str) -> bool:
        """Check if embedding provider/model has changed."""
        return (
            self.embedding_provider != provider_name
            or self.embedding_model != model_name
        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get watch session statistics."""
        return {
            "watch_started_at": self.watch_started_at,
            "total_files_processed": self.total_files_processed,
            "total_indexing_cycles": self.total_indexing_cycles,
            "total_branch_changes": self.total_branch_changes_detected,
            "current_branch": self.current_branch,
            "last_sync_timestamp": self.last_sync_timestamp,
            "processing_interrupted": self.processing_interrupted,
            "files_in_recovery": (
                len(self.files_being_processed) if self.files_being_processed else 0
            ),
        }


class GitStateMonitor:
    """Monitors git state changes during watch operations."""

    def __init__(self, git_topology_service, check_interval: float = 1.0):
        """Initialize git state monitor.

        Args:
            git_topology_service: GitTopologyService instance
            check_interval: How often to check git state (seconds)
        """
        self.git_topology_service = git_topology_service
        self.check_interval = check_interval
        self.current_branch: Optional[str] = None
        self.current_commit: Optional[str] = None
        self.branch_change_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._monitoring = False

    def start_monitoring(self):
        """Start monitoring git state changes."""
        if not self.git_topology_service.is_git_available():
            return False

        # Initialize current state
        self.current_branch = self.git_topology_service.get_current_branch()
        self.current_commit = self._get_current_commit()
        self._monitoring = True
        return True

    def stop_monitoring(self):
        """Stop monitoring git state changes."""
        self._monitoring = False

    def check_for_changes(self) -> Optional[Dict[str, Any]]:
        """Check for git state changes. Returns change event if detected."""
        if not self._monitoring or not self.git_topology_service.is_git_available():
            return None

        new_branch = self.git_topology_service.get_current_branch()
        new_commit = self._get_current_commit()

        # Check for changes
        if new_branch != self.current_branch or new_commit != self.current_commit:
            change_event = {
                "type": "git_state_change",
                "old_branch": self.current_branch,
                "new_branch": new_branch,
                "old_commit": self.current_commit,
                "new_commit": new_commit,
                "timestamp": time.time(),
            }

            # Update current state
            self.current_branch = new_branch
            self.current_commit = new_commit

            # Notify callbacks
            for callback in self.branch_change_callbacks:
                try:
                    callback(change_event)
                except Exception as e:
                    print(f"Warning: Branch change callback failed: {e}")

            return change_event

        return None

    def register_branch_change_callback(self, callback):
        """Register callback for branch change events."""
        self.branch_change_callbacks.append(callback)

    def _get_current_commit(self) -> Optional[str]:
        """Get current commit hash."""
        try:
            import subprocess

            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.git_topology_service.codebase_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def get_current_state(self) -> Dict[str, Any]:
        """Get current git state."""
        return {
            "git_available": self.git_topology_service.is_git_available(),
            "current_branch": self.current_branch,
            "current_commit": self.current_commit,
        }

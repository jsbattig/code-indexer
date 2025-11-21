"""
Structured indexing progress logging for reliable cancellation and resume.

This module provides detailed logging of indexing progress within the .code-indexer
folder to enable efficient resume operations without expensive Filesystem scans.
"""

import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class FileIndexingStatus(Enum):
    """Status of individual file indexing."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class FileIndexingRecord:
    """Record of individual file indexing progress."""

    file_path: str
    status: FileIndexingStatus
    chunks_created: int = 0
    processing_time: float = 0.0
    error_message: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    vector_point_ids: Optional[List[str]] = None  # Track vector store record IDs

    def __post_init__(self):
        if self.vector_point_ids is None:
            self.vector_point_ids = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileIndexingRecord":
        """Create from dictionary loaded from JSON."""
        data["status"] = FileIndexingStatus(data["status"])
        return cls(**data)


@dataclass
class IndexingSession:
    """Complete indexing session information."""

    session_id: str
    operation_type: str  # "full", "incremental", "reconcile"
    started_at: float
    embedding_provider: str
    embedding_model: str
    git_branch: Optional[str] = None
    git_commit: Optional[str] = None
    completed_at: Optional[float] = None
    cancelled_at: Optional[float] = None
    total_files: int = 0
    files_completed: int = 0
    files_failed: int = 0
    chunks_created: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IndexingSession":
        """Create from dictionary loaded from JSON."""
        return cls(**data)


class IndexingProgressLog:
    """
    Structured indexing progress logger for reliable cancellation and resume.

    Maintains detailed file-by-file progress in .code-indexer/indexing_progress.json
    to enable efficient resume operations without scanning Filesystem.
    """

    def __init__(self, config_dir: Path):
        """Initialize progress logger."""
        self.config_dir = Path(config_dir)
        self.progress_file = self.config_dir / "indexing_progress.json"
        self.lock_file = self.config_dir / "indexing_progress.lock"

        # In-memory state
        self.current_session: Optional[IndexingSession] = None
        self.file_records: Dict[str, FileIndexingRecord] = {}

        # Load existing progress
        self._load_progress()

    def start_session(
        self,
        operation_type: str,
        embedding_provider: str,
        embedding_model: str,
        files_to_index: List[str],
        git_branch: Optional[str] = None,
        git_commit: Optional[str] = None,
    ) -> str:
        """
        Start a new indexing session.

        Returns:
            Session ID for tracking
        """
        session_id = f"{operation_type}_{int(time.time())}"

        self.current_session = IndexingSession(
            session_id=session_id,
            operation_type=operation_type,
            started_at=time.time(),
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            git_branch=git_branch,
            git_commit=git_commit,
            total_files=len(files_to_index),
        )

        # Initialize file records for all files as pending
        self.file_records = {
            file_path: FileIndexingRecord(
                file_path=file_path, status=FileIndexingStatus.PENDING
            )
            for file_path in files_to_index
        }

        self._save_progress()
        logger.info(
            f"Started indexing session {session_id} with {len(files_to_index)} files"
        )
        return session_id

    def mark_file_in_progress(self, file_path: str) -> None:
        """Mark a file as currently being processed."""
        if file_path in self.file_records:
            record = self.file_records[file_path]
            record.status = FileIndexingStatus.IN_PROGRESS
            record.started_at = time.time()
            self._save_progress()

    def mark_file_completed(
        self,
        file_path: str,
        chunks_created: int = 0,
        vector_point_ids: Optional[List[str]] = None,
    ) -> None:
        """Mark a file as successfully completed with vector store record IDs."""
        if file_path in self.file_records:
            record = self.file_records[file_path]
            record.status = FileIndexingStatus.COMPLETED
            record.chunks_created = chunks_created
            record.completed_at = time.time()

            if vector_point_ids:
                record.vector_point_ids = vector_point_ids

            if record.started_at:
                record.processing_time = record.completed_at - record.started_at

            if self.current_session:
                self.current_session.files_completed += 1
                self.current_session.chunks_created += chunks_created

            self._save_progress()

            vector_info = (
                f" -> Vector IDs: {vector_point_ids[:3]}{'...' if len(vector_point_ids) > 3 else ''}"
                if vector_point_ids
                else ""
            )
            logger.debug(
                f"Completed file: {file_path} ({chunks_created} chunks){vector_info}"
            )

    def mark_file_failed(self, file_path: str, error_message: str) -> None:
        """Mark a file as failed with error message."""
        if file_path in self.file_records:
            record = self.file_records[file_path]
            record.status = FileIndexingStatus.FAILED
            record.error_message = error_message
            record.completed_at = time.time()

            if record.started_at:
                record.processing_time = record.completed_at - record.started_at

            if self.current_session:
                self.current_session.files_failed += 1

            self._save_progress()
            logger.warning(f"Failed file: {file_path} - {error_message}")

    def mark_session_cancelled(self) -> None:
        """Mark the current session as cancelled."""
        if self.current_session:
            self.current_session.cancelled_at = time.time()

            # Mark all in-progress files as cancelled
            for record in self.file_records.values():
                if record.status == FileIndexingStatus.IN_PROGRESS:
                    record.status = FileIndexingStatus.CANCELLED
                    record.completed_at = time.time()
                    if record.started_at:
                        record.processing_time = record.completed_at - record.started_at

            self._save_progress()
            logger.info(f"Cancelled session {self.current_session.session_id}")

    def complete_session(self) -> None:
        """Mark the current session as completed."""
        if self.current_session:
            self.current_session.completed_at = time.time()
            self._save_progress()
            logger.info(f"Completed session {self.current_session.session_id}")

    def get_pending_files(self) -> List[str]:
        """Get list of files that still need to be processed."""
        return [
            record.file_path
            for record in self.file_records.values()
            if record.status
            in [FileIndexingStatus.PENDING, FileIndexingStatus.CANCELLED]
        ]

    def get_completed_files(self) -> List[str]:
        """Get list of successfully completed files."""
        return [
            record.file_path
            for record in self.file_records.values()
            if record.status == FileIndexingStatus.COMPLETED
        ]

    def get_failed_files(self) -> List[str]:
        """Get list of failed files."""
        return [
            record.file_path
            for record in self.file_records.values()
            if record.status == FileIndexingStatus.FAILED
        ]

    def can_resume_session(self) -> bool:
        """Check if there's a session that can be resumed."""
        return (
            self.current_session is not None
            and self.current_session.completed_at is None
            and len(self.get_pending_files()) > 0
        )

    def get_progress_summary(self) -> Dict[str, Any]:
        """Get summary of current progress."""
        if not self.current_session:
            return {"no_active_session": True}

        pending_files = self.get_pending_files()
        completed_files = self.get_completed_files()
        failed_files = self.get_failed_files()

        return {
            "session_id": self.current_session.session_id,
            "operation_type": self.current_session.operation_type,
            "started_at": self.current_session.started_at,
            "total_files": self.current_session.total_files,
            "files_completed": len(completed_files),
            "files_failed": len(failed_files),
            "files_pending": len(pending_files),
            "chunks_created": self.current_session.chunks_created,
            "can_resume": self.can_resume_session(),
            "cancelled": self.current_session.cancelled_at is not None,
            "completed": self.current_session.completed_at is not None,
        }

    def _load_progress(self) -> None:
        """Load progress from disk."""
        if not self.progress_file.exists():
            return

        try:
            with open(self.progress_file, "r") as f:
                data = json.load(f)

            if "current_session" in data and data["current_session"]:
                self.current_session = IndexingSession.from_dict(
                    data["current_session"]
                )

            if "file_records" in data:
                self.file_records = {
                    file_path: FileIndexingRecord.from_dict(record_data)
                    for file_path, record_data in data["file_records"].items()
                }

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to load progress file: {e}")

    def _save_progress(self) -> None:
        """Save progress to disk atomically."""
        try:
            # Ensure directory exists
            self.config_dir.mkdir(parents=True, exist_ok=True)

            # Prepare data
            data = {
                "current_session": (
                    self.current_session.to_dict() if self.current_session else None
                ),
                "file_records": {
                    file_path: record.to_dict()
                    for file_path, record in self.file_records.items()
                },
                "last_updated": time.time(),
            }

            # Atomic write using temp file
            temp_file = self.progress_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)

            temp_file.replace(self.progress_file)

        except Exception as e:
            logger.error(f"Failed to save progress file: {e}")
            raise

    def cleanup_completed_session(self) -> None:
        """Clean up completed session data to avoid confusion."""
        if self.current_session and self.current_session.completed_at:
            self.current_session = None
            self.file_records = {}

            # Remove the progress file since session is completed
            if self.progress_file.exists():
                self.progress_file.unlink()

            logger.info("Cleaned up completed session data")

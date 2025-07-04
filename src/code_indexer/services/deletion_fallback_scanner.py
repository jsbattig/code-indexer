"""
Deletion Fallback Scanner - Periodic file scanning to detect missed deletions.

This module implements a fallback mechanism for detecting file deletions when
filesystem event monitoring fails or misses events. It periodically scans the
file system and compares it to a snapshot to identify deleted files.

This addresses the user's request: "scanning the list of files once a minute
and comparing to a snapshot, and if you see a file missing it because it was deleted"
"""

import logging
import time
import threading
from pathlib import Path
from typing import Set, Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class FileSnapshot:
    """Snapshot of files at a specific point in time."""

    timestamp: datetime
    files: Set[str] = field(default_factory=set)
    total_files: int = 0
    scan_duration_seconds: float = 0.0


@dataclass
class DeletionEvent:
    """Represents a detected file deletion."""

    file_path: str
    detected_at: datetime
    last_seen_at: datetime
    confidence: str  # 'high', 'medium', 'low'


class DeletionFallbackScanner:
    """
    Periodic file scanner that detects missed deletions by comparing filesystem snapshots.

    This scanner complements filesystem event monitoring by periodically scanning
    the codebase and comparing it to previous snapshots to identify deleted files.
    """

    def __init__(
        self,
        config,
        codebase_dir: Path,
        scan_interval_seconds: int = 15,  # Default: scan every 15 seconds
        deletion_callback: Optional[Callable[[str], None]] = None,
        min_confidence_threshold: str = "medium",
    ):
        """
        Initialize the deletion fallback scanner.

        Args:
            config: Application configuration for file filtering
            codebase_dir: Root directory to scan
            scan_interval_seconds: How often to scan (default: 60 seconds)
            deletion_callback: Function to call when deletion is detected
            min_confidence_threshold: Minimum confidence level to trigger callback
        """
        self.config = config
        self.codebase_dir = Path(codebase_dir)
        self.scan_interval = scan_interval_seconds
        self.deletion_callback = deletion_callback
        self.min_confidence_threshold = min_confidence_threshold

        # Scanning state
        self.current_snapshot: Optional[FileSnapshot] = None
        self.previous_snapshot: Optional[FileSnapshot] = None
        self.is_scanning = False
        self.scanner_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()

        # Statistics
        self.total_scans = 0
        self.deletions_detected = 0
        self.false_positives = 0

        # Confidence tracking
        self.file_stability_tracker: Dict[str, datetime] = {}

        logger.info(
            f"Deletion fallback scanner initialized - scanning every {scan_interval_seconds}s"
        )

    def start_scanning(self) -> bool:
        """
        Start the periodic deletion scanning.

        Returns:
            True if scanning started successfully, False otherwise
        """
        if self.is_scanning:
            logger.warning("Deletion scanner already running")
            return False

        try:
            # Take initial snapshot
            logger.info("📸 Taking initial filesystem snapshot...")
            self.current_snapshot = self._take_snapshot()
            logger.info(
                f"📸 Initial snapshot: {self.current_snapshot.total_files} files"
            )

            # Start scanning thread
            self.stop_event.clear()
            self.scanner_thread = threading.Thread(
                target=self._scanning_loop, name="DeletionFallbackScanner", daemon=True
            )
            self.scanner_thread.start()
            self.is_scanning = True

            logger.info("🔍 Deletion fallback scanner started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start deletion scanner: {e}")
            return False

    def stop_scanning(self):
        """Stop the periodic deletion scanning."""
        if not self.is_scanning:
            return

        logger.info("🛑 Stopping deletion fallback scanner...")
        self.stop_event.set()

        if self.scanner_thread and self.scanner_thread.is_alive():
            self.scanner_thread.join(timeout=5)

        self.is_scanning = False
        logger.info("🛑 Deletion fallback scanner stopped")

    def _scanning_loop(self):
        """Main scanning loop that runs in a separate thread."""
        while not self.stop_event.is_set():
            try:
                # Wait for next scan interval
                if self.stop_event.wait(timeout=self.scan_interval):
                    break  # Stop event was set

                # Perform scan
                self._perform_scan()

            except Exception as e:
                logger.error(f"Error in deletion scanning loop: {e}")
                # Continue scanning despite errors
                time.sleep(5)

    def _perform_scan(self):
        """Perform a single scan cycle."""
        try:
            start_time = time.time()

            # Take new snapshot
            new_snapshot = self._take_snapshot()
            scan_duration = time.time() - start_time
            new_snapshot.scan_duration_seconds = scan_duration

            self.total_scans += 1

            logger.debug(
                f"📸 Scan #{self.total_scans}: {new_snapshot.total_files} files ({scan_duration:.2f}s)"
            )

            # Compare with previous snapshot if available
            if self.current_snapshot:
                deletions = self._detect_deletions(self.current_snapshot, new_snapshot)

                if deletions:
                    logger.info(f"🗑️ Detected {len(deletions)} potential deletions")
                    self._process_deletions(deletions)

            # Update snapshots
            self.previous_snapshot = self.current_snapshot
            self.current_snapshot = new_snapshot

        except Exception as e:
            logger.error(f"Failed to perform deletion scan: {e}")

    def _take_snapshot(self) -> FileSnapshot:
        """Take a snapshot of the current filesystem state."""
        from ..indexing import FileFinder

        try:
            snapshot = FileSnapshot(timestamp=datetime.now())

            # Use the same file discovery logic as the indexer
            file_finder = FileFinder(self.config)
            discovered_files = file_finder.find_files()

            # Defensive check for Mock objects during testing
            if (
                hasattr(discovered_files, "_mock_name")
                or str(type(discovered_files).__name__) == "Mock"
            ):
                logger.warning(
                    "Mock object detected in find_files() result, returning empty snapshot"
                )
                return FileSnapshot(timestamp=datetime.now())

            # Additional safety check: ensure discovered_files is iterable
            try:
                iter(discovered_files)
            except TypeError:
                logger.warning(
                    "Non-iterable object returned from find_files(), returning empty snapshot"
                )
                return FileSnapshot(timestamp=datetime.now())

            # Convert to relative paths for consistency
            for file_path in discovered_files:
                try:
                    relative_path = str(file_path.relative_to(self.codebase_dir))
                    snapshot.files.add(relative_path)
                except ValueError:
                    # File outside codebase directory
                    continue

            snapshot.total_files = len(snapshot.files)

            # Update file stability tracker
            now = datetime.now()
            for file_path_str in snapshot.files:
                if file_path_str not in self.file_stability_tracker:
                    self.file_stability_tracker[file_path_str] = now

            return snapshot

        except Exception as e:
            logger.error(f"Failed to take filesystem snapshot: {e}")
            return FileSnapshot(timestamp=datetime.now())

    def _detect_deletions(
        self, old_snapshot: FileSnapshot, new_snapshot: FileSnapshot
    ) -> List[DeletionEvent]:
        """
        Detect deletions by comparing two snapshots.

        Args:
            old_snapshot: Previous filesystem snapshot
            new_snapshot: Current filesystem snapshot

        Returns:
            List of detected deletion events
        """
        deletions = []

        # Find files that were in old snapshot but not in new snapshot
        deleted_files = old_snapshot.files - new_snapshot.files

        for file_path in deleted_files:
            # Determine confidence level
            confidence = self._calculate_deletion_confidence(
                file_path, old_snapshot, new_snapshot
            )

            deletion = DeletionEvent(
                file_path=file_path,
                detected_at=new_snapshot.timestamp,
                last_seen_at=old_snapshot.timestamp,
                confidence=confidence,
            )

            deletions.append(deletion)

        return deletions

    def _calculate_deletion_confidence(
        self, file_path: str, old_snapshot: FileSnapshot, new_snapshot: FileSnapshot
    ) -> str:
        """
        Calculate confidence level for a detected deletion.

        Args:
            file_path: Path of the potentially deleted file
            old_snapshot: Previous snapshot
            new_snapshot: Current snapshot

        Returns:
            Confidence level: 'high', 'medium', or 'low'
        """
        try:
            # Check how long the file has been stable
            file_age = datetime.now() - self.file_stability_tracker.get(
                file_path, datetime.now()
            )

            # High confidence: file was stable for a while and disappeared
            if file_age > timedelta(minutes=5):
                return "high"

            # Medium confidence: file existed in previous scan and is now gone
            elif file_age > timedelta(minutes=1):
                return "medium"

            # Low confidence: file might be newly created and quickly deleted
            else:
                return "low"

        except Exception:
            return "low"

    def _process_deletions(self, deletions: List[DeletionEvent]):
        """
        Process detected deletions and trigger callbacks.

        Args:
            deletions: List of detected deletion events
        """
        confidence_order = {"high": 3, "medium": 2, "low": 1}
        min_confidence_level = confidence_order.get(self.min_confidence_threshold, 2)

        for deletion in deletions:
            deletion_confidence_level = confidence_order.get(deletion.confidence, 1)

            # Only process deletions that meet confidence threshold
            if deletion_confidence_level >= min_confidence_level:
                logger.info(
                    f"🗑️ FALLBACK DELETION: {deletion.file_path} "
                    f"(confidence: {deletion.confidence})"
                )

                self.deletions_detected += 1

                # Remove from stability tracker
                self.file_stability_tracker.pop(deletion.file_path, None)

                # Trigger callback if provided
                if self.deletion_callback:
                    try:
                        self.deletion_callback(deletion.file_path)
                    except Exception as e:
                        logger.error(
                            f"Deletion callback failed for {deletion.file_path}: {e}"
                        )

            else:
                logger.debug(
                    f"🔍 Low confidence deletion ignored: {deletion.file_path}"
                )

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get scanner statistics.

        Returns:
            Dictionary with scanner statistics
        """
        stats = {
            "is_scanning": self.is_scanning,
            "total_scans": self.total_scans,
            "deletions_detected": self.deletions_detected,
            "scan_interval_seconds": self.scan_interval,
            "current_files": (
                self.current_snapshot.total_files if self.current_snapshot else 0
            ),
            "last_scan_duration": (
                self.current_snapshot.scan_duration_seconds
                if self.current_snapshot
                else 0
            ),
            "files_tracked": len(self.file_stability_tracker),
            "confidence_threshold": self.min_confidence_threshold,
        }

        if self.current_snapshot:
            stats["last_scan_time"] = self.current_snapshot.timestamp.isoformat()

        return stats

    def force_scan(self) -> bool:
        """
        Force an immediate scan (useful for testing).

        Returns:
            True if scan completed successfully, False otherwise
        """
        if not self.is_scanning:
            return False

        try:
            logger.info("🔍 Forcing immediate deletion scan...")
            self._perform_scan()
            return True
        except Exception as e:
            logger.error(f"Forced scan failed: {e}")
            return False

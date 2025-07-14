"""
Git-aware watch handler that integrates file system monitoring with git branch awareness.

Provides seamless git-aware file monitoring that behaves identically to the index command
but with continuous watching capabilities.
"""

import logging
import time
import threading
from pathlib import Path
from typing import Set, Dict, Any, Optional
from watchdog.events import FileSystemEventHandler

from .watch_metadata import WatchMetadata, GitStateMonitor
from .smart_indexer import SmartIndexer
from .git_topology_service import GitTopologyService
from .deletion_fallback_scanner import DeletionFallbackScanner

logger = logging.getLogger(__name__)


class GitAwareWatchHandler(FileSystemEventHandler):
    """Git-aware file system event handler for watch operations."""

    def __init__(
        self,
        config,
        smart_indexer: SmartIndexer,
        git_topology_service: GitTopologyService,
        watch_metadata: WatchMetadata,
        debounce_seconds: float = 2.0,
        enable_deletion_fallback: bool = True,
    ):
        """Initialize git-aware watch handler.

        Args:
            config: Application configuration
            smart_indexer: SmartIndexer instance for git-aware processing
            git_topology_service: Git topology service for branch monitoring
            watch_metadata: Persistent metadata manager
            debounce_seconds: Time to wait before processing accumulated changes
            enable_deletion_fallback: Enable periodic deletion scanning fallback
        """
        super().__init__()
        self.config = config
        self.smart_indexer = smart_indexer
        self.git_topology_service = git_topology_service
        self.watch_metadata = watch_metadata
        self.debounce_seconds = debounce_seconds

        # Thread-safe change tracking
        self.pending_changes: Set[Path] = set()
        self.change_lock = threading.Lock()

        # Git state monitoring
        self.git_monitor = GitStateMonitor(git_topology_service)
        self.git_monitor.register_branch_change_callback(self._handle_branch_change)

        # Processing state
        self.processing_in_progress = False
        self.processing_thread: Optional[threading.Thread] = None

        # Statistics
        self.files_processed_count = 0
        self.indexing_cycles_count = 0

        # Deletion fallback scanner
        self.deletion_fallback: Optional[DeletionFallbackScanner] = None
        if enable_deletion_fallback:
            self.deletion_fallback = DeletionFallbackScanner(
                config=config,
                codebase_dir=config.codebase_dir,
                scan_interval_seconds=15,  # Scan every 15 seconds for faster deletion detection
                deletion_callback=self._handle_fallback_deletion,
                min_confidence_threshold="medium",
            )

    def start_watching(self):
        """Start the git-aware watch process."""
        logger.info("Starting git-aware watch handler")

        # Start git monitoring
        if self.git_monitor.start_monitoring():
            logger.info(
                f"Git monitoring started for branch: {self.git_monitor.current_branch}"
            )
        else:
            logger.warning("Git not available - proceeding with file-only monitoring")

        # Start change processing thread
        self.processing_thread = threading.Thread(
            target=self._process_changes_loop, daemon=True
        )
        if self.processing_thread:
            self.processing_thread.start()

        # Start deletion fallback scanner
        if self.deletion_fallback:
            if self.deletion_fallback.start_scanning():
                logger.info("Deletion fallback scanner started (60s intervals)")
            else:
                logger.warning("Failed to start deletion fallback scanner")

        logger.info("Git-aware watch handler started successfully")

    def stop_watching(self):
        """Stop the git-aware watch process."""
        logger.info("Stopping git-aware watch handler")

        # Stop git monitoring
        self.git_monitor.stop_monitoring()

        # Stop deletion fallback scanner
        if self.deletion_fallback:
            self.deletion_fallback.stop_scanning()

        # Process any remaining changes
        self._process_pending_changes(final_cleanup=True)

        logger.info("Git-aware watch handler stopped")

    def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        print(f"🔧 MODIFIED: {file_path}")  # Simple debug
        self._add_pending_change(file_path, "modified")

    def on_deleted(self, event):
        """Handle file deletion events."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        print(f"🗑️  WATCH MODE: File deletion detected: {file_path}")
        self._add_pending_change(file_path, "deleted")

    def on_created(self, event):
        """Handle file creation events."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        print(f"✨ CREATED: {file_path}")  # Simple debug
        self._add_pending_change(file_path, "created")

    def on_moved(self, event):
        """Handle file move events."""
        if event.is_directory:
            return

        # Treat move as delete + create
        old_path = Path(event.src_path)
        new_path = Path(event.dest_path)

        self._add_pending_change(old_path, "deleted")
        self._add_pending_change(new_path, "created")

    def _add_pending_change(self, file_path: Path, change_type: str):
        """Add a file change to pending queue if it should be indexed."""
        try:
            # For deletion events, always include the file because we can't check
            # file properties on non-existent files
            if change_type != "deleted":
                # Check if file should be included in indexing
                if not self._should_include_file(file_path):
                    print(f"🔍 File excluded from indexing: {file_path}")
                    return
            else:
                # For deleted files, check if the extension would have been included
                if not self._should_include_deleted_file(file_path):
                    print(f"🔍 Deleted file excluded from indexing: {file_path}")
                    return

            with self.change_lock:
                self.pending_changes.add(file_path)
                print(f"📂 Added pending change: {change_type} {file_path}")
                logger.debug(f"Added pending change: {change_type} {file_path}")

        except Exception as e:
            print(f"❌ Failed to add pending change for {file_path}: {e}")
            logger.warning(f"Failed to add pending change for {file_path}: {e}")

    def _should_include_file(self, file_path: Path) -> bool:
        """Check if file should be included in indexing."""
        try:
            # Use the same logic as regular indexing
            from ..indexing import FileFinder

            file_finder = FileFinder(self.config)
            return file_finder._should_include_file(file_path)
        except Exception as e:
            logger.warning(f"Failed to check if file should be included: {e}")
            return False

    def _should_include_deleted_file(self, file_path: Path) -> bool:
        """Check if a deleted file would have been included in indexing."""
        try:
            # For deleted files, just check the file extension
            # This is a simplified check since we can't access file contents or size
            extension = file_path.suffix.lstrip(".")
            return extension in self.config.file_extensions
        except Exception as e:
            logger.warning(f"Failed to check if deleted file should be included: {e}")
            return False

    def _process_changes_loop(self):
        """Main loop for processing file changes with debouncing."""
        while True:
            try:
                time.sleep(self.debounce_seconds)

                # Check for git state changes before processing files
                git_change = self.git_monitor.check_for_changes()
                if git_change:
                    # Branch change detected - handle it and skip this cycle
                    continue

                # Process pending file changes
                self._process_pending_changes()

            except Exception as e:
                logger.error(f"Error in change processing loop: {e}")
                time.sleep(5)  # Wait before retrying

    def _process_pending_changes(self, final_cleanup: bool = False):
        """Process all pending file changes using git-aware indexing."""
        with self.change_lock:
            if not self.pending_changes and not final_cleanup:
                return

            changes_to_process = self.pending_changes.copy()
            self.pending_changes.clear()

        if not changes_to_process and not final_cleanup:
            return

        if self.processing_in_progress:
            # Re-add changes back to queue if already processing
            with self.change_lock:
                self.pending_changes.update(changes_to_process)
            return

        try:
            self.processing_in_progress = True
            self.watch_metadata.mark_processing_start(
                [str(p) for p in changes_to_process]
            )

            if changes_to_process:
                print(
                    f"🔄 Processing {len(changes_to_process)} file changes using git-aware indexing"
                )
                logger.info(
                    f"Processing {len(changes_to_process)} file changes using git-aware indexing"
                )

                # Convert paths to relative paths for smart indexer
                relative_paths = []
                for file_path in changes_to_process:
                    try:
                        relative_path = str(
                            file_path.relative_to(self.config.codebase_dir)
                        )
                        relative_paths.append(relative_path)
                    except ValueError:
                        # File outside codebase directory
                        continue

                if relative_paths:
                    # Use SmartIndexer for git-aware processing (same as index command)
                    stats = self.smart_indexer.process_files_incrementally(
                        relative_paths,
                        force_reprocess=False,  # Use normal timestamp-based change detection
                        quiet=False,  # Show processing output for debugging
                        watch_mode=True,  # Enable verified deletion for reliability
                    )

                    self.files_processed_count += stats.files_processed
                    self.indexing_cycles_count += 1

                    # Print processing status to console for visibility
                    print(
                        f"📝 Processed {stats.files_processed} files: {', '.join(relative_paths)}"
                    )
                    logger.info(
                        f"Processed {stats.files_processed} files in git-aware mode"
                    )

            # Update metadata after successful processing
            self.watch_metadata.update_after_sync_cycle(
                files_processed=len(changes_to_process)
            )

        except Exception as e:
            logger.error(f"Failed to process file changes: {e}")
            self.watch_metadata.mark_processing_interrupted(str(e))

            # Re-add failed changes back to queue for retry
            with self.change_lock:
                self.pending_changes.update(changes_to_process)

        finally:
            self.processing_in_progress = False

    def _handle_fallback_deletion(self, file_path: str):
        """Handle deletion detected by fallback scanner."""
        try:
            logger.info(f"🔧 FALLBACK DELETION: Processing {file_path}")

            # Convert to Path object for consistency
            path_obj = Path(file_path)
            if not path_obj.is_absolute():
                path_obj = self.config.codebase_dir / file_path

            # Add to pending changes as if it was detected by filesystem events
            self._add_pending_change(path_obj, "deleted")

            logger.info(f"🔧 FALLBACK DELETION: Added {file_path} to pending changes")

        except Exception as e:
            logger.error(f"Failed to handle fallback deletion for {file_path}: {e}")

    def _handle_branch_change(self, change_event: Dict[str, Any]):
        """Handle git branch change events."""
        old_branch = change_event["old_branch"]
        new_branch = change_event["new_branch"]

        logger.info(f"Git branch change detected: {old_branch} → {new_branch}")

        try:
            # Stop current processing
            self.processing_in_progress = False

            # Wait for any ongoing processing to complete
            time.sleep(0.5)

            # Update watch metadata with new git state
            self.watch_metadata.update_git_state(
                new_branch or "unknown", change_event["new_commit"] or "unknown"
            )

            # Use git topology analysis for branch transition (same as index command)
            if old_branch and new_branch:
                branch_analysis = self.git_topology_service.analyze_branch_change(
                    old_branch, new_branch
                )

                # Use BranchAwareIndexer for proper branch transition
                collection_name = (
                    self.smart_indexer.qdrant_client.resolve_collection_name(
                        self.config, self.smart_indexer.embedding_provider
                    )
                )

                branch_result = (
                    self.smart_indexer.branch_aware_indexer.index_branch_changes(
                        old_branch=old_branch,
                        new_branch=new_branch,
                        changed_files=branch_analysis.files_to_reindex,
                        unchanged_files=branch_analysis.files_to_update_metadata,
                        collection_name=collection_name,
                    )
                )

                logger.info(
                    f"Branch transition complete: {branch_result.content_points_created} content points created, {branch_result.content_points_reused} content points reused"
                )

            # Clear pending changes as they might be from the old branch context
            with self.change_lock:
                self.pending_changes.clear()

            # Save updated metadata
            metadata_path = (
                self.config.codebase_dir / ".code-indexer" / "watch_metadata.json"
            )
            self.watch_metadata.save_to_disk(metadata_path)

        except Exception as e:
            logger.error(f"Failed to handle branch change: {e}")
            self.watch_metadata.mark_processing_interrupted(f"Branch change error: {e}")

    def get_statistics(self) -> Dict[str, Any]:
        """Get watch session statistics."""
        base_stats = self.watch_metadata.get_statistics()

        # Add handler-specific statistics
        base_stats.update(
            {
                "handler_files_processed": self.files_processed_count,
                "handler_indexing_cycles": self.indexing_cycles_count,
                "pending_changes": len(self.pending_changes),
                "processing_in_progress": self.processing_in_progress,
                "git_monitoring_active": self.git_monitor._monitoring,
                "current_git_branch": self.git_monitor.current_branch,
            }
        )

        # Add deletion fallback scanner statistics
        if self.deletion_fallback:
            fallback_stats = self.deletion_fallback.get_statistics()
            base_stats["deletion_fallback"] = fallback_stats

        return base_stats

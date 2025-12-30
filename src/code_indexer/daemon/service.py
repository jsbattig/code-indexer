"""CIDX Daemon Service - RPyC-based daemon for in-memory index caching.

Provides 16 exposed methods for semantic search, FTS, temporal queries, watch mode, and daemon management.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from rpyc import Service

from .cache import CacheEntry, TTLEvictionThread
from .watch_manager import DaemonWatchManager

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class CIDXDaemonService(Service):
    """RPyC daemon service for in-memory index caching.

    Provides 16 exposed methods organized into categories:
    - Query Operations (4): query, query_fts, query_hybrid, query_temporal
    - Indexing (3): index_blocking, index, get_index_progress
    - Watch Mode (3): watch_start, watch_stop, watch_status
    - Storage Operations (3): clean, clean_data, status
    - Daemon Management (4): get_status, clear_cache, shutdown, ping

    Thread Safety:
        - cache_lock: Protects cache entry loading/replacement
        - CacheEntry.rw_lock: ReaderWriterLock for concurrent reads and exclusive writes
    """

    def __init__(self):
        """Initialize daemon service with cache and eviction thread."""
        super().__init__()

        # Initialize exception logger EARLY for daemon mode
        from ..utils.exception_logger import ExceptionLogger

        exception_logger = ExceptionLogger.initialize(
            project_root=Path.cwd(), mode="daemon"
        )
        exception_logger.install_thread_exception_hook()
        logger.info("ExceptionLogger initialized for daemon mode")

        # Cache state
        self.cache_entry: Optional[CacheEntry] = None
        # FIX Race Condition #1: Use RLock (reentrant lock) to allow nested locking
        # This allows _ensure_cache_loaded to be called both standalone and within lock
        self.cache_lock: threading.RLock = threading.RLock()

        # Watch mode state - managed by DaemonWatchManager
        self.watch_manager = DaemonWatchManager()
        # Keep legacy fields for compatibility (will be removed later)
        self.watch_handler: Optional[Any] = None
        self.watch_thread: Optional[threading.Thread] = None
        self.watch_project_path: Optional[str] = None

        # Indexing state (background thread + progress tracking)
        self.indexing_thread: Optional[threading.Thread] = None
        self.indexing_project_path: Optional[str] = None
        self.indexing_lock_internal: threading.Lock = threading.Lock()

        # Indexing progress state (for polling)
        self.current_files_processed: int = 0
        self.total_files: int = 0
        self.indexing_error: Optional[str] = None
        self.indexing_stats: Optional[Dict[str, Any]] = None

        # Configuration (TODO: Load from config file)
        self.config = type("Config", (), {"auto_shutdown_on_idle": False})()

        # Start TTL eviction thread
        self.eviction_thread = TTLEvictionThread(self, check_interval=60)
        self.eviction_thread.start()

        logger.info("CIDXDaemonService initialized")

    # =============================================================================
    # Query Operations (3 methods)
    # =============================================================================

    def exposed_query(
        self, project_path: str, query: str, limit: int = 10, **kwargs
    ) -> Dict[str, Any]:
        """Execute semantic search with caching and timing information.

        Args:
            project_path: Path to project root
            query: Search query
            limit: Maximum number of results
            **kwargs: Additional search parameters

        Returns:
            Dictionary with 'results' and 'timing' keys
        """
        logger.debug(f"exposed_query: project={project_path}, query={query[:50]}...")

        # FIX Race Condition #1: Hold cache_lock during entire query execution
        # This prevents cache invalidation from occurring mid-query
        with self.cache_lock:
            # Ensure cache is loaded
            self._ensure_cache_loaded(project_path)

            # Update access tracking
            if self.cache_entry:
                self.cache_entry.update_access()

            # Execute semantic search (protected by cache_lock)
            results, timing_info = self._execute_semantic_search(
                project_path, query, limit, **kwargs
            )

            # Apply staleness detection to results (like standalone mode)
            if results:
                try:
                    from code_indexer.remote.staleness_detector import StalenessDetector
                    from code_indexer.api_clients.remote_query_client import (
                        QueryResultItem,
                    )
                    from datetime import datetime

                    # Convert results to QueryResultItem format
                    query_result_items = []
                    for result in results:
                        payload = result.get("payload", {})

                        # Extract timestamps
                        file_last_modified = payload.get("file_last_modified")
                        indexed_at = payload.get("indexed_at")

                        # Convert indexed_at to timestamp if it's ISO format
                        indexed_timestamp = None
                        if indexed_at:
                            try:
                                if isinstance(indexed_at, str):
                                    dt = datetime.fromisoformat(indexed_at.rstrip("Z"))
                                    indexed_timestamp = dt.timestamp()
                                else:
                                    indexed_timestamp = indexed_at
                            except (ValueError, AttributeError):
                                indexed_timestamp = indexed_at

                        query_item = QueryResultItem(
                            similarity_score=result.get("score", 0.0),
                            file_path=payload.get("path", "unknown"),
                            line_number=payload.get("line_start", 1),
                            code_snippet=payload.get("content", ""),
                            repository_alias=Path(project_path).name,
                            file_last_modified=file_last_modified,
                            indexed_timestamp=indexed_timestamp,
                        )
                        query_result_items.append(query_item)

                    # Apply staleness detection
                    detector = StalenessDetector()
                    enhanced_items = detector.apply_staleness_detection(
                        query_result_items, Path(project_path), mode="local"
                    )

                    # Create staleness lookup map by file path
                    # CRITICAL: apply_staleness_detection() sorts results, so we cannot
                    # assign staleness metadata by index position. We must match by file path.
                    staleness_map = {
                        enhanced.file_path: {
                            "is_stale": enhanced.is_stale,
                            "staleness_indicator": enhanced.staleness_indicator,
                            "staleness_delta_seconds": enhanced.staleness_delta_seconds,
                        }
                        for enhanced in enhanced_items
                    }

                    # Add staleness metadata to results by matching file path
                    for result in results:
                        file_path = result.get("payload", {}).get("path")
                        if file_path and file_path in staleness_map:
                            result["staleness"] = staleness_map[file_path]

                except Exception as e:
                    # Graceful fallback - log but continue with results without staleness
                    logger.debug(f"Staleness detection failed in daemon mode: {e}")
                    # Results returned without staleness metadata

        # Convert to plain dict for RPyC serialization (avoid netref issues)
        return dict(
            results=list(results) if results else [],
            timing=dict(timing_info) if timing_info else {},
        )

    def exposed_query_fts(
        self, project_path: str, query: str, **kwargs
    ) -> List[Dict[str, Any]]:
        """Execute FTS search with caching.

        Args:
            project_path: Path to project root
            query: Search query
            **kwargs: Additional search parameters (fuzzy, case_sensitive, etc.)

        Returns:
            List of FTS search results with snippets
        """
        logger.debug(
            f"exposed_query_fts: project={project_path}, query={query[:50]}..."
        )

        # FIX Race Condition #1: Hold cache_lock during entire query execution
        # This prevents cache invalidation from occurring mid-query
        with self.cache_lock:
            # Ensure cache is loaded
            self._ensure_cache_loaded(project_path)

            # Update access tracking
            if self.cache_entry:
                self.cache_entry.update_access()

            # Execute FTS search (protected by cache_lock)
            results = self._execute_fts_search(project_path, query, **kwargs)

        return results

    def exposed_query_hybrid(
        self, project_path: str, query: str, **kwargs
    ) -> Dict[str, Any]:
        """Execute parallel semantic + FTS search.

        Args:
            project_path: Path to project root
            query: Search query
            **kwargs: Additional search parameters

        Returns:
            Dict with 'semantic' and 'fts' result lists
        """
        logger.debug(
            f"exposed_query_hybrid: project={project_path}, query={query[:50]}..."
        )

        # Execute both searches (they share cache loading internally)
        semantic_results = self.exposed_query(project_path, query, **kwargs)
        fts_results = self.exposed_query_fts(project_path, query, **kwargs)

        return {
            "semantic": semantic_results,
            "fts": fts_results,
        }

    def exposed_query_temporal(
        self,
        project_path: str,
        query: str,
        time_range: str,
        limit: int = 10,
        languages: Optional[List[str]] = None,
        exclude_languages: Optional[List[str]] = None,
        path_filter: Optional[List[str]] = None,
        exclude_path: Optional[List[str]] = None,
        min_score: float = 0.0,
        accuracy: str = "balanced",
        chunk_type: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query temporal collection via daemon with mmap cache.

        Args:
            project_path: Path to project root
            query: Semantic search query text
            time_range: Time range filter (e.g., "2024-01-01..2024-12-31", "last-30-days")
            limit: Maximum number of results
            languages: Language filters (include) - list of language names
            exclude_languages: Language filters (exclude) - list of language names
            path_filter: Path pattern filters (include) - list of path patterns
            exclude_path: Path pattern filters (exclude) - list of path patterns
            min_score: Minimum similarity score
            accuracy: Accuracy mode (fast/balanced/high)
            chunk_type: Filter by chunk type ("commit_message" or "commit_diff")
            correlation_id: Correlation ID for progress tracking

        Returns:
            Dict with results, query metadata, and performance stats
        """
        logger.debug(
            f"exposed_query_temporal: project={project_path}, "
            f"query={query[:50]}..., time_range={time_range}"
        )

        project_root = Path(project_path)

        with self.cache_lock:
            # Ensure cache loaded for project
            if (
                self.cache_entry is None
                or self.cache_entry.project_path != project_root
            ):
                self._ensure_cache_loaded(project_path)

            # Load temporal cache if not loaded
            temporal_collection_path = (
                project_root / ".code-indexer/index/code-indexer-temporal"
            )

            if not temporal_collection_path.exists():
                logger.warning(f"Temporal index not found: {temporal_collection_path}")
                return {
                    "error": "Temporal index not found. Run 'cidx index --index-commits' first.",
                    "results": [],
                }

            if self.cache_entry.temporal_hnsw_index is None:
                logger.info("Loading temporal HNSW index into daemon cache")
                self.cache_entry.load_temporal_indexes(temporal_collection_path)

            # Check if cache stale (rebuild detected)
            if self.cache_entry.is_temporal_stale_after_rebuild(
                temporal_collection_path
            ):
                logger.info("Temporal cache stale after rebuild, reloading")
                self.cache_entry.invalidate_temporal()
                self.cache_entry.load_temporal_indexes(temporal_collection_path)

            # Initialize TemporalSearchService with cached index
            from code_indexer.services.temporal.temporal_search_service import (
                TemporalSearchService,
            )
            from code_indexer.services.temporal.temporal_indexer import TemporalIndexer
            from code_indexer.config import ConfigManager
            from code_indexer.backends.backend_factory import BackendFactory
            from code_indexer.services.embedding_factory import EmbeddingProviderFactory

            # Get config and services (reuse from cache if available)
            if not hasattr(self, "config_manager") or self.config_manager is None:
                self.config_manager = ConfigManager.create_with_backtrack(project_root)

            if not hasattr(self, "vector_store") or self.vector_store is None:
                config = self.config_manager.get_config()
                backend = BackendFactory.create(config, project_root)
                self.vector_store = backend.get_vector_store_client()

            if (
                not hasattr(self, "embedding_provider")
                or self.embedding_provider is None
            ):
                config = self.config_manager.get_config()
                self.embedding_provider = EmbeddingProviderFactory.create(config=config)

            temporal_search_service = TemporalSearchService(
                config_manager=self.config_manager,
                project_root=project_root,
                vector_store_client=self.vector_store,
                embedding_provider=self.embedding_provider,
                collection_name=TemporalIndexer.TEMPORAL_COLLECTION_NAME,
            )

            # Convert time_range string to tuple (same logic as cli.py:4819-4840)
            if time_range == "all":
                time_range_tuple = ("1970-01-01", "2100-12-31")
            elif ".." in time_range:
                # Split date range (e.g., "2024-01-01..2024-12-31")
                parts = time_range.split("..")
                if len(parts) != 2:
                    return {
                        "error": f"Invalid time range format: {time_range}. Use YYYY-MM-DD..YYYY-MM-DD",
                        "results": [],
                    }
                time_range_tuple = (parts[0].strip(), parts[1].strip())

                # Validate date format using temporal_search_service
                try:
                    temporal_search_service._validate_date_range(time_range)
                except ValueError as e:
                    return {
                        "error": f"Invalid date format: {e}",
                        "results": [],
                    }
            elif time_range.startswith("last-"):
                # Handle relative date ranges (e.g., "last-7-days", "last-30-days")
                # Convert to absolute date range
                from datetime import datetime, timedelta
                import re

                match = re.match(r"last-(\d+)-days?", time_range)
                if not match:
                    return {
                        "error": f"Invalid time range format: {time_range}. Use 'last-N-days' (e.g., 'last-7-days')",
                        "results": [],
                    }

                days = int(match.group(1))
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=days)).strftime(
                    "%Y-%m-%d"
                )
                time_range_tuple = (start_date, end_date)
            else:
                return {
                    "error": f"Invalid time range format: {time_range}. Use 'all', 'last-N-days', or YYYY-MM-DD..YYYY-MM-DD",
                    "results": [],
                }

            # Query using cached temporal index
            results = temporal_search_service.query_temporal(
                query=query,
                time_range=time_range_tuple,
                limit=limit,
                language=languages,  # Parameter name is 'language' not 'languages'
                exclude_language=exclude_languages,  # Parameter name is 'exclude_language' not 'exclude_languages'
                path_filter=path_filter,
                exclude_path=exclude_path,
                min_score=min_score,
                chunk_type=chunk_type,
            )

            # Update cache access tracking
            self.cache_entry.update_access()

            # Format results for daemon response
            return self._format_temporal_results(results)

    def _format_temporal_results(self, results: Any) -> Dict[str, Any]:
        """Format temporal search results for RPC response."""
        return {
            "results": [
                {
                    "file_path": r.file_path,
                    "chunk_index": r.chunk_index,
                    "content": r.content,
                    "score": r.score,
                    "metadata": r.metadata,
                    "temporal_context": getattr(r, "temporal_context", {}),
                }
                for r in results.results
            ],
            "query": results.query,
            "filter_type": results.filter_type,
            "filter_value": results.filter_value,
            "total_found": results.total_found,
            "performance": results.performance or {},
            "warning": results.warning,
        }

    # =============================================================================
    # Indexing (3 methods)
    # =============================================================================

    def exposed_index_blocking(
        self, project_path: str, callback: Optional[Any] = None, **kwargs
    ) -> Dict[str, Any]:
        """Perform BLOCKING indexing with real-time progress callbacks.

        This method executes indexing synchronously in the main daemon thread,
        streaming progress updates to the client via RPyC callbacks. The RPyC
        connection remains open during indexing, allowing real-time progress
        streaming.

        CRITICAL UX FIX: This provides UX parity with standalone mode by
        displaying real-time progress bar updates in the client terminal.

        Args:
            project_path: Path to project root
            callback: Optional progress callback for real-time updates
            **kwargs: Additional indexing parameters (force_full, enable_fts, batch_size)

        Returns:
            Dict with indexing stats and status
        """
        logger.info(f"exposed_index_blocking: project={project_path} [BLOCKING MODE]")
        logger.info(f"exposed_index_blocking: kwargs={kwargs}")

        try:
            # Invalidate cache BEFORE indexing
            with self.cache_lock:
                if self.cache_entry:
                    logger.info("Invalidating cache before indexing")
                    self.cache_entry = None

            # CRITICAL FIX for Bug #473: Check temporal indexing FIRST before ANY semantic initialization
            # This prevents wasting time on SmartIndexer setup and file discovery when only temporal is needed
            if kwargs.get("index_commits", False):
                # Temporal-only path: Skip ALL semantic indexing infrastructure
                logger.info(
                    "Temporal indexing requested - skipping semantic indexing setup"
                )

                from code_indexer.config import ConfigManager
                from code_indexer.services.temporal.temporal_indexer import (
                    TemporalIndexer,
                )
                from code_indexer.storage.filesystem_vector_store import (
                    FilesystemVectorStore,
                )

                # Only setup what's needed for temporal
                config_manager = ConfigManager.create_with_backtrack(Path(project_path))
                index_dir = Path(project_path) / ".code-indexer" / "index"
                vector_store = FilesystemVectorStore(
                    base_path=index_dir, project_root=Path(project_path)
                )

                # Handle --clear flag for temporal collection
                if kwargs.get("force_full", False):
                    vector_store.clear_collection("code-indexer-temporal")

                # Setup callback infrastructure for temporal progress
                import threading
                import json

                callback_counter = [0]
                callback_lock = threading.Lock()

                def temporal_callback(current, total, file_path, info="", **cb_kwargs):
                    """Progress callback for temporal indexing."""
                    with callback_lock:
                        callback_counter[0] += 1
                        correlation_id = callback_counter[0]

                    concurrent_files = cb_kwargs.get("concurrent_files", [])
                    concurrent_files_json = json.dumps(concurrent_files)

                    # Bug #475 fix: Preserve item_type from temporal indexer
                    filtered_kwargs = {
                        "concurrent_files_json": concurrent_files_json,
                        "correlation_id": correlation_id,
                        "item_type": cb_kwargs.get("item_type", "files"),
                    }

                    if callback:
                        callback(current, total, file_path, info, **filtered_kwargs)

                def reset_progress_timers():
                    """Reset progress timers by delegating to client callback."""
                    if callback and hasattr(callback, "reset_progress_timers"):
                        callback.reset_progress_timers()

                temporal_callback.reset_progress_timers = reset_progress_timers  # type: ignore[attr-defined]

                # Initialize temporal indexer
                temporal_indexer = TemporalIndexer(config_manager, vector_store)

                # Run temporal indexing with progress callback
                result = temporal_indexer.index_commits(
                    all_branches=kwargs.get("all_branches", False),
                    max_commits=kwargs.get("max_commits"),
                    since_date=kwargs.get("since_date"),
                    progress_callback=temporal_callback,
                )

                temporal_indexer.close()

                # Invalidate cache after temporal indexing completes
                with self.cache_lock:
                    if self.cache_entry:
                        logger.info(
                            "Invalidating cache after temporal indexing completed"
                        )
                        self.cache_entry = None

                # Return temporal indexing results
                return {
                    "status": "completed",
                    "stats": {
                        "total_commits": result.total_commits,
                        "files_processed": result.files_processed,
                        "approximate_vectors_created": result.approximate_vectors_created,
                        "skip_ratio": result.skip_ratio,
                        "branches_indexed": result.branches_indexed,
                        "commits_per_branch": result.commits_per_branch,
                        "failed_files": 0,
                        "duration_seconds": 0,  # Not tracked yet
                        "cancelled": False,
                    },
                }

            # Standard semantic indexing path - only executed if NOT temporal
            from code_indexer.services.smart_indexer import SmartIndexer
            from code_indexer.config import ConfigManager
            from code_indexer.backends.backend_factory import BackendFactory
            from code_indexer.services.embedding_factory import EmbeddingProviderFactory

            # Initialize configuration and backend
            config_manager = ConfigManager.create_with_backtrack(Path(project_path))
            config = config_manager.get_config()

            # Create embedding provider and vector store
            embedding_provider = EmbeddingProviderFactory.create(config=config)
            backend = BackendFactory.create(config, Path(project_path))
            vector_store_client = backend.get_vector_store_client()

            # Initialize SmartIndexer
            metadata_path = config_manager.config_path.parent / "metadata.json"
            indexer = SmartIndexer(
                config, embedding_provider, vector_store_client, metadata_path
            )

            # Test string transmission
            import threading

            callback_counter = [0]  # Correlation ID
            callback_lock = threading.Lock()

            def correlated_callback(current, total, file_path, info="", **cb_kwargs):
                """Serialize concurrent_files and remove slot_tracker for daemon transmission."""
                with callback_lock:
                    callback_counter[0] += 1
                    correlation_id = callback_counter[0]
                # FROZEN SLOTS FIX: Serialize concurrent_files as JSON to avoid RPyC list/dict issues
                import json

                concurrent_files = cb_kwargs.get("concurrent_files", [])
                # RPyC WORKAROUND: Serialize concurrent_files to JSON to avoid proxy caching issues
                # This ensures the client receives fresh data on every callback, not stale proxies
                concurrent_files_json = json.dumps(concurrent_files)

                # CRITICAL FIX: Filter out slot_tracker to prevent RPyC proxy leakage
                # Only pass JSON-serializable data to client callback
                filtered_kwargs = {
                    "concurrent_files_json": concurrent_files_json,
                    "correlation_id": correlation_id,
                }

                # Call actual client callback with filtered kwargs
                if callback:
                    callback(current, total, file_path, info, **filtered_kwargs)

            # BUG FIX: Add reset_progress_timers method to correlated_callback
            # This method is called by HighThroughputProcessor during phase transitions
            # (hash→indexing, indexing→branch isolation) to reset Rich Progress internal timers.
            # Without this, the clock freezes at the hash phase completion time.
            def reset_progress_timers():
                """Reset progress timers by delegating to client callback."""
                if callback and hasattr(callback, "reset_progress_timers"):
                    callback.reset_progress_timers()

            # Attach reset method to callback function (makes it accessible via hasattr check)
            correlated_callback.reset_progress_timers = reset_progress_timers  # type: ignore[attr-defined]

            # Standard workspace indexing mode (temporal check moved to top)
            stats = indexer.smart_index(
                force_full=kwargs.get("force_full", False),
                batch_size=kwargs.get("batch_size", 50),
                progress_callback=correlated_callback,  # With correlation IDs
                quiet=True,  # Suppress daemon-side output
                enable_fts=kwargs.get("enable_fts", False),
                reconcile_with_database=kwargs.get("reconcile_with_database", False),
                files_count_to_process=kwargs.get("files_count_to_process"),
                detect_deletions=kwargs.get("detect_deletions", False),
            )

            # Invalidate cache after indexing completes
            with self.cache_lock:
                if self.cache_entry:
                    logger.info("Invalidating cache after indexing completed")
                    self.cache_entry = None

            # Return stats dict (NOT a status dict, but actual stats)
            return {
                "status": "completed",
                "stats": {
                    "files_processed": stats.files_processed,
                    "chunks_created": stats.chunks_created,
                    "failed_files": stats.failed_files,
                    "duration_seconds": stats.duration,
                    "cancelled": getattr(stats, "cancelled", False),
                },
            }

        except Exception as e:
            logger.error(f"Blocking indexing failed: {e}")
            import traceback

            logger.error(traceback.format_exc())

            return {
                "status": "error",
                "message": str(e),
            }

    def exposed_index(
        self, project_path: str, callback: Optional[Any] = None, **kwargs
    ) -> Dict[str, Any]:
        """Start BACKGROUND indexing with progress polling (non-blocking).

        CRITICAL ARCHITECTURE FIX: This method now starts indexing in a
        background thread and returns immediately. The daemon remains
        responsive to handle queries and status checks during indexing.

        Client polls for progress using exposed_get_index_progress().

        Args:
            project_path: Path to project root
            callback: IGNORED (progress polling used instead)
            **kwargs: Additional indexing parameters (force_full, enable_fts, batch_size)

        Returns:
            Indexing start status with job ID for progress polling
        """
        logger.info(f"exposed_index: project={project_path} [BACKGROUND MODE]")

        # Check if indexing is already running (prevent concurrent indexing)
        with self.indexing_lock_internal:
            if self.indexing_thread and self.indexing_thread.is_alive():
                return {
                    "status": "already_running",
                    "message": "Indexing already in progress",
                    "project_path": self.indexing_project_path,
                }
            # Mark as running
            self.indexing_project_path = project_path

            # Reset progress state
            self.current_files_processed = 0
            self.total_files = 0
            self.indexing_error = None
            self.indexing_stats = None

            # Start background thread
            self.indexing_thread = threading.Thread(
                target=self._run_indexing_background,
                args=(project_path, kwargs),
                daemon=True,
            )
            self.indexing_thread.start()

        # Return immediately - client polls for progress
        return {
            "status": "started",
            "message": "Indexing started in background",
            "project_path": project_path,
        }

    def exposed_get_index_progress(self) -> Dict[str, Any]:
        """Get current indexing progress (for polling).

        Returns:
            Progress dictionary with running status, files processed, total files,
            completion stats, or error information
        """
        with self.indexing_lock_internal:
            is_running = (
                self.indexing_thread is not None and self.indexing_thread.is_alive()
            )

            if not is_running and self.indexing_stats:
                # Indexing completed
                return {
                    "running": False,
                    "status": "completed",
                    "stats": self.indexing_stats,
                }
            elif not is_running and self.indexing_error:
                # Indexing failed
                return {
                    "running": False,
                    "status": "error",
                    "message": self.indexing_error,
                }
            elif is_running:
                # Indexing in progress
                return {
                    "running": True,
                    "status": "indexing",
                    "files_processed": self.current_files_processed,
                    "total_files": self.total_files,
                }
            else:
                # No indexing job
                return {
                    "running": False,
                    "status": "idle",
                }

    def _run_indexing_background(
        self, project_path: str, kwargs: Dict[str, Any]
    ) -> None:
        """Run indexing in background thread with progress tracking.

        This method executes the actual indexing work and updates progress
        state for polling. Catches exceptions to prevent thread crashes.

        Args:
            project_path: Path to project root
            kwargs: Additional indexing parameters
        """
        try:
            logger.info("=== BACKGROUND INDEXING THREAD STARTED ===")
            logger.info(f"Project path: {project_path}")
            logger.info(f"Kwargs: {kwargs}")

            # Invalidate cache BEFORE indexing
            with self.cache_lock:
                if self.cache_entry:
                    logger.info("Invalidating cache before indexing")
                    self.cache_entry = None

            from code_indexer.services.smart_indexer import SmartIndexer
            from code_indexer.config import ConfigManager
            from code_indexer.backends.backend_factory import BackendFactory
            from code_indexer.services.embedding_factory import EmbeddingProviderFactory

            logger.info("Step 1: Importing modules complete")

            # Initialize configuration and backend
            logger.info("Step 2: Creating ConfigManager...")
            config_manager = ConfigManager.create_with_backtrack(Path(project_path))
            config = config_manager.get_config()
            logger.info(
                f"Step 2 Complete: Config loaded (codebase_dir={config.codebase_dir})"
            )

            # Create embedding provider and vector store
            logger.info("Step 3: Creating embedding provider...")
            embedding_provider = EmbeddingProviderFactory.create(config=config)
            logger.info(
                f"Step 3 Complete: Embedding provider created ({type(embedding_provider).__name__})"
            )

            logger.info("Step 4: Creating backend and vector store...")
            backend = BackendFactory.create(config, Path(project_path))
            vector_store_client = backend.get_vector_store_client()
            logger.info(
                f"Step 4 Complete: Backend created ({type(vector_store_client).__name__})"
            )

            # Initialize SmartIndexer with correct signature
            metadata_path = config_manager.config_path.parent / "metadata.json"
            logger.info(
                f"Step 5: Creating SmartIndexer (metadata_path={metadata_path})..."
            )
            indexer = SmartIndexer(
                config, embedding_provider, vector_store_client, metadata_path
            )
            logger.info("Step 5 Complete: SmartIndexer created")

            # Create progress callback wrapper that updates internal state for polling
            def progress_callback(
                current: int, total: int, file_path: Path, info: str = "", **kwargs
            ):
                """Update internal progress state for polling-based progress tracking."""
                # Update internal state for polling
                with self.indexing_lock_internal:
                    self.current_files_processed = current
                    self.total_files = total

            # Execute indexing using smart_index method
            logger.info("Step 6: Calling smart_index()...")
            logger.info(f"  force_full={kwargs.get('force_full', False)}")
            logger.info(f"  batch_size={kwargs.get('batch_size', 50)}")
            logger.info(f"  enable_fts={kwargs.get('enable_fts', False)}")

            stats = indexer.smart_index(
                force_full=kwargs.get("force_full", False),
                batch_size=kwargs.get("batch_size", 50),
                progress_callback=progress_callback,
                quiet=True,
                enable_fts=kwargs.get("enable_fts", False),
            )

            logger.info("Step 6 Complete: Indexing finished")
            logger.info(f"=== INDEXING STATS: {stats} ===")

            # Store completion stats
            with self.indexing_lock_internal:
                self.indexing_stats = {
                    "files_processed": stats.files_processed,
                    "chunks_created": stats.chunks_created,
                    "failed_files": stats.failed_files,
                    "duration_seconds": stats.duration,
                    "cancelled": getattr(stats, "cancelled", False),
                }

            # Invalidate cache after indexing completes so next query loads fresh data
            with self.cache_lock:
                if self.cache_entry:
                    logger.info("Invalidating cache after indexing completed")
                    self.cache_entry = None

            logger.info("=== BACKGROUND INDEXING THREAD COMPLETED SUCCESSFULLY ===")

        except Exception as e:
            logger.error("=== BACKGROUND INDEXING FAILED ===")
            logger.error(f"Error: {e}")
            import traceback

            logger.error(traceback.format_exc())

            # Store error message
            with self.indexing_lock_internal:
                self.indexing_error = str(e)

        finally:
            # Clear indexing state
            with self.indexing_lock_internal:
                self.indexing_thread = None
                self.indexing_project_path = None
            logger.info("=== BACKGROUND INDEXING THREAD EXITING ===")

    # =============================================================================
    # Watch Mode (3 methods)
    # =============================================================================

    def exposed_watch_start(
        self, project_path: str, callback: Optional[Any] = None, **kwargs
    ) -> Dict[str, Any]:
        """Start GitAwareWatchHandler in daemon using non-blocking background thread.

        This method delegates to DaemonWatchManager which starts watch mode
        in a background thread, allowing the RPC call to return immediately
        and the daemon to remain responsive to concurrent operations.

        Args:
            project_path: Path to project root
            callback: Optional event callback (unused in background mode)
            **kwargs: Additional watch parameters

        Returns:
            Watch start status (returns immediately, non-blocking)
        """
        logger.info(f"exposed_watch_start: project={project_path}")

        # Delegate to DaemonWatchManager for non-blocking operation
        # Config will be loaded by the manager
        result = self.watch_manager.start_watch(project_path, None, **kwargs)

        # Update legacy fields for compatibility
        if result["status"] == "success":
            # These will be updated after the thread starts
            self.watch_handler = self.watch_manager.watch_handler
            self.watch_thread = self.watch_manager.watch_thread
            self.watch_project_path = self.watch_manager.project_path

        return result

    def exposed_watch_stop(self, project_path: str) -> Dict[str, Any]:
        """Stop watch gracefully with statistics.

        Delegates to DaemonWatchManager which handles graceful shutdown
        of the watch thread and cleanup of resources.

        Args:
            project_path: Path to project root

        Returns:
            Watch stop status with statistics
        """
        logger.info(f"exposed_watch_stop: project={project_path}")

        # Delegate to DaemonWatchManager
        result = self.watch_manager.stop_watch()

        # Clear legacy fields for compatibility
        if result["status"] == "success":
            self.watch_handler = None
            self.watch_thread = None
            self.watch_project_path = None

        return result

    def exposed_watch_status(self) -> Dict[str, Any]:
        """Get current watch state.

        Delegates to DaemonWatchManager to get current watch status
        and statistics.

        Returns:
            Watch status with project path and statistics
        """
        # Get stats from DaemonWatchManager
        stats = self.watch_manager.get_stats()

        # Convert to legacy format for compatibility
        if stats["status"] == "running":
            return {
                "running": True,
                "project_path": stats["project_path"],
                "stats": stats,
            }
        else:
            return {
                "running": False,
                "project_path": None,
            }

    # =============================================================================
    # Storage Operations (3 methods)
    # =============================================================================

    def exposed_clean(self, project_path: str, **kwargs) -> Dict[str, Any]:
        """Clear vectors with cache invalidation.

        Args:
            project_path: Path to project root
            **kwargs: Additional clean parameters

        Returns:
            Clean status
        """
        logger.info(f"exposed_clean: project={project_path}")

        # Invalidate cache FIRST
        with self.cache_lock:
            if self.cache_entry:
                logger.info("Invalidating cache before clean")
                self.cache_entry = None

        try:
            from code_indexer.storage.filesystem_vector_store import (
                FilesystemVectorStore,
            )

            # Clear vectors using clear_collection method
            index_dir = Path(project_path) / ".code-indexer" / "index"
            vector_store = FilesystemVectorStore(
                base_path=index_dir, project_root=Path(project_path)
            )

            # Get collection name from kwargs or auto-resolve
            collection_name = kwargs.get("collection")
            if collection_name is None:
                collections = vector_store.list_collections()
                if len(collections) == 1:
                    collection_name = collections[0]
                elif len(collections) == 0:
                    return {"status": "success", "message": "No collections to clear"}
                else:
                    return {
                        "status": "error",
                        "message": "Multiple collections exist, specify collection parameter",
                    }

            # Clear collection
            remove_projection_matrix = kwargs.get("remove_projection_matrix", False)
            success = vector_store.clear_collection(
                collection_name, remove_projection_matrix
            )

            if success:
                return {
                    "status": "success",
                    "message": f"Collection '{collection_name}' cleared",
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to clear collection '{collection_name}'",
                }

        except Exception as e:
            logger.error(f"Clean failed: {e}")
            return {"status": "error", "message": str(e)}

    def exposed_clean_data(self, project_path: str, **kwargs) -> Dict[str, Any]:
        """Clear all data with cache invalidation (deletes collections).

        Args:
            project_path: Path to project root
            **kwargs: Additional clean parameters (collection for specific collection)

        Returns:
            Clean data status
        """
        logger.info(f"exposed_clean_data: project={project_path}")

        # Invalidate cache FIRST
        with self.cache_lock:
            if self.cache_entry:
                logger.info("Invalidating cache before clean_data")
                self.cache_entry = None

        try:
            from code_indexer.storage.filesystem_vector_store import (
                FilesystemVectorStore,
            )

            # Clear data by deleting collections
            index_dir = Path(project_path) / ".code-indexer" / "index"
            vector_store = FilesystemVectorStore(
                base_path=index_dir, project_root=Path(project_path)
            )

            # Get collection name from kwargs or delete all collections
            collection_name = kwargs.get("collection")
            if collection_name:
                # Delete specific collection
                success = vector_store.delete_collection(collection_name)
                if success:
                    return {
                        "status": "success",
                        "message": f"Collection '{collection_name}' deleted",
                    }
                else:
                    return {
                        "status": "error",
                        "message": f"Failed to delete collection '{collection_name}'",
                    }
            else:
                # Delete all collections
                collections = vector_store.list_collections()
                deleted_count = 0
                for coll in collections:
                    if vector_store.delete_collection(coll):
                        deleted_count += 1

                return {
                    "status": "success",
                    "message": f"Deleted {deleted_count} collection(s)",
                }

        except Exception as e:
            logger.error(f"Clean data failed: {e}")
            return {"status": "error", "message": str(e)}

    def exposed_status(self, project_path: str) -> Dict[str, Any]:
        """Combined daemon + storage status.

        Args:
            project_path: Path to project root

        Returns:
            Combined status dictionary
        """
        logger.debug(f"exposed_status: project={project_path}")

        try:
            # Get cache stats
            cache_stats = {}
            with self.cache_lock:
                if self.cache_entry:
                    cache_stats = self.cache_entry.get_stats()
                else:
                    cache_stats = {"cache_loaded": False}

            # Get storage stats
            from code_indexer.storage.filesystem_vector_store import (
                FilesystemVectorStore,
            )

            index_dir = Path(project_path) / ".code-indexer" / "index"
            vector_store = FilesystemVectorStore(
                base_path=index_dir, project_root=Path(project_path)
            )
            storage_stats = (
                vector_store.get_status() if hasattr(vector_store, "get_status") else {}
            )

            return {
                "cache": cache_stats,
                "storage": storage_stats,
            }

        except Exception as e:
            logger.error(f"Status failed: {e}")
            return {"error": str(e)}

    # =============================================================================
    # Daemon Management (4 methods)
    # =============================================================================

    def exposed_get_status(self) -> Dict[str, Any]:
        """Daemon cache and indexing status.

        Returns:
            Status dictionary with cache and indexing info
        """
        with self.cache_lock:
            cache_status = {}
            if self.cache_entry:
                cache_status = {
                    "cache_loaded": True,
                    **self.cache_entry.get_stats(),
                }
            else:
                cache_status = {"cache_loaded": False}

        # Check indexing status
        with self.indexing_lock_internal:
            indexing_status = {
                "indexing_running": self.indexing_thread is not None
                and self.indexing_thread.is_alive(),
                "indexing_project": (
                    self.indexing_project_path
                    if self.indexing_thread and self.indexing_thread.is_alive()
                    else None
                ),
            }

        # Get watch status from DaemonWatchManager
        watch_stats = self.watch_manager.get_stats()
        watch_status = {
            "watch_running": watch_stats["status"] == "running",
            "watch_project": watch_stats.get("project_path"),
            "watch_uptime_seconds": watch_stats.get("uptime_seconds", 0),
            "watch_files_processed": watch_stats.get("files_processed", 0),
        }

        return {
            **cache_status,
            **indexing_status,
            **watch_status,
        }

    def exposed_clear_cache(self) -> Dict[str, Any]:
        """Clear cache manually.

        Returns:
            Clear cache status
        """
        logger.info("exposed_clear_cache: clearing cache")

        with self.cache_lock:
            self.cache_entry = None

        return {"status": "success", "message": "Cache cleared"}

    def exposed_shutdown(self) -> Dict[str, Any]:
        """Graceful daemon shutdown.

        Stops watch, clears cache, stops eviction thread, exits process.

        Returns:
            Shutdown status
        """
        logger.info("exposed_shutdown: initiating graceful shutdown")

        try:
            # Stop watch if running (via DaemonWatchManager)
            if self.watch_manager.is_running():
                self.watch_manager.stop_watch()

            # Clear cache
            with self.cache_lock:
                self.cache_entry = None

            # Stop eviction thread
            self.eviction_thread.stop()

            logger.info("Shutdown complete")

            # Send SIGTERM to main process (RPyC runs in main thread)
            # This triggers signal handler which cleans up socket and exits
            import os
            import signal

            os.kill(os.getpid(), signal.SIGTERM)

            return {"status": "success", "message": "Shutdown initiated"}

        except Exception as e:
            logger.error(f"Shutdown failed: {e}")
            return {"status": "error", "message": str(e)}

    def exposed_ping(self) -> Dict[str, Any]:
        """Health check endpoint.

        Returns:
            Health status
        """
        return {"status": "ok"}

    # =============================================================================
    # Internal Methods
    # =============================================================================

    def _ensure_cache_loaded(self, project_path: str) -> None:
        """Load indexes into cache if not already loaded.

        AC11: Detects background rebuild via version tracking and invalidates cache.

        Args:
            project_path: Path to project root
        """
        project_path_obj = Path(project_path)

        with self.cache_lock:
            # AC11: Check for staleness after background rebuild
            if (
                self.cache_entry is not None
                and self.cache_entry.project_path == project_path_obj
            ):
                # Same project - check if rebuild occurred
                index_dir = project_path_obj / ".code-indexer" / "index"
                if index_dir.exists():
                    # Find collection directory (assume single collection)
                    collections = [d for d in index_dir.iterdir() if d.is_dir()]
                    if collections:
                        collection_path = collections[0]
                        if self.cache_entry.is_stale_after_rebuild(collection_path):
                            logger.info(
                                "Background rebuild detected, invalidating cache"
                            )
                            self.cache_entry.invalidate()
                            self.cache_entry = None

            # Check if we need to load or replace cache
            if (
                self.cache_entry is None
                or self.cache_entry.project_path != project_path_obj
            ):
                logger.info(f"Loading cache for {project_path}")

                # Create new cache entry
                self.cache_entry = CacheEntry(project_path_obj, ttl_minutes=10)

                # Load semantic indexes
                self._load_semantic_indexes(self.cache_entry)

                # Load FTS indexes
                self._load_fts_indexes(self.cache_entry)

    def _load_semantic_indexes(self, entry: CacheEntry) -> None:
        """Load REAL HNSW index using HNSWIndexManager.

        Args:
            entry: Cache entry to populate
        """
        try:
            from code_indexer.storage.hnsw_index_manager import HNSWIndexManager
            from code_indexer.storage.id_index_manager import IDIndexManager

            index_dir = entry.project_path / ".code-indexer" / "index"
            if not index_dir.exists():
                logger.warning(f"Index directory does not exist: {index_dir}")
                return

            # Get list of collections
            from code_indexer.storage.filesystem_vector_store import (
                FilesystemVectorStore,
            )

            vector_store = FilesystemVectorStore(
                base_path=index_dir, project_root=entry.project_path
            )
            collections = vector_store.list_collections()

            if not collections:
                logger.warning("No collections found in index")
                return

            # Load first collection (single collection per project)
            collection_name = collections[0]
            collection_path = index_dir / collection_name

            # Read collection metadata to get vector dimension
            metadata_file = collection_path / "collection_meta.json"
            if not metadata_file.exists():
                logger.warning(f"Collection metadata not found: {metadata_file}")
                return

            import json

            with open(metadata_file, "r") as f:
                metadata = json.load(f)

            vector_dim = metadata.get("vector_size", 1536)

            # Load HNSW index using HNSWIndexManager
            hnsw_manager = HNSWIndexManager(vector_dim=vector_dim, space="cosine")
            hnsw_index = hnsw_manager.load_index(collection_path, max_elements=100000)

            # Load ID index using IDIndexManager
            id_manager = IDIndexManager()
            id_index = id_manager.load_index(collection_path)

            # Set semantic indexes
            if hnsw_index and id_index:
                entry.set_semantic_indexes(hnsw_index, id_index)
                # Store collection metadata for search execution
                entry.collection_name = collection_name
                entry.vector_dim = vector_dim
                # AC11: Track loaded index version for rebuild detection
                entry.hnsw_index_version = entry._read_index_rebuild_uuid(
                    collection_path
                )
                logger.info(
                    f"Semantic indexes loaded successfully (collection: {collection_name}, vector_dim: {vector_dim}, version: {entry.hnsw_index_version})"
                )
            else:
                logger.warning("Failed to load semantic indexes")

        except ImportError as e:
            logger.warning(f"HNSW dependencies not available: {e}")
        except Exception as e:
            logger.error(f"Error loading semantic indexes: {e}")
            import traceback

            logger.error(traceback.format_exc())

    def _load_fts_indexes(self, entry: CacheEntry) -> None:
        """Load REAL Tantivy FTS index.

        Args:
            entry: Cache entry to populate
        """
        try:
            tantivy_dir = entry.project_path / ".code-indexer" / "tantivy_index"
            if not tantivy_dir.exists():
                logger.debug(f"Tantivy directory does not exist: {tantivy_dir}")
                entry.fts_available = False
                return

            # Lazy import tantivy
            try:
                import tantivy

                # Open REAL Tantivy index
                tantivy_index = tantivy.Index.open(str(tantivy_dir))
                tantivy_searcher = tantivy_index.searcher()

                # Set FTS indexes
                entry.set_fts_indexes(tantivy_index, tantivy_searcher)
                logger.info("FTS indexes loaded successfully")

            except ImportError:
                logger.warning("Tantivy not installed, FTS unavailable")
                entry.fts_available = False

        except Exception as e:
            logger.error(f"Error loading FTS indexes: {e}")
            entry.fts_available = False

    def _execute_semantic_search(
        self, project_path: str, query: str, limit: int = 10, **kwargs
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Execute REAL semantic search using cached indexes with timing.

        Args:
            project_path: Path to project root
            query: Search query
            limit: Maximum results
            **kwargs: Additional search parameters

        Returns:
            Tuple of (results list, timing info dict)
        """
        try:
            from code_indexer.config import ConfigManager
            from code_indexer.backends.backend_factory import BackendFactory
            from code_indexer.services.embedding_factory import EmbeddingProviderFactory

            # Initialize configuration and services
            config_manager = ConfigManager.create_with_backtrack(Path(project_path))
            config = config_manager.get_config()

            # Create embedding provider and vector store
            embedding_provider = EmbeddingProviderFactory.create(config=config)
            backend = BackendFactory.create(config, Path(project_path))
            vector_store = backend.get_vector_store_client()

            # Get collection name
            collection_name = vector_store.resolve_collection_name(
                config, embedding_provider
            )

            # Build filter conditions from raw parameters (same logic as local mode)
            # Extract raw filter parameters from kwargs
            languages = kwargs.get("languages")
            exclude_languages = kwargs.get("exclude_languages")
            path_filter = kwargs.get("path_filter")
            exclude_paths = kwargs.get("exclude_paths")
            # Extract min_score from kwargs (correct parameter name from public API)
            min_score = kwargs.get("min_score")
            # Map to score_threshold for vector_store compatibility
            score_threshold = min_score

            # Build filter_conditions dict
            filter_conditions: Dict[str, Any] = {}

            # Build language inclusion filters
            if languages:
                from code_indexer.services.language_validator import LanguageValidator
                from code_indexer.services.language_mapper import LanguageMapper

                language_validator = LanguageValidator()
                language_mapper = LanguageMapper()
                must_conditions = []

                for lang in languages:
                    # Validate each language
                    validation_result = language_validator.validate_language(lang)

                    if not validation_result.is_valid:
                        logger.warning(f"Invalid language filter: {lang}")
                        continue

                    # Build language filter
                    language_filter = language_mapper.build_language_filter(lang)
                    must_conditions.append(language_filter)

                if must_conditions:
                    filter_conditions["must"] = must_conditions

            # Build path inclusion filters
            if path_filter:
                for pf in path_filter:
                    filter_conditions.setdefault("must", []).append(
                        {"key": "path", "match": {"text": pf}}
                    )

            # Build language exclusion filters (must_not conditions)
            if exclude_languages:
                from code_indexer.services.language_validator import LanguageValidator
                from code_indexer.services.language_mapper import LanguageMapper

                language_validator = LanguageValidator()
                language_mapper = LanguageMapper()
                must_not_conditions = []

                for exclude_lang in exclude_languages:
                    # Validate each exclusion language
                    validation_result = language_validator.validate_language(
                        exclude_lang
                    )

                    if not validation_result.is_valid:
                        logger.warning(f"Invalid exclusion language: {exclude_lang}")
                        continue

                    # Get all extensions for this language
                    extensions = language_mapper.get_extensions(exclude_lang)

                    # Add must_not condition for each extension
                    for ext in extensions:
                        must_not_conditions.append(
                            {"key": "language", "match": {"value": ext}}
                        )

                if must_not_conditions:
                    filter_conditions["must_not"] = must_not_conditions

            # Build path exclusion filters (must_not conditions for paths)
            if exclude_paths:
                from code_indexer.services.path_filter_builder import PathFilterBuilder

                path_filter_builder = PathFilterBuilder()

                # Build path exclusion filters
                path_exclusion_filters = path_filter_builder.build_exclusion_filter(
                    list(exclude_paths)
                )

                # Add to existing must_not conditions
                if path_exclusion_filters.get("must_not"):
                    if "must_not" in filter_conditions:
                        filter_conditions["must_not"].extend(
                            path_exclusion_filters["must_not"]
                        )
                    else:
                        filter_conditions["must_not"] = path_exclusion_filters[
                            "must_not"
                        ]

            # Extract accuracy parameter and map to HNSW ef value
            accuracy = kwargs.get("accuracy", "balanced")
            ef_map = {"fast": 50, "balanced": 100, "high": 200}
            ef = ef_map.get(accuracy, 100)  # Default to balanced if unknown

            # Execute search using FilesystemVectorStore.search() with timing
            # This uses HNSW index for fast approximate nearest neighbor search
            results_raw = vector_store.search(
                query=query,
                embedding_provider=embedding_provider,
                collection_name=collection_name,
                limit=limit,
                score_threshold=score_threshold,
                filter_conditions=filter_conditions,
                return_timing=True,  # CRITICAL FIX: Request timing information
                ef=ef,  # Pass accuracy-based ef parameter
            )

            # Parse return value (tuple when return_timing=True)
            if isinstance(results_raw, tuple):
                results, timing_info = results_raw
            else:
                results = results_raw
                timing_info = {}

            logger.info(f"Semantic search returned {len(results)} results")
            return results, timing_info

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return [], {}

    def _execute_fts_search(
        self, project_path: str, query: str, **kwargs
    ) -> List[Dict[str, Any]]:
        """Execute REAL FTS search using cached Tantivy index.

        Args:
            project_path: Path to project root
            query: Search query
            **kwargs: Additional search parameters

        Returns:
            List of FTS results
        """
        try:
            from code_indexer.services.tantivy_index_manager import TantivyIndexManager

            # Create Tantivy index manager
            fts_index_dir = Path(project_path) / ".code-indexer" / "tantivy_index"
            if not fts_index_dir.exists():
                logger.warning(f"FTS index directory does not exist: {fts_index_dir}")
                return []

            tantivy_manager = TantivyIndexManager(fts_index_dir)
            tantivy_manager.initialize_index(create_new=False)

            # Extract FTS search parameters
            limit = kwargs.get("limit", 10)
            edit_distance = kwargs.get("edit_distance", 0)  # 0=exact, >0=fuzzy
            case_sensitive = kwargs.get("case_sensitive", False)
            use_regex = kwargs.get("use_regex", False)
            snippet_lines = kwargs.get(
                "snippet_lines", 5
            )  # Default 5, 0 for no snippets
            languages = kwargs.get("languages", [])
            exclude_languages = kwargs.get("exclude_languages", [])
            path_filters = kwargs.get("path_filters", [])
            exclude_paths = kwargs.get("exclude_paths", [])

            # Execute FTS search using TantivyIndexManager
            results = tantivy_manager.search(
                query_text=query,
                limit=limit,
                edit_distance=edit_distance,
                case_sensitive=case_sensitive,
                snippet_lines=snippet_lines,  # Pass through snippet_lines parameter
                use_regex=use_regex,
                languages=languages,
                exclude_languages=exclude_languages,
                path_filters=path_filters,
                exclude_paths=exclude_paths,
            )

            logger.info(f"FTS search returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"FTS search failed: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return []

    def exposed_rebuild_fts_index(
        self, project_path: str, callback: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Rebuild FTS index from scratch using FileFinder (daemon mode).

        Args:
            project_path: Path to project root
            callback: Optional progress callback for real-time updates

        Returns:
            Dict with rebuild status and stats
        """
        logger.info(f"exposed_rebuild_fts_index: project={project_path}")

        from pathlib import Path
        import shutil
        from code_indexer.config import ConfigManager
        from code_indexer.indexing.file_finder import FileFinder
        from code_indexer.services.tantivy_index_manager import TantivyIndexManager

        # Check if indexing progress file exists
        progress_file = Path(project_path) / ".code-indexer" / "indexing_progress.json"
        if not progress_file.exists():
            return {
                "status": "error",
                "error": "No indexing progress found. Run 'cidx index' first to create the semantic index.",
            }

        try:
            # Load configuration
            config_manager = ConfigManager.create_with_backtrack(Path(project_path))
            config = config_manager.get_config()

            # Send progress callback: discovering files
            if callback:
                callback(0, 0, Path(""), info="Discovering files...")

            # Use FileFinder to discover files
            file_finder = FileFinder(config)
            discovered_files = list(file_finder.find_files())

            if not discovered_files:
                return {
                    "status": "error",
                    "error": "No files found to index. Check your file_extensions and exclude_dirs configuration.",
                }

            # Send progress callback: found files
            if callback:
                callback(
                    0,
                    len(discovered_files),
                    Path(""),
                    info=f"Found {len(discovered_files)} files",
                )

            # Initialize Tantivy manager
            fts_index_dir = Path(project_path) / ".code-indexer" / "tantivy_index"

            # Clear existing FTS index
            if fts_index_dir.exists():
                if callback:
                    callback(
                        0,
                        len(discovered_files),
                        Path(""),
                        info="Clearing existing FTS index...",
                    )
                shutil.rmtree(fts_index_dir)

            tantivy_manager = TantivyIndexManager(fts_index_dir)
            tantivy_manager.initialize_index(create_new=True)

            if callback:
                callback(
                    0, len(discovered_files), Path(""), info="FTS index initialized"
                )

            # Index all files
            indexed_count = 0
            failed_count = 0

            for i, file_path in enumerate(discovered_files, start=1):
                try:
                    # Read file content
                    if not file_path.exists():
                        failed_count += 1
                        if callback:
                            callback(
                                i,
                                len(discovered_files),
                                file_path,
                                info=f"Indexing files... ({i}/{len(discovered_files)})",
                            )
                        continue

                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    # Detect language from file extension
                    extension = file_path.suffix.lstrip(".")
                    language = extension if extension else "unknown"

                    # Create FTS document
                    doc = {
                        "path": str(file_path),
                        "content": content,
                        "content_raw": content,
                        "identifiers": [],
                        "line_start": 1,
                        "line_end": len(content.splitlines()),
                        "language": language,
                    }

                    # Add to FTS index
                    tantivy_manager.add_document(doc)
                    indexed_count += 1

                except Exception as e:
                    failed_count += 1
                    logger.warning(f"Failed to index {file_path}: {e}")

                # Send progress callback
                if callback:
                    callback(
                        i,
                        len(discovered_files),
                        file_path,
                        info=f"Indexing files... ({i}/{len(discovered_files)})",
                    )

            # Commit all documents
            if callback:
                callback(
                    len(discovered_files),
                    len(discovered_files),
                    Path(""),
                    info="Committing FTS index...",
                )
            tantivy_manager.commit()

            if callback:
                callback(
                    len(discovered_files),
                    len(discovered_files),
                    Path(""),
                    info=f"Complete: {indexed_count} indexed, {failed_count} failed",
                )

            return {
                "status": "success",
                "files_indexed": indexed_count,
                "files_failed": failed_count,
            }

        except Exception as e:
            logger.error(f"Failed to rebuild FTS index: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
            }

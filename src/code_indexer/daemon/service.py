"""CIDX Daemon Service - RPyC-based daemon for in-memory index caching.

Provides 14 exposed methods for semantic search, FTS, watch mode, and daemon management.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from rpyc import Service

from .cache import CacheEntry, TTLEvictionThread

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class CIDXDaemonService(Service):
    """RPyC daemon service for in-memory index caching.

    Provides 14 exposed methods organized into categories:
    - Query Operations (3): query, query_fts, query_hybrid
    - Indexing (1): index
    - Watch Mode (3): watch_start, watch_stop, watch_status
    - Storage Operations (3): clean, clean_data, status
    - Daemon Management (4): get_status, clear_cache, shutdown, ping

    Thread Safety:
        - cache_lock: Protects cache entry loading/replacement
        - CacheEntry.read_lock: Concurrent reads
        - CacheEntry.write_lock: Serialized writes
    """

    def __init__(self):
        """Initialize daemon service with cache and eviction thread."""
        super().__init__()

        # Cache state
        self.cache_entry: Optional[CacheEntry] = None
        # FIX Race Condition #1: Use RLock (reentrant lock) to allow nested locking
        # This allows _ensure_cache_loaded to be called both standalone and within lock
        self.cache_lock: threading.RLock = threading.RLock()

        # Watch mode state
        self.watch_handler: Optional[Any] = None
        self.watch_thread: Optional[threading.Thread] = None
        self.watch_project_path: Optional[str] = None

        # Indexing state
        self.indexing_thread: Optional[threading.Thread] = None
        self.indexing_project_path: Optional[str] = None
        self.indexing_lock_internal: threading.Lock = threading.Lock()

        # Configuration (TODO: Load from config file)
        self.config = type('Config', (), {'auto_shutdown_on_idle': False})()

        # Start TTL eviction thread
        self.eviction_thread = TTLEvictionThread(self, check_interval=60)
        self.eviction_thread.start()

        logger.info("CIDXDaemonService initialized")

    # =============================================================================
    # Query Operations (3 methods)
    # =============================================================================

    def exposed_query(
        self, project_path: str, query: str, limit: int = 10, **kwargs
    ) -> List[Dict[str, Any]]:
        """Execute semantic search with caching.

        Args:
            project_path: Path to project root
            query: Search query
            limit: Maximum number of results
            **kwargs: Additional search parameters

        Returns:
            List of search results with scores
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
            results = self._execute_semantic_search(project_path, query, limit, **kwargs)

        return results

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
        logger.debug(f"exposed_query_fts: project={project_path}, query={query[:50]}...")

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
        logger.debug(f"exposed_query_hybrid: project={project_path}, query={query[:50]}...")

        # Execute both searches (they share cache loading internally)
        semantic_results = self.exposed_query(project_path, query, **kwargs)
        fts_results = self.exposed_query_fts(project_path, query, **kwargs)

        return {
            "semantic": semantic_results,
            "fts": fts_results,
        }

    # =============================================================================
    # Indexing (1 method)
    # =============================================================================

    def exposed_index(
        self, project_path: str, callback: Optional[Any] = None, **kwargs
    ) -> Dict[str, Any]:
        """Perform indexing with cache invalidation in background thread.

        This method starts indexing in a background thread and returns immediately.
        The indexing continues asynchronously while queries can still be served.

        Args:
            project_path: Path to project root
            callback: Optional progress callback
            **kwargs: Additional indexing parameters

        Returns:
            Indexing status (started, already_running, or error)
        """
        logger.info(f"exposed_index: project={project_path}")

        # FIX Race Condition #2: Single lock scope for entire operation
        # This prevents TOCTOU vulnerability where multiple threads could start indexing
        with self.cache_lock:
            with self.indexing_lock_internal:
                # Check if indexing is already running
                if self.indexing_thread and self.indexing_thread.is_alive():
                    return {
                        "status": "already_running",
                        "message": "Indexing already in progress",
                        "project_path": self.indexing_project_path,
                    }

                # Invalidate cache BEFORE starting indexing
                if self.cache_entry:
                    logger.info("Invalidating cache before indexing")
                    self.cache_entry = None

                # Start indexing in background thread
                self.indexing_project_path = project_path
                self.indexing_thread = threading.Thread(
                    target=self._run_indexing_background,
                    args=(project_path, callback, kwargs),
                    daemon=True,
                    name="IndexingThread"
                )
                self.indexing_thread.start()

        return {
            "status": "started",
            "message": "Indexing started in background",
            "project_path": project_path,
        }

    def _run_indexing_background(
        self, project_path: str, callback: Optional[Any], kwargs: Dict[str, Any]
    ) -> None:
        """Run indexing in background thread.

        This method executes the actual indexing work and catches any exceptions
        to prevent thread crashes.

        Args:
            project_path: Path to project root
            callback: Optional progress callback
            kwargs: Additional indexing parameters
        """
        try:
            logger.info(f"=== BACKGROUND INDEXING THREAD STARTED ===")
            logger.info(f"Project path: {project_path}")
            logger.info(f"Kwargs: {kwargs}")

            from code_indexer.services.smart_indexer import SmartIndexer
            from code_indexer.config import ConfigManager
            from code_indexer.backends.backend_factory import BackendFactory
            from code_indexer.services.embedding_factory import EmbeddingProviderFactory

            logger.info("Step 1: Importing modules complete")

            # Initialize configuration and backend
            logger.info("Step 2: Creating ConfigManager...")
            config_manager = ConfigManager.create_with_backtrack(Path(project_path))
            config = config_manager.get_config()
            logger.info(f"Step 2 Complete: Config loaded (codebase_dir={config.codebase_dir})")

            # Create embedding provider and vector store
            logger.info("Step 3: Creating embedding provider...")
            embedding_provider = EmbeddingProviderFactory.create(config=config)
            logger.info(f"Step 3 Complete: Embedding provider created ({type(embedding_provider).__name__})")

            logger.info("Step 4: Creating backend and vector store...")
            backend = BackendFactory.create(config, Path(project_path))
            vector_store_client = backend.get_vector_store_client()
            logger.info(f"Step 4 Complete: Backend created ({type(vector_store_client).__name__})")

            # Initialize SmartIndexer with correct signature
            metadata_path = config_manager.config_path.parent / "metadata.json"
            logger.info(f"Step 5: Creating SmartIndexer (metadata_path={metadata_path})...")
            indexer = SmartIndexer(
                config, embedding_provider, vector_store_client, metadata_path
            )
            logger.info("Step 5 Complete: SmartIndexer created")

            # Execute indexing using smart_index method
            logger.info("Step 6: Calling smart_index()...")
            logger.info(f"  force_full={kwargs.get('force_full', False)}")
            logger.info(f"  batch_size={kwargs.get('batch_size', 50)}")
            logger.info(f"  enable_fts={kwargs.get('enable_fts', False)}")

            stats = indexer.smart_index(
                force_full=kwargs.get('force_full', False),
                batch_size=kwargs.get('batch_size', 50),
                progress_callback=callback,
                quiet=True,
                enable_fts=kwargs.get('enable_fts', False),
            )

            logger.info(f"Step 6 Complete: Indexing finished")
            logger.info(f"=== INDEXING STATS: {stats} ===")

            # Invalidate cache after indexing completes so next query loads fresh data
            with self.cache_lock:
                if self.cache_entry:
                    logger.info("Invalidating cache after indexing completed")
                    self.cache_entry = None

            logger.info("=== BACKGROUND INDEXING THREAD COMPLETED SUCCESSFULLY ===")

        except Exception as e:
            logger.error(f"=== BACKGROUND INDEXING FAILED ===")
            logger.error(f"Error: {e}")
            import traceback
            logger.error(traceback.format_exc())

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
        """Start GitAwareWatchHandler in daemon.

        Args:
            project_path: Path to project root
            callback: Optional event callback
            **kwargs: Additional watch parameters

        Returns:
            Watch start status
        """
        logger.info(f"exposed_watch_start: project={project_path}")

        # FIX Race Condition #3: Protect all watch state access with cache_lock
        # This prevents duplicate watch handlers from starting
        with self.cache_lock:
            # Check if watch already running (watch_handler exists AND thread is alive)
            # This prevents duplicate watch starts
            if self.watch_handler and self.watch_thread and self.watch_thread.is_alive():
                return {
                    "status": "error",
                    "message": "Watch already running",
                }

            try:
                from code_indexer.services.git_aware_watch_handler import GitAwareWatchHandler
                from code_indexer.config import ConfigManager
                from code_indexer.backends.backend_factory import BackendFactory
                from code_indexer.services.embedding_factory import EmbeddingProviderFactory
                from code_indexer.services.smart_indexer import SmartIndexer
                from code_indexer.services.git_topology_service import GitTopologyService
                from code_indexer.services.watch_metadata import WatchMetadata

                # Initialize configuration and services
                config_manager = ConfigManager.create_with_backtrack(Path(project_path))
                config = config_manager.get_config()

                # Create embedding provider and vector store
                embedding_provider = EmbeddingProviderFactory.create(config=config)
                backend = BackendFactory.create(config, Path(project_path))
                vector_store_client = backend.get_vector_store_client()

                # Initialize SmartIndexer
                metadata_path = config_manager.config_path.parent / "metadata.json"
                smart_indexer = SmartIndexer(
                    config, embedding_provider, vector_store_client, metadata_path
                )

                # Initialize git topology service
                git_topology_service = GitTopologyService(config.codebase_dir)

                # Initialize watch metadata
                watch_metadata_path = config_manager.config_path.parent / "watch_metadata.json"
                watch_metadata = WatchMetadata.load_from_disk(watch_metadata_path)

                # Create watch handler with correct signature
                debounce_seconds = kwargs.get('debounce_seconds', 2.0)
                self.watch_handler = GitAwareWatchHandler(
                    config=config,
                    smart_indexer=smart_indexer,
                    git_topology_service=git_topology_service,
                    watch_metadata=watch_metadata,
                    debounce_seconds=debounce_seconds,
                )

                # Start watching
                self.watch_handler.start_watching()
                self.watch_project_path = project_path

                # Capture thread reference from watch handler
                self.watch_thread = self.watch_handler.processing_thread

                # Verify thread actually started
                if not self.watch_thread or not self.watch_thread.is_alive():
                    raise RuntimeError("Watch thread failed to start")

                logger.info("Watch started successfully")
                return {"status": "success", "message": "Watch started"}

            except Exception as e:
                logger.error(f"Watch start failed: {e}")
                import traceback
                logger.error(traceback.format_exc())

                # Clean up watch state on error (protected by cache_lock)
                self.watch_handler = None
                self.watch_thread = None
                self.watch_project_path = None

                return {"status": "error", "message": str(e)}

    def exposed_watch_stop(self, project_path: str) -> Dict[str, Any]:
        """Stop watch gracefully with statistics.

        Args:
            project_path: Path to project root

        Returns:
            Watch stop status with statistics
        """
        logger.info(f"exposed_watch_stop: project={project_path}")

        # FIX Race Condition #3: Protect watch state access with cache_lock
        with self.cache_lock:
            if not self.watch_handler:
                return {
                    "status": "error",
                    "message": "No watch running",
                }

            try:
                # Stop watch handler
                self.watch_handler.stop_watching()

                # Wait for thread to finish
                if self.watch_thread:
                    self.watch_thread.join(timeout=5)

                # Get statistics
                stats = self.watch_handler.get_stats() if hasattr(self.watch_handler, 'get_stats') else {}

                # Clear watch state (protected by cache_lock)
                self.watch_handler = None
                self.watch_thread = None
                self.watch_project_path = None

                logger.info("Watch stopped successfully")
                return {
                    "status": "success",
                    "message": "Watch stopped",
                    "stats": stats,
                }

            except Exception as e:
                logger.error(f"Watch stop failed: {e}")
                return {"status": "error", "message": str(e)}

    def exposed_watch_status(self) -> Dict[str, Any]:
        """Get current watch state.

        Returns:
            Watch status with project path and statistics
        """
        # FIX Race Condition #3: Protect watch state access with cache_lock
        with self.cache_lock:
            if not self.watch_handler or not self.watch_thread or not self.watch_thread.is_alive():
                return {
                    "running": False,
                    "project_path": None,
                }

            # Get statistics from watch handler
            stats = self.watch_handler.get_stats() if hasattr(self.watch_handler, 'get_stats') else {}

            return {
                "running": True,
                "project_path": self.watch_project_path,
                "stats": stats,
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
            from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

            # Clear vectors using clear_collection method
            index_dir = Path(project_path) / ".code-indexer" / "index"
            vector_store = FilesystemVectorStore(
                base_path=index_dir,
                project_root=Path(project_path)
            )

            # Get collection name from kwargs or auto-resolve
            collection_name = kwargs.get('collection')
            if collection_name is None:
                collections = vector_store.list_collections()
                if len(collections) == 1:
                    collection_name = collections[0]
                elif len(collections) == 0:
                    return {"status": "success", "message": "No collections to clear"}
                else:
                    return {"status": "error", "message": "Multiple collections exist, specify collection parameter"}

            # Clear collection
            remove_projection_matrix = kwargs.get('remove_projection_matrix', False)
            success = vector_store.clear_collection(collection_name, remove_projection_matrix)

            if success:
                return {"status": "success", "message": f"Collection '{collection_name}' cleared"}
            else:
                return {"status": "error", "message": f"Failed to clear collection '{collection_name}'"}

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
            from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

            # Clear data by deleting collections
            index_dir = Path(project_path) / ".code-indexer" / "index"
            vector_store = FilesystemVectorStore(
                base_path=index_dir,
                project_root=Path(project_path)
            )

            # Get collection name from kwargs or delete all collections
            collection_name = kwargs.get('collection')
            if collection_name:
                # Delete specific collection
                success = vector_store.delete_collection(collection_name)
                if success:
                    return {"status": "success", "message": f"Collection '{collection_name}' deleted"}
                else:
                    return {"status": "error", "message": f"Failed to delete collection '{collection_name}'"}
            else:
                # Delete all collections
                collections = vector_store.list_collections()
                deleted_count = 0
                for coll in collections:
                    if vector_store.delete_collection(coll):
                        deleted_count += 1

                return {"status": "success", "message": f"Deleted {deleted_count} collection(s)"}

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
            from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

            index_dir = Path(project_path) / ".code-indexer" / "index"
            vector_store = FilesystemVectorStore(
                base_path=index_dir,
                project_root=Path(project_path)
            )
            storage_stats = vector_store.get_status() if hasattr(vector_store, 'get_status') else {}

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
                "indexing_running": self.indexing_thread is not None and self.indexing_thread.is_alive(),
                "indexing_project": self.indexing_project_path if self.indexing_thread and self.indexing_thread.is_alive() else None,
            }

        return {
            **cache_status,
            **indexing_status,
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
            # Stop watch if running
            if self.watch_handler:
                self.watch_handler.stop_watching()
                if self.watch_thread:
                    self.watch_thread.join(timeout=5)

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

        Args:
            project_path: Path to project root
        """
        project_path_obj = Path(project_path)

        with self.cache_lock:
            # Check if we need to load or replace cache
            if self.cache_entry is None or self.cache_entry.project_path != project_path_obj:
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
            from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
            vector_store = FilesystemVectorStore(
                base_path=index_dir,
                project_root=entry.project_path
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
            with open(metadata_file, 'r') as f:
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
                logger.info(f"Semantic indexes loaded successfully (collection: {collection_name})")
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
    ) -> List[Dict[str, Any]]:
        """Execute REAL semantic search using cached indexes.

        Args:
            project_path: Path to project root
            query: Search query
            limit: Maximum results
            **kwargs: Additional search parameters

        Returns:
            List of search results
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
            collection_name = vector_store.resolve_collection_name(config, embedding_provider)

            # Extract search parameters
            filter_conditions = kwargs.get('filter_conditions')
            score_threshold = kwargs.get('score_threshold')

            # Execute search using FilesystemVectorStore.search()
            # This uses HNSW index for fast approximate nearest neighbor search
            results_raw = vector_store.search(
                query=query,
                embedding_provider=embedding_provider,
                collection_name=collection_name,
                limit=limit,
                score_threshold=score_threshold,
                filter_conditions=filter_conditions,
                return_timing=False,
            )

            # Ensure return type is list of dicts (not tuple with timing)
            results: List[Dict[str, Any]] = results_raw if isinstance(results_raw, list) else []

            logger.info(f"Semantic search returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

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
            limit = kwargs.get('limit', 10)
            edit_distance = kwargs.get('edit_distance', 0)  # 0=exact, >0=fuzzy
            case_sensitive = kwargs.get('case_sensitive', False)
            use_regex = kwargs.get('use_regex', False)
            languages = kwargs.get('languages', [])
            exclude_languages = kwargs.get('exclude_languages', [])
            path_filters = kwargs.get('path_filters', [])
            exclude_paths = kwargs.get('exclude_paths', [])

            # Execute FTS search using TantivyIndexManager
            results = tantivy_manager.search(
                query_text=query,
                limit=limit,
                edit_distance=edit_distance,
                case_sensitive=case_sensitive,
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

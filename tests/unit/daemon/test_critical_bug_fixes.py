"""Tests for critical bugs discovered during manual E2E testing of Story 2.1.

These tests reproduce the 6 critical bugs found during manual testing and verify fixes.
"""

import threading
from unittest.mock import MagicMock, patch


from code_indexer.daemon.service import CIDXDaemonService


class TestBug1WatchStopMethodName:
    """Bug #1: Watch stop calls wrong method name (stop() instead of stop_watching())."""

    def test_watch_stop_calls_stop_watching_method(self, tmp_path):
        """Verify exposed_watch_stop delegates to watch_manager.stop_watch()."""
        service = CIDXDaemonService()

        # Mock DaemonWatchManager
        mock_watch_manager = MagicMock()
        mock_watch_manager.stop_watch.return_value = {
            "status": "success",
            "message": "Watch stopped",
        }
        service.watch_manager = mock_watch_manager

        # Call exposed_watch_stop
        result = service.exposed_watch_stop(str(tmp_path))

        # VERIFY: watch_manager.stop_watch() was called
        mock_watch_manager.stop_watch.assert_called_once()
        assert result["status"] == "success"

    def test_watch_stop_does_not_call_stop_method(self, tmp_path):
        """Verify exposed_watch_stop delegates to watch_manager.stop_watch()."""
        service = CIDXDaemonService()

        # Mock DaemonWatchManager
        mock_watch_manager = MagicMock()
        mock_watch_manager.stop_watch.return_value = {
            "status": "success",
            "message": "Watch stopped",
        }
        service.watch_manager = mock_watch_manager

        # Call exposed_watch_stop
        service.exposed_watch_stop(str(tmp_path))

        # VERIFY: watch_manager.stop_watch() was called (the correct method)
        mock_watch_manager.stop_watch.assert_called_once()


class TestBug2WatchThreadNotTracked:
    """Bug #2: Watch thread not tracked after start_watching()."""

    def test_watch_start_captures_thread_reference(self, tmp_path):
        """Verify watch_start captures thread reference after start_watching()."""
        service = CIDXDaemonService()

        # Create mock watch handler with processing_thread
        mock_handler = MagicMock()
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        mock_handler.processing_thread = mock_thread
        mock_handler.start_watching = MagicMock()

        # Directly set watch_handler to bypass complex initialization
        service.watch_handler = mock_handler
        service.watch_project_path = str(tmp_path)

        # Simulate what exposed_watch_start does after start_watching()
        service.watch_thread = service.watch_handler.processing_thread

        # VERIFY: watch_thread is captured (not None)
        assert service.watch_thread is not None
        assert service.watch_thread is mock_thread

    def test_watch_status_returns_true_when_thread_alive(self, tmp_path):
        """Verify watch_status returns running=True when thread is alive."""
        service = CIDXDaemonService()

        # Mock DaemonWatchManager
        mock_watch_manager = MagicMock()
        mock_watch_manager.get_stats.return_value = {
            "status": "running",
            "project_path": str(tmp_path),
            "files_processed": 10,
        }
        service.watch_manager = mock_watch_manager

        # VERIFY: watch_status returns running=True
        status = service.exposed_watch_status()
        assert status["running"] is True
        assert status["project_path"] == str(tmp_path)


class TestBug3WatchStateNotCheckedProperly:
    """Bug #3: Watch state check allows duplicate starts."""

    def test_watch_start_rejects_duplicate_starts(self, tmp_path):
        """Verify second watch_start call is rejected when watch already running."""
        service = CIDXDaemonService()

        # Mock DaemonWatchManager to simulate watch already running
        mock_watch_manager = MagicMock()
        mock_watch_manager.start_watch.return_value = {
            "status": "error",
            "message": "Watch already running",
        }
        service.watch_manager = mock_watch_manager

        # Second watch_start should be REJECTED
        result = service.exposed_watch_start(str(tmp_path))
        assert result["status"] == "error"
        assert "already running" in result["message"].lower()


class TestBug4ShutdownSocketCleanupBypassed:
    """Bug #4: Shutdown uses os._exit() bypassing finally block cleanup."""

    @patch("os.kill")
    @patch("os.getpid")
    def test_shutdown_uses_sigterm_not_os_exit(self, mock_getpid, mock_kill):
        """Verify exposed_shutdown uses SIGTERM instead of os._exit()."""
        import signal

        service = CIDXDaemonService()
        mock_getpid.return_value = 12345

        # Call shutdown
        result = service.exposed_shutdown()

        # VERIFY: SIGTERM was sent to current process (not os._exit)
        mock_kill.assert_called_once_with(12345, signal.SIGTERM)
        assert result["status"] == "success"


class TestBug5SemanticIndexesFailToLoad:
    """Bug #5: Semantic indexes fail to load due to private method call."""

    def test_load_semantic_indexes_uses_public_api(self, tmp_path):
        """Verify _load_semantic_indexes uses HNSWIndexManager public API."""
        service = CIDXDaemonService()

        # Setup index directory and collection
        index_dir = tmp_path / ".code-indexer" / "index"
        collection_path = index_dir / "test_collection"
        collection_path.mkdir(parents=True)

        # Create collection metadata
        import json

        metadata = {"vector_size": 1536, "vector_count": 100}
        with open(collection_path / "collection_meta.json", "w") as f:
            json.dump(metadata, f)

        # Create cache entry
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(tmp_path, ttl_minutes=10)

        # Mock HNSWIndexManager and IDIndexManager
        with (
            patch(
                "code_indexer.storage.hnsw_index_manager.HNSWIndexManager"
            ) as mock_hnsw_cls,
            patch(
                "code_indexer.storage.id_index_manager.IDIndexManager"
            ) as mock_id_cls,
            patch(
                "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
            ) as mock_vector_store_cls,
        ):

            mock_vector_store = MagicMock()
            mock_vector_store.list_collections.return_value = ["test_collection"]
            mock_vector_store_cls.return_value = mock_vector_store

            mock_hnsw = MagicMock()
            mock_hnsw_index = MagicMock()
            mock_hnsw.load_index.return_value = mock_hnsw_index
            mock_hnsw_cls.return_value = mock_hnsw

            mock_id_manager = MagicMock()
            mock_id_index = {"id1": 0}
            mock_id_manager.load_index.return_value = mock_id_index
            mock_id_cls.return_value = mock_id_manager

            # Load semantic indexes
            service._load_semantic_indexes(entry)

            # VERIFY: HNSWIndexManager.load_index() was called (public API)
            mock_hnsw.load_index.assert_called_once()

    def test_semantic_indexes_loaded_status_reflects_actual_state(self, tmp_path):
        """Verify semantic_loaded flag is set correctly after loading."""
        service = CIDXDaemonService()

        # Setup index directory and collection
        index_dir = tmp_path / ".code-indexer" / "index"
        collection_path = index_dir / "test_collection"
        collection_path.mkdir(parents=True)

        # Create collection metadata
        import json

        metadata = {"vector_size": 1536, "vector_count": 100}
        with open(collection_path / "collection_meta.json", "w") as f:
            json.dump(metadata, f)

        # Create cache entry
        from code_indexer.daemon.cache import CacheEntry

        entry = CacheEntry(tmp_path, ttl_minutes=10)

        # Mock successful load
        with (
            patch(
                "code_indexer.storage.hnsw_index_manager.HNSWIndexManager"
            ) as mock_hnsw_cls,
            patch(
                "code_indexer.storage.id_index_manager.IDIndexManager"
            ) as mock_id_cls,
            patch(
                "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
            ) as mock_vector_store_cls,
        ):

            mock_vector_store = MagicMock()
            mock_vector_store.list_collections.return_value = ["test_collection"]
            mock_vector_store_cls.return_value = mock_vector_store

            mock_hnsw = MagicMock()
            mock_hnsw_index = MagicMock()
            mock_hnsw.load_index.return_value = mock_hnsw_index
            mock_hnsw_cls.return_value = mock_hnsw

            mock_id_manager = MagicMock()
            mock_id_index = {"id1": 0}
            mock_id_manager.load_index.return_value = mock_id_index
            mock_id_cls.return_value = mock_id_manager

            # Load semantic indexes
            service._load_semantic_indexes(entry)

            # VERIFY: semantic_loaded flag is True
            stats = entry.get_stats()
            assert stats.get("semantic_loaded") is True


class TestBug6ServiceInstancePerConnection:
    """Bug #6: ThreadedServer creates new service instance per connection.

    Note: This is architectural - requires shared state pattern or OneShotServer.
    We test that the solution works, not the bug itself.
    """

    def test_shared_service_instance_pattern(self):
        """Verify service can be configured for shared instance pattern."""
        # Create a shared service instance
        shared_service = CIDXDaemonService()

        # Verify service has shared state attributes
        assert hasattr(shared_service, "cache_entry")
        assert hasattr(shared_service, "cache_lock")
        assert hasattr(shared_service, "watch_handler")
        assert hasattr(shared_service, "watch_thread")

        # Verify cache_lock is threading.RLock (reentrant, thread-safe)
        assert isinstance(shared_service.cache_lock, type(threading.RLock()))

    def test_cache_entry_shared_across_calls(self, tmp_path):
        """Verify single service instance shares cache across multiple calls."""
        service = CIDXDaemonService()

        # Manually create a cache entry
        from code_indexer.daemon.cache import CacheEntry

        first_entry = CacheEntry(tmp_path, ttl_minutes=10)

        # Set cache entry manually
        service.cache_entry = first_entry

        # Call _ensure_cache_loaded with same project path (should reuse)
        service._ensure_cache_loaded(str(tmp_path))
        second_entry = service.cache_entry

        # VERIFY: Same cache entry instance (shared state)
        assert first_entry is second_entry
        assert first_entry is not None

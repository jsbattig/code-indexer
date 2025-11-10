"""Unit tests for CIDXDaemonService.

Tests all 14 exposed RPyC methods of the daemon service.
"""

import threading
from unittest.mock import Mock, patch
import pytest

from code_indexer.daemon.cache import CacheEntry


class TestCIDXDaemonServiceInitialization:
    """Test daemon service initialization."""

    def test_service_initializes_with_empty_cache(self):
        """Service should initialize with no cache entry."""
        from code_indexer.daemon.service import CIDXDaemonService

        service = CIDXDaemonService()
        assert service.cache_entry is None
        assert service.cache_lock is not None
        assert hasattr(service.cache_lock, 'acquire')  # It's a Lock

    def test_service_starts_eviction_thread(self):
        """Service should start TTL eviction thread on initialization."""
        from code_indexer.daemon.service import CIDXDaemonService

        service = CIDXDaemonService()
        assert service.eviction_thread is not None
        assert service.eviction_thread.is_alive()

        # Cleanup
        service.eviction_thread.stop()
        service.eviction_thread.join(timeout=1)

    def test_service_initializes_watch_handlers(self):
        """Service should initialize watch handler attributes to None."""
        from code_indexer.daemon.service import CIDXDaemonService

        service = CIDXDaemonService()
        assert service.watch_handler is None
        assert service.watch_thread is None

        # Cleanup
        service.eviction_thread.stop()
        service.eviction_thread.join(timeout=1)


class TestExposedQueryMethods:
    """Test exposed query methods (semantic, FTS, hybrid)."""

    @pytest.fixture
    def service(self):
        """Create daemon service with mocked dependencies."""
        from code_indexer.daemon.service import CIDXDaemonService

        service = CIDXDaemonService()
        yield service

        # Cleanup
        service.eviction_thread.stop()
        service.eviction_thread.join(timeout=1)

    @pytest.fixture
    def mock_project_path(self, tmp_path):
        """Create mock project with index structure."""
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        # Create .code-indexer directory structure
        config_dir = project_path / ".code-indexer"
        config_dir.mkdir()
        index_dir = config_dir / "index"
        index_dir.mkdir()

        return project_path

    def test_exposed_query_loads_cache_on_first_call(self, service, mock_project_path):
        """exposed_query should load cache on first call."""
        # Mock the cache loading
        with patch.object(service, '_ensure_cache_loaded') as mock_ensure:
            with patch.object(service, '_execute_semantic_search', return_value=([], {})):
                service.exposed_query(str(mock_project_path), "test query")
                mock_ensure.assert_called_once_with(str(mock_project_path))

    def test_exposed_query_updates_access_tracking(self, service, mock_project_path):
        """exposed_query should update cache access tracking."""
        # Setup cache entry
        service.cache_entry = CacheEntry(mock_project_path)
        initial_count = service.cache_entry.access_count

        with patch.object(service, '_execute_semantic_search', return_value=([], {})):
            service.exposed_query(str(mock_project_path), "test query")

        assert service.cache_entry.access_count == initial_count + 1

    def test_exposed_query_executes_semantic_search(self, service, mock_project_path):
        """exposed_query should execute semantic search and return results."""
        mock_results = [
            {"path": "file1.py", "score": 0.95},
            {"path": "file2.py", "score": 0.88},
        ]
        mock_timing = {"query_time_ms": 50, "total_time_ms": 100}

        with patch.object(service, '_execute_semantic_search', return_value=(mock_results, mock_timing)):
            result = service.exposed_query(str(mock_project_path), "test query", limit=10)

        assert result["results"] == mock_results
        assert result["timing"] == mock_timing

    def test_exposed_query_fts_loads_cache_on_first_call(self, service, mock_project_path):
        """exposed_query_fts should load cache on first call."""
        with patch.object(service, '_ensure_cache_loaded') as mock_ensure:
            with patch.object(service, '_execute_fts_search', return_value=[]):
                service.exposed_query_fts(str(mock_project_path), "test query")
                mock_ensure.assert_called_once_with(str(mock_project_path))

    def test_exposed_query_fts_executes_fts_search(self, service, mock_project_path):
        """exposed_query_fts should execute FTS search and return results."""
        mock_results = [
            {"path": "file1.py", "snippet": "test query"},
        ]

        with patch.object(service, '_execute_fts_search', return_value=mock_results):
            results = service.exposed_query_fts(str(mock_project_path), "test query")

        assert results == mock_results

    def test_exposed_query_hybrid_executes_both_searches(self, service, mock_project_path):
        """exposed_query_hybrid should execute both semantic and FTS searches."""
        semantic_results = [{"path": "file1.py", "score": 0.95}]
        fts_results = [{"path": "file2.py", "snippet": "query"}]

        with patch.object(service, 'exposed_query', return_value=semantic_results):
            with patch.object(service, 'exposed_query_fts', return_value=fts_results):
                results = service.exposed_query_hybrid(str(mock_project_path), "test")

        # Should contain results from both searches
        assert "semantic" in results
        assert "fts" in results


class TestExposedIndexingMethods:
    """Test exposed indexing methods."""

    @pytest.fixture
    def service(self):
        """Create daemon service."""
        from code_indexer.daemon.service import CIDXDaemonService

        service = CIDXDaemonService()
        yield service

        # Cleanup
        service.eviction_thread.stop()
        service.eviction_thread.join(timeout=1)

    def test_exposed_index_invalidates_cache_before_indexing(self, service, tmp_path):
        """exposed_index should invalidate cache before starting indexing."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        # Setup existing cache
        service.cache_entry = CacheEntry(project_path)
        service.cache_entry.hnsw_index = Mock()

        with patch('code_indexer.services.smart_indexer.SmartIndexer'):
            with patch('code_indexer.config.ConfigManager'):
                service.exposed_index(str(project_path))

        # Cache should be invalidated
        assert service.cache_entry is None

    def test_exposed_index_calls_smart_indexer(self, service, tmp_path):
        """exposed_index should use SmartIndexer for indexing."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        # Create comprehensive mocks for all dependencies (use module paths for lazy imports)
        with patch('code_indexer.config.ConfigManager') as MockConfigManager:
            with patch('code_indexer.backends.backend_factory.BackendFactory') as MockBackendFactory:
                with patch('code_indexer.services.embedding_factory.EmbeddingProviderFactory') as MockEmbeddingFactory:
                    with patch('code_indexer.services.smart_indexer.SmartIndexer') as MockSmartIndexer:
                        # Configure mocks
                        mock_config_manager = Mock()
                        mock_config = Mock()
                        mock_config_manager.get_config.return_value = mock_config
                        mock_config_path = Mock()
                        mock_config_path.parent = tmp_path
                        mock_config_manager.config_path = mock_config_path
                        MockConfigManager.create_with_backtrack.return_value = mock_config_manager

                        mock_backend = Mock()
                        mock_vector_store = Mock()
                        mock_backend.get_vector_store_client.return_value = mock_vector_store
                        MockBackendFactory.create.return_value = mock_backend

                        mock_embedding_provider = Mock()
                        MockEmbeddingFactory.create.return_value = mock_embedding_provider

                        mock_indexer = Mock()
                        MockSmartIndexer.return_value = mock_indexer

                        # Execute
                        service.exposed_index(str(project_path))

                        # Verify
                        MockSmartIndexer.assert_called_once()
                        mock_indexer.smart_index.assert_called_once()


class TestExposedWatchMethods:
    """Test exposed watch mode methods."""

    @pytest.fixture
    def service(self):
        """Create daemon service."""
        from code_indexer.daemon.service import CIDXDaemonService

        service = CIDXDaemonService()
        yield service

        # Cleanup
        service.eviction_thread.stop()
        service.eviction_thread.join(timeout=1)

    def test_exposed_watch_start_rejects_duplicate_watch(self, service, tmp_path):
        """exposed_watch_start should reject starting watch when already running."""
        project_path = tmp_path / "project"

        # Mock DaemonWatchManager to simulate watch already running
        mock_watch_manager = Mock()
        mock_watch_manager.start_watch.return_value = {
            "status": "error",
            "message": "Watch already running",
        }
        service.watch_manager = mock_watch_manager

        result = service.exposed_watch_start(str(project_path))

        assert result["status"] == "error"
        assert "already running" in result["message"].lower()

    def test_exposed_watch_start_creates_watch_handler(self, service, tmp_path):
        """exposed_watch_start should delegate to watch_manager.start_watch()."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        # Mock DaemonWatchManager
        mock_watch_manager = Mock()
        mock_watch_manager.start_watch.return_value = {
            "status": "success",
            "message": "Watch started",
        }
        service.watch_manager = mock_watch_manager

        # Execute
        result = service.exposed_watch_start(str(project_path))

        # Verify
        assert result["status"] == "success"
        mock_watch_manager.start_watch.assert_called_once()

    def test_exposed_watch_stop_stops_watch_gracefully(self, service, tmp_path):
        """exposed_watch_stop should delegate to watch_manager.stop_watch()."""
        # Mock DaemonWatchManager
        mock_watch_manager = Mock()
        mock_watch_manager.stop_watch.return_value = {
            "status": "success",
            "message": "Watch stopped",
            "stats": {"files_processed": 10},
        }
        service.watch_manager = mock_watch_manager

        result = service.exposed_watch_stop(str(tmp_path))

        assert result["status"] == "success"
        assert "stats" in result
        mock_watch_manager.stop_watch.assert_called_once()

    def test_exposed_watch_status_returns_not_running_when_no_watch(self, service):
        """exposed_watch_status should return not running when no watch active."""
        result = service.exposed_watch_status()

        assert result["running"] is False
        assert result["project_path"] is None

    def test_exposed_watch_status_returns_running_status(self, service, tmp_path):
        """exposed_watch_status should return running status when watch active."""
        project_path = tmp_path / "project"

        # Mock DaemonWatchManager
        mock_watch_manager = Mock()
        mock_watch_manager.get_stats.return_value = {
            "status": "running",
            "project_path": str(project_path),
            "files_processed": 5,
        }
        service.watch_manager = mock_watch_manager

        result = service.exposed_watch_status()

        assert result["running"] is True
        assert result["project_path"] == str(project_path)
        assert "stats" in result


class TestExposedStorageOperations:
    """Test exposed storage operation methods."""

    @pytest.fixture
    def service(self):
        """Create daemon service."""
        from code_indexer.daemon.service import CIDXDaemonService

        service = CIDXDaemonService()
        yield service

        # Cleanup
        service.eviction_thread.stop()
        service.eviction_thread.join(timeout=1)

    def test_exposed_clean_invalidates_cache_before_clearing(self, service, tmp_path):
        """exposed_clean should invalidate cache before clearing vectors."""
        project_path = tmp_path / "project"

        # Setup cache
        service.cache_entry = CacheEntry(project_path)
        service.cache_entry.hnsw_index = Mock()

        with patch('code_indexer.storage.filesystem_vector_store.FilesystemVectorStore') as MockStore:
            mock_instance = Mock()
            MockStore.return_value = mock_instance
            service.exposed_clean(str(project_path))

        # Cache should be invalidated
        assert service.cache_entry is None

    def test_exposed_clean_data_invalidates_cache_before_clearing(self, service, tmp_path):
        """exposed_clean_data should invalidate cache before clearing data."""
        project_path = tmp_path / "project"

        # Setup cache
        service.cache_entry = CacheEntry(project_path)

        with patch('code_indexer.storage.filesystem_vector_store.FilesystemVectorStore') as MockStore:
            mock_instance = Mock()
            MockStore.return_value = mock_instance
            service.exposed_clean_data(str(project_path))

        # Cache should be invalidated
        assert service.cache_entry is None

    def test_exposed_status_returns_combined_stats(self, service, tmp_path):
        """exposed_status should return daemon + storage statistics."""
        project_path = tmp_path / "project"

        # Setup cache
        service.cache_entry = CacheEntry(project_path)

        with patch('code_indexer.storage.filesystem_vector_store.FilesystemVectorStore') as MockStore:
            mock_instance = Mock()
            mock_instance.get_status.return_value = {"vectors": 100}
            MockStore.return_value = mock_instance

            result = service.exposed_status(str(project_path))

        assert "cache" in result
        assert "storage" in result


class TestExposedDaemonManagement:
    """Test exposed daemon management methods."""

    @pytest.fixture
    def service(self):
        """Create daemon service."""
        from code_indexer.daemon.service import CIDXDaemonService

        service = CIDXDaemonService()
        yield service

        # Cleanup
        service.eviction_thread.stop()
        service.eviction_thread.join(timeout=1)

    def test_exposed_get_status_returns_cache_stats(self, service, tmp_path):
        """exposed_get_status should return cache statistics."""
        project_path = tmp_path / "project"

        # Setup cache
        service.cache_entry = CacheEntry(project_path)
        service.cache_entry.access_count = 5

        result = service.exposed_get_status()

        assert "cache_loaded" in result
        assert result["cache_loaded"] is True

    def test_exposed_clear_cache_clears_cache_entry(self, service, tmp_path):
        """exposed_clear_cache should clear cache entry."""
        project_path = tmp_path / "project"

        # Setup cache
        service.cache_entry = CacheEntry(project_path)

        result = service.exposed_clear_cache()

        assert service.cache_entry is None
        assert result["status"] == "success"

    def test_exposed_shutdown_stops_watch_and_eviction(self, service):
        """exposed_shutdown should stop watch and eviction thread."""
        # Mock DaemonWatchManager
        mock_watch_manager = Mock()
        mock_watch_manager.stop_watch.return_value = {
            "status": "success",
            "message": "Watch stopped",
        }
        service.watch_manager = mock_watch_manager

        # Mock os.kill to prevent SIGTERM being sent to test process
        with patch('os.kill') as mock_kill, \
             patch('os.getpid', return_value=12345):
            service.exposed_shutdown()

            # Should stop watch via watch_manager
            mock_watch_manager.stop_watch.assert_called_once()

            # Should stop eviction
            assert service.eviction_thread.running is False

            # Verify SIGTERM was sent
            import signal
            mock_kill.assert_called_once_with(12345, signal.SIGTERM)

    def test_exposed_ping_returns_success(self, service):
        """exposed_ping should return success for health check."""
        result = service.exposed_ping()

        assert result["status"] == "ok"


class TestCacheLoading:
    """Test cache loading functionality."""

    @pytest.fixture
    def service(self):
        """Create daemon service."""
        from code_indexer.daemon.service import CIDXDaemonService

        service = CIDXDaemonService()
        yield service

        # Cleanup
        service.eviction_thread.stop()
        service.eviction_thread.join(timeout=1)

    def test_ensure_cache_loaded_creates_new_entry(self, service, tmp_path):
        """_ensure_cache_loaded should create new cache entry if none exists."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        with patch.object(service, '_load_semantic_indexes'):
            with patch.object(service, '_load_fts_indexes'):
                service._ensure_cache_loaded(str(project_path))

        assert service.cache_entry is not None
        assert service.cache_entry.project_path == project_path

    def test_ensure_cache_loaded_reuses_existing_entry(self, service, tmp_path):
        """_ensure_cache_loaded should reuse cache entry for same project."""
        project_path = tmp_path / "project"

        # Create initial cache entry
        service.cache_entry = CacheEntry(project_path)
        initial_entry = service.cache_entry

        with patch.object(service, '_load_semantic_indexes'):
            with patch.object(service, '_load_fts_indexes'):
                service._ensure_cache_loaded(str(project_path))

        # Should reuse same entry
        assert service.cache_entry is initial_entry

    def test_ensure_cache_loaded_replaces_entry_for_different_project(self, service, tmp_path):
        """_ensure_cache_loaded should replace cache entry for different project."""
        project1 = tmp_path / "project1"
        project2 = tmp_path / "project2"
        project2.mkdir()

        # Create cache for project1
        service.cache_entry = CacheEntry(project1)

        with patch.object(service, '_load_semantic_indexes'):
            with patch.object(service, '_load_fts_indexes'):
                service._ensure_cache_loaded(str(project2))

        # Should have new entry for project2
        assert service.cache_entry.project_path == project2


class TestConcurrency:
    """Test concurrent access patterns."""

    @pytest.fixture
    def service(self):
        """Create daemon service."""
        from code_indexer.daemon.service import CIDXDaemonService

        service = CIDXDaemonService()
        yield service

        # Cleanup
        service.eviction_thread.stop()
        service.eviction_thread.join(timeout=1)

    def test_concurrent_queries_use_shared_cache(self, service, tmp_path):
        """Multiple concurrent queries should share same cache entry."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        # Setup cache
        service.cache_entry = CacheEntry(project_path)

        results = []

        def query():
            with patch.object(service, '_execute_semantic_search', return_value=([], {})):
                result = service.exposed_query(str(project_path), "test")
                results.append(result)

        # Run 5 concurrent queries
        threads = [threading.Thread(target=query) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All queries should complete
        assert len(results) == 5

        # Cache should still exist
        assert service.cache_entry is not None

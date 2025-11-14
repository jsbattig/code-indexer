"""Test that daemon service supports accuracy parameter for semantic search."""

from unittest.mock import MagicMock, patch
import tempfile
from pathlib import Path

from src.code_indexer.daemon.service import CIDXDaemonService


class TestDaemonAccuracySupport:
    """Tests for accuracy parameter support in daemon service."""

    def test_daemon_accepts_accuracy_parameter(self):
        """Test that daemon service accepts accuracy parameter without error."""
        # Create service instance
        service = CIDXDaemonService()

        # Create a temporary directory for testing
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup minimal project structure
            project_path = Path(tmpdir)
            config_dir = project_path / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"
            config_file.write_text('{"embedding_provider": "voyage_ai"}')

            # Mock cache entry to avoid actual cache loading
            service.cache_entry = MagicMock()
            service.cache_entry.update_access = MagicMock()

            with patch.object(service, '_execute_semantic_search') as mock_search:
                mock_search.return_value = ([], {})

                # Test that accuracy parameter is accepted
                try:
                    # This should not raise an error
                    results = service.exposed_query(
                        str(project_path),
                        "test query",
                        limit=10,
                        accuracy="high"  # This is what we're testing
                    )
                    # If we get here without error, the parameter is accepted
                    assert True
                except Exception as e:
                    if "accuracy" in str(e).lower():
                        pytest.fail(f"Daemon should accept accuracy parameter: {e}")

    def test_daemon_maps_accuracy_to_ef(self):
        """Test that daemon maps accuracy values to correct ef values."""
        # Import at module level for proper patching

        # Create service instance
        service = CIDXDaemonService()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup minimal project structure
            project_path = Path(tmpdir)
            config_dir = project_path / ".code-indexer"
            config_dir.mkdir()
            index_dir = config_dir / "index"
            index_dir.mkdir()
            config_file = config_dir / "config.json"
            config_file.write_text('{"embedding_provider": "voyage-ai", "backend": {"type": "filesystem"}}')

            # Create a complete mock vector store with all required methods
            mock_vector_store = MagicMock()
            mock_vector_store.resolve_collection_name.return_value = "test"
            mock_vector_store.resolve_collection_name.return_value = "test"
            mock_vector_store.search.return_value = ([], {})

            # Mock embedding provider
            mock_embedding_provider = MagicMock()

            # Create mock backend with configured method
            mock_backend = MagicMock()
            mock_backend.get_vector_store_client = MagicMock(return_value=mock_vector_store)

            # Patch the backend factory and embedding provider factory
            with patch('code_indexer.backends.backend_factory.BackendFactory.create', return_value=mock_backend):
                with patch('src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.create') as mock_emb_create:
                    mock_emb_create.return_value = mock_embedding_provider

                    # Call _execute_semantic_search with accuracy="high"
                    results, timing = service._execute_semantic_search(
                        str(project_path),
                        "test query",
                        limit=10,
                        accuracy="high"
                    )

                    # Verify that vector_store.search was called with ef=200
                    mock_vector_store.search.assert_called_once()
                    call_kwargs = mock_vector_store.search.call_args[1]
                    assert call_kwargs.get('ef') == 200, f"Expected ef=200 for high accuracy, got {call_kwargs.get('ef')}"
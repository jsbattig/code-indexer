"""Test for temporal indexer collection name bug.

This test reproduces the critical bug where temporal indexer stores vectors
in the default collection instead of the temporal collection, causing
temporal queries to return 0 results.
"""

import subprocess
from unittest.mock import Mock, patch


def test_temporal_indexer_uses_temporal_collection_name(tmp_path):
    """Test that temporal indexer stores vectors in 'temporal' collection, not default.

    BUG: TemporalIndexer.index_commits() calls vector_store.upsert_points(collection_name=None)
    which stores in DEFAULT collection (voyage-code-3), but TemporalSearchService searches
    'code-indexer-temporal' collection, resulting in 0 results.

    FIX: Must pass explicit collection_name to upsert_points().
    """
    from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
    from src.code_indexer.config import ConfigManager
    from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

    # Create a git repo with one commit
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    test_file = tmp_path / "test.py"
    test_file.write_text("def test_function():\n    return True\n")
    subprocess.run(["git", "add", "test.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        env={
            **subprocess.os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )

    # Create config manager
    config_manager = ConfigManager.create_with_backtrack(tmp_path)

    # Create vector store with spy to track upsert_points calls
    vector_store = FilesystemVectorStore(
        base_path=tmp_path / ".code-indexer/index",
        project_root=tmp_path
    )

    # Track collection_name passed to upsert_points
    upsert_calls = []
    original_upsert = vector_store.upsert_points

    def spy_upsert_points(collection_name, points, **kwargs):
        upsert_calls.append({
            "collection_name": collection_name,
            "num_points": len(points)
        })
        return original_upsert(collection_name, points, **kwargs)

    vector_store.upsert_points = spy_upsert_points

    # Create temporal indexer
    indexer = TemporalIndexer(config_manager, vector_store)

    # Run temporal indexing (mock embedding provider to avoid API calls)
    # Patch factory BEFORE creating indexer to ensure consistent dimensions
    with patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory") as mock_factory_before:
        # Ensure collection is created with 1024 dimensions
        mock_factory_before.get_provider_model_info.return_value = {
            "provider": "voyage-ai",
            "model": "voyage-code-3",
            "dimensions": 1024
        }
        # Re-create indexer with patched factory to ensure collection uses correct dimensions
        indexer = TemporalIndexer(config_manager, vector_store)

    with patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory") as mock_factory:
        provider_info = {
            "provider": "voyage-ai",
            "model": "voyage-code-3",
            "dimensions": 1024
        }

        mock_provider = Mock()
        # Make get_embeddings return embeddings for any number of texts
        def mock_get_embeddings(texts):
            return [[0.1] * 1024 for _ in texts]
        mock_provider.get_embeddings.side_effect = mock_get_embeddings
        mock_provider.get_current_model.return_value = "voyage-code-3"
        mock_factory.create.return_value = mock_provider
        mock_factory.get_provider_model_info.return_value = provider_info

        with patch("src.code_indexer.services.temporal.temporal_indexer.VectorCalculationManager") as mock_vcm:
            # Mock VectorCalculationManager to avoid real embedding calls
            mock_manager = Mock()

            def mock_submit_batch(texts, metadata):
                """Return embeddings matching the number of input texts"""
                mock_future = Mock()
                mock_result = Mock()
                mock_result.error = None
                # Return one embedding per text chunk submitted
                mock_result.embeddings = [[0.1] * 1536 for _ in texts]
                mock_result.error = None  # No error
                mock_future.result.return_value = mock_result
                return mock_future

            mock_manager.submit_batch_task.side_effect = mock_submit_batch
            mock_manager.__enter__ = Mock(return_value=mock_manager)
            mock_manager.__exit__ = Mock(return_value=False)
            mock_vcm.return_value = mock_manager

            result = indexer.index_commits(all_branches=False, max_commits=1)

    # ASSERTION: upsert_points must be called with explicit temporal collection name
    assert len(upsert_calls) > 0, "Expected upsert_points to be called at least once"

    # Check ALL calls to upsert_points
    for call in upsert_calls:
        # BUG: Currently passes collection_name=None
        # FIX: Must pass explicit collection name like "code-indexer-temporal"
        assert call["collection_name"] is not None, (
            "BUG: upsert_points called with collection_name=None. "
            "This stores vectors in DEFAULT collection, but temporal search "
            "queries 'code-indexer-temporal' collection, resulting in 0 results."
        )

        # Verify it's the temporal collection (not default)
        assert "temporal" in call["collection_name"].lower(), (
            f"Expected temporal collection name containing 'temporal', "
            f"got: {call['collection_name']}"
        )

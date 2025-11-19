"""Test for commit message search limit bug.

Bug: Commit message searches return max 3 results despite higher --limit values.

Root Cause: FilesystemVectorStore.search() ignores prefetch_limit parameter
and uses k=limit*2 for HNSW queries, causing insufficient candidates when
filters are applied.

Reproduction:
- 764 commit message vectors indexed
- Query with --limit 20 --chunk-type commit_message
- Expected: Up to 20 results
- Actual: Max 3 results

Evidence:
- HNSW asked for k=limit*2 candidates instead of k=prefetch_limit
- prefetch_limit parameter passed but never used
- Filters reduce candidate pool significantly
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch


def test_search_uses_prefetch_limit_not_limit_multiplier():
    """FAILING TEST: search() should use prefetch_limit for HNSW k parameter.

    This test demonstrates the bug where prefetch_limit is ignored and
    limit*2 is used instead, causing insufficient candidates when filters applied.
    """
    from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

    # Setup
    base_path = Path("/tmp/test_index")
    store = FilesystemVectorStore(base_path=base_path)

    # Mock collection existence
    with patch.object(store, "collection_exists", return_value=True):
        # Mock metadata
        mock_metadata = {"vector_size": 1024}

        with patch("builtins.open", create=True) as mock_open:
            mock_file = MagicMock()
            mock_file.__enter__.return_value = mock_file
            mock_open.return_value = mock_file

            with patch("json.load", return_value=mock_metadata):
                # Mock HNSW manager
                mock_hnsw_manager = Mock()
                mock_hnsw_manager.is_stale.return_value = False
                mock_hnsw_index = Mock()
                mock_hnsw_manager.load_index.return_value = mock_hnsw_index
                mock_hnsw_manager.query.return_value = ([], [])

                with patch(
                    "code_indexer.storage.hnsw_index_manager.HNSWIndexManager",
                    return_value=mock_hnsw_manager,
                ):
                    # Mock ID index
                    with patch.object(store, "_id_index", {"test_collection": {}}):
                        # Mock embedding provider
                        mock_embedding_provider = Mock()
                        mock_embedding_provider.get_embedding.return_value = [
                            0.1
                        ] * 1024

                        # Execute search with prefetch_limit
                        user_limit = 20
                        prefetch_limit = 400  # Over-fetch for filters

                        store.search(
                            query="fix",
                            embedding_provider=mock_embedding_provider,
                            collection_name="test_collection",
                            limit=user_limit,
                            lazy_load=True,
                            prefetch_limit=prefetch_limit,
                        )

                        # CRITICAL ASSERTION: HNSW should be queried with prefetch_limit, not limit*2
                        mock_hnsw_manager.query.assert_called_once()
                        call_kwargs = mock_hnsw_manager.query.call_args[1]

                        # BUG: Currently uses k=limit*2 (=40) instead of k=prefetch_limit (=400)
                        assert call_kwargs["k"] == prefetch_limit, (
                            f"HNSW query should use k=prefetch_limit ({prefetch_limit}), "
                            f"but used k={call_kwargs['k']} (limit*2={user_limit*2})"
                        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

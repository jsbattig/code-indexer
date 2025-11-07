"""
Test for critical bug where TemporalSearchService initialized without vector_store_client.
This test MUST fail initially to prove the bug exists, then pass after fix.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import json
from click.testing import CliRunner

from src.code_indexer.cli import cli
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


def test_temporal_service_initialization_includes_vector_store_client():
    """Test that TemporalSearchService is initialized with vector_store_client parameter."""

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        index_dir = project_root / ".code-indexer" / "index"
        index_dir.mkdir(parents=True, exist_ok=True)

        # Create minimal config
        config_dir = project_root / ".code-indexer"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "config.json"
        config_data = {
            "codebase_dir": str(project_root),
            "qdrant": {"port": 6333, "grpc_port": 6334},
            "voyage_api": {"api_key": "test-key"},
            "embedding_provider": "voyage",
        }
        config_file.write_text(json.dumps(config_data))

        # Create a temporal index file to simulate existing temporal index
        # Use the correct collection name from TemporalSearchService.TEMPORAL_COLLECTION_NAME
        temporal_index_dir = index_dir / "code-indexer-temporal"
        temporal_index_dir.mkdir(parents=True, exist_ok=True)
        collection_meta = temporal_index_dir / "collection_meta.json"
        collection_meta.write_text(
            json.dumps(
                {
                    "name": "code-indexer-temporal",
                    "vector_count": 10,
                    "file_count": 5,
                    "indexed_at": "2025-11-04T12:00:00",
                }
            )
        )

        runner = CliRunner()

        with (
            patch("src.code_indexer.cli.ConfigManager") as mock_config_manager,
            patch(
                "src.code_indexer.services.temporal.temporal_search_service.TemporalSearchService"
            ) as mock_temporal_service_class,
            patch(
                "src.code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
            ) as mock_vector_store_class,
            patch(
                "src.code_indexer.cli.EmbeddingProviderFactory"
            ) as mock_embedding_factory,
        ):

            # Setup mocks
            mock_config = Mock()
            mock_config.codebase_dir = project_root
            mock_config.embedding_provider = "voyage"
            mock_config.voyage_api = Mock(api_key="test-key")
            mock_config.qdrant = Mock(port=6333)
            # CRITICAL: Force standalone mode (not daemon mode) for this test
            # We're testing service initialization, not daemon delegation
            mock_config.daemon = Mock(enabled=False)

            mock_cm_instance = Mock()
            mock_cm_instance.get_config.return_value = mock_config
            mock_cm_instance.load.return_value = (
                mock_config  # cli.py calls config_manager.load()
            )
            mock_cm_instance.get_daemon_config.return_value = {
                "enabled": False
            }  # Force standalone mode
            mock_config_manager.create_with_backtrack.return_value = mock_cm_instance

            # Mock vector store
            mock_vector_store = Mock(spec=FilesystemVectorStore)
            mock_vector_store_class.return_value = mock_vector_store

            # Mock embedding provider
            mock_embedding_service = Mock()
            mock_embedding_service.embed.return_value = ([0.1] * 1536, 10)
            mock_embedding_factory.create.return_value = mock_embedding_service

            # Mock temporal service
            mock_temporal_service = Mock()
            mock_temporal_service.has_temporal_index.return_value = True
            mock_temporal_service.search.return_value = []
            mock_temporal_service_class.return_value = mock_temporal_service

            # Run temporal query
            import os

            old_cwd = os.getcwd()
            try:
                os.chdir(str(project_root))
                result = runner.invoke(
                    cli,
                    [
                        "query",
                        "test",
                        "--time-range",
                        "2025-11-01..2025-11-04",
                        "--limit",
                        "5",
                    ],
                )
            finally:
                os.chdir(old_cwd)

            # Debug output if test fails
            if result.exit_code != 0:
                print(f"Exit code: {result.exit_code}")
                print(f"Output: {result.output}")
                if result.exception:
                    import traceback

                    print(f"Exception: {result.exception}")
                    print("".join(traceback.format_tb(result.exc_info[2])))

            # CRITICAL ASSERTION: Verify TemporalSearchService was initialized with vector_store_client
            mock_temporal_service_class.assert_called_once()
            call_kwargs = mock_temporal_service_class.call_args.kwargs

            # This assertion should FAIL before fix and PASS after fix
            assert (
                "vector_store_client" in call_kwargs
            ), "TemporalSearchService initialized WITHOUT vector_store_client parameter - CRITICAL BUG!"

            assert (
                call_kwargs["vector_store_client"] is not None
            ), "vector_store_client parameter is None - service will fail!"

            # Verify it's the correct vector store instance
            assert (
                call_kwargs["vector_store_client"] == mock_vector_store
            ), "Wrong vector_store_client instance passed"


def test_temporal_query_e2e_with_real_initialization():
    """E2E test that temporal queries work with proper initialization."""

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        index_dir = project_root / ".code-indexer" / "index"
        index_dir.mkdir(parents=True, exist_ok=True)

        # Create config
        config_dir = project_root / ".code-indexer"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "config.json"
        config_data = {
            "codebase_dir": str(project_root),
            "qdrant": {"port": 6333, "grpc_port": 6334},
            "voyage_api": {"api_key": "test-key"},
            "embedding_provider": "voyage",
        }
        config_file.write_text(json.dumps(config_data))

        # Create temporal index with test data
        # Use the correct collection name from TemporalSearchService.TEMPORAL_COLLECTION_NAME
        temporal_dir = index_dir / "code-indexer-temporal"
        temporal_dir.mkdir(parents=True, exist_ok=True)

        # Add collection metadata
        collection_meta = temporal_dir / "collection_meta.json"
        collection_meta.write_text(
            json.dumps(
                {
                    "name": "code-indexer-temporal",
                    "vector_count": 1,
                    "file_count": 1,
                    "indexed_at": "2025-11-04T12:00:00",
                }
            )
        )

        # Add a test vector with temporal metadata
        vector_subdir = temporal_dir / "12" / "34"
        vector_subdir.mkdir(parents=True, exist_ok=True)
        vector_file = vector_subdir / "test-vector-id.json"
        vector_data = {
            "id": "test-vector-id",
            "vector": [0.1] * 1536,  # Dummy vector
            "payload": {
                "file_path": "src/test.py",
                "content": "def authenticate_user():\n    pass",
                "language": "python",
                "start_line": 1,
                "end_line": 2,
                "commit_hash": "abc123",
                "author": "Test Author",
                "timestamp": "2025-11-02T10:00:00Z",
                "diff_type": "[ADDED]",
            },
        }
        vector_file.write_text(json.dumps(vector_data))

        runner = CliRunner()

        with patch(
            "src.code_indexer.cli.EmbeddingProviderFactory"
        ) as mock_embedding_factory:
            # Mock embedding service
            mock_embedding_service = Mock()
            mock_embedding_service.embed.return_value = ([0.1] * 1536, 10)
            mock_embedding_factory.create.return_value = mock_embedding_service

            import os

            old_cwd = os.getcwd()
            try:
                os.chdir(str(project_root))
                # Run temporal query
                result = runner.invoke(
                    cli,
                    [
                        "query",
                        "authentication",
                        "--time-range",
                        "2025-11-01..2025-11-04",
                        "--limit",
                        "5",
                    ],
                )
            finally:
                os.chdir(old_cwd)

            # Should NOT see "Temporal index not found" error
            assert (
                "Temporal index not found" not in result.output
            ), f"Got 'Temporal index not found' error - initialization bug not fixed!\nOutput: {result.output}"

            # Should process temporal query successfully
            if result.exit_code != 0:
                # Check if it's the initialization bug
                assert "vector_store_client" not in str(
                    result.exception
                ), f"Initialization bug: {result.exception}"

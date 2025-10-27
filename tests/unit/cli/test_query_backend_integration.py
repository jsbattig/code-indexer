"""Test that CLI query command uses BackendFactory to respect vector_store configuration.

This test verifies Story 3 integration - the query command must use the configured
backend (filesystem or qdrant) instead of being hardcoded to QdrantClient.

CRITICAL BUG:
- CLI query command hardcodes QdrantClient on line ~2841
- Ignores vector_store.provider configuration
- Results in "no results found" even when filesystem vectors exist
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from code_indexer.cli import cli


class TestQueryBackendIntegration:
    """Test that query command respects vector_store.provider configuration."""

    def test_query_uses_backend_factory_with_filesystem_provider(self):
        """Test that query command uses BackendFactory instead of hardcoded QdrantClient.

        FAILING TEST: This test will fail because cli.py line 2841 hardcodes QdrantClient
        instead of using BackendFactory.create() to respect vector_store.provider.

        Expected behavior:
        1. Load config showing vector_store.provider = "filesystem"
        2. Use BackendFactory.create() to get appropriate backend
        3. Call backend.get_vector_store_client() to get FilesystemVectorStore
        4. Execute query using filesystem backend, not QdrantClient
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "test_project"
            project_dir.mkdir(parents=True)

            # Create .code-indexer directory
            config_dir = project_dir / ".code-indexer"
            config_dir.mkdir()

            # Create config with filesystem provider
            config_data = {
                "codebase_dir": str(project_dir),
                "embedding": {
                    "provider": "ollama",
                    "model": "nomic-embed-text",
                },
                "vector_store": {
                    "provider": "filesystem",  # CRITICAL: Using filesystem, not qdrant
                    "filesystem": {
                        "base_path": str(config_dir / "index"),
                    },
                },
                "qdrant": {
                    "host": "localhost",
                    "port": 6333,
                },
            }

            config_path = config_dir / "config.json"
            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)

            # Create filesystem index directory with vectors
            index_dir = config_dir / "index" / "nomic-embed-text"
            index_dir.mkdir(parents=True)

            # Create a vector file to prove filesystem backend has data
            vector_file = index_dir / "test_file.py_chunk_0.json"
            vector_data = {
                "id": "test_file.py_chunk_0",
                "vector": [0.1] * 768,
                "metadata": {
                    "path": "test_file.py",
                    "content": "def hello(): pass",
                    "language": "python",
                    "line_start": 1,
                    "line_end": 1,
                },
            }
            with open(vector_file, "w") as f:
                json.dump(vector_data, f)

            runner = CliRunner()

            # Mock the services to verify BackendFactory is used
            # Note: BackendFactory is now imported at module level, so we patch it at point of use
            with patch("code_indexer.cli.BackendFactory") as mock_backend_factory:
                mock_backend = MagicMock()
                mock_vector_store = MagicMock()

                # Setup mock chain
                mock_backend_factory.create.return_value = mock_backend
                mock_backend.get_vector_store_client.return_value = mock_vector_store

                # Mock health checks
                mock_vector_store.health_check.return_value = True

                # Mock search results
                mock_vector_store.search.return_value = [
                    {
                        "score": 0.95,
                        "payload": {
                            "path": "test_file.py",
                            "content": "def hello(): pass",
                            "language": "python",
                            "line_start": 1,
                            "line_end": 1,
                        },
                    }
                ]

                with patch(
                    "code_indexer.cli.EmbeddingProviderFactory"
                ) as mock_emb_factory:
                    mock_embedding_provider = MagicMock()
                    mock_emb_factory.create.return_value = mock_embedding_provider
                    mock_embedding_provider.health_check.return_value = True
                    mock_embedding_provider.get_embedding.return_value = [0.1] * 768
                    mock_embedding_provider.get_current_model.return_value = (
                        "nomic-embed-text"
                    )
                    mock_embedding_provider.get_provider_name.return_value = "ollama"
                    mock_embedding_provider.get_model_info.return_value = {
                        "name": "nomic-embed-text"
                    }

                    with patch(
                        "code_indexer.services.git_topology_service.GitTopologyService"
                    ) as mock_git_service:
                        mock_git_instance = MagicMock()
                        mock_git_service.return_value = mock_git_instance
                        mock_git_instance.is_git_available.return_value = False

                        with patch(
                            "code_indexer.services.generic_query_service.GenericQueryService"
                        ):
                            # Execute query command
                            import os

                            orig_cwd = os.getcwd()
                            try:
                                os.chdir(project_dir)
                                result = runner.invoke(
                                    cli,
                                    ["query", "test query", "--quiet"],
                                    catch_exceptions=False,
                                )
                            finally:
                                os.chdir(orig_cwd)

                            # ASSERTION 1: BackendFactory.create was called
                            mock_backend_factory.create.assert_called_once()

                            # ASSERTION 2: BackendFactory.create received correct config
                            call_kwargs = mock_backend_factory.create.call_args.kwargs
                            assert "config" in call_kwargs
                            assert (
                                call_kwargs["config"].vector_store.provider
                                == "filesystem"
                            )

                            # ASSERTION 3: backend.get_vector_store_client() was called
                            mock_backend.get_vector_store_client.assert_called_once()

                            # ASSERTION 4: Query executed without errors
                            assert (
                                result.exit_code == 0
                            ), f"Query failed: {result.output}"

    def test_query_uses_backend_factory_with_qdrant_provider(self):
        """Test that query command uses BackendFactory with qdrant provider.

        This ensures BackendFactory works for both backends, not just filesystem.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "test_project"
            project_dir.mkdir(parents=True)

            config_dir = project_dir / ".code-indexer"
            config_dir.mkdir()

            # Create config with qdrant provider
            config_data = {
                "codebase_dir": str(project_dir),
                "embedding": {
                    "provider": "ollama",
                    "model": "nomic-embed-text",
                },
                "vector_store": {
                    "provider": "qdrant",  # Using qdrant backend
                },
                "qdrant": {
                    "host": "localhost",
                    "port": 6333,
                },
            }

            config_path = config_dir / "config.json"
            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)

            runner = CliRunner()

            # Patch BackendFactory at point of use (module-level import in cli.py)
            with patch("code_indexer.cli.BackendFactory") as mock_backend_factory:
                mock_backend = MagicMock()
                mock_vector_store = MagicMock()

                mock_backend_factory.create.return_value = mock_backend
                mock_backend.get_vector_store_client.return_value = mock_vector_store
                mock_vector_store.health_check.return_value = True
                mock_vector_store.search.return_value = []

                with patch(
                    "code_indexer.cli.EmbeddingProviderFactory"
                ) as mock_emb_factory:
                    mock_embedding_provider = MagicMock()
                    mock_emb_factory.create.return_value = mock_embedding_provider
                    mock_embedding_provider.health_check.return_value = True
                    mock_embedding_provider.get_embedding.return_value = [0.1] * 768
                    mock_embedding_provider.get_current_model.return_value = (
                        "nomic-embed-text"
                    )
                    mock_embedding_provider.get_provider_name.return_value = "ollama"
                    mock_embedding_provider.get_model_info.return_value = {
                        "name": "nomic-embed-text"
                    }

                    with patch(
                        "code_indexer.services.git_topology_service.GitTopologyService"
                    ) as mock_git_service:
                        mock_git_instance = MagicMock()
                        mock_git_service.return_value = mock_git_instance
                        mock_git_instance.is_git_available.return_value = False

                        with patch(
                            "code_indexer.services.generic_query_service.GenericQueryService"
                        ):
                            import os

                            orig_cwd = os.getcwd()
                            try:
                                os.chdir(project_dir)
                                result = runner.invoke(
                                    cli,
                                    ["query", "test query", "--quiet"],
                                    catch_exceptions=False,
                                )
                            finally:
                                os.chdir(orig_cwd)

                            # Verify BackendFactory was used with qdrant config
                            mock_backend_factory.create.assert_called_once()
                            call_kwargs = mock_backend_factory.create.call_args.kwargs
                            assert (
                                call_kwargs["config"].vector_store.provider == "qdrant"
                            )

                            assert result.exit_code == 0

"""
Test cidx status command displays correct components based on backend provider.

Verifies:
- Filesystem backend: Skips Docker Services and Project Collection rows
- Qdrant backend: Shows Docker Services and Project Collection rows
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_indexer.config import (
    Config,
    ConfigManager,
)


@pytest.fixture
def filesystem_config(tmp_path: Path) -> tuple[ConfigManager, Config]:
    """Create config with filesystem backend."""
    config_dir = tmp_path / ".code-indexer"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.json"

    config_data = {
        "codebase_dir": str(tmp_path),
        "embedding_provider": "voyage-ai",
        "embedding": {"model": "voyage-code-3", "dimensions": 1024},
        "vector_store": {"provider": "filesystem"},
    }

    config_path.write_text(json.dumps(config_data))

    config_manager = ConfigManager(config_path)
    config = config_manager.load()
    return config_manager, config


@pytest.fixture
def qdrant_config(tmp_path: Path) -> tuple[ConfigManager, Config]:
    """Create config with Qdrant backend."""
    config_dir = tmp_path / ".code-indexer"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.json"

    config_data = {
        "codebase_dir": str(tmp_path),
        "embedding_provider": "voyage-ai",
        "embedding": {"model": "voyage-code-3", "dimensions": 1024},
        "vector_store": {"provider": "qdrant"},
        "qdrant": {"host": "http://localhost:6333", "api_key": None},
        "project_ports": {
            "qdrant_http": 6333,
            "qdrant_grpc": 6334,
            "ollama": None,
            "data_cleaner": None,
        },
    }

    config_path.write_text(json.dumps(config_data))

    config_manager = ConfigManager(config_path)
    config = config_manager.load()
    return config_manager, config


@patch("code_indexer.cli.Table")
@patch("code_indexer.cli.EmbeddingProviderFactory")
@patch("code_indexer.cli.DockerManager")
def test_filesystem_backend_skips_docker_checks(
    mock_docker_manager_class,
    mock_embedding_factory,
    mock_table_class,
    filesystem_config,
    tmp_path,
):
    """Test that filesystem backend skips Docker Services and Project Collection rows."""
    config_manager, config = filesystem_config

    # Setup mocks
    mock_table = MagicMock()
    mock_table_class.return_value = mock_table

    # Mock embedding provider
    mock_embedding = MagicMock()
    mock_embedding.get_provider_name.return_value = "voyage-ai"
    mock_embedding.get_current_model.return_value = "voyage-code-3"
    mock_embedding.health_check.return_value = True
    mock_embedding_factory.create.return_value = mock_embedding

    # Create filesystem index directory
    index_path = tmp_path / ".code-indexer" / "index"
    index_path.mkdir(parents=True, exist_ok=True)

    # Mock filesystem store health check
    with patch(
        "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
    ) as mock_fs:
        mock_fs_instance = MagicMock()
        mock_fs_instance.health_check.return_value = True
        mock_fs.return_value = mock_fs_instance

        # Import and invoke status command
        from code_indexer.cli import cli
        from click.testing import CliRunner

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=str(tmp_path)):
            # Change to the temp directory so config can be found
            result = runner.invoke(cli, ["status"])

    # Command should succeed
    assert result.exit_code == 0, f"Command failed: {result.output}"

    # Get all add_row calls
    add_row_calls = [call_args for call_args in mock_table.add_row.call_args_list]

    # Extract component names (first argument)
    component_names = [call_args[0][0] for call_args in add_row_calls]

    # Verify Docker Services row NOT added
    assert (
        "Docker Services" not in component_names
    ), f"Docker Services should be skipped for filesystem backend, got: {component_names}"

    # Verify Project Collection row NOT added
    assert (
        "Project Collection" not in component_names
    ), f"Project Collection should be skipped for filesystem backend, got: {component_names}"

    # Verify Vector Storage row WAS added
    assert (
        "Vector Storage" in component_names
    ), f"Vector Storage should be present for filesystem backend, got: {component_names}"

    # Verify Storage Path row WAS added
    assert (
        "Storage Path" in component_names
    ), f"Storage Path should be present for filesystem backend, got: {component_names}"


@patch("code_indexer.cli.Table")
@patch("code_indexer.cli.EmbeddingProviderFactory")
@patch("code_indexer.cli.QdrantClient")
@patch("code_indexer.cli.DockerManager")
def test_qdrant_backend_shows_docker_checks(
    mock_docker_manager_class,
    mock_qdrant_client_class,
    mock_embedding_factory,
    mock_table_class,
    qdrant_config,
    tmp_path,
):
    """Test that Qdrant backend shows Docker Services and Project Collection rows."""
    config_manager, config = qdrant_config

    # Setup mocks
    mock_table = MagicMock()
    mock_table_class.return_value = mock_table

    # Mock Docker manager
    mock_docker = MagicMock()
    mock_docker.get_service_status.return_value = {
        "status": "running",
        "services": {"qdrant": {"state": "running"}},
    }
    mock_docker_manager_class.return_value = mock_docker

    # Mock Qdrant client
    mock_qdrant = MagicMock()
    mock_qdrant.health_check.return_value = True
    mock_qdrant.resolve_collection_name.return_value = "test_collection"
    mock_qdrant.collection_exists.return_value = True
    mock_qdrant.count_points.return_value = 100
    mock_qdrant.get_payload_index_status.return_value = {
        "healthy": True,
        "total_indexes": 3,
    }
    mock_qdrant_client_class.return_value = mock_qdrant

    # Mock embedding provider
    mock_embedding = MagicMock()
    mock_embedding.get_provider_name.return_value = "voyage-ai"
    mock_embedding.get_current_model.return_value = "voyage-code-3"
    mock_embedding.health_check.return_value = True
    mock_embedding_factory.create.return_value = mock_embedding

    # Import and invoke status command
    from code_indexer.cli import cli
    from click.testing import CliRunner

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=str(tmp_path)):
        result = runner.invoke(cli, ["status"])

    # Command should succeed
    assert result.exit_code == 0, f"Command failed: {result.output}"

    # Get all add_row calls
    add_row_calls = [call_args for call_args in mock_table.add_row.call_args_list]

    # Extract component names (first argument)
    component_names = [call_args[0][0] for call_args in add_row_calls]

    # Verify Docker Services row WAS added
    assert (
        "Docker Services" in component_names
    ), f"Docker Services should be present for Qdrant backend, got: {component_names}"

    # Verify Project Collection row WAS added
    assert (
        "Project Collection" in component_names
    ), f"Project Collection should be present for Qdrant backend, got: {component_names}"

    # Verify Qdrant row WAS added
    assert (
        "Qdrant" in component_names
    ), f"Qdrant should be present for Qdrant backend, got: {component_names}"

"""
Test cidx status command displays temporal index information.

Verifies:
- Temporal index section appears when collection exists
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import click

import pytest

from code_indexer.config import (
    Config,
    ConfigManager,
)


@pytest.fixture
def filesystem_config_no_temporal(tmp_path: Path) -> tuple[ConfigManager, Config]:
    """Create config with filesystem backend but NO temporal index."""
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

    # Create index directory but NO temporal collection
    index_path = tmp_path / ".code-indexer" / "index"
    index_path.mkdir(parents=True, exist_ok=True)

    config_manager = ConfigManager(config_path)
    config = config_manager.load()
    return config_manager, config


@pytest.fixture
def filesystem_config_with_temporal(
    tmp_path: Path,
) -> tuple[ConfigManager, Config, Path]:
    """Create config with filesystem backend and temporal index metadata."""
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

    # Create temporal collection directory
    temporal_dir = tmp_path / ".code-indexer" / "index" / "code-indexer-temporal"
    temporal_dir.mkdir(parents=True, exist_ok=True)

    # Create temporal_meta.json
    temporal_meta = {
        "last_commit": "abc123def456",
        "total_commits": 150,
        "files_processed": 2500,
        "approximate_vectors_created": 150,
        "indexed_branches": ["main", "feature/temporal-search"],
        "indexing_mode": "multi-branch",
        "indexed_at": "2025-11-10T16:06:17.122871",
    }
    (temporal_dir / "temporal_meta.json").write_text(json.dumps(temporal_meta))

    # Create collection_meta.json with HNSW metadata
    collection_meta = {
        "hnsw_index": {
            "vector_count": 3500,
            "vector_dim": 1024,
            "file_size_bytes": 14680064,  # ~14 MB
            "last_rebuild": "2025-11-10T22:06:22",
        }
    }
    (temporal_dir / "collection_meta.json").write_text(json.dumps(collection_meta))

    # Create binary index files with realistic sizes
    (temporal_dir / "hnsw_index.bin").write_bytes(b"x" * (14 * 1024 * 1024))  # 14 MB
    (temporal_dir / "id_index.bin").write_bytes(b"x" * (500 * 1024))  # 500 KB

    config_manager = ConfigManager(config_path)
    config = config_manager.load()
    return config_manager, config, temporal_dir


@patch("code_indexer.cli.Table")
@patch("code_indexer.cli.EmbeddingProviderFactory")
def test_temporal_index_section_appears_when_exists(
    mock_embedding_factory,
    mock_table_class,
    filesystem_config_with_temporal,
    tmp_path,
):
    """Test that temporal index section appears when temporal collection exists."""
    config_manager, config, temporal_dir = filesystem_config_with_temporal

    # Setup mocks
    mock_table = MagicMock()
    mock_table_class.return_value = mock_table

    # Mock embedding provider
    mock_embedding = MagicMock()
    mock_embedding.get_provider_name.return_value = "voyage-ai"
    mock_embedding.get_current_model.return_value = "voyage-code-3"
    mock_embedding.health_check.return_value = True
    mock_embedding.get_model_info.return_value = {"dimensions": 1024}
    mock_embedding_factory.create.return_value = mock_embedding

    # Mock filesystem store
    with patch(
        "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
    ) as mock_fs:
        mock_fs_instance = MagicMock()
        mock_fs_instance.health_check.return_value = True
        mock_fs_instance.collection_exists.side_effect = (
            lambda name: name == "code-indexer-temporal"
        )
        mock_fs_instance.resolve_collection_name.return_value = (
            "code-indexer-voyage-code-3-d1024"
        )
        mock_fs_instance.count_points.return_value = 3500
        mock_fs_instance.get_indexed_file_count_fast.return_value = 100
        mock_fs_instance.validate_embedding_dimensions.return_value = True
        mock_fs.return_value = mock_fs_instance

        # Import _status_impl and call it directly
        from code_indexer.cli import cli, _status_impl

        # Create context with config_manager
        ctx = click.Context(cli)
        ctx.obj = {"config_manager": config_manager}

        # Call _status_impl directly
        _status_impl(ctx)

    # Get all add_row calls
    add_row_calls = [call_args for call_args in mock_table.add_row.call_args_list]

    # Extract component names (first argument)
    component_names = [call_args[0][0] for call_args in add_row_calls]

    # Verify Temporal Index row WAS added
    assert (
        "Temporal Index" in component_names
    ), f"Temporal Index should be present when temporal collection exists, got: {component_names}"


@patch("code_indexer.cli.Table")
@patch("code_indexer.cli.EmbeddingProviderFactory")
def test_temporal_metadata_extracted_correctly(
    mock_embedding_factory,
    mock_table_class,
    filesystem_config_with_temporal,
    tmp_path,
):
    """Test that temporal metadata is correctly extracted and displayed."""
    config_manager, config, temporal_dir = filesystem_config_with_temporal

    # Setup mocks
    mock_table = MagicMock()
    mock_table_class.return_value = mock_table

    # Mock embedding provider
    mock_embedding = MagicMock()
    mock_embedding.get_provider_name.return_value = "voyage-ai"
    mock_embedding.get_current_model.return_value = "voyage-code-3"
    mock_embedding.health_check.return_value = True
    mock_embedding.get_model_info.return_value = {"dimensions": 1024}
    mock_embedding_factory.create.return_value = mock_embedding

    # Mock filesystem store
    with patch(
        "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
    ) as mock_fs:
        mock_fs_instance = MagicMock()
        mock_fs_instance.health_check.return_value = True
        mock_fs_instance.collection_exists.side_effect = (
            lambda name: name == "code-indexer-temporal"
        )
        mock_fs_instance.resolve_collection_name.return_value = (
            "code-indexer-voyage-code-3-d1024"
        )
        mock_fs_instance.count_points.return_value = 3500
        mock_fs_instance.get_indexed_file_count_fast.return_value = 100
        mock_fs_instance.validate_embedding_dimensions.return_value = True
        mock_fs.return_value = mock_fs_instance

        # Import _status_impl and call it directly
        from code_indexer.cli import cli, _status_impl

        # Create context with config_manager
        ctx = click.Context(cli)
        ctx.obj = {"config_manager": config_manager}

        # Call _status_impl directly
        _status_impl(ctx)

    # Get all add_row calls
    add_row_calls = [call_args for call_args in mock_table.add_row.call_args_list]

    # Find the Temporal Index row
    temporal_row = None
    for call_args in add_row_calls:
        if call_args[0][0] == "Temporal Index":
            temporal_row = call_args[0]
            break

    assert temporal_row is not None, "Temporal Index row should exist"

    # Verify the details contain the expected metadata
    component, status, details = temporal_row[0], temporal_row[1], temporal_row[2]

    assert component == "Temporal Index"
    assert (
        "✅" in status or status == "✅ Available"
    ), f"Status should be available, got: {status}"

    # Details should contain: commits, files, vectors, branches
    assert "150" in details, f"Should show 150 commits, got: {details}"
    assert (
        "2,500" in details or "2500" in details
    ), f"Should show 2500 files, got: {details}"
    assert (
        "3,500" in details or "3500" in details
    ), f"Should show 3500 vectors, got: {details}"
    assert "main" in details, f"Should show main branch, got: {details}"
    assert (
        "feature/temporal-search" in details
    ), f"Should show feature branch, got: {details}"


@patch("code_indexer.cli.Table")
@patch("code_indexer.cli.EmbeddingProviderFactory")
def test_temporal_index_not_shown_when_missing(
    mock_embedding_factory,
    mock_table_class,
    filesystem_config_no_temporal,
    tmp_path,
):
    """Test that temporal index section is NOT shown when temporal collection doesn't exist."""
    config_manager, config = filesystem_config_no_temporal

    # Setup mocks
    mock_table = MagicMock()
    mock_table_class.return_value = mock_table

    # Mock embedding provider
    mock_embedding = MagicMock()
    mock_embedding.get_provider_name.return_value = "voyage-ai"
    mock_embedding.get_current_model.return_value = "voyage-code-3"
    mock_embedding.health_check.return_value = True
    mock_embedding.get_model_info.return_value = {"dimensions": 1024}
    mock_embedding_factory.create.return_value = mock_embedding

    # Mock filesystem store
    with patch(
        "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
    ) as mock_fs:
        mock_fs_instance = MagicMock()
        mock_fs_instance.health_check.return_value = True
        mock_fs_instance.collection_exists.side_effect = (
            lambda name: False
        )  # No collections exist
        mock_fs_instance.resolve_collection_name.return_value = (
            "code-indexer-voyage-code-3-d1024"
        )
        mock_fs.return_value = mock_fs_instance

        # Import _status_impl and call it directly
        from code_indexer.cli import cli, _status_impl

        # Create context with config_manager
        ctx = click.Context(cli)
        ctx.obj = {"config_manager": config_manager}

        # Call _status_impl directly
        _status_impl(ctx)

    # Get all add_row calls
    add_row_calls = [call_args for call_args in mock_table.add_row.call_args_list]

    # Extract component names (first argument)
    component_names = [call_args[0][0] for call_args in add_row_calls]

    # Verify Temporal Index row NOT added
    assert (
        "Temporal Index" not in component_names
    ), f"Temporal Index should NOT be shown when temporal collection doesn't exist, got: {component_names}"

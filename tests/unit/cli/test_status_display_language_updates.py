"""
Test cidx status command display language updates.

Verifies:
1. Temporal Index status shows "✅ Available" (not "✅ Active")
2. Semantic index component name is "Semantic Index" (not "Index")
3. Index Files status column has no icon (not "📊")
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
def filesystem_config_with_indexes(
    tmp_path: Path,
) -> tuple[ConfigManager, Config, Path, Path]:
    """Create config with filesystem backend, temporal index, and semantic index."""
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
        "indexed_branches": ["main", "feature/test"],
        "indexing_mode": "multi-branch",
        "indexed_at": "2025-11-10T16:06:17.122871",
    }
    (temporal_dir / "temporal_meta.json").write_text(json.dumps(temporal_meta))

    # Create collection_meta.json with HNSW metadata
    collection_meta = {
        "hnsw_index": {
            "vector_count": 3500,
            "vector_dim": 1024,
            "file_size_bytes": 14680064,
            "last_rebuild": "2025-11-10T22:06:22",
        }
    }
    (temporal_dir / "collection_meta.json").write_text(json.dumps(collection_meta))

    # Create binary index files with realistic sizes
    (temporal_dir / "hnsw_index.bin").write_bytes(b"x" * (14 * 1024 * 1024))
    (temporal_dir / "id_index.bin").write_bytes(b"x" * (500 * 1024))

    # Create semantic index collection directory
    semantic_dir = (
        tmp_path / ".code-indexer" / "index" / "code-indexer-voyage-code-3-d1024"
    )
    semantic_dir.mkdir(parents=True, exist_ok=True)

    # Create semantic index metadata
    semantic_meta = {
        "hnsw_index": {
            "vector_count": 1234,
            "vector_dim": 1024,
            "file_size_bytes": 5242880,
            "last_rebuild": "2025-11-10T20:00:00",
        }
    }
    (semantic_dir / "collection_meta.json").write_text(json.dumps(semantic_meta))

    # Create semantic index binary files
    (semantic_dir / "hnsw_index.bin").write_bytes(b"x" * (5 * 1024 * 1024))
    (semantic_dir / "id_index.bin").write_bytes(b"x" * (100 * 1024))

    config_manager = ConfigManager(config_path)
    config = config_manager.load()
    return config_manager, config, temporal_dir, semantic_dir


@patch("code_indexer.cli.Table")
@patch("code_indexer.cli.EmbeddingProviderFactory")
def test_temporal_index_shows_available_not_active(
    mock_embedding_factory,
    mock_table_class,
    filesystem_config_with_indexes,
    tmp_path,
):
    """Test that Temporal Index status shows '✅ Available' not '✅ Active'."""
    config_manager, config, temporal_dir, semantic_dir = filesystem_config_with_indexes

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
        mock_fs_instance.collection_exists.side_effect = lambda name: name in [
            "code-indexer-temporal",
            "code-indexer-voyage-code-3-d1024",
        ]
        mock_fs_instance.resolve_collection_name.return_value = (
            "code-indexer-voyage-code-3-d1024"
        )
        mock_fs_instance.count_points.side_effect = lambda name: (
            3500 if name == "code-indexer-temporal" else 1234
        )
        mock_fs_instance.get_indexed_file_count_fast.return_value = 100
        mock_fs_instance.validate_embedding_dimensions.return_value = True
        mock_fs.return_value = mock_fs_instance

        # Import _status_impl and call it directly
        from code_indexer.cli import _status_impl, cli

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

    # Verify status is "✅ Available" not "✅ Active"
    component, status, _ = temporal_row[0], temporal_row[1], temporal_row[2]
    assert component == "Temporal Index"
    assert status == "✅ Available", f"Expected '✅ Available', got: '{status}'"
    assert "✅ Active" not in status, f"Should not contain '✅ Active', got: '{status}'"


@patch("code_indexer.cli.Table")
@patch("code_indexer.cli.EmbeddingProviderFactory")
def test_semantic_index_component_name(
    mock_embedding_factory,
    mock_table_class,
    filesystem_config_with_indexes,
    tmp_path,
):
    """Test that semantic index component name is 'Semantic Index' not 'Index'."""
    config_manager, config, temporal_dir, semantic_dir = filesystem_config_with_indexes

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

    # Create metadata.json for semantic index
    metadata_path = tmp_path / ".code-indexer" / "metadata.json"
    metadata = {
        "collection_name": "code-indexer-voyage-code-3-d1024",
        "last_indexed": "2025-11-10T20:00:00",
        "files_indexed": 100,
        "chunks_indexed": 1234,
        "indexing_status": "completed",
    }
    metadata_path.write_text(json.dumps(metadata))

    # Mock filesystem store
    with patch(
        "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
    ) as mock_fs:
        mock_fs_instance = MagicMock()
        mock_fs_instance.health_check.return_value = True
        mock_fs_instance.collection_exists.side_effect = lambda name: name in [
            "code-indexer-temporal",
            "code-indexer-voyage-code-3-d1024",
        ]
        mock_fs_instance.resolve_collection_name.return_value = (
            "code-indexer-voyage-code-3-d1024"
        )
        mock_fs_instance.count_points.side_effect = lambda name: (
            3500 if name == "code-indexer-temporal" else 1234
        )
        mock_fs_instance.get_indexed_file_count_fast.return_value = 100
        mock_fs_instance.validate_embedding_dimensions.return_value = True
        mock_fs.return_value = mock_fs_instance

        # Import _status_impl and call it directly
        from code_indexer.cli import _status_impl, cli

        # Create context with config_manager
        ctx = click.Context(cli)
        ctx.obj = {"config_manager": config_manager}

        # Call _status_impl directly
        _status_impl(ctx)

    # Get all add_row calls
    add_row_calls = [call_args for call_args in mock_table.add_row.call_args_list]

    # Extract component names (first argument)
    component_names = [call_args[0][0] for call_args in add_row_calls]

    # Verify "Semantic Index" exists but "Index" does not
    assert (
        "Semantic Index" in component_names
    ), f"Should have 'Semantic Index' component, got: {component_names}"
    assert (
        "Index" not in component_names
    ), f"Should NOT have 'Index' component (should be 'Semantic Index'), got: {component_names}"


@patch("code_indexer.cli.Table")
@patch("code_indexer.cli.EmbeddingProviderFactory")
def test_index_files_status_has_no_icon(
    mock_embedding_factory,
    mock_table_class,
    filesystem_config_with_indexes,
    tmp_path,
):
    """Test that Index Files status column has no icon (not '📊')."""
    config_manager, config, temporal_dir, semantic_dir = filesystem_config_with_indexes

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
        mock_fs_instance.collection_exists.side_effect = lambda name: name in [
            "code-indexer-temporal",
            "code-indexer-voyage-code-3-d1024",
        ]
        mock_fs_instance.resolve_collection_name.return_value = (
            "code-indexer-voyage-code-3-d1024"
        )
        mock_fs_instance.count_points.side_effect = lambda name: (
            3500 if name == "code-indexer-temporal" else 1234
        )
        mock_fs_instance.get_indexed_file_count_fast.return_value = 100
        mock_fs_instance.validate_embedding_dimensions.return_value = True
        mock_fs.return_value = mock_fs_instance

        # Import _status_impl and call it directly
        from code_indexer.cli import _status_impl, cli

        # Create context with config_manager
        ctx = click.Context(cli)
        ctx.obj = {"config_manager": config_manager}

        # Call _status_impl directly
        _status_impl(ctx)

    # Get all add_row calls
    add_row_calls = [call_args for call_args in mock_table.add_row.call_args_list]

    # Find the Index Files row
    index_files_row = None
    for call_args in add_row_calls:
        if call_args[0][0] == "Index Files":
            index_files_row = call_args[0]
            break

    # Index Files row may or may not exist depending on filesystem state
    # If it exists, verify status column has no icon
    if index_files_row is not None:
        component, status, _ = (
            index_files_row[0],
            index_files_row[1],
            index_files_row[2],
        )
        assert component == "Index Files"
        assert (
            "📊" not in status
        ), f"Index Files status should not contain '📊' icon, got: '{status}'"
        # Status should be empty string or text-only (no icons)
        assert status == "" or (
            "📊" not in status and "✅" not in status and "❌" not in status
        ), f"Status should be text-only or empty, got: '{status}'"

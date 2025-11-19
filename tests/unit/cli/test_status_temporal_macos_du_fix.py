"""
Test cidx status command handles macOS BSD du command gracefully.

Verifies:
- GNU du -sb failure triggers fallback to BSD du -sk
- BSD du -sk output is correctly parsed (kilobytes -> bytes)
- Empty stdout from du commands is handled without IndexError
- Final fallback to Python iteration works
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
import subprocess
import click

import pytest

from code_indexer.config import (
    Config,
    ConfigManager,
)


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
        "indexed_branches": ["main"],
        "indexing_mode": "single-branch",
        "indexed_at": "2025-11-19T10:00:00.000000",
    }
    (temporal_dir / "temporal_meta.json").write_text(json.dumps(temporal_meta))

    # Create collection_meta.json with HNSW metadata
    collection_meta = {
        "hnsw_index": {
            "vector_count": 3500,
            "vector_dim": 1024,
            "file_size_bytes": 14680064,
            "last_rebuild": "2025-11-19T10:00:00",
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
@patch("subprocess.run")
def test_macos_bsd_du_fallback(
    mock_subprocess_run,
    mock_embedding_factory,
    mock_table_class,
    filesystem_config_with_temporal,
    tmp_path,
):
    """Test that BSD du -sk fallback works when GNU du -sb fails (macOS scenario)."""
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

    # Mock subprocess.run to simulate macOS BSD du behavior:
    # - First call (du -sb): fails with returncode != 0 (BSD du doesn't support -b)
    # - Second call (du -sk): succeeds with kilobyte output
    # - Other calls: return success (for git commands, etc)
    du_sb_called = False
    du_sk_called = False

    def mock_du_behavior(cmd, **kwargs):
        nonlocal du_sb_called, du_sk_called
        result = Mock()
        if isinstance(cmd, list) and "du" in cmd[0]:
            if "-sb" in cmd:
                # GNU du -sb fails on macOS
                du_sb_called = True
                result.returncode = 1
                result.stdout = ""
                result.stderr = "du: illegal option -- b"
            elif "-sk" in cmd:
                # BSD du -sk succeeds, returns kilobytes (14MB = 14336 KB)
                du_sk_called = True
                result.returncode = 0
                result.stdout = "14336\t/path/to/temporal"
                result.stderr = ""
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
        else:
            # Other subprocess calls (git, etc)
            result.returncode = 0
            result.stdout = "mocked output"
            result.stderr = ""
        return result

    mock_subprocess_run.side_effect = mock_du_behavior

    # Mock filesystem store
    with patch(
        "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
    ) as mock_fs:
        mock_fs_instance = MagicMock()
        mock_fs_instance.health_check.return_value = True
        mock_fs_instance.collection_exists.side_effect = lambda name: name == "code-indexer-temporal"
        mock_fs_instance.resolve_collection_name.return_value = "code-indexer-voyage-code-3-d1024"
        mock_fs_instance.count_points.return_value = 3500
        mock_fs_instance.get_indexed_file_count_fast.return_value = 100
        mock_fs_instance.validate_embedding_dimensions.return_value = True
        mock_fs.return_value = mock_fs_instance

        # Import _status_impl and call it directly
        from code_indexer.cli import _status_impl, cli

        # Create context with config_manager
        ctx = click.Context(cli)
        ctx.obj = {"config_manager": config_manager}

        # Call _status_impl directly - should NOT raise IndexError
        _status_impl(ctx, force_docker=False)

    # Verify both du commands were called
    assert du_sb_called, "du -sb should have been called"
    assert du_sk_called, "du -sk should have been called (BSD fallback)"

    # Get all add_row calls
    add_row_calls = mock_table.add_row.call_args_list

    # Find the Temporal Index row
    temporal_row = None
    for call_args in add_row_calls:
        if call_args[0][0] == "Temporal Index":
            temporal_row = call_args[0]
            break

    assert temporal_row is not None, "Temporal Index row should exist"

    # Verify status is "✅ Available" (not error)
    component, status, details = temporal_row[0], temporal_row[1], temporal_row[2]
    assert component == "Temporal Index"
    assert status == "✅ Available", f"Expected '✅ Available', got: '{status}'"

    # Verify storage size calculation worked (14336 KB = ~14 MB)
    assert "Storage:" in details
    assert "14." in details or "13." in details  # Allow for rounding (~14 MB)
    assert "MB" in details


@patch("code_indexer.cli.Table")
@patch("code_indexer.cli.EmbeddingProviderFactory")
@patch("subprocess.run")
def test_empty_stdout_handled_gracefully(
    mock_subprocess_run,
    mock_embedding_factory,
    mock_table_class,
    filesystem_config_with_temporal,
    tmp_path,
):
    """Test that empty stdout from du commands doesn't cause IndexError."""
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

    # Mock subprocess.run to return empty stdout (simulates the original bug)
    du_call_count = 0

    def mock_du_empty_output(cmd, **kwargs):
        nonlocal du_call_count
        result = Mock()
        if isinstance(cmd, list) and "du" in cmd[0]:
            du_call_count += 1
            result.returncode = 1
            result.stdout = ""  # Empty stdout - this was causing IndexError
            result.stderr = "du: some error"
        else:
            # Other subprocess calls (git, etc)
            result.returncode = 0
            result.stdout = "mocked output"
            result.stderr = ""
        return result

    mock_subprocess_run.side_effect = mock_du_empty_output

    # Mock filesystem store
    with patch(
        "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
    ) as mock_fs:
        mock_fs_instance = MagicMock()
        mock_fs_instance.health_check.return_value = True
        mock_fs_instance.collection_exists.side_effect = lambda name: name == "code-indexer-temporal"
        mock_fs_instance.resolve_collection_name.return_value = "code-indexer-voyage-code-3-d1024"
        mock_fs_instance.count_points.return_value = 3500
        mock_fs_instance.get_indexed_file_count_fast.return_value = 100
        mock_fs_instance.validate_embedding_dimensions.return_value = True
        mock_fs.return_value = mock_fs_instance

        # Import _status_impl and call it directly
        from code_indexer.cli import _status_impl, cli

        # Create context with config_manager
        ctx = click.Context(cli)
        ctx.obj = {"config_manager": config_manager}

        # Call _status_impl directly - should NOT raise IndexError
        _status_impl(ctx, force_docker=False)

    # Verify du commands were called (both du -sb and du -sk fail, triggering Python fallback)
    assert du_call_count == 2, f"Expected 2 du calls, got {du_call_count}"

    # Get all add_row calls
    add_row_calls = mock_table.add_row.call_args_list

    # Find the Temporal Index row
    temporal_row = None
    for call_args in add_row_calls:
        if call_args[0][0] == "Temporal Index":
            temporal_row = call_args[0]
            break

    assert temporal_row is not None, "Temporal Index row should exist"

    # Verify status is "✅ Available" (Python fallback worked)
    component, status, details = temporal_row[0], temporal_row[1], temporal_row[2]
    assert component == "Temporal Index"
    assert status == "✅ Available", f"Expected '✅ Available', got: '{status}'"

    # Verify storage size was calculated via Python fallback
    assert "Storage:" in details
    assert "MB" in details


@patch("code_indexer.cli.Table")
@patch("code_indexer.cli.EmbeddingProviderFactory")
@patch("subprocess.run")
def test_gnu_du_success_path(
    mock_subprocess_run,
    mock_embedding_factory,
    mock_table_class,
    filesystem_config_with_temporal,
    tmp_path,
):
    """Test that GNU du -sb works correctly on Linux."""
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

    # Mock subprocess.run to simulate Linux GNU du behavior (success on first try)
    du_sb_called = False

    def mock_gnu_du_success(cmd, **kwargs):
        nonlocal du_sb_called
        result = Mock()
        if isinstance(cmd, list) and "du" in cmd[0]:
            if "-sb" in cmd:
                # GNU du -sb succeeds with byte count
                du_sb_called = True
                result.returncode = 0
                result.stdout = "14680064\t/path/to/temporal"  # 14 MB in bytes
                result.stderr = ""
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
        else:
            # Other subprocess calls (git, etc)
            result.returncode = 0
            result.stdout = "mocked output"
            result.stderr = ""
        return result

    mock_subprocess_run.side_effect = mock_gnu_du_success

    # Mock filesystem store
    with patch(
        "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
    ) as mock_fs:
        mock_fs_instance = MagicMock()
        mock_fs_instance.health_check.return_value = True
        mock_fs_instance.collection_exists.side_effect = lambda name: name == "code-indexer-temporal"
        mock_fs_instance.resolve_collection_name.return_value = "code-indexer-voyage-code-3-d1024"
        mock_fs_instance.count_points.return_value = 3500
        mock_fs_instance.get_indexed_file_count_fast.return_value = 100
        mock_fs_instance.validate_embedding_dimensions.return_value = True
        mock_fs.return_value = mock_fs_instance

        # Import _status_impl and call it directly
        from code_indexer.cli import _status_impl, cli

        # Create context with config_manager
        ctx = click.Context(cli)
        ctx.obj = {"config_manager": config_manager}

        # Call _status_impl directly
        _status_impl(ctx, force_docker=False)

    # Verify du -sb was called and succeeded (no fallback needed)
    assert du_sb_called, "du -sb should have been called"

    # Get all add_row calls
    add_row_calls = mock_table.add_row.call_args_list

    # Find the Temporal Index row
    temporal_row = None
    for call_args in add_row_calls:
        if call_args[0][0] == "Temporal Index":
            temporal_row = call_args[0]
            break

    assert temporal_row is not None, "Temporal Index row should exist"

    # Verify status is "✅ Available"
    component, status, details = temporal_row[0], temporal_row[1], temporal_row[2]
    assert component == "Temporal Index"
    assert status == "✅ Available", f"Expected '✅ Available', got: '{status}'"

    # Verify exact storage size (14680064 bytes = 14.0 MB)
    assert "Storage: 14.0 MB" in details

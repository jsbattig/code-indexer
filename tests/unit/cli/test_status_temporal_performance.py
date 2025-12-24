"""
Test temporal status performance - must be fast even with large indexes.

Performance requirement: Status command should complete in <500ms even with
50,000+ vector files in temporal index.
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_indexer.config import ConfigManager


@pytest.fixture
def filesystem_config_with_large_temporal_index(tmp_path: Path):
    """Create config with large temporal index (simulating 50,000+ files)."""
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
    index_path = tmp_path / ".code-indexer" / "index"
    temporal_dir = index_path / "code-indexer-temporal"
    temporal_dir.mkdir(parents=True, exist_ok=True)

    # Create temporal metadata
    temporal_meta = {
        "last_commit": "abc123",
        "total_commits": 380,
        "files_processed": 5632,
        "indexed_branches": ["main"],
        "indexed_at": "2025-11-10T16:06:17.122871",
    }
    (temporal_dir / "temporal_meta.json").write_text(json.dumps(temporal_meta))

    # Create collection metadata
    collection_meta = {
        "vector_size": 1024,
        "quantization_bits": 2,
        "quantization_target_dims": 64,
    }
    (temporal_dir / "collection_meta.json").write_text(json.dumps(collection_meta))

    # Simulate large index with many subdirectories and files
    # Real scenario: Large codebases can have 50K+ vector files
    # Create realistic size to trigger performance issue
    for subdir_num in range(256):  # Hex subdirectories like real index
        subdir = temporal_dir / f"{subdir_num:02x}"
        subdir.mkdir(parents=True, exist_ok=True)

        # Increase to 200 files per dir = 51,200 files total
        # This ensures test fails without optimization (>500ms)
        for file_num in range(200):
            vector_file = subdir / f"vec_{file_num}.json"
            # Realistic file size (~4KB like real vector files)
            vector_data = {"id": f"{subdir_num}_{file_num}", "vector": [0.1] * 500}
            vector_file.write_text(str(vector_data))

    config_manager = ConfigManager(config_path)
    config = config_manager.load()
    return config_manager, config, temporal_dir


def test_temporal_status_performance_with_large_index(
    filesystem_config_with_large_temporal_index,
):
    """
    Test that temporal status calculation is fast even with 50K+ files.

    Performance regression: Iterating through all files with stat() takes ~700ms with 50K files.
    Requirement: Should complete in <500ms using optimized approach (du command).
    """
    config_manager, config, temporal_dir = filesystem_config_with_large_temporal_index

    # Verify test setup has many files (simulating real scenario)
    file_count = sum(1 for _ in temporal_dir.rglob("*") if _.is_file())
    assert file_count > 50000, f"Test setup should have 50K+ files, got {file_count}"

    with patch("code_indexer.cli.Table") as mock_table_class:
        with patch(
            "code_indexer.cli.EmbeddingProviderFactory"
        ) as mock_provider_factory:
            mock_table = MagicMock()
            mock_table_class.return_value = mock_table

            mock_provider = MagicMock()
            mock_provider.health_check.return_value = True
            mock_provider.get_model_info.return_value = {"dimensions": 1024}
            mock_provider_factory.create.return_value = mock_provider

            with patch(
                "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
            ) as mock_fs_class:
                mock_fs_instance = MagicMock()
                mock_fs_instance.health_check.return_value = True
                mock_fs_instance.collection_exists.return_value = True
                mock_fs_instance.count_points.return_value = 13000
                mock_fs_instance.resolve_collection_name.return_value = (
                    "code-indexer-voyage-code-3-d1024"
                )
                mock_fs_instance.get_indexed_file_count_fast.return_value = 500
                mock_fs_instance.validate_embedding_dimensions.return_value = True
                mock_fs_class.return_value = mock_fs_instance

                # Time the status calculation
                from code_indexer.cli import _status_impl, cli
                import click

                ctx = click.Context(cli)
                ctx.obj = {"config_manager": config_manager}

                start_time = time.time()
                _status_impl(ctx, force_docker=False)
                elapsed_ms = (time.time() - start_time) * 1000

                # Performance requirement: <500ms even with 13K+ files
                assert elapsed_ms < 500, (
                    f"Temporal status too slow! Took {elapsed_ms:.0f}ms with "
                    f"{file_count} files. Should use optimized du command instead "
                    f"of iterating through all files with stat()."
                )

                # Verify temporal row was still added (functional correctness)
                add_row_calls = mock_table.add_row.call_args_list
                temporal_rows = [
                    call[0] for call in add_row_calls if call[0][0] == "Temporal Index"
                ]
                assert len(temporal_rows) > 0, "Temporal Index row should be present"


def test_temporal_status_fallback_when_du_unavailable(
    filesystem_config_with_large_temporal_index,
):
    """
    Test that status calculation falls back to iteration when du command unavailable.

    Ensures cross-platform compatibility and robustness.
    """
    config_manager, config, temporal_dir = filesystem_config_with_large_temporal_index

    with patch("code_indexer.cli.Table") as mock_table_class:
        with patch(
            "code_indexer.cli.EmbeddingProviderFactory"
        ) as mock_provider_factory:
            mock_table = MagicMock()
            mock_table_class.return_value = mock_table

            mock_provider = MagicMock()
            mock_provider.health_check.return_value = True
            mock_provider.get_model_info.return_value = {"dimensions": 1024}
            mock_provider_factory.create.return_value = mock_provider

            with patch(
                "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
            ) as mock_fs_class:
                mock_fs_instance = MagicMock()
                mock_fs_instance.health_check.return_value = True
                mock_fs_instance.collection_exists.return_value = True
                mock_fs_instance.count_points.return_value = 13000
                mock_fs_instance.resolve_collection_name.return_value = (
                    "code-indexer-voyage-code-3-d1024"
                )
                mock_fs_instance.get_indexed_file_count_fast.return_value = 500
                mock_fs_instance.validate_embedding_dimensions.return_value = True
                mock_fs_class.return_value = mock_fs_instance

                # Mock subprocess.run to raise FileNotFoundError (du not available)
                with patch("code_indexer.cli.subprocess.run") as mock_run:
                    mock_run.side_effect = FileNotFoundError("du command not found")

                    from code_indexer.cli import _status_impl, cli
                    import click

                    ctx = click.Context(cli)
                    ctx.obj = {"config_manager": config_manager}

                    # Should not raise, should fallback to iteration
                    _status_impl(ctx, force_docker=False)

                    # Verify temporal row was added (functional correctness)
                    add_row_calls = mock_table.add_row.call_args_list
                    temporal_rows = [
                        call[0]
                        for call in add_row_calls
                        if call[0][0] == "Temporal Index"
                    ]
                    assert (
                        len(temporal_rows) > 0
                    ), "Temporal Index row should be present"
                    # Verify size was calculated (non-zero)
                    temporal_row_text = temporal_rows[0][2]
                    assert "Storage:" in temporal_row_text
                    assert "MB" in temporal_row_text

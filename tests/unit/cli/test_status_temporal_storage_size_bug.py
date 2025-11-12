"""
Test for temporal index storage size calculation bug.

Bug: Storage size only counts binary files (hnsw_index.bin, id_index.bin)
but ignores vector JSON data in subdirectories, causing 83% underreporting.

Manual testing showed: Actual 340 MB, Displayed 56.9 MB
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_indexer.config import ConfigManager


@pytest.fixture
def filesystem_config_with_temporal_and_vectors(tmp_path: Path):
    """Create config with temporal index including vector JSON subdirectories."""
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
        "total_commits": 100,
        "files_processed": 500,
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

    # Create binary index files (simulate 50 MB)
    (temporal_dir / "hnsw_index.bin").write_bytes(b"x" * (45 * 1024 * 1024))
    (temporal_dir / "id_index.bin").write_bytes(b"x" * (5 * 1024 * 1024))

    # Create vector JSON subdirectories (simulate 250 MB of vector data)
    # This is what the bug misses!
    vector_subdirs = ["55", "56", "59", "5a", "65", "66"]
    for subdir in vector_subdirs:
        subdir_path = temporal_dir / subdir
        subdir_path.mkdir(parents=True, exist_ok=True)

        # Create multiple JSON files per subdirectory
        for i in range(10):
            vector_file = subdir_path / f"vector_{i}.json"
            # Each file ~4 MB - make payload much larger
            vector_data = {
                "id": f"{subdir}_{i}",
                "vector": [0.1] * 1000,  # Simulated vector
                "payload": {
                    "path": f"file_{i}.py",
                    "content": "x" * 4_000_000,
                },  # 4MB per file
            }
            vector_file.write_text(json.dumps(vector_data))

    config_manager = ConfigManager(config_path)
    config = config_manager.load()
    return config_manager, config, temporal_dir


def test_storage_size_includes_all_files_not_just_binaries(
    filesystem_config_with_temporal_and_vectors,
):
    """
    Test that storage size calculation includes ALL files in temporal directory.

    Bug reproduction: Current code only counts hnsw_index.bin + id_index.bin,
    missing vector JSON data in subdirectories.

    Expected: Should calculate total directory size including subdirectories
    Actual (buggy): Only counts binary files
    """
    from code_indexer.cli import cli

    config_manager, config, temporal_dir = filesystem_config_with_temporal_and_vectors

    # Calculate actual total size (what SHOULD be displayed)
    actual_total_size = 0
    for file_path in temporal_dir.rglob("*"):
        if file_path.is_file():
            actual_total_size += file_path.stat().st_size
    actual_size_mb = actual_total_size / (1024 * 1024)

    # Binary files only (what's CURRENTLY calculated - the bug)
    binary_size = (temporal_dir / "hnsw_index.bin").stat().st_size + (
        temporal_dir / "id_index.bin"
    ).stat().st_size
    binary_size_mb = binary_size / (1024 * 1024)

    # Verify we have a significant difference (vector data should be substantial)
    assert (
        actual_size_mb > binary_size_mb * 2
    ), "Test setup error: Vector JSON data should be significant portion of storage"

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
                mock_fs_instance.count_points.return_value = 1000
                mock_fs_instance.resolve_collection_name.return_value = (
                    "code-indexer-voyage-code-3-d1024"
                )
                mock_fs_instance.get_indexed_file_count_fast.return_value = 500
                mock_fs_instance.validate_embedding_dimensions.return_value = True
                mock_fs_class.return_value = mock_fs_instance

                # Call _status_impl directly
                from code_indexer.cli import cli, _status_impl
                import click

                ctx = click.Context(cli)
                ctx.obj = {"config_manager": config_manager}

                _status_impl(ctx, force_docker=False)

                # Extract temporal index row from add_row calls
                add_row_calls = mock_table.add_row.call_args_list
                temporal_row = None
                for call in add_row_calls:
                    if call[0][0] == "Temporal Index":
                        temporal_row = call[0]
                        break

                assert temporal_row, "Temporal Index row not found in status output"

                # Extract storage size from details string
                # Format: "380 commits | 5,632 files changed | 13,283 vectors\nBranches: ...\nStorage: XX.X MB | Last indexed: ..."
                details = temporal_row[2]
                import re

                storage_match = re.search(r"Storage:\s+([\d.]+)\s+MB", details)
                assert storage_match, f"Storage size not found in details:\n{details}"

                displayed_size_mb = float(storage_match.group(1))

                # BUG CHECK: Current code shows binary size only
                # This assertion SHOULD FAIL with current buggy code
                assert displayed_size_mb >= actual_size_mb * 0.9, (
                    f"Storage size underreported! "
                    f"Displayed: {displayed_size_mb:.1f} MB, "
                    f"Actual: {actual_size_mb:.1f} MB, "
                    f"Binary only: {binary_size_mb:.1f} MB. "
                    f"Missing {actual_size_mb - displayed_size_mb:.1f} MB of vector JSON data!"
                )

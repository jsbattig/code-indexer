"""
Test for temporal index error handling in status command.

Anti-Fallback Rule (MESSI #2): Never silently swallow exceptions.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_indexer.config import ConfigManager


@pytest.fixture
def filesystem_config_with_corrupted_temporal(tmp_path: Path):
    """Create config with temporal index but corrupted metadata."""
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

    # Create corrupted/invalid temporal metadata (invalid JSON)
    (temporal_dir / "temporal_meta.json").write_text("{ invalid json }")

    config_manager = ConfigManager(config_path)
    config = config_manager.load()
    return config_manager, config, temporal_dir


def test_temporal_index_error_logged_not_silenced(
    filesystem_config_with_corrupted_temporal, caplog
):
    """
    Test that temporal index errors are logged, not silently swallowed.

    MESSI Rule #2 (Anti-Fallback): "I prefer a clean error message over
    an obscure partial 'success'"

    When temporal metadata is corrupted/unreadable:
    - Error MUST be logged with logger.warning()
    - Error row MUST be added to status table
    - Status command MUST NOT fail completely (graceful degradation)
    """
    config_manager, config, temporal_dir = filesystem_config_with_corrupted_temporal

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
                import logging

                # Enable logging capture
                with caplog.at_level(logging.WARNING):
                    ctx = click.Context(cli)
                    ctx.obj = {"config_manager": config_manager}

                    # Should NOT raise exception (graceful degradation)
                    _status_impl(ctx)

                    # Verify error was logged (Anti-Fallback Rule)
                    log_messages = [record.message for record in caplog.records]
                    assert any(
                        "Failed to check temporal index status" in msg
                        for msg in log_messages
                    ), f"Error not logged! Logs: {log_messages}"

                    # Verify error row was added to table
                    add_row_calls = mock_table.add_row.call_args_list
                    temporal_rows = [
                        call[0]
                        for call in add_row_calls
                        if call[0][0] == "Temporal Index"
                    ]

                    assert len(temporal_rows) > 0, "No Temporal Index row added"

                    # Check status is "⚠️ Error" (not hidden)
                    temporal_row = temporal_rows[0]
                    status = temporal_row[1]
                    details = temporal_row[2]

                    assert (
                        "⚠️ Error" in status or "⚠️" in status
                    ), f"Error not visible in status! Got: {status}"
                    assert (
                        "Failed to read" in details or "Error" in details
                    ), f"Error details not shown! Got: {details}"

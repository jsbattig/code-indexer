"""
Unit tests for daemon mode FTS rebuild with progress callbacks.

Tests AC4: Daemon mode FTS rebuild with progress reporting.
"""

import tempfile
from pathlib import Path
import json
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestDaemonRebuildFTS:
    """Test daemon mode FTS rebuild functionality."""

    def test_daemon_has_rebuild_fts_index_endpoint(self):
        """
        AC4: Verify daemon service has exposed_rebuild_fts_index() RPC endpoint.

        This endpoint already exists but returns "not_implemented".
        We verify it exists and is callable.
        """
        from code_indexer.daemon.service import CIDXDaemonService

        service = CIDXDaemonService()

        # Verify the RPC endpoint exists
        assert hasattr(service, "exposed_rebuild_fts_index"), (
            "Daemon service must have exposed_rebuild_fts_index() method\n"
            "Expected in: src/code_indexer/daemon/service.py\n"
            "Signature: def exposed_rebuild_fts_index(self, project_path, callback=None)"
        )

        # Verify it's callable
        assert callable(service.exposed_rebuild_fts_index), (
            "exposed_rebuild_fts_index must be callable"
        )

    def test_daemon_rebuild_implementation_uses_filefinder(self):
        """
        AC4: Verify daemon rebuild implementation uses FileFinder (not vector JSONs).

        This test will FAIL initially because exposed_rebuild_fts_index()
        returns {"status": "not_implemented"}.

        Expected implementation:
        1. Use FileFinder to discover files
        2. Clear existing FTS index
        3. Index files with progress callbacks
        4. Reload FTS cache
        5. Return success status with stats
        """
        from code_indexer.daemon.service import CIDXDaemonService

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            config_dir = project_dir / ".code-indexer"
            config_dir.mkdir()

            # Create sample source files
            (project_dir / "main.py").write_text("def main(): pass")
            (project_dir / "utils.py").write_text("def helper(): pass")

            # Create config file
            config_file = config_dir / "config.json"
            config_data = {
                "codebase_dir": str(project_dir),
                "embedding_provider": "voyage-ai",
                "embedding_model": "voyage-code-3",
                "file_extensions": [".py"],
                "exclude_dirs": [".git", "node_modules"],
            }
            config_file.write_text(json.dumps(config_data))

            # Create mock progress file (required)
            progress_file = config_dir / "indexing_progress.json"
            progress_data = {
                "current_session": {
                    "session_id": "test",
                    "operation_type": "full",
                    "embedding_provider": "voyage-ai",
                    "embedding_model": "voyage-code-3",
                    "total_files": 2,
                    "files_completed": 2,
                },
                "file_records": {}
            }
            progress_file.write_text(json.dumps(progress_data))

            # Create service
            service = CIDXDaemonService()

            # Mock progress callback
            progress_callback = Mock()

            # Call rebuild
            result = service.exposed_rebuild_fts_index(
                project_path=str(project_dir),
                callback=progress_callback
            )

            # This will FAIL initially because current implementation returns:
            # {"status": "not_implemented"}
            assert result.get("status") != "not_implemented", (
                "exposed_rebuild_fts_index() must be implemented!\n"
                f"Current result: {result}\n\n"
                "Expected implementation in src/code_indexer/daemon/service.py:\n"
                "1. Load config and create FileFinder\n"
                "2. Call FileFinder.find_files() to discover files\n"
                "3. Clear existing FTS index (if exists)\n"
                "4. Index files with progress callbacks\n"
                "5. Reload FTS cache with _get_or_create_fts_manager(force_reload=True)\n"
                "6. Return {'status': 'success', 'files_indexed': N, 'files_failed': M}"
            )

            # Verify success
            assert result.get("status") == "success", f"Expected success, got: {result}"
            assert "files_indexed" in result, "Result must include files_indexed count"

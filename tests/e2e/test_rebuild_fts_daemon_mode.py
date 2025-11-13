"""
E2E test for --rebuild-fts-index in daemon mode.

Tests AC4: Daemon mode FTS rebuild with progress reporting.
"""

import subprocess
import sys
import tempfile
from pathlib import Path
import json


class TestRebuildFTSDaemonMode:
    """E2E test for FTS rebuild in daemon mode."""

    def test_rebuild_fts_index_should_work_in_daemon_mode(self):
        """
        AC4: NEW test - rebuild_fts_index SHOULD work in daemon mode.

        This test will FAIL, driving the implementation.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            config_dir = project_dir / ".code-indexer"
            config_dir.mkdir()

            # Create sample files
            (project_dir / "main.py").write_text("def main(): pass")

            # Initialize
            result = subprocess.run(
                [sys.executable, "-m", "code_indexer.cli", "init", "--vector-store", "filesystem"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0

            # Enable daemon
            result = subprocess.run(
                [sys.executable, "-m", "code_indexer.cli", "config", "--daemon"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0

            # Create progress file
            progress_file = config_dir / "indexing_progress.json"
            progress_file.write_text(json.dumps({
                "current_session": {"session_id": "test", "operation_type": "full",
                                  "embedding_provider": "voyage-ai", "embedding_model": "voyage-code-3",
                                  "total_files": 1, "files_completed": 1},
                "file_records": {}
            }))

            # Rebuild FTS in daemon mode - should work!
            result = subprocess.run(
                [sys.executable, "-m", "code_indexer.cli", "index", "--rebuild-fts-index"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            output = result.stdout + result.stderr

            # Should succeed
            assert result.returncode == 0, f"Expected success, got {result.returncode}\nOutput: {output}"
            assert ("success" in output.lower() or "complete" in output.lower()), f"Expected success message\nOutput: {output}"

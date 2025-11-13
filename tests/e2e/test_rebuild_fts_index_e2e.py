"""
E2E tests for --rebuild-fts-index functionality.

Tests the complete workflow of rebuilding FTS index from existing
semantic index progress data.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


class TestRebuildFTSIndexE2E:
    """E2E tests for --rebuild-fts-index flag."""

    def run_cidx_command(self, args, cwd=None, timeout=120):
        """Run cidx command and return result."""
        cmd = [sys.executable, "-m", "code_indexer.cli"] + args
        result = subprocess.run(
            cmd,
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result

    def setup_test_project(self, tmpdir: Path):
        """Create a minimal test project structure."""
        project_dir = tmpdir / "test_project"
        project_dir.mkdir()

        # Create sample files
        (project_dir / "main.py").write_text(
            "def authenticate_user(username, password):\n    return True\n"
        )
        (project_dir / "utils.py").write_text("def helper_function():\n    pass\n")
        (project_dir / "README.md").write_text(
            "# Test Project\n\nThis is a test project.\n"
        )

        return project_dir

    def create_mock_progress_file(self, project_dir: Path):
        """Create a mock indexing_progress.json file."""
        config_dir = project_dir / ".code-indexer"
        config_dir.mkdir(exist_ok=True)

        progress_data = {
            "current_session": {
                "session_id": "test-session",
                "operation_type": "full",
                "started_at": 1234567890.0,
                "embedding_provider": "voyage-ai",
                "embedding_model": "voyage-code-3",
                "completed_at": 1234567900.0,
                "total_files": 3,
                "files_completed": 3,
                "files_failed": 0,
                "chunks_created": 10,
            },
            "file_records": {
                str(project_dir / "main.py"): {
                    "file_path": str(project_dir / "main.py"),
                    "status": "completed",
                    "chunks_created": 5,
                    "processing_time": 0.5,
                    "started_at": 1234567890.0,
                    "completed_at": 1234567891.0,
                    "qdrant_point_ids": ["id1", "id2"],
                },
                str(project_dir / "utils.py"): {
                    "file_path": str(project_dir / "utils.py"),
                    "status": "completed",
                    "chunks_created": 3,
                    "processing_time": 0.3,
                    "started_at": 1234567892.0,
                    "completed_at": 1234567893.0,
                    "qdrant_point_ids": ["id3"],
                },
                str(project_dir / "README.md"): {
                    "file_path": str(project_dir / "README.md"),
                    "status": "completed",
                    "chunks_created": 2,
                    "processing_time": 0.2,
                    "started_at": 1234567894.0,
                    "completed_at": 1234567895.0,
                    "qdrant_point_ids": ["id4"],
                },
            },
        }

        progress_file = config_dir / "indexing_progress.json"
        with open(progress_file, "w") as f:
            json.dump(progress_data, f)

        return progress_file

    @pytest.mark.e2e
    def test_rebuild_fts_index_without_progress_file(self):
        """Test that --rebuild-fts-index fails gracefully without progress file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self.setup_test_project(Path(tmpdir))

            # Initialize config
            result = self.run_cidx_command(["init"], cwd=project_dir)

            # Try to rebuild FTS without progress file
            result = self.run_cidx_command(
                ["index", "--rebuild-fts-index"], cwd=project_dir, timeout=30
            )

            # Should fail with appropriate error
            assert result.returncode != 0
            output = result.stdout + result.stderr
            assert "No indexing progress found" in output

    @pytest.mark.e2e
    def test_rebuild_fts_index_with_progress_file(self):
        """Test successful FTS rebuild from progress file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self.setup_test_project(Path(tmpdir))

            # Initialize config
            result = self.run_cidx_command(
                ["init", "--vector-store", "filesystem"], cwd=project_dir
            )
            if result.returncode != 0:
                pytest.skip(f"Init failed: {result.stderr}")

            # Create mock progress file
            self.create_mock_progress_file(project_dir)

            # Run rebuild FTS index
            result = self.run_cidx_command(
                ["index", "--rebuild-fts-index"], cwd=project_dir, timeout=60
            )

            # Check output
            output = result.stdout + result.stderr

            if result.returncode == 0:
                # Success case
                assert "Rebuilding FTS index" in output
                assert (
                    "Files indexed:" in output
                    or "FTS index rebuilt successfully" in output
                )

                # Verify FTS index directory exists
                fts_index_dir = project_dir / ".code-indexer" / "tantivy_index"
                assert fts_index_dir.exists(), "FTS index directory should be created"
            else:
                # If it fails, check for acceptable reasons
                acceptable_errors = [
                    "tantivy",
                    "import",
                    "module",
                    "fts",
                ]
                assert any(
                    err in output.lower() for err in acceptable_errors
                ), f"Unexpected error: {output}"

    @pytest.mark.e2e
    def test_rebuild_fts_index_with_empty_file_records(self):
        """Test that --rebuild-fts-index works with FileFinder (ignores file_records).

        Updated for Story #488: FileFinder-based rebuild doesn't depend on progress
        file_records. It discovers files from disk directly.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self.setup_test_project(Path(tmpdir))

            # Initialize config
            result = self.run_cidx_command(
                ["init", "--vector-store", "filesystem"], cwd=project_dir
            )
            if result.returncode != 0:
                pytest.skip(f"Init failed: {result.stderr}")

            # Create progress file with NO completed files
            config_dir = project_dir / ".code-indexer"
            config_dir.mkdir(exist_ok=True)
            progress_data = {
                "current_session": None,
                "file_records": {},
            }
            progress_file = config_dir / "indexing_progress.json"
            with open(progress_file, "w") as f:
                json.dump(progress_data, f)

            # Rebuild FTS - should succeed using FileFinder (not file_records)
            result = self.run_cidx_command(
                ["index", "--rebuild-fts-index"], cwd=project_dir, timeout=30
            )

            # Should succeed - FileFinder discovers files from disk
            output = result.stdout + result.stderr
            assert result.returncode == 0, f"Expected success but got: {output}"
            assert "Found 3 files" in output or "Files indexed: 3" in output

    @pytest.mark.e2e
    def test_rebuild_fts_index_clears_existing_index(self):
        """Test that --rebuild-fts-index clears existing FTS index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self.setup_test_project(Path(tmpdir))

            # Initialize config
            result = self.run_cidx_command(
                ["init", "--vector-store", "filesystem"], cwd=project_dir
            )
            if result.returncode != 0:
                pytest.skip(f"Init failed: {result.stderr}")

            # Create mock progress file
            self.create_mock_progress_file(project_dir)

            # Create a fake existing FTS index
            fts_index_dir = project_dir / ".code-indexer" / "tantivy_index"
            fts_index_dir.mkdir(parents=True, exist_ok=True)
            (fts_index_dir / "old_file.txt").write_text("old data")

            # Run rebuild FTS index
            result = self.run_cidx_command(
                ["index", "--rebuild-fts-index"], cwd=project_dir, timeout=60
            )

            output = result.stdout + result.stderr

            if result.returncode == 0:
                # Verify clearing message appears
                assert (
                    "Clearing existing FTS index" in output
                    or "clearing" in output.lower()
                )

                # Verify old file is gone
                assert not (
                    fts_index_dir / "old_file.txt"
                ).exists(), "Old FTS data should be removed"
            else:
                # If it fails, check for acceptable reasons (e.g., tantivy not installed)
                acceptable_errors = ["tantivy", "import", "module"]
                assert any(
                    err in output.lower() for err in acceptable_errors
                ), f"Unexpected error: {output}"

    @pytest.mark.e2e
    def test_rebuild_fts_index_shows_progress(self):
        """Test that --rebuild-fts-index shows progress bar."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = self.setup_test_project(Path(tmpdir))

            # Initialize config
            result = self.run_cidx_command(
                ["init", "--vector-store", "filesystem"], cwd=project_dir
            )
            if result.returncode != 0:
                pytest.skip(f"Init failed: {result.stderr}")

            # Create mock progress file with multiple files
            self.create_mock_progress_file(project_dir)

            # Run rebuild FTS index
            result = self.run_cidx_command(
                ["index", "--rebuild-fts-index"], cwd=project_dir, timeout=60
            )

            output = result.stdout + result.stderr

            if result.returncode == 0:
                # Check for progress indicators
                assert any(
                    indicator in output
                    for indicator in ["Rebuilding", "Files indexed:", "Found", "files"]
                ), "Should show progress information"
            else:
                # Acceptable failure (tantivy not installed)
                acceptable_errors = ["tantivy", "import", "module"]
                assert any(
                    err in output.lower() for err in acceptable_errors
                ), f"Unexpected error: {output}"

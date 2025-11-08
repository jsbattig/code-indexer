"""End-to-end test for daemon temporal indexing bug fix #473."""

import pytest
import tempfile
import shutil
import time
from pathlib import Path
import subprocess
import os
import json

from code_indexer.daemon.service import CIDXDaemonService


class TestDaemonTemporalE2E:
    """End-to-end tests for daemon temporal indexing optimization."""

    @pytest.fixture
    def git_project(self):
        """Create a temporary git repository with commits."""
        temp_dir = tempfile.mkdtemp(prefix="test_daemon_e2e_temporal_")
        project_path = Path(temp_dir)

        try:
            # Initialize git repository
            subprocess.run(["git", "init"], cwd=project_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project_path, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=project_path, check=True)

            # Create initial commit
            test_file = project_path / "test1.py"
            test_file.write_text("def hello():\n    print('hello')\n")
            subprocess.run(["git", "add", "."], cwd=project_path, check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=project_path, check=True, capture_output=True)

            # Create second commit
            test_file2 = project_path / "test2.py"
            test_file2.write_text("def world():\n    print('world')\n")
            subprocess.run(["git", "add", "."], cwd=project_path, check=True)
            subprocess.run(["git", "commit", "-m", "Add world function"], cwd=project_path, check=True, capture_output=True)

            # Initialize code-indexer config
            config_dir = project_path / ".code-indexer"
            config_dir.mkdir(exist_ok=True)
            config_file = config_dir / "config.json"
            config_content = {
                "provider": "voyageai",
                "api_key": os.environ.get("VOYAGE_API_KEY", "test-key"),
                "language_extensions": {
                    "python": [".py"]
                }
            }
            config_file.write_text(json.dumps(config_content, indent=2))

            yield project_path
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.skipif(
        not os.environ.get("VOYAGE_API_KEY"),
        reason="Requires VOYAGE_API_KEY for real indexing"
    )
    def test_daemon_temporal_no_semantic_overhead_e2e(self, git_project):
        """E2E test that temporal indexing skips semantic setup."""
        daemon = CIDXDaemonService()

        # Track timing to ensure no file discovery delay
        start_time = time.time()

        # Track if any file discovery happens
        files_discovered = []

        def progress_callback(current, total, file_path, info="", **kwargs):
            # If we see files being discovered (not commits), that's wrong
            if info and "Discovering files" in info:
                files_discovered.append(str(file_path))

        # Run temporal indexing
        result = daemon.exposed_index_blocking(
            str(git_project),
            callback=progress_callback,
            index_commits=True,
            max_commits=10
        )

        elapsed = time.time() - start_time

        # Assertions
        assert result["status"] == "completed"
        assert result["stats"]["total_commits"] >= 2  # We made 2 commits

        # CRITICAL: No file discovery should have happened
        assert len(files_discovered) == 0, f"File discovery occurred: {files_discovered}"

        # Temporal indexing should be fast (no semantic overhead)
        # Allow generous time for API calls but should not include file discovery
        assert elapsed < 30, f"Temporal indexing took too long: {elapsed}s (indicates semantic overhead)"

    def test_daemon_semantic_still_works_e2e(self, git_project):
        """E2E test that semantic indexing still works normally."""
        daemon = CIDXDaemonService()

        # Create some Python files for semantic indexing
        (git_project / "module1.py").write_text("def semantic_test():\n    pass\n")
        (git_project / "module2.py").write_text("class TestClass:\n    pass\n")

        # Track that file discovery happens for semantic
        files_discovered = []

        def progress_callback(current, total, file_path, info="", **kwargs):
            if file_path and str(file_path).endswith(".py"):
                files_discovered.append(str(file_path))

        # Run semantic indexing (no index_commits flag)
        result = daemon.exposed_index_blocking(
            str(git_project),
            callback=progress_callback,
            force_full=True
        )

        # Assertions
        assert result["status"] == "completed"

        # For semantic indexing, we SHOULD see file discovery
        assert len(files_discovered) > 0, "No files discovered in semantic indexing"

    def test_daemon_temporal_then_semantic_invalidates_cache(self, git_project):
        """Test that temporal indexing properly invalidates cache for semantic."""
        daemon = CIDXDaemonService()

        # First run temporal indexing
        temporal_result = daemon.exposed_index_blocking(
            str(git_project),
            callback=None,
            index_commits=True
        )
        assert temporal_result["status"] == "completed"

        # Cache should be invalidated, verify by checking internal state
        assert daemon.cache_entry is None, "Cache not invalidated after temporal indexing"

        # Now run semantic indexing
        semantic_result = daemon.exposed_index_blocking(
            str(git_project),
            callback=None,
            force_full=True
        )
        assert semantic_result["status"] == "completed"

        # Cache should be invalidated again
        assert daemon.cache_entry is None, "Cache not invalidated after semantic indexing"
"""
E2E tests for golden repository temporal indexing integration.

Tests the complete workflow from API request to temporal index creation.
"""

import subprocess
import tempfile
from pathlib import Path


class TestGoldenRepoTemporalIntegration:
    """Test golden repository registration with temporal indexing."""

    def test_execute_post_clone_workflow_with_temporal_parameters(self):
        """Test that _execute_post_clone_workflow accepts and uses temporal parameters."""
        from code_indexer.server.repositories.golden_repo_manager import (
            GoldenRepoManager,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple git repo
            repo_path = Path(tmpdir) / "test-repo"
            repo_path.mkdir()

            # Initialize git repo
            subprocess.run(
                ["git", "init"], cwd=str(repo_path), check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
            )

            # Create test file and commit
            test_file = repo_path / "test.py"
            test_file.write_text("print('hello')\n")
            subprocess.run(
                ["git", "add", "."], cwd=str(repo_path), check=True, capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
            )

            # Create another commit
            test_file.write_text("print('hello world')\n")
            subprocess.run(
                ["git", "add", "."], cwd=str(repo_path), check=True, capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-m", "Second commit"],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
            )

            # Test the workflow with temporal parameters
            manager = GoldenRepoManager(data_dir=tmpdir)

            # Call _execute_post_clone_workflow with temporal parameters
            temporal_options = {"max_commits": 10, "diff_context": 3}

            # This should not raise an exception
            manager._execute_post_clone_workflow(
                clone_path=str(repo_path),
                force_init=False,
                enable_temporal=True,
                temporal_options=temporal_options,
            )

            # Verify temporal index was created
            temporal_index_path = (
                repo_path / ".code-indexer" / "index" / "code-indexer-temporal"
            )
            assert temporal_index_path.exists(), "Temporal index directory should exist"

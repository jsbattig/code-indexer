"""Test API signature compatibility fixes for Story 7 Enhanced Sync Integration.

This test verifies that the API signature mismatches identified by the code-reviewer
have been properly fixed without requiring full Docker container startup.
"""

import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

from code_indexer.server.repositories.golden_repo_manager import GoldenRepoManager


class TestAPISignatureCompatibility:
    """Test suite to verify API signature compatibility fixes."""

    def test_add_golden_repo_correct_parameters(self):
        """Test that add_golden_repo accepts correct parameter names."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = GoldenRepoManager(temp_dir)

            # Create a test repository directory
            test_repo_dir = Path(temp_dir) / "test-repo"
            test_repo_dir.mkdir()
            (test_repo_dir / "test.py").write_text("print('hello')")

            # Initialize as git repository
            import subprocess

            subprocess.run(
                ["git", "init"], cwd=test_repo_dir, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=test_repo_dir,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=test_repo_dir,
                check=True,
            )
            subprocess.run(["git", "add", "."], cwd=test_repo_dir, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"], cwd=test_repo_dir, check=True
            )

            # Mock the post-clone workflow to avoid Docker startup
            with patch.object(manager, "_execute_post_clone_workflow") as mock_workflow:
                # This should work with correct parameter names
                result = manager.add_golden_repo(
                    repo_url=str(test_repo_dir), alias="test-repo"
                )

                assert result["success"] is True
                assert "test-repo" in result["message"]
                mock_workflow.assert_called_once()

    def test_add_golden_repo_wrong_parameters_fail(self):
        """Test that add_golden_repo rejects wrong parameter names."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = GoldenRepoManager(temp_dir)

            # Create a test repository directory
            test_repo_dir = Path(temp_dir) / "test-repo"
            test_repo_dir.mkdir()
            (test_repo_dir / "test.py").write_text("print('hello')")

            # Initialize as git repository
            import subprocess

            subprocess.run(
                ["git", "init"], cwd=test_repo_dir, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=test_repo_dir,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=test_repo_dir,
                check=True,
            )
            subprocess.run(["git", "add", "."], cwd=test_repo_dir, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"], cwd=test_repo_dir, check=True
            )

            # This should fail with TypeError for wrong parameter name
            with pytest.raises(TypeError, match="unexpected keyword argument"):
                manager.add_golden_repo(
                    alias="test-repo",
                    git_url=str(test_repo_dir),  # Wrong parameter name
                    description="Test repository",  # Non-existent parameter
                )

    def test_get_golden_repo_method_exists(self):
        """Test that get_golden_repo method exists and works correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = GoldenRepoManager(temp_dir)

            # Test that method exists and returns None for non-existent repo
            result = manager.get_golden_repo("non-existent")
            assert result is None

    def test_golden_repo_clone_path_accessible(self):
        """Test that golden repository clone_path is accessible after creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = GoldenRepoManager(temp_dir)

            # Create a test repository directory
            test_repo_dir = Path(temp_dir) / "test-repo"
            test_repo_dir.mkdir()
            (test_repo_dir / "test.py").write_text("print('hello')")

            # Initialize as git repository
            import subprocess

            subprocess.run(
                ["git", "init"], cwd=test_repo_dir, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=test_repo_dir,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=test_repo_dir,
                check=True,
            )
            subprocess.run(["git", "add", "."], cwd=test_repo_dir, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"], cwd=test_repo_dir, check=True
            )

            # Mock the post-clone workflow to avoid Docker startup
            with patch.object(manager, "_execute_post_clone_workflow"):
                manager.add_golden_repo(repo_url=str(test_repo_dir), alias="test-repo")

                # Should be able to get the repository and access clone_path
                golden_repo = manager.get_golden_repo("test-repo")
                assert golden_repo is not None
                assert hasattr(golden_repo, "clone_path")
                assert Path(golden_repo.clone_path).exists()

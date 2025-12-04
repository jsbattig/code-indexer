"""
Unit tests for meta description lifecycle hooks.

Tests the lifecycle hook infrastructure that creates/deletes .md files
in cidx-meta when golden repos are added/removed.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile
import shutil


@pytest.fixture
def temp_golden_repos_dir():
    """Create temporary golden repos directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def cidx_meta_path(temp_golden_repos_dir):
    """Create cidx-meta directory."""
    meta_path = Path(temp_golden_repos_dir) / "cidx-meta"
    meta_path.mkdir(parents=True)
    return meta_path


class TestOnRepoAdded:
    """Test on_repo_added hook functionality."""

    def test_creates_md_file_for_new_repo(self, cidx_meta_path, temp_golden_repos_dir):
        """Test that .md file is created when a golden repo is added."""
        from code_indexer.global_repos.meta_description_hook import on_repo_added
        from unittest.mock import MagicMock

        # Setup: Create a mock repository
        repo_name = "test-repo"
        repo_url = "https://github.com/test/repo"
        clone_path = Path(temp_golden_repos_dir) / repo_name
        clone_path.mkdir(parents=True)

        # Create a README.md to analyze
        (clone_path / "README.md").write_text("# Test Repo\nA test repository")

        # Mock ClaudeCliManager to be available
        mock_cli_manager = MagicMock()
        mock_cli_manager.check_cli_available.return_value = True

        # Execute: Call hook
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            with patch(
                "code_indexer.global_repos.meta_description_hook.ClaudeCliManager",
                return_value=mock_cli_manager,
            ):
                on_repo_added(
                    repo_name=repo_name,
                    repo_url=repo_url,
                    clone_path=str(clone_path),
                    golden_repos_dir=temp_golden_repos_dir,
                )

        # Verify: .md file was created
        md_file = cidx_meta_path / f"{repo_name}.md"
        assert md_file.exists(), f"Expected .md file at {md_file}"

        # Verify: File contains expected content
        content = md_file.read_text()
        assert repo_name in content
        assert repo_url in content

        # Verify: cidx index was called in cidx-meta directory
        # Find the cidx index call among all subprocess calls
        cidx_index_calls = [
            call for call in mock_run.call_args_list if call[0][0] == ["cidx", "index"]
        ]
        assert len(cidx_index_calls) == 1, "Expected exactly one 'cidx index' call"
        call_args = cidx_index_calls[0]
        assert call_args[1]["cwd"] == str(cidx_meta_path)

    def test_skips_cidx_meta_itself(self, cidx_meta_path, temp_golden_repos_dir):
        """Test that hook does not create .md file for cidx-meta itself."""
        from code_indexer.global_repos.meta_description_hook import on_repo_added

        # Execute: Call hook with cidx-meta as repo_name
        with patch("subprocess.run") as mock_run:
            on_repo_added(
                repo_name="cidx-meta",
                repo_url="local://cidx-meta",
                clone_path=str(cidx_meta_path),
                golden_repos_dir=temp_golden_repos_dir,
            )

        # Verify: No .md file was created
        md_file = cidx_meta_path / "cidx-meta.md"
        assert not md_file.exists(), "cidx-meta should not have its own .md file"

        # Verify: cidx index was NOT called
        mock_run.assert_not_called()

    def test_handles_missing_clone_path_gracefully(
        self, cidx_meta_path, temp_golden_repos_dir
    ):
        """Test that hook handles missing clone path without crashing."""
        from code_indexer.global_repos.meta_description_hook import on_repo_added

        repo_name = "missing-repo"
        repo_url = "https://github.com/test/missing"
        clone_path = Path(temp_golden_repos_dir) / "nonexistent"

        # Execute and verify: Should not crash
        with patch("subprocess.run"):
            on_repo_added(
                repo_name=repo_name,
                repo_url=repo_url,
                clone_path=str(clone_path),
                golden_repos_dir=temp_golden_repos_dir,
            )

        # Verify: No indexing was attempted (file creation failed gracefully)
        # (Actual behavior depends on implementation - we expect graceful handling)


class TestOnRepoRemoved:
    """Test on_repo_removed hook functionality."""

    def test_deletes_md_file_for_removed_repo(
        self, cidx_meta_path, temp_golden_repos_dir
    ):
        """Test that .md file is deleted when a golden repo is removed."""
        from code_indexer.global_repos.meta_description_hook import on_repo_removed

        # Setup: Create an existing .md file
        repo_name = "test-repo"
        md_file = cidx_meta_path / f"{repo_name}.md"
        md_file.write_text("# Test Repo\nDescription")

        assert md_file.exists(), "Setup: .md file should exist"

        # Execute: Call hook
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            on_repo_removed(repo_name=repo_name, golden_repos_dir=temp_golden_repos_dir)

        # Verify: .md file was deleted
        assert not md_file.exists(), f"Expected .md file to be deleted: {md_file}"

        # Verify: cidx index was called to re-index cidx-meta
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["cidx", "index"]
        assert call_args[1]["cwd"] == str(cidx_meta_path)

    def test_handles_nonexistent_md_file_gracefully(
        self, cidx_meta_path, temp_golden_repos_dir
    ):
        """Test that hook handles removal of nonexistent .md file without crashing."""
        from code_indexer.global_repos.meta_description_hook import on_repo_removed

        repo_name = "nonexistent-repo"
        md_file = cidx_meta_path / f"{repo_name}.md"

        assert not md_file.exists(), "Setup: .md file should not exist"

        # Execute and verify: Should not crash
        with patch("subprocess.run") as mock_run:
            on_repo_removed(repo_name=repo_name, golden_repos_dir=temp_golden_repos_dir)

        # Verify: No indexing was attempted (no file to delete)
        mock_run.assert_not_called()


class TestGoldenRepoManagerIntegration:
    """Test integration of hooks into GoldenRepoManager."""

    def test_add_golden_repo_calls_hook(self, temp_golden_repos_dir):
        """Test that adding a golden repo calls the on_repo_added hook."""

        # This test will verify that the hook is called during add_golden_repo
        # The actual implementation will be in golden_repo_manager.py
        pytest.skip(
            "Integration test - will implement after hook infrastructure is complete"
        )

    def test_remove_golden_repo_calls_hook(self, temp_golden_repos_dir):
        """Test that removing a golden repo calls the on_repo_removed hook."""

        # This test will verify that the hook is called during remove_golden_repo
        # The actual implementation will be in golden_repo_manager.py
        pytest.skip(
            "Integration test - will implement after hook infrastructure is complete"
        )

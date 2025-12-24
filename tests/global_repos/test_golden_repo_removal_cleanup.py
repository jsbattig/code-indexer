"""
Tests for golden repository removal cleanup.

Verifies that when a golden repo is REMOVED, all associated resources are properly cleaned up:
1. GlobalActivator.deactivate_golden_repo() is called
2. GlobalRegistry entry is removed
3. Alias pointer file is deleted
4. Meta-directory .md file is deleted
5. Meta-directory is re-indexed
"""

import json
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock


from code_indexer.server.repositories.golden_repo_manager import GoldenRepoManager
from code_indexer.server.repositories.background_jobs import BackgroundJobManager
from code_indexer.global_repos.global_registry import GlobalRegistry
from code_indexer.global_repos.global_activation import GlobalActivator


class TestGoldenRepoRemovalCleanup:
    """Test that golden repo removal properly cleans up all resources."""

    def _wait_for_job(
        self, manager: GoldenRepoManager, job_id: str, max_wait: float = 10.0
    ):
        """Wait for a background job to complete."""
        import time

        elapsed = 0.0
        while elapsed < max_wait:
            job_status = manager.background_job_manager.get_job_status(job_id, "admin")
            if job_status and job_status["status"] in ["completed", "failed"]:
                return job_status
            time.sleep(0.1)
            elapsed += 0.1
        return None

    def test_remove_golden_repo_calls_deactivate_golden_repo(self):
        """Test that remove_golden_repo() calls GlobalActivator.deactivate_golden_repo()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup test repo
            test_repo_dir = Path(tmpdir) / "test-repo"
            test_repo_dir.mkdir()
            (test_repo_dir / ".git").mkdir()
            (test_repo_dir / "test.py").write_text("def test(): pass")

            # Setup manager
            data_dir = Path(tmpdir) / "data"
            manager = GoldenRepoManager(str(data_dir))
            manager.background_job_manager = BackgroundJobManager()

            # Add a golden repo first
            with patch.object(manager, "_execute_post_clone_workflow"):
                with patch.object(
                    manager, "_validate_git_repository", return_value=True
                ):
                    job_id = manager.add_golden_repo(
                        repo_url=str(test_repo_dir),
                        alias="test-repo",
                        default_branch="main",
                    )
                    self._wait_for_job(manager, job_id)

            # Verify it was added
            assert manager.golden_repo_exists("test-repo")

            # Verify global activation occurred
            golden_repos_dir = Path(data_dir) / "golden-repos"
            registry = GlobalRegistry(str(golden_repos_dir))
            global_repos = registry.list_global_repos()
            assert len(global_repos) == 1
            assert global_repos[0]["alias_name"] == "test-repo-global"

            # Now remove the golden repo and verify deactivate_golden_repo is called
            with patch.object(
                GlobalActivator, "deactivate_golden_repo"
            ) as mock_deactivate:
                job_id = manager.remove_golden_repo(alias="test-repo")
                job_status = self._wait_for_job(manager, job_id)

                assert job_status is not None
                assert job_status["status"] == "completed"

                # Verify deactivate_golden_repo was called with correct repo name
                mock_deactivate.assert_called_once_with("test-repo")

    def test_remove_golden_repo_removes_registry_entry(self):
        """Test that remove_golden_repo() removes the GlobalRegistry entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup test repo
            test_repo_dir = Path(tmpdir) / "test-repo"
            test_repo_dir.mkdir()
            (test_repo_dir / ".git").mkdir()
            (test_repo_dir / "test.py").write_text("def test(): pass")

            # Setup manager
            data_dir = Path(tmpdir) / "data"
            manager = GoldenRepoManager(str(data_dir))
            manager.background_job_manager = BackgroundJobManager()

            # Add a golden repo first
            with patch.object(manager, "_execute_post_clone_workflow"):
                with patch.object(
                    manager, "_validate_git_repository", return_value=True
                ):
                    job_id = manager.add_golden_repo(
                        repo_url=str(test_repo_dir),
                        alias="test-repo",
                        default_branch="main",
                    )
                    self._wait_for_job(manager, job_id)

            # Verify global activation occurred
            golden_repos_dir = Path(data_dir) / "golden-repos"
            registry = GlobalRegistry(str(golden_repos_dir))
            global_repos = registry.list_global_repos()
            assert any(r["alias_name"] == "test-repo-global" for r in global_repos)

            # Remove the golden repo
            job_id = manager.remove_golden_repo(alias="test-repo")
            job_status = self._wait_for_job(manager, job_id)

            assert job_status is not None
            assert job_status["status"] == "completed"

            # Verify registry entry was removed
            registry = GlobalRegistry(str(golden_repos_dir))  # Reload
            global_repos = registry.list_global_repos()
            assert not any(r["alias_name"] == "test-repo-global" for r in global_repos)

    def test_remove_golden_repo_removes_alias_pointer_file(self):
        """Test that remove_golden_repo() removes the alias pointer file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup test repo
            test_repo_dir = Path(tmpdir) / "test-repo"
            test_repo_dir.mkdir()
            (test_repo_dir / ".git").mkdir()
            (test_repo_dir / "test.py").write_text("def test(): pass")

            # Setup manager
            data_dir = Path(tmpdir) / "data"
            manager = GoldenRepoManager(str(data_dir))
            manager.background_job_manager = BackgroundJobManager()

            # Add a golden repo first
            with patch.object(manager, "_execute_post_clone_workflow"):
                with patch.object(
                    manager, "_validate_git_repository", return_value=True
                ):
                    job_id = manager.add_golden_repo(
                        repo_url=str(test_repo_dir),
                        alias="test-repo",
                        default_branch="main",
                    )
                    self._wait_for_job(manager, job_id)

            # Verify alias file exists
            golden_repos_dir = Path(data_dir) / "golden-repos"
            alias_file = golden_repos_dir / "aliases" / "test-repo-global.json"
            assert alias_file.exists(), "Alias file should exist after adding repo"

            # Remove the golden repo
            job_id = manager.remove_golden_repo(alias="test-repo")
            job_status = self._wait_for_job(manager, job_id)

            assert job_status is not None
            assert job_status["status"] == "completed"

            # Verify alias file was deleted
            assert not alias_file.exists(), "Alias file should be deleted after removal"


class TestGlobalActivatorDeactivateMetaCleanup:
    """Test that deactivate_golden_repo() cleans up meta-directory .md file."""

    def test_deactivate_golden_repo_deletes_meta_description_file(self):
        """Test that deactivate_golden_repo() deletes the meta-directory .md file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            golden_repos_dir.mkdir()

            # Create meta-directory structure
            meta_dir = golden_repos_dir / "cidx-meta"
            meta_dir.mkdir()

            # Create aliases directory
            aliases_dir = golden_repos_dir / "aliases"
            aliases_dir.mkdir()

            # Create a mock repo entry in registry
            registry = GlobalRegistry(str(golden_repos_dir))
            registry.register_global_repo(
                repo_name="test-repo",
                alias_name="test-repo-global",
                repo_url="https://github.com/test/test-repo",
                index_path=str(golden_repos_dir / "test-repo"),
            )

            # Create alias pointer file
            alias_file = aliases_dir / "test-repo-global.json"
            alias_data = {
                "alias_name": "test-repo-global",
                "target_path": str(golden_repos_dir / "test-repo"),
                "repo_name": "test-repo",
            }
            alias_file.write_text(json.dumps(alias_data))

            # Create the meta-directory description file that should be deleted
            # File name is {repo_name}.md (NOT {alias_name}.md)
            meta_description_file = meta_dir / "test-repo.md"
            meta_description_file.write_text(
                """---
name: test-repo
url: https://github.com/test/test-repo
technologies:
  - Python
purpose: Test repository
---

# test-repo

A test repository for unit testing.
"""
            )
            assert meta_description_file.exists()

            # Deactivate the golden repo
            activator = GlobalActivator(str(golden_repos_dir))
            activator.deactivate_golden_repo("test-repo")

            # Verify the meta description file was deleted
            assert (
                not meta_description_file.exists()
            ), "Meta-directory .md file should be deleted after deactivation"


class TestMetaDirectoryReIndexing:
    """Test that meta-directory is re-indexed after golden repo removal."""

    def test_deactivate_golden_repo_triggers_meta_directory_reindex(self):
        """Test that deactivate_golden_repo() triggers cidx index on meta-directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            golden_repos_dir.mkdir()

            # Create meta-directory with .code-indexer init
            meta_dir = golden_repos_dir / "cidx-meta"
            meta_dir.mkdir()
            (meta_dir / ".code-indexer").mkdir()  # Mark as initialized

            # Create aliases directory
            aliases_dir = golden_repos_dir / "aliases"
            aliases_dir.mkdir()

            # Create a mock repo entry in registry
            registry = GlobalRegistry(str(golden_repos_dir))
            registry.register_global_repo(
                repo_name="test-repo",
                alias_name="test-repo-global",
                repo_url="https://github.com/test/test-repo",
                index_path=str(golden_repos_dir / "test-repo"),
            )

            # Create alias pointer file
            alias_file = aliases_dir / "test-repo-global.json"
            alias_data = {
                "alias_name": "test-repo-global",
                "target_path": str(golden_repos_dir / "test-repo"),
                "repo_name": "test-repo",
            }
            alias_file.write_text(json.dumps(alias_data))

            # Create meta-directory description file
            meta_description_file = meta_dir / "test-repo.md"
            meta_description_file.write_text("# test-repo\nTest content")

            # Mock subprocess.run to capture the cidx index call
            original_run = subprocess.run
            index_calls = []

            def mock_subprocess_run(cmd, **kwargs):
                if isinstance(cmd, list) and "cidx" in cmd[0]:
                    index_calls.append((cmd, kwargs))
                    # Return success for cidx commands
                    return MagicMock(returncode=0, stdout="", stderr="")
                return original_run(cmd, **kwargs)

            with patch("subprocess.run", side_effect=mock_subprocess_run):
                activator = GlobalActivator(str(golden_repos_dir))
                activator.deactivate_golden_repo("test-repo")

            # Verify cidx index was called on meta-directory
            assert (
                len(index_calls) > 0
            ), "cidx index should be called on meta-directory after deactivation"

            # Find the index call
            index_call = None
            for call_args, call_kwargs in index_calls:
                if "index" in call_args:
                    index_call = (call_args, call_kwargs)
                    break

            assert index_call is not None, "cidx index command should be in the calls"

            # Verify it was called with cwd set to meta-directory
            _, kwargs = index_call
            assert "cwd" in kwargs
            assert kwargs["cwd"] == str(meta_dir)


class TestGoldenRepoRemovalIntegration:
    """Integration tests for complete golden repo removal workflow."""

    def _wait_for_job(
        self, manager: GoldenRepoManager, job_id: str, max_wait: float = 10.0
    ):
        """Wait for a background job to complete."""
        import time

        elapsed = 0.0
        while elapsed < max_wait:
            job_status = manager.background_job_manager.get_job_status(job_id, "admin")
            if job_status and job_status["status"] in ["completed", "failed"]:
                return job_status
            time.sleep(0.1)
            elapsed += 0.1
        return None

    def test_full_removal_cleanup_workflow(self):
        """Test complete removal workflow cleans up all resources."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup test repo
            test_repo_dir = Path(tmpdir) / "test-repo"
            test_repo_dir.mkdir()
            (test_repo_dir / ".git").mkdir()
            (test_repo_dir / "test.py").write_text("def test(): pass")

            # Setup manager
            data_dir = Path(tmpdir) / "data"
            manager = GoldenRepoManager(str(data_dir))
            manager.background_job_manager = BackgroundJobManager()

            # Add a golden repo first
            with patch.object(manager, "_execute_post_clone_workflow"):
                with patch.object(
                    manager, "_validate_git_repository", return_value=True
                ):
                    job_id = manager.add_golden_repo(
                        repo_url=str(test_repo_dir),
                        alias="test-repo",
                        default_branch="main",
                    )
                    self._wait_for_job(manager, job_id)

            # Setup meta-directory to simulate full environment
            golden_repos_dir = Path(data_dir) / "golden-repos"
            meta_dir = golden_repos_dir / "cidx-meta"
            meta_dir.mkdir(exist_ok=True)

            # Create meta-directory description file
            meta_description_file = meta_dir / "test-repo.md"
            meta_description_file.write_text("# test-repo\nTest content")

            # Verify all resources exist before removal
            registry = GlobalRegistry(str(golden_repos_dir))
            assert manager.golden_repo_exists("test-repo")
            assert any(
                r["alias_name"] == "test-repo-global"
                for r in registry.list_global_repos()
            )
            alias_file = golden_repos_dir / "aliases" / "test-repo-global.json"
            assert alias_file.exists()
            assert meta_description_file.exists()

            # Remove the golden repo (mock subprocess to avoid actual cidx calls)
            with patch("subprocess.run", return_value=MagicMock(returncode=0)):
                job_id = manager.remove_golden_repo(alias="test-repo")
                job_status = self._wait_for_job(manager, job_id)

            assert job_status is not None
            assert job_status["status"] == "completed"

            # Verify all resources were cleaned up
            assert not manager.golden_repo_exists(
                "test-repo"
            ), "Golden repo should be removed from manager"

            registry = GlobalRegistry(str(golden_repos_dir))  # Reload
            assert not any(
                r["alias_name"] == "test-repo-global"
                for r in registry.list_global_repos()
            ), "Registry entry should be removed"

            assert not alias_file.exists(), "Alias file should be deleted"

            assert (
                not meta_description_file.exists()
            ), "Meta-directory .md file should be deleted"


class TestGoldenRepoDeactivationErrorHandling:
    """Test error handling during deactivation."""

    def test_deactivation_handles_missing_meta_file_gracefully(self):
        """Test that deactivation doesn't fail if meta file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            golden_repos_dir.mkdir()

            # Create meta-directory (but no .md file)
            meta_dir = golden_repos_dir / "cidx-meta"
            meta_dir.mkdir()

            # Create aliases directory
            aliases_dir = golden_repos_dir / "aliases"
            aliases_dir.mkdir()

            # Create a mock repo entry in registry
            registry = GlobalRegistry(str(golden_repos_dir))
            registry.register_global_repo(
                repo_name="test-repo",
                alias_name="test-repo-global",
                repo_url="https://github.com/test/test-repo",
                index_path=str(golden_repos_dir / "test-repo"),
            )

            # Create alias pointer file
            alias_file = aliases_dir / "test-repo-global.json"
            alias_data = {
                "alias_name": "test-repo-global",
                "target_path": str(golden_repos_dir / "test-repo"),
                "repo_name": "test-repo",
            }
            alias_file.write_text(json.dumps(alias_data))

            # Note: No meta description file created

            # Deactivate should not raise an error
            activator = GlobalActivator(str(golden_repos_dir))
            activator.deactivate_golden_repo("test-repo")

            # Verify registry and alias were still cleaned up
            registry = GlobalRegistry(str(golden_repos_dir))  # Reload
            assert not any(
                r["alias_name"] == "test-repo-global"
                for r in registry.list_global_repos()
            )
            assert not alias_file.exists()

    def test_deactivation_handles_missing_meta_directory_gracefully(self):
        """Test that deactivation doesn't fail if meta-directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            golden_repos_dir.mkdir()

            # Note: No meta-directory created

            # Create aliases directory
            aliases_dir = golden_repos_dir / "aliases"
            aliases_dir.mkdir()

            # Create a mock repo entry in registry
            registry = GlobalRegistry(str(golden_repos_dir))
            registry.register_global_repo(
                repo_name="test-repo",
                alias_name="test-repo-global",
                repo_url="https://github.com/test/test-repo",
                index_path=str(golden_repos_dir / "test-repo"),
            )

            # Create alias pointer file
            alias_file = aliases_dir / "test-repo-global.json"
            alias_data = {
                "alias_name": "test-repo-global",
                "target_path": str(golden_repos_dir / "test-repo"),
                "repo_name": "test-repo",
            }
            alias_file.write_text(json.dumps(alias_data))

            # Deactivate should not raise an error
            activator = GlobalActivator(str(golden_repos_dir))
            activator.deactivate_golden_repo("test-repo")

            # Verify registry and alias were still cleaned up
            registry = GlobalRegistry(str(golden_repos_dir))  # Reload
            assert not any(
                r["alias_name"] == "test-repo-global"
                for r in registry.list_global_repos()
            )
            assert not alias_file.exists()

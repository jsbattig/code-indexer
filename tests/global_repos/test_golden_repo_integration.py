"""
Integration tests for golden repo automatic global activation.

Tests the integration between GoldenRepoManager and GlobalActivator.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from code_indexer.server.repositories.golden_repo_manager import GoldenRepoManager
from code_indexer.server.repositories.background_jobs import BackgroundJobManager
from code_indexer.global_repos.global_registry import GlobalRegistry


class TestGoldenRepoGlobalActivationIntegration:
    """Test integration between golden repo registration and global activation."""

    def test_golden_repo_add_automatically_creates_global_activation(self):
        """Test that adding a golden repo automatically activates it globally (AC1)."""
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

            # Mock the post-clone workflow to skip actual indexing
            with patch.object(manager, "_execute_post_clone_workflow"):
                with patch.object(
                    manager, "_validate_git_repository", return_value=True
                ):
                    # Add golden repo
                    job_id = manager.add_golden_repo(
                        repo_url=str(test_repo_dir),
                        alias="test-repo",
                        default_branch="main",
                    )

                    # Wait for background job to complete
                    import time

                    max_wait = 10
                    elapsed = 0
                    while elapsed < max_wait:
                        job_status = manager.background_job_manager.get_job_status(
                            job_id, "admin"
                        )
                        if job_status and job_status["status"] == "completed":
                            break
                        time.sleep(0.1)
                        elapsed += 0.1

            # Verify golden repo was added
            assert manager.golden_repo_exists("test-repo")

            # Verify global activation occurred
            golden_repos_dir = Path(data_dir) / "golden-repos"
            registry = GlobalRegistry(str(golden_repos_dir))
            global_repos = registry.list_global_repos()

            assert len(global_repos) == 1
            assert global_repos[0]["repo_name"] == "test-repo"
            assert global_repos[0]["alias_name"] == "test-repo-global"

            # Verify alias file exists
            alias_file = golden_repos_dir / "aliases" / "test-repo-global.json"
            assert alias_file.exists()

            # Verify alias points to correct path
            with open(alias_file) as f:
                alias_data = json.load(f)
            assert "target_path" in alias_data

    def test_global_activation_failure_does_not_prevent_golden_repo_registration(self):
        """Test that global activation failure doesn't prevent golden repo registration (AC4)."""
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

            # Mock post-clone workflow
            with patch.object(manager, "_execute_post_clone_workflow"):
                with patch.object(
                    manager, "_validate_git_repository", return_value=True
                ):
                    # Make global activation fail by making aliases dir read-only
                    golden_repos_dir = Path(data_dir) / "golden-repos"
                    golden_repos_dir.mkdir(parents=True, exist_ok=True)
                    aliases_dir = golden_repos_dir / "aliases"
                    aliases_dir.mkdir(parents=True, exist_ok=True)

                    # We'll patch GlobalActivator to raise an error
                    from code_indexer.global_repos.global_activation import (
                        GlobalActivator,
                    )

                    def failing_activate(self, repo_name, repo_url, clone_path):
                        raise RuntimeError("Simulated global activation failure")

                    with patch.object(
                        GlobalActivator, "activate_golden_repo", failing_activate
                    ):
                        # Add golden repo
                        job_id = manager.add_golden_repo(
                            repo_url=str(test_repo_dir),
                            alias="test-repo",
                            default_branch="main",
                        )

                        # Wait for background job to complete
                        import time

                        max_wait = 10
                        elapsed = 0
                        while elapsed < max_wait:
                            job_status = manager.background_job_manager.get_job_status(
                                job_id, "admin"
                            )
                            if job_status and job_status["status"] in [
                                "completed",
                                "failed",
                            ]:
                                break
                            time.sleep(0.1)
                            elapsed += 0.1

            # Verify golden repo was STILL added despite global activation failure
            assert manager.golden_repo_exists("test-repo")

            # Verify job completed successfully
            job_status = manager.background_job_manager.get_job_status(job_id, "admin")
            assert job_status["status"] == "completed"

    def test_multiple_golden_repos_create_multiple_global_activations(self):
        """Test that multiple golden repos create multiple global activations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup manager
            data_dir = Path(tmpdir) / "data"
            manager = GoldenRepoManager(str(data_dir))
            manager.background_job_manager = BackgroundJobManager()

            # Create multiple test repos
            for i in range(3):
                test_repo_dir = Path(tmpdir) / f"test-repo-{i}"
                test_repo_dir.mkdir()
                (test_repo_dir / ".git").mkdir()
                (test_repo_dir / "test.py").write_text(f"def test{i}(): pass")

                with patch.object(manager, "_execute_post_clone_workflow"):
                    with patch.object(
                        manager, "_validate_git_repository", return_value=True
                    ):
                        job_id = manager.add_golden_repo(
                            repo_url=str(test_repo_dir),
                            alias=f"test-repo-{i}",
                            default_branch="main",
                        )

                        # Wait for job to complete
                        import time

                        max_wait = 10
                        elapsed = 0
                        while elapsed < max_wait:
                            job_status = manager.background_job_manager.get_job_status(
                                job_id, "admin"
                            )
                            if job_status and job_status["status"] == "completed":
                                break
                            time.sleep(0.1)
                            elapsed += 0.1

            # Verify all repos were added
            assert len(manager.list_golden_repos()) == 3

            # Verify all global activations occurred
            golden_repos_dir = Path(data_dir) / "golden-repos"
            registry = GlobalRegistry(str(golden_repos_dir))
            global_repos = registry.list_global_repos()

            assert len(global_repos) == 3
            for i in range(3):
                assert any(
                    repo["alias_name"] == f"test-repo-{i}-global"
                    for repo in global_repos
                )

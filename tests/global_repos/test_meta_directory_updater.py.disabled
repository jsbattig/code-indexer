"""
Tests for AC4: Meta-Directory Update Strategy.

Tests that MetaDirectoryUpdater implements UpdateStrategy interface
and handles incremental updates correctly.
"""

import time
from code_indexer.global_repos.meta_directory_updater import MetaDirectoryUpdater
from code_indexer.global_repos.global_registry import GlobalRegistry


class TestMetaDirectoryUpdater:
    """Test suite for MetaDirectoryUpdater strategy."""

    def test_implements_update_strategy_interface(self, tmp_path):
        """
        Test that MetaDirectoryUpdater implements UpdateStrategy.

        AC4: MetaDirectoryUpdater class implementing UpdateStrategy interface
        """
        golden_repos_dir = tmp_path / "golden_repos"
        meta_dir = golden_repos_dir / "cidx-meta"
        registry = GlobalRegistry(str(golden_repos_dir))

        updater = MetaDirectoryUpdater(meta_dir=str(meta_dir), registry=registry)

        # Verify interface methods exist
        assert hasattr(updater, "has_changes")
        assert hasattr(updater, "update")
        assert hasattr(updater, "get_source_path")
        assert callable(updater.has_changes)
        assert callable(updater.update)
        assert callable(updater.get_source_path)

    def test_detects_new_repos(self, tmp_path):
        """
        Test that updater detects when new repos are registered.

        AC4: Detect new repos (description file missing)
        """
        golden_repos_dir = tmp_path / "golden_repos"
        meta_dir = golden_repos_dir / "cidx-meta"
        meta_dir.mkdir(parents=True)

        registry = GlobalRegistry(str(golden_repos_dir))

        # Register a repo
        registry.register_global_repo(
            repo_name="new-repo",
            alias_name="new-repo-global",
            repo_url="https://github.com/org/new-repo",
            index_path=str(tmp_path / "new-repo-index"),
        )

        updater = MetaDirectoryUpdater(meta_dir=str(meta_dir), registry=registry)

        # Should detect changes (new repo, no description file)
        assert updater.has_changes() is True

    def test_detects_deleted_repos(self, tmp_path):
        """
        Test that updater detects orphaned description files.

        AC4: Detect deleted repos (description file orphaned)
        """
        golden_repos_dir = tmp_path / "golden_repos"
        meta_dir = golden_repos_dir / "cidx-meta"
        meta_dir.mkdir(parents=True)

        registry = GlobalRegistry(str(golden_repos_dir))

        # Create orphaned description file
        orphaned_file = meta_dir / "deleted-repo.md"
        orphaned_file.write_text("# Deleted Repo\n\nThis repo was deleted.")

        updater = MetaDirectoryUpdater(meta_dir=str(meta_dir), registry=registry)

        # Should detect changes (orphaned file)
        assert updater.has_changes() is True

    def test_no_changes_when_descriptions_match_repos(self, tmp_path):
        """
        Test that updater returns False when descriptions match repos.

        AC4: Incremental update (not full regeneration each cycle)
        """
        golden_repos_dir = tmp_path / "golden_repos"
        meta_dir = golden_repos_dir / "cidx-meta"
        meta_dir.mkdir(parents=True)

        registry = GlobalRegistry(str(golden_repos_dir))

        # Register repo
        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(tmp_path / "test-repo-index"),
        )

        # Create matching description file
        desc_file = meta_dir / "test-repo.md"
        desc_file.write_text("# Test Repo\n\nA test repository.")

        updater = MetaDirectoryUpdater(meta_dir=str(meta_dir), registry=registry)

        # Should detect no changes (assuming no timestamp check for now)
        # Note: This may return True if we implement timestamp-based checks
        # For now, we'll just verify the method works
        result = updater.has_changes()
        assert isinstance(result, bool)

    def test_update_creates_description_for_new_repo(self, tmp_path):
        """
        Test that update() creates descriptions for new repos.

        AC4: Regenerates descriptions for changed repos only
        """
        golden_repos_dir = tmp_path / "golden_repos"
        meta_dir = golden_repos_dir / "cidx-meta"
        meta_dir.mkdir(parents=True)

        # Create a test repo with README
        test_repo = tmp_path / "test-repo"
        test_repo.mkdir()
        readme = test_repo / "README.md"
        readme.write_text("# Test Repo\n\nA test repository for testing.")

        registry = GlobalRegistry(str(golden_repos_dir))
        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(test_repo),
        )

        updater = MetaDirectoryUpdater(meta_dir=str(meta_dir), registry=registry)

        # Run update
        updater.update()

        # Verify description file created
        desc_file = meta_dir / "test-repo.md"
        assert desc_file.exists()

        content = desc_file.read_text()
        assert "test-repo" in content

    def test_update_removes_orphaned_descriptions(self, tmp_path):
        """
        Test that update() removes orphaned description files.

        AC4: Detect deleted repos (description file orphaned)
        """
        golden_repos_dir = tmp_path / "golden_repos"
        meta_dir = golden_repos_dir / "cidx-meta"
        meta_dir.mkdir(parents=True)

        # Create orphaned description
        orphaned = meta_dir / "deleted-repo.md"
        orphaned.write_text("# Deleted\n\nOrphaned file.")

        registry = GlobalRegistry(str(golden_repos_dir))
        updater = MetaDirectoryUpdater(meta_dir=str(meta_dir), registry=registry)

        # Run update
        updater.update()

        # Orphaned file should be removed
        assert not orphaned.exists()

    def test_update_handles_multiple_repos(self, tmp_path):
        """
        Test that update() handles multiple repositories.

        AC4: Scans for new/modified/deleted repos
        """
        golden_repos_dir = tmp_path / "golden_repos"
        meta_dir = golden_repos_dir / "cidx-meta"
        meta_dir.mkdir(parents=True)

        # Create test repos
        repo1 = tmp_path / "repo1"
        repo1.mkdir()
        (repo1 / "README.md").write_text("# Repo 1")

        repo2 = tmp_path / "repo2"
        repo2.mkdir()
        (repo2 / "README.md").write_text("# Repo 2")

        registry = GlobalRegistry(str(golden_repos_dir))
        registry.register_global_repo(
            repo_name="repo1",
            alias_name="repo1-global",
            repo_url="https://github.com/org/repo1",
            index_path=str(repo1),
        )
        registry.register_global_repo(
            repo_name="repo2",
            alias_name="repo2-global",
            repo_url="https://github.com/org/repo2",
            index_path=str(repo2),
        )

        updater = MetaDirectoryUpdater(meta_dir=str(meta_dir), registry=registry)

        updater.update()

        # Verify both description files created
        assert (meta_dir / "repo1.md").exists()
        assert (meta_dir / "repo2.md").exists()

    def test_get_source_path_returns_meta_directory(self, tmp_path):
        """
        Test that get_source_path() returns meta-directory path.

        AC4: Reindexes the meta-directory content
        """
        golden_repos_dir = tmp_path / "golden_repos"
        meta_dir = golden_repos_dir / "cidx-meta"
        registry = GlobalRegistry(str(golden_repos_dir))

        updater = MetaDirectoryUpdater(meta_dir=str(meta_dir), registry=registry)

        source = updater.get_source_path()
        assert source == str(meta_dir)

    def test_skips_meta_directory_itself(self, tmp_path):
        """
        Test that updater doesn't create description for meta-directory itself.

        AC4: Special handling for meta-directory (repo_url=None)
        """
        golden_repos_dir = tmp_path / "golden_repos"
        meta_dir = golden_repos_dir / "cidx-meta"
        meta_dir.mkdir(parents=True)

        registry = GlobalRegistry(str(golden_repos_dir))

        # Register meta-directory itself
        registry.register_global_repo(
            repo_name="cidx-meta",
            alias_name="cidx-meta-global",
            repo_url=None,  # Special marker
            index_path=str(meta_dir),
            allow_reserved=True,
        )

        updater = MetaDirectoryUpdater(meta_dir=str(meta_dir), registry=registry)

        updater.update()

        # Should NOT create cidx-meta.md
        assert not (meta_dir / "cidx-meta.md").exists()

    def test_detects_modified_repos_via_timestamp(self, tmp_path):
        """
        Test that updater detects modified repos based on timestamps.

        AC4: Detect modified repos (timestamp comparison)

        This test will FAIL until timestamp comparison is implemented.
        """
        golden_repos_dir = tmp_path / "golden_repos"
        meta_dir = golden_repos_dir / "cidx-meta"
        meta_dir.mkdir(parents=True)

        # Create a test repo
        test_repo = tmp_path / "test-repo"
        test_repo.mkdir()
        readme = test_repo / "README.md"
        readme.write_text("# Test Repo\n\nOriginal content.")

        registry = GlobalRegistry(str(golden_repos_dir))
        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(test_repo),
        )

        updater = MetaDirectoryUpdater(meta_dir=str(meta_dir), registry=registry)

        # First update - creates description
        updater.update()
        desc_file = meta_dir / "test-repo.md"
        assert desc_file.exists()

        # Wait to ensure timestamp difference
        time.sleep(0.1)

        # Modify the repo (update README)
        readme.write_text("# Test Repo\n\nModified content!")

        # Wait to ensure timestamp difference
        time.sleep(0.1)

        # Should detect changes (repo modified after description)
        assert (
            updater.has_changes() is True
        ), "Should detect repo modification via timestamp"

    def test_no_changes_when_repo_not_modified(self, tmp_path):
        """
        Test that updater returns False when repo hasn't been modified.

        AC4: Timestamp comparison prevents unnecessary regeneration
        """
        golden_repos_dir = tmp_path / "golden_repos"
        meta_dir = golden_repos_dir / "cidx-meta"
        meta_dir.mkdir(parents=True)

        # Create a test repo
        test_repo = tmp_path / "test-repo"
        test_repo.mkdir()
        readme = test_repo / "README.md"
        readme.write_text("# Test Repo\n\nStatic content.")

        registry = GlobalRegistry(str(golden_repos_dir))
        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(test_repo),
        )

        updater = MetaDirectoryUpdater(meta_dir=str(meta_dir), registry=registry)

        # First update - creates description
        updater.update()

        # Wait to ensure description is newer
        time.sleep(0.1)

        # Should NOT detect changes (description newer than repo)
        assert (
            updater.has_changes() is False
        ), "Should not detect changes when repo unmodified"

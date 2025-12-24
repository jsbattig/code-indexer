"""
Tests for AC5: Migration of Existing Repos.

Tests that the meta-directory initializer handles migration of
existing repos when meta-directory is first created.
"""

from code_indexer.global_repos.meta_directory_initializer import (
    MetaDirectoryInitializer,
)
from code_indexer.global_repos.global_registry import GlobalRegistry


class TestMetaDirectoryMigration:
    """Test suite for meta-directory migration and initialization."""

    def test_initializer_creates_meta_directory(self, tmp_path):
        """
        Test that initializer creates meta-directory.

        AC5: On first meta-directory creation
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        initializer = MetaDirectoryInitializer(
            golden_repos_dir=str(golden_repos_dir), registry=registry
        )

        meta_dir = initializer.initialize()

        assert meta_dir.exists()
        assert meta_dir.is_dir()
        assert meta_dir.name == "cidx-meta"

    def test_migration_generates_descriptions_for_existing_repos(self, tmp_path):
        """
        Test that migration generates descriptions for all existing repos.

        AC5: Descriptions generated for all existing repos
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        # Register existing repos
        repo1 = tmp_path / "repo1"
        repo1.mkdir()
        (repo1 / "README.md").write_text("# Repo 1\n\nFirst repository.")

        repo2 = tmp_path / "repo2"
        repo2.mkdir()
        (repo2 / "README.md").write_text("# Repo 2\n\nSecond repository.")

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

        # Initialize meta-directory (migration)
        initializer = MetaDirectoryInitializer(
            golden_repos_dir=str(golden_repos_dir), registry=registry
        )
        meta_dir = initializer.initialize()

        # Verify descriptions created
        assert (meta_dir / "repo1.md").exists()
        assert (meta_dir / "repo2.md").exists()

    def test_migration_logs_progress(self, tmp_path, caplog):
        """
        Test that migration logs progress.

        AC5: Log migration progress
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        # Register multiple repos
        for i in range(3):
            repo = tmp_path / f"repo{i}"
            repo.mkdir()
            (repo / "README.md").write_text(f"# Repo {i}")

            registry.register_global_repo(
                repo_name=f"repo{i}",
                alias_name=f"repo{i}-global",
                repo_url=f"https://github.com/org/repo{i}",
                index_path=str(repo),
            )

        initializer = MetaDirectoryInitializer(
            golden_repos_dir=str(golden_repos_dir), registry=registry
        )

        with caplog.at_level("INFO"):
            initializer.initialize()

        # Verify progress was logged
        assert any("Meta-directory" in record.message for record in caplog.records)

    def test_migration_handles_large_number_of_repos(self, tmp_path):
        """
        Test that migration handles many repos gracefully.

        AC5: Handle large numbers of repos gracefully
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        # Register many repos
        num_repos = 20
        for i in range(num_repos):
            repo = tmp_path / f"repo{i}"
            repo.mkdir()
            (repo / "README.md").write_text(f"# Repo {i}")

            registry.register_global_repo(
                repo_name=f"repo{i}",
                alias_name=f"repo{i}-global",
                repo_url=f"https://github.com/org/repo{i}",
                index_path=str(repo),
            )

        initializer = MetaDirectoryInitializer(
            golden_repos_dir=str(golden_repos_dir), registry=registry
        )
        meta_dir = initializer.initialize()

        # Verify all descriptions created
        desc_files = list(meta_dir.glob("*.md"))
        assert len(desc_files) == num_repos

    def test_migration_is_idempotent(self, tmp_path):
        """
        Test that running migration multiple times is safe.

        AC5: Feature immediately useful without re-registration
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        repo = tmp_path / "repo1"
        repo.mkdir()
        (repo / "README.md").write_text("# Repo 1")

        registry.register_global_repo(
            repo_name="repo1",
            alias_name="repo1-global",
            repo_url="https://github.com/org/repo1",
            index_path=str(repo),
        )

        initializer = MetaDirectoryInitializer(
            golden_repos_dir=str(golden_repos_dir), registry=registry
        )

        # Run migration twice
        meta_dir1 = initializer.initialize()
        meta_dir2 = initializer.initialize()

        # Both should succeed
        assert meta_dir1 == meta_dir2
        assert (meta_dir2 / "repo1.md").exists()

    def test_registers_meta_directory_as_global_repo(self, tmp_path):
        """
        Test that initializer registers meta-directory as global repo.

        AC5: Meta-directory is indexed
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        initializer = MetaDirectoryInitializer(
            golden_repos_dir=str(golden_repos_dir), registry=registry
        )
        initializer.initialize()

        # Verify meta-directory registered
        meta_repo = registry.get_global_repo("cidx-meta-global")
        assert meta_repo is not None
        assert meta_repo["repo_url"] is None

    def test_skips_meta_directory_in_batch_generation(self, tmp_path):
        """
        Test that migration doesn't create description for meta-directory itself.

        AC5: Batch generation for repos only
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        # Register regular repo
        repo = tmp_path / "repo1"
        repo.mkdir()
        (repo / "README.md").write_text("# Repo 1")

        registry.register_global_repo(
            repo_name="repo1",
            alias_name="repo1-global",
            repo_url="https://github.com/org/repo1",
            index_path=str(repo),
        )

        # Initialize (also registers meta-directory)
        initializer = MetaDirectoryInitializer(
            golden_repos_dir=str(golden_repos_dir), registry=registry
        )
        meta_dir = initializer.initialize()

        # Should have description for repo1 only
        assert (meta_dir / "repo1.md").exists()
        assert not (meta_dir / "cidx-meta.md").exists()

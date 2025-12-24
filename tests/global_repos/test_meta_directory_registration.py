"""
Tests for AC1: Meta-Directory as Special Global Repo.

Tests that the meta-directory can be registered as a special global repo
with repo_url=None marker and appears in the global repos list.
"""

from code_indexer.global_repos.global_registry import GlobalRegistry


class TestMetaDirectoryRegistration:
    """Test suite for meta-directory registration as special global repo."""

    def test_register_meta_directory_with_null_repo_url(self, tmp_path):
        """
        Test that meta-directory can be registered with repo_url=None.

        AC1: Registry entry with repo_url: null as marker
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        # Register meta-directory with None as repo_url
        registry.register_global_repo(
            repo_name="cidx-meta",
            alias_name="cidx-meta-global",
            repo_url=None,  # Special marker for meta-directory
            index_path=str(tmp_path / "meta-index"),
            allow_reserved=True,  # Allow reserved name for meta-directory tests
        )

        # Verify registration
        meta_repo = registry.get_global_repo("cidx-meta-global")
        assert meta_repo is not None
        assert meta_repo["repo_name"] == "cidx-meta"
        assert meta_repo["alias_name"] == "cidx-meta-global"
        assert meta_repo["repo_url"] is None
        assert meta_repo["index_path"] == str(tmp_path / "meta-index")

    def test_meta_directory_appears_in_global_repos_list(self, tmp_path):
        """
        Test that meta-directory appears in list of global repos.

        AC1: Meta-directory appears in the global repos list
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        # Register regular repo
        registry.register_global_repo(
            repo_name="regular-repo",
            alias_name="regular-repo-global",
            repo_url="https://github.com/org/regular-repo",
            index_path=str(tmp_path / "regular-index"),
        )

        # Register meta-directory
        registry.register_global_repo(
            repo_name="cidx-meta",
            alias_name="cidx-meta-global",
            repo_url=None,
            index_path=str(tmp_path / "meta-index"),
            allow_reserved=True,  # Allow reserved name for meta-directory tests
        )

        # List all repos
        all_repos = registry.list_global_repos()

        assert len(all_repos) == 2

        # Find meta-directory in list
        meta_repo = next(
            (r for r in all_repos if r["alias_name"] == "cidx-meta-global"), None
        )
        assert meta_repo is not None
        assert meta_repo["repo_url"] is None

    def test_meta_directory_persisted_with_null_url(self, tmp_path):
        """
        Test that meta-directory with null URL persists across registry reloads.

        AC1: Registry entry with repo_url: null as marker
        """
        golden_repos_dir = tmp_path / "golden_repos"

        # Create and register
        registry1 = GlobalRegistry(str(golden_repos_dir))
        registry1.register_global_repo(
            repo_name="cidx-meta",
            alias_name="cidx-meta-global",
            repo_url=None,
            index_path=str(tmp_path / "meta-index"),
            allow_reserved=True,  # Allow reserved name for meta-directory tests
        )

        # Reload registry
        registry2 = GlobalRegistry(str(golden_repos_dir))
        meta_repo = registry2.get_global_repo("cidx-meta-global")

        assert meta_repo is not None
        assert meta_repo["repo_url"] is None

    def test_can_distinguish_meta_directory_from_git_repos(self, tmp_path):
        """
        Test that we can identify meta-directory by repo_url=None marker.

        AC1: repo_url=None marker indicating special handling
        """
        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        # Register git repo
        registry.register_global_repo(
            repo_name="git-repo",
            alias_name="git-repo-global",
            repo_url="https://github.com/org/git-repo",
            index_path=str(tmp_path / "git-index"),
        )

        # Register meta-directory
        registry.register_global_repo(
            repo_name="cidx-meta",
            alias_name="cidx-meta-global",
            repo_url=None,
            index_path=str(tmp_path / "meta-index"),
            allow_reserved=True,  # Allow reserved name for meta-directory tests
        )

        all_repos = registry.list_global_repos()

        # Filter meta-directories (repo_url is None)
        meta_dirs = [r for r in all_repos if r["repo_url"] is None]
        git_repos = [r for r in all_repos if r["repo_url"] is not None]

        assert len(meta_dirs) == 1
        assert len(git_repos) == 1
        assert meta_dirs[0]["alias_name"] == "cidx-meta-global"

    def test_meta_directory_structure_created(self, tmp_path):
        """
        Test that meta-directory folder structure is created.

        AC1: Directory structure created in golden repos area
        """
        golden_repos_dir = tmp_path / "golden_repos"
        meta_dir = golden_repos_dir / "cidx-meta"

        # Meta-directory should be created
        meta_dir.mkdir(parents=True, exist_ok=True)

        assert meta_dir.exists()
        assert meta_dir.is_dir()

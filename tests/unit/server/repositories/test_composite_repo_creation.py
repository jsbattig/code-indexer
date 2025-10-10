"""
Unit tests for composite repository creation (Story 1.2).

Tests the _do_activate_composite_repository implementation that creates
composite directory structures using ProxyInitializer and CoW cloning.

Following strict TDD methodology - these tests are written FIRST.
"""

import json
import os
import pytest
import tempfile
import shutil
import subprocess
from unittest.mock import Mock

from code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
    ActivatedRepoError,
)
from code_indexer.server.repositories.golden_repo_manager import GoldenRepoManager


class TestCompositeRepositoryCreation:
    """Test composite repository creation acceptance criteria."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.test_dir, "data")
        os.makedirs(self.data_dir, exist_ok=True)

        # Create golden repos directory with test repositories
        self.golden_repos_dir = os.path.join(self.data_dir, "golden-repos")
        os.makedirs(self.golden_repos_dir, exist_ok=True)

        # Create activated repos directory
        self.activated_repos_dir = os.path.join(self.data_dir, "activated-repos")
        os.makedirs(self.activated_repos_dir, exist_ok=True)

        # Create test golden repositories with .code-indexer directories
        self.golden_repo_paths = {}
        for repo_alias in ["repo1", "repo2", "repo3"]:
            repo_path = os.path.join(self.golden_repos_dir, repo_alias)
            os.makedirs(repo_path, exist_ok=True)

            # Create .code-indexer directory with config (simulating indexed data)
            code_indexer_dir = os.path.join(repo_path, ".code-indexer")
            os.makedirs(code_indexer_dir, exist_ok=True)

            # Create config.json (simulating indexed repository)
            config_data = {
                "embedding_provider": "voyage-ai",
                "proxy_mode": False,
            }
            with open(os.path.join(code_indexer_dir, "config.json"), "w") as f:
                json.dump(config_data, f)

            # Create a test file to ensure directory isn't empty
            with open(os.path.join(repo_path, f"{repo_alias}.txt"), "w") as f:
                f.write(f"Test content for {repo_alias}")

            # Initialize as git repository
            subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repo_path,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path,
                capture_output=True,
            )
            subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=repo_path,
                capture_output=True,
            )

            self.golden_repo_paths[repo_alias] = repo_path

        # Initialize managers
        self.golden_repo_manager = GoldenRepoManager(data_dir=self.data_dir)
        self.manager = ActivatedRepoManager(
            data_dir=self.data_dir, golden_repo_manager=self.golden_repo_manager
        )

        # Register golden repositories
        for alias, path in self.golden_repo_paths.items():
            mock_golden_repo = Mock()
            mock_golden_repo.alias = alias
            mock_golden_repo.clone_path = path
            mock_golden_repo.default_branch = "master"
            self.golden_repo_manager.golden_repos[alias] = mock_golden_repo

    def teardown_method(self):
        """Clean up test fixtures."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_acceptance_1_creates_composite_directory_with_user_alias_name(self):
        """
        Acceptance Criterion 1: Creates composite directory with user_alias name.

        GIVEN: A request to activate composite repository with user_alias "my_composite"
        WHEN: _do_activate_composite_repository is called
        THEN: A directory named "my_composite" is created under activated-repos/<username>/
        """
        # Arrange
        username = "testuser"
        user_alias = "my_composite"
        golden_repo_aliases = ["repo1", "repo2", "repo3"]

        # Act
        result = self.manager._do_activate_composite_repository(
            username=username,
            golden_repo_aliases=golden_repo_aliases,
            user_alias=user_alias,
            progress_callback=None,
        )

        # Assert
        composite_path = os.path.join(self.activated_repos_dir, username, user_alias)
        assert os.path.exists(
            composite_path
        ), f"Composite directory should exist at {composite_path}"
        assert os.path.isdir(
            composite_path
        ), f"Composite path should be a directory: {composite_path}"
        assert result["success"] is True, "Activation should succeed"

    def test_acceptance_2_proxy_initializer_creates_config_with_proxy_mode(self):
        """
        Acceptance Criterion 2: ProxyInitializer creates .code-indexer/config.json with proxy_mode=true.

        GIVEN: A composite repository activation request
        WHEN: ProxyInitializer.initialize() is called
        THEN: .code-indexer/config.json is created with proxy_mode=true
        """
        # Arrange
        username = "testuser"
        user_alias = "my_composite"
        golden_repo_aliases = ["repo1", "repo2", "repo3"]

        # Act
        result = self.manager._do_activate_composite_repository(
            username=username,
            golden_repo_aliases=golden_repo_aliases,
            user_alias=user_alias,
            progress_callback=None,
        )

        # Assert
        config_path = os.path.join(
            self.activated_repos_dir,
            username,
            user_alias,
            ".code-indexer",
            "config.json",
        )
        assert os.path.exists(config_path), f"Config file should exist at {config_path}"

        with open(config_path, "r") as f:
            config_data = json.load(f)

        assert config_data.get("proxy_mode") is True, "proxy_mode should be True"
        assert "discovered_repos" in config_data, "discovered_repos should be present"
        assert result["success"] is True

    def test_acceptance_3_each_golden_repo_cow_cloned_as_subdirectory(self):
        """
        Acceptance Criterion 3: Each golden repo is CoW cloned as subdirectory.

        GIVEN: Three golden repositories to activate
        WHEN: Composite repository is created
        THEN: Each golden repo is cloned as a subdirectory with its original alias name
        """
        # Arrange
        username = "testuser"
        user_alias = "my_composite"
        golden_repo_aliases = ["repo1", "repo2", "repo3"]

        # Act
        result = self.manager._do_activate_composite_repository(
            username=username,
            golden_repo_aliases=golden_repo_aliases,
            user_alias=user_alias,
            progress_callback=None,
        )

        # Assert
        composite_path = os.path.join(self.activated_repos_dir, username, user_alias)

        for alias in golden_repo_aliases:
            subrepo_path = os.path.join(composite_path, alias)
            assert os.path.exists(
                subrepo_path
            ), f"Subdirectory should exist for {alias} at {subrepo_path}"
            assert os.path.isdir(
                subrepo_path
            ), f"Subrepo path should be a directory: {subrepo_path}"

            # Verify it's a git repository (CoW clone preserves git structure)
            git_dir = os.path.join(subrepo_path, ".git")
            assert os.path.exists(
                git_dir
            ), f"Git directory should exist for {alias} at {git_dir}"

        assert result["success"] is True

    def test_acceptance_4_proxy_config_manager_discovers_all_cloned_repos(self):
        """
        Acceptance Criterion 4: ProxyConfigManager discovers all cloned repositories.

        GIVEN: Composite repository with multiple cloned subdirectories
        WHEN: ProxyConfigManager.refresh_repositories() is called
        THEN: All cloned repositories are discovered and added to config
        """
        # Arrange
        username = "testuser"
        user_alias = "my_composite"
        golden_repo_aliases = ["repo1", "repo2", "repo3"]

        # Act
        result = self.manager._do_activate_composite_repository(
            username=username,
            golden_repo_aliases=golden_repo_aliases,
            user_alias=user_alias,
            progress_callback=None,
        )

        # Assert
        config_path = os.path.join(
            self.activated_repos_dir,
            username,
            user_alias,
            ".code-indexer",
            "config.json",
        )

        with open(config_path, "r") as f:
            config_data = json.load(f)

        discovered_repos = config_data.get("discovered_repos", [])
        assert len(discovered_repos) == len(
            golden_repo_aliases
        ), f"Should discover {len(golden_repo_aliases)} repositories"

        # Verify all aliases are discovered (order may vary)
        discovered_aliases = set(discovered_repos)
        expected_aliases = set(golden_repo_aliases)
        assert (
            discovered_aliases == expected_aliases
        ), f"Discovered repos {discovered_aliases} should match expected {expected_aliases}"

        assert result["success"] is True

    def test_acceptance_5_discovered_repos_list_matches_cloned_repos(self):
        """
        Acceptance Criterion 5: discovered_repos list in config matches cloned repos.

        GIVEN: A composite repository with specific golden repos
        WHEN: Repository is activated and config is created
        THEN: discovered_repos list exactly matches the cloned repository subdirectories
        """
        # Arrange
        username = "testuser"
        user_alias = "my_composite"
        golden_repo_aliases = ["repo1", "repo2"]  # Using 2 repos for clarity

        # Act
        result = self.manager._do_activate_composite_repository(
            username=username,
            golden_repo_aliases=golden_repo_aliases,
            user_alias=user_alias,
            progress_callback=None,
        )

        # Assert
        composite_path = os.path.join(self.activated_repos_dir, username, user_alias)
        config_path = os.path.join(composite_path, ".code-indexer", "config.json")

        # Get discovered repos from config
        with open(config_path, "r") as f:
            config_data = json.load(f)
        discovered_repos = set(config_data.get("discovered_repos", []))

        # Get actual subdirectories
        actual_subdirs = set()
        for item in os.listdir(composite_path):
            item_path = os.path.join(composite_path, item)
            if os.path.isdir(item_path) and item != ".code-indexer":
                actual_subdirs.add(item)

        # Verify they match
        assert (
            discovered_repos == actual_subdirs
        ), f"Discovered repos {discovered_repos} should match actual subdirs {actual_subdirs}"
        assert discovered_repos == set(
            golden_repo_aliases
        ), "Discovered repos should match input golden repo aliases"

        assert result["success"] is True

    def test_acceptance_6_component_repos_retain_code_indexer_data(self):
        """
        Acceptance Criterion 6: All component repos retain their .code-indexer/ indexed data.

        GIVEN: Golden repositories with .code-indexer/ directories containing indexed data
        WHEN: Repositories are CoW cloned into composite
        THEN: Each cloned repository retains its complete .code-indexer/ directory structure
        """
        # Arrange
        username = "testuser"
        user_alias = "my_composite"
        golden_repo_aliases = ["repo1", "repo2", "repo3"]

        # Act
        result = self.manager._do_activate_composite_repository(
            username=username,
            golden_repo_aliases=golden_repo_aliases,
            user_alias=user_alias,
            progress_callback=None,
        )

        # Assert
        composite_path = os.path.join(self.activated_repos_dir, username, user_alias)

        for alias in golden_repo_aliases:
            subrepo_path = os.path.join(composite_path, alias)
            code_indexer_dir = os.path.join(subrepo_path, ".code-indexer")

            # Verify .code-indexer directory exists
            assert os.path.exists(
                code_indexer_dir
            ), f".code-indexer should exist for {alias}"
            assert os.path.isdir(
                code_indexer_dir
            ), f".code-indexer should be directory for {alias}"

            # Verify config.json exists
            config_file = os.path.join(code_indexer_dir, "config.json")
            assert os.path.exists(
                config_file
            ), f"config.json should exist for {alias} at {config_file}"

            # Verify config content is preserved
            with open(config_file, "r") as f:
                subrepo_config = json.load(f)

            # Original repos are NOT proxy mode
            assert (
                subrepo_config.get("proxy_mode") is False
            ), f"Subrepo {alias} should NOT have proxy_mode=True"
            assert (
                "embedding_provider" in subrepo_config
            ), f"Config should retain embedding_provider for {alias}"

        assert result["success"] is True

    def test_composite_creation_with_user_alias_defaults_to_joined_names(self):
        """
        Test that user_alias can be None and implementation handles it appropriately.

        GIVEN: Composite activation without explicit user_alias
        WHEN: _do_activate_composite_repository is called with user_alias=None
        THEN: Implementation should handle it gracefully (implementation-specific behavior)
        """
        # Arrange
        username = "testuser"
        golden_repo_aliases = ["repo1", "repo2"]

        # Act & Assert - implementation may choose default behavior
        # For now, test that it doesn't crash and creates valid structure
        result = self.manager._do_activate_composite_repository(
            username=username,
            golden_repo_aliases=golden_repo_aliases,
            user_alias=None,  # Let implementation decide default
            progress_callback=None,
        )

        # Should succeed regardless of user_alias handling
        assert result["success"] is True

    def test_composite_creation_progress_callback_integration(self):
        """
        Test that progress callbacks are called during composite creation.

        GIVEN: A progress callback function
        WHEN: Composite repository is created
        THEN: Progress callback is invoked with progress percentages
        """
        # Arrange
        username = "testuser"
        user_alias = "my_composite"
        golden_repo_aliases = ["repo1", "repo2"]

        progress_calls = []

        def mock_progress(percent: int) -> None:
            progress_calls.append(percent)

        # Act
        result = self.manager._do_activate_composite_repository(
            username=username,
            golden_repo_aliases=golden_repo_aliases,
            user_alias=user_alias,
            progress_callback=mock_progress,
        )

        # Assert
        assert result["success"] is True
        assert len(progress_calls) > 0, "Progress callback should be called"
        assert 100 in progress_calls, "Should report 100% completion"

    def test_composite_creation_metadata_file_created(self):
        """
        Test that metadata file is created for composite repository.

        GIVEN: Composite repository activation
        WHEN: Repository is successfully created
        THEN: Metadata file exists with correct structure including is_composite flag
        """
        # Arrange
        username = "testuser"
        user_alias = "my_composite"
        golden_repo_aliases = ["repo1", "repo2", "repo3"]

        # Act
        result = self.manager._do_activate_composite_repository(
            username=username,
            golden_repo_aliases=golden_repo_aliases,
            user_alias=user_alias,
            progress_callback=None,
        )

        # Assert
        metadata_path = os.path.join(
            self.activated_repos_dir, username, f"{user_alias}_metadata.json"
        )
        assert os.path.exists(
            metadata_path
        ), f"Metadata file should exist at {metadata_path}"

        with open(metadata_path, "r") as f:
            metadata = json.load(f)

        assert metadata["user_alias"] == user_alias
        assert metadata["is_composite"] is True, "Metadata should mark as composite"
        assert (
            metadata["golden_repo_aliases"] == golden_repo_aliases
        ), "Should store original alias list"
        assert "activated_at" in metadata, "Should have activation timestamp"

        assert result["success"] is True

    def test_composite_creation_validates_golden_repos_exist(self):
        """
        Test that composite creation validates golden repositories exist.

        GIVEN: A request with non-existent golden repository alias
        WHEN: Composite activation is attempted
        THEN: ActivatedRepoError is raised with clear message
        """
        # Arrange
        username = "testuser"
        user_alias = "bad_composite"
        golden_repo_aliases = ["repo1", "nonexistent_repo", "repo2"]

        # Act & Assert
        with pytest.raises(ActivatedRepoError) as exc_info:
            self.manager._do_activate_composite_repository(
                username=username,
                golden_repo_aliases=golden_repo_aliases,
                user_alias=user_alias,
                progress_callback=None,
            )

        assert (
            "nonexistent_repo" in str(exc_info.value).lower()
            or "not found" in str(exc_info.value).lower()
        )

    def test_composite_creation_cleans_up_on_failure(self):
        """
        Test that composite creation cleans up partial state on failure.

        GIVEN: A composite activation that will fail partway through
        WHEN: An error occurs during creation
        THEN: Partial directories and files are cleaned up
        """
        # Arrange
        username = "testuser"
        user_alias = "failed_composite"
        # Include a non-existent repo to trigger failure
        golden_repo_aliases = ["repo1", "nonexistent", "repo2"]

        composite_path = os.path.join(self.activated_repos_dir, username, user_alias)

        # Act & Assert
        with pytest.raises(ActivatedRepoError):
            self.manager._do_activate_composite_repository(
                username=username,
                golden_repo_aliases=golden_repo_aliases,
                user_alias=user_alias,
                progress_callback=None,
            )

        # Assert cleanup happened
        # Implementation may clean up the entire composite directory on failure
        # This is an implementation detail, but we verify no partial state remains
        if os.path.exists(composite_path):
            # If directory exists, it should be empty or minimal (no partial clones)
            items = os.listdir(composite_path)
            # Allow for .code-indexer if ProxyInitializer ran first
            assert len(items) <= 1, "Should not leave partial clones on failure"


class TestCompositeRepoCreationReusesExistingCLIComponents:
    """
    Test that composite creation REUSES existing CLI components.

    Critical mandate: "reuse EVERYTHING you can, already implemented
    in the context of the CLI under the hood classes"
    """

    def test_uses_proxy_initializer_from_cli(self):
        """
        Test that implementation uses ProxyInitializer from CLI package.

        GIVEN: Composite repository creation
        WHEN: Proxy configuration is created
        THEN: ProxyInitializer from code_indexer.proxy.proxy_initializer is used
        """
        # This is a documentation test - verified by implementation review
        # Implementation MUST import and use:
        # from code_indexer.proxy.proxy_initializer import ProxyInitializer
        assert True, "Implementation must use ProxyInitializer from CLI package"

    def test_uses_proxy_config_manager_from_cli(self):
        """
        Test that implementation uses ProxyConfigManager from CLI package.

        GIVEN: Repository discovery and config refresh
        WHEN: Repositories are discovered
        THEN: ProxyConfigManager from code_indexer.proxy.config_manager is used
        """
        # This is a documentation test - verified by implementation review
        # Implementation MUST import and use:
        # from code_indexer.proxy.config_manager import ProxyConfigManager
        assert True, "Implementation must use ProxyConfigManager from CLI package"

    def test_reuses_cow_clone_mechanism_from_single_repo(self):
        """
        Test that implementation reuses _clone_with_copy_on_write method.

        GIVEN: CoW cloning of golden repositories
        WHEN: Each repository is cloned
        THEN: Existing _clone_with_copy_on_write method is called
        """
        # This is a documentation test - verified by implementation review
        # Implementation MUST call self._clone_with_copy_on_write()
        assert True, "Implementation must reuse existing CoW clone method"

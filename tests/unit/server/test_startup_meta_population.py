"""
Unit tests for server startup meta-directory population.

Tests the logic for auto-populating meta-directory with repository
descriptions on server startup.
"""

import pytest
from unittest.mock import Mock, patch
from code_indexer.server.lifecycle.startup_meta_populator import (
    StartupMetaPopulator,
)


class TestStartupMetaPopulator:
    """Test suite for StartupMetaPopulator."""

    @pytest.fixture
    def temp_meta_dir(self, tmp_path):
        """Create temporary meta-directory."""
        meta_dir = tmp_path / "cidx-meta"
        meta_dir.mkdir()
        return meta_dir

    @pytest.fixture
    def temp_golden_repos_dir(self, tmp_path):
        """Create temporary golden repos directory."""
        golden_repos_dir = tmp_path / "golden-repos"
        golden_repos_dir.mkdir()
        return golden_repos_dir

    @pytest.fixture
    def mock_registry(self):
        """Create mock global registry."""
        registry = Mock()
        registry.list_global_repos.return_value = []
        return registry

    @pytest.fixture
    def mock_updater(self):
        """Create mock meta-directory updater."""
        with patch(
            "code_indexer.server.lifecycle.startup_meta_populator.MetaDirectoryUpdater"
        ) as mock_updater_class:
            mock_instance = Mock()
            mock_updater_class.return_value = mock_instance
            yield mock_instance

    def test_empty_meta_directory_triggers_population(
        self, temp_meta_dir, temp_golden_repos_dir, mock_registry, mock_updater
    ):
        """
        Test: Server starts with empty meta-directory
        Given: The CIDX server has registered repositories
        And: The meta-directory exists but is empty
        When: The server starts
        Then: All registered repositories have description files generated
        """
        # Setup: Registry has 2 repos (excluding meta-directory itself)
        mock_registry.list_global_repos.return_value = [
            {"repo_name": "repo1", "repo_url": "https://github.com/user/repo1"},
            {"repo_name": "repo2", "repo_url": "https://github.com/user/repo2"},
            {"repo_name": "cidx-meta", "repo_url": None},  # Meta-directory itself
        ]

        # Empty meta-directory (no description files)
        assert len(list(temp_meta_dir.glob("*.md"))) == 0

        # Act: Create populator and run startup population
        populator = StartupMetaPopulator(
            meta_dir=str(temp_meta_dir),
            golden_repos_dir=str(temp_golden_repos_dir),
            registry=mock_registry,
        )
        result = populator.populate_on_startup()

        # Assert: Update was called to generate descriptions
        mock_updater.update.assert_called_once()
        assert result["populated"] is True
        assert result["repos_processed"] == 2
        assert "meta-directory populated" in result["message"].lower()

    def test_partially_populated_meta_directory_updates_missing(
        self, temp_meta_dir, temp_golden_repos_dir, mock_registry, mock_updater
    ):
        """
        Test: Server starts with partially populated meta-directory
        Given: Some repositories have descriptions but others don't
        When: The server starts
        Then: Only missing descriptions are generated
        And: Existing descriptions are preserved
        """
        # Setup: Create one existing description file
        existing_desc = temp_meta_dir / "repo1.md"
        existing_desc.write_text("# repo1\nExisting description")
        existing_mtime = existing_desc.stat().st_mtime

        # Registry has 2 repos, but only 1 has description
        mock_registry.list_global_repos.return_value = [
            {"repo_name": "repo1", "repo_url": "https://github.com/user/repo1"},
            {"repo_name": "repo2", "repo_url": "https://github.com/user/repo2"},
            {"repo_name": "cidx-meta", "repo_url": None},
        ]

        # Act: Run startup population
        populator = StartupMetaPopulator(
            meta_dir=str(temp_meta_dir),
            golden_repos_dir=str(temp_golden_repos_dir),
            registry=mock_registry,
        )
        result = populator.populate_on_startup()

        # Assert: Update was called (it handles incremental logic)
        mock_updater.update.assert_called_once()
        assert result["populated"] is True

        # Existing file should be preserved (not modified)
        assert existing_desc.exists()
        assert existing_desc.stat().st_mtime == existing_mtime

    def test_fully_populated_meta_directory_skips_population(
        self, temp_meta_dir, temp_golden_repos_dir, mock_registry, mock_updater
    ):
        """
        Test: Server starts with fully populated meta-directory
        Given: All repositories have descriptions
        When: The server starts
        Then: No new descriptions are generated
        And: Startup completes quickly
        """
        # Setup: Create description files for all repos
        (temp_meta_dir / "repo1.md").write_text("# repo1")
        (temp_meta_dir / "repo2.md").write_text("# repo2")

        # Registry matches existing descriptions
        mock_registry.list_global_repos.return_value = [
            {"repo_name": "repo1", "repo_url": "https://github.com/user/repo1"},
            {"repo_name": "repo2", "repo_url": "https://github.com/user/repo2"},
            {"repo_name": "cidx-meta", "repo_url": None},
        ]

        # Mock has_changes to return False (no changes needed)
        mock_updater.has_changes.return_value = False

        # Act: Run startup population
        populator = StartupMetaPopulator(
            meta_dir=str(temp_meta_dir),
            golden_repos_dir=str(temp_golden_repos_dir),
            registry=mock_registry,
        )
        result = populator.populate_on_startup()

        # Assert: Update was NOT called (no changes needed)
        mock_updater.has_changes.assert_called_once()
        mock_updater.update.assert_not_called()
        assert result["populated"] is False
        assert result["repos_processed"] == 0
        assert "up to date" in result["message"].lower()

    def test_description_generation_failure_does_not_block_startup(
        self, temp_meta_dir, temp_golden_repos_dir, mock_registry, mock_updater
    ):
        """
        Test: Description generation fails for one repository
        Given: The server starts with an empty meta-directory
        When: AI description generation fails for one repository
        Then: The server continues startup
        And: An error is logged for the failed repository
        """
        # Setup: Registry has repos
        mock_registry.list_global_repos.return_value = [
            {"repo_name": "repo1", "repo_url": "https://github.com/user/repo1"},
            {"repo_name": "repo2", "repo_url": "https://github.com/user/repo2"},
            {"repo_name": "cidx-meta", "repo_url": None},
        ]

        # Mock update() to raise exception (simulating AI failure)
        mock_updater.update.side_effect = Exception("AI API timeout")

        # Act: Run startup population
        populator = StartupMetaPopulator(
            meta_dir=str(temp_meta_dir),
            golden_repos_dir=str(temp_golden_repos_dir),
            registry=mock_registry,
        )

        # Should NOT raise exception - error should be caught
        result = populator.populate_on_startup()

        # Assert: Startup continued despite error
        assert result["populated"] is False
        assert "error" in result
        assert "AI API timeout" in result["error"]
        assert result["repos_processed"] == 0

    def test_no_registered_repos_skips_population(
        self, temp_meta_dir, temp_golden_repos_dir, mock_registry, mock_updater
    ):
        """
        Test: Server starts with no registered repositories
        Given: The registry is empty (only meta-directory exists)
        When: The server starts
        Then: No population is attempted
        And: Startup completes successfully
        """
        # Setup: Only meta-directory in registry
        mock_registry.list_global_repos.return_value = [
            {"repo_name": "cidx-meta", "repo_url": None}
        ]

        # Act: Run startup population
        populator = StartupMetaPopulator(
            meta_dir=str(temp_meta_dir),
            golden_repos_dir=str(temp_golden_repos_dir),
            registry=mock_registry,
        )
        result = populator.populate_on_startup()

        # Assert: No update was called
        mock_updater.update.assert_not_called()
        assert result["populated"] is False
        assert result["repos_processed"] == 0
        assert "no repositories" in result["message"].lower()

    def test_meta_directory_creation_if_missing(
        self, temp_golden_repos_dir, mock_registry, mock_updater
    ):
        """
        Test: Meta-directory is created if it doesn't exist
        Given: The meta-directory path doesn't exist
        When: The server starts
        Then: The meta-directory is created
        And: Population proceeds normally
        """
        # Setup: Meta-directory doesn't exist
        meta_dir = temp_golden_repos_dir / "cidx-meta"
        assert not meta_dir.exists()

        mock_registry.list_global_repos.return_value = [
            {"repo_name": "repo1", "repo_url": "https://github.com/user/repo1"},
            {"repo_name": "cidx-meta", "repo_url": None},
        ]

        # Act: Run startup population
        populator = StartupMetaPopulator(
            meta_dir=str(meta_dir),
            golden_repos_dir=str(temp_golden_repos_dir),
            registry=mock_registry,
        )
        result = populator.populate_on_startup()

        # Assert: Meta-directory was created
        assert meta_dir.exists()
        assert meta_dir.is_dir()
        mock_updater.update.assert_called_once()
        assert result["populated"] is True

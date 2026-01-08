"""
Tests for Batch Golden Repository Creation.

Following TDD methodology - these tests are written FIRST before implementation.
Tests define the expected behavior for batch creation endpoint and alias generation.

Story #692: Batch Creation
"""

from unittest.mock import MagicMock

import pytest


class TestGenerateUniqueAlias:
    """Tests for the generate_unique_alias helper function."""

    def test_alias_from_full_path(self):
        """Test that 'org/project' generates 'project' alias."""
        from code_indexer.server.web.routes import generate_unique_alias

        mock_manager = MagicMock()
        mock_manager.list_golden_repos.return_value = []

        result = generate_unique_alias("org/my-project", mock_manager)
        assert result == "my-project"

    def test_alias_from_nested_path(self):
        """Test that 'group/sub/proj' generates 'proj' alias."""
        from code_indexer.server.web.routes import generate_unique_alias

        mock_manager = MagicMock()
        mock_manager.list_golden_repos.return_value = []

        result = generate_unique_alias("group/subgroup/project-name", mock_manager)
        assert result == "project-name"

    def test_alias_conflict_suffix(self):
        """Test that numeric suffix is added on alias conflict."""
        from code_indexer.server.web.routes import generate_unique_alias

        mock_manager = MagicMock()
        mock_manager.list_golden_repos.return_value = [{"alias": "project"}]

        result = generate_unique_alias("org/project", mock_manager)
        assert result == "project-2"

    def test_alias_conflict_suffix_multiple(self):
        """Test that numeric suffix increments correctly on multiple conflicts."""
        from code_indexer.server.web.routes import generate_unique_alias

        mock_manager = MagicMock()
        mock_manager.list_golden_repos.return_value = [
            {"alias": "project"},
            {"alias": "project-2"},
            {"alias": "project-3"},
        ]

        result = generate_unique_alias("org/project", mock_manager)
        assert result == "project-4"

    def test_alias_case_normalization(self):
        """Test that alias is converted to lowercase."""
        from code_indexer.server.web.routes import generate_unique_alias

        mock_manager = MagicMock()
        mock_manager.list_golden_repos.return_value = []

        result = generate_unique_alias("org/MyProject", mock_manager)
        assert result == result.lower()
        assert result == "myproject"

    def test_alias_special_chars(self):
        """Test that special characters are sanitized to dashes."""
        from code_indexer.server.web.routes import generate_unique_alias

        mock_manager = MagicMock()
        mock_manager.list_golden_repos.return_value = []

        result = generate_unique_alias("org/my_project.name", mock_manager)
        assert "@" not in result
        assert "." not in result
        assert "_" not in result

    def test_alias_simple_name(self):
        """Test that simple name without path works."""
        from code_indexer.server.web.routes import generate_unique_alias

        mock_manager = MagicMock()
        mock_manager.list_golden_repos.return_value = []

        result = generate_unique_alias("myproject", mock_manager)
        assert result == "myproject"


class TestBatchCreateLogic:
    """Tests for batch create business logic using mocks."""

    @pytest.fixture
    def mock_golden_repo_manager(self):
        """Create a mock golden repo manager."""
        manager = MagicMock()
        manager.list_golden_repos.return_value = []
        manager.add_golden_repo.return_value = "job-123"
        return manager

    def test_batch_create_success(self, mock_golden_repo_manager):
        """Test that all repos are created successfully."""
        from code_indexer.server.web.routes import _batch_create_repos

        repos = [
            {
                "clone_url": "https://github.com/org/repo1.git",
                "alias": "org/repo1",
                "branch": "main",
                "platform": "github",
            },
            {
                "clone_url": "https://github.com/org/repo2.git",
                "alias": "org/repo2",
                "branch": "master",
                "platform": "github",
            },
        ]

        results = _batch_create_repos(repos, "admin", mock_golden_repo_manager)

        assert results["success"] is True
        assert len(results["results"]) == 2
        assert all(r["status"] == "success" for r in results["results"])
        assert "2 succeeded, 0 failed" in results["summary"]

    def test_batch_create_partial_failure(self, mock_golden_repo_manager):
        """Test handling when some repos succeed and some fail."""
        from code_indexer.server.web.routes import _batch_create_repos

        mock_golden_repo_manager.add_golden_repo.side_effect = [
            "job-123",
            Exception("Repository already exists"),
        ]

        repos = [
            {
                "clone_url": "https://github.com/org/repo1.git",
                "alias": "org/repo1",
                "branch": "main",
                "platform": "github",
            },
            {
                "clone_url": "https://github.com/org/repo2.git",
                "alias": "org/repo2",
                "branch": "main",
                "platform": "github",
            },
        ]

        results = _batch_create_repos(repos, "admin", mock_golden_repo_manager)

        assert results["success"] is False
        assert len(results["results"]) == 2
        statuses = [r["status"] for r in results["results"]]
        assert "success" in statuses
        assert "failed" in statuses
        assert "1 succeeded, 1 failed" in results["summary"]

    def test_batch_create_all_fail(self, mock_golden_repo_manager):
        """Test handling when all repos fail to create."""
        from code_indexer.server.web.routes import _batch_create_repos

        mock_golden_repo_manager.add_golden_repo.side_effect = Exception(
            "Connection error"
        )

        repos = [
            {
                "clone_url": "https://github.com/org/repo1.git",
                "alias": "org/repo1",
                "branch": "main",
                "platform": "github",
            },
            {
                "clone_url": "https://github.com/org/repo2.git",
                "alias": "org/repo2",
                "branch": "main",
                "platform": "github",
            },
        ]

        results = _batch_create_repos(repos, "admin", mock_golden_repo_manager)

        assert results["success"] is False
        assert len(results["results"]) == 2
        assert all(r["status"] == "failed" for r in results["results"])
        assert "0 succeeded, 2 failed" in results["summary"]
        assert all("error" in r for r in results["results"])

    def test_batch_create_empty_list(self, mock_golden_repo_manager):
        """Test handling of empty repository list."""
        from code_indexer.server.web.routes import _batch_create_repos

        repos = []

        results = _batch_create_repos(repos, "admin", mock_golden_repo_manager)

        assert results["success"] is True
        assert len(results["results"]) == 0
        assert "0 succeeded, 0 failed" in results["summary"]

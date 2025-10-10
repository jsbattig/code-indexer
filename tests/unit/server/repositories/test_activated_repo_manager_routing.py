"""
Unit tests for ActivatedRepoManager.activate_repository routing logic.

Tests the routing between single and composite repository activation methods.
Following TDD methodology - these tests are written FIRST before implementation.
"""

import pytest
from unittest.mock import Mock
from code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
)


class TestActivatedRepoManagerSingleRepoRouting:
    """Test routing for single repository activation (existing functionality)."""

    def test_single_repo_calls_do_activate_repository(self):
        """Test that single repo activation routes to _do_activate_repository."""
        # Arrange
        manager = ActivatedRepoManager()

        # Mock the background job manager
        mock_job_manager = Mock()
        mock_job_manager.submit_job.return_value = "job-123"
        manager.background_job_manager = mock_job_manager

        # Mock golden repo manager
        mock_golden_repo = Mock()
        mock_golden_repo.default_branch = "main"
        manager.golden_repo_manager.golden_repos = {"repo1": mock_golden_repo}

        # Act
        job_id = manager.activate_repository(
            username="user1",
            golden_repo_alias="repo1",
            branch_name="main",
            user_alias="my_repo",
        )

        # Assert
        assert job_id == "job-123"
        mock_job_manager.submit_job.assert_called_once()
        call_args = mock_job_manager.submit_job.call_args

        # Verify it submitted with _do_activate_repository
        assert call_args[0][0] == "activate_repository"
        assert call_args[0][1] == manager._do_activate_repository

    def test_single_repo_with_none_golden_repo_aliases(self):
        """Test single repo activation when golden_repo_aliases is explicitly None."""
        # Arrange
        manager = ActivatedRepoManager()

        mock_job_manager = Mock()
        mock_job_manager.submit_job.return_value = "job-456"
        manager.background_job_manager = mock_job_manager

        mock_golden_repo = Mock()
        mock_golden_repo.default_branch = "main"
        manager.golden_repo_manager.golden_repos = {"repo1": mock_golden_repo}

        # Act
        job_id = manager.activate_repository(
            username="user1",
            golden_repo_alias="repo1",
            golden_repo_aliases=None,
            user_alias="my_repo",
        )

        # Assert
        assert job_id == "job-456"


class TestActivatedRepoManagerCompositeRepoRouting:
    """Test routing for composite repository activation (NEW functionality)."""

    def test_composite_repo_routes_to_do_activate_composite_repository(self):
        """Test that composite repo activation routes to _do_activate_composite_repository."""
        # Arrange
        manager = ActivatedRepoManager()

        # Create a stub for _do_activate_composite_repository
        manager._do_activate_composite_repository = Mock(
            return_value={"status": "pending"}
        )

        # Mock background job manager
        mock_job_manager = Mock()
        mock_job_manager.submit_job.return_value = "job-composite-123"
        manager.background_job_manager = mock_job_manager

        # Act
        job_id = manager.activate_repository(
            username="user1",
            golden_repo_aliases=["repo1", "repo2", "repo3"],
            user_alias="composite_repo",
        )

        # Assert
        assert job_id == "job-composite-123"
        mock_job_manager.submit_job.assert_called_once()
        call_args = mock_job_manager.submit_job.call_args

        # Verify it submitted with _do_activate_composite_repository
        assert call_args[0][0] == "activate_composite_repository"
        assert call_args[0][1] == manager._do_activate_composite_repository

    def test_composite_repo_with_none_golden_repo_alias(self):
        """Test composite activation when golden_repo_alias is explicitly None."""
        # Arrange
        manager = ActivatedRepoManager()
        manager._do_activate_composite_repository = Mock(
            return_value={"status": "pending"}
        )

        mock_job_manager = Mock()
        mock_job_manager.submit_job.return_value = "job-comp-456"
        manager.background_job_manager = mock_job_manager

        # Act
        job_id = manager.activate_repository(
            username="user1",
            golden_repo_alias=None,
            golden_repo_aliases=["repo1", "repo2"],
            user_alias="composite",
        )

        # Assert
        assert job_id == "job-comp-456"


class TestActivatedRepoManagerRoutingValidation:
    """Test validation in the routing logic."""

    def test_both_parameters_raises_error(self):
        """Test that providing both parameters raises ValueError."""
        # Arrange
        manager = ActivatedRepoManager()

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            manager.activate_repository(
                username="user1",
                golden_repo_alias="repo1",
                golden_repo_aliases=["repo2", "repo3"],
                user_alias="test",
            )

        assert "cannot specify both" in str(exc_info.value).lower()

    def test_neither_parameter_raises_error(self):
        """Test that providing neither parameter raises ValueError."""
        # Arrange
        manager = ActivatedRepoManager()

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            manager.activate_repository(
                username="user1",
                golden_repo_alias=None,
                golden_repo_aliases=None,
                user_alias="test",
            )

        assert "must specify either" in str(exc_info.value).lower()

    def test_composite_with_single_repo_raises_error(self):
        """Test that composite activation with only 1 repo raises ValueError."""
        # Arrange
        manager = ActivatedRepoManager()

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            manager.activate_repository(
                username="user1",
                golden_repo_aliases=["repo1"],
                user_alias="test",
            )

        assert "at least 2 repositories" in str(exc_info.value).lower()

    def test_composite_with_empty_list_raises_error(self):
        """Test that composite activation with empty list raises ValueError."""
        # Arrange
        manager = ActivatedRepoManager()

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            manager.activate_repository(
                username="user1",
                golden_repo_aliases=[],
                user_alias="test",
            )

        assert "at least 2 repositories" in str(exc_info.value).lower()


class TestActivatedRepoManagerCompositeImplementation:
    """Test the implemented _do_activate_composite_repository method."""

    def test_composite_implementation_validates_golden_repos(self):
        """Test that composite implementation validates golden repositories exist."""
        # Arrange
        manager = ActivatedRepoManager()

        # Act & Assert - should raise ActivatedRepoError, not NotImplementedError
        with pytest.raises(Exception) as exc_info:
            manager._do_activate_composite_repository(
                username="user1",
                golden_repo_aliases=["repo1", "repo2"],
                user_alias="composite",
            )

        # Should raise ActivatedRepoError for missing golden repos, not NotImplementedError
        assert "ActivatedRepoError" in str(type(exc_info.value).__name__)

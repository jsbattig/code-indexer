"""
Unit tests for FTS parameter wiring through semantic_query_manager.

Phase 2 of Story #503: Verify FTS parameters flow correctly through
the internal method chain:
  query_user_repositories -> _perform_search -> _search_single_repository

This test suite uses mocking to verify parameters are passed without
requiring actual search infrastructure.
"""

import tempfile
from unittest.mock import patch, MagicMock, Mock, call
import pytest

from src.code_indexer.server.query.semantic_query_manager import (
    SemanticQueryManager,
    QueryResult,
)


class TestFTSParameterWiring:
    """Test suite for FTS parameter wiring through internal method chain."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def query_manager(self, temp_data_dir):
        """Create SemanticQueryManager instance with mocked dependencies."""
        with patch(
            "src.code_indexer.server.query.semantic_query_manager.ActivatedRepoManager"
        ) as mock_activated_manager, patch(
            "src.code_indexer.server.query.semantic_query_manager.BackgroundJobManager"
        ) as mock_job_manager:
            # Configure activated repo manager mock
            mock_activated_instance = MagicMock()
            mock_activated_instance.list_activated_repositories.return_value = [
                {
                    "user_alias": "test-repo",
                    "golden_repo_alias": "test-repo-golden",
                    "current_branch": "main",
                }
            ]
            mock_activated_instance.get_activated_repo_path.return_value = (
                f"{temp_data_dir}/test-repo"
            )
            mock_activated_manager.return_value = mock_activated_instance

            # Configure job manager mock
            mock_job_instance = MagicMock()
            mock_job_manager.return_value = mock_job_instance

            manager = SemanticQueryManager(data_dir=temp_data_dir)
            return manager

    def test_fts_parameters_passed_to_perform_search(self, query_manager):
        """Test that FTS parameters are passed from query_user_repositories to _perform_search.

        This is a RED test proving the current bug: FTS parameters are accepted
        in query_user_repositories but NOT passed to _perform_search.
        """
        # Mock _perform_search to capture parameters
        with patch.object(
            query_manager, "_perform_search", return_value=[]
        ) as mock_perform_search:
            # Call query_user_repositories with FTS parameters
            query_manager.query_user_repositories(
                username="testuser",
                query_text="authenticate",
                limit=10,
                # FTS parameters
                case_sensitive=True,
                fuzzy=True,
                edit_distance=2,
                snippet_lines=10,
                regex=False,
            )

            # Verify _perform_search was called with FTS parameters
            mock_perform_search.assert_called_once()
            call_kwargs = mock_perform_search.call_args[1]

            # These assertions will FAIL until we wire the parameters through
            assert (
                "case_sensitive" in call_kwargs
            ), "case_sensitive parameter not passed to _perform_search"
            assert (
                call_kwargs["case_sensitive"] is True
            ), "case_sensitive value not preserved"

            assert "fuzzy" in call_kwargs, "fuzzy parameter not passed to _perform_search"
            assert call_kwargs["fuzzy"] is True, "fuzzy value not preserved"

            assert (
                "edit_distance" in call_kwargs
            ), "edit_distance parameter not passed to _perform_search"
            assert call_kwargs["edit_distance"] == 2, "edit_distance value not preserved"

            assert (
                "snippet_lines" in call_kwargs
            ), "snippet_lines parameter not passed to _perform_search"
            assert (
                call_kwargs["snippet_lines"] == 10
            ), "snippet_lines value not preserved"

            assert "regex" in call_kwargs, "regex parameter not passed to _perform_search"
            assert call_kwargs["regex"] is False, "regex value not preserved"

    def test_fts_parameters_passed_to_search_single_repository(self, query_manager):
        """Test that FTS parameters are passed from _perform_search to _search_single_repository.

        This is a RED test proving the next level of the call chain.
        """
        # Create a mock user repo list
        user_repos = [
            {
                "user_alias": "test-repo",
                "golden_repo_alias": "test-repo-golden",
                "current_branch": "main",
            }
        ]

        # Mock _search_single_repository to capture parameters
        with patch.object(
            query_manager, "_search_single_repository", return_value=[]
        ) as mock_search_single:
            # Call _perform_search with FTS parameters
            query_manager._perform_search(
                username="testuser",
                user_repos=user_repos,
                query_text="authenticate",
                limit=10,
                min_score=0.5,
                file_extensions=None,
                language=None,
                exclude_language=None,
                path_filter=None,
                exclude_path=None,
                accuracy=None,
                time_range=None,
                at_commit=None,
                include_removed=False,
                show_evolution=False,
                evolution_limit=None,
                # FTS parameters
                case_sensitive=True,
                fuzzy=True,
                edit_distance=2,
                snippet_lines=10,
                regex=False,
            )

            # Verify _search_single_repository was called with FTS parameters
            mock_search_single.assert_called_once()
            call_kwargs = mock_search_single.call_args[1]

            # These assertions will FAIL until we wire the parameters through
            assert (
                "case_sensitive" in call_kwargs
            ), "case_sensitive parameter not passed to _search_single_repository"
            assert (
                call_kwargs["case_sensitive"] is True
            ), "case_sensitive value not preserved"

            assert (
                "fuzzy" in call_kwargs
            ), "fuzzy parameter not passed to _search_single_repository"
            assert call_kwargs["fuzzy"] is True, "fuzzy value not preserved"

            assert (
                "edit_distance" in call_kwargs
            ), "edit_distance parameter not passed to _search_single_repository"
            assert call_kwargs["edit_distance"] == 2, "edit_distance value not preserved"

            assert (
                "snippet_lines" in call_kwargs
            ), "snippet_lines parameter not passed to _search_single_repository"
            assert (
                call_kwargs["snippet_lines"] == 10
            ), "snippet_lines value not preserved"

            assert (
                "regex" in call_kwargs
            ), "regex parameter not passed to _search_single_repository"
            assert call_kwargs["regex"] is False, "regex value not preserved"

    def test_fts_parameter_defaults(self, query_manager):
        """Test that FTS parameters use correct defaults when not specified."""
        # Mock _perform_search to capture parameters
        with patch.object(
            query_manager, "_perform_search", return_value=[]
        ) as mock_perform_search:
            # Call without FTS parameters
            query_manager.query_user_repositories(
                username="testuser",
                query_text="test",
                limit=10,
            )

            # Verify defaults are passed
            call_kwargs = mock_perform_search.call_args[1]

            # These will fail until implementation is complete
            assert call_kwargs.get("case_sensitive", None) is False
            assert call_kwargs.get("fuzzy", None) is False
            assert call_kwargs.get("edit_distance", None) == 0
            assert call_kwargs.get("snippet_lines", None) == 5
            assert call_kwargs.get("regex", None) is False

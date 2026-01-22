"""
Unit tests for SemanticQueryManager warning log conditions.

Story #725: Fix Excessive Warning Logs for Default Accuracy Parameter

Tests the condition that triggers warning logs for non-composite repositories
when advanced filter parameters are used that won't be applied.

The bug was that `accuracy="balanced"` (the default) is truthy, causing the
warning to fire for EVERY semantic/hybrid query, even when no filters are
explicitly set.

Acceptance Criteria:
- Warning does NOT appear for queries with all default parameter values
- Warning DOES appear when user explicitly sets `path_filter` parameter
- Warning DOES appear when user explicitly sets `language` filter
- Warning DOES appear when user sets non-default `accuracy` value
"""

import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.code_indexer.server.query.semantic_query_manager import (
    SemanticQueryManager,
)


class TestWarningLogConditions:
    """Test suite for warning log conditions in _search_single_repository."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def mock_managers(self):
        """Create mock managers for SemanticQueryManager."""
        activated_repo_manager = MagicMock()
        background_job_manager = MagicMock()
        return activated_repo_manager, background_job_manager

    @pytest.fixture
    def query_manager(self, temp_data_dir, mock_managers):
        """Create SemanticQueryManager instance for testing."""
        activated_repo_manager, background_job_manager = mock_managers
        return SemanticQueryManager(
            data_dir=temp_data_dir,
            activated_repo_manager=activated_repo_manager,
            background_job_manager=background_job_manager,
        )

    @pytest.fixture
    def mock_non_composite_repo(self, temp_data_dir):
        """Create a mock non-composite repository path."""
        repo_path = Path(temp_data_dir) / "test-repo"
        repo_path.mkdir(parents=True, exist_ok=True)
        # Do NOT create .code-indexer/proxy_mode.json - this makes it non-composite
        return str(repo_path)

    def test_no_warning_for_default_parameters(
        self, query_manager, mock_non_composite_repo, caplog
    ):
        """
        AC: Warning does NOT appear for queries with all default parameter values.

        When a query is made with default parameters (language=None, path_filter=None,
        accuracy="balanced"), the warning should NOT be logged because no advanced
        filters were explicitly set by the user.
        """
        # Mock SemanticSearchService to avoid actual search
        with patch(
            "src.code_indexer.server.services.search_service.SemanticSearchService"
        ) as mock_search_service:
            mock_service = MagicMock()
            mock_service.search.return_value = []
            mock_search_service.return_value = mock_service

            with caplog.at_level(logging.WARNING):
                # Call with all defaults: language=None, exclude_language=None,
                # path_filter=None, exclude_path=None, accuracy="balanced" (default)
                query_manager._search_single_repository(
                    repo_path=mock_non_composite_repo,
                    repository_alias="test-repo",
                    query_text="test query",
                    limit=10,
                    min_score=None,
                    file_extensions=None,
                    language=None,
                    exclude_language=None,
                    path_filter=None,
                    exclude_path=None,
                    accuracy="balanced",  # Default value
                    search_mode="semantic",
                )

        # Verify NO warning was logged for default parameters
        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        filter_warnings = [
            m
            for m in warning_messages
            if "Advanced filter parameters" in m
            or "are not supported for non-composite" in m
        ]
        assert (
            len(filter_warnings) == 0
        ), f"Expected no warnings for default params, got: {filter_warnings}"

    def test_no_warning_for_none_accuracy(
        self, query_manager, mock_non_composite_repo, caplog
    ):
        """
        AC: Warning does NOT appear when accuracy is None (not explicitly set).

        This tests the case where accuracy is not set at all (None).
        """
        with patch(
            "src.code_indexer.server.services.search_service.SemanticSearchService"
        ) as mock_search_service:
            mock_service = MagicMock()
            mock_service.search.return_value = []
            mock_search_service.return_value = mock_service

            with caplog.at_level(logging.WARNING):
                query_manager._search_single_repository(
                    repo_path=mock_non_composite_repo,
                    repository_alias="test-repo",
                    query_text="test query",
                    limit=10,
                    min_score=None,
                    file_extensions=None,
                    language=None,
                    exclude_language=None,
                    path_filter=None,
                    exclude_path=None,
                    accuracy=None,  # Not set
                    search_mode="semantic",
                )

        # Verify NO warning was logged
        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        filter_warnings = [
            m
            for m in warning_messages
            if "Advanced filter parameters" in m
            or "are not supported for non-composite" in m
        ]
        assert (
            len(filter_warnings) == 0
        ), f"Expected no warnings for None accuracy, got: {filter_warnings}"

    def test_warning_for_explicit_path_filter(
        self, query_manager, mock_non_composite_repo, caplog
    ):
        """
        AC: Warning DOES appear when user explicitly sets `path_filter` parameter.

        When path_filter is explicitly set (non-None), the warning should be logged
        because this filter won't be applied to non-composite repos.
        """
        with patch(
            "src.code_indexer.server.services.search_service.SemanticSearchService"
        ) as mock_search_service:
            mock_service = MagicMock()
            mock_service.search.return_value = []
            mock_search_service.return_value = mock_service

            with caplog.at_level(logging.WARNING):
                query_manager._search_single_repository(
                    repo_path=mock_non_composite_repo,
                    repository_alias="test-repo",
                    query_text="test query",
                    limit=10,
                    min_score=None,
                    file_extensions=None,
                    language=None,
                    exclude_language=None,
                    path_filter="*/tests/*",  # Explicitly set
                    exclude_path=None,
                    accuracy="balanced",
                    search_mode="semantic",
                )

        # Verify warning WAS logged for explicit path_filter
        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        filter_warnings = [
            m
            for m in warning_messages
            if "Advanced filter parameters" in m
            or "are not supported for non-composite" in m
        ]
        assert (
            len(filter_warnings) == 1
        ), f"Expected 1 warning for path_filter, got {len(filter_warnings)}: {filter_warnings}"
        assert "path_filter=*/tests/*" in filter_warnings[0]

    def test_warning_for_explicit_language_filter(
        self, query_manager, mock_non_composite_repo, caplog
    ):
        """
        AC: Warning DOES appear when user explicitly sets `language` filter.

        When language filter is explicitly set, the warning should be logged.
        """
        with patch(
            "src.code_indexer.server.services.search_service.SemanticSearchService"
        ) as mock_search_service:
            mock_service = MagicMock()
            mock_service.search.return_value = []
            mock_search_service.return_value = mock_service

            with caplog.at_level(logging.WARNING):
                query_manager._search_single_repository(
                    repo_path=mock_non_composite_repo,
                    repository_alias="test-repo",
                    query_text="test query",
                    limit=10,
                    min_score=None,
                    file_extensions=None,
                    language="python",  # Explicitly set
                    exclude_language=None,
                    path_filter=None,
                    exclude_path=None,
                    accuracy="balanced",
                    search_mode="semantic",
                )

        # Verify warning WAS logged for explicit language
        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        filter_warnings = [
            m
            for m in warning_messages
            if "Advanced filter parameters" in m
            or "are not supported for non-composite" in m
        ]
        assert (
            len(filter_warnings) == 1
        ), f"Expected 1 warning for language, got {len(filter_warnings)}: {filter_warnings}"
        assert "language=python" in filter_warnings[0]

    def test_warning_for_non_default_accuracy(
        self, query_manager, mock_non_composite_repo, caplog
    ):
        """
        AC: Warning DOES appear when user sets non-default `accuracy` value.

        When accuracy is set to something other than "balanced" (e.g., "high"),
        the warning should be logged.
        """
        with patch(
            "src.code_indexer.server.services.search_service.SemanticSearchService"
        ) as mock_search_service:
            mock_service = MagicMock()
            mock_service.search.return_value = []
            mock_search_service.return_value = mock_service

            with caplog.at_level(logging.WARNING):
                query_manager._search_single_repository(
                    repo_path=mock_non_composite_repo,
                    repository_alias="test-repo",
                    query_text="test query",
                    limit=10,
                    min_score=None,
                    file_extensions=None,
                    language=None,
                    exclude_language=None,
                    path_filter=None,
                    exclude_path=None,
                    accuracy="high",  # Non-default value
                    search_mode="semantic",
                )

        # Verify warning WAS logged for non-default accuracy
        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        filter_warnings = [
            m
            for m in warning_messages
            if "Advanced filter parameters" in m
            or "are not supported for non-composite" in m
        ]
        assert (
            len(filter_warnings) == 1
        ), f"Expected 1 warning for accuracy=high, got {len(filter_warnings)}: {filter_warnings}"
        assert "accuracy=high" in filter_warnings[0]

    def test_warning_for_exclude_language(
        self, query_manager, mock_non_composite_repo, caplog
    ):
        """
        Test that warning appears when exclude_language is set.
        """
        with patch(
            "src.code_indexer.server.services.search_service.SemanticSearchService"
        ) as mock_search_service:
            mock_service = MagicMock()
            mock_service.search.return_value = []
            mock_search_service.return_value = mock_service

            with caplog.at_level(logging.WARNING):
                query_manager._search_single_repository(
                    repo_path=mock_non_composite_repo,
                    repository_alias="test-repo",
                    query_text="test query",
                    limit=10,
                    min_score=None,
                    file_extensions=None,
                    language=None,
                    exclude_language="java",  # Explicitly set
                    path_filter=None,
                    exclude_path=None,
                    accuracy="balanced",
                    search_mode="semantic",
                )

        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        filter_warnings = [
            m
            for m in warning_messages
            if "Advanced filter parameters" in m
            or "are not supported for non-composite" in m
        ]
        assert (
            len(filter_warnings) == 1
        ), f"Expected 1 warning for exclude_language, got {len(filter_warnings)}"
        assert "exclude_language=java" in filter_warnings[0]

    def test_warning_for_exclude_path(
        self, query_manager, mock_non_composite_repo, caplog
    ):
        """
        Test that warning appears when exclude_path is set.
        """
        with patch(
            "src.code_indexer.server.services.search_service.SemanticSearchService"
        ) as mock_search_service:
            mock_service = MagicMock()
            mock_service.search.return_value = []
            mock_search_service.return_value = mock_service

            with caplog.at_level(logging.WARNING):
                query_manager._search_single_repository(
                    repo_path=mock_non_composite_repo,
                    repository_alias="test-repo",
                    query_text="test query",
                    limit=10,
                    min_score=None,
                    file_extensions=None,
                    language=None,
                    exclude_language=None,
                    path_filter=None,
                    exclude_path="*/node_modules/*",  # Explicitly set
                    accuracy="balanced",
                    search_mode="semantic",
                )

        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        filter_warnings = [
            m
            for m in warning_messages
            if "Advanced filter parameters" in m
            or "are not supported for non-composite" in m
        ]
        assert (
            len(filter_warnings) == 1
        ), f"Expected 1 warning for exclude_path, got {len(filter_warnings)}"
        assert "exclude_path=*/node_modules/*" in filter_warnings[0]

    def test_warning_for_hybrid_mode_with_default_params(
        self, query_manager, mock_non_composite_repo, caplog
    ):
        """
        Test that hybrid mode does NOT trigger warning with default parameters.

        The bug affects both 'semantic' and 'hybrid' search modes.
        """
        with patch(
            "src.code_indexer.server.services.search_service.SemanticSearchService"
        ) as mock_search_service:
            mock_service = MagicMock()
            mock_service.search.return_value = []
            mock_search_service.return_value = mock_service

            # Also mock FTS search
            with patch.object(query_manager, "_execute_fts_search", return_value=[]):
                with caplog.at_level(logging.WARNING):
                    query_manager._search_single_repository(
                        repo_path=mock_non_composite_repo,
                        repository_alias="test-repo",
                        query_text="test query",
                        limit=10,
                        min_score=None,
                        file_extensions=None,
                        language=None,
                        exclude_language=None,
                        path_filter=None,
                        exclude_path=None,
                        accuracy="balanced",  # Default
                        search_mode="hybrid",
                    )

        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        filter_warnings = [
            m
            for m in warning_messages
            if "Advanced filter parameters" in m
            or "are not supported for non-composite" in m
        ]
        assert (
            len(filter_warnings) == 0
        ), f"Expected no warnings for hybrid mode with defaults, got: {filter_warnings}"

    def test_no_warning_for_fts_mode(
        self, query_manager, mock_non_composite_repo, caplog
    ):
        """
        Test that FTS mode does NOT trigger the warning at all.

        The warning is only for semantic and hybrid modes, not pure FTS.
        """
        with patch.object(query_manager, "_execute_fts_search", return_value=[]):
            with caplog.at_level(logging.WARNING):
                query_manager._search_single_repository(
                    repo_path=mock_non_composite_repo,
                    repository_alias="test-repo",
                    query_text="test query",
                    limit=10,
                    min_score=None,
                    file_extensions=None,
                    language="python",  # Even with explicit filter
                    exclude_language=None,
                    path_filter=None,
                    exclude_path=None,
                    accuracy="high",  # Even with non-default accuracy
                    search_mode="fts",  # FTS mode returns early
                )

        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        filter_warnings = [
            m
            for m in warning_messages
            if "Advanced filter parameters" in m
            or "are not supported for non-composite" in m
        ]
        assert (
            len(filter_warnings) == 0
        ), f"Expected no warnings for FTS mode, got: {filter_warnings}"

    def test_multiple_explicit_filters_single_warning(
        self, query_manager, mock_non_composite_repo, caplog
    ):
        """
        Test that setting multiple explicit filters only produces one warning.
        """
        with patch(
            "src.code_indexer.server.services.search_service.SemanticSearchService"
        ) as mock_search_service:
            mock_service = MagicMock()
            mock_service.search.return_value = []
            mock_search_service.return_value = mock_service

            with caplog.at_level(logging.WARNING):
                query_manager._search_single_repository(
                    repo_path=mock_non_composite_repo,
                    repository_alias="test-repo",
                    query_text="test query",
                    limit=10,
                    min_score=None,
                    file_extensions=None,
                    language="python",  # Explicitly set
                    exclude_language="java",  # Explicitly set
                    path_filter="*/src/*",  # Explicitly set
                    exclude_path="*/tests/*",  # Explicitly set
                    accuracy="high",  # Non-default
                    search_mode="semantic",
                )

        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        filter_warnings = [
            m
            for m in warning_messages
            if "Advanced filter parameters" in m
            or "are not supported for non-composite" in m
        ]
        # Should still be just ONE warning, listing all the filters
        assert (
            len(filter_warnings) == 1
        ), f"Expected 1 warning for multiple filters, got {len(filter_warnings)}"
        # Verify all filters are mentioned in the warning
        assert "language=python" in filter_warnings[0]
        assert "exclude_language=java" in filter_warnings[0]
        assert "path_filter=*/src/*" in filter_warnings[0]
        assert "exclude_path=*/tests/*" in filter_warnings[0]
        assert "accuracy=high" in filter_warnings[0]

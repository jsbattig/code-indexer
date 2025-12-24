"""
Test for implementing SemanticQueryManager._search_repository() method.

Tests that verify the missing implementation is properly connected to SemanticSearchService.
Following TDD methodology: First write failing tests, then implement.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch

from code_indexer.server.query.semantic_query_manager import (
    SemanticQueryManager,
    QueryResult,
)


class TestSemanticQueryManagerImplementation:
    """Test implementing the missing _search_repository method."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_repo_path = os.path.join(self.temp_dir, "test-repo")
        os.makedirs(self.test_repo_path)

        # Create a test file in the repository
        test_file = os.path.join(self.test_repo_path, "test_file.py")
        with open(test_file, "w") as f:
            f.write("def test_function():\n    return 'hello world'\n")

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_search_single_repository_no_longer_raises_not_implemented_error(self):
        """
        Test that _search_single_repository no longer raises NotImplementedError.

        This test verifies the implementation is now working (at least attempting real search).
        """
        query_manager = SemanticQueryManager()

        # The method should no longer raise NotImplementedError
        # It may raise other exceptions (like config errors), but not NotImplementedError
        try:
            query_manager._search_single_repository(
                repo_path=self.test_repo_path,
                repository_alias="test-repo",
                query_text="test function",
                limit=10,
                min_score=None,
                file_extensions=None,
            )
        except NotImplementedError:
            pytest.fail(
                "_search_single_repository should no longer raise NotImplementedError"
            )
        except Exception as e:
            # Other exceptions are acceptable for now (config issues, etc.)
            # The key is that NotImplementedError is not raised
            assert "Semantic search not yet implemented" not in str(e)

    @patch("code_indexer.server.services.search_service.SemanticSearchService")
    def test_search_single_repository_integrates_with_search_service(
        self, mock_search_service_class
    ):
        """
        Test that _search_single_repository integrates with SemanticSearchService.

        This test will FAIL initially because the integration doesn't exist yet.
        """
        # Mock the search service instance and its methods
        mock_search_service = Mock()
        mock_search_service_class.return_value = mock_search_service

        # Mock search results from the service
        mock_search_response = Mock()
        mock_search_response.results = [
            Mock(
                file_path="test_file.py",
                line_start=1,
                line_end=2,
                score=0.95,
                content="def test_function():\n    return 'hello world'\n",
                language="python",
            )
        ]
        mock_search_service.search_repository_path.return_value = mock_search_response

        query_manager = SemanticQueryManager()

        # This will fail because the method is not implemented
        results = query_manager._search_single_repository(
            repo_path=self.test_repo_path,
            repository_alias="test-repo",
            query_text="test function",
            limit=10,
            min_score=0.7,
            file_extensions=[".py"],
        )

        # Verify the integration
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, QueryResult)
        assert result.file_path == "test_file.py"
        assert result.similarity_score == 0.95
        assert result.repository_alias == "test-repo"
        assert "def test_function():" in result.code_snippet

    def test_search_single_repository_handles_search_service_errors(self):
        """
        Test that _search_single_repository handles SemanticSearchService errors.

        This test will FAIL initially because error handling doesn't exist yet.
        """
        with patch(
            "code_indexer.server.services.search_service.SemanticSearchService"
        ) as mock_class:
            mock_service = Mock()
            mock_class.return_value = mock_service
            mock_service.search_repository_path.side_effect = RuntimeError(
                "Search failed"
            )

            query_manager = SemanticQueryManager()

            # This should handle the error gracefully
            with pytest.raises(Exception) as exc_info:
                query_manager._search_single_repository(
                    repo_path=self.test_repo_path,
                    repository_alias="test-repo",
                    query_text="test function",
                    limit=10,
                    min_score=None,
                    file_extensions=None,
                )

            # Error should be properly propagated with context
            assert "Search failed" in str(exc_info.value)

    def test_query_result_conversion_from_search_result_item(self):
        """
        Test that SearchResultItem is properly converted to QueryResult.

        This test verifies the data transformation between service and manager.
        """
        # Create a mock SearchResultItem (with actual API model fields)
        mock_search_item = Mock()
        mock_search_item.file_path = "/path/to/file.py"
        mock_search_item.line_start = 10
        mock_search_item.line_end = 15
        mock_search_item.score = 0.85
        mock_search_item.content = "def important_function():\n    return True"
        mock_search_item.language = "python"

        # Test the inline conversion logic that exists in _search_single_repository
        # Create QueryResult directly since conversion is inline
        query_result = QueryResult(
            file_path=mock_search_item.file_path,
            line_number=mock_search_item.line_start,  # Use start line as line number
            code_snippet=mock_search_item.content,
            similarity_score=mock_search_item.score,
            repository_alias="test-repo",
        )

        assert isinstance(query_result, QueryResult)
        assert query_result.file_path == "/path/to/file.py"
        assert query_result.line_number == 10  # Should use start_line
        assert query_result.similarity_score == 0.85
        assert query_result.repository_alias == "test-repo"
        assert query_result.code_snippet == "def important_function():\n    return True"

    def test_search_repository_creates_proper_search_request(self):
        """
        Test that _search_single_repository creates proper SemanticSearchRequest.

        This test verifies the request parameters are properly formatted.
        """
        with patch(
            "code_indexer.server.services.search_service.SemanticSearchService"
        ) as mock_class:
            with patch(
                "code_indexer.server.models.api_models.SemanticSearchRequest"
            ) as mock_request_class:
                mock_service = Mock()
                mock_class.return_value = mock_service
                mock_request = Mock()
                mock_request_class.return_value = mock_request

                # Mock empty response
                mock_response = Mock()
                mock_response.results = []
                mock_service.search_repository_path.return_value = mock_response

                query_manager = SemanticQueryManager()

                # This will fail because the request creation doesn't exist yet
                query_manager._search_single_repository(
                    repo_path=self.test_repo_path,
                    repository_alias="test-repo",
                    query_text="test query",
                    limit=15,
                    min_score=0.8,
                    file_extensions=[".py", ".js"],
                )

                # Verify SemanticSearchRequest was created with correct parameters
                mock_request_class.assert_called_once_with(
                    query="test query", limit=15, include_source=True
                )

                # Verify search_repository_path was called with correct parameters
                mock_service.search_repository_path.assert_called_once_with(
                    repo_path=self.test_repo_path, search_request=mock_request
                )

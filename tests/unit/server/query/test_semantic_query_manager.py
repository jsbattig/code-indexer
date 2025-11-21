"""
Unit tests for SemanticQueryManager.

Tests the core functionality of semantic search operations including:
- Query processing with user isolation
- Repository filtering and validation
- Result formatting and ranking
- Background job integration for long-running queries
- Resource limits and timeout handling
- Integration with existing search infrastructure
"""

import tempfile
from unittest.mock import patch, MagicMock

import pytest

from src.code_indexer.server.query.semantic_query_manager import (
    SemanticQueryManager,
    SemanticQueryError,
    QueryResult,
)


@pytest.mark.e2e
class TestSemanticQueryManager:
    """Test suite for SemanticQueryManager functionality."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def activated_repo_manager_mock(self):
        """Mock activated repo manager."""
        mock = MagicMock()

        # Mock activated repos for test user
        mock.list_activated_repositories.return_value = [
            {
                "user_alias": "my-repo",
                "golden_repo_alias": "test-repo",
                "current_branch": "main",
                "activated_at": "2024-01-01T00:00:00Z",
                "last_accessed": "2024-01-01T00:00:00Z",
            },
            {
                "user_alias": "second-repo",
                "golden_repo_alias": "another-repo",
                "current_branch": "develop",
                "activated_at": "2024-01-01T00:00:00Z",
                "last_accessed": "2024-01-01T00:00:00Z",
            },
        ]

        # Mock repository paths
        mock.get_activated_repo_path.side_effect = (
            lambda username, user_alias: f"/tmp/repos/{username}/{user_alias}"
        )

        return mock

    @pytest.fixture
    def background_job_manager_mock(self):
        """Mock background job manager."""
        mock = MagicMock()

        # Mock job submission
        mock.submit_job.return_value = "test-job-id-123"

        # Mock job status
        mock.get_job_status.return_value = {
            "job_id": "test-job-id-123",
            "operation_type": "semantic_query",
            "status": "completed",
            "created_at": "2024-01-01T00:00:00Z",
            "started_at": "2024-01-01T00:00:00Z",
            "completed_at": "2024-01-01T00:00:00Z",
            "progress": 100,
            "result": {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "test query",
                    "execution_time_ms": 100,
                    "repositories_searched": 2,
                    "timeout_occurred": False,
                },
            },
            "error": None,
        }

        return mock

    @pytest.fixture
    def search_engine_mock(self):
        """Mock search engine from core functionality."""
        mock = MagicMock()

        # Mock search results
        mock.search.return_value = [
            MagicMock(
                file_path="/tmp/repos/testuser/my-repo/src/main.py",
                content="def main():\n    print('Hello World')",
                language="python",
                score=0.85,
                chunk_index=0,
                total_chunks=1,
            ),
            MagicMock(
                file_path="/tmp/repos/testuser/my-repo/src/utils.py",
                content="def helper():\n    return 'helper'",
                language="python",
                score=0.72,
                chunk_index=0,
                total_chunks=1,
            ),
        ]

        return mock

    @pytest.fixture
    def semantic_query_manager(
        self, temp_data_dir, activated_repo_manager_mock, background_job_manager_mock
    ):
        """Create SemanticQueryManager instance for testing."""
        return SemanticQueryManager(
            data_dir=temp_data_dir,
            activated_repo_manager=activated_repo_manager_mock,
            background_job_manager=background_job_manager_mock,
        )

    def test_semantic_query_manager_initialization(
        self, semantic_query_manager, temp_data_dir
    ):
        """Test SemanticQueryManager initializes correctly."""
        assert semantic_query_manager.data_dir == temp_data_dir
        assert semantic_query_manager.activated_repo_manager is not None
        assert semantic_query_manager.background_job_manager is not None
        assert semantic_query_manager.query_timeout_seconds == 30
        assert semantic_query_manager.max_concurrent_queries_per_user == 5
        assert semantic_query_manager.max_results_per_query == 100

    def test_query_user_repositories_basic(
        self, semantic_query_manager, search_engine_mock
    ):
        """Test basic query functionality across user's repositories."""

        # Mock the _search_single_repository method directly
        def mock_search_single_repo(
            repo_path, repo_alias, query_text, limit, min_score, file_extensions
        ):
            from src.code_indexer.server.query.semantic_query_manager import QueryResult

            return [
                QueryResult(
                    file_path=f"{repo_path}/src/main.py",
                    line_number=1,
                    code_snippet="def main():\n    print('Hello World')",
                    similarity_score=0.85,
                    repository_alias=repo_alias,
                ),
                QueryResult(
                    file_path=f"{repo_path}/src/utils.py",
                    line_number=1,
                    code_snippet="def helper():\n    return 'helper'",
                    similarity_score=0.72,
                    repository_alias=repo_alias,
                ),
            ]

        with patch.object(
            semantic_query_manager,
            "_search_single_repository",
            side_effect=mock_search_single_repo,
        ):
            results = semantic_query_manager.query_user_repositories(
                username="testuser", query_text="test function", limit=10, min_score=0.5
            )

            assert "results" in results
            assert "total_results" in results
            assert "query_metadata" in results
            assert isinstance(results["results"], list)
            assert len(results["results"]) == 4  # 2 repos * 2 results each
            assert results["query_metadata"]["query_text"] == "test function"
            assert results["query_metadata"]["repositories_searched"] == 2

    def test_query_single_repository(self, semantic_query_manager, search_engine_mock):
        """Test querying a specific repository by alias."""

        # Mock the _search_single_repository method directly
        def mock_search_single_repo(
            repo_path, repo_alias, query_text, limit, min_score, file_extensions
        ):
            from src.code_indexer.server.query.semantic_query_manager import QueryResult

            return [
                QueryResult(
                    file_path=f"{repo_path}/src/main.py",
                    line_number=1,
                    code_snippet="def main():\n    print('Hello World')",
                    similarity_score=0.85,
                    repository_alias=repo_alias,
                ),
                QueryResult(
                    file_path=f"{repo_path}/src/utils.py",
                    line_number=1,
                    code_snippet="def helper():\n    return 'helper'",
                    similarity_score=0.72,
                    repository_alias=repo_alias,
                ),
            ]

        with patch.object(
            semantic_query_manager,
            "_search_single_repository",
            side_effect=mock_search_single_repo,
        ):
            results = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="helper function",
                repository_alias="my-repo",
                limit=5,
            )

            assert "results" in results
            assert len(results["results"]) == 2  # Single repo returns 2 results
            assert results["query_metadata"]["repositories_searched"] == 1

    def test_query_nonexistent_repository_alias(self, semantic_query_manager):
        """Test querying with invalid repository alias raises error."""
        with pytest.raises(SemanticQueryError) as exc_info:
            semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="test",
                repository_alias="nonexistent-repo",
            )

        assert "Repository 'nonexistent-repo' not found" in str(exc_info.value)

    def test_query_user_with_no_repositories(
        self, temp_data_dir, background_job_manager_mock
    ):
        """Test querying user with no activated repositories."""
        # Create manager with empty repo list
        empty_repo_manager = MagicMock()
        empty_repo_manager.list_activated_repositories.return_value = []

        manager = SemanticQueryManager(
            data_dir=temp_data_dir,
            activated_repo_manager=empty_repo_manager,
            background_job_manager=background_job_manager_mock,
        )

        with pytest.raises(SemanticQueryError) as exc_info:
            manager.query_user_repositories(username="testuser", query_text="test")

        assert "No activated repositories found" in str(exc_info.value)

    def test_query_with_background_job(self, semantic_query_manager):
        """Test submitting long-running query as background job."""
        job_id = semantic_query_manager.submit_query_job(
            username="testuser",
            query_text="complex search query",
            limit=50,
            min_score=0.8,
        )

        assert job_id == "test-job-id-123"
        semantic_query_manager.background_job_manager.submit_job.assert_called_once()

        # Verify job was submitted with correct parameters
        call_args = semantic_query_manager.background_job_manager.submit_job.call_args
        assert call_args[0][0] == "semantic_query"
        assert "username" in call_args[1]
        assert "query_text" in call_args[1]

    def test_get_query_job_status(self, semantic_query_manager):
        """Test getting status of background query job."""
        status = semantic_query_manager.get_query_job_status(
            "test-job-id-123", "testuser"
        )

        assert status["job_id"] == "test-job-id-123"
        assert status["operation_type"] == "semantic_query"
        assert status["status"] == "completed"
        assert status["result"] is not None

    def test_get_nonexistent_job_status(self, semantic_query_manager):
        """Test getting status of nonexistent job returns None."""
        semantic_query_manager.background_job_manager.get_job_status.return_value = None

        status = semantic_query_manager.get_query_job_status(
            "nonexistent-job", "testuser"
        )
        assert status is None

    def test_query_result_formatting(self, semantic_query_manager, search_engine_mock):
        """Test query results are properly formatted with required fields."""

        # Mock the _search_single_repository method directly
        def mock_search_single_repo(
            repo_path, repo_alias, query_text, limit, min_score, file_extensions
        ):
            from src.code_indexer.server.query.semantic_query_manager import QueryResult

            return [
                QueryResult(
                    file_path=f"{repo_path}/src/main.py",
                    line_number=1,
                    code_snippet="def main():\n    print('Hello World')",
                    similarity_score=0.85,
                    repository_alias=repo_alias,
                ),
            ]

        with patch.object(
            semantic_query_manager,
            "_search_single_repository",
            side_effect=mock_search_single_repo,
        ):
            results = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="test",
            )

            # Verify result structure
            assert "results" in results
            assert "total_results" in results
            assert "query_metadata" in results

            # Verify each result has required fields
            for result in results["results"]:
                assert "file_path" in result
                assert "line_number" in result
                assert "code_snippet" in result
                assert "similarity_score" in result
                assert "repository_alias" in result

            # Verify metadata
            metadata = results["query_metadata"]
            assert "query_text" in metadata
            assert "execution_time_ms" in metadata
            assert "repositories_searched" in metadata
            assert "timeout_occurred" in metadata

    def test_query_results_sorted_by_score(
        self, semantic_query_manager, search_engine_mock
    ):
        """Test query results are sorted by similarity score in descending order."""

        # Mock the _search_single_repository method to return results with different scores
        def mock_search_single_repo(
            repo_path, repo_alias, query_text, limit, min_score, file_extensions
        ):
            from src.code_indexer.server.query.semantic_query_manager import QueryResult

            return [
                QueryResult(
                    file_path=f"{repo_path}/test1.py",
                    line_number=1,
                    code_snippet="test1",
                    similarity_score=0.6,
                    repository_alias=repo_alias,
                ),
                QueryResult(
                    file_path=f"{repo_path}/test2.py",
                    line_number=1,
                    code_snippet="test2",
                    similarity_score=0.9,
                    repository_alias=repo_alias,
                ),
                QueryResult(
                    file_path=f"{repo_path}/test3.py",
                    line_number=1,
                    code_snippet="test3",
                    similarity_score=0.75,
                    repository_alias=repo_alias,
                ),
            ]

        with patch.object(
            semantic_query_manager,
            "_search_single_repository",
            side_effect=mock_search_single_repo,
        ):
            results = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="test",
            )

            scores = [r["similarity_score"] for r in results["results"]]
            assert scores == sorted(
                scores, reverse=True
            )  # Should be in descending order

    def test_concurrent_query_limits(self, semantic_query_manager):
        """Test concurrent query limits are enforced per user."""
        # This test would need to be expanded with proper concurrent query tracking
        # For now, test that the configuration values are set correctly
        assert semantic_query_manager.max_concurrent_queries_per_user == 5

        # Test would involve tracking active queries per user and rejecting excess
        # Implementation depends on how concurrent queries are tracked

    def test_query_timeout_handling(self, semantic_query_manager):
        """Test query timeout is handled gracefully."""

        # Mock _search_single_repository to simulate timeout
        def mock_search_timeout(*args, **kwargs):
            raise TimeoutError("Query timed out")

        with patch.object(
            semantic_query_manager,
            "_search_single_repository",
            side_effect=mock_search_timeout,
        ):
            with pytest.raises(SemanticQueryError) as exc_info:
                semantic_query_manager.query_user_repositories(
                    username="testuser",
                    query_text="test",
                )

            assert "Query timed out" in str(exc_info.value)

    def test_result_limit_enforcement(
        self, semantic_query_manager, activated_repo_manager_mock
    ):
        """Test result limit is properly enforced."""

        # Mock the _search_single_repository to return many results per repo
        def mock_search_single_repo(
            repo_path, repo_alias, query_text, limit, min_score, file_extensions
        ):
            # Return 75 results per repo (150 total from 2 repos, should be limited to 100)
            return [
                QueryResult(
                    file_path=f"{repo_path}/test{i}.py",
                    line_number=1,
                    code_snippet=f"test content {i}",
                    similarity_score=0.8,
                    repository_alias=repo_alias,
                )
                for i in range(75)
            ]

        with patch.object(
            semantic_query_manager,
            "_search_single_repository",
            side_effect=mock_search_single_repo,
        ):
            results = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="test",
                limit=120,  # Exceeds max_results_per_query (100)
            )

            # Should be limited to max_results_per_query
            assert len(results["results"]) == 100

    def test_invalid_query_parameters(self, semantic_query_manager):
        """Test validation of query parameters."""
        # Test empty query text
        with pytest.raises(SemanticQueryError):
            semantic_query_manager.query_user_repositories(
                username="testuser", query_text=""
            )

        # Test invalid limit
        with pytest.raises(SemanticQueryError):
            semantic_query_manager.query_user_repositories(
                username="testuser", query_text="test", limit=0
            )

        # Test invalid min_score
        with pytest.raises(SemanticQueryError):
            semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="test",
                min_score=1.5,  # Should be <= 1.0
            )

    def test_user_isolation(self, semantic_query_manager, activated_repo_manager_mock):
        """Test that users can only query their own repositories."""

        # Setup different repos for different users
        def mock_list_repos(username):
            if username == "user1":
                return [
                    {
                        "user_alias": "repo1",
                        "golden_repo_alias": "golden1",
                        "current_branch": "main",
                        "activated_at": "2024-01-01T00:00:00Z",
                        "last_accessed": "2024-01-01T00:00:00Z",
                    }
                ]
            elif username == "user2":
                return [
                    {
                        "user_alias": "repo2",
                        "golden_repo_alias": "golden2",
                        "current_branch": "main",
                        "activated_at": "2024-01-01T00:00:00Z",
                        "last_accessed": "2024-01-01T00:00:00Z",
                    }
                ]
            else:
                return []

        activated_repo_manager_mock.list_activated_repositories.side_effect = (
            mock_list_repos
        )

        # Mock the _search_single_repository method to return empty results
        def mock_search_single_repo(
            repo_path, repo_alias, query_text, limit, min_score, file_extensions
        ):
            return []

        with patch.object(
            semantic_query_manager,
            "_search_single_repository",
            side_effect=mock_search_single_repo,
        ):
            # User1 should only see their repos
            results = semantic_query_manager.query_user_repositories(
                username="user1", query_text="test"
            )

            # Verify user1's call was made with their repos only
            activated_repo_manager_mock.list_activated_repositories.assert_called_with(
                "user1"
            )

            # Verify results are empty but properly formatted
            assert results["results"] == []
            assert results["total_results"] == 0
            assert results["query_metadata"]["repositories_searched"] == 1

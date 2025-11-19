"""
Integration tests for Phase 3 temporal filtering parameter wiring (Story #503).

Tests the complete parameter flow from API handlers through SemanticQueryManager
to CLI argument construction for diff_type, author, and chunk_type.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from src.code_indexer.server.query.semantic_query_manager import SemanticQueryManager


@pytest.fixture
def temp_data_dir():
    """Create temporary data directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def activated_repo_manager_mock():
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
    ]

    # Mock repository path
    def get_repo_path(username, user_alias):
        temp_path = Path(tempfile.gettempdir()) / f"repos-{username}-{user_alias}"
        temp_path.mkdir(parents=True, exist_ok=True)
        return str(temp_path)

    mock.get_activated_repo_path.side_effect = get_repo_path

    return mock


@pytest.fixture
def semantic_query_manager(temp_data_dir, activated_repo_manager_mock):
    """Create semantic query manager with mocked dependencies."""
    return SemanticQueryManager(
        data_dir=temp_data_dir,
        activated_repo_manager=activated_repo_manager_mock,
    )


class TestDiffTypeParameterWiring:
    """Test diff_type parameter flows through complete call chain."""

    def test_diff_type_string_passed_to_search_single_repository(
        self, semantic_query_manager, activated_repo_manager_mock
    ):
        """Verify diff_type string parameter reaches _search_single_repository."""
        with patch.object(
            semantic_query_manager, "_search_single_repository"
        ) as mock_search:
            mock_search.return_value = []

            result = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="authentication",
                time_range="2024-01-01..2024-12-31",
                diff_type="added",
            )

            assert result is not None
            call_kwargs = mock_search.call_args[1]
            assert "diff_type" in call_kwargs
            assert call_kwargs["diff_type"] == "added"

    def test_diff_type_array_passed_to_search_single_repository(
        self, semantic_query_manager, activated_repo_manager_mock
    ):
        """Verify diff_type array parameter reaches _search_single_repository."""
        with patch.object(
            semantic_query_manager, "_search_single_repository"
        ) as mock_search:
            mock_search.return_value = []

            result = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="authentication",
                time_range="2024-01-01..2024-12-31",
                diff_type=["added", "modified"],
            )

            assert result is not None
            call_kwargs = mock_search.call_args[1]
            assert "diff_type" in call_kwargs
            assert call_kwargs["diff_type"] == ["added", "modified"]

    def test_diff_type_none_passed_to_search_single_repository(
        self, semantic_query_manager, activated_repo_manager_mock
    ):
        """Verify diff_type=None is passed when not specified."""
        with patch.object(
            semantic_query_manager, "_search_single_repository"
        ) as mock_search:
            mock_search.return_value = []

            result = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="authentication",
                time_range="2024-01-01..2024-12-31",
            )

            assert result is not None
            call_kwargs = mock_search.call_args[1]
            assert "diff_type" in call_kwargs
            assert call_kwargs["diff_type"] is None


class TestAuthorParameterWiring:
    """Test author parameter flows through complete call chain."""

    def test_author_email_passed_to_search_single_repository(
        self, semantic_query_manager, activated_repo_manager_mock
    ):
        """Verify author email parameter reaches _search_single_repository."""
        with patch.object(
            semantic_query_manager, "_search_single_repository"
        ) as mock_search:
            mock_search.return_value = []

            result = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="authentication",
                time_range="2024-01-01..2024-12-31",
                author="dev@example.com",
            )

            assert result is not None
            call_kwargs = mock_search.call_args[1]
            assert "author" in call_kwargs
            assert call_kwargs["author"] == "dev@example.com"

    def test_author_name_passed_to_search_single_repository(
        self, semantic_query_manager, activated_repo_manager_mock
    ):
        """Verify author name parameter reaches _search_single_repository."""
        with patch.object(
            semantic_query_manager, "_search_single_repository"
        ) as mock_search:
            mock_search.return_value = []

            result = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="authentication",
                time_range="2024-01-01..2024-12-31",
                author="John Doe",
            )

            assert result is not None
            call_kwargs = mock_search.call_args[1]
            assert "author" in call_kwargs
            assert call_kwargs["author"] == "John Doe"

    def test_author_none_passed_to_search_single_repository(
        self, semantic_query_manager, activated_repo_manager_mock
    ):
        """Verify author=None is passed when not specified."""
        with patch.object(
            semantic_query_manager, "_search_single_repository"
        ) as mock_search:
            mock_search.return_value = []

            result = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="authentication",
                time_range="2024-01-01..2024-12-31",
            )

            assert result is not None
            call_kwargs = mock_search.call_args[1]
            assert "author" in call_kwargs
            assert call_kwargs["author"] is None


class TestChunkTypeParameterWiring:
    """Test chunk_type parameter flows through complete call chain."""

    def test_chunk_type_commit_message_passed_to_search_single_repository(
        self, semantic_query_manager, activated_repo_manager_mock
    ):
        """Verify chunk_type='commit_message' reaches _search_single_repository."""
        with patch.object(
            semantic_query_manager, "_search_single_repository"
        ) as mock_search:
            mock_search.return_value = []

            result = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="fix bug",
                time_range="2024-01-01..2024-12-31",
                chunk_type="commit_message",
            )

            assert result is not None
            call_kwargs = mock_search.call_args[1]
            assert "chunk_type" in call_kwargs
            assert call_kwargs["chunk_type"] == "commit_message"

    def test_chunk_type_commit_diff_passed_to_search_single_repository(
        self, semantic_query_manager, activated_repo_manager_mock
    ):
        """Verify chunk_type='commit_diff' reaches _search_single_repository."""
        with patch.object(
            semantic_query_manager, "_search_single_repository"
        ) as mock_search:
            mock_search.return_value = []

            result = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="authentication",
                time_range="2024-01-01..2024-12-31",
                chunk_type="commit_diff",
            )

            assert result is not None
            call_kwargs = mock_search.call_args[1]
            assert "chunk_type" in call_kwargs
            assert call_kwargs["chunk_type"] == "commit_diff"

    def test_chunk_type_none_passed_to_search_single_repository(
        self, semantic_query_manager, activated_repo_manager_mock
    ):
        """Verify chunk_type=None is passed when not specified."""
        with patch.object(
            semantic_query_manager, "_search_single_repository"
        ) as mock_search:
            mock_search.return_value = []

            result = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="authentication",
                time_range="2024-01-01..2024-12-31",
            )

            assert result is not None
            call_kwargs = mock_search.call_args[1]
            assert "chunk_type" in call_kwargs
            assert call_kwargs["chunk_type"] is None


class TestCombinedPhase3ParameterWiring:
    """Test all Phase 3 parameters together."""

    def test_all_phase3_parameters_passed_together(
        self, semantic_query_manager, activated_repo_manager_mock
    ):
        """Verify all Phase 3 parameters reach _search_single_repository together."""
        with patch.object(
            semantic_query_manager, "_search_single_repository"
        ) as mock_search:
            mock_search.return_value = []

            result = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="authentication",
                time_range="2024-01-01..2024-12-31",
                diff_type="modified",
                author="dev@example.com",
                chunk_type="commit_diff",
            )

            assert result is not None
            call_kwargs = mock_search.call_args[1]
            assert call_kwargs["diff_type"] == "modified"
            assert call_kwargs["author"] == "dev@example.com"
            assert call_kwargs["chunk_type"] == "commit_diff"

    def test_phase3_with_existing_temporal_parameters(
        self, semantic_query_manager, activated_repo_manager_mock
    ):
        """Verify Phase 3 parameters work alongside existing temporal parameters."""
        with patch.object(
            semantic_query_manager, "_search_single_repository"
        ) as mock_search:
            mock_search.return_value = []

            result = semantic_query_manager.query_user_repositories(
                username="testuser",
                query_text="authentication",
                # Existing temporal parameters (Story #446)
                time_range="2024-01-01..2024-12-31",
                at_commit="abc123",
                include_removed=True,
                show_evolution=True,
                # Phase 3 temporal filtering parameters
                diff_type=["added", "modified"],
                author="dev@example.com",
                chunk_type="commit_diff",
            )

            assert result is not None
            call_kwargs = mock_search.call_args[1]
            # Existing temporal
            assert call_kwargs["time_range"] == "2024-01-01..2024-12-31"
            assert call_kwargs["at_commit"] == "abc123"
            assert call_kwargs["include_removed"] is True
            assert call_kwargs["show_evolution"] is True
            # Phase 3
            assert call_kwargs["diff_type"] == ["added", "modified"]
            assert call_kwargs["author"] == "dev@example.com"
            assert call_kwargs["chunk_type"] == "commit_diff"


class TestCLIArgumentConversion:
    """Test CLI argument construction for Phase 3 parameters in _build_cli_args."""

    def test_diff_type_string_converts_to_cli_arg(self, semantic_query_manager):
        """Verify diff_type string converts to --diff-type CLI flag."""
        args = semantic_query_manager._build_cli_args(
            query="authentication",
            limit=10,
            diff_type="added",
        )

        assert "--diff-type" in args
        diff_type_index = args.index("--diff-type")
        assert args[diff_type_index + 1] == "added"

    def test_diff_type_array_converts_to_multiple_cli_args(
        self, semantic_query_manager
    ):
        """Verify diff_type array converts to multiple --diff-type CLI flags."""
        args = semantic_query_manager._build_cli_args(
            query="authentication",
            limit=10,
            diff_type=["added", "modified"],
        )

        # Should have two --diff-type flags
        diff_type_indices = [i for i, arg in enumerate(args) if arg == "--diff-type"]
        assert len(diff_type_indices) == 2
        assert args[diff_type_indices[0] + 1] == "added"
        assert args[diff_type_indices[1] + 1] == "modified"

    def test_diff_type_comma_separated_converts_to_multiple_cli_args(
        self, semantic_query_manager
    ):
        """Verify diff_type comma-separated string splits to multiple CLI flags."""
        args = semantic_query_manager._build_cli_args(
            query="authentication",
            limit=10,
            diff_type="added,modified",
        )

        # Should split and create multiple --diff-type flags
        diff_type_indices = [i for i, arg in enumerate(args) if arg == "--diff-type"]
        assert len(diff_type_indices) == 2
        assert args[diff_type_indices[0] + 1] == "added"
        assert args[diff_type_indices[1] + 1] == "modified"

    def test_diff_type_none_omits_cli_arg(self, semantic_query_manager):
        """Verify diff_type=None omits --diff-type CLI flag."""
        args = semantic_query_manager._build_cli_args(
            query="authentication",
            limit=10,
            diff_type=None,
        )

        assert "--diff-type" not in args

    def test_author_converts_to_cli_arg(self, semantic_query_manager):
        """Verify author converts to --author CLI flag."""
        args = semantic_query_manager._build_cli_args(
            query="authentication",
            limit=10,
            author="dev@example.com",
        )

        assert "--author" in args
        author_index = args.index("--author")
        assert args[author_index + 1] == "dev@example.com"

    def test_author_none_omits_cli_arg(self, semantic_query_manager):
        """Verify author=None omits --author CLI flag."""
        args = semantic_query_manager._build_cli_args(
            query="authentication",
            limit=10,
            author=None,
        )

        assert "--author" not in args

    def test_chunk_type_converts_to_cli_arg(self, semantic_query_manager):
        """Verify chunk_type converts to --chunk-type CLI flag."""
        args = semantic_query_manager._build_cli_args(
            query="authentication",
            limit=10,
            chunk_type="commit_message",
        )

        assert "--chunk-type" in args
        chunk_type_index = args.index("--chunk-type")
        assert args[chunk_type_index + 1] == "commit_message"

    def test_chunk_type_none_omits_cli_arg(self, semantic_query_manager):
        """Verify chunk_type=None omits --chunk-type CLI flag."""
        args = semantic_query_manager._build_cli_args(
            query="authentication",
            limit=10,
            chunk_type=None,
        )

        assert "--chunk-type" not in args

    def test_all_phase3_parameters_convert_to_cli_args(self, semantic_query_manager):
        """Verify all Phase 3 parameters convert to CLI arguments together."""
        args = semantic_query_manager._build_cli_args(
            query="authentication",
            limit=10,
            diff_type=["added", "modified"],
            author="dev@example.com",
            chunk_type="commit_diff",
        )

        # Verify diff_type flags
        diff_type_indices = [i for i, arg in enumerate(args) if arg == "--diff-type"]
        assert len(diff_type_indices) == 2
        assert args[diff_type_indices[0] + 1] == "added"
        assert args[diff_type_indices[1] + 1] == "modified"

        # Verify author flag
        assert "--author" in args
        author_index = args.index("--author")
        assert args[author_index + 1] == "dev@example.com"

        # Verify chunk_type flag
        assert "--chunk-type" in args
        chunk_type_index = args.index("--chunk-type")
        assert args[chunk_type_index + 1] == "commit_diff"

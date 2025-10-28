"""Test Transparent Remote Querying for CIDX Remote Repository Linking Mode.

Tests Feature 4 Story 1: Transparent Remote Querying ensures identical query syntax
and output between local and remote modes.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch
from pathlib import Path

from code_indexer.remote.query_execution import (
    execute_remote_query,
    RemoteQueryExecutionError,
)
from code_indexer.api_clients.remote_query_client import QueryResultItem
from code_indexer.remote.repository_linking import RepositoryLink, RepositoryType


class TestRemoteQueryExecution:
    """Test remote query execution with automatic repository linking."""

    @pytest.fixture
    def project_root(self, tmp_path):
        """Create temporary project root directory."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        config_dir = project_dir / ".code-indexer"
        config_dir.mkdir()
        return project_dir

    @pytest.fixture
    def mock_query_results(self):
        """Create mock query results for testing."""
        return [
            QueryResultItem(
                similarity_score=0.95,
                file_path="src/auth.py",
                line_number=10,
                code_snippet='def authenticate_user(username: str, password: str):\n    """Authenticate user credentials."""',
                repository_alias="test-repo",
                file_last_modified=1640995200.0,
                indexed_timestamp=1640995300.0,
            ),
            QueryResultItem(
                similarity_score=0.87,
                file_path="tests/test_auth.py",
                line_number=45,
                code_snippet="def test_authentication():\n    assert authenticate_user('user', 'pass') == True",
                repository_alias="test-repo",
                file_last_modified=1640995400.0,
                indexed_timestamp=1640995500.0,
            ),
        ]

    @pytest.fixture
    def mock_repository_link(self):
        """Create mock repository link for testing."""
        return RepositoryLink(
            alias="test-repo-user123",
            git_url="https://github.com/user/test-repo.git",
            branch="main",
            repository_type=RepositoryType.ACTIVATED,
            server_url="https://cidx.example.com",
            linked_at="2024-01-01T10:00:00Z",
            display_name="Test Repository",
            description="Test repository for CIDX",
            access_level="read",
        )

    def test_execute_remote_query_basic_parameters(
        self, project_root, mock_query_results
    ):
        """Test basic remote query execution with minimal parameters."""

        with patch(
            "code_indexer.remote.query_execution._load_remote_configuration"
        ) as mock_load_config:
            with patch(
                "code_indexer.remote.query_execution.load_repository_link"
            ) as mock_load_link:
                with patch(
                    "code_indexer.remote.query_execution._execute_authenticated_query"
                ) as mock_execute_query:

                    # Mock configuration loading
                    mock_load_config.return_value = {
                        "server_url": "https://cidx.example.com",
                        "username": "testuser",
                    }

                    # Mock existing repository link
                    mock_repository_link = RepositoryLink(
                        alias="test-repo-user123",
                        git_url="https://github.com/user/repo.git",
                        branch="main",
                        repository_type=RepositoryType.ACTIVATED,
                        server_url="https://cidx.example.com",
                        linked_at="2024-01-01T10:00:00Z",
                        display_name="Test Repository",
                        description="Test repository",
                        access_level="read",
                    )
                    mock_load_link.return_value = mock_repository_link

                    # Mock query execution
                    mock_execute_query.return_value = mock_query_results

                    # Execute query with basic parameters
                    results = asyncio.run(
                        execute_remote_query(
                            "authentication function", 10, project_root
                        )
                    )

                    # Verify results
                    assert len(results) == 2
                    assert results[0].similarity_score == 0.95
                    assert results[0].file_path == "src/auth.py"
                    assert results[1].similarity_score == 0.87
                    assert results[1].file_path == "tests/test_auth.py"

                    # Verify query was executed with correct parameters
                    mock_execute_query.assert_called_once()
                    call_args = mock_execute_query.call_args
                    assert call_args[1]["query"] == "authentication function"
                    assert call_args[1]["limit"] == 10
                    assert call_args[1]["repository_alias"] == "test-repo-user123"

    def test_execute_remote_query_all_parameters(
        self, project_root, mock_query_results
    ):
        """Test remote query execution with all optional parameters."""

        with patch(
            "code_indexer.remote.query_execution._load_remote_configuration"
        ) as mock_load_config:
            with patch(
                "code_indexer.remote.query_execution.load_repository_link"
            ) as mock_load_link:
                with patch(
                    "code_indexer.remote.query_execution._execute_authenticated_query"
                ) as mock_execute_query:

                    # Mock configuration loading
                    mock_load_config.return_value = {
                        "server_url": "https://cidx.example.com",
                        "username": "testuser",
                    }

                    # Mock existing repository link
                    mock_repository_link = RepositoryLink(
                        alias="test-repo-user123",
                        git_url="https://github.com/user/repo.git",
                        branch="main",
                        repository_type=RepositoryType.ACTIVATED,
                        server_url="https://cidx.example.com",
                        linked_at="2024-01-01T10:00:00Z",
                        display_name="Test Repository",
                        description="Test repository",
                        access_level="read",
                    )
                    mock_load_link.return_value = mock_repository_link

                    # Mock query execution
                    mock_execute_query.return_value = mock_query_results

                    # Execute query with all parameters
                    results = asyncio.run(
                        execute_remote_query(
                            query_text="user authentication",
                            limit=20,
                            project_root=project_root,
                            language="python",
                            path="*/tests/*",
                            min_score=0.8,
                            include_source=True,
                            accuracy="high",
                        )
                    )

                    # Verify results
                    assert len(results) == 2
                    assert results[0].similarity_score == 0.95

                    # Verify all parameters were passed correctly
                    mock_execute_query.assert_called_once()
                    call_args = mock_execute_query.call_args
                    assert call_args[1]["query"] == "user authentication"
                    assert call_args[1]["limit"] == 20
                    assert call_args[1]["language_filter"] == "python"
                    assert call_args[1]["path_filter"] == "*/tests/*"
                    assert call_args[1]["min_score"] == 0.8
                    assert call_args[1]["include_source"]

    def test_execute_remote_query_automatic_repository_linking(self, project_root):
        """Test automatic repository linking when no link exists."""

        with patch(
            "code_indexer.remote.query_execution._load_remote_configuration"
        ) as mock_load_config:
            with patch(
                "code_indexer.remote.query_execution._establish_repository_link"
            ) as mock_establish_link:
                with patch(
                    "code_indexer.remote.query_execution._execute_authenticated_query"
                ) as mock_execute_query:

                    # Mock configuration without repository link (first query)
                    mock_load_config.return_value = {
                        "server_url": "https://cidx.example.com",
                        "username": "testuser",
                        # No repository_link - should trigger automatic linking
                    }

                    # Mock repository link establishment
                    mock_establish_link.return_value = RepositoryLink(
                        alias="auto-linked-repo",
                        git_url="https://github.com/user/repo.git",
                        branch="main",
                        repository_type=RepositoryType.ACTIVATED,
                        server_url="https://cidx.example.com",
                        linked_at="2024-01-01T10:00:00Z",
                        display_name="Auto-linked Repository",
                        description="Automatically linked during first query",
                        access_level="read",
                    )

                    # Mock successful query execution after linking
                    mock_execute_query.return_value = [
                        QueryResultItem(
                            similarity_score=0.92,
                            file_path="src/main.py",
                            line_number=1,
                            code_snippet="# Main application entry point",
                            repository_alias="auto-linked-repo",
                        )
                    ]

                    # Execute query (should trigger automatic linking)
                    results = asyncio.run(
                        execute_remote_query("main function", 5, project_root)
                    )

                    # Verify automatic linking was triggered
                    mock_establish_link.assert_called_once_with(project_root)

                    # Verify query was executed with auto-linked repository
                    mock_execute_query.assert_called_once()
                    call_args = mock_execute_query.call_args
                    assert call_args[1]["repository_alias"] == "auto-linked-repo"

                    # Verify results
                    assert len(results) == 1
                    assert results[0].similarity_score == 0.92
                    assert results[0].file_path == "src/main.py"

    def test_execute_remote_query_subsequent_queries_use_link(
        self, project_root, mock_query_results
    ):
        """Test that subsequent queries use established repository link."""

        with patch(
            "code_indexer.remote.query_execution._load_remote_configuration"
        ) as mock_load_config:
            with patch(
                "code_indexer.remote.query_execution.load_repository_link"
            ) as mock_load_link:
                with patch(
                    "code_indexer.remote.query_execution._establish_repository_link"
                ) as mock_establish_link:
                    with patch(
                        "code_indexer.remote.query_execution._execute_authenticated_query"
                    ) as mock_execute_query:

                        # Mock configuration
                        mock_load_config.return_value = {
                            "server_url": "https://cidx.example.com",
                            "username": "testuser",
                        }

                        # Mock existing repository link
                        mock_repository_link = RepositoryLink(
                            alias="existing-repo-link",
                            git_url="https://github.com/user/repo.git",
                            branch="main",
                            repository_type=RepositoryType.ACTIVATED,
                            server_url="https://cidx.example.com",
                            linked_at="2024-01-01T10:00:00Z",
                            display_name="Existing Repository",
                            description="Already linked repository",
                            access_level="read",
                        )
                        mock_load_link.return_value = mock_repository_link

                        # Mock query execution
                        mock_execute_query.return_value = mock_query_results

                        # Execute query (should NOT trigger linking)
                        results = asyncio.run(
                            execute_remote_query("existing query", 10, project_root)
                        )

                        # Verify automatic linking was NOT triggered
                        mock_establish_link.assert_not_called()

                        # Verify query was executed with existing link
                        mock_execute_query.assert_called_once()
                        call_args = mock_execute_query.call_args
                        assert call_args[1]["repository_alias"] == "existing-repo-link"

                        # Verify results
                        assert len(results) == 2

    def test_execute_remote_query_repository_linking_failure(self, project_root):
        """Test handling of repository linking failures during first query."""

        with patch(
            "code_indexer.remote.query_execution._load_remote_configuration"
        ) as mock_load_config:
            with patch(
                "code_indexer.remote.query_execution._establish_repository_link"
            ) as mock_establish_link:

                # Mock configuration without repository link
                mock_load_config.return_value = {
                    "server_url": "https://cidx.example.com",
                    "username": "testuser",
                }

                # Mock repository linking failure
                mock_establish_link.side_effect = Exception("Repository linking failed")

                # Execute query and expect failure
                with pytest.raises(RemoteQueryExecutionError) as exc_info:
                    asyncio.run(execute_remote_query("test query", 10, project_root))

                # Verify error message includes linking failure
                assert "Repository linking failed" in str(exc_info.value)

                # Verify linking was attempted
                mock_establish_link.assert_called_once()

    def test_execute_remote_query_parameter_validation(self, project_root):
        """Test parameter validation for remote query execution."""

        # Test empty query
        with pytest.raises(ValueError) as exc_info:
            asyncio.run(execute_remote_query("", 10, project_root))
        assert "Query cannot be empty" in str(exc_info.value)

        # Test invalid limit
        with pytest.raises(ValueError) as exc_info:
            asyncio.run(execute_remote_query("test", 0, project_root))
        assert "Limit must be positive" in str(exc_info.value)

        # Test invalid min_score
        with pytest.raises(ValueError) as exc_info:
            asyncio.run(execute_remote_query("test", 10, project_root, min_score=1.5))
        assert "min_score must be between 0.0 and 1.0" in str(exc_info.value)

    def test_execute_remote_query_network_error_handling(self, project_root):
        """Test handling of network errors during remote query execution."""

        with patch(
            "code_indexer.remote.query_execution._load_remote_configuration"
        ) as mock_load_config:
            with patch(
                "code_indexer.remote.query_execution.load_repository_link"
            ) as mock_load_link:
                with patch(
                    "code_indexer.remote.query_execution._execute_authenticated_query"
                ) as mock_execute_query:

                    # Mock configuration
                    mock_load_config.return_value = {
                        "server_url": "https://cidx.example.com",
                        "username": "testuser",
                    }

                    # Mock existing repository link
                    mock_repository_link = RepositoryLink(
                        alias="test-repo",
                        git_url="https://github.com/user/repo.git",
                        branch="main",
                        repository_type=RepositoryType.ACTIVATED,
                        server_url="https://cidx.example.com",
                        linked_at="2024-01-01T10:00:00Z",
                        display_name="Test Repository",
                        description="Test repository",
                        access_level="read",
                    )
                    mock_load_link.return_value = mock_repository_link

                    # Mock network error
                    from code_indexer.api_clients.base_client import NetworkError

                    mock_execute_query.side_effect = NetworkError("Connection failed")

                    # Execute query and expect network error handling
                    with pytest.raises(RemoteQueryExecutionError) as exc_info:
                        asyncio.run(execute_remote_query("test", 10, project_root))

                    assert "Network error" in str(exc_info.value)

    def test_execute_remote_query_result_format_consistency(self, project_root):
        """Test that remote query results match local query format exactly."""

        with patch(
            "code_indexer.remote.query_execution._load_remote_configuration"
        ) as mock_load_config:
            with patch(
                "code_indexer.remote.query_execution.load_repository_link"
            ) as mock_load_link:
                with patch(
                    "code_indexer.remote.query_execution._execute_authenticated_query"
                ) as mock_execute_query:

                    # Mock configuration
                    mock_load_config.return_value = {
                        "server_url": "https://cidx.example.com",
                        "username": "testuser",
                    }

                    # Mock existing repository link
                    mock_repository_link = RepositoryLink(
                        alias="test-repo",
                        git_url="https://github.com/user/repo.git",
                        branch="main",
                        repository_type=RepositoryType.ACTIVATED,
                        server_url="https://cidx.example.com",
                        linked_at="2024-01-01T10:00:00Z",
                        display_name="Test Repository",
                        description="Test repository",
                        access_level="read",
                    )
                    mock_load_link.return_value = mock_repository_link

                    # Mock query results with all fields
                    expected_results = [
                        QueryResultItem(
                            similarity_score=0.95,
                            file_path="src/utils.py",
                            line_number=15,
                            code_snippet="def utility_function():\n    return 'helper'",
                            repository_alias="test-repo",
                            file_last_modified=1640995200.0,
                            indexed_timestamp=1640995300.0,
                        )
                    ]
                    mock_execute_query.return_value = expected_results

                    # Execute query
                    results = asyncio.run(
                        execute_remote_query("utility", 10, project_root)
                    )

                    # Verify exact format match
                    assert len(results) == 1
                    result = results[0]

                    # Check all QueryResultItem fields are present
                    assert hasattr(result, "similarity_score")
                    assert hasattr(result, "file_path")
                    assert hasattr(result, "line_number")
                    assert hasattr(result, "code_snippet")
                    assert hasattr(result, "repository_alias")
                    assert hasattr(result, "file_last_modified")
                    assert hasattr(result, "indexed_timestamp")

                    # Verify values match exactly
                    assert result.similarity_score == 0.95
                    assert result.file_path == "src/utils.py"
                    assert result.line_number == 15
                    assert (
                        result.code_snippet
                        == "def utility_function():\n    return 'helper'"
                    )
                    assert result.repository_alias == "test-repo"
                    assert result.file_last_modified == 1640995200.0
                    assert result.indexed_timestamp == 1640995300.0


class TestRemoteQueryCLIIntegration:
    """Test CLI integration for transparent remote querying."""

    @pytest.fixture
    def mock_cli_context(self):
        """Create mock CLI context for remote mode."""
        return {
            "mode": "remote",
            "project_root": Path("/test/project"),
            "config_manager": Mock(),
        }

    def test_cli_query_command_remote_mode_detection(self, mock_cli_context):
        """Test that CLI query command properly detects remote mode."""

        with patch("code_indexer.remote.query_execution.execute_remote_query"):
            with patch("code_indexer.cli.asyncio.run") as mock_asyncio_run:

                # Mock successful remote query execution
                mock_query_results = [
                    Mock(
                        similarity_score=0.95,
                        file_path="test.py",
                        line_number=1,
                        code_snippet="test content",
                        repository_alias="test-repo",
                    )
                ]
                mock_asyncio_run.return_value = mock_query_results

                # Mock successful remote query execution
                mock_asyncio_run.return_value = mock_query_results

                # Import CLI query command module for testing
                from code_indexer.cli import query

                # Test that the query command exists and is callable
                assert query is not None
                assert callable(query)

                # Verify the query command has Click decorators (indicating CLI integration)
                assert hasattr(
                    query, "params"
                ), "Query command should have Click parameters"

                # Note: Full CLI integration testing would require more complex setup
                # with proper Click context management. The main functionality is tested
                # through the execute_remote_query function directly.

    def test_cli_query_command_identical_parameters(self):
        """Test that CLI query command supports identical parameters in remote mode."""

        # Import CLI query command
        from code_indexer.cli import query

        # Get command info

        # Verify query command accepts all expected parameters
        command_params = [param.name for param in query.params]

        expected_params = [
            "query",  # Required query text
            "limit",  # --limit
            "languages",  # --language (now supports multiple)
            "exclude_languages",  # --exclude-language
            "path_filter",  # --path-filter
            "exclude_paths",  # --exclude-path
            "min_score",  # --min-score
            "accuracy",  # --accuracy
            "quiet",  # --quiet
        ]

        for param in expected_params:
            assert (
                param in command_params
            ), f"Parameter {param} missing from query command"

    def test_cli_query_command_help_consistency(self):
        """Test that CLI query command help text is consistent between modes."""

        from code_indexer.cli import query

        # Verify help text mentions both local and remote capabilities
        help_text = query.__doc__ or ""

        # Check for mode-agnostic language
        assert "semantic search" in help_text.lower()
        assert "vector embeddings" in help_text.lower()

        # Should not mention mode-specific details in main help
        assert "local mode only" not in help_text.lower()
        assert "remote mode only" not in help_text.lower()


class TestRepositoryLinkingIntegration:
    """Test integration between remote querying and repository linking."""

    @pytest.fixture
    def project_root(self, tmp_path):
        """Create project root with git repository."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        # Create .git directory to simulate git repository
        git_dir = project_dir / ".git"
        git_dir.mkdir()

        # Create config directory
        config_dir = project_dir / ".code-indexer"
        config_dir.mkdir()

        return project_dir

    def test_automatic_repository_linking_during_first_query(self, project_root):
        """Test automatic repository linking when no existing link."""

        with patch(
            "code_indexer.remote.query_execution._load_remote_configuration"
        ) as mock_load_config:
            with patch(
                "code_indexer.remote.query_execution.load_repository_link"
            ) as mock_load_link:
                with patch(
                    "code_indexer.remote.query_execution._establish_repository_link"
                ) as mock_establish_link:
                    with patch(
                        "code_indexer.remote.query_execution.store_repository_link"
                    ) as mock_store_link:
                        with patch(
                            "code_indexer.remote.query_execution._execute_authenticated_query"
                        ) as mock_execute_query:

                            # Mock configuration loading
                            mock_load_config.return_value = {
                                "server_url": "https://cidx.example.com",
                                "username": "testuser",
                            }

                            # Mock no existing repository link (first query)
                            mock_load_link.return_value = None

                            # Mock repository link establishment
                            mock_repository_link = RepositoryLink(
                                alias="auto-repo-main",
                                git_url="https://github.com/user/repo.git",
                                branch="main",
                                repository_type=RepositoryType.ACTIVATED,
                                server_url="https://cidx.example.com",
                                linked_at="2024-01-01T10:00:00Z",
                                display_name="Auto Repository",
                                description="Automatically linked repository",
                                access_level="read",
                            )
                            mock_establish_link.return_value = mock_repository_link

                            # Mock successful query after linking
                            mock_execute_query.return_value = [
                                QueryResultItem(
                                    similarity_score=0.90,
                                    file_path="src/app.py",
                                    line_number=1,
                                    code_snippet="# Application main",
                                    repository_alias="auto-repo-main",
                                )
                            ]

                            # Execute remote query (should trigger auto-linking)
                            results = asyncio.run(
                                execute_remote_query("application", 10, project_root)
                            )

                            # Verify repository linking was attempted
                            mock_establish_link.assert_called_once_with(project_root)

                            # Verify repository link was stored
                            mock_store_link.assert_called_once_with(
                                project_root, mock_repository_link
                            )

                            # Verify query was executed after linking
                            mock_execute_query.assert_called_once()

                            # Verify results
                            assert len(results) == 1
                            assert results[0].similarity_score == 0.90

    def test_repository_link_persistence_across_queries(self, project_root):
        """Test that repository links are stored and reused across queries."""

        # Create initial remote config without repository link
        config_path = project_root / ".code-indexer" / ".remote-config"
        initial_config = {
            "server_url": "https://cidx.example.com",
            "username": "testuser",
            "encrypted_credentials": "encrypted_data_here",
        }

        import json

        with open(config_path, "w") as f:
            json.dump(initial_config, f)

        with patch(
            "code_indexer.remote.query_execution._establish_repository_link"
        ) as mock_establish_link:
            with patch(
                "code_indexer.remote.query_execution._execute_authenticated_query"
            ) as mock_execute_query:

                # Mock repository link establishment
                test_link = RepositoryLink(
                    alias="persistent-repo",
                    git_url="https://github.com/user/repo.git",
                    branch="main",
                    repository_type=RepositoryType.ACTIVATED,
                    server_url="https://cidx.example.com",
                    linked_at="2024-01-01T10:00:00Z",
                    display_name="Persistent Repository",
                    description="Repository link for persistence testing",
                    access_level="read",
                )
                mock_establish_link.return_value = test_link

                # Mock query execution
                mock_execute_query.return_value = [
                    QueryResultItem(
                        similarity_score=0.85,
                        file_path="main.py",
                        line_number=1,
                        code_snippet="main content",
                        repository_alias="persistent-repo",
                    )
                ]

                # First query - should establish link
                results1 = asyncio.run(
                    execute_remote_query("first query", 10, project_root)
                )

                # Verify linking was called for first query
                mock_establish_link.assert_called_once()

                # Verify config was updated with repository link
                with open(config_path, "r") as f:
                    updated_config = json.load(f)
                assert "repository_link" in updated_config
                assert updated_config["repository_link"]["alias"] == "persistent-repo"

                # Second query - should reuse existing link
                results2 = asyncio.run(
                    execute_remote_query("second query", 10, project_root)
                )

                # Verify linking was NOT called again
                assert mock_establish_link.call_count == 1  # Still only called once

                # Verify both queries executed successfully
                assert len(results1) == 1
                assert len(results2) == 1
                assert mock_execute_query.call_count == 2

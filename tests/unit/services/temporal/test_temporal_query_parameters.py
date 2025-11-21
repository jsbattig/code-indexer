"""Tests for temporal query parameter changes (diff-based system).

Test coverage:
1. REMOVAL: --include-removed parameter (obsolete in diff-based system)
2. ADDITION: --diff-type parameter (filter by change type)
3. ADDITION: --author parameter (filter by commit author)

All tests follow TDD approach with failing tests written first.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock

from src.code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchService,
)


# ==================== FIXTURES ====================


@pytest.fixture
def mock_config_manager():
    """Mock ConfigManager for tests."""
    config = Mock()
    config.filesystem = Mock()
    config.filesystem.host = "localhost"
    config.filesystem.port = 6333
    return config


@pytest.fixture
def mock_vector_store():
    """Mock vector store client."""
    from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

    store = Mock(spec=FilesystemVectorStore)
    store.collection_exists = Mock(return_value=True)
    store.search = Mock(return_value=[])
    return store


@pytest.fixture
def mock_embedding_provider():
    """Mock embedding provider."""
    provider = Mock()
    provider.get_embedding = Mock(return_value=[0.1] * 1536)
    return provider


@pytest.fixture
def temporal_service(mock_config_manager, mock_vector_store, mock_embedding_provider):
    """TemporalSearchService instance with mocks."""
    return TemporalSearchService(
        config_manager=mock_config_manager,
        project_root=Path("/tmp/test-repo"),
        vector_store_client=mock_vector_store,
        embedding_provider=mock_embedding_provider,
        collection_name="code-indexer-temporal",
    )


@pytest.fixture
def sample_search_results():
    """Sample search results with diverse diff types and authors.

    NEW FORMAT: chunk_text at root level (not in payload)
    """
    from datetime import datetime

    base_timestamp = int(datetime(2025, 11, 1).timestamp())

    return [
        {
            "score": 0.95,
            "chunk_text": "def new_feature():\n    pass",  # NEW FORMAT
            "payload": {
                "file_path": "src/feature.py",
                "chunk_index": 0,
                "commit_hash": "abc123",
                "commit_date": "2025-11-01",
                "commit_message": "Add new feature",
                "author_name": "Alice Developer",
                "author_email": "alice@example.com",
                "commit_timestamp": base_timestamp,
                "diff_type": "added",
            },
        },
        {
            "score": 0.88,
            "chunk_text": "def fix_bug():\n    # Fixed",  # NEW FORMAT
            "payload": {
                "file_path": "src/bug_fix.py",
                "chunk_index": 0,
                "commit_hash": "def456",
                "commit_date": "2025-11-02",
                "commit_message": "Fix critical bug",
                "author_name": "Bob Tester",
                "author_email": "bob@example.com",
                "commit_timestamp": base_timestamp + 86400,
                "diff_type": "modified",
            },
        },
        {
            "score": 0.82,
            "chunk_text": "# Deleted file content",  # NEW FORMAT
            "payload": {
                "file_path": "src/deprecated.py",
                "chunk_index": 0,
                "commit_hash": "ghi789",
                "commit_date": "2025-11-03",
                "commit_message": "Remove deprecated code",
                "author_name": "Alice Developer",
                "author_email": "alice@example.com",
                "commit_timestamp": base_timestamp + 86400 * 2,
                "diff_type": "deleted",
            },
        },
    ]


# ==================== TEST 1: REMOVE --include-removed ====================


class TestIncludeRemovedRemoval:
    """Tests verifying --include-removed parameter removal."""

    def test_query_temporal_signature_no_include_removed(self, temporal_service):
        """Test that query_temporal signature doesn't have include_removed parameter.

        EXPECTED FAILURE: This test will fail until include_removed is removed from signature.
        """
        import inspect

        sig = inspect.signature(temporal_service.query_temporal)

        # Verify include_removed is NOT in parameters
        assert (
            "include_removed" not in sig.parameters
        ), "include_removed parameter should be removed from query_temporal signature"

    def test_filter_by_time_range_signature_no_include_removed(self, temporal_service):
        """Test that _filter_by_time_range signature doesn't have include_removed parameter.

        EXPECTED FAILURE: This test will fail until include_removed is removed from signature.
        """
        import inspect

        sig = inspect.signature(temporal_service._filter_by_time_range)

        # Verify include_removed is NOT in parameters
        assert (
            "include_removed" not in sig.parameters
        ), "include_removed parameter should be removed from _filter_by_time_range signature"

    def test_query_temporal_calls_filter_without_include_removed(
        self, temporal_service, mock_vector_store
    ):
        """Test that query_temporal calls _filter_by_time_range without include_removed.

        EXPECTED FAILURE: This test will fail until the call site is updated.
        """
        from datetime import datetime
        from unittest.mock import patch

        # Setup mock to return sample results
        # NEW FORMAT: chunk_text at root level
        sample_results = [
            {
                "score": 0.95,
                "chunk_text": "test content",  # NEW FORMAT
                "payload": {
                    "file_path": "test.py",
                    "chunk_index": 0,
                    "commit_hash": "abc123",
                    "commit_date": "2025-11-01",
                    "commit_message": "Test commit",
                    "author_name": "Test Author",
                    "commit_timestamp": int(datetime(2025, 11, 1).timestamp()),
                    "diff_type": "added",
                },
            }
        ]
        mock_vector_store.search.return_value = (sample_results, {})

        # Patch _filter_by_time_range to verify it's called without include_removed
        with patch.object(
            temporal_service, "_filter_by_time_range", return_value=([], 0.0)
        ) as mock_filter:
            temporal_service.query_temporal(
                query="test query",
                time_range=("2025-11-01", "2025-11-05"),
                limit=10,
            )

            # Verify _filter_by_time_range was called
            mock_filter.assert_called_once()

            # Verify include_removed was NOT passed as an argument
            call_args = mock_filter.call_args
            assert (
                "include_removed" not in call_args.kwargs
            ), "include_removed should not be passed to _filter_by_time_range"

    def test_cli_query_command_no_include_removed_parameter(self):
        """Test that CLI query command doesn't have --include-removed option.

        EXPECTED FAILURE: This test will fail until --include-removed is removed from CLI.
        """
        from click.testing import CliRunner
        from src.code_indexer.cli import query

        runner = CliRunner()
        result = runner.invoke(query, ["--help"])

        # Verify --include-removed is NOT in help output
        assert (
            "--include-removed" not in result.output
        ), "--include-removed option should be removed from CLI query command"

    def test_cli_code_does_not_reference_include_removed(self):
        """Test that CLI code doesn't reference include_removed variable.

        EXPECTED FAILURE: This test will fail until all include_removed references are removed from CLI code.
        """
        from pathlib import Path

        cli_path = (
            Path(__file__).parent.parent.parent.parent.parent
            / "src"
            / "code_indexer"
            / "cli.py"
        )
        cli_content = cli_path.read_text()

        # Check that include_removed is not referenced in the query command code
        # We need to ensure no variable references remain (validation, usage in calls, etc.)
        assert (
            "include_removed" not in cli_content
        ), "include_removed variable should be completely removed from CLI code"


# ==================== TEST 2: ADD --diff-type ====================


class TestDiffTypeParameter:
    """Tests for --diff-type parameter implementation."""

    def test_query_temporal_accepts_diff_types_parameter(
        self, temporal_service, mock_vector_store, sample_search_results
    ):
        """Test that query_temporal accepts diff_types parameter.

        EXPECTED FAILURE: This test will fail until diff_types parameter is added.
        """
        import inspect

        sig = inspect.signature(temporal_service.query_temporal)

        # Verify diff_types IS in parameters
        assert (
            "diff_types" in sig.parameters
        ), "diff_types parameter should be added to query_temporal signature"

    def test_filter_by_single_diff_type(
        self, temporal_service, mock_vector_store, sample_search_results
    ):
        """Test filtering by single diff type.

        EXPECTED FAILURE: This test will fail until diff_type filtering is implemented.
        """

        # Setup mock to return all sample results
        mock_vector_store.search.return_value = (sample_search_results, {})

        # Query with diff_types=["added"] - should return only "added" results
        results = temporal_service.query_temporal(
            query="test query",
            time_range=("2025-11-01", "2025-11-05"),
            diff_types=["added"],
            limit=10,
        )

        # Verify only "added" results are returned
        assert (
            len(results.results) == 1
        ), f"Expected 1 result, got {len(results.results)}"
        assert results.results[0].metadata["diff_type"] == "added"
        assert results.results[0].metadata["file_path"] == "src/feature.py"

    def test_filter_by_multiple_diff_types(
        self, temporal_service, mock_vector_store, sample_search_results
    ):
        """Test filtering by multiple diff types.

        EXPECTED FAILURE: This test will fail until multiple diff_type filtering is implemented.
        """
        # Setup mock to return all sample results
        mock_vector_store.search.return_value = (sample_search_results, {})

        # Query with diff_types=["added", "modified"] - should return both added and modified
        results = temporal_service.query_temporal(
            query="test query",
            time_range=("2025-11-01", "2025-11-05"),
            diff_types=["added", "modified"],
            limit=10,
        )

        # Verify both "added" and "modified" results are returned (but not "deleted")
        assert (
            len(results.results) == 2
        ), f"Expected 2 results, got {len(results.results)}"
        diff_types = [r.metadata["diff_type"] for r in results.results]
        assert "added" in diff_types
        assert "modified" in diff_types
        assert "deleted" not in diff_types

    def test_filter_by_none_diff_types(
        self, temporal_service, mock_vector_store, sample_search_results
    ):
        """Test that None diff_types returns all results.

        EXPECTED FAILURE: This test will fail until None handling is implemented.
        """
        # Setup mock to return all sample results
        mock_vector_store.search.return_value = (sample_search_results, {})

        # Query with diff_types=None - should return ALL results
        results = temporal_service.query_temporal(
            query="test query",
            time_range=("2025-11-01", "2025-11-05"),
            diff_types=None,
            limit=10,
        )

        # Verify all 3 results are returned (added, modified, deleted)
        assert (
            len(results.results) == 3
        ), f"Expected 3 results, got {len(results.results)}"
        diff_types = [r.metadata["diff_type"] for r in results.results]
        assert "added" in diff_types
        assert "modified" in diff_types
        assert "deleted" in diff_types

    def test_filter_by_empty_diff_types(
        self, temporal_service, mock_vector_store, sample_search_results
    ):
        """Test that empty diff_types list returns all results.

        EXPECTED FAILURE: This test will fail until empty list handling is implemented.
        """
        # Setup mock to return all sample results
        mock_vector_store.search.return_value = (sample_search_results, {})

        # Query with diff_types=[] - should return ALL results
        results = temporal_service.query_temporal(
            query="test query",
            time_range=("2025-11-01", "2025-11-05"),
            diff_types=[],
            limit=10,
        )

        # Verify all 3 results are returned (added, modified, deleted)
        assert (
            len(results.results) == 3
        ), f"Expected 3 results, got {len(results.results)}"
        diff_types = [r.metadata["diff_type"] for r in results.results]
        assert "added" in diff_types
        assert "modified" in diff_types
        assert "deleted" in diff_types

    def test_cli_has_diff_type_option(self):
        """Test that CLI query command has --diff-type option.

        EXPECTED FAILURE: This test will fail until --diff-type is added to CLI.
        """
        from click.testing import CliRunner
        from src.code_indexer.cli import query

        runner = CliRunner()
        result = runner.invoke(query, ["--help"])

        # Verify --diff-type IS in help output
        assert (
            "--diff-type" in result.output
        ), "--diff-type option should be added to CLI query command"


# ==================== TEST 3: ADD --author ====================


class TestAuthorParameter:
    """Tests for --author parameter implementation."""

    def test_query_temporal_accepts_author_parameter(
        self, temporal_service, mock_vector_store, sample_search_results
    ):
        """Test that query_temporal accepts author parameter.

        EXPECTED FAILURE: This test will fail until author parameter is added.
        """
        import inspect

        sig = inspect.signature(temporal_service.query_temporal)

        # Verify author IS in parameters
        assert (
            "author" in sig.parameters
        ), "author parameter should be added to query_temporal signature"

    def test_filter_by_author_name(
        self, temporal_service, mock_vector_store, sample_search_results
    ):
        """Test filtering by author name (partial, case-insensitive).

        EXPECTED FAILURE: This test will fail until author filtering is implemented.
        """
        # Setup mock to return all sample results
        mock_vector_store.search.return_value = (sample_search_results, {})

        # Query with author="alice" - should match "Alice Developer"
        results = temporal_service.query_temporal(
            query="test query",
            time_range=("2025-11-01", "2025-11-05"),
            author="alice",
            limit=10,
        )

        # Verify only Alice's results are returned (2 results: added and deleted)
        assert (
            len(results.results) == 2
        ), f"Expected 2 results, got {len(results.results)}"
        for result in results.results:
            assert "alice" in result.metadata["author_name"].lower()

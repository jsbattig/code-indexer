"""Unit tests for temporal metadata in QueryResult (Story #503).

Tests that temporal query results include proper metadata and temporal_context
fields in the QueryResult objects returned by _execute_temporal_query.

This ensures MCP/REST API parity with CLI for temporal search responses.
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.code_indexer.server.query.semantic_query_manager import (
    QueryResult,
    SemanticQueryManager,
)
from src.code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchResult,
    TemporalSearchResults,
)


class TestQueryResultTemporalMetadata:
    """Test QueryResult dataclass includes temporal metadata fields."""

    def test_query_result_has_metadata_field(self):
        """Verify QueryResult dataclass has metadata field."""
        result = QueryResult(
            file_path="test.py",
            line_number=1,
            code_snippet="def test(): pass",
            similarity_score=0.85,
            repository_alias="test-repo",
        )
        assert hasattr(result, "metadata")
        assert result.metadata is None  # Default is None

    def test_query_result_has_temporal_context_field(self):
        """Verify QueryResult dataclass has temporal_context field."""
        result = QueryResult(
            file_path="test.py",
            line_number=1,
            code_snippet="def test(): pass",
            similarity_score=0.85,
            repository_alias="test-repo",
        )
        assert hasattr(result, "temporal_context")
        assert result.temporal_context is None  # Default is None

    def test_query_result_accepts_metadata_in_constructor(self):
        """Verify QueryResult accepts metadata in constructor."""
        metadata = {
            "commit_hash": "abc123",
            "commit_date": "2025-05-28",
            "author_name": "Test Author",
            "author_email": "test@example.com",
            "commit_message": "Test commit message",
            "diff_type": "modified",
        }
        result = QueryResult(
            file_path="test.py",
            line_number=1,
            code_snippet="def test(): pass",
            similarity_score=0.85,
            repository_alias="test-repo",
            metadata=metadata,
        )
        assert result.metadata == metadata

    def test_query_result_accepts_temporal_context_in_constructor(self):
        """Verify QueryResult accepts temporal_context in constructor."""
        temporal_context = {
            "first_seen": "2025-03-24",
            "last_seen": "2025-05-28",
            "commit_count": 5,
            "commits": ["abc123", "def456"],
        }
        result = QueryResult(
            file_path="test.py",
            line_number=1,
            code_snippet="def test(): pass",
            similarity_score=0.85,
            repository_alias="test-repo",
            temporal_context=temporal_context,
        )
        assert result.temporal_context == temporal_context

    def test_to_dict_includes_metadata_when_present(self):
        """Verify to_dict() includes metadata when present."""
        metadata = {
            "commit_hash": "abc123",
            "commit_date": "2025-05-28",
            "author_name": "Test Author",
            "author_email": "test@example.com",
            "commit_message": "Test commit message",
            "diff_type": "modified",
        }
        result = QueryResult(
            file_path="test.py",
            line_number=1,
            code_snippet="def test(): pass",
            similarity_score=0.85,
            repository_alias="test-repo",
            metadata=metadata,
        )
        result_dict = result.to_dict()
        assert "metadata" in result_dict
        assert result_dict["metadata"] == metadata

    def test_to_dict_includes_temporal_context_when_present(self):
        """Verify to_dict() includes temporal_context when present."""
        temporal_context = {
            "first_seen": "2025-03-24",
            "last_seen": "2025-05-28",
            "commit_count": 5,
            "commits": ["abc123", "def456"],
        }
        result = QueryResult(
            file_path="test.py",
            line_number=1,
            code_snippet="def test(): pass",
            similarity_score=0.85,
            repository_alias="test-repo",
            temporal_context=temporal_context,
        )
        result_dict = result.to_dict()
        assert "temporal_context" in result_dict
        assert result_dict["temporal_context"] == temporal_context

    def test_to_dict_excludes_metadata_when_none(self):
        """Verify to_dict() excludes metadata when None."""
        result = QueryResult(
            file_path="test.py",
            line_number=1,
            code_snippet="def test(): pass",
            similarity_score=0.85,
            repository_alias="test-repo",
            metadata=None,
        )
        result_dict = result.to_dict()
        assert "metadata" not in result_dict

    def test_to_dict_excludes_temporal_context_when_none(self):
        """Verify to_dict() excludes temporal_context when None."""
        result = QueryResult(
            file_path="test.py",
            line_number=1,
            code_snippet="def test(): pass",
            similarity_score=0.85,
            repository_alias="test-repo",
            temporal_context=None,
        )
        result_dict = result.to_dict()
        assert "temporal_context" not in result_dict

    def test_to_dict_includes_both_metadata_and_temporal_context(self):
        """Verify to_dict() includes both fields when both are present."""
        metadata = {
            "commit_hash": "abc123",
            "commit_date": "2025-05-28",
            "author_name": "Test Author",
            "author_email": "test@example.com",
            "commit_message": "Test commit message",
            "diff_type": "modified",
        }
        temporal_context = {
            "first_seen": "2025-03-24",
            "last_seen": "2025-05-28",
            "commit_count": 5,
            "commits": ["abc123", "def456"],
        }
        result = QueryResult(
            file_path="test.py",
            line_number=1,
            code_snippet="def test(): pass",
            similarity_score=0.85,
            repository_alias="test-repo",
            metadata=metadata,
            temporal_context=temporal_context,
        )
        result_dict = result.to_dict()
        assert "metadata" in result_dict
        assert "temporal_context" in result_dict
        assert result_dict["metadata"] == metadata
        assert result_dict["temporal_context"] == temporal_context


class TestExecuteTemporalQueryMetadataExtraction:
    """Test _execute_temporal_query extracts and passes temporal metadata correctly."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def mock_activated_repo_manager(self):
        """Mock activated repo manager."""
        mock = MagicMock()
        mock.list_activated_repositories.return_value = [
            {
                "user_alias": "my-repo",
                "golden_repo_alias": "test-repo",
                "current_branch": "main",
                "activated_at": "2024-01-01T00:00:00Z",
                "last_accessed": "2024-01-01T00:00:00Z",
            },
        ]

        def get_repo_path(username, user_alias):
            temp_path = Path(tempfile.gettempdir()) / f"repos-{username}-{user_alias}"
            temp_path.mkdir(parents=True, exist_ok=True)
            return str(temp_path)

        mock.get_activated_repo_path.side_effect = get_repo_path
        return mock

    @pytest.fixture
    def semantic_query_manager(self, temp_data_dir, mock_activated_repo_manager):
        """Create semantic query manager with mocked dependencies."""
        return SemanticQueryManager(
            data_dir=temp_data_dir,
            activated_repo_manager=mock_activated_repo_manager,
        )

    def test_execute_temporal_query_extracts_commit_metadata(
        self, semantic_query_manager, temp_data_dir
    ):
        """Verify _execute_temporal_query extracts commit metadata from temporal results.

        This is the key test - temporal results should have metadata field populated
        with commit_hash, commit_date, author_name, author_email, commit_message, diff_type.
        """
        # Create temporal search results using real dataclasses
        temporal_result = TemporalSearchResult(
            file_path="src/example.py",
            chunk_index=0,
            content="def example(): pass",
            score=0.85,
            metadata={
                "commit_hash": "0b7b331",
                "commit_date": "2025-05-28",
                "author_name": "Ryan Pearson",
                "author_email": "ryan.pearson@example.com",
                "commit_message": "EVO-45522 Making changes to the Layout.",
                "diff_type": "modified",
            },
            temporal_context={
                "first_seen": "2025-03-24",
                "last_seen": "2025-05-28",
                "appearance_count": 5,
                "commits": ["abc123", "def456", "0b7b331"],
            },
        )

        temporal_results = TemporalSearchResults(
            results=[temporal_result],
            query="example",
            filter_type="time_range",
            filter_value=("2025-01-01", "2025-12-31"),
            total_found=1,
        )

        # Create a mock repo path with .code-indexer config
        repo_path = Path(temp_data_dir) / "test-repo"
        repo_path.mkdir(parents=True, exist_ok=True)
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Mock all dependencies - patch at source modules since these are lazy imports
        with (
            patch(
                "src.code_indexer.proxy.config_manager.ConfigManager"
            ) as MockConfigManager,
            patch(
                "src.code_indexer.backends.backend_factory.BackendFactory"
            ) as MockBackendFactory,
            patch(
                "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory"
            ) as MockEmbeddingFactory,
            patch(
                "src.code_indexer.services.temporal.temporal_search_service.TemporalSearchService"
            ) as MockTemporalService,
        ):
            # Setup config manager mock
            mock_config = MagicMock()
            mock_config_manager = MagicMock()
            mock_config_manager.get_config.return_value = mock_config
            MockConfigManager.create_with_backtrack.return_value = mock_config_manager

            # Setup backend mock
            mock_backend = MagicMock()
            mock_vector_store = MagicMock()
            mock_backend.get_vector_store_client.return_value = mock_vector_store
            MockBackendFactory.create.return_value = mock_backend

            # Setup embedding provider mock
            mock_embedding = MagicMock()
            MockEmbeddingFactory.create.return_value = mock_embedding

            # Setup temporal service mock
            mock_temporal_service = MagicMock()
            mock_temporal_service.has_temporal_index.return_value = True
            mock_temporal_service._validate_date_range.return_value = (
                "2025-01-01",
                "2025-12-31",
            )
            mock_temporal_service.query_temporal.return_value = temporal_results
            MockTemporalService.return_value = mock_temporal_service
            MockTemporalService.TEMPORAL_COLLECTION_NAME = "code-indexer-temporal"

            # Execute temporal query
            results = semantic_query_manager._execute_temporal_query(
                repo_path=repo_path,
                repository_alias="test-repo",
                query_text="example",
                limit=10,
                min_score=None,
                time_range="2025-01-01..2025-12-31",
                at_commit=None,
                include_removed=False,
                show_evolution=False,
                evolution_limit=None,
            )

            # Verify results
            assert len(results) == 1
            result = results[0]

            # KEY ASSERTION: metadata field should be populated
            assert result.metadata is not None
            assert result.metadata["commit_hash"] == "0b7b331"
            assert result.metadata["commit_date"] == "2025-05-28"
            assert result.metadata["author_name"] == "Ryan Pearson"
            assert result.metadata["author_email"] == "ryan.pearson@example.com"
            assert (
                result.metadata["commit_message"]
                == "EVO-45522 Making changes to the Layout."
            )
            assert result.metadata["diff_type"] == "modified"

    def test_execute_temporal_query_includes_temporal_context(
        self, semantic_query_manager, temp_data_dir
    ):
        """Verify _execute_temporal_query includes temporal_context in QueryResult."""
        temporal_result = TemporalSearchResult(
            file_path="src/example.py",
            chunk_index=0,
            content="def example(): pass",
            score=0.85,
            metadata={
                "commit_hash": "0b7b331",
                "commit_date": "2025-05-28",
                "author_name": "Test Author",
                "author_email": "test@example.com",
                "commit_message": "Test commit",
                "diff_type": "modified",
            },
            temporal_context={
                "first_seen": "2025-03-24",
                "last_seen": "2025-05-28",
                "appearance_count": 5,
                "commits": ["abc123", "def456", "0b7b331"],
            },
        )

        temporal_results = TemporalSearchResults(
            results=[temporal_result],
            query="example",
            filter_type="time_range",
            filter_value=("2025-01-01", "2025-12-31"),
            total_found=1,
        )

        repo_path = Path(temp_data_dir) / "test-repo"
        repo_path.mkdir(parents=True, exist_ok=True)
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch(
                "src.code_indexer.proxy.config_manager.ConfigManager"
            ) as MockConfigManager,
            patch(
                "src.code_indexer.backends.backend_factory.BackendFactory"
            ) as MockBackendFactory,
            patch(
                "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory"
            ) as MockEmbeddingFactory,
            patch(
                "src.code_indexer.services.temporal.temporal_search_service.TemporalSearchService"
            ) as MockTemporalService,
        ):
            mock_config = MagicMock()
            mock_config_manager = MagicMock()
            mock_config_manager.get_config.return_value = mock_config
            MockConfigManager.create_with_backtrack.return_value = mock_config_manager

            mock_backend = MagicMock()
            mock_vector_store = MagicMock()
            mock_backend.get_vector_store_client.return_value = mock_vector_store
            MockBackendFactory.create.return_value = mock_backend

            mock_embedding = MagicMock()
            MockEmbeddingFactory.create.return_value = mock_embedding

            mock_temporal_service = MagicMock()
            mock_temporal_service.has_temporal_index.return_value = True
            mock_temporal_service._validate_date_range.return_value = (
                "2025-01-01",
                "2025-12-31",
            )
            mock_temporal_service.query_temporal.return_value = temporal_results
            MockTemporalService.return_value = mock_temporal_service
            MockTemporalService.TEMPORAL_COLLECTION_NAME = "code-indexer-temporal"

            results = semantic_query_manager._execute_temporal_query(
                repo_path=repo_path,
                repository_alias="test-repo",
                query_text="example",
                limit=10,
                min_score=None,
                time_range="2025-01-01..2025-12-31",
                at_commit=None,
                include_removed=False,
                show_evolution=False,
                evolution_limit=None,
            )

            assert len(results) == 1
            result = results[0]

            # KEY ASSERTION: temporal_context field should be populated
            assert result.temporal_context is not None
            assert result.temporal_context["first_seen"] == "2025-03-24"
            assert result.temporal_context["last_seen"] == "2025-05-28"
            assert result.temporal_context["commit_count"] == 5
            assert result.temporal_context["commits"] == ["abc123", "def456", "0b7b331"]

    def test_execute_temporal_query_to_dict_produces_expected_mcp_response(
        self, semantic_query_manager, temp_data_dir
    ):
        """Verify QueryResult.to_dict() produces the expected MCP response format.

        This tests the complete flow from temporal query to JSON-serializable dict.
        """
        temporal_result = TemporalSearchResult(
            file_path="code/src/dms/PartsTransferPanel.java",
            chunk_index=0,
            content="public class PartsTransferPanel {}",
            score=0.627,
            metadata={
                "commit_hash": "0b7b331",
                "commit_date": "2025-05-28",
                "author_name": "Ryan Pearson",
                "author_email": "ryan.pearson@lightspeeddms.com",
                "commit_message": "EVO-45522 Making changes to the PartsTransferPanel Layout.",
                "diff_type": "modified",
            },
            temporal_context={
                "first_seen": "2025-03-24",
                "last_seen": "2025-05-28",
                "appearance_count": 5,
                "commits": [
                    {"hash": "abc123", "date": "2025-03-24"},
                    {"hash": "def456", "date": "2025-04-15"},
                    {"hash": "0b7b331", "date": "2025-05-28"},
                ],
            },
        )

        temporal_results = TemporalSearchResults(
            results=[temporal_result],
            query="PartsTransferPanel",
            filter_type="time_range",
            filter_value=("2025-01-01", "2025-12-31"),
            total_found=1,
        )

        repo_path = Path(temp_data_dir) / "test-repo"
        repo_path.mkdir(parents=True, exist_ok=True)
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch(
                "src.code_indexer.proxy.config_manager.ConfigManager"
            ) as MockConfigManager,
            patch(
                "src.code_indexer.backends.backend_factory.BackendFactory"
            ) as MockBackendFactory,
            patch(
                "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory"
            ) as MockEmbeddingFactory,
            patch(
                "src.code_indexer.services.temporal.temporal_search_service.TemporalSearchService"
            ) as MockTemporalService,
        ):
            mock_config = MagicMock()
            mock_config_manager = MagicMock()
            mock_config_manager.get_config.return_value = mock_config
            MockConfigManager.create_with_backtrack.return_value = mock_config_manager

            mock_backend = MagicMock()
            mock_vector_store = MagicMock()
            mock_backend.get_vector_store_client.return_value = mock_vector_store
            MockBackendFactory.create.return_value = mock_backend

            mock_embedding = MagicMock()
            MockEmbeddingFactory.create.return_value = mock_embedding

            mock_temporal_service = MagicMock()
            mock_temporal_service.has_temporal_index.return_value = True
            mock_temporal_service._validate_date_range.return_value = (
                "2025-01-01",
                "2025-12-31",
            )
            mock_temporal_service.query_temporal.return_value = temporal_results
            MockTemporalService.return_value = mock_temporal_service
            MockTemporalService.TEMPORAL_COLLECTION_NAME = "code-indexer-temporal"

            results = semantic_query_manager._execute_temporal_query(
                repo_path=repo_path,
                repository_alias="evolution-temporal-global",
                query_text="PartsTransferPanel",
                limit=10,
                min_score=None,
                time_range="2025-01-01..2025-12-31",
                at_commit=None,
                include_removed=False,
                show_evolution=False,
                evolution_limit=None,
            )

            assert len(results) == 1
            result = results[0]

            # Convert to dict (what MCP API returns)
            result_dict = result.to_dict()

            # Verify full expected MCP response structure
            assert result_dict["file_path"] == "code/src/dms/PartsTransferPanel.java"
            assert result_dict["line_number"] == 1
            assert result_dict["code_snippet"] == "public class PartsTransferPanel {}"
            assert result_dict["similarity_score"] == 0.627
            assert result_dict["repository_alias"] == "evolution-temporal-global"
            assert result_dict["source_repo"] is None

            # Verify metadata in response
            assert "metadata" in result_dict
            assert result_dict["metadata"]["commit_hash"] == "0b7b331"
            assert result_dict["metadata"]["commit_date"] == "2025-05-28"
            assert result_dict["metadata"]["author_name"] == "Ryan Pearson"
            assert (
                result_dict["metadata"]["author_email"]
                == "ryan.pearson@lightspeeddms.com"
            )
            assert (
                result_dict["metadata"]["commit_message"]
                == "EVO-45522 Making changes to the PartsTransferPanel Layout."
            )
            assert result_dict["metadata"]["diff_type"] == "modified"

            # Verify temporal_context in response
            assert "temporal_context" in result_dict
            assert result_dict["temporal_context"]["first_seen"] == "2025-03-24"
            assert result_dict["temporal_context"]["last_seen"] == "2025-05-28"
            assert result_dict["temporal_context"]["commit_count"] == 5

    def test_execute_temporal_query_handles_missing_metadata_fields_gracefully(
        self, semantic_query_manager, temp_data_dir
    ):
        """Verify _execute_temporal_query handles missing metadata fields gracefully."""
        # Create temporal result with minimal metadata
        temporal_result = TemporalSearchResult(
            file_path="src/example.py",
            chunk_index=0,
            content="def example(): pass",
            score=0.85,
            metadata={
                "commit_hash": "abc123",
                # Missing: commit_date, author_name, author_email, commit_message, diff_type
            },
            temporal_context={
                "first_seen": "2025-03-24",
                # Missing: last_seen, appearance_count, commits
            },
        )

        temporal_results = TemporalSearchResults(
            results=[temporal_result],
            query="example",
            filter_type="time_range",
            filter_value=("2025-01-01", "2025-12-31"),
            total_found=1,
        )

        repo_path = Path(temp_data_dir) / "test-repo"
        repo_path.mkdir(parents=True, exist_ok=True)
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch(
                "src.code_indexer.proxy.config_manager.ConfigManager"
            ) as MockConfigManager,
            patch(
                "src.code_indexer.backends.backend_factory.BackendFactory"
            ) as MockBackendFactory,
            patch(
                "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory"
            ) as MockEmbeddingFactory,
            patch(
                "src.code_indexer.services.temporal.temporal_search_service.TemporalSearchService"
            ) as MockTemporalService,
        ):
            mock_config = MagicMock()
            mock_config_manager = MagicMock()
            mock_config_manager.get_config.return_value = mock_config
            MockConfigManager.create_with_backtrack.return_value = mock_config_manager

            mock_backend = MagicMock()
            mock_vector_store = MagicMock()
            mock_backend.get_vector_store_client.return_value = mock_vector_store
            MockBackendFactory.create.return_value = mock_backend

            mock_embedding = MagicMock()
            MockEmbeddingFactory.create.return_value = mock_embedding

            mock_temporal_service = MagicMock()
            mock_temporal_service.has_temporal_index.return_value = True
            mock_temporal_service._validate_date_range.return_value = (
                "2025-01-01",
                "2025-12-31",
            )
            mock_temporal_service.query_temporal.return_value = temporal_results
            MockTemporalService.return_value = mock_temporal_service
            MockTemporalService.TEMPORAL_COLLECTION_NAME = "code-indexer-temporal"

            # Should not raise exception with missing fields
            results = semantic_query_manager._execute_temporal_query(
                repo_path=repo_path,
                repository_alias="test-repo",
                query_text="example",
                limit=10,
                min_score=None,
                time_range="2025-01-01..2025-12-31",
                at_commit=None,
                include_removed=False,
                show_evolution=False,
                evolution_limit=None,
            )

            assert len(results) == 1
            result = results[0]

            # Metadata should exist with available fields (others None)
            assert result.metadata is not None
            assert result.metadata["commit_hash"] == "abc123"
            assert result.metadata.get("commit_date") is None
            assert result.metadata.get("author_name") is None

            # Temporal context should exist with available fields
            assert result.temporal_context is not None
            assert result.temporal_context["first_seen"] == "2025-03-24"

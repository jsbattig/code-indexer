"""Test suite for Story 2 critical violations fixes.

Tests verify critical violations are fixed per code review.
"""

from pathlib import Path
from unittest.mock import Mock

from src.code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchService
)


class TestMethodDeletions:
    """Verify that obsolete methods have been deleted."""

    def test_fetch_commit_file_changes_deleted(self):
        """Verify _fetch_commit_file_changes method no longer exists."""
        # Create service instance
        mock_config_manager = Mock()
        service = TemporalSearchService(
            config_manager=mock_config_manager,
            project_root=Path("/test/repo")
        )

        # Verify method doesn't exist
        assert not hasattr(service, "_fetch_commit_file_changes"), (
            "_fetch_commit_file_changes() should be deleted per spec line 166"
        )

    def test_fetch_blob_content_deleted(self):
        """Verify _fetch_blob_content method no longer exists."""
        # Create service instance
        mock_config_manager = Mock()
        service = TemporalSearchService(
            config_manager=mock_config_manager,
            project_root=Path("/test/repo")
        )

        # Verify method doesn't exist
        assert not hasattr(service, "_fetch_blob_content"), (
            "_fetch_blob_content() should be deleted - all blob-based helpers removed"
        )


class TestFetchMatchContent:
    """Verify _fetch_match_content has no blob_hash references."""

    def test_no_blob_hash_logic_in_fetch_match_content(self):
        """Verify _fetch_match_content doesn't reference blob_hash."""
        import inspect

        mock_config_manager = Mock()
        service = TemporalSearchService(
            config_manager=mock_config_manager,
            project_root=Path("/test/repo")
        )

        # Get the source code of _fetch_match_content
        source = inspect.getsource(service._fetch_match_content)

        # Check for blob_hash references (should be removed per spec line 320)
        assert "blob_hash" not in source, (
            "_fetch_match_content should not reference blob_hash per spec line 320"
        )


class TestContentDisplay:
    """Verify content is fetched from payload, not placeholders."""

    def test_filter_by_time_range_uses_payload_content(self):
        """Verify _filter_by_time_range uses content from payload."""
        mock_config_manager = Mock()
        service = TemporalSearchService(
            config_manager=mock_config_manager,
            project_root=Path("/test/repo")
        )

        # Create mock semantic results with content in payload
        actual_content = "def authenticate(user, password):\n    return True"
        semantic_results = [
            Mock(
                payload={
                    "type": "commit_diff",
                    "commit_hash": "abc123",
                    "commit_timestamp": 1730505600,  # 2024-11-01
                    "commit_date": "2024-11-01",
                    "commit_message": "Add authentication",
                    "author_name": "Test User",
                    "file_path": "src/auth.py",
                    "chunk_index": 0,
                    "diff_type": "added",
                    "content": actual_content  # Actual content in payload
                },
                content="[Placeholder text]",  # Placeholder in result.content
                score=0.95
            )
        ]

        # Filter by time range (returns tuple of results and fetch_time)
        result_tuple = service._filter_by_time_range(
            semantic_results,
            start_date="2024-11-01",
            end_date="2024-11-01",
        )

        # Extract results from tuple
        results = result_tuple[0]
        fetch_time = result_tuple[1]

        # Verify result uses actual content from payload, not placeholder
        assert len(results) == 1
        assert results[0].content == actual_content, (
            "Should use payload['content'], not result.content placeholder"
        )
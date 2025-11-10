"""Test that old blob-based code is properly cleaned up for Story 2."""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from src.code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchService,
    TemporalSearchResult,
)


class TestBlobCodeCleanup:
    """Test that old blob-based code paths are no longer used."""

    def test_filter_by_time_range_handles_diff_payloads_only(self):
        """Test that _filter_by_time_range processes diff-based payloads correctly."""
        # Arrange
        mock_config_manager = MagicMock()
        service = TemporalSearchService(
            config_manager=mock_config_manager,
            project_root=Path("/tmp/test_project"),
        )
        service.commits_db_path = Path("/tmp/test_commits.db")

        # Create semantic results with new diff-based payload
        # NEW FORMAT: chunk_text at root level
        semantic_results = [
            {
                "score": 0.95,
                "chunk_text": "test content",  # NEW FORMAT: chunk_text at root level
                "payload": {
                    "type": "commit_diff",  # New diff-based type
                    "commit_hash": "abc123",
                    "file_path": "src/file.py",
                    "diff_type": "modified",
                    "chunk_index": 0,
                    "line_start": 1,
                    "line_end": 10,
                    "commit_timestamp": 1700000000,
                },
            }
        ]

        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()

            # Mock the commits query to return our test commit
            mock_cursor.__iter__ = MagicMock(
                return_value=iter(
                    [
                        {
                            "commit_hash": "abc123",
                            "commit_date": 1700000000,
                            "commit_message": "Test commit",
                            "author_name": "Test Author",
                        }
                    ]
                )
            )
            mock_cursor.__getitem__ = lambda self, key: {
                "commit_hash": "abc123",
                "commit_date": 1700000000,
                "commit_message": "Test commit",
                "author_name": "Test Author",
            }[key]

            mock_conn.execute.return_value = mock_cursor
            mock_conn.row_factory = None
            mock_connect.return_value = mock_conn

            # Mock _fetch_match_content to return test content
            with patch.object(
                service, "_fetch_match_content", return_value="test content"
            ):
                # Act
                results, fetch_time = service._filter_by_time_range(
                    semantic_results,
                    "2023-11-14",
                    "2023-11-16",
                )

                # Assert
                assert len(results) == 1
                result = results[0]
                assert isinstance(result, TemporalSearchResult)
                assert result.file_path == "src/file.py"
                assert result.metadata["diff_type"] == "modified"
                assert result.temporal_context["diff_type"] == "modified"
                # Should NOT have old blob-based fields
                assert "first_seen" not in result.temporal_context
                assert "last_seen" not in result.temporal_context
                assert "appearance_count" not in result.temporal_context


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
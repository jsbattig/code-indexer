"""Test that methods querying trees table are properly handled for Story 2."""

import pytest
from unittest.mock import MagicMock, patch
import sqlite3
from pathlib import Path
from src.code_indexer.services.temporal.temporal_search_service import TemporalSearchService


class TestTreesTableRemoval:
    """Test that trees table queries are removed/handled correctly."""

    def test_fetch_commit_file_changes_no_trees_table(self):
        """Test that _fetch_commit_file_changes handles missing trees table gracefully."""
        # Arrange
        mock_config_manager = MagicMock()
        service = TemporalSearchService(
            config_manager=mock_config_manager,
            project_root=Path("/tmp/test_project"),
        )
        service.commits_db_path = Path("/tmp/test_commits.db")

        # Mock database without trees table
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()

            # Simulate OperationalError when querying non-existent trees table
            mock_cursor.execute.side_effect = sqlite3.OperationalError("no such table: trees")
            mock_conn.execute.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            # Act
            result = service._fetch_commit_file_changes("abc123def456")

            # Assert - should return empty list instead of crashing
            assert result == []

    def test_fetch_commit_file_changes_returns_empty_for_diff_based(self):
        """Test that _fetch_commit_file_changes returns empty list with diff-based indexing."""
        # Arrange
        mock_config_manager = MagicMock()
        service = TemporalSearchService(
            config_manager=mock_config_manager,
            project_root=Path("/tmp/test_project"),
        )
        service.commits_db_path = Path("/tmp/test_commits.db")

        # Act - calling the actual method (no mocking)
        # This test verifies the method should return empty list for diff-based indexing
        with patch('src.code_indexer.services.temporal.temporal_search_service.sqlite3.connect') as mock_connect:
            # Mock a valid connection that would normally work
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.__iter__ = MagicMock(return_value=iter([]))  # No rows
            mock_conn.execute.return_value = mock_cursor
            mock_conn.row_factory = None
            mock_connect.return_value = mock_conn

            result = service._fetch_commit_file_changes("abc123def456")

            # Assert - with diff-based indexing, should return empty list
            assert result == [], "Should return empty list for diff-based indexing"
            # Should not attempt to query trees table in diff-based world
            mock_conn.execute.assert_not_called()

    def test_is_new_file_returns_false_for_diff_based(self):
        """Test that _is_new_file returns False with diff-based indexing."""
        # Arrange
        mock_config_manager = MagicMock()
        service = TemporalSearchService(
            config_manager=mock_config_manager,
            project_root=Path("/tmp/test_project"),
        )
        service.commits_db_path = Path("/tmp/test_commits.db")

        # Act & Assert
        # With diff-based indexing, this method should not query trees table
        result = service._is_new_file("src/file.py", "abc123def456")

        # Should return False (conservative default) without querying database
        assert result == False, "Should return False for diff-based indexing"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
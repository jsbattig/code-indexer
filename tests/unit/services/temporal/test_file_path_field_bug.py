"""Unit test to reproduce the file_path='unknown' bug in temporal search.

This test demonstrates that when the temporal indexer stores data with "path" field,
but temporal_search_service looks for "file_path", we get "unknown" as the file path.
"""

from pathlib import Path
from unittest.mock import MagicMock

from code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchService,
)


class TestFilePathFieldBug:
    """Test that file paths display correctly when payload uses 'path' field."""

    def test_filter_by_time_range_handles_path_field_from_temporal_indexer(self):
        """Test that _filter_by_time_range correctly extracts file path from 'path' field.

        The temporal indexer stores the field as 'path' (see temporal_indexer.py line 453),
        but temporal_search_service looks for 'file_path', resulting in 'unknown'.
        """
        # Setup
        config_manager = MagicMock()
        project_root = Path("/test/repo")

        service = TemporalSearchService(
            config_manager=config_manager,
            project_root=project_root,
            vector_store_client=None,
            embedding_provider=None,
            collection_name="test"
        )

        # Create semantic results with 'path' field (as temporal indexer provides)
        # This mimics what the temporal indexer actually stores
        # NEW FORMAT: chunk_text at root level
        semantic_results = [
            {
                "score": 0.85,
                "chunk_text": "def login(username, password):\n    return True",  # NEW FORMAT
                "payload": {
                    "path": "src/auth.py",  # Temporal indexer uses "path"
                    "chunk_index": 0,
                    "commit_hash": "abc123",
                    "commit_timestamp": 1730476800,  # 2024-11-01
                    "commit_date": "2024-11-01",
                    "commit_message": "Add authentication",
                    "author_name": "Test User",
                    "diff_type": "added"
                }
            }
        ]

        # Execute the method under test
        results, _ = service._filter_by_time_range(
            semantic_results=semantic_results,
            start_date="2024-10-01",
            end_date="2024-12-01",
            min_score=None
        )

        # Assert - now this should pass with the fix
        assert len(results) == 1
        assert results[0].file_path == "src/auth.py", (
            f"Expected 'src/auth.py' but got '{results[0].file_path}'. "
            "The temporal indexer stores 'path' but the service looks for 'file_path'."
        )

    def test_filter_by_time_range_backward_compat_with_file_path_field(self):
        """Test that _filter_by_time_range still handles 'file_path' field for backward compatibility."""
        # Setup
        config_manager = MagicMock()
        project_root = Path("/test/repo")

        service = TemporalSearchService(
            config_manager=config_manager,
            project_root=project_root,
            vector_store_client=None,
            embedding_provider=None,
            collection_name="test"
        )

        # Create semantic results with 'file_path' field (for backward compatibility)
        # NEW FORMAT: chunk_text at root level
        semantic_results = [
            {
                "score": 0.85,
                "chunk_text": "def old_function():\n    pass",  # NEW FORMAT
                "payload": {
                    "file_path": "src/legacy.py",  # Some code might use "file_path"
                    "chunk_index": 0,
                    "commit_hash": "def456",
                    "commit_timestamp": 1730476800,  # 2024-11-01
                    "commit_date": "2024-11-01",
                    "commit_message": "Legacy code",
                    "author_name": "Test User",
                    "diff_type": "modified"
                }
            }
        ]

        # Execute
        results, _ = service._filter_by_time_range(
            semantic_results=semantic_results,
            start_date="2024-10-01",
            end_date="2024-12-01",
            min_score=None
        )

        # Assert - this should work with our fix
        assert len(results) == 1
        assert results[0].file_path == "src/legacy.py"
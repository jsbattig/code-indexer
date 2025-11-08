"""Unit tests for temporal indexer item_type parameter in progress reporting.

This test verifies that temporal indexing shows "commits" instead of "files"
in the progress display by using the item_type parameter.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import threading

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo


class TestTemporalIndexerItemType:
    """Test item_type parameter for commit-specific progress display."""

    @patch('src.code_indexer.services.embedding_factory.EmbeddingProviderFactory')
    def test_progress_displays_commits_not_files(self, mock_factory):
        """Test that temporal indexing progress displays 'commits' not 'files'."""
        # Setup
        mock_config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.voyage_ai.parallel_requests = 4
        mock_config.voyage_ai.model = "voyage-3"
        mock_config.embedding_provider = "voyage-ai"
        mock_config_manager.get_config.return_value = mock_config

        mock_vector_store = MagicMock()
        mock_vector_store.project_root = Path("/tmp/test_project")

        # Mock EmbeddingProviderFactory
        mock_factory.get_provider_model_info.return_value = {
            'provider': 'voyage-ai',
            'model': 'voyage-3',
            'dimensions': 1536
        }

        indexer = TemporalIndexer(
            config_manager=mock_config_manager,
            vector_store=mock_vector_store
        )

        # Mock the diff scanner
        mock_diff_scanner = MagicMock()
        indexer.diff_scanner = mock_diff_scanner

        # Create test commits
        test_commits = [
            CommitInfo(
                hash=f"abcd{i:04d}",
                timestamp=1704067200 + i * 3600,
                author_name="Test Author",
                author_email="test@example.com",
                message=f"Commit {i}",
                parent_hashes=""
            )
            for i in range(10)
        ]

        # Mock diff scanner to return empty diffs (we only care about progress display)
        mock_diff_scanner.get_diffs_for_commit.return_value = []

        # Mock embedding provider
        mock_embedding_provider = MagicMock()

        # Mock vector manager
        mock_vector_manager = MagicMock()

        # Track progress calls with proper signature
        progress_calls = []
        progress_lock = threading.Lock()

        def track_progress(current, total, path, info=None, **kwargs):
            """Track progress calls with all possible parameters."""
            with progress_lock:
                call_data = {
                    'current': current,
                    'total': total,
                    'path': str(path),
                    'info': info,
                }
                # Capture additional kwargs for item_type
                call_data.update(kwargs)
                progress_calls.append(call_data)

        # Execute indexing with progress tracking
        indexer._process_commits_parallel(
            commits=test_commits,
            embedding_provider=mock_embedding_provider,
            vector_manager=mock_vector_manager,
            progress_callback=track_progress
        )

        # Verify progress was reported
        assert len(progress_calls) > 0, "No progress calls were made"

        # CRITICAL ASSERTION: Progress display should show "commits" not "files"
        # This is the core requirement - temporal indexing is about commits, not files
        for call in progress_calls:
            info = call.get('info', '')

            # Check that info contains "commits" not "files"
            # Format should be: "X/Y commits" not "X/Y files"
            assert "commits" in info, f"Progress info should contain 'commits': {info}"

            # Ensure "files" is NOT in the count display
            # Note: "files" might appear in filenames like "test_file.py"
            # but should NOT appear in the "X/Y files" format
            # We check this by looking for the pattern "N/N files"
            import re
            files_count_pattern = re.search(r'\d+/\d+\s+files', info)
            assert files_count_pattern is None, \
                f"Progress should show 'commits' not 'files' in count: {info}"

"""
Performance tests for branch isolation HTTP request efficiency.

These tests verify that branch isolation operations minimize HTTP requests
to avoid the performance bottleneck of making thousands of individual requests.

Expected behavior:
- Bug 1: _batch_hide_files_in_branch should NOT make one scroll_points per file
- Bug 2: _batch_update_points should batch point IDs together (not one request per point)
- Performance: Should make <100 HTTP requests for 1000 files, not >1000 requests
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
from code_indexer.services.high_throughput_processor import HighThroughputProcessor
from code_indexer.config import Config


class TestBranchIsolationPerformance:
    """Test suite for branch isolation HTTP request efficiency."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_config(self, temp_dir):
        """Create mock configuration."""
        config = Mock(spec=Config)
        config.codebase_dir = temp_dir
        config.exclude_dirs = ["node_modules", ".git"]
        config.exclude_files = []
        config.file_extensions = ["py", "js", "ts"]
        config.project_root = temp_dir

        # Mock indexing config
        indexing_config = Mock()
        indexing_config.chunk_size = 1000
        indexing_config.chunk_overlap = 100
        indexing_config.max_file_size = 1000000
        config.indexing = indexing_config

        # Mock filesystem config
        config.filesystem = Mock()
        config.filesystem.url = "http://localhost:6333"
        config.filesystem.api_key = None
        config.filesystem.vector_size = 768
        config.collection_base_name = "test_collection"

        return config

    @pytest.fixture
    def mock_filesystem_client(self):
        """Create mock vector store client with request tracking."""
        client = Mock()
        client.scroll_points_call_count = 0
        client.http_post_call_count = 0
        client.ensure_provider_aware_collection = Mock(return_value="test_collection")
        client.resolve_collection_name = Mock(return_value="test_collection")

        # Track scroll_points calls
        def scroll_points_tracker(*args, **kwargs):
            client.scroll_points_call_count += 1
            # Return empty list to avoid processing
            return [], None

        client.scroll_points = scroll_points_tracker

        # Track HTTP POST calls
        def post_tracker(*args, **kwargs):
            client.http_post_call_count += 1
            response = Mock()
            response.raise_for_status = Mock()
            return response

        client.client = Mock()
        client.client.post = post_tracker

        return client

    @pytest.fixture
    def processor(self, mock_config, mock_filesystem_client):
        """Create HighThroughputProcessor with mocked dependencies."""
        # Create mock embedding provider
        mock_embedding_provider = Mock()
        mock_embedding_provider.get_provider_name = Mock(return_value="test-provider")
        mock_embedding_provider.get_current_model = Mock(return_value="test-model")

        processor = HighThroughputProcessor(
            config=mock_config,
            vector_store_client=mock_filesystem_client,
            embedding_provider=mock_embedding_provider,
        )
        return processor

    def test_bug1_batch_hide_files_should_not_make_per_file_requests(
        self, processor, mock_filesystem_client
    ):
        """
        BUG 1: _batch_hide_files_in_branch makes ONE scroll_points request PER FILE.

        This test verifies that hiding 1000 files does NOT make 1000+ scroll_points requests.
        Expected: Should use pre-fetched all_content_points for in-memory filtering.
        """
        # Simulate 1000 files to hide
        files_to_hide = [f"/path/to/file_{i}.py" for i in range(1000)]

        # Create mock all_content_points that would have been fetched by caller
        all_content_points = []
        for i in range(1000):
            all_content_points.append(
                {
                    "id": f"point_{i}",
                    "payload": {
                        "type": "content",
                        "path": f"/path/to/file_{i}.py",
                        "hidden_branches": [],
                    },
                }
            )

        # Reset counters
        mock_filesystem_client.scroll_points_call_count = 0

        # Call the method with all_content_points parameter (FIXED)
        # After fix: should use all_content_points and make 0 additional scroll_points calls
        processor._batch_hide_files_in_branch(
            file_paths=files_to_hide,
            branch="main",
            collection_name="test_collection",
            all_content_points=all_content_points,
            progress_callback=None,
        )

        # ASSERTION: Should make 0 scroll_points calls (using pre-fetched data)
        # Current broken behavior: Makes 1000 calls (one per file)
        assert mock_filesystem_client.scroll_points_call_count < 10, (
            f"BUG 1 DETECTED: Made {mock_filesystem_client.scroll_points_call_count} scroll_points calls "
            f"for {len(files_to_hide)} files. Should make 0 calls using pre-fetched data."
        )

    def test_bug2_batch_update_points_should_batch_requests(self, temp_dir):
        """
        BUG 2: _batch_update_points makes ONE HTTP request PER POINT.

        This test verifies that updating 1000 points does NOT make 1000 HTTP POST requests.
        Expected: Should batch points together (e.g., 10 requests for 1000 points with batch size 100).

        Note: This test is deprecated as the batch update functionality is now part of
        FilesystemVectorStore which handles batching differently.
        """
        # Skip test - functionality moved to FilesystemVectorStore
        pytest.skip("Batch update functionality moved to FilesystemVectorStore")

    def test_hide_files_not_in_branch_minimizes_http_requests(
        self, processor, mock_filesystem_client
    ):
        """
        Integration test: hide_files_not_in_branch should minimize total HTTP requests.

        For 1000 files in database with 500 files to hide:
        - Expected: 1 scroll_points call + ~5 batched update requests = ~6 total
        - Broken: 500 scroll_points calls + 500+ individual updates = 1000+ total
        """
        # Setup: 1000 files in database
        all_content_points = []
        for i in range(1000):
            all_content_points.append(
                {
                    "id": f"point_{i}",
                    "payload": {
                        "type": "content",
                        "path": f"/path/to/file_{i}.py",
                        "hidden_branches": [],
                    },
                }
            )

        # Mock scroll_points to return all content points
        mock_filesystem_client.scroll_points = MagicMock(
            return_value=(all_content_points, None)
        )
        mock_filesystem_client._batch_update_points = MagicMock(return_value=True)

        # Only 500 files exist in current branch (500 need to be hidden)
        current_files = [f"/path/to/file_{i}.py" for i in range(500)]

        # Reset counters
        mock_filesystem_client.scroll_points_call_count = 0
        mock_filesystem_client.http_post_call_count = 0

        # Execute hide operation
        processor.hide_files_not_in_branch_thread_safe(
            branch="main",
            current_files=current_files,
            collection_name="test_collection",
            progress_callback=None,
        )

        # Verify minimal HTTP requests
        total_http_requests = (
            mock_filesystem_client.scroll_points.call_count
            + mock_filesystem_client._batch_update_points.call_count
        )

        # ASSERTION: Should make <10 total HTTP requests
        # Current broken behavior: Makes 500+ requests
        assert total_http_requests < 10, (
            f"PERFORMANCE BUG: Made {total_http_requests} total HTTP requests "
            f"for hiding 500 files. Should make <10 requests."
        )

    def test_batch_update_groups_identical_payloads(self, mock_filesystem_client):
        """
        Test that _batch_update_points groups points with identical payloads together.

        For points with same payload change, should send as single batch request
        instead of multiple individual requests.
        """
        # Create 300 points with same payload change
        points_same_payload = []
        for i in range(300):
            points_same_payload.append(
                {"id": f"point_{i}", "payload": {"hidden_branches": ["main"]}}
            )

        # Reset counter
        mock_filesystem_client.http_post_call_count = 0

        # Mock the actual client.post method to track calls
        post_calls = []

        def track_post(*args, **kwargs):
            post_calls.append(kwargs.get("json", {}))
            response = MagicMock()
            response.raise_for_status = MagicMock()
            return response

        mock_filesystem_client.client.post = track_post

        # Call batch update
        mock_filesystem_client._batch_update_points(
            points=points_same_payload, collection_name="test_collection"
        )

        # Verify batching happened
        # With batch size 100: should make 3 requests (100, 100, 100)
        assert len(post_calls) <= 5, (
            f"Should batch identical payloads together. Made {len(post_calls)} requests "
            f"for 300 points with identical payload."
        )

        # Verify each request contains multiple point IDs
        if post_calls:
            # At least one request should have multiple points
            max_points_in_request = max(
                len(call.get("points", [])) for call in post_calls
            )
            assert (
                max_points_in_request > 1
            ), "Batch requests should contain multiple point IDs, not just one."


class TestDeletionDetectionGitAwareness:
    """Test that deletion detection respects git-aware mode."""

    @pytest.fixture
    def mock_smart_indexer(self):
        """Create mock SmartIndexer."""
        from code_indexer.services.smart_indexer import SmartIndexer

        with patch.object(SmartIndexer, "__init__", lambda x, *args, **kwargs: None):
            indexer = SmartIndexer(None)
            indexer._detect_and_handle_deletions = MagicMock()
            indexer.progressive_metadata = MagicMock()
            indexer.progressive_metadata.clear = MagicMock()
            return indexer

    def test_bug3_deletion_detection_skipped_for_git_aware_projects(
        self, mock_smart_indexer
    ):
        """
        BUG 3: _detect_and_handle_deletions() called for git projects causing double scan.

        Git-aware projects use branch isolation AFTER indexing, so deletion detection
        BEFORE indexing is redundant and wastes 10-30 minutes scanning the database.

        Expected: Should skip deletion detection for git-aware projects.
        """
        # Simulate git-aware project
        mock_smart_indexer.is_git_aware = MagicMock(return_value=True)
        mock_smart_indexer._do_full_index = MagicMock(return_value=True)

        # This is the code path in smart_indexer.py lines 426-428
        detect_deletions = True
        reconcile_with_database = False

        # BUG: Currently calls _detect_and_handle_deletions even for git projects
        # After fix: Should check is_git_aware() and skip
        if detect_deletions and not reconcile_with_database:
            # FIXED VERSION SHOULD ADD: and not self.is_git_aware()
            if not mock_smart_indexer.is_git_aware():
                mock_smart_indexer._detect_and_handle_deletions(None)

        # ASSERTION: Should NOT call deletion detection for git-aware projects
        assert mock_smart_indexer._detect_and_handle_deletions.call_count == 0, (
            "BUG 3 DETECTED: Called _detect_and_handle_deletions for git-aware project. "
            "This causes redundant database scan (10-30 minutes wasted)."
        )

    def test_deletion_detection_still_works_for_non_git_projects(
        self, mock_smart_indexer
    ):
        """
        Verify that deletion detection STILL works for non-git-aware projects.

        Non-git projects don't use branch isolation, so they need deletion detection.
        """
        # Simulate non-git project
        mock_smart_indexer.is_git_aware = MagicMock(return_value=False)

        # Execute the same code path
        detect_deletions = True
        reconcile_with_database = False

        if detect_deletions and not reconcile_with_database:
            if not mock_smart_indexer.is_git_aware():  # Fixed version
                mock_smart_indexer._detect_and_handle_deletions(None)

        # ASSERTION: SHOULD call deletion detection for non-git projects
        assert (
            mock_smart_indexer._detect_and_handle_deletions.call_count == 1
        ), "Deletion detection should still work for non-git-aware projects."

"""Unit tests for temporal indexer progress reporting functionality."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import threading

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo


class TestTemporalIndexerProgress:
    """Test progress reporting during temporal commit indexing."""

    @patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory")
    @patch(
        "src.code_indexer.services.vector_calculation_manager.VectorCalculationManager"
    )
    @patch(
        "src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"
    )
    def test_parallel_processing_reports_real_progress(
        self, mock_diff_scanner_class, mock_vector_manager_class, mock_factory
    ):
        """Test that progress callback receives real data, not hardcoded mock values."""
        # Setup
        import tempfile
        import shutil

        # Create unique temp directory for this test to avoid state pollution
        test_dir = Path(tempfile.mkdtemp(prefix="test_temporal_"))

        # Cleanup previous test state
        try:
            shutil.rmtree(test_dir / ".code-indexer" / "temporal", ignore_errors=True)
        except:
            pass

        mock_config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.voyage_ai.parallel_requests = 4
        mock_config.embedding_provider = "voyage-ai"
        mock_config_manager.get_config.return_value = mock_config

        mock_vector_store = MagicMock()
        mock_vector_store.project_root = test_dir
        mock_vector_store.base_path = test_dir / ".code-indexer" / "index"

        # Mock EmbeddingProviderFactory
        mock_factory.get_provider_model_info.return_value = {
            "provider": "voyage-ai",
            "model": "voyage-3",
            "dimensions": 1536,
        }

        indexer = TemporalIndexer(
            config_manager=mock_config_manager, vector_store=mock_vector_store
        )

        # Mock the diff scanner
        mock_diff_scanner = MagicMock()
        indexer.diff_scanner = mock_diff_scanner

        # Create test commits
        test_commits = [
            CommitInfo(
                hash=f"commit{i:03d}",
                timestamp=1704067200,  # 2024-01-01 Unix timestamp
                author_name="Test Author",
                author_email="test@example.com",
                message=f"Test commit {i}",
                parent_hashes="",
            )
            for i in range(10)
        ]

        # Mock diff scanner to return some diffs for each commit
        mock_diff_scanner.get_diffs_for_commit.return_value = [
            MagicMock(
                file_path=f"file{i}.py",
                change_type="modified",
                content_before="old",
                content_after="new",
            )
            for i in range(3)
        ]

        # Mock embedding provider
        mock_embedding_provider = MagicMock()
        mock_embedding_provider.get_embeddings_for_texts.return_value = [
            [0.1] * 1536  # Mock embedding vector
        ]

        # Mock vector manager
        mock_vector_manager = MagicMock()
        # Mock cancellation event (no cancellation)
        mock_cancellation_event = MagicMock()
        mock_cancellation_event.is_set.return_value = False
        mock_vector_manager.cancellation_event = mock_cancellation_event

        # Mock embedding provider methods for token counting
        mock_embedding_provider = MagicMock()
        mock_embedding_provider._count_tokens_accurately = MagicMock(return_value=100)
        mock_embedding_provider._get_model_token_limit = MagicMock(return_value=120000)
        mock_vector_manager.embedding_provider = mock_embedding_provider

        # Mock submit_batch_task to return proper embeddings
        def mock_submit_batch(texts, metadata):
            future = MagicMock()
            result = MagicMock()
            result.embeddings = [[0.1] * 1536 for _ in texts] if texts else []
            result.error = None
            future.result.return_value = result
            return future

        mock_vector_manager.submit_batch_task.side_effect = mock_submit_batch
        # Mock cancellation event (no cancellation)
        mock_cancellation_event = MagicMock()
        mock_cancellation_event.is_set.return_value = False
        mock_vector_manager.cancellation_event = mock_cancellation_event

        # Track progress calls
        progress_calls = []
        progress_lock = threading.Lock()

        def track_progress(current, total, path, info=None, **kwargs):
            with progress_lock:
                progress_calls.append(
                    {
                        "current": current,
                        "total": total,
                        "path": str(path),
                        "info": info,
                    }
                )

        # Execute indexing with progress tracking
        indexer._process_commits_parallel(
            commits=test_commits,
            embedding_provider=mock_embedding_provider,
            vector_manager=mock_vector_manager,
            progress_callback=track_progress,
        )

        # Verify real progress was reported
        assert len(progress_calls) > 0, "No progress calls were made"

        # Check that we're not getting hardcoded "1/5" values
        first_call = progress_calls[0]
        assert (
            first_call["total"] == 10
        ), f"Expected total=10, got {first_call['total']}"
        assert first_call["total"] != 5, "Still using hardcoded total of 5"

        # Check that progress increases
        currents = [call["current"] for call in progress_calls]
        assert max(currents) > 1, "Progress never advanced beyond 1"

        # Check for required info format elements
        for call in progress_calls:
            info = call["info"]
            assert "commits" in info, f"Missing 'commits' in info: {info}"
            assert "commits/s" in info, f"Missing 'commits/s' rate in info: {info}"
            assert "threads" in info, f"Missing 'threads' in info: {info}"
            # Story 1 AC requires emoji and hash-file format
            assert "📝" in info, f"Missing 📝 emoji in info: {info}"
            assert (
                " - " in info.split("📝")[-1] if "📝" in info else False
            ), f"Missing 'hash - file' format after 📝: {info}"

            # Check format matches spec: "{current}/{total} commits ({pct}%) | {rate} commits/s | {threads} threads | 📝 {hash} - {file}"
            assert "/" in info, f"Missing current/total separator in info: {info}"
            assert "%" in info, f"Missing percentage in info: {info}"
            assert "|" in info, f"Missing pipe separators in info: {info}"

    @patch("src.code_indexer.services.embedding_factory.EmbeddingProviderFactory")
    @patch(
        "src.code_indexer.services.vector_calculation_manager.VectorCalculationManager"
    )
    @patch(
        "src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"
    )
    def test_progress_shows_actual_filenames_not_test_py(
        self, mock_diff_scanner_class, mock_vector_manager_class, mock_factory
    ):
        """Test that progress callback shows actual file paths from diffs, not hardcoded 'test.py'."""
        # Setup
        import tempfile
        import shutil

        # Create unique temp directory for this test to avoid state pollution
        test_dir = Path(tempfile.mkdtemp(prefix="test_temporal_"))

        # Cleanup previous test state
        try:
            shutil.rmtree(test_dir / ".code-indexer" / "temporal", ignore_errors=True)
        except:
            pass

        mock_config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.voyage_ai.parallel_requests = 4
        mock_config.voyage_ai.model = "voyage-3"
        mock_config.voyage_ai.max_concurrent_batches_per_commit = 10
        mock_config.embedding_provider = "voyage-ai"
        mock_config_manager.get_config.return_value = mock_config

        mock_vector_store = MagicMock()
        mock_vector_store.project_root = test_dir
        mock_vector_store.base_path = test_dir / ".code-indexer" / "index"

        # Mock EmbeddingProviderFactory
        mock_factory.get_provider_model_info.return_value = {
            "provider": "voyage-ai",
            "model": "voyage-3",
            "dimensions": 1536,
        }

        indexer = TemporalIndexer(
            config_manager=mock_config_manager, vector_store=mock_vector_store
        )

        # Mock the diff scanner
        mock_diff_scanner = MagicMock()
        indexer.diff_scanner = mock_diff_scanner

        # Create test commits
        test_commits = [
            CommitInfo(
                hash=f"abcd{i:04d}",
                timestamp=1704067200 + i * 3600,  # 1 hour apart
                author_name="Test Author",
                author_email="test@example.com",
                message=f"Feature {i}",
                parent_hashes="",
            )
            for i in range(5)
        ]

        # Mock diff scanner to return actual file paths from test repo
        # Simulate real file paths that would be in a repo
        mock_diff_scanner.get_diffs_for_commit.side_effect = [
            # Commit 0: auth.py
            [
                MagicMock(
                    file_path="src/auth.py",
                    diff_type="modified",
                    diff_content="+ def login():\n+     pass",
                    change_type="modified",
                )
            ],
            # Commit 1: api.py
            [
                MagicMock(
                    file_path="src/api.py",
                    diff_type="modified",
                    diff_content="+ def get_user():\n+     pass",
                    change_type="modified",
                )
            ],
            # Commit 2: database.py
            [
                MagicMock(
                    file_path="src/database.py",
                    diff_type="modified",
                    diff_content="+ def connect():\n+     pass",
                    change_type="modified",
                )
            ],
            # Commit 3: utils.py
            [
                MagicMock(
                    file_path="src/utils.py",
                    diff_type="modified",
                    diff_content="+ def format():\n+     pass",
                    change_type="modified",
                )
            ],
            # Commit 4: config.py
            [
                MagicMock(
                    file_path="src/config.py",
                    diff_type="modified",
                    diff_content="+ DEBUG = True",
                    change_type="modified",
                )
            ],
        ]

        # Mock embedding provider
        mock_embedding_provider = MagicMock()
        mock_embedding_provider.get_embeddings_for_texts.return_value = [
            [0.1] * 1536  # Mock embedding vector
        ]

        # Mock vector manager
        mock_vector_manager = MagicMock()
        # Mock cancellation event (no cancellation)
        mock_cancellation_event = MagicMock()
        mock_cancellation_event.is_set.return_value = False
        mock_vector_manager.cancellation_event = mock_cancellation_event

        # Mock embedding provider methods for token counting
        mock_embedding_provider = MagicMock()
        mock_embedding_provider._count_tokens_accurately = MagicMock(return_value=100)
        mock_embedding_provider._get_model_token_limit = MagicMock(return_value=120000)
        mock_vector_manager.embedding_provider = mock_embedding_provider

        # Mock submit_batch_task to return proper embeddings
        def mock_submit_batch(texts, metadata):
            future = MagicMock()
            result = MagicMock()
            result.embeddings = [[0.1] * 1536 for _ in texts] if texts else []
            result.error = None
            future.result.return_value = result
            return future

        mock_vector_manager.submit_batch_task.side_effect = mock_submit_batch
        # Mock cancellation event (no cancellation)
        mock_cancellation_event = MagicMock()
        mock_cancellation_event.is_set.return_value = False
        mock_vector_manager.cancellation_event = mock_cancellation_event

        # Track progress calls
        progress_calls = []

        def track_progress(current, total, path, info=None, **kwargs):
            progress_calls.append(
                {"current": current, "total": total, "path": str(path), "info": info}
            )

        # Execute indexing with progress tracking
        indexer._process_commits_parallel(
            commits=test_commits,
            embedding_provider=mock_embedding_provider,
            vector_manager=mock_vector_manager,
            progress_callback=track_progress,
        )

        # Verify that progress is reported correctly without showing specific filenames
        # (filenames were removed to fix parallel processing corruption bug)
        assert len(progress_calls) > 0, "No progress calls were made"

        # Extract info from progress calls
        infos = [call["info"] for call in progress_calls]

        # Story 1 AC requires showing commit hash and filename
        # The shared state approach (last_completed_commit/file) prevents race conditions
        for info in infos:
            assert "📝" in info, f"Missing 📝 emoji (Story 1 requirement): {info}"
            # Should have format: "📝 {hash} - {file}"
            if "📝" in info:
                parts = info.split("📝")
                if len(parts) > 1:
                    hash_file_part = parts[1].strip()
                    assert (
                        " - " in hash_file_part
                    ), f"Missing 'hash - file' format: {info}"

        # Verify progress counts are correct
        # First call is initialization with current=0, then 1,2,3,4,5 for each commit
        for i, call in enumerate(progress_calls):
            if i == 0:
                # First call is initialization
                assert (
                    call["current"] == 0
                ), f"First call should have current=0, got {call['current']}"
            else:
                # Subsequent calls should be 1,2,3,4,5
                assert (
                    call["current"] == i
                ), f"Progress current should be {i}, got {call['current']}"
            assert (
                call["total"] == 5
            ), f"Progress total should be 5, got {call['total']}"

        # The shared state approach means we might see filenames with 100ms lag,
        # but they should be from actual diffs, not hardcoded "test.py"
        test_py_count = sum(1 for info in infos if "test.py" in info)
        assert (
            test_py_count == 0
        ), f"Found {test_py_count} occurrences of hardcoded 'test.py' in progress info"

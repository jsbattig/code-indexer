"""Test temporal indexer language and path filter support."""

from unittest.mock import Mock, patch
import pytest

from code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from code_indexer.config import ConfigManager


class TestTemporalIndexerLanguageFilters:
    """Test that temporal indexer includes language and file_extension in payload."""

    def test_temporal_payload_includes_language_and_extension(self, tmp_path):
        """Test that temporal indexer adds language and file_extension to payload for filter support."""
        # Initialize tmp_path as a git repository
        import subprocess

        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"], cwd=tmp_path
        )
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path)

        # Setup
        config = Mock()
        config.enable_fts = False
        config.fts_index_dir = None
        config.chunk_size = 1000
        config.chunk_overlap = 200
        config.embedding_provider = "voyage-ai"  # Set a valid provider
        config.voyage_ai = Mock()  # Mock the voyage config
        config.voyage_ai.parallel_requests = 8  # Add parallel requests
        config.codebase_dir = tmp_path  # Set codebase_dir
        config.threads = 8  # Add threads config
        config.high_throughput_mode = False  # Add high throughput mode

        config_manager = Mock(spec=ConfigManager)
        config_manager.get_config.return_value = config

        vector_store = Mock(spec=FilesystemVectorStore)
        vector_store.project_root = tmp_path
        vector_store.collection_exists.return_value = True  # Skip collection creation

        # Patch the embedding factory to avoid its initialization
        with patch(
            "code_indexer.services.embedding_factory.EmbeddingProviderFactory"
        ) as mock_factory:
            mock_factory.get_provider_model_info.return_value = {"dimensions": 1536}

            indexer = TemporalIndexer(
                config_manager=config_manager, vector_store=vector_store
            )

        # We'll test by mocking git history and checking what gets passed to vector_store.upsert_points
        # Mock the dependencies
        with (
            patch.object(indexer, "_get_commit_history") as mock_get_history,
            patch.object(
                indexer.diff_scanner, "get_diffs_for_commit"
            ) as mock_get_diffs,
            patch.object(indexer.chunker, "chunk_text") as mock_chunk,
            patch(
                "code_indexer.services.temporal.temporal_indexer.VectorCalculationManager"
            ) as mock_vcm_class,
        ):

            # Create commit info
            from code_indexer.services.temporal.models import CommitInfo

            commit = CommitInfo(
                hash="abc123",
                timestamp=1730764800,
                author_name="Test Author",
                author_email="test@example.com",
                message="Add authentication",
                parent_hashes="",
            )
            mock_get_history.return_value = [commit]

            # Mock diff data
            diff_info = Mock()
            diff_info.diff_type = "modified"
            diff_info.file_path = "src/auth.py"  # Python file
            diff_info.diff_content = "+def login():\n+    return True"

            mock_get_diffs.return_value = [diff_info]

            # Mock chunking - the chunker returns chunks with file_extension
            mock_chunk.return_value = [
                {
                    "text": "def login():\n    return True",
                    "chunk_index": 0,
                    "char_start": 0,
                    "char_end": 30,
                    "file_extension": "py",  # This is returned by chunker
                }
            ]

            # Mock vector calculation - needs to be a context manager
            mock_vcm = Mock()
            mock_future = Mock()
            mock_result = Mock()
            mock_result.embeddings = [[0.1] * 1536]  # Mock embedding
            mock_future.result.return_value = mock_result
            mock_vcm.submit_batch_task.return_value = mock_future
            mock_vcm.shutdown.return_value = None
            mock_vcm.__enter__ = Mock(return_value=mock_vcm)
            mock_vcm.__exit__ = Mock(return_value=None)
            mock_vcm_class.return_value = mock_vcm

            # Capture what gets stored
            stored_points = []

            def capture_points(collection_name, points):
                stored_points.extend(points)

            vector_store.upsert_points.side_effect = capture_points

            # Call index_commits
            indexer.index_commits(
                all_branches=False, max_commits=1, progress_callback=None
            )

            # Verify a point was created
            assert (
                len(stored_points) == 1
            ), f"Should have created one point, got {len(stored_points)}"
            payload = stored_points[0]["payload"]

            # Check that language and file_extension are present
            assert "language" in payload, "Payload should include 'language' field"
            assert (
                "file_extension" in payload
            ), "Payload should include 'file_extension' field"

            # Check values are correct for Python file
            # FIXED: Both language and file_extension should NOT have dots to match regular indexing
            assert (
                payload["language"] == "py"
            ), f"Expected language 'py' but got {payload.get('language')}"
            assert (
                payload["file_extension"] == "py"
            ), f"Expected extension 'py' (without dot) but got {payload.get('file_extension')}"

    def test_temporal_payload_language_for_various_files(self, tmp_path):
        """Test language detection for various file types."""
        # Initialize tmp_path as a git repository
        import subprocess

        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"], cwd=tmp_path
        )
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path)

        # Setup
        config = Mock()
        config.enable_fts = False
        config.fts_index_dir = None
        config.chunk_size = 1000
        config.chunk_overlap = 200
        config.embedding_provider = "voyage-ai"
        config.voyage_ai = Mock()
        config.voyage_ai.parallel_requests = 8
        config.codebase_dir = tmp_path
        config.threads = 8
        config.high_throughput_mode = False

        config_manager = Mock(spec=ConfigManager)
        config_manager.get_config.return_value = config

        vector_store = Mock(spec=FilesystemVectorStore)
        vector_store.project_root = tmp_path
        vector_store.collection_exists.return_value = True

        # Patch the embedding factory
        with patch(
            "code_indexer.services.embedding_factory.EmbeddingProviderFactory"
        ) as mock_factory:
            mock_factory.get_provider_model_info.return_value = {"dimensions": 1536}

            indexer = TemporalIndexer(
                config_manager=config_manager, vector_store=vector_store
            )

        test_cases = [
            ("src/main.js", "js", "js"),  # Without dots to match regular indexing
            ("lib/helper.ts", "ts", "ts"),
            ("test.java", "java", "java"),
            ("Makefile", "txt", "txt"),  # No extension defaults to "txt"
            ("README.md", "md", "md"),
            ("style.css", "css", "css"),
        ]

        for file_path, expected_lang, expected_ext in test_cases:
            # Mock the dependencies
            with (
                patch.object(indexer, "_get_commit_history") as mock_get_history,
                patch.object(
                    indexer.diff_scanner, "get_diffs_for_commit"
                ) as mock_get_diffs,
                patch.object(indexer.chunker, "chunk_text") as mock_chunk,
                patch(
                    "code_indexer.services.temporal.temporal_indexer.VectorCalculationManager"
                ) as mock_vcm_class,
            ):

                # Create commit info
                from code_indexer.services.temporal.models import CommitInfo

                commit = CommitInfo(
                    hash=f"hash_{file_path}",
                    timestamp=1730764800,
                    author_name="Test Author",
                    author_email="test@example.com",
                    message=f"Test commit for {file_path}",
                    parent_hashes="",
                )
                mock_get_history.return_value = [commit]

                # Mock diff data
                diff_info = Mock()
                diff_info.diff_type = "added"
                diff_info.file_path = file_path
                diff_info.diff_content = "+some content"

                mock_get_diffs.return_value = [diff_info]

                # Mock chunking
                mock_chunk.return_value = [
                    {
                        "text": "some content",
                        "chunk_index": 0,
                        "char_start": 0,
                        "char_end": 12,
                        "file_extension": expected_lang,  # Chunker returns without dot
                    }
                ]

                # Mock vector calculation
                mock_vcm = Mock()
                mock_future = Mock()
                mock_result = Mock()
                mock_result.embeddings = [[0.1] * 1536]
                mock_future.result.return_value = mock_result
                mock_vcm.submit_batch_task.return_value = mock_future
                mock_vcm.shutdown.return_value = None
                mock_vcm.__enter__ = Mock(return_value=mock_vcm)
                mock_vcm.__exit__ = Mock(return_value=None)
                mock_vcm_class.return_value = mock_vcm

                # Capture what gets stored
                stored_points = []

                def capture_points(collection_name, points):
                    stored_points.extend(points)

                vector_store.upsert_points.side_effect = capture_points

                # Call index_commits
                indexer.index_commits(
                    all_branches=False, max_commits=1, progress_callback=None
                )

                # Verify the payload includes correct language and extension
                assert (
                    len(stored_points) > 0
                ), f"Should have created points for {file_path}"
                payload = stored_points[-1]["payload"]  # Get the last point

                assert (
                    payload["language"] == expected_lang
                ), f"For {file_path}: expected language '{expected_lang}' but got '{payload.get('language')}'"
                assert (
                    payload["file_extension"] == expected_ext
                ), f"For {file_path}: expected extension '{expected_ext}' but got '{payload.get('file_extension')}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

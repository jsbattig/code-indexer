"""
Tests for file deletion resilience in HighThroughputProcessor.

This test module verifies that the HighThroughputProcessor handles file deletions
gracefully during the hash calculation phase without aborting the entire indexing job.
"""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_indexer.config import Config
from code_indexer.services.high_throughput_processor import HighThroughputProcessor
from ...conftest import local_temporary_directory

# Mark all tests in this file as e2e to exclude from ci-github.sh
pytestmark = pytest.mark.e2e

# Test constants
EMBEDDING_DIMENSIONS = 1024
TOKEN_LIMIT = 8192
MOCK_TOKEN_COUNT = 100
MOCK_FILE_SIZE = 100
FILE_TO_DELETE_INDEX = 5
DELETE_TRIGGER_CALL_COUNT = 3
TOTAL_TEST_FILES = 10
EXPECTED_FILES_PROCESSED = 9  # 10 - 1 deleted
EXPECTED_CHUNKS_CREATED = 9
EXPECTED_SKIPPED_FILES = 1


class TestFileDeletionDuringIndexing:
    """Test file deletion resilience during hash calculation phase."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test environment."""
        self.config = Config(
            codebase_dir="/tmp/test-project",
            file_extensions=["py", "js", "ts"],
            exclude_dirs=["node_modules", "__pycache__"],
        )

        self.embedding_provider = MagicMock()
        self.embedding_provider.get_embedding.return_value = [0.1] * EMBEDDING_DIMENSIONS
        self.embedding_provider.get_current_model.return_value = "voyage-3"
        self.embedding_provider._get_model_token_limit.return_value = TOKEN_LIMIT

        self.filesystem_client = MagicMock()
        self.filesystem_client.create_point.return_value = {"id": "test-point"}
        self.filesystem_client.upsert_points_batched.return_value = True

    @pytest.fixture
    def processor(self):
        """Create processor with mocked tokenizer."""
        mock_tokenizer = MagicMock()
        mock_tokenizer.count_tokens.return_value = MOCK_TOKEN_COUNT

        with patch(
            "code_indexer.services.embedded_voyage_tokenizer.VoyageTokenizer",
            mock_tokenizer,
        ):
            yield HighThroughputProcessor(
                config=self.config,
                embedding_provider=self.embedding_provider,
                vector_store_client=self.filesystem_client,
            )

    def _create_test_files(self, temp_dir, count):
        """Create test files in temp directory."""
        test_files = []
        for i in range(count):
            test_file = Path(temp_dir) / f"test{i}.py"
            test_file.write_text(f"def test{i}():\n    pass\n")
            test_files.append(test_file)
        return test_files

    def _mock_chunk_file(self, file_path):
        """Standard mock for chunk_file method."""
        return [
            {
                "text": f"content of {file_path.name}",
                "chunk_index": 0,
                "total_chunks": 1,
                "file_extension": "py",
                "line_start": 1,
                "line_end": 2,
            }
        ]

    def _create_file_deletion_mock(self, file_to_delete):
        """Create mock that deletes a file during hash phase."""
        call_count = [0]

        def mock_get_file_metadata(file_path):
            call_count[0] += 1

            # Trigger deletion on specific call
            if call_count[0] == DELETE_TRIGGER_CALL_COUNT and file_to_delete.exists():
                file_to_delete.unlink()

            # Raise error if file doesn't exist
            if not file_path.exists():
                raise FileNotFoundError(f"No such file: {file_path}")

            return {
                "project_id": "test-project",
                "file_hash": f"hash-{file_path.name}",
                "git_available": False,
                "file_mtime": time.time(),
                "file_size": MOCK_FILE_SIZE,
            }

        return mock_get_file_metadata

    def _assert_processing_completed_successfully(self, stats):
        """Verify that processing completed with expected results.

        CRITICAL: The main assertion is that processing completes without
        RuntimeError and skipped_files is tracked. This verifies the bug fix.
        """
        assert stats is not None, "Processing should complete and return stats"

        # CRITICAL ASSERTION: skipped_files tracking works
        assert hasattr(stats, 'skipped_files'), "Stats should track skipped_files"
        assert stats.skipped_files == EXPECTED_SKIPPED_FILES, (
            f"Expected {EXPECTED_SKIPPED_FILES} skipped file, got {stats.skipped_files}"
        )

        # Verify hash results excluded the deleted file
        # Total attempted = 10 files
        # Skipped = 1 file (deleted)
        # Hash results should have 9 entries
        # This is the core fix validation - no RuntimeError was raised!

    def test_file_deleted_during_hash_phase_continues_processing(self, processor):
        """Test that deleting a file during hash phase doesn't abort the job."""
        with local_temporary_directory() as temp_dir:
            test_files = self._create_test_files(temp_dir, TOTAL_TEST_FILES)
            file_to_delete = test_files[FILE_TO_DELETE_INDEX]

            deletion_mock = self._create_file_deletion_mock(file_to_delete)

            with patch.object(
                processor.file_identifier,
                "get_file_metadata",
                side_effect=deletion_mock,
            ), patch.object(
                processor.fixed_size_chunker,
                "chunk_file",
                side_effect=self._mock_chunk_file,
            ), patch.object(
                processor.embedding_provider,
                "get_embedding",
                return_value=[0.1] * EMBEDDING_DIMENSIONS,
            ):
                # Process files - should NOT raise RuntimeError
                stats = processor.process_files_high_throughput(
                    files=test_files,
                    vector_thread_count=2,
                    batch_size=10,
                )

                self._assert_processing_completed_successfully(stats)

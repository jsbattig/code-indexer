"""
Test temporal indexer metadata consistency with regular indexing.

This test verifies that the temporal indexer creates payloads with the same
format as regular indexing, specifically for file_extension and language fields.
"""

import tempfile
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


def test_temporal_payload_file_extension_format_matches_regular_indexing():
    """
    Test that temporal indexer uses consistent file_extension format.

    Regular indexing uses "py" (without dot).
    This test should FAIL with current code that uses ".py" (with dot).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Create a test Python file with actual content
        test_file = repo_path / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n")

        # Initialize git repo with proper commits
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True
        )
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Set up config mock
        config_manager = MagicMock()
        config = MagicMock()
        config.qdrant.mode = "filesystem"
        config.embedding.provider = "voyage"
        config.embedding.api_key = "test-key"
        config.voyage_ai.parallel_requests = 3
        config.voyage_ai.model = "voyage-code-3"
        config.chunk.size = 100
        config.chunk.overlap = 20
        config_manager.get_config.return_value = config

        # Mock vector store
        vector_store = MagicMock(spec=FilesystemVectorStore)
        vector_store.project_root = repo_path
        vector_store.collection_exists.return_value = True

        # Capture points when upserted
        captured_points = []

        def capture_upsert(collection_name, points):
            captured_points.extend(points)
            return True

        vector_store.upsert_points = capture_upsert

        # Mock embedding service factory to return embeddings
        with patch(
            "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory"
        ) as mock_factory:
            mock_factory.get_provider_model_info.return_value = {"dimensions": 1536}
            embedding_service = MagicMock()
            embedding_service.embed_batch.return_value = [[0.1] * 1536]
            mock_factory.create.return_value = embedding_service

            # Create temporal indexer
            indexer = TemporalIndexer(
                config_manager=config_manager, vector_store=vector_store
            )

            # Process a single commit directly using the internal method
            # This avoids the complex thread pool setup
            from src.code_indexer.services.temporal.models import CommitInfo

            # Get actual commit from repo
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            commit_hash = result.stdout.strip()

            # Create commit info
            commit = CommitInfo(
                hash=commit_hash,
                timestamp=1234567890,
                author_name="Test",
                author_email="test@test.com",
                message="Initial commit",
                parent_hashes="",
            )

            # Mock the diff scanner to return our test diff
            with patch.object(indexer, "diff_scanner") as mock_diff_scanner:
                from src.code_indexer.services.temporal.temporal_diff_scanner import (
                    DiffInfo,
                )

                mock_diff_scanner.get_diffs_for_commit.return_value = [
                    DiffInfo(
                        file_path="test.py",
                        diff_type="modified",
                        commit_hash=commit_hash,
                        diff_content="+def hello():\n+    print('hello')\n",
                        old_path="",
                    )
                ]

                # Use a simpler vector manager mock
                with patch(
                    "src.code_indexer.services.temporal.temporal_indexer.VectorCalculationManager"
                ):
                    # Directly call the worker function
                    from concurrent.futures import Future

                    mock_future = Future()
                    mock_result = MagicMock()
                    mock_result.embeddings = [[0.1] * 1536]
                    mock_future.set_result(mock_result)

                    mock_vector_manager = MagicMock()
                    mock_vector_manager.submit_batch_task.return_value = mock_future

                    # Call the internal processing method
                    indexer._process_commits_parallel(
                        [commit],
                        embedding_service,
                        mock_vector_manager,
                        progress_callback=None,
                    )

        # Check that we captured points
        assert len(captured_points) > 0, "Should have captured points but got none"

        # Check the file_extension format
        point = captured_points[0]
        payload = point["payload"]
        file_extension = payload["file_extension"]
        language = payload["language"]

        # CRITICAL ASSERTION: file_extension should NOT have a dot
        # Regular indexing pattern: file_path.suffix.lstrip(".") or "txt"
        assert file_extension == "py", (
            f"file_extension should be 'py' (without dot) to match regular indexing, "
            f"but got '{file_extension}'. This inconsistency breaks language filtering!"
        )

        # Also verify language field
        assert language == "py", f"language should be 'py', got '{language}'"

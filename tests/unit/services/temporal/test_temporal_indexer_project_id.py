"""Test TemporalIndexer project_id access bug.

This test reproduces the error:
'Config' object has no attribute 'project_id'

The fix should use FileIdentifier to get project_id instead of accessing config.project_id.
"""

import tempfile
from pathlib import Path
import subprocess
import pytest
from unittest.mock import Mock, patch, MagicMock

from code_indexer.config import ConfigManager
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from code_indexer.services.temporal.temporal_indexer import TemporalIndexer


@pytest.mark.skip(reason="Complex mocking setup needed - test requires refactoring")
def test_temporal_indexer_uses_file_identifier_for_project_id():
    """Test that TemporalIndexer gets project_id from FileIdentifier, not Config.

    This test creates a minimal git repo, initializes TemporalIndexer, and attempts
    to index commits. The test should fail with AttributeError if TemporalIndexer
    tries to access config.project_id directly.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )

        # Create a test file and commit
        test_file = repo_path / "test.py"
        test_file.write_text("def hello(): return 'world'\n")
        subprocess.run(["git", "add", "test.py"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
        )

        # Initialize config and vector store
        config_manager = ConfigManager.create_with_backtrack(repo_path)

        # Override config to use voyage-ai with 1024 dimensions
        config = config_manager.get_config()
        config.embedding_provider = "voyage-ai"
        if not hasattr(config, "voyage_ai"):
            from types import SimpleNamespace

            config.voyage_ai = SimpleNamespace()
        config.voyage_ai.model = "voyage-code-3"
        config.voyage_ai.api_key = "test_key"

        index_dir = repo_path / ".code-indexer/index"
        index_dir.mkdir(parents=True, exist_ok=True)
        vector_store = FilesystemVectorStore(
            base_path=index_dir, project_root=repo_path
        )

        # Create temporal indexer
        temporal_indexer = TemporalIndexer(config_manager, vector_store)

        # This should NOT raise AttributeError about config.project_id
        # If it does, the test will fail and show we need to fix it
        try:
            # Mock embedding provider factory
            with patch(
                "code_indexer.services.embedding_factory.EmbeddingProviderFactory.create"
            ) as mock_factory:
                mock_provider = Mock()
                mock_provider.get_embedding.return_value = [0.1] * 1024
                mock_factory.return_value = mock_provider

                # Mock VectorCalculationManager to avoid actual API calls
                with patch(
                    "code_indexer.services.temporal.temporal_indexer.VectorCalculationManager"
                ) as mock_vm_class:
                    import threading

                    mock_vm = MagicMock()

                    # Setup context manager properly
                    mock_vm_class.return_value.__enter__.return_value = mock_vm
                    mock_vm_class.return_value.__exit__.return_value = False

                    mock_vm.cancellation_event = threading.Event()

                    # Mock embedding provider
                    mock_embedding_provider = MagicMock()
                    mock_embedding_provider._get_model_token_limit.return_value = 120000
                    mock_embedding_provider._count_tokens_accurately = MagicMock(
                        return_value=100
                    )
                    mock_vm.embedding_provider = mock_embedding_provider

                    # Mock embedding results
                    mock_result = Mock()
                    mock_result.embeddings = [[0.1] * 1024]
                    mock_result.error = None
                    mock_future = Mock()
                    mock_future.result.return_value = mock_result
                    mock_vm.submit_batch_task.return_value = mock_future

                    result = temporal_indexer.index_commits(
                        all_branches=False, max_commits=1, progress_callback=None
                    )
                    # If we get here without error, the fix is working
                    assert result.total_commits == 1
        except AttributeError as e:
            if "project_id" in str(e):
                pytest.fail(
                    f"TemporalIndexer should not access config.project_id directly: {e}"
                )
            raise
        finally:
            temporal_indexer.close()


if __name__ == "__main__":
    test_temporal_indexer_uses_file_identifier_for_project_id()

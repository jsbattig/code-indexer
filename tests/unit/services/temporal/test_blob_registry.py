"""Test blob registry for deduplication in temporal indexing."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestBlobRegistry:
    """Test that TemporalIndexer maintains a blob registry for deduplication."""

    def test_temporal_indexer_tracks_indexed_blobs(self):
        """Test that TemporalIndexer tracks which blobs have been indexed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Initialize git repo
            import subprocess
            subprocess.run(["git", "init"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)

            # Setup
            config_manager = MagicMock()
            config = MagicMock()
            config.codebase_dir = repo_path
            config.voyage_ai.parallel_requests = 1
            config_manager.get_config.return_value = config

            index_dir = repo_path / ".code-indexer" / "index"
            vector_store = FilesystemVectorStore(base_path=index_dir, project_root=repo_path)

            with patch('src.code_indexer.services.embedding_factory.EmbeddingProviderFactory') as mock_factory:
                mock_factory.get_provider_model_info.return_value = {"dimensions": 1024}
                temporal_indexer = TemporalIndexer(config_manager, vector_store)

                # TemporalIndexer should have a way to track indexed blobs
                assert hasattr(temporal_indexer, 'indexed_blobs') or hasattr(temporal_indexer, '_indexed_blobs'), \
                    "TemporalIndexer should have indexed_blobs tracking"
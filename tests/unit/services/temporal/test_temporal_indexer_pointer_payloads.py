"""Test temporal_indexer creates pointer-based payloads for added/deleted files."""

import pytest
import subprocess
from unittest.mock import Mock, patch, MagicMock


class TestTemporalIndexerPointerPayloads:
    """Test that temporal_indexer creates correct payloads for storage optimization."""

    @pytest.fixture
    def temp_git_repo(self, tmp_path):
        """Create a temporary git repository with added/deleted/modified files."""
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        # Commit 1: Add file
        test_file = repo_dir / "test.py"
        test_file.write_text("def hello():\n    return 'world'\n")
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add test.py"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        add_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Commit 2: Modify file
        test_file.write_text("def hello():\n    return 'universe'\n")
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Modify test.py"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        modify_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Commit 3: Delete file
        test_file.unlink()
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Delete test.py"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        delete_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        return {
            "repo_dir": repo_dir,
            "add_commit": add_commit,
            "modify_commit": modify_commit,
            "delete_commit": delete_commit,
        }

    def test_added_file_creates_pointer_payload(self, temp_git_repo):
        """Test that indexing an added file creates reconstruct_from_git payload."""
        from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
        from src.code_indexer.config import ConfigManager
        from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        repo_dir = temp_git_repo["repo_dir"]
        add_commit = temp_git_repo["add_commit"]

        # Create real components
        config_manager = ConfigManager.create_with_backtrack(repo_dir)
        vector_store = FilesystemVectorStore(
            base_path=repo_dir / ".code-indexer" / "index",
            project_root=repo_dir,
        )

        # Track what gets upserted
        upserted_points = []
        original_upsert = vector_store.upsert_points

        def capture_upsert(collection_name, points, **kwargs):
            upserted_points.extend(points)
            return {"status": "ok", "count": len(points)}

        vector_store.upsert_points = capture_upsert

        # Create indexer and index the add commit
        indexer = TemporalIndexer(config_manager, vector_store)

        # Mock embedding provider to avoid API calls
        with patch(
            "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.create"
        ) as mock_factory:
            mock_provider = Mock()
            mock_provider.get_embedding.return_value = [0.1] * 1024
            mock_factory.return_value = mock_provider

            # Index only the add commit
            with patch.object(indexer, "_get_commit_history") as mock_history:
                from src.code_indexer.services.temporal.models import CommitInfo

                mock_history.return_value = [
                    CommitInfo(
                        hash=add_commit,
                        timestamp=1234567890,
                        author_name="Test User",
                        author_email="test@example.com",
                        message="Add test.py",
                        parent_hashes="",
                    )
                ]

                # Mock vector manager to return embeddings
                with patch(
                    "src.code_indexer.services.temporal.temporal_indexer.VectorCalculationManager"
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
                    mock_embedding_provider._count_tokens_accurately = MagicMock(return_value=100)
                    mock_vm.embedding_provider = mock_embedding_provider

                    # Mock embedding results
                    mock_result = Mock()
                    mock_result.embeddings = [[0.1] * 1024]
                    mock_result.error = None
                    mock_future = Mock()
                    mock_future.result.return_value = mock_result
                    mock_vm.submit_batch_task.return_value = mock_future

                    # Run indexing
                    result = indexer.index_commits(all_branches=False)

        # Verify: at least one point was created for the added file
        assert len(upserted_points) > 0, "Should have created at least one point"

        # Find points for the added file
        added_points = [
            p
            for p in upserted_points
            if p["payload"].get("diff_type") == "added"
        ]

        assert len(added_points) > 0, "Should have points for added file"

        # Verify: added file payload has reconstruct_from_git marker
        added_payload = added_points[0]["payload"]
        assert (
            added_payload.get("reconstruct_from_git") is True
        ), "Added file should have reconstruct_from_git=True"

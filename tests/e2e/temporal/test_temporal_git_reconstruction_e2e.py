"""E2E test for temporal query with git reconstruction.

Tests the complete flow: temporal indexing with pointer storage → query-time reconstruction.
"""

import subprocess
from datetime import datetime


class TestTemporalGitReconstructionE2E:
    """E2E test for git reconstruction during temporal queries."""

    def test_temporal_query_reconstructs_added_deleted_files_e2e(self, tmp_path):
        """E2E test: Index temporal data with pointers, query and verify content reconstruction."""
        from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
        from src.code_indexer.services.temporal.temporal_search_service import (
            TemporalSearchService,
        )
        from src.code_indexer.config import ConfigManager
        from src.code_indexer.storage.filesystem_vector_store import (
            FilesystemVectorStore,
        )

        # Setup: Create git repo with added and deleted files
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # Initialize git
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
        test_file = repo_dir / "example.py"
        original_content = "def greet(name):\n    return f'Hello, {name}!'\n"
        test_file.write_text(original_content)
        subprocess.run(
            ["git", "add", "."], cwd=repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add example.py"],
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

        add_timestamp = int(
            subprocess.run(
                ["git", "show", "-s", "--format=%ct", add_commit],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )

        # Commit 2: Delete file
        test_file.unlink()
        subprocess.run(
            ["git", "add", "."], cwd=repo_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Delete example.py"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        delete_timestamp = int(
            subprocess.run(
                ["git", "show", "-s", "--format=%ct", "HEAD"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )

        # Setup components
        config_manager = ConfigManager.create_with_backtrack(repo_dir)
        config = config_manager.get_config()

        vector_store = FilesystemVectorStore(
            base_path=repo_dir / ".code-indexer" / "index",
            project_root=repo_dir,
        )

        # Mock embedding provider to avoid API calls
        from unittest.mock import Mock, MagicMock, patch

        # Use default embedding dimension (768 for ollama)
        embedding_dim = 768

        mock_embedding_provider = Mock()
        mock_embedding_provider.get_embedding.return_value = [0.1] * embedding_dim
        mock_embedding_provider.get_embeddings_batch.return_value = [
            [0.1] * embedding_dim
        ]

        # Index temporal data with mocked VectorCalculationManager
        indexer = TemporalIndexer(config_manager, vector_store)

        with patch(
            "src.code_indexer.services.temporal.temporal_indexer.VectorCalculationManager"
        ) as mock_vm_class:
            mock_vm = MagicMock()
            mock_result = Mock()
            mock_result.embeddings = [[0.1] * embedding_dim]
            mock_result.error = None
            mock_future = Mock()
            mock_future.result.return_value = mock_result
            mock_vm.submit_batch_task.return_value = mock_future
            mock_vm.__enter__.return_value = mock_vm
            mock_vm.__exit__.return_value = False
            mock_vm_class.return_value = mock_vm

            # Run indexing (this should create pointer-based payloads for added/deleted files)
            result = indexer.index_commits(all_branches=False)

        assert result.total_commits > 0, "Should have indexed commits"

        # Query: Search for the function
        search_service = TemporalSearchService(
            config_manager=config_manager,
            project_root=repo_dir,
            vector_store_client=vector_store,
            embedding_provider=mock_embedding_provider,
            collection_name="code-indexer-temporal",
        )

        # Query for added file
        start_date = datetime.fromtimestamp(add_timestamp - 86400).strftime("%Y-%m-%d")
        end_date = datetime.fromtimestamp(delete_timestamp + 86400).strftime("%Y-%m-%d")

        results = search_service.query_temporal(
            query="greet function",
            time_range=(start_date, end_date),
        )

        # Verify: Should get results with reconstructed content
        assert len(results.results) > 0, "Should find temporal results"

        # Find added file result
        added_results = [
            r for r in results.results if r.metadata.get("diff_type") == "added"
        ]
        assert len(added_results) > 0, "Should find added file"

        added_result = added_results[0]
        # Verify content was reconstructed from git
        assert added_result.content, "Added file content should not be empty"
        assert (
            "def greet" in added_result.content
        ), "Should contain original function definition"
        assert (
            original_content.strip() in added_result.content
        ), "Should match original content"

        # Find deleted file result
        deleted_results = [
            r for r in results.results if r.metadata.get("diff_type") == "deleted"
        ]
        assert len(deleted_results) > 0, "Should find deleted file"

        deleted_result = deleted_results[0]
        # Verify content was reconstructed from parent commit
        assert deleted_result.content, "Deleted file content should not be empty"
        assert (
            "def greet" in deleted_result.content
        ), "Should contain original function definition"
        assert (
            original_content.strip() in deleted_result.content
        ), "Should match content from parent commit"

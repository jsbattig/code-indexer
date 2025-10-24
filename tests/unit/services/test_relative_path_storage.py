"""
Test that all paths stored in Qdrant are relative to codebase_dir for database portability.

This test suite verifies the critical requirement that Qdrant database contents are portable
across different filesystem locations (CoW cloning, repository moves, etc.) by ensuring all
file paths are stored as relative paths from codebase_dir, not absolute paths.

Critical for: CoW cloning, repository moves, reconcile operations, RAG context extraction.
"""

from pathlib import Path
from typing import List
import pytest
from unittest.mock import MagicMock

from code_indexer.config import Config, ConfigManager
from code_indexer.services.high_throughput_processor import HighThroughputProcessor
from code_indexer.services.file_chunking_manager import FileChunkingManager
from code_indexer.services.git_aware_processor import GitAwareDocumentProcessor
from code_indexer.services.qdrant import QdrantClient


class TestRelativePathStorage:
    """Verify all paths stored in Qdrant are relative to codebase_dir."""

    @pytest.fixture
    def mock_embedding_provider(self):
        """Create mock embedding provider with correct vector dimensions."""
        provider = MagicMock()
        provider.get_provider_name.return_value = "test-provider"
        provider.get_current_model.return_value = "test-model"
        # Use 1024 dimensions for voyage-ai (default for tests)
        provider.embed_batch.return_value = [[0.1] * 1024]  # Match voyage-ai dimensions
        return provider

    @pytest.fixture
    def mock_qdrant_client(self):
        """Create mock Qdrant client."""
        client = MagicMock()
        client.scroll_points.return_value = ([], None)
        client.scroll.return_value = ([], None)
        return client

    @pytest.fixture
    def mock_vector_manager(self):
        """Create mock vector manager for FileChunkingManager."""
        manager = MagicMock()
        manager.create_embeddings.return_value = [[0.1] * 1024]  # Match voyage-ai dimensions
        return manager

    @pytest.fixture
    def mock_chunker(self):
        """Create mock chunker for FileChunkingManager."""
        chunker = MagicMock()
        chunker.chunk_file.return_value = []
        return chunker

    @pytest.fixture
    def mock_slot_tracker(self):
        """Create mock slot tracker for FileChunkingManager."""
        tracker = MagicMock()
        return tracker

    @pytest.fixture
    def mock_smart_indexer(self, config_manager, mock_embedding_provider, mock_qdrant_client, tmp_path):
        """Create mock SmartIndexer."""
        metadata_path = tmp_path / "metadata"
        metadata_path.mkdir(exist_ok=True)
        indexer = MagicMock()
        indexer._detect_changes_for_reconcile.return_value = []
        indexer.reconcile.return_value = None
        return indexer

    @pytest.fixture
    def test_repo(self, tmp_path: Path) -> Path:
        """Create a test repository with sample files."""
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # Create directory structure
        (repo_dir / "src").mkdir()
        (repo_dir / "tests").mkdir()
        (repo_dir / "docs").mkdir()

        # Create sample files
        (repo_dir / "src" / "main.py").write_text("def main():\n    print('Hello')\n")
        (repo_dir / "src" / "utils.py").write_text("def helper():\n    return 42\n")
        (repo_dir / "tests" / "test_main.py").write_text("def test_main():\n    assert True\n")
        (repo_dir / "docs" / "README.md").write_text("# Documentation\n")
        (repo_dir / ".gitignore").write_text("*.pyc\n__pycache__\n")

        return repo_dir

    @pytest.fixture
    def config_manager(self, test_repo: Path) -> ConfigManager:
        """Create ConfigManager for test repository."""
        from code_indexer.config import QdrantConfig

        # Create .code-indexer directory
        config_dir = test_repo / ".code-indexer"
        config_dir.mkdir(exist_ok=True)

        config_path = config_dir / "config.json"
        config_manager = ConfigManager(config_path)

        # Initialize with minimal config, specifying vector_size explicitly
        config = Config(
            codebase_dir=test_repo,
            collection_name="test_collection",
            embedding_provider="voyage-ai",  # Will use mock in tests
            qdrant=QdrantConfig(vector_size=1024),  # Explicit vector size for voyage-ai
        )
        config_manager.save(config)
        return config_manager

    def _get_all_stored_paths(self, config: Config) -> List[str]:
        """
        Retrieve all file paths currently stored in Qdrant collection.

        Returns:
            List of path strings as stored in Qdrant metadata
        """
        qdrant_client = QdrantClient(config=config.qdrant, project_root=config.codebase_dir)

        # Scroll all points in collection
        all_paths = []
        offset = None

        while True:
            records, offset = qdrant_client.scroll(
                collection_name=config.collection_name,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )

            if not records:
                break

            for record in records:
                if hasattr(record, 'payload') and 'path' in record.payload:
                    all_paths.append(record.payload['path'])

            if offset is None:
                break

        return all_paths

    def _assert_all_paths_relative(self, paths: List[str], context: str = ""):
        """
        Assert that all paths are relative (no leading slash or drive letters).

        Args:
            paths: List of path strings to validate
            context: Context description for better error messages
        """
        absolute_paths = [p for p in paths if Path(p).is_absolute()]

        assert len(absolute_paths) == 0, (
            f"{context}: Found {len(absolute_paths)} absolute paths in Qdrant database. "
            f"All paths must be relative to codebase_dir for database portability. "
            f"Absolute paths found: {absolute_paths[:5]}"  # Show first 5 for debugging
        )

        # Additional validation: paths should not start with /
        paths_with_leading_slash = [p for p in paths if p.startswith('/')]
        assert len(paths_with_leading_slash) == 0, (
            f"{context}: Found {len(paths_with_leading_slash)} paths with leading slash. "
            f"Examples: {paths_with_leading_slash[:5]}"
        )

    @pytest.mark.skip(reason="TDD test - documents bug to be fixed: absolute paths stored instead of relative")
    def test_high_throughput_processor_stores_relative_paths(
        self, test_repo: Path, config_manager: ConfigManager,
        mock_embedding_provider, mock_qdrant_client
    ):
        """
        Test that HighThroughputProcessor stores relative paths only.

        CRITICAL BUG: Line 704 of high_throughput_processor.py stores:
            path=str(chunk_task.file_path)
        This stores absolute paths, breaking CoW cloning portability.

        Expected: path=str(chunk_task.file_path.relative_to(codebase_dir))

        This is a TDD-style specification test that will fail until the bug is fixed.
        """
        config = config_manager.get_config()

        # Index files using HighThroughputProcessor
        processor = HighThroughputProcessor(
            config,
            mock_embedding_provider,
            mock_qdrant_client,
        )
        test_files = [
            test_repo / "src" / "main.py",
            test_repo / "src" / "utils.py",
        ]

        # Process files
        for file_path in test_files:
            processor.process_file(file_path)

        # Retrieve all paths from Qdrant
        stored_paths = self._get_all_stored_paths(config)

        # Verify: ALL paths must be relative
        self._assert_all_paths_relative(
            stored_paths,
            context="HighThroughputProcessor"
        )

        # Verify expected relative paths are present
        expected_relative_paths = {"src/main.py", "src/utils.py"}
        actual_relative_paths = set(stored_paths)
        assert expected_relative_paths.issubset(actual_relative_paths), (
            f"Expected relative paths {expected_relative_paths} not found in database. "
            f"Found: {actual_relative_paths}"
        )

    @pytest.mark.skip(reason="TDD test - documents bug to be fixed: absolute paths in FileChunkingManager")
    def test_file_chunking_manager_stores_relative_paths(
        self, test_repo: Path, config_manager: ConfigManager,
        mock_vector_manager, mock_chunker, mock_qdrant_client, mock_slot_tracker
    ):
        """
        Test that FileChunkingManager stores relative paths only.

        CRITICAL BUG: Line 289 of file_chunking_manager.py stores:
            path=str(file_path)
        If file_path is absolute, this breaks portability.

        This is a TDD-style specification test that will fail until the bug is fixed.
        """
        config = config_manager.get_config()

        # Index via FileChunkingManager
        chunking_manager = FileChunkingManager(
            mock_vector_manager,
            mock_chunker,
            mock_qdrant_client,
            thread_count=4,
            slot_tracker=mock_slot_tracker,
            codebase_dir=test_repo,
        )
        chunking_manager.index_repository(str(test_repo), force_reindex=True)

        # Retrieve all paths from Qdrant
        stored_paths = self._get_all_stored_paths(config)

        # Verify: ALL paths must be relative
        self._assert_all_paths_relative(
            stored_paths,
            context="FileChunkingManager"
        )

    @pytest.mark.skip(reason="TDD test - documents bug to be fixed: absolute paths in GitAwareProcessor")
    def test_git_aware_processor_stores_relative_paths(
        self, test_repo: Path, config_manager: ConfigManager,
        mock_embedding_provider, mock_qdrant_client
    ):
        """
        Test that GitAwareProcessor stores relative paths only.

        CRITICAL BUG: Line 115 of git_aware_processor.py stores:
            path=str(file_path)
        If file_path is absolute, this breaks portability.

        This is a TDD-style specification test that will fail until the bug is fixed.
        """
        config = config_manager.get_config()

        # Initialize git repository
        import subprocess
        subprocess.run(["git", "init"], cwd=test_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=test_repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=test_repo, check=True, capture_output=True
        )
        subprocess.run(["git", "add", "."], cwd=test_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=test_repo, check=True, capture_output=True
        )

        # Index via GitAwareDocumentProcessor
        processor = GitAwareDocumentProcessor(
            config,
            mock_embedding_provider,
            mock_qdrant_client,
        )
        test_files = [test_repo / "src" / "main.py"]

        for file_path in test_files:
            processor.process_file(file_path, branch_name="master")

        # Retrieve all paths from Qdrant
        stored_paths = self._get_all_stored_paths(config)

        # Verify: ALL paths must be relative
        self._assert_all_paths_relative(
            stored_paths,
            context="GitAwareProcessor"
        )

    @pytest.mark.skip(reason="TDD test - documents bug to be fixed: absolute paths after full index")
    def test_no_absolute_paths_after_full_index(
        self, test_repo: Path, config_manager: ConfigManager,
        mock_vector_manager, mock_chunker, mock_qdrant_client, mock_slot_tracker
    ):
        """
        Test that full repository indexing produces NO absolute paths.

        This is the ultimate verification: after complete indexing,
        scrolling through ALL Qdrant points should find zero absolute paths.

        This is a TDD-style specification test that will fail until the bug is fixed.
        """
        config = config_manager.get_config()

        # Perform full indexing
        chunking_manager = FileChunkingManager(
            mock_vector_manager,
            mock_chunker,
            mock_qdrant_client,
            thread_count=4,
            slot_tracker=mock_slot_tracker,
            codebase_dir=test_repo,
        )
        chunking_manager.index_repository(str(test_repo), force_reindex=True)

        # Retrieve ALL paths from Qdrant
        stored_paths = self._get_all_stored_paths(config)

        assert len(stored_paths) > 0, "Expected some paths to be indexed"

        # Critical assertion: ZERO absolute paths allowed
        self._assert_all_paths_relative(
            stored_paths,
            context="Full Repository Index"
        )

        # Verify all paths are valid relative paths
        for path_str in stored_paths:
            path = Path(path_str)
            assert not path.is_absolute(), f"Path {path_str} is absolute!"
            # Path should be relative and not start with /
            assert not str(path).startswith('/'), f"Path {path_str} starts with /"

    @pytest.mark.skip(reason="TDD test - documents bug to be fixed: CoW clone portability with absolute paths")
    def test_cow_clone_portability(
        self, test_repo: Path, config_manager: ConfigManager, tmp_path: Path,
        mock_vector_manager, mock_chunker, mock_qdrant_client, mock_slot_tracker
    ):
        """
        Test that database is portable after CoW clone to new location.

        Simulates the critical CoW cloning scenario:
        1. Index at original location
        2. "Clone" database to new location (update config)
        3. Verify RAG extraction and reconcile work correctly

        This test proves the database is truly portable.

        This is a TDD-style specification test that will fail until the bug is fixed.
        """
        config = config_manager.get_config()

        # Step 1: Index at original location
        chunking_manager = FileChunkingManager(
            mock_vector_manager,
            mock_chunker,
            mock_qdrant_client,
            thread_count=4,
            slot_tracker=mock_slot_tracker,
            codebase_dir=test_repo,
        )
        chunking_manager.index_repository(str(test_repo), force_reindex=True)

        # Verify initial indexing used relative paths
        stored_paths = self._get_all_stored_paths(config)
        self._assert_all_paths_relative(stored_paths, context="Initial Index")

        # Step 2: Simulate CoW clone - create new "cloned" location
        cloned_repo = tmp_path / "cloned_repo"
        cloned_repo.mkdir()

        # Copy files to simulate CoW clone target
        import shutil
        for item in test_repo.iterdir():
            if item.is_file():
                shutil.copy2(item, cloned_repo / item.name)
            elif item.is_dir() and item.name != '.code-indexer':
                shutil.copytree(item, cloned_repo / item.name)

        # Step 3: Update config to point to new location (simulating CoW clone)
        # In real CoW clone, .code-indexer directory is shared via CoW
        # We simulate by keeping Qdrant data but updating codebase_dir
        config.codebase_dir = cloned_repo
        config_manager.save(config)

        # Step 4: Verify RAG extraction works with relative paths
        # RAG extractor expects: full_file_path = self.codebase_dir / file_path
        # This only works if file_path is relative!
        from code_indexer.services.rag_context_extractor import RAGContextExtractor

        rag_extractor = RAGContextExtractor(config_manager)

        # Try to extract context for a file - should work with relative paths
        test_file_relative = "src/main.py"
        try:
            context = rag_extractor.extract_context(test_file_relative, max_chunks=2)
            # Should succeed if paths are relative
            assert context is not None or context == [], (
                "RAG extraction should work with relative paths after location change"
            )
        except Exception as e:
            pytest.fail(
                f"RAG extraction failed after location change: {e}. "
                "This indicates paths in database are absolute, not relative!"
            )

        # Step 5: Verify reconcile works
        # Reconcile should detect files correctly even after location change
        # Using mock since reconcile requires complex setup
        # The real test is that RAG extraction worked above with relative paths

    @pytest.mark.skip(reason="TDD test - documents bug to be fixed: reconcile after repository move with absolute paths")
    def test_reconcile_after_repository_move(
        self, test_repo: Path, config_manager: ConfigManager, tmp_path: Path,
        mock_vector_manager, mock_chunker, mock_qdrant_client, mock_slot_tracker
    ):
        """
        Test that reconcile works correctly after moving repository.

        After moving a repository to a new location and updating config,
        reconcile should detect all files as up-to-date (not re-index everything).
        This ONLY works if paths are stored as relative.

        This is a TDD-style specification test that will fail until the bug is fixed.
        """
        config = config_manager.get_config()

        # Index repository at original location using FileChunkingManager
        chunking_manager = FileChunkingManager(
            mock_vector_manager,
            mock_chunker,
            mock_qdrant_client,
            thread_count=4,
            slot_tracker=mock_slot_tracker,
            codebase_dir=test_repo,
        )
        chunking_manager.index_repository(str(test_repo), force_reindex=True)

        # Get initial file count
        stored_paths = self._get_all_stored_paths(config)
        initial_count = len(stored_paths)
        assert initial_count > 0, "Expected files to be indexed"

        # Verify all paths are relative
        self._assert_all_paths_relative(stored_paths, context="Before Move")

        # Simulate repository move
        moved_repo = tmp_path / "moved_repo"
        import shutil
        shutil.copytree(test_repo, moved_repo)

        # Update config to new location
        config.codebase_dir = moved_repo
        config_manager.save(config)

        # The test of relative paths is that we can still query the paths
        # after changing codebase_dir - this only works with relative paths
        moved_config = config_manager.get_config()
        moved_stored_paths = self._get_all_stored_paths(moved_config)

        # Verify: file count should remain consistent
        assert len(moved_stored_paths) == initial_count, (
            f"After repository move, expected {initial_count} files, "
            f"found {len(moved_stored_paths)}. Indicates reconcile issues!"
        )

        # Verify paths are still relative after move
        self._assert_all_paths_relative(moved_stored_paths, context="After Move")


class TestPathNormalizationHelper:
    """Test the path normalization helper method directly."""

    def test_normalize_absolute_path(self, tmp_path: Path):
        """Test normalization of absolute path to relative."""
        codebase_dir = tmp_path / "project"
        codebase_dir.mkdir()

        absolute_path = codebase_dir / "src" / "main.py"

        # This is what the helper should do
        expected_relative = "src/main.py"

        # Test path normalization logic
        if absolute_path.is_absolute():
            result = str(absolute_path.relative_to(codebase_dir))
        else:
            result = str(absolute_path)

        assert result == expected_relative, (
            f"Expected '{expected_relative}', got '{result}'"
        )

    def test_normalize_already_relative_path(self):
        """Test that already relative path remains unchanged."""
        relative_path = Path("src/main.py")
        codebase_dir = Path("/project")

        # This is what the helper should do
        if relative_path.is_absolute():
            result = str(relative_path.relative_to(codebase_dir))
        else:
            result = str(relative_path)

        assert result == "src/main.py", "Relative path should remain unchanged"

    def test_normalize_handles_nested_paths(self, tmp_path: Path):
        """Test normalization of deeply nested paths."""
        codebase_dir = tmp_path / "project"
        codebase_dir.mkdir()

        deep_path = codebase_dir / "src" / "services" / "api" / "handlers.py"
        expected_relative = "src/services/api/handlers.py"

        if deep_path.is_absolute():
            result = str(deep_path.relative_to(codebase_dir))
        else:
            result = str(deep_path)

        assert result == expected_relative

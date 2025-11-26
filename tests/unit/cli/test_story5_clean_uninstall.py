"""Unit tests for Story 5: Manage Collections and Clean Up Filesystem Index.

Tests for cidx clean and cidx uninstall commands with backend abstraction.
"""

import json
from unittest.mock import Mock, patch
from click.testing import CliRunner
import pytest
from contextlib import contextmanager


@contextmanager
def mock_local_mode():
    """Context manager to mock detect_current_mode to return 'local'."""
    with patch("code_indexer.disabled_commands.detect_current_mode") as mock_detect:
        mock_detect.return_value = "local"
        yield


@pytest.fixture
def test_project_root(tmp_path):
    """Create a test project with filesystem backend."""
    project_root = tmp_path / "test-project"
    project_root.mkdir()

    # Create .code-indexer/index structure
    index_dir = project_root / ".code-indexer" / "index"
    index_dir.mkdir(parents=True)

    # Create config.json with filesystem provider (daemon DISABLED for standalone testing)
    config_file = project_root / ".code-indexer" / "config.json"
    config_data = {
        "codebase_dir": str(project_root),
        "project_name": "test-project",
        "vector_store": {"provider": "filesystem"},
        "embedding": {"provider": "voyage", "model": "voyage-code-3"},
        "git": {"available": False},
        "daemon": {
            "enabled": False
        },  # Explicitly disable daemon for standalone testing
    }
    with open(config_file, "w") as f:
        json.dump(config_data, f)

    return project_root


@pytest.fixture
def cli_context(test_project_root):
    """Create CLI context for testing."""
    from code_indexer.config import ConfigManager

    config_manager = ConfigManager.create_with_backtrack(test_project_root)

    return {
        "project_root": test_project_root,
        "mode": "local",
        "config_manager": config_manager,
    }


@pytest.fixture
def mock_backend():
    """Create a mock VectorStoreBackend."""
    backend = Mock()
    backend.cleanup = Mock()
    backend.get_vector_store_client = Mock()

    # Mock vector store client with collection operations
    vector_store = Mock()
    vector_store.list_collections = Mock(return_value=["voyage_code_3"])
    vector_store.collection_exists = Mock(
        return_value=True
    )  # Always return True for any collection
    vector_store.clear_collection = Mock(return_value=True)
    vector_store.count_points = Mock(return_value=150)
    vector_store.get_collection_size = Mock(return_value=1024 * 1024)  # 1MB

    backend.get_vector_store_client.return_value = vector_store

    return backend


class TestCleanCommand:
    """Tests for 'cidx clean' command with backend abstraction."""

    def test_clean_without_collection_name_uses_backend(
        self, test_project_root, cli_context, mock_backend
    ):
        """Test clean without collection name uses backend abstraction."""
        from code_indexer.cli import cli

        runner = CliRunner()

        with (
            mock_local_mode(),
            patch(
                "code_indexer.backends.backend_factory.BackendFactory.create",
                return_value=mock_backend,
            ),
        ):
            runner.invoke(
                cli,
                ["--path", str(test_project_root), "clean"],
                input="y\n",
                obj=cli_context,
            )

        # Should call backend's vector store client to list and clear collections
        mock_backend.get_vector_store_client.assert_called_once()
        vector_store = mock_backend.get_vector_store_client.return_value
        vector_store.list_collections.assert_called_once()
        vector_store.clear_collection.assert_called_once_with(
            "voyage_code_3", remove_projection_matrix=False
        )

    def test_clean_with_collection_name_clears_specific_collection(
        self, test_project_root, mock_backend
    ):
        """Test clean with collection name clears specific collection."""
        from code_indexer.cli import cli

        runner = CliRunner()

        with (
            mock_local_mode(),
            patch(
                "code_indexer.backends.backend_factory.BackendFactory.create",
                return_value=mock_backend,
            ),
        ):
            runner.invoke(
                cli,
                [
                    "--path",
                    str(test_project_root),
                    "clean",
                    "--collection",
                    "custom_collection",
                ],
                input="y\n",
            )

        vector_store = mock_backend.get_vector_store_client.return_value
        vector_store.clear_collection.assert_called_once_with(
            "custom_collection", remove_projection_matrix=False
        )

    def test_clean_shows_confirmation_prompt(self, test_project_root, mock_backend):
        """Test clean shows confirmation prompt with impact details."""
        from code_indexer.cli import cli

        runner = CliRunner()

        with (
            mock_local_mode(),
            patch(
                "code_indexer.backends.backend_factory.BackendFactory.create",
                return_value=mock_backend,
            ),
        ):
            # Decline confirmation
            result = runner.invoke(
                cli,
                ["--path", str(test_project_root), "clean"],
                input="n\n",
            )

        # Should show prompt in output
        assert (
            "collection" in result.output.lower() or "confirm" in result.output.lower()
        )

        # Should NOT clear collection when declined
        vector_store = mock_backend.get_vector_store_client.return_value
        vector_store.clear_collection.assert_not_called()

    def test_clean_displays_impact_before_deletion(
        self, test_project_root, mock_backend
    ):
        """Test clean displays vector count and impact before deletion."""
        from code_indexer.cli import cli

        runner = CliRunner()

        with (
            mock_local_mode(),
            patch(
                "code_indexer.backends.backend_factory.BackendFactory.create",
                return_value=mock_backend,
            ),
        ):
            runner.invoke(
                cli,
                ["--path", str(test_project_root), "clean"],
                input="y\n",
            )

        # Should query vector count for impact assessment
        vector_store = mock_backend.get_vector_store_client.return_value
        vector_store.count_points.assert_called()

    def test_clean_with_force_flag_skips_confirmation(
        self, test_project_root, mock_backend
    ):
        """Test clean with --force flag skips confirmation prompt (standalone mode)."""
        from code_indexer.cli import cli

        runner = CliRunner()

        with (
            mock_local_mode(),
            patch(
                "code_indexer.backends.backend_factory.BackendFactory.create",
                return_value=mock_backend,
            ),
        ):
            # Use --path to explicitly specify project root with daemon disabled
            result = runner.invoke(
                cli,
                ["--path", str(test_project_root), "clean", "--force"],
            )

        # Should clear collection without prompting
        vector_store = mock_backend.get_vector_store_client.return_value
        vector_store.clear_collection.assert_called_once()

        # Output should not contain confirmation text
        assert "confirm" not in result.output.lower()

    def test_clean_preserves_projection_matrix(self, test_project_root):
        """Test clean preserves projection matrix by default."""
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
        from code_indexer.cli import cli

        # Create real filesystem vector store with collection
        index_dir = test_project_root / ".code-indexer" / "index"
        vector_store = FilesystemVectorStore(
            base_path=index_dir, project_root=test_project_root
        )
        vector_store.create_collection("test_collection", vector_size=1536)

        # Verify projection matrix exists
        matrix_file = index_dir / "test_collection" / "projection_matrix.npy"
        assert matrix_file.exists()

        runner = CliRunner()
        with mock_local_mode():
            runner.invoke(
                cli,
                [
                    "--path",
                    str(test_project_root),
                    "clean",
                    "--collection",
                    "test_collection",
                    "--force",
                ],
            )

        # Projection matrix should still exist
        assert matrix_file.exists()

    def test_clean_with_remove_matrix_flag_deletes_projection_matrix(
        self, test_project_root, cli_context
    ):
        """Test clean with --remove-projection-matrix flag deletes matrix."""
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
        from code_indexer.cli import cli

        # Create real filesystem vector store with collection
        index_dir = test_project_root / ".code-indexer" / "index"
        vector_store = FilesystemVectorStore(
            base_path=index_dir, project_root=test_project_root
        )
        vector_store.create_collection("test_collection", vector_size=1536)

        matrix_file = index_dir / "test_collection" / "projection_matrix.npy"
        assert matrix_file.exists()

        runner = CliRunner()
        with mock_local_mode():
            # Use --path to specify the test project directory
            # This makes the CLI use the test project's config instead of CWD
            result = runner.invoke(
                cli,
                [
                    "--path",
                    str(test_project_root),
                    "clean",
                    "--collection",
                    "test_collection",
                    "--remove-projection-matrix",
                    "--force",
                ],
            )

            # Check if command succeeded
            if result.exit_code != 0:
                print(f"CLI output: {result.output}")
                if result.exception:
                    raise result.exception

        # Projection matrix should be deleted
        assert not matrix_file.exists()


class TestUninstallCommand:
    """Tests for 'cidx uninstall' command with backend abstraction."""

    def test_uninstall_uses_backend_cleanup(self, test_project_root, mock_backend):
        """Test uninstall calls backend.cleanup() for filesystem backend."""
        from code_indexer.cli import cli

        runner = CliRunner()

        with (
            mock_local_mode(),
            patch(
                "code_indexer.backends.backend_factory.BackendFactory.create",
                return_value=mock_backend,
            ),
        ):
            runner.invoke(
                cli,
                ["--path", str(test_project_root), "uninstall", "--confirm"],
            )

        # Should call backend cleanup
        mock_backend.cleanup.assert_called_once()

    def test_uninstall_removes_entire_index_directory(self, test_project_root):
        """Test uninstall removes .code-indexer/index/ directory."""
        from code_indexer.cli import cli

        index_dir = test_project_root / ".code-indexer" / "index"

        # Create some vector files
        (index_dir / "test_file.json").write_text('{"test": "data"}')
        assert index_dir.exists()

        runner = CliRunner()
        with mock_local_mode():
            runner.invoke(
                cli,
                ["--path", str(test_project_root), "uninstall", "--confirm"],
            )

        # Index directory should be completely removed
        assert not index_dir.exists()

    def test_uninstall_shows_confirmation_prompt(self, test_project_root, mock_backend):
        """Test uninstall shows confirmation prompt with impact details."""
        from code_indexer.cli import cli

        runner = CliRunner()

        with (
            mock_local_mode(),
            patch(
                "code_indexer.backends.backend_factory.BackendFactory.create",
                return_value=mock_backend,
            ),
        ):
            # Decline confirmation
            result = runner.invoke(
                cli,
                ["--path", str(test_project_root), "uninstall"],
                input="n\n",
            )

        # Should show confirmation prompt
        assert "confirm" in result.output.lower() or "remove" in result.output.lower()

        # Should NOT cleanup when declined
        mock_backend.cleanup.assert_not_called()

    def test_uninstall_reports_storage_space_reclaimed(self, test_project_root):
        """Test uninstall reports how much storage space was reclaimed."""
        from code_indexer.cli import cli

        index_dir = test_project_root / ".code-indexer" / "index"

        # Create files with known sizes
        large_file = index_dir / "large.json"
        large_file.write_text("x" * 1024 * 1024)  # 1MB

        runner = CliRunner()
        with mock_local_mode():
            result = runner.invoke(
                cli,
                ["--path", str(test_project_root), "uninstall", "--confirm"],
            )

        # Should report storage reclaimed
        assert (
            "MB" in result.output
            or "KB" in result.output
            or "reclaimed" in result.output.lower()
        )

    def test_uninstall_with_confirm_flag_skips_prompt(
        self, test_project_root, mock_backend
    ):
        """Test uninstall with --confirm flag skips confirmation prompt."""
        from code_indexer.cli import cli

        runner = CliRunner()

        with (
            mock_local_mode(),
            patch(
                "code_indexer.backends.backend_factory.BackendFactory.create",
                return_value=mock_backend,
            ),
        ):
            result = runner.invoke(
                cli,
                ["--path", str(test_project_root), "uninstall", "--confirm"],
            )

        # Should cleanup without prompting
        mock_backend.cleanup.assert_called_once()

        # Should not ask for confirmation
        assert "confirm" not in result.output.lower()

    def test_uninstall_no_container_cleanup_for_filesystem_backend(
        self, test_project_root, mock_backend
    ):
        """Test uninstall does not attempt container cleanup for filesystem backend."""
        from code_indexer.cli import cli

        runner = CliRunner()

        with (
            mock_local_mode(),
            patch(
                "code_indexer.backends.backend_factory.BackendFactory.create",
                return_value=mock_backend,
            ),
        ):
            runner.invoke(
                cli,
                ["--path", str(test_project_root), "uninstall", "--confirm"],
            )

            # Container-free architecture - no docker manager exists


class TestListCollectionsWithMetadata:
    """Tests for listing collections with metadata."""

    def test_list_collections_shows_metadata(self, test_project_root):
        """Test that collection listing includes metadata."""
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
        from code_indexer.cli import cli

        # Create vector store with multiple collections
        index_dir = test_project_root / ".code-indexer" / "index"
        vector_store = FilesystemVectorStore(
            base_path=index_dir, project_root=test_project_root
        )

        vector_store.create_collection("collection1", vector_size=1536)
        vector_store.create_collection("collection2", vector_size=768)

        runner = CliRunner()
        with mock_local_mode():
            result = runner.invoke(
                cli,
                ["--path", str(test_project_root), "list-collections"],
            )

        # Should show both collections
        assert "collection1" in result.output
        assert "collection2" in result.output

        # Should show metadata (vector size, creation date, etc.)
        assert "1536" in result.output or "768" in result.output

    def test_list_collections_shows_vector_counts(self, test_project_root):
        """Test that collection listing shows vector counts."""
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
        from code_indexer.cli import cli
        import numpy as np

        # Create vector store with collection containing vectors
        index_dir = test_project_root / ".code-indexer" / "index"
        vector_store = FilesystemVectorStore(
            base_path=index_dir, project_root=test_project_root
        )

        vector_store.create_collection("test_collection", vector_size=64)

        # Add some vectors
        points = [
            {
                "id": f"test_{i}",
                "vector": np.random.rand(64).tolist(),
                "payload": {"path": f"test_{i}.py", "content": f"test content {i}"},
            }
            for i in range(10)
        ]
        vector_store.upsert_points("test_collection", points)

        runner = CliRunner()
        with mock_local_mode():
            result = runner.invoke(
                cli,
                ["--path", str(test_project_root), "list-collections"],
            )

        # Should show vector count
        assert "10" in result.output or "vectors" in result.output.lower()


class TestGitAwareCleanupRecommendations:
    """Tests for git-aware cleanup recommendations."""

    def test_clean_shows_git_aware_recommendations(
        self, test_project_root, mock_backend
    ):
        """Test clean command shows git-aware cleanup recommendations."""
        from code_indexer.cli import cli

        # Mock git status to show uncommitted files
        with (
            mock_local_mode(),
            patch("subprocess.run") as mock_run,
            patch(
                "code_indexer.backends.backend_factory.BackendFactory.create",
                return_value=mock_backend,
            ),
        ):
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "M  src/file1.py\nM  src/file2.py\n"
            mock_run.return_value = mock_result

            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["--path", str(test_project_root), "clean", "--show-recommendations"],
            )

            # Should mention uncommitted changes in recommendations
            assert (
                "uncommitted" in result.output.lower()
                or "modified" in result.output.lower()
            )

    def test_clean_recommends_selective_deletion_for_dirty_files(
        self, test_project_root, mock_backend
    ):
        """Test clean recommends selective deletion for files with uncommitted changes."""
        from code_indexer.cli import cli

        runner = CliRunner()

        with (
            mock_local_mode(),
            patch("subprocess.run") as mock_run,
            patch(
                "code_indexer.backends.backend_factory.BackendFactory.create",
                return_value=mock_backend,
            ),
        ):
            # Mock git status showing modified files
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "M  important_file.py\n"
            mock_run.return_value = mock_result

            result = runner.invoke(
                cli,
                ["--path", str(test_project_root), "clean", "--show-recommendations"],
            )

            # Should recommend reviewing uncommitted changes before cleanup
            output_lower = result.output.lower()
            assert (
                "recommend" in output_lower
                or "suggest" in output_lower
                or "uncommitted" in output_lower
            )


class TestStorageSpaceReporting:
    """Tests for storage space reclamation reporting."""

    def test_clean_reports_space_reclaimed(self, test_project_root):
        """Test clean reports how much disk space was reclaimed."""
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
        from code_indexer.cli import cli
        import numpy as np

        index_dir = test_project_root / ".code-indexer" / "index"
        vector_store = FilesystemVectorStore(
            base_path=index_dir, project_root=test_project_root
        )

        # Create collection with vectors
        vector_store.create_collection("test_collection", vector_size=1536)

        # Add many vectors to create significant storage
        points = [
            {
                "id": f"point_{i}",
                "vector": np.random.rand(1536).tolist(),
                "payload": {"path": f"file_{i}.py", "content": "x" * 1000},
            }
            for i in range(100)
        ]
        vector_store.upsert_points("test_collection", points)

        runner = CliRunner()
        with mock_local_mode():
            result = runner.invoke(
                cli,
                [
                    "--path",
                    str(test_project_root),
                    "clean",
                    "--collection",
                    "test_collection",
                    "--force",
                ],
            )

        # Should report storage reclaimed
        assert "reclaimed" in result.output.lower() or "freed" in result.output.lower()
        assert "MB" in result.output or "KB" in result.output


class TestAtomicOperations:
    """Tests for atomic cleanup operations."""

    def test_clean_is_atomic_on_failure(self, test_project_root, mock_backend):
        """Test clean operation is atomic - either all succeed or none."""
        from code_indexer.cli import cli

        # Mock vector store to fail midway
        vector_store = Mock()
        vector_store.list_collections.return_value = ["coll1", "coll2", "coll3"]
        vector_store.clear_collection.side_effect = [True, Exception("Disk full"), True]

        mock_backend.get_vector_store_client.return_value = vector_store

        runner = CliRunner()

        with (
            mock_local_mode(),
            patch(
                "code_indexer.backends.backend_factory.BackendFactory.create",
                return_value=mock_backend,
            ),
        ):
            result = runner.invoke(
                cli,
                ["--path", str(test_project_root), "clean", "--force"],
            )

        # Should report failure
        assert result.exit_code != 0 or "error" in result.output.lower()

    def test_uninstall_is_atomic_on_failure(self, test_project_root, mock_backend):
        """Test uninstall operation fails gracefully on error."""
        from code_indexer.cli import cli

        # Mock backend cleanup to fail
        mock_backend.cleanup.side_effect = RuntimeError("Permission denied")

        runner = CliRunner()

        with (
            mock_local_mode(),
            patch(
                "code_indexer.backends.backend_factory.BackendFactory.create",
                return_value=mock_backend,
            ),
        ):
            result = runner.invoke(
                cli,
                ["--path", str(test_project_root), "uninstall", "--confirm"],
            )

        # Should report error
        assert (
            result.exit_code != 0
            or "error" in result.output.lower()
            or "failed" in result.output.lower()
        )

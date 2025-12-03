"""
Unit tests for cidx-meta legacy migration logic.

Tests the migration from old special-case cidx-meta to regular golden repo.
"""

import pytest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import Mock, patch


@pytest.fixture
def temp_data_dir():
    """Create temporary data directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def golden_repos_dir(temp_data_dir):
    """Create golden-repos directory."""
    gr_dir = Path(temp_data_dir) / "golden-repos"
    gr_dir.mkdir(parents=True)
    return gr_dir


@pytest.fixture
def metadata_file(golden_repos_dir):
    """Return path to metadata.json file."""
    return golden_repos_dir / "metadata.json"


class TestMigrateLegacyCidxMeta:
    """Test legacy cidx-meta migration scenarios."""

    def test_migrates_directory_without_registry_entry(
        self, golden_repos_dir, metadata_file
    ):
        """Test migration when cidx-meta directory exists but not in metadata.json."""
        # Setup: Create cidx-meta directory
        cidx_meta_path = golden_repos_dir / "cidx-meta"
        cidx_meta_path.mkdir()

        # Create empty metadata.json (no cidx-meta entry)
        metadata_file.write_text("{}")

        # Create mock golden_repo_manager
        mock_manager = Mock()
        mock_manager.golden_repo_exists = Mock(return_value=False)
        mock_manager.golden_repos = {}  # Add golden_repos dictionary
        mock_manager._save_metadata = Mock()

        # Mock GlobalActivator to avoid actual global activation
        with patch(
            "code_indexer.global_repos.global_activation.GlobalActivator"
        ) as mock_activator_class:
            mock_activator = Mock()
            mock_activator_class.return_value = mock_activator

            # Execute migration
            from code_indexer.server.app import migrate_legacy_cidx_meta

            migrate_legacy_cidx_meta(mock_manager, str(golden_repos_dir))

            # Verify: cidx-meta was registered with local:// URL
            assert "cidx-meta" in mock_manager.golden_repos
            repo = mock_manager.golden_repos["cidx-meta"]
            assert repo.repo_url == "local://cidx-meta"
            assert repo.alias == "cidx-meta"
            mock_manager._save_metadata.assert_called_once()

    def test_migrates_repo_url_none_to_local_scheme(
        self, golden_repos_dir, metadata_file
    ):
        """Test migration when cidx-meta has repo_url=None in metadata.json."""
        # Setup: Create cidx-meta directory and metadata with None repo_url
        cidx_meta_path = golden_repos_dir / "cidx-meta"
        cidx_meta_path.mkdir()

        metadata = {
            "cidx-meta": {
                "alias": "cidx-meta",
                "repo_url": None,  # Old special marker
                "default_branch": "main",
                "clone_path": str(cidx_meta_path),
                "created_at": "2024-01-01T00:00:00Z",
                "enable_temporal": False,
            }
        }
        metadata_file.write_text(json.dumps(metadata, indent=2))

        # Create mock manager with a mock repo that has modifiable repo_url
        mock_manager = Mock()
        mock_manager.golden_repo_exists = Mock(return_value=True)

        # Use a simple Mock object with settable repo_url attribute
        mock_repo = Mock()
        mock_repo.repo_url = None
        mock_repo.alias = "cidx-meta"

        mock_manager.get_golden_repo = Mock(return_value=mock_repo)
        mock_manager._save_metadata = Mock()

        # Execute migration
        from code_indexer.server.app import migrate_legacy_cidx_meta

        migrate_legacy_cidx_meta(mock_manager, str(golden_repos_dir))

        # Verify: repo_url was updated to local://cidx-meta
        assert mock_repo.repo_url == "local://cidx-meta"
        mock_manager._save_metadata.assert_called_once()

    def test_no_op_when_already_migrated(self, golden_repos_dir, metadata_file):
        """Test that migration is no-op when cidx-meta already uses local:// URL."""
        # Setup: Create cidx-meta directory
        cidx_meta_path = golden_repos_dir / "cidx-meta"
        cidx_meta_path.mkdir()

        # Create mock repo that's already migrated
        mock_repo = Mock()
        mock_repo.repo_url = "local://cidx-meta"  # Already migrated
        mock_repo.alias = "cidx-meta"

        # Create mock manager
        mock_manager = Mock()
        mock_manager.golden_repo_exists = Mock(return_value=True)
        mock_manager.get_golden_repo = Mock(return_value=mock_repo)
        mock_manager.add_golden_repo = Mock()
        mock_manager._save_metadata = Mock()

        # Execute migration
        from code_indexer.server.app import migrate_legacy_cidx_meta

        migrate_legacy_cidx_meta(mock_manager, str(golden_repos_dir))

        # Verify: No changes were made
        assert mock_repo.repo_url == "local://cidx-meta"  # Unchanged
        mock_manager.add_golden_repo.assert_not_called()
        mock_manager._save_metadata.assert_not_called()

    def test_no_op_when_no_cidx_meta_directory(self, golden_repos_dir):
        """Test that migration is no-op when cidx-meta directory doesn't exist."""
        # Setup: No cidx-meta directory

        # Create mock manager
        mock_manager = Mock()
        mock_manager.golden_repo_exists = Mock(return_value=False)
        mock_manager.add_golden_repo = Mock()

        # Execute migration
        from code_indexer.server.app import migrate_legacy_cidx_meta

        migrate_legacy_cidx_meta(mock_manager, str(golden_repos_dir))

        # Verify: No migration attempted
        mock_manager.add_golden_repo.assert_not_called()


class TestBootstrapCidxMeta:
    """Test cidx-meta bootstrap on fresh installation."""

    def test_creates_cidx_meta_on_fresh_install(self, golden_repos_dir):
        """Test that cidx-meta is auto-created on fresh installation."""
        # Setup: No cidx-meta exists

        # Create mock manager
        mock_manager = Mock()
        mock_manager.golden_repo_exists = Mock(return_value=False)
        mock_manager.golden_repos = {}
        mock_manager._save_metadata = Mock()

        # Mock GlobalActivator to avoid actual global activation
        with patch(
            "code_indexer.global_repos.global_activation.GlobalActivator"
        ) as mock_activator_class:
            mock_activator = Mock()
            mock_activator_class.return_value = mock_activator

            # Mock subprocess.run to verify cidx init/index calls
            with patch("subprocess.run") as mock_subprocess:
                # Execute bootstrap
                from code_indexer.server.app import bootstrap_cidx_meta

                bootstrap_cidx_meta(mock_manager, str(golden_repos_dir))

                # Verify: cidx-meta was created with local:// URL
                assert "cidx-meta" in mock_manager.golden_repos
                repo = mock_manager.golden_repos["cidx-meta"]
                assert repo.repo_url == "local://cidx-meta"
                assert repo.alias == "cidx-meta"

                # Verify: cidx init was called
                cidx_meta_path = golden_repos_dir / "cidx-meta"
                init_call = [
                    call
                    for call in mock_subprocess.call_args_list
                    if call[0][0] == ["cidx", "init"]
                ]
                assert len(init_call) == 1
                assert init_call[0][1]["cwd"] == str(cidx_meta_path)
                assert init_call[0][1]["check"] is True

                # Verify: cidx index was called
                index_call = [
                    call
                    for call in mock_subprocess.call_args_list
                    if call[0][0] == ["cidx", "index"]
                ]
                assert len(index_call) == 1
                assert index_call[0][1]["cwd"] == str(cidx_meta_path)
                assert index_call[0][1]["check"] is True

    def test_no_op_when_cidx_meta_already_exists(self, golden_repos_dir):
        """Test that bootstrap is no-op when cidx-meta already exists."""
        # Setup: cidx-meta already exists

        # Create mock manager
        mock_manager = Mock()
        mock_manager.golden_repo_exists = Mock(return_value=True)
        mock_manager.golden_repos = {}

        # Mock subprocess to ensure it's NOT called
        with patch("subprocess.run") as mock_subprocess:
            # Execute bootstrap
            from code_indexer.server.app import bootstrap_cidx_meta

            bootstrap_cidx_meta(mock_manager, str(golden_repos_dir))

            # Verify: No cidx commands were executed
            mock_subprocess.assert_not_called()

    def test_creates_directory_structure(self, golden_repos_dir):
        """Test that bootstrap creates the cidx-meta directory."""
        # Setup: No cidx-meta directory

        # Create mock manager
        mock_manager = Mock()
        mock_manager.golden_repo_exists = Mock(return_value=False)
        mock_manager.golden_repos = {}
        mock_manager._save_metadata = Mock()

        # Mock GlobalActivator to avoid actual global activation
        with patch(
            "code_indexer.global_repos.global_activation.GlobalActivator"
        ) as mock_activator_class:
            mock_activator = Mock()
            mock_activator_class.return_value = mock_activator

            # Mock subprocess to avoid actual cidx calls
            with patch("subprocess.run") as mock_subprocess:
                # Execute bootstrap
                from code_indexer.server.app import bootstrap_cidx_meta

                bootstrap_cidx_meta(mock_manager, str(golden_repos_dir))

                # Verify: Directory was created
                cidx_meta_path = golden_repos_dir / "cidx-meta"
                assert cidx_meta_path.exists()
                assert cidx_meta_path.is_dir()

    def test_init_skipped_when_code_indexer_exists(self, golden_repos_dir):
        """Test that cidx init is skipped when .code-indexer directory already exists."""
        # Setup: Create cidx-meta directory with existing .code-indexer
        cidx_meta_path = golden_repos_dir / "cidx-meta"
        cidx_meta_path.mkdir(parents=True)
        (cidx_meta_path / ".code-indexer").mkdir()

        # Create mock manager
        mock_manager = Mock()
        mock_manager.golden_repo_exists = Mock(return_value=False)
        mock_manager.golden_repos = {}
        mock_manager._save_metadata = Mock()

        # Mock GlobalActivator
        with patch(
            "code_indexer.global_repos.global_activation.GlobalActivator"
        ) as mock_activator_class:
            mock_activator = Mock()
            mock_activator_class.return_value = mock_activator

            # Mock subprocess
            with patch("subprocess.run") as mock_subprocess:
                # Execute bootstrap
                from code_indexer.server.app import bootstrap_cidx_meta

                bootstrap_cidx_meta(mock_manager, str(golden_repos_dir))

                # Verify: cidx init was NOT called
                init_calls = [
                    call
                    for call in mock_subprocess.call_args_list
                    if call[0][0] == ["cidx", "init"]
                ]
                assert len(init_calls) == 0

                # Verify: cidx index WAS still called
                index_calls = [
                    call
                    for call in mock_subprocess.call_args_list
                    if call[0][0] == ["cidx", "index"]
                ]
                assert len(index_calls) == 1

    def test_subprocess_error_handling(self, golden_repos_dir):
        """Test that bootstrap handles subprocess errors gracefully."""
        # Setup: No cidx-meta exists
        mock_manager = Mock()
        mock_manager.golden_repo_exists = Mock(return_value=False)
        mock_manager.golden_repos = {}
        mock_manager._save_metadata = Mock()

        # Mock GlobalActivator
        with patch(
            "code_indexer.global_repos.global_activation.GlobalActivator"
        ) as mock_activator_class:
            mock_activator = Mock()
            mock_activator_class.return_value = mock_activator

            # Mock subprocess to raise an error
            with patch("subprocess.run") as mock_subprocess:
                import subprocess

                mock_subprocess.side_effect = subprocess.CalledProcessError(
                    1, ["cidx", "init"], stderr="Error running cidx init"
                )

                # Execute bootstrap - should not raise exception
                from code_indexer.server.app import bootstrap_cidx_meta

                # Should complete without raising exception
                bootstrap_cidx_meta(mock_manager, str(golden_repos_dir))

                # Verify: Directory and registration still happened
                cidx_meta_path = golden_repos_dir / "cidx-meta"
                assert cidx_meta_path.exists()
                assert "cidx-meta" in mock_manager.golden_repos

    def test_idempotent_multiple_calls(self, golden_repos_dir):
        """Test that multiple bootstrap calls are safe (idempotent)."""
        # Setup
        mock_manager = Mock()
        mock_manager.golden_repos = {}
        mock_manager._save_metadata = Mock()

        # First call: golden_repo_exists returns False
        mock_manager.golden_repo_exists = Mock(return_value=False)

        # Mock GlobalActivator
        with patch(
            "code_indexer.global_repos.global_activation.GlobalActivator"
        ) as mock_activator_class:
            mock_activator = Mock()
            mock_activator_class.return_value = mock_activator

            # Mock subprocess
            with patch("subprocess.run") as mock_subprocess:
                # Execute bootstrap first time
                from code_indexer.server.app import bootstrap_cidx_meta

                bootstrap_cidx_meta(mock_manager, str(golden_repos_dir))

                first_call_count = mock_subprocess.call_count

                # Second call: golden_repo_exists returns True (already exists)
                mock_manager.golden_repo_exists = Mock(return_value=True)
                mock_subprocess.reset_mock()

                bootstrap_cidx_meta(mock_manager, str(golden_repos_dir))

                # Verify: Second call didn't execute any cidx commands
                assert mock_subprocess.call_count == 0

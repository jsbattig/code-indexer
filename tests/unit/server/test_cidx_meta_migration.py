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
        mock_manager.add_golden_repo = Mock()

        # Execute migration
        from code_indexer.server.app import migrate_legacy_cidx_meta

        migrate_legacy_cidx_meta(mock_manager, str(golden_repos_dir))

        # Verify: add_golden_repo was called with local:// URL
        mock_manager.add_golden_repo.assert_called_once()
        call_args = mock_manager.add_golden_repo.call_args
        assert call_args[1]["repo_url"] == "local://cidx-meta"
        assert call_args[1]["alias"] == "cidx-meta"

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
        mock_manager.add_golden_repo = Mock()

        # Execute bootstrap
        from code_indexer.server.app import bootstrap_cidx_meta

        bootstrap_cidx_meta(mock_manager, str(golden_repos_dir))

        # Verify: cidx-meta was created with local:// URL
        mock_manager.add_golden_repo.assert_called_once()
        call_args = mock_manager.add_golden_repo.call_args
        assert call_args[1]["repo_url"] == "local://cidx-meta"
        assert call_args[1]["alias"] == "cidx-meta"

    def test_no_op_when_cidx_meta_already_exists(self, golden_repos_dir):
        """Test that bootstrap is no-op when cidx-meta already exists."""
        # Setup: cidx-meta already exists

        # Create mock manager
        mock_manager = Mock()
        mock_manager.golden_repo_exists = Mock(return_value=True)
        mock_manager.add_golden_repo = Mock()

        # Execute bootstrap
        from code_indexer.server.app import bootstrap_cidx_meta

        bootstrap_cidx_meta(mock_manager, str(golden_repos_dir))

        # Verify: No creation attempted
        mock_manager.add_golden_repo.assert_not_called()

    def test_creates_directory_structure(self, golden_repos_dir):
        """Test that bootstrap creates the cidx-meta directory."""
        # Setup: No cidx-meta directory

        # Create mock manager
        mock_manager = Mock()
        mock_manager.golden_repo_exists = Mock(return_value=False)
        mock_manager.add_golden_repo = Mock()

        # Execute bootstrap
        from code_indexer.server.app import bootstrap_cidx_meta

        bootstrap_cidx_meta(mock_manager, str(golden_repos_dir))

        # Verify: Directory was created
        cidx_meta_path = golden_repos_dir / "cidx-meta"
        assert cidx_meta_path.exists()
        assert cidx_meta_path.is_dir()

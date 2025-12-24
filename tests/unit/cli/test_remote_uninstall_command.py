"""Test module for remote uninstall command functionality.

Tests the behavior of uninstall command when running in remote mode,
including safe credential removal and configuration cleanup.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_indexer.remote_uninstall import RemoteUninstaller


class TestRemoteUninstaller:
    """Test class for remote uninstall functionality."""

    @pytest.fixture
    def temp_project_root(self):
        """Create temporary project root for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()
            yield project_root

    @pytest.fixture
    def mock_remote_config(self):
        """Create mock remote configuration for testing."""
        return {
            "server_url": "https://server.example.com",
            "encrypted_credentials": "encrypted_jwt_token",
            "repository_link": {
                "alias": "test-repo",
                "url": "https://github.com/test/repo.git",
                "branch": "main",
            },
        }

    def test_uninstall_remote_mode_with_confirmation(
        self, temp_project_root, mock_remote_config
    ):
        """Test remote mode uninstall with user confirmation."""
        # Create remote config file
        config_path = temp_project_root / ".code-indexer" / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(mock_remote_config, f)

        # Create some additional files that should be preserved
        (temp_project_root / "README.md").write_text("Project readme")
        src_dir = temp_project_root / "src"
        src_dir.mkdir(parents=True)
        (src_dir / "main.py").write_text("print('hello')")

        uninstaller = RemoteUninstaller(temp_project_root)

        with patch("builtins.input", return_value="y"):
            result = uninstaller.uninstall(confirm=False)

            # Test should fail initially because function doesn't exist
            assert result is True
            assert not config_path.exists()  # Remote config should be removed
            assert (temp_project_root / "README.md").exists()  # Project files preserved
            assert (
                temp_project_root / "src" / "main.py"
            ).exists()  # Project files preserved

    def test_uninstall_remote_mode_skip_confirmation(
        self, temp_project_root, mock_remote_config
    ):
        """Test remote mode uninstall with confirmation flag set."""
        # Create remote config file
        config_path = temp_project_root / ".code-indexer" / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(mock_remote_config, f)

        uninstaller = RemoteUninstaller(temp_project_root)

        result = uninstaller.uninstall(confirm=True)

        # Test should fail initially because function doesn't exist
        assert result is True
        assert not config_path.exists()  # Remote config should be removed

    def test_uninstall_remote_mode_user_cancels(
        self, temp_project_root, mock_remote_config
    ):
        """Test remote mode uninstall when user cancels operation."""
        # Create remote config file
        config_path = temp_project_root / ".code-indexer" / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(mock_remote_config, f)

        uninstaller = RemoteUninstaller(temp_project_root)

        with patch("builtins.input", return_value="n"):
            result = uninstaller.uninstall(confirm=False)

            # Test should fail initially because function doesn't exist
            assert result is False
            assert config_path.exists()  # Remote config should be preserved

    def test_uninstall_remote_mode_missing_config(self, temp_project_root):
        """Test remote mode uninstall when remote config is missing."""
        uninstaller = RemoteUninstaller(temp_project_root)

        # Should handle missing config gracefully
        result = uninstaller.uninstall(confirm=True)

        # Test should fail initially because function doesn't exist
        assert result is True  # Should succeed even if no config to remove

    def test_uninstall_removes_encrypted_credentials_safely(
        self, temp_project_root, mock_remote_config
    ):
        """Test that uninstall safely removes encrypted credential storage."""
        # Create remote config with encrypted credentials
        config_path = temp_project_root / ".code-indexer" / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(mock_remote_config, f)

        # Create additional credential files
        credential_cache = temp_project_root / ".code-indexer" / ".credential-cache"
        credential_cache.write_text("cached_credentials")

        uninstaller = RemoteUninstaller(temp_project_root)

        result = uninstaller.uninstall(confirm=True)

        # Test should fail initially because function doesn't exist
        assert result is True
        assert not config_path.exists()
        assert not credential_cache.exists()

    def test_uninstall_preserves_local_files(
        self, temp_project_root, mock_remote_config
    ):
        """Test that uninstall preserves local project files and structure."""
        # Create remote config
        config_path = temp_project_root / ".code-indexer" / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(mock_remote_config, f)

        # Create local project structure
        src_dir = temp_project_root / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("print('hello world')")
        (src_dir / "utils.py").write_text("def helper(): pass")

        docs_dir = temp_project_root / "docs"
        docs_dir.mkdir()
        (docs_dir / "README.md").write_text("# Documentation")

        # Create local git repository
        git_dir = temp_project_root / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]\n\trepositoryformatversion = 0")

        uninstaller = RemoteUninstaller(temp_project_root)

        result = uninstaller.uninstall(confirm=True)

        # Test should fail initially because function doesn't exist
        assert result is True

        # Verify remote config removed
        assert not config_path.exists()

        # Verify local files preserved
        assert src_dir.exists()
        assert (src_dir / "main.py").exists()
        assert (src_dir / "utils.py").exists()
        assert docs_dir.exists()
        assert (docs_dir / "README.md").exists()
        assert git_dir.exists()
        assert (git_dir / "config").exists()

    def test_uninstall_provides_reinitialize_guidance(
        self, temp_project_root, mock_remote_config
    ):
        """Test that uninstall provides guidance for re-initialization."""
        # Create remote config
        config_path = temp_project_root / ".code-indexer" / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(mock_remote_config, f)

        uninstaller = RemoteUninstaller(temp_project_root)

        with patch("builtins.print") as mock_print:
            result = uninstaller.uninstall(confirm=True)

            # Test should fail initially because function doesn't exist
            assert result is True

            # Verify guidance messages were printed
            print_calls = [str(call) for call in mock_print.call_args_list]
            guidance_found = any(
                "cidx init" in call or "remote" in call for call in print_calls
            )
            assert guidance_found

    def test_get_uninstall_preview_shows_what_will_be_removed(
        self, temp_project_root, mock_remote_config
    ):
        """Test that uninstall preview shows exactly what will be removed and preserved."""
        # Create remote config and various files
        config_path = temp_project_root / ".code-indexer" / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(mock_remote_config, f)

        credential_cache = temp_project_root / ".code-indexer" / ".credential-cache"
        credential_cache.write_text("cached_data")

        src_dir = temp_project_root / "src"
        src_dir.mkdir(parents=True)
        (src_dir / "main.py").write_text("print('hello')")

        uninstaller = RemoteUninstaller(temp_project_root)

        preview = uninstaller.get_uninstall_preview()

        # Test should work now that function is implemented
        assert "files_to_remove" in preview
        assert "files_to_preserve" in preview

        # Check for partial matches since full path includes .code-indexer/
        files_to_remove = " ".join(preview["files_to_remove"])
        assert ".remote-config" in files_to_remove

        files_to_preserve = " ".join(preview["files_to_preserve"])
        assert "main.py" in files_to_preserve

    def test_uninstall_handles_permission_errors_gracefully(
        self, temp_project_root, mock_remote_config
    ):
        """Test that uninstall handles file permission errors gracefully."""
        # Create remote config
        config_path = temp_project_root / ".code-indexer" / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(mock_remote_config, f)

        # Make config file unremovable
        config_path.chmod(0o444)

        uninstaller = RemoteUninstaller(temp_project_root)

        try:
            with patch(
                "pathlib.Path.unlink", side_effect=PermissionError("Permission denied")
            ):
                result = uninstaller.uninstall(confirm=True)

                # Test should fail initially because function doesn't exist
                # Should handle permission errors gracefully
                assert isinstance(result, bool)
        finally:
            # Restore permissions for cleanup
            config_path.chmod(0o644)

    def test_uninstall_logs_removed_files(self, temp_project_root, mock_remote_config):
        """Test that uninstall logs which files were successfully removed."""
        # Create remote config and additional files
        config_path = temp_project_root / ".code-indexer" / ".remote-config"
        with open(config_path, "w") as f:
            json.dump(mock_remote_config, f)

        credential_cache = temp_project_root / ".code-indexer" / ".credential-cache"
        credential_cache.write_text("cached_data")

        uninstaller = RemoteUninstaller(temp_project_root)

        with patch("logging.Logger.info") as mock_log:
            result = uninstaller.uninstall(confirm=True)

            # Test should fail initially because function doesn't exist
            assert result is True

            # Verify logging of removed files
            log_calls = [str(call) for call in mock_log.call_args_list]
            removed_file_logs = any(
                "removed" in call.lower() and "remote-config" in call
                for call in log_calls
            )
            assert removed_file_logs

"""Unit tests for secure credential storage functionality."""

import stat
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

from code_indexer.remote.credential_manager import (
    store_encrypted_credentials,
    load_encrypted_credentials,
    CredentialNotFoundError,
)


class TestSecureCredentialStorage:
    """Test secure credential storage implementation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_data = b"encrypted_credential_data_here"

    def teardown_method(self):
        """Clean up test fixtures."""
        # Clean up temp directory
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_store_creates_config_directory_with_secure_permissions(self):
        """Test config directory is created with owner-only permissions (700)."""
        project_root = self.temp_dir / "project"
        project_root.mkdir()

        store_encrypted_credentials(project_root, self.test_data)

        config_dir = project_root / ".code-indexer"
        assert config_dir.exists()
        assert config_dir.is_dir()

        # Check directory permissions (700 = owner rwx only)
        dir_mode = config_dir.stat().st_mode
        assert stat.filemode(dir_mode) == "drwx------"

    def test_store_creates_credentials_file_with_secure_permissions(self):
        """Test credentials file is created with owner-only read/write (600)."""
        project_root = self.temp_dir / "project"
        project_root.mkdir()

        store_encrypted_credentials(project_root, self.test_data)

        creds_file = project_root / ".code-indexer" / ".creds"
        assert creds_file.exists()

        # Check file permissions (600 = owner rw only)
        file_mode = creds_file.stat().st_mode
        assert stat.filemode(file_mode) == "-rw-------"

    def test_store_writes_correct_data(self):
        """Test credentials file contains correct encrypted data."""
        project_root = self.temp_dir / "project"
        project_root.mkdir()

        store_encrypted_credentials(project_root, self.test_data)

        creds_file = project_root / ".code-indexer" / ".creds"
        with open(creds_file, "rb") as f:
            stored_data = f.read()

        assert stored_data == self.test_data

    def test_store_uses_atomic_write_operation(self):
        """Test atomic write using temporary file."""
        project_root = self.temp_dir / "project"
        project_root.mkdir()

        # Mock file operations to simulate failure after temp file creation
        def mock_rename(self, target):
            # Simulate failure during atomic rename
            raise OSError("Simulated rename failure")

        with patch.object(Path, "rename", mock_rename):
            with pytest.raises(OSError, match="Simulated rename failure"):
                store_encrypted_credentials(project_root, self.test_data)

        # Verify no partial file was left behind
        creds_file = project_root / ".code-indexer" / ".creds"
        assert not creds_file.exists()

        # Verify temp file was cleaned up
        config_dir = project_root / ".code-indexer"
        temp_files = list(config_dir.glob("*.tmp")) if config_dir.exists() else []
        assert len(temp_files) == 0

    def test_store_overwrites_existing_credentials(self):
        """Test storing new credentials overwrites existing ones."""
        project_root = self.temp_dir / "project"
        project_root.mkdir()

        # Store initial credentials
        initial_data = b"initial_credentials"
        store_encrypted_credentials(project_root, initial_data)

        # Store new credentials
        new_data = b"updated_credentials"
        store_encrypted_credentials(project_root, new_data)

        # Verify new data was stored
        creds_file = project_root / ".code-indexer" / ".creds"
        with open(creds_file, "rb") as f:
            stored_data = f.read()

        assert stored_data == new_data

    def test_load_returns_correct_data(self):
        """Test loading encrypted credentials returns correct data."""
        project_root = self.temp_dir / "project"
        project_root.mkdir()

        # Store test data
        store_encrypted_credentials(project_root, self.test_data)

        # Load and verify
        loaded_data = load_encrypted_credentials(project_root)
        assert loaded_data == self.test_data

    def test_load_nonexistent_credentials_raises_error(self):
        """Test loading from nonexistent path raises CredentialNotFoundError."""
        project_root = self.temp_dir / "nonexistent"

        with pytest.raises(
            CredentialNotFoundError, match="No stored credentials found"
        ):
            load_encrypted_credentials(project_root)

    def test_load_auto_fixes_insecure_permissions(self):
        """Test loading auto-fixes files with insecure permissions."""
        project_root = self.temp_dir / "project"
        project_root.mkdir()

        # Create credentials file with insecure permissions
        config_dir = project_root / ".code-indexer"
        config_dir.mkdir()
        creds_file = config_dir / ".creds"

        with open(creds_file, "wb") as f:
            f.write(self.test_data)

        # Set insecure permissions (readable by group/others)
        creds_file.chmod(0o644)

        # Should auto-fix permissions and load successfully
        loaded_data = load_encrypted_credentials(project_root)
        assert loaded_data == self.test_data

        # Verify permissions were fixed to 600
        file_mode = creds_file.stat().st_mode
        assert not (file_mode & 0o077), "File should have secure permissions (600)"

    def test_load_accepts_secure_permissions(self):
        """Test loading succeeds with secure permissions (600)."""
        project_root = self.temp_dir / "project"
        project_root.mkdir()

        # Store with secure permissions
        store_encrypted_credentials(project_root, self.test_data)

        # Should load successfully
        loaded_data = load_encrypted_credentials(project_root)
        assert loaded_data == self.test_data

    def test_store_handles_directory_creation_failure(self):
        """Test storage handles directory creation failures gracefully."""
        # Try to create in a path that doesn't exist and can't be created
        with patch("pathlib.Path.mkdir") as mock_mkdir:
            mock_mkdir.side_effect = OSError("Permission denied")

            project_root = self.temp_dir / "project"

            with pytest.raises(OSError):
                store_encrypted_credentials(project_root, self.test_data)

    def test_store_handles_file_write_failure(self):
        """Test storage handles file write failures gracefully."""
        project_root = self.temp_dir / "project"
        project_root.mkdir()

        with patch("builtins.open", side_effect=OSError("Disk full")):
            with pytest.raises(OSError):
                store_encrypted_credentials(project_root, self.test_data)

    @pytest.mark.parametrize(
        "insecure_mode",
        [
            0o644,  # Readable by group/others
            0o755,  # Readable/executable by all
            0o777,  # Full permissions for all
            0o622,  # Writable by group
        ],
    )
    def test_load_auto_fixes_various_insecure_permissions(self, insecure_mode):
        """Test loading auto-fixes various insecure permission combinations."""
        project_root = self.temp_dir / "project"
        project_root.mkdir()

        # Create file with insecure permissions
        config_dir = project_root / ".code-indexer"
        config_dir.mkdir()
        creds_file = config_dir / ".creds"

        with open(creds_file, "wb") as f:
            f.write(self.test_data)

        creds_file.chmod(insecure_mode)

        # Should auto-fix permissions and load successfully
        loaded_data = load_encrypted_credentials(project_root)
        assert loaded_data == self.test_data

        # Verify permissions were fixed to 600
        file_mode = creds_file.stat().st_mode
        assert not (
            file_mode & 0o077
        ), f"File should have secure permissions (600), but has {oct(file_mode)}"

    def test_credentials_file_location(self):
        """Test credentials are stored in correct location (.code-indexer/.creds)."""
        project_root = self.temp_dir / "project"
        project_root.mkdir()

        store_encrypted_credentials(project_root, self.test_data)

        expected_path = project_root / ".code-indexer" / ".creds"
        assert expected_path.exists()

        # Verify no credentials stored elsewhere
        other_locations = [
            project_root / ".creds",
            project_root / ".code-indexer" / "credentials",
            project_root / ".code-indexer" / "creds.txt",
        ]

        for location in other_locations:
            assert not location.exists()

    def test_concurrent_access_handling(self):
        """Test handling of concurrent access to credential files."""
        project_root = self.temp_dir / "project"
        project_root.mkdir()

        # This is a basic test - in practice, proper file locking
        # or atomic operations would be needed for true concurrent safety
        store_encrypted_credentials(project_root, self.test_data)

        # Multiple loads should work
        data1 = load_encrypted_credentials(project_root)
        data2 = load_encrypted_credentials(project_root)

        assert data1 == data2 == self.test_data

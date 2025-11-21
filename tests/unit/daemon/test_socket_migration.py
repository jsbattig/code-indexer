"""Unit tests for socket migration functionality."""

import tempfile
from pathlib import Path


from code_indexer.daemon.socket_helper import cleanup_old_socket


class TestSocketMigration:
    """Tests for migrating from old socket location to new."""

    def test_cleanup_old_socket_removes_code_indexer_socket(self):
        """Should remove old .code-indexer/daemon.sock file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            old_socket_dir = repo_path / ".code-indexer"
            old_socket_dir.mkdir()
            old_socket = old_socket_dir / "daemon.sock"
            old_socket.touch()

            assert old_socket.exists()

            cleanup_old_socket(repo_path)

            assert not old_socket.exists()

    def test_cleanup_old_socket_only_removes_if_exists(self):
        """Should not error if old socket doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            # No old socket exists

            # Should not raise any exception
            cleanup_old_socket(repo_path)

    def test_cleanup_old_socket_handles_missing_directory(self):
        """Should not error if .code-indexer directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            # No .code-indexer directory exists

            # Should not raise any exception
            cleanup_old_socket(repo_path)

    def test_cleanup_old_socket_preserves_other_files(self):
        """Should only remove daemon.sock, not other files in .code-indexer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            old_socket_dir = repo_path / ".code-indexer"
            old_socket_dir.mkdir()

            # Create multiple files
            old_socket = old_socket_dir / "daemon.sock"
            old_socket.touch()
            config_file = old_socket_dir / "config.yaml"
            config_file.touch()
            other_file = old_socket_dir / "other.txt"
            other_file.touch()

            cleanup_old_socket(repo_path)

            # Only daemon.sock should be removed
            assert not old_socket.exists()
            assert config_file.exists()
            assert other_file.exists()

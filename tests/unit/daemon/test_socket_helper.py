"""Unit tests for socket_helper module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_indexer.daemon.socket_helper import (
    generate_repo_hash,
    get_socket_directory,
    ensure_socket_directory,
    generate_socket_path,
    create_mapping_file,
    get_repo_from_mapping,
    cleanup_old_socket,
    SocketMode,
)


class TestGenerateRepoHash:
    """Tests for generate_repo_hash function."""

    def test_generate_socket_path_uses_tmp_cidx(self):
        """Socket path should use /tmp/cidx/ base directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            socket_path = generate_socket_path(repo_path)
            assert socket_path.parent == Path("/tmp/cidx")

    def test_socket_path_hash_is_deterministic(self):
        """Same repo path should always generate same hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            hash1 = generate_repo_hash(repo_path)
            hash2 = generate_repo_hash(repo_path)
            assert hash1 == hash2

    def test_socket_path_length_under_limit(self):
        """Socket path must be under 108 characters."""
        # Create a very deep directory structure
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create path that would exceed 108 chars with old method
            deep_path = Path(tmpdir)
            for i in range(20):
                deep_path = deep_path / f"very_long_directory_name_{i}"

            # Even with extremely deep path, socket should be short
            socket_path = generate_socket_path(deep_path)
            assert len(str(socket_path)) < 108
            # Should be /tmp/cidx/{16-char-hash}.sock (32 chars max)
            assert len(str(socket_path)) <= 32

    def test_socket_path_hash_is_unique(self):
        """Different repo paths should generate different hashes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo1 = Path(tmpdir) / "repo1"
            repo2 = Path(tmpdir) / "repo2"
            repo1.mkdir()
            repo2.mkdir()

            hash1 = generate_repo_hash(repo1)
            hash2 = generate_repo_hash(repo2)
            assert hash1 != hash2


class TestMappingFiles:
    """Tests for mapping file functionality."""

    def test_create_mapping_file_stores_repo_path(self):
        """Mapping file should contain original repo path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir) / "test_repo"
            repo_path.mkdir()
            socket_path = Path(tmpdir) / "test.sock"

            create_mapping_file(repo_path, socket_path)

            mapping_path = socket_path.with_suffix('.repo-path')
            assert mapping_path.exists()
            assert mapping_path.read_text().strip() == str(repo_path.resolve())

    def test_get_repo_from_mapping_returns_correct_path(self):
        """get_repo_from_mapping should return the correct repository path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir) / "test_repo"
            repo_path.mkdir()
            socket_path = Path(tmpdir) / "test.sock"

            create_mapping_file(repo_path, socket_path)
            retrieved_path = get_repo_from_mapping(socket_path)

            assert retrieved_path == repo_path.resolve()

    def test_get_repo_from_mapping_returns_none_if_missing(self):
        """get_repo_from_mapping should return None if mapping doesn't exist."""
        socket_path = Path("/tmp/nonexistent.sock")
        result = get_repo_from_mapping(socket_path)
        assert result is None


class TestSocketDirectory:
    """Tests for socket directory management."""

    def test_ensure_socket_directory_creates_tmp_cidx(self):
        """Should create /tmp/cidx with proper permissions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_dir = Path(tmpdir) / "cidx"

            ensure_socket_directory(socket_dir, mode="shared")

            assert socket_dir.exists()
            assert socket_dir.is_dir()

    def test_ensure_socket_directory_sets_permissions_1777(self):
        """Directory should have sticky bit + world writable for shared mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_dir = Path(tmpdir) / "cidx"

            ensure_socket_directory(socket_dir, mode="shared")

            # Check permissions (0o1777 = sticky bit + rwxrwxrwx)
            stat_info = socket_dir.stat()
            # Extract permission bits
            mode = stat_info.st_mode & 0o7777
            assert mode == 0o1777

    def test_ensure_socket_directory_sets_permissions_700_for_user_mode(self):
        """Directory should have 700 permissions for user mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_dir = Path(tmpdir) / "cidx"

            ensure_socket_directory(socket_dir, mode="user")

            stat_info = socket_dir.stat()
            mode = stat_info.st_mode & 0o7777
            assert mode == 0o700

    @patch.dict(os.environ, {}, clear=True)
    def test_fallback_to_tmp_when_xdg_not_set(self):
        """Should use /tmp/cidx when XDG_RUNTIME_DIR not set in user mode."""
        socket_dir = get_socket_directory(mode="user")
        assert socket_dir == Path("/tmp/cidx")

    def test_get_socket_directory_prefers_tmp_in_shared_mode(self):
        """Shared mode should use /tmp/cidx."""
        socket_dir = get_socket_directory(mode="shared")
        assert socket_dir == Path("/tmp/cidx")

    @patch.dict(os.environ, {"XDG_RUNTIME_DIR": "/run/user/1000"})
    def test_get_socket_directory_uses_xdg_in_user_mode(self):
        """User mode should use XDG_RUNTIME_DIR/cidx when available."""
        socket_dir = get_socket_directory(mode="user")
        assert socket_dir == Path("/run/user/1000/cidx")


class TestSocketCleanup:
    """Tests for cleaning up old socket files."""

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


class TestSocketPathGeneration:
    """Tests for complete socket path generation."""

    def test_generate_socket_path_creates_directory(self):
        """generate_socket_path should ensure directory exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use a custom temp directory for testing
            with patch('code_indexer.daemon.socket_helper.get_socket_directory') as mock_get_dir:
                test_socket_dir = Path(tmpdir) / "test_cidx"
                mock_get_dir.return_value = test_socket_dir

                repo_path = Path(tmpdir) / "test_repo"
                repo_path.mkdir()

                socket_path = generate_socket_path(repo_path)

                assert test_socket_dir.exists()
                assert socket_path.parent == test_socket_dir

    def test_hash_is_exactly_16_chars(self):
        """Hash should be exactly 16 characters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            hash_str = generate_repo_hash(repo_path)
            assert len(hash_str) == 16
            assert all(c in '0123456789abcdef' for c in hash_str)
"""Unit tests for DeploymentLock - deployment concurrency control."""

from pathlib import Path
from unittest.mock import patch, mock_open

from code_indexer.server.auto_update.deployment_lock import DeploymentLock


class TestDeploymentLockInitialization:
    """Test DeploymentLock initialization."""

    def test_initializes_with_lock_file_path(self):
        """DeploymentLock should initialize with lock file path."""
        lock = DeploymentLock(lock_file=Path("/tmp/test.lock"))

        assert lock.lock_file == Path("/tmp/test.lock")


class TestDeploymentLockAcquire:
    """Test DeploymentLock acquire operation."""

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.getpid")
    def test_acquire_creates_lock_file_when_not_exists(
        self, mock_getpid, mock_file, mock_exists
    ):
        """acquire() should create lock file when it doesn't exist."""
        mock_exists.return_value = False
        mock_getpid.return_value = 12345

        lock = DeploymentLock(lock_file=Path("/tmp/test.lock"))
        result = lock.acquire()

        assert result is True
        mock_file.assert_called_once_with(Path("/tmp/test.lock"), "w")
        mock_file().write.assert_called_once_with("12345")

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="99999")
    @patch("os.kill")
    def test_acquire_returns_false_when_lock_held_by_active_process(
        self, mock_kill, mock_file, mock_exists
    ):
        """acquire() should return False when lock is held by active process."""
        mock_exists.return_value = True
        # os.kill doesn't raise = process is alive
        mock_kill.return_value = None

        lock = DeploymentLock(lock_file=Path("/tmp/test.lock"))
        result = lock.acquire()

        assert result is False

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="99999")
    @patch("os.kill")
    @patch("pathlib.Path.unlink")
    @patch("os.getpid")
    def test_acquire_removes_stale_lock_and_creates_new(
        self, mock_getpid, mock_unlink, mock_kill, mock_file, mock_exists
    ):
        """acquire() should remove stale lock and create new one."""
        mock_exists.return_value = True
        # os.kill raises OSError = process is dead
        mock_kill.side_effect = OSError("No such process")
        mock_getpid.return_value = 12345

        # Need to handle both read and write calls
        read_mock = mock_open(read_data="99999")
        write_mock = mock_open()
        mock_file.side_effect = [read_mock.return_value, write_mock.return_value]

        lock = DeploymentLock(lock_file=Path("/tmp/test.lock"))
        result = lock.acquire()

        assert result is True
        mock_unlink.assert_called_once()

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="invalid")
    @patch("pathlib.Path.unlink")
    @patch("os.getpid")
    def test_acquire_handles_invalid_pid_in_lock_file(
        self, mock_getpid, mock_unlink, mock_file, mock_exists
    ):
        """acquire() should handle invalid PID in lock file as stale."""
        mock_exists.return_value = True
        mock_getpid.return_value = 12345

        # Need to handle both read and write calls
        read_mock = mock_open(read_data="invalid")
        write_mock = mock_open()
        mock_file.side_effect = [read_mock.return_value, write_mock.return_value]

        lock = DeploymentLock(lock_file=Path("/tmp/test.lock"))
        result = lock.acquire()

        assert result is True
        mock_unlink.assert_called_once()


class TestDeploymentLockRelease:
    """Test DeploymentLock release operation."""

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.unlink")
    def test_release_deletes_lock_file(self, mock_unlink, mock_exists):
        """release() should delete lock file."""
        mock_exists.return_value = True

        lock = DeploymentLock(lock_file=Path("/tmp/test.lock"))
        lock.release()

        mock_unlink.assert_called_once()

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.unlink")
    def test_release_handles_missing_lock_file(self, mock_unlink, mock_exists):
        """release() should handle missing lock file gracefully."""
        mock_exists.return_value = False

        lock = DeploymentLock(lock_file=Path("/tmp/test.lock"))
        lock.release()

        mock_unlink.assert_not_called()

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.unlink")
    def test_release_handles_permission_error(self, mock_unlink, mock_exists):
        """release() should handle permission errors gracefully."""
        mock_exists.return_value = True
        mock_unlink.side_effect = PermissionError("Permission denied")

        lock = DeploymentLock(lock_file=Path("/tmp/test.lock"))
        # Should not raise exception
        lock.release()


class TestDeploymentLockStaleDetection:
    """Test DeploymentLock stale lock detection."""

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="99999")
    @patch("os.kill")
    def test_is_stale_returns_true_when_process_dead(
        self, mock_kill, mock_file, mock_exists
    ):
        """is_stale() should return True when process doesn't exist."""
        mock_exists.return_value = True
        mock_kill.side_effect = OSError("No such process")

        lock = DeploymentLock(lock_file=Path("/tmp/test.lock"))
        result = lock.is_stale()

        assert result is True

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="99999")
    @patch("os.kill")
    def test_is_stale_returns_false_when_process_alive(
        self, mock_kill, mock_file, mock_exists
    ):
        """is_stale() should return False when process is alive."""
        mock_exists.return_value = True
        mock_kill.return_value = None  # No exception = process alive

        lock = DeploymentLock(lock_file=Path("/tmp/test.lock"))
        result = lock.is_stale()

        assert result is False

    @patch("pathlib.Path.exists")
    def test_is_stale_returns_false_when_lock_file_missing(self, mock_exists):
        """is_stale() should return False when lock file doesn't exist."""
        mock_exists.return_value = False

        lock = DeploymentLock(lock_file=Path("/tmp/test.lock"))
        result = lock.is_stale()

        assert result is False

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_is_stale_returns_false_on_read_ioerror(self, mock_file, mock_exists):
        """is_stale() should return False when lock file can't be read."""
        mock_exists.return_value = True
        mock_file.side_effect = IOError("Permission denied")

        lock = DeploymentLock(lock_file=Path("/tmp/test.lock"))
        result = lock.is_stale()

        assert result is False


class TestDeploymentLockExceptionHandling:
    """Test DeploymentLock exception handling during I/O operations."""

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_acquire_raises_on_read_ioerror(self, mock_file, mock_exists):
        """acquire() should raise IOError when lock file can't be read."""
        import pytest

        mock_exists.return_value = True
        mock_file.side_effect = IOError("Permission denied")

        lock = DeploymentLock(lock_file=Path("/tmp/test.lock"))

        with pytest.raises(IOError, match="Permission denied"):
            lock.acquire()

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.getpid")
    def test_acquire_raises_on_write_ioerror(self, mock_getpid, mock_file, mock_exists):
        """acquire() should raise IOError when lock file can't be written."""
        import pytest

        mock_exists.return_value = False
        mock_getpid.return_value = 12345

        # First call for write fails
        mock_file.side_effect = IOError("Disk full")

        lock = DeploymentLock(lock_file=Path("/tmp/test.lock"))

        with pytest.raises(IOError, match="Disk full"):
            lock.acquire()

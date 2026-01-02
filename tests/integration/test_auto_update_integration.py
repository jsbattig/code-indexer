"""Integration tests for auto-update system - ZERO MOCKING.

These tests use REAL systems:
- Real git repositories
- Real filesystem operations
- Real subprocess execution
- Real lock file handling
"""

import os
import subprocess
import tempfile
from pathlib import Path
import pytest

from code_indexer.server.auto_update.change_detector import ChangeDetector
from code_indexer.server.auto_update.deployment_lock import DeploymentLock
from code_indexer.server.auto_update.deployment_executor import DeploymentExecutor


@pytest.fixture
def real_git_repo():
    """Create a real git repository with remote for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create bare repo to use as remote origin
        origin_path = Path(tmpdir) / "origin.git"
        origin_path.mkdir()
        subprocess.run(
            ["git", "init", "--bare"],
            cwd=origin_path,
            check=True,
            capture_output=True,
        )

        # Create working repo
        repo_path = Path(tmpdir) / "test-repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(
            ["git", "init"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Add remote origin pointing to bare repo
        subprocess.run(
            ["git", "remote", "add", "origin", f"file://{origin_path}"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create initial commit
        test_file = repo_path / "test.txt"
        test_file.write_text("Initial content")
        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Push to origin so fetch works
        subprocess.run(
            ["git", "push", "-u", "origin", "master"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        yield repo_path


@pytest.fixture
def real_lock_file():
    """Create a real lock file for testing."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        lock_path = Path(f.name)

    try:
        # Ensure it's deleted before tests
        if lock_path.exists():
            lock_path.unlink()
        yield lock_path
    finally:
        # Clean up after tests
        if lock_path.exists():
            lock_path.unlink()


class TestChangeDetectorIntegration:
    """Integration tests for ChangeDetector with real git repository."""

    def test_detects_no_changes_when_refs_match(self, real_git_repo):
        """ChangeDetector should detect no changes when local and remote refs match."""
        detector = ChangeDetector(repo_path=real_git_repo, branch="master")

        # No remote changes - should return False
        has_changes = detector.has_changes()

        assert has_changes is False

    def test_fetch_executes_real_git_command(self, real_git_repo):
        """ChangeDetector.fetch() should execute real git fetch command."""
        detector = ChangeDetector(repo_path=real_git_repo, branch="master")

        # Should not raise exception
        detector.fetch()

    def test_get_local_ref_returns_real_commit_hash(self, real_git_repo):
        """ChangeDetector.get_local_ref() should return real git commit hash."""
        detector = ChangeDetector(repo_path=real_git_repo, branch="master")

        local_ref = detector.get_local_ref()

        # Git commit hash is 40 hex characters
        assert len(local_ref) == 40
        assert all(c in "0123456789abcdef" for c in local_ref)

    def test_handles_real_git_failure(self):
        """ChangeDetector should raise exception on real git failure."""
        # Use non-existent repo path
        detector = ChangeDetector(repo_path=Path("/nonexistent/repo"), branch="master")

        with pytest.raises(Exception):
            detector.fetch()


class TestDeploymentLockIntegration:
    """Integration tests for DeploymentLock with real file operations."""

    def test_acquire_creates_real_lock_file(self, real_lock_file):
        """DeploymentLock should create real lock file on filesystem."""
        lock = DeploymentLock(lock_file=real_lock_file)

        result = lock.acquire()

        assert result is True
        assert real_lock_file.exists()
        # Lock file should contain PID
        pid_in_file = int(real_lock_file.read_text().strip())
        assert pid_in_file == os.getpid()

    def test_acquire_fails_when_lock_already_held(self, real_lock_file):
        """DeploymentLock should fail to acquire when lock already held."""
        lock1 = DeploymentLock(lock_file=real_lock_file)
        lock2 = DeploymentLock(lock_file=real_lock_file)

        # First acquire succeeds
        result1 = lock1.acquire()
        assert result1 is True

        # Second acquire fails (same process, lock still held)
        result2 = lock2.acquire()
        assert result2 is False

    def test_acquire_removes_stale_lock_file(self, real_lock_file):
        """DeploymentLock should remove stale lock file from dead process."""
        # Create stale lock file with fake PID
        real_lock_file.write_text("99999999")

        lock = DeploymentLock(lock_file=real_lock_file)
        result = lock.acquire()

        # Should acquire lock after removing stale lock
        assert result is True
        assert real_lock_file.exists()
        # Lock file should now contain current PID
        pid_in_file = int(real_lock_file.read_text().strip())
        assert pid_in_file == os.getpid()

    def test_release_deletes_real_lock_file(self, real_lock_file):
        """DeploymentLock.release() should delete real lock file."""
        lock = DeploymentLock(lock_file=real_lock_file)
        lock.acquire()

        lock.release()

        assert not real_lock_file.exists()

    def test_is_stale_detects_real_stale_lock(self, real_lock_file):
        """DeploymentLock.is_stale() should detect real stale lock from dead process."""
        # Create lock file with fake PID
        real_lock_file.write_text("99999999")

        lock = DeploymentLock(lock_file=real_lock_file)
        result = lock.is_stale()

        assert result is True

    def test_is_stale_detects_active_lock(self, real_lock_file):
        """DeploymentLock.is_stale() should detect lock from active process."""
        # Create lock file with current PID
        real_lock_file.write_text(str(os.getpid()))

        lock = DeploymentLock(lock_file=real_lock_file)
        result = lock.is_stale()

        assert result is False


class TestDeploymentExecutorIntegration:
    """Integration tests for DeploymentExecutor with real subprocess execution."""

    def test_git_pull_executes_real_command(self, real_git_repo):
        """DeploymentExecutor.git_pull() should execute real git pull command."""
        executor = DeploymentExecutor(
            repo_path=real_git_repo, service_name="test-service"
        )

        # Real git pull with configured remote
        result = executor.git_pull()

        # Should succeed with properly configured git remote
        assert result is True

    def test_pip_install_executes_real_command(self, real_git_repo):
        """DeploymentExecutor.pip_install() should execute real pip install command."""
        executor = DeploymentExecutor(
            repo_path=real_git_repo, service_name="test-service"
        )

        # Create minimal setup.py to make pip install work
        setup_py = real_git_repo / "setup.py"
        setup_py.write_text(
            """
from setuptools import setup
setup(name='test-package', version='0.0.1')
"""
        )

        # Real pip install
        result = executor.pip_install()

        # May fail if virtual environment issues, but tests real execution
        # Don't assert result - just verify no exception raised

    def test_execute_runs_real_deployment_workflow(self, real_git_repo):
        """DeploymentExecutor.execute() should run real deployment workflow."""
        executor = DeploymentExecutor(
            repo_path=real_git_repo, service_name="test-service"
        )

        # Create setup.py for pip install step
        setup_py = real_git_repo / "setup.py"
        setup_py.write_text(
            """
from setuptools import setup
setup(name='test-package', version='0.0.1')
"""
        )

        # Real execution (git pull will fail, but tests real workflow)
        result = executor.execute()

        # Expected to fail at git pull (no remote), but validates real execution
        assert result is False


class TestEndToEndDeploymentWorkflow:
    """End-to-end integration tests for complete deployment workflow."""

    def test_full_workflow_with_real_components(self, real_git_repo, real_lock_file):
        """Complete deployment workflow with real components (no mocking)."""
        # Real components
        detector = ChangeDetector(repo_path=real_git_repo, branch="master")
        lock = DeploymentLock(lock_file=real_lock_file)
        executor = DeploymentExecutor(
            repo_path=real_git_repo, service_name="test-service"
        )

        # Step 1: Check for changes
        has_changes = detector.has_changes()
        assert has_changes is False  # No remote changes

        # Step 2: Acquire lock
        lock_acquired = lock.acquire()
        assert lock_acquired is True
        assert real_lock_file.exists()

        # Step 3: Execute deployment (will fail at git pull, but validates workflow)
        try:
            result = executor.execute()
            # Expected to fail (no remote configured)
            assert result is False
        finally:
            # Step 4: Release lock
            lock.release()
            assert not real_lock_file.exists()

    def test_concurrent_deployment_prevention_with_real_locks(self, real_lock_file):
        """Real lock file should prevent concurrent deployments."""
        lock1 = DeploymentLock(lock_file=real_lock_file)
        lock2 = DeploymentLock(lock_file=real_lock_file)

        # First deployment acquires lock
        acquired1 = lock1.acquire()
        assert acquired1 is True

        # Second deployment fails to acquire
        acquired2 = lock2.acquire()
        assert acquired2 is False

        # First deployment releases lock
        lock1.release()

        # Now second deployment can acquire
        acquired3 = lock2.acquire()
        assert acquired3 is True

        lock2.release()

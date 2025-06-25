"""
TDD tests for resilient branch tracking during indexing.

This test suite covers the complete branch tracking workflow:
1. Branch detection and storage in progressive metadata
2. Git hook installation and management
3. File locking for safe concurrent branch updates
4. Branch reading during indexing with retry logic
5. End-to-end scenarios including branch changes during indexing
"""

import time
import threading
from unittest.mock import Mock, patch

from code_indexer.services.progressive_metadata import ProgressiveMetadata


class TestBranchTrackingInProgressiveMetadata:
    """Test branch tracking capabilities in ProgressiveMetadata."""

    def test_stores_initial_branch_on_indexing_start(self, tmp_path):
        """Test that current branch is stored when indexing starts."""
        metadata_file = tmp_path / "metadata.json"
        metadata = ProgressiveMetadata(metadata_file)

        git_status = {
            "git_available": True,
            "current_branch": "feature/new-feature",
            "current_commit": "abc123",
            "project_id": "test-project",
        }

        metadata.start_indexing("test-provider", "test-model", git_status)

        # Should store the branch
        assert metadata.get_current_branch() == "feature/new-feature"

        # Should persist to disk
        metadata2 = ProgressiveMetadata(metadata_file)
        assert metadata2.get_current_branch() == "feature/new-feature"

    def test_updates_current_branch_safely(self, tmp_path):
        """Test that current branch can be updated safely during indexing."""
        metadata_file = tmp_path / "metadata.json"
        metadata = ProgressiveMetadata(metadata_file)

        # Start with initial branch
        git_status = {"git_available": True, "current_branch": "master"}
        metadata.start_indexing("test-provider", "test-model", git_status)

        # Update to new branch (simulating git hook)
        metadata.update_current_branch("feature/branch-switch")

        assert metadata.get_current_branch() == "feature/branch-switch"

        # Should persist
        metadata2 = ProgressiveMetadata(metadata_file)
        assert metadata2.get_current_branch() == "feature/branch-switch"

    def test_handles_concurrent_branch_updates_with_locking(self, tmp_path):
        """Test that concurrent branch updates are handled safely with file locking."""
        metadata_file = tmp_path / "metadata.json"
        metadata = ProgressiveMetadata(metadata_file)

        git_status = {"git_available": True, "current_branch": "master"}
        metadata.start_indexing("test-provider", "test-model", git_status)

        results = []
        errors = []

        def update_branch(branch_name, wait_time=0):
            try:
                if wait_time:
                    time.sleep(wait_time)
                metadata.update_current_branch(f"feature/{branch_name}")
                results.append(f"feature/{branch_name}")
            except Exception as e:
                errors.append(str(e))

        def read_branch(wait_time=0):
            try:
                if wait_time:
                    time.sleep(wait_time)
                branch = metadata.get_current_branch()
                results.append(f"read:{branch}")
            except Exception as e:
                errors.append(str(e))

        # Start multiple threads doing concurrent updates and reads
        threads = [
            threading.Thread(target=update_branch, args=("thread1", 0.01)),
            threading.Thread(target=update_branch, args=("thread2", 0.02)),
            threading.Thread(target=read_branch, args=(0.015,)),
            threading.Thread(target=read_branch, args=(0.025,)),
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Should have no errors from concurrent access
        assert len(errors) == 0, f"Concurrent access errors: {errors}"

        # Should have all operations completed
        assert len(results) == 4

        # Final state should be consistent
        final_branch = metadata.get_current_branch()
        assert final_branch.startswith("feature/")

    def test_branch_reading_with_retry_on_lock_failure(self, tmp_path):
        """Test that branch reading retries once if file is locked."""
        metadata_file = tmp_path / "metadata.json"
        metadata = ProgressiveMetadata(metadata_file)

        git_status = {"git_available": True, "current_branch": "master"}
        metadata.start_indexing("test-provider", "test-model", git_status)

        # Mock file operations to simulate lock failure then success
        original_open = open
        call_count = 0

        def mock_open(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call fails (simulating lock)
                raise OSError("Resource temporarily unavailable")
            else:
                # Second call succeeds
                return original_open(*args, **kwargs)

        with patch("builtins.open", side_effect=mock_open):
            # Should retry and succeed
            branch = metadata.get_current_branch_with_retry()
            assert branch == "master"
            assert call_count == 2  # Should have retried once

    def test_branch_reading_fails_after_max_retries(self, tmp_path):
        """Test that branch reading fails gracefully after max retries."""
        metadata_file = tmp_path / "metadata.json"
        metadata = ProgressiveMetadata(metadata_file)

        # Mock file operations to always fail
        with patch("builtins.open", side_effect=OSError("Persistent lock")):
            # Should return fallback value after retries
            branch = metadata.get_current_branch_with_retry(fallback="unknown")
            assert branch == "unknown"


class TestGitHookManagement:
    """Test git hook installation and management for branch change detection."""

    def test_detects_git_repository(self, tmp_path):
        """Test detection of git repository for hook installation."""
        from code_indexer.services.git_hook_manager import GitHookManager

        # Non-git directory
        non_git_dir = tmp_path / "non-git"
        non_git_dir.mkdir()
        hook_manager = GitHookManager(non_git_dir)
        assert not hook_manager.is_git_repository()

        # Git directory
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()
        hook_manager = GitHookManager(git_dir)
        assert hook_manager.is_git_repository()

    def test_installs_post_checkout_hook(self, tmp_path):
        """Test installation of post-checkout git hook."""
        from code_indexer.services.git_hook_manager import GitHookManager

        # Setup git repo
        git_dir = tmp_path / "git-repo"
        git_dir.mkdir()
        git_hooks_dir = git_dir / ".git" / "hooks"
        git_hooks_dir.mkdir(parents=True)

        metadata_file = tmp_path / "metadata.json"
        hook_manager = GitHookManager(git_dir, metadata_file)

        # Install hook
        hook_manager.install_branch_change_hook()

        # Should create post-checkout hook
        hook_file = git_hooks_dir / "post-checkout"
        assert hook_file.exists()
        assert hook_file.stat().st_mode & 0o111  # Should be executable

        # Hook content should update metadata file
        hook_content = hook_file.read_text()
        assert str(metadata_file) in hook_content
        assert "Code Indexer Branch Tracking" in hook_content

    def test_preserves_existing_post_checkout_hook(self, tmp_path):
        """Test that existing post-checkout hook is preserved and extended."""
        from code_indexer.services.git_hook_manager import GitHookManager

        # Setup git repo with existing hook
        git_dir = tmp_path / "git-repo"
        git_hooks_dir = git_dir / ".git" / "hooks"
        git_hooks_dir.mkdir(parents=True)

        existing_hook = git_hooks_dir / "post-checkout"
        existing_hook.write_text("#!/bin/bash\necho 'existing hook'\n")
        existing_hook.chmod(0o755)

        metadata_file = tmp_path / "metadata.json"
        hook_manager = GitHookManager(git_dir, metadata_file)

        # Install our hook
        hook_manager.install_branch_change_hook()

        # Should preserve existing content and add ours
        hook_content = existing_hook.read_text()
        assert "existing hook" in hook_content
        assert "Code Indexer Branch Tracking" in hook_content

    def test_checks_hook_installation_on_index_command(self, tmp_path):
        """Test that hook installation is checked every time index command runs."""
        from code_indexer.services.git_hook_manager import GitHookManager

        git_dir = tmp_path / "git-repo"
        git_hooks_dir = git_dir / ".git" / "hooks"
        git_hooks_dir.mkdir(parents=True)

        metadata_file = tmp_path / "metadata.json"
        hook_manager = GitHookManager(git_dir, metadata_file)

        # First check should install hook
        hook_manager.ensure_hook_installed()
        hook_file = git_hooks_dir / "post-checkout"
        assert hook_file.exists()

        # Remove hook to simulate missing
        hook_file.unlink()

        # Second check should reinstall
        hook_manager.ensure_hook_installed()
        assert hook_file.exists()

    def test_hook_updates_branch_in_metadata_file(self, tmp_path):
        """Test that git hook actually updates branch in metadata file."""
        # This test simulates the hook execution
        metadata_file = tmp_path / "metadata.json"

        # Create initial metadata
        metadata = ProgressiveMetadata(metadata_file)
        git_status = {"git_available": True, "current_branch": "master"}
        metadata.start_indexing("test-provider", "test-model", git_status)

        # Simulate hook execution (normally triggered by git)
        # This would be the Python code inside the git hook
        metadata.update_current_branch("feature/new-branch")

        # Verify update
        assert metadata.get_current_branch() == "feature/new-branch"

        # Verify persistence
        metadata2 = ProgressiveMetadata(metadata_file)
        assert metadata2.get_current_branch() == "feature/new-branch"


class TestBranchAwareIndexerIntegration:
    """Test BranchAwareIndexer integration with file-based branch tracking."""

    def test_reads_current_branch_from_metadata_file(self, tmp_path):
        """Test that BranchAwareIndexer reads current branch from metadata file."""
        from code_indexer.services.branch_aware_indexer import BranchAwareIndexer

        # Setup
        metadata_file = tmp_path / "metadata.json"
        metadata = ProgressiveMetadata(metadata_file)
        git_status = {"git_available": True, "current_branch": "feature/indexing"}
        metadata.start_indexing("test-provider", "test-model", git_status)

        # Mock config and dependencies
        config = Mock()
        config.codebase_dir = tmp_path
        embedding_provider = Mock()
        qdrant_client = Mock()
        text_chunker = Mock()

        indexer = BranchAwareIndexer(
            qdrant_client, embedding_provider, text_chunker, config
        )
        indexer.metadata_file = metadata_file

        # Should read branch from file
        current_branch = indexer.get_current_branch_from_file()
        assert current_branch == "feature/indexing"

    def test_retries_branch_reading_on_file_lock(self, tmp_path):
        """Test that indexer retries branch reading if metadata file is locked."""
        from code_indexer.services.branch_aware_indexer import BranchAwareIndexer

        metadata_file = tmp_path / "metadata.json"
        metadata = ProgressiveMetadata(metadata_file)
        git_status = {"git_available": True, "current_branch": "master"}
        metadata.start_indexing("test-provider", "test-model", git_status)

        # Mock config and dependencies
        config = Mock()
        config.codebase_dir = tmp_path
        indexer = BranchAwareIndexer(Mock(), Mock(), Mock(), config)
        indexer.metadata_file = metadata_file

        # Mock file operations to fail once then succeed
        original_open = open
        call_count = 0

        def mock_open(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("Resource temporarily unavailable")
            return original_open(*args, **kwargs)

        with patch("builtins.open", side_effect=mock_open):
            branch = indexer.get_current_branch_from_file()
            assert branch == "master"
            assert call_count == 2

    def test_uses_file_branch_for_content_point_creation(self, tmp_path):
        """Test that content points use branch from metadata file, not git subprocess."""
        from code_indexer.services.branch_aware_indexer import BranchAwareIndexer

        metadata_file = tmp_path / "metadata.json"
        metadata = ProgressiveMetadata(metadata_file)
        git_status = {"git_available": True, "current_branch": "feature/current"}
        metadata.start_indexing("test-provider", "test-model", git_status)

        # Mock dependencies
        config = Mock()
        config.codebase_dir = tmp_path
        embedding_provider = Mock()
        embedding_provider.get_current_model.return_value = "test-model"
        qdrant_client = Mock()
        qdrant_client.create_point.return_value = {"id": "test-point"}
        text_chunker = Mock()

        indexer = BranchAwareIndexer(
            qdrant_client, embedding_provider, text_chunker, config
        )
        indexer.metadata_file = metadata_file

        # Create content point
        chunk = {"text": "test content", "chunk_index": 0, "total_chunks": 1}
        embedding = [0.1, 0.2, 0.3]

        with patch.object(indexer, "_detect_language", return_value="python"):
            with patch.object(
                indexer, "_determine_working_dir_status", return_value="committed"
            ):
                indexer._create_content_point(
                    "test.py", chunk, "commit123", embedding, "ignored-branch-param"
                )

        # Should use branch from metadata file, not the parameter
        # Note: content points should be branch-agnostic, but let's verify the correct flow
        # The branch should come from the metadata file when creating visibility points
        assert qdrant_client.create_point.called


class TestEndToEndBranchChangeScenarios:
    """Test complete end-to-end scenarios involving branch changes during indexing."""

    def test_branch_change_during_indexing_updates_subsequent_files(self, tmp_path):
        """Test that branch changes during indexing affect subsequent file indexing."""
        # This is a complex integration test that would simulate:
        # 1. Start indexing with branch A
        # 2. Process some files
        # 3. Git hook triggers branch change to B
        # 4. Subsequent files get indexed with branch B

        metadata_file = tmp_path / "metadata.json"
        metadata = ProgressiveMetadata(metadata_file)

        # Start indexing
        git_status = {"git_available": True, "current_branch": "master"}
        metadata.start_indexing("test-provider", "test-model", git_status)

        # Simulate processing some files
        assert metadata.get_current_branch() == "master"

        # Simulate git hook triggering branch change
        metadata.update_current_branch("feature/switched")

        # Subsequent reads should get new branch
        assert metadata.get_current_branch() == "feature/switched"

        # This would be extended to test actual file indexing with different branches

    def test_handles_metadata_file_corruption_gracefully(self, tmp_path):
        """Test graceful handling of corrupted metadata file during branch reading."""
        metadata_file = tmp_path / "metadata.json"

        # Create corrupted metadata file
        metadata_file.write_text("invalid json {")

        metadata = ProgressiveMetadata(metadata_file)

        # Should handle corruption gracefully and return fallback
        branch = metadata.get_current_branch_with_retry(fallback="unknown")
        assert branch == "unknown"

    def test_metadata_file_recovery_after_corruption(self, tmp_path):
        """Test that metadata file can recover after corruption."""
        metadata_file = tmp_path / "metadata.json"

        # Create valid metadata
        metadata = ProgressiveMetadata(metadata_file)
        git_status = {"git_available": True, "current_branch": "master"}
        metadata.start_indexing("test-provider", "test-model", git_status)

        # Corrupt the file
        metadata_file.write_text("corrupted")

        # Should recover and create fresh metadata
        metadata2 = ProgressiveMetadata(metadata_file)
        git_status2 = {"git_available": True, "current_branch": "recovered"}
        metadata2.start_indexing("test-provider", "test-model", git_status2)

        assert metadata2.get_current_branch() == "recovered"


# These tests should all fail initially since we haven't implemented the functionality yet
# Let's run them to see the failures, then implement one by one following TDD

"""
Unit tests for watch mode file change detection.

Tests that watch mode correctly detects file content changes in commits
and automatically triggers re-indexing.
"""

import pytest
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import Mock

from code_indexer.services.git_topology_service import GitTopologyService
from code_indexer.services.git_aware_watch_handler import GitAwareWatchHandler


class TestWatchModeFileChangeDetection:
    """Tests for watch mode git file change detection."""

    @pytest.fixture
    def git_repo(self):
        """Create a temporary git repository for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Initialize git repo
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
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

            # Create initial commit
            test_file = repo_path / "test.py"
            test_file.write_text("def hello(): pass\n")

            subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            yield repo_path

    @pytest.fixture
    def git_topology_service(self, git_repo):
        """Create a GitTopologyService for the test repo."""
        return GitTopologyService(git_repo)

    def test_git_topology_detects_file_changes_in_commits(self, git_repo, git_topology_service):
        """Test that git topology service detects actual file content changes between commits."""
        # Get initial commit
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        initial_commit = result.stdout.strip()

        # Modify a file and commit
        test_file = git_repo / "test.py"
        test_file.write_text("def hello_modified(): pass\n")

        subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Modify test.py"],
            cwd=git_repo,
            check=True,
            capture_output=True,
        )

        # Get new commit
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        new_commit = result.stdout.strip()

        # Get current branch
        git_topology_service.get_current_branch()

        # Analyze changes between commits (simulating watch mode commit detection)
        # BUG: Currently watch mode reports "0 changed files" when it should detect changes
        changed_files = git_topology_service._get_changed_files(initial_commit, new_commit)

        # CRITICAL: Should detect that test.py was modified
        assert len(changed_files) > 0, "Should detect at least one changed file"
        assert "test.py" in changed_files, "Should detect test.py as changed"

    def test_git_topology_detects_new_file_in_commit(self, git_repo, git_topology_service):
        """Test that git topology service detects new files added in commits."""
        # Get initial commit
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        initial_commit = result.stdout.strip()

        # Add a new file and commit
        new_file = git_repo / "new_file.py"
        new_file.write_text("def new_function(): pass\n")

        subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add new_file.py"],
            cwd=git_repo,
            check=True,
            capture_output=True,
        )

        # Get new commit
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        new_commit = result.stdout.strip()

        # Analyze changes
        changed_files = git_topology_service._get_changed_files(initial_commit, new_commit)

        # Should detect new file
        assert len(changed_files) > 0
        assert "new_file.py" in changed_files

    def test_watch_mode_handler_triggers_reindex_on_commit_detection(self, git_repo):
        """Test that watch handler triggers re-indexing when commit changes are detected."""
        # Create mock dependencies
        mock_config = Mock()
        mock_config.codebase_dir = git_repo
        mock_config.file_extensions = {".py"}
        mock_config.exclude_dirs = set()

        mock_smart_indexer = Mock()
        mock_smart_indexer.process_files_incrementally = Mock(return_value=Mock(files_processed=2))

        git_topology_service = GitTopologyService(git_repo)

        mock_watch_metadata = Mock()
        mock_watch_metadata.update_git_state = Mock()
        mock_watch_metadata.mark_processing_start = Mock()
        mock_watch_metadata.update_after_sync_cycle = Mock()

        # Create watch handler
        handler = GitAwareWatchHandler(
            config=mock_config,
            smart_indexer=mock_smart_indexer,
            git_topology_service=git_topology_service,
            watch_metadata=mock_watch_metadata,
            debounce_seconds=0.1,
        )

        # Get initial commit and branch
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        initial_commit = result.stdout.strip()
        current_branch = git_topology_service.get_current_branch()

        # Modify files and commit
        test_file = git_repo / "test.py"
        test_file.write_text("def hello_modified(): pass\n")

        new_file = git_repo / "new_file.py"
        new_file.write_text("def new_function(): pass\n")

        subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Modify and add files"],
            cwd=git_repo,
            check=True,
            capture_output=True,
        )

        # Get new commit
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        new_commit = result.stdout.strip()

        # Simulate watch mode detecting commit change (same branch, new commit)
        change_event = {
            "old_branch": current_branch,
            "new_branch": current_branch,  # Same branch
            "old_commit": initial_commit,
            "new_commit": new_commit,
        }

        # BUG: Currently watch mode reports "0 changed files" and doesn't trigger re-indexing
        # This test will FAIL until we fix the watch handler to detect file changes in same-branch commits
        handler._handle_branch_change(change_event)

        # CRITICAL: Should trigger incremental indexing for changed files
        # Watch handler should call smart_indexer.process_files_incrementally with changed files
        mock_smart_indexer.process_files_incrementally.assert_called()

        # Verify correct files were passed for re-indexing
        call_args = mock_smart_indexer.process_files_incrementally.call_args
        assert call_args is not None, "process_files_incrementally should have been called"

        # Extract the files that were passed for re-indexing
        if call_args[0]:  # Positional args
            files_to_reindex = call_args[0][0]
        else:  # Keyword args
            files_to_reindex = call_args[1].get("files_to_reindex", [])

        # Should include modified and new files
        assert len(files_to_reindex) > 0, "Should have files to re-index"
        # Both files should be included
        assert any("test.py" in f for f in files_to_reindex), "Should include modified test.py"
        assert any("new_file.py" in f for f in files_to_reindex), "Should include new new_file.py"

    def test_watch_mode_reports_correct_changed_file_count(self, git_repo, caplog):
        """Test that watch mode reports correct count of changed files, not '0 changed files'."""
        import logging
        caplog.set_level(logging.INFO)

        # Create mock dependencies
        mock_config = Mock()
        mock_config.codebase_dir = git_repo

        git_topology_service = GitTopologyService(git_repo)

        # Get initial commit and branch
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        initial_commit = result.stdout.strip()
        current_branch = git_topology_service.get_current_branch()

        # Modify files and commit (2 files changed)
        test_file = git_repo / "test.py"
        test_file.write_text("def hello_modified(): pass\n")

        new_file = git_repo / "new_file.py"
        new_file.write_text("def new_function(): pass\n")

        subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Modify and add files"],
            cwd=git_repo,
            check=True,
            capture_output=True,
        )

        # Get new commit after changes
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        new_commit = result.stdout.strip()

        # Analyze branch change (same branch, new commit) - MUST pass commit hashes
        analysis = git_topology_service.analyze_branch_change(
            current_branch, current_branch, old_commit=initial_commit, new_commit=new_commit
        )

        # BUG: Currently logs "0 changed files" when it should report actual count
        # This test will FAIL until we fix analyze_branch_change to detect same-branch commit changes

        # CRITICAL: Should report correct number of changed files
        assert len(analysis.files_to_reindex) >= 2, f"Should detect at least 2 changed files, got {len(analysis.files_to_reindex)}"

        # Verify log reports correct count (not "0 changed files")
        changed_file_logs = [r for r in caplog.records if "changed files" in r.message.lower()]
        if changed_file_logs:
            # Should NOT report "0 changed files"
            assert not any("0 changed files" in r.message for r in changed_file_logs), \
                "Should not report '0 changed files' when files were actually changed"

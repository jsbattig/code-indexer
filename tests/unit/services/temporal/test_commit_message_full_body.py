"""Test that full multi-paragraph commit messages are stored correctly.

This test verifies Bug Fix: Commit message vectorization must capture full message body,
not just first line (subject).

CRITICAL: This is about storage format, not display. The temporal indexer MUST:
1. Use %B (full body) in git log format
2. Parse correctly with null-byte delimiters
3. Store FULL multi-paragraph message in vector chunk_text
4. Support searching across all paragraphs of commit messages
"""

import tempfile
from pathlib import Path
import subprocess

from code_indexer.config import ConfigManager
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from code_indexer.services.temporal.temporal_indexer import TemporalIndexer


def test_commit_message_parsing_captures_full_body():
    """Test that _get_commit_history() captures full multi-paragraph commit messages.

    BUG: Mismatch between git format delimiter (%x00 null byte) and parsing (pipe |)
    FIX: Must use matching delimiter for parsing

    This test directly tests the _get_commit_history() method.
    """
    # Create temporary repo
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path, check=True, capture_output=True
        )

        # Create file and make commit with multi-paragraph message
        test_file = repo_path / "test.py"
        test_file.write_text("print('hello')\n")

        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)

        # Multi-paragraph commit message with pipe character (would break old parsing)
        commit_message = """feat: implement watch mode | add real-time indexing

This commit adds comprehensive watch mode functionality that monitors
file system changes and automatically re-indexes modified files.

Technical Details:
- Uses watchdog library for cross-platform file monitoring
- Implements debouncing to avoid redundant indexing | prevents thrashing
- Supports both semantic and FTS index updates
- Thread-safe queue-based architecture

Architecture Changes:
- Added WatchService class in daemon module
- Integrated with existing daemon for seamless operation
- Proper resource cleanup on shutdown

This is critical functionality for development workflows."""

        # Create commit with subprocess to preserve exact message
        subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=repo_path, check=True, capture_output=True,
            env={
                **subprocess.os.environ,
                "GIT_AUTHOR_NAME": "Test User",
                "GIT_AUTHOR_EMAIL": "test@example.com",
                "GIT_COMMITTER_NAME": "Test User",
                "GIT_COMMITTER_EMAIL": "test@example.com",
            },
        )

        # Initialize config and indexer just to test parsing
        config_manager = ConfigManager.create_with_backtrack(repo_path)
        temporal_dir = repo_path / ".code-indexer" / "index"
        temporal_dir.mkdir(parents=True, exist_ok=True)

        vector_store = FilesystemVectorStore(
            base_path=temporal_dir,
            project_root=repo_path
        )
        indexer = TemporalIndexer(config_manager, vector_store)

        # Get commit history - this will invoke _get_commit_history()
        commits = indexer._get_commit_history(
            all_branches=False,
            max_commits=None,
            since_date=None
        )

        # Should have exactly one commit
        assert len(commits) == 1, f"Expected 1 commit, got {len(commits)}"

        commit = commits[0]

        # CRITICAL VERIFICATION: Check that full message was captured
        # The message field should contain FULL body, not just subject line
        assert "feat: implement watch mode | add real-time indexing" in commit.message, \
            f"Subject line not found in commit message. Got: {commit.message[:100]}"

        # Verify multi-paragraph content is preserved
        assert "Technical Details:" in commit.message, \
            f"Multi-paragraph message not preserved. Got: {commit.message[:200]}"

        assert "Architecture Changes:" in commit.message, \
            f"Multi-paragraph message not preserved. Got: {commit.message[:200]}"

        # Verify pipe character in message didn't break parsing
        assert "prevents thrashing" in commit.message, \
            f"Content after pipe character was truncated. Got: {commit.message[:200]}"

        # Verify it's not truncated to first line
        first_line = "feat: implement watch mode | add real-time indexing"
        assert len(commit.message) > len(first_line) * 2, \
            f"Message appears truncated to first line only ({len(commit.message)} chars)"

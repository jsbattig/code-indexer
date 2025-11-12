"""
Focused unit tests for BUG #1: Commit hash not stripped.

This is a surgical test targeting ONLY the parsing logic in _get_commit_history
to verify that commit hashes are properly stripped of leading/trailing whitespace.

BUG #1 (Critical): Commit hash not stripped in temporal_indexer.py line 438
- Location: src/code_indexer/services/temporal/temporal_indexer.py:438
- Issue: hash=parts[0] should be hash=parts[0].strip()
- Impact: All commit hashes stored with leading newline, breaking progressive metadata
"""

import subprocess
from unittest.mock import Mock, patch

import pytest

from code_indexer.config import ConfigManager
from code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestCommitHashStrippingBug:
    """Test that commit hashes from git log are properly stripped (BUG #1)."""

    def test_commit_hash_should_be_stripped_in_get_commit_history(self, tmp_path):
        """
        Test that _get_commit_history strips leading/trailing whitespace from commit hashes.

        BUG #1: Line 438 has `hash=parts[0]` but should be `hash=parts[0].strip()`

        The git log format string in line 398 uses:
        %H%x00%at%x00%an%x00%ae%x00%B%x00%P%x1e

        Where:
        - %H = commit hash
        - %x00 = null byte delimiter
        - %at = author timestamp
        - ... etc
        - %x1e = record separator

        Git output can have newlines before/after the hash depending on git version
        and format handling, so we MUST strip() to ensure clean data.
        """
        # ARRANGE: Create real git repo to test actual git log output
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

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

        # Create a commit
        test_file = repo_path / "test.txt"
        test_file.write_text("test content")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Test commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Set up mock dependencies
        config_manager = Mock(spec=ConfigManager)
        config = Mock()
        config.voyage_ai = Mock()
        config_manager.get_config.return_value = config

        vector_store = Mock(spec=FilesystemVectorStore)
        vector_store.project_root = repo_path
        vector_store.base_path = repo_path / ".code-indexer" / "index"
        vector_store.base_path.mkdir(parents=True, exist_ok=True)
        vector_store.collection_exists.return_value = False

        # Mock embedding factory
        with patch(
            "code_indexer.services.embedding_factory.EmbeddingProviderFactory"
        ) as factory_mock:
            factory_mock.get_provider_model_info.return_value = {"dimensions": 1024}

            indexer = TemporalIndexer(
                config_manager=config_manager,
                vector_store=vector_store,
            )

            # ACT: Get commit history (this calls _get_commit_history internally)
            commits = indexer._get_commit_history(
                all_branches=False, max_commits=None, since_date=None
            )

        # ASSERT: Commit hash must be clean (no leading/trailing whitespace)
        assert len(commits) > 0, "Should have at least one commit"

        commit_hash = commits[0].hash

        # CRITICAL: These assertions will FAIL with the current buggy code
        assert not commit_hash.startswith("\n"), (
            f"BUG #1: Commit hash starts with newline: {repr(commit_hash)}"
        )
        assert not commit_hash.endswith("\n"), (
            f"BUG #1: Commit hash ends with newline: {repr(commit_hash)}"
        )
        assert not commit_hash.startswith(" "), (
            f"BUG #1: Commit hash starts with space: {repr(commit_hash)}"
        )
        assert not commit_hash.endswith(" "), (
            f"BUG #1: Commit hash ends with space: {repr(commit_hash)}"
        )

        # Verify it's a valid 40-character SHA-1 hash
        assert len(commit_hash) == 40, (
            f"Commit hash should be 40 chars, got {len(commit_hash)}: {repr(commit_hash)}"
        )
        assert all(c in "0123456789abcdef" for c in commit_hash), (
            f"Commit hash should be hex only: {repr(commit_hash)}"
        )

    def test_parent_hashes_should_also_be_stripped(self, tmp_path):
        """
        Test that parent hashes are also stripped (line 443 already has .strip()).

        This is a consistency check - parent hashes at line 443 DO have .strip(),
        but commit hash at line 438 does NOT. Both should be stripped.
        """
        # ARRANGE: Create git repo with 2 commits (so second has parent)
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

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

        # First commit
        test_file = repo_path / "test.txt"
        test_file.write_text("first")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "First"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Second commit (will have parent)
        test_file.write_text("second")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Second"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Set up mocks
        config_manager = Mock(spec=ConfigManager)
        config = Mock()
        config.voyage_ai = Mock()
        config_manager.get_config.return_value = config

        vector_store = Mock(spec=FilesystemVectorStore)
        vector_store.project_root = repo_path
        vector_store.base_path = repo_path / ".code-indexer" / "index"
        vector_store.base_path.mkdir(parents=True, exist_ok=True)
        vector_store.collection_exists.return_value = False

        with patch(
            "code_indexer.services.embedding_factory.EmbeddingProviderFactory"
        ) as factory_mock:
            factory_mock.get_provider_model_info.return_value = {"dimensions": 1024}

            indexer = TemporalIndexer(
                config_manager=config_manager,
                vector_store=vector_store,
            )

            commits = indexer._get_commit_history(
                all_branches=False, max_commits=None, since_date=None
            )

        # ASSERT: Second commit's parent hash should be clean
        assert len(commits) >= 2, "Should have at least 2 commits"
        second_commit = commits[1]

        # Parent hashes (line 443 already has .strip(), so this should pass)
        if second_commit.parent_hashes:
            assert not second_commit.parent_hashes.startswith("\n"), (
                f"Parent hash starts with newline: {repr(second_commit.parent_hashes)}"
            )
            assert not second_commit.parent_hashes.endswith("\n"), (
                f"Parent hash ends with newline: {repr(second_commit.parent_hashes)}"
            )

        # BUT the commit hash itself should ALSO be clean (BUG #1)
        assert not second_commit.hash.startswith("\n"), (
            f"BUG #1: Commit hash starts with newline: {repr(second_commit.hash)}"
        )
        assert not second_commit.hash.endswith("\n"), (
            f"BUG #1: Commit hash ends with newline: {repr(second_commit.hash)}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

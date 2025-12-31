"""
Unit tests for Issue #500: CoW clone must copy .code-indexer/ directory.

Tests verify that repository activation properly clones .code-indexer/ directory
including all indexes, ensuring search works without manual indexing.
"""

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from datetime import datetime, timezone

import pytest

from src.code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
)
from src.code_indexer.server.repositories.golden_repo_manager import GoldenRepo


@pytest.mark.e2e
class TestCowCloneIssue500:
    """Unit tests for CoW clone .code-indexer/ copying (Issue #500)."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def golden_repo_with_indexes(self, temp_data_dir):
        """Create a real git repository with .code-indexer/ and indexes."""
        golden_path = Path(temp_data_dir) / "golden" / "test-repo"
        golden_path.mkdir(parents=True, exist_ok=True)

        # Initialize git repo
        subprocess.run(
            ["git", "init"], cwd=golden_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=golden_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=golden_path,
            check=True,
            capture_output=True,
        )

        # Create Python files with searchable content
        (golden_path / "auth.py").write_text(
            """
def authenticate_user(username, password):
    '''Authenticate user with credentials'''
    pass
"""
        )

        # Commit files
        subprocess.run(
            ["git", "add", "."], cwd=golden_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add code files"],
            cwd=golden_path,
            check=True,
            capture_output=True,
        )

        # Create .code-indexer/ directory with config and mock indexes
        code_indexer_dir = golden_path / ".code-indexer"
        code_indexer_dir.mkdir(parents=True, exist_ok=True)

        # Create config.json
        config_data = {
            "vector_store": {"provider": "filesystem"},
            "embedding_provider": "voyage-ai",
            "voyage_ai": {"model": "voyage-code-3"},
        }
        (code_indexer_dir / "config.json").write_text(json.dumps(config_data, indent=2))

        # Create mock index directory structure
        index_dir = code_indexer_dir / "index" / "default"
        index_dir.mkdir(parents=True, exist_ok=True)

        # Create mock vector files (simulating real indexes)
        (index_dir / "vectors_000.json").write_text(
            json.dumps(
                {
                    "vectors": [
                        {
                            "id": "auth.py:1",
                            "vector": [0.1] * 1024,
                            "metadata": {"file": "auth.py"},
                        },
                    ]
                },
                indent=2,
            )
        )

        # Create metadata file
        metadata = {
            "indexed_files": ["auth.py"],
            "total_chunks": 1,
            "last_indexed": datetime.now(timezone.utc).isoformat(),
        }
        (code_indexer_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

        return golden_path

    @pytest.fixture
    def golden_repo_manager_mock(self, golden_repo_with_indexes):
        """Mock golden repo manager with real git repo."""
        mock = MagicMock()

        golden_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/example/test-repo.git",
            default_branch="master",
            clone_path=str(golden_repo_with_indexes),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        mock.golden_repos = {"test-repo": golden_repo}
        # Mock get_actual_repo_path() to return the real path (for canonical path resolution)
        mock.get_actual_repo_path = MagicMock(
            return_value=str(golden_repo_with_indexes)
        )
        return mock

    @pytest.fixture
    def background_job_manager_mock(self):
        """Mock background job manager."""
        mock = MagicMock()
        mock.submit_job.return_value = "job-123"
        return mock

    @pytest.fixture
    def activated_repo_manager(
        self, temp_data_dir, golden_repo_manager_mock, background_job_manager_mock
    ):
        """Create ActivatedRepoManager instance with temp directory."""
        return ActivatedRepoManager(
            data_dir=temp_data_dir,
            golden_repo_manager=golden_repo_manager_mock,
            background_job_manager=background_job_manager_mock,
        )

    def test_cow_clone_copies_code_indexer_directory(
        self, activated_repo_manager, temp_data_dir
    ):
        """
        CRITICAL TEST: Verify CoW clone copies .code-indexer/ directory.

        This test MUST FAIL with current implementation because git clone --local
        does NOT copy gitignored .code-indexer/ directory.

        Expected to PASS after implementing proper CoW clone (cp --reflink=auto).
        """
        username = "testuser"
        golden_repo_alias = "test-repo"
        user_alias = "my-repo"

        # Execute activation
        result = activated_repo_manager._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        # Verify activation succeeded
        assert result["success"] is True

        # Get activated repo path
        activated_repo_path = (
            Path(temp_data_dir) / "activated-repos" / username / user_alias
        )

        # CRITICAL ASSERTION: .code-indexer/ directory MUST exist
        code_indexer_dir = activated_repo_path / ".code-indexer"
        assert code_indexer_dir.exists(), (
            "FAILURE: .code-indexer/ directory NOT copied by CoW clone! "
            "git clone --local skips gitignored directories. "
            "Must use cp --reflink=auto -r instead."
        )

        # Verify config.json exists
        config_file = code_indexer_dir / "config.json"
        assert (
            config_file.exists()
        ), ".code-indexer/config.json must exist (copied from golden repo)"

    def test_cow_clone_copies_indexes(self, activated_repo_manager, temp_data_dir):
        """
        CRITICAL TEST: Verify CoW clone copies index files.

        This test MUST FAIL with current implementation because git clone --local
        does NOT copy .code-indexer/index/ directory.

        Expected to PASS after implementing proper CoW clone.
        """
        username = "testuser"
        golden_repo_alias = "test-repo"
        user_alias = "my-repo"

        # Execute activation
        result = activated_repo_manager._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        assert result["success"] is True

        # Get activated repo path
        activated_repo_path = (
            Path(temp_data_dir) / "activated-repos" / username / user_alias
        )

        # CRITICAL ASSERTION: index directory MUST exist with vector files
        index_dir = activated_repo_path / ".code-indexer" / "index" / "default"
        assert index_dir.exists(), (
            "FAILURE: .code-indexer/index/ directory NOT copied! "
            "Search will return 0 results without indexes."
        )

        # Verify vector files exist
        vector_file = index_dir / "vectors_000.json"
        assert vector_file.exists(), (
            "FAILURE: Vector index files NOT copied! "
            "Activated repo has config but NO indexes - Issue #500 root cause."
        )

        # Verify metadata.json exists
        metadata_file = activated_repo_path / ".code-indexer" / "metadata.json"
        assert metadata_file.exists(), "metadata.json must be copied from golden repo"

    def test_git_operations_clean_status_after_cow_clone(
        self, activated_repo_manager, temp_data_dir
    ):
        """
        TEST: Verify git operations clean up CoW clone status.

        After CoW clone, git status shows all files as modified due to timestamp
        changes. git update-index --refresh + git restore . must clean this up.

        Note: .code-indexer/ showing as untracked (??) is expected and acceptable
        because it's gitignored. We only care that tracked files are NOT modified.

        This test will FAIL until git operations are added after CoW clone.
        """
        username = "testuser"
        golden_repo_alias = "test-repo"
        user_alias = "my-repo"

        # Execute activation
        result = activated_repo_manager._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        assert result["success"] is True

        # Get activated repo path
        activated_repo_path = (
            Path(temp_data_dir) / "activated-repos" / username / user_alias
        )

        # Run git status to check for modified files
        git_status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=activated_repo_path,
            capture_output=True,
            text=True,
            check=True,
        )

        # Parse git status output
        status_lines = [
            line.strip()
            for line in git_status.stdout.strip().split("\n")
            if line.strip()
        ]

        # Filter out .code-indexer/ (it's gitignored, so ?? is expected)
        modified_files = [
            line
            for line in status_lines
            if not line.endswith(".code-indexer/") and line.strip()
        ]

        # CRITICAL ASSERTION: No tracked files should be modified
        assert len(modified_files) == 0, (
            "FAILURE: git status shows modified tracked files after CoW clone!\n"
            "Modified files:\n" + "\n".join(modified_files) + "\n"
            "Must run 'git update-index --refresh' and 'git restore .' after CoW clone.\n"
            "Note: .code-indexer/ being untracked is OK (it's gitignored)."
        )

    def test_cidx_fix_config_updates_paths(self, activated_repo_manager, temp_data_dir):
        """
        TEST: Verify cidx fix-config updates cloned config paths.

        CoW cloned config.json contains paths from golden repo. cidx fix-config --force
        must update these paths to point to activated repo location.

        This test will FAIL until cidx fix-config is called after CoW clone.
        """
        username = "testuser"
        golden_repo_alias = "test-repo"
        user_alias = "my-repo"

        # Execute activation
        result = activated_repo_manager._do_activate_repository(
            username=username,
            golden_repo_alias=golden_repo_alias,
            branch_name="master",
            user_alias=user_alias,
        )

        assert result["success"] is True

        # Get activated repo path
        activated_repo_path = (
            Path(temp_data_dir) / "activated-repos" / username / user_alias
        )

        # Load config.json
        config_file = activated_repo_path / ".code-indexer" / "config.json"
        assert config_file.exists(), "config.json must exist"

        with open(config_file, "r") as f:
            config_data = json.load(f)

        # Verify codebase_dir points to activated repo (not golden repo)
        if "codebase_dir" in config_data:
            codebase_dir = Path(config_data["codebase_dir"])
            # Config paths should be absolute and point to activated repo
            assert str(activated_repo_path) in str(codebase_dir), (
                f"FAILURE: config.json paths NOT updated by cidx fix-config!\n"
                f"codebase_dir: {codebase_dir}\n"
                f"Expected to contain: {activated_repo_path}\n"
                f"Must call 'cidx fix-config --force' after CoW clone."
            )

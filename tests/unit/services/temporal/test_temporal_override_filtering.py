"""Test temporal indexing respects override filtering rules.

CRITICAL BUG: Temporal indexing currently processes ALL files in git history
without applying override filtering. This causes:
1. Processing of excluded directories (like help/) in git history
2. Performance issues with large excluded files
3. Violation of user's explicit exclusion configuration

This test verifies the fix that integrates OverrideFilterService into TemporalDiffScanner.
"""

import subprocess
from pathlib import Path

import pytest

from code_indexer.config import OverrideConfig
from code_indexer.services.temporal.temporal_diff_scanner import TemporalDiffScanner
from code_indexer.services.override_filter_service import OverrideFilterService


@pytest.fixture
def git_repo_with_excluded_dir(tmp_path):
    """Create a git repo with files in excluded and included directories."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    # Create files in help/ directory (should be excluded)
    help_dir = repo_dir / "help"
    help_dir.mkdir()
    (help_dir / "large_help.html").write_text("<html>" + "x" * 44000 + "</html>")
    (help_dir / "README.md").write_text("# Help documentation")

    # Create files in src/ directory (should be included)
    src_dir = repo_dir / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("def main():\n    print('hello')")
    (src_dir / "utils.py").write_text("def helper():\n    return 42")

    # Commit all files
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit with all files"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    # Get commit hash
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    commit_hash = result.stdout.strip()

    return {
        "repo_dir": repo_dir,
        "commit_hash": commit_hash,
    }


def test_temporal_diff_scanner_respects_add_exclude_dirs(git_repo_with_excluded_dir):
    """Test temporal diff scanner respects add_exclude_dirs from override config.

    CRITICAL BUG FIX: Files in directories listed in add_exclude_dirs should NOT
    appear in diffs returned by TemporalDiffScanner.

    This test will FAIL initially (demonstrating the bug) because TemporalDiffScanner
    currently does not integrate with OverrideFilterService.

    After fix, files in 'help/' directory will be filtered out.
    """
    repo_info = git_repo_with_excluded_dir

    # Create override config that excludes 'help' directory
    override_config = OverrideConfig(
        add_exclude_dirs=["help"],
        force_exclude_patterns=[],
        force_include_patterns=[],
        add_extensions=[],
        remove_extensions=[],
        add_include_dirs=[],
    )

    # Create OverrideFilterService
    override_service = OverrideFilterService(override_config)

    # Create diff scanner WITH override filtering (FIXED behavior)
    scanner = TemporalDiffScanner(
        repo_info["repo_dir"],
        override_filter_service=override_service,
    )

    # Get diffs for commit
    diffs = scanner.get_diffs_for_commit(repo_info["commit_hash"])

    # Extract file paths from diffs
    diff_files = {diff.file_path for diff in diffs}

    # ASSERTION: Excluded files should NOT appear in diffs
    assert "help/large_help.html" not in diff_files, "help/ files should be excluded by add_exclude_dirs"
    assert "help/README.md" not in diff_files, "help/ files should be excluded by add_exclude_dirs"

    # Included files SHOULD appear
    assert "src/main.py" in diff_files, "src/ files should be included"
    assert "src/utils.py" in diff_files, "src/ files should be included"


def test_temporal_indexer_respects_override_config(git_repo_with_excluded_dir):
    """Test that TemporalIndexer uses override config when indexing commits.

    This test verifies the complete integration: TemporalIndexer should create
    TemporalDiffScanner with OverrideFilterService based on override_config.

    Files in excluded directories should not be indexed at all.
    """
    import tempfile
    from code_indexer.config import Config, IndexingConfig, VoyageAIConfig
    from code_indexer.services.temporal.temporal_indexer import TemporalIndexer
    from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

    repo_info = git_repo_with_excluded_dir

    # Create a temporary index directory
    with tempfile.TemporaryDirectory() as index_dir:
        index_path = Path(index_dir)

        # Create override config that excludes 'help' directory
        override_config = OverrideConfig(
            add_exclude_dirs=["help"],
            force_exclude_patterns=[],
            force_include_patterns=[],
            add_extensions=[],
            remove_extensions=[],
            add_include_dirs=[],
        )

        # Create config with override config
        config = Config(
            codebase_dir=repo_info["repo_dir"],
            file_extensions=["py", "md", "html", "txt"],
            exclude_dirs=[],
            indexing=IndexingConfig(),
            voyage_ai=VoyageAIConfig(),
            override_config=override_config,
        )

        # Create ConfigManager mock
        class ConfigManagerMock:
            def __init__(self, config):
                self._config = config

            def get_config(self):
                return self._config

        config_manager = ConfigManagerMock(config)

        # Create vector store
        vector_store = FilesystemVectorStore(
            base_path=index_path,
            project_root=repo_info["repo_dir"],
        )

        # Create TemporalIndexer
        indexer = TemporalIndexer(config_manager, vector_store)

        # Index commits (this will fail if override service not integrated)
        # We're only checking that the diff scanner filters correctly
        diffs = indexer.diff_scanner.get_diffs_for_commit(repo_info["commit_hash"])

        # Extract file paths
        diff_files = {diff.file_path for diff in diffs}

        # Verify excluded files are NOT in diffs
        assert "help/large_help.html" not in diff_files, "help/ files should be excluded via TemporalIndexer integration"
        assert "help/README.md" not in diff_files, "help/ files should be excluded via TemporalIndexer integration"

        # Verify included files ARE in diffs
        assert "src/main.py" in diff_files, "src/ files should be included"
        assert "src/utils.py" in diff_files, "src/ files should be included"

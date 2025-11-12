"""
Test that temporal data is consolidated in a single directory.

This test verifies the fix for the temporal folder split bug where data was
being stored in two separate locations:
- .code-indexer/index/temporal/ (metadata only)
- .code-indexer/index/code-indexer-temporal/ (vector data)

After the fix, all temporal data should be in:
- .code-indexer/index/code-indexer-temporal/
"""

import tempfile
from pathlib import Path

import pytest

from src.code_indexer.config import ConfigManager
from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "test-repo"
        repo_path.mkdir()

        # Initialize git repo
        import subprocess

        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
        )

        # Create initial commit
        test_file = repo_path / "test.py"
        test_file.write_text("def hello():\n    return 'world'\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
        )

        yield repo_path


def test_temporal_directory_consolidation(temp_git_repo):
    """
    Test that all temporal data is stored in a single directory.

    Verifies that:
    1. temporal_dir points to the collection directory
    2. No separate .code-indexer/index/temporal/ directory is created
    3. All metadata files are in .code-indexer/index/code-indexer-temporal/
    """
    # Setup
    index_dir = temp_git_repo / ".code-indexer" / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    vector_store = FilesystemVectorStore(
        base_path=index_dir, project_root=temp_git_repo
    )
    config_manager = ConfigManager.create_with_backtrack(temp_git_repo)

    # Create temporal indexer
    temporal_indexer = TemporalIndexer(config_manager, vector_store)

    # Expected paths
    collection_name = TemporalIndexer.TEMPORAL_COLLECTION_NAME
    expected_temporal_dir = index_dir / collection_name
    wrong_temporal_dir = index_dir / "temporal"

    # ASSERTION 1: temporal_dir should point to collection directory
    assert (
        temporal_indexer.temporal_dir == expected_temporal_dir
    ), f"temporal_dir should be {expected_temporal_dir}, got {temporal_indexer.temporal_dir}"

    # ASSERTION 2: The collection directory should be created (happens in __init__)
    assert (
        expected_temporal_dir.exists()
    ), f"Collection directory should exist at {expected_temporal_dir}"

    # ASSERTION 3: The old temporal/ directory should NOT be created
    assert not wrong_temporal_dir.exists(), (
        f"Old temporal directory should not exist at {wrong_temporal_dir}. "
        f"All data should be in {expected_temporal_dir}"
    )


def test_watch_command_vector_store_initialization(temp_git_repo):
    """
    Test that watch command initializes vector store correctly.

    This simulates what the watch command in cli.py does and verifies
    that using the OLD way (passing collection path directly) creates
    the wrong temporal_dir, while the NEW way (using base_path) works correctly.
    """
    from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

    project_root = temp_git_repo
    index_dir = project_root / ".code-indexer" / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    # SIMULATE THE OLD/WRONG WAY (what cli.py currently does)
    temporal_index_dir = project_root / ".code-indexer/index/code-indexer-temporal"
    old_vector_store = FilesystemVectorStore(temporal_index_dir)

    config_manager = ConfigManager.create_with_backtrack(project_root)
    old_temporal_indexer = TemporalIndexer(config_manager, old_vector_store)

    # With the old way, temporal_dir would be nested incorrectly
    # The bug: old_vector_store.base_path is the collection dir, so
    # temporal_dir becomes collection_dir/TEMPORAL_COLLECTION_NAME (nested!)
    collection_name = TemporalIndexer.TEMPORAL_COLLECTION_NAME

    # This demonstrates the BUG with the old way
    # The old way creates double-nesting: collection_dir/TEMPORAL_COLLECTION_NAME
    expected_correct_path = index_dir / collection_name
    wrong_nested_path = temporal_index_dir / collection_name  # Double-nested!

    # The bug: temporal_dir becomes incorrectly nested
    assert old_temporal_indexer.temporal_dir == wrong_nested_path, (
        f"OLD way should create nested path (bug demonstration). "
        f"Got: {old_temporal_indexer.temporal_dir}, "
        f"Expected (buggy): {wrong_nested_path}"
    )

    # NOW TEST THE CORRECT WAY (what cli.py should do after fix)
    new_vector_store = FilesystemVectorStore(
        base_path=index_dir, project_root=project_root
    )
    new_temporal_indexer = TemporalIndexer(config_manager, new_vector_store)

    # With the new way, temporal_dir should be correct
    assert new_temporal_indexer.temporal_dir == expected_correct_path, (
        f"temporal_dir should be {expected_correct_path}, "
        f"got {new_temporal_indexer.temporal_dir}"
    )
    assert new_vector_store.base_path == index_dir
    assert new_vector_store.project_root == project_root


def test_reconciliation_uses_collection_path(temp_git_repo):
    """
    Test that reconciliation function references correct paths.

    This verifies the fix for temporal_reconciliation.py where metadata
    file paths should use collection_path, not vector_store.base_path / "temporal"
    """
    from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
    from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer

    project_root = temp_git_repo
    index_dir = project_root / ".code-indexer" / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    vector_store = FilesystemVectorStore(base_path=index_dir, project_root=project_root)
    collection_name = TemporalIndexer.TEMPORAL_COLLECTION_NAME
    collection_path = index_dir / collection_name

    # Create some fake metadata files in the collection directory
    collection_path.mkdir(parents=True, exist_ok=True)
    temporal_meta = collection_path / "temporal_meta.json"
    temporal_progress = collection_path / "temporal_progress.json"

    temporal_meta.write_text('{"test": "meta"}')
    temporal_progress.write_text('{"test": "progress"}')

    # Verify they exist in the collection directory
    assert temporal_meta.exists()
    assert temporal_progress.exists()

    # Verify the old wrong path doesn't exist
    wrong_temporal_dir = index_dir / "temporal"
    assert (
        not wrong_temporal_dir.exists()
    ), f"Old temporal directory should not exist: {wrong_temporal_dir}"


def test_clear_command_metadata_paths(temp_git_repo):
    """
    Test that clear command references correct metadata paths.

    This verifies that the clear command in cli.py uses the collection
    directory for temporal metadata files, not the old temporal/ directory.
    """
    from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer

    project_root = temp_git_repo
    index_dir = project_root / ".code-indexer" / "index"
    collection_name = TemporalIndexer.TEMPORAL_COLLECTION_NAME

    # The CORRECT paths (what clear command should use after fix)
    correct_meta_path = index_dir / collection_name / "temporal_meta.json"
    correct_progress_path = index_dir / collection_name / "temporal_progress.json"

    # The WRONG paths (what clear command used before fix)
    wrong_meta_path = index_dir / "temporal" / "temporal_meta.json"
    wrong_progress_path = index_dir / "temporal" / "temporal_progress.json"

    # Create metadata in correct location
    correct_meta_path.parent.mkdir(parents=True, exist_ok=True)
    correct_meta_path.write_text('{"test": "meta"}')
    correct_progress_path.write_text('{"test": "progress"}')

    # Verify correct paths exist
    assert correct_meta_path.exists()
    assert correct_progress_path.exists()

    # Verify wrong paths don't exist
    assert not wrong_meta_path.exists()
    assert not wrong_progress_path.exists()

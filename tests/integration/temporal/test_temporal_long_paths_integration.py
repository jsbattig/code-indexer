"""Integration tests for temporal indexing with long file paths (Story #669).

Tests end-to-end indexing of repositories with deeply nested file paths that
would exceed 255-character filename limits in v1 format.
"""

import subprocess
import pytest

from src.code_indexer.config import ConfigManager
from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from src.code_indexer.storage.temporal_metadata_store import TemporalMetadataStore

# Constants for test validation
V2_VECTOR_FILENAME_LENGTH = 28  # "vector_" (7) + 16 char hash + ".json" (5) = 28
MIN_LONG_PATH_CHARS = 200  # Minimum path length to test v2 format necessity
EXTREMELY_LONG_PATH_CHARS = 250  # Extremely long path for stress testing
NESTING_LEVELS_FOR_LONG_PATH = 10  # Creates path > 200 chars
NESTING_LEVELS_FOR_EXTREME_PATH = 30  # Creates path > 250 chars
FILENAME_REPEAT_COUNT = 5  # Repeats base string to create sufficiently long filename


@pytest.fixture
def git_repo(tmp_path):
    """Create initialized git repository."""
    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()

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

    return repo_dir


@pytest.fixture
def temporal_indexer(git_repo):
    """Create temporal indexer with config and vector store."""
    index_dir = git_repo / ".code-indexer" / "index"
    index_dir.mkdir(parents=True)

    config_path = git_repo / ".code-indexer" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text('{"voyage_ai": {"api_key": "test-key", "model": "voyage-3"}}')

    config_manager = ConfigManager(config_path=config_path)
    vector_store = FilesystemVectorStore(base_path=index_dir, project_root=git_repo)

    indexer = TemporalIndexer(config_manager, vector_store)

    return indexer, index_dir, git_repo


def commit_file(repo_dir, file_path, content, message):
    """Helper to write, add and commit a file."""
    file_path.write_text(content)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )


class TestTemporalLongPathsIntegration:
    """Integration tests for temporal indexing with long file paths."""

    def test_index_repository_with_long_file_paths(self, git_repo, temporal_indexer):
        """AC1: Index repository with files having paths longer than 200 characters."""
        indexer, index_dir, _ = temporal_indexer

        # Create deeply nested directory with long path
        nested_path = git_repo / "src" / "deeply" / "nested" / "directory" / "structure"
        for i in range(NESTING_LEVELS_FOR_LONG_PATH):
            nested_path = nested_path / f"level{i}"
        nested_path.mkdir(parents=True)

        long_filename = "VeryLongFileNameForTesting" * FILENAME_REPEAT_COUNT + ".py"
        test_file = nested_path / long_filename

        # Verify path length exceeds minimum threshold
        full_path_relative = test_file.relative_to(git_repo)
        assert len(str(full_path_relative)) > MIN_LONG_PATH_CHARS

        # Commit file
        commit_file(git_repo, test_file, "def test_function():\n    pass\n", "Add file with long path")

        # Index commits (should NOT raise OSError)
        try:
            result = indexer.index_commits()
        except OSError as e:
            if "File name too long" in str(e):
                pytest.fail(f"OSError raised for long filename (v1 format bug): {e}")
            raise

        # Verify success
        assert result.total_commits > 0

        # Verify all filenames use v2 format
        temporal_collection_path = index_dir / "code-indexer-temporal"
        vector_files = list(temporal_collection_path.rglob("vector_*.json"))

        assert len(vector_files) > 0
        for vector_file in vector_files:
            assert len(vector_file.name) == V2_VECTOR_FILENAME_LENGTH

        # Verify metadata database exists (v2 format indicator)
        metadata_db_path = temporal_collection_path / "temporal_metadata.db"
        assert metadata_db_path.exists()

        # Verify metadata contains entries
        metadata_store = TemporalMetadataStore(temporal_collection_path)
        assert metadata_store.count_entries() > 0

    def test_extremely_long_path_no_oserror(self, git_repo, temporal_indexer):
        """AC1: Even extremely long paths (250+ chars) should not cause OSError."""
        indexer, index_dir, _ = temporal_indexer

        # Create path that would result in extremely long point_id in v1 format
        nested_path = git_repo
        for i in range(NESTING_LEVELS_FOR_EXTREME_PATH):
            nested_path = nested_path / f"very_long_directory_name_{i:02d}"
        nested_path.mkdir(parents=True)

        test_file = nested_path / "TestFile.py"
        full_path_relative = test_file.relative_to(git_repo)

        # Verify path is extremely long
        assert len(str(full_path_relative)) > EXTREMELY_LONG_PATH_CHARS

        # Commit file
        commit_file(git_repo, test_file, "# Test file\n", "Add extremely long path")

        # Index (should NOT raise OSError)
        result = indexer.index_commits()

        # Verify success
        assert result.total_commits > 0

        # Verify all filenames are v2 format
        temporal_collection_path = index_dir / "code-indexer-temporal"
        vector_files = list(temporal_collection_path.rglob("vector_*.json"))

        for vector_file in vector_files:
            assert len(vector_file.name) == V2_VECTOR_FILENAME_LENGTH

    def test_metadata_contains_correct_file_path_mapping(self, git_repo, temporal_indexer):
        """AC2: Metadata database correctly maps hash prefixes to point_ids with file paths."""
        indexer, index_dir, _ = temporal_indexer

        # Create test file
        test_file = git_repo / "path" / "to" / "nested" / "TestFile.py"
        test_file.parent.mkdir(parents=True)

        commit_file(git_repo, test_file, "def test():\n    pass\n", "Add test file")

        # Index
        indexer.index_commits()

        # Verify metadata contains file path information
        temporal_collection_path = index_dir / "code-indexer-temporal"
        metadata_store = TemporalMetadataStore(temporal_collection_path)

        # Get vector files and check metadata
        vector_files = list(temporal_collection_path.rglob("vector_*.json"))
        assert len(vector_files) > 0

        # Check metadata for each hash prefix
        for vector_file in vector_files:
            filename = vector_file.stem
            if filename.startswith("vector_"):
                hash_prefix = filename[len("vector_"):]
                metadata = metadata_store.get_metadata(hash_prefix)

                # Should have metadata entry with point_id and file_path
                if metadata and metadata.get("file_path"):
                    assert "point_id" in metadata
                    assert len(metadata["file_path"]) > 0

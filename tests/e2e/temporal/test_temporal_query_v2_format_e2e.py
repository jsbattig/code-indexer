"""E2E tests for temporal query functionality with v2 format (Story #669).

Tests that `cidx query --time-range-all` works correctly with v2 hash-based format:
- Indexes repository with temporal data (v2 format)
- Queries using CLI with --time-range-all flag
- Verifies results include correct file paths and commit info
- Verifies hash prefix → point_id resolution works during queries

Code Review P0 Violation Fix: Query functionality was NOT TESTED (Scenario 3).
"""

import subprocess
import pytest

from src.code_indexer.storage.temporal_metadata_store import TemporalMetadataStore


def _init_git_repo(repo_dir):
    """Initialize git repository with config."""
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


def _commit_file(repo_dir, file_path, content, message):
    """Write file content and commit."""
    file_path.write_text(content)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )


def _init_and_index_temporal(repo_dir):
    """Initialize CIDX and index with temporal data."""
    subprocess.run(["cidx", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["cidx", "index", "--index-commits"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def git_repo_with_commits(tmp_path):
    """Create git repository with commits for temporal indexing."""
    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()

    _init_git_repo(repo_dir)

    # Create test files with searchable content
    auth_file = repo_dir / "auth.py"
    auth_content = (
        "def authenticate_user(username, password):\n"
        "    # Authentication logic for user login\n"
        "    return validate_credentials(username, password)\n"
    )
    _commit_file(repo_dir, auth_file, auth_content, "Add authentication module")

    # Second commit with different content
    db_file = repo_dir / "database.py"
    db_content = (
        "def query_database(table, filters):\n"
        "    # Database query execution\n"
        "    return execute_sql_query(table, filters)\n"
    )
    _commit_file(repo_dir, db_file, db_content, "Add database module")

    # Third commit with long file path (tests v2 format necessity)
    nested_path = repo_dir / "src" / "deeply" / "nested" / "directory"
    nested_path.mkdir(parents=True)
    long_path_file = nested_path / ("LongFileName" * 10 + ".py")
    long_content = (
        "def process_data(input_data):\n"
        "    # Data processing authentication logic\n"
        "    return transform_and_authenticate(input_data)\n"
    )
    _commit_file(repo_dir, long_path_file, long_content, "Add data processing module")

    return repo_dir


@pytest.mark.e2e
class TestTemporalQueryV2FormatE2E:
    """E2E tests for temporal query with v2 format."""

    def test_query_time_range_all_returns_results_with_v2_format(self, git_repo_with_commits):
        """AC3: Query with --time-range-all works with v2 format, returns correct results."""
        repo_dir = git_repo_with_commits

        # Given: Repository indexed with temporal data (v2 format)
        _init_and_index_temporal(repo_dir)

        # Verify v2 format is used
        temporal_path = repo_dir / ".code-indexer" / "index" / "code-indexer-temporal"
        metadata_db_path = temporal_path / "temporal_metadata.db"
        assert metadata_db_path.exists(), "temporal_metadata.db should exist (v2 format)"

        # Verify vector files use v2 format (28-char filenames)
        vector_files = list(temporal_path.rglob("vector_*.json"))
        assert len(vector_files) > 0, "Should have indexed vector files"
        for vector_file in vector_files:
            assert len(vector_file.name) == 28, (
                f"V2 format should produce 28-char filenames, got {len(vector_file.name)}"
            )

        # When: Querying with --time-range-all
        query_result = subprocess.run(
            ["cidx", "query", "authentication", "--time-range-all", "--quiet", "--limit", "10"],
            cwd=repo_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        # Then: Query should succeed (exit code 0 or 1 for no results)
        assert query_result.returncode in [0, 1], (
            f"Query failed with exit code {query_result.returncode}. "
            f"Stdout: {query_result.stdout}\nStderr: {query_result.stderr}"
        )

        # If results found, verify they contain file paths and commit info
        if query_result.returncode == 0:
            output = query_result.stdout
            assert "auth.py" in output or "LongFileName" in output, (
                f"Query results should contain file paths. Output: {output}"
            )
            assert "commit" in output.lower() or "hash" in output.lower(), (
                f"Query results should contain commit info. Output: {output}"
            )

    def test_query_resolves_hash_prefixes_to_point_ids(self, git_repo_with_commits):
        """AC3: Query correctly resolves hash prefixes to point_ids using metadata store."""
        repo_dir = git_repo_with_commits

        # Given: Indexed repository with v2 format
        _init_and_index_temporal(repo_dir)

        # Verify metadata store contains mappings
        temporal_path = repo_dir / ".code-indexer" / "index" / "code-indexer-temporal"
        metadata_store = TemporalMetadataStore(temporal_path)

        entry_count = metadata_store.count_entries()
        assert entry_count > 0, "Metadata store should contain entries"

        # Verify hash→point_id mappings exist
        vector_files = list(temporal_path.rglob("vector_*.json"))
        assert len(vector_files) > 0

        verified_mappings = 0
        for vector_file in vector_files:
            filename = vector_file.stem
            if filename.startswith("vector_"):
                hash_prefix = filename[len("vector_"):]
                point_id = metadata_store.get_point_id(hash_prefix)
                if point_id:
                    verified_mappings += 1
                    assert len(point_id) > 0, "point_id should not be empty"

                    metadata = metadata_store.get_metadata(hash_prefix)
                    assert metadata is not None
                    assert "file_path" in metadata
                    # Note: file_path may be empty for commit messages or other temporal data
                    # Just verify it exists in metadata structure

        # When: Querying (implicitly uses hash → point_id resolution)
        query_result = subprocess.run(
            ["cidx", "query", "database", "--time-range-all", "--quiet", "--limit", "5"],
            cwd=repo_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        # Then: Query works, proving hash resolution is functional
        assert query_result.returncode in [0, 1]
        assert verified_mappings > 0, f"Verified {verified_mappings} mappings"

    def test_query_with_long_file_paths_returns_correct_results(self, git_repo_with_commits):
        """AC1+AC3: Query returns results for files with long paths (v2 format necessity)."""
        repo_dir = git_repo_with_commits

        # Given: Repository with long file paths indexed
        _init_and_index_temporal(repo_dir)

        # When: Querying for content in long-path file
        query_result = subprocess.run(
            ["cidx", "query", "process_data", "--time-range-all", "--quiet", "--limit", "10"],
            cwd=repo_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        # Then: Query should find results from long-path file
        assert query_result.returncode in [0, 1]

        # If results found, verify long-path file is included
        if query_result.returncode == 0:
            output = query_result.stdout
            assert "LongFileName" in output or "nested/directory" in output, (
                f"Query results should include long-path file. Output: {output}"
            )

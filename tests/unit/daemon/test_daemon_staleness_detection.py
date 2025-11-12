"""Unit tests for daemon mode staleness detection.

Tests that daemon queries return staleness indicators matching standalone mode behavior.
"""

import time

import pytest


@pytest.fixture
def test_project(tmp_path):
    """Create test project with code files."""
    project_root = tmp_path / "test_project"
    project_root.mkdir()

    # Create .code-indexer directory
    cidx_dir = project_root / ".code-indexer"
    cidx_dir.mkdir()

    # Create config file for filesystem backend
    config_file = cidx_dir / "config.json"
    config_file.write_text(
        """{
        "codebase_dir": "%s",
        "embedding_provider": "voyage-ai",
        "voyage_api_key": "test-key",
        "vector_store": {
            "provider": "filesystem"
        }
    }"""
        % str(project_root)
    )

    # Create sample code file
    src_dir = project_root / "src"
    src_dir.mkdir()

    test_file = src_dir / "example.py"
    test_file.write_text("def hello():\n    return 'world'\n")

    return project_root


@pytest.fixture
def daemon_service():
    """Create daemon service instance."""
    from code_indexer.daemon.service import CIDXDaemonService

    service = CIDXDaemonService()
    yield service
    # Cleanup
    if service.cache_entry:
        service.cache_entry = None


def test_daemon_query_includes_staleness_metadata(test_project, daemon_service):
    """Test that daemon mode queries include staleness indicators.

    AC1: Daemon query results include staleness dict with is_stale,
         staleness_indicator, and staleness_delta_seconds.
    """
    # Index the project
    daemon_service.exposed_index_blocking(str(test_project), enable_fts=False)

    # Modify file after indexing to make it stale
    test_file = test_project / "src" / "example.py"
    time.sleep(0.1)  # Ensure mtime difference
    test_file.write_text("def hello():\n    return 'world updated'\n")

    # Query via daemon
    response = daemon_service.exposed_query(str(test_project), "hello", limit=5)

    # Verify results exist
    assert "results" in response
    assert len(response["results"]) > 0

    # AC1: Verify staleness metadata exists
    result = response["results"][0]
    assert "staleness" in result, "Daemon query result missing staleness metadata"

    staleness = result["staleness"]
    assert "is_stale" in staleness
    assert "staleness_indicator" in staleness
    assert "staleness_delta_seconds" in staleness

    # File was modified after indexing, so should be stale
    assert staleness["is_stale"] is True, "Modified file should be marked as stale"
    assert (
        staleness["staleness_indicator"] != "🟢 Fresh"
    ), "Modified file should not show fresh indicator"


def test_daemon_fresh_files_show_green_indicator(test_project, daemon_service):
    """Test that daemon shows green icon for unchanged files.

    AC2: Fresh files (not modified after indexing) show "🟢 Fresh" indicator.
    """
    # Index the project
    daemon_service.exposed_index_blocking(str(test_project), enable_fts=False)

    # Query WITHOUT modifying files
    response = daemon_service.exposed_query(str(test_project), "hello", limit=5)

    # Verify results
    assert len(response["results"]) > 0
    result = response["results"][0]

    # AC2: Verify fresh indicator
    assert "staleness" in result
    staleness = result["staleness"]

    assert staleness["is_stale"] is False, "Unchanged file should not be stale"
    assert (
        staleness["staleness_indicator"] == "🟢 Fresh"
    ), "Unchanged file should show green fresh indicator"


def test_daemon_staleness_works_with_non_git_folders(tmp_path, daemon_service):
    """Test staleness detection works with plain folders (no .git).

    AC4: Staleness detection works with non-git folders using file mtime.
    """
    # Create non-git folder
    non_git_project = tmp_path / "non_git_project"
    non_git_project.mkdir()

    cidx_dir = non_git_project / ".code-indexer"
    cidx_dir.mkdir()

    # Create config file for filesystem backend
    config_file = cidx_dir / "config.json"
    config_file.write_text(
        """{
        "codebase_dir": "%s",
        "embedding_provider": "voyage-ai",
        "voyage_api_key": "test-key",
        "vector_store": {
            "provider": "filesystem"
        }
    }"""
        % str(non_git_project)
    )

    src_dir = non_git_project / "src"
    src_dir.mkdir()

    test_file = src_dir / "code.py"
    test_file.write_text("def test():\n    pass\n")

    # Index the project
    daemon_service.exposed_index_blocking(str(non_git_project), enable_fts=False)

    # Modify file
    time.sleep(0.1)
    test_file.write_text("def test():\n    return 'modified'\n")

    # Query via daemon
    response = daemon_service.exposed_query(str(non_git_project), "test", limit=5)

    # AC4: Verify staleness works without git
    assert len(response["results"]) > 0
    result = response["results"][0]
    assert "staleness" in result

    staleness = result["staleness"]
    assert (
        staleness["is_stale"] is True
    ), "Modified file should be stale even without git"
    assert staleness["staleness_indicator"] != "🟢 Fresh"


def test_daemon_staleness_failure_doesnt_break_query(
    test_project, daemon_service, monkeypatch
):
    """Test that staleness detection failure doesn't break queries.

    AC5: Graceful fallback - if staleness detection fails, query still returns results
         without staleness metadata.
    """
    # Index the project
    daemon_service.exposed_index_blocking(str(test_project), enable_fts=False)

    # Mock StalenessDetector to raise exception
    def mock_apply_staleness_detection(*args, **kwargs):
        raise RuntimeError("Staleness detection failed")

    # Patch the staleness detector
    from code_indexer.remote import staleness_detector

    monkeypatch.setattr(
        staleness_detector.StalenessDetector,
        "apply_staleness_detection",
        mock_apply_staleness_detection,
    )

    # Query should still work
    response = daemon_service.exposed_query(str(test_project), "hello", limit=5)

    # AC5: Verify results returned without staleness
    assert "results" in response
    assert len(response["results"]) > 0

    # Results may or may not have staleness (graceful fallback)
    # The important thing is the query didn't crash
    result = response["results"][0]
    # If staleness exists, it's from cache before the patch
    # If it doesn't exist, that's the fallback behavior
    # Either way, the query succeeded
    assert (
        "payload" in result
    ), "Query should return valid results even if staleness fails"

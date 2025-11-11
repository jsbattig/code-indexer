"""
Test for daemon staleness ordering bug.

Critical Bug: Staleness metadata assigned by index position instead of file path,
causing inverted staleness indicators when apply_staleness_detection() sorts results.

Root Cause:
- apply_staleness_detection() sorts results by staleness priority (fresh before stale)
- daemon service assigns staleness metadata by index: results[i]["staleness"] = enhanced_items[i]
- When sort order changes, staleness metadata gets assigned to wrong files

Expected Behavior:
- Match staleness metadata by file path, not index position
- Modified files show stale indicators
- Unchanged files show fresh indicators
"""

import time
from pathlib import Path

import pytest


@pytest.fixture
def test_project_two_files(tmp_path):
    """Create test project with two files for staleness ordering test."""
    project_root = tmp_path / "test_project"
    project_root.mkdir()

    # Create .code-indexer directory with config
    cidx_dir = project_root / ".code-indexer"
    cidx_dir.mkdir()

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

    # Create two files
    src_dir = project_root / "src"
    src_dir.mkdir()

    file1 = src_dir / "file1.py"
    file2 = src_dir / "file2.py"

    file1.write_text("def function_one():\n    return 'one'\n")
    file2.write_text("def function_two():\n    return 'two'\n")

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


def test_daemon_staleness_matches_by_file_path_not_index(
    test_project_two_files, daemon_service
):
    """
    Test that daemon staleness metadata is matched by file path, not index position.

    Scenario:
    1. Create 2 files: file1.py and file2.py
    2. Index both files
    3. Modify file2.py AFTER indexing (make it stale)
    4. Query returns results in score order (varies based on query)
    5. Staleness detection sorts to: [fresh, stale] (changed from input order)
    6. Verify: Each file gets correct staleness metadata by path matching
       - file1.py (unchanged) → fresh indicator
       - file2.py (modified) → stale indicator
       - NOT inverted due to index position mismatch

    This test FAILS with current implementation (inverted staleness).
    This test PASSES after fix (file path matching).
    """
    project_root = test_project_two_files

    # Index the project (both files indexed at same time)
    daemon_service.exposed_index_blocking(str(project_root), enable_fts=False)

    # Wait 2 seconds, then modify ONLY file2.py to make it stale
    time.sleep(2)
    file2 = project_root / "src" / "file2.py"
    file2.write_text("def function_two():\n    return 'MODIFIED two'\n")

    # Query that should return both files
    response = daemon_service.exposed_query(str(project_root), "function", limit=10)

    # Verify results exist
    assert "results" in response
    results = response["results"]
    assert len(results) >= 2, f"Expected at least 2 results, got {len(results)}"

    # Find results by file path
    file1_result = None
    file2_result = None

    for result in results:
        file_path = result.get("payload", {}).get("path", "")
        if "file1.py" in file_path:
            file1_result = result
        elif "file2.py" in file_path:
            file2_result = result

    # Verify both files found
    assert file1_result is not None, "file1.py not found in results"
    assert file2_result is not None, "file2.py not found in results"

    # CRITICAL ASSERTION: Verify correct staleness metadata by file path
    # file1.py (unchanged) should be FRESH
    file1_staleness = file1_result.get("staleness", {})
    assert file1_staleness.get("is_stale") is False, (
        f"file1.py should be FRESH (unchanged), but is_stale={file1_staleness.get('is_stale')}. "
        f"Indicator: {file1_staleness.get('staleness_indicator')}"
    )
    assert "🟢" in file1_staleness.get("staleness_indicator", ""), (
        f"file1.py should show fresh indicator 🟢, "
        f"got: {file1_staleness.get('staleness_indicator')}"
    )

    # file2.py (modified) should be STALE
    file2_staleness = file2_result.get("staleness", {})
    assert file2_staleness.get("is_stale") is True, (
        f"file2.py should be STALE (modified), but is_stale={file2_staleness.get('is_stale')}. "
        f"Indicator: {file2_staleness.get('staleness_indicator')}"
    )
    assert "🟡" in file2_staleness.get(
        "staleness_indicator", ""
    ) or "🟠" in file2_staleness.get("staleness_indicator", ""), (
        f"file2.py should show stale indicator (🟡 or 🟠), "
        f"got: {file2_staleness.get('staleness_indicator')}"
    )

    # Additional verification: Check staleness delta
    assert file2_staleness.get("staleness_delta_seconds", 0) >= 2, (
        f"file2.py should have staleness delta >=2 seconds, "
        f"got: {file2_staleness.get('staleness_delta_seconds')}"
    )

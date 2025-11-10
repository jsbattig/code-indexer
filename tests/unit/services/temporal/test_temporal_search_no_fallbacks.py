"""Test that temporal search has NO forbidden fallbacks (Messi Rule #2).

Verifies:
- Bug 2: No fallback at line 559-566 in temporal_search_service.py
- Bug 3: No fallback at line 447 in temporal_search_service.py
- Content comes directly from chunk_text at root level
- Missing content fails fast with clear error, NOT silent empty string fallback
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from code_indexer.services.temporal.temporal_search_service import TemporalSearchService


@pytest.fixture
def temp_dir():
    """Temporary directory for test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temporal_search_service(temp_dir):
    """Temporal search service instance."""
    return TemporalSearchService(
        config_manager=Mock(),
        project_root=temp_dir,
        vector_store_client=Mock(),
        embedding_provider=Mock(),
        collection_name="test_collection",
    )


def test_reads_content_from_chunk_text_at_root_not_fallback(temporal_search_service):
    """Test Bug 2: Should read from chunk_text at root, NOT fallback to result.content.

    The forbidden fallback at lines 559-566 was:
    ```python
    content = payload.get("content", "")
    if not content:
        content = result.get("content", "")  # FORBIDDEN FALLBACK
    ```

    Fix should read from chunk_text at root level first (Bug 1 fix provides this).
    """
    # Arrange: Simulate what _filter_by_time_range receives
    # After Bug 1 fix, results have chunk_text at root level
    import time
    current_timestamp = int(time.time())  # Current time, within 2020-2025 range

    semantic_results = [
        {
            "id": "test_id",
            "score": 0.95,
            "payload": {
                "path": "test.py",
                "type": "file_chunk",
                "commit_timestamp": current_timestamp,
            },
            "chunk_text": "This is the content from chunk_text at root",  # NEW FORMAT
        }
    ]

    # Act: Call the actual method to verify it reads from chunk_text
    filtered_results, _ = temporal_search_service._filter_by_time_range(
        semantic_results=semantic_results,
        start_date="2020-01-01",
        end_date="2030-12-31",
        min_score=0.0,
    )

    # Assert: Should have extracted content from chunk_text at root level
    assert len(filtered_results) == 1
    result = filtered_results[0]

    # The content should come from chunk_text at root
    assert result.content == "This is the content from chunk_text at root"


def test_missing_chunk_text_raises_runtime_error_no_fallback(temporal_search_service):
    """Test that missing chunk_text raises RuntimeError with NO fallback (Messi Rule #2).

    This verifies the fix for forbidden fallbacks at lines 571-579:
    - Line 571-573: Backward compatibility fallback to payload["content"] - FORBIDDEN
    - Line 579: Silent data loss with "[Content unavailable]" - FORBIDDEN

    Expected behavior:
    - When chunk_text is None/missing and no reconstruct_from_git flag
    - Should raise RuntimeError with clear error message
    - Error message must contain commit_hash and path from payload
    - NO silent fallbacks allowed - fail fast
    """
    # Arrange: Result with missing chunk_text (None) and no reconstruct_from_git
    import time
    current_timestamp = int(time.time())

    semantic_results = [
        {
            "id": "test_id",
            "score": 0.95,
            "payload": {
                "path": "test_file.py",
                "commit_hash": "abc123def456",
                "type": "file_chunk",
                "commit_timestamp": current_timestamp,
                # NO "content" key - this is new indexing format
                # NO "reconstruct_from_git" flag
            },
            # NO chunk_text key - simulates missing content
        }
    ]

    # Act & Assert: Should raise RuntimeError with clear message
    with pytest.raises(RuntimeError) as exc_info:
        temporal_search_service._filter_by_time_range(
            semantic_results=semantic_results,
            start_date="2020-01-01",
            end_date="2030-12-31",
            min_score=0.0,
        )

    # Verify error message contains critical information
    error_message = str(exc_info.value)
    assert "abc123def456" in error_message, "Error must contain commit_hash"
    assert "test_file.py" in error_message, "Error must contain file path"
    assert (
        "chunk_text" in error_message.lower()
        or "missing" in error_message.lower()
        or "unavailable" in error_message.lower()
    ), "Error must indicate missing content"

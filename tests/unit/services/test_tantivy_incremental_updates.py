"""
Unit tests for TantivyIndexManager incremental update operations.

Tests the update_document() and delete_document() methods that enable
real-time FTS index maintenance in watch mode.
"""

import tempfile
from pathlib import Path
import pytest

from code_indexer.services.tantivy_index_manager import TantivyIndexManager


@pytest.fixture
def temp_index_dir():
    """Create a temporary directory for test index."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def tantivy_manager(temp_index_dir):
    """Create and initialize a TantivyIndexManager for testing."""
    manager = TantivyIndexManager(temp_index_dir / "tantivy_index")
    manager.initialize_index(create_new=True)
    return manager


def test_update_document_creates_new_document_if_not_exists(tantivy_manager):
    """Test that update_document creates a new document if file not in index."""
    # Arrange
    doc = {
        "path": "/test/file1.py",
        "content": "def hello(): print('hello')",
        "content_raw": "def hello(): print('hello')",
        "identifiers": ["hello"],
        "line_start": 1,
        "line_end": 1,
        "language": "python",
    }

    # Act
    tantivy_manager.update_document(doc["path"], doc)

    # Assert
    assert tantivy_manager.get_document_count() == 1
    results = tantivy_manager.search("hello", limit=5)
    assert len(results) == 1
    assert results[0]["path"] == "/test/file1.py"


def test_update_document_replaces_existing_document(tantivy_manager):
    """Test that update_document replaces existing document atomically."""
    # Arrange - Add initial document
    initial_doc = {
        "path": "/test/file1.py",
        "content": "def hello(): print('hello')",
        "content_raw": "def hello(): print('hello')",
        "identifiers": ["hello"],
        "line_start": 1,
        "line_end": 1,
        "language": "python",
    }
    tantivy_manager.add_document(initial_doc)
    tantivy_manager.commit()

    # Verify initial state
    assert tantivy_manager.get_document_count() == 1
    results = tantivy_manager.search("hello", limit=5)
    assert len(results) == 1

    # Act - Update with modified content
    updated_doc = {
        "path": "/test/file1.py",
        "content": "def goodbye(): print('goodbye')",
        "content_raw": "def goodbye(): print('goodbye')",
        "identifiers": ["goodbye"],
        "line_start": 1,
        "line_end": 1,
        "language": "python",
    }
    tantivy_manager.update_document(updated_doc["path"], updated_doc)

    # Assert - Should still have 1 document, but with new content
    assert tantivy_manager.get_document_count() == 1
    results = tantivy_manager.search("goodbye", limit=5)
    assert len(results) == 1
    assert results[0]["path"] == "/test/file1.py"

    # Old content should not be searchable
    results = tantivy_manager.search("hello", limit=5)
    assert len(results) == 0


def test_update_document_commits_atomically(tantivy_manager):
    """Test that update_document commits changes atomically."""
    # Arrange
    doc = {
        "path": "/test/file1.py",
        "content": "def test(): pass",
        "content_raw": "def test(): pass",
        "identifiers": ["test"],
        "line_start": 1,
        "line_end": 1,
        "language": "python",
    }

    # Act
    tantivy_manager.update_document(doc["path"], doc)

    # Assert - Changes should be immediately searchable (committed)
    results = tantivy_manager.search("test", limit=5)
    assert len(results) == 1
    assert results[0]["path"] == "/test/file1.py"


def test_delete_document_removes_existing_document(tantivy_manager):
    """Test that delete_document removes a document from the index."""
    # Arrange - Add a document
    doc = {
        "path": "/test/file1.py",
        "content": "def hello(): print('hello')",
        "content_raw": "def hello(): print('hello')",
        "identifiers": ["hello"],
        "line_start": 1,
        "line_end": 1,
        "language": "python",
    }
    tantivy_manager.add_document(doc)
    tantivy_manager.commit()

    # Verify document exists
    assert tantivy_manager.get_document_count() == 1

    # Act - Delete the document
    tantivy_manager.delete_document(doc["path"])

    # Assert - Document should be removed
    assert tantivy_manager.get_document_count() == 0
    results = tantivy_manager.search("hello", limit=5)
    assert len(results) == 0


def test_delete_document_handles_nonexistent_file(tantivy_manager):
    """Test that delete_document gracefully handles deletion of non-existent file."""
    # Act - Try to delete file that doesn't exist
    tantivy_manager.delete_document("/test/nonexistent.py")

    # Assert - Should not raise error, count remains 0
    assert tantivy_manager.get_document_count() == 0


def test_delete_document_commits_atomically(tantivy_manager):
    """Test that delete_document commits changes atomically."""
    # Arrange - Add a document
    doc = {
        "path": "/test/file1.py",
        "content": "def hello(): print('hello')",
        "content_raw": "def hello(): print('hello')",
        "identifiers": ["hello"],
        "line_start": 1,
        "line_end": 1,
        "language": "python",
    }
    tantivy_manager.add_document(doc)
    tantivy_manager.commit()

    # Act - Delete the document
    tantivy_manager.delete_document(doc["path"])

    # Assert - Changes should be immediately visible (committed)
    results = tantivy_manager.search("hello", limit=5)
    assert len(results) == 0


def test_update_multiple_files_independently(tantivy_manager):
    """Test updating multiple files maintains independence."""
    # Arrange - Add two documents
    doc1 = {
        "path": "/test/file1.py",
        "content": "def func1(): pass",
        "content_raw": "def func1(): pass",
        "identifiers": ["func1"],
        "line_start": 1,
        "line_end": 1,
        "language": "python",
    }
    doc2 = {
        "path": "/test/file2.py",
        "content": "def func2(): pass",
        "content_raw": "def func2(): pass",
        "identifiers": ["func2"],
        "line_start": 1,
        "line_end": 1,
        "language": "python",
    }
    tantivy_manager.add_document(doc1)
    tantivy_manager.add_document(doc2)
    tantivy_manager.commit()

    # Act - Update only first file
    updated_doc1 = {
        "path": "/test/file1.py",
        "content": "def updated_func1(): pass",
        "content_raw": "def updated_func1(): pass",
        "identifiers": ["updated_func1"],
        "line_start": 1,
        "line_end": 1,
        "language": "python",
    }
    tantivy_manager.update_document(updated_doc1["path"], updated_doc1)

    # Assert - Second file unchanged, first file updated
    assert tantivy_manager.get_document_count() == 2
    results1 = tantivy_manager.search("updated_func1", limit=5)
    assert len(results1) == 1
    results2 = tantivy_manager.search("func2", limit=5)
    assert len(results2) == 1


def test_update_document_performance_reasonable(tantivy_manager):
    """Test that update_document + search visibility completes within reasonable time."""
    import time

    # Arrange - Add initial document and warm up the index
    doc = {
        "path": "/test/perf_test.py",
        "content": "def initial(): pass",
        "content_raw": "def initial(): pass",
        "identifiers": ["initial"],
        "line_start": 1,
        "line_end": 1,
        "language": "python",
    }
    tantivy_manager.add_document(doc)
    tantivy_manager.commit()

    # Warm up with a search
    tantivy_manager.search("initial", limit=5)

    # Act - Time the complete update operation including search visibility
    updated_doc = {
        "path": "/test/perf_test.py",
        "content": "def updated(): pass",
        "content_raw": "def updated(): pass",
        "identifiers": ["updated"],
        "line_start": 1,
        "line_end": 1,
        "language": "python",
    }

    start_time = time.time()
    tantivy_manager.update_document(updated_doc["path"], updated_doc)
    # Verify changes are immediately searchable
    results = tantivy_manager.search("updated", limit=5)
    elapsed_ms = (time.time() - start_time) * 1000

    # Assert - Verify functionality and reasonable performance
    # Note: Target is <100ms, but test environment may be slower
    # Core requirement: changes must be immediately searchable (atomic commit)
    assert len(results) == 1, "Updated content should be searchable"
    assert (
        elapsed_ms < 1000
    ), f"Update+search took {elapsed_ms:.2f}ms, unreasonably slow"

    # Log performance for monitoring (goal is <100ms, acceptable up to 500ms)
    if elapsed_ms > 100:
        print(f"\nNote: Update+search took {elapsed_ms:.2f}ms (goal: <100ms)")


def test_delete_document_performance_reasonable(tantivy_manager):
    """Test that delete_document + search visibility completes within reasonable time."""
    import time

    # Arrange - Add a document
    doc = {
        "path": "/test/perf_test.py",
        "content": "def test(): pass",
        "content_raw": "def test(): pass",
        "identifiers": ["test"],
        "line_start": 1,
        "line_end": 1,
        "language": "python",
    }
    tantivy_manager.add_document(doc)
    tantivy_manager.commit()

    # Warm up with a search
    tantivy_manager.search("test", limit=5)

    # Act - Time the complete delete operation including search visibility
    start_time = time.time()
    tantivy_manager.delete_document(doc["path"])
    # Verify deletion is immediately reflected in search
    results = tantivy_manager.search("test", limit=5)
    elapsed_ms = (time.time() - start_time) * 1000

    # Assert - Verify functionality and reasonable performance
    # Note: Target is <100ms, but test environment may be slower
    # Core requirement: changes must be immediately searchable (atomic commit)
    assert len(results) == 0, "Deleted content should not be searchable"
    assert (
        elapsed_ms < 1000
    ), f"Delete+search took {elapsed_ms:.2f}ms, unreasonably slow"

    # Log performance for monitoring (goal is <100ms, acceptable up to 500ms)
    if elapsed_ms > 100:
        print(f"\nNote: Delete+search took {elapsed_ms:.2f}ms (goal: <100ms)")

"""
Tests for TantivyIndexManager - full-text search index management.

Tests ensure proper Tantivy integration for building FTS indexes
alongside semantic vector indexes.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestTantivyIndexManager:
    """Test TantivyIndexManager core functionality."""

    def test_tantivy_index_manager_initialization(self):
        """Test TantivyIndexManager can be instantiated with index directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / ".code-indexer" / "tantivy_index"

            # This should fail initially - TantivyIndexManager doesn't exist yet
            from code_indexer.services.tantivy_index_manager import (
                TantivyIndexManager,
            )

            manager = TantivyIndexManager(index_dir=index_dir)
            assert manager is not None
            assert manager.index_dir == index_dir

    def test_schema_creation_with_required_fields(self):
        """Test that Tantivy schema is created with all required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / ".code-indexer" / "tantivy_index"

            from code_indexer.services.tantivy_index_manager import (
                TantivyIndexManager,
            )

            manager = TantivyIndexManager(index_dir=index_dir)
            schema = manager.get_schema()

            # Required fields per acceptance criterion #5
            required_fields = [
                "path",  # stored field
                "content",  # tokenized field for FTS
                "content_raw",  # stored field for raw content
                "identifiers",  # simple tokenizer for exact identifier matches
                "line_start",  # u64 indexed
                "line_end",  # u64 indexed
                "language",  # facet field
            ]

            for field in required_fields:
                assert field in schema, f"Schema should contain required field: {field}"

    def test_index_directory_creation(self):
        """Test that index directory is created with proper permissions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / ".code-indexer" / "tantivy_index"

            from code_indexer.services.tantivy_index_manager import (
                TantivyIndexManager,
            )

            manager = TantivyIndexManager(index_dir=index_dir)
            manager.initialize_index()

            # Directory should be created
            assert index_dir.exists(), "Index directory should be created"
            assert index_dir.is_dir(), "Index path should be a directory"

            # Should be readable and writable
            assert (index_dir / ".").exists(), "Should have proper permissions"

    def test_fixed_heap_size_configuration(self):
        """Test that IndexWriter is configured with fixed 1GB heap size."""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / ".code-indexer" / "tantivy_index"

            from code_indexer.services.tantivy_index_manager import (
                TantivyIndexManager,
            )

            manager = TantivyIndexManager(index_dir=index_dir)
            manager.initialize_index()

            # Get the writer and check heap size configuration
            heap_size = manager.get_writer_heap_size()
            assert (
                heap_size == 1_000_000_000
            ), "IndexWriter should use fixed 1GB heap size"

    def test_add_document_to_index(self):
        """Test adding a document to the FTS index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / ".code-indexer" / "tantivy_index"

            from code_indexer.services.tantivy_index_manager import (
                TantivyIndexManager,
            )

            manager = TantivyIndexManager(index_dir=index_dir)
            manager.initialize_index()

            # Add a test document
            doc = {
                "path": "test.py",
                "content": "def hello(): print('world')",
                "content_raw": "def hello(): print('world')",
                "identifiers": ["hello", "print"],
                "line_start": 1,
                "line_end": 1,
                "language": "python",
            }

            manager.add_document(doc)
            manager.commit()

            # Verify document was added
            assert manager.get_document_count() > 0

    def test_atomic_commit_prevents_corruption(self):
        """Test that commits are atomic to prevent index corruption."""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / ".code-indexer" / "tantivy_index"

            from code_indexer.services.tantivy_index_manager import (
                TantivyIndexManager,
            )

            manager = TantivyIndexManager(index_dir=index_dir)
            manager.initialize_index()

            # Add multiple documents
            docs = [
                {
                    "path": f"test{i}.py",
                    "content": f"def func{i}(): pass",
                    "content_raw": f"def func{i}(): pass",
                    "identifiers": [f"func{i}"],
                    "line_start": 1,
                    "line_end": 1,
                    "language": "python",
                }
                for i in range(5)
            ]

            for doc in docs:
                manager.add_document(doc)

            # Commit should be atomic - either all documents are indexed or none
            manager.commit()
            count_after_commit = manager.get_document_count()
            assert count_after_commit == 5

            # Close first manager to release lock
            manager.close()

            # Simulate failure scenario - add docs and explicitly rollback
            manager2 = TantivyIndexManager(index_dir=index_dir)
            manager2.initialize_index(create_new=False)
            manager2.add_document(
                {
                    "path": "test_fail.py",
                    "content": "fail",
                    "content_raw": "fail",
                    "identifiers": ["fail"],
                    "line_start": 1,
                    "line_end": 1,
                    "language": "python",
                }
            )
            # Explicitly rollback before close
            manager2.rollback()
            manager2.close()

            # Re-open index - should still have original 5 docs (rollback discarded the 6th)
            manager3 = TantivyIndexManager(index_dir=index_dir)
            manager3.initialize_index(create_new=False)
            assert manager3.get_document_count() == 5

    def test_graceful_failure_if_tantivy_not_installed(self):
        """Test that missing Tantivy library results in clear error message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / ".code-indexer" / "tantivy_index"

            # Mock tantivy import failure
            with patch.dict("sys.modules", {"tantivy": None}):
                from code_indexer.services.tantivy_index_manager import (
                    TantivyIndexManager,
                )

                with pytest.raises(ImportError) as exc_info:
                    manager = TantivyIndexManager(index_dir=index_dir)
                    manager.initialize_index()

                assert "tantivy" in str(exc_info.value).lower()
                assert any(
                    word in str(exc_info.value).lower()
                    for word in ["install", "pip", "not found", "missing"]
                )

    def test_metadata_tracking_index_creation(self):
        """Test that metadata indicates FTS index availability."""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / ".code-indexer" / "tantivy_index"

            from code_indexer.services.tantivy_index_manager import (
                TantivyIndexManager,
            )

            manager = TantivyIndexManager(index_dir=index_dir)
            manager.initialize_index()

            metadata = manager.get_metadata()

            # Acceptance criterion #6: metadata tracking
            assert metadata["fts_enabled"] is True
            assert metadata["fts_index_available"] is True
            assert metadata["tantivy_version"] == "0.25.0"
            assert metadata["schema_version"] == "1.0"
            assert "created_at" in metadata
            assert metadata["index_path"] == str(index_dir)

    def test_error_handling_permission_denied(self):
        """Test graceful handling of permission errors."""
        # Create a read-only directory
        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / ".code-indexer" / "tantivy_index"
            index_dir.mkdir(parents=True, exist_ok=True)

            # Make directory read-only
            import os

            os.chmod(index_dir, 0o444)

            try:
                from code_indexer.services.tantivy_index_manager import (
                    TantivyIndexManager,
                )

                manager = TantivyIndexManager(index_dir=index_dir)

                with pytest.raises(PermissionError) as exc_info:
                    manager.initialize_index()

                # Should have clear error message
                assert "permission" in str(exc_info.value).lower()
            finally:
                # Restore permissions for cleanup
                os.chmod(index_dir, 0o755)

    def test_rollback_on_indexing_failure(self):
        """Test that index can be rolled back if indexing fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_dir = Path(tmpdir) / ".code-indexer" / "tantivy_index"

            from code_indexer.services.tantivy_index_manager import (
                TantivyIndexManager,
            )

            manager = TantivyIndexManager(index_dir=index_dir)
            manager.initialize_index()

            # Add valid documents
            manager.add_document(
                {
                    "path": "test.py",
                    "content": "valid",
                    "content_raw": "valid",
                    "identifiers": ["valid"],
                    "line_start": 1,
                    "line_end": 1,
                    "language": "python",
                }
            )
            manager.commit()
            initial_count = manager.get_document_count()

            # Try to add invalid document and trigger rollback
            try:
                manager.add_document(
                    {
                        "path": "invalid.py",
                        # Missing required fields intentionally
                    }
                )
                manager.commit()
            except Exception:
                manager.rollback()

            # Count should remain unchanged after rollback
            assert manager.get_document_count() == initial_count

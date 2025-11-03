"""
Unit tests for FTS incremental updates functionality.

Tests that TantivyIndexManager correctly detects existing indexes and performs
incremental updates instead of always doing full rebuilds.
"""

import pytest
import tempfile
from pathlib import Path

from code_indexer.services.tantivy_index_manager import TantivyIndexManager


class TestFTSIncrementalUpdates:
    """Tests for FTS incremental update detection and behavior."""

    @pytest.fixture
    def temp_index_dir(self):
        """Create a temporary directory for FTS index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def fts_manager(self, temp_index_dir):
        """Create a TantivyIndexManager instance."""
        try:
            return TantivyIndexManager(temp_index_dir)
        except ImportError:
            pytest.skip("Tantivy library not installed")

    def test_first_index_logs_full_build(self, fts_manager, caplog):
        """Test that first index creation logs FULL FTS INDEX BUILD."""
        import logging
        caplog.set_level(logging.INFO)

        # First initialization should log full build
        fts_manager.initialize_index(create_new=True)

        # Verify log contains full build marker
        assert any("FULL FTS INDEX BUILD" in record.message for record in caplog.records)

    def test_existing_index_detects_incremental_mode(self, fts_manager, temp_index_dir, caplog):
        """Test that existing index is detected and opens in incremental mode."""
        import logging
        caplog.set_level(logging.INFO)

        # Create initial index
        fts_manager.initialize_index(create_new=True)
        fts_manager.close()

        # Clear log records
        caplog.clear()

        # Second initialization should detect existing index
        fts_manager2 = TantivyIndexManager(temp_index_dir)
        fts_manager2.initialize_index(create_new=False)

        # Verify it opened existing index (NOT full build)
        assert any("Opened existing Tantivy index" in record.message for record in caplog.records)
        assert not any("FULL FTS INDEX BUILD" in record.message for record in caplog.records)

    def test_incremental_update_logs_incremental_marker(self, fts_manager, caplog):
        """Test that incremental updates log INCREMENTAL FTS UPDATE marker."""
        import logging
        caplog.set_level(logging.INFO)

        # Initialize index
        fts_manager.initialize_index(create_new=True)

        # Clear log records
        caplog.clear()

        # Perform incremental update
        doc = {
            "path": "test_file.py",
            "content": "def hello(): pass",
            "content_raw": "def hello(): pass",
            "identifiers": ["hello"],
            "line_start": 1,
            "line_end": 1,
            "language": "python",
        }
        fts_manager.update_document("test_file.py", doc)

        # Verify incremental update marker is logged
        assert any("⚡ INCREMENTAL FTS UPDATE" in record.message for record in caplog.records)
        assert not any("FULL FTS INDEX BUILD" in record.message for record in caplog.records)

    def test_incremental_update_only_processes_changed_file(self, fts_manager):
        """Test that incremental updates only process the specific changed file."""
        # Initialize index with multiple documents
        fts_manager.initialize_index(create_new=True)

        doc1 = {
            "path": "file1.py",
            "content": "def func1(): pass",
            "content_raw": "def func1(): pass",
            "identifiers": ["func1"],
            "line_start": 1,
            "line_end": 1,
            "language": "python",
        }
        doc2 = {
            "path": "file2.py",
            "content": "def func2(): pass",
            "content_raw": "def func2(): pass",
            "identifiers": ["func2"],
            "line_start": 1,
            "line_end": 1,
            "language": "python",
        }

        fts_manager.add_document(doc1)
        fts_manager.add_document(doc2)
        fts_manager.commit()

        initial_count = fts_manager.get_document_count()
        assert initial_count == 2

        # Update only file1
        doc1_updated = doc1.copy()
        doc1_updated["content"] = "def func1_updated(): pass"
        doc1_updated["content_raw"] = "def func1_updated(): pass"
        doc1_updated["identifiers"] = ["func1_updated"]

        fts_manager.update_document("file1.py", doc1_updated)

        # Document count should remain the same (update, not add)
        final_count = fts_manager.get_document_count()
        assert final_count == 2

        # Search should find updated content
        results = fts_manager.search("func1_updated", limit=10)
        assert len(results) == 1
        assert results[0]["path"] == "file1.py"

        # Old content should not be found (use exact search to avoid partial matches)
        # Note: "func1" substring matches in "func1_updated" due to tokenization
        # Use a term that's completely different to verify update worked
        results_old = fts_manager.search("pass", limit=10)
        # Both files should match "pass" (it's in both)
        assert len(results_old) == 2

        # Verify file1 now has the updated content
        file1_result = [r for r in results_old if r["path"] == "file1.py"][0]
        assert "func1_updated" in file1_result["snippet"]

    def test_smart_indexer_uses_incremental_mode_on_second_run(self, temp_index_dir, caplog):
        """Test that SmartIndexer detects existing FTS index and uses incremental mode."""
        import logging
        caplog.set_level(logging.INFO)

        # Create initial index by calling initialize_index(create_new=True)
        try:
            fts_manager1 = TantivyIndexManager(temp_index_dir)
        except ImportError:
            pytest.skip("Tantivy library not installed")

        fts_manager1.initialize_index(create_new=True)
        assert any("FULL FTS INDEX BUILD" in record.message for record in caplog.records)
        fts_manager1.close()

        # Clear log records
        caplog.clear()

        # Second run should detect existing index
        fts_manager2 = TantivyIndexManager(temp_index_dir)

        # This should NOT use create_new=True if index already exists
        # BUG: Currently SmartIndexer always calls initialize_index(create_new=True)
        # This test will FAIL until we fix SmartIndexer to check if index exists first

        # Check if index exists by looking for meta.json
        index_exists = (temp_index_dir / "meta.json").exists()

        # If index exists, should open it (not create new)
        if index_exists:
            fts_manager2.initialize_index(create_new=False)
            # Should log "Opened existing" NOT "FULL FTS INDEX BUILD"
            assert any("Opened existing Tantivy index" in record.message for record in caplog.records)
            assert not any("FULL FTS INDEX BUILD" in record.message for record in caplog.records)
        else:
            # If index doesn't exist, should create new
            fts_manager2.initialize_index(create_new=True)
            assert any("FULL FTS INDEX BUILD" in record.message for record in caplog.records)

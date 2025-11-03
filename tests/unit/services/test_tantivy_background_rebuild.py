"""Tests for FTS background rebuild using BackgroundIndexRebuilder.

Tests that FTS rebuilds use the same background+atomic swap pattern as HNSW/ID
indexes to avoid blocking query operations (Story 0 AC3).
"""

import threading
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from code_indexer.services.tantivy_index_manager import TantivyIndexManager


class TestFTSBackgroundRebuild:
    """Test FTS background rebuild pattern (Bug #1 - AC3)."""

    @pytest.fixture
    def sample_documents(self) -> List[Dict[str, Any]]:
        """Create sample documents for testing."""
        return [
            {
                "path": "test1.py",
                "content": "def hello world",
                "content_raw": "def hello() -> str:\n    return 'world'\n",
                "identifiers": ["hello", "world"],
                "line_start": 1,
                "line_end": 2,
                "language": "python",
            },
            {
                "path": "test2.py",
                "content": "def goodbye world",
                "content_raw": "def goodbye() -> str:\n    return 'world'\n",
                "identifiers": ["goodbye", "world"],
                "line_start": 1,
                "line_end": 2,
                "language": "python",
            },
        ]

    def test_tantivy_has_background_rebuild_method(self, tmp_path: Path):
        """Test that TantivyIndexManager has rebuild_from_documents_background method.

        EXPECTED TO FAIL: Method doesn't exist yet.
        """
        fts_dir = tmp_path / "tantivy_fts"
        fts_dir.mkdir()

        manager = TantivyIndexManager(fts_dir)

        # Should have background rebuild method
        assert hasattr(manager, "rebuild_from_documents_background"), (
            "TantivyIndexManager must have rebuild_from_documents_background method "
            "for non-blocking rebuilds (AC3)"
        )

    def test_fts_rebuild_does_not_block_queries(
        self, tmp_path: Path, sample_documents: List[Dict[str, Any]]
    ):
        """Test that FTS rebuild doesn't block search queries (AC3).

        Pattern: Same as HNSW/ID - rebuild to .tmp, atomic swap.

        EXPECTED TO FAIL: rebuild_from_documents_background doesn't exist yet.
        """
        collection_path = tmp_path / "collection"
        collection_path.mkdir()
        fts_dir = collection_path / "tantivy_fts"
        fts_dir.mkdir()

        # Create initial FTS index
        manager = TantivyIndexManager(fts_dir)
        manager.initialize_index(create_new=True)

        for doc in sample_documents:
            manager.add_document(doc)
        manager.commit()

        # Verify initial search works
        results = manager.search("hello", limit=10)
        assert len(results) > 0

        # Start background rebuild in thread
        rebuild_started = threading.Event()
        rebuild_in_progress = threading.Event()
        query_during_rebuild_succeeded = threading.Event()

        def slow_rebuild():
            """Simulate slow rebuild (100ms)."""
            rebuild_started.set()

            # Simulate slow document fetching
            slow_documents = sample_documents.copy()
            time.sleep(0.1)  # Simulate slow fetch

            rebuild_in_progress.set()

            # Background rebuild (should not block queries)
            rebuild_thread = manager.rebuild_from_documents_background(
                collection_path=collection_path,
                documents=slow_documents
            )

            # Wait for rebuild to complete
            rebuild_thread.join(timeout=2.0)

        def query_during_rebuild():
            """Query while rebuild is in progress."""
            # Wait for rebuild to start
            rebuild_in_progress.wait(timeout=1.0)

            # This query should NOT block (queries don't need locks)
            try:
                start_time = time.perf_counter()
                results = manager.search("hello", limit=10)
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                # Query should complete quickly (<100ms, not blocked by rebuild)
                assert elapsed_ms < 100, (
                    f"Query took {elapsed_ms:.2f}ms - appears to be blocked by rebuild. "
                    "AC3 requires queries continue during rebuild."
                )

                # Query should succeed
                assert len(results) > 0
                query_during_rebuild_succeeded.set()

            except Exception as e:
                pytest.fail(f"Query failed during rebuild: {e}")

        # Start threads
        t1 = threading.Thread(target=slow_rebuild)
        t2 = threading.Thread(target=query_during_rebuild)

        t1.start()
        t2.start()

        # Wait for both to complete
        t1.join(timeout=3.0)
        t2.join(timeout=3.0)

        # Verify query succeeded during rebuild (AC3)
        assert query_during_rebuild_succeeded.is_set(), (
            "Query must succeed during rebuild without blocking (AC3)"
        )

    def test_fts_rebuild_uses_atomic_swap(
        self, tmp_path: Path, sample_documents: List[Dict[str, Any]]
    ):
        """Test that FTS rebuild uses atomic swap pattern (.tmp → final).

        EXPECTED TO FAIL: rebuild_from_documents_background doesn't exist yet.
        """
        collection_path = tmp_path / "collection"
        collection_path.mkdir()
        fts_dir = collection_path / "tantivy_fts"
        fts_dir.mkdir()

        # Create initial FTS index
        manager = TantivyIndexManager(fts_dir)
        manager.initialize_index(create_new=True)

        for doc in sample_documents:
            manager.add_document(doc)
        manager.commit()

        # Trigger background rebuild
        rebuild_thread = manager.rebuild_from_documents_background(
            collection_path=collection_path,
            documents=sample_documents
        )

        # Wait for rebuild
        rebuild_thread.join(timeout=2.0)

        # Verify .tmp file was created and swapped (should not exist after swap)
        temp_fts_dir = collection_path / "tantivy_fts.tmp"
        assert not temp_fts_dir.exists(), (
            "Temp directory should not exist after atomic swap"
        )

        # Verify final index exists
        assert fts_dir.exists()
        assert (fts_dir / "meta.json").exists()


class TestOrphanedTempFileCleanup:
    """Test cleanup of orphaned .tmp files (Bug #2 - AC9)."""

    def test_cleanup_called_before_rebuild(self, tmp_path: Path):
        """Test that cleanup_orphaned_temp_files is called before rebuild starts.

        EXPECTED TO FAIL: cleanup_orphaned_temp_files is never called.
        """
        collection_path = tmp_path / "collection"
        collection_path.mkdir()

        # Create orphaned .tmp files (simulate crash)
        orphaned_tmp1 = collection_path / "tantivy_fts.tmp"
        orphaned_tmp1.mkdir()
        (orphaned_tmp1 / "meta.json").write_text('{"orphaned": true}')

        orphaned_tmp2 = collection_path / "hnsw_index.bin.tmp"
        orphaned_tmp2.write_text("orphaned hnsw data")

        # Make them old (2 hours ago)
        import os
        two_hours_ago = time.time() - (2 * 3600)
        os.utime(orphaned_tmp1, (two_hours_ago, two_hours_ago))
        os.utime(orphaned_tmp2, (two_hours_ago, two_hours_ago))

        # Trigger rebuild (should cleanup orphaned files first)
        from code_indexer.storage.background_index_rebuilder import BackgroundIndexRebuilder

        rebuilder = BackgroundIndexRebuilder(collection_path)

        # Simple rebuild that triggers cleanup
        target_file = collection_path / "test_index.bin"

        def simple_build(temp_file: Path):
            temp_file.write_text("new data")

        rebuilder.rebuild_with_lock(simple_build, target_file)

        # Verify orphaned files were cleaned up (AC9)
        assert not orphaned_tmp1.exists(), (
            "Orphaned tantivy_fts.tmp should be cleaned up before rebuild (AC9)"
        )
        assert not orphaned_tmp2.exists(), (
            "Orphaned hnsw_index.bin.tmp should be cleaned up before rebuild (AC9)"
        )

    def test_cleanup_preserves_recent_temp_files(self, tmp_path: Path):
        """Test that cleanup preserves recent .tmp files (active rebuilds)."""
        collection_path = tmp_path / "collection"
        collection_path.mkdir()

        # Create recent temp file (10 seconds ago)
        recent_tmp = collection_path / "active_rebuild.tmp"
        recent_tmp.write_text("active rebuild in progress")

        import os
        ten_seconds_ago = time.time() - 10
        os.utime(recent_tmp, (ten_seconds_ago, ten_seconds_ago))

        # Create old temp file (2 hours ago)
        old_tmp = collection_path / "old_rebuild.tmp"
        old_tmp.write_text("orphaned rebuild")
        two_hours_ago = time.time() - (2 * 3600)
        os.utime(old_tmp, (two_hours_ago, two_hours_ago))

        # Trigger rebuild (cleanup with default 1 hour threshold)
        from code_indexer.storage.background_index_rebuilder import BackgroundIndexRebuilder

        rebuilder = BackgroundIndexRebuilder(collection_path)

        target_file = collection_path / "test_index.bin"

        def simple_build(temp_file: Path):
            temp_file.write_text("new data")

        rebuilder.rebuild_with_lock(simple_build, target_file)

        # Verify recent file preserved, old file removed
        assert recent_tmp.exists(), "Recent temp files should be preserved"
        assert not old_tmp.exists(), "Old temp files should be removed"

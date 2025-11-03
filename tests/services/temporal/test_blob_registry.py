"""Tests for BlobRegistry - SQLite-based blob deduplication - TDD approach."""
import pytest
import sqlite3
from pathlib import Path
from code_indexer.services.temporal.blob_registry import BlobRegistry


class TestBlobRegistry:
    """Test BlobRegistry for tracking blob_hash -> point_id mappings."""

    def test_blob_registry_creates_database(self, tmp_path):
        """Test BlobRegistry creates SQLite database file."""
        db_path = tmp_path / "blob_registry.db"

        registry = BlobRegistry(db_path)

        assert db_path.exists()

    def test_blob_registry_creates_table_with_schema(self, tmp_path):
        """Test BlobRegistry creates table with correct schema."""
        db_path = tmp_path / "blob_registry.db"

        registry = BlobRegistry(db_path)

        # Verify table exists with correct columns
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("PRAGMA table_info(blob_registry)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}  # name: type
        conn.close()

        assert "blob_hash" in columns
        assert "point_id" in columns
        assert columns["blob_hash"] == "TEXT"
        assert columns["point_id"] == "TEXT"

    def test_register_blob_adds_mapping(self, tmp_path):
        """Test register() adds blob_hash -> point_id mapping."""
        db_path = tmp_path / "blob_registry.db"
        registry = BlobRegistry(db_path)

        registry.register("abc123", "point_1")

        # Verify in database
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT point_id FROM blob_registry WHERE blob_hash = ?",
            ("abc123",)
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "point_1"

    def test_register_blob_allows_multiple_points_per_blob(self, tmp_path):
        """Test register() allows multiple point_ids for same blob_hash (chunks)."""
        db_path = tmp_path / "blob_registry.db"
        registry = BlobRegistry(db_path)

        # Same blob can have multiple point IDs (one per chunk)
        registry.register("abc123", "point_1")
        registry.register("abc123", "point_2")
        registry.register("abc123", "point_3")

        # Verify all stored
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT point_id FROM blob_registry WHERE blob_hash = ? ORDER BY point_id",
            ("abc123",)
        )
        results = cursor.fetchall()
        conn.close()

        assert len(results) == 3
        point_ids = [r[0] for r in results]
        assert point_ids == ["point_1", "point_2", "point_3"]

    def test_has_blob_returns_true_when_exists(self, tmp_path):
        """Test has_blob() returns True when blob exists in registry."""
        db_path = tmp_path / "blob_registry.db"
        registry = BlobRegistry(db_path)

        registry.register("abc123", "point_1")

        assert registry.has_blob("abc123") is True

    def test_has_blob_returns_false_when_not_exists(self, tmp_path):
        """Test has_blob() returns False when blob doesn't exist."""
        db_path = tmp_path / "blob_registry.db"
        registry = BlobRegistry(db_path)

        assert registry.has_blob("nonexistent") is False

    def test_get_point_ids_returns_all_points_for_blob(self, tmp_path):
        """Test get_point_ids() returns all point IDs for a blob."""
        db_path = tmp_path / "blob_registry.db"
        registry = BlobRegistry(db_path)

        registry.register("abc123", "point_1")
        registry.register("abc123", "point_2")
        registry.register("abc123", "point_3")

        point_ids = registry.get_point_ids("abc123")

        assert len(point_ids) == 3
        assert set(point_ids) == {"point_1", "point_2", "point_3"}

    def test_get_point_ids_returns_empty_for_nonexistent_blob(self, tmp_path):
        """Test get_point_ids() returns empty list for nonexistent blob."""
        db_path = tmp_path / "blob_registry.db"
        registry = BlobRegistry(db_path)

        point_ids = registry.get_point_ids("nonexistent")

        assert point_ids == []

    def test_register_duplicate_mapping_is_idempotent(self, tmp_path):
        """Test registering same blob_hash + point_id twice is idempotent."""
        db_path = tmp_path / "blob_registry.db"
        registry = BlobRegistry(db_path)

        # Register same mapping twice
        registry.register("abc123", "point_1")
        registry.register("abc123", "point_1")

        # Should only have one entry
        point_ids = registry.get_point_ids("abc123")
        assert len(point_ids) == 1
        assert point_ids[0] == "point_1"

    def test_registry_with_large_number_of_blobs(self, tmp_path):
        """Test registry can handle large number of blobs (performance test)."""
        db_path = tmp_path / "blob_registry.db"
        registry = BlobRegistry(db_path)

        # Register 1000 blobs with 3 points each (3000 total entries)
        for i in range(1000):
            blob_hash = f"blob_{i:04d}"
            for j in range(3):
                point_id = f"point_{i:04d}_{j}"
                registry.register(blob_hash, point_id)

        # Verify lookups are fast
        assert registry.has_blob("blob_0500") is True
        assert registry.has_blob("blob_9999") is False

        # Verify retrieval works
        point_ids = registry.get_point_ids("blob_0500")
        assert len(point_ids) == 3

    def test_registry_has_index_on_blob_hash(self, tmp_path):
        """Test registry has index on blob_hash for fast lookups."""
        db_path = tmp_path / "blob_registry.db"
        registry = BlobRegistry(db_path)

        # Check for index existence
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='blob_registry'"
        )
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()

        # Should have at least one index (could be idx_blob_hash or PRIMARY KEY)
        assert len(indexes) > 0

    def test_registry_uses_wal_mode(self, tmp_path):
        """Test registry uses WAL mode for concurrent access."""
        db_path = tmp_path / "blob_registry.db"
        registry = BlobRegistry(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        conn.close()

        assert journal_mode.upper() == "WAL"

    def test_clear_removes_all_entries(self, tmp_path):
        """Test clear() removes all entries from registry."""
        db_path = tmp_path / "blob_registry.db"
        registry = BlobRegistry(db_path)

        # Add some entries
        registry.register("abc123", "point_1")
        registry.register("def456", "point_2")

        # Clear
        registry.clear()

        # Verify empty
        assert registry.has_blob("abc123") is False
        assert registry.has_blob("def456") is False

    def test_count_returns_total_blobs(self, tmp_path):
        """Test count() returns total number of unique blobs."""
        db_path = tmp_path / "blob_registry.db"
        registry = BlobRegistry(db_path)

        # Add blobs (some with multiple points)
        registry.register("abc123", "point_1")
        registry.register("abc123", "point_2")  # Same blob
        registry.register("def456", "point_3")
        registry.register("ghi789", "point_4")

        count = registry.count()

        # Should count unique blobs, not total entries
        assert count == 3

    def test_registry_handles_empty_database(self, tmp_path):
        """Test registry operations work with empty database."""
        db_path = tmp_path / "blob_registry.db"
        registry = BlobRegistry(db_path)

        assert registry.has_blob("anything") is False
        assert registry.get_point_ids("anything") == []
        assert registry.count() == 0

    def test_close_closes_database_connection(self, tmp_path):
        """Test close() properly closes database connection."""
        db_path = tmp_path / "blob_registry.db"
        registry = BlobRegistry(db_path)

        registry.register("abc123", "point_1")

        registry.close()

        # Should be able to open new connection after close
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM blob_registry")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 1

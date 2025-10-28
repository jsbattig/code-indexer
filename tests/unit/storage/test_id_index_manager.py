"""Unit tests for binary mmap-based ID index manager."""

import struct
from pathlib import Path
import pytest
import tempfile
import shutil

from code_indexer.storage.id_index_manager import IDIndexManager


class TestIDIndexManagerBinary:
    """Test binary serialization and mmap-based loading."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = IDIndexManager()

    def teardown_method(self):
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_empty_index_serialization(self):
        """Test serialization of empty index."""
        # Given: Empty ID index
        id_index = {}

        # When: Save empty index
        self.manager.save_index(self.temp_dir, id_index)

        # Then: Binary file should exist with correct header
        index_file = self.temp_dir / "id_index.bin"
        assert index_file.exists()

        # Verify binary format: num_entries = 0
        with open(index_file, "rb") as f:
            num_entries = struct.unpack("<I", f.read(4))[0]
            assert num_entries == 0

    def test_single_entry_serialization(self):
        """Test serialization of single entry."""
        # Given: ID index with one entry
        id_index = {"point_id_1": self.temp_dir / "vectors" / "vector_001.json"}

        # When: Save index
        self.manager.save_index(self.temp_dir, id_index)

        # Then: Load should return same data
        loaded_index = self.manager.load_index(self.temp_dir)
        assert len(loaded_index) == 1
        assert "point_id_1" in loaded_index
        assert (
            loaded_index["point_id_1"] == self.temp_dir / "vectors" / "vector_001.json"
        )

    def test_multiple_entries_serialization(self):
        """Test serialization of multiple entries."""
        # Given: ID index with multiple entries
        id_index = {
            f"point_id_{i}": self.temp_dir / "vectors" / f"vector_{i:03d}.json"
            for i in range(100)
        }

        # When: Save and load
        self.manager.save_index(self.temp_dir, id_index)
        loaded_index = self.manager.load_index(self.temp_dir)

        # Then: All entries should match
        assert len(loaded_index) == 100
        for i in range(100):
            point_id = f"point_id_{i}"
            assert point_id in loaded_index
            assert (
                loaded_index[point_id]
                == self.temp_dir / "vectors" / f"vector_{i:03d}.json"
            )

    def test_unicode_handling(self):
        """Test handling of Unicode characters in IDs and paths."""
        # Given: ID index with Unicode characters
        id_index = {
            "point_id_español": self.temp_dir / "vectors" / "文件.json",
            "точка_id_русский": self.temp_dir / "vectors" / "αρχείο.json",
        }

        # When: Save and load
        self.manager.save_index(self.temp_dir, id_index)
        loaded_index = self.manager.load_index(self.temp_dir)

        # Then: Unicode should be preserved
        assert len(loaded_index) == 2
        assert (
            loaded_index["point_id_español"] == self.temp_dir / "vectors" / "文件.json"
        )
        assert (
            loaded_index["точка_id_русский"]
            == self.temp_dir / "vectors" / "αρχείο.json"
        )

    def test_large_index_performance(self):
        """Test performance with large index (1000+ entries)."""
        # Given: Large ID index
        id_index = {
            f"point_id_{i:06d}": self.temp_dir / "vectors" / f"vector_{i:06d}.json"
            for i in range(1000)
        }

        # When: Save and load
        import time

        t0 = time.time()
        self.manager.save_index(self.temp_dir, id_index)
        save_time = (time.time() - t0) * 1000

        t0 = time.time()
        loaded_index = self.manager.load_index(self.temp_dir)
        load_time = (time.time() - t0) * 1000

        # Then: All entries should match
        assert len(loaded_index) == 1000

        # Performance requirements (should be fast with mmap)
        # Note: These are conservative limits - actual should be much faster
        assert save_time < 1000, f"Save took {save_time:.2f}ms, expected <1000ms"
        assert load_time < 100, f"Load took {load_time:.2f}ms, expected <100ms"

    def test_mmap_loading_consistency(self):
        """Test that mmap loading produces same results as regular loading."""
        # Given: ID index
        id_index = {
            f"point_id_{i}": self.temp_dir / "vectors" / f"vector_{i:03d}.json"
            for i in range(50)
        }

        # When: Save once
        self.manager.save_index(self.temp_dir, id_index)

        # Then: Multiple loads should produce identical results
        loaded_1 = self.manager.load_index(self.temp_dir)
        loaded_2 = self.manager.load_index(self.temp_dir)

        assert loaded_1 == loaded_2

    def test_corrupted_file_handling(self):
        """Test handling of corrupted binary files."""
        # Given: Corrupted binary file
        index_file = self.temp_dir / "id_index.bin"
        with open(index_file, "wb") as f:
            f.write(b"\xff\xff\xff\xff")  # Invalid header

        # When/Then: Should handle gracefully
        with pytest.raises(Exception):  # Should raise appropriate exception
            self.manager.load_index(self.temp_dir)

    def test_missing_file_handling(self):
        """Test handling of missing index file."""
        # Given: No index file exists

        # When: Load non-existent index
        loaded_index = self.manager.load_index(self.temp_dir)

        # Then: Should return empty dict
        assert loaded_index == {}

    def test_binary_format_structure(self):
        """Test binary format structure matches specification."""
        # Given: ID index with known data
        id_index = {
            "id1": self.temp_dir / "path1.json",
            "id2": self.temp_dir / "path2.json",
        }

        # When: Save index
        self.manager.save_index(self.temp_dir, id_index)

        # Then: Manually verify binary format
        index_file = self.temp_dir / "id_index.bin"
        with open(index_file, "rb") as f:
            # Read header: num_entries (4 bytes)
            num_entries = struct.unpack("<I", f.read(4))[0]
            assert num_entries == 2

            # Read first entry
            id_len = struct.unpack("<H", f.read(2))[0]
            id_str = f.read(id_len).decode("utf-8")
            path_len = struct.unpack("<H", f.read(2))[0]
            path_str = f.read(path_len).decode("utf-8")

            # Verify first entry (order may vary due to dict)
            assert id_str in ["id1", "id2"]
            assert path_str in ["path1.json", "path2.json"]

    def test_incremental_update(self):
        """Test incremental updates to index."""
        # Given: Initial index
        initial_index = {
            "id1": self.temp_dir / "path1.json",
            "id2": self.temp_dir / "path2.json",
        }
        self.manager.save_index(self.temp_dir, initial_index)

        # When: Update with new entries
        updates = {
            "id3": self.temp_dir / "path3.json",
            "id4": self.temp_dir / "path4.json",
        }
        self.manager.update_batch(self.temp_dir, updates)

        # Then: All entries should be present
        loaded_index = self.manager.load_index(self.temp_dir)
        assert len(loaded_index) == 4
        assert all(f"id{i}" in loaded_index for i in range(1, 5))

    def test_remove_ids(self):
        """Test removing IDs from index."""
        # Given: Index with multiple entries
        id_index = {f"id{i}": self.temp_dir / f"path{i}.json" for i in range(1, 6)}
        self.manager.save_index(self.temp_dir, id_index)

        # When: Remove some IDs
        self.manager.remove_ids(self.temp_dir, ["id2", "id4"])

        # Then: Removed IDs should be gone
        loaded_index = self.manager.load_index(self.temp_dir)
        assert len(loaded_index) == 3
        assert "id1" in loaded_index
        assert "id2" not in loaded_index
        assert "id3" in loaded_index
        assert "id4" not in loaded_index
        assert "id5" in loaded_index

    def test_long_paths(self):
        """Test handling of very long file paths."""
        # Given: ID index with long paths
        long_path = "a" * 200 + "/b" * 50 + "/vector.json"
        id_index = {"point_id_long": self.temp_dir / long_path}

        # When: Save and load
        self.manager.save_index(self.temp_dir, id_index)
        loaded_index = self.manager.load_index(self.temp_dir)

        # Then: Long path should be preserved
        assert len(loaded_index) == 1
        assert loaded_index["point_id_long"] == self.temp_dir / long_path

    def test_relative_path_conversion(self):
        """Test that paths are stored relative to collection path."""
        # Given: ID index with absolute paths
        id_index = {"id1": self.temp_dir / "vectors" / "sub" / "vector.json"}

        # When: Save index
        self.manager.save_index(self.temp_dir, id_index)

        # Then: Check binary format uses relative path
        index_file = self.temp_dir / "id_index.bin"
        with open(index_file, "rb") as f:
            struct.unpack("<I", f.read(4))  # Skip num_entries
            id_len = struct.unpack("<H", f.read(2))[0]
            f.read(id_len)  # Skip ID
            path_len = struct.unpack("<H", f.read(2))[0]
            path_str = f.read(path_len).decode("utf-8")

            # Should be relative, not absolute
            assert not path_str.startswith("/")
            assert path_str == "vectors/sub/vector.json"


class TestIDIndexManagerThreadSafety:
    """Test thread safety of ID index operations."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = IDIndexManager()

    def teardown_method(self):
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_concurrent_updates(self):
        """Test concurrent updates don't corrupt index."""
        import threading

        # Given: Initial empty index
        id_index = {}
        self.manager.save_index(self.temp_dir, id_index)

        # When: Multiple threads update concurrently
        def update_worker(worker_id):
            updates = {
                f"id_{worker_id}_{i}": self.temp_dir / f"path_{worker_id}_{i}.json"
                for i in range(10)
            }
            self.manager.update_batch(self.temp_dir, updates)

        threads = [threading.Thread(target=update_worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Then: All updates should be present
        loaded_index = self.manager.load_index(self.temp_dir)
        assert len(loaded_index) == 50  # 5 workers * 10 entries each

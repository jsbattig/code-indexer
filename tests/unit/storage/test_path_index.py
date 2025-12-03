"""Unit tests for PathIndex reverse index (file_path -> point_ids mapping).

Tests the path-to-point_ids reverse index that prevents duplicate chunks
when files are re-indexed. This addresses Story #540.
"""

import pytest
from pathlib import Path
import tempfile
import msgpack
from src.code_indexer.storage.filesystem_vector_store import PathIndex


class TestPathIndexBasicOperations:
    """Test basic PathIndex operations: add, remove, get."""

    def test_add_point_creates_new_set_for_file(self):
        """Adding first point for a file should create new set."""
        path_index = PathIndex()

        path_index.add_point("src/auth.py", "point_a1")

        point_ids = path_index.get_point_ids("src/auth.py")
        assert point_ids == {"point_a1"}

    def test_add_multiple_points_to_same_file(self):
        """Adding multiple points to same file should accumulate in set."""
        path_index = PathIndex()

        path_index.add_point("src/auth.py", "point_a1")
        path_index.add_point("src/auth.py", "point_a2")
        path_index.add_point("src/auth.py", "point_a3")

        point_ids = path_index.get_point_ids("src/auth.py")
        assert point_ids == {"point_a1", "point_a2", "point_a3"}

    def test_add_points_to_different_files(self):
        """Adding points to different files should maintain separate sets."""
        path_index = PathIndex()

        path_index.add_point("src/auth.py", "auth_a1")
        path_index.add_point("src/auth.py", "auth_a2")
        path_index.add_point("src/utils.py", "utils_u1")

        assert path_index.get_point_ids("src/auth.py") == {"auth_a1", "auth_a2"}
        assert path_index.get_point_ids("src/utils.py") == {"utils_u1"}

    def test_add_duplicate_point_id_is_idempotent(self):
        """Adding same point_id twice should be idempotent (set behavior)."""
        path_index = PathIndex()

        path_index.add_point("src/auth.py", "point_a1")
        path_index.add_point("src/auth.py", "point_a1")  # duplicate

        point_ids = path_index.get_point_ids("src/auth.py")
        assert point_ids == {"point_a1"}

    def test_remove_point_removes_from_set(self):
        """Removing a point should remove it from the file's set."""
        path_index = PathIndex()
        path_index.add_point("src/auth.py", "point_a1")
        path_index.add_point("src/auth.py", "point_a2")

        path_index.remove_point("src/auth.py", "point_a1")

        point_ids = path_index.get_point_ids("src/auth.py")
        assert point_ids == {"point_a2"}

    def test_remove_last_point_deletes_file_entry(self):
        """Removing last point for a file should delete the file's entry entirely."""
        path_index = PathIndex()
        path_index.add_point("src/auth.py", "point_a1")

        path_index.remove_point("src/auth.py", "point_a1")

        # File should not exist in index anymore
        point_ids = path_index.get_point_ids("src/auth.py")
        assert point_ids == set()

        # Internal _path_index should not contain the file
        assert "src/auth.py" not in path_index._path_index

    def test_remove_nonexistent_point_is_safe(self):
        """Removing a point that doesn't exist should not raise error."""
        path_index = PathIndex()
        path_index.add_point("src/auth.py", "point_a1")

        # Should not raise
        path_index.remove_point("src/auth.py", "point_nonexistent")

        # Original point should still be there
        assert path_index.get_point_ids("src/auth.py") == {"point_a1"}

    def test_remove_from_nonexistent_file_is_safe(self):
        """Removing from a file that doesn't exist should not raise error."""
        path_index = PathIndex()

        # Should not raise
        path_index.remove_point("src/nonexistent.py", "point_x")

    def test_get_point_ids_returns_copy(self):
        """get_point_ids should return a copy, not the internal set."""
        path_index = PathIndex()
        path_index.add_point("src/auth.py", "point_a1")

        point_ids_1 = path_index.get_point_ids("src/auth.py")
        point_ids_2 = path_index.get_point_ids("src/auth.py")

        # Should be equal but not the same object
        assert point_ids_1 == point_ids_2
        assert point_ids_1 is not point_ids_2

        # Modifying returned set should not affect internal state
        point_ids_1.add("point_a2")
        assert path_index.get_point_ids("src/auth.py") == {"point_a1"}

    def test_get_point_ids_for_nonexistent_file_returns_empty_set(self):
        """Getting point_ids for nonexistent file should return empty set."""
        path_index = PathIndex()

        point_ids = path_index.get_point_ids("src/nonexistent.py")
        assert point_ids == set()


class TestPathIndexPersistence:
    """Test PathIndex persistence with msgpack."""

    def test_save_and_load_empty_index(self):
        """Saving and loading empty index should work."""
        path_index = PathIndex()

        with tempfile.TemporaryDirectory() as tmpdir:
            index_file = Path(tmpdir) / "path_index.bin"

            path_index.save(index_file)
            assert index_file.exists()

            loaded_index = PathIndex.load(index_file)
            assert loaded_index._path_index == {}

    def test_save_and_load_populated_index(self):
        """Saving and loading populated index should preserve all data."""
        path_index = PathIndex()
        path_index.add_point("src/auth.py", "auth_a1")
        path_index.add_point("src/auth.py", "auth_a2")
        path_index.add_point("src/auth.py", "auth_a3")
        path_index.add_point("src/utils.py", "utils_u1")
        path_index.add_point("src/utils.py", "utils_u2")
        path_index.add_point("src/config.py", "config_c1")

        with tempfile.TemporaryDirectory() as tmpdir:
            index_file = Path(tmpdir) / "path_index.bin"

            path_index.save(index_file)
            loaded_index = PathIndex.load(index_file)

            assert loaded_index.get_point_ids("src/auth.py") == {"auth_a1", "auth_a2", "auth_a3"}
            assert loaded_index.get_point_ids("src/utils.py") == {"utils_u1", "utils_u2"}
            assert loaded_index.get_point_ids("src/config.py") == {"config_c1"}

    def test_load_nonexistent_file_returns_empty_index(self):
        """Loading from nonexistent file should return empty PathIndex."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent_file = Path(tmpdir) / "nonexistent.bin"

            loaded_index = PathIndex.load(nonexistent_file)
            assert loaded_index._path_index == {}

    def test_save_creates_parent_directories(self):
        """save() should create parent directories if they don't exist."""
        path_index = PathIndex()
        path_index.add_point("src/auth.py", "auth_a1")

        with tempfile.TemporaryDirectory() as tmpdir:
            nested_file = Path(tmpdir) / "nested" / "dirs" / "path_index.bin"

            path_index.save(nested_file)
            assert nested_file.exists()

            loaded_index = PathIndex.load(nested_file)
            assert loaded_index.get_point_ids("src/auth.py") == {"auth_a1"}

    def test_msgpack_format_compatibility(self):
        """Saved file should use msgpack format and be loadable directly."""
        path_index = PathIndex()
        path_index.add_point("src/auth.py", "auth_a1")

        with tempfile.TemporaryDirectory() as tmpdir:
            index_file = Path(tmpdir) / "path_index.bin"

            path_index.save(index_file)

            # Load directly with msgpack
            with open(index_file, "rb") as f:
                raw_data = msgpack.load(f)

            # Should be dict with str keys and list values (sets are serialized as lists)
            assert isinstance(raw_data, dict)
            assert "src/auth.py" in raw_data
            assert "auth_a1" in raw_data["src/auth.py"]

    def test_roundtrip_preserves_data_integrity(self):
        """Multiple save/load cycles should preserve data integrity."""
        path_index = PathIndex()
        path_index.add_point("src/auth.py", "auth_a1")
        path_index.add_point("src/utils.py", "utils_u1")

        with tempfile.TemporaryDirectory() as tmpdir:
            index_file = Path(tmpdir) / "path_index.bin"

            # First save/load cycle
            path_index.save(index_file)
            loaded_1 = PathIndex.load(index_file)

            # Modify and save again
            loaded_1.add_point("src/config.py", "config_c1")
            loaded_1.save(index_file)

            # Second load
            loaded_2 = PathIndex.load(index_file)

            assert loaded_2.get_point_ids("src/auth.py") == {"auth_a1"}
            assert loaded_2.get_point_ids("src/utils.py") == {"utils_u1"}
            assert loaded_2.get_point_ids("src/config.py") == {"config_c1"}


class TestPathIndexEdgeCases:
    """Test PathIndex edge cases and error handling."""

    def test_empty_file_path_is_valid(self):
        """Empty string as file_path should be handled gracefully."""
        path_index = PathIndex()

        path_index.add_point("", "point_x")
        assert path_index.get_point_ids("") == {"point_x"}

    def test_file_path_with_special_characters(self):
        """File paths with special characters should work."""
        path_index = PathIndex()

        special_paths = [
            "src/file with spaces.py",
            "src/file-with-dashes.py",
            "src/файл.py",  # Cyrillic
            "src/文件.py",  # Chinese
            "path/to/../relative/file.py",
        ]

        for i, file_path in enumerate(special_paths):
            point_id = f"point_{i}"
            path_index.add_point(file_path, point_id)
            assert path_index.get_point_ids(file_path) == {point_id}

    def test_point_id_with_special_characters(self):
        """Point IDs with special characters should work."""
        path_index = PathIndex()

        special_ids = [
            "point-with-dashes",
            "point_with_underscores",
            "point.with.dots",
            "point/with/slashes",
            "point:with:colons",
        ]

        for point_id in special_ids:
            path_index.add_point("src/auth.py", point_id)

        assert path_index.get_point_ids("src/auth.py") == set(special_ids)

    def test_large_number_of_files_and_points(self):
        """PathIndex should handle large number of files and points efficiently."""
        path_index = PathIndex()

        # Add 1000 files with 10 points each
        num_files = 1000
        points_per_file = 10

        for file_idx in range(num_files):
            file_path = f"src/file_{file_idx}.py"
            for point_idx in range(points_per_file):
                point_id = f"file{file_idx}_point{point_idx}"
                path_index.add_point(file_path, point_id)

        # Verify all files are present
        for file_idx in range(num_files):
            file_path = f"src/file_{file_idx}.py"
            point_ids = path_index.get_point_ids(file_path)
            assert len(point_ids) == points_per_file

        # Verify total internal state
        assert len(path_index._path_index) == num_files

    def test_concurrent_operations_thread_safety(self):
        """PathIndex operations should be thread-safe (if locks added in future)."""
        # NOTE: Current implementation is not thread-safe
        # This test documents expected behavior if thread safety is added later
        path_index = PathIndex()

        # For now, just test that basic operations work sequentially
        path_index.add_point("src/auth.py", "point_a1")
        path_index.add_point("src/auth.py", "point_a2")
        path_index.remove_point("src/auth.py", "point_a1")

        assert path_index.get_point_ids("src/auth.py") == {"point_a2"}

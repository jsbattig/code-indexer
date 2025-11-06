"""Tests for FilesystemVectorStore.load_id_index method."""


import pytest

from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestLoadIdIndex:
    """Tests for the public load_id_index method."""

    def test_load_id_index_returns_set_of_existing_ids(self, tmp_path):
        """Test that load_id_index returns a set of existing point IDs."""
        # Create a vector store
        index_dir = tmp_path / "index"
        vector_store = FilesystemVectorStore(base_path=index_dir, project_root=tmp_path)

        # Create a collection with some points
        collection_name = "test_collection"
        vector_store.create_collection(collection_name, 128)

        # Add some test points
        test_points = [
            {"id": "point1", "vector": [0.1] * 128, "payload": {"test": 1}},
            {"id": "point2", "vector": [0.2] * 128, "payload": {"test": 2}},
            {"id": "point3", "vector": [0.3] * 128, "payload": {"test": 3}},
        ]

        vector_store.upsert_points(collection_name, test_points)

        # Call the public method (this will fail initially as it doesn't exist)
        existing_ids = vector_store.load_id_index(collection_name)

        # Verify it returns a set of the IDs
        assert isinstance(existing_ids, set), "Should return a set"
        assert existing_ids == {"point1", "point2", "point3"}, "Should return all point IDs"

        # Verify empty collection returns empty set
        empty_collection = "empty_collection"
        vector_store.create_collection(empty_collection, 128)
        empty_ids = vector_store.load_id_index(empty_collection)
        assert empty_ids == set(), "Empty collection should return empty set"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
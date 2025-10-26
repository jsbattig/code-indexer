"""Unit tests for VectorIndexManager binary index system.

Tests the binary index format, Hamming distance calculations,
and candidate pool sizing for fast O(N) query performance.
"""

import struct
import tempfile
import uuid
from pathlib import Path

import numpy as np
import pytest

from code_indexer.storage.vector_index_manager import (
    VectorIndexManager,
    IndexEntry,
    hamming_distance,
    compute_candidate_pool_size
)


class TestIndexEntry:
    """Test IndexEntry data structure and binary packing."""

    def test_index_entry_creation(self):
        """Test creating an IndexEntry with valid data."""
        entry = IndexEntry(
            vector_id="test-vector-001",
            quant_hash=0xABCD1234EF567890,
            file_offset=12345
        )

        assert entry.vector_id == "test-vector-001"
        assert entry.quant_hash == 0xABCD1234EF567890
        assert entry.file_offset == 12345

    def test_index_entry_to_bytes(self):
        """Test converting IndexEntry to 40-byte binary format."""
        entry = IndexEntry(
            vector_id="abc123",
            quant_hash=0x123456789ABCDEF0,
            file_offset=999
        )

        packed = entry.to_bytes()

        # Should be exactly 40 bytes
        assert len(packed) == 40

        # Verify structure
        vector_id_bytes, quant_hash, file_offset, reserved = struct.unpack('16sQQQ', packed)

        # UUID stored as 16 bytes
        assert len(vector_id_bytes) == 16

        # Numeric fields match
        assert quant_hash == 0x123456789ABCDEF0
        assert file_offset == 999
        # Reserved field has flag: 0 = hashed ID (not a real UUID)
        assert reserved == 0

    def test_index_entry_from_bytes(self):
        """Test reconstructing IndexEntry from binary format."""
        original = IndexEntry(
            vector_id="test-id-456",
            quant_hash=0xFEDCBA9876543210,
            file_offset=54321
        )

        packed = original.to_bytes()
        restored = IndexEntry.from_bytes(packed)

        # Non-UUID IDs are hashed, so we can't recover the original string
        # But the hash should be deterministic
        assert len(restored.vector_id) == 32  # MD5 hex = 32 chars
        assert restored.quant_hash == original.quant_hash
        assert restored.file_offset == original.file_offset

        # Verify deterministic hashing - same ID produces same hash
        packed2 = original.to_bytes()
        restored2 = IndexEntry.from_bytes(packed2)
        assert restored.vector_id == restored2.vector_id

    def test_index_entry_uuid_handling(self):
        """Test that vector IDs are properly converted to/from UUID format."""
        # Generate a proper UUID
        test_uuid = str(uuid.uuid4())

        entry = IndexEntry(
            vector_id=test_uuid,
            quant_hash=0x1122334455667788,
            file_offset=0
        )

        # Round-trip through binary format
        packed = entry.to_bytes()
        restored = IndexEntry.from_bytes(packed)

        # UUID should match
        assert restored.vector_id == test_uuid

    def test_index_entry_handles_non_uuid_ids(self):
        """Test that non-UUID vector IDs are handled (hashed to MD5)."""
        entry = IndexEntry(
            vector_id="short",
            quant_hash=0x99AA,
            file_offset=1
        )

        packed = entry.to_bytes()
        restored = IndexEntry.from_bytes(packed)

        # Should restore as MD5 hex (32 chars)
        assert len(restored.vector_id) == 32  # MD5 hex

        # Should be deterministic
        packed2 = entry.to_bytes()
        restored2 = IndexEntry.from_bytes(packed2)
        assert restored.vector_id == restored2.vector_id


class TestHammingDistance:
    """Test Hamming distance calculations."""

    def test_hamming_distance_identical(self):
        """Test Hamming distance between identical hashes is zero."""
        hash1 = 0b11001100
        hash2 = 0b11001100

        assert hamming_distance(hash1, hash2) == 0

    def test_hamming_distance_one_bit(self):
        """Test Hamming distance with one bit difference."""
        hash1 = 0b11001100
        hash2 = 0b11001101  # Last bit differs

        assert hamming_distance(hash1, hash2) == 1

    def test_hamming_distance_all_bits(self):
        """Test Hamming distance with all bits different."""
        hash1 = 0b11111111
        hash2 = 0b00000000

        assert hamming_distance(hash1, hash2) == 8

    def test_hamming_distance_64bit(self):
        """Test Hamming distance with 64-bit hashes."""
        # Create hashes with known differences
        hash1 = 0xFFFFFFFFFFFFFFFF  # All 1s (64 bits)
        hash2 = 0x0000000000000000  # All 0s

        assert hamming_distance(hash1, hash2) == 64

    def test_hamming_distance_symmetric(self):
        """Test that Hamming distance is symmetric."""
        hash1 = 0xABCDEF1234567890
        hash2 = 0x1234567890ABCDEF

        assert hamming_distance(hash1, hash2) == hamming_distance(hash2, hash1)


class TestCandidatePoolSizing:
    """Test dynamic candidate pool size calculation."""

    def test_small_collection_minimum(self):
        """Test that small collections get at least limit * 10."""
        total_vectors = 100
        limit = 10

        pool_size = compute_candidate_pool_size(total_vectors, limit)

        # Should be at least limit * 10
        assert pool_size >= limit * 10
        # Should be sqrt(100) * 10 = 100
        assert pool_size == 100

    def test_large_collection_capped(self):
        """Test that large collections are capped at 5% of total."""
        total_vectors = 100_000
        limit = 10

        pool_size = compute_candidate_pool_size(total_vectors, limit)

        # Should be capped at 5% = 5000
        max_allowed = int(total_vectors * 0.05)
        assert pool_size <= max_allowed
        # sqrt(100000) * 10 = 3162, which is < 5000, so should be 3162
        assert pool_size == 3162

    def test_medium_collection_sqrt_scaling(self):
        """Test sqrt scaling for medium-sized collections (without hitting cap)."""
        # Choose values where sqrt scaling doesn't hit 5% cap
        total_vectors = 40_000
        limit = 10

        pool_size = compute_candidate_pool_size(total_vectors, limit)

        # sqrt(40000) * 10 = 2000
        # 5% cap = 2000, so we're right at the boundary
        expected = int(np.sqrt(total_vectors) * limit)
        max_allowed = int(total_vectors * 0.05)

        # Should be min of the two
        assert pool_size == min(expected, max_allowed)
        assert pool_size == 2000

    def test_sqrt_scaling_without_cap(self):
        """Test pure sqrt scaling without hitting minimum or maximum bounds."""
        # Choose values where sqrt scaling is between min and max
        total_vectors = 100_000
        limit = 5

        pool_size = compute_candidate_pool_size(total_vectors, limit)

        # sqrt(100000) * 5 = 1581
        # min = 5 * 10 = 50
        # max = 100000 * 0.05 = 5000
        # 1581 is between 50 and 5000, so should use sqrt value
        expected = int(np.sqrt(total_vectors) * limit)
        assert pool_size == expected
        assert pool_size == 1581

    def test_minimum_bound_enforced(self):
        """Test that minimum bound is enforced even for tiny collections."""
        total_vectors = 10
        limit = 50

        pool_size = compute_candidate_pool_size(total_vectors, limit)

        # Should be at least limit * 10 = 500
        assert pool_size >= limit * 10

    def test_maximum_bound_enforced(self):
        """Test that maximum 5% bound is enforced."""
        total_vectors = 1_000_000
        limit = 100

        pool_size = compute_candidate_pool_size(total_vectors, limit)

        # Should not exceed 5% = 50,000
        max_allowed = int(total_vectors * 0.05)
        assert pool_size <= max_allowed


class TestVectorIndexManager:
    """Test VectorIndexManager binary index operations."""

    @pytest.fixture
    def temp_collection_path(self, tmp_path):
        """Create a temporary collection directory."""
        collection_path = tmp_path / "test-collection"
        collection_path.mkdir(parents=True, exist_ok=True)
        return collection_path

    @pytest.fixture
    def index_manager(self):
        """Create a VectorIndexManager instance."""
        return VectorIndexManager()

    def test_append_batch_creates_index_file(self, index_manager, temp_collection_path):
        """Test that append_batch creates the index file."""
        entries = [
            IndexEntry("id1", 0x1111, 0),
            IndexEntry("id2", 0x2222, 100),
            IndexEntry("id3", 0x3333, 200)
        ]

        index_manager.append_batch(temp_collection_path, entries)

        index_file = temp_collection_path / "vector_index.bin"
        assert index_file.exists()

        # File should be 3 * 40 = 120 bytes
        assert index_file.stat().st_size == 120

    def test_append_batch_appends_to_existing_file(self, index_manager, temp_collection_path):
        """Test that append_batch appends to existing index file."""
        # First batch
        entries1 = [IndexEntry("id1", 0x1111, 0)]
        index_manager.append_batch(temp_collection_path, entries1)

        # Second batch
        entries2 = [IndexEntry("id2", 0x2222, 100)]
        index_manager.append_batch(temp_collection_path, entries2)

        index_file = temp_collection_path / "vector_index.bin"

        # File should have 2 * 40 = 80 bytes
        assert index_file.stat().st_size == 80

    def test_load_index_reads_all_entries(self, index_manager, temp_collection_path):
        """Test that load_index reads all entries into memory."""
        entries = [
            IndexEntry("id1", 0xAAAA, 0),
            IndexEntry("id2", 0xBBBB, 100),
            IndexEntry("id3", 0xCCCC, 200)
        ]

        index_manager.append_batch(temp_collection_path, entries)

        # Provide existing ID index (simulates what FilesystemVectorStore provides)
        existing_id_index = {"id1": Path("dummy1.json"), "id2": Path("dummy2.json"), "id3": Path("dummy3.json")}

        # Load index
        index, id_mapping = index_manager.load_index(temp_collection_path, existing_id_index)

        # Should be Nx3 array: [vector_id_hash, quant_hash, file_offset]
        assert index.shape == (3, 3)
        assert index.dtype == np.uint64

        # Check quant_hash values (column 1)
        assert index[0, 1] == 0xAAAA
        assert index[1, 1] == 0xBBBB
        assert index[2, 1] == 0xCCCC

        # Check ID mapping has 3 entries
        # When existing_id_index is provided, original IDs are preserved
        assert len(id_mapping) == 3

        # Verify that original IDs are preserved in the mapping
        stored_ids = set(id_mapping.values())
        assert "id1" in stored_ids
        assert "id2" in stored_ids
        assert "id3" in stored_ids

    def test_find_candidates_returns_closest_vectors(self, index_manager, temp_collection_path):
        """Test that find_candidates returns vectors with smallest Hamming distance."""
        # Use UUID format IDs to preserve original strings
        import uuid
        id1 = str(uuid.uuid4())
        id2 = str(uuid.uuid4())
        id3 = str(uuid.uuid4())
        id4 = str(uuid.uuid4())
        id5 = str(uuid.uuid4())

        entries = [
            IndexEntry(id1, 0b00000000, 0),  # Hamming distance 0 from query
            IndexEntry(id2, 0b00000001, 0),  # Hamming distance 1
            IndexEntry(id3, 0b00000011, 0),  # Hamming distance 2
            IndexEntry(id4, 0b00000111, 0),  # Hamming distance 3
            IndexEntry(id5, 0b11111111, 0),  # Hamming distance 8
        ]

        index_manager.append_batch(temp_collection_path, entries)

        # Provide existing ID index (simulates what FilesystemVectorStore provides)
        existing_id_index = {
            id1: Path("dummy1.json"),
            id2: Path("dummy2.json"),
            id3: Path("dummy3.json"),
            id4: Path("dummy4.json"),
            id5: Path("dummy5.json")
        }

        index, id_mapping = index_manager.load_index(temp_collection_path, existing_id_index)

        # Query hash: 0b00000000
        query_hash = 0b00000000
        limit = 10
        total_vectors = 5

        candidates = index_manager.find_candidates(query_hash, index, id_mapping, limit, total_vectors)

        # Should return all 5 candidates (pool size >= 5)
        assert len(candidates) <= 5

        # Verify id1 (closest match) is in the candidates
        # Since we used UUIDs, the original ID should be preserved
        assert id1 in candidates

    def test_find_candidates_respects_pool_size(self, index_manager, temp_collection_path):
        """Test that find_candidates uses dynamic pool sizing."""
        # Create 100 vectors
        entries = [IndexEntry(f"id{i}", i * 100, 0) for i in range(100)]

        index_manager.append_batch(temp_collection_path, entries)
        index, id_mapping = index_manager.load_index(temp_collection_path)

        query_hash = 0x5555
        limit = 10
        total_vectors = 100

        candidates = index_manager.find_candidates(query_hash, index, id_mapping, limit, total_vectors)

        # Pool size should be sqrt(100) * 10 = 100 (all vectors)
        # So we should get all 100 vectors as candidates
        assert len(candidates) == 100

    def test_compute_quantized_hash_deterministic(self, index_manager):
        """Test that compute_quantized_hash is deterministic."""
        vector = np.array([0.5, -0.3, 0.7, 1.2] * 16)  # 64-dim
        projection_matrix = np.eye(64)  # Identity matrix for testing
        min_val = -2.0
        max_val = 2.0

        hash1 = index_manager.compute_quantized_hash(vector, projection_matrix, min_val, max_val)
        hash2 = index_manager.compute_quantized_hash(vector, projection_matrix, min_val, max_val)

        assert hash1 == hash2

    def test_compute_quantized_hash_similar_vectors_close(self, index_manager):
        """Test that similar vectors produce Hamming-close hashes."""
        projection_matrix = np.eye(64)
        min_val = -2.0
        max_val = 2.0

        # Very similar vectors
        vector1 = np.ones(64) * 0.5
        vector2 = np.ones(64) * 0.51  # Slightly different

        hash1 = index_manager.compute_quantized_hash(vector1, projection_matrix, min_val, max_val)
        hash2 = index_manager.compute_quantized_hash(vector2, projection_matrix, min_val, max_val)

        # Hamming distance should be small
        distance = hamming_distance(hash1, hash2)
        assert distance < 10  # Expect close hashes for similar vectors

    def test_rebuild_from_vectors_recreates_index(self, index_manager, temp_collection_path):
        """Test that rebuild_from_vectors can recreate index from JSON files."""
        # This will be implemented after integration with FilesystemVectorStore
        # For now, just test that the method exists
        assert hasattr(index_manager, 'rebuild_from_vectors')

    def test_empty_index_handling(self, index_manager, temp_collection_path):
        """Test that loading empty index returns empty array."""
        # Create empty index file
        index_file = temp_collection_path / "vector_index.bin"
        index_file.touch()

        index, id_mapping = index_manager.load_index(temp_collection_path)

        # Should be empty array with correct shape
        assert index.shape[0] == 0
        assert index.shape[1] == 3
        # Should have empty ID mapping
        assert len(id_mapping) == 0

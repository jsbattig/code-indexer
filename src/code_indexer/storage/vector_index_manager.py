"""Binary index manager for fast vector search in filesystem storage.

Implements compact binary index with Hamming distance-based candidate selection
for O(N) query performance instead of loading all JSON files.
"""

import hashlib
import struct
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict

import numpy as np


@dataclass
class IndexEntry:
    """Single index record for a vector.

    Binary format (40 bytes):
    - vector_id: 16 bytes (UUID as bytes)
    - quant_hash: 8 bytes (uint64, 2-bit quantization hash)
    - file_offset: 8 bytes (uint64, for future use)
    - reserved: 8 bytes (uint64, future expansion)
    """
    vector_id: str
    quant_hash: int
    file_offset: int

    def to_bytes(self) -> bytes:
        """Convert entry to 40-byte binary format.

        Format uses reserved field's lowest byte as a flag:
        - Bit 0: 1 = real UUID, 0 = hashed ID string

        Returns:
            40 bytes of packed binary data
        """
        # Convert vector_id to 16-byte representation
        # Check if it's a properly formatted UUID (with dashes), not just a hex string
        is_uuid = False
        try:
            # Only treat as UUID if it contains dashes (proper UUID format)
            # This prevents MD5 hashes (32 hex chars) from being parsed as UUIDs
            if '-' in self.vector_id:
                vector_id_bytes = uuid.UUID(self.vector_id).bytes
                is_uuid = True
            elif len(self.vector_id) == 32 and all(c in '0123456789abcdef' for c in self.vector_id.lower()):
                # MD5 hash string (32 hex chars) - convert directly to bytes without hashing again
                vector_id_bytes = bytes.fromhex(self.vector_id)
            else:
                # Arbitrary string - create deterministic 16-byte hash
                hash_obj = hashlib.md5(self.vector_id.encode('utf-8'))
                vector_id_bytes = hash_obj.digest()
        except ValueError:
            # Not a valid format - create deterministic 16-byte hash
            hash_obj = hashlib.md5(self.vector_id.encode('utf-8'))
            vector_id_bytes = hash_obj.digest()

        # Set flag in reserved field (bit 0 = is_uuid, bit 1 = is_md5_hash)
        # reserved = 0: arbitrary string (hashed with MD5)
        # reserved = 1: UUID format
        # reserved = 2: MD5 hash string (stored as-is)
        if is_uuid:
            reserved = 1
        elif len(self.vector_id) == 32 and all(c in '0123456789abcdef' for c in self.vector_id.lower()):
            reserved = 2  # MD5 hash
        else:
            reserved = 0  # Hashed arbitrary string

        # Pack into binary format: 16s (bytes) + 3 * Q (uint64)
        packed = struct.pack(
            '16sQQQ',
            vector_id_bytes,
            self.quant_hash,
            self.file_offset,
            reserved
        )

        return packed

    @staticmethod
    def from_bytes(data: bytes) -> 'IndexEntry':
        """Reconstruct IndexEntry from binary format.

        Args:
            data: 40 bytes of packed binary data

        Returns:
            IndexEntry instance
        """
        if len(data) != 40:
            raise ValueError(f"Expected 40 bytes, got {len(data)}")

        # Unpack binary format
        vector_id_bytes, quant_hash, file_offset, reserved = struct.unpack('16sQQQ', data)

        # Check flag to determine how to reconstruct ID
        if reserved == 1:
            # UUID format
            vector_id = str(uuid.UUID(bytes=vector_id_bytes))
        elif reserved == 2:
            # MD5 hash string - convert bytes back to hex string
            vector_id = vector_id_bytes.hex()
        else:
            # Hashed arbitrary string - we can't recover the original string
            # Store as hex for now (will need ID mapping in real implementation)
            vector_id = vector_id_bytes.hex()

        return IndexEntry(
            vector_id=vector_id,
            quant_hash=quant_hash,
            file_offset=file_offset
        )


def hamming_distance(hash1: int, hash2: int) -> int:
    """Compute Hamming distance between two 64-bit hashes.

    Args:
        hash1: First 64-bit hash
        hash2: Second 64-bit hash

    Returns:
        Number of differing bits
    """
    # XOR to find differing bits, count 1s
    xor = hash1 ^ hash2
    return bin(xor).count('1')


def compute_candidate_pool_size(total_vectors: int, limit: int) -> int:
    """Compute dynamic candidate pool size using sqrt scaling.

    Formula:
    - Base: sqrt(N) * limit
    - Minimum: limit * 10
    - Maximum: N * 0.05 (5% of collection)

    Args:
        total_vectors: Total number of vectors in collection
        limit: Requested result limit

    Returns:
        Number of candidates to load from index
    """
    # Base calculation: sqrt scaling
    candidates = int(np.sqrt(total_vectors) * limit)

    # Apply bounds
    min_candidates = limit * 10
    max_candidates = int(total_vectors * 0.05)

    return max(min_candidates, min(candidates, max_candidates))


class VectorIndexManager:
    """Manages binary index for fast vector search.

    Provides:
    - Incremental index building during upsert
    - Fast in-memory index loading
    - Hamming distance-based candidate selection
    - Index rebuild from JSON files
    """

    INDEX_FILENAME = "vector_index.bin"
    RECORD_SIZE = 40  # bytes per index entry

    def __init__(self):
        """Initialize VectorIndexManager."""
        pass

    def append_batch(self, collection_path: Path, entries: List[IndexEntry]) -> None:
        """Append batch of index entries to binary index file.

        Args:
            collection_path: Path to collection directory
            entries: List of IndexEntry objects to append
        """
        index_file = collection_path / self.INDEX_FILENAME

        # Open in append mode, create if doesn't exist
        with open(index_file, 'ab') as f:
            for entry in entries:
                f.write(entry.to_bytes())

    def load_index(
        self,
        collection_path: Path,
        existing_id_index: Optional[Dict[str, Path]] = None
    ) -> tuple[np.ndarray, Dict[int, str]]:
        """Load entire index into memory as numpy array with ID mapping.

        Args:
            collection_path: Path to collection directory
            existing_id_index: Optional pre-built ID index (point_id -> file_path mapping)
                             to avoid scanning JSON files

        Returns:
            Tuple of (index_array, id_mapping) where:
            - index_array: Nx3 numpy array with [vector_id_hash, quant_hash, file_offset]
            - id_mapping: Dict mapping vector_id_hash to original vector_id string
        """
        index_file = collection_path / self.INDEX_FILENAME

        if not index_file.exists():
            # Return empty array and empty mapping
            return np.zeros((0, 3), dtype=np.uint64), {}

        file_size = index_file.stat().st_size

        if file_size == 0:
            return np.zeros((0, 3), dtype=np.uint64), {}

        # Calculate number of records
        num_records = file_size // self.RECORD_SIZE

        # Read all records from binary index
        entries = []

        with open(index_file, 'rb') as f:
            for _ in range(num_records):
                record_bytes = f.read(self.RECORD_SIZE)
                if len(record_bytes) < self.RECORD_SIZE:
                    break  # Incomplete record at end

                entry = IndexEntry.from_bytes(record_bytes)

                # Hash the vector_id to uint64 for array storage
                id_hash = self._hash_vector_id(entry.vector_id)

                entries.append([id_hash, entry.quant_hash, entry.file_offset])

        # Build ID mapping
        id_mapping = {}

        if existing_id_index is not None:
            # Use existing ID index (fast path - O(N) where N is number of points)
            for point_id in existing_id_index.keys():
                id_hash = self._hash_vector_id(point_id)
                id_mapping[id_hash] = point_id
        else:
            # Scan JSON files to build mapping (slow path - requires file I/O)
            import json
            for vector_file in collection_path.rglob('vector_*.json'):
                try:
                    with open(vector_file) as f:
                        data = json.load(f)
                        point_id = data['id']
                        id_hash = self._hash_vector_id(point_id)
                        id_mapping[id_hash] = point_id
                except (json.JSONDecodeError, KeyError):
                    continue

        # Convert to numpy array
        if entries:
            return np.array(entries, dtype=np.uint64), id_mapping
        else:
            return np.zeros((0, 3), dtype=np.uint64), {}

    def find_candidates(
        self,
        query_hash: int,
        index: np.ndarray,
        id_mapping: dict,
        limit: int,
        total_vectors: int
    ) -> List[str]:
        """Find candidate vectors using Hamming distance.

        Args:
            query_hash: Quantized hash of query vector
            index: Loaded index array (Nx3)
            id_mapping: Mapping from vector_id_hash to original vector_id
            limit: Requested result limit
            total_vectors: Total number of vectors in collection

        Returns:
            List of vector IDs to load as candidates
        """
        if index.shape[0] == 0:
            return []

        # Compute pool size
        pool_size = compute_candidate_pool_size(total_vectors, limit)
        pool_size = min(pool_size, index.shape[0])  # Can't exceed available vectors

        # Extract quant_hash column (column 1)
        quant_hashes = index[:, 1]

        # Vectorized Hamming distance computation
        distances = self._vectorized_hamming_distance(query_hash, quant_hashes)

        # Get top-k smallest distances
        if pool_size >= len(distances):
            # Return all indices
            top_k_indices = np.arange(len(distances))
        else:
            # Use argpartition for efficient top-k selection
            top_k_indices = np.argpartition(distances, pool_size)[:pool_size]

        # Sort by distance (smallest first)
        sorted_indices = top_k_indices[np.argsort(distances[top_k_indices])]

        # Extract vector ID hashes and convert back to original IDs
        id_hashes = index[sorted_indices, 0]

        # Convert hashes back to original vector IDs using mapping
        vector_ids = [id_mapping.get(int(id_hash), f"{id_hash:016x}") for id_hash in id_hashes]

        return vector_ids

    def compute_quantized_hash(
        self,
        vector: np.ndarray,
        projection_matrix: np.ndarray,
        min_val: float,
        max_val: float
    ) -> int:
        """Compute 64-bit quantized hash from vector.

        Args:
            vector: Input vector (high-dimensional)
            projection_matrix: Projection matrix for dimensionality reduction
            min_val: Minimum value for quantization range
            max_val: Maximum value for quantization range

        Returns:
            64-bit hash representing quantized vector
        """
        # Project to reduced dimensions
        reduced = vector @ projection_matrix

        # Quantize to 2-bit values (0, 1, 2, 3)
        quantized = self._quantize_to_2bit(reduced, min_val, max_val)

        # Pack into 64-bit hash
        # 64 dimensions * 2 bits = 128 bits, but we only use 64 bits
        # Pack first 32 dimensions into 64-bit hash
        hash_val = 0
        for i in range(32):
            # Each dimension contributes 2 bits
            hash_val = (hash_val << 2) | int(quantized[i])

        return hash_val

    def rebuild_from_vectors(self, collection_path: Path) -> None:
        """Rebuild index from existing vector JSON files.

        Args:
            collection_path: Path to collection directory
        """
        import json
        from .projection_matrix_manager import ProjectionMatrixManager

        # Load projection matrix
        matrix_manager = ProjectionMatrixManager()
        projection_matrix = matrix_manager.load_matrix(collection_path)

        if projection_matrix is None:
            raise RuntimeError(f"No projection matrix found for collection at {collection_path}")

        # Load quantization range from metadata
        metadata_path = collection_path / 'collection_meta.json'
        if not metadata_path.exists():
            raise FileNotFoundError(f"Collection metadata not found at {metadata_path}")

        with open(metadata_path) as f:
            metadata = json.load(f)
            min_val = metadata['quantization_range']['min']
            max_val = metadata['quantization_range']['max']

        # Delete old index if exists
        index_file = collection_path / self.INDEX_FILENAME
        if index_file.exists():
            index_file.unlink()

        # Scan all vector JSON files
        entries = []
        for vector_file in collection_path.rglob('vector_*.json'):
            try:
                with open(vector_file) as f:
                    data = json.load(f)

                vector = np.array(data['vector'])
                point_id = data['id']

                # Project vector to reduced dimensions
                reduced = vector @ projection_matrix

                # Compute quantized hash using identity matrix (already projected)
                quant_hash = self.compute_quantized_hash(
                    vector=reduced,
                    projection_matrix=np.eye(64, dtype=np.float32),
                    min_val=min_val,
                    max_val=max_val
                )

                entries.append(IndexEntry(
                    vector_id=point_id,
                    quant_hash=quant_hash,
                    file_offset=0
                ))

                # Write in batches to avoid memory issues
                if len(entries) >= 1000:
                    self.append_batch(collection_path, entries)
                    entries = []

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                # Skip malformed files
                continue

        # Write remaining entries
        if entries:
            self.append_batch(collection_path, entries)

    def _quantize_to_2bit(
        self,
        vector: np.ndarray,
        min_val: float,
        max_val: float
    ) -> np.ndarray:
        """Quantize vector to 2-bit representation.

        Args:
            vector: Float vector to quantize
            min_val: Minimum value for quantization range
            max_val: Maximum value for quantization range

        Returns:
            Array of uint8 values in {0, 1, 2, 3}
        """
        # Clip values to range
        clipped = np.clip(vector, min_val, max_val)

        # Map [min_val, max_val] → [0, 3.999] → int [0, 3]
        range_size = max_val - min_val
        normalized = (clipped - min_val) / range_size  # [0, 1]
        quantized = (normalized * 3.999).astype(np.uint8)  # [0, 3]

        # Ensure values are in valid range
        return np.clip(quantized, 0, 3)

    def _vectorized_hamming_distance(
        self,
        query_hash: int,
        stored_hashes: np.ndarray
    ) -> np.ndarray:
        """Compute Hamming distance between query and all stored hashes.

        Args:
            query_hash: Single query hash
            stored_hashes: Array of stored hashes

        Returns:
            Array of Hamming distances
        """
        # XOR with query hash
        xors = np.bitwise_xor(stored_hashes, query_hash)

        # Count bits in each XOR result
        # Convert to bytes and count 1s
        distances = np.zeros(len(xors), dtype=np.uint8)
        for i, xor_val in enumerate(xors):
            distances[i] = bin(int(xor_val)).count('1')

        return distances

    def _hash_vector_id(self, vector_id: str) -> int:
        """Hash vector ID string to uint64.

        Args:
            vector_id: Vector ID string

        Returns:
            64-bit hash of the ID
        """
        # Use MD5 hash and take first 8 bytes as uint64
        hash_obj = hashlib.md5(vector_id.encode('utf-8'))
        hash_bytes = hash_obj.digest()[:8]
        result: int = struct.unpack('Q', hash_bytes)[0]
        return result

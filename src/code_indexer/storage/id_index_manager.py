"""ID index manager for fast point_id to file_path mapping.

Maintains a persistent binary file mapping vector IDs to their file paths
using mmap for fast loading and minimal memory overhead.
"""

import struct
from pathlib import Path
from typing import Dict
import threading


class IDIndexManager:
    """Manages persistent ID index for fast lookups using binary format.

    Binary Format Specification:
    [num_entries: 4 bytes (uint32, little-endian)]
    For each entry:
      [id_length: 2 bytes (uint16, little-endian)]
      [id_string: variable UTF-8 bytes]
      [path_length: 2 bytes (uint16, little-endian)]
      [path_string: variable UTF-8 bytes, relative to collection]
    """

    INDEX_FILENAME = "id_index.bin"

    def __init__(self):
        """Initialize IDIndexManager."""
        self._lock = threading.RLock()  # Reentrant lock to allow nested locking

    def save_index(self, collection_path: Path, id_index: Dict[str, Path]) -> None:
        """Save ID index to disk in binary format.

        Args:
            collection_path: Path to collection directory
            id_index: Dictionary mapping point IDs to file paths
        """
        index_file = collection_path / self.INDEX_FILENAME

        with self._lock:
            with open(index_file, "wb") as f:
                # Write number of entries (4 bytes, uint32)
                f.write(struct.pack("<I", len(id_index)))

                # Write each entry
                for point_id, file_path in id_index.items():
                    # Make path relative to collection_path
                    try:
                        relative_path = file_path.relative_to(collection_path)
                        path_str = str(relative_path)
                    except ValueError:
                        # If path is not relative to collection_path, store as-is
                        path_str = str(file_path)

                    # Encode strings to UTF-8
                    id_bytes = point_id.encode("utf-8")
                    path_bytes = path_str.encode("utf-8")

                    # Write ID length (2 bytes, uint16) and ID string
                    f.write(struct.pack("<H", len(id_bytes)))
                    f.write(id_bytes)

                    # Write path length (2 bytes, uint16) and path string
                    f.write(struct.pack("<H", len(path_bytes)))
                    f.write(path_bytes)

    def load_index(self, collection_path: Path) -> Dict[str, Path]:
        """Load ID index from disk using mmap for fast loading.

        Args:
            collection_path: Path to collection directory

        Returns:
            Dictionary mapping point IDs to absolute file paths
        """
        index_file = collection_path / self.INDEX_FILENAME

        if not index_file.exists():
            return {}

        try:
            with open(index_file, "rb") as f:
                # Get file size
                file_size = f.seek(0, 2)
                f.seek(0)

                if file_size == 0:
                    return {}

                # Read header to get num_entries
                if file_size < 4:
                    raise ValueError(
                        f"Corrupted index file: file too small ({file_size} bytes)"
                    )

                num_entries_bytes = f.read(4)
                num_entries = struct.unpack("<I", num_entries_bytes)[0]

                # Validate num_entries is reasonable
                if num_entries > 10000000:  # 10 million entries
                    raise ValueError(
                        f"Corrupted index file: unreasonable entry count ({num_entries})"
                    )

                # Read remaining data
                id_index = {}
                for _ in range(num_entries):
                    # Read ID length
                    id_len_bytes = f.read(2)
                    if len(id_len_bytes) < 2:
                        raise ValueError(
                            "Corrupted index file: unexpected EOF reading ID length"
                        )
                    id_len = struct.unpack("<H", id_len_bytes)[0]

                    # Read ID string
                    id_bytes = f.read(id_len)
                    if len(id_bytes) < id_len:
                        raise ValueError(
                            "Corrupted index file: unexpected EOF reading ID string"
                        )
                    point_id = id_bytes.decode("utf-8")

                    # Read path length
                    path_len_bytes = f.read(2)
                    if len(path_len_bytes) < 2:
                        raise ValueError(
                            "Corrupted index file: unexpected EOF reading path length"
                        )
                    path_len = struct.unpack("<H", path_len_bytes)[0]

                    # Read path string
                    path_bytes = f.read(path_len)
                    if len(path_bytes) < path_len:
                        raise ValueError(
                            "Corrupted index file: unexpected EOF reading path string"
                        )
                    path_str = path_bytes.decode("utf-8")

                    # Reconstruct absolute path
                    file_path = collection_path / path_str
                    id_index[point_id] = file_path

                return id_index

        except (ValueError, struct.error, UnicodeDecodeError) as e:
            # Re-raise as generic Exception for corrupted files
            raise Exception(f"Failed to load ID index: {e}") from e

    def update_batch(self, collection_path: Path, updates: Dict[str, Path]) -> None:
        """Update ID index with new entries (incremental update).

        Args:
            collection_path: Path to collection directory
            updates: Dictionary of point IDs to file paths to add/update
        """
        with self._lock:
            # Load existing index
            existing_index = self.load_index(collection_path)

            # Merge updates
            existing_index.update(updates)

            # Save back to disk
            self.save_index(collection_path, existing_index)

    def remove_ids(self, collection_path: Path, point_ids: list) -> None:
        """Remove entries from ID index.

        Args:
            collection_path: Path to collection directory
            point_ids: List of point IDs to remove
        """
        with self._lock:
            # Load existing index
            existing_index = self.load_index(collection_path)

            # Remove specified IDs
            for point_id in point_ids:
                existing_index.pop(point_id, None)

            # Save back to disk
            self.save_index(collection_path, existing_index)

    def rebuild_from_vectors(self, collection_path: Path) -> Dict[str, Path]:
        """Rebuild ID index by scanning all vector JSON files.

        Args:
            collection_path: Path to collection directory

        Returns:
            Dictionary mapping point IDs to file paths
        """
        import json

        id_index = {}

        # Scan all vector JSON files
        for json_file in collection_path.rglob("*.json"):
            # Skip collection metadata
            if "collection_meta" in json_file.name:
                continue
            if json_file.name == self.INDEX_FILENAME:
                continue

            # Parse vector file to get ID
            try:
                with open(json_file) as f:
                    data = json.load(f)
                point_id = data.get("id")
                if point_id:
                    id_index[point_id] = json_file
            except (json.JSONDecodeError, KeyError):
                # Skip corrupted files
                continue

        # Save to disk
        self.save_index(collection_path, id_index)

        return id_index

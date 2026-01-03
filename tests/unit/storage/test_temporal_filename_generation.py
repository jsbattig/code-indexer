"""Unit tests for temporal collection filename generation (Story #669).

Tests v2 format hash-based filename generation to fix filesystem 255-character limit issues.
"""

import hashlib
import tempfile
from pathlib import Path
import pytest

from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestTemporalFilenameGeneration:
    """Test hash-based filename generation for temporal collections (v2 format)."""

    def test_generate_filename_v2_format_for_temporal_collection(self):
        """AC2: Temporal collections use v2 format (16-char SHA256 hash prefix)."""
        # Given: A point_id that would exceed 255 characters in v1 format
        long_file_path = "A" * 200  # 200-char file path
        point_id = f"project:diff:646986fd:{long_file_path}:2"

        # When: Generating filename for temporal collection
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemVectorStore(base_path=Path(tmpdir))

            # Calculate expected hash prefix (16-char SHA256 prefix)
            expected_hash = hashlib.sha256(point_id.encode()).hexdigest()[:16]
            expected_filename = f"vector_{expected_hash}.json"

            # Create temporal collection
            store.create_collection("code-indexer-temporal", vector_size=1024)

            # Upsert point to trigger filename generation
            point = {
                "id": point_id,
                "vector": [0.1] * 1024,
                "payload": {"path": long_file_path, "commit_hash": "646986fd"},
                "chunk_text": "test content"
            }
            store.upsert_points("code-indexer-temporal", [point])

            # Then: Filename should be hash-based (v2 format)
            # Find the generated file
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            vector_files = list(collection_path.rglob("vector_*.json"))

            assert len(vector_files) == 1, f"Expected 1 vector file, found {len(vector_files)}"
            actual_filename = vector_files[0].name

            assert actual_filename == expected_filename, (
                f"Expected v2 format filename '{expected_filename}', "
                f"got '{actual_filename}'"
            )

            # Verify filename length is under 255 characters
            assert len(actual_filename) < 255, (
                f"Filename '{actual_filename}' exceeds 255 character limit"
            )

            # Verify filename is exactly 28 characters (vector_ + 16 hex + .json)
            assert len(actual_filename) == 28, (
                f"V2 format filename should be 28 chars, got {len(actual_filename)}"
            )

    def test_hash_determinism_same_point_id_produces_same_hash(self):
        """AC2: Same point_id always produces same hash prefix (deterministic)."""
        # Given: The same point_id used twice
        point_id = "project:diff:abc123:path/to/file.py:0"

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemVectorStore(base_path=Path(tmpdir))
            store.create_collection("code-indexer-temporal", vector_size=1024)

            # When: Upserting the same point twice
            point = {
                "id": point_id,
                "vector": [0.1] * 1024,
                "payload": {"path": "path/to/file.py"},
                "chunk_text": "content"
            }

            # First upsert
            store.upsert_points("code-indexer-temporal", [point])
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            files_after_first = list(collection_path.rglob("vector_*.json"))

            # Second upsert (should update same file, not create new one)
            store.upsert_points("code-indexer-temporal", [point])
            files_after_second = list(collection_path.rglob("vector_*.json"))

            # Then: Same filename should be used both times (deterministic hash)
            assert len(files_after_first) == 1, "First upsert should create 1 file"
            assert len(files_after_second) == 1, "Second upsert should not create duplicate"
            assert files_after_first[0] == files_after_second[0], (
                "Same point_id should produce same filename (deterministic hash)"
            )

    def test_non_temporal_collection_uses_original_format(self):
        """Non-temporal collections should continue using original filename format."""
        # Given: A non-temporal collection (default collection)
        point_id = "simple_id"

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemVectorStore(base_path=Path(tmpdir))
            store.create_collection("default", vector_size=1024)

            # When: Upserting to non-temporal collection
            point = {
                "id": point_id,
                "vector": [0.1] * 1024,
                "payload": {"path": "file.py"},
                "chunk_text": "content"
            }
            store.upsert_points("default", [point])

            # Then: Filename should use original format (not hash-based)
            collection_path = Path(tmpdir) / "default"
            vector_files = list(collection_path.rglob("vector_*.json"))

            assert len(vector_files) == 1
            actual_filename = vector_files[0].name

            # Original format: vector_{point_id}.json with slashes replaced
            expected_filename = f"vector_{point_id.replace('/', '_')}.json"
            assert actual_filename == expected_filename, (
                f"Non-temporal collection should use original format, "
                f"expected '{expected_filename}', got '{actual_filename}'"
            )

    def test_extremely_long_point_id_stays_under_255_chars(self):
        """AC1: Filenames must stay under 255 characters even with very long point_ids."""
        # Given: An extremely long point_id (300+ characters)
        long_path = "deeply/nested/" + "subdirectory/" * 20 + "VeryLongFileName.cs"
        point_id = f"project-id-here:diff:commit-hash-here:{long_path}:999"

        assert len(point_id) > 255, f"Test setup: point_id should exceed 255 chars, got {len(point_id)}"

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemVectorStore(base_path=Path(tmpdir))
            store.create_collection("code-indexer-temporal", vector_size=1024)

            # When: Upserting point with extremely long ID
            point = {
                "id": point_id,
                "vector": [0.1] * 1024,
                "payload": {"path": long_path},
                "chunk_text": "content"
            }
            store.upsert_points("code-indexer-temporal", [point])

            # Then: Filename must be under 255 characters
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            vector_files = list(collection_path.rglob("vector_*.json"))

            assert len(vector_files) == 1
            actual_filename = vector_files[0].name

            assert len(actual_filename) < 255, (
                f"Filename length {len(actual_filename)} exceeds 255 char limit"
            )

            # Verify it's using v2 format (28 chars exactly)
            assert len(actual_filename) == 28, (
                f"V2 format should produce 28-char filename, got {len(actual_filename)}"
            )

    def test_different_point_ids_produce_different_hashes(self):
        """Different point_ids should produce different hash prefixes (collision avoidance)."""
        # Given: Two different point_ids
        point_id_1 = "project:diff:abc123:file1.py:0"
        point_id_2 = "project:diff:abc123:file2.py:0"

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemVectorStore(base_path=Path(tmpdir))
            store.create_collection("code-indexer-temporal", vector_size=1024)

            # When: Upserting both points
            points = [
                {
                    "id": point_id_1,
                    "vector": [0.1] * 1024,
                    "payload": {"path": "file1.py"},
                    "chunk_text": "content1"
                },
                {
                    "id": point_id_2,
                    "vector": [0.2] * 1024,
                    "payload": {"path": "file2.py"},
                    "chunk_text": "content2"
                }
            ]
            store.upsert_points("code-indexer-temporal", points)

            # Then: Two different files should be created
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            vector_files = list(collection_path.rglob("vector_*.json"))

            assert len(vector_files) == 2, f"Expected 2 files, got {len(vector_files)}"

            # Filenames should be different (different hashes)
            filenames = {f.name for f in vector_files}
            assert len(filenames) == 2, "Different point_ids should produce different filenames"

"""
Test to reproduce the partial file indexing bug.

This test creates a scenario where cancellation definitely causes partial files.
"""

import pytest

from ...conftest import local_temporary_directory
import time
from pathlib import Path
from unittest.mock import Mock, patch
from collections import defaultdict

# Mark as e2e since this tests the actual bug
pytestmark = pytest.mark.e2e


class TrackedQdrantClient:
    """Qdrant client that carefully tracks what gets indexed."""

    def __init__(self):
        self.indexed_chunks = defaultdict(list)  # file_path -> list of chunk_indices
        self.upsert_calls = []

    def upsert_points(self, points):
        """Track exactly which chunks get indexed."""
        print(f"QDRANT: Upserting {len(points)} points")
        self.upsert_calls.append(points)

        for point in points:
            payload = point.get("payload", {})
            file_path = payload.get("path", "unknown")
            chunk_index = payload.get("chunk_index", -1)
            self.indexed_chunks[file_path].append(chunk_index)
            print(f"  - Indexed {file_path} chunk {chunk_index}")

        return True

    def upsert_points_batched(self, points):
        """Atomic version of upsert_points."""
        return self.upsert_points(points)

    def create_point(self, point_id, vector, payload, embedding_model=None):
        return {"id": point_id, "vector": vector, "payload": payload}

    def get_file_completeness(self):
        """Check which files have partial vs complete indexing."""
        results = {}
        for file_path, chunks in self.indexed_chunks.items():
            chunk_indices = sorted(chunks)
            # A file with chunks [0,1,2,3,4] is complete
            # A file with chunks [0,1,2] is partial if it should have had 5 chunks
            results[file_path] = {
                "indexed_chunks": chunk_indices,
                "is_complete": (
                    len(chunk_indices) == max(chunk_indices) + 1
                    if chunk_indices
                    else True
                ),
                "chunk_count": len(chunk_indices),
            }
        return results


def test_partial_file_bug_reproduction():
    """Reproduce the partial file indexing bug with aggressive conditions."""

    with local_temporary_directory() as temp_dir:
        # Create ONE file that will have multiple chunks
        test_file = Path(temp_dir) / "multi_chunk_file.py"
        content = "\n".join(
            [
                f"def function_{i}():\n    '''Function {i}'''\n    pass\n"
                for i in range(20)
            ]
        )
        test_file.write_text(content)

        tracked_qdrant = TrackedQdrantClient()

        with (
            patch("code_indexer.services.git_aware_processor.FileIdentifier"),
            patch("code_indexer.services.git_aware_processor.GitDetectionService"),
            patch("code_indexer.indexing.processor.FileFinder"),
            patch("code_indexer.indexing.chunker.TextChunker") as mock_chunker,
        ):
            # Configure chunker to return exactly 5 chunks for this file
            def mock_chunk_file(file_path):
                print(f"CHUNKER: Processing {file_path}")
                return [
                    {
                        "text": f"chunk {i} content of {file_path.name}",
                        "chunk_index": i,
                        "total_chunks": 5,
                        "file_extension": "py",
                    }
                    for i in range(5)  # Exactly 5 chunks
                ]

            mock_chunker.return_value.chunk_file.side_effect = mock_chunk_file

            from code_indexer.services.high_throughput_processor import (
                HighThroughputProcessor,
            )

            config = Mock()
            config.codebase_dir = Path(temp_dir)

            # Use very slow embedding to ensure we can cancel mid-processing
            embedding_provider = Mock()
            embedding_provider.get_current_model.return_value = "test-model"

            call_count = 0

            def slow_get_embedding(text, model=None):
                nonlocal call_count
                call_count += 1
                print(
                    f"EMBEDDING: Processing embedding {call_count} for: {text[:50]}..."
                )
                time.sleep(0.2)  # Slow enough to cancel mid-process
                return [1.0] * 768

            embedding_provider.get_embedding.side_effect = slow_get_embedding

            processor = HighThroughputProcessor(
                config=config,
                embedding_provider=embedding_provider,
                qdrant_client=tracked_qdrant,
            )

            # Mock file identifier
            processor.file_identifier.get_file_metadata.return_value = {
                "project_id": "test-project",
                "file_hash": "test-hash",
                "git_available": False,
                "file_mtime": time.time(),
                "file_size": 1000,
            }

            # Cancel after 2 chunks are processed to create partial file
            processed_chunks = 0

            def progress_callback(
                current, total, path, info=None, concurrent_files=None
            ):
                nonlocal processed_chunks
                processed_chunks += 1
                print(
                    f"PROGRESS: Callback {processed_chunks} - {current}/{total} files"
                )
                # Cancel after we've processed some chunks but not all
                if processed_chunks == 3:  # This should catch us mid-file
                    print("PROGRESS: Requesting cancellation!")
                    return "INTERRUPT"
                return None

            # Use small batch size to force frequent Qdrant calls
            print("Starting processing...")
            stats = processor.process_files_high_throughput(
                files=[test_file],
                vector_thread_count=1,  # Single thread for predictable timing
                batch_size=2,  # Small batch - chunks will be sent in batches of 2
            )

            print(
                f"Processing completed. Stats: {stats.files_processed} files, {stats.chunks_created} chunks"
            )

            # Analyze what got indexed
            file_completeness = tracked_qdrant.get_file_completeness()
            print("File completeness analysis:")
            for file_path, info in file_completeness.items():
                print(f"  {file_path}: {info}")

            # THE BUG: Check if we have partial files
            test_file_str = str(test_file)
            if test_file_str in file_completeness:
                file_info = file_completeness[test_file_str]
                chunk_count = file_info["chunk_count"]

                # If we have 1-4 chunks indexed, that's a partial file (BUG!)
                # We should have either 0 chunks (not started) or 5 chunks (complete)
                print(f"File has {chunk_count} chunks indexed")

                if 1 <= chunk_count <= 4:
                    print("🐛 BUG REPRODUCED: Partial file detected!")
                    print(f"Expected 0 or 5 chunks, but got {chunk_count} chunks")
                    print(f"Indexed chunks: {file_info['indexed_chunks']}")

                    # This assertion will fail, proving the bug exists
                    assert False, (
                        f"PARTIAL FILE BUG: File {test_file} has {chunk_count} chunks "
                        f"(chunks {file_info['indexed_chunks']}) but should have 0 or 5. "
                        f"This violates file-level atomicity!"
                    )
                elif chunk_count == 0:
                    print("✅ Good: No chunks indexed (clean cancellation)")
                elif chunk_count == 5:
                    print("✅ Good: All chunks indexed (completed before cancellation)")
                else:
                    print(f"❓ Unexpected: {chunk_count} chunks (should be 0-5)")
            else:
                print("✅ Good: No file indexed at all")


if __name__ == "__main__":
    test_partial_file_bug_reproduction()

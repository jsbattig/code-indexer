"""Test for critical bug: temporal diff content not stored correctly.

This test reproduces the issue where FilesystemVectorStore's git-aware optimization
incorrectly applies to temporal diffs, causing their content to be lost.
"""

import tempfile
from pathlib import Path
import subprocess
import json
import numpy as np


from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestTemporalDiffContentBug:
    """Test suite for temporal diff content storage bug."""

    def test_temporal_diff_content_stored_in_chunk_text(self):
        """Test that temporal diff content is properly stored in chunk_text field.

        This reproduces the critical bug where temporal diff content gets lost
        because FilesystemVectorStore incorrectly applies git-aware optimization
        to temporal diffs, storing only blob hashes from current HEAD instead
        of the actual historical diff content.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a git repo with a file
            subprocess.run(["git", "init"], cwd=tmpdir_path, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=tmpdir_path,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=tmpdir_path,
                check=True,
            )

            # Create a file that exists in current HEAD
            test_file = tmpdir_path / "auth.py"
            test_file.write_text("def existing_function(): pass\n")
            subprocess.run(["git", "add", "."], cwd=tmpdir_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=tmpdir_path,
                check=True,
            )

            # Initialize vector store
            vector_store = FilesystemVectorStore(
                base_path=tmpdir_path / ".code-indexer" / "index",
                project_root=tmpdir_path,
            )

            # Create collection
            collection_name = "temporal_test"
            vector_store.create_collection(collection_name, vector_size=1536)

            # Create temporal diff payload - simulating what temporal indexer does
            # CRITICAL: This is a temporal diff from a historical commit,
            # NOT the current file content
            temporal_diff_content = "+def login(): pass\n+def logout(): pass"

            payload = {
                "type": "commit_diff",  # This indicates it's a temporal diff
                "path": "auth.py",  # File exists in current HEAD
                "content": temporal_diff_content,  # Historical diff content
                "commit_hash": "abc123",
                "timestamp": "2025-11-01T00:00:00Z",
                "start_line": 1,
                "end_line": 2,
                "language": "python",
            }

            # Create a point with the temporal diff
            point_id = "temporal_diff_1"
            vector = np.random.rand(1536).astype(np.float32)

            # Store the vector with temporal payload
            vector_store.upsert_points(
                collection_name=collection_name,
                points=[
                    {
                        "id": point_id,
                        "vector": vector,
                        "payload": payload,
                    }
                ],
            )

            # Now retrieve the stored data directly from filesystem
            # to verify what was actually stored
            collection_path = tmpdir_path / ".code-indexer" / "index" / collection_name

            # Find the vector file
            vector_files = list(collection_path.rglob(f"vector_{point_id}.json"))
            assert (
                len(vector_files) == 1
            ), f"Expected 1 vector file, found {len(vector_files)}"

            # Load the stored data
            with open(vector_files[0]) as f:
                stored_data = json.load(f)

            # CRITICAL ASSERTION: The temporal diff content should be stored
            # Either in chunk_text or in payload["content"]
            has_content = False
            actual_content = None

            # Check chunk_text field
            if "chunk_text" in stored_data:
                actual_content = stored_data["chunk_text"]
                has_content = actual_content == temporal_diff_content

            # Check payload content (shouldn't be deleted for temporal diffs)
            if not has_content and "payload" in stored_data:
                if "content" in stored_data["payload"]:
                    actual_content = stored_data["payload"]["content"]
                    has_content = actual_content == temporal_diff_content

            # The bug is that neither location has the content - it's been lost!
            assert has_content, (
                f"Temporal diff content was lost!\n"
                f"Expected content: {temporal_diff_content}\n"
                f"chunk_text: {stored_data.get('chunk_text', 'MISSING')}\n"
                f"payload.content: {stored_data.get('payload', {}).get('content', 'MISSING')}\n"
                f"git_blob_hash: {stored_data.get('git_blob_hash', 'MISSING')}\n"
                f"This proves the bug: temporal content replaced with current HEAD blob hash"
            )

    def test_regular_file_uses_git_optimization(self):
        """Test that regular (non-temporal) files still use git-aware optimization.

        This ensures our fix doesn't break the existing optimization for regular files.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a git repo with a file
            subprocess.run(
                ["git", "init"], cwd=tmpdir_path, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=tmpdir_path,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=tmpdir_path,
                check=True,
            )

            # Create a clean file
            test_file = tmpdir_path / "main.py"
            file_content = "def main(): pass\n"
            test_file.write_text(file_content)
            subprocess.run(["git", "add", "."], cwd=tmpdir_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Add main.py"],
                cwd=tmpdir_path,
                check=True,
                capture_output=True,
            )

            # Initialize vector store
            vector_store = FilesystemVectorStore(
                base_path=tmpdir_path / ".code-indexer" / "index",
                project_root=tmpdir_path,
            )

            # Create collection
            collection_name = "regular_test"
            vector_store.create_collection(collection_name, vector_size=1536)

            # Create regular file payload (NOT a temporal diff)
            payload = {
                "type": "file_chunk",  # Regular file chunk
                "path": "main.py",
                "content": file_content,
                "start_line": 1,
                "end_line": 1,
                "language": "python",
            }

            # Store the vector
            point_id = "regular_file_1"
            vector = np.random.rand(1536).astype(np.float32)

            vector_store.upsert_points(
                collection_name=collection_name,
                points=[
                    {
                        "id": point_id,
                        "vector": vector,
                        "payload": payload,
                    }
                ],
            )

            # Load the stored data
            collection_path = tmpdir_path / ".code-indexer" / "index" / collection_name
            vector_files = list(collection_path.rglob(f"vector_{point_id}.json"))

            with open(vector_files[0]) as f:
                stored_data = json.load(f)

            # For regular clean files, we expect git optimization:
            # - Should have git_blob_hash
            # - Should NOT have chunk_text (saving space)
            assert (
                "git_blob_hash" in stored_data
            ), "Regular clean file should use git blob hash optimization"
            assert (
                "chunk_text" not in stored_data
            ), "Regular clean file should not store chunk_text (space optimization)"

"""Integration test for temporal diff content storage fix.

This test verifies that the temporal indexing system correctly stores
diff content in the vector store, and that queries return the actual
diff content rather than meaningless blob hashes.
"""

import tempfile
from pathlib import Path
import subprocess
import json


from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.temporal_search_service import (
    TemporalSearchService,
)
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from src.code_indexer.config import ConfigManager


class TestTemporalDiffContentIntegration:
    """Integration test for temporal diff content storage."""

    def test_temporal_diff_content_searchable(self):
        """Test that temporal diff content is properly stored and searchable.

        This integration test verifies the complete flow:
        1. Create a test repository with commits
        2. Index temporal diffs
        3. Search for content
        4. Verify search results contain actual diff content, not blob hashes
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create test repository with history
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

            # Commit 1: Initial file
            auth_file = tmpdir_path / "auth.py"
            auth_file.write_text("def authenticate():\n    pass\n")
            subprocess.run(["git", "add", "."], cwd=tmpdir_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial auth module"],
                cwd=tmpdir_path,
                check=True,
            )

            # Commit 2: Add login function
            auth_file.write_text(
                "def authenticate():\n    pass\n\ndef login(username, password):\n    return True\n"
            )
            subprocess.run(["git", "add", "."], cwd=tmpdir_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Add login function"],
                cwd=tmpdir_path,
                check=True,
            )

            # Commit 3: Add logout function
            auth_file.write_text(
                "def authenticate():\n    pass\n\ndef login(username, password):\n    return True\n\ndef logout():\n    pass\n"
            )
            subprocess.run(["git", "add", "."], cwd=tmpdir_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Add logout function"],
                cwd=tmpdir_path,
                check=True,
            )

            # Initialize config and services
            config_dir = tmpdir_path / ".code-indexer"
            config_dir.mkdir(exist_ok=True)

            config_manager = ConfigManager(config_path=config_dir / "config.json")
            config = config_manager.get_config()

            # Create vector store and temporal indexer
            vector_store = FilesystemVectorStore(
                base_path=config_dir / "index",
                project_root=tmpdir_path,
            )

            # Initialize temporal indexer (it will create its own collection)
            temporal_indexer = TemporalIndexer(
                config_manager=config_manager,
                vector_store=vector_store,
            )

            # Get the collection name from the indexer
            collection_name = temporal_indexer.TEMPORAL_COLLECTION_NAME

            # Index the temporal diffs (index all commits)
            temporal_indexer.index_commits()

            # Verify vectors were created with content
            collection_path = config_dir / "index" / collection_name

            # Check that we have vector files
            vector_files = list(collection_path.rglob("vector_*.json"))
            assert len(vector_files) > 0, "No vectors were created"

            # Check at least one vector has chunk_text (diff content)
            found_diff_content = False
            for vector_file in vector_files:
                with open(vector_file) as f:
                    data = json.load(f)
                    if "chunk_text" in data:
                        # Found diff content!
                        chunk_text = data["chunk_text"]
                        # Temporal diffs should have + or - prefixes
                        if chunk_text and (
                            chunk_text.startswith("+") or chunk_text.startswith("-")
                        ):
                            found_diff_content = True
                            # Verify it's actual code diff, not empty
                            assert (
                                "def" in chunk_text
                                or "pass" in chunk_text
                                or "return" in chunk_text
                            ), f"Chunk text doesn't look like code diff: {chunk_text}"
                            break

            assert found_diff_content, (
                "No temporal diff content found in any vector! "
                "All vectors are missing chunk_text or have wrong content."
            )

            # Now test search functionality
            search_service = TemporalSearchService(
                config=config,
                project_root=tmpdir_path,
            )

            # Search for login function that was added
            results = search_service.search(
                query="login function",
                collection_name=collection_name,
                limit=5,
            )

            # Verify we get results
            assert len(results) > 0, "No search results found for 'login function'"

            # Verify at least one result contains actual diff content
            found_login_diff = False
            for result in results:
                content = result.get("content", "")
                if "login" in content.lower():
                    found_login_diff = True
                    # Should be a diff with + prefix
                    assert (
                        "+" in content or "-" in content
                    ), f"Result doesn't look like a diff: {content}"
                    break

            assert found_login_diff, (
                "Search results don't contain login diff content. "
                "This suggests the bug is not fully fixed."
            )

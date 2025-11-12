"""
Test for CRITICAL BUG: cidx index --index-commits --clear wipes BOTH indexes.

BUG DESCRIPTION:
When user runs `cidx index --index-commits --clear`, the command clears BOTH:
- Regular semantic index (model-based collection) ❌ SHOULD NOT CLEAR
- Temporal index (code-indexer-temporal collection) ✅ SHOULD CLEAR

EXPECTED BEHAVIOR:
- `cidx index --clear` → Clear regular semantic index only
- `cidx index --index-commits --clear` → Clear temporal index only (leave regular index intact)
- Each index type should have independent --clear behavior
"""

import subprocess
from pathlib import Path
import tempfile


def test_index_commits_clear_does_not_wipe_regular_index():
    """Test that --index-commits --clear only clears temporal index, NOT regular index."""

    # Create temporary git repository
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create test file and commit
        test_file = repo_path / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n")
        subprocess.run(
            ["git", "add", "."], cwd=repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # STEP 1: Initialize cidx and create config
        init_result = subprocess.run(
            ["cidx", "init"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        assert init_result.returncode == 0, f"cidx init failed: {init_result.stderr}"

        # STEP 2: Index regular semantic index first
        index_result = subprocess.run(
            ["cidx", "index"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert index_result.returncode == 0, f"cidx index failed: {index_result.stderr}"

        # STEP 3: Verify regular semantic index exists
        index_dir = repo_path / ".code-indexer" / "index"
        collections_before = [d.name for d in index_dir.iterdir() if d.is_dir()]

        # Find the semantic collection (should be model-based name like "voyage-code-3")
        semantic_collections = [
            c for c in collections_before if c != "code-indexer-temporal"
        ]
        assert (
            len(semantic_collections) >= 1
        ), f"No semantic collection found! Collections: {collections_before}"
        semantic_collection_name = semantic_collections[0]

        # Count vectors in semantic index
        semantic_collection_path = index_dir / semantic_collection_name
        semantic_vectors_before = list(semantic_collection_path.glob("**/*.json"))
        semantic_vector_count_before = len(
            [f for f in semantic_vectors_before if f.name.startswith("vector_")]
        )

        assert (
            semantic_vector_count_before > 0
        ), "Semantic index has no vectors after initial indexing!"

        print(f"✓ Semantic index created: {semantic_collection_name}")
        print(f"✓ Semantic vectors: {semantic_vector_count_before}")

        # STEP 4: Index temporal index
        temporal_index_result = subprocess.run(
            ["cidx", "index", "--index-commits"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            temporal_index_result.returncode == 0
        ), f"cidx index --index-commits failed: {temporal_index_result.stderr}"

        # STEP 5: Verify temporal index exists
        temporal_collection_path = index_dir / "code-indexer-temporal"
        assert temporal_collection_path.exists(), "Temporal index not created!"

        temporal_vectors_before = list(temporal_collection_path.glob("**/*.json"))
        temporal_vector_count_before = len(
            [f for f in temporal_vectors_before if f.name.startswith("vector_")]
        )

        assert (
            temporal_vector_count_before > 0
        ), "Temporal index has no vectors after indexing!"

        print("✓ Temporal index created: code-indexer-temporal")
        print(f"✓ Temporal vectors: {temporal_vector_count_before}")

        # STEP 6: Run the buggy command: cidx index --index-commits --clear
        print("\n🐛 Running buggy command: cidx index --index-commits --clear")
        clear_result = subprocess.run(
            ["cidx", "index", "--index-commits", "--clear"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            clear_result.returncode == 0
        ), f"cidx index --index-commits --clear failed: {clear_result.stderr}"

        # STEP 7: Check regular semantic index SHOULD STILL EXIST (this is the bug!)
        semantic_vectors_after = list(semantic_collection_path.glob("**/*.json"))
        semantic_vector_count_after = len(
            [f for f in semantic_vectors_after if f.name.startswith("vector_")]
        )

        print("\n📊 RESULTS:")
        print(f"  Semantic vectors BEFORE clear: {semantic_vector_count_before}")
        print(f"  Semantic vectors AFTER clear:  {semantic_vector_count_after}")

        # THIS IS THE BUG: semantic index should NOT be cleared!
        assert semantic_vector_count_after == semantic_vector_count_before, (
            f"BUG CONFIRMED: Regular semantic index was wiped! "
            f"Had {semantic_vector_count_before} vectors, now has {semantic_vector_count_after}"
        )

        # STEP 8: Check temporal index SHOULD BE CLEARED AND RE-INDEXED
        # Note: --clear means "clear and rebuild", not "clear and leave empty"
        if temporal_collection_path.exists():
            temporal_vectors_after = list(temporal_collection_path.glob("**/*.json"))
            temporal_vector_count_after = len(
                [f for f in temporal_vectors_after if f.name.startswith("vector_")]
            )
        else:
            temporal_vector_count_after = 0

        print(f"  Temporal vectors BEFORE clear: {temporal_vector_count_before}")
        print(f"  Temporal vectors AFTER clear:  {temporal_vector_count_after}")

        # Temporal should be re-indexed (same or similar count)
        assert (
            temporal_vector_count_after > 0
        ), "Temporal index should be re-indexed but has no vectors"

        print(
            "\n✅ TEST PASSED: --index-commits --clear correctly preserves semantic index and rebuilds temporal"
        )

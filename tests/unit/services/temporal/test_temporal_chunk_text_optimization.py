"""
Test temporal indexer chunk_text optimization.

Tests verify elimination of wasteful create-then-delete pattern:
1. Point structure has chunk_text at root, NOT in payload
"""

from pathlib import Path


class TestChunkTextOptimization:
    """Test chunk_text optimization in temporal indexer."""

    def test_point_structure_has_chunk_text_at_root_not_payload(self):
        """
        Test 1: Point structure has chunk_text at root, NOT in payload.

        VERIFICATION:
        - Point should have "chunk_text" field at root level
        - Point["payload"] should NOT contain "content" field
        - This eliminates wasteful create-then-delete pattern

        This is a CODE INSPECTION test that verifies the optimization
        by checking the actual code structure in temporal_indexer.py.
        """
        # Read the temporal_indexer.py file
        indexer_file = Path(
            "/home/jsbattig/Dev/code-indexer/src/code_indexer/services/temporal/temporal_indexer.py"
        )
        content = indexer_file.read_text()
        lines = content.split("\n")

        # Find the point creation logic (around line 868)
        point_creation_found = False
        chunk_text_at_root = False
        content_in_payload = False

        for i, line in enumerate(lines):
            # Look for point = { structure
            if "point = {" in line and i > 920 and i < 945:
                point_creation_found = True
                # Check next 10 lines for structure
                point_block = "\n".join(lines[i : i + 15])

                # Optimized: chunk_text should be at root level
                if '"chunk_text":' in point_block or "'chunk_text':" in point_block:
                    chunk_text_at_root = True

                # Wasteful pattern: content should NOT be in payload creation (around line 848)
                payload_block = "\n".join(lines[i - 30 : i])
                if '"content":' in payload_block and "chunk.get" in payload_block:
                    content_in_payload = True

                break

        # Assertions
        assert (
            point_creation_found
        ), "Could not find point creation logic in temporal_indexer.py"

        # CRITICAL: This test FAILS until optimization is implemented
        assert chunk_text_at_root, (
            "Point missing chunk_text at root level. "
            "Expected point structure:\n"
            "  point = {\n"
            "    'id': point_id,\n"
            "    'vector': list(embedding),\n"
            "    'payload': payload,\n"
            "    'chunk_text': chunk.get('text', '')  # <-- ADD THIS\n"
            "  }\n"
            "Currently: chunk_text not found in point structure"
        )

        assert not content_in_payload, (
            "Payload should NOT contain 'content' field (wasteful pattern). "
            "Found payload['content'] creation around line 848-850. "
            "This creates content just to delete it later in filesystem_vector_store.py"
        )

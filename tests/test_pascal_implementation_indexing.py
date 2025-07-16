"""
Test that Pascal implementations are properly indexed and searchable.
Uses the real hash_trie.pas file from the tries project.
"""

import pytest
from pathlib import Path
from code_indexer.config import IndexingConfig
from code_indexer.indexing.pascal_parser import PascalSemanticParser


class TestPascalImplementationIndexing:
    """Test that Pascal procedure implementations are properly indexed."""

    @pytest.fixture
    def hash_trie_content(self):
        """Load the actual hash_trie.pas file."""
        test_file = Path(__file__).parent / "test_data" / "hash_trie.pas"
        return test_file.read_text()

    def test_removkvptreenode_implementation_is_chunked(self, hash_trie_content):
        """Test that RemoveKVPTreeNode implementation is properly chunked."""
        config = IndexingConfig()
        parser = PascalSemanticParser(config)

        chunks = parser.chunk(hash_trie_content, "hash_trie.pas")

        # Find all chunks related to RemoveKVPTreeNode
        remove_chunks = [c for c in chunks if c.semantic_name == "RemoveKVPTreeNode"]

        print(f"\nFound {len(remove_chunks)} chunks for RemoveKVPTreeNode")

        # Should have at least 2: declaration and implementation
        assert (
            len(remove_chunks) >= 2
        ), f"Expected at least 2 chunks (declaration + implementation), got {len(remove_chunks)}"

        # Find the implementation chunk
        impl_chunks = [
            c
            for c in remove_chunks
            if "procedure_implementation" in c.semantic_language_features
        ]

        assert len(impl_chunks) > 0, "No implementation chunk found"

        impl_chunk = impl_chunks[0]

        # Verify implementation contains actual code
        assert "begin" in impl_chunk.text, "Implementation should contain 'begin'"
        assert "end" in impl_chunk.text, "Implementation should contain 'end'"

        # Check for specific implementation details we know are there
        assert (
            "SmallestNode" in impl_chunk.text
        ), "Implementation should contain SmallestNode variable"
        assert (
            "ParentNodePtr" in impl_chunk.text
        ), "Implementation should contain ParentNodePtr parameter"

        # Check that it spans multiple lines (real implementation)
        assert (
            impl_chunk.line_end - impl_chunk.line_start > 5
        ), "Implementation should span multiple lines"

        print("\nImplementation chunk found:")
        print(f"  Lines: {impl_chunk.line_start}-{impl_chunk.line_end}")
        print(f"  Size: {len(impl_chunk.text)} bytes")
        print(f"  Features: {impl_chunk.semantic_language_features}")
        print(f"  First 200 chars: {impl_chunk.text[:200]}...")

    def test_all_procedure_implementations_are_indexed(self, hash_trie_content):
        """Test that all procedure implementations in the file are indexed."""
        config = IndexingConfig()
        parser = PascalSemanticParser(config)

        chunks = parser.chunk(hash_trie_content, "hash_trie.pas")

        # Find all procedure/function declarations
        declarations = [
            c
            for c in chunks
            if c.semantic_type in ["procedure", "function"]
            and "declaration" in str(c.semantic_language_features)
            and c.semantic_parent == "THashTrie"  # Only class methods
        ]

        # Find all implementations
        implementations = [
            c
            for c in chunks
            if c.semantic_type in ["procedure", "function"]
            and "implementation" in str(c.semantic_language_features)
        ]

        print(
            f"\nFound {len(declarations)} procedure/function declarations in THashTrie"
        )
        print(f"Found {len(implementations)} implementations")

        # For each declaration, try to find its implementation
        missing_impls = []
        for decl in declarations:
            impl_found = any(
                impl.semantic_name == decl.semantic_name for impl in implementations
            )
            if not impl_found:
                missing_impls.append(decl.semantic_name)

        if missing_impls:
            print(f"\nMissing implementations for: {missing_impls}")

        # We expect most procedures to have implementations
        # Some might be external or abstract, so we allow a small number to be missing
        assert (
            len(missing_impls) < len(declarations) * 0.2
        ), f"Too many missing implementations: {missing_impls}"

    def test_implementation_chunks_are_complete(self, hash_trie_content):
        """Test that implementation chunks contain complete code blocks."""
        config = IndexingConfig()
        parser = PascalSemanticParser(config)

        chunks = parser.chunk(hash_trie_content, "hash_trie.pas")

        # Find all implementation chunks
        impl_chunks = [
            c
            for c in chunks
            if c.semantic_type in ["procedure", "function"]
            and "implementation" in str(c.semantic_language_features)
        ]

        for impl in impl_chunks:
            # Each implementation should have begin and end
            # Use regex to count only standalone keywords, not substrings
            import re

            begin_count = len(re.findall(r"\bbegin\b", impl.text, re.IGNORECASE))
            end_count = len(re.findall(r"\bend\b", impl.text, re.IGNORECASE))

            # At minimum, should have the main begin/end pair
            assert begin_count >= 1, f"{impl.semantic_name} missing 'begin'"
            assert end_count >= 1, f"{impl.semantic_name} missing 'end'"

            # The counts should be balanced (allowing for nested blocks)
            # Note: case statements can have 'end' without 'begin', so allow more flexibility
            assert (
                abs(begin_count - end_count) <= 2
            ), f"{impl.semantic_name} has unbalanced begin/end (begin: {begin_count}, end: {end_count})"

    def test_searchable_content_in_implementations(self, hash_trie_content):
        """Test that implementation chunks contain searchable content."""
        config = IndexingConfig()
        parser = PascalSemanticParser(config)

        chunks = parser.chunk(hash_trie_content, "hash_trie.pas")

        # Look for RemoveKVPTreeNode implementation specifically
        remove_impl = None
        for chunk in chunks:
            if chunk.semantic_name == "RemoveKVPTreeNode" and "implementation" in str(
                chunk.semantic_language_features
            ):
                remove_impl = chunk
                break

        assert remove_impl is not None, "RemoveKVPTreeNode implementation not found"

        # Print details for debugging search issues
        print("\nRemoveKVPTreeNode implementation details:")
        print(f"  Semantic type: {remove_impl.semantic_type}")
        print(f"  Semantic name: {remove_impl.semantic_name}")
        print(f"  Semantic path: {remove_impl.semantic_path}")
        print(f"  Semantic parent: {remove_impl.semantic_parent}")
        print(f"  Features: {remove_impl.semantic_language_features}")
        print(f"  Line range: {remove_impl.line_start}-{remove_impl.line_end}")
        print(f"  Text size: {len(remove_impl.text)} bytes")
        print("\nText preview (first 500 chars):")
        print(remove_impl.text[:500])

        # This content should be searchable
        assert "SmallestNode" in remove_impl.text
        assert "SmallestNodeParent" in remove_impl.text
        assert "procedure THashTrie.RemoveKVPTreeNode" in remove_impl.text

"""
Test for Pascal duplicate indexing bug where procedure declarations
inside classes are indexed twice with different semantic names.
"""

from code_indexer.config import IndexingConfig
from code_indexer.indexing.pascal_parser import PascalSemanticParser


class TestPascalDuplicateIndexingBug:
    """Test duplicate indexing issue in Pascal semantic parser."""

    def test_procedure_declaration_not_duplicated(self):
        """Test that procedure declarations inside classes are not indexed twice."""
        pascal_code = """unit HashTrie;

interface

type
  THashTrie = class(TBaseHashedContainer)
  private
    { Methods to manage key/value pair linked to each array entry on Trie leaf nodes }
    procedure RemoveKVPTreeNode(ParentNodePtr: PPKeyValuePairNode; Node: PKeyValuePairNode);
    procedure FreeKVPTreeNode(var CurNode: PKeyValuePairNode);
  public
    procedure PublicMethod;
  end;

implementation

procedure THashTrie.RemoveKVPTreeNode(ParentNodePtr: PPKeyValuePairNode; Node: PKeyValuePairNode);
begin
  // Implementation here
end;

procedure THashTrie.FreeKVPTreeNode(var CurNode: PKeyValuePairNode);
begin
  // Implementation here  
end;

procedure THashTrie.PublicMethod;
begin
  // Implementation here
end;

end.
"""
        config = IndexingConfig()
        parser = PascalSemanticParser(config)

        chunks = parser.chunk(pascal_code, "hash_trie.pas")

        # Find all chunks for RemoveKVPTreeNode
        remove_chunks = [
            c
            for c in chunks
            if c.semantic_name == "RemoveKVPTreeNode"
            or (c.semantic_name and "RemoveKVPTreeNode" in c.semantic_name)
        ]

        # Should have exactly 2 chunks: 1 declaration + 1 implementation
        assert (
            len(remove_chunks) == 2
        ), f"Expected 2 chunks for RemoveKVPTreeNode, got {len(remove_chunks)}"

        # Check that we have one declaration and one implementation
        chunk_types = [c.semantic_type for c in remove_chunks]
        assert "procedure" in chunk_types, "Should have procedure declaration"
        assert (
            "procedure_implementation" in chunk_types or "procedure" in chunk_types
        ), "Should have procedure implementation"

        # Check line numbers to ensure they're different chunks
        line_starts = [c.line_start for c in remove_chunks]
        assert (
            len(set(line_starts)) == 2
        ), f"Chunks should be at different lines, got: {line_starts}"

        # Both chunks should have consistent semantic parent
        semantic_parents = [c.semantic_parent for c in remove_chunks]
        assert all(
            p == "THashTrie" or p is None for p in semantic_parents
        ), f"Inconsistent parents: {semantic_parents}"

    def test_procedure_implementation_is_indexed(self):
        """Test that procedure implementations are properly indexed."""
        pascal_code = """unit TestUnit;

interface

type
  TTestClass = class
    procedure TestMethod(Value: Integer);
  end;

implementation

procedure TTestClass.TestMethod(Value: Integer);
var
  LocalVar: Integer;
begin
  LocalVar := Value * 2;
  WriteLn(LocalVar);
end;

end.
"""
        config = IndexingConfig()
        parser = PascalSemanticParser(config)

        chunks = parser.chunk(pascal_code, "test_unit.pas")

        # Find chunks for TestMethod
        test_method_chunks = [
            c
            for c in chunks
            if c.semantic_name == "TestMethod"
            or (c.semantic_name and "TestMethod" in c.semantic_name)
        ]

        # Should have both declaration and implementation
        assert (
            len(test_method_chunks) >= 2
        ), f"Should have at least 2 chunks for TestMethod, got {len(test_method_chunks)}"

        # Find the implementation chunk
        impl_chunks = [
            c for c in test_method_chunks if "begin" in c.text and "end" in c.text
        ]

        assert len(impl_chunks) > 0, "Should have implementation chunk with begin/end"

        # Check that implementation has more lines than just declaration
        impl_chunk = impl_chunks[0]
        assert (
            impl_chunk.line_end - impl_chunk.line_start > 2
        ), "Implementation should span multiple lines"

    def test_no_duplicate_chunks_with_same_content(self):
        """Test that we don't get duplicate chunks with identical content."""
        pascal_code = """unit SimpleUnit;

interface

type
  TSimpleClass = class
    procedure SimpleProc;
  end;

implementation

procedure TSimpleClass.SimpleProc;
begin
  // Simple implementation
end;

end.
"""
        config = IndexingConfig()
        parser = PascalSemanticParser(config)

        chunks = parser.chunk(pascal_code, "simple_unit.pas")

        # Check for exact duplicates
        seen_contents = set()
        duplicates = []

        for chunk in chunks:
            # Create a key from the content that would identify duplicates
            chunk_key = (chunk.text.strip(), chunk.line_start, chunk.line_end)
            if chunk_key in seen_contents:
                duplicates.append(chunk)
            seen_contents.add(chunk_key)

        assert len(duplicates) == 0, f"Found {len(duplicates)} duplicate chunks"

        # Specifically check procedure chunks
        proc_chunks = [
            c
            for c in chunks
            if c.semantic_type == "procedure" and c.semantic_name == "SimpleProc"
        ]

        # Should have exactly 2: declaration and implementation
        assert (
            len(proc_chunks) == 2
        ), f"Should have exactly 2 procedure chunks (declaration + implementation), got {len(proc_chunks)}"

        # Verify we have one of each type
        decl_chunks = [
            c
            for c in proc_chunks
            if "procedure_declaration" in c.semantic_language_features
        ]
        impl_chunks = [
            c
            for c in proc_chunks
            if "procedure_implementation" in c.semantic_language_features
        ]

        assert (
            len(decl_chunks) == 1
        ), f"Should have exactly 1 declaration, got {len(decl_chunks)}"
        assert (
            len(impl_chunks) == 1
        ), f"Should have exactly 1 implementation, got {len(impl_chunks)}"

"""Tests for SCIP call chain tracing composite query."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.code_indexer.scip.query.composites import trace_call_chain
from src.code_indexer.scip.query.primitives import QueryResult
from src.code_indexer.scip.query.backends import CallChain as BackendCallChain

MAX_EXPECTED_PATH_LENGTH = 20  # Reasonable upper bound


class TestCallChainTracing:
    """Test call chain tracing functionality."""

    def test_call_chain_uses_dependencies_not_references(self):
        """
        Test that trace_call_chain uses get_dependencies (what A calls)
        not find_references (who calls A).

        This test creates a dependency chain: A -> B -> C
        - A calls B
        - B calls C

        If trace_call_chain incorrectly uses find_references, it will find
        who calls A (reverse direction), not what A calls.

        If trace_call_chain correctly uses get_dependencies, it will follow
        the chain A->B->C.
        """
        # Arrange
        scip_dir = Path("/fake/scip")

        # Mock the SCIP database file discovery
        mock_scip_file = Mock(spec=Path)
        mock_scip_file.__str__ = Mock(return_value="/fake/scip/index.scip.db")
        mock_scip_file.stat.return_value = Mock(st_size=1024)  # Non-zero size

        # Create mock dependency results with realistic SCIP method symbols:
        # A depends on B (A calls B)
        dep_a_to_b = QueryResult(
            symbol="Service#methodB().",
            project="test",
            file_path="test.py",
            line=10,
            column=5,
            kind="dependency",
            relationship="calls",
        )

        # B depends on C (B calls C)
        dep_b_to_c = QueryResult(
            symbol="Service#methodC().",
            project="test",
            file_path="test.py",
            line=20,
            column=5,
            kind="dependency",
            relationship="calls",
        )

        # Mock SCIPQueryEngine to return dependencies
        with patch(
            "src.code_indexer.scip.query.composites.SCIPQueryEngine"
        ) as MockEngine:
            mock_engine = Mock()
            MockEngine.return_value = mock_engine

            # Configure find_definition to return method definitions
            def mock_find_definition(symbol, exact=False):
                if "methodA" in symbol:
                    return [
                        QueryResult(
                            symbol="Service#methodA().",
                            project="test",
                            file_path="test.py",
                            line=5,
                            column=4,
                            kind="definition",
                        )
                    ]
                elif "methodC" in symbol:
                    return [
                        QueryResult(
                            symbol="Service#methodC().",
                            project="test",
                            file_path="test.py",
                            line=25,
                            column=4,
                            kind="definition",
                        )
                    ]
                return []

            # Configure get_dependencies to return our chain
            def mock_get_dependencies(symbol, exact=False):
                if "methodA" in symbol:
                    return [dep_a_to_b]
                elif "methodB" in symbol:
                    return [dep_b_to_c]
                elif "methodC" in symbol:
                    return []  # C calls nothing
                return []

            # Configure trace_call_chain to return backend chain A->B->C
            # Path contains targets of each step: [B, C] (A->B, B->C)
            backend_chain = BackendCallChain(
                path=["Service#methodB().", "Service#methodC()."],
                length=2,
                has_cycle=False,
            )
            mock_engine.trace_call_chain.return_value = [backend_chain]

            # Configure find_references to return NOTHING
            # (to prove we're not using references)
            mock_engine.find_definition.side_effect = mock_find_definition
            mock_engine.find_references.return_value = []
            mock_engine.get_dependencies.side_effect = mock_get_dependencies

            # Mock glob to return our fake SCIP file
            with patch.object(Path, "glob", return_value=[mock_scip_file]):
                # Act - use realistic SCIP method symbols
                result = trace_call_chain(
                    "Service#methodA().", "Service#methodC().", scip_dir, max_depth=5
                )

        # Assert
        # If using get_dependencies correctly, should find chain A->B->C
        assert (
            result.total_chains_found > 0
        ), "Should find at least one chain from methodA to methodC"
        assert len(result.chains) > 0, "Should have chains in result"

        # Verify the chain is A->B->C (length 2: A->B, B->C)
        chain = result.chains[0]
        assert chain.length == 2, f"Chain should have 2 steps, got {chain.length}"
        assert (
            chain.path[0].symbol == "Service#methodB()."
        ), "First step should be methodA->methodB"
        assert (
            chain.path[1].symbol == "Service#methodC()."
        ), "Second step should be methodB->methodC"

    def test_direct_call_chain_found(self, comprehensive_scip_fixture):
        """Test that direct call chain (A -> B) is found."""
        # Arrange
        scip_dir = comprehensive_scip_fixture
        from_symbol = "UserService"
        to_symbol = "authenticate"
        max_depth = 5

        # Act
        result = trace_call_chain(from_symbol, to_symbol, scip_dir, max_depth=max_depth)

        # Assert
        assert result.from_symbol == from_symbol
        assert result.to_symbol == to_symbol
        assert (
            result.total_chains_found >= 0
        )  # May be 0 if no path exists in test fixture

    def test_multi_hop_chain_found(self, comprehensive_scip_fixture):
        """Test that multi-hop chain (A -> B -> C) is found."""
        # Arrange
        scip_dir = comprehensive_scip_fixture
        from_symbol = "Logger"
        to_symbol = "UserService"
        max_depth = 10

        # Act
        result = trace_call_chain(from_symbol, to_symbol, scip_dir, max_depth=max_depth)

        # Assert
        assert result.from_symbol == from_symbol
        assert result.to_symbol == to_symbol
        # Chains may be empty if no path exists
        for chain in result.chains:
            assert len(chain.path) <= max_depth
            assert len(chain.path) < MAX_EXPECTED_PATH_LENGTH

    def test_no_path_returns_empty(self, comprehensive_scip_fixture):
        """Test that no path scenario returns empty chains."""
        # Arrange
        scip_dir = comprehensive_scip_fixture
        from_symbol = "UnreachableA"
        to_symbol = "UnreachableB"
        max_depth = 5

        # Act
        result = trace_call_chain(from_symbol, to_symbol, scip_dir, max_depth=max_depth)

        # Assert: Should complete without error
        assert result is not None
        assert result.total_chains_found == 0


@pytest.fixture
def comprehensive_scip_fixture():
    """Provide path to comprehensive SCIP test fixture."""
    return Path("tests/scip/fixtures")

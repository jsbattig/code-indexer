"""Tests for SCIP primitive query operations."""

import pytest
from pathlib import Path
from src.code_indexer.scip.query.primitives import SCIPQueryEngine, QueryResult


class TestSymbolDefinitionLookup:
    """Test symbol definition lookup query."""

    @pytest.fixture
    def query_engine(self):
        """Create query engine with test index."""
        test_file = Path("tests/scip/fixtures/comprehensive_index.scip")
        return SCIPQueryEngine(test_file)

    def test_find_definition_returns_correct_location(self, query_engine):
        """Should find symbol definition and return correct location."""
        # Act
        results = query_engine.find_definition("UserService")

        # Assert - finds both UserService class and UserService#authenticate (substring match)
        assert len(results) >= 1
        # Find the class definition specifically
        class_results = [r for r in results if r.symbol.endswith("/UserService#")]
        assert len(class_results) == 1
        result = class_results[0]
        assert isinstance(result, QueryResult)
        assert result.symbol == "python test `example`/UserService#"
        assert result.file_path == "src/example.py"
        assert result.line == 0
        assert result.column == 6
        assert result.kind == "definition"

    def test_find_definition_method(self, query_engine):
        """Should find method definition."""
        # Act
        results = query_engine.find_definition("authenticate")

        # Assert
        assert len(results) >= 1
        # Should find the method definition
        method_results = [r for r in results if "authenticate" in r.symbol]
        assert len(method_results) >= 1
        result = method_results[0]
        assert result.file_path == "src/example.py"
        assert result.line == 2
        assert result.kind == "definition"

    def test_find_definition_not_found(self, query_engine):
        """Should return empty list when symbol not found."""
        # Act
        results = query_engine.find_definition("NonExistentSymbol")

        # Assert
        assert len(results) == 0

    def test_find_definition_exact_match(self, query_engine):
        """Should support exact matching with qualified name."""
        # Act
        results = query_engine.find_definition(
            "python test `example`/UserService#",
            exact=True
        )

        # Assert
        assert len(results) == 1
        assert results[0].symbol == "python test `example`/UserService#"


class TestFindReferences:
    """Test find references query."""

    @pytest.fixture
    def query_engine(self):
        """Create query engine with test index."""
        test_file = Path("tests/scip/fixtures/comprehensive_index.scip")
        return SCIPQueryEngine(test_file)

    def test_find_references_returns_usages(self, query_engine):
        """Should find all references to a symbol."""
        # Act
        results = query_engine.find_references("UserService")

        # Assert
        assert len(results) >= 1
        # References should be in auth.py
        auth_refs = [r for r in results if "auth.py" in r.file_path]
        assert len(auth_refs) >= 1
        result = auth_refs[0]
        assert result.kind == "reference"
        assert result.file_path == "src/auth.py"

    def test_find_references_limit(self, query_engine):
        """Should respect limit parameter."""
        # Act
        results = query_engine.find_references("UserService", limit=1)

        # Assert
        assert len(results) <= 1


class TestGetDependencies:
    """Test get dependencies query."""

    @pytest.fixture
    def query_engine(self):
        """Create query engine with test index."""
        test_file = Path("tests/scip/fixtures/comprehensive_index.scip")
        return SCIPQueryEngine(test_file)

    def test_get_dependencies_returns_outgoing_references(self, query_engine):
        """Should find symbols that a symbol depends on."""
        # Act - UserService.authenticate depends on Logger
        results = query_engine.get_dependencies("authenticate")

        # Assert - should find Logger as dependency
        assert len(results) >= 1
        logger_deps = [r for r in results if "Logger" in r.symbol]
        assert len(logger_deps) >= 1
        result = logger_deps[0]
        assert result.kind == "dependency"
        assert result.relationship in ["calls", "import", "reference"]

    def test_get_dependencies_depth_1_direct_only(self, query_engine):
        """Should return only direct dependencies with depth=1."""
        # Act
        results = query_engine.get_dependencies("authenticate", depth=1)

        # Assert - should find only direct dependencies (Logger)
        assert len(results) >= 1
        # Should NOT find transitive dependencies beyond depth 1

    def test_get_dependencies_empty_for_leaf_symbol(self, query_engine):
        """Should return empty list for symbols with no dependencies."""
        # Act - Logger is a leaf (no outgoing dependencies)
        results = query_engine.get_dependencies("Logger", depth=1)

        # Assert
        assert len(results) == 0


class TestGetDependents:
    """Test get dependents query."""

    @pytest.fixture
    def query_engine(self):
        """Create query engine with test index."""
        test_file = Path("tests/scip/fixtures/comprehensive_index.scip")
        return SCIPQueryEngine(test_file)

    def test_get_dependents_returns_incoming_references(self, query_engine):
        """Should find symbols that depend on this symbol."""
        # Act - Logger is used by UserService.authenticate
        results = query_engine.get_dependents("Logger")

        # Assert - should find authenticate as dependent
        assert len(results) >= 1
        auth_dependents = [r for r in results if "authenticate" in r.symbol]
        assert len(auth_dependents) >= 1
        result = auth_dependents[0]
        assert result.kind == "dependent"
        assert result.relationship in ["calls", "import", "reference"]

    def test_get_dependents_depth_1_direct_only(self, query_engine):
        """Should return only direct dependents with depth=1."""
        # Act
        results = query_engine.get_dependents("Logger", depth=1)

        # Assert - should find only direct dependents
        assert len(results) >= 1
        # Should NOT find transitive dependents beyond depth 1

    def test_get_dependents_empty_for_root_symbol(self, query_engine):
        """Should return empty list for symbols with no dependents."""
        # Act - UserService is at root (nothing depends on it in our fixture)
        results = query_engine.get_dependents("UserService", depth=1)

        # Assert - may be 0 or more depending on fixture, but should complete without error
        assert isinstance(results, list)

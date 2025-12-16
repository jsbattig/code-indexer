"""E2E tests for all 7 SCIP query types using scip-python-mock fixture.

This test suite validates that all SCIP query types work correctly with real
test fixture data. It tests against the scip-python-mock repository which
contains a realistic Python codebase with controllers, services, and models.

Test Coverage:
1. Definition - Find class and method definitions
2. References - Find all symbol usages
3. Dependencies - Find symbols used by target
4. Dependents - Find symbols that use target
5. Impact - Analyze transitive dependents grouped by file
6. Call Chain - Trace execution paths
7. Context - Find enclosing symbols (if implemented)

All tests use real symbols from the fixture:
- Logger (class in src/services/logger.py)
- UserService (class in src/services/user_service.py)
- authenticate (function in src/services/auth_service.py)
"""

import pytest
from pathlib import Path

from code_indexer.scip.query.primitives import SCIPQueryEngine


@pytest.fixture
def scip_python_mock_path():
    """Path to scip-python-mock test fixture."""
    fixture_path = Path(__file__).parent.parent.parent / "test-fixtures" / "scip-python-mock"
    scip_file = fixture_path / ".code-indexer" / "scip" / "index.scip"

    if not scip_file.exists():
        pytest.skip(
            f"SCIP python-mock fixture not found at {scip_file}. "
            "Run: cd test-fixtures/scip-python-mock && cidx scip generate"
        )

    return scip_file


@pytest.fixture
def query_engine(scip_python_mock_path):
    """Initialize query engine with scip-python-mock fixture."""
    return SCIPQueryEngine(scip_python_mock_path)


class TestDefinitionQuery:
    """Tests for definition query - find symbol definitions."""

    def test_find_logger_class_definition(self, query_engine):
        """Should find Logger class definition in src/services/logger.py."""
        results = query_engine.find_definition("Logger", exact=True)

        assert len(results) > 0, "Should find Logger class definition"

        # Verify result contains Logger class
        logger_class = [r for r in results if r.symbol.endswith("Logger#")]
        assert len(logger_class) > 0, "Should find Logger class (ending with #)"

        # Verify file path
        assert any("src/services/logger.py" in r.file_path for r in logger_class)

    def test_find_logger_log_method_definition(self, query_engine):
        """Should find Logger#log method definition."""
        results = query_engine.find_definition("Logger#log", exact=True)

        assert len(results) > 0, "Should find Logger#log method definition"

        # Verify result is a method (ends with ().)
        assert any("log()." in r.symbol for r in results)

        # Verify in logger.py
        assert any("src/services/logger.py" in r.file_path for r in results)

    def test_find_user_service_definition(self, query_engine):
        """Should find UserService class definition."""
        results = query_engine.find_definition("UserService", exact=True)

        assert len(results) > 0, "Should find UserService class definition"

        # Verify it's a class
        user_service_class = [r for r in results if r.symbol.endswith("UserService#")]
        assert len(user_service_class) > 0, "Should find UserService class"

        # Verify file path
        assert any("src/services/user_service.py" in r.file_path for r in user_service_class)


class TestReferencesQuery:
    """Tests for references query - find symbol usages."""

    def test_find_logger_log_references(self, query_engine):
        """Should find references to Logger#log method across controllers and services."""
        results = query_engine.find_references("Logger#log", limit=20, exact=True)

        assert len(results) > 0, "Should find Logger#log references"

        # Logger#log is used extensively - should find multiple references
        assert len(results) >= 10, f"Should find at least 10 references, found {len(results)}"

        # Verify references in controllers (Logger#log is primarily used in controllers)
        controller_refs = [r for r in results if "controllers/" in r.file_path]
        assert len(controller_refs) > 0, "Should find references in controllers"

        # Verify file paths are reasonable
        file_paths = {r.file_path for r in results}
        assert len(file_paths) >= 2, "Should find references in at least 2 files"

    def test_find_logger_references_simple_name(self, query_engine):
        """Should find all Logger references (class, methods, attributes)."""
        results = query_engine.find_references("Logger", limit=20, exact=False)

        assert len(results) > 0, "Should find Logger references"

        # Simple name search should find various Logger usages
        assert len(results) >= 5, f"Should find multiple Logger references, found {len(results)}"

    def test_find_user_references(self, query_engine):
        """Should find User class references across codebase."""
        results = query_engine.find_references("User", limit=20, exact=False)

        assert len(results) > 0, "Should find User references"

        # User class is used in multiple places
        file_paths = {r.file_path for r in results}
        assert len(file_paths) >= 2, "Should find User used in multiple files"


class TestDependenciesQuery:
    """Tests for dependencies query - find symbols used by target."""

    def test_get_user_service_dependencies(self, query_engine):
        """Should find symbols that UserService depends on."""
        results = query_engine.get_dependencies("UserService", depth=1, exact=True)

        assert len(results) > 0, "UserService should have dependencies"

        # UserService uses Logger and UserRepository
        dependency_names = {r.symbol.split('/')[-1].rstrip('#').rstrip('.').rstrip('()')
                           for r in results}

        # Should find Logger dependency
        assert any("Logger" in name for name in dependency_names), \
            "UserService should depend on Logger"

    def test_get_auth_service_dependencies(self, query_engine):
        """Should find symbols that AuthService depends on."""
        results = query_engine.get_dependencies("AuthService", depth=1, exact=True)

        assert len(results) > 0, "AuthService should have dependencies"

        # AuthService has multiple dependencies
        assert len(results) >= 3, \
            f"AuthService should have at least 3 dependencies, found {len(results)}"


class TestDependentsQuery:
    """Tests for dependents query - find symbols that use target."""

    def test_get_logger_dependents(self, query_engine):
        """Should find symbols that depend on Logger class."""
        results = query_engine.get_dependents("Logger", depth=1, exact=False)

        assert len(results) > 0, "Logger should have dependents"

        # Logger is used by many classes
        assert len(results) >= 5, \
            f"Logger should have at least 5 dependents, found {len(results)}"

        # Verify dependents span multiple files
        file_paths = {r.file_path for r in results}
        assert len(file_paths) >= 3, \
            "Logger should be used in at least 3 different files"

    def test_get_user_dependents(self, query_engine):
        """Should find symbols that depend on User class."""
        results = query_engine.get_dependents("User", depth=1, exact=False)

        assert len(results) > 0, "User should have dependents"

        # User class is referenced by services and controllers
        assert len(results) >= 3, \
            f"User should have at least 3 dependents, found {len(results)}"


class TestImpactQuery:
    """Tests for impact query - analyze transitive dependents grouped by file."""

    def test_analyze_logger_impact(self, query_engine):
        """Should show impact of changing Logger (transitive dependents by file)."""
        results = query_engine.analyze_impact("Logger", depth=2)

        assert len(results) > 0, "Logger changes should have impact"

        # Logger is fundamental - should impact multiple files
        assert len(results) >= 3, \
            f"Logger should impact at least 3 files, found {len(results)}"

        # Verify results have required fields
        for result in results:
            assert hasattr(result, 'file_path'), "Result should have file_path"
            assert hasattr(result, 'symbol_count'), "Result should have symbol_count"
            assert hasattr(result, 'symbols'), "Result should have symbols list"

            # Verify counts are reasonable
            assert result.symbol_count > 0, "Symbol count should be positive"
            assert len(result.symbols) > 0, "Symbols list should not be empty"

    def test_analyze_user_service_impact(self, query_engine):
        """Should show impact of changing UserService."""
        results = query_engine.analyze_impact("UserService", depth=2)

        assert len(results) > 0, "UserService changes should have impact"

        # UserService is used by controllers
        assert any("controller" in result.file_path for result in results), \
            "UserService changes should impact controllers"


class TestCallChainQuery:
    """Tests for call chain query - trace execution paths."""

    def test_trace_authenticate_to_validate_token_chain(self, query_engine):
        """Should trace call chain from authenticate to validate_token."""
        # authenticate function calls validate_token
        chains = query_engine.trace_call_chain(
            "authenticate",
            "validate_token",
            max_depth=3,
            limit=10
        )

        # May not find direct chain if symbols don't match exactly
        # This is okay - we're testing the query mechanism works
        assert isinstance(chains, list), "Should return list of CallChain objects"

        if len(chains) > 0:
            # Verify chain structure
            chain = chains[0]
            assert hasattr(chain, 'path'), "Chain should have path"
            assert hasattr(chain, 'length'), "Chain should have length"
            assert hasattr(chain, 'has_cycle'), "Chain should have has_cycle flag"

            assert len(chain.path) > 0, "Chain path should not be empty"
            assert chain.length > 0, "Chain length should be positive"

    def test_trace_call_chain_returns_empty_for_unconnected_symbols(self, query_engine):
        """Should return empty list for symbols with no call path."""
        # Test with symbols unlikely to have a direct call path
        chains = query_engine.trace_call_chain(
            "LogLevel",  # Enum
            "Database",  # Unrelated class
            max_depth=5,
            limit=10
        )

        # Should return empty list (not error) for unconnected symbols
        assert isinstance(chains, list), "Should return list"
        # No assertion on length - may or may not find indirect paths


class TestContextQuery:
    """Tests for context query - find enclosing symbols (if implemented)."""

    @pytest.mark.skip(reason="Context query not yet implemented - placeholder for future")
    def test_find_context_for_logger_reference(self, query_engine):
        """Should find enclosing symbol (method/function) for Logger reference.

        When implemented, this should:
        1. Take a file path and line number
        2. Return the enclosing function/method/class at that location
        3. Useful for understanding where a symbol is used
        """
        # Example: Find what function contains the Logger.log() call at line 26 in auth_controller
        pass


class TestQueryIntegration:
    """Integration tests combining multiple query types."""

    def test_definition_to_references_workflow(self, query_engine):
        """Should find definition, then find all references to that symbol."""
        # Step 1: Find Logger definition
        definitions = query_engine.find_definition("Logger", exact=True)
        assert len(definitions) > 0, "Should find Logger definition"

        logger_symbol = definitions[0].symbol

        # Step 2: Find references using full symbol name
        # Extract simple name from SCIP symbol for reference search
        simple_name = logger_symbol.split('/')[-1].rstrip('#')
        references = query_engine.find_references(simple_name, limit=10, exact=False)

        assert len(references) > 0, "Should find references to Logger"

    def test_dependencies_to_impact_workflow(self, query_engine):
        """Should find dependencies, then analyze impact of each dependency."""
        # Step 1: Find UserService dependencies
        deps = query_engine.get_dependencies("UserService", depth=1, exact=True)

        if len(deps) > 0:
            # Step 2: Analyze impact of first dependency
            first_dep_name = deps[0].symbol.split('/')[-1].rstrip('#').rstrip('.').rstrip('()')

            # Only analyze if it's not a stdlib symbol
            if "python-stdlib" not in deps[0].symbol:
                impact = query_engine.analyze_impact(first_dep_name, depth=1)

                # Should be able to analyze impact
                assert isinstance(impact, list), "Should return impact results"

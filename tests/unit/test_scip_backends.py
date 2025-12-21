"""Unit tests for SCIP query backend abstraction."""

import pytest
from pathlib import Path

try:
    from pysqlite3 import dbapi2 as sqlite3
except ImportError:
    import sqlite3


@pytest.fixture
def scip_fixture_path():
    """Path to comprehensive SCIP test fixture."""
    return (
        Path(__file__).parent.parent / "scip" / "fixtures" / "comprehensive_index.scip"
    )


@pytest.fixture
def db_fixture_path(scip_fixture_path):
    """Path to SCIP database fixture (must exist)."""
    db_path = Path(str(scip_fixture_path) + ".db")
    if not db_path.exists():
        pytest.skip(f"Database fixture not available: {db_path}")
    return db_path


class TestDatabaseBackend:
    """Tests for DatabaseBackend implementation."""

    def test_database_backend_initialization(self, db_fixture_path):
        """Should initialize DatabaseBackend with database connection."""
        from code_indexer.scip.query.backends import DatabaseBackend

        backend = DatabaseBackend(db_fixture_path)

        assert backend.db_path == db_fixture_path
        assert backend.conn is not None
        assert isinstance(backend.conn, sqlite3.Connection)

    def test_database_backend_find_definition(self, db_fixture_path):
        """Should find symbol definitions using database queries."""
        from code_indexer.scip.query.backends import DatabaseBackend
        from code_indexer.scip.query.primitives import QueryResult

        backend = DatabaseBackend(db_fixture_path)

        results = backend.find_definition("UserService", exact=True)

        assert len(results) > 0
        assert all(isinstance(r, QueryResult) for r in results)
        assert all(r.kind == "definition" for r in results)
        assert any("UserService" in r.symbol for r in results)

    def test_database_backend_find_references(self, db_fixture_path):
        """Should find symbol references using database queries."""
        from code_indexer.scip.query.backends import DatabaseBackend
        from code_indexer.scip.query.primitives import QueryResult

        backend = DatabaseBackend(db_fixture_path)

        results = backend.find_references("UserService#authenticate().", limit=10, exact=True)

        assert len(results) > 0
        assert all(isinstance(r, QueryResult) for r in results)
        assert all(r.kind == "reference" for r in results)

    def test_database_backend_find_references_substring(self, db_fixture_path):
        """Should find symbol references using substring matching (exact=False).

        Bug reproduction: DatabaseBackend.find_references() returns empty list
        when exact=False, even though database contains matching symbols.

        This test verifies the fix that enables LIKE pattern matching in the
        database query when exact=False.
        """
        from code_indexer.scip.query.backends import DatabaseBackend
        from code_indexer.scip.query.primitives import QueryResult

        backend = DatabaseBackend(db_fixture_path)

        # Test substring matching: "UserService" should match full symbols like
        # ".../.../UserService#authenticate()." in the database
        results = backend.find_references("UserService", limit=10, exact=False)

        # Should find references (not empty)
        assert len(results) > 0, "find_references with exact=False should return results for substring matching"
        assert all(isinstance(r, QueryResult) for r in results)
        assert all(r.kind == "reference" for r in results)
        # Verify substring matching worked - all symbols should contain "UserService"
        assert all("UserService" in r.symbol for r in results)

    def test_database_backend_get_dependencies(self, db_fixture_path):
        """Should find symbol dependencies using database queries."""
        from code_indexer.scip.query.backends import DatabaseBackend
        from code_indexer.scip.query.primitives import QueryResult

        backend = DatabaseBackend(db_fixture_path)

        results = backend.get_dependencies("UserService", depth=1, exact=True)

        # May or may not have results depending on fixture
        assert isinstance(results, list)
        assert all(isinstance(r, QueryResult) for r in results)
        if len(results) > 0:
            assert all(r.kind == "dependency" for r in results)

    def test_database_backend_get_dependents(self, db_fixture_path):
        """Should find symbol dependents using database queries."""
        from code_indexer.scip.query.backends import DatabaseBackend
        from code_indexer.scip.query.primitives import QueryResult

        backend = DatabaseBackend(db_fixture_path)

        results = backend.get_dependents("Logger", depth=1, exact=True)

        # May or may not have results depending on fixture
        assert isinstance(results, list)
        assert all(isinstance(r, QueryResult) for r in results)
        if len(results) > 0:
            assert all(r.kind == "dependent" for r in results)

    def test_database_backend_analyze_impact_validates_depth(self, db_fixture_path):
        """
        Test that DatabaseBackend.analyze_impact() validates depth parameter.

        Given invalid depth values (< 1 or > 10)
        When analyze_impact() is called
        Then ValueError is raised with appropriate message

        This tests Issue #3 from Story #603 code review (backends.py line 264).
        """
        from code_indexer.scip.query.backends import DatabaseBackend

        backend = DatabaseBackend(db_fixture_path)

        # Test depth < 1
        with pytest.raises(ValueError, match="Depth must be between 1 and 10"):
            backend.analyze_impact("SomeSymbol", depth=0)

        # Test depth > 10
        with pytest.raises(ValueError, match="Depth must be between 1 and 10"):
            backend.analyze_impact("SomeSymbol", depth=11)

    def test_database_backend_trace_call_chain(self, db_fixture_path):
        """
        Test DatabaseBackend.trace_call_chain() discovers call chains.

        Given a database with call graph edges
        When trace_call_chain() is called
        Then results contain CallChain objects with path, length, has_cycle
        """
        from code_indexer.scip.query.backends import DatabaseBackend, CallChain

        backend = DatabaseBackend(db_fixture_path)

        # Try to trace a call chain (may not find any depending on fixture)
        results = backend.trace_call_chain("UserService", "Logger", max_depth=3)

        # Assertions
        assert isinstance(results, list)
        assert all(isinstance(r, CallChain) for r in results)
        if len(results) > 0:
            # Verify CallChain structure
            for chain in results:
                assert isinstance(chain.path, list)
                assert len(chain.path) > 0
                assert isinstance(chain.length, int)
                assert chain.length >= 1
                assert isinstance(chain.has_cycle, bool)

    def test_get_dependencies_performance_no_redundant_expansion(self):
        """
        Test that get_dependencies completes in <1 second for class symbols.

        Validates that SQL CTE handles class-to-method expansion instead of
        Python code making N separate SQL calls (Story #611 performance fix).

        Given a class symbol with many methods (e.g., SmartIndexer with ~30 methods)
        When get_dependencies is called with depth=3
        Then it should complete in <1 second (not 4+ seconds from redundant expansion)
        """
        import time
        from code_indexer.scip.query.backends import DatabaseBackend

        # Get project root dynamically
        project_root = Path(__file__).resolve().parent.parent.parent
        db_path = project_root / ".code-indexer/scip/index.scip.db"
        scip_file = project_root / ".code-indexer/scip/code-indexer.scip"

        if not db_path.exists():
            pytest.skip(f"Database not found: {db_path}")
        if not scip_file.exists():
            pytest.skip(f"SCIP file not found: {scip_file}")

        backend = DatabaseBackend(db_path, project_root=str(project_root), scip_file=scip_file)

        # Query SmartIndexer class (ends with #, has ~30 methods)
        start = time.time()
        results = backend.get_dependencies("SmartIndexer", depth=3, exact=False)
        elapsed = time.time() - start

        # Performance assertion: Should complete in <1 second
        # Before fix: 4.3s (37 separate SQL calls)
        # After fix: <1s (1 SQL call with CTE expansion)
        assert elapsed < 1.0, f"get_dependencies took {elapsed:.3f}s, expected <1.0s"

        # Sanity check: Should find some dependencies
        assert isinstance(results, list)

    def test_get_dependents_performance_no_redundant_expansion(self):
        """
        Test that get_dependents completes in <1 second for class symbols.

        Validates that SQL CTE handles class-to-method expansion instead of
        Python code making N separate SQL calls (Story #611 performance fix).

        Given a class symbol with many methods
        When get_dependents is called with depth=3
        Then it should complete in <1 second
        """
        import time
        from code_indexer.scip.query.backends import DatabaseBackend

        # Get project root dynamically
        project_root = Path(__file__).resolve().parent.parent.parent
        db_path = project_root / ".code-indexer/scip/index.scip.db"
        scip_file = project_root / ".code-indexer/scip/code-indexer.scip"

        if not db_path.exists():
            pytest.skip(f"Database not found: {db_path}")
        if not scip_file.exists():
            pytest.skip(f"SCIP file not found: {scip_file}")

        backend = DatabaseBackend(db_path, project_root=str(project_root), scip_file=scip_file)

        # Query FileFinder class (should have methods)
        start = time.time()
        results = backend.get_dependents("FileFinder", depth=3, exact=False)
        elapsed = time.time() - start

        # Performance assertion: Should complete in <1 second
        assert elapsed < 1.0, f"get_dependents took {elapsed:.3f}s, expected <1.0s"

        # Sanity check: Should find some dependents
        assert isinstance(results, list)

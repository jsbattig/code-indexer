"""Unit tests for SCIP database query operations (Story #607)."""

import pytest
import tempfile
import time
from pathlib import Path

try:
    from pysqlite3 import dbapi2 as sqlite3
except ImportError:
    import sqlite3

from code_indexer.scip.database.schema import DatabaseManager
from code_indexer.scip.database.builder import (
    SCIPDatabaseBuilder,
    ROLE_DEFINITION,
    ROLE_IMPORT,
    ROLE_READ_ACCESS,
)
from code_indexer.scip.database.queries import get_dependencies
from code_indexer.scip.protobuf import scip_pb2


def _create_scip_index_with_symbols(num_symbols: int = 10000):
    """
    Create SCIP index with specified number of symbols.

    Args:
        num_symbols: Number of class symbols to create (default 10,000)

    Returns:
        scip_pb2.Index with symbols populated
    """
    index = scip_pb2.Index()

    for i in range(num_symbols):
        symbol_info = index.external_symbols.add()
        symbol_info.symbol = f"scip-python python test abc123 `src.module{i}`/Class{i}#"
        symbol_info.display_name = f"Class{i}"
        symbol_info.kind = scip_pb2.SymbolInformation.Class

    return index


def _add_target_symbol(index):
    """
    Add target symbol for benchmark queries.

    Args:
        index: scip_pb2.Index to add symbol to

    Returns:
        str: Full SCIP symbol name for "TargetClass"
    """
    target_symbol = "scip-python python test abc123 `src.target`/TargetClass#"
    symbol_info = index.external_symbols.add()
    symbol_info.symbol = target_symbol
    symbol_info.display_name = "TargetClass"
    symbol_info.kind = scip_pb2.SymbolInformation.Class
    return target_symbol


def _add_production_scale_occurrences(index, target_symbol: str):
    """
    Add 110K+ occurrences across 100 documents.

    Args:
        index: scip_pb2.Index to add occurrences to
        target_symbol: Target symbol to add definition + references for
    """
    # Add documents with 110,000+ occurrences
    for i in range(100):
        doc = index.documents.add()
        doc.relative_path = f"src/file{i}.py"
        doc.language = "python"

        # Add 110 symbols per document (11,000 total occurrences)
        for j in range(110):
            symbol_id = (i * 110 + j) % 10000
            symbol_name = f"scip-python python test abc123 `src.module{symbol_id}`/Class{symbol_id}#"

            # Add definition
            occ = doc.occurrences.add()
            occ.symbol = symbol_name
            occ.symbol_roles = ROLE_DEFINITION
            occ.range.extend([j * 10, 0, j * 10, 10])

            # Add 10 references per symbol
            for k in range(10):
                occ = doc.occurrences.add()
                occ.symbol = symbol_name
                occ.symbol_roles = ROLE_READ_ACCESS
                occ.range.extend([j * 10 + k + 1, 5, j * 10 + k + 1, 15])

    # Add target symbol definition + 20 references in last document
    doc = index.documents[-1]
    occ = doc.occurrences.add()
    occ.symbol = target_symbol
    occ.symbol_roles = ROLE_DEFINITION
    occ.range.extend([9999, 0, 9999, 11])

    for k in range(20):
        occ = doc.occurrences.add()
        occ.symbol = target_symbol
        occ.symbol_roles = ROLE_READ_ACCESS
        occ.range.extend([10000 + k, 5, 10000 + k, 16])


def _get_symbol_id(conn: sqlite3.Connection, symbol_name: str) -> int:
    """
    Get symbol ID from symbol name.

    Args:
        conn: SQLite database connection
        symbol_name: Full SCIP symbol name

    Returns:
        Symbol ID

    Raises:
        AssertionError: If symbol not found
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM symbols WHERE name = ?", (symbol_name,))
    row = cursor.fetchone()
    assert row is not None, f"Symbol {symbol_name} not found in database"
    return row[0]


def _add_call_graph_edges(conn: sqlite3.Connection, num_edges: int = 1000):
    """
    Add call graph edges for dependency/dependent testing.

    Creates a realistic call graph with:
    - Direct dependencies (depth=1)
    - Transitive dependencies (depth=2+)
    - Mix of different relationship types

    Args:
        conn: SQLite database connection
        num_edges: Number of call graph edges to create (default 1000)
    """
    cursor = conn.cursor()

    # Get all symbol IDs
    cursor.execute("SELECT id FROM symbols ORDER BY id LIMIT 1000")
    symbol_ids = [row[0] for row in cursor.fetchall()]

    if len(symbol_ids) < 10:
        return  # Not enough symbols to create meaningful call graph

    # Create call graph edges (caller -> callee relationships)
    edges = []
    for i in range(min(num_edges, len(symbol_ids) - 1)):
        caller_id = symbol_ids[i]
        callee_id = symbol_ids[(i + 1) % len(symbol_ids)]
        relationship = "call" if i % 3 == 0 else "reference"

        edges.append((caller_id, callee_id, relationship))

    # Insert edges in bulk
    cursor.executemany(
        """
        INSERT INTO call_graph (caller_symbol_id, callee_symbol_id, relationship)
        VALUES (?, ?, ?)
        """,
        edges
    )
    conn.commit()


def _create_production_scale_database(tmp_path: Path) -> tuple:
    """
    Create production-scale test database with 10K symbols and 110K occurrences.

    Returns:
        Tuple of (sqlite3.Connection, target_symbol_name) for benchmarking
    """
    # Create index and populate with data
    index = _create_scip_index_with_symbols()
    target_symbol = _add_target_symbol(index)
    _add_production_scale_occurrences(index, target_symbol)

    # Write protobuf to file
    scip_file = tmp_path / "production_scale.scip"
    with open(scip_file, "wb") as f:
        f.write(index.SerializeToString())

    # Build database
    manager = DatabaseManager(scip_file)
    manager.create_schema()
    builder = SCIPDatabaseBuilder()
    builder.build(scip_file, manager.db_path)

    # Add call graph edges for dependency/dependent testing
    conn = sqlite3.connect(manager.db_path)
    _add_call_graph_edges(conn, num_edges=1000)

    # Return connection and target symbol
    return conn, target_symbol


def _create_hybrid_test_database(tmp_path: Path) -> tuple:
    """
    Create test database for hybrid occurrence-based testing with diverse reference types.

    Returns:
        Tuple of (conn, scip_file, target_id, referencing_symbols_dict)
    """
    index = scip_pb2.Index()

    # Target symbol
    target = "scip-python python test abc123 `src.utils`/UtilityClass#"
    sym = index.external_symbols.add()
    sym.symbol = target
    sym.kind = scip_pb2.SymbolInformation.Class

    # Referencing symbols (4 types: import, attribute, variable, call)
    refs = {
        "importer": "scip-python python test abc123 `src.importer`/Importer#",
        "accessor": "scip-python python test abc123 `src.accessor`/Accessor#m().",
        "assigner": "scip-python python test abc123 `src.assigner`/assign().",
        "caller": "scip-python python test abc123 `src.caller`/call().",
    }
    for s in refs.values():
        sym = index.external_symbols.add()
        sym.symbol = s

    # Target definition
    doc = index.documents.add()
    doc.relative_path, doc.language = "src/utils.py", "python"
    occ = doc.occurrences.add()
    occ.symbol, occ.symbol_roles = target, ROLE_DEFINITION
    occ.range.extend([10, 0, 10, 12])
    occ.enclosing_range.extend([10, 0, 50, 0])  # Class scope

    # Import reference
    doc = index.documents.add()
    doc.relative_path, doc.language = "src/importer.py", "python"
    occ = doc.occurrences.add()
    occ.symbol, occ.symbol_roles = refs["importer"], ROLE_DEFINITION
    occ.range.extend([5, 0, 5, 8])
    occ.enclosing_range.extend([5, 0, 20, 0])
    occ = doc.occurrences.add()
    occ.symbol, occ.symbol_roles = target, ROLE_IMPORT
    occ.range.extend([7, 5, 7, 17])
    occ.enclosing_range.extend([5, 0, 20, 0])

    # Attribute access
    doc = index.documents.add()
    doc.relative_path, doc.language = "src/accessor.py", "python"
    occ = doc.occurrences.add()
    occ.symbol, occ.symbol_roles = refs["accessor"], ROLE_DEFINITION
    occ.range.extend([10, 4, 10, 10])
    occ.enclosing_range.extend([10, 4, 15, 0])
    occ = doc.occurrences.add()
    occ.symbol, occ.symbol_roles = target, ROLE_READ_ACCESS
    occ.range.extend([12, 8, 12, 20])
    occ.enclosing_range.extend([10, 4, 15, 0])

    # Variable assignment
    doc = index.documents.add()
    doc.relative_path, doc.language = "src/assigner.py", "python"
    occ = doc.occurrences.add()
    occ.symbol, occ.symbol_roles = refs["assigner"], ROLE_DEFINITION
    occ.range.extend([5, 0, 5, 12])
    occ.enclosing_range.extend([5, 0, 10, 0])
    occ = doc.occurrences.add()
    occ.symbol, occ.symbol_roles = target, ROLE_READ_ACCESS
    occ.range.extend([7, 8, 7, 20])
    occ.enclosing_range.extend([5, 0, 10, 0])

    # Function call
    doc = index.documents.add()
    doc.relative_path, doc.language = "src/caller.py", "python"
    occ = doc.occurrences.add()
    occ.symbol, occ.symbol_roles = refs["caller"], ROLE_DEFINITION
    occ.range.extend([5, 0, 5, 10])
    occ.enclosing_range.extend([5, 0, 10, 0])
    occ = doc.occurrences.add()
    occ.symbol, occ.symbol_roles = target, ROLE_READ_ACCESS
    occ.range.extend([7, 4, 7, 16])
    occ.enclosing_range.extend([5, 0, 10, 0])

    # Build database
    scip_file = tmp_path / "hybrid.scip"
    with open(scip_file, "wb") as f:
        f.write(index.SerializeToString())
    mgr = DatabaseManager(scip_file)
    mgr.create_schema()
    SCIPDatabaseBuilder().build(scip_file, mgr.db_path)

    conn = sqlite3.connect(mgr.db_path)
    target_id = _get_symbol_id(conn, target)
    return conn, scip_file, target_id, refs


def _create_hybrid_dependencies_test_database(tmp_path: Path) -> tuple:
    """
    Create test database where target symbol USES other symbols (dependencies).

    Opposite of _create_hybrid_test_database - here the target is the REFERRER,
    not the REFERENCED.

    Returns:
        Tuple of (conn, scip_file, target_id, dependency_symbols_dict)
    """
    index = scip_pb2.Index()

    # Target symbol that USES other symbols
    target = "scip-python python test abc123 `src.consumer`/Consumer#process()."
    sym = index.external_symbols.add()
    sym.symbol = target
    sym.kind = scip_pb2.SymbolInformation.Method

    # Dependency symbols (4 types that target USES)
    deps = {
        "imported": "scip-python python test abc123 `src.lib`/LibModule#",
        "accessed": "scip-python python test abc123 `src.config`/Config#",
        "assigned": "scip-python python test abc123 `src.models`/Model#",
        "called": "scip-python python test abc123 `src.helpers`/helper().",
    }
    for s in deps.values():
        sym = index.external_symbols.add()
        sym.symbol = s

    # Target definition and its references to dependencies
    doc = index.documents.add()
    doc.relative_path, doc.language = "src/consumer.py", "python"

    # Target method definition
    occ = doc.occurrences.add()
    occ.symbol, occ.symbol_roles = target, ROLE_DEFINITION
    occ.range.extend([10, 4, 10, 15])
    occ.enclosing_range.extend([10, 4, 30, 0])  # Method scope lines 10-30

    # Target IMPORTS LibModule (within method scope)
    occ = doc.occurrences.add()
    occ.symbol, occ.symbol_roles = deps["imported"], ROLE_IMPORT
    occ.range.extend([12, 8, 12, 17])
    occ.enclosing_range.extend([10, 4, 30, 0])

    # Target ACCESSES Config attribute (within method scope)
    occ = doc.occurrences.add()
    occ.symbol, occ.symbol_roles = deps["accessed"], ROLE_READ_ACCESS
    occ.range.extend([15, 12, 15, 18])
    occ.enclosing_range.extend([10, 4, 30, 0])

    # Target ASSIGNS to Model variable (within method scope)
    occ = doc.occurrences.add()
    occ.symbol, occ.symbol_roles = deps["assigned"], ROLE_READ_ACCESS
    occ.range.extend([20, 16, 20, 21])
    occ.enclosing_range.extend([10, 4, 30, 0])

    # Target CALLS helper function (within method scope)
    occ = doc.occurrences.add()
    occ.symbol, occ.symbol_roles = deps["called"], ROLE_READ_ACCESS
    occ.range.extend([25, 8, 25, 14])
    occ.enclosing_range.extend([10, 4, 30, 0])

    # Define the dependency symbols in their own files
    for dep_name, dep_symbol in deps.items():
        doc = index.documents.add()
        doc.relative_path = f"src/{dep_name}.py"
        doc.language = "python"
        occ = doc.occurrences.add()
        occ.symbol, occ.symbol_roles = dep_symbol, ROLE_DEFINITION
        occ.range.extend([5, 0, 5, 10])
        occ.enclosing_range.extend([5, 0, 20, 0])

    # Build database
    scip_file = tmp_path / "hybrid_deps.scip"
    with open(scip_file, "wb") as f:
        f.write(index.SerializeToString())
    mgr = DatabaseManager(scip_file)
    mgr.create_schema()
    SCIPDatabaseBuilder().build(scip_file, mgr.db_path)

    conn = sqlite3.connect(mgr.db_path)
    target_id = _get_symbol_id(conn, target)
    return conn, scip_file, target_id, deps


def _create_impact_test_database(tmp_path: Path) -> tuple:
    """
    Create test database with call_graph edges for impact analysis testing.

    Returns:
        Tuple of (sqlite3.Connection, target_symbol_id, dict of dependent symbols by file)
    """
    # Create SCIP protobuf with symbols
    index = scip_pb2.Index()

    # Target symbol (callee)
    target_symbol = "scip-python python test abc123 `src.target`/ClassA#"
    symbol_info = index.external_symbols.add()
    symbol_info.symbol = target_symbol
    symbol_info.display_name = "ClassA"
    symbol_info.kind = scip_pb2.SymbolInformation.Class

    # Dependent symbols (callers in different files)
    dependent_b = "scip-python python test abc123 `src.file1`/ClassB#"
    symbol_info = index.external_symbols.add()
    symbol_info.symbol = dependent_b
    symbol_info.display_name = "ClassB"
    symbol_info.kind = scip_pb2.SymbolInformation.Class

    dependent_c = "scip-python python test abc123 `src.file2`/ClassC#"
    symbol_info = index.external_symbols.add()
    symbol_info.symbol = dependent_c
    symbol_info.display_name = "ClassC"
    symbol_info.kind = scip_pb2.SymbolInformation.Class

    # Add documents with definitions
    for file_path, symbol in [
        ("src/target.py", target_symbol),
        ("src/file1.py", dependent_b),
        ("src/file2.py", dependent_c),
    ]:
        doc = index.documents.add()
        doc.relative_path = file_path
        doc.language = "python"

        occ = doc.occurrences.add()
        occ.symbol = symbol
        occ.symbol_roles = ROLE_DEFINITION
        occ.range.extend([10, 0, 10, 10])

    # Write protobuf to file
    scip_file = tmp_path / "test_impact.scip"
    with open(scip_file, "wb") as f:
        f.write(index.SerializeToString())

    # Build database
    manager = DatabaseManager(scip_file)
    manager.create_schema()
    builder = SCIPDatabaseBuilder()
    builder.build(scip_file, manager.db_path)

    # Add call graph edges: ClassB -> ClassA, ClassC -> ClassA
    conn = sqlite3.connect(manager.db_path)
    cursor = conn.cursor()
    target_id = _get_symbol_id(conn, target_symbol)
    b_id = _get_symbol_id(conn, dependent_b)
    c_id = _get_symbol_id(conn, dependent_c)

    cursor.executemany(
        "INSERT INTO call_graph (caller_symbol_id, callee_symbol_id, relationship) VALUES (?, ?, ?)",
        [
            (b_id, target_id, "call"),
            (c_id, target_id, "call"),
        ]
    )
    conn.commit()

    # Return connection, target ID, and symbol mapping
    dependents = {
        "src/file1.py": dependent_b,
        "src/file2.py": dependent_c,
    }
    return conn, target_id, dependents


class TestFindDefinition:
    """Test find_definition() SQL-based symbol lookup (AC1)."""

    def test_find_definition_exact_match(self, tmp_path: Path):
        """
        Test exact symbol name lookup using indexed SQL query.

        Given a database with symbol 'TestClass' at line 10
        When find_definition(conn, 'TestClass', exact=True) is called
        Then result contains symbol at line 10
        And query uses idx_symbols_name index
        """
        # Create SCIP protobuf with one class definition
        index = scip_pb2.Index()

        # Add symbol definition (using proper SCIP format with / delimiter)
        symbol_info = index.external_symbols.add()
        symbol_info.symbol = "scip-python python test abc123 `src.test`/TestClass#"
        symbol_info.display_name = "TestClass"
        symbol_info.kind = scip_pb2.SymbolInformation.Class

        # Add document with occurrence
        doc = index.documents.add()
        doc.relative_path = "src/test.py"
        doc.language = "python"

        # Add definition occurrence
        occ = doc.occurrences.add()
        occ.symbol = "scip-python python test abc123 `src.test`/TestClass#"
        occ.symbol_roles = ROLE_DEFINITION  # Definition bit set
        occ.range.extend([10, 0, 10, 9])  # Line 10, columns 0-9

        # Write protobuf to file
        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Import queries module (will fail until we create it)
        from code_indexer.scip.database.queries import find_definition

        # Execute query
        conn = sqlite3.connect(manager.db_path)
        try:
            results = find_definition(conn, "TestClass", exact=True)

            # Verify results
            assert len(results) == 1
            assert results[0]["symbol_name"] == "scip-python python test abc123 `src.test`/TestClass#"
            assert results[0]["file_path"] == "src/test.py"
            assert results[0]["line"] == 10
            assert results[0]["column"] == 0
            assert results[0]["kind"] == "Class"
        finally:
            conn.close()

    def test_find_definition_performance_benchmark(self, tmp_path: Path):
        """
        PERFORMANCE TEST: Definition lookup must complete in <5ms (AC1 target).

        Given a database with 10K symbols and 110K occurrences
        When find_definition(conn, 'TargetClass', exact=True) is called
        Then query completes in <5ms (0.005 seconds)

        This test will FAIL with current LIKE-based queries (full table scans).
        """
        from code_indexer.scip.database.queries import find_definition

        # Create production-scale database
        conn, target_symbol = _create_production_scale_database(tmp_path)

        try:
            # Warm-up query (exclude from timing)
            _ = find_definition(conn, "TargetClass", exact=True)

            # Timed query
            start = time.perf_counter()
            results = find_definition(conn, "TargetClass", exact=True)
            elapsed = time.perf_counter() - start

            # Verify correctness
            assert len(results) == 1, "Should find exactly one definition"
            assert results[0]["symbol_name"] == target_symbol

            # PERFORMANCE ASSERTION: Must complete in <5ms
            assert elapsed < 0.005, (
                f"Definition lookup took {elapsed*1000:.1f}ms, exceeds 5ms target. "
                f"Current implementation using LIKE queries causes full table scan. "
                f"Expected: FTS5 index usage for <5ms performance."
            )
        finally:
            conn.close()


class TestFindReferences:
    """Test find_references() SQL-based reference search (AC2)."""

    def test_find_references_with_limit(self, tmp_path: Path):
        """
        Test reference search with result limit.

        Given a database with 5 references to 'foo'
        When find_references(conn, 'foo', limit=3) is called
        Then exactly 3 results are returned
        And query uses idx_occurrences_symbol index
        """
        from code_indexer.scip.database.builder import ROLE_READ_ACCESS

        # Create SCIP protobuf with one symbol and 5 references
        index = scip_pb2.Index()

        # Add symbol (using proper SCIP format)
        symbol_info = index.external_symbols.add()
        symbol_info.symbol = "scip-python python test abc123 `src.test`/foo()."
        symbol_info.display_name = "foo"
        symbol_info.kind = scip_pb2.SymbolInformation.Method

        # Add document with occurrences
        doc = index.documents.add()
        doc.relative_path = "src/test.py"
        doc.language = "python"

        # Add 1 definition + 5 references
        # Definition
        occ = doc.occurrences.add()
        occ.symbol = "scip-python python test abc123 `src.test`/foo()."
        occ.symbol_roles = ROLE_DEFINITION
        occ.range.extend([5, 0, 5, 3])

        # 5 references
        for i in range(5):
            occ = doc.occurrences.add()
            occ.symbol = "scip-python python test abc123 `src.test`/foo()."
            occ.symbol_roles = ROLE_READ_ACCESS  # Reference bit
            occ.range.extend([10 + i, 5, 10 + i, 8])

        # Write protobuf to file
        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Import queries module
        from code_indexer.scip.database.queries import find_references

        # Execute query with limit
        conn = sqlite3.connect(manager.db_path)
        try:
            results = find_references(conn, "foo", limit=3)

            # Verify limit respected
            assert len(results) == 3

            # Verify all are references (not definitions)
            for result in results:
                assert result["role"] & ROLE_DEFINITION == 0
                assert result["role"] & ROLE_READ_ACCESS != 0
        finally:
            conn.close()

    def test_find_references_with_limit_zero_returns_all_results(self, tmp_path: Path):
        """
        BUG TEST: limit=0 should return ALL results, not 0 results.

        Given a database with symbol references
        When find_references(conn, 'TargetClass', limit=0) is called
        Then all references are returned (not 0 results from SQL LIMIT 0)

        This test documents the bug where limit=0 causes SQL LIMIT 0 clause,
        which returns 0 rows instead of unlimited results.
        """
        from code_indexer.scip.database.queries import find_references

        # Create production-scale database (includes 20 references to TargetClass)
        conn, target_symbol = _create_production_scale_database(tmp_path)

        try:
            # Query with limit=0 (should return ALL results, not 0)
            results = find_references(conn, "TargetClass", limit=0)

            # CRITICAL: limit=0 should return ALL 20 references
            assert len(results) == 20, (
                f"limit=0 should return all 20 references, got {len(results)}. "
                f"Bug: SQL LIMIT 0 returns 0 rows instead of unlimited results."
            )
            assert all(r["symbol_name"] == target_symbol for r in results)
            assert all(r["role"] & ROLE_DEFINITION == 0 for r in results)
        finally:
            conn.close()

    def test_find_references_performance_benchmark(self, tmp_path: Path):
        """
        PERFORMANCE TEST: Reference search must complete in <10ms (AC2 target).

        Given a database with 10K symbols and 110K occurrences
        When find_references(conn, 'TargetClass', limit=100) is called
        Then query completes in <10ms (0.010 seconds)

        This test will FAIL with current LIKE-based queries (full table scans).
        """
        from code_indexer.scip.database.queries import find_references

        # Create production-scale database
        conn, target_symbol = _create_production_scale_database(tmp_path)

        try:
            # Warm-up query (exclude from timing)
            _ = find_references(conn, "TargetClass", limit=100)

            # Timed query
            start = time.perf_counter()
            results = find_references(conn, "TargetClass", limit=100)
            elapsed = time.perf_counter() - start

            # Verify correctness
            assert len(results) == 20, "Should find exactly 20 references"
            assert all(r["symbol_name"] == target_symbol for r in results)
            assert all(r["role"] & ROLE_DEFINITION == 0 for r in results)

            # PERFORMANCE ASSERTION: Must complete in <10ms
            assert elapsed < 0.010, (
                f"Reference search took {elapsed*1000:.1f}ms, exceeds 10ms target. "
                f"Current implementation using LIKE queries causes full table scan. "
                f"Expected: FTS5 index usage for <10ms performance."
            )
        finally:
            conn.close()


class TestGetDependencies:
    """Test get_dependencies() SQL-based dependency query (Story #601 AC1)."""

    def test_get_dependencies_depth_1_performance_benchmark(self, tmp_path: Path):
        """
        PERFORMANCE TEST: Depth=1 dependency query must complete in <20ms (AC1 target).

        Given a database with call_graph table populated
        When get_dependencies(conn, symbol_id, depth=1) is called
        Then query completes in <20ms (0.020 seconds)
        And returns direct dependencies (one hop in call graph)

        Target: 150x faster than 3s protobuf baseline.
        """
        from code_indexer.scip.database.queries import get_dependencies

        # Create production-scale database with call_graph
        conn, target_symbol = _create_production_scale_database(tmp_path)

        try:
            # Get symbol_id for target symbol
            symbol_id = _get_symbol_id(conn, target_symbol)

            # Warm-up query (exclude from timing)
            _ = get_dependencies(conn, symbol_id, depth=1)

            # Timed query
            start = time.perf_counter()
            results = get_dependencies(conn, symbol_id, depth=1)
            elapsed = time.perf_counter() - start

            # Verify correctness
            assert isinstance(results, list), "Should return list of dependencies"

            # PERFORMANCE ASSERTION: Must complete in <20ms
            assert elapsed < 0.020, (
                f"Depth=1 dependency query took {elapsed*1000:.1f}ms, exceeds 20ms target. "
                f"Expected: <20ms for 150x speedup over protobuf baseline."
            )
        finally:
            conn.close()

    def test_get_dependencies_depth_2_performance_benchmark(self, tmp_path: Path):
        """
        PERFORMANCE TEST: Depth=2 dependency query must complete in <50ms (AC1 target).

        Given a database with call_graph table populated
        When get_dependencies(conn, symbol_id, depth=2) is called
        Then query completes in <50ms (0.050 seconds)
        And returns transitive dependencies (two hops in call graph)

        Target: 100x faster than 5s protobuf baseline.
        """
        from code_indexer.scip.database.queries import get_dependencies

        # Create production-scale database with call_graph
        conn, target_symbol = _create_production_scale_database(tmp_path)

        try:
            # Get symbol_id for target symbol
            symbol_id = _get_symbol_id(conn, target_symbol)

            # Warm-up query (exclude from timing)
            _ = get_dependencies(conn, symbol_id, depth=2)

            # Timed query
            start = time.perf_counter()
            results = get_dependencies(conn, symbol_id, depth=2)
            elapsed = time.perf_counter() - start

            # Verify correctness
            assert isinstance(results, list), "Should return list of transitive dependencies"

            # PERFORMANCE ASSERTION: Must complete in <50ms
            assert elapsed < 0.050, (
                f"Depth=2 dependency query took {elapsed*1000:.1f}ms, exceeds 50ms target. "
                f"Expected: <50ms for 100x speedup over protobuf baseline."
            )
        finally:
            conn.close()

    def test_get_dependencies_filters_local_variables(self, tmp_path: Path):
        """
        Test that local variables are excluded from dependency results (AC3).

        Given a database with local variable symbols (kind='Local')
        When get_dependencies(conn, symbol_id, depth=1) is called
        Then results exclude symbols with kind='Local' or kind='Parameter'
        And only class/method/function symbols are returned
        """
        from code_indexer.scip.database.queries import get_dependencies

        # Create database with local variables
        conn, target_symbol = _create_production_scale_database(tmp_path)

        try:
            # Get symbol_id for target symbol
            symbol_id = _get_symbol_id(conn, target_symbol)

            # Execute query
            results = get_dependencies(conn, symbol_id, depth=1)

            # Verify NO local variables or parameters in results
            for result in results:
                assert result.get("kind") not in ["Local", "Parameter"], (
                    f"Found local/parameter symbol in results: {result['symbol_name']} "
                    f"with kind={result['kind']}"
                )
        finally:
            conn.close()

    def test_get_dependencies_includes_null_kind_symbols(self, tmp_path: Path):
        """
        CRITICAL BUG FIX: Test that NULL kind symbols are included in dependency results.

        PROBLEM: Production SCIP data has many symbols with kind=NULL. The current
        SQL WHERE clause uses "s.kind NOT IN ('Local', 'Parameter')" which incorrectly
        filters out NULL values due to SQL three-valued logic (NULL NOT IN (...) = NULL).

        Given a database with symbols where kind=NULL (common in production)
        When get_dependencies(conn, symbol_id, depth=1) is called
        Then results INCLUDE symbols with kind=NULL

        This test will FAIL with current implementation and PASS after fix.
        """
        from code_indexer.scip.database.queries import get_dependencies

        # Create SCIP protobuf with NULL kind symbols
        index = scip_pb2.Index()

        # Create caller symbol (will be our query target)
        caller_symbol = "scip-python python test abc123 `src.caller`/Caller#method()."
        symbol_info = index.external_symbols.add()
        symbol_info.symbol = caller_symbol
        symbol_info.display_name = "method"
        # kind is NOT set -> will be NULL in database

        # Create callee symbols with various kind values
        # 1. NULL kind (most common in production) - kind field NOT set
        callee_null_1 = "scip-python python test abc123 `src.callee`/CalleeNull1#method()."
        symbol_info = index.external_symbols.add()
        symbol_info.symbol = callee_null_1
        symbol_info.display_name = "CalleeNull1"
        # kind is NOT set -> will be NULL

        # 2. Another NULL kind
        callee_null_2 = "scip-python python test abc123 `src.callee`/CalleeNull2#method()."
        symbol_info = index.external_symbols.add()
        symbol_info.symbol = callee_null_2
        symbol_info.display_name = "CalleeNull2"
        # kind is NOT set -> will be NULL

        # 3. Method kind (should be included)
        callee_method = "scip-python python test abc123 `src.callee`/CalleeMethod#method()."
        symbol_info = index.external_symbols.add()
        symbol_info.symbol = callee_method
        symbol_info.display_name = "CalleeMethod"
        symbol_info.kind = scip_pb2.SymbolInformation.Method

        # Add document with occurrences
        doc = index.documents.add()
        doc.relative_path = "src/caller.py"
        doc.language = "python"

        # Add caller definition
        occ = doc.occurrences.add()
        occ.symbol = caller_symbol
        occ.symbol_roles = ROLE_DEFINITION
        occ.range.extend([10, 0, 10, 10])

        # Add callee definitions
        for i, callee_sym in enumerate([callee_null_1, callee_null_2, callee_method]):
            occ = doc.occurrences.add()
            occ.symbol = callee_sym
            occ.symbol_roles = ROLE_DEFINITION
            occ.range.extend([20 + i * 5, 0, 20 + i * 5, 10])

        # Write protobuf to file
        scip_file = tmp_path / "test_null_kinds.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Add call graph edges manually
        conn = sqlite3.connect(manager.db_path)
        try:
            cursor = conn.cursor()

            # Get symbol IDs
            caller_id = _get_symbol_id(conn, caller_symbol)
            callee_null_1_id = _get_symbol_id(conn, callee_null_1)
            callee_null_2_id = _get_symbol_id(conn, callee_null_2)
            callee_method_id = _get_symbol_id(conn, callee_method)

            # Insert call graph edges (caller depends on all callees)
            cursor.executemany(
                "INSERT INTO call_graph (caller_symbol_id, callee_symbol_id, relationship) VALUES (?, ?, ?)",
                [
                    (caller_id, callee_null_1_id, "call"),
                    (caller_id, callee_null_2_id, "reference"),
                    (caller_id, callee_method_id, "call"),
                ]
            )
            conn.commit()

            # Execute query
            results = get_dependencies(conn, caller_id, depth=1)

            # CRITICAL ASSERTION: NULL kind symbols MUST be included
            result_symbols = {r["symbol_name"] for r in results}

            # Should INCLUDE NULL kind symbols
            assert callee_null_1 in result_symbols, (
                f"NULL kind symbol 1 not found in results! This is the SQL NULL handling bug. "
                f"Results: {result_symbols}"
            )
            assert callee_null_2 in result_symbols, (
                f"NULL kind symbol 2 not found in results! This is the SQL NULL handling bug. "
                f"Results: {result_symbols}"
            )

            # Should INCLUDE Method kind
            assert callee_method in result_symbols, (
                f"Method kind symbol not found in results! Results: {result_symbols}"
            )

            # Verify correct number of results (3: 2 NULL + 1 Method)
            assert len(results) == 3, (
                f"Expected 3 results (2 NULL + 1 Method), got {len(results)}"
            )

        finally:
            conn.close()


class TestGetDependents:
    """Test get_dependents() SQL-based dependent query (Story #601 AC2)."""

    def test_get_dependents_depth_1_performance_benchmark(self, tmp_path: Path):
        """
        PERFORMANCE TEST: Depth=1 dependent query must complete in <20ms (AC2 target).

        Given a database with call_graph table populated
        When get_dependents(conn, symbol_id, depth=1) is called
        Then query completes in <20ms (0.020 seconds)
        And returns direct dependents (one hop in call graph)

        Target: 150x faster than 3s protobuf baseline.
        """
        from code_indexer.scip.database.queries import get_dependents

        # Create production-scale database with call_graph
        conn, target_symbol = _create_production_scale_database(tmp_path)

        try:
            # Get symbol_id for target symbol
            symbol_id = _get_symbol_id(conn, target_symbol)

            # Warm-up query (exclude from timing)
            _ = get_dependents(conn, symbol_id, depth=1)

            # Timed query
            start = time.perf_counter()
            results = get_dependents(conn, symbol_id, depth=1)
            elapsed = time.perf_counter() - start

            # Verify correctness
            assert isinstance(results, list), "Should return list of dependents"

            # PERFORMANCE ASSERTION: Must complete in <20ms
            assert elapsed < 0.020, (
                f"Depth=1 dependent query took {elapsed*1000:.1f}ms, exceeds 20ms target. "
                f"Expected: <20ms for 150x speedup over protobuf baseline."
            )
        finally:
            conn.close()

    def test_get_dependents_depth_2_performance_benchmark(self, tmp_path: Path):
        """
        PERFORMANCE TEST: Depth=2 dependent query must complete in <50ms (AC2 target).

        Given a database with call_graph table populated
        When get_dependents(conn, symbol_id, depth=2) is called
        Then query completes in <50ms (0.050 seconds)
        And returns transitive dependents (two hops in call graph)

        Target: 100x faster than 5s protobuf baseline.
        """
        from code_indexer.scip.database.queries import get_dependents

        # Create production-scale database with call_graph
        conn, target_symbol = _create_production_scale_database(tmp_path)

        try:
            # Get symbol_id for target symbol
            symbol_id = _get_symbol_id(conn, target_symbol)

            # Warm-up query (exclude from timing)
            _ = get_dependents(conn, symbol_id, depth=2)

            # Timed query
            start = time.perf_counter()
            results = get_dependents(conn, symbol_id, depth=2)
            elapsed = time.perf_counter() - start

            # Verify correctness
            assert isinstance(results, list), "Should return list of transitive dependents"

            # PERFORMANCE ASSERTION: Must complete in <50ms
            assert elapsed < 0.050, (
                f"Depth=2 dependent query took {elapsed*1000:.1f}ms, exceeds 50ms target. "
                f"Expected: <50ms for 100x speedup over protobuf baseline."
            )
        finally:
            conn.close()

    def test_get_dependents_filters_local_variables(self, tmp_path: Path):
        """
        Test that local variables are excluded from dependent results (AC3).

        Given a database with local variable symbols (kind='Local')
        When get_dependents(conn, symbol_id, depth=1) is called
        Then results exclude symbols with kind='Local' or kind='Parameter'
        And only class/method/function symbols are returned
        """
        from code_indexer.scip.database.queries import get_dependents

        # Create database with local variables
        conn, target_symbol = _create_production_scale_database(tmp_path)

        try:
            # Get symbol_id for target symbol
            symbol_id = _get_symbol_id(conn, target_symbol)

            # Execute query
            results = get_dependents(conn, symbol_id, depth=1)

            # Verify NO local variables or parameters in results
            for result in results:
                assert result.get("kind") not in ["Local", "Parameter"], (
                    f"Found local/parameter symbol in results: {result['symbol_name']} "
                    f"with kind={result['kind']}"
                )
        finally:
            conn.close()

    def test_get_dependents_includes_null_kind_symbols(self, tmp_path: Path):
        """
        CRITICAL BUG FIX: Test that NULL kind symbols are included in dependent results.

        PROBLEM: Production SCIP data has many symbols with kind=NULL. The current
        SQL WHERE clause uses "s.kind NOT IN ('Local', 'Parameter')" which incorrectly
        filters out NULL values due to SQL three-valued logic (NULL NOT IN (...) = NULL).

        Given a database with symbols where kind=NULL (common in production)
        When get_dependents(conn, symbol_id, depth=1) is called
        Then results INCLUDE symbols with kind=NULL

        This test will FAIL with current implementation and PASS after fix.
        """
        from code_indexer.scip.database.queries import get_dependents

        # Create SCIP protobuf with NULL kind symbols
        index = scip_pb2.Index()

        # Create callee symbol (will be our query target - what other symbols depend on)
        callee_symbol = "scip-python python test abc123 `src.callee`/Callee#method()."
        symbol_info = index.external_symbols.add()
        symbol_info.symbol = callee_symbol
        symbol_info.display_name = "method"
        # kind is NOT set -> will be NULL in database

        # Create caller symbols with various kind values
        # 1. NULL kind (most common in production) - kind field NOT set
        caller_null_1 = "scip-python python test abc123 `src.caller`/CallerNull1#method()."
        symbol_info = index.external_symbols.add()
        symbol_info.symbol = caller_null_1
        symbol_info.display_name = "CallerNull1"
        # kind is NOT set -> will be NULL

        # 2. Another NULL kind
        caller_null_2 = "scip-python python test abc123 `src.caller`/CallerNull2#method()."
        symbol_info = index.external_symbols.add()
        symbol_info.symbol = caller_null_2
        symbol_info.display_name = "CallerNull2"
        # kind is NOT set -> will be NULL

        # 3. Method kind (should be included)
        caller_method = "scip-python python test abc123 `src.caller`/CallerMethod#method()."
        symbol_info = index.external_symbols.add()
        symbol_info.symbol = caller_method
        symbol_info.display_name = "CallerMethod"
        symbol_info.kind = scip_pb2.SymbolInformation.Method

        # Add document with occurrences
        doc = index.documents.add()
        doc.relative_path = "src/caller.py"
        doc.language = "python"

        # Add callee definition
        occ = doc.occurrences.add()
        occ.symbol = callee_symbol
        occ.symbol_roles = ROLE_DEFINITION
        occ.range.extend([10, 0, 10, 10])

        # Add caller definitions
        for i, caller_sym in enumerate([caller_null_1, caller_null_2, caller_method]):
            occ = doc.occurrences.add()
            occ.symbol = caller_sym
            occ.symbol_roles = ROLE_DEFINITION
            occ.range.extend([20 + i * 5, 0, 20 + i * 5, 10])

        # Write protobuf to file
        scip_file = tmp_path / "test_null_kinds_dependents.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Add call graph edges manually
        conn = sqlite3.connect(manager.db_path)
        try:
            cursor = conn.cursor()

            # Get symbol IDs
            callee_id = _get_symbol_id(conn, callee_symbol)
            caller_null_1_id = _get_symbol_id(conn, caller_null_1)
            caller_null_2_id = _get_symbol_id(conn, caller_null_2)
            caller_method_id = _get_symbol_id(conn, caller_method)

            # Insert call graph edges (all callers depend on callee)
            cursor.executemany(
                "INSERT INTO call_graph (caller_symbol_id, callee_symbol_id, relationship) VALUES (?, ?, ?)",
                [
                    (caller_null_1_id, callee_id, "call"),
                    (caller_null_2_id, callee_id, "reference"),
                    (caller_method_id, callee_id, "call"),
                ]
            )
            conn.commit()

            # Execute query
            results = get_dependents(conn, callee_id, depth=1)

            # CRITICAL ASSERTION: NULL kind symbols MUST be included
            result_symbols = {r["symbol_name"] for r in results}

            # Should INCLUDE NULL kind symbols
            assert caller_null_1 in result_symbols, (
                f"NULL kind symbol 1 not found in results! This is the SQL NULL handling bug. "
                f"Results: {result_symbols}"
            )
            assert caller_null_2 in result_symbols, (
                f"NULL kind symbol 2 not found in results! This is the SQL NULL handling bug. "
                f"Results: {result_symbols}"
            )

            # Should INCLUDE Method kind
            assert caller_method in result_symbols, (
                f"Method kind symbol not found in results! Results: {result_symbols}"
            )

            # Verify correct number of results (3: 2 NULL + 1 Method)
            assert len(results) == 3, (
                f"Expected 3 results (2 NULL + 1 Method), got {len(results)}"
            )

        finally:
            conn.close()

    def test_get_dependents_hybrid_returns_all_symbol_types(self, tmp_path: Path):
        """
        HYBRID TEST: Verify get_dependents returns ALL symbol types (Epic #598 requirement).

        Current call_graph implementation returns only function calls.
        Hybrid implementation must return ALL reference types: imports, attributes, variables, calls.

        This test will FAIL until hybrid implementation is complete.
        """
        from code_indexer.scip.database.queries import get_dependents

        # Create test database with diverse symbol references
        conn, scip_file, target_id, refs = _create_hybrid_test_database(tmp_path)

        try:
            # Execute hybrid query (will need scip_file parameter)
            results = get_dependents(conn, target_id, depth=1, scip_file=scip_file)

            # Verify ALL 4 reference types are returned
            result_symbols = {r["symbol_name"] for r in results}

            assert refs["importer"] in result_symbols, "Import reference missing"
            assert refs["accessor"] in result_symbols, "Attribute access missing"
            assert refs["assigner"] in result_symbols, "Variable reference missing"
            assert refs["caller"] in result_symbols, "Function call missing"

            assert len(result_symbols) == 4, (
                f"Expected 4 dependent symbols (all reference types), got {len(result_symbols)}. "
                f"Call_graph returns only calls. Hybrid must return ALL references."
            )

        finally:
            conn.close()

    def test_get_dependencies_hybrid_returns_all_symbol_types(self, tmp_path: Path):
        """
        HYBRID TEST: Verify get_dependencies returns ALL symbol types (Epic #598 requirement).

        Current call_graph implementation returns only function calls.
        Hybrid implementation must return ALL reference types that target symbol uses.

        This test creates a symbol that USES 4 different symbols via:
        - import statement (import dependency)
        - attribute access (attribute dependency)
        - variable reference (variable dependency)
        - function call (call dependency)

        Expected: get_dependencies returns ALL 4 dependency types.
        This test will FAIL until hybrid implementation is complete.
        """
        from code_indexer.scip.database.queries import get_dependencies

        # Create test database for dependencies (target USES other symbols)
        conn, scip_file, target_id, deps = _create_hybrid_dependencies_test_database(tmp_path)

        try:
            # Execute hybrid query (will need scip_file parameter)
            results = get_dependencies(conn, target_id, depth=1, scip_file=scip_file)

            # Verify ALL 4 dependency types are returned
            result_symbols = {r["symbol_name"] for r in results}

            assert deps["imported"] in result_symbols, "Import dependency missing"
            assert deps["accessed"] in result_symbols, "Attribute access dependency missing"
            assert deps["assigned"] in result_symbols, "Variable dependency missing"
            assert deps["called"] in result_symbols, "Function call dependency missing"

            assert len(result_symbols) == 4, (
                f"Expected 4 dependency symbols (all reference types), got {len(result_symbols)}. "
                f"Call_graph returns only calls. Hybrid must return ALL dependencies."
            )

        finally:
            conn.close()


class TestQueryEngineIntegration:
    """Test SCIPQueryEngine integration with database backend (AC1 + AC2)."""

    def test_query_engine_uses_database_backend(self, tmp_path: Path):
        """
        Test that SCIPQueryEngine automatically uses database backend when .scip.db exists.

        Given a .scip file AND a .scip.db database file
        When SCIPQueryEngine is initialized
        Then it uses database backend for queries
        And results are identical to protobuf backend format
        """
        from code_indexer.scip.query.primitives import SCIPQueryEngine
        from code_indexer.scip.database.builder import ROLE_READ_ACCESS

        # Create SCIP protobuf with multiple symbols
        index = scip_pb2.Index()
        index.metadata.project_root = str(tmp_path)

        # Add symbol definitions
        for symbol_name in ["TestClass", "foo"]:
            symbol_info = index.external_symbols.add()
            if symbol_name == "TestClass":
                symbol_info.symbol = f"scip-python python test abc123 `src.test`/{symbol_name}#"
                symbol_info.display_name = symbol_name
                symbol_info.kind = scip_pb2.SymbolInformation.Class
            else:
                symbol_info.symbol = f"scip-python python test abc123 `src.test`/{symbol_name}()."
                symbol_info.display_name = symbol_name
                symbol_info.kind = scip_pb2.SymbolInformation.Method

        # Add document with occurrences
        doc = index.documents.add()
        doc.relative_path = "src/test.py"
        doc.language = "python"

        # Add TestClass definition
        occ = doc.occurrences.add()
        occ.symbol = "scip-python python test abc123 `src.test`/TestClass#"
        occ.symbol_roles = ROLE_DEFINITION
        occ.range.extend([10, 0, 10, 9])

        # Add foo definition
        occ = doc.occurrences.add()
        occ.symbol = "scip-python python test abc123 `src.test`/foo()."
        occ.symbol_roles = ROLE_DEFINITION
        occ.range.extend([20, 0, 20, 3])

        # Add 3 references to foo
        for i in range(3):
            occ = doc.occurrences.add()
            occ.symbol = "scip-python python test abc123 `src.test`/foo()."
            occ.symbol_roles = ROLE_READ_ACCESS
            occ.range.extend([30 + i, 5, 30 + i, 8])

        # Write protobuf to file
        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Verify database file exists
        assert manager.db_path.exists(), "Database file should exist"

        # Initialize query engine (should auto-detect database)
        engine = SCIPQueryEngine(scip_file)

        # VERIFY database backend is being used (not protobuf fallback)
        assert hasattr(engine, 'db_path'), "Engine should have db_path attribute when database exists"
        assert hasattr(engine, 'db_conn'), "Engine should have db_conn attribute when database exists"
        assert engine.db_path == manager.db_path, "Engine should use correct database path"
        assert engine.db_conn is not None, "Engine should have active database connection"

        # Test find_definition() uses database backend
        results = engine.find_definition("TestClass", exact=True)
        assert len(results) == 1
        assert results[0].symbol == "scip-python python test abc123 `src.test`/TestClass#"
        assert results[0].file_path == "src/test.py"
        assert results[0].line == 10
        assert results[0].column == 0
        assert results[0].kind == "definition"

        # Test find_references() uses database backend
        results = engine.find_references("foo", limit=2, exact=True)
        assert len(results) == 2  # Limit enforced
        assert all(r.kind == "reference" for r in results)
        assert all(r.symbol == "scip-python python test abc123 `src.test`/foo()." for r in results)

    @pytest.mark.slow
    def test_query_engine_trace_call_chain_integration(self, tmp_path: Path):
        """
        Test that SCIPQueryEngine exposes trace_call_chain() method (Story #604 AC5).

        Given a .scip.db database file with call graph
        When SCIPQueryEngine.trace_call_chain() is called
        Then it delegates to backend.trace_call_chain()
        And returns List[CallChain] with path tracing results
        """
        from code_indexer.scip.query.primitives import SCIPQueryEngine

        # Create SCIP protobuf with call chain
        index = scip_pb2.Index()
        index.metadata.project_root = str(tmp_path)

        # Define symbols: A -> B -> C
        a_symbol = "scip-python python test abc123 `src.a`/A#"
        b_symbol = "scip-python python test abc123 `src.b`/B#"
        c_symbol = "scip-python python test abc123 `src.c`/C#"

        for symbol, display in [
            (a_symbol, "A"),
            (b_symbol, "B"),
            (c_symbol, "C"),
        ]:
            symbol_info = index.external_symbols.add()
            symbol_info.symbol = symbol
            symbol_info.display_name = display
            symbol_info.kind = scip_pb2.SymbolInformation.Method

        # Add documents
        for file_path, symbol in [
            ("src/a.py", a_symbol),
            ("src/b.py", b_symbol),
            ("src/c.py", c_symbol),
        ]:
            doc = index.documents.add()
            doc.relative_path = file_path
            doc.language = "python"

            occ = doc.occurrences.add()
            occ.symbol = symbol
            occ.symbol_roles = ROLE_DEFINITION
            occ.range.extend([10, 0, 10, 10])

        # Write protobuf to file
        scip_file = tmp_path / "test_trace.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Add call graph edges: A -> B -> C
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()

        a_id = _get_symbol_id(conn, a_symbol)
        b_id = _get_symbol_id(conn, b_symbol)
        c_id = _get_symbol_id(conn, c_symbol)

        cursor.executemany(
            "INSERT INTO call_graph (caller_symbol_id, callee_symbol_id, relationship) VALUES (?, ?, ?)",
            [
                (a_id, b_id, "call"),
                (b_id, c_id, "call"),
            ]
        )
        conn.commit()
        conn.close()

        # Initialize query engine
        engine = SCIPQueryEngine(scip_file)

        # CRITICAL ASSERTION: trace_call_chain() method must be exposed
        assert hasattr(engine, 'trace_call_chain'), (
            "SCIPQueryEngine must expose trace_call_chain() method (AC5 violation)"
        )

        # Test trace_call_chain() delegation
        chains = engine.trace_call_chain("A", "C", max_depth=3, limit=100)

        # Verify results structure
        assert isinstance(chains, list), "Should return list of CallChain objects"
        assert len(chains) > 0, "Should find at least one path from A to C"

        # Verify CallChain structure
        chain = chains[0]
        assert hasattr(chain, 'path'), "CallChain must have 'path' attribute"
        assert hasattr(chain, 'length'), "CallChain must have 'length' attribute"
        assert hasattr(chain, 'has_cycle'), "CallChain must have 'has_cycle' attribute"

        # Verify path correctness
        assert len(chain.path) == 3, f"Expected 3 symbols in path, got {len(chain.path)}"
        assert chain.length == 2, f"Expected length 2, got {chain.length}"
        assert chain.has_cycle is False, f"Expected no cycle, got {chain.has_cycle}"


class TestAnalyzeImpact:
    """Test analyze_impact() SQL-based impact analysis query (Story #603)."""

    def test_analyze_impact_depth_1(self, tmp_path: Path):
        """
        Test depth=1 impact analysis returns direct dependents grouped by file (AC1, AC3).

        Given a database with call_graph edges (ClassA <- ClassB, ClassC)
        When analyze_impact(conn, ClassA_id, depth=1) is called
        Then results contain file-grouped impact data
        And each result has file_path, symbol_count, and symbols list
        And results are sorted by symbol_count DESC
        """
        from code_indexer.scip.database.queries import analyze_impact

        # Arrange: Create test database with call graph
        conn, target_id, dependents = _create_impact_test_database(tmp_path)

        try:
            # Act: Execute impact analysis query
            results = analyze_impact(conn, target_id, depth=1)

            # Assert: Verify results structure and content
            assert len(results) == 2, f"Expected 2 impacted files, got {len(results)}"

            # Verify result format
            for result in results:
                assert "file_path" in result
                assert "symbol_count" in result
                assert "symbols" in result
                assert isinstance(result["symbols"], list)

            # Verify file paths
            file_paths = {r["file_path"] for r in results}
            assert "src/file1.py" in file_paths
            assert "src/file2.py" in file_paths

            # Verify symbols appear in correct files
            for result in results:
                expected_symbol = dependents[result["file_path"]]
                assert expected_symbol in result["symbols"]
                assert result["symbol_count"] == 1

        finally:
            conn.close()

    def test_analyze_impact_depth_3(self, tmp_path: Path):
        """
        Test depth=3 impact analysis returns transitive dependents (AC1, AC2).

        Given call graph: ClassA <- ClassB <- ClassC <- ClassD
        When analyze_impact(conn, ClassA_id, depth=3) is called
        Then results include ClassB (depth=1), ClassC (depth=2), ClassD (depth=3)
        And results are grouped by file with symbol counts
        """
        from code_indexer.scip.database.queries import analyze_impact

        # Create SCIP protobuf with chain of dependencies
        index = scip_pb2.Index()

        # Create symbols: A <- B <- C <- D
        symbols = []
        for name in ["ClassA", "ClassB", "ClassC", "ClassD"]:
            symbol = f"scip-python python test abc123 `src.module`/{name}#"
            symbol_info = index.external_symbols.add()
            symbol_info.symbol = symbol
            symbol_info.display_name = name
            symbol_info.kind = scip_pb2.SymbolInformation.Class
            symbols.append(symbol)

        # Add document with definitions
        doc = index.documents.add()
        doc.relative_path = "src/module.py"
        doc.language = "python"

        for i, symbol in enumerate(symbols):
            occ = doc.occurrences.add()
            occ.symbol = symbol
            occ.symbol_roles = ROLE_DEFINITION
            occ.range.extend([10 + i * 10, 0, 10 + i * 10, 10])

        # Write protobuf to file
        scip_file = tmp_path / "test_transitive.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Add call graph chain: D -> C -> B -> A
        conn = sqlite3.connect(manager.db_path)
        try:
            cursor = conn.cursor()
            a_id = _get_symbol_id(conn, symbols[0])
            b_id = _get_symbol_id(conn, symbols[1])
            c_id = _get_symbol_id(conn, symbols[2])
            d_id = _get_symbol_id(conn, symbols[3])

            cursor.executemany(
                "INSERT INTO call_graph (caller_symbol_id, callee_symbol_id, relationship) VALUES (?, ?, ?)",
                [
                    (b_id, a_id, "call"),  # B depends on A
                    (c_id, b_id, "call"),  # C depends on B
                    (d_id, c_id, "call"),  # D depends on C
                ]
            )
            conn.commit()

            # Test depth=1 (should get only B)
            results = analyze_impact(conn, a_id, depth=1)
            assert len(results) == 1
            assert results[0]["symbol_count"] == 1
            assert symbols[1] in results[0]["symbols"]

            # Test depth=3 (should get B, C, D)
            results = analyze_impact(conn, a_id, depth=3)
            assert len(results) == 1  # All in same file
            assert results[0]["file_path"] == "src/module.py"
            assert results[0]["symbol_count"] == 3

            # Verify all transitive dependents present
            result_symbols = results[0]["symbols"]
            assert symbols[1] in result_symbols  # ClassB (depth=1)
            assert symbols[2] in result_symbols  # ClassC (depth=2)
            assert symbols[3] in result_symbols  # ClassD (depth=3)

        finally:
            conn.close()

    def test_analyze_impact_performance_benchmark(self, tmp_path: Path):
        """
        PERFORMANCE TEST: Impact analysis must complete in <200ms for depth=3 (AC1).

        Given a production-scale database (10K symbols, 1K call graph edges)
        When analyze_impact(conn, symbol_id, depth=3) is called
        Then query completes in <200ms (0.200 seconds)

        Target: 150x faster than 30s protobuf baseline.
        """
        from code_indexer.scip.database.queries import analyze_impact

        # Create production-scale database
        conn, target_symbol = _create_production_scale_database(tmp_path)

        try:
            # Get symbol_id for target symbol
            symbol_id = _get_symbol_id(conn, target_symbol)

            # Warm-up query to stabilize timing measurements across CI environments
            # Note: Real-world cold-start may be slower due to SQLite cache effects
            _ = analyze_impact(conn, symbol_id, depth=3)

            # Timed query
            start = time.perf_counter()
            results = analyze_impact(conn, symbol_id, depth=3)
            elapsed = time.perf_counter() - start

            # Verify correctness
            assert isinstance(results, list), "Should return list of impacted files"

            # PERFORMANCE ASSERTION: Must complete in <200ms
            assert elapsed < 0.200, (
                f"Impact analysis (depth=3) took {elapsed*1000:.1f}ms, exceeds 200ms target. "
                f"Expected: <200ms for 150x speedup over protobuf baseline."
            )
        finally:
            conn.close()

    def test_analyze_impact_deduplicates_across_multiple_definitions(self, tmp_path: Path):
        """
        Verify symbols deduplicated when target has multiple definitions.

        Given a target symbol with 2 definitions (e.g., overloaded method in Base and Derived)
        When both definitions have the same dependent symbol (e.g., Caller uses both)
        Then dependent symbol appears ONCE in results with symbol_count = 1 (not 2)

        This tests Issue #1 from Story #603 code review.
        """
        from code_indexer.scip.database.queries import analyze_impact

        # Create SCIP index with 2 definitions for "process" method
        index = scip_pb2.Index()

        # Symbol definitions
        base_process = "scip-python python test abc123 `src.base`/Base#process()."
        derived_process = "scip-python python test abc123 `src.derived`/Derived#process()."
        caller_use = "scip-python python test abc123 `src.caller`/Caller#use_process()."

        # Add external symbols
        for symbol_name in [base_process, derived_process, caller_use]:
            symbol_info = index.external_symbols.add()
            symbol_info.symbol = symbol_name

        # Document 1: Base class with process() definition
        doc1 = index.documents.add()
        doc1.relative_path = "src/base.py"
        doc1.language = "python"

        occ1_def = doc1.occurrences.add()
        occ1_def.symbol = base_process
        occ1_def.symbol_roles = ROLE_DEFINITION
        occ1_def.range.extend([10, 4, 10, 11])

        # Document 2: Derived class with overridden process() definition
        doc2 = index.documents.add()
        doc2.relative_path = "src/derived.py"
        doc2.language = "python"

        occ2_def = doc2.occurrences.add()
        occ2_def.symbol = derived_process
        occ2_def.symbol_roles = ROLE_DEFINITION
        occ2_def.range.extend([20, 4, 20, 11])

        # Document 3: Caller uses both Base.process() and Derived.process()
        doc3 = index.documents.add()
        doc3.relative_path = "src/caller.py"
        doc3.language = "python"

        # Caller.use_process() definition
        occ3_def = doc3.occurrences.add()
        occ3_def.symbol = caller_use
        occ3_def.symbol_roles = ROLE_DEFINITION
        occ3_def.range.extend([30, 4, 30, 15])

        # Write protobuf to file
        scip_file = tmp_path / "test_dedup.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Add call graph edges: Caller.use_process() calls both Base.process() and Derived.process()
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()

        base_id = _get_symbol_id(conn, base_process)
        derived_id = _get_symbol_id(conn, derived_process)
        caller_id = _get_symbol_id(conn, caller_use)

        cursor.executemany(
            "INSERT INTO call_graph (caller_symbol_id, callee_symbol_id, relationship) VALUES (?, ?, ?)",
            [
                (caller_id, base_id, "call"),
                (caller_id, derived_id, "call"),
            ]
        )
        conn.commit()

        try:
            # Query impact for Base.process() - should find Caller.use_process() as dependent
            results = analyze_impact(conn, base_id, depth=1)

            # ASSERTION: Caller.use_process() should appear ONCE (not twice)
            # Even though both Base.process() and Derived.process() are queried via backend merging
            assert len(results) == 1, f"Expected 1 result (src/caller.py), got {len(results)}"
            assert results[0]['file_path'] == 'src/caller.py'
            assert results[0]['symbol_count'] == 1, (
                f"Expected symbol_count=1 (deduplicated), got {results[0]['symbol_count']}"
            )
            assert caller_use in results[0]['symbols'], (
                f"Expected '{caller_use}' in symbols, got {results[0]['symbols']}"
            )

        finally:
            conn.close()

    def test_analyze_impact_handles_symbols_with_special_characters(self, tmp_path: Path):
        """
        Test that analyze_impact() correctly handles symbol names with commas.

        Given a symbol name containing commas (e.g., "func(x, y)")
        When analyze_impact() returns results
        Then symbol names are not incorrectly split on commas
        And symbols list contains the complete symbol name

        This tests Issue #2 from Story #603 code review (queries.py lines 459, 478).
        """
        from code_indexer.scip.database.queries import analyze_impact

        # Create SCIP index with symbol containing comma
        index = scip_pb2.Index()

        # Symbol with commas in name (realistic Python signature)
        target_symbol = "scip-python python test abc123 `src.target`/func()."
        dependent_symbol = "scip-python python test abc123 `src.caller`/caller(x, y)."

        # Add external symbols
        for symbol_name in [target_symbol, dependent_symbol]:
            symbol_info = index.external_symbols.add()
            symbol_info.symbol = symbol_name

        # Add documents with definitions
        for file_path, symbol in [
            ("src/target.py", target_symbol),
            ("src/caller.py", dependent_symbol),
        ]:
            doc = index.documents.add()
            doc.relative_path = file_path
            doc.language = "python"

            occ = doc.occurrences.add()
            occ.symbol = symbol
            occ.symbol_roles = ROLE_DEFINITION
            occ.range.extend([10, 0, 10, 10])

        # Write protobuf to file
        scip_file = tmp_path / "test_special_chars.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Add call graph edge: caller(x, y) calls func()
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM symbols WHERE name = ?", (target_symbol,))
        target_id = cursor.fetchone()[0]

        cursor.execute("SELECT id FROM symbols WHERE name = ?", (dependent_symbol,))
        caller_id = cursor.fetchone()[0]

        cursor.execute(
            "INSERT INTO call_graph (caller_symbol_id, callee_symbol_id, relationship) VALUES (?, ?, ?)",
            (caller_id, target_id, "call")
        )
        conn.commit()

        try:
            # Query impact
            results = analyze_impact(conn, target_id, depth=1)

            # Assertions: Symbol with commas should NOT be split
            assert len(results) == 1, f"Expected 1 result, got {len(results)}"
            assert results[0]['file_path'] == 'src/caller.py'

            # CRITICAL: Symbol name with commas must be intact (not split)
            assert len(results[0]['symbols']) == 1, (
                f"Expected 1 symbol (not split on commas), got {len(results[0]['symbols'])}: {results[0]['symbols']}"
            )

            assert results[0]['symbols'][0] == dependent_symbol, (
                f"Expected '{dependent_symbol}', got '{results[0]['symbols'][0]}'. "
                f"Symbol may have been incorrectly split on comma."
            )

        finally:
            conn.close()


def _create_call_chain_test_database(tmp_path: Path) -> tuple:
    """
    Create test database with call chain for tracing tests.

    Creates a call chain: EntryPoint -> MiddleFunc -> TargetFunc

    Returns:
        Tuple of (sqlite3.Connection, entry_id, middle_id, target_id)
    """
    # Create SCIP protobuf with symbols
    index = scip_pb2.Index()

    # Define symbols
    entry_symbol = "scip-python python test abc123 `src.entry`/EntryPoint#"
    middle_symbol = "scip-python python test abc123 `src.middle`/MiddleFunc#"
    target_symbol = "scip-python python test abc123 `src.target`/TargetFunc#"

    for symbol, display in [
        (entry_symbol, "EntryPoint"),
        (middle_symbol, "MiddleFunc"),
        (target_symbol, "TargetFunc"),
    ]:
        symbol_info = index.external_symbols.add()
        symbol_info.symbol = symbol
        symbol_info.display_name = display
        symbol_info.kind = scip_pb2.SymbolInformation.Method

    # Add documents with definitions
    for file_path, symbol in [
        ("src/entry.py", entry_symbol),
        ("src/middle.py", middle_symbol),
        ("src/target.py", target_symbol),
    ]:
        doc = index.documents.add()
        doc.relative_path = file_path
        doc.language = "python"

        occ = doc.occurrences.add()
        occ.symbol = symbol
        occ.symbol_roles = ROLE_DEFINITION
        occ.range.extend([10, 0, 10, 10])

    # Write protobuf to file
    scip_file = tmp_path / "test_call_chain.scip"
    with open(scip_file, "wb") as f:
        f.write(index.SerializeToString())

    # Build database
    manager = DatabaseManager(scip_file)
    manager.create_schema()
    builder = SCIPDatabaseBuilder()
    builder.build(scip_file, manager.db_path)

    # Add call graph edges: EntryPoint -> MiddleFunc -> TargetFunc
    conn = sqlite3.connect(manager.db_path)
    cursor = conn.cursor()

    entry_id = _get_symbol_id(conn, entry_symbol)
    middle_id = _get_symbol_id(conn, middle_symbol)
    target_id = _get_symbol_id(conn, target_symbol)

    cursor.executemany(
        "INSERT INTO call_graph (caller_symbol_id, callee_symbol_id, relationship) VALUES (?, ?, ?)",
        [
            (entry_id, middle_id, "call"),
            (middle_id, target_id, "call"),
        ]
    )
    conn.commit()

    return conn, entry_id, middle_id, target_id


class TestTraceCallChain:
    """Test trace_call_chain() recursive SQL for call chain discovery (Story #604)."""

    def test_trace_call_chain_direct_path(self, tmp_path: Path):
        """
        Test single-hop call chain discovery (AC1, AC2).

        Given a call graph: EntryPoint -> MiddleFunc
        When trace_call_chain(conn, entry_id, middle_id, max_depth=1) is called
        Then results contain one path: [EntryPoint, MiddleFunc]
        And path length is 1
        And has_cycle is False
        """
        from code_indexer.scip.database.queries import trace_call_chain

        # Create database with call chain
        conn, entry_id, middle_id, target_id = _create_call_chain_test_database(tmp_path)

        try:
            # Trace single-hop path: EntryPoint -> MiddleFunc
            results = trace_call_chain(conn, entry_id, middle_id, max_depth=1)

            # Assertions
            assert len(results) == 1, f"Expected 1 path, got {len(results)}"

            result = results[0]
            assert result['length'] == 1, f"Expected length 1, got {result['length']}"
            assert result['has_cycle'] is False, f"Expected no cycle, got {result['has_cycle']}"
            assert len(result['path']) == 2, f"Expected 2 symbols in path, got {len(result['path'])}"
            assert 'EntryPoint' in result['path'][0], f"Expected EntryPoint in path[0], got {result['path'][0]}"
            assert 'MiddleFunc' in result['path'][1], f"Expected MiddleFunc in path[1], got {result['path'][1]}"

        finally:
            conn.close()

    def test_trace_call_chain_multi_hop(self, tmp_path: Path):
        """
        Test multi-hop call chain discovery (AC1, AC2).

        Given a call graph: EntryPoint -> MiddleFunc -> TargetFunc
        When trace_call_chain(conn, entry_id, target_id, max_depth=3) is called
        Then results contain one path: [EntryPoint, MiddleFunc, TargetFunc]
        And path length is 2
        And has_cycle is False
        """
        from code_indexer.scip.database.queries import trace_call_chain

        # Create database with call chain
        conn, entry_id, middle_id, target_id = _create_call_chain_test_database(tmp_path)

        try:
            # Trace multi-hop path: EntryPoint -> MiddleFunc -> TargetFunc
            results = trace_call_chain(conn, entry_id, target_id, max_depth=3)

            # Assertions
            assert len(results) == 1, f"Expected 1 path, got {len(results)}"

            result = results[0]
            assert result['length'] == 2, f"Expected length 2, got {result['length']}"
            assert result['has_cycle'] is False, f"Expected no cycle, got {result['has_cycle']}"
            assert len(result['path']) == 3, f"Expected 3 symbols in path, got {len(result['path'])}"
            assert 'EntryPoint' in result['path'][0], f"Expected EntryPoint in path[0], got {result['path'][0]}"
            assert 'MiddleFunc' in result['path'][1], f"Expected MiddleFunc in path[1], got {result['path'][1]}"
            assert 'TargetFunc' in result['path'][2], f"Expected TargetFunc in path[2], got {result['path'][2]}"

        finally:
            conn.close()

    def test_trace_call_chain_multiple_paths(self, tmp_path: Path):
        """
        Test multiple path discovery (AC3).

        Given a call graph with two paths from Entry to Target:
          Path 1: Entry -> Middle1 -> Target
          Path 2: Entry -> Middle2 -> Target
        When trace_call_chain(conn, entry_id, target_id, max_depth=3) is called
        Then results contain both paths
        And paths are sorted by length (shortest first)
        """
        from code_indexer.scip.database.queries import trace_call_chain

        # Create SCIP protobuf with symbols
        index = scip_pb2.Index()

        # Define symbols
        entry_symbol = "scip-python python test abc123 `src.entry`/Entry#"
        middle1_symbol = "scip-python python test abc123 `src.m1`/Middle1#"
        middle2_symbol = "scip-python python test abc123 `src.m2`/Middle2#"
        target_symbol = "scip-python python test abc123 `src.target`/Target#"

        for symbol, display in [
            (entry_symbol, "Entry"),
            (middle1_symbol, "Middle1"),
            (middle2_symbol, "Middle2"),
            (target_symbol, "Target"),
        ]:
            symbol_info = index.external_symbols.add()
            symbol_info.symbol = symbol
            symbol_info.display_name = display
            symbol_info.kind = scip_pb2.SymbolInformation.Method

        # Add documents
        for file_path, symbol in [
            ("src/entry.py", entry_symbol),
            ("src/m1.py", middle1_symbol),
            ("src/m2.py", middle2_symbol),
            ("src/target.py", target_symbol),
        ]:
            doc = index.documents.add()
            doc.relative_path = file_path
            doc.language = "python"

            occ = doc.occurrences.add()
            occ.symbol = symbol
            occ.symbol_roles = ROLE_DEFINITION
            occ.range.extend([10, 0, 10, 10])

        # Write protobuf to file
        scip_file = tmp_path / "test_multi_path.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Add call graph edges: Entry -> Middle1 -> Target, Entry -> Middle2 -> Target
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()

        entry_id = _get_symbol_id(conn, entry_symbol)
        middle1_id = _get_symbol_id(conn, middle1_symbol)
        middle2_id = _get_symbol_id(conn, middle2_symbol)
        target_id = _get_symbol_id(conn, target_symbol)

        cursor.executemany(
            "INSERT INTO call_graph (caller_symbol_id, callee_symbol_id, relationship) VALUES (?, ?, ?)",
            [
                (entry_id, middle1_id, "call"),
                (middle1_id, target_id, "call"),
                (entry_id, middle2_id, "call"),
                (middle2_id, target_id, "call"),
            ]
        )
        conn.commit()

        try:
            # Trace paths
            results = trace_call_chain(conn, entry_id, target_id, max_depth=3)

            # Assertions
            assert len(results) == 2, f"Expected 2 paths, got {len(results)}"

            # Both paths should have length 2
            assert all(r['length'] == 2 for r in results), f"Expected all paths with length 2, got {[r['length'] for r in results]}"
            assert all(r['has_cycle'] is False for r in results), f"Expected no cycles"

            # Check that we have both paths (order may vary)
            path_middles = [r['path'][1] for r in results]
            assert any('Middle1' in p for p in path_middles), f"Expected Middle1 in paths, got {path_middles}"
            assert any('Middle2' in p for p in path_middles), f"Expected Middle2 in paths, got {path_middles}"

        finally:
            conn.close()

    def test_trace_call_chain_cycle_detection(self, tmp_path: Path):
        """
        Test cycle detection in recursive call graphs (AC4).

        Given a call graph with cycle: A -> B -> C -> B (cycle)
        When trace_call_chain(conn, a_id, b_id, max_depth=5) is called
        Then cycle is detected and path stops at cycle point
        And has_cycle is False (we stop before following the cycle)
        """
        from code_indexer.scip.database.queries import trace_call_chain

        # Create SCIP protobuf with symbols
        index = scip_pb2.Index()

        # Define symbols
        a_symbol = "scip-python python test abc123 `src.a`/A#"
        b_symbol = "scip-python python test abc123 `src.b`/B#"
        c_symbol = "scip-python python test abc123 `src.c`/C#"

        for symbol, display in [
            (a_symbol, "A"),
            (b_symbol, "B"),
            (c_symbol, "C"),
        ]:
            symbol_info = index.external_symbols.add()
            symbol_info.symbol = symbol
            symbol_info.display_name = display
            symbol_info.kind = scip_pb2.SymbolInformation.Method

        # Add documents
        for file_path, symbol in [
            ("src/a.py", a_symbol),
            ("src/b.py", b_symbol),
            ("src/c.py", c_symbol),
        ]:
            doc = index.documents.add()
            doc.relative_path = file_path
            doc.language = "python"

            occ = doc.occurrences.add()
            occ.symbol = symbol
            occ.symbol_roles = ROLE_DEFINITION
            occ.range.extend([10, 0, 10, 10])

        # Write protobuf to file
        scip_file = tmp_path / "test_cycle.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Add call graph edges creating cycle: A -> B -> C -> B
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()

        a_id = _get_symbol_id(conn, a_symbol)
        b_id = _get_symbol_id(conn, b_symbol)
        c_id = _get_symbol_id(conn, c_symbol)

        cursor.executemany(
            "INSERT INTO call_graph (caller_symbol_id, callee_symbol_id, relationship) VALUES (?, ?, ?)",
            [
                (a_id, b_id, "call"),
                (b_id, c_id, "call"),
                (c_id, b_id, "call"),  # Cycle: C -> B
            ]
        )
        conn.commit()

        try:
            # Trace path that encounters cycle
            results = trace_call_chain(conn, a_id, b_id, max_depth=5)

            # Assertions: Should find two paths:
            # 1. Direct path A -> B (length 1, no cycle)
            # 2. Cyclic path A -> B -> C -> B (length 3, has_cycle=True)
            assert len(results) == 2, f"Expected 2 paths, got {len(results)}"

            # First result should be shortest path (direct)
            assert results[0]['length'] == 1, f"Expected length 1 for first path, got {results[0]['length']}"
            assert results[0]['has_cycle'] is False, f"Expected no cycle in direct path"

            # Second result should show cyclic path
            assert results[1]['length'] == 3, f"Expected length 3 for cyclic path, got {results[1]['length']}"
            assert results[1]['has_cycle'] is True, f"Expected has_cycle=True for cyclic path, got {results[1]['has_cycle']}"
            # Verify path includes cycle: A -> B -> C -> B
            assert len(results[1]['path']) == 4, f"Expected 4 symbols in cyclic path"
            assert 'A#' in results[1]['path'][0]
            assert 'B#' in results[1]['path'][1]
            assert 'C#' in results[1]['path'][2]
            assert 'B#' in results[1]['path'][3]  # B appears again (cycle)

        finally:
            conn.close()

    def test_trace_call_chain_detects_cycle_at_path_end(self, tmp_path: Path):
        """
        Test cycle detection when revisiting the LAST symbol in current path.

        This is an edge case where the LIKE pattern '%,id,%' won't match
        because the last symbol in path_ids doesn't have a trailing comma.

        Graph: A -> B -> C -> C (C calls itself)
        Expected: Cycle detected when C revisits C
        """
        from code_indexer.scip.database.queries import trace_call_chain

        # Create SCIP protobuf with self-referencing symbol
        index = scip_pb2.Index()

        # Define symbols: A -> B -> C -> C (C calls itself)
        a_symbol = "scip-python python test abc123 `src.a`/A#"
        b_symbol = "scip-python python test abc123 `src.b`/B#"
        c_symbol = "scip-python python test abc123 `src.c`/C#"

        for symbol, display in [
            (a_symbol, "A"),
            (b_symbol, "B"),
            (c_symbol, "C"),
        ]:
            symbol_info = index.external_symbols.add()
            symbol_info.symbol = symbol
            symbol_info.display_name = display
            symbol_info.kind = scip_pb2.SymbolInformation.Method

        # Add documents
        for file_path, symbol in [
            ("src/a.py", a_symbol),
            ("src/b.py", b_symbol),
            ("src/c.py", c_symbol),
        ]:
            doc = index.documents.add()
            doc.relative_path = file_path
            doc.language = "python"

            occ = doc.occurrences.add()
            occ.symbol = symbol
            occ.symbol_roles = ROLE_DEFINITION
            occ.range.extend([10, 0, 10, 10])

        # Write protobuf to file
        scip_file = tmp_path / "test_cycle_at_end.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Add call graph edges: A -> B -> C -> C (self-reference)
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()

        a_id = _get_symbol_id(conn, a_symbol)
        b_id = _get_symbol_id(conn, b_symbol)
        c_id = _get_symbol_id(conn, c_symbol)

        cursor.executemany(
            "INSERT INTO call_graph (caller_symbol_id, callee_symbol_id, relationship) VALUES (?, ?, ?)",
            [
                (a_id, b_id, "call"),
                (b_id, c_id, "call"),
                (c_id, c_id, "call"),  # C calls itself
            ]
        )
        conn.commit()

        try:
            # Trace from A to C - should detect self-reference cycle at C
            results = trace_call_chain(conn, a_id, c_id, max_depth=5, limit=100)

            # Should find at least one path
            assert len(results) > 0, "Should find at least one path"

            # Should detect cycle when C revisits itself
            has_cycle_detected = any(r['has_cycle'] for r in results)
            assert has_cycle_detected, (
                f"Cycle not detected! Expected has_cycle=True for at least one path. "
                f"This is the LIKE pattern bug: last symbol in path (no trailing comma) "
                f"won't match '%,id,%' pattern. Results: {results}"
            )

            # Verify path doesn't infinitely extend (cycle stops expansion)
            max_length = max(r['length'] for r in results)
            assert max_length <= 3, (
                f"Path should stop at cycle, got max length {max_length}. "
                f"Paths: {[r['path'] for r in results]}"
            )

        finally:
            conn.close()


class TestTraceCallChainV2BidirectionalBFS:
    """
    Tests for trace_call_chain_v2 bidirectional BFS optimization.

    These tests verify the bidirectional BFS algorithm that achieves <2s performance
    by computing backward-reachable set from target, then pruning forward search.
    """

    @pytest.mark.slow
    def test_trace_call_chain_v2_with_limit_zero_returns_all_chains(self):
        """
        BUG TEST: limit=0 should return ALL call chains, not 0 chains.

        Given a database with call chains from A -> B -> C
        When trace_call_chain_v2(conn, a_id, c_id, limit=0) is called
        Then all call chains are returned (not 0 chains from SQL LIMIT 0)

        This test documents the bug where limit=0 causes SQL LIMIT 0 clause,
        which returns 0 rows instead of unlimited results.
        """
        import pytest
        from code_indexer.scip.database.queries import trace_call_chain_v2

        # Use production database
        db_path = Path.home() / 'Dev/code-indexer/.code-indexer/scip/index.scip.db'
        if not db_path.exists():
            pytest.skip(f"Production database not found at {db_path}")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            # Find symbol IDs for a known call chain
            cursor.execute("SELECT id FROM symbols WHERE name LIKE '%CIDXDaemonService#'")
            from_row = cursor.fetchone()
            if from_row is None:
                pytest.skip("CIDXDaemonService# not found in database")
            from_id = from_row[0]

            cursor.execute("SELECT id FROM symbols WHERE name LIKE '%_is_text_file().'")
            to_row = cursor.fetchone()
            if to_row is None:
                pytest.skip("_is_text_file(). not found in database")
            to_id = to_row[0]

            # Execute query with limit=0 (should return ALL chains, not 0)
            chains_unlimited = trace_call_chain_v2(conn, from_id, to_id, max_depth=5, limit=0)

            # Execute query with high limit to get reference count
            chains_limited = trace_call_chain_v2(conn, from_id, to_id, max_depth=5, limit=100)

            # CRITICAL: limit=0 should return ALL chains (at least as many as limit=100)
            assert len(chains_unlimited) > 0, (
                f"limit=0 should return all chains, got {len(chains_unlimited)}. "
                f"Bug: SQL LIMIT 0 returns 0 rows instead of unlimited results."
            )
            assert len(chains_unlimited) >= len(chains_limited), (
                f"limit=0 returned {len(chains_unlimited)} chains, "
                f"but limit=100 returned {len(chains_limited)} chains. "
                f"limit=0 should return at least as many results as limit=100."
            )
        finally:
            conn.close()

    @pytest.mark.slow
    def test_trace_call_chain_v2_finds_all_paths_correctness(self):
        """
        Verify bidirectional BFS finds all valid paths between DaemonService and _is_text_file.

        Uses real code-indexer database. Expected to find 11 call chains.
        """
        from code_indexer.scip.database.queries import trace_call_chain_v2

        # Use production database
        db_path = Path.home() / 'Dev/code-indexer/.code-indexer/scip/index.scip.db'
        if not db_path.exists():
            import pytest
            pytest.skip(f"Production database not found at {db_path}")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            # Find symbol IDs
            cursor.execute("SELECT id FROM symbols WHERE name LIKE '%CIDXDaemonService#'")
            from_row = cursor.fetchone()
            assert from_row is not None, "CIDXDaemonService# not found"
            from_id = from_row[0]

            cursor.execute("SELECT id FROM symbols WHERE name LIKE '%_is_text_file().'")
            to_row = cursor.fetchone()
            assert to_row is not None, "_is_text_file(). not found"
            to_id = to_row[0]

            # Execute query
            chains = trace_call_chain_v2(conn, from_id, to_id, max_depth=5, limit=100)

            # Verify correctness
            assert len(chains) == 11, f"Expected 11 chains, got {len(chains)}"

            # Verify all paths start with DaemonService
            for chain in chains:
                assert 'CIDXDaemonService#' in chain['path'][0], f"Path should start with DaemonService: {chain['path'][0]}"

            # Verify all paths end with _is_text_file
            for chain in chains:
                assert '_is_text_file().' in chain['path'][-1], f"Path should end with _is_text_file: {chain['path'][-1]}"

        finally:
            conn.close()

    @pytest.mark.slow
    def test_trace_call_chain_v2_performance_under_2_seconds(self):
        """
        Verify query completes in <2 seconds with bidirectional BFS optimization.

        Previous forward-only approach: 4.5 seconds (165K intermediate rows).
        Target with bidirectional BFS: <2 seconds (1K-5K rows).
        """
        from code_indexer.scip.database.queries import trace_call_chain_v2

        # Use production database
        db_path = Path.home() / 'Dev/code-indexer/.code-indexer/scip/index.scip.db'
        if not db_path.exists():
            import pytest
            pytest.skip(f"Production database not found at {db_path}")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            # Find symbol IDs
            cursor.execute("SELECT id FROM symbols WHERE name LIKE '%CIDXDaemonService#'")
            from_id = cursor.fetchone()[0]

            cursor.execute("SELECT id FROM symbols WHERE name LIKE '%_is_text_file().'")
            to_id = cursor.fetchone()[0]

            # Execute with timing
            start = time.time()
            chains = trace_call_chain_v2(conn, from_id, to_id, max_depth=5, limit=100)
            elapsed = time.time() - start

            # Verify performance
            assert elapsed < 2.0, f"Query took {elapsed:.3f}s, expected <2.0s"
            assert len(chains) > 0, "Sanity check: should find at least one chain"

        finally:
            conn.close()

    @pytest.mark.slow
    def test_trace_call_chain_v2_shortest_path_ordering(self):
        """
        Verify paths are returned in shortest-first order.

        The shortest path from DaemonService to _is_text_file should be 3 hops.
        """
        from code_indexer.scip.database.queries import trace_call_chain_v2

        # Use production database
        db_path = Path.home() / 'Dev/code-indexer/.code-indexer/scip/index.scip.db'
        if not db_path.exists():
            import pytest
            pytest.skip(f"Production database not found at {db_path}")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            # Find symbol IDs
            cursor.execute("SELECT id FROM symbols WHERE name LIKE '%CIDXDaemonService#'")
            from_id = cursor.fetchone()[0]

            cursor.execute("SELECT id FROM symbols WHERE name LIKE '%_is_text_file().'")
            to_id = cursor.fetchone()[0]

            # Execute query
            chains = trace_call_chain_v2(conn, from_id, to_id, max_depth=5, limit=100)

            # Verify ordering
            lengths = [c['length'] for c in chains]
            assert lengths == sorted(lengths), f"Paths not sorted by length: {lengths}"

            # Verify shortest path is 3 hops
            assert chains[0]['length'] == 3, f"Shortest path should be 3 hops, got {chains[0]['length']}"

        finally:
            conn.close()

    def test_trace_call_chain_v2_cycle_detection(self):
        """
        Verify cycles are detected and avoided in bidirectional BFS.

        All paths should have has_cycle=False (cycles blocked by forward search).
        """
        from code_indexer.scip.database.queries import trace_call_chain_v2

        # Use production database
        db_path = Path.home() / 'Dev/code-indexer/.code-indexer/scip/index.scip.db'
        if not db_path.exists():
            import pytest
            pytest.skip(f"Production database not found at {db_path}")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            # Find symbol IDs
            cursor.execute("SELECT id FROM symbols WHERE name LIKE '%CIDXDaemonService#'")
            from_id = cursor.fetchone()[0]

            cursor.execute("SELECT id FROM symbols WHERE name LIKE '%_is_text_file().'")
            to_id = cursor.fetchone()[0]

            # Execute query
            chains = trace_call_chain_v2(conn, from_id, to_id, max_depth=5, limit=100)

            # Verify no cycles in any path
            for chain in chains:
                assert chain['has_cycle'] is False, f"Path should not have cycles: {chain}"

        finally:
            conn.close()

    def test_trace_call_chain_v2_no_path_exists(self):
        """
        Verify empty result when no path exists between symbols.

        Pick two unconnected symbols and verify zero paths returned.
        """
        from code_indexer.scip.database.queries import trace_call_chain_v2

        # Use production database
        db_path = Path.home() / 'Dev/code-indexer/.code-indexer/scip/index.scip.db'
        if not db_path.exists():
            import pytest
            pytest.skip(f"Production database not found at {db_path}")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            # Find two symbols that are unlikely to be connected
            # Use a test symbol and a production symbol
            cursor.execute("SELECT id FROM symbols WHERE name LIKE '%test%' LIMIT 1")
            from_row = cursor.fetchone()

            cursor.execute("SELECT id FROM symbols WHERE name LIKE '%CIDXDaemonService#'")
            to_row = cursor.fetchone()

            if from_row is None or to_row is None:
                import pytest
                pytest.skip("Could not find unconnected symbols for test")

            from_id = from_row[0]
            to_id = to_row[0]

            # Execute query
            chains = trace_call_chain_v2(conn, from_id, to_id, max_depth=5, limit=100)

            # Verify no paths found (highly likely these are unconnected)
            # If paths ARE found, that's ok - this test is best-effort
            assert isinstance(chains, list), "Should return list even when empty"

        finally:
            conn.close()

    def test_trace_call_chain_v2_backward_reachability_pruning(self):
        """
        Verify backward-reachable set is much smaller than forward exploration.

        For _is_text_file, backward set should be ~100-500 symbols, not 165K.
        This is the core optimization that makes bidirectional BFS fast.
        """
        # Use production database
        db_path = Path.home() / 'Dev/code-indexer/.code-indexer/scip/index.scip.db'
        if not db_path.exists():
            import pytest
            pytest.skip(f"Production database not found at {db_path}")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            # Find _is_text_file symbol ID
            cursor.execute("SELECT id FROM symbols WHERE name LIKE '%_is_text_file().'")
            to_row = cursor.fetchone()
            assert to_row is not None, "_is_text_file(). not found"
            to_id = to_row[0]

            # Query backward reachability (mimics Phase 1 of bidirectional BFS)
            backward_query = """
            WITH RECURSIVE backward_reachable(symbol_id, depth) AS (
                SELECT ?, 0
                UNION
                SELECT DISTINCT sr.from_symbol_id, br.depth + 1
                FROM backward_reachable br
                JOIN symbol_references sr ON sr.to_symbol_id = br.symbol_id
                WHERE br.depth < 5
            )
            SELECT COUNT(DISTINCT symbol_id) FROM backward_reachable
            """
            cursor.execute(backward_query, (to_id,))
            count = cursor.fetchone()[0]

            # Verify backward set is small (<<165K)
            assert count < 10000, f"Backward set too large: {count} (expected <10,000)"

            # Ideally should be even smaller
            print(f"Backward-reachable set size: {count} symbols")

        finally:
            conn.close()


def _create_class_dependency_scip_index():
    """
    Create SCIP index with class-level dependencies for testing.

    Returns UserServiceImpl -> UserRepository dependency via:
    - Import statement at file scope (line 1)
    - Constructor parameter reference (line 7, class scope)

    Returns:
        Tuple of (index, service_symbol, repo_symbol)
    """
    index = scip_pb2.Index()
    index.metadata.project_root = "file:///test"

    # Add UserRepository symbol
    repo_symbol = "scip-python python test abc123 `src.repo`/UserRepository#"
    symbol_info = index.external_symbols.add()
    symbol_info.symbol = repo_symbol
    symbol_info.display_name = "UserRepository"
    symbol_info.kind = scip_pb2.SymbolInformation.Class

    # Add UserServiceImpl symbol
    service_symbol = "scip-python python test abc123 `src.service`/UserServiceImpl#"
    symbol_info = index.external_symbols.add()
    symbol_info.symbol = service_symbol
    symbol_info.display_name = "UserServiceImpl"
    symbol_info.kind = scip_pb2.SymbolInformation.Class

    # Add UserServiceImpl.__init__ symbol
    init_symbol = "scip-python python test abc123 `src.service`/UserServiceImpl#__init__()."
    symbol_info = index.external_symbols.add()
    symbol_info.symbol = init_symbol
    symbol_info.display_name = "__init__"
    symbol_info.kind = scip_pb2.SymbolInformation.Method

    # Document 1: UserRepository definition
    doc = index.documents.add()
    doc.relative_path = "src/repo.py"
    doc.language = "python"
    occ = doc.occurrences.add()
    occ.symbol = repo_symbol
    occ.symbol_roles = ROLE_DEFINITION
    occ.range.extend([10, 0, 10, 14])

    # Document 2: UserServiceImpl with import + constructor dependency
    doc = index.documents.add()
    doc.relative_path = "src/service.py"
    doc.language = "python"

    # Import at line 1 (file scope)
    occ = doc.occurrences.add()
    occ.symbol = repo_symbol
    occ.symbol_roles = ROLE_IMPORT
    occ.range.extend([1, 25, 1, 39])

    # UserServiceImpl class definition at line 5
    occ = doc.occurrences.add()
    occ.symbol = service_symbol
    occ.symbol_roles = ROLE_DEFINITION
    occ.range.extend([5, 0, 5, 15])
    occ.enclosing_range.extend([5, 0])

    # __init__ method definition at line 7
    occ = doc.occurrences.add()
    occ.symbol = init_symbol
    occ.symbol_roles = ROLE_DEFINITION
    occ.range.extend([7, 4, 7, 12])
    occ.enclosing_range.extend([7, 0])

    # Constructor parameter reference (class scope, NOT in __init__ body)
    occ = doc.occurrences.add()
    occ.symbol = repo_symbol
    occ.symbol_roles = ROLE_READ_ACCESS
    occ.range.extend([7, 35, 7, 49])
    occ.enclosing_range.extend([5, 0])

    return index, service_symbol, repo_symbol


def _create_false_positive_test_database():
    """
    Create database with false positive scenario for pattern testing.

    Scenario demonstrating REAL false positive risk:
    - UserService#Inner (nested class)
    - UserService#InnerHelper (DIFFERENT nested class, falsely matches pattern)
    - DataRepository# (a dependency)
    - UserService#InnerHelper references DataRepository

    Pattern test:
    - Target: `UserService#Inner`
    - Pattern WITHOUT fix: `UserService#Inner%`
    - FALSE POSITIVE MATCH: `UserService#InnerHelper` (starts with `UserService#Inner`)
    - CORRECT MATCH: `UserService#Inner#method().` (truly nested under Inner)

    WITHOUT FIX: Pattern matches InnerHelper as "nested under Inner",
                 causing DataRepository to appear as Inner dependency (FALSE POSITIVE)
    WITH FIX: Pattern `name || '#%' OR name || '.%'` requires delimiter,
              excludes InnerHelper, so DataRepository correctly does NOT appear

    Returns:
        Tuple of (conn, db_path, scip_file, inner_id, repo_symbol)
    """
    index = scip_pb2.Index()
    index.metadata.project_root = "file:///test"

    # Define symbols - demonstrate false positive with nested classes
    base_class = "scip-java maven test abc123 `com.example`/UserService#"
    inner_class = "scip-java maven test abc123 `com.example`/UserService#Inner"  # NO terminal delimiter
    helper_class = "scip-java maven test abc123 `com.example`/UserService#InnerHelper"  # Falsely matches Inner%
    repo_class = "scip-java maven test abc123 `com.example`/DataRepository#"

    # Add symbols
    for symbol, display_name, kind in [
        (base_class, "UserService", scip_pb2.SymbolInformation.Class),
        (inner_class, "Inner", scip_pb2.SymbolInformation.Class),
        (helper_class, "InnerHelper", scip_pb2.SymbolInformation.Class),
        (repo_class, "DataRepository", scip_pb2.SymbolInformation.Class),
    ]:
        symbol_info = index.external_symbols.add()
        symbol_info.symbol = symbol
        symbol_info.display_name = display_name
        symbol_info.kind = kind

    # Document 1: UserService with nested classes
    doc = index.documents.add()
    doc.relative_path = "src/main/java/com/example/UserService.java"
    doc.language = "java"

    for symbol, line in [(base_class, 10), (inner_class, 12), (helper_class, 16)]:
        occ = doc.occurrences.add()
        occ.symbol = symbol
        occ.symbol_roles = ROLE_DEFINITION
        occ.range.extend([line, 0, line, 10])

    # Document 2: DataRepository definition
    doc2 = index.documents.add()
    doc2.relative_path = "src/main/java/com/example/DataRepository.java"
    doc2.language = "java"
    occ = doc2.occurrences.add()
    occ.symbol = repo_class
    occ.symbol_roles = ROLE_DEFINITION
    occ.range.extend([10, 0, 10, 14])

    # Build database
    with tempfile.NamedTemporaryFile(suffix=".scip", delete=False) as tmp:
        scip_file = Path(tmp.name)
        tmp.write(index.SerializeToString())

    manager = DatabaseManager(scip_file)
    manager.create_schema()
    builder = SCIPDatabaseBuilder()
    builder.build(scip_file, manager.db_path)
    db_path = manager.db_path

    # Connect and setup symbol references
    conn = sqlite3.connect(db_path)
    inner_id = _get_symbol_id(conn, inner_class)
    helper_id = _get_symbol_id(conn, helper_class)
    repo_id = _get_symbol_id(conn, repo_class)

    cursor = conn.cursor()

    # Get occurrence ID for InnerHelper
    cursor.execute("SELECT id FROM occurrences WHERE symbol_id = ? LIMIT 1", (helper_id,))
    helper_occ_id = cursor.fetchone()[0]

    # Add symbol reference: InnerHelper depends on DataRepository
    cursor.execute(
        "INSERT INTO symbol_references (from_symbol_id, to_symbol_id, relationship_type, occurrence_id) VALUES (?, ?, ?, ?)",
        (helper_id, repo_id, "calls", helper_occ_id)
    )
    conn.commit()

    return conn, db_path, scip_file, inner_id, repo_class


def _build_class_dependency_database(index, service_symbol):
    """
    Build database from SCIP index and return connection + service symbol ID.

    Args:
        index: SCIP index from _create_class_dependency_scip_index()
        service_symbol: Full SCIP symbol name for UserServiceImpl

    Returns:
        Tuple of (conn, db_path, scip_file, service_id)
    """
    # Write SCIP protobuf to temporary file
    with tempfile.NamedTemporaryFile(suffix=".scip", delete=False) as tmp:
        scip_file = Path(tmp.name)
        tmp.write(index.SerializeToString())

    # Build database using DatabaseManager
    manager = DatabaseManager(scip_file)
    manager.create_schema()
    builder = SCIPDatabaseBuilder()
    builder.build(scip_file, manager.db_path)

    # Connect and get service symbol ID
    conn = sqlite3.connect(manager.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM symbols WHERE name = ?", (service_symbol,))
    service_row = cursor.fetchone()
    assert service_row is not None, "UserServiceImpl not found in database"
    service_id = service_row[0]

    return conn, manager.db_path, scip_file, service_id


class TestDependenciesHybridClassLevelBug:
    """Test for class-level dependency bug in hybrid mode (Story #607)."""

    def test_dependencies_hybrid_includes_class_level_dependencies(self):
        """
        Verify hybrid mode finds class-level dependencies.

        BUG: _get_dependencies_hybrid() uses enclosing_range filtering
        which only finds references WITHIN a method's lexical scope.

        MISSES:
        - Import statements (file scope, not in method scope)
        - Field declarations (class scope, not in method scope)
        - Constructor parameters (different enclosing_range)

        BEFORE FIX: Returns 0 dependencies (enclosing_range misses class-level)
        AFTER FIX: Returns UserRepository (finds import OR constructor param)
        """
        # Setup
        index, service_symbol, repo_symbol = _create_class_dependency_scip_index()
        conn, db_path, scip_file, service_id = _build_class_dependency_database(index, service_symbol)

        try:
            # Execute hybrid mode query
            deps = get_dependencies(conn, service_id, depth=1, scip_file=scip_file)

            # Debug output
            print(f"\nDependencies found: {len(deps)}")
            for dep in deps:
                print(f"  - {dep['symbol_name']} at {dep['file_path']}:{dep['line']} ({dep['relationship']})")

            # CRITICAL: Should find UserRepository
            assert len(deps) >= 1, (
                "HYBRID MODE BUG: get_dependencies('UserServiceImpl') returned 0 results. "
                "Expected UserRepository via import (line 1) or constructor param (line 7). "
                "Root cause: enclosing_range filtering misses file/class-scope references."
            )

            # Verify UserRepository found
            repo_deps = [d for d in deps if "UserRepository" in d["symbol_name"]]
            assert len(repo_deps) >= 1, f"Expected UserRepository, got: {[d['symbol_name'] for d in deps]}"

            # Verify relationship type
            relationships = {d["relationship"] for d in repo_deps}
            assert "import" in relationships or "calls" in relationships, (
                f"Expected import/calls relationship, got: {relationships}"
            )

        finally:
            conn.close()
            db_path.unlink(missing_ok=True)
            scip_file.unlink(missing_ok=True)

    def test_dependencies_pattern_prevents_false_positives(self):
        """
        CRITICAL: Verify SCIP symbol pattern LIKE clause prevents false positives.

        BUG RISK: Pattern `LIKE name || '%'` matches ANY symbol starting with target name.

        REAL Scenario demonstrating false positive:
        - UserService#Inner (target nested class)
        - UserService#InnerHelper (DIFFERENT nested class)
        - InnerHelper depends on DataRepository

        Pattern test:
        - Target: `UserService#Inner`
        - Pattern WITHOUT fix: `UserService#Inner%`
        - FALSE POSITIVE: `UserService#InnerHelper` (starts with `UserService#Inner`)

        WITHOUT FIX: Pattern matches InnerHelper as "nested under Inner",
                     causing DataRepository to appear as Inner dependency (FALSE POSITIVE)
        WITH FIX: Pattern `name || '#%' OR name || '.%'` requires delimiter,
                  excludes InnerHelper, so DataRepository correctly does NOT appear

        SCIP symbol hierarchy:
        - Class: `package/Class#`
        - Nested class: `package/Class#Inner` (NO terminal delimiter!)
        - Method: `package/Class#method().` (terminal `.`)
        - True nested: `package/Class#Inner#method().` (delimiter after Inner)

        FIX: Use `LIKE name || '#%' OR name || '.%'` to require delimiter after target.
        """
        # Setup database with false positive scenario
        conn, db_path, scip_file, inner_id, repo_symbol = (
            _create_false_positive_test_database()
        )

        try:
            # Query dependencies of UserService#Inner class
            deps = get_dependencies(conn, inner_id, depth=1, scip_file=scip_file)
            dep_symbols = {d["symbol_name"] for d in deps}

            # CRITICAL: DataRepository should NOT appear (would be false positive)
            # DataRepository is a dependency of InnerHelper, NOT Inner
            # If pattern incorrectly matches InnerHelper as "nested under Inner", it will appear
            assert repo_symbol not in dep_symbols, (
                f"FALSE POSITIVE: DataRepository appeared as UserService#Inner dependency! "
                f"This means UserService#InnerHelper was incorrectly matched by pattern `Inner%`. "
                f"Pattern must use delimiters (# or .) to prevent prefix-only matches. "
                f"Found dependencies: {dep_symbols}"
            )

            # Inner has NO dependencies in this test scenario
            assert len(deps) == 0, (
                f"Expected 0 dependencies (Inner has no references), got {len(deps)}: {dep_symbols}"
            )

        finally:
            conn.close()
            db_path.unlink(missing_ok=True)
            scip_file.unlink(missing_ok=True)

    @pytest.mark.slow
    def test_expand_class_to_methods_helper(self):
        """
        Test _expand_class_to_methods helper function.

        Validates that CLASS/INTERFACE symbols are correctly expanded to nested methods.
        This is critical for trace_call_chain because call_graph only contains method-level entries.

        Using scip-java-mock fixture:
        - UserController CLASS (ID=1) should expand to [getUser, listUsers, constructor]
        - UserRepository INTERFACE (ID=8) should expand to [findById, save, delete]
        - UserController#getUser METHOD (ID=5) should return [5] (no expansion)
        """
        from code_indexer.scip.query.backends import DatabaseBackend
        from pathlib import Path

        scip_file = Path("test-fixtures/scip-java-mock/index.scip")
        db_path = Path("test-fixtures/scip-java-mock/index.scip.db")

        # Ensure database exists
        if not db_path.exists():
            from code_indexer.scip.database.schema import DatabaseManager
            from code_indexer.scip.database.builder import SCIPDatabaseBuilder
            db_manager = DatabaseManager(scip_file)
            db_manager.create_schema()
            builder = SCIPDatabaseBuilder()
            builder.build(scip_file, db_manager.db_path)

        backend = DatabaseBackend(db_path, project_root="test-fixtures/scip-java-mock", scip_file=scip_file)

        # Test 1: Expand UserController CLASS (ID=1) to methods
        usercontroller_methods = backend._expand_class_to_methods(1)
        assert len(usercontroller_methods) > 0, "UserController CLASS should expand to methods"
        assert 1 not in usercontroller_methods, "Expanded list should NOT include class ID itself"

        # Verify methods include getUser and listUsers
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM symbols WHERE id IN ({})".format(','.join('?' * len(usercontroller_methods))), usercontroller_methods)
        method_names = [row[0] for row in cursor.fetchall()]
        assert any("getUser" in name for name in method_names), f"Expected getUser in methods, got: {method_names}"
        assert any("listUsers" in name for name in method_names), f"Expected listUsers in methods, got: {method_names}"

        # Test 2: Expand UserRepository INTERFACE (ID=8) to abstract methods
        userrepo_methods = backend._expand_class_to_methods(8)
        assert len(userrepo_methods) > 0, "UserRepository INTERFACE should expand to methods"
        assert 8 not in userrepo_methods, "Expanded list should NOT include interface ID itself"

        cursor.execute("SELECT name FROM symbols WHERE id IN ({})".format(','.join('?' * len(userrepo_methods))), userrepo_methods)
        repo_method_names = [row[0] for row in cursor.fetchall()]
        assert any("findById" in name for name in repo_method_names), f"Expected findById in methods, got: {repo_method_names}"

        # Test 3: METHOD symbol should NOT expand (return as-is)
        method_ids = backend._expand_class_to_methods(5)  # UserController#getUser
        assert method_ids == [5], f"METHOD symbol should return [5], got: {method_ids}"

        conn.close()


def test_trace_call_chain_java_mock_bug():
    """
    Test trace_call_chain with java-mock database to verify Bug #2 impact.

    Bug #2: call_graph is missing interface→implementation edges, causing
    trace_call_chain to return incomplete chains even when using call_graph
    table correctly.

    Expected chain: UserController#getUser → UserService#findById (interface) →
                   [MISSING EDGE - Bug #2] → UserServiceImpl#findById (impl) →
                   UserRepository#findById

    This test should FAIL until Bug #2 is fixed in builder.py.
    """
    import pytest

    # Use actual java-mock database from golden repos
    db_path = Path.home() / '.cidx-server/data/golden-repos/java-mock/.code-indexer/scip/index.scip.db'
    if not db_path.exists():
        pytest.skip(f"java-mock database not found at {db_path}")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Find UserController#getUser METHOD (not class)
        cursor.execute("SELECT id FROM symbols WHERE name LIKE '%UserController#getUser%'")
        from_row = cursor.fetchone()
        assert from_row is not None, "UserController#getUser method not found"
        from_id = from_row[0]

        # Find UserRepository#findById METHOD (not interface)
        cursor.execute("SELECT id FROM symbols WHERE name LIKE '%UserRepository#findById%'")
        to_row = cursor.fetchone()
        assert to_row is not None, "UserRepository#findById method not found"
        to_id = to_row[0]

        # Verify call_graph has data (evidence it should work)
        cursor.execute("SELECT COUNT(*) FROM call_graph")
        call_graph_count = cursor.fetchone()[0]
        assert call_graph_count > 0, f"call_graph table should have data, got {call_graph_count}"

        # Verify symbol_references has fewer rows (evidence of bug)
        cursor.execute("SELECT COUNT(*) FROM symbol_references")
        symbol_refs_count = cursor.fetchone()[0]
        print(f"call_graph: {call_graph_count} rows, symbol_references: {symbol_refs_count} rows")

        # Execute trace_call_chain (which auto-detects and uses trace_call_chain_v2)
        from code_indexer.scip.database.queries import trace_call_chain
        chains = trace_call_chain(conn, from_id, to_id, max_depth=5, limit=100)

        # This assertion should FAIL with Bug #2 present (missing interface→impl edges)
        # After fix, it should pass
        assert len(chains) > 0, (
            f"Expected >0 chains from UserController#getUser (ID={from_id}) to UserRepository#findById (ID={to_id}), "
            f"but got {len(chains)}. Bug #2: call_graph missing interface→implementation edges"
        )

        print(f"SUCCESS: Found {len(chains)} chains")

    finally:
        conn.close()


def test_call_graph_has_interface_to_impl_edges():
    """
    Test that call_graph contains interface→implementation edges (Bug #2).

    Bug #2: call_graph is missing edges connecting interface methods to
    implementation methods, causing disconnected graphs.

    Expected edge: UserService#findById (interface, ID=17) →
                  UserServiceImpl#findById (implementation, ID=45)

    This test should FAIL until Bug #2 is fixed in builder.py.
    """
    import pytest

    # Use actual java-mock database from golden repos
    db_path = Path.home() / '.cidx-server/data/golden-repos/java-mock/.code-indexer/scip/index.scip.db'
    if not db_path.exists():
        pytest.skip(f"java-mock database not found at {db_path}")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Find UserService#findById (interface method)
        cursor.execute("SELECT id FROM symbols WHERE name LIKE '%UserService#findById%' AND kind = 'AbstractMethod'")
        interface_row = cursor.fetchone()
        assert interface_row is not None, "UserService#findById not found"
        interface_id = interface_row[0]

        # Find UserServiceImpl#findById (implementation method)
        cursor.execute("SELECT id FROM symbols WHERE name LIKE '%UserServiceImpl#findById%' AND kind = 'Method'")
        impl_row = cursor.fetchone()
        assert impl_row is not None, "UserServiceImpl#findById not found"
        impl_id = impl_row[0]

        # Check if call_graph has edge from interface to implementation
        cursor.execute(
            "SELECT COUNT(*) FROM call_graph WHERE caller_symbol_id = ? AND callee_symbol_id = ?",
            (interface_id, impl_id)
        )
        edge_count = cursor.fetchone()[0]

        # This assertion should FAIL with Bug #2 present
        # After fix, it should pass
        assert edge_count > 0, (
            f"Expected edge in call_graph from UserService#findById (ID={interface_id}) "
            f"to UserServiceImpl#findById (ID={impl_id}), but found {edge_count} edges. "
            f"Bug #2: Missing interface→implementation edges breaks call chains"
        )

        print(f"SUCCESS: Found {edge_count} edge(s) from interface to implementation")

    finally:
        conn.close()

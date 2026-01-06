"""Unit tests for SCIP database ETL pipeline builder."""

import sqlite3
from pathlib import Path


try:
    from pysqlite3 import dbapi2 as sqlite3
except ImportError:
    import sqlite3

from code_indexer.scip.database.builder import SCIPDatabaseBuilder
from code_indexer.scip.database.schema import DatabaseManager
from code_indexer.scip.protobuf import scip_pb2


class TestSchemaCreation:
    """Test database schema creation during build process."""

    def test_build_creates_schema_before_inserting(self, tmp_path: Path):
        """
        Test that build() creates database schema before inserting data.

        CRITICAL BUG: build() tries to insert into symbols table at line 71
        without calling create_schema() first, causing:
        sqlite3.OperationalError: no such table: symbols

        Given a minimal SCIP protobuf file
        When calling build() on empty database
        Then schema should be created automatically before data insertion
        And no sqlite3.OperationalError should occur
        """
        # Create minimal SCIP protobuf with one symbol
        index = scip_pb2.Index()

        symbol_info = index.external_symbols.add()
        symbol_info.symbol = "test.py::TestClass#"
        symbol_info.display_name = "TestClass"
        symbol_info.kind = scip_pb2.SymbolInformation.Class

        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database WITHOUT manually creating schema
        db_path = tmp_path / "test.scip.db"
        builder = SCIPDatabaseBuilder()

        # This should NOT raise sqlite3.OperationalError
        # build() should create schema internally
        result = builder.build(scip_file, db_path)

        # Verify build succeeded
        assert result["symbol_count"] == 1

        # Verify tables exist
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check symbols table exists and has data
        cursor.execute("SELECT COUNT(*) FROM symbols")
        count = cursor.fetchone()[0]
        assert count == 1

        # Check other required tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "symbols" in tables
        assert "documents" in tables
        assert "occurrences" in tables
        assert "call_graph" in tables

        conn.close()


class TestSymbolExtraction:
    """Test symbol extraction from SCIP protobuf."""

    def test_parse_symbols_from_protobuf(self, tmp_path: Path):
        """
        Test extraction of symbols from SCIP protobuf.

        Given a SCIP protobuf file with symbols
        When the ETL pipeline parses the protobuf
        Then all symbols are extracted with complete metadata
        """
        # Create a minimal SCIP protobuf file with one symbol
        index = scip_pb2.Index()

        # Add a symbol
        symbol_info = index.external_symbols.add()
        symbol_info.symbol = "test.py::TestClass#"
        symbol_info.display_name = "TestClass"
        symbol_info.kind = scip_pb2.SymbolInformation.Class

        # Add signature documentation
        sig_doc = scip_pb2.Document()
        sig_doc.text = "class TestClass:"
        symbol_info.signature_documentation.CopyFrom(sig_doc)

        # Add documentation
        symbol_info.documentation.append("Test class documentation")

        # Write protobuf to file
        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Parse symbols
        builder = SCIPDatabaseBuilder()
        symbols = builder._parse_symbols(scip_file)

        # Verify extraction
        assert len(symbols) == 1
        assert symbols[0]["name"] == "test.py::TestClass#"
        assert symbols[0]["display_name"] == "TestClass"
        assert symbols[0]["kind"] == "Class"
        assert symbols[0]["signature"] == "class TestClass:"
        assert symbols[0]["documentation"] == "Test class documentation"

    def test_insert_symbols_batch(self, tmp_path: Path):
        """
        Test batch insertion of symbols into database.

        Given a list of symbols extracted from protobuf
        When inserting symbols into database
        Then all symbols are inserted with batch operations
        And a symbol_id mapping is returned
        """
        # Create symbols list
        symbols = [
            {
                "name": "test.py::ClassA#",
                "display_name": "ClassA",
                "kind": "Class",
                "signature": "class ClassA:",
                "documentation": "Class A docs",
            },
            {
                "name": "test.py::ClassB#",
                "display_name": "ClassB",
                "kind": "Class",
                "signature": "class ClassB:",
                "documentation": "Class B docs",
            },
            {
                "name": "test.py::method_a().",
                "display_name": "method_a",
                "kind": "Method",
                "signature": "def method_a():",
                "documentation": None,
            },
        ]

        # Create database with schema
        scip_file = tmp_path / "test.scip"
        from code_indexer.scip.database.schema import DatabaseManager

        manager = DatabaseManager(scip_file)
        manager.create_schema()

        # Connect to the database
        db_path = manager.db_path
        conn = sqlite3.connect(db_path)

        # Insert symbols
        builder = SCIPDatabaseBuilder()
        symbol_map = builder._insert_symbols(conn, symbols)

        # Verify all symbols inserted
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM symbols")
        count = cursor.fetchone()[0]
        assert count == 3

        # Verify symbol_map created
        assert len(symbol_map) == 3
        assert "test.py::ClassA#" in symbol_map
        assert "test.py::ClassB#" in symbol_map
        assert "test.py::method_a()." in symbol_map

        # Verify each symbol has valid ID
        for symbol_name, symbol_id in symbol_map.items():
            assert symbol_id > 0
            cursor.execute("SELECT name FROM symbols WHERE id = ?", (symbol_id,))
            result = cursor.fetchone()
            assert result[0] == symbol_name

        conn.close()


class TestOccurrenceExtraction:
    """Test occurrence extraction from SCIP protobuf."""

    def test_parse_occurrences_from_protobuf(self, tmp_path: Path):
        """
        Test extraction of occurrences from SCIP protobuf documents.

        Given a SCIP protobuf with documents containing occurrences
        When the ETL pipeline parses occurrences
        Then all occurrences are extracted with location data and roles
        """
        # Create a SCIP protobuf with document and occurrences
        index = scip_pb2.Index()

        # Add document
        doc = index.documents.add()
        doc.relative_path = "test.py"
        doc.language = "Python"

        # Add occurrence with 4-element range (start_line, start_char, end_line, end_char)
        occ1 = doc.occurrences.add()
        occ1.symbol = "test.py::TestClass#"
        occ1.range.extend([10, 0, 10, 9])  # Line 10, columns 0-9
        occ1.symbol_roles = 1  # Definition

        # Add occurrence with 2-element range (line, char)
        occ2 = doc.occurrences.add()
        occ2.symbol = "test.py::TestClass#"
        occ2.range.extend([20, 5])  # Line 20, column 5
        occ2.symbol_roles = 2  # Reference

        # Add occurrence with enclosing_range
        occ3 = doc.occurrences.add()
        occ3.symbol = "test.py::method()."
        occ3.range.extend([15, 4, 15, 10])
        occ3.symbol_roles = 2  # Reference
        occ3.enclosing_range.extend([14, 0, 16, 0])  # Enclosing function

        # Write protobuf
        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Parse occurrences
        builder = SCIPDatabaseBuilder()
        documents, occurrences = builder._parse_occurrences(scip_file)

        # Verify document extraction
        assert len(documents) == 1
        assert documents[0]["relative_path"] == "test.py"
        assert documents[0]["language"] == "Python"

        # Verify occurrence extraction
        assert len(occurrences) == 3

        # Check first occurrence (4-element range)
        assert occurrences[0]["symbol_name"] == "test.py::TestClass#"
        assert occurrences[0]["start_line"] == 10
        assert occurrences[0]["start_char"] == 0
        assert occurrences[0]["end_line"] == 10
        assert occurrences[0]["end_char"] == 9
        assert occurrences[0]["role"] == 1
        assert occurrences[0]["enclosing_range_start_line"] is None

        # Check second occurrence (2-element range, same line end)
        assert occurrences[1]["start_line"] == 20
        assert occurrences[1]["start_char"] == 5
        assert occurrences[1]["end_line"] == 20  # Same as start_line
        assert occurrences[1]["end_char"] == 5  # Same as start_char

        # Check third occurrence (with enclosing_range)
        assert occurrences[2]["enclosing_range_start_line"] == 14
        assert occurrences[2]["enclosing_range_start_char"] == 0
        assert occurrences[2]["enclosing_range_end_line"] == 16
        assert occurrences[2]["enclosing_range_end_char"] == 0


class TestCallGraphGeneration:
    """Test pre-computed call graph generation."""

    def _create_proximity_test_scip(self, tmp_path: Path) -> Path:
        """Create SCIP file with function call requiring proximity resolution."""
        index = scip_pb2.Index()

        doc = index.documents.add()
        doc.relative_path = "test.py"
        doc.language = "Python"

        # Function definition at line 10
        func_def = doc.occurrences.add()
        func_def.symbol = "test.py::my_function()."
        func_def.range.extend([10, 0, 10, 11])
        func_def.symbol_roles = 1

        # Helper definition at line 5
        helper_def = doc.occurrences.add()
        helper_def.symbol = "test.py::helper()."
        helper_def.range.extend([5, 0, 5, 6])
        helper_def.symbol_roles = 1

        # Reference at line 12 (NO enclosing_range) - Reference + ReadAccess for function call
        helper_ref = doc.occurrences.add()
        helper_ref.symbol = "test.py::helper()."
        helper_ref.range.extend([12, 4, 12, 10])
        helper_ref.symbol_roles = (
            10  # Bit 2 (reference) + Bit 8 (ReadAccess) = calls relationship
        )

        # Add symbols
        func_symbol = index.external_symbols.add()
        func_symbol.symbol = "test.py::my_function()."
        func_symbol.display_name = "my_function"
        func_symbol.kind = scip_pb2.SymbolInformation.Method

        helper_symbol = index.external_symbols.add()
        helper_symbol.symbol = "test.py::helper()."
        helper_symbol.display_name = "helper"
        helper_symbol.kind = scip_pb2.SymbolInformation.Method

        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        return scip_file

    def test_call_graph_uses_proximity_resolution(self, tmp_path: Path):
        """
        Test that call graph edges are created using proximity heuristic.

        Given a SCIP protobuf with references without enclosing_range
        When building the database with call graph
        Then call graph edges are created using proximity heuristic
        """
        scip_file = self._create_proximity_test_scip(tmp_path)

        from code_indexer.scip.database.schema import DatabaseManager

        manager = DatabaseManager(scip_file)
        manager.create_schema()

        builder = SCIPDatabaseBuilder()
        result = builder.build(scip_file, manager.db_path)

        assert result["call_graph_count"] > 0

        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT caller_symbol_id, callee_symbol_id, relationship FROM call_graph"
        )
        edges = cursor.fetchall()

        assert len(edges) == 1
        caller_id, callee_id, relationship = edges[0]

        cursor.execute("SELECT name FROM symbols WHERE id = ?", (caller_id,))
        caller_name = cursor.fetchone()[0]

        cursor.execute("SELECT name FROM symbols WHERE id = ?", (callee_id,))
        callee_name = cursor.fetchone()[0]

        assert caller_name == "test.py::my_function()."
        assert callee_name == "test.py::helper()."
        assert relationship == "calls"

        conn.close()

    def test_call_graph_with_read_access_role(self, tmp_path: Path):
        """
        Test that call graph edges are created for role=8 (ROLE_READ_ACCESS).

        CRITICAL BUG FIX: Role bitmask was checking role & 2 (ROLE_IMPORT) when
        real SCIP data has role=8 (ROLE_READ_ACCESS) for function calls.

        Given a SCIP protobuf with occurrences having role=8 (ReadAccess)
        When building the database with call graph
        Then call graph edges are created (not 0 edges)
        """
        index = scip_pb2.Index()

        doc = index.documents.add()
        doc.relative_path = "test.py"
        doc.language = "Python"

        # Function definition
        func_def = doc.occurrences.add()
        func_def.symbol = "test.py::caller()."
        func_def.range.extend([10, 0, 10, 6])
        func_def.symbol_roles = 1  # ROLE_DEFINITION

        # Helper definition
        helper_def = doc.occurrences.add()
        helper_def.symbol = "test.py::callee()."
        helper_def.range.extend([5, 0, 5, 6])
        helper_def.symbol_roles = 1  # ROLE_DEFINITION

        # Reference with role=8 (ROLE_READ_ACCESS) - this is what real SCIP data has
        helper_ref = doc.occurrences.add()
        helper_ref.symbol = "test.py::callee()."
        helper_ref.range.extend([12, 4, 12, 10])
        helper_ref.symbol_roles = (
            8  # ROLE_READ_ACCESS (374,685 occurrences in real data)
        )

        # Add symbols
        func_symbol = index.external_symbols.add()
        func_symbol.symbol = "test.py::caller()."
        func_symbol.display_name = "caller"
        func_symbol.kind = scip_pb2.SymbolInformation.Method

        helper_symbol = index.external_symbols.add()
        helper_symbol.symbol = "test.py::callee()."
        helper_symbol.display_name = "callee"
        helper_symbol.kind = scip_pb2.SymbolInformation.Method

        scip_file = tmp_path / "test_role8.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        from code_indexer.scip.database.schema import DatabaseManager

        manager = DatabaseManager(scip_file)
        manager.create_schema()

        builder = SCIPDatabaseBuilder()
        result = builder.build(scip_file, manager.db_path)

        # CRITICAL: With role=8, call_graph_count MUST be > 0
        # Bug was: checking role & 2 (ROLE_IMPORT) when should check role & 8 (ROLE_READ_ACCESS)
        assert (
            result["call_graph_count"] > 0
        ), "Call graph should have edges for role=8 (ROLE_READ_ACCESS)"

        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT caller_symbol_id, callee_symbol_id, relationship FROM call_graph"
        )
        edges = cursor.fetchall()

        assert len(edges) == 1
        caller_id, callee_id, relationship = edges[0]

        cursor.execute("SELECT name FROM symbols WHERE id = ?", (caller_id,))
        caller_name = cursor.fetchone()[0]

        cursor.execute("SELECT name FROM symbols WHERE id = ?", (callee_id,))
        callee_name = cursor.fetchone()[0]

        assert caller_name == "test.py::caller()."
        assert callee_name == "test.py::callee()."
        assert relationship == "calls"

        conn.close()

    def test_no_data_loss_with_external_symbols(self, tmp_path: Path):
        """
        Test that external symbol references are not silently dropped.

        CRITICAL BUG FIX: 73,669 occurrences (15.5%) were silently dropped because
        the code skips occurrences when symbol not found in symbol_map.

        Given a SCIP protobuf with occurrences referencing external symbols
        When building the database
        Then all occurrences are inserted (no silent data loss)
        And external symbols are created as placeholder entries
        """
        index = scip_pb2.Index()

        doc = index.documents.add()
        doc.relative_path = "test.py"
        doc.language = "Python"

        # Internal function definition (this will be in symbol_map)
        internal_def = doc.occurrences.add()
        internal_def.symbol = "test.py::internal_func()."
        internal_def.range.extend([10, 0, 10, 13])
        internal_def.symbol_roles = 1  # ROLE_DEFINITION

        # Add internal symbol
        internal_symbol = index.external_symbols.add()
        internal_symbol.symbol = "test.py::internal_func()."
        internal_symbol.display_name = "internal_func"
        internal_symbol.kind = scip_pb2.SymbolInformation.Method

        # Reference to external symbol (NOT in external_symbols list - simulates external lib)
        external_ref = doc.occurrences.add()
        external_ref.symbol = "numpy::`ndarray#"  # External symbol not in index
        external_ref.range.extend([12, 4, 12, 11])
        external_ref.symbol_roles = 8  # ROLE_READ_ACCESS

        # Another reference to same external symbol
        external_ref2 = doc.occurrences.add()
        external_ref2.symbol = "numpy::`ndarray#"
        external_ref2.range.extend([15, 4, 15, 11])
        external_ref2.symbol_roles = 8  # ROLE_READ_ACCESS

        scip_file = tmp_path / "test_external.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        from code_indexer.scip.database.schema import DatabaseManager

        manager = DatabaseManager(scip_file)
        manager.create_schema()

        builder = SCIPDatabaseBuilder()
        result = builder.build(scip_file, manager.db_path)

        # CRITICAL: All 3 occurrences MUST be inserted (no data loss)
        assert (
            result["occurrence_count"] == 3
        ), f"Expected 3 occurrences, got {result['occurrence_count']}"

        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()

        # Verify external symbol was created
        cursor.execute(
            "SELECT COUNT(*) FROM symbols WHERE name = ?", ("numpy::`ndarray#",)
        )
        external_symbol_count = cursor.fetchone()[0]
        assert (
            external_symbol_count == 1
        ), "External symbol should be created as placeholder"

        # Verify all occurrences inserted
        cursor.execute("SELECT COUNT(*) FROM occurrences")
        occ_count = cursor.fetchone()[0]
        assert occ_count == 3, f"All occurrences should be inserted, got {occ_count}"

        conn.close()


class TestComputeEnclosingRanges:
    """Test computing enclosing ranges for definitions missing protobuf data."""

    def test_compute_enclosing_ranges_top_level_definitions(self):
        """
        Test computing enclosing ranges for top-level definitions.

        Given occurrences with multiple top-level function definitions without enclosing_range
        When computing enclosing ranges
        Then each definition's scope extends from def_line to (next_def_line - 1)
        """
        builder = SCIPDatabaseBuilder()

        # Create occurrences for two top-level functions
        # func_a defined at line 10, func_b defined at line 20
        occurrences = [
            {
                "symbol_name": "test.py::func_a().",
                "document_index": 0,
                "start_line": 10,
                "start_char": 0,
                "role": 1,  # ROLE_DEFINITION
                "enclosing_range_start_line": None,  # Missing protobuf data
            },
            {
                "symbol_name": "test.py::func_b().",
                "document_index": 0,
                "start_line": 20,
                "start_char": 0,
                "role": 1,  # ROLE_DEFINITION
                "enclosing_range_start_line": None,  # Missing protobuf data
            },
        ]

        # Compute enclosing ranges
        computed_ranges = builder._compute_enclosing_ranges(occurrences)

        # Verify func_a scope: lines 10-19 (up to func_b - 1)
        assert (0, "test.py::func_a().") in computed_ranges
        start_line, end_line = computed_ranges[(0, "test.py::func_a().")]
        assert start_line == 10
        assert end_line == 19

        # Verify func_b scope: lines 20-999999 (extends to EOF)
        assert (0, "test.py::func_b().") in computed_ranges
        start_line, end_line = computed_ranges[(0, "test.py::func_b().")]
        assert start_line == 20
        assert end_line == 999999  # EOF marker

    def test_compute_enclosing_ranges_preserves_protobuf_ranges(self):
        """
        Test that definitions with protobuf enclosing_range are NOT included in computed ranges.

        Given occurrences with some definitions having protobuf enclosing_range
        When computing enclosing ranges
        Then only definitions WITHOUT protobuf data should be in computed_ranges
        And definitions WITH protobuf data should be excluded
        """
        builder = SCIPDatabaseBuilder()

        occurrences = [
            {
                "symbol_name": "test.py::func_with_protobuf().",
                "document_index": 0,
                "start_line": 10,
                "start_char": 0,
                "role": 1,  # ROLE_DEFINITION
                "enclosing_range_start_line": 10,  # Has protobuf data
                "enclosing_range_end_line": 15,
            },
            {
                "symbol_name": "test.py::func_without_protobuf().",
                "document_index": 0,
                "start_line": 20,
                "start_char": 0,
                "role": 1,  # ROLE_DEFINITION
                "enclosing_range_start_line": None,  # Missing protobuf data
            },
        ]

        computed_ranges = builder._compute_enclosing_ranges(occurrences)

        # func_with_protobuf should NOT be in computed_ranges (has protobuf data)
        assert (0, "test.py::func_with_protobuf().") not in computed_ranges

        # func_without_protobuf SHOULD be in computed_ranges
        assert (0, "test.py::func_without_protobuf().") in computed_ranges
        start_line, end_line = computed_ranges[(0, "test.py::func_without_protobuf().")]
        assert start_line == 20
        assert end_line == 999999

    def test_compute_enclosing_ranges_multiple_documents(self):
        """
        Test that enclosing ranges are computed separately for each document.

        Given occurrences from multiple documents with definitions
        When computing enclosing ranges
        Then each document's definitions are processed independently
        And scopes do not cross document boundaries
        """
        builder = SCIPDatabaseBuilder()

        occurrences = [
            # Document 0
            {
                "symbol_name": "test1.py::func_a().",
                "document_index": 0,
                "start_line": 10,
                "start_char": 0,
                "role": 1,
                "enclosing_range_start_line": None,
            },
            # Document 1
            {
                "symbol_name": "test2.py::func_b().",
                "document_index": 1,
                "start_line": 5,
                "start_char": 0,
                "role": 1,
                "enclosing_range_start_line": None,
            },
            {
                "symbol_name": "test2.py::func_c().",
                "document_index": 1,
                "start_line": 15,
                "start_char": 0,
                "role": 1,
                "enclosing_range_start_line": None,
            },
        ]

        computed_ranges = builder._compute_enclosing_ranges(occurrences)

        # Document 0: func_a extends to EOF
        assert (0, "test1.py::func_a().") in computed_ranges
        start_line, end_line = computed_ranges[(0, "test1.py::func_a().")]
        assert start_line == 10
        assert end_line == 999999

        # Document 1: func_b extends to func_c - 1
        assert (1, "test2.py::func_b().") in computed_ranges
        start_line, end_line = computed_ranges[(1, "test2.py::func_b().")]
        assert start_line == 5
        assert end_line == 14

        # Document 1: func_c extends to EOF
        assert (1, "test2.py::func_c().") in computed_ranges
        start_line, end_line = computed_ranges[(1, "test2.py::func_c().")]
        assert start_line == 15
        assert end_line == 999999

    def test_build_symbol_references_creates_edges_without_protobuf_enclosing_range(
        self, tmp_path: Path
    ):
        """
        Test symbol_references gets edges when definitions lack protobuf enclosing_range.
        CRITICAL: Only 3.3% of definitions have protobuf data. Must use computed ranges for all.
        """
        # Create SCIP with definitions missing enclosing_range
        index = scip_pb2.Index()
        doc = index.documents.add()
        doc.relative_path = "test.py"
        # Function def at line 10 (NO protobuf enclosing_range)
        func_def = doc.occurrences.add()
        func_def.symbol = "test.py::my_function()."
        func_def.range.extend([10, 0, 10, 11])
        func_def.symbol_roles = 1
        helper_def = doc.occurrences.add()
        helper_def.symbol = "test.py::helper()."
        helper_def.range.extend([5, 0, 5, 6])
        helper_def.symbol_roles = 1
        # Reference at line 12 (within my_function computed scope)
        helper_ref = doc.occurrences.add()
        helper_ref.symbol = "test.py::helper()."
        helper_ref.range.extend([12, 4, 12, 10])
        helper_ref.symbol_roles = 8
        # Add symbols
        func_symbol = index.external_symbols.add()
        func_symbol.symbol = "test.py::my_function()."
        helper_symbol = index.external_symbols.add()
        helper_symbol.symbol = "test.py::helper()."
        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())
        from code_indexer.scip.database.schema import DatabaseManager

        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)
        # Verify symbol_references has edges
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM symbol_references")
        edge_count = cursor.fetchone()[0]
        conn.close()
        assert (
            edge_count > 0
        ), "symbol_references should have edges despite missing protobuf enclosing_range"

    def test_call_graph_populated_from_java_repository(self, tmp_path: Path):
        """
        Test that call_graph table is populated after building database from Java-style SCIP.

        CRITICAL BUG: Dependencies/dependents queries return no results because call_graph
        table is empty, even though _build_call_graph() is called during database build.

        Given a SCIP protobuf with Java-style class dependencies (UserServiceImpl -> UserRepository)
        When building the database
        Then call_graph table should have > 0 rows
        And specific dependency edges should exist (UserServiceImpl -> UserRepository)
        """
        # Create SCIP file modeling Java repository pattern
        # UserServiceImpl has constructor that depends on UserRepository
        index = scip_pb2.Index()

        doc = index.documents.add()
        doc.relative_path = "com/example/service/UserServiceImpl.java"
        doc.language = "java"

        # UserServiceImpl class definition at line 10
        service_class_def = doc.occurrences.add()
        service_class_def.symbol = "com.example.service/UserServiceImpl#"
        service_class_def.range.extend([10, 0, 10, 15])
        service_class_def.symbol_roles = 1  # ROLE_DEFINITION

        # UserServiceImpl constructor definition at line 15
        constructor_def = doc.occurrences.add()
        constructor_def.symbol = "com.example.service/UserServiceImpl#`<init>`()."
        constructor_def.range.extend([15, 4, 15, 18])
        constructor_def.symbol_roles = 1  # ROLE_DEFINITION

        # UserRepository reference in constructor parameter (line 15) - ReadAccess for dependency
        repo_ref = doc.occurrences.add()
        repo_ref.symbol = "com.example.repository/UserRepository#"
        repo_ref.range.extend([15, 38, 15, 52])
        repo_ref.symbol_roles = 8  # ROLE_READ_ACCESS (dependency relationship)

        # Add symbols
        service_symbol = index.external_symbols.add()
        service_symbol.symbol = "com.example.service/UserServiceImpl#"
        service_symbol.display_name = "UserServiceImpl"
        service_symbol.kind = scip_pb2.SymbolInformation.Class

        constructor_symbol = index.external_symbols.add()
        constructor_symbol.symbol = "com.example.service/UserServiceImpl#`<init>`()."
        constructor_symbol.display_name = "<init>"
        constructor_symbol.kind = scip_pb2.SymbolInformation.Method

        repo_symbol = index.external_symbols.add()
        repo_symbol.symbol = "com.example.repository/UserRepository#"
        repo_symbol.display_name = "UserRepository"
        repo_symbol.kind = scip_pb2.SymbolInformation.Class

        scip_file = tmp_path / "test_java_deps.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        from code_indexer.scip.database.schema import DatabaseManager

        manager = DatabaseManager(scip_file)
        manager.create_schema()

        builder = SCIPDatabaseBuilder()
        result = builder.build(scip_file, manager.db_path)

        # CRITICAL: call_graph table MUST have edges
        assert (
            result["call_graph_count"] > 0
        ), f"call_graph table should be populated, got {result['call_graph_count']} rows"

        # Verify specific dependency edge exists: UserServiceImpl.<init> -> UserRepository
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT c.caller_display_name, c.callee_display_name, c.relationship
            FROM call_graph c
            WHERE c.callee_display_name = 'UserRepository'
        """
        )
        edges = cursor.fetchall()

        assert len(edges) > 0, "Should have at least one edge to UserRepository"

        # Verify constructor depends on UserRepository
        caller_names = [e[0] for e in edges]
        assert (
            "<init>" in caller_names
        ), f"Constructor should depend on UserRepository, found callers: {caller_names}"

        conn.close()

    def test_call_graph_includes_all_reference_types(self, tmp_path: Path):
        """
        Test that call_graph includes ALL reference types (import, write, calls).

        FIXED BEHAVIOR: symbol_references AND call_graph both include ALL reference types.
        Previous bug: call_graph ONLY included role & 8 (ReadAccess), causing it to be empty
        for Java dependencies that use import (role=2) or write (role=4) relationships.

        Given a SCIP protobuf with import (role=2) and write (role=4) references
        When building the database
        Then both symbol_references AND call_graph should have edges
        Because dependencies/dependents queries need ALL reference types to work correctly
        """
        index = scip_pb2.Index()

        doc = index.documents.add()
        doc.relative_path = "test.py"
        doc.language = "python"

        # Function definition at line 10
        func_def = doc.occurrences.add()
        func_def.symbol = "test.py::my_function()."
        func_def.range.extend([10, 0, 10, 11])
        func_def.symbol_roles = 1  # ROLE_DEFINITION

        # Import reference at line 5 (role=2, NOT ReadAccess)
        import_ref = doc.occurrences.add()
        import_ref.symbol = "external/Library#"
        import_ref.range.extend([5, 0, 5, 7])
        import_ref.symbol_roles = 2  # ROLE_IMPORT (not ReadAccess)

        # Write reference at line 12 (role=4, NOT ReadAccess)
        write_ref = doc.occurrences.add()
        write_ref.symbol = "test.py::variable."
        write_ref.range.extend([12, 4, 12, 12])
        write_ref.symbol_roles = 4  # ROLE_WRITE_ACCESS (not ReadAccess)

        # Add symbols
        func_symbol = index.external_symbols.add()
        func_symbol.symbol = "test.py::my_function()."
        func_symbol.display_name = "my_function"

        lib_symbol = index.external_symbols.add()
        lib_symbol.symbol = "external/Library#"
        lib_symbol.display_name = "Library"

        var_symbol = index.external_symbols.add()
        var_symbol.symbol = "test.py::variable."
        var_symbol.display_name = "variable"

        scip_file = tmp_path / "test_import_write.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        from code_indexer.scip.database.schema import DatabaseManager

        manager = DatabaseManager(scip_file)
        manager.create_schema()

        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # FIXED: Both tables should have edges (all reference types)
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM symbol_references")
        sr_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM call_graph")
        cg_count = cursor.fetchone()[0]

        conn.close()

        # After fix: Both tables include ALL reference types
        assert (
            sr_count > 0
        ), "symbol_references should have edges for import/write references"
        assert (
            cg_count > 0
        ), "call_graph should ALSO have edges for import/write references (FIX for dependencies/dependents bug)"

    def test_call_graph_with_external_symbol_reference(self, tmp_path: Path):
        """
        Test that call_graph is populated when method references external symbol.

        Reproduces user's bug scenario: Service method calls Repository (external library)
        where Repository is NOT in external_symbols list but should get placeholder entry.

        Given a SCIP with method definition and ReadAccess reference to external symbol
        When building the database (which auto-creates placeholder for external symbols)
        Then call_graph should have edge from method to external symbol
        """
        index = scip_pb2.Index()
        doc = index.documents.add()
        doc.relative_path = "Service.java"

        # Method definition at line 15
        method_def = doc.occurrences.add()
        method_def.symbol = "com.example/Service#doWork()."
        method_def.range.extend([15, 4, 15, 10])
        method_def.symbol_roles = 1

        # External Repository reference at line 17 (ReadAccess)
        repo_ref = doc.occurrences.add()
        repo_ref.symbol = "com.example/Repository#"
        repo_ref.range.extend([17, 8, 17, 18])
        repo_ref.symbol_roles = 8  # ROLE_READ_ACCESS

        # Only add method to external_symbols (Repository is external library)
        method_symbol = index.external_symbols.add()
        method_symbol.symbol = "com.example/Service#doWork()."
        method_symbol.display_name = "doWork"

        scip_file = tmp_path / "external_ref.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        from code_indexer.scip.database.schema import DatabaseManager

        manager = DatabaseManager(scip_file)
        manager.create_schema()

        builder = SCIPDatabaseBuilder()
        result = builder.build(scip_file, manager.db_path)

        # Verify call_graph has edge for method -> Repository
        assert (
            result["call_graph_count"] > 0
        ), f"call_graph should have edge for method -> external Repository, got {result['call_graph_count']}"

        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT callee_display_name FROM call_graph")
        callees = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert (
            "Repository" in callees
        ), f"call_graph should reference external Repository symbol, got: {callees}"

    def test_call_graph_empty_when_symbol_references_populated(self, tmp_path: Path):
        """
        Test that reproduces CRITICAL BUG from manual testing evidence.

        EVIDENCE FROM MANUAL TESTING:
        - symbols: 155 rows
        - occurrences: 491 rows
        - symbol_references: 193 rows ✅ POPULATED
        - call_graph: 0 rows ❌ EMPTY (BUG)

        ROOT CAUSE: _build_call_graph() requires role & 8 (ROLE_READ_ACCESS) at line 640,
        but _build_symbol_references() includes ALL reference types (import/write/calls).

        If SCIP data has references with role=2 (ROLE_IMPORT) or role=4 (ROLE_WRITE_ACCESS)
        but NOT role=8 (ROLE_READ_ACCESS), then symbol_references gets populated but
        call_graph remains empty.

        This test verifies the bug exists by creating SCIP data that mimics the
        real java-mock scenario: many occurrences, symbol_references populated,
        but call_graph empty due to no role & 8 occurrences.
        """
        index = scip_pb2.Index()

        doc = index.documents.add()
        doc.relative_path = "Service.java"
        doc.language = "java"

        # Method definition at line 10
        method_def = doc.occurrences.add()
        method_def.symbol = "com.example/Service#doWork()."
        method_def.range.extend([10, 4, 10, 10])
        method_def.symbol_roles = 1  # ROLE_DEFINITION

        # Repository class definition at line 5
        repo_def = doc.occurrences.add()
        repo_def.symbol = "com.example/Repository#"
        repo_def.range.extend([5, 0, 5, 10])
        repo_def.symbol_roles = 1  # ROLE_DEFINITION

        # CRITICAL: Reference with role=2 (ROLE_IMPORT) - NOT ReadAccess
        # This is what causes the bug - symbol_references includes it, call_graph excludes it
        repo_ref = doc.occurrences.add()
        repo_ref.symbol = "com.example/Repository#"
        repo_ref.range.extend([12, 8, 12, 18])
        repo_ref.symbol_roles = 2  # ROLE_IMPORT (NO ReadAccess bit 8)

        # Add symbols
        method_symbol = index.external_symbols.add()
        method_symbol.symbol = "com.example/Service#doWork()."
        method_symbol.display_name = "doWork"
        method_symbol.kind = scip_pb2.SymbolInformation.Method

        repo_symbol = index.external_symbols.add()
        repo_symbol.symbol = "com.example/Repository#"
        repo_symbol.display_name = "Repository"
        repo_symbol.kind = scip_pb2.SymbolInformation.Class

        scip_file = tmp_path / "bug_test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        from code_indexer.scip.database.schema import DatabaseManager

        manager = DatabaseManager(scip_file)
        manager.create_schema()

        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Verify the BUG: symbol_references has edges, call_graph is empty
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM symbol_references")
        sr_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM call_graph")
        cg_count = cursor.fetchone()[0]

        conn.close()

        # THIS IS THE BUG - symbol_references populated but call_graph empty
        # Expected: If symbol_references has edges, call_graph should also have edges
        # Actual: symbol_references > 0, call_graph = 0
        print(f"DEBUG: symbol_references={sr_count}, call_graph={cg_count}")
        assert (
            sr_count > 0
        ), "symbol_references should be populated (matches manual test evidence)"
        # THIS ASSERTION SHOULD FAIL, reproducing the bug
        assert cg_count > 0, (
            f"BUG REPRODUCED: call_graph is empty ({cg_count}) while symbol_references has {sr_count} rows. "
            f"Root cause: _build_call_graph() requires role & 8 (ReadAccess) but this test only has role=2 (Import)."
        )

    def test_enclosing_resolver_excludes_local_variables(self, tmp_path: Path):
        """
        Test that EnclosingSymbolResolver excludes local variables from proximity resolution.

        CRITICAL BUG FIX: When method definition and parameter definition occur on same line,
        proximity resolver was selecting parameter (local variable) instead of method as
        enclosing symbol, causing call_graph entries to be attributed to wrong symbol.

        Example: UserController.getUser(Long userId) has both method and parameter at line 12.
        Before fix: References inside getUser were attributed to "username" parameter.
        After fix: References correctly attributed to "getUser" method.

        Given real SCIP file with method definitions and parameters on same line
        When building call_graph after fix
        Then method definitions should have call_graph entries (was 0 before fix)
        """
        import pytest

        real_scip_file = Path("test-fixtures/scip-java-mock/index.scip")
        if not real_scip_file.exists():
            pytest.skip(f"Test fixture not available: {real_scip_file}")

        # Build database
        test_db_path = tmp_path / "test.db"
        manager = DatabaseManager(real_scip_file)
        manager.db_path = test_db_path
        manager.create_schema()

        builder = SCIPDatabaseBuilder()
        result = builder.build(real_scip_file, test_db_path)

        assert result["symbol_count"] > 0
        assert result["call_graph_count"] > 0

        with sqlite3.connect(test_db_path) as conn:
            cursor = conn.cursor()

            # Get getUser method
            cursor.execute(
                "SELECT id FROM symbols WHERE display_name='getUser' LIMIT 1"
            )
            getUser_row = cursor.fetchone()
            assert getUser_row, "getUser method should exist"
            getUser_id = getUser_row[0]

            # CRITICAL ASSERTION: getUser method should have call_graph entries as caller
            # Before fix: 0 entries (references attributed to "username" local variable)
            # After fix: >0 entries (references correctly attributed to getUser method)
            cursor.execute(
                "SELECT COUNT(*) FROM call_graph WHERE caller_symbol_id=?",
                (getUser_id,),
            )
            cg_from_getUser = cursor.fetchone()[0]
            assert (
                cg_from_getUser > 0
            ), f"FIX VERIFICATION FAILED: getUser has {cg_from_getUser} call_graph entries (expected >0)"

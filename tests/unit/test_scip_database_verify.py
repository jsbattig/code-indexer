"""Unit tests for SCIP database verification pipeline."""

from pathlib import Path

try:
    from pysqlite3 import dbapi2 as sqlite3
except ImportError:
    import sqlite3

from code_indexer.scip.database.verify import SCIPDatabaseVerifier, VerificationResult
from code_indexer.scip.database.builder import (
    SCIPDatabaseBuilder,
    ROLE_DEFINITION,
    ROLE_READ_ACCESS,
)
from code_indexer.scip.database.schema import DatabaseManager
from code_indexer.scip.protobuf import scip_pb2


class TestSymbolVerification:
    """Test symbol count and content verification (AC1)."""

    def test_verify_symbols_exact_count_match(self, tmp_path: Path):
        """
        Test symbol count verification when counts match exactly.

        Given a SCIP protobuf with 3 symbols
        And a database with 3 symbols
        When verifying symbols
        Then verification passes
        And symbol_count matches
        """
        # Create SCIP protobuf with 3 symbols
        index = scip_pb2.Index()
        for i in range(3):
            symbol = index.external_symbols.add()
            symbol.symbol = f"test.py::Symbol{i}#"
            symbol.display_name = f"Symbol{i}"
            symbol.kind = scip_pb2.SymbolInformation.Class

        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Verify
        verifier = SCIPDatabaseVerifier(manager.db_path, scip_file)
        result = verifier.verify()

        assert result.passed is True
        assert result.symbol_count_match is True
        assert result.total_errors == 0

    def test_verify_symbols_count_mismatch(self, tmp_path: Path):
        """
        Test symbol count verification when counts mismatch.

        Given a SCIP protobuf with 3 symbols
        And a database with only 2 symbols (data corruption)
        When verifying symbols
        Then verification fails
        And error message indicates count mismatch
        """
        # Create SCIP protobuf with 3 symbols
        index = scip_pb2.Index()
        for i in range(3):
            symbol = index.external_symbols.add()
            symbol.symbol = f"test.py::Symbol{i}#"
            symbol.display_name = f"Symbol{i}"
            symbol.kind = scip_pb2.SymbolInformation.Class

        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Corrupt database by deleting one symbol
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM symbols WHERE name = ?", ("test.py::Symbol0#",))
        conn.commit()
        conn.close()

        # Verify
        verifier = SCIPDatabaseVerifier(manager.db_path, scip_file)
        result = verifier.verify()

        assert result.passed is False
        assert result.symbol_count_match is False
        assert "symbol count mismatch" in result.errors[0].lower()
        assert "expected: 3" in result.errors[0].lower()
        assert "actual: 2" in result.errors[0].lower()

    def test_verify_symbols_sample_content(self, tmp_path: Path):
        """
        Test symbol content verification using random sampling.

        Given a SCIP protobuf with 150 symbols
        When verifying symbols with sample size 100
        Then 100 random symbols are checked for name/display_name/kind match
        And verification passes if all samples match
        """
        # Create SCIP protobuf with 150 symbols
        index = scip_pb2.Index()
        for i in range(150):
            symbol = index.external_symbols.add()
            symbol.symbol = f"test.py::Symbol{i}#"
            symbol.display_name = f"Symbol{i}"
            symbol.kind = scip_pb2.SymbolInformation.Class

        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Verify
        verifier = SCIPDatabaseVerifier(manager.db_path, scip_file)
        result = verifier.verify()

        assert result.passed is True
        assert result.symbol_sample_verified is True
        # Verify sample size (should be 100 for 150 symbols)
        assert 90 <= result.symbols_sampled <= 100


class TestOccurrenceVerification:
    """Test occurrence count and content verification (AC2)."""

    def test_verify_occurrences_exact_count_match(self, tmp_path: Path):
        """
        Test occurrence count verification when counts match exactly.

        Given a SCIP protobuf with 5 occurrences
        And a database with 5 occurrences
        When verifying occurrences
        Then verification passes
        And occurrence_count matches
        """
        # Create SCIP protobuf with document and 5 occurrences
        index = scip_pb2.Index()

        # Add symbol
        symbol = index.external_symbols.add()
        symbol.symbol = "test.py::TestClass#"
        symbol.display_name = "TestClass"
        symbol.kind = scip_pb2.SymbolInformation.Class

        # Add document with 5 occurrences
        doc = index.documents.add()
        doc.relative_path = "test.py"
        doc.language = "Python"

        for i in range(5):
            occ = doc.occurrences.add()
            occ.symbol = "test.py::TestClass#"
            occ.range.extend([i * 10, 0, i * 10, 9])
            occ.symbol_roles = 1 if i == 0 else 8  # First is definition, rest are references

        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Verify
        verifier = SCIPDatabaseVerifier(manager.db_path, scip_file)
        result = verifier.verify()

        assert result.passed is True
        assert result.occurrence_count_match is True

    def test_verify_occurrences_count_mismatch(self, tmp_path: Path):
        """
        Test occurrence count verification when counts mismatch.

        Given a SCIP protobuf with 5 occurrences
        And a database with only 3 occurrences (ETL bug)
        When verifying occurrences
        Then verification fails
        And error message indicates count mismatch
        """
        # Create SCIP protobuf with 5 occurrences
        index = scip_pb2.Index()

        symbol = index.external_symbols.add()
        symbol.symbol = "test.py::TestClass#"
        symbol.display_name = "TestClass"
        symbol.kind = scip_pb2.SymbolInformation.Class

        doc = index.documents.add()
        doc.relative_path = "test.py"
        doc.language = "Python"

        for i in range(5):
            occ = doc.occurrences.add()
            occ.symbol = "test.py::TestClass#"
            occ.range.extend([i * 10, 0, i * 10, 9])
            occ.symbol_roles = 1 if i == 0 else 8

        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Corrupt database by deleting 2 occurrences
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM occurrences WHERE id IN (SELECT id FROM occurrences LIMIT 2)")
        conn.commit()
        conn.close()

        # Verify
        verifier = SCIPDatabaseVerifier(manager.db_path, scip_file)
        result = verifier.verify()

        assert result.passed is False
        assert result.occurrence_count_match is False
        assert "occurrence count mismatch" in result.errors[0].lower()

    def test_verify_occurrences_sample_content(self, tmp_path: Path):
        """
        Test occurrence content verification using random sampling.

        Given a SCIP protobuf with 2000 occurrences
        When verifying occurrences with sample size 1000
        Then 1000 random occurrences are checked for location/role match
        And verification passes if all samples match
        """
        # Create SCIP protobuf with 2000 occurrences
        index = scip_pb2.Index()

        symbol = index.external_symbols.add()
        symbol.symbol = "test.py::TestClass#"
        symbol.display_name = "TestClass"
        symbol.kind = scip_pb2.SymbolInformation.Class

        doc = index.documents.add()
        doc.relative_path = "test.py"
        doc.language = "Python"

        for i in range(2000):
            occ = doc.occurrences.add()
            occ.symbol = "test.py::TestClass#"
            occ.range.extend([i, 0, i, 9])
            occ.symbol_roles = 8  # ReadAccess

        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Verify
        verifier = SCIPDatabaseVerifier(manager.db_path, scip_file)
        result = verifier.verify()

        assert result.passed is True
        assert result.occurrence_sample_verified is True
        # Verify sample size (should be 1000 for 2000 occurrences)
        assert 900 <= result.occurrences_sampled <= 1000


class TestDocumentVerification:
    """Test document verification (AC3)."""

    def test_verify_documents_all_paths_and_languages(self, tmp_path: Path):
        """Test document verification checks all paths and languages."""
        # Create SCIP protobuf with 3 documents
        index = scip_pb2.Index()

        for i, (path, lang) in enumerate([
            ("src/main.py", "Python"),
            ("src/utils.py", "Python"),
            ("test/test_main.py", "Python"),
        ]):
            doc = index.documents.add()
            doc.relative_path = path
            doc.language = lang

            # Add minimal symbol/occurrence
            symbol = index.external_symbols.add()
            symbol.symbol = f"{path}::Symbol{i}#"
            symbol.display_name = f"Symbol{i}"

            occ = doc.occurrences.add()
            occ.symbol = f"{path}::Symbol{i}#"
            occ.range.extend([1, 0, 1, 10])
            occ.symbol_roles = 1

        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Verify
        verifier = SCIPDatabaseVerifier(manager.db_path, scip_file)
        result = verifier.verify()

        assert result.passed is True
        assert result.documents_verified is True

    def test_verify_documents_path_mismatch(self, tmp_path: Path):
        """Test document verification fails when paths mismatch."""
        index = scip_pb2.Index()

        symbol = index.external_symbols.add()
        symbol.symbol = "src/main.py::Symbol#"
        symbol.display_name = "Symbol"

        doc = index.documents.add()
        doc.relative_path = "src/main.py"
        doc.language = "Python"

        occ = doc.occurrences.add()
        occ.symbol = "src/main.py::Symbol#"
        occ.range.extend([1, 0, 1, 10])
        occ.symbol_roles = 1

        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        # Build database
        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Corrupt database
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE documents SET relative_path = ? WHERE relative_path = ?",
                      ("src/wrong.py", "src/main.py"))
        conn.commit()
        conn.close()

        # Verify
        verifier = SCIPDatabaseVerifier(manager.db_path, scip_file)
        result = verifier.verify()

        assert result.passed is False
        assert result.documents_verified is False
        assert "document path mismatch" in result.errors[0].lower()


class TestCallGraphVerification:
    """Test call graph FK integrity and edge verification (AC4)."""

    def test_verify_call_graph_fk_integrity(self, tmp_path: Path):
        """Test call graph FK integrity verification."""
        index = scip_pb2.Index()

        caller_symbol = index.external_symbols.add()
        caller_symbol.symbol = "test.py::caller()."
        caller_symbol.display_name = "caller"
        caller_symbol.kind = scip_pb2.SymbolInformation.Method

        callee_symbol = index.external_symbols.add()
        callee_symbol.symbol = "test.py::callee()."
        callee_symbol.display_name = "callee"
        callee_symbol.kind = scip_pb2.SymbolInformation.Method

        doc = index.documents.add()
        doc.relative_path = "test.py"
        doc.language = "Python"

        caller_def = doc.occurrences.add()
        caller_def.symbol = "test.py::caller()."
        caller_def.range.extend([10, 0, 10, 6])
        caller_def.symbol_roles = ROLE_DEFINITION

        callee_def = doc.occurrences.add()
        callee_def.symbol = "test.py::callee()."
        callee_def.range.extend([5, 0, 5, 6])
        callee_def.symbol_roles = ROLE_DEFINITION

        callee_ref = doc.occurrences.add()
        callee_ref.symbol = "test.py::callee()."
        callee_ref.range.extend([12, 4, 12, 10])
        callee_ref.symbol_roles = ROLE_READ_ACCESS

        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        verifier = SCIPDatabaseVerifier(manager.db_path, scip_file)
        result = verifier.verify()

        assert result.passed is True
        assert result.call_graph_fk_valid is True

    def test_verify_call_graph_fk_integrity_broken(self, tmp_path: Path):
        """Test call graph FK integrity verification detects broken FKs."""
        index = scip_pb2.Index()

        caller_symbol = index.external_symbols.add()
        caller_symbol.symbol = "test.py::caller()."
        caller_symbol.display_name = "caller"
        caller_symbol.kind = scip_pb2.SymbolInformation.Method

        callee_symbol = index.external_symbols.add()
        callee_symbol.symbol = "test.py::callee()."
        callee_symbol.display_name = "callee"
        callee_symbol.kind = scip_pb2.SymbolInformation.Method

        doc = index.documents.add()
        doc.relative_path = "test.py"
        doc.language = "Python"

        caller_def = doc.occurrences.add()
        caller_def.symbol = "test.py::caller()."
        caller_def.range.extend([10, 0, 10, 6])
        caller_def.symbol_roles = ROLE_DEFINITION

        callee_def = doc.occurrences.add()
        callee_def.symbol = "test.py::callee()."
        callee_def.range.extend([5, 0, 5, 6])
        callee_def.symbol_roles = ROLE_DEFINITION

        callee_ref = doc.occurrences.add()
        callee_ref.symbol = "test.py::callee()."
        callee_ref.range.extend([12, 4, 12, 10])
        callee_ref.symbol_roles = ROLE_READ_ACCESS

        scip_file = tmp_path / "test.scip"
        with open(scip_file, "wb") as f:
            f.write(index.SerializeToString())

        manager = DatabaseManager(scip_file)
        manager.create_schema()
        builder = SCIPDatabaseBuilder()
        builder.build(scip_file, manager.db_path)

        # Corrupt database by breaking FK
        conn = sqlite3.connect(manager.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = OFF")
        cursor.execute("DELETE FROM symbols WHERE name = ?", ("test.py::callee().",))
        conn.commit()
        conn.close()

        verifier = SCIPDatabaseVerifier(manager.db_path, scip_file)
        result = verifier.verify()

        assert result.passed is False
        assert result.call_graph_fk_valid is False
        # Check if any error contains "foreign key" or "invalid reference"
        assert any("foreign key" in err.lower() or "invalid reference" in err.lower() for err in result.errors)

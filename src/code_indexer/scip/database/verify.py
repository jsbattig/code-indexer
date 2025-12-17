"""SCIP database verification pipeline - ensures ETL accuracy."""

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

try:
    from pysqlite3 import dbapi2 as sqlite3
except ImportError:
    import sqlite3

from ..protobuf import scip_pb2


# Verification sampling constants
MAX_SYMBOL_SAMPLE_SIZE = 100
MAX_OCCURRENCE_SAMPLE_SIZE = 1000
MAX_CALL_GRAPH_SAMPLE_SIZE = 100


@dataclass
class VerificationResult:
    """Result of database verification checks."""

    passed: bool
    symbol_count_match: bool
    occurrence_count_match: bool
    documents_verified: bool
    call_graph_fk_valid: bool
    symbol_sample_verified: bool
    occurrence_sample_verified: bool
    call_graph_sample_verified: bool
    errors: List[str] = field(default_factory=list)
    total_errors: int = 0
    symbols_sampled: int = 0
    occurrences_sampled: int = 0
    call_graph_edges_sampled: int = 0


class SCIPDatabaseVerifier:
    """Verifies SCIP database contents match protobuf source."""

    def __init__(self, db_path: Path, scip_file: Path):
        """
        Initialize verifier with database and protobuf file paths.

        Args:
            db_path: Path to SQLite database file
            scip_file: Path to source .scip protobuf file
        """
        self.db_path = Path(db_path)
        self.scip_file = Path(scip_file)

    def verify(self) -> VerificationResult:
        """
        Run all verification checks.

        Returns:
            VerificationResult with pass/fail status and error details
        """
        errors: List[str] = []

        # Run all verification checks
        symbol_count_match, symbol_sample_ok, symbols_sampled = self._verify_symbols(errors)
        occurrence_count_match, occurrence_sample_ok, occurrences_sampled = self._verify_occurrences(errors)
        documents_ok = self._verify_documents(errors)
        call_graph_fk_ok, call_graph_sample_ok, call_graph_sampled = self._verify_call_graph(errors)

        # Determine overall pass/fail
        passed = (
            symbol_count_match
            and symbol_sample_ok
            and occurrence_count_match
            and occurrence_sample_ok
            and documents_ok
            and call_graph_fk_ok
            and call_graph_sample_ok
        )

        return VerificationResult(
            passed=passed,
            symbol_count_match=symbol_count_match,
            occurrence_count_match=occurrence_count_match,
            documents_verified=documents_ok,
            call_graph_fk_valid=call_graph_fk_ok,
            symbol_sample_verified=symbol_sample_ok,
            occurrence_sample_verified=occurrence_sample_ok,
            call_graph_sample_verified=call_graph_sample_ok,
            errors=errors,
            total_errors=len(errors),
            symbols_sampled=symbols_sampled,
            occurrences_sampled=occurrences_sampled,
            call_graph_edges_sampled=call_graph_sampled,
        )

    def _verify_symbols(self, errors: List[str]) -> tuple[bool, bool, int]:
        """
        Verify symbol count and sample content.

        Counts both explicit symbols from protobuf AND external symbols that
        builder auto-generates for references not in the symbol list.

        Args:
            errors: List to append error messages to

        Returns:
            Tuple of (count_match, sample_ok, symbols_sampled)
        """
        # Parse symbols from protobuf
        protobuf_symbols = self._parse_protobuf_symbols()

        # Parse occurrences to find external symbols (not in protobuf symbol list)
        protobuf_occurrences = self._parse_protobuf_occurrences()

        # Build set of symbol names from protobuf
        protobuf_symbol_names = {sym.symbol for sym in protobuf_symbols}

        # Find unique symbol names in occurrences that are NOT in protobuf symbol list
        # These are external symbols that builder will auto-generate
        external_symbol_names = set()
        for occ in protobuf_occurrences:
            symbol_name = occ['symbol']
            if symbol_name not in protobuf_symbol_names:
                external_symbol_names.add(symbol_name)

        # Expected count = protobuf symbols + auto-generated external symbols
        expected_count = len(protobuf_symbols) + len(external_symbol_names)

        # Count symbols in database
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM symbols")
            actual_count = cursor.fetchone()[0]

        # Check count match
        count_match = expected_count == actual_count
        if not count_match:
            errors.append(
                f"Symbol count mismatch: expected: {expected_count}, actual: {actual_count}"
            )

        # Sample verification
        sample_ok, symbols_sampled = self._verify_symbol_sample(protobuf_symbols, errors)

        return count_match, sample_ok, symbols_sampled

    def _parse_protobuf_symbols(self) -> List:
        """
        Parse symbols from SCIP protobuf file.

        Returns:
            List of symbol SymbolInformation objects
        """
        with open(self.scip_file, "rb") as f:
            index = scip_pb2.Index()  # type: ignore[attr-defined]
            index.ParseFromString(f.read())

        # Collect symbols from external_symbols and document symbols
        protobuf_symbols = []
        for symbol_info in index.external_symbols:
            protobuf_symbols.append(symbol_info)

        for doc in index.documents:
            for symbol_info in doc.symbols:
                protobuf_symbols.append(symbol_info)

        return protobuf_symbols

    def _verify_symbol_sample(self, protobuf_symbols: List, errors: List[str]) -> tuple[bool, int]:
        """
        Verify random sample of symbols match database.

        Args:
            protobuf_symbols: List of symbol objects from protobuf
            errors: List to append error messages to

        Returns:
            Tuple of (sample_ok, symbols_sampled)
        """
        expected_count = len(protobuf_symbols)
        sample_size = min(MAX_SYMBOL_SAMPLE_SIZE, expected_count)
        symbols_sampled = 0
        sample_ok = True

        if expected_count == 0 or sample_size == 0:
            return sample_ok, symbols_sampled

        # Sample random symbols
        sample_indices = random.sample(range(expected_count), sample_size)
        sampled_symbols = [protobuf_symbols[i] for i in sample_indices]

        # Verify each sampled symbol
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            for symbol_info in sampled_symbols:
                symbol_name = symbol_info.symbol
                cursor.execute(
                    "SELECT display_name, kind FROM symbols WHERE name = ?",
                    (symbol_name,),
                )
                result = cursor.fetchone()

                if result is None:
                    errors.append(f"Symbol not found in database: {symbol_name}")
                    sample_ok = False
                else:
                    db_display_name, db_kind = result
                    # Verify display_name matches if present
                    if symbol_info.display_name and db_display_name != symbol_info.display_name:
                        errors.append(
                            f"Symbol display_name mismatch for {symbol_name}: "
                            f"expected {symbol_info.display_name}, actual {db_display_name}"
                        )
                        sample_ok = False

                symbols_sampled += 1

        return sample_ok, symbols_sampled

    def _verify_occurrences(self, errors: List[str]) -> tuple[bool, bool, int]:
        """
        Verify occurrence count and sample content.

        Args:
            errors: List to append error messages to

        Returns:
            Tuple of (count_match, sample_ok, occurrences_sampled)
        """
        # Parse occurrences from protobuf
        protobuf_occurrences = self._parse_protobuf_occurrences()
        expected_count = len(protobuf_occurrences)

        # Count occurrences in database
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM occurrences")
            actual_count = cursor.fetchone()[0]

        # Check count match
        count_match = expected_count == actual_count
        if not count_match:
            errors.append(
                f"Occurrence count mismatch: expected: {expected_count}, actual: {actual_count}"
            )

        # Sample verification
        sample_ok, occurrences_sampled = self._verify_occurrence_sample(protobuf_occurrences, errors)

        return count_match, sample_ok, occurrences_sampled

    def _parse_protobuf_occurrences(self) -> List:
        """
        Parse occurrences from SCIP protobuf file.

        Returns:
            List of occurrence dictionaries
        """
        with open(self.scip_file, "rb") as f:
            index = scip_pb2.Index()  # type: ignore[attr-defined]
            index.ParseFromString(f.read())

        # Collect all occurrences from documents
        protobuf_occurrences = []
        for doc in index.documents:
            for occ in doc.occurrences:
                protobuf_occurrences.append({
                    'symbol': occ.symbol,
                    'range': list(occ.range),
                    'role': occ.symbol_roles,
                })

        return protobuf_occurrences

    def _verify_occurrence_sample(self, protobuf_occurrences: List, errors: List[str]) -> tuple[bool, int]:
        """
        Verify random sample of occurrences match database.

        Args:
            protobuf_occurrences: List of occurrence dicts from protobuf
            errors: List to append error messages to

        Returns:
            Tuple of (sample_ok, occurrences_sampled)
        """
        expected_count = len(protobuf_occurrences)
        sample_size = min(MAX_OCCURRENCE_SAMPLE_SIZE, expected_count)
        occurrences_sampled = 0
        sample_ok = True

        if expected_count == 0 or sample_size == 0:
            return sample_ok, occurrences_sampled

        # Sample random occurrences
        sample_indices = random.sample(range(expected_count), sample_size)
        sampled_occurrences = [protobuf_occurrences[i] for i in sample_indices]

        # Verify each sampled occurrence exists in database
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            for occ in sampled_occurrences:
                symbol_name = occ['symbol']
                occ_range = occ['range']
                role = occ['role']

                # Parse range to get start line/char
                if len(occ_range) >= 2:
                    start_line = occ_range[0]
                    start_char = occ_range[1]

                    # Check if occurrence exists with matching symbol, location, and role
                    cursor.execute(
                        """
                        SELECT COUNT(*) FROM occurrences o
                        JOIN symbols s ON o.symbol_id = s.id
                        WHERE s.name = ? AND o.start_line = ? AND o.start_char = ? AND o.role = ?
                        """,
                        (symbol_name, start_line, start_char, role),
                    )
                    result = cursor.fetchone()[0]

                    if result == 0:
                        errors.append(
                            f"Occurrence not found in database: {symbol_name} at line {start_line}, char {start_char}"
                        )
                        sample_ok = False

                occurrences_sampled += 1

        return sample_ok, occurrences_sampled

    def _verify_documents(self, errors: List[str]) -> bool:
        """
        Verify all document paths and languages match.

        Args:
            errors: List to append error messages to

        Returns:
            True if all documents verified, False otherwise
        """
        # Parse documents from protobuf
        with open(self.scip_file, "rb") as f:
            index = scip_pb2.Index()  # type: ignore[attr-defined]
            index.ParseFromString(f.read())

        expected_docs = {doc.relative_path: doc.language or None for doc in index.documents}
        documents_ok = True

        # Verify documents in single database connection
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Get all documents from database
            cursor.execute("SELECT relative_path, language FROM documents")
            db_docs = {row[0]: row[1] for row in cursor.fetchall()}

            # Check expected documents exist with correct language
            for expected_path, expected_lang in expected_docs.items():
                if expected_path not in db_docs:
                    errors.append(f"Document path mismatch: expected {expected_path} not found in database")
                    documents_ok = False
                elif db_docs[expected_path] != expected_lang:
                    errors.append(
                        f"Document language mismatch for {expected_path}: "
                        f"expected {expected_lang}, actual {db_docs[expected_path]}"
                    )
                    documents_ok = False

            # Check for unexpected documents in database
            unexpected_paths = set(db_docs.keys()) - set(expected_docs.keys())
            for path in unexpected_paths:
                errors.append(f"Document path mismatch: unexpected {path} found in database")
                documents_ok = False

        return documents_ok

    def _verify_call_graph(self, errors: List[str]) -> tuple[bool, bool, int]:
        """
        Verify call graph FK integrity and sample edges.

        Args:
            errors: List to append error messages to

        Returns:
            Tuple of (fk_valid, sample_ok, edges_sampled)
        """
        fk_valid = True
        sample_ok = True
        edges_sampled = 0

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Check FK integrity - find call graph edges with invalid symbol references
            cursor.execute(
                """
                SELECT cg.id, cg.caller_symbol_id, cg.callee_symbol_id
                FROM call_graph cg
                LEFT JOIN symbols s1 ON cg.caller_symbol_id = s1.id
                LEFT JOIN symbols s2 ON cg.callee_symbol_id = s2.id
                WHERE s1.id IS NULL OR s2.id IS NULL
                """
            )
            invalid_fks = cursor.fetchall()

            if invalid_fks:
                fk_valid = False
                for edge_id, caller_id, callee_id in invalid_fks:
                    errors.append(
                        f"Call graph foreign key violation: edge {edge_id} references "
                        f"invalid symbol ID (caller: {caller_id}, callee: {callee_id})"
                    )

            # Sample verification - verify random sample of edges
            cursor.execute("SELECT COUNT(*) FROM call_graph")
            total_edges = cursor.fetchone()[0]

            if total_edges > 0:
                sample_size = min(MAX_CALL_GRAPH_SAMPLE_SIZE, total_edges)
                cursor.execute(
                    """
                    SELECT cg.caller_symbol_id, cg.callee_symbol_id, s1.name, s2.name
                    FROM call_graph cg
                    JOIN symbols s1 ON cg.caller_symbol_id = s1.id
                    JOIN symbols s2 ON cg.callee_symbol_id = s2.id
                    ORDER BY RANDOM()
                    LIMIT ?
                    """,
                    (sample_size,),
                )
                sampled_edges = cursor.fetchall()
                edges_sampled = len(sampled_edges)

                # Verify each sampled edge has valid symbol references
                for caller_id, callee_id, caller_name, callee_name in sampled_edges:
                    if not caller_name or not callee_name:
                        errors.append(
                            f"Call graph edge has invalid symbol reference: "
                            f"caller_id={caller_id}, callee_id={callee_id}"
                        )
                        sample_ok = False

        return fk_valid, sample_ok, edges_sampled

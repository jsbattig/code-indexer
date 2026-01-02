"""SCIP database ETL pipeline - transforms protobuf to SQLite database."""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from .enclosing_resolver import EnclosingSymbolResolver
from ..protobuf import scip_pb2

# SCIP symbol_roles bitmask constants
ROLE_DEFINITION = 1
ROLE_IMPORT = 2
ROLE_WRITE_ACCESS = 4
ROLE_READ_ACCESS = 8
ROLE_GENERATED = 16
ROLE_TEST = 32

# Sentinel value for end-of-file scope boundary
EOF_LINE_MARKER = 999999


class SCIPDatabaseBuilder:
    """Transforms SCIP protobuf data into SQLite database with pre-computed call graph."""

    def _determine_relationship_type(self, role: int) -> str:
        """
        Determine relationship type from SCIP symbol_roles bitmask.

        Priority order: ReadAccess > WriteAccess > Import > default
        (ReadAccess checked first because it often combines with Import bit)

        Args:
            role: Symbol roles bitmask

        Returns:
            Relationship type string: 'import', 'write', 'calls', or 'reference'
        """
        if role & ROLE_READ_ACCESS:
            return "calls"
        elif role & ROLE_WRITE_ACCESS:
            return "write"
        elif role & ROLE_IMPORT:
            return "import"
        else:
            return "reference"

    def build(self, scip_file: Path, db_path: Path) -> Dict[str, int]:
        """
        Main ETL entry point - transform SCIP protobuf to database.

        Args:
            scip_file: Path to .scip protobuf file
            db_path: Path to SQLite database

        Returns:
            Dictionary with counts: symbol_count, document_count, occurrence_count, call_graph_count
        """
        # Ensure parent directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create schema first, bypassing DatabaseManager.__init__ to avoid
        # its side effect of deleting existing databases.
        # Note: create_schema() only requires db_path attribute.
        from .schema import DatabaseManager

        temp_manager = DatabaseManager.__new__(DatabaseManager)
        temp_manager.db_path = db_path
        temp_manager.create_schema()

        conn = sqlite3.connect(db_path)

        try:
            # Set performance pragmas for bulk inserts
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("PRAGMA synchronous = OFF")
            conn.execute("PRAGMA journal_mode = MEMORY")

            # Parse protobuf
            symbols = self._parse_symbols(scip_file)
            documents, occurrences = self._parse_occurrences(scip_file)

            # Insert symbols
            symbol_map = self._insert_symbols(conn, symbols)

            # Collect and insert external symbols (not in protobuf symbol list)
            external_symbols = {}
            for occ in occurrences:
                symbol_name = occ["symbol_name"]
                if (
                    symbol_name not in symbol_map
                    and symbol_name not in external_symbols
                ):
                    # Create placeholder for external symbol (e.g., stdlib, external libraries)
                    display_name = (
                        symbol_name.split("/")[-1]
                        if "/" in symbol_name
                        else symbol_name
                    )
                    # Strip SCIP symbol suffixes for cleaner display
                    if display_name.endswith("#") or display_name.endswith("."):
                        display_name = display_name[:-1]
                    external_symbols[symbol_name] = {
                        "name": symbol_name,
                        "display_name": display_name,
                        "kind": None,
                        "signature": None,
                        "documentation": None,
                    }

            # Insert external symbols
            cursor = conn.cursor()
            for symbol_data in external_symbols.values():
                cursor.execute(
                    """
                    INSERT INTO symbols (name, display_name, kind, signature, documentation, package_id, enclosing_symbol_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol_data["name"],
                        symbol_data["display_name"],
                        symbol_data["kind"],
                        symbol_data["signature"],
                        symbol_data["documentation"],
                        None,
                        None,
                    ),
                )
                assert (
                    cursor.lastrowid is not None
                )  # lastrowid is always set after INSERT
                symbol_map[symbol_data["name"]] = cursor.lastrowid
            conn.commit()

            # Insert documents
            doc_map = self._insert_documents(conn, documents)

            # Insert occurrences (now all symbols exist in symbol_map)
            self._insert_occurrences(conn, occurrences, symbol_map, doc_map)

            # Build symbol_references for fast trace_call_chain
            self._build_symbol_references(conn, occurrences, symbol_map, doc_map)

            # Build call graph
            call_graph_count = self._build_call_graph(
                conn, occurrences, symbol_map, doc_map
            )

            # Create indexes for query performance
            self._create_indexes(conn)

            # Rebuild FTS5 index to sync with symbols table
            conn.execute("INSERT INTO symbols_fts(symbols_fts) VALUES('rebuild')")

            # Commit transaction before changing safety level
            conn.commit()

            # Restore safe pragmas
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA synchronous = FULL")

            # Get actual counts from database
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM symbols")
            symbol_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM documents")
            document_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM occurrences")
            occurrence_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM call_graph")
            call_graph_count = cursor.fetchone()[0]

            return {
                "symbol_count": symbol_count,
                "document_count": document_count,
                "occurrence_count": occurrence_count,
                "call_graph_count": call_graph_count,
            }
        finally:
            conn.close()

    def _create_indexes(self, conn: sqlite3.Connection) -> None:
        """Create database indexes for optimal query performance."""
        cursor = conn.cursor()

        # Symbols table indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name)")

        # Occurrences table indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_occurrences_symbol ON occurrences(symbol_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_occurrences_document ON occurrences(document_id)"
        )

        # Call graph indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_call_graph_caller ON call_graph(caller_symbol_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_call_graph_callee ON call_graph(callee_symbol_id)"
        )

        # Documents table indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(relative_path)"
        )

        # Symbol references indexes (for fast trace_call_chain)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_symbol_refs_from ON symbol_references(from_symbol_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_symbol_refs_to ON symbol_references(to_symbol_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_symbol_refs_type ON symbol_references(relationship_type)"
        )

        conn.commit()

    def _insert_symbols(
        self, conn: sqlite3.Connection, symbols: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Insert symbols into database and track generated IDs.

        Args:
            conn: SQLite database connection
            symbols: List of symbol dictionaries

        Returns:
            Dictionary mapping symbol name to database ID
        """
        cursor = conn.cursor()
        symbol_map = {}

        # Insert symbols one by one to capture lastrowid
        for symbol in symbols:
            cursor.execute(
                """
                INSERT INTO symbols (name, display_name, kind, signature, documentation, package_id, enclosing_symbol_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol["name"],
                    symbol.get("display_name"),
                    symbol.get("kind"),
                    symbol.get("signature"),
                    symbol.get("documentation"),
                    None,  # package_id
                    None,  # enclosing_symbol_id
                ),
            )
            assert cursor.lastrowid is not None  # lastrowid is always set after INSERT
            symbol_map[symbol["name"]] = cursor.lastrowid

        conn.commit()
        return symbol_map

    def _insert_documents(
        self, conn: sqlite3.Connection, documents: List[Dict[str, Any]]
    ) -> Dict[int, int]:
        """
        Insert documents into database.

        Args:
            conn: SQLite database connection
            documents: List of document dictionaries

        Returns:
            Dictionary mapping document index to database ID
        """
        cursor = conn.cursor()
        doc_map = {}

        for idx, doc in enumerate(documents):
            cursor.execute(
                """
                INSERT INTO documents (relative_path, language)
                VALUES (?, ?)
                """,
                (doc["relative_path"], doc.get("language")),
            )
            assert cursor.lastrowid is not None  # lastrowid is always set after INSERT
            doc_map[idx] = cursor.lastrowid

        conn.commit()
        return doc_map

    def _insert_occurrences(
        self,
        conn: sqlite3.Connection,
        occurrences: List[Dict[str, Any]],
        symbol_map: Dict[str, int],
        doc_map: Dict[int, int],
    ) -> None:
        """
        Insert occurrences into database with batch operations.

        Args:
            conn: SQLite database connection
            occurrences: List of occurrence dictionaries
            symbol_map: Mapping of symbol name to database ID
            doc_map: Mapping of document index to database ID
        """
        cursor = conn.cursor()
        batch_size = 1000

        for i in range(0, len(occurrences), batch_size):
            batch = occurrences[i : i + batch_size]

            batch_data = []
            for occ in batch:
                symbol_name = occ["symbol_name"]
                doc_index = occ["document_index"]

                # Skip if symbol or document not found
                if symbol_name not in symbol_map or doc_index not in doc_map:
                    continue

                batch_data.append(
                    (
                        symbol_map[symbol_name],
                        doc_map[doc_index],
                        occ["start_line"],
                        occ["start_char"],
                        occ["end_line"],
                        occ["end_char"],
                        occ["role"],
                        occ.get("enclosing_range_start_line"),
                        occ.get("enclosing_range_start_char"),
                        occ.get("enclosing_range_end_line"),
                        occ.get("enclosing_range_end_char"),
                    )
                )

            if batch_data:
                cursor.executemany(
                    """
                    INSERT INTO occurrences (
                        symbol_id, document_id, start_line, start_char, end_line, end_char,
                        role, enclosing_range_start_line, enclosing_range_start_char,
                        enclosing_range_end_line, enclosing_range_end_char
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch_data,
                )

        conn.commit()

    def _compute_enclosing_ranges(
        self, occurrences: List[Dict[str, Any]]
    ) -> Dict[tuple, tuple]:
        """
        Compute enclosing ranges for definitions missing protobuf enclosing_range.

        Algorithm:
        - Group occurrences by document
        - For each document, sort definitions by line number
        - Compute scope using heuristic:
          * Scope start = definition line
          * Scope end = (next definition line - 1) OR (end of file)

        Args:
            occurrences: List of occurrence dictionaries

        Returns:
            Dict mapping (doc_index, symbol_name) -> (start_line, end_line)
        """
        computed_ranges = {}

        # Group occurrences by document
        occurrences_by_doc: Dict[int, List[Dict[str, Any]]] = {}
        for occ in occurrences:
            doc_idx = occ["document_index"]
            if doc_idx not in occurrences_by_doc:
                occurrences_by_doc[doc_idx] = []
            occurrences_by_doc[doc_idx].append(occ)

        # Process each document
        for doc_idx, doc_occurrences in occurrences_by_doc.items():
            # Find all definitions in this document
            definitions = []
            for occ in doc_occurrences:
                if occ["role"] & ROLE_DEFINITION:
                    # Only compute ranges for definitions missing protobuf data
                    if occ.get("enclosing_range_start_line") is None:
                        definitions.append(
                            {
                                "symbol_name": occ["symbol_name"],
                                "def_line": occ["start_line"],
                            }
                        )

            # Sort definitions by line number
            definitions.sort(key=lambda d: d["def_line"])

            # Compute scope for each definition
            for i, defn in enumerate(definitions):
                start_line = defn["def_line"]

                # Scope extends to next definition - 1, or EOF
                if i + 1 < len(definitions):
                    end_line = definitions[i + 1]["def_line"] - 1
                else:
                    end_line = EOF_LINE_MARKER

                computed_ranges[(doc_idx, defn["symbol_name"])] = (start_line, end_line)

        return computed_ranges

    def _build_symbol_references(
        self,
        conn: sqlite3.Connection,
        occurrences: List[Dict[str, Any]],
        symbol_map: Dict[str, int],
        doc_map: Dict[int, int],
    ) -> int:
        """
        Build symbol_references table for fast trace_call_chain queries.

        Uses top-down algorithm matching hybrid get_dependencies:
        For each definition with enclosing range, create edges to all
        non-definition occurrences within that range.

        Args:
            conn: SQLite database connection
            occurrences: List of occurrence dictionaries
            symbol_map: Mapping of symbol name to database ID
            doc_map: Mapping of document index to database ID

        Returns:
            Count of symbol_references edges created
        """
        cursor = conn.cursor()

        # Build occurrence ID map
        cursor.execute(
            "SELECT symbol_id, document_id, start_line, start_char, id FROM occurrences"
        )
        occurrence_id_map = {}
        for row in cursor.fetchall():
            symbol_id, doc_id, start_line, start_char, occ_id = row
            occurrence_id_map[(symbol_id, doc_id, start_line, start_char)] = occ_id

        # Group occurrences by document for efficient processing
        occurrences_by_doc: Dict[int, List[Dict[str, Any]]] = {}
        for occ in occurrences:
            doc_idx = occ["document_index"]
            if doc_idx not in occurrences_by_doc:
                occurrences_by_doc[doc_idx] = []
            occurrences_by_doc[doc_idx].append(occ)

        # Compute enclosing ranges for definitions missing protobuf data
        computed_ranges = self._compute_enclosing_ranges(occurrences)

        # Collect all edges to batch insert
        edges = []

        # Process each document
        for doc_idx, doc_occurrences in occurrences_by_doc.items():
            # Find all definitions with enclosing ranges in this document
            definitions_with_ranges = []
            all_definitions = []
            for occ in doc_occurrences:
                if occ["role"] & ROLE_DEFINITION:
                    from_symbol_name = occ["symbol_name"]
                    if from_symbol_name in symbol_map:
                        defn_info = {
                            "symbol_id": symbol_map[from_symbol_name],
                            "symbol_name": from_symbol_name,
                            "def_line": occ["start_line"],
                        }
                        all_definitions.append(defn_info)

                        # Check if this definition has an enclosing range (protobuf or computed)
                        if occ.get("enclosing_range_start_line") is not None:
                            # Use protobuf enclosing_range
                            defn_info["start_line"] = occ["enclosing_range_start_line"]
                            defn_info["end_line"] = occ.get(
                                "enclosing_range_end_line",
                                occ["enclosing_range_start_line"],
                            )
                            definitions_with_ranges.append(defn_info)
                        elif (doc_idx, from_symbol_name) in computed_ranges:
                            # Use computed enclosing_range
                            start_line, end_line = computed_ranges[
                                (doc_idx, from_symbol_name)
                            ]
                            defn_info["start_line"] = start_line
                            defn_info["end_line"] = end_line
                            definitions_with_ranges.append(defn_info)

            # Sort definitions by line number for proximity heuristic
            all_definitions.sort(key=lambda d: d["def_line"])

            # For each definition with enclosing range, find all references within that range
            for defn in definitions_with_ranges:
                from_symbol_id = defn["symbol_id"]
                scope_start = defn["start_line"]
                scope_end = defn["end_line"]

                for occ in doc_occurrences:
                    # Skip definitions
                    if occ["role"] & ROLE_DEFINITION:
                        continue

                    # Skip if reference is to the same symbol (self-reference)
                    if occ["symbol_name"] == defn["symbol_name"]:
                        continue

                    # Skip local variables
                    if occ["symbol_name"].startswith("local "):
                        continue

                    # Check if occurrence is within enclosing range
                    occ_line = occ["start_line"]
                    if occ_line < scope_start or occ_line > scope_end:
                        continue

                    # Get referenced symbol ID
                    to_symbol_name = occ["symbol_name"]
                    if to_symbol_name not in symbol_map:
                        continue

                    to_symbol_id = symbol_map[to_symbol_name]

                    # Get occurrence ID for this reference
                    doc_id = doc_map.get(doc_idx)
                    if doc_id is not None:
                        occ_key = (
                            to_symbol_id,
                            doc_id,
                            occ["start_line"],
                            occ["start_char"],
                        )
                        occurrence_id = occurrence_id_map.get(occ_key)
                    else:
                        occurrence_id = None

                    # Skip if no occurrence ID found
                    if occurrence_id is None:
                        continue

                    # Determine relationship type from role bitmask
                    relationship_type = self._determine_relationship_type(occ["role"])

                    # Add edge to batch
                    edges.append(
                        (
                            from_symbol_id,
                            to_symbol_id,
                            relationship_type,
                            occurrence_id,
                        )
                    )

            # Also process references using proximity heuristic for ALL definitions
            # (This handles the 82.5% of references not covered by enclosing ranges)
            references_covered_by_ranges = set()
            for defn in definitions_with_ranges:
                scope_start = defn["start_line"]
                scope_end = defn["end_line"]
                for occ in doc_occurrences:
                    if not (occ["role"] & ROLE_DEFINITION):
                        occ_line = occ["start_line"]
                        if scope_start <= occ_line <= scope_end:
                            # Track which references are already covered by enclosing ranges
                            references_covered_by_ranges.add(
                                (
                                    occ["symbol_name"],
                                    occ["start_line"],
                                    occ["start_char"],
                                )
                            )

            # For each reference NOT covered by enclosing ranges, use proximity heuristic
            for occ in doc_occurrences:
                # Skip definitions
                if occ["role"] & ROLE_DEFINITION:
                    continue

                # Skip local variables
                if occ["symbol_name"].startswith("local "):
                    continue

                # Check if already covered by enclosing range
                occ_key = (occ["symbol_name"], occ["start_line"], occ["start_char"])  # type: ignore[assignment]
                if occ_key in references_covered_by_ranges:
                    continue

                # Use proximity heuristic - find nearest definition before this reference
                occ_line = occ["start_line"]
                from_symbol_id = None
                for defn in all_definitions:
                    if defn["def_line"] <= occ_line:
                        from_symbol_id = defn["symbol_id"]
                        from_symbol_name = defn["symbol_name"]
                    else:
                        break

                if from_symbol_id is None:
                    # Module-level reference, skip
                    continue

                # Skip self-references
                if occ["symbol_name"] == from_symbol_name:
                    continue

                # Get referenced symbol ID
                to_symbol_name = occ["symbol_name"]
                if to_symbol_name not in symbol_map:
                    continue

                to_symbol_id = symbol_map[to_symbol_name]

                # Get occurrence ID for this reference
                doc_id = doc_map.get(doc_idx)
                if doc_id is not None:
                    occ_key_db = (
                        to_symbol_id,
                        doc_id,
                        occ["start_line"],
                        occ["start_char"],
                    )
                    occurrence_id = occurrence_id_map.get(occ_key_db)
                else:
                    occurrence_id = None

                # Skip if no occurrence ID found
                if occurrence_id is None:
                    continue

                # Determine relationship type from role bitmask
                relationship_type = self._determine_relationship_type(occ["role"])

                # Add edge to batch
                edges.append(
                    (
                        from_symbol_id,
                        to_symbol_id,
                        relationship_type,
                        occurrence_id,
                    )
                )

        # Batch insert all edges
        if edges:
            cursor.executemany(
                """
                INSERT INTO symbol_references (
                    from_symbol_id, to_symbol_id, relationship_type, occurrence_id
                )
                VALUES (?, ?, ?, ?)
                """,
                edges,
            )

        conn.commit()
        return len(edges)

    def _add_interface_to_impl_edges(self, conn: sqlite3.Connection) -> int:
        """
        Add synthetic interface→implementation edges to call_graph (Bug #2 fix).

        Detects interface→implementation relationships by matching:
        - Interface: kind='AbstractMethod'
        - Implementation: kind='Method', follows naming pattern (e.g., UserServiceImpl implements UserService)

        Pattern detection:
        1. Find all AbstractMethod symbols (interfaces)
        2. For each interface method, find matching implementation by:
           - Matching method signature (same name after '#')
           - Implementation in /impl/ subpackage with 'Impl' suffix pattern

        Args:
            conn: SQLite database connection

        Returns:
            Count of synthetic edges created
        """
        cursor = conn.cursor()

        # Get all AbstractMethod symbols (interface methods)
        cursor.execute(
            """
            SELECT id, name, display_name
            FROM symbols
            WHERE kind = 'AbstractMethod'
        """
        )
        interface_methods = cursor.fetchall()

        edges = []

        for interface_id, interface_name, interface_display_name in interface_methods:
            # Extract method signature (part after '#')
            if "#" not in interface_name:
                continue

            method_sig = interface_name.split("#", 1)[1]

            # Extract interface class name and package
            # Pattern: "prefix com/example/service/UserService#findById()."
            # Extract: "com/example/service/UserService"
            prefix_end = interface_name.rfind(" ")
            if prefix_end == -1:
                # No space found, try parsing without prefix
                class_part = interface_name.split("#")[0]
            else:
                class_part = interface_name[prefix_end + 1 :].split("#")[0]

            # Extract class name (last part after /)
            if "/" in class_part:
                interface_class = class_part.split("/")[-1]
            else:
                interface_class = class_part

            # Look for implementation following pattern:
            # 1. Same package + /impl/ subpackage
            # 2. Class name = InterfaceNameImpl
            # 3. Same method signature after '#'

            # Search for implementation with /impl/ pattern and Impl suffix
            cursor.execute(
                """
                SELECT id, name, display_name
                FROM symbols
                WHERE kind = 'Method'
                  AND name LIKE ?
                  AND name LIKE ?
            """,
                (f"%/impl/%Impl#{method_sig}", f"%{interface_class}Impl#%"),
            )

            impl_matches = cursor.fetchall()

            for impl_id, impl_name, impl_display_name in impl_matches:
                # Create synthetic edge from interface to implementation
                # Use NULL for occurrence_id since this is synthetic
                # Use 'calls' as relationship type
                edges.append(
                    (
                        interface_id,
                        impl_id,
                        None,  # occurrence_id (synthetic edge)
                        "calls",
                        interface_display_name,
                        impl_display_name,
                    )
                )

        # Batch insert synthetic edges
        if edges:
            cursor.executemany(
                """
                INSERT INTO call_graph (
                    caller_symbol_id, callee_symbol_id, occurrence_id, relationship,
                    caller_display_name, callee_display_name
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                edges,
            )
            conn.commit()

        return len(edges)

    def _build_call_graph(
        self,
        conn: sqlite3.Connection,
        occurrences: List[Dict[str, Any]],
        symbol_map: Dict[str, int],
        doc_map: Dict[int, int],
    ) -> int:
        """
        Build pre-computed call graph edges.

        For each reference occurrence, determine the enclosing (caller) symbol
        using hybrid resolution strategy, then create call graph edge.

        Args:
            conn: SQLite database connection
            occurrences: List of occurrence dictionaries
            symbol_map: Mapping of symbol name to database ID
            doc_map: Mapping of document index to database ID

        Returns:
            Count of call graph edges created
        """
        # Pre-fetch all symbol display names to avoid N+1 queries
        cursor = conn.cursor()
        cursor.execute("SELECT id, display_name FROM symbols")
        display_name_map = {row[0]: row[1] for row in cursor.fetchall()}

        # Build occurrence ID map (track which occurrence each edge came from)
        cursor.execute(
            "SELECT symbol_id, document_id, start_line, start_char, id FROM occurrences"
        )
        occurrence_id_map = {}
        for row in cursor.fetchall():
            symbol_id, doc_id, start_line, start_char, occ_id = row
            occurrence_id_map[(symbol_id, doc_id, start_line, start_char)] = occ_id

        # Initialize resolver
        resolver = EnclosingSymbolResolver()
        resolver.build_enclosing_range_map(occurrences, symbol_map)

        # Collect all edges to batch insert
        edges = []

        # Process reference occurrences (all non-definition occurrences)
        for occ in occurrences:
            # Skip definitions, process all references (imports, writes, calls)
            # FIXED: Previous code required role & 8 (ReadAccess), which excluded imports/writes
            # and caused call_graph to be empty when SCIP data had only import/write roles
            if occ["role"] & ROLE_DEFINITION:
                continue

            # Resolve enclosing symbol (caller)
            caller_id = resolver.resolve(occ)
            if caller_id is None:
                # Module-level reference, skip
                continue

            # Get callee symbol ID
            callee_name = occ["symbol_name"]
            if callee_name not in symbol_map:
                continue

            callee_id = symbol_map[callee_name]

            # Get display names from pre-fetched map
            caller_display_name = display_name_map.get(caller_id)
            callee_display_name = display_name_map.get(callee_id)

            # Get occurrence ID for this reference (map doc_index to doc_id)
            doc_index = occ["document_index"]
            doc_id = doc_map.get(doc_index)
            if doc_id is not None:
                occ_key = (callee_id, doc_id, occ["start_line"], occ["start_char"])
                occurrence_id = occurrence_id_map.get(occ_key)
            else:
                occurrence_id = None

            # Determine relationship type from role bitmask
            relationship = self._determine_relationship_type(occ["role"])

            # Add edge to batch
            edges.append(
                (
                    caller_id,
                    callee_id,
                    occurrence_id,
                    relationship,
                    caller_display_name,
                    callee_display_name,
                )
            )

        # Batch insert all edges
        if edges:
            cursor.executemany(
                """
                INSERT INTO call_graph (
                    caller_symbol_id, callee_symbol_id, occurrence_id, relationship,
                    caller_display_name, callee_display_name
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                edges,
            )

        conn.commit()

        # Add synthetic interface→implementation edges (Bug #2 fix)
        interface_impl_edges = self._add_interface_to_impl_edges(conn)

        return len(edges) + interface_impl_edges

    def _parse_occurrences(
        self, scip_file: Path
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Parse occurrences and documents from SCIP protobuf file.

        Args:
            scip_file: Path to .scip protobuf file

        Returns:
            Tuple of (documents, occurrences) where:
                documents: List of document dicts with relative_path, language
                occurrences: List of occurrence dicts with location, role, symbol_name
        """
        with open(scip_file, "rb") as f:
            index = scip_pb2.Index()  # type: ignore[attr-defined]
            index.ParseFromString(f.read())

        documents = []
        occurrences = []

        for doc in index.documents:
            # Extract document metadata
            doc_dict = {
                "relative_path": doc.relative_path,
                "language": doc.language or None,
            }
            documents.append(doc_dict)
            doc_index = len(documents) - 1

            # Extract occurrences from this document
            for occ in doc.occurrences:
                occ_dict = self._extract_occurrence_fields(occ, doc_index)
                occurrences.append(occ_dict)

        return documents, occurrences

    def _extract_occurrence_fields(
        self, occ: scip_pb2.Occurrence, doc_index: int  # type: ignore[name-defined]
    ) -> Dict[str, Any]:
        """
        Extract fields from Occurrence protobuf message.

        SCIP range format can be:
        - [line, char] - single position (end = start)
        - [line, start_char, end_char] - single-line range
        - [start_line, start_char, end_line, end_char] - full range

        Args:
            occ: SCIP Occurrence message
            doc_index: Index of containing document

        Returns:
            Dictionary with occurrence fields
        """
        # Parse range (can be 2, 3, or 4 elements)
        if len(occ.range) == 2:
            start_line = occ.range[0]
            start_char = occ.range[1]
            end_line = start_line
            end_char = start_char
        elif len(occ.range) == 3:
            # Single-line range with different start and end chars
            start_line = occ.range[0]
            start_char = occ.range[1]
            end_line = start_line
            end_char = occ.range[2]
        elif len(occ.range) >= 4:
            start_line = occ.range[0]
            start_char = occ.range[1]
            end_line = occ.range[2]
            end_char = occ.range[3]
        else:
            # Handle edge case of empty or 1-element range
            start_line = occ.range[0] if len(occ.range) > 0 else 0
            start_char = 0
            end_line = start_line
            end_char = 0

        # Parse enclosing_range if present
        enclosing_range_start_line = None
        enclosing_range_start_char = None
        enclosing_range_end_line = None
        enclosing_range_end_char = None

        if len(occ.enclosing_range) >= 4:
            enclosing_range_start_line = occ.enclosing_range[0]
            enclosing_range_start_char = occ.enclosing_range[1]
            enclosing_range_end_line = occ.enclosing_range[2]
            enclosing_range_end_char = occ.enclosing_range[3]

        return {
            "symbol_name": occ.symbol,
            "document_index": doc_index,
            "start_line": start_line,
            "start_char": start_char,
            "end_line": end_line,
            "end_char": end_char,
            "role": occ.symbol_roles,
            "enclosing_range_start_line": enclosing_range_start_line,
            "enclosing_range_start_char": enclosing_range_start_char,
            "enclosing_range_end_line": enclosing_range_end_line,
            "enclosing_range_end_char": enclosing_range_end_char,
        }

    def _parse_symbols(self, scip_file: Path) -> List[Dict[str, Any]]:
        """
        Parse symbols from SCIP protobuf file.

        Args:
            scip_file: Path to .scip protobuf file

        Returns:
            List of symbol dictionaries with keys:
                - name: Symbol identifier
                - display_name: Human-readable name
                - kind: Symbol kind (Class, Method, etc.)
                - signature: Function/class signature
                - documentation: Symbol documentation
        """
        with open(scip_file, "rb") as f:
            index = scip_pb2.Index()  # type: ignore[attr-defined]
            index.ParseFromString(f.read())

        symbols = []

        # Extract external symbols
        for symbol_info in index.external_symbols:
            symbol_dict = self._extract_symbol_fields(symbol_info)
            symbols.append(symbol_dict)

        # Extract symbols from documents
        for doc in index.documents:
            for symbol_info in doc.symbols:
                symbol_dict = self._extract_symbol_fields(symbol_info)
                symbols.append(symbol_dict)

        return symbols

    def _extract_symbol_fields(self, symbol_info: scip_pb2.SymbolInformation) -> Dict[str, Any]:  # type: ignore[name-defined]
        """
        Extract fields from SymbolInformation protobuf message.

        Args:
            symbol_info: SCIP SymbolInformation message

        Returns:
            Dictionary with symbol fields
        """
        # Map SCIP kind enum to string
        kind_name = scip_pb2.SymbolInformation.Kind.Name(symbol_info.kind) if symbol_info.kind else None  # type: ignore[attr-defined]

        # Extract signature from signature_documentation
        signature = None
        if symbol_info.HasField("signature_documentation"):
            signature = symbol_info.signature_documentation.text or None

        # Extract first documentation string (SCIP allows multiple)
        documentation = None
        if symbol_info.documentation:
            documentation = (
                symbol_info.documentation[0]
                if len(symbol_info.documentation) > 0
                else None
            )

        return {
            "name": symbol_info.symbol or "",
            "display_name": symbol_info.display_name or None,
            "kind": kind_name,
            "signature": signature,
            "documentation": documentation,
        }

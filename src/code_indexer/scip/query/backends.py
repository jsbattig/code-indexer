"""SCIP query backend abstraction layer."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

try:
    from pysqlite3 import dbapi2 as sqlite3
except ImportError:
    import sqlite3

from .primitives import QueryResult


@dataclass
class ImpactResult:
    """Result of impact analysis query."""

    file_path: str
    symbol_count: int
    symbols: List[str]


@dataclass
class CallChain:
    """Result of call chain tracing query."""

    path: List[str]  # Symbol names in execution order
    length: int  # Number of hops in chain
    has_cycle: bool  # True if path contains cycle


class SCIPBackend(ABC):
    """Abstract base class for SCIP query backends."""

    @abstractmethod
    def find_definition(self, symbol: str, exact: bool = False) -> List[QueryResult]:
        """
        Find definition locations for a symbol.

        Args:
            symbol: Symbol name to search for
            exact: If True, match exact symbol name; if False, match substring

        Returns:
            List of QueryResult objects with definition locations
        """
        pass

    @abstractmethod
    def find_references(
        self, symbol: str, limit: int = 100, exact: bool = False
    ) -> List[QueryResult]:
        """
        Find all references to a symbol.

        Args:
            symbol: Symbol name to search for
            limit: Maximum number of results to return
            exact: If True, match exact symbol name; if False, match substring

        Returns:
            List of QueryResult objects with reference locations
        """
        pass

    @abstractmethod
    def get_dependencies(
        self, symbol: str, depth: int = 1, exact: bool = False
    ) -> List[QueryResult]:
        """
        Get symbols that this symbol depends on.

        Args:
            symbol: Symbol name to analyze
            depth: Depth of transitive dependencies (1 = direct only)
            exact: If True, match exact symbol name; if False, match substring

        Returns:
            List of QueryResult objects with dependency information
        """
        pass

    @abstractmethod
    def get_dependents(
        self, symbol: str, depth: int = 1, exact: bool = False
    ) -> List[QueryResult]:
        """
        Get symbols that depend on this symbol.

        Args:
            symbol: Symbol name to analyze
            depth: Depth of transitive dependents (1 = direct only)
            exact: If True, match exact symbol name; if False, match substring

        Returns:
            List of QueryResult objects with dependent information
        """
        pass

    @abstractmethod
    def analyze_impact(self, symbol: str, depth: int = 3) -> List[ImpactResult]:
        """
        Analyze impact of changing symbol (transitive dependents grouped by file).

        Args:
            symbol: Symbol name to analyze
            depth: Maximum dependency depth (1-10, default 3)

        Returns:
            List of ImpactResult objects with file_path, symbol_count, and symbols
        """
        pass

    @abstractmethod
    def trace_call_chain(
        self, from_symbol: str, to_symbol: str, max_depth: int = 5, limit: int = 100
    ) -> List[CallChain]:
        """
        Trace all call chains from entry point to target function.

        Args:
            from_symbol: Entry point symbol name
            to_symbol: Target function symbol name
            max_depth: Maximum path length (1-10, default 5)
            limit: Maximum number of paths to return (default 100)

        Returns:
            List of CallChain objects with path, length, and has_cycle
        """
        pass


class DatabaseBackend(SCIPBackend):
    """SQLite database backend for SCIP queries."""

    def __init__(
        self, db_path: Path, project_root: str = "", scip_file: Optional[Path] = None
    ):
        """
        Initialize database backend.

        Args:
            db_path: Path to .scip.db database file
            project_root: Project root path for QueryResult objects
            scip_file: Optional path to .scip protobuf file for hybrid mode (ALL symbol references)
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.project_root = project_root
        self.scip_file = scip_file

        # Run migration to ensure indexes exist (Story #609)
        self._ensure_migration_complete()

    def _ensure_migration_complete(self) -> None:
        """
        Ensure SCIP database indexes exist, with fast-path version check.

        Version tracking prevents redundant index creation checks on every query.
        Migration is idempotent, so safe to run multiple times if version tracking fails.

        Performance:
        - Fast path (version >= 2): <1ms (version check only)
        - Migration path (version < 2): ~100-500ms (create 5 indexes)
        """
        from ..database.migration import (
            ensure_indexes_created,
            get_scip_db_version,
            update_scip_db_version,
        )

        # Determine config path (Story #609)
        # Convert project_root to Path for local use only
        project_root_path = Path(self.project_root) if self.project_root else Path.cwd()
        config_path = project_root_path / ".code-indexer" / "config.json"

        # Fast path: Skip migration if version >= 2
        current_version = get_scip_db_version(config_path)
        if current_version >= 2:
            return  # Already migrated

        # Migration path: Create indexes and update version
        ensure_indexes_created(self.conn)
        update_scip_db_version(config_path, 2)

    def find_definition(self, symbol: str, exact: bool = False) -> List[QueryResult]:
        """Find definition locations using database queries."""
        from ..database.queries import find_definition as db_find_definition

        db_results = db_find_definition(self.conn, symbol, exact=exact)

        # Convert database results to QueryResult objects
        results = []
        for row in db_results:
            # Filter out parameter definitions (noise)
            if "().(" in row["symbol_name"]:
                continue

            result = QueryResult(
                symbol=row["symbol_name"],
                project=self.project_root,
                file_path=row["file_path"],
                line=row["line"],
                column=row["column"],
                kind="definition",
            )
            results.append(result)

        # For simple name queries (without "#" or "("), if we found class definitions,
        # filter out method/attribute definitions to reduce noise
        if "#" not in symbol and "(" not in symbol:
            has_class_definitions = any(r.symbol.endswith("#") for r in results)
            if has_class_definitions:
                results = [r for r in results if r.symbol.endswith("#")]

        return results

    def find_references(
        self, symbol: str, limit: int = 100, exact: bool = False
    ) -> List[QueryResult]:
        """Find references using database queries."""
        from ..database.queries import find_references as db_find_references

        # Database backend supports both exact and substring matching
        db_results = db_find_references(self.conn, symbol, limit=limit, exact=exact)

        # Convert database results to QueryResult objects
        results = []
        for row in db_results:
            result = QueryResult(
                symbol=row["symbol_name"],
                project=self.project_root,
                file_path=row["file_path"],
                line=row["line"],
                column=row["column"],
                kind="reference",
            )
            results.append(result)

        return results

    def get_dependencies(
        self, symbol: str, depth: int = 1, exact: bool = False
    ) -> List[QueryResult]:
        """Get dependencies using database queries."""
        from ..database.queries import get_dependencies as db_get_dependencies

        # Find definition to get symbol_id
        definitions = self.find_definition(symbol, exact=exact)
        if not definitions:
            return []

        # Get symbol_id from database
        cursor = self.conn.cursor()
        results = []

        for defn in definitions:
            cursor.execute("SELECT id FROM symbols WHERE name = ?", (defn.symbol,))
            row = cursor.fetchone()
            if row is None:
                continue

            symbol_id = row[0]

            # SQL CTE handles class→method expansion via target_and_nested
            db_results = db_get_dependencies(
                self.conn, symbol_id, depth=depth, scip_file=self.scip_file
            )

            # Convert database results to QueryResult objects
            seen_symbols = set()  # Deduplicate across all definitions
            for db_row in db_results:
                # Deduplicate by symbol name
                if db_row["symbol_name"] in seen_symbols:
                    continue
                seen_symbols.add(db_row["symbol_name"])

                result = QueryResult(
                    symbol=db_row["symbol_name"],
                    project=self.project_root,
                    file_path=db_row["file_path"],
                    line=db_row["line"],
                    column=db_row["column"],
                    kind="dependency",
                    relationship=db_row.get("relationship"),
                    depth=db_row.get("depth"),
                )
                results.append(result)

        return results

    def get_dependents(
        self, symbol: str, depth: int = 1, exact: bool = False
    ) -> List[QueryResult]:
        """Get dependents using database queries."""
        from ..database.queries import get_dependents as db_get_dependents

        # Find definition to get symbol_id
        definitions = self.find_definition(symbol, exact=exact)
        if not definitions:
            return []

        # Get symbol_id from database
        cursor = self.conn.cursor()
        results = []

        for defn in definitions:
            cursor.execute("SELECT id FROM symbols WHERE name = ?", (defn.symbol,))
            row = cursor.fetchone()
            if row is None:
                continue

            symbol_id = row[0]

            # Query database for dependents
            db_results = db_get_dependents(
                self.conn, symbol_id, depth=depth, scip_file=self.scip_file
            )

            # Convert database results to QueryResult objects
            for db_row in db_results:
                result = QueryResult(
                    symbol=db_row["symbol_name"],
                    project=self.project_root,
                    file_path=db_row["file_path"],
                    line=db_row["line"],
                    column=db_row["column"],
                    kind="dependent",
                    relationship=db_row.get("relationship"),
                    depth=db_row.get("depth"),
                )
                results.append(result)

        return results

    def analyze_impact(self, symbol: str, depth: int = 3) -> List[ImpactResult]:
        """Analyze impact of changing symbol using database queries."""
        from ..database.queries import analyze_impact as db_analyze_impact

        # Validate depth parameter
        if depth < 1 or depth > 10:
            raise ValueError(f"Depth must be between 1 and 10, got {depth}")

        # Find symbol definitions (same pattern as get_dependencies)
        definitions = self.find_definition(symbol, exact=True)
        if not definitions:
            return []

        # Get symbol IDs
        cursor = self.conn.cursor()
        all_impact_results = []

        for defn in definitions:
            cursor.execute("SELECT id FROM symbols WHERE name = ?", (defn.symbol,))
            row = cursor.fetchone()
            if row is None:
                continue

            symbol_id = row[0]
            db_results = db_analyze_impact(
                self.conn, symbol_id, depth=depth, scip_file=self.scip_file
            )

            # Convert to ImpactResult objects
            for db_row in db_results:
                all_impact_results.append(
                    ImpactResult(
                        file_path=db_row["file_path"],
                        symbol_count=db_row["symbol_count"],
                        symbols=db_row["symbols"],
                    )
                )

        # Merge results from multiple definitions
        # Group by file_path and deduplicate symbols
        merged: Dict[str, ImpactResult] = {}
        for result in all_impact_results:
            if result.file_path in merged:
                # Extend symbols list
                merged[result.file_path].symbols.extend(result.symbols)
                # Deduplicate symbols using set
                merged[result.file_path].symbols = list(
                    set(merged[result.file_path].symbols)
                )
                # Recalculate symbol_count after deduplication
                merged[result.file_path].symbol_count = len(
                    merged[result.file_path].symbols
                )
            else:
                # Ensure initial result also has deduplicated symbols
                result.symbols = list(set(result.symbols))
                result.symbol_count = len(result.symbols)
                merged[result.file_path] = result

        # Sort by symbol_count DESC
        return sorted(merged.values(), key=lambda r: r.symbol_count, reverse=True)

    def _expand_class_to_methods(self, symbol_id: int) -> List[int]:
        """
        Expand CLASS/INTERFACE symbol to all nested methods.

        If symbol is a CLASS or INTERFACE, returns list of all nested method IDs.
        Otherwise returns [symbol_id].

        This is needed because call_graph contains method-level entries, not class-level.
        When user searches from/to a CLASS name, we need to expand to all methods.

        Args:
            symbol_id: Symbol ID to potentially expand

        Returns:
            List of symbol IDs (either [symbol_id] or list of nested method IDs)
        """
        cursor = self.conn.cursor()

        # Check if symbol is CLASS or INTERFACE
        cursor.execute("SELECT kind, name FROM symbols WHERE id = ?", (symbol_id,))
        row = cursor.fetchone()

        if not row:
            return [symbol_id]

        kind, symbol_name = row

        # Check if this is a class/interface
        # kind may be NULL in some SCIP indexes (e.g., Python)
        # Fall back to symbol naming: classes end with "#" (e.g., "Foo#")
        is_class = (kind in ("Class", "Interface")) or (
            kind is None and symbol_name.endswith("#")
        )

        if not is_class:
            # Not a class/interface, return as-is
            return [symbol_id]

        # Expand to all nested methods
        # SCIP uses hierarchical naming: com/example/Foo# for class, com/example/Foo#method(). for methods
        # Pattern: symbol_name ends with '#', methods are symbol_name + method_name
        # Note: kind field may be NULL in some SCIP indexes (e.g., Python), so we filter by
        # symbol naming convention: methods end with "()" or "()."
        cursor.execute(
            """
            SELECT id FROM symbols
            WHERE name LIKE ? || '%'
            AND name != ?
            AND (name LIKE '%()' OR name LIKE '%().')
        """,
            (symbol_name, symbol_name),
        )

        method_ids = [r[0] for r in cursor.fetchall()]

        # Return method IDs only, never include the class ID itself
        # If no methods found, return empty list (not [symbol_id])
        return method_ids

    def _expand_method_to_scopes(self, symbol_id: int) -> List[int]:
        """
        Expand METHOD symbol to include all internal scopes (parameters, locals).

        Call graph stores relationships at a very granular level - from PARAMETERS
        and LOCAL VARIABLES inside methods, not from the methods themselves.
        For example, the method CustomChain#chat(). (ID 381) doesn't appear as a
        caller in call_graph, but CustomChain#chat().(attempt) (ID 385) does.

        This function expands a method ID to include all its internal scopes so
        call chain analysis can find the actual call relationships.

        Args:
            symbol_id: Symbol ID to potentially expand

        Returns:
            List of symbol IDs (method itself + all internal scopes)
        """
        cursor = self.conn.cursor()

        # Get symbol name
        cursor.execute("SELECT name FROM symbols WHERE id = ?", (symbol_id,))
        row = cursor.fetchone()

        if not row:
            return [symbol_id]

        symbol_name = row[0]

        # Check if this is a method (ends with ().)
        if not symbol_name.endswith("()."):
            return [symbol_id]

        # Find all internal scopes: symbol_name + (scope_name)
        # Example: CustomChain#chat(). expands to:
        #   - CustomChain#chat().(self)
        #   - CustomChain#chat().(query)
        #   - CustomChain#chat().(attempt)
        cursor.execute(
            """
            SELECT id FROM symbols
            WHERE name LIKE ? || '%'
        """,
            (symbol_name,),
        )

        scope_ids = [r[0] for r in cursor.fetchall()]

        # Return method ID + all internal scope IDs
        return scope_ids if scope_ids else [symbol_id]

    def trace_call_chain(
        self, from_symbol: str, to_symbol: str, max_depth: int = 5, limit: int = 100
    ) -> List[CallChain]:
        """Trace call chains from entry point to target using database."""
        from ..database.queries import trace_call_chain_v2_batched

        # Find symbol IDs for from/to symbols (use fuzzy matching for user queries)
        from_defs = self.find_definition(from_symbol, exact=False)
        to_defs = self.find_definition(to_symbol, exact=False)

        if not from_defs or not to_defs:
            return []

        cursor = self.conn.cursor()

        # Phase 1: Collect ALL from_ids (no queries yet)
        all_from_ids = set()
        for from_def in from_defs:
            cursor.execute("SELECT id FROM symbols WHERE name = ?", (from_def.symbol,))
            from_row = cursor.fetchone()
            if not from_row:
                continue
            from_id = from_row[0]

            # Expand CLASS/INTERFACE to methods (call_graph only has method entries)
            from_ids = self._expand_class_to_methods(from_id)

            # Skip if class has no methods (empty expansion means no call_graph entries exist)
            if not from_ids:
                continue

            # Further expand methods to internal scopes (parameters, locals) where actual calls happen
            expanded_from_ids = []
            for fid in from_ids:
                expanded_from_ids.extend(self._expand_method_to_scopes(fid))
            from_ids = expanded_from_ids if expanded_from_ids else from_ids

            # Collect all IDs (no queries)
            all_from_ids.update(from_ids)

        # Phase 2: Collect ALL to_ids (no queries yet)
        all_to_ids = set()
        for to_def in to_defs:
            cursor.execute("SELECT id FROM symbols WHERE name = ?", (to_def.symbol,))
            to_row = cursor.fetchone()
            if not to_row:
                continue
            to_id = to_row[0]

            # Expand CLASS/INTERFACE to methods
            to_ids = self._expand_class_to_methods(to_id)

            # Skip if class has no methods (empty expansion means no call_graph entries exist)
            if not to_ids:
                continue

            # Further expand methods to internal scopes
            expanded_to_ids = []
            for tid in to_ids:
                expanded_to_ids.extend(self._expand_method_to_scopes(tid))
            to_ids = expanded_to_ids if expanded_to_ids else to_ids

            # Collect all IDs (no queries)
            all_to_ids.update(to_ids)

        # Remove self-loops from IDs (prevent trivial zero-length paths)
        all_from_ids = all_from_ids - all_to_ids.intersection(all_from_ids)

        # Early return if no IDs collected
        if not all_from_ids or not all_to_ids:
            return []

        # Phase 3: ONE batched query with all IDs (Story #610)
        db_results, error_msg = trace_call_chain_v2_batched(
            self.conn,
            from_symbol_ids=list(all_from_ids),
            to_symbol_ids=list(all_to_ids),
            max_depth=max_depth,
            limit=limit,
        )

        if error_msg:
            # Log timeout/error but continue with partial results
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"trace_call_chain batched query: {error_msg}")

        # Convert to CallChain objects
        all_chains = []
        for db_row in db_results:
            all_chains.append(
                CallChain(
                    path=db_row["path"],
                    length=db_row["length"],
                    has_cycle=db_row["has_cycle"],
                )
            )

        # Deduplicate and sort
        seen = set()
        unique_chains = []
        for chain in all_chains:
            path_key = tuple(chain.path)
            if path_key not in seen:
                seen.add(path_key)
                unique_chains.append(chain)

        return sorted(unique_chains, key=lambda c: c.length)[:limit]

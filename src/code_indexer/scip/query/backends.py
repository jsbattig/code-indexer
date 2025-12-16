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
    length: int      # Number of hops in chain
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

    def __init__(self, db_path: Path, project_root: str = "", scip_file: Optional[Path] = None):
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

        # For simple name queries, if we found class definitions,
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

            # Query database for dependencies
            db_results = db_get_dependencies(self.conn, symbol_id, depth=depth, scip_file=self.scip_file)

            # Convert database results to QueryResult objects
            for db_row in db_results:
                result = QueryResult(
                    symbol=db_row["symbol_name"],
                    project=self.project_root,
                    file_path=db_row["file_path"],
                    line=db_row["line"],
                    column=db_row["column"],
                    kind="dependency",
                    relationship=db_row.get("relationship"),
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
            db_results = db_get_dependents(self.conn, symbol_id, depth=depth, scip_file=self.scip_file)

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
            db_results = db_analyze_impact(self.conn, symbol_id, depth=depth, scip_file=self.scip_file)

            # Convert to ImpactResult objects
            for db_row in db_results:
                all_impact_results.append(ImpactResult(
                    file_path=db_row['file_path'],
                    symbol_count=db_row['symbol_count'],
                    symbols=db_row['symbols']
                ))

        # Merge results from multiple definitions
        # Group by file_path and deduplicate symbols
        merged: Dict[str, ImpactResult] = {}
        for result in all_impact_results:
            if result.file_path in merged:
                # Extend symbols list
                merged[result.file_path].symbols.extend(result.symbols)
                # Deduplicate symbols using set
                merged[result.file_path].symbols = list(set(merged[result.file_path].symbols))
                # Recalculate symbol_count after deduplication
                merged[result.file_path].symbol_count = len(merged[result.file_path].symbols)
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

        if kind not in ('Class', 'Interface'):
            # Not a class/interface, return as-is
            return [symbol_id]

        # Expand to all nested methods
        # SCIP uses hierarchical naming: com/example/Foo# for class, com/example/Foo#method(). for methods
        # Pattern: symbol_name ends with '#', methods are symbol_name + method_name
        cursor.execute("""
            SELECT id FROM symbols
            WHERE name LIKE ? || '%'
            AND name != ?
            AND kind IN ('Method', 'AbstractMethod', 'Function', 'Constructor')
        """, (symbol_name, symbol_name))

        method_ids = [r[0] for r in cursor.fetchall()]

        # If no methods found, return class ID as fallback
        return method_ids if method_ids else [symbol_id]

    def trace_call_chain(
        self, from_symbol: str, to_symbol: str, max_depth: int = 5, limit: int = 100
    ) -> List[CallChain]:
        """Trace call chains from entry point to target using database."""
        from ..database.queries import trace_call_chain as db_trace_call_chain

        # Find symbol IDs for from/to symbols (use fuzzy matching for user queries)
        from_defs = self.find_definition(from_symbol, exact=False)
        to_defs = self.find_definition(to_symbol, exact=False)

        if not from_defs or not to_defs:
            return []

        cursor = self.conn.cursor()
        all_chains = []

        for from_def in from_defs:
            cursor.execute("SELECT id FROM symbols WHERE name = ?", (from_def.symbol,))
            from_row = cursor.fetchone()
            if not from_row:
                continue
            from_id = from_row[0]

            # Expand CLASS/INTERFACE to methods (call_graph only has method entries)
            from_ids = self._expand_class_to_methods(from_id)

            # Defensive check: expansion should never return empty, but guard against it
            if not from_ids:
                from_ids = [from_id]

            for to_def in to_defs:
                cursor.execute("SELECT id FROM symbols WHERE name = ?", (to_def.symbol,))
                to_row = cursor.fetchone()
                if not to_row:
                    continue
                to_id = to_row[0]

                # Expand CLASS/INTERFACE to methods
                to_ids = self._expand_class_to_methods(to_id)

                # Defensive check: expansion should never return empty, but guard against it
                if not to_ids:
                    to_ids = [to_id]

                # Query call chains for all from/to method combinations
                for from_method_id in from_ids:
                    for to_method_id in to_ids:
                        db_results = db_trace_call_chain(
                            self.conn, from_method_id, to_method_id, max_depth=max_depth, limit=limit, scip_file=self.scip_file
                        )

                        # Convert to CallChain objects
                        for db_row in db_results:
                            all_chains.append(CallChain(
                                path=db_row['path'],
                                length=db_row['length'],
                                has_cycle=db_row['has_cycle']
                            ))

        # Deduplicate and sort
        seen = set()
        unique_chains = []
        for chain in all_chains:
            path_key = tuple(chain.path)
            if path_key not in seen:
                seen.add(path_key)
                unique_chains.append(chain)

        return sorted(unique_chains, key=lambda c: c.length)[:limit]

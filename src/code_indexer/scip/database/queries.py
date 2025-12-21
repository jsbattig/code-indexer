"""SCIP database query operations for symbol lookup and reference search."""

try:
    from pysqlite3 import dbapi2 as sqlite3
except ImportError:
    import sqlite3

import logging
import signal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from .builder import ROLE_DEFINITION, ROLE_IMPORT, ROLE_WRITE_ACCESS, ROLE_READ_ACCESS

logger = logging.getLogger(__name__)


class QueryTimeoutError(Exception):
    """Raised when a query exceeds the timeout limit."""

    pass


def _timeout_handler(signum: int, frame: Any) -> None:
    """Signal handler for query timeout."""
    raise QueryTimeoutError("Query exceeded timeout limit")


def _determine_relationship(role: int) -> str:
    """Map SCIP role flags to relationship type."""
    if role & ROLE_IMPORT:
        return "import"
    elif role & ROLE_WRITE_ACCESS:
        return "write"
    elif role & ROLE_READ_ACCESS:
        return "call"
    return "reference"


def find_definition(
    conn: sqlite3.Connection, symbol_name: str, exact: bool = False
) -> List[Dict[str, Any]]:
    """
    Find definition locations for a symbol using FTS5-optimized SQL query.

    Uses FTS5 symbols_fts table for fast symbol name lookup, eliminating
    full table scans and achieving <5ms performance on production datasets.

    Args:
        conn: SQLite database connection
        symbol_name: Symbol name to search for (e.g., "TestClass", "authenticate")
        exact: If True, match exact symbol name; if False, match substring (FTS5 MATCH)

    Returns:
        List of dictionaries with keys:
            - symbol_name: Full SCIP symbol identifier
            - file_path: Relative file path
            - line: Line number (0-indexed)
            - column: Column number (0-indexed)
            - kind: Symbol kind (Class, Method, etc.)
            - role: Role bitmask
    """
    cursor = conn.cursor()

    # Sanitize input for FTS5 (escape double quotes)
    safe_symbol_name = symbol_name.replace('"', '""')

    if exact:
        # Check if this is a full SCIP symbol path (starts with language prefix)
        # Full SCIP symbols start with: "python ", "java ", "typescript ", etc.
        is_full_scip_symbol = any(
            symbol_name.startswith(prefix)
            for prefix in [
                "python ",
                "java ",
                "typescript ",
                "go ",
                "rust ",
                "cpp ",
                "csharp ",
                "ruby ",
            ]
        )

        if is_full_scip_symbol:
            # Use direct equality match for full SCIP symbols
            query = """
                SELECT
                    s.name as symbol_name,
                    d.relative_path as file_path,
                    o.start_line as line,
                    o.start_char as column,
                    s.kind as kind,
                    o.role as role
                FROM symbols s
                JOIN occurrences o ON o.symbol_id = s.id
                JOIN documents d ON o.document_id = d.id
                WHERE s.name = ?
                    AND (o.role & 1) = 1
                ORDER BY d.relative_path, o.start_line
            """
            cursor.execute(query, (symbol_name,))
        else:
            # Use FTS5 for fast symbol name lookup combined with LIKE for exact suffix matching
            # FTS5 MATCH query returns matching symbol IDs instantly
            # LIKE filters to exact symbol definitions based on format:
            #   - Class: /ClassName# (exact)
            #   - Method: /ClassName#method(). or /ClassName#method() (allow both formats)
            #   - Attribute: /ClassName#attr.
            query = """
                SELECT
                    s.name as symbol_name,
                    d.relative_path as file_path,
                    o.start_line as line,
                    o.start_char as column,
                    s.kind as kind,
                    o.role as role
                FROM symbols_fts fts
                JOIN symbols s ON fts.rowid = s.id
                JOIN occurrences o ON o.symbol_id = s.id
                JOIN documents d ON o.document_id = d.id
                WHERE fts.name MATCH ?
                    AND s.name LIKE ?
                    AND (o.role & 1) = 1
                ORDER BY d.relative_path, o.start_line
            """

            # Determine SCIP format based on symbol_name
            if "#" in symbol_name:
                # Method or attribute query: ClassName#method or ClassName#attr
                # SCIP format: .../ClassName#method(). or .../ClassName#attr.
                # Handle both ClassName#method and ClassName#method() input formats
                if symbol_name.endswith("()"):
                    # User provided ClassName#method() format
                    base = symbol_name[:-2]  # Remove ()
                else:
                    # User provided ClassName#method format
                    base = symbol_name

                # FTS5 pattern for fast filtering
                fts_pattern = f'"/{safe_symbol_name}"'
                # LIKE pattern matches method/attribute format
                # Match both /ClassName#method(). and /ClassName#method().X patterns
                like_pattern = f"%/{base}()%"
            else:
                # Class query: ClassName
                # SCIP format: .../ClassName# (exact, no method/attribute suffix)
                # FTS5 MATCH pattern for fast filtering
                fts_pattern = f'"/{safe_symbol_name}#"'
                # LIKE pattern for exact suffix match (class definition only)
                like_pattern = f"%/{symbol_name}#"

            cursor.execute(query, (fts_pattern, like_pattern))
    else:
        # Fall back to LIKE for substring matching (acceptable for pattern queries)
        # FTS5 MATCH doesn't support true substring matching (requires token boundaries)
        # LIKE is slower but still acceptable for fuzzy queries (not critical path)
        query = """
            SELECT
                s.name as symbol_name,
                d.relative_path as file_path,
                o.start_line as line,
                o.start_char as column,
                s.kind as kind,
                o.role as role
            FROM symbols s
            JOIN occurrences o ON o.symbol_id = s.id
            JOIN documents d ON o.document_id = d.id
            WHERE s.name LIKE ?
                AND (o.role & 1) = 1
            ORDER BY d.relative_path, o.start_line
        """
        # LIKE pattern for substring match
        cursor.execute(query, (f"%{symbol_name}%",))

    # Fetch all results and convert to dictionaries
    results = []
    for row in cursor.fetchall():
        results.append(
            {
                "symbol_name": row[0],
                "file_path": row[1],
                "line": row[2],
                "column": row[3],
                "kind": row[4],
                "role": row[5],
            }
        )

    return results


def trace_call_chain_v2_batched(
    conn: sqlite3.Connection,
    from_symbol_ids: List[int],
    to_symbol_ids: List[int],
    max_depth: int = 3,
    limit: int = 100,
    timeout_seconds: int = 30,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Trace call chains using bidirectional BFS on symbol_references table.

    This is the batched version of trace_call_chain_v2 that accepts LISTS of
    from/to symbol IDs and finds chains from ANY source to ANY target in a
    single query. This solves the O(n×m) query problem in Story #610.

    Performance improvement: O(1) queries instead of O(n×m) queries.
    Uses symbol_references table (METHOD->METHOD relationships) instead of
    call_graph table (PARAMETER->METHOD relationships) for accurate tracing.

    Args:
        conn: SQLite database connection
        from_symbol_ids: List of entry point symbol IDs (classes or methods)
        to_symbol_ids: List of target function symbol IDs (classes or methods)
        max_depth: Maximum path length (1-10, capped at 3)
        limit: Maximum number of paths to return
        timeout_seconds: Maximum execution time in seconds (default 30)

    Returns:
        Tuple of (results, error_message):
            - results: List of dicts with keys:
                - path: List of symbol names in execution order
                - length: Number of hops
                - has_cycle: Boolean indicating cycle presence
            - error_message: Error message if timeout occurred, None otherwise
    """
    # Cap max_depth at 3 to prevent runaway queries (Story #609)
    MAX_DEPTH_CAP = 3
    if max_depth > MAX_DEPTH_CAP:
        logger.warning(
            f"Requested max_depth {max_depth} exceeds cap of {MAX_DEPTH_CAP}. "
            f"Capping at {MAX_DEPTH_CAP} to prevent performance degradation."
        )
        max_depth = MAX_DEPTH_CAP

    if max_depth < 1 or max_depth > 10:
        raise ValueError(f"Max depth must be between 1 and 10, got {max_depth}")

    if not from_symbol_ids or not to_symbol_ids:
        return [], None

    cursor = conn.cursor()

    # Create temp tables for source/target IDs (Story #610)
    # Using temp tables is more efficient than long IN clauses for large ID lists
    cursor.execute(
        "CREATE TEMP TABLE IF NOT EXISTS batch_from_ids (id INTEGER PRIMARY KEY)"
    )
    cursor.execute(
        "CREATE TEMP TABLE IF NOT EXISTS batch_to_ids (id INTEGER PRIMARY KEY)"
    )
    cursor.execute("DELETE FROM batch_from_ids")
    cursor.execute("DELETE FROM batch_to_ids")

    # Insert IDs into temp tables
    cursor.executemany(
        "INSERT OR IGNORE INTO batch_from_ids VALUES (?)",
        [(id,) for id in from_symbol_ids],
    )
    cursor.executemany(
        "INSERT OR IGNORE INTO batch_to_ids VALUES (?)", [(id,) for id in to_symbol_ids]
    )

    # Modified query using temp tables instead of single source/target IDs
    query = """
        WITH RECURSIVE
        -- Phase 0a: Expand source symbols (class -> class + methods) from temp table
        source_symbols(symbol_id) AS (
            SELECT id FROM batch_from_ids
            UNION
            SELECT s.id
            FROM symbols s, symbols s_src
            JOIN batch_from_ids bf ON s_src.id = bf.id
            WHERE s_src.name LIKE '%#'
              AND s_src.name NOT LIKE '%()%'
              AND s.name LIKE s_src.name || '%'
              AND s.name LIKE '%()%'
        ),

        -- Phase 0b: Expand target symbols (class -> class + methods) from temp table
        target_symbols(symbol_id) AS (
            SELECT id FROM batch_to_ids
            UNION
            SELECT s.id
            FROM symbols s, symbols s_tgt
            JOIN batch_to_ids bt ON s_tgt.id = bt.id
            WHERE s_tgt.name LIKE '%#'
              AND s_tgt.name NOT LIKE '%()%'
              AND s.name LIKE s_tgt.name || '%'
              AND s.name LIKE '%()%'
        ),

        -- Phase 1: Backward reachability from ALL target symbols
        backward_reachable(symbol_id, depth) AS (
            SELECT symbol_id, 0 FROM target_symbols
            UNION
            SELECT DISTINCT sr.from_symbol_id, br.depth + 1
            FROM backward_reachable br
            JOIN symbol_references sr ON sr.to_symbol_id = br.symbol_id
            WHERE br.depth < ?
        ),

        -- Phase 2: Forward BFS from ALL source symbols with pruning
        forward_paths(symbol_id, path_ids, path_symbols, depth, has_cycle) AS (
            -- Base: all source symbols
            SELECT
                ss.symbol_id,
                CAST(ss.symbol_id AS TEXT),
                (SELECT name FROM symbols WHERE id = ss.symbol_id),
                0,
                0
            FROM source_symbols ss

            UNION

            -- Recursive: explore only backward-reachable symbols
            SELECT
                sr.to_symbol_id,
                fp.path_ids || ',' || sr.to_symbol_id,
                fp.path_symbols || '|||' || s.name,
                fp.depth + 1,
                CASE
                    WHEN instr(',' || fp.path_ids || ',', ',' || CAST(sr.to_symbol_id AS TEXT) || ',') > 0
                    THEN 1 ELSE 0
                END
            FROM forward_paths fp
            JOIN symbol_references sr ON fp.symbol_id = sr.from_symbol_id
            JOIN symbols s ON sr.to_symbol_id = s.id
            WHERE fp.depth < ?
              AND fp.has_cycle = 0
              -- CRITICAL PRUNING: Only explore nodes that can reach target
              AND sr.to_symbol_id IN (SELECT symbol_id FROM backward_reachable)
        )

        -- Phase 3: Extract paths that reached ANY target symbol
        SELECT DISTINCT path_symbols, path_ids, depth, has_cycle
        FROM forward_paths fp
        WHERE fp.symbol_id IN (SELECT symbol_id FROM target_symbols)
        ORDER BY depth
    """

    # Build parameter list
    params = [max_depth, max_depth]

    # Conditionally add LIMIT clause (limit=0 means unlimited)
    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    # Set timeout alarm (Story #609 AC#6)
    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout_seconds)

    try:
        cursor.execute(query, tuple(params))

        results = []
        for row in cursor.fetchall():
            path_symbols_str, path_ids_str, depth, has_cycle = row
            path_symbols = path_symbols_str.split("|||")

            results.append(
                {
                    "path": path_symbols,
                    "length": depth,  # Number of hops/edges, not nodes
                    "has_cycle": bool(has_cycle),
                }
            )

        # Cancel alarm - query completed successfully
        signal.alarm(0)
        return results, None

    except QueryTimeoutError:
        # Timeout occurred - return empty results with error message
        error_msg = (
            f"Query exceeded {timeout_seconds}-second timeout. "
            "Try reducing depth or narrowing search."
        )
        logger.warning(f"trace_call_chain_v2_batched timeout: {error_msg}")
        return [], error_msg

    finally:
        # Restore original signal handler
        signal.signal(signal.SIGALRM, old_handler)
        signal.alarm(0)  # Ensure alarm is cancelled
        # Clean up temp tables
        cursor.execute("DELETE FROM batch_from_ids")
        cursor.execute("DELETE FROM batch_to_ids")


def trace_call_chain_v2(
    conn: sqlite3.Connection,
    from_symbol_id: int,
    to_symbol_id: int,
    max_depth: int = 5,
    limit: int = 100,
    timeout_seconds: int = 30,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Trace call chains using bidirectional BFS on symbol_references table.

    Uses bidirectional BFS optimization:
    1. Compute backward-reachable set from target (small, ~100-500 symbols)
    2. Forward BFS from source, pruned to only backward-reachable nodes
    3. Extract paths that reached target

    Performance: <3s for complex queries (17x faster than O(n*m) approach).
    Uses symbol_references table (METHOD->METHOD relationships) instead of
    call_graph table (PARAMETER->METHOD relationships) for accurate tracing.

    Args:
        conn: SQLite database connection
        from_symbol_id: Entry point symbol ID (class or method)
        to_symbol_id: Target function symbol ID (class or method)
        max_depth: Maximum path length (1-10)
        limit: Maximum number of paths to return
        timeout_seconds: Maximum execution time in seconds (default 30)

    Returns:
        Tuple of (results, error_message):
            - results: List of dicts with keys:
                - path: List of symbol names in execution order
                - length: Number of hops
                - has_cycle: Boolean indicating cycle presence
            - error_message: Error message if timeout occurred, None otherwise

    Note:
        If from_symbol_id or to_symbol_id refers to a class (symbol ending with #),
        the function automatically expands to include all methods of that class.
        This ensures call chains are found even when class IDs are provided.
    """
    # Cap max_depth at 3 to prevent runaway queries (Story #609)
    MAX_DEPTH_CAP = 3
    if max_depth > MAX_DEPTH_CAP:
        logger.warning(
            f"Requested max_depth {max_depth} exceeds cap of {MAX_DEPTH_CAP}. "
            f"Capping at {MAX_DEPTH_CAP} to prevent performance degradation."
        )
        max_depth = MAX_DEPTH_CAP

    if max_depth < 1 or max_depth > 10:
        raise ValueError(f"Max depth must be between 1 and 10, got {max_depth}")

    cursor = conn.cursor()

    # Class expansion using CTEs: If from_symbol_id/to_symbol_id is a class,
    # materialize ALL method IDs in a CTE, then use those as starting/ending points.
    #
    # This approach:
    # 1. Checks if symbol is a class (ends with #, no parentheses)
    # 2. If yes, creates a CTE with class ID + all method IDs
    # 3. Uses that CTE as the source/target set for BFS
    #
    # Performance: Materializes method IDs once in CTE, then BFS operates on that set.
    # Much faster than N*M nested loops or EXISTS subqueries.

    query = """
        WITH RECURSIVE
        -- Phase 0a: Expand source symbol (class -> class + methods)
        source_symbols(symbol_id) AS (
            SELECT ? AS symbol_id  -- Always include the source ID itself
            UNION
            SELECT s.id
            FROM symbols s, symbols s_src
            WHERE s_src.id = ?
              -- Check if source is a class (ends with #, no parentheses)
              AND s_src.name LIKE '%#'
              AND s_src.name NOT LIKE '%()%'
              -- If it's a class, find all methods (name starts with class name, contains ())
              AND s.name LIKE s_src.name || '%'
              AND s.name LIKE '%()%'
        ),

        -- Phase 0b: Expand target symbol (class -> class + methods)
        target_symbols(symbol_id) AS (
            SELECT ? AS symbol_id  -- Always include the target ID itself
            UNION
            SELECT s.id
            FROM symbols s, symbols s_tgt
            WHERE s_tgt.id = ?
              -- Check if target is a class (ends with #, no parentheses)
              AND s_tgt.name LIKE '%#'
              AND s_tgt.name NOT LIKE '%()%'
              -- If it's a class, find all methods (name starts with class name, contains ())
              AND s.name LIKE s_tgt.name || '%'
              AND s.name LIKE '%()%'
        ),

        -- Phase 1: Backward reachability from ALL target symbols
        backward_reachable(symbol_id, depth) AS (
            SELECT symbol_id, 0 FROM target_symbols
            UNION
            SELECT DISTINCT sr.from_symbol_id, br.depth + 1
            FROM backward_reachable br
            JOIN symbol_references sr ON sr.to_symbol_id = br.symbol_id
            WHERE br.depth < ?
        ),

        -- Phase 2: Forward BFS from ALL source symbols with pruning
        forward_paths(symbol_id, path_ids, path_symbols, depth, has_cycle) AS (
            -- Base: all source symbols
            SELECT
                ss.symbol_id,
                CAST(ss.symbol_id AS TEXT),
                (SELECT name FROM symbols WHERE id = ss.symbol_id),
                0,
                0
            FROM source_symbols ss

            UNION

            -- Recursive: explore only backward-reachable symbols
            SELECT
                sr.to_symbol_id,
                fp.path_ids || ',' || sr.to_symbol_id,
                fp.path_symbols || '|||' || s.name,
                fp.depth + 1,
                CASE
                    WHEN instr(',' || fp.path_ids || ',', ',' || CAST(sr.to_symbol_id AS TEXT) || ',') > 0
                    THEN 1 ELSE 0
                END
            FROM forward_paths fp
            JOIN symbol_references sr ON fp.symbol_id = sr.from_symbol_id
            JOIN symbols s ON sr.to_symbol_id = s.id
            WHERE fp.depth < ?
              AND fp.has_cycle = 0
              -- CRITICAL PRUNING: Only explore nodes that can reach target
              AND sr.to_symbol_id IN (SELECT symbol_id FROM backward_reachable)
        )

        -- Phase 3: Extract paths that reached ANY target symbol
        SELECT DISTINCT path_symbols, path_ids, depth, has_cycle
        FROM forward_paths fp
        WHERE fp.symbol_id IN (SELECT symbol_id FROM target_symbols)
        ORDER BY depth
    """

    # Build parameter list
    params = [
        from_symbol_id,
        from_symbol_id,
        to_symbol_id,
        to_symbol_id,
        max_depth,
        max_depth,
    ]

    # Conditionally add LIMIT clause (limit=0 means unlimited)
    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    # Set timeout alarm (Story #609 AC#6)
    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout_seconds)

    try:
        cursor.execute(query, tuple(params))

        results = []
        for row in cursor.fetchall():
            path_symbols_str, path_ids_str, depth, has_cycle = row
            path_symbols = path_symbols_str.split("|||")

            results.append(
                {
                    "path": path_symbols,
                    "length": depth,  # Number of hops/edges, not nodes
                    "has_cycle": bool(has_cycle),
                }
            )

        # Cancel alarm - query completed successfully
        signal.alarm(0)
        return results, None

    except QueryTimeoutError:
        # Timeout occurred - return empty results with error message
        error_msg = (
            f"Query exceeded {timeout_seconds}-second timeout. "
            "Try reducing depth or narrowing search."
        )
        logger.warning(f"trace_call_chain_v2 timeout: {error_msg}")
        return [], error_msg

    finally:
        # Restore original signal handler
        signal.signal(signal.SIGALRM, old_handler)
        signal.alarm(0)  # Ensure alarm is cancelled


def trace_call_chain(
    conn: sqlite3.Connection,
    from_symbol_id: int,
    to_symbol_id: int,
    max_depth: int = 5,
    limit: int = 100,
    scip_file: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Trace all call chains from entry point to target function.

    Auto-detects if call_graph table exists and uses fast recursive CTE
    (trace_call_chain_v2, 0.5ms-5ms) if available. Falls back to BFS hybrid
    approach (slow, 10-100s) for legacy databases without call_graph.

    Performance improvement: 10000x faster with call_graph table.

    Args:
        conn: SQLite database connection
        from_symbol_id: Entry point symbol ID
        to_symbol_id: Target function symbol ID
        max_depth: Maximum path length (1-10)
        limit: Maximum number of paths to return
        scip_file: Optional path to .scip file for hybrid mode (legacy fallback only)

    Returns:
        List of dicts with keys:
            - path: List of symbol names in execution order
            - length: Number of hops
            - has_cycle: Boolean indicating cycle presence
    """
    if max_depth < 1 or max_depth > 10:
        raise ValueError(f"Max depth must be between 1 and 10, got {max_depth}")

    # Auto-detect call_graph table (fast path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='call_graph'
    """
    )
    has_call_graph_table = cursor.fetchone() is not None

    # Check if table exists AND has data
    has_call_graph = False
    if has_call_graph_table:
        cursor.execute("SELECT COUNT(*) FROM call_graph LIMIT 1")
        count = cursor.fetchone()[0]
        has_call_graph = count > 0

    if has_call_graph:
        # Fast path: Use bidirectional BFS on call_graph
        results, error_msg = trace_call_chain_v2(
            conn, from_symbol_id, to_symbol_id, max_depth, limit
        )
        if error_msg:
            logger.warning(f"trace_call_chain timeout: {error_msg}")
        return results

    # Legacy fallback: BFS hybrid approach (slow, for databases without symbol_references)
    from collections import deque

    cursor = conn.cursor()

    # Get starting and target symbol names for matching
    cursor.execute("SELECT name FROM symbols WHERE id = ?", (from_symbol_id,))
    from_row = cursor.fetchone()
    if not from_row:
        return []
    from_symbol_name = from_row[0]

    cursor.execute("SELECT name FROM symbols WHERE id = ?", (to_symbol_id,))
    to_row = cursor.fetchone()
    if not to_row:
        return []
    to_symbol_name = to_row[0]

    # Simplify starting symbol name
    from_simple_name = (
        from_symbol_name.split("/")[-1].rstrip("#").rstrip(".").rstrip("()")
    )
    to_simple_name = to_symbol_name.split("/")[-1].rstrip("#").rstrip(".").rstrip("()")

    # BFS with hybrid queries
    # Queue contains: (current_symbol_id, path_so_far, visited_set)
    queue = deque([(from_symbol_id, [from_simple_name], {from_symbol_id})])
    chains: List[Dict[str, Any]] = []
    MAX_CHAINS = limit
    MAX_NODES_EXPLORED = 3000  # Prevent BFS explosion, keep <2s performance
    nodes_explored = 0

    while queue and len(chains) < MAX_CHAINS and nodes_explored < MAX_NODES_EXPLORED:
        current_id, path, visited = queue.popleft()
        nodes_explored += 1

        # Check depth
        if len(path) > max_depth:
            continue

        # Get dependencies using HYBRID (ALL symbols)
        deps = get_dependencies(conn, current_id, depth=1, scip_file=scip_file)

        for dep in deps:
            # Early termination if we have enough chains
            if len(chains) >= MAX_CHAINS:
                break

            # Find dep symbol ID
            cursor.execute(
                "SELECT id, name, kind FROM symbols WHERE name = ?",
                (dep["symbol_name"],),
            )
            dep_row = cursor.fetchone()
            if not dep_row:
                continue
            dep_id, dep_name, dep_kind = dep_row

            # Skip parameters and locals (noise that explodes BFS)
            if dep_kind in ("Parameter", "Local") or dep_name.startswith("local "):
                continue

            # Extract simplified symbol name (last part after /)
            dep_simple_name = (
                dep_name.split("/")[-1].rstrip("#").rstrip(".").rstrip("()")
            )

            # Skip if already in path (simple name check to avoid cycles)
            if dep_simple_name in path:
                continue

            # Check if reached target (fuzzy match on simple name)
            if dep_simple_name == to_simple_name or to_simple_name in dep_simple_name:
                # Found a chain!
                full_path = path + [dep_simple_name]
                chains.append(
                    {
                        "path": full_path,
                        "length": len(full_path) - 1,  # Number of hops/edges, not nodes
                        "has_cycle": False,
                    }
                )
                continue

            # Cycle detection
            if dep_id in visited:
                continue

            # Add to queue
            new_visited = visited | {dep_id}
            queue.append((dep_id, path + [dep_simple_name], new_visited))

    # Sort by length
    return sorted(chains, key=lambda c: c["length"])


def find_references(
    conn: sqlite3.Connection,
    symbol_name: str,
    limit: int = 100,
    role_filter: Optional[int] = None,
    exact: bool = True,
) -> List[Dict[str, Any]]:
    """
    Find all references to a symbol using FTS5-optimized SQL query.

    Uses FTS5 symbols_fts table for fast symbol name lookup, eliminating
    full table scans and achieving <10ms performance on production datasets.

    Args:
        conn: SQLite database connection
        symbol_name: Symbol name to search for
        limit: Maximum number of results to return (default 100)
        role_filter: Optional role bitmask to filter by (e.g., ROLE_READ_ACCESS=8)
        exact: If True (default), match exact symbol name; if False, match substring (LIKE)

    Returns:
        List of dictionaries with keys:
            - symbol_name: Full SCIP symbol identifier
            - file_path: Relative file path
            - line: Line number (0-indexed)
            - column: Column number (0-indexed)
            - kind: Symbol kind (Class, Method, etc.)
            - role: Role bitmask
    """
    cursor = conn.cursor()

    # Build WHERE clause and parameter list
    where_clauses = [f"(o.role & {ROLE_DEFINITION}) = 0"]  # Exclude definitions

    # Add role filter if specified (parameterized to prevent SQL injection)
    params: List[Any] = []
    if role_filter is not None:
        where_clauses.append("(o.role & ?) != 0")
        params.append(role_filter)

    if exact:
        # Sanitize input for FTS5 (escape double quotes)
        safe_symbol_name = symbol_name.replace('"', '""')

        # Use FTS5 for fast symbol name lookup
        # FTS5 MATCH query returns matching symbol IDs instantly
        # Then join to occurrences using indexed symbol_id column
        fts_pattern = (
            f'"{safe_symbol_name}#" OR "{safe_symbol_name}()" OR "{safe_symbol_name}."'
        )

        where_clause = " AND ".join(where_clauses)

        query = f"""
            SELECT
                s.name as symbol_name,
                d.relative_path as file_path,
                o.start_line as line,
                o.start_char as column,
                s.kind as kind,
                o.role as role
            FROM symbols_fts fts
            JOIN symbols s ON fts.rowid = s.id
            JOIN occurrences o ON o.symbol_id = s.id
            JOIN documents d ON o.document_id = d.id
            WHERE fts.name MATCH ?
                AND {where_clause}
            ORDER BY d.relative_path, o.start_line
        """

        # Prepend FTS pattern to params
        params = [fts_pattern] + params

        # Conditionally add LIMIT clause (limit=0 means unlimited)
        if limit > 0:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, tuple(params))
    else:
        # Fall back to LIKE for substring matching
        # FTS5 MATCH doesn't support true substring matching (requires token boundaries)
        # LIKE is slower but acceptable for fuzzy queries (not critical path)
        where_clause = " AND ".join(where_clauses)

        query = f"""
            SELECT
                s.name as symbol_name,
                d.relative_path as file_path,
                o.start_line as line,
                o.start_char as column,
                s.kind as kind,
                o.role as role
            FROM symbols s
            JOIN occurrences o ON o.symbol_id = s.id
            JOIN documents d ON o.document_id = d.id
            WHERE s.name LIKE ?
                AND {where_clause}
            ORDER BY d.relative_path, o.start_line
        """

        # Prepend LIKE pattern to params
        params = [f"%{symbol_name}%"] + params

        # Conditionally add LIMIT clause (limit=0 means unlimited)
        if limit > 0:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, tuple(params))

    # Fetch results and convert to dictionaries
    results = []
    for row in cursor.fetchall():
        results.append(
            {
                "symbol_name": row[0],
                "file_path": row[1],
                "line": row[2],
                "column": row[3],
                "kind": row[4],
                "role": row[5],
            }
        )

    return results


def _get_dependencies_hybrid(
    conn: sqlite3.Connection,
    symbol_id: int,
    depth: int,
    scip_file: "Path",
) -> List[Dict[str, Any]]:
    """Find ALL symbols that the target symbol depends on using symbol_references table.

    Uses symbol_references table with SQL recursive CTE to find ALL dependencies
    regardless of scope (imports, fields, constructor parameters, method calls) in a single query.

    The scip_file parameter is kept for API compatibility but not used (all data is in database).
    """
    # Validate depth to prevent stack overflow
    if depth < 1 or depth > 10:
        raise ValueError(f"Depth must be between 1 and 10, got {depth}")

    cursor = conn.cursor()

    # SQL recursive CTE for transitive dependencies lookup
    # Replaces Python recursion with single database query (256x faster)
    query = """
        WITH target_and_nested AS (
            SELECT ? AS symbol_id
            UNION
            SELECT DISTINCT s_nested.id
            FROM symbols s_nested, symbols s_target
            WHERE s_target.id = ?
            AND s_nested.id != ?
            AND (
                -- If target ends with delimiter (# or .), match anything starting with target
                (s_target.name LIKE '%#' OR s_target.name LIKE '%.') AND s_nested.name LIKE s_target.name || '%'
                OR
                -- If target has no delimiter, require delimiter after target to prevent false positives
                (s_target.name NOT LIKE '%#' AND s_target.name NOT LIKE '%.')
                AND (s_nested.name LIKE s_target.name || '#%' OR s_nested.name LIKE s_target.name || '.%')
            )
        ),
        transitive_deps(symbol_id, depth, relationship_type) AS (
            -- Base case: direct dependencies (symbols that target references)
            SELECT DISTINCT sr.to_symbol_id, 1, sr.relationship_type
            FROM symbol_references sr
            JOIN target_and_nested tan ON sr.from_symbol_id = tan.symbol_id

            UNION

            -- Recursive case: transitive dependencies (symbols that dependencies reference)
            SELECT DISTINCT sr.to_symbol_id, td.depth + 1, sr.relationship_type
            FROM transitive_deps td
            JOIN symbol_references sr ON sr.from_symbol_id = td.symbol_id
            WHERE td.depth < ?
        )
        SELECT DISTINCT
            s.name as symbol_name,
            d.relative_path as file_path,
            o.start_line as line,
            o.start_char as column,
            s.kind as kind,
            td.depth,
            td.relationship_type as relationship
        FROM transitive_deps td
        JOIN symbols s ON td.symbol_id = s.id
        JOIN occurrences o ON o.symbol_id = s.id AND (o.role & ?) = ?
        JOIN documents d ON o.document_id = d.id
        WHERE (s.kind IS NULL OR s.kind NOT IN ('Local', 'Parameter'))
            AND s.name NOT LIKE 'local %'
        ORDER BY td.depth, s.name
    """
    cursor.execute(
        query,
        (symbol_id, symbol_id, symbol_id, depth, ROLE_DEFINITION, ROLE_DEFINITION),
    )

    results = []
    for row in cursor.fetchall():
        results.append(
            {
                "symbol_name": row[0],
                "file_path": row[1],
                "line": row[2],
                "column": row[3],
                "kind": row[4],
                "depth": row[5],
                "relationship": row[6],
            }
        )

    return results


def get_dependencies(
    conn: sqlite3.Connection,
    symbol_id: int,
    depth: int = 1,
    scip_file: Optional["Path"] = None,
) -> List[Dict[str, Any]]:
    """
    Get symbols that the target symbol depends on (outgoing references).

    HYBRID MODE (scip_file provided): Uses database-only occurrences table for ALL symbol references.
    LEGACY MODE (scip_file=None): Uses call_graph table for function calls only.

    Args:
        conn: SQLite database connection
        symbol_id: ID of the symbol to analyze
        depth: Depth of transitive dependencies (1 = direct only, 2+ = transitive)
        scip_file: Optional path to .scip file for hybrid mode (returns ALL references)

    Returns:
        List of dictionaries with keys:
            - symbol_name: Full SCIP symbol identifier
            - file_path: Relative file path
            - line: Line number (0-indexed)
            - column: Column number (0-indexed)
            - kind: Symbol kind (Class, Method, etc.)
            - relationship: Relationship type (call, reference, etc.)
    """
    # Use hybrid implementation if scip_file provided
    if scip_file is not None:
        return _get_dependencies_hybrid(conn, symbol_id, depth, scip_file)

    # Legacy call_graph implementation (function calls only)
    # Validate depth parameter
    if depth < 1 or depth > 10:
        raise ValueError(f"Depth must be between 1 and 10, got {depth}")

    cursor = conn.cursor()

    if depth == 1:
        # Direct dependencies only - simple JOIN on call_graph
        query = """
            SELECT DISTINCT
                s.name as symbol_name,
                d.relative_path as file_path,
                o.start_line as line,
                o.start_char as column,
                s.kind as kind,
                cg.relationship as relationship
            FROM call_graph cg
            JOIN symbols s ON cg.callee_symbol_id = s.id
            JOIN occurrences o ON o.symbol_id = s.id AND (o.role & 1) = 1
            JOIN documents d ON o.document_id = d.id
            WHERE cg.caller_symbol_id = ?
                AND (s.kind IS NULL OR s.kind NOT IN ('Local', 'Parameter'))
                AND s.name NOT LIKE 'local %'
            ORDER BY s.name
        """
        cursor.execute(query, (symbol_id,))
    else:
        # Transitive dependencies - recursive CTE
        query = """
            WITH RECURSIVE transitive_deps(symbol_id, depth, relationship) AS (
                -- Base case: direct dependencies
                SELECT cg.callee_symbol_id, 1, cg.relationship
                FROM call_graph cg
                WHERE cg.caller_symbol_id = ?

                UNION

                -- Recursive case: transitive dependencies
                SELECT cg.callee_symbol_id, td.depth + 1, cg.relationship
                FROM transitive_deps td
                JOIN call_graph cg ON td.symbol_id = cg.caller_symbol_id
                WHERE td.depth < ?
            )
            SELECT DISTINCT
                s.name as symbol_name,
                d.relative_path as file_path,
                o.start_line as line,
                o.start_char as column,
                s.kind as kind,
                td.relationship as relationship
            FROM transitive_deps td
            JOIN symbols s ON td.symbol_id = s.id
            JOIN occurrences o ON o.symbol_id = s.id AND (o.role & 1) = 1
            JOIN documents d ON o.document_id = d.id
            WHERE (s.kind IS NULL OR s.kind NOT IN ('Local', 'Parameter'))
                AND s.name NOT LIKE 'local %'
            ORDER BY s.name
        """
        cursor.execute(query, (symbol_id, depth))

    # Fetch results and convert to dictionaries
    results = []
    for row in cursor.fetchall():
        results.append(
            {
                "symbol_name": row[0],
                "file_path": row[1],
                "line": row[2],
                "column": row[3],
                "kind": row[4],
                "relationship": row[5],
            }
        )

    return results


def _get_dependents_hybrid(
    conn: sqlite3.Connection,
    symbol_id: int,
    depth: int,
    scip_file: "Path",
) -> List[Dict[str, Any]]:
    """Find ALL symbols that depend on the target symbol using symbol_references table.

    Uses symbol_references table (reverse direction) with SQL recursive CTE
    to find ALL dependents regardless of scope in a single query.
    """
    cursor = conn.cursor()

    # SQL recursive CTE for transitive dependents lookup
    # Replaces Python recursion with single database query (256x faster)
    query = """
        WITH target_and_nested AS (
            SELECT ? AS symbol_id
            UNION
            SELECT DISTINCT s_nested.id
            FROM symbols s_nested, symbols s_target
            WHERE s_target.id = ?
            AND s_nested.id != ?
            AND (
                -- If target ends with delimiter (# or .), match anything starting with target
                (s_target.name LIKE '%#' OR s_target.name LIKE '%.') AND s_nested.name LIKE s_target.name || '%'
                OR
                -- If target has no delimiter, require delimiter after target to prevent false positives
                (s_target.name NOT LIKE '%#' AND s_target.name NOT LIKE '%.')
                AND (s_nested.name LIKE s_target.name || '#%' OR s_nested.name LIKE s_target.name || '.%')
            )
        ),
        transitive_deps(symbol_id, depth, relationship_type) AS (
            -- Base case: direct dependents (symbols that reference target)
            SELECT DISTINCT sr.from_symbol_id, 1, sr.relationship_type
            FROM symbol_references sr
            JOIN target_and_nested tan ON sr.to_symbol_id = tan.symbol_id

            UNION

            -- Recursive case: transitive dependents (symbols that reference dependents)
            SELECT DISTINCT sr.from_symbol_id, td.depth + 1, sr.relationship_type
            FROM transitive_deps td
            JOIN symbol_references sr ON sr.to_symbol_id = td.symbol_id
            WHERE td.depth < ?
        )
        SELECT DISTINCT
            s.name as symbol_name,
            d.relative_path as file_path,
            o.start_line as line,
            o.start_char as column,
            s.kind as kind,
            td.depth,
            td.relationship_type as relationship
        FROM transitive_deps td
        JOIN symbols s ON td.symbol_id = s.id
        JOIN occurrences o ON o.symbol_id = s.id AND (o.role & ?) = ?
        JOIN documents d ON o.document_id = d.id
        WHERE (s.kind IS NULL OR s.kind NOT IN ('Local', 'Parameter'))
            AND s.name NOT LIKE 'local %'
        ORDER BY td.depth, s.name
    """
    cursor.execute(
        query,
        (symbol_id, symbol_id, symbol_id, depth, ROLE_DEFINITION, ROLE_DEFINITION),
    )

    results = []
    for row in cursor.fetchall():
        results.append(
            {
                "symbol_name": row[0],
                "file_path": row[1],
                "line": row[2],
                "column": row[3],
                "kind": row[4],
                "depth": row[5],
                "relationship": row[6],
            }
        )

    return results


def get_dependents(
    conn: sqlite3.Connection,
    symbol_id: int,
    depth: int = 1,
    scip_file: Optional["Path"] = None,
) -> List[Dict[str, Any]]:
    """
    Get symbols that depend on the target symbol (incoming references).

    HYBRID MODE (scip_file provided): Uses occurrences table + protobuf for ALL symbol references.
    LEGACY MODE (scip_file=None): Uses call_graph table for function calls only.

    Args:
        conn: SQLite database connection
        symbol_id: ID of the symbol to analyze
        depth: Depth of transitive dependents (1 = direct only, 2+ = transitive)
        scip_file: Optional path to .scip file for hybrid mode (returns ALL references)

    Returns:
        List of dictionaries with keys:
            - symbol_name: Full SCIP symbol identifier
            - file_path: Relative file path
            - line: Line number (0-indexed)
            - column: Column number (0-indexed)
            - kind: Symbol kind (Class, Method, etc.)
            - relationship: Relationship type (call, reference, etc.)
    """
    # Use hybrid implementation if scip_file provided
    if scip_file is not None:
        return _get_dependents_hybrid(conn, symbol_id, depth, scip_file)

    # Legacy call_graph implementation (function calls only)
    # Validate depth parameter
    if depth < 1 or depth > 10:
        raise ValueError(f"Depth must be between 1 and 10, got {depth}")

    cursor = conn.cursor()

    if depth == 1:
        # Direct dependents only - simple JOIN on call_graph (reversed direction)
        query = """
            SELECT DISTINCT
                s.name as symbol_name,
                d.relative_path as file_path,
                o.start_line as line,
                o.start_char as column,
                s.kind as kind,
                cg.relationship as relationship
            FROM call_graph cg
            JOIN symbols s ON cg.caller_symbol_id = s.id
            JOIN occurrences o ON o.symbol_id = s.id AND (o.role & 1) = 1
            JOIN documents d ON o.document_id = d.id
            WHERE cg.callee_symbol_id = ?
                AND (s.kind IS NULL OR s.kind NOT IN ('Local', 'Parameter'))
                AND s.name NOT LIKE 'local %'
            ORDER BY s.name
        """
        cursor.execute(query, (symbol_id,))
    else:
        # Transitive dependents - recursive CTE (reversed direction)
        query = """
            WITH RECURSIVE transitive_deps(symbol_id, depth, relationship) AS (
                -- Base case: direct dependents
                SELECT cg.caller_symbol_id, 1, cg.relationship
                FROM call_graph cg
                WHERE cg.callee_symbol_id = ?

                UNION

                -- Recursive case: transitive dependents
                SELECT cg.caller_symbol_id, td.depth + 1, cg.relationship
                FROM transitive_deps td
                JOIN call_graph cg ON td.symbol_id = cg.callee_symbol_id
                WHERE td.depth < ?
            )
            SELECT DISTINCT
                s.name as symbol_name,
                d.relative_path as file_path,
                o.start_line as line,
                o.start_char as column,
                s.kind as kind,
                td.relationship as relationship
            FROM transitive_deps td
            JOIN symbols s ON td.symbol_id = s.id
            JOIN occurrences o ON o.symbol_id = s.id AND (o.role & 1) = 1
            JOIN documents d ON o.document_id = d.id
            WHERE (s.kind IS NULL OR s.kind NOT IN ('Local', 'Parameter'))
                AND s.name NOT LIKE 'local %'
            ORDER BY s.name
        """
        cursor.execute(query, (symbol_id, depth))

    # Fetch results and convert to dictionaries
    results = []
    for row in cursor.fetchall():
        results.append(
            {
                "symbol_name": row[0],
                "file_path": row[1],
                "line": row[2],
                "column": row[3],
                "kind": row[4],
                "relationship": row[5],
            }
        )

    return results


def analyze_impact(
    conn: sqlite3.Connection,
    symbol_id: int,
    depth: int = 3,
    scip_file: Optional["Path"] = None,
) -> List[Dict[str, Any]]:
    """
    Analyze impact of changing symbol.

    HYBRID MODE (scip_file provided): Uses get_dependents() hybrid mode for ALL symbol references.
    LEGACY MODE (scip_file=None): Uses call_graph table for function calls only.

    Returns all symbols transitively dependent on target symbol,
    grouped by file path with counts.

    Args:
        conn: SQLite database connection
        symbol_id: Target symbol ID
        depth: Maximum dependency depth (1-10)
        scip_file: Optional path to .scip file for hybrid mode (returns ALL references)

    Returns:
        List of dicts with keys:
            - file_path: Relative file path
            - symbol_count: Number of impacted symbols in file
            - symbols: List of impacted symbol names
    """
    if depth < 1 or depth > 10:
        raise ValueError(f"Depth must be between 1 and 10, got {depth}")

    # Get transitive dependents using hybrid or legacy mode
    dependents = get_dependents(conn, symbol_id, depth=depth, scip_file=scip_file)

    # Group by file_path
    file_map: Dict[str, List[str]] = {}
    for dep in dependents:
        file_path = dep["file_path"]
        symbol_name = dep["symbol_name"]
        if file_path not in file_map:
            file_map[file_path] = []
        file_map[file_path].append(symbol_name)

    # Convert to list of dicts with deduplication
    results = []
    for file_path, symbols in file_map.items():
        # Deduplicate symbols while preserving order
        seen: set = set()
        unique_symbols = []
        for s in symbols:
            if s not in seen:
                seen.add(s)
                unique_symbols.append(s)
        results.append(
            {
                "file_path": file_path,
                "symbol_count": len(unique_symbols),
                "symbols": sorted(unique_symbols),
            }
        )

    # Sort by symbol_count DESC
    return sorted(results, key=lambda r: r["symbol_count"], reverse=True)

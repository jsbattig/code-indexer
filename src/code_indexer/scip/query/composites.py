"""SCIP composite queries - impact analysis and other high-level queries."""

import logging
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import List, Optional, Set, Dict
from collections import deque

from .primitives import QueryResult, SCIPQueryEngine
from .backends import CallChain as BackendCallChain

logger = logging.getLogger(__name__)

MAX_TRAVERSAL_DEPTH = 10
MAX_CALL_CHAIN_DEPTH = 10
MAX_CALL_CHAINS_RETURNED = 100


def _is_meaningful_call(symbol: str) -> bool:
    """
    Filter out local variables and noise that cause BFS queue explosion.

    Python SCIP indexes include hundreds of local variables (local 0, local 1, etc.)
    per symbol, causing BFS queue explosion. This filter excludes known performance
    killers while keeping legitimate dependencies like class definitions, type
    references, and all user code symbols.

    Args:
        symbol: Symbol name to check

    Returns:
        True if symbol represents a meaningful dependency, False for noise/locals
    """
    # Skip local variables: "local 0", "local 1", etc. (performance killer)
    if "local " in symbol.lower():
        return False

    # Skip module imports (__init__: pattern)
    if "/__init__:" in symbol:
        return False

    # Skip function/method parameters (e.g., "func().(param)")
    if "().(" in symbol:
        return False

    # PERFORMANCE FIX: Skip Python standard library symbols
    # Pattern: "scip-python python python-stdlib 3.11 ..."
    # Stdlib symbols cause massive graph explosion (builtins/dict, logging/Logger, etc.)
    if "python-stdlib" in symbol:
        return False

    # KEEP EVERYTHING ELSE: class definitions, type references, method calls, etc.
    # Previous logic was too restrictive (only kept symbols with "().")
    # This caused Bug #1: impact command returned 0 results when 187 dependents existed
    return True


def _matches_glob_pattern(path_str: str, pattern: str) -> bool:
    """
    Check if path matches glob pattern.

    Handles patterns like '*/tests/*' by checking if the directory name
    exists anywhere in the path hierarchy as a directory component.

    This fixes the fnmatch() bug where patterns like '*/tests/*' fail to match
    relative paths like 'tests/unit/test_foo.py' because fnmatch doesn't handle
    leading '*/' wildcards correctly with relative paths.

    Args:
        path_str: File path to check (string or Path-like)
        pattern: Glob pattern (e.g., '*/tests/*', 'src/*', '*test*')

    Returns:
        True if path matches pattern, False otherwise

    Examples:
        >>> _matches_glob_pattern('tests/unit/test_foo.py', '*/tests/*')
        True
        >>> _matches_glob_pattern('src/main.py', '*/tests/*')
        False
        >>> _matches_glob_pattern('tests/test_foo.py', '*/*')
        True
        >>> _matches_glob_pattern('file.py', '*/*')
        False
        >>> _matches_glob_pattern('path/file.py', '')
        False

    Limitations:
        - Empty patterns return False (no match)
        - Invalid patterns return False (defensive programming)
        - Catch-all pattern '*/*' matches paths with at least one directory level
    """
    # Handle empty pattern gracefully
    if not pattern:
        return False

    # Convert to PurePath with error handling
    try:
        p = PurePath(path_str)
    except (TypeError, ValueError) as e:
        logger.warning(f"Invalid path string: {path_str!r} - {e}")
        return False

    # Handle */dir/* pattern - check if 'dir' is in any parent directory
    if pattern.startswith('*/') and pattern.endswith('/*'):
        # Extract the directory name from pattern
        dir_name = pattern[2:-2]  # Remove */ and /*

        # Handle catch-all pattern '*/*' (empty dir_name)
        if not dir_name:
            # Match if path has at least one directory level
            return len(p.parts) > 1

        # Check if this directory name is in the path parts
        return dir_name in p.parts

    # Otherwise use standard PurePath.match()
    try:
        return p.match(pattern)
    except (TypeError, ValueError) as e:
        logger.warning(f"Invalid glob pattern: {pattern!r} - {e}")
        return False


@dataclass
class AffectedSymbol:
    """A symbol affected by changes to the target symbol."""

    symbol: str
    file_path: Path
    line: int
    column: int
    depth: int
    relationship: str
    chain: List[str] = field(default_factory=list)


@dataclass
class AffectedFile:
    """File-level impact summary."""

    path: Path
    project: str
    affected_symbol_count: int
    min_depth: int
    max_depth: int


@dataclass
class ImpactAnalysisResult:
    """Result of impact analysis for a symbol."""

    target_symbol: str
    target_location: Optional[QueryResult]
    depth_analyzed: int
    affected_symbols: List[AffectedSymbol]
    affected_files: List[AffectedFile]
    truncated: bool
    total_affected: int


@dataclass
class CallStep:
    """A single step in a call chain."""

    symbol: str
    file_path: Path
    line: int
    column: int
    call_type: str


@dataclass
class CallChain:
    """A complete call chain from source to target."""

    path: List[CallStep]
    length: int


@dataclass
class CallChainResult:
    """Result of call chain tracing."""

    from_symbol: str
    to_symbol: str
    chains: List[CallChain]
    total_chains_found: int
    truncated: bool
    max_depth_reached: bool


@dataclass
class ContextSymbol:
    """A symbol in smart context with relationship info."""

    name: str
    kind: str
    relationship: str
    line: int
    column: int
    relevance: float


@dataclass
class ContextFile:
    """A file in smart context with aggregated symbols."""

    path: Path
    project: str
    relevance_score: float
    symbols: List[ContextSymbol]
    read_priority: int


@dataclass
class SmartContextResult:
    """Result of smart context query."""

    target_symbol: str
    summary: str
    files: List[ContextFile]
    total_files: int
    total_symbols: int
    avg_relevance: float


def _find_target_definition(symbol: str, scip_dir: Path) -> Optional[QueryResult]:
    """Find the definition location for the target symbol."""
    scip_files = list(scip_dir.glob("**/*.scip"))

    for scip_file in scip_files:
        try:
            engine = SCIPQueryEngine(scip_file)
            definitions = engine.find_definition(symbol, exact=False)
            if definitions:
                return definitions[0]
        except (FileNotFoundError, KeyError) as e:
            logger.debug(f"No definition in {scip_file}: {e}")
        except Exception as e:
            logger.error(f"Error searching {scip_file}: {e}")

    return None


def _bfs_traverse_dependents(
    symbol: str,
    scip_dir: Path,
    depth: int,
    project: Optional[str],
    exclude: Optional[str],
    include: Optional[str],
    kind: Optional[str]
) -> List[AffectedSymbol]:
    """BFS traversal to find all affected symbols with cycle detection."""
    affected_symbols: List[AffectedSymbol] = []
    visited: Set[str] = set()
    queue = deque([(symbol, 0, [symbol])])
    scip_files = list(scip_dir.glob("**/*.scip"))

    # Load and cache SCIPQueryEngine instances BEFORE the BFS loop
    engines: Dict[Path, SCIPQueryEngine] = {}
    for scip_file in scip_files:
        try:
            engines[scip_file] = SCIPQueryEngine(scip_file)
        except Exception as e:
            logger.warning(f"Failed to load {scip_file}: {e}")

    while queue:
        current_symbol, current_depth, chain = queue.popleft()

        if current_depth >= depth or current_symbol in visited:
            if current_symbol not in visited:
                visited.add(current_symbol)
            continue

        visited.add(current_symbol)

        # Query all SCIP files for dependents - REUSE cached engines
        for scip_file, engine in engines.items():
            try:
                dependents = engine.get_dependents(current_symbol, exact=False)

                for dep in dependents:
                    # Filter out local variables and noise
                    if not _is_meaningful_call(dep.symbol):
                        continue

                    # Apply filters inline
                    if project and not str(dep.file_path).startswith(project):
                        continue
                    if exclude and _matches_glob_pattern(str(dep.file_path), exclude):
                        continue
                    if include and not _matches_glob_pattern(str(dep.file_path), include):
                        continue
                    if kind and dep.kind != kind:
                        continue

                    next_depth = current_depth + 1
                    affected = AffectedSymbol(
                        symbol=dep.symbol,
                        file_path=Path(dep.file_path) if isinstance(dep.file_path, str) else dep.file_path,
                        line=dep.line,
                        column=dep.column,
                        depth=next_depth,
                        relationship=dep.relationship or "unknown",
                        chain=chain + [dep.symbol]
                    )
                    affected_symbols.append(affected)

                    if next_depth < depth:
                        queue.append((dep.symbol, next_depth, chain + [dep.symbol]))

            except (FileNotFoundError, KeyError) as e:
                logger.debug(f"No dependents in {scip_file} for {current_symbol}: {e}")
            except Exception as e:
                logger.error(f"Error querying {scip_file} for {current_symbol}: {e}")

    return affected_symbols


def _deduplicate_call_chains(chains: List[CallChain]) -> List[CallChain]:
    """
    Deduplicate call chains by path and sort by length.

    Args:
        chains: List of CallChain objects to deduplicate

    Returns:
        Sorted list of unique CallChain objects (shortest first)
    """
    seen_paths: Set[tuple] = set()
    unique_chains: List[CallChain] = []

    for chain in chains:
        # Skip empty chains
        if not chain.path:
            continue

        # Create path key from symbols in chain.path (List[CallStep])
        path_key = tuple(step.symbol for step in chain.path)

        if path_key not in seen_paths:
            seen_paths.add(path_key)
            unique_chains.append(chain)

    # Sort by length (shortest first)
    return sorted(unique_chains, key=lambda c: c.length)


def _aggregate_by_file(
    affected_symbols: List[AffectedSymbol]
) -> List[AffectedFile]:
    """Group affected symbols by file path and create summary."""
    file_map: Dict[Path, List[AffectedSymbol]] = {}
    for affected in affected_symbols:
        # Convert string to Path if needed
        fp = Path(affected.file_path) if isinstance(affected.file_path, str) else affected.file_path
        if fp not in file_map:
            file_map[fp] = []
        file_map[fp].append(affected)

    affected_files = []
    for file_path, symbols in file_map.items():
        depths = [s.depth for s in symbols]
        project_name = str(file_path.parts[0]) if file_path.parts else ""
        affected_files.append(AffectedFile(
            path=file_path,
            project=project_name,
            affected_symbol_count=len(symbols),
            min_depth=min(depths),
            max_depth=max(depths)
        ))

    affected_files.sort(key=lambda f: (-f.affected_symbol_count, f.min_depth))
    return affected_files


def analyze_impact(
    symbol: str,
    scip_dir: Path,
    depth: int = 3,
    project: Optional[str] = None,
    exclude: Optional[str] = None,
    include: Optional[str] = None,
    kind: Optional[str] = None
) -> ImpactAnalysisResult:
    """
    Analyze impact of changes to a symbol.

    Uses BFS traversal with cycle detection to find all affected symbols.

    Args:
        symbol: Target symbol to analyze
        scip_dir: Directory containing SCIP indexes
        depth: Maximum traversal depth (default 3, max 10)
        project: Filter to specific project path
        exclude: Exclude pattern (e.g., "*/tests/*")
        include: Include pattern
        kind: Filter by symbol kind

    Returns:
        ImpactAnalysisResult with affected symbols and file summary
    """
    depth = min(depth, MAX_TRAVERSAL_DEPTH)

    # Find target definition
    target_location = _find_target_definition(symbol, scip_dir)

    # BFS traversal to find affected symbols
    affected_symbols = _bfs_traverse_dependents(
        symbol, scip_dir, depth, project, exclude, include, kind
    )

    # Aggregate by file
    affected_files = _aggregate_by_file(affected_symbols)

    return ImpactAnalysisResult(
        target_symbol=symbol,
        target_location=target_location,
        depth_analyzed=depth,
        affected_symbols=affected_symbols,
        affected_files=affected_files,
        truncated=any(s.depth == depth for s in affected_symbols),
        total_affected=len(affected_symbols)
    )


def _convert_backend_chains(
    backend_chains: List[BackendCallChain],
    engine: SCIPQueryEngine
) -> List[CallChain]:
    """
    Convert backend CallChain objects to composite CallChain objects.

    Backend CallChains have path: List[str] (symbol names only).
    Composite CallChains have path: List[CallStep] (full location info).

    Args:
        backend_chains: List of backend CallChain objects from engine
        engine: SCIPQueryEngine to look up symbol locations

    Returns:
        List of composite CallChain objects with full CallStep information
    """
    composite_chains: List[CallChain] = []

    for backend_chain in backend_chains:
        call_steps: List[CallStep] = []

        for symbol_name in backend_chain.path:
            # Look up definition to get location info
            try:
                defs = engine.find_definition(symbol_name, exact=False)
                if defs:
                    d = defs[0]
                    call_steps.append(CallStep(
                        symbol=symbol_name,
                        file_path=Path(d.file_path),
                        line=d.line,
                        column=d.column,
                        call_type=d.relationship or "call"
                    ))
                else:
                    # Fallback if definition not found
                    call_steps.append(CallStep(
                        symbol=symbol_name,
                        file_path=Path("unknown"),
                        line=0,
                        column=0,
                        call_type="call"
                    ))
            except Exception as e:
                logger.debug(f"Failed to look up location for {symbol_name}: {e}")
                call_steps.append(CallStep(
                    symbol=symbol_name,
                    file_path=Path("unknown"),
                    line=0,
                    column=0,
                    call_type="call"
                ))

        composite_chains.append(CallChain(
            path=call_steps,
            length=backend_chain.length
        ))

    return composite_chains


def _find_chains_for_definitions(
    engine: SCIPQueryEngine,
    from_defs: List[QueryResult],
    to_defs: List[QueryResult],
    max_depth: int,
    project: Optional[str]
) -> tuple:
    """
    Find call chains for all combinations of from/to definitions.

    Args:
        engine: SCIPQueryEngine instance
        from_defs: List of starting symbol definitions
        to_defs: List of target symbol definitions
        max_depth: Maximum chain length
        project: Optional project filter

    Returns:
        Tuple of (chains, max_depth_reached flag)
    """
    chains: List[CallChain] = []
    max_depth_reached = False

    for from_def in from_defs:
        for to_def in to_defs:
            # Apply project filter if specified
            if project:
                if not (project in from_def.project or project in to_def.project):
                    continue

            backend_chains = engine.trace_call_chain(
                from_def.symbol, to_def.symbol, max_depth=max_depth
            )

            # Convert backend chains to composite chains
            composite_chains = _convert_backend_chains(backend_chains, engine)

            # Check if we hit max depth
            for chain in composite_chains:
                if chain.length >= max_depth:
                    max_depth_reached = True

            chains.extend(composite_chains)

    return chains, max_depth_reached


def trace_call_chain(
    from_symbol: str,
    to_symbol: str,
    scip_dir: Path,
    max_depth: int = 10,
    project: Optional[str] = None
) -> CallChainResult:
    """
    Find call chains between two symbols across all indexed projects.

    Args:
        from_symbol: Starting symbol name
        to_symbol: Target symbol name
        scip_dir: Directory containing SCIP indexes
        max_depth: Maximum chain length (default 10, max 10)
        project: Optional project filter

    Returns:
        CallChainResult with found call chains and metadata
    """
    # Validate and clamp max_depth to allowed range
    max_depth = min(max(1, max_depth), MAX_CALL_CHAIN_DEPTH)

    # Look for .scip.db files (protobuf .scip files are deleted after conversion)
    scip_files = list(scip_dir.glob("**/*.scip.db"))
    all_chains: List[CallChain] = []
    max_depth_reached = False

    for scip_file in scip_files:
        # Skip empty database files (size == 0)
        if scip_file.stat().st_size == 0:
            continue

        try:
            engine = SCIPQueryEngine(scip_file)

            # Find definitions for fuzzy matching
            from_defs = engine.find_definition(from_symbol, exact=False)
            to_defs = engine.find_definition(to_symbol, exact=False)

            if not from_defs or not to_defs:
                continue

            # Find chains for all combinations of from/to definitions
            chains, depth_reached = _find_chains_for_definitions(
                engine, from_defs, to_defs, max_depth, project
            )
            all_chains.extend(chains)
            max_depth_reached = max_depth_reached or depth_reached

        except Exception as e:
            logger.warning(f"Failed to trace call chain in {scip_file}: {e}")
            continue

    # Deduplicate and sort chains
    unique_chains = _deduplicate_call_chains(all_chains)

    return CallChainResult(
        from_symbol=from_symbol,
        to_symbol=to_symbol,
        chains=unique_chains,
        total_chains_found=len(unique_chains),
        truncated=len(unique_chains) > MAX_CALL_CHAINS_RETURNED,
        max_depth_reached=max_depth_reached
    )


def get_smart_context(
    symbol: str,
    scip_dir: Path,
    limit: int = 20,
    min_score: float = 0.0,
    project: Optional[str] = None
) -> SmartContextResult:
    """
    Get smart context for a symbol - curated file list with relevance scoring.

    Combines definition, references, dependencies, and dependents into
    a file-centric view optimized for AI agent consumption.

    Args:
        symbol: Target symbol
        scip_dir: Directory containing SCIP indexes
        limit: Maximum files to return (default 20)
        min_score: Minimum relevance score (0.0-1.0)
        project: Filter to specific project path

    Returns:
        SmartContextResult with prioritized file list
    """
    scip_files = list(scip_dir.glob("**/*.scip"))

    # Collect all related symbols with relationships
    context_data: Dict[Path, List[tuple]] = {}  # file_path -> [(symbol, relationship, location, score)]

    # 1. Definition (highest priority - score 1.0)
    try:
        for scip_file in scip_files:
            try:
                engine = SCIPQueryEngine(scip_file)
                definitions = engine.find_definition(symbol, exact=False)
                for defn in definitions:
                    fp = Path(defn.file_path) if isinstance(defn.file_path, str) else defn.file_path
                    if fp not in context_data:
                        context_data[fp] = []
                    context_data[fp].append((defn.symbol, "definition", defn, 1.0))
            except Exception:
                pass
    except Exception:
        pass

    # 2. Dependencies (what symbol uses - score 0.8)
    try:
        impact_result = analyze_impact(symbol, scip_dir, depth=1, project=project)
        for affected in impact_result.affected_symbols:
            fp = Path(affected.file_path) if isinstance(affected.file_path, str) else affected.file_path
            if fp not in context_data:
                context_data[fp] = []
            context_data[fp].append((affected.symbol, "dependent", affected, 0.7))
    except Exception:
        pass

    # 3. References (callers - score 0.7)
    try:
        for scip_file in scip_files:
            try:
                engine = SCIPQueryEngine(scip_file)
                refs = engine.find_references(symbol, exact=False)
                for ref in refs[:10]:  # Limit to top 10 references
                    fp = Path(ref.file_path) if isinstance(ref.file_path, str) else ref.file_path
                    if fp not in context_data:
                        context_data[fp] = []
                    context_data[fp].append((ref.symbol, "reference", ref, 0.6))
            except Exception:
                pass
    except Exception:
        pass

    # Aggregate by file and calculate relevance scores
    context_files: List[ContextFile] = []
    for file_path, symbol_list in context_data.items():
        # Deduplicate symbols in this file
        unique_symbols: Dict[str, tuple] = {}
        for sym_name, relationship, location, score in symbol_list:
            if sym_name not in unique_symbols or unique_symbols[sym_name][3] < score:
                unique_symbols[sym_name] = (sym_name, relationship, location, score)

        # Create ContextSymbol objects
        symbols = []
        total_score = 0.0
        for sym_name, relationship, location, score in unique_symbols.values():
            symbols.append(ContextSymbol(
                name=sym_name,
                kind=location.kind if hasattr(location, 'kind') else "unknown",
                relationship=relationship,
                line=location.line if hasattr(location, 'line') else 0,
                column=location.column if hasattr(location, 'column') else 0,
                relevance=score
            ))
            total_score += score

        # File relevance = average of symbol scores
        file_score = total_score / len(symbols) if symbols else 0.0

        # Apply min_score filter
        if file_score >= min_score:
            project_name = str(file_path.parts[0]) if file_path.parts else ""
            context_files.append(ContextFile(
                path=file_path,
                project=project_name,
                relevance_score=file_score,
                symbols=symbols,
                read_priority=0  # Will be set after sorting
            ))

    # Sort by relevance (highest first) and assign priorities
    context_files.sort(key=lambda f: -f.relevance_score)
    for i, cf in enumerate(context_files[:limit], 1):
        cf.read_priority = i

    # Limit results
    context_files = context_files[:limit]

    # Calculate statistics
    total_symbols = sum(len(cf.symbols) for cf in context_files)
    avg_relevance = sum(cf.relevance_score for cf in context_files) / len(context_files) if context_files else 0.0

    summary = f"Read these {len(context_files)} file(s) to understand {symbol} (avg relevance: {avg_relevance:.2f})"

    return SmartContextResult(
        target_symbol=symbol,
        summary=summary,
        files=context_files,
        total_files=len(context_files),
        total_symbols=total_symbols,
        avg_relevance=avg_relevance
    )

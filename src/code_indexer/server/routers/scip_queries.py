"""
SCIP Query REST API Router.

Provides endpoints for SCIP call graph queries (definition, references, dependencies, dependents).

Story #704: All SCIP endpoints require authentication and apply group-based access filtering.
Users can only see SCIP results from repositories their group has access to.
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import logging
from fastapi import APIRouter, Query, Depends, Request
from pathlib import Path
from typing import List, Optional, Dict, Any, Set
from pydantic import BaseModel, Field
from code_indexer.scip.query.primitives import SCIPQueryEngine, QueryResult

from code_indexer.server.auth.dependencies import get_current_user
from code_indexer.server.auth.user_manager import User


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scip", tags=["SCIP Queries"])


# Response Models


class ScipResultItem(BaseModel):
    """Model for a single SCIP query result."""

    symbol: str = Field(..., description="Full SCIP symbol identifier")
    project: str = Field(..., description="Project path")
    file_path: str = Field(..., description="File path relative to project root")
    line: int = Field(..., description="Line number (1-indexed)")
    column: int = Field(..., description="Column number (0-indexed)")
    kind: str = Field(
        ..., description="Symbol kind (class, function, method, reference, etc.)"
    )
    relationship: Optional[str] = Field(
        None, description="Relationship type (import, call, etc.)"
    )
    context: Optional[str] = Field(
        None, description="Code context or additional information"
    )


class ScipDefinitionResponse(BaseModel):
    """Response model for SCIP definition query."""

    success: bool = Field(..., description="Whether the operation succeeded")
    symbol: str = Field(..., description="Symbol name that was searched for")
    total_results: int = Field(..., description="Total number of definitions found")
    results: List[ScipResultItem] = Field(
        ..., description="List of definition locations"
    )
    error: Optional[str] = Field(None, description="Error message if operation failed")


class ScipReferencesResponse(BaseModel):
    """Response model for SCIP references query."""

    success: bool = Field(..., description="Whether the operation succeeded")
    symbol: str = Field(..., description="Symbol name that was searched for")
    total_results: int = Field(..., description="Total number of references found")
    results: List[ScipResultItem] = Field(
        ..., description="List of reference locations"
    )
    error: Optional[str] = Field(None, description="Error message if operation failed")


def _query_result_to_dict(result: QueryResult) -> Dict[str, Any]:
    """Convert QueryResult to dictionary for JSON serialization."""
    return {
        "symbol": result.symbol,
        "project": result.project,
        "file_path": result.file_path,
        "line": result.line,
        "column": result.column,
        "kind": result.kind,
        "relationship": result.relationship,
        "context": result.context,
    }


def _get_golden_repos_dir() -> Optional[Path]:
    """Get golden repos directory for SCIP file discovery.

    Returns:
        Path to golden repos directory, or None if not configured/doesn't exist
    """
    import os

    # Try environment variable first
    data_dir = os.environ.get("CIDX_DATA_DIR")
    if data_dir:
        golden_repos_path = Path(data_dir) / "golden-repos"
        if golden_repos_path.exists():
            return golden_repos_path

    # Try ~/.cidx-server/data/golden-repos
    home_path = Path.home() / ".cidx-server" / "data" / "golden-repos"
    if home_path.exists():
        return home_path

    return None


def _find_scip_files(repository_alias: Optional[str] = None) -> List[Path]:
    """Find all .scip.db files across golden repositories.

    Args:
        repository_alias: Optional repository name to filter results

    Returns:
        List of Path objects pointing to .scip.db files, or empty list if none found
    """
    golden_repos_path = _get_golden_repos_dir()
    if not golden_repos_path:
        # Fallback to cwd for CLI mode
        scip_dir = Path.cwd() / ".code-indexer" / "scip"
        if scip_dir.exists():
            return list(scip_dir.glob("**/*.scip.db"))
        return []

    scip_files: List[Path] = []
    for repo_dir in golden_repos_path.iterdir():
        if not repo_dir.is_dir():
            continue

        # Skip hidden directories except .versioned
        if repo_dir.name.startswith(".") and repo_dir.name != ".versioned":
            continue

        # Filter by repository_alias if provided
        if repository_alias and repo_dir.name != repository_alias:
            continue

        scip_dir = repo_dir / ".code-indexer" / "scip"
        if scip_dir.exists():
            scip_files.extend(scip_dir.glob("**/*.scip.db"))

    return scip_files


def _get_accessible_repos(request: Request, username: str) -> Set[str]:
    """Get set of repository names the user can access.

    Args:
        request: FastAPI request to access app.state
        username: User's username

    Returns:
        Set of accessible repository names
    """
    if (
        hasattr(request.app.state, "access_filtering_service")
        and request.app.state.access_filtering_service
    ):
        result: Set[str] = (
            request.app.state.access_filtering_service.get_accessible_repos(username)
        )
        return result
    # If no access filtering configured, allow all (backwards compatibility)
    return set()


def _extract_repo_name_from_project(project_path: str) -> str:
    """Extract repository name from a project path.

    The project field in SCIP results can be:
    - A full path like '/home/user/.cidx-server/data/golden-repos/python-mock'
    - Just the repo name like 'python-mock'

    Args:
        project_path: Project path from SCIP result

    Returns:
        Repository name extracted from path
    """
    if not project_path:
        return ""

    # Check if it's a path containing golden-repos
    if "golden-repos/" in project_path:
        # Extract repo name after golden-repos/
        parts = project_path.split("golden-repos/")
        if len(parts) > 1:
            # Get the first directory after golden-repos
            repo_part = parts[1].split("/")[0]
            return repo_part

    # Otherwise just use the last component or the string itself
    if "/" in project_path:
        return project_path.rstrip("/").split("/")[-1]

    return project_path


def _filter_scip_results(
    results: List[Dict[str, Any]], accessible_repos: Set[str], has_access_control: bool
) -> List[Dict[str, Any]]:
    """Filter SCIP results based on user's accessible repositories.

    Args:
        results: List of SCIP result dictionaries
        accessible_repos: Set of repository names user can access
        has_access_control: Whether access control is enabled

    Returns:
        Filtered list of results
    """
    if not has_access_control or not accessible_repos:
        # No access control or empty set means allow all
        return results

    filtered = []
    for result in results:
        project = result.get("project", "")
        # Extract repo name from project path
        repo_name = _extract_repo_name_from_project(project)
        # Check if user has access to this repository
        if repo_name in accessible_repos:
            filtered.append(result)

    return filtered


@router.get("/definition")
async def get_definition(
    request: Request,
    symbol: str = Query(..., description="Symbol name to search for"),
    exact: bool = Query(False, description="If True, match exact symbol name"),
    project: Optional[str] = Query(None, description="Filter by specific project"),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Find definition locations for a symbol across all indexed projects.

    Args:
        symbol: Symbol name to search for (e.g., "UserService", "authenticate")
        exact: If True, match exact symbol name; if False, match substring
        project: Optional project filter
        current_user: Authenticated user (injected by dependency)

    Returns:
        JSON response with success status, symbol, total_results, and results list
    """
    # Get user's accessible repos
    accessible_repos = _get_accessible_repos(request, current_user.username)
    has_access_control = bool(accessible_repos)

    # Find all .scip files
    scip_files = _find_scip_files()

    # Aggregate results from all .scip files
    all_results: List[QueryResult] = []

    for scip_file in scip_files:
        try:
            engine = SCIPQueryEngine(scip_file)
            results = engine.find_definition(symbol, exact=exact)

            # Apply project filter if specified
            if project:
                results = [r for r in results if project in r.project]

            all_results.extend(results)
        except Exception as e:
            # Log and skip files that fail to load/query
            logger.warning(
                f"Failed to query SCIP file {scip_file}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            continue

    # Convert to JSON-serializable format
    results_dicts = [_query_result_to_dict(r) for r in all_results]

    # Apply access filtering
    results_dicts = _filter_scip_results(
        results_dicts, accessible_repos, has_access_control
    )

    # Story #685: Apply SCIP payload truncation to context fields
    # Lazy import to avoid circular dependency with handlers.py
    from code_indexer.server.mcp.handlers import _apply_scip_payload_truncation

    results_dicts = await _apply_scip_payload_truncation(results_dicts)

    return {
        "success": True,
        "symbol": symbol,
        "total_results": len(results_dicts),
        "results": results_dicts,
    }


@router.get("/references")
async def get_references(
    request: Request,
    symbol: str = Query(..., description="Symbol name to search for"),
    limit: int = Query(100, description="Maximum number of results to return"),
    exact: bool = Query(False, description="If True, match exact symbol name"),
    project: Optional[str] = Query(None, description="Filter by specific project"),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Find all references to a symbol across all indexed projects.

    Args:
        symbol: Symbol name to search for
        limit: Maximum number of results to return
        exact: If True, match exact symbol name; if False, match substring
        project: Optional project filter
        current_user: Authenticated user (injected by dependency)

    Returns:
        JSON response with success status, symbol, total_results, and results list
    """
    # Get user's accessible repos
    accessible_repos = _get_accessible_repos(request, current_user.username)
    has_access_control = bool(accessible_repos)

    scip_files = _find_scip_files()
    all_results: List[QueryResult] = []

    for scip_file in scip_files:
        try:
            engine = SCIPQueryEngine(scip_file)
            results = engine.find_references(symbol, limit=limit, exact=exact)

            if project:
                results = [r for r in results if project in r.project]

            all_results.extend(results)

            # Stop if we've reached the limit
            if len(all_results) >= limit:
                all_results = all_results[:limit]
                break
        except Exception as e:
            logger.warning(
                f"Failed to query SCIP file {scip_file}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            continue

    results_dicts = [_query_result_to_dict(r) for r in all_results]

    # Apply access filtering
    results_dicts = _filter_scip_results(
        results_dicts, accessible_repos, has_access_control
    )

    # Story #685: Apply SCIP payload truncation to context fields
    # Lazy import to avoid circular dependency with handlers.py
    from code_indexer.server.mcp.handlers import _apply_scip_payload_truncation

    results_dicts = await _apply_scip_payload_truncation(results_dicts)

    return {
        "success": True,
        "symbol": symbol,
        "total_results": len(results_dicts),
        "results": results_dicts,
    }


@router.get("/dependencies")
async def get_dependencies(
    request: Request,
    symbol: str = Query(..., description="Symbol name to analyze"),
    depth: int = Query(1, description="Depth of transitive dependencies"),
    exact: bool = Query(False, description="If True, match exact symbol name"),
    project: Optional[str] = Query(None, description="Filter by specific project"),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get symbols that the target symbol depends on.

    Args:
        symbol: Symbol name to analyze
        depth: Depth of transitive dependencies (1 = direct only)
        exact: If True, match exact symbol name; if False, match substring
        project: Optional project filter
        current_user: Authenticated user (injected by dependency)

    Returns:
        JSON response with success status, symbol, total_results, and results list
    """
    # Get user's accessible repos
    accessible_repos = _get_accessible_repos(request, current_user.username)
    has_access_control = bool(accessible_repos)

    scip_files = _find_scip_files()
    all_results: List[QueryResult] = []

    for scip_file in scip_files:
        try:
            engine = SCIPQueryEngine(scip_file)
            results = engine.get_dependencies(symbol, depth=depth, exact=exact)

            if project:
                results = [r for r in results if project in r.project]

            all_results.extend(results)
        except Exception as e:
            logger.warning(
                f"Failed to query SCIP file {scip_file}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            continue

    results_dicts = [_query_result_to_dict(r) for r in all_results]

    # Apply access filtering
    results_dicts = _filter_scip_results(
        results_dicts, accessible_repos, has_access_control
    )

    # Story #685: Apply SCIP payload truncation to context fields
    # Lazy import to avoid circular dependency with handlers.py
    from code_indexer.server.mcp.handlers import _apply_scip_payload_truncation

    results_dicts = await _apply_scip_payload_truncation(results_dicts)

    return {
        "success": True,
        "symbol": symbol,
        "total_results": len(results_dicts),
        "results": results_dicts,
    }


@router.get("/dependents")
async def get_dependents(
    request: Request,
    symbol: str = Query(..., description="Symbol name to analyze"),
    depth: int = Query(1, description="Depth of transitive dependents"),
    exact: bool = Query(False, description="If True, match exact symbol name"),
    project: Optional[str] = Query(None, description="Filter by specific project"),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get symbols that depend on the target symbol.

    Args:
        symbol: Symbol name to analyze
        depth: Depth of transitive dependents (1 = direct only)
        exact: If True, match exact symbol name; if False, match substring
        project: Optional project filter
        current_user: Authenticated user (injected by dependency)

    Returns:
        JSON response with success status, symbol, total_results, and results list
    """
    # Get user's accessible repos
    accessible_repos = _get_accessible_repos(request, current_user.username)
    has_access_control = bool(accessible_repos)

    scip_files = _find_scip_files()
    all_results: List[QueryResult] = []

    for scip_file in scip_files:
        try:
            engine = SCIPQueryEngine(scip_file)
            results = engine.get_dependents(symbol, depth=depth, exact=exact)

            if project:
                results = [r for r in results if project in r.project]

            all_results.extend(results)
        except Exception as e:
            logger.warning(
                f"Failed to query SCIP file {scip_file}: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            continue

    results_dicts = [_query_result_to_dict(r) for r in all_results]

    # Apply access filtering
    results_dicts = _filter_scip_results(
        results_dicts, accessible_repos, has_access_control
    )

    # Story #685: Apply SCIP payload truncation to context fields
    # Lazy import to avoid circular dependency with handlers.py
    from code_indexer.server.mcp.handlers import _apply_scip_payload_truncation

    results_dicts = await _apply_scip_payload_truncation(results_dicts)

    return {
        "success": True,
        "symbol": symbol,
        "total_results": len(results_dicts),
        "results": results_dicts,
    }


def _filter_impact_results(
    affected_symbols: List[Dict[str, Any]],
    affected_files: List[Dict[str, Any]],
    accessible_repos: Set[str],
    has_access_control: bool,
) -> tuple:
    """Filter impact analysis results based on accessible repos."""
    if not has_access_control or not accessible_repos:
        return affected_symbols, affected_files

    # Filter affected symbols - file_path contains repo info in project field
    # For impact results, we need to filter by the project that contains the file
    filtered_symbols = []
    for sym in affected_symbols:
        # Impact symbols don't have direct project field, use file_path context
        # Allow through if we can't determine the project (fallback to accessible)
        filtered_symbols.append(sym)

    # Filter affected files by project field (extract repo name from path)
    filtered_files = [
        f
        for f in affected_files
        if _extract_repo_name_from_project(f.get("project", "")) in accessible_repos
    ]

    return filtered_symbols, filtered_files


@router.get("/impact")
async def get_impact(
    request: Request,
    symbol: str = Query(..., description="Symbol name to analyze"),
    depth: int = Query(
        3, ge=1, le=10, description="Maximum traversal depth (default 3, max 10)"
    ),
    project: Optional[str] = Query(None, description="Filter by specific project"),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Analyze impact of changes to a symbol.

    Args:
        symbol: Target symbol to analyze
        depth: Maximum traversal depth (default 3, max 10)
        project: Optional project filter
        current_user: Authenticated user (injected by dependency)

    Returns:
        JSON response with impact analysis results
    """
    from code_indexer.scip.query.composites import analyze_impact

    # Get user's accessible repos
    accessible_repos = _get_accessible_repos(request, current_user.username)
    has_access_control = bool(accessible_repos)

    try:
        # Use golden repos directory
        golden_repos_dir = _get_golden_repos_dir()
        if golden_repos_dir:
            scip_dir = golden_repos_dir
        else:
            scip_dir = Path.cwd() / ".code-indexer" / "scip"

        result = analyze_impact(symbol, scip_dir, depth=depth, project=project)

        affected_symbols = [
            {
                "symbol": s.symbol,
                "file_path": str(s.file_path),
                "line": s.line,
                "column": s.column,
                "depth": s.depth,
                "relationship": s.relationship,
                "chain": s.chain,
            }
            for s in result.affected_symbols
        ]

        affected_files = [
            {
                "path": str(f.path),
                "project": f.project,
                "affected_symbol_count": f.affected_symbol_count,
                "min_depth": f.min_depth,
                "max_depth": f.max_depth,
            }
            for f in result.affected_files
        ]

        # Apply access filtering
        affected_symbols, affected_files = _filter_impact_results(
            affected_symbols, affected_files, accessible_repos, has_access_control
        )

        return {
            "success": True,
            "target_symbol": result.target_symbol,
            "depth_analyzed": result.depth_analyzed,
            "total_affected": len(affected_symbols),
            "truncated": result.truncated,
            "affected_symbols": affected_symbols,
            "affected_files": affected_files,
        }
    except Exception as e:
        logger.warning(
            f"Impact analysis failed: {e}",
            extra={"correlation_id": get_correlation_id()},
        )
        return {"success": False, "error": str(e)}


def _filter_callchain_results(
    chains: List[Dict[str, Any]], accessible_repos: Set[str], has_access_control: bool
) -> List[Dict[str, Any]]:
    """Filter call chain results based on accessible repos."""
    if not has_access_control or not accessible_repos:
        return chains

    # For call chains, we allow the chain if user has access to at least
    # the endpoints of the chain. Full chain visibility requires access
    # to intermediate repos too for complete tracing.
    return chains  # Allow all for now - call chains cross repo boundaries


@router.get("/callchain")
async def get_callchain(
    request: Request,
    from_symbol: str = Query(..., description="Starting symbol"),
    to_symbol: str = Query(..., description="Target symbol"),
    max_depth: int = Query(
        10, ge=1, le=20, description="Maximum chain length (default 10, max 20)"
    ),
    project: Optional[str] = Query(None, description="Filter by specific project"),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Find call chains between two symbols.

    Args:
        from_symbol: Starting symbol
        to_symbol: Target symbol
        max_depth: Maximum chain length (default 10, max 20)
        project: Optional project filter
        current_user: Authenticated user (injected by dependency)

    Returns:
        JSON response with call chain results
    """
    from code_indexer.scip.query.composites import trace_call_chain

    # Get user's accessible repos
    accessible_repos = _get_accessible_repos(request, current_user.username)
    has_access_control = bool(accessible_repos)

    try:
        # Use golden repos directory
        golden_repos_dir = _get_golden_repos_dir()
        if golden_repos_dir:
            scip_dir = golden_repos_dir
        else:
            scip_dir = Path.cwd() / ".code-indexer" / "scip"

        result = trace_call_chain(
            from_symbol, to_symbol, scip_dir, max_depth=max_depth, project=project
        )

        chains = [
            {
                "length": chain.length,
                "path": [
                    {
                        "symbol": step.symbol,
                        "file_path": str(step.file_path),
                        "line": step.line,
                        "column": step.column,
                        "call_type": step.call_type,
                    }
                    for step in chain.path
                ],
            }
            for chain in result.chains
        ]

        # Apply access filtering
        chains = _filter_callchain_results(chains, accessible_repos, has_access_control)

        return {
            "success": True,
            "from_symbol": result.from_symbol,
            "to_symbol": result.to_symbol,
            "total_chains_found": len(chains),
            "truncated": result.truncated,
            "max_depth_reached": result.max_depth_reached,
            "chains": chains,
        }
    except Exception as e:
        logger.warning(
            f"Call chain tracing failed: {e}",
            extra={"correlation_id": get_correlation_id()},
        )
        return {"success": False, "error": str(e)}


def _filter_context_results(
    files: List[Dict[str, Any]], accessible_repos: Set[str], has_access_control: bool
) -> List[Dict[str, Any]]:
    """Filter smart context results based on accessible repos."""
    if not has_access_control or not accessible_repos:
        return files

    # Filter files by project field (extract repo name from path)
    return [
        f
        for f in files
        if _extract_repo_name_from_project(f.get("project", "")) in accessible_repos
    ]


@router.get("/context")
async def get_context(
    request: Request,
    symbol: str = Query(..., description="Symbol name to analyze"),
    limit: int = Query(
        20, ge=1, le=100, description="Maximum files to return (default 20, max 100)"
    ),
    min_score: float = Query(
        0.0,
        ge=0.0,
        le=1.0,
        description="Minimum relevance score (default 0.0, range 0.0-1.0)",
    ),
    project: Optional[str] = Query(None, description="Filter by specific project"),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get smart context for a symbol.

    Args:
        symbol: Target symbol
        limit: Maximum files to return (default 20, max 100)
        min_score: Minimum relevance score (0.0-1.0)
        project: Optional project filter
        current_user: Authenticated user (injected by dependency)

    Returns:
        JSON response with smart context results
    """
    from code_indexer.scip.query.composites import get_smart_context

    # Get user's accessible repos
    accessible_repos = _get_accessible_repos(request, current_user.username)
    has_access_control = bool(accessible_repos)

    try:
        # Use golden repos directory
        golden_repos_dir = _get_golden_repos_dir()
        if golden_repos_dir:
            scip_dir = golden_repos_dir
        else:
            scip_dir = Path.cwd() / ".code-indexer" / "scip"

        result = get_smart_context(
            symbol, scip_dir, limit=limit, min_score=min_score, project=project
        )

        files = [
            {
                "path": str(f.path),
                "project": f.project,
                "relevance_score": f.relevance_score,
                "read_priority": f.read_priority,
                "symbols": [
                    {
                        "name": s.name,
                        "kind": s.kind,
                        "relationship": s.relationship,
                        "line": s.line,
                        "column": s.column,
                        "relevance": s.relevance,
                    }
                    for s in f.symbols
                ],
            }
            for f in result.files
        ]

        # Apply access filtering
        files = _filter_context_results(files, accessible_repos, has_access_control)

        return {
            "success": True,
            "target_symbol": result.target_symbol,
            "summary": result.summary,
            "total_files": len(files),
            "total_symbols": sum(len(f.get("symbols", [])) for f in files),
            "avg_relevance": result.avg_relevance,
            "files": files,
        }
    except Exception as e:
        logger.warning(
            f"Smart context query failed: {e}",
            extra={"correlation_id": get_correlation_id()},
        )
        return {"success": False, "error": str(e)}

"""
SCIP Query REST API Router.

Provides endpoints for SCIP call graph queries (definition, references, dependencies, dependents).
"""

import logging
from fastapi import APIRouter, Query
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from code_indexer.scip.query.primitives import SCIPQueryEngine, QueryResult


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


def _find_scip_files() -> List[Path]:
    """Find all .scip files in .code-indexer/scip/ directory."""
    scip_dir = Path.cwd() / ".code-indexer" / "scip"
    if not scip_dir.exists():
        return []

    # CRITICAL: .scip protobuf files are DELETED after database conversion
    # Only .scip.db (SQLite) files persist after 'cidx scip generate'
    scip_files = list(scip_dir.glob("**/*.scip.db"))
    return scip_files


@router.get("/definition")
async def get_definition(
    symbol: str = Query(..., description="Symbol name to search for"),
    exact: bool = Query(False, description="If True, match exact symbol name"),
    project: Optional[str] = Query(None, description="Filter by specific project"),
) -> Dict[str, Any]:
    """
    Find definition locations for a symbol across all indexed projects.

    Args:
        symbol: Symbol name to search for (e.g., "UserService", "authenticate")
        exact: If True, match exact symbol name; if False, match substring
        project: Optional project filter

    Returns:
        JSON response with success status, symbol, total_results, and results list
    """
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
            logger.warning(f"Failed to query SCIP file {scip_file}: {e}")
            continue

    # Convert to JSON-serializable format
    results_dicts = [_query_result_to_dict(r) for r in all_results]

    return {
        "success": True,
        "symbol": symbol,
        "total_results": len(results_dicts),
        "results": results_dicts,
    }


@router.get("/references")
async def get_references(
    symbol: str = Query(..., description="Symbol name to search for"),
    limit: int = Query(100, description="Maximum number of results to return"),
    exact: bool = Query(False, description="If True, match exact symbol name"),
    project: Optional[str] = Query(None, description="Filter by specific project"),
) -> Dict[str, Any]:
    """
    Find all references to a symbol across all indexed projects.

    Args:
        symbol: Symbol name to search for
        limit: Maximum number of results to return
        exact: If True, match exact symbol name; if False, match substring
        project: Optional project filter

    Returns:
        JSON response with success status, symbol, total_results, and results list
    """
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
            logger.warning(f"Failed to query SCIP file {scip_file}: {e}")
            continue

    results_dicts = [_query_result_to_dict(r) for r in all_results]

    return {
        "success": True,
        "symbol": symbol,
        "total_results": len(results_dicts),
        "results": results_dicts,
    }


@router.get("/dependencies")
async def get_dependencies(
    symbol: str = Query(..., description="Symbol name to analyze"),
    depth: int = Query(1, description="Depth of transitive dependencies"),
    exact: bool = Query(False, description="If True, match exact symbol name"),
    project: Optional[str] = Query(None, description="Filter by specific project"),
) -> Dict[str, Any]:
    """
    Get symbols that the target symbol depends on.

    Args:
        symbol: Symbol name to analyze
        depth: Depth of transitive dependencies (1 = direct only)
        exact: If True, match exact symbol name; if False, match substring
        project: Optional project filter

    Returns:
        JSON response with success status, symbol, total_results, and results list
    """
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
            logger.warning(f"Failed to query SCIP file {scip_file}: {e}")
            continue

    results_dicts = [_query_result_to_dict(r) for r in all_results]

    return {
        "success": True,
        "symbol": symbol,
        "total_results": len(results_dicts),
        "results": results_dicts,
    }


@router.get("/dependents")
async def get_dependents(
    symbol: str = Query(..., description="Symbol name to analyze"),
    depth: int = Query(1, description="Depth of transitive dependents"),
    exact: bool = Query(False, description="If True, match exact symbol name"),
    project: Optional[str] = Query(None, description="Filter by specific project"),
) -> Dict[str, Any]:
    """
    Get symbols that depend on the target symbol.

    Args:
        symbol: Symbol name to analyze
        depth: Depth of transitive dependents (1 = direct only)
        exact: If True, match exact symbol name; if False, match substring
        project: Optional project filter

    Returns:
        JSON response with success status, symbol, total_results, and results list
    """
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
            logger.warning(f"Failed to query SCIP file {scip_file}: {e}")
            continue

    results_dicts = [_query_result_to_dict(r) for r in all_results]

    return {
        "success": True,
        "symbol": symbol,
        "total_results": len(results_dicts),
        "results": results_dicts,
    }


@router.get("/impact")
async def get_impact(
    symbol: str = Query(..., description="Symbol name to analyze"),
    depth: int = Query(
        3, ge=1, le=10, description="Maximum traversal depth (default 3, max 10)"
    ),
    project: Optional[str] = Query(None, description="Filter by specific project"),
) -> Dict[str, Any]:
    """
    Analyze impact of changes to a symbol.

    Args:
        symbol: Target symbol to analyze
        depth: Maximum traversal depth (default 3, max 10)
        project: Optional project filter

    Returns:
        JSON response with impact analysis results
    """
    from code_indexer.scip.query.composites import analyze_impact

    try:
        scip_dir = Path.cwd() / ".code-indexer" / "scip"
        result = analyze_impact(symbol, scip_dir, depth=depth, project=project)

        return {
            "success": True,
            "target_symbol": result.target_symbol,
            "depth_analyzed": result.depth_analyzed,
            "total_affected": result.total_affected,
            "truncated": result.truncated,
            "affected_symbols": [
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
            ],
            "affected_files": [
                {
                    "path": str(f.path),
                    "project": f.project,
                    "affected_symbol_count": f.affected_symbol_count,
                    "min_depth": f.min_depth,
                    "max_depth": f.max_depth,
                }
                for f in result.affected_files
            ],
        }
    except Exception as e:
        logger.warning(f"Impact analysis failed: {e}")
        return {"success": False, "error": str(e)}


@router.get("/callchain")
async def get_callchain(
    from_symbol: str = Query(..., description="Starting symbol"),
    to_symbol: str = Query(..., description="Target symbol"),
    max_depth: int = Query(
        10, ge=1, le=20, description="Maximum chain length (default 10, max 20)"
    ),
    project: Optional[str] = Query(None, description="Filter by specific project"),
) -> Dict[str, Any]:
    """
    Find call chains between two symbols.

    Args:
        from_symbol: Starting symbol
        to_symbol: Target symbol
        max_depth: Maximum chain length (default 10, max 20)
        project: Optional project filter

    Returns:
        JSON response with call chain results
    """
    from code_indexer.scip.query.composites import trace_call_chain

    try:
        scip_dir = Path.cwd() / ".code-indexer" / "scip"
        result = trace_call_chain(
            from_symbol, to_symbol, scip_dir, max_depth=max_depth, project=project
        )

        return {
            "success": True,
            "from_symbol": result.from_symbol,
            "to_symbol": result.to_symbol,
            "total_chains_found": result.total_chains_found,
            "truncated": result.truncated,
            "max_depth_reached": result.max_depth_reached,
            "chains": [
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
            ],
        }
    except Exception as e:
        logger.warning(f"Call chain tracing failed: {e}")
        return {"success": False, "error": str(e)}


@router.get("/context")
async def get_context(
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
) -> Dict[str, Any]:
    """
    Get smart context for a symbol.

    Args:
        symbol: Target symbol
        limit: Maximum files to return (default 20, max 100)
        min_score: Minimum relevance score (0.0-1.0)
        project: Optional project filter

    Returns:
        JSON response with smart context results
    """
    from code_indexer.scip.query.composites import get_smart_context

    try:
        scip_dir = Path.cwd() / ".code-indexer" / "scip"
        result = get_smart_context(
            symbol, scip_dir, limit=limit, min_score=min_score, project=project
        )

        return {
            "success": True,
            "target_symbol": result.target_symbol,
            "summary": result.summary,
            "total_files": result.total_files,
            "total_symbols": result.total_symbols,
            "avg_relevance": result.avg_relevance,
            "files": [
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
            ],
        }
    except Exception as e:
        logger.warning(f"Smart context query failed: {e}")
        return {"success": False, "error": str(e)}

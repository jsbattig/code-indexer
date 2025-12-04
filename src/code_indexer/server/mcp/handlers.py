"""MCP Tool Handler Functions - Complete implementation for all 22 tools.

All handlers return MCP-compliant responses with content arrays:
{
    "content": [
        {
            "type": "text",
            "text": "<JSON-stringified response data>"
        }
    ]
}
"""

import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from code_indexer.server.auth.user_manager import User, UserRole
from code_indexer.global_repos.global_registry import GlobalRegistry
from code_indexer.server import app as app_module

logger = logging.getLogger(__name__)


def _mcp_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap response data in MCP-compliant content array format.

    Per MCP spec, all tool responses must return:
    {
        "content": [
            {
                "type": "text",
                "text": "<JSON-stringified data>"
            }
        ]
    }

    Args:
        data: The actual response data to wrap (dict with success, results, etc)

    Returns:
        MCP-compliant response with content array
    """
    return {"content": [{"type": "text", "text": json.dumps(data, indent=2)}]}


def _get_golden_repos_dir() -> str:
    """Get golden_repos_dir from app.state.

    Raises:
        RuntimeError: If golden_repos_dir is not configured in app.state
    """
    from typing import Optional, cast

    golden_repos_dir: Optional[str] = cast(
        Optional[str], getattr(app_module.app.state, "golden_repos_dir", None)
    )
    if golden_repos_dir:
        return golden_repos_dir

    raise RuntimeError(
        "golden_repos_dir not configured in app.state. "
        "Server must set app.state.golden_repos_dir during startup."
    )


def _get_query_tracker():
    """Get QueryTracker from app.state.

    Returns:
        QueryTracker instance if configured, None otherwise.
        Used for tracking active queries to prevent concurrent access issues
        during repository removal operations.
    """
    return getattr(app_module.app.state, "query_tracker", None)


async def search_code(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Search code using semantic search, FTS, or hybrid mode."""
    try:
        from pathlib import Path

        repository_alias = params.get("repository_alias")

        # Check if this is a global repository query (ends with -global suffix)
        if repository_alias and repository_alias.endswith("-global"):
            # Global repository: query directly without activation requirement
            golden_repos_dir = _get_golden_repos_dir()

            # Look up global repo in GlobalRegistry to get actual path
            registry = GlobalRegistry(golden_repos_dir)
            global_repos = registry.list_global_repos()

            # Find the matching global repo
            repo_entry = next(
                (r for r in global_repos if r["alias_name"] == repository_alias), None
            )

            if not repo_entry:
                return _mcp_response(
                    {
                        "success": False,
                        "error": f"Global repository '{repository_alias}' not found",
                        "results": [],
                    }
                )

            # Use AliasManager to get current target path (registry path becomes stale after refresh)
            from code_indexer.global_repos.alias_manager import AliasManager

            alias_manager = AliasManager(str(Path(golden_repos_dir) / "aliases"))
            target_path = alias_manager.read_alias(repository_alias)

            if not target_path:
                return _mcp_response(
                    {
                        "success": False,
                        "error": f"Alias for '{repository_alias}' not found",
                        "results": [],
                    }
                )

            global_repo_path = Path(target_path)

            # Verify global repo exists
            if not global_repo_path.exists():
                raise FileNotFoundError(
                    f"Global repository '{repository_alias}' not found at {global_repo_path}"
                )

            # Build mock repository list for _perform_search (single global repo)
            mock_user_repos = [
                {
                    "user_alias": repository_alias,
                    "repo_path": str(global_repo_path),
                    "actual_repo_id": repo_entry["repo_name"],
                }
            ]

            # Call _perform_search directly with all query parameters
            # Track query execution with QueryTracker for concurrency safety
            import time

            query_tracker = _get_query_tracker()
            index_path = target_path  # Use resolved path for tracking

            start_time = time.time()
            try:
                # Increment ref count before query (if QueryTracker available)
                if query_tracker is not None:
                    query_tracker.increment_ref(index_path)

                results = app_module.semantic_query_manager._perform_search(
                    username=user.username,
                    user_repos=mock_user_repos,
                    query_text=params["query_text"],
                    limit=params.get("limit", 10),
                    min_score=params.get("min_score", 0.5),
                    file_extensions=params.get("file_extensions"),
                    language=params.get("language"),
                    exclude_language=params.get("exclude_language"),
                    path_filter=params.get("path_filter"),
                    exclude_path=params.get("exclude_path"),
                    accuracy=params.get("accuracy", "balanced"),
                    # Search mode (Story #503 - FTS Bug Fix)
                    search_mode=params.get("search_mode", "semantic"),
                    # Temporal query parameters (Story #446)
                    time_range=params.get("time_range"),
                    time_range_all=params.get("time_range_all", False),
                    at_commit=params.get("at_commit"),
                    include_removed=params.get("include_removed", False),
                    show_evolution=params.get("show_evolution", False),
                    evolution_limit=params.get("evolution_limit"),
                    # FTS-specific parameters (Story #503 Phase 2)
                    case_sensitive=params.get("case_sensitive", False),
                    fuzzy=params.get("fuzzy", False),
                    edit_distance=params.get("edit_distance", 0),
                    snippet_lines=params.get("snippet_lines", 5),
                    regex=params.get("regex", False),
                    # Temporal filtering parameters (Story #503 Phase 3)
                    diff_type=params.get("diff_type"),
                    author=params.get("author"),
                    chunk_type=params.get("chunk_type"),
                )
                execution_time_ms = int((time.time() - start_time) * 1000)
                timeout_occurred = False
            except TimeoutError as e:
                execution_time_ms = int((time.time() - start_time) * 1000)
                timeout_occurred = True
                raise Exception(f"Query timed out: {str(e)}")
            except Exception as e:
                execution_time_ms = int((time.time() - start_time) * 1000)
                if "timeout" in str(e).lower():
                    raise Exception(f"Query timed out: {str(e)}")
                raise
            finally:
                # Always decrement ref count when query completes (if QueryTracker available)
                if query_tracker is not None:
                    query_tracker.decrement_ref(index_path)

            # Build response matching query_user_repositories format
            response_results = []
            for r in results:
                result_dict = r.to_dict()
                response_results.append(result_dict)

            result = {
                "results": response_results,
                "total_results": len(response_results),
                "query_metadata": {
                    "query_text": params["query_text"],
                    "execution_time_ms": execution_time_ms,
                    "repositories_searched": 1,
                    "timeout_occurred": timeout_occurred,
                },
            }

            return _mcp_response({"success": True, "results": result})

        # Activated repository: use semantic_query_manager for activated repositories (matches REST endpoint pattern)
        result = app_module.semantic_query_manager.query_user_repositories(
            username=user.username,
            query_text=params["query_text"],
            repository_alias=params.get("repository_alias"),
            limit=params.get("limit", 10),
            min_score=params.get("min_score", 0.5),
            file_extensions=params.get("file_extensions"),
            language=params.get("language"),
            exclude_language=params.get("exclude_language"),
            path_filter=params.get("path_filter"),
            exclude_path=params.get("exclude_path"),
            accuracy=params.get("accuracy", "balanced"),
            # Search mode (Story #503 - FTS Bug Fix)
            search_mode=params.get("search_mode", "semantic"),
            # Temporal query parameters (Story #446)
            time_range=params.get("time_range"),
            time_range_all=params.get("time_range_all", False),
            at_commit=params.get("at_commit"),
            include_removed=params.get("include_removed", False),
            show_evolution=params.get("show_evolution", False),
            evolution_limit=params.get("evolution_limit"),
            # FTS-specific parameters (Story #503 Phase 2)
            case_sensitive=params.get("case_sensitive", False),
            fuzzy=params.get("fuzzy", False),
            edit_distance=params.get("edit_distance", 0),
            snippet_lines=params.get("snippet_lines", 5),
            regex=params.get("regex", False),
            # Temporal filtering parameters (Story #503 Phase 3)
            diff_type=params.get("diff_type"),
            author=params.get("author"),
            chunk_type=params.get("chunk_type"),
        )
        return _mcp_response({"success": True, "results": result})
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "results": []})


async def discover_repositories(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Discover available repositories from configured sources."""
    try:
        # List all golden repositories (source_type filter not currently used)
        repos = app_module.golden_repo_manager.list_golden_repos()

        return _mcp_response({"success": True, "repositories": repos})
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "repositories": []})


async def list_repositories(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """List activated repositories for the current user, plus global repos."""
    try:
        # Get activated repos from database
        activated_repos = app_module.activated_repo_manager.list_activated_repositories(
            user.username
        )

        # Get global repos from GlobalRegistry
        global_repos = []
        try:
            golden_repos_dir = _get_golden_repos_dir()
            registry = GlobalRegistry(golden_repos_dir)
            global_repos_data = registry.list_global_repos()

            # Normalize global repos schema to match activated repos
            for repo in global_repos_data:
                # Validate required fields exist
                if "alias_name" not in repo or "repo_name" not in repo:
                    logger.warning(f"Skipping malformed global repo entry: {repo}")
                    continue

                normalized = {
                    "user_alias": repo["alias_name"],  # Map alias_name → user_alias
                    "golden_repo_alias": repo[
                        "repo_name"
                    ],  # Map repo_name → golden_repo_alias
                    "current_branch": None,  # Global repos are read-only snapshots
                    "is_global": True,
                    "repo_url": repo.get("repo_url"),
                    "last_refresh": repo.get("last_refresh"),
                    "index_path": repo.get(
                        "index_path"
                    ),  # Preserve for backward compatibility
                    "created_at": repo.get("created_at"),  # Preserve creation timestamp
                }
                global_repos.append(normalized)

        except Exception as e:
            # Log but don't fail - continue with activated repos only
            logger.warning(
                f"Failed to load global repos from {golden_repos_dir}: {e}",
                exc_info=True,
            )

        # Merge activated and global repos
        all_repos = activated_repos + global_repos

        return _mcp_response({"success": True, "repositories": all_repos})
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "repositories": []})


async def activate_repository(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Activate a repository for querying (supports single or composite)."""
    try:
        job_id = app_module.activated_repo_manager.activate_repository(
            username=user.username,
            golden_repo_alias=params.get("golden_repo_alias"),
            golden_repo_aliases=params.get("golden_repo_aliases"),
            branch_name=params.get("branch_name"),
            user_alias=params.get("user_alias"),
        )
        return _mcp_response(
            {
                "success": True,
                "job_id": job_id,
                "message": "Repository activation started",
            }
        )
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "job_id": None})


async def deactivate_repository(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Deactivate a repository."""
    try:
        user_alias = params["user_alias"]
        job_id = app_module.activated_repo_manager.deactivate_repository(
            username=user.username, user_alias=user_alias
        )
        return _mcp_response(
            {
                "success": True,
                "job_id": job_id,
                "message": f"Repository '{user_alias}' deactivation started",
            }
        )
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "job_id": None})


async def get_repository_status(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Get detailed status of a repository."""
    from pathlib import Path

    try:
        user_alias = params["repository_alias"]

        # Check if this is a global repository (ends with -global suffix)
        if user_alias and user_alias.endswith("-global"):
            golden_repos_dir = _get_golden_repos_dir()
            registry = GlobalRegistry(golden_repos_dir)
            global_repos = registry.list_global_repos()

            repo_entry = next(
                (r for r in global_repos if r["alias_name"] == user_alias), None
            )

            if not repo_entry:
                return _mcp_response(
                    {
                        "success": False,
                        "error": f"Global repository '{user_alias}' not found",
                        "status": {},
                    }
                )

            # Build status directly from registry entry (no alias file needed)
            status = {
                "user_alias": repo_entry["alias_name"],
                "golden_repo_alias": repo_entry.get("repo_name"),
                "repo_url": repo_entry.get("repo_url"),
                "is_global": True,
                "path": repo_entry.get("index_path"),
                "last_refresh": repo_entry.get("last_refresh"),
                "created_at": repo_entry.get("created_at"),
                "index_path": repo_entry.get("index_path"),
            }
            return _mcp_response({"success": True, "status": status})

        # Activated repository (original code)
        status = app_module.repository_listing_manager.get_repository_details(
            user_alias, user.username
        )
        return _mcp_response({"success": True, "status": status})
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "status": {}})


async def sync_repository(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Sync repository with upstream."""
    try:
        user_alias = params["user_alias"]
        # Resolve alias to repository details
        repos = app_module.activated_repo_manager.list_activated_repositories(
            user.username
        )
        repo_id = None
        for repo in repos:
            if repo["user_alias"] == user_alias:
                repo_id = repo.get("actual_repo_id", user_alias)
                break

        if not repo_id:
            return _mcp_response(
                {
                    "success": False,
                    "error": f"Repository '{user_alias}' not found",
                    "job_id": None,
                }
            )

        # Defensive check
        if app_module.background_job_manager is None:
            return _mcp_response(
                {
                    "success": False,
                    "error": "Background job manager not initialized",
                    "job_id": None,
                }
            )

        # Create sync job wrapper function
        from code_indexer.server.app import _execute_repository_sync

        def sync_job_wrapper():
            return _execute_repository_sync(
                repo_id=repo_id,
                username=user.username,
                options={},
                progress_callback=None,
            )

        # Submit sync job with correct signature
        job_id = app_module.background_job_manager.submit_job(
            operation_type="sync_repository",
            func=sync_job_wrapper,
            submitter_username=user.username,
        )
        return _mcp_response(
            {
                "success": True,
                "job_id": job_id,
                "message": f"Repository '{user_alias}' sync started",
            }
        )
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "job_id": None})


async def switch_branch(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Switch repository to different branch."""
    try:
        user_alias = params["user_alias"]
        branch_name = params["branch_name"]
        create = params.get("create", False)

        # Use activated_repo_manager.switch_branch (matches app.py endpoint pattern)
        result = app_module.activated_repo_manager.switch_branch(
            username=user.username,
            user_alias=user_alias,
            branch_name=branch_name,
            create=create,
        )
        return _mcp_response({"success": True, "message": result["message"]})
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e)})


async def list_files(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """List files in a repository."""
    from code_indexer.server.models.api_models import FileListQueryParams
    from pathlib import Path

    try:
        repository_alias = params["repository_alias"]
        path_filter = params.get("path", "")

        # Check if this is a global repository (ends with -global suffix)
        if repository_alias and repository_alias.endswith("-global"):
            # Look up global repo in GlobalRegistry to get actual path
            golden_repos_dir = _get_golden_repos_dir()

            registry = GlobalRegistry(golden_repos_dir)
            global_repos = registry.list_global_repos()

            # Find the matching global repo
            repo_entry = next(
                (r for r in global_repos if r["alias_name"] == repository_alias), None
            )

            if not repo_entry:
                return _mcp_response(
                    {
                        "success": False,
                        "error": f"Global repository '{repository_alias}' not found",
                        "files": [],
                    }
                )

            # Use AliasManager to get current target path (registry path becomes stale after refresh)
            from code_indexer.global_repos.alias_manager import AliasManager

            alias_manager = AliasManager(str(Path(golden_repos_dir) / "aliases"))
            target_path = alias_manager.read_alias(repository_alias)

            if not target_path:
                return _mcp_response(
                    {
                        "success": False,
                        "error": f"Alias for '{repository_alias}' not found",
                        "files": [],
                    }
                )

            # Use resolved path instead of alias for file_service
            query_params = FileListQueryParams(
                page=1,
                limit=500,  # Max limit for MCP tool usage
                path_pattern=path_filter if path_filter else None,
            )

            result = app_module.file_service.list_files_by_path(
                repo_path=target_path,
                query_params=query_params,
            )
        else:
            # Create FileListQueryParams object as required by service method signature
            query_params = FileListQueryParams(
                page=1,
                limit=500,  # Max limit for MCP tool usage
                path_pattern=path_filter if path_filter else None,
            )

            # Call with correct signature: list_files(repo_id, username, query_params)
            result = app_module.file_service.list_files(
                repo_id=repository_alias,
                username=user.username,
                query_params=query_params,
            )

        # Extract files from FileListResponse and serialize FileInfo objects
        # Handle both FileListResponse objects and plain dicts
        if hasattr(result, "files"):
            # FileListResponse object with FileInfo objects
            files_data = result.files
        elif isinstance(result, dict):
            # Plain dict (for backward compatibility with tests)
            files_data = result.get("files", [])
        else:
            files_data = []

        # Convert FileInfo Pydantic objects to dicts with proper datetime serialization
        # Use mode='json' to convert datetime objects to ISO format strings
        serialized_files = [
            f.model_dump(mode="json") if hasattr(f, "model_dump") else f
            for f in files_data
        ]

        return _mcp_response({"success": True, "files": serialized_files})
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "files": []})


async def get_file_content(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Get content of a specific file.

    Returns MCP-compliant response with content as array of text blocks.
    Per MCP spec, content must be an array of content blocks, each with 'type' and 'text' fields.
    """
    from pathlib import Path

    try:
        repository_alias = params["repository_alias"]
        file_path = params["file_path"]

        # Check if this is a global repository (ends with -global suffix)
        if repository_alias and repository_alias.endswith("-global"):
            # Look up global repo in GlobalRegistry to get actual path
            golden_repos_dir = _get_golden_repos_dir()

            registry = GlobalRegistry(golden_repos_dir)
            global_repos = registry.list_global_repos()

            # Find the matching global repo
            repo_entry = next(
                (r for r in global_repos if r["alias_name"] == repository_alias), None
            )

            if not repo_entry:
                return _mcp_response(
                    {
                        "success": False,
                        "error": f"Global repository '{repository_alias}' not found",
                        "content": [],
                        "metadata": {},
                    }
                )

            # Use AliasManager to get current target path (registry path becomes stale after refresh)
            from code_indexer.global_repos.alias_manager import AliasManager

            alias_manager = AliasManager(str(Path(golden_repos_dir) / "aliases"))
            target_path = alias_manager.read_alias(repository_alias)

            if not target_path:
                return _mcp_response(
                    {
                        "success": False,
                        "error": f"Alias for '{repository_alias}' not found",
                        "content": [],
                        "metadata": {},
                    }
                )

            # Use resolved path for file_service
            result = app_module.file_service.get_file_content_by_path(
                repo_path=target_path,
                file_path=file_path,
            )
        else:
            result = app_module.file_service.get_file_content(
                repository_alias=repository_alias,
                file_path=file_path,
                username=user.username,
            )

        # MCP spec: content must be array of content blocks
        file_content = result.get("content", "")
        content_blocks = (
            [{"type": "text", "text": file_content}] if file_content else []
        )

        return _mcp_response(
            {
                "success": True,
                "content": content_blocks,
                "metadata": result.get("metadata", {}),
            }
        )
    except Exception as e:
        # Even on error, content must be an array (empty array is valid)
        return _mcp_response(
            {"success": False, "error": str(e), "content": [], "metadata": {}}
        )


async def browse_directory(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Browse directory recursively.

    FileListingService doesn't have browse_directory method.
    Use list_files with path patterns instead.
    """
    from code_indexer.server.models.api_models import FileListQueryParams
    from pathlib import Path

    try:
        repository_alias = params["repository_alias"]
        path = params.get("path", "")
        recursive = params.get("recursive", True)
        user_path_pattern = params.get("path_pattern")
        language = params.get("language")
        limit = params.get("limit", 500)
        sort_by = params.get("sort_by", "path")

        # Validate limit range
        if limit < 1:
            limit = 1
        elif limit > 500:
            limit = 500

        # Validate sort_by value
        if sort_by not in ("path", "size", "modified_at"):
            sort_by = "path"

        # Check if this is a global repository (ends with -global suffix)
        if repository_alias and repository_alias.endswith("-global"):
            # Look up global repo in GlobalRegistry to get actual path
            golden_repos_dir = _get_golden_repos_dir()

            registry = GlobalRegistry(golden_repos_dir)
            global_repos = registry.list_global_repos()

            # Find the matching global repo
            repo_entry = next(
                (r for r in global_repos if r["alias_name"] == repository_alias), None
            )

            if not repo_entry:
                return _mcp_response(
                    {
                        "success": False,
                        "error": f"Global repository '{repository_alias}' not found",
                        "structure": {},
                    }
                )

            # Use AliasManager to get current target path (registry path becomes stale after refresh)
            from code_indexer.global_repos.alias_manager import AliasManager

            alias_manager = AliasManager(str(Path(golden_repos_dir) / "aliases"))
            target_path = alias_manager.read_alias(repository_alias)

            if not target_path:
                return _mcp_response(
                    {
                        "success": False,
                        "error": f"Alias for '{repository_alias}' not found",
                        "structure": {},
                    }
                )

            # Use resolved path instead of alias for file_service
            repository_alias = target_path
            is_global_repo = True
        else:
            is_global_repo = False

        # Build path pattern combining path and user's pattern
        final_path_pattern = None
        # Normalize path first (remove trailing slash) - "/" becomes ""
        path = path.rstrip("/") if path else ""
        if path:
            # Base pattern for the specified directory
            base_pattern = f"{path}/**/*" if recursive else f"{path}/*"
            if user_path_pattern:
                # Combine path with user's pattern
                # e.g., path="src", path_pattern="*.py" -> "src/**/*.py"
                if recursive:
                    final_path_pattern = f"{path}/**/{user_path_pattern}"
                else:
                    final_path_pattern = f"{path}/{user_path_pattern}"
            else:
                final_path_pattern = base_pattern
        elif user_path_pattern:
            # Just use the user's pattern directly
            final_path_pattern = user_path_pattern
        # else: final_path_pattern stays None (all files)

        # Use list_files with user-specified limit
        query_params = FileListQueryParams(
            page=1,
            limit=limit,
            path_pattern=final_path_pattern,
            language=language,
            sort_by=sort_by,
        )

        if is_global_repo:
            result = app_module.file_service.list_files_by_path(
                repo_path=repository_alias,
                query_params=query_params,
            )
        else:
            result = app_module.file_service.list_files(
                repo_id=repository_alias,
                username=user.username,
                query_params=query_params,
            )

        # Convert FileInfo objects to dict structure
        files_data = (
            result.files if hasattr(result, "files") else result.get("files", [])
        )
        serialized_files = [
            f.model_dump(mode="json") if hasattr(f, "model_dump") else f
            for f in files_data
        ]

        # Build directory structure from file list
        structure = {
            "path": path or "/",
            "files": serialized_files,
            "total": len(serialized_files),
        }

        return _mcp_response({"success": True, "structure": structure})
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "structure": {}})


async def get_branches(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Get available branches for a repository."""
    from pathlib import Path
    from code_indexer.services.git_topology_service import GitTopologyService
    from code_indexer.server.services.branch_service import BranchService

    try:
        repository_alias = params["repository_alias"]
        include_remote = params.get("include_remote", False)

        # Check if this is a global repository (ends with -global suffix)
        if repository_alias and repository_alias.endswith("-global"):
            # Look up global repo in GlobalRegistry to get actual path
            golden_repos_dir = _get_golden_repos_dir()

            registry = GlobalRegistry(golden_repos_dir)
            global_repos = registry.list_global_repos()

            # Find the matching global repo
            repo_entry = next(
                (r for r in global_repos if r["alias_name"] == repository_alias), None
            )

            if not repo_entry:
                return _mcp_response(
                    {
                        "success": False,
                        "error": f"Global repository '{repository_alias}' not found",
                        "branches": [],
                    }
                )

            # Use AliasManager to get current target path (registry path becomes stale after refresh)
            from code_indexer.global_repos.alias_manager import AliasManager

            alias_manager = AliasManager(str(Path(golden_repos_dir) / "aliases"))
            target_path = alias_manager.read_alias(repository_alias)

            if not target_path:
                return _mcp_response(
                    {
                        "success": False,
                        "error": f"Alias for '{repository_alias}' not found",
                        "branches": [],
                    }
                )

            # Use resolved path for git operations
            repo_path = target_path
        else:
            # Get repository path (matches app.py endpoint pattern at line 4383-4395)
            repo_path = app_module.activated_repo_manager.get_activated_repo_path(
                username=user.username,
                user_alias=repository_alias,
            )

        # Initialize git topology service
        git_topology_service = GitTopologyService(Path(repo_path))

        # Use BranchService as context manager (matches app.py pattern at line 4404-4408)
        with BranchService(
            git_topology_service=git_topology_service, index_status_manager=None
        ) as branch_service:
            # Get branch information
            branches = branch_service.list_branches(include_remote=include_remote)

            # Convert BranchInfo objects to dicts for JSON serialization
            branches_data = [
                {
                    "name": b.name,
                    "is_current": b.is_current,
                    "last_commit": {
                        "sha": b.last_commit.sha,
                        "message": b.last_commit.message,
                        "author": b.last_commit.author,
                        "date": b.last_commit.date,
                    },
                    "index_status": (
                        {
                            "status": b.index_status.status,
                            "files_indexed": b.index_status.files_indexed,
                            "total_files": b.index_status.total_files,
                            "last_indexed": b.index_status.last_indexed,
                            "progress_percentage": b.index_status.progress_percentage,
                        }
                        if b.index_status
                        else None
                    ),
                    "remote_tracking": (
                        {
                            "remote": b.remote_tracking.remote,
                            "ahead": b.remote_tracking.ahead,
                            "behind": b.remote_tracking.behind,
                        }
                        if b.remote_tracking
                        else None
                    ),
                }
                for b in branches
            ]

            return _mcp_response({"success": True, "branches": branches_data})
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "branches": []})


async def check_health(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Check system health status."""
    try:
        from code_indexer.server.services.health_service import health_service

        # Call the actual method (not async)
        health_response = health_service.get_system_health()
        # Use mode='json' to serialize datetime objects to ISO format strings
        return _mcp_response(
            {"success": True, "health": health_response.model_dump(mode="json")}
        )
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "health": {}})


async def add_golden_repo(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Add a golden repository (admin only).

    Supports temporal indexing via enable_temporal and temporal_options parameters.
    When enable_temporal=True, the repository will be indexed with --index-commits
    to support time-based searches (git history search).
    """
    try:
        repo_url = params["url"]
        alias = params["alias"]
        default_branch = params.get("branch", "main")

        # Extract temporal indexing parameters (Story #527)
        enable_temporal = params.get("enable_temporal", False)
        temporal_options = params.get("temporal_options")

        job_id = app_module.golden_repo_manager.add_golden_repo(
            repo_url=repo_url,
            alias=alias,
            default_branch=default_branch,
            enable_temporal=enable_temporal,
            temporal_options=temporal_options,
            submitter_username=user.username,
        )
        return _mcp_response(
            {
                "success": True,
                "job_id": job_id,
                "message": f"Golden repository '{alias}' addition started",
            }
        )
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e)})


async def remove_golden_repo(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Remove a golden repository (admin only)."""
    try:
        alias = params["alias"]
        job_id = app_module.golden_repo_manager.remove_golden_repo(
            alias, submitter_username=user.username
        )
        return _mcp_response(
            {
                "success": True,
                "job_id": job_id,
                "message": f"Golden repository '{alias}' removal started",
            }
        )
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e)})


async def refresh_golden_repo(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Refresh a golden repository (admin only)."""
    try:
        alias = params["alias"]
        job_id = app_module.golden_repo_manager.refresh_golden_repo(
            alias, submitter_username=user.username
        )
        return _mcp_response(
            {
                "success": True,
                "job_id": job_id,
                "message": f"Golden repository '{alias}' refresh started",
            }
        )
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "job_id": None})


async def list_users(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """List all users (admin only)."""
    try:
        all_users = app_module.user_manager.get_all_users()
        return _mcp_response(
            {
                "success": True,
                "users": [
                    {
                        "username": u.username,
                        "role": u.role.value,
                        "created_at": u.created_at.isoformat(),
                    }
                    for u in all_users
                ],
                "total": len(all_users),
            }
        )
    except Exception as e:
        return _mcp_response(
            {"success": False, "error": str(e), "users": [], "total": 0}
        )


async def create_user(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Create a new user (admin only)."""
    try:
        username = params["username"]
        password = params["password"]
        role = UserRole(params["role"])

        new_user = app_module.user_manager.create_user(
            username=username, password=password, role=role
        )
        return _mcp_response(
            {
                "success": True,
                "user": {
                    "username": new_user.username,
                    "role": new_user.role.value,
                    "created_at": new_user.created_at.isoformat(),
                },
                "message": f"User '{username}' created successfully",
            }
        )
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "user": None})


async def get_repository_statistics(
    params: Dict[str, Any], user: User
) -> Dict[str, Any]:
    """Get repository statistics."""
    from pathlib import Path

    try:
        repository_alias = params["repository_alias"]

        # Check if this is a global repository (ends with -global suffix)
        if repository_alias and repository_alias.endswith("-global"):
            golden_repos_dir = _get_golden_repos_dir()
            registry = GlobalRegistry(golden_repos_dir)
            global_repos = registry.list_global_repos()

            repo_entry = next(
                (r for r in global_repos if r["alias_name"] == repository_alias), None
            )

            if not repo_entry:
                return _mcp_response(
                    {
                        "success": False,
                        "error": f"Global repository '{repository_alias}' not found",
                        "statistics": {},
                    }
                )

            from code_indexer.global_repos.alias_manager import AliasManager

            alias_manager = AliasManager(str(Path(golden_repos_dir) / "aliases"))
            target_path = alias_manager.read_alias(repository_alias)

            if not target_path:
                return _mcp_response(
                    {
                        "success": False,
                        "error": f"Alias for '{repository_alias}' not found",
                        "statistics": {},
                    }
                )

            # Build basic statistics for global repo
            statistics = {
                "repository_alias": repository_alias,
                "is_global": True,
                "path": target_path,
                "index_path": repo_entry.get("index_path"),
            }
            return _mcp_response({"success": True, "statistics": statistics})

        # Activated repository (original code)
        from code_indexer.server.services.stats_service import stats_service

        stats_response = stats_service.get_repository_stats(
            repository_alias, username=user.username
        )
        return _mcp_response(
            {"success": True, "statistics": stats_response.model_dump(mode="json")}
        )
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "statistics": {}})


async def get_job_statistics(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Get background job statistics.

    BackgroundJobManager doesn't have get_job_statistics method.
    Use get_active_job_count, get_pending_job_count, get_failed_job_count instead.
    """
    try:
        active = app_module.background_job_manager.get_active_job_count()
        pending = app_module.background_job_manager.get_pending_job_count()
        failed = app_module.background_job_manager.get_failed_job_count()

        stats = {
            "active": active,
            "pending": pending,
            "failed": failed,
            "total": active + pending + failed,
        }

        return _mcp_response({"success": True, "statistics": stats})
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "statistics": {}})


async def get_all_repositories_status(
    params: Dict[str, Any], user: User
) -> Dict[str, Any]:
    """Get status summary of all repositories."""
    try:
        # Get activated repos status
        repos = app_module.activated_repo_manager.list_activated_repositories(
            user.username
        )
        status_summary = []
        for repo in repos:
            try:
                details = app_module.repository_listing_manager.get_repository_details(
                    repo["user_alias"], user.username
                )
                status_summary.append(details)
            except Exception:
                continue

        # Get global repos status (same pattern as list_repositories handler)
        try:
            golden_repos_dir = _get_golden_repos_dir()
            registry = GlobalRegistry(golden_repos_dir)
            global_repos_data = registry.list_global_repos()

            for repo in global_repos_data:
                if "alias_name" not in repo or "repo_name" not in repo:
                    logger.warning(f"Skipping malformed global repo entry: {repo}")
                    continue

                global_status = {
                    "user_alias": repo["alias_name"],
                    "golden_repo_alias": repo["repo_name"],
                    "current_branch": None,
                    "is_global": True,
                    "repo_url": repo.get("repo_url"),
                    "last_refresh": repo.get("last_refresh"),
                    "index_path": repo.get("index_path"),
                    "created_at": repo.get("created_at"),
                }
                status_summary.append(global_status)
        except Exception as e:
            logger.warning(f"Failed to load global repos status: {e}", exc_info=True)

        return _mcp_response(
            {
                "success": True,
                "repositories": status_summary,
                "total": len(status_summary),
            }
        )
    except Exception as e:
        return _mcp_response(
            {"success": False, "error": str(e), "repositories": [], "total": 0}
        )


async def manage_composite_repository(
    params: Dict[str, Any], user: User
) -> Dict[str, Any]:
    """Manage composite repository operations."""
    try:
        operation = params["operation"]
        user_alias = params["user_alias"]
        golden_repo_aliases = params.get("golden_repo_aliases", [])

        if operation == "create":
            job_id = app_module.activated_repo_manager.activate_repository(
                username=user.username,
                golden_repo_aliases=golden_repo_aliases,
                user_alias=user_alias,
            )
            return _mcp_response(
                {
                    "success": True,
                    "job_id": job_id,
                    "message": f"Composite repository '{user_alias}' creation started",
                }
            )

        elif operation == "update":
            # For update, deactivate then reactivate
            try:
                app_module.activated_repo_manager.deactivate_repository(
                    username=user.username, user_alias=user_alias
                )
            except Exception:
                pass  # Ignore if doesn't exist

            job_id = app_module.activated_repo_manager.activate_repository(
                username=user.username,
                golden_repo_aliases=golden_repo_aliases,
                user_alias=user_alias,
            )
            return _mcp_response(
                {
                    "success": True,
                    "job_id": job_id,
                    "message": f"Composite repository '{user_alias}' update started",
                }
            )

        elif operation == "delete":
            job_id = app_module.activated_repo_manager.deactivate_repository(
                username=user.username, user_alias=user_alias
            )
            return _mcp_response(
                {
                    "success": True,
                    "job_id": job_id,
                    "message": f"Composite repository '{user_alias}' deletion started",
                }
            )

        else:
            return _mcp_response(
                {"success": False, "error": f"Unknown operation: {operation}"}
            )

    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "job_id": None})


async def handle_list_global_repos(args: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Handler for list_global_repos tool."""
    from code_indexer.global_repos.shared_operations import GlobalRepoOperations

    golden_repos_dir = _get_golden_repos_dir()
    ops = GlobalRepoOperations(golden_repos_dir)
    repos = ops.list_repos()
    return _mcp_response({"success": True, "repos": repos})


async def handle_global_repo_status(args: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Handler for global_repo_status tool."""
    from code_indexer.global_repos.shared_operations import GlobalRepoOperations

    golden_repos_dir = _get_golden_repos_dir()
    ops = GlobalRepoOperations(golden_repos_dir)
    alias = args.get("alias")

    if not alias:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: alias"}
        )

    try:
        status = ops.get_status(alias)
        return _mcp_response({"success": True, **status})
    except ValueError:
        return _mcp_response(
            {"success": False, "error": f"Global repo '{alias}' not found"}
        )


async def handle_get_global_config(args: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Handler for get_global_config tool."""
    from code_indexer.global_repos.shared_operations import GlobalRepoOperations

    golden_repos_dir = _get_golden_repos_dir()
    ops = GlobalRepoOperations(golden_repos_dir)
    config = ops.get_config()
    return _mcp_response({"success": True, **config})


async def handle_set_global_config(args: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Handler for set_global_config tool."""
    from code_indexer.global_repos.shared_operations import GlobalRepoOperations

    golden_repos_dir = _get_golden_repos_dir()
    ops = GlobalRepoOperations(golden_repos_dir)
    refresh_interval = args.get("refresh_interval")

    if not refresh_interval:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: refresh_interval"}
        )

    try:
        ops.set_config(refresh_interval)
        return _mcp_response(
            {"success": True, "status": "updated", "refresh_interval": refresh_interval}
        )
    except ValueError as e:
        return _mcp_response({"success": False, "error": str(e)})




async def handle_regex_search(args: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Handler for regex_search tool - pattern matching in repository files."""
    from pathlib import Path
    from code_indexer.global_repos.regex_search import RegexSearchService

    repo_identifier = args.get("repo_identifier")
    pattern = args.get("pattern")

    # Validate required parameters
    if not repo_identifier:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: repo_identifier"}
        )
    if not pattern:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: pattern"}
        )

    try:
        golden_repos_dir = _get_golden_repos_dir()

        # Resolve repo_identifier to actual path
        # Check if it's a global repo alias
        if repo_identifier.endswith("-global"):
            from code_indexer.global_repos.global_registry import GlobalRegistry

            registry = GlobalRegistry(golden_repos_dir)
            repo_entry = registry.get_global_repo(repo_identifier)

            if not repo_entry:
                return _mcp_response(
                    {"success": False, "error": f"Repository '{repo_identifier}' not found"}
                )

            # Use index_path from registry entry directly
            index_path = repo_entry.get("index_path")
            if not index_path:
                return _mcp_response(
                    {"success": False, "error": f"Index path for '{repo_identifier}' not found"}
                )

            repo_path = Path(index_path)
        else:
            # Try as full path or check registry without -global suffix
            repo_path = Path(repo_identifier)
            if not repo_path.exists():
                # Try adding -global suffix
                from code_indexer.global_repos.global_registry import GlobalRegistry

                registry = GlobalRegistry(golden_repos_dir)
                repo_entry = registry.get_global_repo(f"{repo_identifier}-global")

                if repo_entry:
                    index_path = repo_entry.get("index_path")
                    if index_path:
                        repo_path = Path(index_path)
                    else:
                        return _mcp_response(
                            {"success": False, "error": f"Repository '{repo_identifier}' not found"}
                        )
                else:
                    return _mcp_response(
                        {"success": False, "error": f"Repository '{repo_identifier}' not found"}
                    )

        if not repo_path.exists():
            return _mcp_response(
                {"success": False, "error": f"Repository path does not exist: {repo_path}"}
            )

        # Create service and execute search
        service = RegexSearchService(repo_path)
        result = service.search(
            pattern=pattern,
            path=args.get("path"),
            include_patterns=args.get("include_patterns"),
            exclude_patterns=args.get("exclude_patterns"),
            case_sensitive=args.get("case_sensitive", True),
            context_lines=args.get("context_lines", 0),
            max_results=args.get("max_results", 100),
        )

        # Convert dataclass to dict for JSON serialization
        matches = [
            {
                "file_path": m.file_path,
                "line_number": m.line_number,
                "column": m.column,
                "line_content": m.line_content,
                "context_before": m.context_before,
                "context_after": m.context_after,
            }
            for m in result.matches
        ]

        return _mcp_response(
            {
                "success": True,
                "matches": matches,
                "total_matches": result.total_matches,
                "truncated": result.truncated,
                "search_engine": result.search_engine,
                "search_time_ms": result.search_time_ms,
            }
        )

    except Exception as e:
        logger.exception(f"Error in regex_search: {e}")
        return _mcp_response({"success": False, "error": str(e)})

# Handler registry mapping tool names to handler functions
HANDLER_REGISTRY = {
    "search_code": search_code,
    "discover_repositories": discover_repositories,
    "list_repositories": list_repositories,
    "activate_repository": activate_repository,
    "deactivate_repository": deactivate_repository,
    "get_repository_status": get_repository_status,
    "sync_repository": sync_repository,
    "switch_branch": switch_branch,
    "list_files": list_files,
    "get_file_content": get_file_content,
    "browse_directory": browse_directory,
    "get_branches": get_branches,
    "check_health": check_health,
    "add_golden_repo": add_golden_repo,
    "remove_golden_repo": remove_golden_repo,
    "refresh_golden_repo": refresh_golden_repo,
    "list_users": list_users,
    "create_user": create_user,
    "get_repository_statistics": get_repository_statistics,
    "get_job_statistics": get_job_statistics,
    "get_all_repositories_status": get_all_repositories_status,
    "manage_composite_repository": manage_composite_repository,
    "list_global_repos": handle_list_global_repos,
    "global_repo_status": handle_global_repo_status,
    "get_global_config": handle_get_global_config,
    "set_global_config": handle_set_global_config,
    "regex_search": handle_regex_search,
}


async def handle_git_log(args: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Handler for git_log tool - retrieve commit history from a repository."""
    from pathlib import Path
    from code_indexer.global_repos.git_operations import GitOperationsService

    repo_identifier = args.get("repo_identifier")

    # Validate required parameters
    if not repo_identifier:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: repo_identifier"}
        )

    try:
        golden_repos_dir = _get_golden_repos_dir()

        # Resolve repo_identifier to actual path
        repo_path = _resolve_repo_path(repo_identifier, golden_repos_dir)
        if repo_path is None:
            return _mcp_response(
                {"success": False, "error": f"Repository '{repo_identifier}' not found"}
            )

        # Create service and execute query
        service = GitOperationsService(Path(repo_path))
        result = service.get_log(
            limit=args.get("limit", 50),
            path=args.get("path"),
            author=args.get("author"),
            since=args.get("since"),
            until=args.get("until"),
            branch=args.get("branch"),
        )

        # Convert dataclasses to dicts for JSON serialization
        commits = [
            {
                "hash": c.hash,
                "short_hash": c.short_hash,
                "author_name": c.author_name,
                "author_email": c.author_email,
                "author_date": c.author_date,
                "committer_name": c.committer_name,
                "committer_email": c.committer_email,
                "committer_date": c.committer_date,
                "subject": c.subject,
                "body": c.body,
            }
            for c in result.commits
        ]

        return _mcp_response(
            {
                "success": True,
                "commits": commits,
                "total_count": result.total_count,
                "truncated": result.truncated,
            }
        )

    except Exception as e:
        logger.exception(f"Error in git_log: {e}")
        return _mcp_response({"success": False, "error": str(e)})


async def handle_git_show_commit(args: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Handler for git_show_commit tool - get detailed commit information."""
    from pathlib import Path
    from code_indexer.global_repos.git_operations import GitOperationsService

    repo_identifier = args.get("repo_identifier")
    commit_hash = args.get("commit_hash")

    # Validate required parameters
    if not repo_identifier:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: repo_identifier"}
        )
    if not commit_hash:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: commit_hash"}
        )

    try:
        golden_repos_dir = _get_golden_repos_dir()

        # Resolve repo_identifier to actual path
        repo_path = _resolve_repo_path(repo_identifier, golden_repos_dir)
        if repo_path is None:
            return _mcp_response(
                {"success": False, "error": f"Repository '{repo_identifier}' not found"}
            )

        # Create service and execute query
        service = GitOperationsService(Path(repo_path))
        result = service.show_commit(
            commit_hash=commit_hash,
            include_diff=args.get("include_diff", False),
            include_stats=args.get("include_stats", True),
        )

        # Convert dataclasses to dicts for JSON serialization
        commit_dict = {
            "hash": result.commit.hash,
            "short_hash": result.commit.short_hash,
            "author_name": result.commit.author_name,
            "author_email": result.commit.author_email,
            "author_date": result.commit.author_date,
            "committer_name": result.commit.committer_name,
            "committer_email": result.commit.committer_email,
            "committer_date": result.commit.committer_date,
            "subject": result.commit.subject,
            "body": result.commit.body,
        }

        stats_list = None
        if result.stats is not None:
            stats_list = [
                {
                    "path": s.path,
                    "insertions": s.insertions,
                    "deletions": s.deletions,
                    "status": s.status,
                }
                for s in result.stats
            ]

        return _mcp_response(
            {
                "success": True,
                "commit": commit_dict,
                "stats": stats_list,
                "diff": result.diff,
                "parents": result.parents,
            }
        )

    except ValueError as e:
        return _mcp_response({"success": False, "error": str(e)})
    except Exception as e:
        logger.exception(f"Error in git_show_commit: {e}")
        return _mcp_response({"success": False, "error": str(e)})


async def handle_git_file_at_revision(args: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Handler for git_file_at_revision tool - get file contents at specific revision."""
    from pathlib import Path
    from code_indexer.global_repos.git_operations import GitOperationsService

    repo_identifier = args.get("repo_identifier")
    path = args.get("path")
    revision = args.get("revision")

    # Validate required parameters
    if not repo_identifier:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: repo_identifier"}
        )
    if not path:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: path"}
        )
    if not revision:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: revision"}
        )

    try:
        golden_repos_dir = _get_golden_repos_dir()

        # Resolve repo_identifier to actual path
        repo_path = _resolve_repo_path(repo_identifier, golden_repos_dir)
        if repo_path is None:
            return _mcp_response(
                {"success": False, "error": f"Repository '{repo_identifier}' not found"}
            )

        # Create service and execute query
        service = GitOperationsService(Path(repo_path))
        result = service.get_file_at_revision(path=path, revision=revision)

        return _mcp_response(
            {
                "success": True,
                "path": result.path,
                "revision": result.revision,
                "resolved_revision": result.resolved_revision,
                "content": result.content,
                "size_bytes": result.size_bytes,
            }
        )

    except ValueError as e:
        return _mcp_response({"success": False, "error": str(e)})
    except Exception as e:
        logger.exception(f"Error in git_file_at_revision: {e}")
        return _mcp_response({"success": False, "error": str(e)})




def _is_git_repo(path: Path) -> bool:
    """Check if path is a valid git repository."""
    return path.exists() and (path / ".git").exists()


def _find_latest_versioned_repo(base_path: Path, repo_name: str) -> Optional[str]:
    """Find most recent versioned git repo in .versioned/{name}/v_*/ structure."""
    versioned_base = base_path / ".versioned" / repo_name
    if not versioned_base.exists():
        return None

    version_dirs = sorted(
        [d for d in versioned_base.iterdir() if d.is_dir() and d.name.startswith("v_")],
        key=lambda d: d.name,
        reverse=True
    )

    for version_dir in version_dirs:
        if _is_git_repo(version_dir):
            return str(version_dir)

    return None


def _resolve_repo_path(repo_identifier: str, golden_repos_dir: str) -> Optional[str]:
    """Resolve repository identifier to filesystem path with actual git repo.

    Searches multiple locations to find a directory with .git:
    1. The index_path from registry (if it has .git)
    2. The golden-repos/{name} directory
    3. The golden-repos/repos/{name} directory
    4. Versioned repos in .versioned/{name}/v_*/

    Args:
        repo_identifier: Repository alias or path
        golden_repos_dir: Path to golden repos directory

    Returns:
        Filesystem path to git repository, or None if not found
    """
    # Try as full path first
    if not repo_identifier.endswith("-global"):
        repo_path = Path(repo_identifier)
        if _is_git_repo(repo_path):
            return str(repo_path)
        # Try adding -global suffix
        repo_identifier = f"{repo_identifier}-global"

    # Look up in global registry
    registry = GlobalRegistry(golden_repos_dir)
    repo_entry = registry.get_global_repo(repo_identifier)

    if not repo_entry:
        return None

    # Get repo name without -global suffix
    repo_name = repo_identifier.replace("-global", "")

    # Try 1: index_path directly (might be a git repo in test environments)
    index_path = repo_entry.get("index_path")
    if index_path:
        index_path_obj = Path(index_path)
        if _is_git_repo(index_path_obj):
            return index_path

    # Get base directory (.cidx-server/)
    base_dir = Path(golden_repos_dir).parent.parent

    # Try 2: Check golden-repos/{name}
    alt_path = base_dir / "golden-repos" / repo_name
    if _is_git_repo(alt_path):
        return str(alt_path)

    # Try 3: Check golden-repos/repos/{name}
    alt_path = base_dir / "golden-repos" / "repos" / repo_name
    if _is_git_repo(alt_path):
        return str(alt_path)

    # Try 4: Check versioned repos in data/golden-repos/.versioned
    versioned_path = _find_latest_versioned_repo(Path(golden_repos_dir), repo_name)
    if versioned_path:
        return versioned_path

    # Try 5: Check versioned repos in alternative location
    versioned_path = _find_latest_versioned_repo(base_dir / "data" / "golden-repos", repo_name)
    if versioned_path:
        return versioned_path

    return None



# Update handler registry with git exploration tools
HANDLER_REGISTRY["git_log"] = handle_git_log
HANDLER_REGISTRY["git_show_commit"] = handle_git_show_commit
HANDLER_REGISTRY["git_file_at_revision"] = handle_git_file_at_revision


# Story #555: Git Diff and Blame handlers
async def handle_git_diff(args: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Handler for git_diff tool - get diff between revisions."""
    from pathlib import Path
    from code_indexer.global_repos.git_operations import GitOperationsService

    repo_identifier = args.get("repo_identifier")
    from_revision = args.get("from_revision")

    # Validate required parameters
    if not repo_identifier:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: repo_identifier"}
        )
    if not from_revision:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: from_revision"}
        )

    try:
        golden_repos_dir = _get_golden_repos_dir()

        # Resolve repo_identifier to actual path
        repo_path = _resolve_repo_path(repo_identifier, golden_repos_dir)
        if repo_path is None:
            return _mcp_response(
                {"success": False, "error": f"Repository '{repo_identifier}' not found"}
            )

        # Create service and execute query
        service = GitOperationsService(Path(repo_path))
        result = service.get_diff(
            from_revision=from_revision,
            to_revision=args.get("to_revision"),
            path=args.get("path"),
            context_lines=args.get("context_lines", 3),
            stat_only=args.get("stat_only", False),
        )

        # Convert dataclasses to dicts for JSON serialization
        files = [
            {
                "path": f.path,
                "old_path": f.old_path,
                "status": f.status,
                "insertions": f.insertions,
                "deletions": f.deletions,
                "hunks": [
                    {
                        "old_start": h.old_start,
                        "old_count": h.old_count,
                        "new_start": h.new_start,
                        "new_count": h.new_count,
                        "content": h.content,
                    }
                    for h in f.hunks
                ],
            }
            for f in result.files
        ]

        return _mcp_response(
            {
                "success": True,
                "from_revision": result.from_revision,
                "to_revision": result.to_revision,
                "files": files,
                "total_insertions": result.total_insertions,
                "total_deletions": result.total_deletions,
                "stat_summary": result.stat_summary,
            }
        )

    except Exception as e:
        logger.exception(f"Error in git_diff: {e}")
        return _mcp_response({"success": False, "error": str(e)})


async def handle_git_blame(args: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Handler for git_blame tool - get line-by-line blame annotations."""
    from pathlib import Path
    from code_indexer.global_repos.git_operations import GitOperationsService

    repo_identifier = args.get("repo_identifier")
    path = args.get("path")

    # Validate required parameters
    if not repo_identifier:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: repo_identifier"}
        )
    if not path:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: path"}
        )

    try:
        golden_repos_dir = _get_golden_repos_dir()

        # Resolve repo_identifier to actual path
        repo_path = _resolve_repo_path(repo_identifier, golden_repos_dir)
        if repo_path is None:
            return _mcp_response(
                {"success": False, "error": f"Repository '{repo_identifier}' not found"}
            )

        # Create service and execute query
        service = GitOperationsService(Path(repo_path))
        result = service.get_blame(
            path=path,
            revision=args.get("revision"),
            start_line=args.get("start_line"),
            end_line=args.get("end_line"),
        )

        # Convert dataclasses to dicts for JSON serialization
        lines = [
            {
                "line_number": line.line_number,
                "commit_hash": line.commit_hash,
                "short_hash": line.short_hash,
                "author_name": line.author_name,
                "author_email": line.author_email,
                "author_date": line.author_date,
                "original_line_number": line.original_line_number,
                "content": line.content,
            }
            for line in result.lines
        ]

        return _mcp_response(
            {
                "success": True,
                "path": result.path,
                "revision": result.revision,
                "lines": lines,
                "unique_commits": result.unique_commits,
            }
        )

    except ValueError as e:
        return _mcp_response({"success": False, "error": str(e)})
    except Exception as e:
        logger.exception(f"Error in git_blame: {e}")
        return _mcp_response({"success": False, "error": str(e)})


async def handle_git_file_history(args: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Handler for git_file_history tool - get commit history for a file."""
    from pathlib import Path
    from code_indexer.global_repos.git_operations import GitOperationsService

    repo_identifier = args.get("repo_identifier")
    path = args.get("path")

    # Validate required parameters
    if not repo_identifier:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: repo_identifier"}
        )
    if not path:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: path"}
        )

    try:
        golden_repos_dir = _get_golden_repos_dir()

        # Resolve repo_identifier to actual path
        repo_path = _resolve_repo_path(repo_identifier, golden_repos_dir)
        if repo_path is None:
            return _mcp_response(
                {"success": False, "error": f"Repository '{repo_identifier}' not found"}
            )

        # Create service and execute query
        service = GitOperationsService(Path(repo_path))
        result = service.get_file_history(
            path=path,
            limit=args.get("limit", 50),
            follow_renames=args.get("follow_renames", True),
        )

        # Convert dataclasses to dicts for JSON serialization
        commits = [
            {
                "hash": c.hash,
                "short_hash": c.short_hash,
                "author_name": c.author_name,
                "author_date": c.author_date,
                "subject": c.subject,
                "insertions": c.insertions,
                "deletions": c.deletions,
                "old_path": c.old_path,
            }
            for c in result.commits
        ]

        return _mcp_response(
            {
                "success": True,
                "path": result.path,
                "commits": commits,
                "total_count": result.total_count,
                "truncated": result.truncated,
                "renamed_from": result.renamed_from,
            }
        )

    except ValueError as e:
        return _mcp_response({"success": False, "error": str(e)})
    except Exception as e:
        logger.exception(f"Error in git_file_history: {e}")
        return _mcp_response({"success": False, "error": str(e)})


# Update handler registry with git diff/blame tools (Story #555)
HANDLER_REGISTRY["git_diff"] = handle_git_diff
HANDLER_REGISTRY["git_blame"] = handle_git_blame
HANDLER_REGISTRY["git_file_history"] = handle_git_file_history


# Story #556: Git Content Search handlers
async def handle_git_search_commits(args: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Handler for git_search_commits tool - search commit messages."""
    from pathlib import Path
    from code_indexer.global_repos.git_operations import GitOperationsService

    repo_identifier = args.get("repo_identifier")
    query = args.get("query")

    # Validate required parameters
    if not repo_identifier:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: repo_identifier"}
        )
    if not query:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: query"}
        )

    try:
        golden_repos_dir = _get_golden_repos_dir()

        # Resolve repo_identifier to actual path
        repo_path = _resolve_repo_path(repo_identifier, golden_repos_dir)
        if repo_path is None:
            return _mcp_response(
                {"success": False, "error": f"Repository '{repo_identifier}' not found"}
            )

        # Create service and execute search
        service = GitOperationsService(Path(repo_path))
        result = service.search_commits(
            query=query,
            is_regex=args.get("is_regex", False),
            author=args.get("author"),
            since=args.get("since"),
            until=args.get("until"),
            limit=args.get("limit", 50),
        )

        # Convert dataclasses to dicts for JSON serialization
        matches = [
            {
                "hash": m.hash,
                "short_hash": m.short_hash,
                "author_name": m.author_name,
                "author_email": m.author_email,
                "author_date": m.author_date,
                "subject": m.subject,
                "body": m.body,
                "match_highlights": m.match_highlights,
            }
            for m in result.matches
        ]

        return _mcp_response(
            {
                "success": True,
                "query": result.query,
                "is_regex": result.is_regex,
                "matches": matches,
                "total_matches": result.total_matches,
                "truncated": result.truncated,
                "search_time_ms": result.search_time_ms,
            }
        )

    except Exception as e:
        logger.exception(f"Error in git_search_commits: {e}")
        return _mcp_response({"success": False, "error": str(e)})


async def handle_git_search_diffs(args: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Handler for git_search_diffs tool - search for code changes (pickaxe search)."""
    from pathlib import Path
    from code_indexer.global_repos.git_operations import GitOperationsService

    repo_identifier = args.get("repo_identifier")
    search_string = args.get("search_string")
    search_pattern = args.get("search_pattern")
    is_regex = args.get("is_regex", False)

    # Validate required parameters
    if not repo_identifier:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: repo_identifier"}
        )

    # Determine which search parameter to use based on is_regex
    search_term = search_pattern if is_regex else search_string

    # Validate that at least one search parameter is provided
    if not search_term:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: search_string or search_pattern"}
        )

    try:
        golden_repos_dir = _get_golden_repos_dir()

        # Resolve repo_identifier to actual path
        repo_path = _resolve_repo_path(repo_identifier, golden_repos_dir)
        if repo_path is None:
            return _mcp_response(
                {"success": False, "error": f"Repository '{repo_identifier}' not found"}
            )

        # Create service and execute search
        # search_diffs uses search_string for literal, search_pattern for regex
        service = GitOperationsService(Path(repo_path))
        is_regex = args.get("is_regex", False)
        if is_regex:
            result = service.search_diffs(
                search_pattern=search_term,
                is_regex=True,
                path=args.get("path"),
                since=args.get("since"),
                until=args.get("until"),
                limit=args.get("limit", 50),
            )
        else:
            result = service.search_diffs(
                search_string=search_term,
                is_regex=False,
                path=args.get("path"),
                since=args.get("since"),
                until=args.get("until"),
                limit=args.get("limit", 50),
            )

        # Convert dataclasses to dicts for JSON serialization
        matches = [
            {
                "hash": m.hash,
                "short_hash": m.short_hash,
                "author_name": m.author_name,
                "author_date": m.author_date,
                "subject": m.subject,
                "files_changed": m.files_changed,
                "diff_snippet": m.diff_snippet,
            }
            for m in result.matches
        ]

        return _mcp_response(
            {
                "success": True,
                "search_term": result.search_term,
                "is_regex": result.is_regex,
                "matches": matches,
                "total_matches": result.total_matches,
                "truncated": result.truncated,
                "search_time_ms": result.search_time_ms,
            }
        )

    except ValueError as e:
        return _mcp_response({"success": False, "error": str(e)})
    except Exception as e:
        logger.exception(f"Error in git_search_diffs: {e}")
        return _mcp_response({"success": False, "error": str(e)})


# Update handler registry with git content search tools (Story #556)
HANDLER_REGISTRY["git_search_commits"] = handle_git_search_commits
HANDLER_REGISTRY["git_search_diffs"] = handle_git_search_diffs


# Story #557: Directory Tree handler
async def handle_directory_tree(args: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Handler for directory_tree tool - generate hierarchical tree view."""
    from pathlib import Path
    from code_indexer.global_repos.directory_explorer import DirectoryExplorerService

    repo_identifier = args.get("repo_identifier")

    # Validate required parameters
    if not repo_identifier:
        return _mcp_response(
            {"success": False, "error": "Missing required parameter: repo_identifier"}
        )

    try:
        golden_repos_dir = _get_golden_repos_dir()

        # Resolve repo_identifier to actual path
        repo_path = _resolve_repo_path(repo_identifier, golden_repos_dir)
        if repo_path is None:
            return _mcp_response(
                {"success": False, "error": f"Repository '{repo_identifier}' not found"}
            )

        # Create service and generate tree
        service = DirectoryExplorerService(Path(repo_path))
        result = service.generate_tree(
            path=args.get("path"),
            max_depth=args.get("max_depth", 3),
            max_files_per_dir=args.get("max_files_per_dir", 50),
            include_patterns=args.get("include_patterns"),
            exclude_patterns=args.get("exclude_patterns"),
            show_stats=args.get("show_stats", False),
            include_hidden=args.get("include_hidden", False),
        )

        # Convert TreeNode to dict recursively
        def tree_node_to_dict(node):
            result_dict = {
                "name": node.name,
                "path": node.path,
                "is_directory": node.is_directory,
                "truncated": node.truncated,
                "hidden_count": node.hidden_count,
            }
            if node.children is not None:
                result_dict["children"] = [tree_node_to_dict(c) for c in node.children]
            else:
                result_dict["children"] = None
            return result_dict

        return _mcp_response(
            {
                "success": True,
                "tree_string": result.tree_string,
                "root": tree_node_to_dict(result.root),
                "total_directories": result.total_directories,
                "total_files": result.total_files,
                "max_depth_reached": result.max_depth_reached,
                "root_path": result.root_path,
            }
        )

    except ValueError as e:
        return _mcp_response({"success": False, "error": str(e)})
    except Exception as e:
        logger.exception(f"Error in directory_tree: {e}")
        return _mcp_response({"success": False, "error": str(e)})


# Update handler registry with directory tree tool (Story #557)
HANDLER_REGISTRY["directory_tree"] = handle_directory_tree

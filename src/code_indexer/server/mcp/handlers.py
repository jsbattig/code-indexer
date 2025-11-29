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
import os
from typing import Dict, Any
from code_indexer.server.auth.user_manager import User, UserRole
from code_indexer.global_repos.global_registry import GlobalRegistry

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
    """Get golden_repos_dir with three-tier fallback strategy.

    Fallback order:
    1. app.state.golden_repos_dir (set during server startup)
    2. GOLDEN_REPOS_DIR environment variable
    3. Default: ~/.code-indexer/golden-repos

    Returns:
        str: Absolute path to golden repos directory
    """
    from code_indexer.server import app
    from typing import Optional, cast

    # PRIMARY: app.state (set during server startup)
    golden_repos_dir: Optional[str] = cast(Optional[str], getattr(app.state, 'golden_repos_dir', None))
    if golden_repos_dir:
        return golden_repos_dir

    # SECONDARY: Environment variable
    golden_repos_dir = os.environ.get("GOLDEN_REPOS_DIR")
    if golden_repos_dir:
        return golden_repos_dir

    # TERTIARY: Default fallback
    return os.path.expanduser("~/.code-indexer/golden-repos")


async def search_code(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Search code using semantic search, FTS, or hybrid mode."""
    try:
        from code_indexer.server import app
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
                (r for r in global_repos if r["alias_name"] == repository_alias),
                None
            )

            if not repo_entry:
                return _mcp_response({
                    "success": False,
                    "error": f"Global repository '{repository_alias}' not found",
                    "results": []
                })

            # Extract actual repo path from index_path
            # index_path is like: /path/to/repo/.code-indexer/index
            # We need: /path/to/repo
            index_path = Path(repo_entry["index_path"])
            global_repo_path = index_path.parent.parent  # Go up two levels from index dir

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
            import time

            start_time = time.time()
            try:
                results = app.semantic_query_manager._perform_search(
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
        result = app.semantic_query_manager.query_user_repositories(
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
            # Temporal query parameters (Story #446)
            time_range=params.get("time_range"),
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
        from code_indexer.server.app import golden_repo_manager

        # List all golden repositories (source_type filter not currently used)
        repos = golden_repo_manager.list_golden_repos()

        return _mcp_response({"success": True, "repositories": repos})
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "repositories": []})


async def list_repositories(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """List activated repositories for the current user, plus global repos."""
    from code_indexer.server import app

    try:
        # Get activated repos from database
        activated_repos = app.activated_repo_manager.list_activated_repositories(
            user.username
        )

        # Get global repos from GlobalRegistry
        global_repos = []
        try:
            golden_repos_dir = _get_golden_repos_dir()
            registry = GlobalRegistry(golden_repos_dir)
            global_repos_data = registry.list_global_repos()

            # Mark global repos with is_global: true
            for repo in global_repos_data:
                repo["is_global"] = True
                global_repos.append(repo)

        except Exception as e:
            # Log but don't fail - continue with activated repos only
            logger.warning(
                f"Failed to load global repos from {golden_repos_dir}: {e}",
                exc_info=True
            )

        # Merge activated and global repos
        all_repos = activated_repos + global_repos

        return _mcp_response({"success": True, "repositories": all_repos})
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "repositories": []})


async def activate_repository(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Activate a repository for querying (supports single or composite)."""
    from code_indexer.server import app

    try:
        job_id = app.activated_repo_manager.activate_repository(
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
    from code_indexer.server import app

    try:
        user_alias = params["user_alias"]
        job_id = app.activated_repo_manager.deactivate_repository(
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
    from code_indexer.server import app

    try:
        user_alias = params["user_alias"]
        status = app.repository_listing_manager.get_repository_details(
            user_alias, user.username
        )
        return _mcp_response({"success": True, "status": status})
    except Exception as e:
        return _mcp_response({"success": False, "error": str(e), "status": {}})


async def sync_repository(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Sync repository with upstream."""
    from code_indexer.server import app

    try:
        user_alias = params["user_alias"]
        # Resolve alias to repository details
        repos = app.activated_repo_manager.list_activated_repositories(user.username)
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
        if (
            not hasattr(app, "background_job_manager")
            or app.background_job_manager is None
        ):
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
        job_id = app.background_job_manager.submit_job(
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
    from code_indexer.server import app

    try:
        user_alias = params["user_alias"]
        branch_name = params["branch_name"]
        create = params.get("create", False)

        # Use activated_repo_manager.switch_branch (matches app.py endpoint pattern)
        result = app.activated_repo_manager.switch_branch(
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
    from code_indexer.server import app
    from code_indexer.server.models.api_models import FileListQueryParams

    try:
        repository_alias = params["repository_alias"]
        path_filter = params.get("path", "")

        # Create FileListQueryParams object as required by service method signature
        query_params = FileListQueryParams(
            page=1,
            limit=500,  # Max limit for MCP tool usage
            path_pattern=path_filter if path_filter else None,
        )

        # Call with correct signature: list_files(repo_id, username, query_params)
        result = app.file_service.list_files(
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
    from code_indexer.server import app

    try:
        repository_alias = params["repository_alias"]
        file_path = params["file_path"]

        result = app.file_service.get_file_content(
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
    from code_indexer.server import app
    from code_indexer.server.models.api_models import FileListQueryParams
    from pathlib import Path

    try:
        repository_alias = params["repository_alias"]
        path = params.get("path", "")
        recursive = params.get("recursive", True)

        # Check if this is a global repository (ends with -global suffix)
        if repository_alias and repository_alias.endswith("-global"):
            # Look up global repo in GlobalRegistry to get actual path
            golden_repos_dir = _get_golden_repos_dir()

            registry = GlobalRegistry(golden_repos_dir)
            global_repos = registry.list_global_repos()

            # Find the matching global repo
            repo_entry = next(
                (r for r in global_repos if r["alias_name"] == repository_alias),
                None
            )

            if not repo_entry:
                return _mcp_response({
                    "success": False,
                    "error": f"Global repository '{repository_alias}' not found",
                    "structure": {}
                })

            # Extract actual repo path from index_path
            # index_path is like: /path/to/repo/.code-indexer/index
            # We need: /path/to/repo
            index_path = Path(repo_entry["index_path"])
            repo_path_resolved = str(index_path.parent.parent)

            # Use resolved path instead of alias for file_service
            repository_alias = repo_path_resolved

        # Build path pattern for recursive search
        path_pattern = None
        if path:
            # Match files under the specified path
            path_pattern = f"{path}/**/*" if recursive else f"{path}/*"

        # Use list_files with max allowed limit to get directory structure
        query_params = FileListQueryParams(
            page=1,
            limit=500,  # Max limit allowed by FileListQueryParams
            path_pattern=path_pattern,
        )

        result = app.file_service.list_files(
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
    from code_indexer.server import app
    from pathlib import Path
    from code_indexer.services.git_topology_service import GitTopologyService
    from code_indexer.server.services.branch_service import BranchService

    try:
        repository_alias = params["repository_alias"]
        include_remote = params.get("include_remote", False)

        # Get repository path (matches app.py endpoint pattern at line 4383-4395)
        repo_path = app.activated_repo_manager.get_activated_repo_path(
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
    """Add a golden repository (admin only)."""
    from code_indexer.server import app

    try:
        repo_url = params["url"]
        alias = params["alias"]
        default_branch = params.get("branch", "main")

        job_id = app.golden_repo_manager.add_golden_repo(
            repo_url=repo_url,
            alias=alias,
            default_branch=default_branch,
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
    from code_indexer.server import app

    try:
        alias = params["alias"]
        job_id = app.golden_repo_manager.remove_golden_repo(
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
    from code_indexer.server import app

    try:
        alias = params["alias"]
        job_id = app.golden_repo_manager.refresh_golden_repo(
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
    from code_indexer.server import app

    try:
        all_users = app.user_manager.get_all_users()
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
    from code_indexer.server import app

    try:
        username = params["username"]
        password = params["password"]
        role = UserRole(params["role"])

        new_user = app.user_manager.create_user(
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
    try:
        from code_indexer.server.services.stats_service import stats_service

        repository_alias = params["repository_alias"]
        # Call with username to lookup activated repository
        stats_response = stats_service.get_repository_stats(
            repository_alias, username=user.username
        )
        # Use mode='json' to serialize datetime objects to ISO format strings
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
    from code_indexer.server import app

    try:
        active = app.background_job_manager.get_active_job_count()
        pending = app.background_job_manager.get_pending_job_count()
        failed = app.background_job_manager.get_failed_job_count()

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
    from code_indexer.server import app

    try:
        repos = app.activated_repo_manager.list_activated_repositories(user.username)
        status_summary = []
        for repo in repos:
            try:
                details = app.repository_listing_manager.get_repository_details(
                    repo["user_alias"], user.username
                )
                status_summary.append(details)
            except Exception:
                # Skip repos that fail to get details
                continue

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
    from code_indexer.server import app

    try:
        operation = params["operation"]
        user_alias = params["user_alias"]
        golden_repo_aliases = params.get("golden_repo_aliases", [])

        if operation == "create":
            job_id = app.activated_repo_manager.activate_repository(
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
                app.activated_repo_manager.deactivate_repository(
                    username=user.username, user_alias=user_alias
                )
            except Exception:
                pass  # Ignore if doesn't exist

            job_id = app.activated_repo_manager.activate_repository(
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
            job_id = app.activated_repo_manager.deactivate_repository(
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
}

"""MCP Tool Handler Functions - Complete implementation for all 22 tools."""

from typing import Dict, Any, Optional
from code_indexer.server.auth.user_manager import User, UserRole
from fastapi import HTTPException


async def search_code(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Search code using semantic search, FTS, or hybrid mode."""
    try:
        from code_indexer.server.services.search_service import search_service
        from code_indexer.server.models.api_models import SemanticSearchRequest

        # Build search request
        search_request = SemanticSearchRequest(
            query=params["query_text"],
            limit=params.get("limit", 10),
            min_score=params.get("min_score", 0.5),
        )

        # Use repository_alias as repo_id
        repo_id = params.get("repository_alias", user.username)

        # Call the actual search_repository method that exists
        result = search_service.search_repository(repo_id, search_request)
        return {"success": True, "results": result.model_dump()}
    except Exception as e:
        return {"success": False, "error": str(e), "results": []}


async def discover_repositories(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Discover available repositories from configured sources."""
    try:
        # Import actual dependencies as done in app.py endpoint
        from code_indexer.server.services.repository_discovery_service import RepositoryDiscoveryService
        from code_indexer.server.app import golden_repo_manager, activated_repo_manager

        # Instantiate service following app.py pattern
        discovery_service = RepositoryDiscoveryService(
            golden_repo_manager=golden_repo_manager,
            activated_repo_manager=activated_repo_manager,
        )

        # Call with source from params
        result = await discovery_service.discover_repositories(
            repo_url=params.get("source", ""),
            user=user,
        )

        return {"success": True, "repositories": result.model_dump()["matching_repositories"]}
    except Exception as e:
        return {"success": False, "error": str(e), "repositories": []}


async def list_repositories(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """List activated repositories for the current user."""
    from code_indexer.server import app

    try:
        repos = app.activated_repo_manager.list_activated_repositories(user.username)
        return {"success": True, "repositories": repos}
    except Exception as e:
        return {"success": False, "error": str(e), "repositories": []}


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
        return {"success": True, "job_id": job_id, "message": "Repository activation started"}
    except Exception as e:
        return {"success": False, "error": str(e), "job_id": None}


async def deactivate_repository(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Deactivate a repository."""
    from code_indexer.server import app

    try:
        user_alias = params["user_alias"]
        job_id = app.activated_repo_manager.deactivate_repository(
            username=user.username, user_alias=user_alias
        )
        return {"success": True, "job_id": job_id, "message": f"Repository '{user_alias}' deactivation started"}
    except Exception as e:
        return {"success": False, "error": str(e), "job_id": None}


async def get_repository_status(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Get detailed status of a repository."""
    from code_indexer.server import app

    try:
        user_alias = params["user_alias"]
        status = app.repository_listing_manager.get_repository_details(
            user_alias, user.username
        )
        return {"success": True, "status": status}
    except Exception as e:
        return {"success": False, "error": str(e), "status": {}}


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
            return {"success": False, "error": f"Repository '{user_alias}' not found", "job_id": None}

        # Submit sync job
        job_id = app.background_job_manager.submit_job(
            operation="sync_repository",
            params={"repo_id": repo_id, "username": user.username},
            username=user.username,
        )
        return {"success": True, "job_id": job_id, "message": f"Repository '{user_alias}' sync started"}
    except Exception as e:
        return {"success": False, "error": str(e), "job_id": None}


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
        return {"success": True, "message": result["message"]}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def list_files(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """List files in a repository."""
    from code_indexer.server import app

    try:
        repository_alias = params["repository_alias"]
        path_filter = params.get("path", "")

        result = await app.file_service.list_files(
            repository_alias=repository_alias,
            username=user.username,
            path=path_filter,
        )
        return {"success": True, "files": result.get("files", [])}
    except Exception as e:
        return {"success": False, "error": str(e), "files": []}


async def get_file_content(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Get content of a specific file."""
    from code_indexer.server import app

    try:
        repository_alias = params["repository_alias"]
        file_path = params["file_path"]

        result = await app.file_service.get_file_content(
            repository_alias=repository_alias,
            file_path=file_path,
            username=user.username,
        )
        return {"success": True, "content": result.get("content", ""), "metadata": result.get("metadata", {})}
    except Exception as e:
        return {"success": False, "error": str(e), "content": "", "metadata": {}}


async def browse_directory(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Browse directory recursively."""
    from code_indexer.server import app

    try:
        repository_alias = params["repository_alias"]
        path = params.get("path", "")
        recursive = params.get("recursive", True)

        result = await app.file_service.browse_directory(
            repository_alias=repository_alias,
            path=path,
            recursive=recursive,
            username=user.username,
        )
        return {"success": True, "structure": result}
    except Exception as e:
        return {"success": False, "error": str(e), "structure": {}}


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
            git_topology_service=git_topology_service, 
            index_status_manager=None
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
                    "index_status": {
                        "status": b.index_status.status,
                        "files_indexed": b.index_status.files_indexed,
                        "total_files": b.index_status.total_files,
                        "last_indexed": b.index_status.last_indexed,
                        "progress_percentage": b.index_status.progress_percentage,
                    } if b.index_status else None,
                    "remote_tracking": {
                        "remote": b.remote_tracking.remote,
                        "ahead": b.remote_tracking.ahead,
                        "behind": b.remote_tracking.behind,
                    } if b.remote_tracking else None,
                }
                for b in branches
            ]
            
            return {"success": True, "branches": branches_data}
    except Exception as e:
        return {"success": False, "error": str(e), "branches": []}


async def check_health(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Check system health status."""
    try:
        from code_indexer.server.services.health_service import health_service

        # Call the actual method (not async)
        health_response = health_service.get_system_health()
        return {"success": True, "health": health_response.model_dump()}
    except Exception as e:
        return {"success": False, "error": str(e), "health": {}}


async def add_golden_repo(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Add a golden repository (admin only)."""
    from code_indexer.server import app

    try:
        repo_url = params["url"]
        alias = params["alias"]
        default_branch = params.get("branch", "main")

        result = app.golden_repo_manager.add_golden_repo(
            repo_url=repo_url, alias=alias, default_branch=default_branch
        )
        return {"success": True, "message": result["message"]}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def remove_golden_repo(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Remove a golden repository (admin only)."""
    from code_indexer.server import app

    try:
        alias = params["alias"]
        app.golden_repo_manager.remove_golden_repo(alias)
        return {"success": True, "message": f"Golden repository '{alias}' removed successfully"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def refresh_golden_repo(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Refresh a golden repository (admin only)."""
    from code_indexer.server import app

    try:
        alias = params["alias"]
        job_id = app.golden_repo_manager.refresh_golden_repo(alias)
        return {"success": True, "job_id": job_id, "message": f"Golden repository '{alias}' refresh started"}
    except Exception as e:
        return {"success": False, "error": str(e), "job_id": None}


async def list_users(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """List all users (admin only)."""
    from code_indexer.server import app

    try:
        all_users = app.user_manager.get_all_users()
        return {
            "success": True,
            "users": [{"username": u.username, "role": u.role.value, "created_at": u.created_at.isoformat()} for u in all_users],
            "total": len(all_users),
        }
    except Exception as e:
        return {"success": False, "error": str(e), "users": [], "total": 0}


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
        return {
            "success": True,
            "user": {
                "username": new_user.username,
                "role": new_user.role.value,
                "created_at": new_user.created_at.isoformat(),
            },
            "message": f"User '{username}' created successfully",
        }
    except Exception as e:
        return {"success": False, "error": str(e), "user": None}


async def get_repository_statistics(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Get repository statistics."""
    try:
        from code_indexer.server.services.stats_service import stats_service

        repository_alias = params["repository_alias"]
        # Call the actual method (not async, different name)
        stats_response = stats_service.get_repository_stats(repository_alias)
        return {"success": True, "statistics": stats_response.model_dump()}
    except Exception as e:
        return {"success": False, "error": str(e), "statistics": {}}


async def get_job_statistics(params: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Get background job statistics."""
    from code_indexer.server import app

    try:
        stats = app.background_job_manager.get_job_statistics()
        return {"success": True, "statistics": stats}
    except Exception as e:
        return {"success": False, "error": str(e), "statistics": {}}


async def get_all_repositories_status(params: Dict[str, Any], user: User) -> Dict[str, Any]:
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

        return {"success": True, "repositories": status_summary, "total": len(status_summary)}
    except Exception as e:
        return {"success": False, "error": str(e), "repositories": [], "total": 0}


async def manage_composite_repository(params: Dict[str, Any], user: User) -> Dict[str, Any]:
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
            return {"success": True, "job_id": job_id, "message": f"Composite repository '{user_alias}' creation started"}

        elif operation == "update":
            # For update, deactivate then reactivate
            try:
                deactivate_job = app.activated_repo_manager.deactivate_repository(
                    username=user.username, user_alias=user_alias
                )
            except Exception:
                pass  # Ignore if doesn't exist

            job_id = app.activated_repo_manager.activate_repository(
                username=user.username,
                golden_repo_aliases=golden_repo_aliases,
                user_alias=user_alias,
            )
            return {"success": True, "job_id": job_id, "message": f"Composite repository '{user_alias}' update started"}

        elif operation == "delete":
            job_id = app.activated_repo_manager.deactivate_repository(
                username=user.username, user_alias=user_alias
            )
            return {"success": True, "job_id": job_id, "message": f"Composite repository '{user_alias}' deletion started"}

        else:
            return {"success": False, "error": f"Unknown operation: {operation}"}

    except Exception as e:
        return {"success": False, "error": str(e), "job_id": None}


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
}

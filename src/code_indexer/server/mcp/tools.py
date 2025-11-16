"""MCP Tool Registry - Defines tools with JSON schemas and role requirements."""

from typing import List, Dict, Any
from code_indexer.server.auth.user_manager import User

# MCP Tool Registry - All 22 tools with complete JSON schemas
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Tools 1-2: Search
    "search_code": {
        "name": "search_code",
        "description": "Search code using semantic search, FTS, or hybrid mode",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query_text": {
                    "type": "string",
                    "description": "Search query text",
                },
                "repository_alias": {
                    "type": "string",
                    "description": "Repository alias to search (optional)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100,
                },
                "min_score": {
                    "type": "number",
                    "description": "Minimum similarity score",
                    "default": 0.5,
                    "minimum": 0,
                    "maximum": 1,
                },
                "search_mode": {
                    "type": "string",
                    "description": "Search mode",
                    "enum": ["semantic", "fts", "hybrid"],
                    "default": "semantic",
                },
            },
            "required": ["query_text"],
        },
        "required_permission": "query_repos",
    },
    "discover_repositories": {
        "name": "discover_repositories",
        "description": "Discover available repositories from configured sources",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_type": {
                    "type": "string",
                    "description": "Source type filter (optional)",
                },
            },
            "required": [],
        },
        "required_permission": "query_repos",
    },
    # Tools 3-8: Repository Management
    "list_repositories": {
        "name": "list_repositories",
        "description": "List activated repositories for the current user",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "required_permission": "query_repos",
    },
    "activate_repository": {
        "name": "activate_repository",
        "description": "Activate a repository for querying (supports single or composite)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "golden_repo_alias": {
                    "type": "string",
                    "description": "Golden repository alias (for single repo)",
                },
                "golden_repo_aliases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Multiple golden repos (for composite)",
                },
                "branch_name": {
                    "type": "string",
                    "description": "Branch to activate (optional)",
                },
                "user_alias": {
                    "type": "string",
                    "description": "User-defined alias (optional)",
                },
            },
            "required": [],
        },
        "required_permission": "activate_repos",
    },
    "deactivate_repository": {
        "name": "deactivate_repository",
        "description": "Deactivate a repository",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_alias": {
                    "type": "string",
                    "description": "User alias of repository to deactivate",
                },
            },
            "required": ["user_alias"],
        },
        "required_permission": "activate_repos",
    },
    "get_repository_status": {
        "name": "get_repository_status",
        "description": "Get detailed status of a repository",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_alias": {
                    "type": "string",
                    "description": "User alias of repository",
                },
            },
            "required": ["user_alias"],
        },
        "required_permission": "query_repos",
    },
    "sync_repository": {
        "name": "sync_repository",
        "description": "Sync repository with upstream",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_alias": {
                    "type": "string",
                    "description": "User alias of repository",
                },
            },
            "required": ["user_alias"],
        },
        "required_permission": "activate_repos",
    },
    "switch_branch": {
        "name": "switch_branch",
        "description": "Switch repository to different branch",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_alias": {
                    "type": "string",
                    "description": "User alias of repository",
                },
                "branch_name": {
                    "type": "string",
                    "description": "Target branch name",
                },
            },
            "required": ["user_alias", "branch_name"],
        },
        "required_permission": "activate_repos",
    },
    # Tools 9-13: Files & Health
    "list_files": {
        "name": "list_files",
        "description": "List files in a repository",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repository_alias": {
                    "type": "string",
                    "description": "Repository alias",
                },
                "path": {
                    "type": "string",
                    "description": "Directory path (optional)",
                },
            },
            "required": ["repository_alias"],
        },
        "required_permission": "query_repos",
    },
    "get_file_content": {
        "name": "get_file_content",
        "description": "Get content of a specific file",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repository_alias": {
                    "type": "string",
                    "description": "Repository alias",
                },
                "file_path": {
                    "type": "string",
                    "description": "File path",
                },
            },
            "required": ["repository_alias", "file_path"],
        },
        "required_permission": "query_repos",
    },
    "browse_directory": {
        "name": "browse_directory",
        "description": "Browse directory recursively",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repository_alias": {
                    "type": "string",
                    "description": "Repository alias",
                },
                "path": {
                    "type": "string",
                    "description": "Directory path (optional)",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Recursive listing",
                    "default": True,
                },
            },
            "required": ["repository_alias"],
        },
        "required_permission": "query_repos",
    },
    "get_branches": {
        "name": "get_branches",
        "description": "Get available branches for a repository",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repository_alias": {
                    "type": "string",
                    "description": "Repository alias",
                },
            },
            "required": ["repository_alias"],
        },
        "required_permission": "query_repos",
    },
    "check_health": {
        "name": "check_health",
        "description": "Check system health status",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "required_permission": "query_repos",
    },
    # Tools 14-18: Admin
    "add_golden_repo": {
        "name": "add_golden_repo",
        "description": "Add a golden repository",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Repository URL",
                },
                "alias": {
                    "type": "string",
                    "description": "Repository alias",
                },
                "branch": {
                    "type": "string",
                    "description": "Default branch (optional)",
                },
            },
            "required": ["url", "alias"],
        },
        "required_permission": "manage_golden_repos",
    },
    "remove_golden_repo": {
        "name": "remove_golden_repo",
        "description": "Remove a golden repository",
        "inputSchema": {
            "type": "object",
            "properties": {
                "alias": {
                    "type": "string",
                    "description": "Repository alias",
                },
            },
            "required": ["alias"],
        },
        "required_permission": "manage_golden_repos",
    },
    "refresh_golden_repo": {
        "name": "refresh_golden_repo",
        "description": "Refresh a golden repository",
        "inputSchema": {
            "type": "object",
            "properties": {
                "alias": {
                    "type": "string",
                    "description": "Repository alias",
                },
            },
            "required": ["alias"],
        },
        "required_permission": "manage_golden_repos",
    },
    "list_users": {
        "name": "list_users",
        "description": "List all users",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "required_permission": "manage_users",
    },
    "create_user": {
        "name": "create_user",
        "description": "Create a new user",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "Username",
                },
                "password": {
                    "type": "string",
                    "description": "Password",
                },
                "role": {
                    "type": "string",
                    "description": "User role",
                    "enum": ["admin", "power_user", "normal_user"],
                },
            },
            "required": ["username", "password", "role"],
        },
        "required_permission": "manage_users",
    },
    # Tools 19-22: Analytics
    "get_repository_statistics": {
        "name": "get_repository_statistics",
        "description": "Get repository statistics",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repository_alias": {
                    "type": "string",
                    "description": "Repository alias",
                },
            },
            "required": ["repository_alias"],
        },
        "required_permission": "query_repos",
    },
    "get_job_statistics": {
        "name": "get_job_statistics",
        "description": "Get background job statistics",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "required_permission": "query_repos",
    },
    "get_all_repositories_status": {
        "name": "get_all_repositories_status",
        "description": "Get status summary of all repositories",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "required_permission": "query_repos",
    },
    "manage_composite_repository": {
        "name": "manage_composite_repository",
        "description": "Manage composite repository operations",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "Operation type",
                    "enum": ["create", "update", "delete"],
                },
                "user_alias": {
                    "type": "string",
                    "description": "Composite repository alias",
                },
                "golden_repo_aliases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Golden repository aliases",
                },
            },
            "required": ["operation", "user_alias"],
        },
        "required_permission": "activate_repos",
    },
}


def filter_tools_by_role(user: User) -> List[Dict[str, Any]]:
    """
    Filter tools based on user role and permissions.

    Args:
        user: Authenticated user with role information

    Returns:
        List of tool definitions available to the user
    """
    filtered_tools = []

    for tool_name, tool_def in TOOL_REGISTRY.items():
        required_permission = tool_def["required_permission"]
        if user.has_permission(required_permission):
            filtered_tools.append(tool_def)

    return filtered_tools

"""MCP Tool Registry - Defines tools with JSON schemas and role requirements."""

from typing import List, Dict, Any
from code_indexer.server.auth.user_manager import User

# MCP Tool Registry - All 22 tools with complete JSON schemas
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Tools 1-2: Search
    "search_code": {
        "name": "search_code",
        "description": "Search code using semantic search, FTS, or hybrid mode. DISCOVERY WORKFLOW: For exploring unfamiliar codebases, query 'cidx-meta-global' first to discover which repositories contain relevant content (it returns repository descriptions), then query specific repositories for detailed code. Example: search_code('API endpoints', repository_alias='cidx-meta-global') finds repos with APIs, then search_code('user authentication endpoint', repository_alias='backend-global') for implementation details.",
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
                    "description": "Maximum number of results. IMPORTANT: Start with limit=5 to conserve context tokens. Each result consumes tokens proportional to code snippet size. Only increase limit if initial results insufficient. High limits (>20) can rapidly consume context window.",
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
                "language": {
                    "type": "string",
                    "description": "Filter by programming language. Supported languages: c, cpp, csharp, dart, go, java, javascript, kotlin, php, python, ruby, rust, scala, swift, typescript, css, html, vue, markdown, xml, json, yaml, bash, shell, and more. Can use friendly names or file extensions (py, js, ts, etc.).",
                },
                "exclude_language": {
                    "type": "string",
                    "description": "Exclude files of specified language. Use same language names as --language parameter.",
                },
                "path_filter": {
                    "type": "string",
                    "description": "Filter by file path pattern using glob syntax (e.g., '*/tests/*' for test files, '*/src/**/*.py' for Python files in src). Supports *, **, ?, [seq] wildcards.",
                },
                "exclude_path": {
                    "type": "string",
                    "description": "Exclude files matching path pattern. Supports glob patterns (*, **, ?, [seq]). Example: '*/tests/*' to exclude all test files, '*.min.js' to exclude minified JavaScript.",
                },
                "file_extensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": 'Filter by file extensions (e.g., [".py", ".js"]). Alternative to language filter when you need exact extension matching.',
                },
                "accuracy": {
                    "type": "string",
                    "enum": ["fast", "balanced", "high"],
                    "default": "balanced",
                    "description": "Search accuracy profile: 'fast' (lower accuracy, faster response), 'balanced' (default, good tradeoff), 'high' (higher accuracy, slower response). Affects embedding search precision.",
                },
                # Temporal query parameters (Story #446)
                "time_range": {
                    "type": "string",
                    "description": "Time range filter for temporal queries (format: YYYY-MM-DD..YYYY-MM-DD, e.g., '2024-01-01..2024-12-31'). Returns only code that existed during this period. Requires temporal index built with 'cidx index --index-commits'.",
                },
                "time_range_all": {
                    "type": "boolean",
                    "default": False,
                    "description": "Query across all git history without time range limit. Requires temporal index built with 'cidx index --index-commits'. Equivalent to querying from first commit to HEAD.",
                },
                "at_commit": {
                    "type": "string",
                    "description": "Query code at a specific commit hash or ref (e.g., 'abc123' or 'HEAD~5'). Returns code state as it existed at that commit. Requires temporal index.",
                },
                "include_removed": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include files that have been removed from the current HEAD in search results. Only applicable with temporal queries. Removed files will have is_removed flag in temporal_context.",
                },
                "show_evolution": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include code evolution timeline with commit history and diffs in response. Shows how code changed over time. Requires temporal index.",
                },
                "evolution_limit": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Limit number of evolution entries per result (user-controlled, no maximum). Only applicable when show_evolution=true. Higher values provide more complete history but increase response size.",
                },
                # FTS-specific parameters (Story #503 Phase 2)
                "case_sensitive": {
                    "type": "boolean",
                    "default": False,
                    "description": "Enable case-sensitive FTS matching. Only applicable when search_mode is 'fts' or 'hybrid'. When true, query matches must have exact case.",
                },
                "fuzzy": {
                    "type": "boolean",
                    "default": False,
                    "description": "Enable fuzzy matching with edit distance of 1 (typo tolerance). Only applicable when search_mode is 'fts' or 'hybrid'. Incompatible with regex=true.",
                },
                "edit_distance": {
                    "type": "integer",
                    "default": 0,
                    "minimum": 0,
                    "maximum": 3,
                    "description": "Fuzzy match tolerance level (0=exact, 1=1 typo, 2=2 typos, 3=3 typos). Only applicable when search_mode is 'fts' or 'hybrid'. Higher values allow more typos but may reduce precision.",
                },
                "snippet_lines": {
                    "type": "integer",
                    "default": 5,
                    "minimum": 0,
                    "maximum": 50,
                    "description": "Number of context lines to show around FTS matches (0=list only, 1-50=show context). Only applicable when search_mode is 'fts' or 'hybrid'. Higher values provide more context but increase response size.",
                },
                "regex": {
                    "type": "boolean",
                    "default": False,
                    "description": "Interpret query as regex pattern for token-based matching. Only applicable when search_mode is 'fts' or 'hybrid'. Incompatible with fuzzy=true. Enables pattern matching like 'def.*auth' or 'test_.*'.",
                },
                # Temporal filtering parameters (Story #503 Phase 3)
                "diff_type": {
                    "type": "string",
                    "description": "Filter temporal results by diff type (added/modified/deleted/renamed/binary). Can be comma-separated for multiple types (e.g., 'added,modified'). Only applicable when time_range is specified.",
                },
                "author": {
                    "type": "string",
                    "description": "Filter temporal results by commit author (name or email). Only applicable when time_range is specified.",
                },
                "chunk_type": {
                    "type": "string",
                    "enum": ["commit_message", "commit_diff"],
                    "description": "Filter temporal results by chunk type: 'commit_message' searches commit messages, 'commit_diff' searches code diffs. Only applicable when time_range is specified.",
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
    "list_global_repos": {
        "name": "list_global_repos",
        "description": "List all globally accessible repositories for instant querying without activation. Global repositories are pre-indexed and immediately queryable. IMPORTANT: 'cidx-meta-global' is the meta-directory catalog - it contains descriptions of all repositories. DISCOVERY WORKFLOW: (1) Query cidx-meta-global first to discover which repositories contain content on your topic, (2) then query those specific repositories for detailed code. Example: search_code('authentication', repository_alias='cidx-meta-global') returns repositories that handle authentication, then search_code('OAuth implementation', repository_alias='backend-api-global') for actual code.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "required_permission": "query_repos",
    },
    "global_repo_status": {
        "name": "global_repo_status",
        "description": "Get detailed status of a specific global repository including refresh timestamps",
        "inputSchema": {
            "type": "object",
            "properties": {
                "alias": {
                    "type": "string",
                    "description": "Global repository alias (e.g., 'repo-name-global')",
                }
            },
            "required": ["alias"],
        },
        "required_permission": "query_repos",
    },
    "get_global_config": {
        "name": "get_global_config",
        "description": "Get global repository refresh configuration",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "required_permission": "query_repos",
    },
    "set_global_config": {
        "name": "set_global_config",
        "description": "Update global repository refresh interval (minimum 60 seconds)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "refresh_interval": {
                    "type": "integer",
                    "description": "Refresh interval in seconds",
                    "minimum": 60,
                }
            },
            "required": ["refresh_interval"],
        },
        "required_permission": "manage_golden_repos",
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

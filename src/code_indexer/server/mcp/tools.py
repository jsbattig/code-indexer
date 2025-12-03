"""MCP Tool Registry - Defines tools with JSON schemas and role requirements."""

from typing import List, Dict, Any
from code_indexer.server.auth.user_manager import User

# MCP Tool Registry - All 22 tools with complete JSON schemas
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Tools 1-2: Search
    "search_code": {
        "name": "search_code",
        "description": "Search code using semantic search, FTS, or hybrid mode. ALIAS GLOSSARY: 'repository_alias' is what you search with - global repos end in '-global' (e.g., 'backend-global'), activated repos use custom aliases. Use list_global_repos to discover available global repo aliases. DISCOVERY WORKFLOW: For exploring unfamiliar codebases, query 'cidx-meta-global' first to discover which repositories contain relevant content (it returns repository descriptions), then query specific repositories for detailed code. Example: search_code('API endpoints', repository_alias='cidx-meta-global') finds repos with APIs, then search_code('user authentication endpoint', repository_alias='backend-global') for implementation details. TROUBLESHOOTING: Empty results? Check: (1) repository_alias exists via list_global_repos, (2) query is not too specific, (3) try FTS mode for exact text. 'Repository not found'? Verify alias with list_global_repos; global repos end in '-global'. Slow queries? Reduce limit, use path_filter to narrow scope. Temporal queries empty? Use global_repo_status to check enable_temporal field.",
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
                    "description": "Search mode: 'semantic' for natural language/conceptual queries ('how authentication works'), 'fts' for exact text/identifiers ('def authenticate_user'), 'hybrid' for both. Default: semantic.",
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
                    "description": "Time range filter for temporal queries (format: YYYY-MM-DD..YYYY-MM-DD, e.g., '2024-01-01..2024-12-31'). Returns only code that existed during this period. Requires temporal index built with 'cidx index --index-commits'. NOTE: To verify temporal indexing is available, use global_repo_status to check the enable_temporal field, or try a temporal query - empty results may indicate temporal indexing is not enabled.",
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether the search operation succeeded",
                },
                "results": {
                    "type": "object",
                    "description": "Search results (present when success=True)",
                    "properties": {
                        "results": {
                            "type": "array",
                            "description": "Array of code search results",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "file_path": {
                                        "type": "string",
                                        "description": "Relative path to file",
                                    },
                                    "line_number": {
                                        "type": "integer",
                                        "description": "Line number where match found",
                                    },
                                    "code_snippet": {
                                        "type": "string",
                                        "description": "Code snippet containing match",
                                    },
                                    "similarity_score": {
                                        "type": "number",
                                        "description": "Semantic similarity score (0.0-1.0)",
                                    },
                                    "repository_alias": {
                                        "type": "string",
                                        "description": "Repository where result found",
                                    },
                                    "source_repo": {
                                        "type": ["string", "null"],
                                        "description": "Component repository name for composite repositories. Null for single repositories. Indicates which repo in a composite this result came from.",
                                    },
                                    "file_last_modified": {
                                        "type": ["number", "null"],
                                        "description": "Unix timestamp when file last modified (null if stat failed)",
                                    },
                                    "indexed_timestamp": {
                                        "type": ["number", "null"],
                                        "description": "Unix timestamp when file was indexed (null if not available)",
                                    },
                                    "temporal_context": {
                                        "type": ["object", "null"],
                                        "description": "Temporal metadata for time-range queries (null for non-temporal queries)",
                                        "properties": {
                                            "first_seen": {
                                                "type": "string",
                                                "description": "ISO timestamp when code first appeared",
                                            },
                                            "last_seen": {
                                                "type": "string",
                                                "description": "ISO timestamp when code last modified",
                                            },
                                            "commit_count": {
                                                "type": "integer",
                                                "description": "Number of commits affecting this code",
                                            },
                                            "commits": {
                                                "type": "array",
                                                "description": "List of commits affecting this code",
                                                "items": {"type": "object"},
                                            },
                                            "is_removed": {
                                                "type": "boolean",
                                                "description": "Whether file was removed from current HEAD (only when include_removed=true)",
                                            },
                                            "evolution": {
                                                "type": ["array", "null"],
                                                "description": "Code evolution timeline (only when show_evolution=true)",
                                                "items": {"type": "object"},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                        "total_results": {
                            "type": "integer",
                            "description": "Total number of results returned",
                        },
                        "query_metadata": {
                            "type": "object",
                            "description": "Query execution metadata",
                            "properties": {
                                "query_text": {
                                    "type": "string",
                                    "description": "Original query text",
                                },
                                "execution_time_ms": {
                                    "type": "integer",
                                    "description": "Query execution time in milliseconds",
                                },
                                "repositories_searched": {
                                    "type": "integer",
                                    "description": "Number of repositories searched",
                                },
                                "timeout_occurred": {
                                    "type": "boolean",
                                    "description": "Whether query timed out",
                                },
                            },
                        },
                    },
                },
                "error": {
                    "type": "string",
                    "description": "Error message (present when success=False)",
                },
            },
            "required": ["success"],
        },
    },
    "discover_repositories": {
        "name": "discover_repositories",
        "description": "List repositories available from external source configurations (Git forges, local paths). DIFFERENT FROM list_global_repos: This shows POTENTIAL repos from sources like GitHub organizations; those repos may not yet be indexed. To make a discovered repo queryable, use add_golden_repo. For already-indexed repos ready to query, use list_global_repos.",
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "repositories": {
                    "type": "array",
                    "description": "List of discovered golden repositories",
                    "items": {
                        "type": "object",
                        "description": "Golden repository information from GoldenRepository.to_dict()",
                        "properties": {
                            "alias": {
                                "type": "string",
                                "description": "Repository alias",
                            },
                            "repo_url": {
                                "type": "string",
                                "description": "Git repository URL",
                            },
                            "default_branch": {
                                "type": "string",
                                "description": "Default branch name",
                            },
                            "clone_path": {
                                "type": "string",
                                "description": "Filesystem path to cloned repository",
                            },
                            "created_at": {
                                "type": "string",
                                "description": "Repository creation timestamp",
                            },
                            "enable_temporal": {
                                "type": "boolean",
                                "description": "Whether temporal indexing is enabled",
                            },
                            "temporal_options": {
                                "type": "object",
                                "description": "Temporal indexing configuration options",
                            },
                        },
                    },
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
    },
    # Tools 3-8: Repository Management
    "list_repositories": {
        "name": "list_repositories",
        "description": "List repositories YOU have activated (user-specific). DIFFERENT FROM list_global_repos: This shows YOUR activated repos (created via activate_repository for specific branches or composites); list_global_repos shows shared pre-indexed repos available to everyone. Most users only need list_global_repos unless they've activated specific branches or created composites.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "required_permission": "query_repos",
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "repositories": {
                    "type": "array",
                    "description": "Combined list of activated and global repositories",
                    "items": {
                        "type": "object",
                        "description": "Normalized repository information (activated or global)",
                        "properties": {
                            "user_alias": {
                                "type": "string",
                                "description": "User-visible repository alias (queryable name). For global repos, ends with '-global' suffix",
                            },
                            "golden_repo_alias": {
                                "type": "string",
                                "description": "Base golden repository name (without -global suffix)",
                            },
                            "current_branch": {
                                "type": ["string", "null"],
                                "description": "Active branch for activated repos, null for global repos (read-only snapshots)",
                            },
                            "is_global": {
                                "type": "boolean",
                                "description": "True if globally accessible shared repo, false if user-activated repo",
                            },
                            "repo_url": {
                                "type": ["string", "null"],
                                "description": "Repository URL (for global repos)",
                            },
                            "last_refresh": {
                                "type": ["string", "null"],
                                "description": "ISO 8601 timestamp of last index refresh",
                            },
                            "index_path": {
                                "type": "string",
                                "description": "Filesystem path to repository index",
                            },
                            "created_at": {
                                "type": ["string", "null"],
                                "description": "ISO 8601 timestamp when repository was added",
                            },
                        },
                    },
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
    },
    "activate_repository": {
        "name": "activate_repository",
        "description": "Create a user-specific repository activation for branch selection or composite repositories. DECISION: Use '{name}-global' directly for default branch queries (no activation needed). Only activate if you need: (1) a non-default branch, (2) composite of multiple repos, or (3) user-specific configuration. After activation, query using the user_alias you provide.",
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "job_id": {
                    "type": ["string", "null"],
                    "description": "Background job ID for tracking activation progress",
                },
                "message": {
                    "type": "string",
                    "description": "Human-readable status message",
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "job_id": {
                    "type": ["string", "null"],
                    "description": "Background job ID for tracking deactivation",
                },
                "message": {
                    "type": "string",
                    "description": "Human-readable status message",
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "status": {
                    "type": "object",
                    "description": "Detailed repository status information",
                    "properties": {
                        "alias": {"type": "string", "description": "Repository alias"},
                        "repo_url": {"type": "string", "description": "Repository URL"},
                        "default_branch": {
                            "type": "string",
                            "description": "Default branch name",
                        },
                        "clone_path": {
                            "type": "string",
                            "description": "Filesystem path to cloned repository",
                        },
                        "created_at": {
                            "type": "string",
                            "description": "Repository creation timestamp",
                        },
                        "activation_status": {
                            "type": "string",
                            "description": "Activation status (activated/available)",
                        },
                        "branches_list": {
                            "type": "array",
                            "description": "List of available branches",
                            "items": {"type": "string"},
                        },
                        "file_count": {
                            "type": "integer",
                            "description": "Number of files in repository",
                        },
                        "index_size": {
                            "type": "integer",
                            "description": "Size of index in bytes",
                        },
                        "last_updated": {
                            "type": "string",
                            "description": "Last update timestamp",
                        },
                        "enable_temporal": {
                            "type": "boolean",
                            "description": "Whether temporal indexing is enabled",
                        },
                        "temporal_status": {
                            "type": ["object", "null"],
                            "description": "Temporal indexing status (null if disabled)",
                            "properties": {
                                "enabled": {
                                    "type": "boolean",
                                    "description": "Whether temporal indexing is enabled",
                                },
                                "diff_context": {
                                    "type": "integer",
                                    "description": "Number of context lines for diffs",
                                },
                            },
                        },
                    },
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "job_id": {
                    "type": ["string", "null"],
                    "description": "Background job ID for tracking sync progress",
                },
                "message": {
                    "type": "string",
                    "description": "Human-readable status message",
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "message": {
                    "type": "string",
                    "description": "Human-readable status message",
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "files": {
                    "type": "array",
                    "description": "List of files in repository",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Relative file path",
                            },
                            "size_bytes": {
                                "type": "integer",
                                "description": "File size in bytes",
                            },
                            "modified_at": {
                                "type": "string",
                                "description": "ISO 8601 last modification timestamp",
                            },
                            "language": {
                                "type": ["string", "null"],
                                "description": "Detected programming language",
                            },
                            "is_indexed": {
                                "type": "boolean",
                                "description": "Whether file is indexed",
                            },
                        },
                    },
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "content": {
                    "type": "array",
                    "description": "Array of content blocks (MCP spec compliant)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["text"],
                                "description": "Content block type",
                            },
                            "text": {
                                "type": "string",
                                "description": "File content as text",
                            },
                        },
                    },
                },
                "metadata": {
                    "type": "object",
                    "description": "File metadata (size, language, etc)",
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
    },
    "browse_directory": {
        "name": "browse_directory",
        "description": "Browse directory structure of an indexed repository with filtering and sorting. Returns file metadata (path, size, language, modification time) for matching files. Automatically excludes .code-indexer/, .git/, and files matching .gitignore patterns. Use for exploring repository structure, finding files by pattern, or understanding codebase organization before performing targeted searches.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repository_alias": {
                    "type": "string",
                    "description": "Repository alias to browse. Use '-global' suffix aliases (e.g., 'myproject-global') for persistent global repositories, or activated repository aliases without suffix. Use list_repositories to discover available aliases.",
                },
                "path": {
                    "type": "string",
                    "description": "Subdirectory path within the repository to browse (relative to repository root). Examples: 'src', 'src/components', 'tests/unit'. Omit or use empty string to browse from repository root.",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "When true (default), returns all files in directory and subdirectories. When false, returns only immediate children of the specified directory (single level). Use recursive=false to explore directory structure level by level.",
                    "default": True,
                },
                "path_pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files. Combines with 'path' parameter (pattern applied within the specified directory). Supports: * (any chars), ** (any path segments), ? (single char), [seq] (char class). Examples: '*.py' (Python files), 'test_*.py' (test files), '**/*.ts' (TypeScript at any depth), 'src/**/index.js' (index files under src).",
                },
                "language": {
                    "type": "string",
                    "description": "Filter by programming language. Supported languages: c, cpp, csharp, dart, go, java, javascript, kotlin, php, python, ruby, rust, scala, swift, typescript, css, html, vue, markdown, xml, json, yaml, bash, shell, and more. Can use friendly names or file extensions (py, js, ts, etc.).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum files to return. IMPORTANT: Start with limit=50-100 to conserve context tokens. Each file entry consumes tokens for path, size, and metadata. Only increase if you need comprehensive listing. Default 500 is high for most exploration tasks.",
                    "default": 500,
                    "minimum": 1,
                    "maximum": 500,
                },
                "sort_by": {
                    "type": "string",
                    "description": "Sort order for results. Options: 'path' (alphabetical by file path - default, good for exploring structure), 'size' (by file size - useful for finding large files), 'modified_at' (by modification time - useful for finding recently changed files).",
                    "enum": ["path", "size", "modified_at"],
                    "default": "path",
                },
            },
            "required": ["repository_alias"],
        },
        "required_permission": "query_repos",
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "structure": {
                    "type": "object",
                    "description": "Directory structure with files",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory path browsed",
                        },
                        "files": {
                            "type": "array",
                            "description": "Array of file information objects",
                        },
                        "total": {
                            "type": "integer",
                            "description": "Total number of files",
                        },
                    },
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "branches": {
                    "type": "array",
                    "description": "List of branches",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Branch name"},
                            "is_current": {
                                "type": "boolean",
                                "description": "Whether this is the active branch",
                            },
                            "last_commit": {
                                "type": "object",
                                "properties": {
                                    "sha": {
                                        "type": "string",
                                        "description": "Commit SHA",
                                    },
                                    "message": {
                                        "type": "string",
                                        "description": "Commit message",
                                    },
                                    "author": {
                                        "type": "string",
                                        "description": "Commit author",
                                    },
                                    "date": {
                                        "type": "string",
                                        "description": "Commit date",
                                    },
                                },
                            },
                            "index_status": {
                                "type": ["object", "null"],
                                "description": "Index status for this branch (nullable)",
                            },
                            "remote_tracking": {
                                "type": ["object", "null"],
                                "description": "Remote tracking information (nullable)",
                            },
                        },
                    },
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "health": {
                    "type": "object",
                    "description": "System health information",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["healthy", "degraded", "unhealthy"],
                            "description": "Overall health status",
                        },
                        "timestamp": {
                            "type": "string",
                            "description": "ISO 8601 health check timestamp",
                        },
                        "checks": {
                            "type": "object",
                            "description": "Individual service health checks",
                        },
                    },
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
    },
    # Tools 14-18: Admin
    "add_golden_repo": {
        "name": "add_golden_repo",
        "description": "Register a new repository for indexing (ASYNC operation). Returns immediately but indexing runs in background. WORKFLOW: (1) Call add_golden_repo(url, alias), (2) Poll get_job_statistics() until active=0 and pending=0, (3) Repository becomes available as '{alias}-global' for querying. TIMING: Small repos (<1K files): seconds. Medium repos (1K-10K files): minutes. Large repos (10K-100K files): 10-30 minutes. Very large repos (10GB+, 100K+ files): can take HOURS. Poll get_job_statistics every 30 seconds. NAMING: Use descriptive aliases; '-global' suffix added automatically for global access. TEMPORAL: Set enable_temporal=true to index git history for time-based searches.",
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
                "enable_temporal": {
                    "type": "boolean",
                    "default": False,
                    "description": "Enable temporal indexing (git history search). When true, repository is indexed with --index-commits flag to support time-based queries. Default: false for backward compatibility.",
                },
                "temporal_options": {
                    "type": "object",
                    "description": "Temporal indexing configuration options. Only used when enable_temporal=true.",
                    "properties": {
                        "max_commits": {
                            "type": "integer",
                            "description": "Maximum number of commits to index. Omit for all commits.",
                            "minimum": 1,
                        },
                        "since_date": {
                            "type": "string",
                            "description": "Only index commits after this date (format: YYYY-MM-DD).",
                        },
                        "diff_context": {
                            "type": "integer",
                            "default": 5,
                            "description": "Number of context lines in diffs. Default: 5. Higher values increase storage.",
                            "minimum": 0,
                            "maximum": 50,
                        },
                    },
                },
            },
            "required": ["url", "alias"],
        },
        "required_permission": "manage_golden_repos",
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "job_id": {
                    "type": ["string", "null"],
                    "description": "Background job ID for tracking indexing progress",
                },
                "message": {
                    "type": "string",
                    "description": "Human-readable status message",
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "job_id": {
                    "type": ["string", "null"],
                    "description": "Background job ID",
                },
                "message": {"type": "string", "description": "Status message"},
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "job_id": {
                    "type": ["string", "null"],
                    "description": "Background job ID",
                },
                "message": {"type": "string", "description": "Status message"},
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "users": {
                    "type": "array",
                    "description": "List of users",
                    "items": {
                        "type": "object",
                        "properties": {
                            "username": {"type": "string", "description": "Username"},
                            "role": {
                                "type": "string",
                                "enum": ["admin", "power_user", "normal_user"],
                                "description": "User role",
                            },
                            "created_at": {
                                "type": "string",
                                "description": "ISO 8601 creation timestamp",
                            },
                        },
                    },
                },
                "total": {"type": "integer", "description": "Total number of users"},
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "user": {
                    "type": ["object", "null"],
                    "description": "Created user information",
                    "properties": {
                        "username": {"type": "string", "description": "Username"},
                        "role": {"type": "string", "description": "User role"},
                        "created_at": {
                            "type": "string",
                            "description": "ISO 8601 creation timestamp",
                        },
                    },
                },
                "message": {"type": "string", "description": "Status message"},
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "statistics": {
                    "type": "object",
                    "description": "Repository statistics (RepositoryStatsResponse model)",
                    "properties": {
                        "repository_id": {
                            "type": "string",
                            "description": "Repository identifier",
                        },
                        "files": {
                            "type": "object",
                            "description": "File statistics",
                            "properties": {
                                "total": {
                                    "type": "integer",
                                    "description": "Total number of files",
                                },
                                "indexed": {
                                    "type": "integer",
                                    "description": "Number of indexed files",
                                },
                                "by_language": {
                                    "type": "object",
                                    "description": "File counts by programming language",
                                },
                            },
                        },
                        "storage": {
                            "type": "object",
                            "description": "Storage statistics",
                            "properties": {
                                "repository_size_bytes": {
                                    "type": "integer",
                                    "description": "Total repository size in bytes",
                                },
                                "index_size_bytes": {
                                    "type": "integer",
                                    "description": "Index size in bytes",
                                },
                                "embedding_count": {
                                    "type": "integer",
                                    "description": "Number of embeddings stored",
                                },
                            },
                        },
                        "activity": {
                            "type": "object",
                            "description": "Activity statistics",
                            "properties": {
                                "created_at": {
                                    "type": "string",
                                    "description": "Repository creation timestamp (ISO 8601)",
                                },
                                "last_sync_at": {
                                    "type": ["string", "null"],
                                    "description": "Last synchronization timestamp (ISO 8601)",
                                },
                                "last_accessed_at": {
                                    "type": ["string", "null"],
                                    "description": "Last access timestamp (ISO 8601)",
                                },
                                "sync_count": {
                                    "type": "integer",
                                    "description": "Number of successful syncs",
                                },
                            },
                        },
                        "health": {
                            "type": "object",
                            "description": "Health assessment",
                            "properties": {
                                "score": {
                                    "type": "number",
                                    "description": "Health score between 0.0 and 1.0",
                                },
                                "issues": {
                                    "type": "array",
                                    "description": "List of identified health issues",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
    },
    "get_job_statistics": {
        "name": "get_job_statistics",
        "description": "Get counts of background repository indexing jobs (active/pending/failed). Use this to monitor if repository registration, activation, or sync operations are still in progress. Returns job counts, not individual job details. Example: after calling add_golden_repo, check this periodically - when active=0 and pending=0, indexing is complete. FAILURE HANDLING: If failed>0, errors typically from invalid URLs, auth issues, or network problems. Check server logs or REST API /api/admin/jobs for detailed error messages.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "required_permission": "query_repos",
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "statistics": {
                    "type": "object",
                    "description": "Job statistics",
                    "properties": {
                        "active": {
                            "type": "integer",
                            "description": "Number of currently running jobs",
                        },
                        "pending": {
                            "type": "integer",
                            "description": "Number of queued jobs waiting to run",
                        },
                        "failed": {
                            "type": "integer",
                            "description": "Number of failed jobs",
                        },
                        "total": {
                            "type": "integer",
                            "description": "Total jobs (active + pending + failed)",
                        },
                    },
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "repositories": {
                    "type": "array",
                    "description": "Array of repository status summaries",
                },
                "total": {
                    "type": "integer",
                    "description": "Total number of repositories",
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "job_id": {
                    "type": ["string", "null"],
                    "description": "Background job ID",
                },
                "message": {"type": "string", "description": "Status message"},
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
    },
    "list_global_repos": {
        "name": "list_global_repos",
        "description": "List all globally accessible repositories. REPOSITORY STATES: Discovered (from discover_repositories, not yet indexed) -> Golden/Global (after add_golden_repo, immediately queryable as '{name}-global') -> Activated (optional, via activate_repository for branch selection or composites). TERMINOLOGY: Golden repositories are admin-registered source repos. Global repositories are the publicly queryable versions accessible via '{name}-global' alias. SPECIAL: 'cidx-meta-global' is the meta-directory catalog containing descriptions of ALL repositories. DISCOVERY WORKFLOW: (1) Query cidx-meta-global to discover which repositories contain content on your topic, (2) then query those specific repositories for detailed code. Example: search_code('authentication', repository_alias='cidx-meta-global') returns repositories that handle authentication, then search_code('OAuth implementation', repository_alias='backend-api-global') for actual code. STATUS: All listed global repos are ready for querying immediately; use global_repo_status for detailed info.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "required_permission": "query_repos",
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "repos": {
                    "type": "array",
                    "description": "List of global repositories (normalized schema)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "user_alias": {
                                "type": "string",
                                "description": "Global repository alias (ends with '-global')",
                            },
                            "golden_repo_alias": {
                                "type": "string",
                                "description": "Base repository name",
                            },
                            "is_global": {
                                "type": "boolean",
                                "description": "Always true for global repos",
                            },
                            "repo_url": {
                                "type": ["string", "null"],
                                "description": "Repository URL",
                            },
                            "last_refresh": {
                                "type": ["string", "null"],
                                "description": "ISO 8601 last refresh timestamp",
                            },
                            "index_path": {
                                "type": "string",
                                "description": "Filesystem path to index",
                            },
                            "created_at": {
                                "type": ["string", "null"],
                                "description": "ISO 8601 creation timestamp",
                            },
                        },
                    },
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
    },
    "global_repo_status": {
        "name": "global_repo_status",
        "description": "Get detailed status of a specific global repository including refresh timestamps and temporal indexing status",
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "error": {"type": "string", "description": "Error message if failed"},
                "alias": {"type": "string", "description": "Global repository alias"},
                "repo_name": {"type": "string", "description": "Repository name"},
                "url": {"type": "string", "description": "Git repository URL"},
                "last_refresh": {
                    "type": ["string", "null"],
                    "description": "ISO 8601 timestamp of last refresh",
                },
                "enable_temporal": {
                    "type": "boolean",
                    "description": "Whether temporal indexing (git history search) is enabled for this repository. If true, time-based queries are supported.",
                },
            },
            "required": ["success"],
        },
    },
    "get_global_config": {
        "name": "get_global_config",
        "description": "Get global repository refresh configuration",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "required_permission": "query_repos",
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "error": {"type": "string", "description": "Error message if failed"},
                "refresh_interval": {
                    "type": "integer",
                    "description": "Refresh interval in seconds (minimum 60)",
                },
            },
            "required": ["success"],
        },
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
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether operation succeeded",
                },
                "status": {"type": "string", "description": "Operation status"},
                "refresh_interval": {
                    "type": "integer",
                    "description": "Updated refresh interval in seconds",
                },
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["success"],
        },
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

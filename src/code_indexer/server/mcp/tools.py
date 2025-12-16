"""MCP Tool Registry - Defines tools with JSON schemas and role requirements."""

from typing import List, Dict, Any
from code_indexer.server.auth.user_manager import User

# MCP Tool Registry - All 22 tools with complete JSON schemas
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Tools 1-2: Search
    "search_code": {
        "name": "search_code",
        "description": "TL;DR: Search code using pre-built indexes. Use semantic mode for conceptual queries, FTS for exact text. SEARCH MODE DECISION: 'authentication logic' (concept) -> semantic | 'def authenticate_user' (exact text) -> fts | unsure -> hybrid. CRITICAL - SEMANTIC SEARCH IS NOT TEXT SEARCH: Semantic mode finds code by MEANING, not exact text. Results are APPROXIMATE and help identify areas of concern for a topic. For exhaustive exact-text results, use FTS mode or regex_search tool. QUICK START: search_code('user authentication', repository_alias='myrepo-global', search_mode='semantic', limit=5). DISCOVERY: Run list_global_repos first to see available repositories. ALIAS FORMAT: Global repos end in '-global' (e.g., 'backend-global'). CIDX-META: For exploring unfamiliar codebases, cidx-meta-global contains .md descriptions of all repos - use browse_directory + get_file_content (NOT search_code) since it's a small catalog. TROUBLESHOOTING: (1) 0 results? Verify alias with list_global_repos, try broader terms, check filters. (2) Temporal queries empty? Check enable_temporal via global_repo_status. (3) Slow? Start with limit=5, use path_filter. WHEN NOT TO USE: (1) Need comprehensive pattern search with ALL matches -> use regex_search instead (not approximate), (2) Know exact text but want direct file search -> use regex_search (no index required), (3) Exploring directory structure -> use browse_directory or directory_tree first. RELATED TOOLS: regex_search (comprehensive pattern matching without index), git_search_diffs (find when code was added/removed).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query_text": {
                    "type": "string",
                    "description": "Search query text",
                },
                "repository_alias": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                    "description": "Repository alias(es) to search. String for single repo, array for omni-search across multiple repos. Supports wildcard patterns like '*-global' when using array.",
                },
                "aggregation_mode": {
                    "type": "string",
                    "enum": ["global", "per_repo"],
                    "default": "global",
                    "description": "How to aggregate results across multiple repositories. 'global' (default): Returns top N results by score across ALL repos - best for finding absolute best matches (e.g., limit=10 across 3 repos returns 10 best total, might be 8 from repo1, 2 from repo2, 0 from repo3). 'per_repo': Distributes N results evenly across repos - best for balanced representation (e.g., limit=10 across 3 repos returns ~3 from each repo).",
                },
                "exclude_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Regex patterns to exclude repositories from omni-search.",
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
                    "description": "Time range filter for temporal queries (format: YYYY-MM-DD..YYYY-MM-DD, e.g., '2024-01-01..2024-12-31'). Returns only code that existed during this period. Requires temporal index built with 'cidx index --index-commits'. Check repository's temporal support via global_repo_status - look for enable_temporal: true in the response. Empty temporal query results typically indicate temporal indexing is not enabled for the repository.",
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
                "response_format": {
                    "type": "string",
                    "enum": ["flat", "grouped"],
                    "default": "flat",
                    "description": 'Response format for omni-search (multi-repo) results. Only applies when repository_alias is an array.\n\n\'flat\' (default): Returns all results in a single array, each with source_repo field.\nExample response: {"results": [{"file_path": "src/auth.py", "source_repo": "backend-global", "content": "...", "score": 0.95}, {"file_path": "Login.tsx", "source_repo": "frontend-global", "content": "...", "score": 0.89}], "total_results": 2}\n\n\'grouped\': Groups results by repository under results_by_repo object.\nExample response: {"results_by_repo": {"backend-global": {"count": 1, "results": [{"file_path": "src/auth.py", "content": "...", "score": 0.95}]}, "frontend-global": {"count": 1, "results": [{"file_path": "Login.tsx", "content": "...", "score": 0.89}]}}, "total_results": 2}\n\nUse \'grouped\' when you need to process results per-repository or display results organized by source.',
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
    "cidx_quick_reference": {
        "name": "cidx_quick_reference",
        "description": (
            "CIDX Quick Reference - What tool should I use? "
            "SEARCH CODE: search_code (semantic=meaning, fts=exact text, hybrid=both) | regex_search (comprehensive pattern match, slower). "
            "GIT HISTORY: git_log (recent commits) | git_file_history (one file's commits) | git_blame (who wrote each line) | git_diff (compare versions) | git_search_commits (find by message) | git_search_diffs (find when code added/removed - SLOW on large repos). "
            "EXPLORE FILES: directory_tree (visual hierarchy) | browse_directory (file list with metadata) | get_file_content (read file). "
            "REPOSITORIES: list_global_repos (see available repos) | global_repo_status (one repo's details) | cidx-meta-global (catalog of all repo descriptions). "
            "DECISION GUIDE: Concept search -> search_code(semantic) | Exact text -> search_code(fts) or regex_search | Pattern/regex -> regex_search | Who wrote code -> git_blame | File history -> git_file_history | When code added -> git_search_diffs. "
            "START HERE: (1) list_global_repos to see repos, (2) browse cidx-meta-global for descriptions, (3) search_code for code."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "required_permission": "query_repos",
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean", "description": "Always true"},
                "reference": {"type": "string", "description": "Quick reference guide"},
            },
            "required": ["success", "reference"],
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
        "description": "Create a user-specific repository activation for branch selection or composite repositories. DECISION: Use '{name}-global' directly for default branch queries (no activation needed). Only activate if you need: (1) a non-default branch, (2) composite of multiple repos, or (3) user-specific configuration. After activation, query using the user_alias you provide. COMPOSITE REPOS: To search across multiple repositories at once, use golden_repo_aliases (array) to create a composite. Example: activate_repository(golden_repo_aliases=['frontend', 'backend', 'shared'], user_alias='full-stack') creates a searchable union.",
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
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                    "description": "Repository alias(es): String for single repo, array for omni-list-files across multiple repos.",
                },
                "aggregation_mode": {
                    "type": "string",
                    "enum": ["global", "per_repo"],
                    "default": "global",
                    "description": "How to aggregate file listings across multiple repositories. 'global' (default): Returns files sorted by repo then path - shows all files in order. 'per_repo': Distributes limit evenly across repos - ensures balanced representation (e.g., limit=30 across 3 repos returns ~10 from each repo).",
                },
                "path": {
                    "type": "string",
                    "description": "Directory path (optional)",
                },
                "response_format": {
                    "type": "string",
                    "enum": ["flat", "grouped"],
                    "default": "flat",
                    "description": 'Response format for omni-search (multi-repo) results. Only applies when repository_alias is an array.\n\n\'flat\' (default): Returns all results in a single array, each with source_repo field.\nExample response: {"results": [{"file_path": "src/auth.py", "source_repo": "backend-global", "content": "...", "score": 0.95}, {"file_path": "Login.tsx", "source_repo": "frontend-global", "content": "...", "score": 0.89}], "total_results": 2}\n\n\'grouped\': Groups results by repository under results_by_repo object.\nExample response: {"results_by_repo": {"backend-global": {"count": 1, "results": [{"file_path": "src/auth.py", "content": "...", "score": 0.95}]}, "frontend-global": {"count": 1, "results": [{"file_path": "Login.tsx", "content": "...", "score": 0.89}]}}, "total_results": 2}\n\nUse \'grouped\' when you need to process results per-repository or display results organized by source.',
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
        "description": "TL;DR: List files with metadata (size, language, modified date) - flat list for filtering/sorting. WHEN TO USE: (1) Find files by pattern, (2) Filter by language/size, (3) Programmatic file listing. COMPARISON: browse_directory = flat list with metadata | directory_tree = visual ASCII hierarchy. RELATED TOOLS: directory_tree (visual hierarchy), get_file_content (read files), list_files (simple file listing).",
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
                "server_version": {
                    "type": "string",
                    "description": "Server version string",
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
        "description": "Register a new repository for indexing (ASYNC operation). Returns immediately but indexing runs in background. WORKFLOW: (1) Call add_golden_repo(url, alias), (2) Poll get_job_statistics() until active=0 and pending=0, (3) Repository becomes available as '{alias}-global' for querying. NAMING: Use descriptive aliases; '-global' suffix added automatically for global access. NAMING WARNING: Avoid aliases that already end in '-global' as this creates confusing double-suffixed names like 'myrepo-global-global'. TEMPORAL: Set enable_temporal=true to index git history for time-based searches. PERFORMANCE EXPECTATIONS: Small repos (<1K files): seconds to minutes. Medium repos (1K-10K files): 1-5 minutes. Large repos (10K-100K files): 5-30 minutes. Very large repos (>100K files, multi-GB): 30 minutes to hours. Monitor progress with get_job_statistics. If job stays in PENDING/RUNNING for 2x expected time, check server logs.",
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
        "description": "Get counts of background repository indexing jobs (active/pending/failed). Use this to monitor if repository registration, activation, or sync operations are still in progress. Returns job counts, not individual job details. Example: after calling add_golden_repo, check this periodically - when active=0 and pending=0, indexing is complete. FAILURE HANDLING: If failed>0, common causes: (1) Invalid/inaccessible Git URL, (2) Authentication required for private repo, (3) Network timeout during clone, (4) Disk space issues. For details, admin can check server logs or REST API /api/admin/jobs endpoint.",
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
        "description": "List all globally accessible repositories. REPOSITORY STATES: Discovered (from discover_repositories, not yet indexed) -> Golden/Global (after add_golden_repo, immediately queryable as '{name}-global') -> Activated (optional, via activate_repository for branch selection or composites). TERMINOLOGY: Golden repositories are admin-registered source repos. Global repositories are the publicly queryable versions accessible via '{name}-global' alias. SPECIAL: 'cidx-meta-global' is the meta-directory catalog containing descriptions of ALL repositories. DISCOVERY WORKFLOW: (1) Query cidx-meta-global to discover which repositories contain content on your topic, (2) then query those specific repositories for detailed code. Example: search_code('authentication', repository_alias='cidx-meta-global') returns repositories that handle authentication, then search_code('OAuth implementation', repository_alias='backend-api-global') for actual code. STATUS: All listed global repos are ready for querying immediately; use global_repo_status for detailed info. TYPICAL WORKFLOW: (1) list_global_repos to see available repositories, (2) browse_directory(repository_alias='cidx-meta-global') to read repository descriptions, (3) search_code with specific repository_alias for code details. WHEN NOT TO USE: (1) Need detailed status of ONE repo (temporal support, refresh times) -> use global_repo_status instead, (2) Want to search code -> use search_code with repository_alias, (3) Looking for repo descriptions -> browse cidx-meta-global first.",
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
    # Tool 23: Regex Search (Story #553 - Remote Repository Exploration)
    "regex_search": {
        "name": "regex_search",
        "description": (
            "TL;DR: Direct pattern search on files without index - comprehensive but slower. "
            "WHEN TO USE: (1) Find exact text/identifiers: 'def authenticate_user', "
            "(2) Complex patterns: 'class.*Controller', (3) TODO/FIXME comments, "
            "(4) Comprehensive search when you need ALL matches (not approximate). "
            "WHEN NOT TO USE: (1) Conceptual queries like 'authentication logic' -> use search_code(semantic), "
            "(2) Fast repeated searches -> use search_code(fts) which is indexed. "
            "COMPARISON: regex_search = comprehensive/slower (searches files directly) | "
            "search_code(fts) = fast/indexed (may miss unindexed files) | "
            "search_code(semantic) = conceptual/approximate (finds by meaning, not text). "
            "RELATED TOOLS: search_code (pre-indexed semantic/FTS search), git_search_diffs (find code changes in git history)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repository_alias": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                    "description": (
                        "Repository identifier(s): String for single repo search, "
                        "array of strings for omni-regex search across multiple repos. "
                        "Use list_global_repos to see available repositories."
                    ),
                },
                "aggregation_mode": {
                    "type": "string",
                    "enum": ["global", "per_repo"],
                    "default": "global",
                    "description": "How to aggregate regex search results across multiple repositories. 'global' (default): Returns top N matches by relevance across ALL repos - best for finding absolute best matches (e.g., limit=20 across 3 repos returns 20 best total). 'per_repo': Distributes N results evenly across repos - ensures balanced representation (e.g., limit=20 across 3 repos returns ~7 from each repo).",
                },
                "pattern": {
                    "type": "string",
                    "description": (
                        "Regular expression pattern to search for. Uses ripgrep regex "
                        "syntax. Examples: 'def\\s+test_' matches Python test functions, "
                        "'TODO|FIXME' matches either word."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Subdirectory to search within (relative to repo root). "
                        "Default: search entire repository."
                    ),
                },
                "include_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Glob patterns for files to include. Examples: ['*.py'] for "
                        "Python files, ['*.ts', '*.tsx'] for TypeScript."
                    ),
                },
                "exclude_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Glob patterns for files to exclude. Examples: ['*_test.py'] "
                        "to exclude tests, ['node_modules/**'] to exclude deps."
                    ),
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Whether search is case-sensitive. Default: true.",
                    "default": True,
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Lines of context before/after match. Default: 0.",
                    "default": 0,
                    "minimum": 0,
                    "maximum": 10,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum matches to return. Default: 100.",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 1000,
                },
                "response_format": {
                    "type": "string",
                    "enum": ["flat", "grouped"],
                    "default": "flat",
                    "description": 'Response format for omni-search (multi-repo) results. Only applies when repository_alias is an array.\n\n\'flat\' (default): Returns all results in a single array, each with source_repo field.\nExample response: {"results": [{"file_path": "src/auth.py", "source_repo": "backend-global", "content": "...", "score": 0.95}, {"file_path": "Login.tsx", "source_repo": "frontend-global", "content": "...", "score": 0.89}], "total_results": 2}\n\n\'grouped\': Groups results by repository under results_by_repo object.\nExample response: {"results_by_repo": {"backend-global": {"count": 1, "results": [{"file_path": "src/auth.py", "content": "...", "score": 0.95}]}, "frontend-global": {"count": 1, "results": [{"file_path": "Login.tsx", "content": "...", "score": 0.89}]}}, "total_results": 2}\n\nUse \'grouped\' when you need to process results per-repository or display results organized by source.',
                },
            },
            "required": ["repository_alias", "pattern"],
        },
        "required_permission": "query_repos",
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean", "description": "Whether succeeded"},
                "matches": {
                    "type": "array",
                    "description": "Array of regex match results",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "line_number": {"type": "integer"},
                            "column": {"type": "integer"},
                            "line_content": {"type": "string"},
                            "context_before": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "context_after": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                },
                "total_matches": {"type": "integer"},
                "truncated": {"type": "boolean"},
                "search_engine": {"type": "string"},
                "search_time_ms": {"type": "number"},
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


# Append regex_search tool definition - temporary workaround

# Tools 24-26: Git Exploration (Story #554 - Remote Repository Exploration)
TOOL_REGISTRY["git_log"] = {
    "name": "git_log",
    "description": (
        "TL;DR: Browse commit history with filtering by path, author, date, or branch. "
        "WHEN TO USE: (1) View recent commits, (2) Find when changes were made, (3) Filter history by author/date/path. "
        "WHEN NOT TO USE: Search commit messages for keywords -> git_search_commits | Find when code was added/removed -> git_search_diffs | Single commit details -> git_show_commit. "
        "RELATED TOOLS: git_show_commit (commit details), git_search_commits (search messages), git_diff (compare revisions)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {
                "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}},
                ],
                "description": (
                    "Repository identifier: either an alias (e.g., 'my-project' or "
                    "'my-project-global') or full path. Use list_global_repos to see "
                    "available repositories and their aliases."
                ),
            },
            "limit": {
                "type": "integer",
                "description": (
                    "Maximum number of commits to return. Default: 50. Range: 1-500. "
                    "Lower values for quick overview, higher for comprehensive history."
                ),
                "default": 50,
                "minimum": 1,
                "maximum": 500,
            },
            "path": {
                "type": "string",
                "description": (
                    "Filter commits to only those affecting this path (file or directory). "
                    "Path is relative to repo root. Examples: 'src/main.py' for single file, "
                    "'src/' for all files under src directory."
                ),
            },
            "author": {
                "type": "string",
                "description": (
                    "Filter commits by author. Matches against author name or email. "
                    "Partial matches supported. Examples: 'john@example.com', 'John Smith', 'john'."
                ),
            },
            "since": {
                "type": "string",
                "description": (
                    "Include only commits after this date. Format: YYYY-MM-DD or relative "
                    "like '2 weeks ago', '2024-01-01'. Inclusive of the date."
                ),
            },
            "until": {
                "type": "string",
                "description": (
                    "Include only commits before this date. Format: YYYY-MM-DD or relative "
                    "like 'yesterday', '2024-06-30'. Inclusive of the date."
                ),
            },
            "branch": {
                "type": "string",
                "description": (
                    "Branch to get log from. Default: current HEAD. Examples: 'main', "
                    "'feature/auth', 'origin/develop'. Can also be a tag like 'v1.0.0'."
                ),
            },
            "aggregation_mode": {
                "type": "string",
                "enum": ["global", "per_repo"],
                "description": "How to aggregate git log results across multiple repositories. 'global' (default): Merges commits by date across ALL repos - shows complete chronological history. 'per_repo': Distributes limit evenly across repos - ensures balanced representation (e.g., limit=30 across 3 repos returns ~10 commits from each repo).",
                "default": "global",
            },
            "response_format": {
                "type": "string",
                "enum": ["flat", "grouped"],
                "default": "flat",
                "description": 'Response format for omni-search (multi-repo) results. Only applies when repository_alias is an array.\n\n\'flat\' (default): Returns all results in a single array, each with source_repo field.\nExample response: {"results": [{"file_path": "src/auth.py", "source_repo": "backend-global", "content": "...", "score": 0.95}, {"file_path": "Login.tsx", "source_repo": "frontend-global", "content": "...", "score": 0.89}], "total_results": 2}\n\n\'grouped\': Groups results by repository under results_by_repo object.\nExample response: {"results_by_repo": {"backend-global": {"count": 1, "results": [{"file_path": "src/auth.py", "content": "...", "score": 0.95}]}, "frontend-global": {"count": 1, "results": [{"file_path": "Login.tsx", "content": "...", "score": 0.89}]}}, "total_results": 2}\n\nUse \'grouped\' when you need to process results per-repository or display results organized by source.',
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
            "commits": {
                "type": "array",
                "description": "List of commits matching filters",
                "items": {
                    "type": "object",
                    "properties": {
                        "hash": {
                            "type": "string",
                            "description": "Full 40-char commit SHA",
                        },
                        "short_hash": {
                            "type": "string",
                            "description": "Abbreviated SHA",
                        },
                        "author_name": {"type": "string", "description": "Author name"},
                        "author_email": {
                            "type": "string",
                            "description": "Author email",
                        },
                        "author_date": {
                            "type": "string",
                            "description": "Author date (ISO 8601)",
                        },
                        "committer_name": {
                            "type": "string",
                            "description": "Committer name",
                        },
                        "committer_email": {
                            "type": "string",
                            "description": "Committer email",
                        },
                        "committer_date": {
                            "type": "string",
                            "description": "Committer date (ISO 8601)",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Commit subject line",
                        },
                        "body": {
                            "type": "string",
                            "description": "Full commit message body",
                        },
                    },
                },
            },
            "total_count": {
                "type": "integer",
                "description": "Number of commits returned",
            },
            "truncated": {
                "type": "boolean",
                "description": "Whether results were truncated",
            },
            "error": {"type": "string", "description": "Error message if failed"},
        },
        "required": ["success"],
    },
}

TOOL_REGISTRY["git_show_commit"] = {
    "name": "git_show_commit",
    "description": (
        "TL;DR: View detailed info about a single commit (message, stats, diff). "
        "WHEN TO USE: (1) Examine a specific commit, (2) See what files changed, (3) Get full diff of one commit. "
        "WHEN NOT TO USE: Browse commit history -> git_log | Compare two different revisions -> git_diff | View file at commit -> git_file_at_revision. "
        "RELATED TOOLS: git_log (find commits), git_diff (compare revisions), git_file_at_revision (view file content)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {
                "type": "string",
                "description": (
                    "Repository identifier: either an alias (e.g., 'my-project' or "
                    "'my-project-global') or full path. Use list_global_repos to see "
                    "available repositories and their aliases."
                ),
            },
            "commit_hash": {
                "type": "string",
                "description": (
                    "The commit to show. Can be full SHA (40 chars), abbreviated SHA "
                    "(7+ chars), or symbolic reference like 'HEAD', 'HEAD~3', 'main^'. "
                    "Examples: 'abc1234', 'abc1234def5678...', 'HEAD~1'."
                ),
            },
            "include_diff": {
                "type": "boolean",
                "description": (
                    "Whether to include the full diff in the response. Default: false. "
                    "Set to true to see exactly what lines changed. Warning: large commits "
                    "may produce very long diffs."
                ),
                "default": False,
            },
            "include_stats": {
                "type": "boolean",
                "description": (
                    "Whether to include file change statistics (files changed, insertions, "
                    "deletions). Default: true. Provides quick summary of commit scope."
                ),
                "default": True,
            },
        },
        "required": ["repository_alias", "commit_hash"],
    },
    "required_permission": "query_repos",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {
                "type": "boolean",
                "description": "Whether operation succeeded",
            },
            "commit": {
                "type": "object",
                "description": "Commit metadata",
                "properties": {
                    "hash": {"type": "string"},
                    "short_hash": {"type": "string"},
                    "author_name": {"type": "string"},
                    "author_email": {"type": "string"},
                    "author_date": {"type": "string"},
                    "committer_name": {"type": "string"},
                    "committer_email": {"type": "string"},
                    "committer_date": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
            "stats": {
                "type": ["array", "null"],
                "description": "File change statistics (when include_stats=true)",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "insertions": {"type": "integer"},
                        "deletions": {"type": "integer"},
                        "status": {
                            "type": "string",
                            "enum": ["added", "modified", "deleted", "renamed"],
                        },
                    },
                },
            },
            "diff": {
                "type": ["string", "null"],
                "description": "Full diff (when include_diff=true)",
            },
            "parents": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Parent commit SHAs",
            },
            "error": {"type": "string", "description": "Error message if failed"},
        },
        "required": ["success"],
    },
}

TOOL_REGISTRY["git_file_at_revision"] = {
    "name": "git_file_at_revision",
    "description": (
        "TL;DR: View a file's contents as it existed at any commit, branch, or tag. "
        "WHEN TO USE: (1) See old version of a file, (2) Compare file before/after changes, (3) View file at specific tag. "
        "WHEN NOT TO USE: Commits that modified file -> git_file_history | Who wrote each line -> git_blame | Full commit details -> git_show_commit. "
        "RELATED TOOLS: git_file_history (commits modifying file), git_blame (line attribution), git_show_commit (commit details)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {
                "type": "string",
                "description": (
                    "Repository identifier: either an alias (e.g., 'my-project' or "
                    "'my-project-global') or full path. Use list_global_repos to see "
                    "available repositories and their aliases."
                ),
            },
            "path": {
                "type": "string",
                "description": (
                    "Path to the file, relative to repository root. Must be exact path "
                    "to a file (not directory). Example: 'src/utils/helper.py'."
                ),
            },
            "revision": {
                "type": "string",
                "description": (
                    "The revision to get the file from. Can be commit SHA (full or abbreviated), "
                    "branch name, tag, or symbolic reference. Examples: 'abc1234' (commit), "
                    "'main' (branch), 'v1.0.0' (tag), 'HEAD~5' (5 commits ago), "
                    "'feature/auth' (branch)."
                ),
            },
        },
        "required": ["repository_alias", "path", "revision"],
    },
    "required_permission": "query_repos",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {
                "type": "boolean",
                "description": "Whether operation succeeded",
            },
            "path": {"type": "string", "description": "File path requested"},
            "revision": {"type": "string", "description": "Revision requested"},
            "resolved_revision": {
                "type": "string",
                "description": "Resolved full commit SHA",
            },
            "content": {
                "type": "string",
                "description": "File content at the revision",
            },
            "size_bytes": {
                "type": "integer",
                "description": "Size of the file in bytes",
            },
            "error": {"type": "string", "description": "Error message if failed"},
        },
        "required": ["success"],
    },
}

# Tools 27-29: Git Diff/Blame/History (Story #555 - Git Diff and Blame)
TOOL_REGISTRY["git_diff"] = {
    "name": "git_diff",
    "description": (
        "TL;DR: Show line-by-line changes between two revisions (commits, branches, tags). "
        "WHEN TO USE: (1) Compare two commits/branches, (2) See what changed between releases, (3) Review branch differences. "
        "WHEN NOT TO USE: Find commits where code was added/removed -> git_search_diffs | Single commit's changes -> git_show_commit | Browse history -> git_log. "
        "RELATED TOOLS: git_show_commit (single commit diff), git_search_diffs (find code changes), git_log (find commits)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {
                "type": "string",
                "description": "Repository alias or full path.",
            },
            "from_revision": {
                "type": "string",
                "description": (
                    "Starting revision (the 'before' state). Accepts: commit SHA "
                    "(full or abbreviated), branch name ('main', 'develop'), tag ('v1.0.0'), "
                    "relative refs ('HEAD~3', 'main~5'), or 'HEAD'. Example: 'abc123' or 'main~2'."
                ),
            },
            "to_revision": {
                "type": "string",
                "description": (
                    "Ending revision (the 'after' state). Default: HEAD. Same formats as "
                    "from_revision. Common patterns: 'HEAD' (latest), branch name, commit SHA. "
                    "Example: Compare feature branch to main with from='main', to='feature-x'."
                ),
            },
            "path": {
                "type": "string",
                "description": (
                    "Limit diff to this path (file or directory). Relative to repo root. "
                    "Use to focus on specific files/directories in large diffs. "
                    "Examples: 'src/auth.py', 'lib/utils/', '*.md' (all markdown files)."
                ),
            },
            "context_lines": {
                "type": "integer",
                "description": "Context lines around changes. Default: 3.",
                "default": 3,
                "minimum": 0,
                "maximum": 20,
            },
            "stat_only": {
                "type": "boolean",
                "description": "Return only statistics without hunks. Default: false.",
                "default": False,
            },
        },
        "required": ["repository_alias", "from_revision"],
    },
    "required_permission": "query_repos",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "from_revision": {"type": "string"},
            "to_revision": {"type": ["string", "null"]},
            "files": {"type": "array"},
            "total_insertions": {"type": "integer"},
            "total_deletions": {"type": "integer"},
            "stat_summary": {"type": "string"},
            "error": {"type": "string"},
        },
        "required": ["success"],
    },
}

TOOL_REGISTRY["git_blame"] = {
    "name": "git_blame",
    "description": (
        "TL;DR: See who wrote each line of a file and when (line-by-line attribution). "
        "WHEN TO USE: (1) 'Who wrote this code?', (2) Find who introduced a bug, (3) Understand code ownership. "
        "WHEN NOT TO USE: File's commit history -> git_file_history | Full commit details -> git_show_commit. "
        "RELATED TOOLS: git_file_history (commits that modified file), git_show_commit (commit details), git_file_at_revision (view file at any commit)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {
                "type": "string",
                "description": "Repository alias or full path.",
            },
            "path": {
                "type": "string",
                "description": (
                    "Path to file to blame (relative to repo root). Must be a file, not directory. "
                    "Examples: 'src/auth/login.py', 'lib/utils.js', 'README.md'."
                ),
            },
            "revision": {
                "type": "string",
                "description": (
                    "Blame file as of this revision. Default: HEAD (current state). Use to see "
                    "blame at a historical point, e.g., before a refactor. Accepts: commit SHA, "
                    "branch name, tag, or relative ref like 'HEAD~5' or 'v1.0.0'."
                ),
            },
            "start_line": {
                "type": "integer",
                "description": (
                    "First line to include (1-indexed). Use with end_line to focus on specific "
                    "code sections in large files. Example: start_line=100, end_line=150 blames "
                    "lines 100 through 150."
                ),
                "minimum": 1,
            },
            "end_line": {
                "type": "integer",
                "description": (
                    "Last line to include (1-indexed, inclusive). Must be >= start_line. "
                    "Omit both start_line and end_line to blame entire file."
                ),
                "minimum": 1,
            },
        },
        "required": ["repository_alias", "path"],
    },
    "required_permission": "query_repos",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "path": {"type": "string"},
            "revision": {"type": "string"},
            "lines": {"type": "array"},
            "unique_commits": {"type": "integer"},
            "error": {"type": "string"},
        },
        "required": ["success"],
    },
}

TOOL_REGISTRY["git_file_history"] = {
    "name": "git_file_history",
    "description": (
        "TL;DR: Get all commits that modified a specific file. "
        "WHEN TO USE: (1) Track file evolution, (2) Find when bug was introduced, (3) See who worked on a file. "
        "WHEN NOT TO USE: Repo-wide history -> git_log | Line attribution -> git_blame | View old version -> git_file_at_revision. "
        "RELATED TOOLS: git_log (repo-wide history, can also filter by path), git_blame (who wrote each line), git_file_at_revision (view file at commit)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {
                "type": "string",
                "description": "Repository alias or full path.",
            },
            "path": {
                "type": "string",
                "description": (
                    "Path to file (relative to repo root). Must be a file path, not directory. "
                    "Examples: 'src/auth/login.py', 'package.json', 'docs/API.md'."
                ),
            },
            "limit": {
                "type": "integer",
                "description": (
                    "Maximum commits to return. Default: 50. Range: 1-500. For files with long "
                    "history, start with lower limits and use date filters to narrow results."
                ),
                "default": 50,
                "minimum": 1,
                "maximum": 500,
            },
            "follow_renames": {
                "type": "boolean",
                "description": "Follow file history across renames. Default: true.",
                "default": True,
            },
        },
        "required": ["repository_alias", "path"],
    },
    "required_permission": "query_repos",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "path": {"type": "string"},
            "commits": {"type": "array"},
            "total_count": {"type": "integer"},
            "truncated": {"type": "boolean"},
            "renamed_from": {"type": ["string", "null"]},
            "error": {"type": "string"},
        },
        "required": ["success"],
    },
}

# Tools 30-31: Git Content Search (Story #556)
TOOL_REGISTRY["git_search_commits"] = {
    "name": "git_search_commits",
    "description": (
        "TL;DR: Search commit messages for keywords, ticket numbers, or patterns. "
        "WHEN TO USE: (1) Find commits mentioning 'JIRA-123', (2) Search for 'fix bug', (3) Find feature-related commits by message. "
        "WHEN NOT TO USE: Find when code was added/removed -> git_search_diffs | Browse recent history -> git_log | Commit details -> git_show_commit. "
        "RELATED TOOLS: git_search_diffs (search code changes), git_show_commit (view commit), git_log (browse history)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {
                "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}},
                ],
                "description": (
                    "Repository identifier: either an alias (e.g., 'my-project') or "
                    "full path (e.g., '/home/user/repos/my-project'). Use list_global_repos "
                    "to see available repositories and their aliases."
                ),
            },
            "query": {
                "type": "string",
                "description": (
                    "Text or pattern to search for in commit messages. Case-insensitive by "
                    "default. Examples: 'fix authentication', 'JIRA-123', 'refactor.*database'. "
                    "Use is_regex=true for regex patterns."
                ),
            },
            "is_regex": {
                "type": "boolean",
                "description": (
                    "Treat query as a regular expression. Default: false (literal text search). "
                    "When true, uses POSIX extended regex syntax. Example patterns: "
                    "'JIRA-\\d+' for ticket numbers, 'fix(ed)?\\s+bug' for variations."
                ),
                "default": False,
            },
            "author": {
                "type": "string",
                "description": (
                    "Filter to commits by this author. Matches name or email, partial match "
                    "supported. Default: all authors. Examples: 'john@example.com', 'John'."
                ),
            },
            "since": {
                "type": "string",
                "description": (
                    "Search only commits after this date. Format: YYYY-MM-DD or relative "
                    "like '6 months ago'. Default: no date limit. Useful to focus on recent history."
                ),
            },
            "until": {
                "type": "string",
                "description": (
                    "Search only commits before this date. Format: YYYY-MM-DD or relative. "
                    "Default: no date limit. Combine with since for date ranges."
                ),
            },
            "limit": {
                "type": "integer",
                "description": (
                    "Maximum number of matching commits to return. Default: 50. Range: 1-500. "
                    "Popular search terms may match many commits."
                ),
                "default": 50,
                "minimum": 1,
                "maximum": 500,
            },
            "aggregation_mode": {
                "type": "string",
                "enum": ["global", "per_repo"],
                "description": "How to aggregate commit search results across multiple repositories. 'global' (default): Returns top N commits by relevance across ALL repos - best for finding most relevant matches. 'per_repo': Distributes N results evenly across repos - ensures balanced representation (e.g., limit=30 across 3 repos returns ~10 commits from each repo).",
                "default": "global",
            },
            "response_format": {
                "type": "string",
                "enum": ["flat", "grouped"],
                "default": "flat",
                "description": 'Response format for omni-search (multi-repo) results. Only applies when repository_alias is an array.\n\n\'flat\' (default): Returns all results in a single array, each with source_repo field.\nExample response: {"results": [{"file_path": "src/auth.py", "source_repo": "backend-global", "content": "...", "score": 0.95}, {"file_path": "Login.tsx", "source_repo": "frontend-global", "content": "...", "score": 0.89}], "total_results": 2}\n\n\'grouped\': Groups results by repository under results_by_repo object.\nExample response: {"results_by_repo": {"backend-global": {"count": 1, "results": [{"file_path": "src/auth.py", "content": "...", "score": 0.95}]}, "frontend-global": {"count": 1, "results": [{"file_path": "Login.tsx", "content": "...", "score": 0.89}]}}, "total_results": 2}\n\nUse \'grouped\' when you need to process results per-repository or display results organized by source.',
            },
        },
        "required": ["repository_alias", "query"],
    },
    "required_permission": "query_repos",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {
                "type": "boolean",
                "description": "Whether operation succeeded",
            },
            "query": {"type": "string", "description": "Search query used"},
            "is_regex": {
                "type": "boolean",
                "description": "Whether regex mode was used",
            },
            "matches": {
                "type": "array",
                "description": "List of matching commits",
                "items": {
                    "type": "object",
                    "properties": {
                        "hash": {
                            "type": "string",
                            "description": "Full 40-char commit SHA",
                        },
                        "short_hash": {
                            "type": "string",
                            "description": "Abbreviated SHA",
                        },
                        "author_name": {"type": "string", "description": "Author name"},
                        "author_email": {
                            "type": "string",
                            "description": "Author email",
                        },
                        "author_date": {
                            "type": "string",
                            "description": "Author date (ISO 8601)",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Commit subject line",
                        },
                        "body": {
                            "type": "string",
                            "description": "Full commit message body",
                        },
                        "match_highlights": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Lines containing matches",
                        },
                    },
                },
            },
            "total_matches": {
                "type": "integer",
                "description": "Number of matching commits",
            },
            "truncated": {
                "type": "boolean",
                "description": "Whether results were truncated",
            },
            "search_time_ms": {
                "type": "number",
                "description": "Search execution time in ms",
            },
            "error": {"type": "string", "description": "Error message if failed"},
        },
        "required": ["success"],
    },
}

TOOL_REGISTRY["git_search_diffs"] = {
    "name": "git_search_diffs",
    "description": (
        "TL;DR: Find when specific code was added/removed in git history (pickaxe search). "
        "WHAT IS PICKAXE? Git's term for searching code CHANGES (not commit messages). Finds commits where text was introduced or deleted. "
        "WHEN TO USE: (1) 'When was this function added?', (2) 'Who introduced this bug?', (3) Track code pattern evolution. "
        "WHEN NOT TO USE: Search commit messages -> use git_search_commits instead. "
        "WARNING: Can be slow on large repos (may take 1-3+ minutes). Start with limit=5. "
        "RELATED TOOLS: git_search_commits (searches commit messages), git_blame (who wrote current code), git_show_commit (view commit details)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {
                "type": "string",
                "description": (
                    "Repository identifier: either an alias (e.g., 'my-project') or "
                    "full path (e.g., '/home/user/repos/my-project'). Use list_global_repos "
                    "to see available repositories and their aliases."
                ),
            },
            "search_string": {
                "type": "string",
                "description": (
                    "Exact string to search for in diff content. Finds commits where this "
                    "string was added or removed. Use for function names, variable names, "
                    "or specific code. Example: 'calculateTotalPrice'. Mutually exclusive "
                    "with search_pattern."
                ),
            },
            "search_pattern": {
                "type": "string",
                "description": (
                    "Regex pattern to search for in diff content. Finds commits where lines "
                    "matching the pattern were added or removed. Use for flexible matching. "
                    "Example: 'def\\s+calculate.*' to find function definitions. Mutually "
                    "exclusive with search_string. Requires is_regex=true."
                ),
            },
            "is_regex": {
                "type": "boolean",
                "description": (
                    "When true, use search_pattern as regex (-G flag). When false, use "
                    "search_string as literal (-S flag). Default: false. Regex is slower "
                    "but more flexible."
                ),
                "default": False,
            },
            "path": {
                "type": "string",
                "description": (
                    "Limit search to diffs in this path (file or directory). Relative to "
                    "repo root. Default: entire repository. Examples: 'src/auth/', "
                    "'lib/utils.py'."
                ),
            },
            "since": {
                "type": "string",
                "description": (
                    "Search only commits after this date. Format: YYYY-MM-DD or relative. "
                    "Default: no limit. Useful to narrow down large search results."
                ),
            },
            "until": {
                "type": "string",
                "description": (
                    "Search only commits before this date. Format: YYYY-MM-DD or relative. "
                    "Default: no limit."
                ),
            },
            "limit": {
                "type": "integer",
                "description": (
                    "Maximum number of matching commits to return. Default: 50. Range: 1-200. "
                    "Diff search is computationally expensive; lower limits recommended. "
                    "Response indicates if results were truncated."
                ),
                "default": 50,
                "minimum": 1,
                "maximum": 200,
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
            "search_term": {"type": "string", "description": "Search term used"},
            "is_regex": {
                "type": "boolean",
                "description": "Whether regex mode was used",
            },
            "matches": {
                "type": "array",
                "description": "List of commits that added/removed matching content",
                "items": {
                    "type": "object",
                    "properties": {
                        "hash": {
                            "type": "string",
                            "description": "Full 40-char commit SHA",
                        },
                        "short_hash": {
                            "type": "string",
                            "description": "Abbreviated SHA",
                        },
                        "author_name": {"type": "string", "description": "Author name"},
                        "author_date": {
                            "type": "string",
                            "description": "Author date (ISO 8601)",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Commit subject line",
                        },
                        "files_changed": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Files modified in this commit",
                        },
                        "diff_snippet": {
                            "type": ["string", "null"],
                            "description": "Relevant portion of diff (if available)",
                        },
                    },
                },
            },
            "total_matches": {
                "type": "integer",
                "description": "Number of matching commits",
            },
            "truncated": {
                "type": "boolean",
                "description": "Whether results were truncated",
            },
            "search_time_ms": {
                "type": "number",
                "description": "Search execution time in ms",
            },
            "error": {"type": "string", "description": "Error message if failed"},
        },
        "required": ["success"],
    },
}

# Tool 32: Directory Tree (Story #557 - Remote Repository Exploration)
TOOL_REGISTRY["directory_tree"] = {
    "name": "directory_tree",
    "description": (
        "TL;DR: Visual ASCII tree of directory structure (like 'tree' command). "
        "WHEN TO USE: (1) Understand project layout, (2) Explore unfamiliar codebase, (3) Find where files are located. "
        "COMPARISON: directory_tree = visual hierarchy | browse_directory = flat list with metadata (size, language, dates). "
        "RELATED TOOLS: browse_directory (flat list with file details), get_file_content (read files)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {
                "type": "string",
                "description": (
                    "Repository identifier: either an alias (e.g., 'my-project') or "
                    "full path (e.g., '/home/user/repos/my-project'). Use list_global_repos "
                    "to see available repositories and their aliases."
                ),
            },
            "path": {
                "type": "string",
                "description": (
                    "Subdirectory to use as tree root (relative to repo root). Default: "
                    "repository root. Examples: 'src' shows tree starting from src/, "
                    "'lib/utils' shows tree starting from lib/utils/."
                ),
            },
            "max_depth": {
                "type": "integer",
                "description": (
                    "Maximum depth of tree to display. Default: 3. Range: 1-10. Deeper "
                    "directories show '[...]' indicator. Use 1 for top-level overview, "
                    "higher values for detailed exploration."
                ),
                "default": 3,
                "minimum": 1,
                "maximum": 10,
            },
            "max_files_per_dir": {
                "type": "integer",
                "description": (
                    "Maximum files to show per directory before truncating. Default: 50. "
                    "Range: 1-200. Directories with more files show '[+N more files]'. "
                    "Use lower values for cleaner output on large directories."
                ),
                "default": 50,
                "minimum": 1,
                "maximum": 200,
            },
            "include_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Glob patterns for files to include. Only matching files shown; "
                    "directories shown if they contain matches. Default: all files. "
                    "Examples: ['*.py'] for Python, ['*.ts', '*.tsx'] for TypeScript, "
                    "['Makefile', '*.mk'] for makefiles."
                ),
            },
            "exclude_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Glob patterns for files/directories to exclude. Default excludes: "
                    ".git, node_modules, __pycache__, .venv, .idea, .vscode. Additional "
                    "patterns are merged with defaults. Examples: ['*.log', 'dist/', 'build/']."
                ),
            },
            "show_stats": {
                "type": "boolean",
                "description": (
                    "Show statistics: file counts per directory, total files/dirs. "
                    "Default: false. When true, adds summary like '15 directories, 127 files'."
                ),
                "default": False,
            },
            "include_hidden": {
                "type": "boolean",
                "description": (
                    "Include hidden files/directories (starting with dot). Default: false. "
                    "Note: .git is always excluded regardless of this setting. Set to true "
                    "to see .env, .gitignore, .eslintrc, etc."
                ),
                "default": False,
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
            "tree_string": {
                "type": "string",
                "description": "Pre-formatted tree output with ASCII characters",
            },
            "root": {
                "type": "object",
                "description": "Root TreeNode with hierarchical structure",
                "properties": {
                    "name": {"type": "string", "description": "Directory/file name"},
                    "path": {
                        "type": "string",
                        "description": "Relative path from repo root",
                    },
                    "is_directory": {
                        "type": "boolean",
                        "description": "True if directory",
                    },
                    "children": {
                        "type": ["array", "null"],
                        "description": "Child nodes (null for files)",
                    },
                    "truncated": {
                        "type": "boolean",
                        "description": "True if max_files exceeded",
                    },
                    "hidden_count": {
                        "type": "integer",
                        "description": "Number of hidden children",
                    },
                },
            },
            "total_directories": {
                "type": "integer",
                "description": "Total number of directories",
            },
            "total_files": {"type": "integer", "description": "Total number of files"},
            "max_depth_reached": {
                "type": "boolean",
                "description": "Whether max_depth limit was reached",
            },
            "root_path": {
                "type": "string",
                "description": "Filesystem path to tree root",
            },
            "error": {"type": "string", "description": "Error message if failed"},
        },
        "required": ["success"],
    },
}

# Tool 10: Authenticate (Public endpoint)
TOOL_REGISTRY["authenticate"] = {
    "name": "authenticate",
    "description": (
        "TL;DR: Authenticate with username and API key to establish session. "
        "WHEN TO USE: Required before using other tools on /mcp-public endpoint. "
        "WHEN NOT TO USE: Already authenticated. "
        "RELATED TOOLS: create_user (create new user account)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "username": {"type": "string", "description": "Username"},
            "api_key": {
                "type": "string",
                "description": "API key (format: cidx_sk_...)",
            },
        },
        "required": ["username", "api_key"],
    },
    "required_permission": "public",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {
                "type": "boolean",
                "description": "Whether authentication succeeded",
            },
            "token": {
                "type": "string",
                "description": "JWT session token for subsequent requests",
            },
            "error": {"type": "string", "description": "Error message if failed"},
        },
        "required": ["success"],
    },
}

# Tool 11: SSH Key Create (Story #584)
TOOL_REGISTRY["cidx_ssh_key_create"] = {
    "name": "cidx_ssh_key_create",
    "description": (
        "TL;DR: Create new SSH key pair managed by CIDX server. "
        "WHEN TO USE: (1) Generate SSH key for remote repository access, "
        "(2) Create key with specific type (ed25519/rsa), "
        "(3) Generate key with email/description metadata. "
        "WHEN NOT TO USE: Key already exists with that name -> delete first | "
        "Need to import existing key -> not yet supported. "
        "SECURITY: Keys stored in ~/.ssh/ with metadata in ~/.code-indexer-server/ssh_keys/. "
        "Generated keys are 4096-bit RSA or Ed25519 (default). "
        "RELATED TOOLS: cidx_ssh_key_list (view keys), cidx_ssh_key_assign_host "
        "(configure SSH host), cidx_ssh_key_show_public (get public key for server upload)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Key name (identifier). Must be filesystem-safe (alphanumeric, "
                    "dashes, underscores). Used for filenames: ~/.ssh/cidx-managed-{name}"
                ),
            },
            "key_type": {
                "type": "string",
                "enum": ["ed25519", "rsa"],
                "default": "ed25519",
                "description": (
                    "Key type to generate. ed25519: Modern, secure, fast (default). "
                    "rsa: 4096-bit, wider compatibility with older systems."
                ),
            },
            "email": {
                "type": "string",
                "description": (
                    "Email address for key comment (appears in public key). "
                    "Optional but recommended for key identification on remote servers."
                ),
            },
            "description": {
                "type": "string",
                "description": (
                    "Human-readable description of key purpose. "
                    "Example: 'GitHub personal repos' or 'Production server access'"
                ),
            },
        },
        "required": ["name"],
    },
    "required_permission": "activate_repos",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {
                "type": "boolean",
                "description": "Whether key creation succeeded",
            },
            "name": {"type": "string", "description": "Key name (identifier)"},
            "fingerprint": {
                "type": "string",
                "description": "SSH key fingerprint (SHA256)",
            },
            "key_type": {"type": "string", "description": "Key type (ed25519/rsa)"},
            "public_key": {
                "type": "string",
                "description": (
                    "Full public key content (suitable for copying to authorized_keys "
                    "or git hosting services)"
                ),
            },
            "email": {
                "type": ["string", "null"],
                "description": "Email address (if provided)",
            },
            "description": {
                "type": ["string", "null"],
                "description": "Key description (if provided)",
            },
            "error": {"type": "string", "description": "Error message if failed"},
        },
        "required": ["success"],
    },
}

# Tool 12: SSH Key List (Story #584)
TOOL_REGISTRY["cidx_ssh_key_list"] = {
    "name": "cidx_ssh_key_list",
    "description": (
        "TL;DR: List all SSH keys (CIDX-managed and unmanaged). "
        "WHEN TO USE: (1) See available keys, (2) Check key fingerprints, "
        "(3) View which hosts are assigned to each key, (4) Discover unmanaged keys in ~/.ssh. "
        "WHEN NOT TO USE: Need public key content -> use cidx_ssh_key_show_public. "
        "KEY TYPES: Managed keys have metadata (email, description, hosts), "
        "unmanaged keys are detected in ~/.ssh but not managed by CIDX. "
        "RELATED TOOLS: cidx_ssh_key_create (create key), cidx_ssh_key_show_public "
        "(get public key), cidx_ssh_key_assign_host (assign to host)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {},
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
            "managed": {
                "type": "array",
                "description": "CIDX-managed keys with full metadata",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Key name"},
                        "fingerprint": {
                            "type": "string",
                            "description": "SSH fingerprint (SHA256)",
                        },
                        "key_type": {
                            "type": "string",
                            "description": "Key type (ed25519/rsa)",
                        },
                        "hosts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Hostnames configured in SSH config",
                        },
                        "email": {
                            "type": ["string", "null"],
                            "description": "Email address",
                        },
                        "description": {
                            "type": ["string", "null"],
                            "description": "Key description",
                        },
                        "is_imported": {
                            "type": "boolean",
                            "description": "Whether key was imported (not yet implemented)",
                        },
                    },
                },
            },
            "unmanaged": {
                "type": "array",
                "description": (
                    "Keys detected in ~/.ssh but not managed by CIDX "
                    "(cannot be assigned to hosts or deleted via CIDX)"
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Filename without extension",
                        },
                        "fingerprint": {
                            "type": "string",
                            "description": "SSH fingerprint (SHA256)",
                        },
                        "private_path": {
                            "type": "string",
                            "description": "Full path to private key file",
                        },
                    },
                },
            },
            "error": {"type": "string", "description": "Error message if failed"},
        },
        "required": ["success"],
    },
}

# Tool 13: SSH Key Delete (Story #584)
TOOL_REGISTRY["cidx_ssh_key_delete"] = {
    "name": "cidx_ssh_key_delete",
    "description": (
        "TL;DR: Delete CIDX-managed SSH key and remove from SSH config. "
        "WHEN TO USE: (1) Remove unused key, (2) Rotate compromised key, "
        "(3) Clean up old keys. "
        "WHEN NOT TO USE: Key is actively used by repositories -> reassign hosts first. "
        "SECURITY WARNING: Deletes both private and public key files from ~/.ssh/. "
        "Removes all Host entries from SSH config that use this key. "
        "Operation is IDEMPOTENT (always succeeds even if key doesn't exist). "
        "DESTRUCTIVE: Cannot be undone. "
        "RELATED TOOLS: cidx_ssh_key_list (view keys before deletion), "
        "cidx_ssh_key_create (create replacement key)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Key name to delete",
            },
        },
        "required": ["name"],
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
                "description": "Confirmation message",
            },
            "error": {"type": "string", "description": "Error message if failed"},
        },
        "required": ["success"],
    },
}

# Tool 14: SSH Key Show Public (Story #584)
TOOL_REGISTRY["cidx_ssh_key_show_public"] = {
    "name": "cidx_ssh_key_show_public",
    "description": (
        "TL;DR: Get public key content for copying to remote servers. "
        "WHEN TO USE: (1) Upload public key to GitHub/GitLab, "
        "(2) Add to authorized_keys on remote server, "
        "(3) Share public key with team member. "
        "WHEN NOT TO USE: Need full key metadata -> use cidx_ssh_key_list. "
        "OUTPUT: Returns formatted public key string suitable for direct copy/paste "
        "to authorized_keys or git hosting services. "
        "SECURITY: Only returns PUBLIC key (safe to share). Private key never exposed. "
        "RELATED TOOLS: cidx_ssh_key_list (view all keys), cidx_ssh_key_create "
        "(create new key), cidx_ssh_key_assign_host (configure SSH host)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Key name to retrieve public key for",
            },
        },
        "required": ["name"],
    },
    "required_permission": "activate_repos",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {
                "type": "boolean",
                "description": "Whether operation succeeded",
            },
            "name": {"type": "string", "description": "Key name"},
            "public_key": {
                "type": "string",
                "description": (
                    "Full public key content (suitable for copying to authorized_keys "
                    "or git hosting services). Format: 'ssh-ed25519 AAAA... user@host' "
                    "or 'ssh-rsa AAAA... user@host'"
                ),
            },
            "error": {"type": "string", "description": "Error message if failed"},
        },
        "required": ["success"],
    },
}

# Tool 15: SSH Key Assign Host (Story #584)
TOOL_REGISTRY["cidx_ssh_key_assign_host"] = {
    "name": "cidx_ssh_key_assign_host",
    "description": (
        "TL;DR: Assign SSH key to hostname in SSH config (~/.ssh/config). "
        "WHEN TO USE: (1) Configure key for GitHub/GitLab host, "
        "(2) Set up key for remote server access, "
        "(3) Create SSH Host entry for repository cloning. "
        "WHEN NOT TO USE: Host already configured -> use force=true to override. "
        "CONFIGURATION: Adds 'Host {hostname}' entry to SSH config with IdentityFile "
        "pointing to the managed key. Updates ~/.ssh/config with proper formatting "
        "and preserves existing configuration. "
        "CONFLICT HANDLING: By default, fails if hostname already exists in SSH config. "
        "Use force=true to replace existing Host entry. "
        "RELATED TOOLS: cidx_ssh_key_create (create key first), "
        "cidx_ssh_key_list (view configured hosts), cidx_ssh_key_show_public "
        "(get public key for remote server setup)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Key name to assign",
            },
            "hostname": {
                "type": "string",
                "description": (
                    "Hostname or Host alias for SSH config. Examples: 'github.com', "
                    "'gitlab.com', 'myserver.example.com', 'production-server'"
                ),
            },
            "force": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Force overwrite if hostname already exists in SSH config. "
                    "Default: false (fails on conflict). Set to true to replace "
                    "existing Host entry."
                ),
            },
        },
        "required": ["name", "hostname"],
    },
    "required_permission": "activate_repos",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {
                "type": "boolean",
                "description": "Whether operation succeeded",
            },
            "name": {"type": "string", "description": "Key name"},
            "fingerprint": {
                "type": "string",
                "description": "SSH key fingerprint (SHA256)",
            },
            "key_type": {"type": "string", "description": "Key type (ed25519/rsa)"},
            "hosts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "All hostnames now configured for this key",
            },
            "email": {
                "type": ["string", "null"],
                "description": "Email address",
            },
            "description": {
                "type": ["string", "null"],
                "description": "Key description",
            },
            "error": {"type": "string", "description": "Error message if failed"},
        },
        "required": ["success"],
    },
}

# =============================================================================
# SCIP (Code Intelligence) Tools
# =============================================================================

TOOL_REGISTRY["scip_definition"] = {
    "name": "scip_definition",
    "description": (
        "TL;DR: Find where a symbol is defined (class, function, method). Returns exact file location, line number, and symbol kind. "
        "SYMBOL FORMAT: Pass simple names like 'UserService', 'authenticate', 'DatabaseManager'. SCIP will match fuzzy by default - 'User' matches 'UserService', 'UserManager', etc. For exact matching, use exact=true. Full SCIP format like 'scip-python python code-indexer abc123 `module`/ClassName#method().' is handled internally - you only provide the readable part. "
        "FUZZY VS EXACT MATCHING: Fuzzy (default, exact=false) uses substring matching - 'User' matches 'UserService', 'UserManager', 'UserRepository'. Fast and flexible, best for exploration when you don't know the exact symbol name. Exact (exact=true) uses precise matching - 'UserService' only matches 'UserService'. Slower but guaranteed accuracy, best when you know the exact symbol name and want no false positives. "
        "WHEN TO USE: Finding where a class/function/method is defined. Locating the source of a symbol before reading its implementation. Understanding what a symbol is (class vs function vs method). First step before using scip_references, scip_dependencies, or scip_dependents. "
        "WHEN NOT TO USE: Finding all usages of a symbol (use scip_references instead). Understanding what a symbol depends on (use scip_dependencies). Understanding what depends on a symbol (use scip_dependents). Impact analysis (use scip_impact). Tracing call paths (use scip_callchain). Getting curated file list for a symbol (use scip_context). "
        "REQUIRES: SCIP indexes must be generated via 'cidx scip generate' before querying. Check .code-indexer/scip/ directory for .scip files. "
        "RELATED TOOLS: scip_references (find all usages), scip_dependencies (what symbol depends on), scip_dependents (what depends on symbol), scip_context (get curated file list). "
        "EXAMPLE: {\"symbol\": \"DatabaseManager\", \"exact\": false} returns [{\"symbol\": \"com.example.DatabaseManager\", \"project\": \"code-indexer\", \"file_path\": \"src/code_indexer/scip/database/schema.py\", \"line\": 13, \"column\": 0, \"kind\": \"class\", \"relationship\": null, \"context\": null}]"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Symbol name to find definition for (e.g., 'UserService', 'authenticate', 'DatabaseManager')",
            },
            "exact": {
                "type": "boolean",
                "default": False,
                "description": "Use exact matching instead of fuzzy substring matching. Default false for flexible exploration.",
            },
            "project": {
                "type": ["string", "null"],
                "default": None,
                "description": "Optional project filter to limit search to specific project",
            },
        },
        "required": ["symbol"],
    },
    "required_permission": "query_repos",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Whether the operation succeeded"},
            "symbol": {"type": "string", "description": "Symbol name that was searched for"},
            "total_results": {"type": "integer", "description": "Total number of definitions found"},
            "results": {
                "type": "array",
                "description": "List of definition locations",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Full SCIP symbol identifier"},
                        "project": {"type": "string", "description": "Project path"},
                        "file_path": {"type": "string", "description": "File path relative to project root"},
                        "line": {"type": "integer", "description": "Line number (1-indexed)"},
                        "column": {"type": "integer", "description": "Column number (0-indexed)"},
                        "kind": {"type": "string", "description": "Symbol kind (class, function, method, variable, etc.)"},
                        "relationship": {"type": ["string", "null"], "description": "Relationship type (always null for definitions)"},
                        "context": {"type": ["string", "null"], "description": "Additional context (always null for definitions)"},
                    },
                    "required": ["symbol", "project", "file_path", "line", "column", "kind"],
                },
            },
            "error": {"type": "string", "description": "Error message if operation failed"},
        },
        "required": ["success", "results"],
    },
}

TOOL_REGISTRY["scip_references"] = {
    "name": "scip_references",
    "description": (
        "TL;DR: Find all places where a symbol is used/referenced (imports, calls, instantiations). Returns file locations, line numbers, and usage context. "
        "SYMBOL FORMAT: Pass simple names like 'UserService', 'authenticate', 'DatabaseManager'. SCIP will match fuzzy by default - 'User' matches 'UserService', 'UserManager', etc. For exact matching, use exact=true. Full SCIP format like 'scip-python python code-indexer abc123 `module`/ClassName#method().' is handled internally - you only provide the readable part. "
        "FUZZY VS EXACT MATCHING: Fuzzy (default, exact=false) uses substring matching - 'User' matches 'UserService', 'UserManager', 'UserRepository'. Fast and flexible, best for exploration when you want to find all related usages. Exact (exact=true) uses precise matching - 'UserService' only matches 'UserService'. Slower but guaranteed accuracy, best when you know the exact symbol name and want only its references. "
        "WHEN TO USE: Finding all code that uses/imports/calls a symbol. Understanding how widespread a symbol's usage is. Identifying all callsites before refactoring. Finding examples of how a symbol is used in practice. "
        "WHEN NOT TO USE: Finding where a symbol is defined (use scip_definition instead). Understanding what a symbol depends on (use scip_dependencies). Understanding what depends on a symbol (use scip_dependents - references show usage points, dependents show dependent symbols). Impact analysis (use scip_impact). Tracing call paths (use scip_callchain). Getting curated file list (use scip_context). "
        "REQUIRES: SCIP indexes must be generated via 'cidx scip generate' before querying. Check .code-indexer/scip/ directory for .scip files. "
        "RELATED TOOLS: scip_definition (find definition), scip_dependents (what symbols depend on target), scip_impact (recursive dependency analysis), scip_context (get curated file list). "
        "EXAMPLE: {\"symbol\": \"DatabaseManager\", \"limit\": 100, \"exact\": false} returns [{\"symbol\": \"com.example.DatabaseManager\", \"project\": \"code-indexer\", \"file_path\": \"src/code_indexer/scip/query/primitives.py\", \"line\": 42, \"column\": 8, \"kind\": \"reference\", \"relationship\": \"import\", \"context\": \"from code_indexer.scip.database.schema import DatabaseManager\"}]"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Symbol name to find references for (e.g., 'UserService', 'authenticate', 'DatabaseManager')",
            },
            "limit": {
                "type": "integer",
                "default": 100,
                "description": "Maximum number of references to return. Default 100.",
            },
            "exact": {
                "type": "boolean",
                "default": False,
                "description": "Use exact matching instead of fuzzy substring matching. Default false for flexible exploration.",
            },
            "project": {
                "type": ["string", "null"],
                "default": None,
                "description": "Optional project filter to limit search to specific project",
            },
        },
        "required": ["symbol"],
    },
    "required_permission": "query_repos",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Whether the operation succeeded"},
            "symbol": {"type": "string", "description": "Symbol name that was searched for"},
            "total_results": {"type": "integer", "description": "Total number of references found"},
            "results": {
                "type": "array",
                "description": "List of reference locations",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Full SCIP symbol identifier"},
                        "project": {"type": "string", "description": "Project path"},
                        "file_path": {"type": "string", "description": "File path relative to project root"},
                        "line": {"type": "integer", "description": "Line number (1-indexed)"},
                        "column": {"type": "integer", "description": "Column number (0-indexed)"},
                        "kind": {"type": "string", "description": "Symbol kind (reference)"},
                        "relationship": {"type": ["string", "null"], "description": "Relationship type (import, call, instantiation, etc.)"},
                        "context": {"type": ["string", "null"], "description": "Code context where reference occurs"},
                    },
                    "required": ["symbol", "project", "file_path", "line", "column", "kind"],
                },
            },
            "error": {"type": "string", "description": "Error message if operation failed"},
        },
        "required": ["success", "results"],
    },
}

TOOL_REGISTRY["scip_dependencies"] = {
    "name": "scip_dependencies",
    "description": (
        "TL;DR: Find what a symbol depends on (imports, calls, uses). Returns symbols and files that the target symbol requires to function. "
        "SYMBOL FORMAT: Pass simple names like 'UserService', 'authenticate', 'DatabaseManager'. SCIP will match fuzzy by default - 'User' matches 'UserService', 'UserManager', etc. For exact matching, use exact=true. Full SCIP format like 'scip-python python code-indexer abc123 `module`/ClassName#method().' is handled internally - you only provide the readable part. "
        "FUZZY VS EXACT MATCHING: Fuzzy (default, exact=false) uses substring matching - 'User' matches 'UserService', 'UserManager', 'UserRepository'. Fast and flexible, best for exploration. Exact (exact=true) uses precise matching - 'UserService' only matches 'UserService'. Slower but guaranteed accuracy, best when you know the exact symbol name. "
        "WHEN TO USE: Understanding what a symbol needs to work (its dependencies). Identifying imports and external dependencies. Finding all symbols a target symbol calls or uses. Understanding coupling and dependency relationships. Planning refactoring by understanding dependencies. "
        "WHEN NOT TO USE: Finding what depends on a symbol (use scip_dependents instead - opposite direction). Finding all usages (use scip_references). Finding definitions (use scip_definition). Impact analysis (use scip_impact for recursive dependency tree). Tracing call paths (use scip_callchain). Getting curated file list (use scip_context). "
        "REQUIRES: SCIP indexes must be generated via 'cidx scip generate' before querying. Check .code-indexer/scip/ directory for .scip files. "
        "RELATED TOOLS: scip_dependents (opposite direction - what depends on symbol), scip_impact (recursive dependency analysis), scip_definition (find symbol definition), scip_context (get curated file list). "
        "EXAMPLE: {\"symbol\": \"SCIPQueryEngine\", \"depth\": 1, \"exact\": false} returns [{\"symbol\": \"com.example.DatabaseManager\", \"project\": \"code-indexer\", \"file_path\": \"src/code_indexer/scip/query/primitives.py\", \"line\": 15, \"column\": 0, \"kind\": \"dependency\", \"relationship\": \"import\", \"context\": \"from code_indexer.scip.database.schema import DatabaseManager\"}]"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Symbol name to find dependencies for (e.g., 'UserService', 'authenticate', 'DatabaseManager')",
            },
            "depth": {
                "type": "integer",
                "default": 1,
                "description": "Dependency traversal depth. Default 1 for direct dependencies only.",
            },
            "exact": {
                "type": "boolean",
                "default": False,
                "description": "Use exact matching instead of fuzzy substring matching. Default false for flexible exploration.",
            },
            "project": {
                "type": ["string", "null"],
                "default": None,
                "description": "Optional project filter to limit search to specific project",
            },
        },
        "required": ["symbol"],
    },
    "required_permission": "query_repos",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Whether the operation succeeded"},
            "symbol": {"type": "string", "description": "Symbol name that was searched for"},
            "total_results": {"type": "integer", "description": "Total number of dependencies found"},
            "results": {
                "type": "array",
                "description": "List of dependency symbols",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Full SCIP symbol identifier of dependency"},
                        "project": {"type": "string", "description": "Project path"},
                        "file_path": {"type": "string", "description": "File path relative to project root"},
                        "line": {"type": "integer", "description": "Line number (1-indexed)"},
                        "column": {"type": "integer", "description": "Column number (0-indexed)"},
                        "kind": {"type": "string", "description": "Symbol kind (dependency)"},
                        "relationship": {"type": ["string", "null"], "description": "Relationship type (import, call, use, etc.)"},
                        "context": {"type": ["string", "null"], "description": "Code context where dependency occurs"},
                    },
                    "required": ["symbol", "project", "file_path", "line", "column", "kind"],
                },
            },
            "error": {"type": "string", "description": "Error message if operation failed"},
        },
        "required": ["success", "results"],
    },
}

TOOL_REGISTRY["scip_dependents"] = {
    "name": "scip_dependents",
    "description": (
        "TL;DR: Find what depends on a symbol (reverse dependencies). Returns symbols and files that require/use the target symbol. Opposite of scip_dependencies. "
        "SYMBOL FORMAT: Pass simple names like 'UserService', 'authenticate', 'DatabaseManager'. SCIP will match fuzzy by default - 'User' matches 'UserService', 'UserManager', etc. For exact matching, use exact=true. Full SCIP format like 'scip-python python code-indexer abc123 `module`/ClassName#method().' is handled internally - you only provide the readable part. "
        "FUZZY VS EXACT MATCHING: Fuzzy (default, exact=false) uses substring matching - 'User' matches 'UserService', 'UserManager', 'UserRepository'. Fast and flexible, best for exploration. Exact (exact=true) uses precise matching - 'UserService' only matches 'UserService'. Slower but guaranteed accuracy, best when you know the exact symbol name. "
        "WHEN TO USE: Understanding impact of changing a symbol (what will break). Finding all code that relies on a symbol. Identifying coupling and understanding how widely a symbol is used. Planning refactoring by understanding dependent code. Understanding blast radius before modifying a symbol. "
        "WHEN NOT TO USE: Finding what a symbol depends on (use scip_dependencies instead - opposite direction). Finding all usages (use scip_references for raw usage points). Finding definitions (use scip_definition). Full recursive impact analysis (use scip_impact for complete dependency tree). Tracing call paths (use scip_callchain). Getting curated file list (use scip_context). "
        "REQUIRES: SCIP indexes must be generated via 'cidx scip generate' before querying. Check .code-indexer/scip/ directory for .scip files. "
        "RELATED TOOLS: scip_dependencies (opposite direction - what symbol depends on), scip_impact (recursive dependency analysis), scip_references (raw usage points), scip_context (get curated file list). "
        "EXAMPLE: {\"symbol\": \"DatabaseManager\", \"depth\": 1, \"exact\": false} returns [{\"symbol\": \"com.example.SCIPQueryEngine\", \"project\": \"code-indexer\", \"file_path\": \"src/code_indexer/scip/query/primitives.py\", \"line\": 15, \"column\": 0, \"kind\": \"dependent\", \"relationship\": \"uses\", \"context\": \"self.db = DatabaseManager()\"}]"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Symbol name to find dependents for (e.g., 'UserService', 'authenticate', 'DatabaseManager')",
            },
            "depth": {
                "type": "integer",
                "default": 1,
                "description": "Dependent traversal depth. Default 1 for direct dependents only.",
            },
            "exact": {
                "type": "boolean",
                "default": False,
                "description": "Use exact matching instead of fuzzy substring matching. Default false for flexible exploration.",
            },
            "project": {
                "type": ["string", "null"],
                "default": None,
                "description": "Optional project filter to limit search to specific project",
            },
        },
        "required": ["symbol"],
    },
    "required_permission": "query_repos",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Whether the operation succeeded"},
            "symbol": {"type": "string", "description": "Symbol name that was searched for"},
            "total_results": {"type": "integer", "description": "Total number of dependents found"},
            "results": {
                "type": "array",
                "description": "List of dependent symbols",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Full SCIP symbol identifier of dependent"},
                        "project": {"type": "string", "description": "Project path"},
                        "file_path": {"type": "string", "description": "File path relative to project root"},
                        "line": {"type": "integer", "description": "Line number (1-indexed)"},
                        "column": {"type": "integer", "description": "Column number (0-indexed)"},
                        "kind": {"type": "string", "description": "Symbol kind (dependent)"},
                        "relationship": {"type": ["string", "null"], "description": "Relationship type (uses, calls, imports, etc.)"},
                        "context": {"type": ["string", "null"], "description": "Code context where dependent uses target"},
                    },
                    "required": ["symbol", "project", "file_path", "line", "column", "kind"],
                },
            },
            "error": {"type": "string", "description": "Error message if operation failed"},
        },
        "required": ["success", "results"],
    },
}

TOOL_REGISTRY["scip_impact"] = {
    "name": "scip_impact",
    "description": (
        "TL;DR: Recursive impact analysis - find ALL symbols and files affected by changing a symbol. Returns complete dependency tree with depth tracking and file-level summaries. Use this for comprehensive change impact assessment. "
        "SYMBOL FORMAT: Pass simple names like 'UserService', 'authenticate', 'DatabaseManager'. SCIP will match fuzzy by default. Full SCIP format like 'scip-python python code-indexer abc123 `module`/ClassName#method().' is handled internally - you only provide the readable part. "
        "DEPTH BEHAVIOR: Results grow linearly with depth (BFS traversal with cycle detection prevents exponential growth). depth=1 shows direct dependents, depth=2 adds dependents-of-dependents, depth=3 adds third-level dependents. Use depth=3 (default) for comprehensive analysis, depth=5+ for mission-critical changes requiring complete blast radius understanding. Higher depth increases query time but ensures complete impact visibility. "
        "WHEN TO USE: Understanding full blast radius of changing a symbol. Planning refactoring with complete dependency tree visibility. Assessing risk before modifying critical code. Generating file lists for comprehensive testing. Understanding cascading dependencies across multiple levels. Finding all code that transitively depends on a symbol. "
        "WHEN NOT TO USE: Finding direct dependencies only (use scip_dependencies for faster single-level query). Finding direct dependents only (use scip_dependents for faster single-level query). Simple usage point lookup (use scip_references). Finding definitions (use scip_definition). Tracing specific call paths (use scip_callchain). Getting prioritized file list for reading (use scip_context). "
        "REQUIRES: SCIP indexes must be generated via 'cidx scip generate' before querying. Check .code-indexer/scip/ directory for .scip files. "
        "RELATED TOOLS: scip_dependents (single-level dependents), scip_dependencies (single-level dependencies), scip_callchain (trace call paths), scip_context (get curated file list with relevance scoring). "
        "EXAMPLE: {\"symbol\": \"DatabaseManager\", \"depth\": 3} returns {\"target_symbol\": \"com.example.DatabaseManager\", \"depth_analyzed\": 3, \"total_affected\": 47, \"affected_symbols\": [{\"symbol\": \"SCIPQueryEngine\", \"file_path\": \"src/code_indexer/scip/query/primitives.py\", \"line\": 15, \"column\": 0, \"depth\": 1, \"relationship\": \"uses\", \"chain\": [\"DatabaseManager\", \"SCIPQueryEngine\"]}], \"affected_files\": [{\"path\": \"src/code_indexer/scip/query/primitives.py\", \"project\": \"code-indexer\", \"affected_symbol_count\": 3, \"min_depth\": 1, \"max_depth\": 2}]}"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Symbol name to analyze impact for (e.g., 'UserService', 'authenticate', 'DatabaseManager')",
            },
            "depth": {
                "type": "integer",
                "default": 3,
                "description": "Recursive traversal depth for impact analysis. Default 3. Max 10. Higher depth = more complete analysis but slower query.",
            },
            "project": {
                "type": ["string", "null"],
                "default": None,
                "description": "Optional project filter to limit search to specific project",
            },
        },
        "required": ["symbol"],
    },
    "required_permission": "query_repos",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Whether the operation succeeded"},
            "target_symbol": {"type": "string", "description": "Full SCIP symbol identifier analyzed"},
            "depth_analyzed": {"type": "integer", "description": "Actual depth analyzed"},
            "total_affected": {"type": "integer", "description": "Total number of affected symbols"},
            "truncated": {"type": "boolean", "description": "Whether results were truncated due to size limits"},
            "affected_symbols": {
                "type": "array",
                "description": "List of all symbols affected by changing target symbol",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Full SCIP symbol identifier"},
                        "file_path": {"type": "string", "description": "File path relative to project root"},
                        "line": {"type": "integer", "description": "Line number (1-indexed)"},
                        "column": {"type": "integer", "description": "Column number (0-indexed)"},
                        "depth": {"type": "integer", "description": "Depth level in dependency tree"},
                        "relationship": {"type": "string", "description": "Relationship type (uses, calls, imports, etc.)"},
                        "chain": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Dependency chain from target to this symbol",
                        },
                    },
                    "required": ["symbol", "file_path", "line", "column", "depth", "relationship", "chain"],
                },
            },
            "affected_files": {
                "type": "array",
                "description": "File-level summary of impact",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to project root"},
                        "project": {"type": "string", "description": "Project path"},
                        "affected_symbol_count": {"type": "integer", "description": "Number of affected symbols in file"},
                        "min_depth": {"type": "integer", "description": "Minimum depth of affected symbols"},
                        "max_depth": {"type": "integer", "description": "Maximum depth of affected symbols"},
                    },
                    "required": ["path", "project", "affected_symbol_count", "min_depth", "max_depth"],
                },
            },
            "error": {"type": "string", "description": "Error message if operation failed"},
        },
        "required": ["success", "affected_symbols", "affected_files"],
    },
}

TOOL_REGISTRY["scip_callchain"] = {
    "name": "scip_callchain",
    "description": (
        "TL;DR: Find call chains/paths between two symbols. Returns all possible call paths showing how from_symbol can reach to_symbol. Use this for tracing execution flow and understanding call relationships. "
        "SYMBOL FORMAT: Pass simple names like 'UserService', 'authenticate', 'DatabaseManager'. SCIP will match fuzzy by default. Full SCIP format like 'scip-python python code-indexer abc123 `module`/ClassName#method().' is handled internally - you only provide the readable part. "
        "DEPTH BEHAVIOR: Results grow linearly with depth (BFS traversal with cycle detection prevents exponential growth). max_depth=5 searches 5 levels deep for call paths. Higher max_depth finds longer chains but increases query time. Start with default max_depth=10, increase to 20 if no paths found and symbols are distantly connected. "
        "WHEN TO USE: Understanding how one symbol calls/reaches another. Tracing execution flow between components. Finding indirect call relationships. Debugging call stack issues. Understanding coupling between distant symbols. Verifying expected call paths exist. "
        "WHEN NOT TO USE: Finding all usages (use scip_references). Impact analysis (use scip_impact). Finding dependencies (use scip_dependencies). Finding dependents (use scip_dependents). Getting curated file list (use scip_context). Finding definitions (use scip_definition). "
        "REQUIRES: SCIP indexes must be generated via 'cidx scip generate' before querying. Check .code-indexer/scip/ directory for .scip files. "
        "RELATED TOOLS: scip_impact (full dependency tree), scip_dependencies (what symbol depends on), scip_dependents (what depends on symbol), scip_context (get curated file list). "
        "EXAMPLE: {\"from_symbol\": \"handle_request\", \"to_symbol\": \"DatabaseManager\", \"max_depth\": 10} returns {\"from_symbol\": \"handle_request\", \"to_symbol\": \"DatabaseManager\", \"total_chains_found\": 2, \"chains\": [{\"length\": 3, \"path\": [{\"symbol\": \"handle_request\", \"file_path\": \"src/api/handler.py\", \"line\": 10, \"column\": 0, \"call_type\": \"call\"}, {\"symbol\": \"UserService.authenticate\", \"file_path\": \"src/services/user.py\", \"line\": 25, \"column\": 4, \"call_type\": \"call\"}, {\"symbol\": \"DatabaseManager.query\", \"file_path\": \"src/database/manager.py\", \"line\": 50, \"column\": 8, \"call_type\": \"call\"}]}]}"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "from_symbol": {
                "type": "string",
                "description": "Starting symbol (e.g., 'handle_request', 'Controller.process')",
            },
            "to_symbol": {
                "type": "string",
                "description": "Target symbol to reach (e.g., 'DatabaseManager', 'authenticate')",
            },
            "max_depth": {
                "type": "integer",
                "default": 10,
                "description": "Maximum chain length to search. Default 10. Max 20. Higher values find longer chains but slower query.",
            },
            "project": {
                "type": ["string", "null"],
                "default": None,
                "description": "Optional project filter to limit search to specific project",
            },
        },
        "required": ["from_symbol", "to_symbol"],
    },
    "required_permission": "query_repos",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Whether the operation succeeded"},
            "from_symbol": {"type": "string", "description": "Starting symbol searched"},
            "to_symbol": {"type": "string", "description": "Target symbol searched"},
            "total_chains_found": {"type": "integer", "description": "Total number of call chains found"},
            "truncated": {"type": "boolean", "description": "Whether results were truncated due to size limits"},
            "max_depth_reached": {"type": "boolean", "description": "Whether search hit max_depth limit"},
            "chains": {
                "type": "array",
                "description": "List of call chains from source to target",
                "items": {
                    "type": "object",
                    "properties": {
                        "length": {"type": "integer", "description": "Number of steps in chain"},
                        "path": {
                            "type": "array",
                            "description": "Sequence of call steps from source to target",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "symbol": {"type": "string", "description": "Symbol at this step"},
                                    "file_path": {"type": "string", "description": "File path relative to project root"},
                                    "line": {"type": "integer", "description": "Line number (1-indexed)"},
                                    "column": {"type": "integer", "description": "Column number (0-indexed)"},
                                    "call_type": {"type": "string", "description": "Type of call (call, import, instantiation, etc.)"},
                                },
                                "required": ["symbol", "file_path", "line", "column", "call_type"],
                            },
                        },
                    },
                    "required": ["length", "path"],
                },
            },
            "error": {"type": "string", "description": "Error message if operation failed"},
        },
        "required": ["success", "chains"],
    },
}

TOOL_REGISTRY["scip_context"] = {
    "name": "scip_context",
    "description": (
        "TL;DR: Get smart, curated file list for understanding a symbol. Returns prioritized files with relevance scoring - files containing definition, direct dependencies/dependents, and related symbols. Perfect for 'what files should I read to understand X?' Use this before reading code. "
        "SYMBOL FORMAT: Pass simple names like 'UserService', 'authenticate', 'DatabaseManager'. SCIP will match fuzzy by default. Full SCIP format like 'scip-python python code-indexer abc123 `module`/ClassName#method().' is handled internally - you only provide the readable part. "
        "WHEN TO USE: Getting curated list of files to read for understanding a symbol. Prioritized file list before code review. Understanding symbol context without reading entire codebase. Building mental model of symbol's ecosystem. Finding related code for refactoring. Efficient context gathering for code analysis. "
        "WHEN NOT TO USE: Finding all usages (use scip_references). Impact analysis (use scip_impact). Finding dependencies (use scip_dependencies). Finding dependents (use scip_dependents). Tracing call paths (use scip_callchain). Finding definitions (use scip_definition). "
        "REQUIRES: SCIP indexes must be generated via 'cidx scip generate' before querying. Check .code-indexer/scip/ directory for .scip files. "
        "RELATED TOOLS: scip_definition (find definition first), scip_impact (full dependency tree), scip_dependencies (what symbol depends on), scip_dependents (what depends on symbol). "
        "EXAMPLE: {\"symbol\": \"DatabaseManager\", \"limit\": 20, \"min_score\": 0.0} returns {\"target_symbol\": \"com.example.DatabaseManager\", \"summary\": \"Read these 3 file(s) - 1 HIGH priority, 2 MEDIUM priority\", \"total_files\": 3, \"total_symbols\": 8, \"avg_relevance\": 0.75, \"files\": [{\"path\": \"src/code_indexer/scip/database/schema.py\", \"project\": \"code-indexer\", \"relevance_score\": 1.0, \"read_priority\": 1, \"symbols\": [{\"name\": \"DatabaseManager\", \"kind\": \"class\", \"relationship\": \"definition\", \"line\": 13, \"column\": 0, \"relevance\": 1.0}]}]}"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Symbol name to get context for (e.g., 'UserService', 'authenticate', 'DatabaseManager')",
            },
            "limit": {
                "type": "integer",
                "default": 20,
                "description": "Maximum number of files to return. Default 20. Max 100.",
            },
            "min_score": {
                "type": "number",
                "default": 0.0,
                "description": "Minimum relevance score threshold (0.0-1.0). Default 0.0 for all relevant files.",
            },
            "project": {
                "type": ["string", "null"],
                "default": None,
                "description": "Optional project filter to limit search to specific project",
            },
        },
        "required": ["symbol"],
    },
    "required_permission": "query_repos",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Whether the operation succeeded"},
            "target_symbol": {"type": "string", "description": "Full SCIP symbol identifier analyzed"},
            "summary": {"type": "string", "description": "Human-readable summary of results"},
            "total_files": {"type": "integer", "description": "Total number of files returned"},
            "total_symbols": {"type": "integer", "description": "Total number of symbols across all files"},
            "avg_relevance": {"type": "number", "description": "Average relevance score across all files"},
            "files": {
                "type": "array",
                "description": "Prioritized list of files to read, sorted by relevance",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to project root"},
                        "project": {"type": "string", "description": "Project path"},
                        "relevance_score": {
                            "type": "number",
                            "description": "Relevance score (0.0-1.0) - higher is more relevant",
                        },
                        "read_priority": {
                            "type": "integer",
                            "description": "Read priority (1=HIGH, 2=MEDIUM, 3=LOW) - lower number means read first",
                        },
                        "symbols": {
                            "type": "array",
                            "description": "Symbols in file related to target symbol",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string", "description": "Symbol name"},
                                    "kind": {"type": "string", "description": "Symbol kind (class, function, method, etc.)"},
                                    "relationship": {
                                        "type": "string",
                                        "description": "Relationship to target (definition, dependency, dependent, reference)",
                                    },
                                    "line": {"type": "integer", "description": "Line number (1-indexed)"},
                                    "column": {"type": "integer", "description": "Column number (0-indexed)"},
                                    "relevance": {"type": "number", "description": "Symbol relevance score (0.0-1.0)"},
                                },
                                "required": ["name", "kind", "relationship", "line", "column", "relevance"],
                            },
                        },
                    },
                    "required": ["path", "project", "relevance_score", "read_priority", "symbols"],
                },
            },
            "error": {"type": "string", "description": "Error message if operation failed"},
        },
        "required": ["success", "files"],
    },
}

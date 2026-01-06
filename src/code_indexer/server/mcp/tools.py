"""MCP Tool Registry - Defines tools with JSON schemas and role requirements."""

from typing import List, Dict, Any
from code_indexer.server.auth.user_manager import User

# =============================================================================
# REPOSITORY DISCOVERY WORKFLOW (HIGH PRIORITY)
# =============================================================================
"""
CRITICAL: Unless the user explicitly specifies which repository to search,
FIRST search cidx-meta-global to discover which repositories are relevant.

MANDATORY WORKFLOW:
1. search_code('topic', repository_alias='cidx-meta-global')
   → Returns .md files describing each repository's contents

2. Then search the specific repositories identified
   → search_code('detailed query', repository_alias='identified-repo-global')

EXCEPTION: Skip cidx-meta discovery ONLY if user explicitly names a repository.

EXAMPLES:
✓ User: "Find authentication code"
  → search_code('authentication', repository_alias='cidx-meta-global') first
  → Then search specific repos that handle auth

✗ User: "Find authentication in backend-global"
  → Skip cidx-meta, search backend-global directly (user specified repo)

✓ User: "How does error handling work?"
  → search_code('error handling', repository_alias='cidx-meta-global') first
  → Then search identified repos

WHY THIS MATTERS:
- Prevents wasted searches in irrelevant repositories
- Discovers which repos contain relevant code
- Provides context about each repository's purpose
- More efficient than guessing or listing all repos
"""

# =============================================================================
# REPOSITORY ALIAS RULES AND PERMISSION SYSTEM
# =============================================================================
"""
REPOSITORY ALIAS NAMING CONVENTIONS:

The CIDX MCP server uses two types of repository identifiers with distinct purposes:

1. GLOBAL REPOSITORIES (read-only, shared across all users):
   Format: '{repo-name}-global'
   Examples: 'backend-global', 'frontend-global', 'cidx-meta-global'

   Purpose: Pre-indexed shared repositories available to all users for search/browse

   Used by:
   - search_code (required for semantic/FTS search)
   - regex_search (searches without index)
   - browse_directory (file listing)
   - directory_tree (visual hierarchy)
   - get_file_content (read files)
   - All git exploration tools (git_log, git_blame, git_file_history, etc.)

   How to discover: Use list_global_repos() to see all available global repositories

   Key characteristics:
   - Immutable (read-only for all users)
   - Shared indexes (semantic + FTS + temporal + SCIP)
   - No write operations allowed
   - Automatically maintained by administrators

2. ACTIVATED REPOSITORIES (user-specific, writable workspaces):
   Format: Your custom alias (NO '-global' suffix required)
   Examples: 'my-backend', 'feature-branch-work', 'personal-fork'

   Purpose: User-specific repository activations for file editing and git operations

   Created by: activate_repository tool (clones or references existing global repos)

   Used by:
   - All file CRUD tools (create_file, edit_file, delete_file)
   - All git write operations (git_stage, git_commit, git_push, etc.)
   - Git read operations (git_status works with activated repos)

   How to discover: Use list_activated_repos() to see your activated repositories

   Key characteristics:
   - User-specific (isolated workspaces)
   - Writable (can edit files, commit, push)
   - Optional composite indexes (multiple repos in one workspace)
   - Can be deactivated when no longer needed

3. TOOLS ACCEPTING BOTH TYPES:
   These tools auto-detect repository type by the '-global' suffix:

   - browse_directory: Works with 'repo-global' OR 'my-repo'
   - directory_tree: Works with 'repo-global' OR 'my-repo'
   - get_file_content: Works with 'repo-global' OR 'my-repo'

   Auto-detection logic: If alias ends with '-global', treated as global repo.
   Otherwise, treated as activated repo.

4. COMMON ERRORS AND HOW TO FIX THEM:

   ERROR: "Repository 'myrepo' not found"
   FIX: Check if you meant 'myrepo-global' (for search) or need to activate first
   DIAGNOSIS: Use list_global_repos() and list_activated_repos() to verify available aliases

   ERROR: "Cannot write to global repository 'backend-global'"
   FIX: Activate the repository first with activate_repository, then use your custom alias
   DIAGNOSIS: Global repos are read-only. File CRUD requires activated workspace.

   ERROR: "Repository 'myrepo-global' not activated"
   FIX: Don't use '-global' suffix for activated repos. Use your custom activation alias.
   DIAGNOSIS: Activated repos use custom names without '-global' suffix.

   ERROR: "Permission denied: requires repository:write"
   FIX: Check your role with whoami(). normal_user role cannot write files.
   DIAGNOSIS: See permission matrix below for role requirements.

5. TYPICAL WORKFLOWS:

   WORKFLOW A - Search existing code (read-only):
   Step 1: list_global_repos() -> See ['backend-global', 'frontend-global']
   Step 2: search_code('authentication', 'backend-global') -> Find relevant code
   Step 3: get_file_content('backend-global', 'src/auth.py') -> Read full file

   WORKFLOW B - Edit and commit changes:
   Step 1: activate_repository('backend-global', 'my-backend-work') -> Create workspace
   Step 2: edit_file('my-backend-work', 'src/auth.py', ...) -> Modify file
   Step 3: git_stage('my-backend-work', ['src/auth.py']) -> Stage changes
   Step 4: git_commit('my-backend-work', 'Fix auth bug') -> Commit
   Step 5: git_push('my-backend-work') -> Push to remote
   Step 6: deactivate_repository('my-backend-work') -> Clean up when done

   WORKFLOW C - Explore unfamiliar codebase:
   Step 1: list_global_repos() -> See available repositories
   Step 2: get_file_content('cidx-meta-global', 'backend-global.md') -> Read repo description
   Step 3: directory_tree('backend-global') -> See file structure
   Step 4: search_code('main entry point', 'backend-global') -> Find starting point

PERMISSION SYSTEM:

The CIDX MCP server uses role-based access control with granular permissions.

Permission              | Roles                              | Grants Access To
------------------------|------------------------------------|-----------------------------------------
query_repos             | normal_user, power_user, admin    | search_code, regex_search, browse_directory,
                        |                                    | directory_tree, get_file_content, all git
                        |                                    | exploration tools (git_log, git_blame, etc.)
------------------------|------------------------------------|-----------------------------------------
activate_repos          | power_user, admin                  | activate_repository, deactivate_repository,
                        |                                    | list_activated_repos
------------------------|------------------------------------|-----------------------------------------
repository:read         | normal_user, power_user, admin    | git_status (on activated repos),
                        |                                    | read operations on user workspaces
------------------------|------------------------------------|-----------------------------------------
repository:write        | power_user, admin                  | create_file, edit_file, delete_file,
                        |                                    | git_stage, git_unstage, git_commit,
                        |                                    | git_checkout_file, git_clean, git_reset
------------------------|------------------------------------|-----------------------------------------
repository:admin        | admin                              | add_golden_repo, remove_golden_repo,
                        |                                    | force operations, user management
------------------------|------------------------------------|-----------------------------------------
manage_golden_repos     | admin                              | Repository administration (add/remove/reindex
                        |                                    | global repositories)
------------------------|------------------------------------|-----------------------------------------
manage_users            | admin                              | User and role management, permission grants

ROLE CAPABILITIES SUMMARY:

normal_user:
- Search and browse all global repositories (read-only)
- Use git exploration tools (log, blame, diff) on global repos
- Read file contents from global repos
- CANNOT activate repositories or edit files
- CANNOT perform git write operations

power_user (extends normal_user):
- Everything normal_user can do
- Activate/deactivate repositories (create workspaces)
- Full file CRUD (create, edit, delete files)
- Git write operations (stage, commit, push, branch management)
- Manage own composite repositories
- CANNOT add/remove global repositories
- CANNOT manage other users

admin (extends power_user):
- Everything power_user can do
- Add/remove global repositories (manage_golden_repos)
- Reindex repositories
- User and role management
- Force operations (bypass safety checks)
- System-wide repository administration

HOW TO CHECK YOUR PERMISSIONS:

Use the whoami() tool to see:
- Your username
- Your assigned role
- Your effective permissions
- Repositories you have activated

Example whoami() response:
{
  "success": true,
  "username": "alice",
  "role": "power_user",
  "permissions": ["query_repos", "activate_repos", "repository:read", "repository:write"],
  "activated_repositories": ["my-backend-work", "feature-123"]
}

PERMISSION DENIED TROUBLESHOOTING:

If you receive "Permission denied: requires {permission_name}", this means:
1. Your role does not grant the required permission
2. Check the permission matrix above to see which roles have this permission
3. Contact administrator if you need elevated privileges
4. Some operations (like file CRUD) also require repository activation

Common scenarios:
- "requires repository:write" -> You need power_user or admin role
- "requires activate_repos" -> You need power_user or admin role
- "requires manage_golden_repos" -> You need admin role
- "Repository not activated" -> Use activate_repository first (requires activate_repos permission)
"""

# MCP Tool Registry - All tools with complete JSON schemas
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Tools 1-2: Search
    "search_code": {
        "name": "search_code",
        "description": "REPOSITORY SELECTION: If repository is not specified by user, search cidx-meta-global first to discover relevant repositories (search_code('topic', repository_alias='cidx-meta-global')), then search the specific repositories identified. Skip cidx-meta only if user explicitly names a repository. TL;DR: Search code using pre-built indexes. Use semantic mode for conceptual queries, FTS for exact text. SEARCH MODE DECISION: 'authentication logic' (concept) -> semantic | 'def authenticate_user' (exact text) -> fts | unsure -> hybrid. CRITICAL - SEMANTIC SEARCH IS NOT TEXT SEARCH: Semantic mode finds code by MEANING, not exact text. Results are APPROXIMATE and help identify areas of concern for a topic. For exhaustive exact-text results, use FTS mode or regex_search tool. QUICK START: search_code('user authentication', repository_alias='myrepo-global', search_mode='semantic', limit=5). DISCOVERY: Run list_global_repos first to see available repositories. ALIAS FORMAT: Global repos end in '-global' (e.g., 'backend-global'). CIDX-META: For exploring unfamiliar codebases, cidx-meta-global contains .md descriptions of all repos - use browse_directory + get_file_content (NOT search_code) since it's a small catalog. TROUBLESHOOTING: (1) 0 results? Verify alias with list_global_repos, try broader terms, check filters. (2) Temporal queries empty? Check enable_temporal via global_repo_status. (3) Slow? Start with limit=5, use path_filter. WHEN NOT TO USE: (1) Need comprehensive pattern search with ALL matches -> use regex_search instead (not approximate), (2) Know exact text but want direct file search -> use regex_search (no index required), (3) Exploring directory structure -> use browse_directory or directory_tree first. RELATED TOOLS: regex_search (comprehensive pattern matching without index), git_search_diffs (find when code was added/removed).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query_text": {
                    "type": "string",
                    "description": "Search query text. MULTI-TERM FTS QUERIES: When using search_mode='fts' with multiple terms (e.g., 'authenticate user'), ALL terms must match (AND semantics). Single-term queries match normally. For OR semantics, use separate queries or regex mode with '|' operator (e.g., 'term1|term2').",
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
                    "description": "Search mode: 'semantic' for natural language/conceptual queries ('how authentication works'), 'fts' for exact text/identifiers ('def authenticate_user'), 'hybrid' for both. Default: semantic. NOTE: FTS multi-term queries use AND semantics - all terms must match. Example: 'password reset' requires both words. For OR behavior, use regex mode.",
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
    "discover_repositories": {
        "name": "discover_repositories",
        "description": """TL;DR: List repositories available from external source configurations like GitHub organizations or local paths that are NOT yet indexed.

USE CASES:
(1) Explore what repositories are available in your GitHub organization before indexing them
(2) Find repositories from configured sources to decide which ones to add as queryable golden repos
(3) Audit external repository sources to see what's accessible

REQUIREMENTS:
- Permission: 'query_repos' (all roles)
- External sources must be configured in CIDX server config
- Network access for remote sources (GitHub/GitLab APIs)

DIFFERENCE FROM list_global_repos:
- discover_repositories: Shows POTENTIAL repos from external sources (not yet indexed)
- list_global_repos: Shows already-indexed repos ready to query

RETURNS:
{
  "success": true,
  "repositories": [
    {
      "alias": "my-backend",
      "repo_url": "https://github.com/org/backend.git",
      "default_branch": "main",
      "source_type": "github_org"
    }
  ]
}

EXAMPLE:
discover_repositories(source_type='github_org')
-> Returns all repos from configured GitHub organization

COMMON ERRORS:
- "No external sources configured" -> Admin must configure repository sources in server config
- "API rate limit exceeded" -> GitHub/GitLab API throttling, wait or use authentication
- "Source not accessible" -> Network issues or invalid credentials

RELATED TOOLS:
- list_global_repos: See already-indexed queryable repositories
- add_golden_repo: Index a discovered repository to make it queryable
- get_job_statistics: Monitor indexing progress after adding repos
""",
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
        "description": """TL;DR: List repositories YOU have activated (user-specific workspaces), distinct from global shared repositories.

USE CASES:
(1) See which repositories you've activated for editing or branch-specific work
(2) Find your custom repository aliases to use in file CRUD or git operations
(3) Check if you have an activation before trying to edit files

WHAT IT DOES:
- Lists YOUR activated repositories (user-specific workspaces)
- Shows both single-repo activations and composite repositories you've created
- Returns user_alias, branch, and activation status for each
- Does NOT show global repositories (use list_global_repos for that)

REQUIREMENTS:
- Permission: 'query_repos' (all roles)
- No parameters needed - returns only your activations

DIFFERENCE FROM list_global_repos:
- list_repositories: YOUR activated repos (editable, user-specific, custom branches)
- list_global_repos: Shared repos (read-only, available to all users, default branches)

RETURNS:
{
  "success": true,
  "repositories": [
    {
      "user_alias": "my-backend",
      "golden_repo_alias": "backend",
      "current_branch": "feature-123",
      "is_global": false
    }
  ]
}

EXAMPLE:
list_repositories()
-> Returns [{"user_alias": "my-backend", "current_branch": "feature-123"}]

COMMON ERRORS:
- Empty list -> You haven't activated any repositories yet, use activate_repository first
- "Permission denied" -> All roles can use this tool

TYPICAL WORKFLOW:
1. List your activations: list_repositories()
2. Edit files: edit_file(repository_alias='my-backend', ...)
3. Commit changes: git_commit('my-backend', 'Fix bug')
4. Clean up: deactivate_repository('my-backend')

RELATED TOOLS:
- list_global_repos: See shared global repositories
- activate_repository: Create a new activation
- deactivate_repository: Remove an activation
- get_repository_status: Get detailed status of an activation
""",
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
        "description": """TL;DR: Create a user-specific repository workspace for editing files, working on non-default branches, or combining multiple repos into a composite.

USE CASES:
(1) Work on a non-default branch (e.g., feature branch or release branch)
(2) Create a composite repository searching across multiple repos (frontend + backend + shared)
(3) Set up an editable workspace for file CRUD and git write operations

WHEN TO USE vs WHEN NOT TO USE:
- Use activate_repository: Need to edit files, commit changes, or work on non-default branch
- Skip activation: Just searching/reading code on default branch (use 'repo-global' directly)

WHAT IT DOES:
- Creates a user-specific repository workspace with custom alias
- Clones or references golden repository for your exclusive use
- Enables file CRUD and git write operations on your workspace
- Optionally combines multiple golden repos into single searchable composite

REQUIREMENTS:
- Permission: 'activate_repos' (power_user or admin role)
- Golden repository must exist (use list_global_repos to verify)
- For composites: all component golden repos must exist

PARAMETERS:
- golden_repo_alias: Single repo to activate (mutually exclusive with golden_repo_aliases)
- golden_repo_aliases: Array of repos for composite (mutually exclusive with golden_repo_alias)
- user_alias: Your custom name for this activation (optional, auto-generated if omitted)
- branch_name: Specific branch to check out (optional, uses default branch if omitted)

RETURNS:
{
  "success": true,
  "job_id": "abc-123",
  "message": "Activation started, use get_job_statistics to monitor progress"
}

EXAMPLE - Single repo:
activate_repository(golden_repo_alias='backend', user_alias='my-backend', branch_name='feature-auth')
-> Creates 'my-backend' workspace on feature-auth branch

EXAMPLE - Composite:
activate_repository(golden_repo_aliases=['frontend', 'backend', 'shared'], user_alias='fullstack')
-> Creates 'fullstack' composite searching across all 3 repos

COMMON ERRORS:
- "Permission denied" -> You need power_user or admin role
- "Golden repository not found" -> Use list_global_repos to verify alias
- "Branch does not exist" -> Check available branches with get_branches
- "Activation already exists" -> Use different user_alias or deactivate existing one first

TYPICAL WORKFLOW:
1. Find repo: list_global_repos()
2. Activate: activate_repository(golden_repo_alias='backend', user_alias='my-work')
3. Monitor: get_job_statistics() until active=0
4. Use: edit_file(repository_alias='my-work', ...)
5. Cleanup: deactivate_repository('my-work')

RELATED TOOLS:
- list_global_repos: See available golden repositories
- deactivate_repository: Remove activation when done
- manage_composite_repository: Modify composite after creation
- get_job_statistics: Monitor activation progress
""",
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
        "description": """TL;DR: Remove a user-specific repository activation and delete associated user indexes. Does NOT affect the underlying golden repository or global indexes shared by other users.

USE CASES:
(1) Clean up repository activations you no longer need to free storage
(2) Remove old branch-specific activations when done with feature work
(3) Delete composite repository configurations that are no longer relevant

WHAT IT DOES:
- Removes repository from your personal activated repositories list
- Deletes all user-specific indexes (composite indexes, branch-specific indexes)
- Frees disk space (typically 100MB-2GB per activation depending on repo size)
- Does NOT affect the golden repository or global indexes used by other users
- Does NOT delete the golden repository itself (use remove_golden_repo for that - requires admin)

REQUIREMENTS:
- Permission: 'activate_repos' (power_user or admin role)
- Must provide exact user_alias you used when activating
- Cannot deactivate global repositories (those ending in '-global')

PARAMETERS:
- user_alias: YOUR alias for the activated repo (not the golden repo alias)
  Example: If you activated 'backend-golden' as 'my-backend', use 'my-backend'

RETURNS:
{
  "success": true,
  "deactivated_alias": "my-backend",
  "indexes_deleted": ["composite", "branch-specific"],
  "space_freed_mb": 1234
}

EXAMPLE:
deactivate_repository(user_alias='my-old-project')
-> Removes 'my-old-project' activation, deletes ~500MB of indexes

COMMON ERRORS:
- "Repository not activated" -> Check alias with list_activated_repos()
- "Permission denied" -> You need 'activate_repos' permission (power_user or admin role)
- "Cannot deactivate global repository" -> Global repos can't be deactivated, only removed (admin only)

RELATED TOOLS:
- activate_repository: Create a new activation
- list_activated_repos: See all your current activations
- remove_golden_repo: Admin tool to delete golden repositories (different from deactivation)
- get_repository_status: Check status before deactivating
""",
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
        "description": "TL;DR: Get comprehensive status of YOUR activated repository including indexing state, file counts, git branch info, and temporal capabilities. REQUIRES: User-specific repository activation (use your custom alias, NOT '-global' suffix). QUICK START: get_repository_status('my-backend') returns full status of your activated repo. KEY STATUS FIELDS: activation_status (activated/available), file_count, index_size, branches_list, enable_temporal, last_updated. USE CASES: (1) Verify repository activation before file operations, (2) Check indexing progress, (3) Confirm temporal search availability, (4) List available branches for switch_branch operation. TEMPORAL STATUS: Check enable_temporal field to confirm if time_range queries are supported in search_code. If false, temporal queries will return empty results. ALIAS REQUIREMENT: This tool works with YOUR activated repositories (user-specific aliases). For global read-only repositories, use global_repo_status instead. TROUBLESHOOTING: Repository not found? Use list_repositories to see your activated repos, or activate_repository to create activation. COMPARISON: get_repository_status (YOUR activated repos) vs global_repo_status (shared read-only repos). RELATED TOOLS: global_repo_status (check global repos), list_repositories (list your repos), activate_repository (create activation), get_all_repositories_status (summary of all).",
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
        "description": """TL;DR: Synchronize an activated repository with its golden repository source. Pulls latest changes from the golden repo and optionally re-indexes to reflect updates.

USE CASES:
(1) Update your activated repository when the golden repo has new commits
(2) Ensure your local activation matches the latest golden repo state
(3) Refresh indexes after upstream changes

WHAT IT DOES:
- Performs git pull from golden repository to your activated repo
- Optionally triggers re-indexing to update search indexes with new code
- Preserves your local branch state (won't switch branches)
- Does NOT affect golden repository itself (read-only operation on golden)

REQUIREMENTS:
- Permission: 'activate_repos' (power_user or admin role)
- Repository must be activated (not a global repo)
- Golden repository must exist and be accessible

PARAMETERS:
- user_alias: Your user alias for the activated repository
- reindex: Boolean, default true - Whether to re-index after sync
  Set to false if you just want git pull without waiting for indexing

RETURNS:
{
  "success": true,
  "repository_alias": "my-backend",
  "commits_pulled": 5,
  "files_changed": 23,
  "reindex_triggered": true,
  "reindex_job_id": "abc123"  // if reindex=true
}

EXAMPLE:
sync_repository(user_alias='my-backend', reindex=true)
-> Pulls 5 new commits, updates 23 files, starts re-indexing

COMMON ERRORS:
- "Repository not activated" -> Use list_activated_repos() to check
- "Golden repository not found" -> Golden repo may have been removed
- "Merge conflict" -> You have local changes conflicting with upstream

TYPICAL WORKFLOW:
1. Check status: get_repository_status('my-backend')
2. Sync: sync_repository('my-backend', reindex=true)
3. Wait for reindex: monitor job with background job tools
4. Resume work with updated code

RELATED TOOLS:
- activate_repository: Create activation
- get_repository_status: Check sync status before syncing
- refresh_golden_repo: Update the golden repository itself (admin only)
""",
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
        "description": "TL;DR: Switch YOUR activated repository to different branch and re-index automatically. Changes the active branch for your user-specific repository copy. REQUIRES: Repository must be activated (use activate_repository first). QUICK START: switch_branch('my-backend', 'develop') switches to develop branch. USE CASES: (1) Work on different feature branches, (2) Compare code across branches (switch + search), (3) Test different versions. AUTOMATIC RE-INDEX: After branch switch, repository is automatically re-indexed to reflect new branch state. This ensures search results match current branch content. BRANCH DISCOVERY: Use get_branches or get_repository_status to list available branches before switching. WARNING: Uncommitted changes may be lost. Commit or stash changes before switching. ALIAS REQUIREMENT: Works only with YOUR activated repositories (user-specific aliases). Cannot switch branches on global read-only repositories. TROUBLESHOOTING: Branch not found? Use get_branches to verify branch exists. Repository not activated? Use activate_repository first. RELATED TOOLS: get_branches (list available branches), activate_repository (activate repo with specific branch), get_repository_status (check current branch), git_branch_create (create new branch), git_branch_switch (git operation alternative).",
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
        "description": "TL;DR: List all files in repository with metadata (size, modified_at, language, is_indexed). Returns flat list of files with filtering options. QUICK START: list_files('backend-global') returns all files. USE CASES: (1) Inventory repository contents, (2) Check indexing status across files, (3) Find files by path pattern. FILTERING: Use path parameter to scope to directory (path='src/auth'). OMNI-SEARCH: Pass array of aliases (['backend-global', 'frontend-global']) to list files across multiple repos. AGGREGATION: Use aggregation_mode='per_repo' for balanced representation, 'global' for sorted results. RESPONSE FORMATS: 'flat' (default) returns single array with source_repo field, 'grouped' organizes by repository. WHEN NOT TO USE: (1) Need file content -> use get_file_content, (2) Need directory tree view -> use browse_directory or directory_tree, (3) Need to search file content -> use search_code or regex_search. OUTPUT: Returns array of file objects with path, size_bytes, modified_at, language, is_indexed fields. TROUBLESHOOTING: Empty results? Check repository_alias with list_global_repos. RELATED TOOLS: browse_directory (tree view with directories), get_file_content (read file), directory_tree (recursive directory structure).",
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
                    "description": "Directory path to list files from (optional). Lists all files IN the specified directory. Example: path='src/auth' lists files matching 'src/auth/**/*' pattern.",
                },
                "recursive": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to recursively list files in subdirectories (default: true). When true, uses '**/*' pattern. When false, uses '*' pattern (only direct children).",
                },
                "path_pattern": {
                    "type": "string",
                    "description": "Optional glob pattern to filter files within the directory specified by 'path'. Example: path='src', path_pattern='*.py' lists files matching 'src/**/*.py'. If 'path' is not specified, applies pattern to entire repository.",
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
        "description": "TL;DR: Read file content from repository with metadata and token-based pagination to prevent LLM context exhaustion. CRITICAL BEHAVIOR CHANGE: Default behavior (no offset/limit params) now returns FIRST CHUNK ONLY (up to 5000 tokens, ~200-250 lines), NOT entire file. Token limits enforced on ALL requests. QUICK START: get_file_content('backend-global', 'src/auth.py') returns first ~200-250 lines if file is large. Check metadata.requires_pagination to see if more content exists. USE PAGINATION: get_file_content('backend-global', 'large_file.py', offset=251, limit=250) reads next chunk. AUTOMATIC TRUNCATION: Content exceeding token budget is truncated. Check metadata.truncated and metadata.truncated_at_line. Use metadata.pagination_hint for navigation instructions. USE CASES: (1) Read source code after search_code identifies relevant files, (2) Inspect configuration files, (3) Review file content before editing, (4) Navigate large files efficiently with token budgets. TOKEN ENFORCEMENT: Default config: 5000 tokens max per request (~20000 chars at 4 chars/token). Small files returned completely. Large files returned in chunks. metadata.estimated_tokens shows actual token count of returned content. PAGINATION WORKFLOW: (1) Call without params to get first chunk, (2) Check metadata.requires_pagination, (3) If true, use metadata.pagination_hint offset value to continue, (4) Repeat until metadata.requires_pagination=false. OUTPUT FORMAT: Returns array of content blocks following MCP specification - each block has type='text' and text=file_content. Metadata includes file size, detected language, modification timestamp, pagination info, and token enforcement info (estimated_tokens, max_tokens_per_request, truncated, requires_pagination, pagination_hint). WHEN TO USE: After identifying target file via search_code, browse_directory, or list_files. WHEN NOT TO USE: (1) Need file listing -> use list_files or browse_directory, (2) Need to search content -> use search_code or regex_search first, (3) Need directory structure -> use directory_tree. TROUBLESHOOTING: File not found? Verify file_path with list_files or browse_directory. Permission denied? Check repository is activated and accessible. Content truncated unexpectedly? Check metadata.truncated and metadata.estimated_tokens - use offset/limit params to navigate. RELATED TOOLS: list_files (find files), search_code (search content), edit_file (modify content), browse_directory (list with metadata).",
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
                "offset": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Line number to start reading from (1-indexed). Optional. Default: read from beginning. Example: offset=100 starts at line 100.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Maximum number of lines to return. Optional. Default: token-limited chunk (up to 5000 tokens). Recommended: 200-250 lines per request to stay within 5000 token budget. Token limits enforced even if you specify larger limit. Use metadata.requires_pagination to detect if more content exists.",
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
                    "description": "File metadata including pagination info",
                    "properties": {
                        "size": {
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
                        "path": {
                            "type": "string",
                            "description": "Relative file path",
                        },
                        "total_lines": {
                            "type": "integer",
                            "description": "Total lines in file",
                        },
                        "returned_lines": {
                            "type": "integer",
                            "description": "Number of lines returned in this response",
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Starting line number (1-indexed) for returned content",
                        },
                        "limit": {
                            "type": ["integer", "null"],
                            "description": "Limit used (null if unlimited)",
                        },
                        "has_more": {
                            "type": "boolean",
                            "description": "True if more lines exist beyond returned range. Use this to detect when pagination is needed.",
                        },
                        "estimated_tokens": {
                            "type": "integer",
                            "description": "Estimated token count of returned content based on character length and chars_per_token ratio.",
                        },
                        "max_tokens_per_request": {
                            "type": "integer",
                            "description": "Current token limit from server configuration (default: 5000).",
                        },
                        "truncated": {
                            "type": "boolean",
                            "description": "True if content was truncated due to token limit enforcement.",
                        },
                        "truncated_at_line": {
                            "type": ["integer", "null"],
                            "description": "Line number where truncation occurred (null if not truncated).",
                        },
                        "requires_pagination": {
                            "type": "boolean",
                            "description": "True if file has more content to read (either due to truncation or more lines beyond current range).",
                        },
                        "pagination_hint": {
                            "type": ["string", "null"],
                            "description": "Helpful message with suggested offset value to continue reading (null if no more content).",
                        },
                    },
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
        "description": "TL;DR: List all git branches for repository with detailed metadata (current branch, last commit info, index status, remote tracking). Supports both global and activated repositories. QUICK START: get_branches('backend-global') lists all branches. OUTPUT FIELDS: Each branch includes name, is_current (boolean), last_commit (sha, message, author, date), index_status (indexing state), remote_tracking (upstream branch info). USE CASES: (1) Discover available branches before switch_branch, (2) Check which branch is currently active, (3) See last commit on each branch for comparison, (4) Verify branch exists before operations. CURRENT BRANCH: Look for is_current=true to identify active branch. INDEX STATUS: Shows indexing state per branch (indexed, pending, not_indexed). REMOTE TRACKING: Indicates if branch tracks remote (origin/main, etc.). WORKS WITH: Both global read-only repos ('-global' suffix) and your activated repos (custom aliases). TROUBLESHOOTING: Empty list? Repository might not be initialized or have no branches. RELATED TOOLS: switch_branch (change active branch), git_branch_list (git operation alternative), get_repository_status (includes current branch), git_branch_create (create new branch).",
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
        "description": "TL;DR: Check CIDX server health and availability. Returns system status, uptime, and service availability indicators. QUICK START: check_health() with no parameters returns health status. USE CASES: (1) Verify server is operational before operations, (2) Debug connection issues, (3) Monitor system availability. OUTPUT: Returns success boolean, status (healthy/degraded/down), uptime, and component health checks (database, indexes, embeddings). TROUBLESHOOTING: If success=false or status='down', indicates server issues that may affect operations. Check error field for diagnostic information. WHEN TO USE: Before starting work session to confirm server availability, or when experiencing unexpected errors. NO PARAMETERS REQUIRED: Health check needs no input arguments. RELATED TOOLS: get_repository_status (check specific repo health), get_all_repositories_status (all repos health), get_job_statistics (background job health).",
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
        "description": "TL;DR: Remove global shared repository from CIDX server. Deletes repository from golden repos list, removes indexes, and cleans up storage. ADMIN ONLY (requires manage_golden_repos permission). QUICK START: remove_golden_repo('backend-global') removes the global repository. DESTRUCTIVE OPERATION: This permanently removes the repository and all associated indexes for ALL users. Global repos serve all users, so removal affects everyone. BACKGROUND JOB: Returns job_id for async operation - use get_job_details to monitor progress. USE CASES: (1) Decommission deprecated repositories, (2) Clean up test repositories, (3) Free storage space. VERIFICATION: Use list_global_repos to confirm removal. ALIAS FORMAT: Provide the full alias including '-global' suffix. TROUBLESHOOTING: Permission denied? Requires admin role. Repository not found? Verify alias with list_global_repos. RELATED TOOLS: add_golden_repo (add new global repo), list_global_repos (see all global repos), get_job_details (monitor removal job).",
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
        "description": "TL;DR: Update global repository by pulling latest changes from git remote and re-indexing. Synchronizes global repo with upstream repository. ADMIN ONLY (requires manage_golden_repos permission). QUICK START: refresh_golden_repo('backend-global') pulls latest and re-indexes. WHAT IT DOES: (1) Git pull from remote origin, (2) Re-index all new/changed files, (3) Update search indexes with latest code. BACKGROUND JOB: Returns job_id for async operation - refresh can take minutes for large repos. Use get_job_details to monitor. AUTOMATIC REFRESH: Global repos also have auto-refresh configured via get_global_config/set_global_config (minimum 60s interval). This tool triggers manual on-demand refresh. USE CASES: (1) Get latest code changes immediately without waiting for auto-refresh, (2) Refresh after known upstream changes, (3) Force re-index after issues. VERIFICATION: Check global_repo_status after job completes - last_refreshed timestamp should update. RELATED TOOLS: global_repo_status (check last refresh time), get_job_details (monitor refresh job), set_global_config (configure auto-refresh interval).",
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
        "description": "TL;DR: List all users in CIDX system with roles and creation timestamps. ADMIN ONLY (requires manage_users permission). QUICK START: list_users() with no parameters returns all users. OUTPUT FIELDS: Each user includes username, role (admin/power_user/normal_user), created_at (ISO 8601 timestamp). Total count included. ROLE TYPES: admin (full access), power_user (can activate repos and write files), normal_user (read-only query access). USE CASES: (1) Audit user accounts, (2) Check user roles before granting permissions, (3) Monitor user growth. NO PARAMETERS: Returns all users without filtering. TROUBLESHOOTING: Permission denied? Requires admin role with manage_users permission. RELATED TOOLS: create_user (add new user), authenticate (login).",
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
        "description": "TL;DR: Create new user account with specified username, password, and role. ADMIN ONLY (requires manage_users permission). QUICK START: create_user('alice', 'secure_password', 'power_user') creates power user. REQUIRED FIELDS: username (unique identifier), password (stored securely), role (admin/power_user/normal_user). ROLE SELECTION: Choose based on needed permissions - normal_user (query only), power_user (activate repos + write files + query), admin (full access including user/repo management). SECURITY: Passwords are hashed before storage. Username must be unique. USE CASES: (1) Onboard new team members, (2) Create service accounts for automation, (3) Grant appropriate access levels. VERIFICATION: Use list_users to confirm user creation. User can immediately authenticate with credentials. TROUBLESHOOTING: Username exists? Must be unique across system. Permission denied? Requires admin role. RELATED TOOLS: list_users (verify creation), authenticate (test login).",
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
        "description": "TL;DR: Get comprehensive statistics for repository including file counts, storage usage, language breakdown, indexing progress, and health score. QUICK START: get_repository_statistics('backend-global') returns full stats. OUTPUT CATEGORIES: (1) files - total/indexed counts, breakdown by_language, (2) storage - repository_size_bytes, index_size_bytes, embedding_count, (3) activity - created_at, last_sync_at, last_accessed_at, sync_count, (4) health - score (0.0-1.0), issues array. USE CASES: (1) Monitor indexing progress (indexed vs total files), (2) Track storage usage and growth, (3) Identify language distribution in codebase, (4) Assess repository health. HEALTH SCORE: 1.0 = perfect health, <0.8 may indicate issues (check issues array for details). WORKS WITH: Both global and activated repositories. TROUBLESHOOTING: Low health score? Check issues array for specific problems (missing indexes, sync failures, etc.). RELATED TOOLS: get_all_repositories_status (summary across all repos), get_repository_status (activation status), get_job_statistics (background job health).",
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
        "description": "TL;DR: Get high-level status summary of ALL repositories (both global and user-activated) in one call. Returns array of repository status summaries. QUICK START: get_all_repositories_status() with no parameters returns all repos. USE CASES: (1) Dashboard overview of system health, (2) Monitor indexing progress across all repos, (3) Identify repos needing attention. OUTPUT: Array of status summaries including alias, activation_status, file_count, last_updated, health indicators. Total count included. SCOPE: Includes both global shared repositories (read-only, '-global' suffix) and your activated repositories (writable, user-specific). NO PARAMETERS: Returns comprehensive list without filtering. COMPARISON: This tool provides overview across all repos. For detailed status of specific repo, use get_repository_status or global_repo_status. TROUBLESHOOTING: Large list? Filter results client-side by activation_status or alias pattern. RELATED TOOLS: get_repository_status (detailed user repo status), global_repo_status (detailed global repo status), get_repository_statistics (comprehensive stats for one repo).",
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
    "add_golden_repo_index": {
        "name": "add_golden_repo_index",
        "description": "Add an index type to an existing golden repository. Submits a background job and returns job_id for tracking. INDEX TYPES: 'semantic_fts' (semantic search + full-text search), 'temporal' (git history/time-based search), 'scip' (call graph for code navigation). WORKFLOW: (1) Call add_golden_repo_index with alias and index_type, (2) Returns job_id immediately, (3) Monitor progress via get_job_statistics. REQUIREMENTS: Repository must already exist as golden repo (use add_golden_repo first if needed). ERROR CASES: Returns error if alias not found, invalid index_type, or index already exists (idempotent). PERFORMANCE: Index addition runs in background - semantic_fts takes seconds to minutes, temporal depends on commit history size, scip depends on codebase complexity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "alias": {
                    "type": "string",
                    "description": "Golden repository alias (base name, not '-global' suffix)",
                },
                "index_type": {
                    "type": "string",
                    "enum": ["semantic_fts", "temporal", "scip"],
                    "description": "Index type to add: 'semantic_fts' for semantic+FTS search, 'temporal' for git history search, 'scip' for call graph navigation",
                },
            },
            "required": ["alias", "index_type"],
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
                    "type": "string",
                    "description": "Background job ID for tracking progress",
                },
                "message": {
                    "type": "string",
                    "description": "Status message with guidance on tracking progress",
                },
                "error": {
                    "type": "string",
                    "description": "Error message if operation failed (alias not found, invalid type, or index already exists)",
                },
            },
            "required": ["success"],
        },
    },
    "get_golden_repo_indexes": {
        "name": "get_golden_repo_indexes",
        "description": "Get structured status of all index types for a golden repository. Shows which indexes exist (semantic_fts, temporal, scip) with paths and last updated timestamps. USE CASES: (1) Check if index types are available before querying, (2) Verify index addition completed successfully, (3) Troubleshoot missing search capabilities. RESPONSE: Returns exists flag, filesystem path, and last_updated timestamp for each index type. Empty/null values indicate index does not exist yet.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "alias": {
                    "type": "string",
                    "description": "Golden repository alias (base name, not '-global' suffix)",
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
                "alias": {
                    "type": "string",
                    "description": "Golden repository alias",
                },
                "indexes": {
                    "type": "object",
                    "description": "Status of each index type",
                    "properties": {
                        "semantic_fts": {
                            "type": "object",
                            "properties": {
                                "exists": {"type": "boolean"},
                                "path": {"type": ["string", "null"]},
                                "last_updated": {"type": ["string", "null"]},
                            },
                        },
                        "temporal": {
                            "type": "object",
                            "properties": {
                                "exists": {"type": "boolean"},
                                "path": {"type": ["string", "null"]},
                                "last_updated": {"type": ["string", "null"]},
                            },
                        },
                        "scip": {
                            "type": "object",
                            "properties": {
                                "exists": {"type": "boolean"},
                                "path": {"type": ["string", "null"]},
                                "last_updated": {"type": ["string", "null"]},
                            },
                        },
                    },
                },
                "error": {
                    "type": "string",
                    "description": "Error message if operation failed (alias not found)",
                },
            },
            "required": ["success"],
        },
    },
    "manage_composite_repository": {
        "name": "manage_composite_repository",
        "description": """TL;DR: Perform operations on composite repositories (multi-repo activations). Manage repositories created from multiple golden repos as a single searchable unit.

USE CASES:
(1) Update component repositories in a composite (add/remove repos from the composite)
(2) Re-sync all component repos in a composite activation
(3) Rebuild composite indexes after component changes

WHAT IS A COMPOSITE REPOSITORY:
A composite repository is an activation that combines multiple golden repositories into a single searchable unit.
Example: Combine 'backend-golden', 'frontend-golden', 'shared-golden' into one composite 'fullstack' activation.
Queries against the composite search across all component repositories.

WHAT IT DOES:
- Add or remove component repositories from existing composite
- Re-sync all components with their golden sources
- Rebuild composite indexes (necessary after component changes)
- View component repository status within composite

REQUIREMENTS:
- Permission: 'activate_repos' (power_user or admin role)
- Composite repository must already exist (created via activate_repository with golden_repo_aliases array)
- Component golden repositories must exist

PARAMETERS:
- user_alias: Your alias for the composite repository
- operation: String, one of:
  - 'create': Create new composite repository
  - 'update': Modify composite components
  - 'delete': Remove composite repository
- golden_repo_aliases: Array of golden repo aliases (required for create/update operations)

RETURNS:
{
  "success": true,
  "composite_alias": "fullstack",
  "operation": "update",
  "components": ["backend-golden", "frontend-golden", "shared-golden"],
  "reindex_job_id": "xyz789"  // if reindex triggered
}

EXAMPLE:
manage_composite_repository(
  user_alias='fullstack',
  operation='update',
  golden_repo_aliases=['backend-golden', 'frontend-golden', 'api-golden']
)
-> Updates 'fullstack' composite to include 'api-golden', triggers re-indexing

COMMON ERRORS:
- "Composite not found" -> Check alias with list_activated_repos()
- "Not a composite repository" -> Alias points to single-repo activation
- "Component already exists" -> Golden repo already in composite
- "Cannot remove last component" -> Composites need at least 2 components

TYPICAL WORKFLOW:
1. Create composite: manage_composite_repository(user_alias='fullstack', operation='create', golden_repo_aliases=['backend-golden', 'frontend-golden'])
2. Later add component: manage_composite_repository(user_alias='fullstack', operation='update', golden_repo_aliases=['backend-golden', 'frontend-golden', 'shared-golden'])
3. Delete composite: manage_composite_repository(user_alias='fullstack', operation='delete')

RELATED TOOLS:
- activate_repository: Create composite (pass array to golden_repo_aliases)
- list_activated_repos: See all your composites
- deactivate_repository: Remove entire composite
""",
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
        "description": "List all globally accessible repositories. REPOSITORY STATES: Discovered (from discover_repositories, not yet indexed) -> Golden/Global (after add_golden_repo, immediately queryable as '{name}-global') -> Activated (optional, via activate_repository for branch selection or composites). TERMINOLOGY: Golden repositories are admin-registered source repos. Global repositories are the publicly queryable versions accessible via '{name}-global' alias. SPECIAL: 'cidx-meta-global' is the meta-directory catalog containing descriptions of ALL repositories. DISCOVERY: Before calling this tool, search cidx-meta-global to discover which repositories are relevant (search_code('topic', repository_alias='cidx-meta-global')). Use list_global_repos() only when explicitly asked for the repo list or to verify a repo exists. DISCOVERY WORKFLOW: (1) Query cidx-meta-global to discover which repositories contain content on your topic, (2) then query those specific repositories for detailed code. Example: search_code('authentication', repository_alias='cidx-meta-global') returns repositories that handle authentication, then search_code('OAuth implementation', repository_alias='backend-api-global') for actual code. STATUS: All listed global repos are ready for querying immediately; use global_repo_status for detailed info. TYPICAL WORKFLOW: (1) search cidx-meta-global to discover relevant repos, (2) search specific repositories identified, (3) use list_global_repos only if needed to verify repo exists. WHEN NOT TO USE: (1) Need detailed status of ONE repo (temporal support, refresh times) -> use global_repo_status instead, (2) Want to search code -> use search_code with repository_alias, (3) Looking for repo descriptions -> search cidx-meta-global first.",
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
        "description": "TL;DR: Get detailed status of specific GLOBAL repository (shared, read-only) including refresh timestamps and temporal indexing capabilities. ALIAS REQUIREMENT: Use full '-global' suffix alias (e.g., 'backend-global'). QUICK START: global_repo_status('backend-global') returns global repo status. OUTPUT FIELDS: alias, repo_name, url (git repository URL), last_refresh (ISO 8601 timestamp), enable_temporal (boolean indicating git history search support). USE CASES: (1) Check when global repo was last refreshed, (2) Verify temporal search availability before time-range queries, (3) Confirm repository URL and configuration. TEMPORAL STATUS: If enable_temporal=true, can use time_range/at_commit parameters in search_code. If false, temporal queries return empty results. COMPARISON: global_repo_status (global shared repos) vs get_repository_status (your activated repos). TROUBLESHOOTING: Repository not found? Verify alias with list_global_repos. Want to force refresh? Use refresh_golden_repo. RELATED TOOLS: list_global_repos (see all global repos), refresh_golden_repo (update repo), get_global_config (check auto-refresh interval), search_code with temporal params (use temporal index).",
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
        "description": "TL;DR: Get current auto-refresh interval for ALL global repositories. Returns how frequently global repos automatically pull latest changes and re-index. QUICK START: get_global_config() returns current interval. OUTPUT: refresh_interval in seconds (minimum 60). USE CASES: (1) Check current auto-refresh frequency, (2) Audit system configuration, (3) Understand why repos update at certain intervals. SCOPE: This setting applies to ALL global repositories system-wide. Individual repos cannot have different intervals. NO PARAMETERS: Returns global configuration without filtering. TYPICAL VALUES: 300 (5 min), 900 (15 min), 3600 (1 hour). Lower values = fresher code but more system load. RELATED TOOLS: set_global_config (change interval), global_repo_status (check last refresh time for specific repo), refresh_golden_repo (force immediate refresh).",
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
        "description": "TL;DR: Configure auto-refresh interval for ALL global repositories system-wide. ADMIN ONLY (requires manage_golden_repos permission). QUICK START: set_global_config(300) sets 5-minute refresh interval. REQUIRED PARAMETER: refresh_interval in seconds (minimum 60, no maximum). EFFECT: All global repositories will automatically pull latest changes and re-index at this interval. TYPICAL VALUES: 300 (5 min, frequent updates), 900 (15 min, balanced), 3600 (1 hour, less load), 86400 (1 day, minimal). TRADEOFFS: Lower intervals = fresher code but higher system load and network usage. Higher intervals = less load but stale code between refreshes. USE CASES: (1) Adjust refresh frequency based on team velocity, (2) Reduce system load during peak hours, (3) Increase update frequency for critical repos. VERIFICATION: Use get_global_config to confirm new setting. SCOPE: Applies to ALL global repos - cannot set per-repo intervals. TROUBLESHOOTING: Permission denied? Requires admin role. Value too low? Must be >= 60 seconds. RELATED TOOLS: get_global_config (check current interval), refresh_golden_repo (force immediate refresh without changing interval), global_repo_status (check when specific repo last refreshed).",
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
    "get_job_details": {
        "name": "get_job_details",
        "description": "TL;DR: Get detailed status and progress information for specific background job using job_id. Monitor long-running operations like repository indexing, refresh, or removal. QUICK START: get_job_details(job_id) where job_id comes from add_golden_repo, remove_golden_repo, refresh_golden_repo, add_golden_repo_index. OUTPUT FIELDS: job_id (UUID), operation_type (what operation), status (pending/running/completed/failed/cancelled), created_at, started_at, completed_at (ISO 8601 timestamps), progress (0-100%), result (operation output if completed), error (diagnostic message if failed), username (who submitted job). USE CASES: (1) Monitor repository indexing progress after add_golden_repo, (2) Check if refresh_golden_repo completed successfully, (3) Diagnose job failures with error messages, (4) Track long-running operations. JOB LIFECYCLE: pending → running → completed/failed. Poll this endpoint periodically until status is completed or failed. TROUBLESHOOTING: Job not found? job_id may be expired (old jobs are cleaned up). Job stuck in running? Check error field for issues, or contact admin for server logs. RELATED TOOLS: get_job_statistics (overview of all jobs), add_golden_repo (returns job_id), refresh_golden_repo (returns job_id), remove_golden_repo (returns job_id), add_golden_repo_index (returns job_id).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The unique identifier of the job to query (UUID format)",
                }
            },
            "required": ["job_id"],
        },
        "required_permission": "query_repos",
        "outputSchema": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether the operation succeeded",
                },
                "job": {
                    "type": "object",
                    "description": "Job details including status, timestamps, progress, and error information",
                    "properties": {
                        "job_id": {
                            "type": "string",
                            "description": "Unique job identifier (UUID)",
                        },
                        "operation_type": {
                            "type": "string",
                            "description": "Type of operation (e.g., add_golden_repo, remove_golden_repo)",
                        },
                        "status": {
                            "type": "string",
                            "description": "Current job status (pending, running, completed, failed, cancelled)",
                        },
                        "created_at": {
                            "type": "string",
                            "description": "ISO 8601 timestamp when job was created",
                        },
                        "started_at": {
                            "type": ["string", "null"],
                            "description": "ISO 8601 timestamp when job started (null if not started)",
                        },
                        "completed_at": {
                            "type": ["string", "null"],
                            "description": "ISO 8601 timestamp when job completed (null if not completed)",
                        },
                        "progress": {
                            "type": "integer",
                            "description": "Job progress percentage (0-100)",
                        },
                        "result": {
                            "type": ["object", "null"],
                            "description": "Job result data (null if not completed or failed)",
                        },
                        "error": {
                            "type": ["string", "null"],
                            "description": "Error message if job failed (null if no error)",
                        },
                        "username": {
                            "type": "string",
                            "description": "Username of the user who submitted the job",
                        },
                    },
                },
                "error": {
                    "type": "string",
                    "description": "Error message if operation failed",
                },
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
        List of MCP-compliant tool definitions (name, description, inputSchema only)
    """
    filtered_tools = []

    for tool_name, tool_def in TOOL_REGISTRY.items():
        required_permission = tool_def["required_permission"]
        if user.has_permission(required_permission):
            # Only include MCP-valid fields (name, description, inputSchema)
            # Filter out internal fields (required_permission, outputSchema)
            mcp_tool = {
                "name": tool_def["name"],
                "description": tool_def["description"],
                "inputSchema": tool_def["inputSchema"],
            }
            filtered_tools.append(mcp_tool)

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
        "TL;DR: [SCIP Code Intelligence] Find where a symbol is defined (class, function, method). Returns exact file location, line number, and symbol kind. "
        "SYMBOL FORMAT: Pass simple names like 'UserService', 'authenticate', 'DatabaseManager'. SCIP will match fuzzy by default - 'User' matches 'UserService', 'UserManager', etc. For exact matching, use exact=true. Full SCIP format like 'scip-python python code-indexer abc123 `module`/ClassName#method().' is handled internally - you only provide the readable part. "
        "FUZZY VS EXACT MATCHING: Fuzzy (default, exact=false) uses substring matching - 'User' matches 'UserService', 'UserManager', 'UserRepository'. Fast and flexible, best for exploration when you don't know the exact symbol name. Exact (exact=true) uses precise matching - 'UserService' only matches 'UserService'. Slower but guaranteed accuracy, best when you know the exact symbol name and want no false positives. "
        "WHEN TO USE: Finding where a class/function/method is defined. Locating the source of a symbol before reading its implementation. Understanding what a symbol is (class vs function vs method). First step before using scip_references, scip_dependencies, or scip_dependents. "
        "WHEN NOT TO USE: Finding all usages of a symbol (use scip_references instead). Understanding what a symbol depends on (use scip_dependencies). Understanding what depends on a symbol (use scip_dependents). Impact analysis (use scip_impact). Tracing call paths (use scip_callchain). Getting curated file list for a symbol (use scip_context). "
        "REQUIRES: SCIP indexes must be generated via 'cidx scip generate' before querying. Check .code-indexer/scip/ directory for .scip files. "
        "RELATED TOOLS: scip_references (find all usages), scip_dependencies (what symbol depends on), scip_dependents (what depends on symbol), scip_context (get curated file list). "
        'EXAMPLE: {"symbol": "DatabaseManager", "exact": false} returns [{"symbol": "com.example.DatabaseManager", "project": "code-indexer", "file_path": "src/code_indexer/scip/database/schema.py", "line": 13, "column": 0, "kind": "class", "relationship": null, "context": null}]'
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
            "success": {
                "type": "boolean",
                "description": "Whether the operation succeeded",
            },
            "symbol": {
                "type": "string",
                "description": "Symbol name that was searched for",
            },
            "total_results": {
                "type": "integer",
                "description": "Total number of definitions found",
            },
            "results": {
                "type": "array",
                "description": "List of definition locations",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Full SCIP symbol identifier",
                        },
                        "project": {"type": "string", "description": "Project path"},
                        "file_path": {
                            "type": "string",
                            "description": "File path relative to project root",
                        },
                        "line": {
                            "type": "integer",
                            "description": "Line number (1-indexed)",
                        },
                        "column": {
                            "type": "integer",
                            "description": "Column number (0-indexed)",
                        },
                        "kind": {
                            "type": "string",
                            "description": "Symbol kind (class, function, method, variable, etc.)",
                        },
                        "relationship": {
                            "type": ["string", "null"],
                            "description": "Relationship type (always null for definitions)",
                        },
                        "context": {
                            "type": ["string", "null"],
                            "description": "Additional context (always null for definitions)",
                        },
                    },
                    "required": [
                        "symbol",
                        "project",
                        "file_path",
                        "line",
                        "column",
                        "kind",
                    ],
                },
            },
            "error": {
                "type": "string",
                "description": "Error message if operation failed",
            },
        },
        "required": ["success", "results"],
    },
}

TOOL_REGISTRY["scip_references"] = {
    "name": "scip_references",
    "description": (
        "TL;DR: [SCIP Code Intelligence] Find all places where a symbol is used/referenced (imports, calls, instantiations). Returns file locations, line numbers, and usage context. "
        "SYMBOL FORMAT: Pass simple names like 'UserService', 'authenticate', 'DatabaseManager'. SCIP will match fuzzy by default - 'User' matches 'UserService', 'UserManager', etc. For exact matching, use exact=true. Full SCIP format like 'scip-python python code-indexer abc123 `module`/ClassName#method().' is handled internally - you only provide the readable part. "
        "FUZZY VS EXACT MATCHING: Fuzzy (default, exact=false) uses substring matching - 'User' matches 'UserService', 'UserManager', 'UserRepository'. Fast and flexible, best for exploration when you want to find all related usages. Exact (exact=true) uses precise matching - 'UserService' only matches 'UserService'. Slower but guaranteed accuracy, best when you know the exact symbol name and want only its references. "
        "WHEN TO USE: Finding all code that uses/imports/calls a symbol. Understanding how widespread a symbol's usage is. Identifying all callsites before refactoring. Finding examples of how a symbol is used in practice. "
        "WHEN NOT TO USE: Finding where a symbol is defined (use scip_definition instead). Understanding what a symbol depends on (use scip_dependencies). Understanding what depends on a symbol (use scip_dependents - references show usage points, dependents show dependent symbols). Impact analysis (use scip_impact). Tracing call paths (use scip_callchain). Getting curated file list (use scip_context). "
        "REQUIRES: SCIP indexes must be generated via 'cidx scip generate' before querying. Check .code-indexer/scip/ directory for .scip files. "
        "RELATED TOOLS: scip_definition (find definition), scip_dependents (what symbols depend on target), scip_impact (recursive dependency analysis), scip_context (get curated file list). "
        'EXAMPLE: {"symbol": "DatabaseManager", "limit": 100, "exact": false} returns [{"symbol": "com.example.DatabaseManager", "project": "code-indexer", "file_path": "src/code_indexer/scip/query/primitives.py", "line": 42, "column": 8, "kind": "reference", "relationship": "import", "context": "from code_indexer.scip.database.schema import DatabaseManager"}]'
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
            "success": {
                "type": "boolean",
                "description": "Whether the operation succeeded",
            },
            "symbol": {
                "type": "string",
                "description": "Symbol name that was searched for",
            },
            "total_results": {
                "type": "integer",
                "description": "Total number of references found",
            },
            "results": {
                "type": "array",
                "description": "List of reference locations",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Full SCIP symbol identifier",
                        },
                        "project": {"type": "string", "description": "Project path"},
                        "file_path": {
                            "type": "string",
                            "description": "File path relative to project root",
                        },
                        "line": {
                            "type": "integer",
                            "description": "Line number (1-indexed)",
                        },
                        "column": {
                            "type": "integer",
                            "description": "Column number (0-indexed)",
                        },
                        "kind": {
                            "type": "string",
                            "description": "Symbol kind (reference)",
                        },
                        "relationship": {
                            "type": ["string", "null"],
                            "description": "Relationship type (import, call, instantiation, etc.)",
                        },
                        "context": {
                            "type": ["string", "null"],
                            "description": "Code context where reference occurs",
                        },
                    },
                    "required": [
                        "symbol",
                        "project",
                        "file_path",
                        "line",
                        "column",
                        "kind",
                    ],
                },
            },
            "error": {
                "type": "string",
                "description": "Error message if operation failed",
            },
        },
        "required": ["success", "results"],
    },
}

TOOL_REGISTRY["scip_dependencies"] = {
    "name": "scip_dependencies",
    "description": (
        "TL;DR: [SCIP Code Intelligence] Find what a symbol depends on (imports, calls, uses). Returns symbols and files that the target symbol requires to function. "
        "SYMBOL FORMAT: Pass simple names like 'UserService', 'authenticate', 'DatabaseManager'. SCIP will match fuzzy by default - 'User' matches 'UserService', 'UserManager', etc. For exact matching, use exact=true. Full SCIP format like 'scip-python python code-indexer abc123 `module`/ClassName#method().' is handled internally - you only provide the readable part. "
        "FUZZY VS EXACT MATCHING: Fuzzy (default, exact=false) uses substring matching - 'User' matches 'UserService', 'UserManager', 'UserRepository'. Fast and flexible, best for exploration. Exact (exact=true) uses precise matching - 'UserService' only matches 'UserService'. Slower but guaranteed accuracy, best when you know the exact symbol name. "
        "WHEN TO USE: Understanding what a symbol needs to work (its dependencies). Identifying imports and external dependencies. Finding all symbols a target symbol calls or uses. Understanding coupling and dependency relationships. Planning refactoring by understanding dependencies. "
        "WHEN NOT TO USE: Finding what depends on a symbol (use scip_dependents instead - opposite direction). Finding all usages (use scip_references). Finding definitions (use scip_definition). Impact analysis (use scip_impact for recursive dependency tree). Tracing call paths (use scip_callchain). Getting curated file list (use scip_context). "
        "REQUIRES: SCIP indexes must be generated via 'cidx scip generate' before querying. Check .code-indexer/scip/ directory for .scip files. "
        "RELATED TOOLS: scip_dependents (opposite direction - what depends on symbol), scip_impact (recursive dependency analysis), scip_definition (find symbol definition), scip_context (get curated file list). "
        'EXAMPLE: {"symbol": "SCIPQueryEngine", "depth": 1, "exact": false} returns [{"symbol": "com.example.DatabaseManager", "project": "code-indexer", "file_path": "src/code_indexer/scip/query/primitives.py", "line": 15, "column": 0, "kind": "dependency", "relationship": "import", "context": "from code_indexer.scip.database.schema import DatabaseManager"}]'
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
            "success": {
                "type": "boolean",
                "description": "Whether the operation succeeded",
            },
            "symbol": {
                "type": "string",
                "description": "Symbol name that was searched for",
            },
            "total_results": {
                "type": "integer",
                "description": "Total number of dependencies found",
            },
            "results": {
                "type": "array",
                "description": "List of dependency symbols",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Full SCIP symbol identifier of dependency",
                        },
                        "project": {"type": "string", "description": "Project path"},
                        "file_path": {
                            "type": "string",
                            "description": "File path relative to project root",
                        },
                        "line": {
                            "type": "integer",
                            "description": "Line number (1-indexed)",
                        },
                        "column": {
                            "type": "integer",
                            "description": "Column number (0-indexed)",
                        },
                        "kind": {
                            "type": "string",
                            "description": "Symbol kind (dependency)",
                        },
                        "relationship": {
                            "type": ["string", "null"],
                            "description": "Relationship type (import, call, use, etc.)",
                        },
                        "context": {
                            "type": ["string", "null"],
                            "description": "Code context where dependency occurs",
                        },
                    },
                    "required": [
                        "symbol",
                        "project",
                        "file_path",
                        "line",
                        "column",
                        "kind",
                    ],
                },
            },
            "error": {
                "type": "string",
                "description": "Error message if operation failed",
            },
        },
        "required": ["success", "results"],
    },
}

TOOL_REGISTRY["scip_dependents"] = {
    "name": "scip_dependents",
    "description": (
        "TL;DR: [SCIP Code Intelligence] Find what depends on a symbol (reverse dependencies). Returns symbols and files that require/use the target symbol. Opposite of scip_dependencies. "
        "SYMBOL FORMAT: Pass simple names like 'UserService', 'authenticate', 'DatabaseManager'. SCIP will match fuzzy by default - 'User' matches 'UserService', 'UserManager', etc. For exact matching, use exact=true. Full SCIP format like 'scip-python python code-indexer abc123 `module`/ClassName#method().' is handled internally - you only provide the readable part. "
        "FUZZY VS EXACT MATCHING: Fuzzy (default, exact=false) uses substring matching - 'User' matches 'UserService', 'UserManager', 'UserRepository'. Fast and flexible, best for exploration. Exact (exact=true) uses precise matching - 'UserService' only matches 'UserService'. Slower but guaranteed accuracy, best when you know the exact symbol name. "
        "WHEN TO USE: Understanding impact of changing a symbol (what will break). Finding all code that relies on a symbol. Identifying coupling and understanding how widely a symbol is used. Planning refactoring by understanding dependent code. Understanding blast radius before modifying a symbol. "
        "WHEN NOT TO USE: Finding what a symbol depends on (use scip_dependencies instead - opposite direction). Finding all usages (use scip_references for raw usage points). Finding definitions (use scip_definition). Full recursive impact analysis (use scip_impact for complete dependency tree). Tracing call paths (use scip_callchain). Getting curated file list (use scip_context). "
        "REQUIRES: SCIP indexes must be generated via 'cidx scip generate' before querying. Check .code-indexer/scip/ directory for .scip files. "
        "RELATED TOOLS: scip_dependencies (opposite direction - what symbol depends on), scip_impact (recursive dependency analysis), scip_references (raw usage points), scip_context (get curated file list). "
        'EXAMPLE: {"symbol": "DatabaseManager", "depth": 1, "exact": false} returns [{"symbol": "com.example.SCIPQueryEngine", "project": "code-indexer", "file_path": "src/code_indexer/scip/query/primitives.py", "line": 15, "column": 0, "kind": "dependent", "relationship": "uses", "context": "self.db = DatabaseManager()"}]'
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
            "success": {
                "type": "boolean",
                "description": "Whether the operation succeeded",
            },
            "symbol": {
                "type": "string",
                "description": "Symbol name that was searched for",
            },
            "total_results": {
                "type": "integer",
                "description": "Total number of dependents found",
            },
            "results": {
                "type": "array",
                "description": "List of dependent symbols",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Full SCIP symbol identifier of dependent",
                        },
                        "project": {"type": "string", "description": "Project path"},
                        "file_path": {
                            "type": "string",
                            "description": "File path relative to project root",
                        },
                        "line": {
                            "type": "integer",
                            "description": "Line number (1-indexed)",
                        },
                        "column": {
                            "type": "integer",
                            "description": "Column number (0-indexed)",
                        },
                        "kind": {
                            "type": "string",
                            "description": "Symbol kind (dependent)",
                        },
                        "relationship": {
                            "type": ["string", "null"],
                            "description": "Relationship type (uses, calls, imports, etc.)",
                        },
                        "context": {
                            "type": ["string", "null"],
                            "description": "Code context where dependent uses target",
                        },
                    },
                    "required": [
                        "symbol",
                        "project",
                        "file_path",
                        "line",
                        "column",
                        "kind",
                    ],
                },
            },
            "error": {
                "type": "string",
                "description": "Error message if operation failed",
            },
        },
        "required": ["success", "results"],
    },
}

TOOL_REGISTRY["scip_impact"] = {
    "name": "scip_impact",
    "description": (
        "TL;DR: [SCIP Code Intelligence] Recursive impact analysis - find ALL symbols and files affected by changing a symbol. Returns complete dependency tree with depth tracking and file-level summaries. Use this for comprehensive change impact assessment. "
        "SYMBOL FORMAT: Pass simple names like 'UserService', 'authenticate', 'DatabaseManager'. SCIP will match fuzzy by default. Full SCIP format like 'scip-python python code-indexer abc123 `module`/ClassName#method().' is handled internally - you only provide the readable part. "
        "DEPTH BEHAVIOR: Results grow linearly with depth (BFS traversal with cycle detection prevents exponential growth). depth=1 shows direct dependents, depth=2 adds dependents-of-dependents, depth=3 adds third-level dependents. Use depth=3 (default) for comprehensive analysis, depth=5+ for mission-critical changes requiring complete blast radius understanding. Higher depth increases query time but ensures complete impact visibility. "
        "WHEN TO USE: Understanding full blast radius of changing a symbol. Planning refactoring with complete dependency tree visibility. Assessing risk before modifying critical code. Generating file lists for comprehensive testing. Understanding cascading dependencies across multiple levels. Finding all code that transitively depends on a symbol. "
        "WHEN NOT TO USE: Finding direct dependencies only (use scip_dependencies for faster single-level query). Finding direct dependents only (use scip_dependents for faster single-level query). Simple usage point lookup (use scip_references). Finding definitions (use scip_definition). Tracing specific call paths (use scip_callchain). Getting prioritized file list for reading (use scip_context). "
        "REQUIRES: SCIP indexes must be generated via 'cidx scip generate' before querying. Check .code-indexer/scip/ directory for .scip files. "
        "RELATED TOOLS: scip_dependents (single-level dependents), scip_dependencies (single-level dependencies), scip_callchain (trace call paths), scip_context (get curated file list with relevance scoring). "
        'EXAMPLE: {"symbol": "DatabaseManager", "depth": 3} returns {"target_symbol": "com.example.DatabaseManager", "depth_analyzed": 3, "total_affected": 47, "affected_symbols": [{"symbol": "SCIPQueryEngine", "file_path": "src/code_indexer/scip/query/primitives.py", "line": 15, "column": 0, "depth": 1, "relationship": "uses", "chain": ["DatabaseManager", "SCIPQueryEngine"]}], "affected_files": [{"path": "src/code_indexer/scip/query/primitives.py", "project": "code-indexer", "affected_symbol_count": 3, "min_depth": 1, "max_depth": 2}]}'
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
            "success": {
                "type": "boolean",
                "description": "Whether the operation succeeded",
            },
            "target_symbol": {
                "type": "string",
                "description": "Full SCIP symbol identifier analyzed",
            },
            "depth_analyzed": {
                "type": "integer",
                "description": "Actual depth analyzed",
            },
            "total_affected": {
                "type": "integer",
                "description": "Total number of affected symbols",
            },
            "truncated": {
                "type": "boolean",
                "description": "Whether results were truncated due to size limits",
            },
            "affected_symbols": {
                "type": "array",
                "description": "List of all symbols affected by changing target symbol",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Full SCIP symbol identifier",
                        },
                        "file_path": {
                            "type": "string",
                            "description": "File path relative to project root",
                        },
                        "line": {
                            "type": "integer",
                            "description": "Line number (1-indexed)",
                        },
                        "column": {
                            "type": "integer",
                            "description": "Column number (0-indexed)",
                        },
                        "depth": {
                            "type": "integer",
                            "description": "Depth level in dependency tree",
                        },
                        "relationship": {
                            "type": "string",
                            "description": "Relationship type (uses, calls, imports, etc.)",
                        },
                        "chain": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Dependency chain from target to this symbol",
                        },
                    },
                    "required": [
                        "symbol",
                        "file_path",
                        "line",
                        "column",
                        "depth",
                        "relationship",
                        "chain",
                    ],
                },
            },
            "affected_files": {
                "type": "array",
                "description": "File-level summary of impact",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path relative to project root",
                        },
                        "project": {"type": "string", "description": "Project path"},
                        "affected_symbol_count": {
                            "type": "integer",
                            "description": "Number of affected symbols in file",
                        },
                        "min_depth": {
                            "type": "integer",
                            "description": "Minimum depth of affected symbols",
                        },
                        "max_depth": {
                            "type": "integer",
                            "description": "Maximum depth of affected symbols",
                        },
                    },
                    "required": [
                        "path",
                        "project",
                        "affected_symbol_count",
                        "min_depth",
                        "max_depth",
                    ],
                },
            },
            "error": {
                "type": "string",
                "description": "Error message if operation failed",
            },
        },
        "required": ["success", "affected_symbols", "affected_files"],
    },
}

TOOL_REGISTRY["scip_callchain"] = {
    "name": "scip_callchain",
    "description": (
        "TL;DR: [SCIP Code Intelligence] Trace all execution paths from entry point (from_symbol) to target function (to_symbol). "
        "\n\n"
        "SUPPORTED SYMBOL FORMATS:\n"
        '- Simple names: "chat", "invoke", "CustomChain", "BaseClient"\n'
        '- Class#method: "CustomChain#chat", "BaseClient#invoke"\n'
        '- Full SCIP identifiers: "scip-python python . hash `module`/Class#method()."\n'
        "\n\n"
        "USAGE EXAMPLES:\n"
        '- Method to method: from_symbol="chat", to_symbol="invoke"\n'
        '- Class to class: from_symbol="CustomChain", to_symbol="BaseClient"\n'
        '- Within class: from_symbol="CustomChain#chat", to_symbol="CustomChain#_generate_sql"\n'
        "\n\n"
        "KNOWN LIMITATIONS:\n"
        "- May not capture FastAPI endpoint decorators (@app.post, @app.get)\n"
        "- Factory functions may not show call chains to instantiated methods\n"
        "- Cross-repository search: omit repository_alias to search all repositories\n"
        "\n\n"
        "RESPONSE INCLUDES:\n"
        "- path: List of symbol names in execution order\n"
        "- length: Number of hops in the chain\n"
        "- has_cycle: Boolean indicating if path contains cycles\n"
        "- diagnostic: Helpful message when no chains found\n"
        "- scip_files_searched: Number of SCIP indexes searched\n"
        "- repository_filter: Which repository was searched\n"
        "\n\n"
        "TIPS FOR BEST RESULTS:\n"
        "- Start with simple class or method names\n"
        "- Use repository_alias to limit search scope\n"
        "- Increase max_depth if chains seem incomplete (max: 10)\n"
        "- Check diagnostic message if 0 chains found\n"
        "\n\n"
        "REQUIRES: SCIP indexes must be generated via 'cidx scip generate' before querying. Check .code-indexer/scip/ directory for .scip files. "
        "RELATED TOOLS: scip_impact (full dependency tree), scip_dependencies (what symbol depends on), scip_dependents (what depends on symbol), scip_context (get curated file list). "
        'EXAMPLE: {"from_symbol": "handle_request", "to_symbol": "DatabaseManager", "max_depth": 10} returns {"from_symbol": "handle_request", "to_symbol": "DatabaseManager", "total_chains_found": 2, "chains": [{"length": 3, "path": [{"symbol": "handle_request", "file_path": "src/api/handler.py", "line": 10, "column": 0, "call_type": "call"}, {"symbol": "UserService.authenticate", "file_path": "src/services/user.py", "line": 25, "column": 4, "call_type": "call"}, {"symbol": "DatabaseManager.query", "file_path": "src/database/manager.py", "line": 50, "column": 8, "call_type": "call"}]}]}'
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
            "success": {
                "type": "boolean",
                "description": "Whether the operation succeeded",
            },
            "from_symbol": {
                "type": "string",
                "description": "Starting symbol searched",
            },
            "to_symbol": {"type": "string", "description": "Target symbol searched"},
            "total_chains_found": {
                "type": "integer",
                "description": "Total number of call chains found",
            },
            "truncated": {
                "type": "boolean",
                "description": "Whether results were truncated due to size limits",
            },
            "max_depth_reached": {
                "type": "boolean",
                "description": "Whether search hit max_depth limit",
            },
            "chains": {
                "type": "array",
                "description": "List of call chains from source to target",
                "items": {
                    "type": "object",
                    "properties": {
                        "length": {
                            "type": "integer",
                            "description": "Number of steps in chain",
                        },
                        "path": {
                            "type": "array",
                            "description": "Sequence of call steps from source to target",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "symbol": {
                                        "type": "string",
                                        "description": "Symbol at this step",
                                    },
                                    "file_path": {
                                        "type": "string",
                                        "description": "File path relative to project root",
                                    },
                                    "line": {
                                        "type": "integer",
                                        "description": "Line number (1-indexed)",
                                    },
                                    "column": {
                                        "type": "integer",
                                        "description": "Column number (0-indexed)",
                                    },
                                    "call_type": {
                                        "type": "string",
                                        "description": "Type of call (call, import, instantiation, etc.)",
                                    },
                                },
                                "required": [
                                    "symbol",
                                    "file_path",
                                    "line",
                                    "column",
                                    "call_type",
                                ],
                            },
                        },
                    },
                    "required": ["length", "path"],
                },
            },
            "error": {
                "type": "string",
                "description": "Error message if operation failed",
            },
        },
        "required": ["success", "chains"],
    },
}

TOOL_REGISTRY["scip_context"] = {
    "name": "scip_context",
    "description": (
        "TL;DR: [SCIP Code Intelligence] Get smart, curated file list for understanding a symbol. Returns prioritized files with relevance scoring - files containing definition, direct dependencies/dependents, and related symbols. Perfect for 'what files should I read to understand X?' Use this before reading code. "
        "SYMBOL FORMAT: Pass simple names like 'UserService', 'authenticate', 'DatabaseManager'. SCIP will match fuzzy by default. Full SCIP format like 'scip-python python code-indexer abc123 `module`/ClassName#method().' is handled internally - you only provide the readable part. "
        "WHEN TO USE: Getting curated list of files to read for understanding a symbol. Prioritized file list before code review. Understanding symbol context without reading entire codebase. Building mental model of symbol's ecosystem. Finding related code for refactoring. Efficient context gathering for code analysis. "
        "WHEN NOT TO USE: Finding all usages (use scip_references). Impact analysis (use scip_impact). Finding dependencies (use scip_dependencies). Finding dependents (use scip_dependents). Tracing call paths (use scip_callchain). Finding definitions (use scip_definition). "
        "REQUIRES: SCIP indexes must be generated via 'cidx scip generate' before querying. Check .code-indexer/scip/ directory for .scip files. "
        "RELATED TOOLS: scip_definition (find definition first), scip_impact (full dependency tree), scip_dependencies (what symbol depends on), scip_dependents (what depends on symbol). "
        'EXAMPLE: {"symbol": "DatabaseManager", "limit": 20, "min_score": 0.0} returns {"target_symbol": "com.example.DatabaseManager", "summary": "Read these 3 file(s) - 1 HIGH priority, 2 MEDIUM priority", "total_files": 3, "total_symbols": 8, "avg_relevance": 0.75, "files": [{"path": "src/code_indexer/scip/database/schema.py", "project": "code-indexer", "relevance_score": 1.0, "read_priority": 1, "symbols": [{"name": "DatabaseManager", "kind": "class", "relationship": "definition", "line": 13, "column": 0, "relevance": 1.0}]}]}'
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
            "success": {
                "type": "boolean",
                "description": "Whether the operation succeeded",
            },
            "target_symbol": {
                "type": "string",
                "description": "Full SCIP symbol identifier analyzed",
            },
            "summary": {
                "type": "string",
                "description": "Human-readable summary of results",
            },
            "total_files": {
                "type": "integer",
                "description": "Total number of files returned",
            },
            "total_symbols": {
                "type": "integer",
                "description": "Total number of symbols across all files",
            },
            "avg_relevance": {
                "type": "number",
                "description": "Average relevance score across all files",
            },
            "files": {
                "type": "array",
                "description": "Prioritized list of files to read, sorted by relevance",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path relative to project root",
                        },
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
                                    "name": {
                                        "type": "string",
                                        "description": "Symbol name",
                                    },
                                    "kind": {
                                        "type": "string",
                                        "description": "Symbol kind (class, function, method, etc.)",
                                    },
                                    "relationship": {
                                        "type": "string",
                                        "description": "Relationship to target (definition, dependency, dependent, reference)",
                                    },
                                    "line": {
                                        "type": "integer",
                                        "description": "Line number (1-indexed)",
                                    },
                                    "column": {
                                        "type": "integer",
                                        "description": "Column number (0-indexed)",
                                    },
                                    "relevance": {
                                        "type": "number",
                                        "description": "Symbol relevance score (0.0-1.0)",
                                    },
                                },
                                "required": [
                                    "name",
                                    "kind",
                                    "relationship",
                                    "line",
                                    "column",
                                    "relevance",
                                ],
                            },
                        },
                    },
                    "required": [
                        "path",
                        "project",
                        "relevance_score",
                        "read_priority",
                        "symbols",
                    ],
                },
            },
            "error": {
                "type": "string",
                "description": "Error message if operation failed",
            },
        },
        "required": ["success", "files"],
    },
}
# =============================================================================
# Documentation & Help Tools
# =============================================================================

TOOL_REGISTRY["cidx_quick_reference"] = {
    "name": "cidx_quick_reference",
    "description": (
        "TL;DR: Get quick reference documentation for CIDX MCP tools. Returns concise summaries of available tools with their purposes and when to use them. "
        "USE CASES: (1) Discover what tools are available, (2) Understand tool purposes before using them, (3) Find the right tool for a specific task, (4) Filter tools by category. "
        "CATEGORIES: search (semantic/FTS code search), scip (code intelligence - definitions, references, dependencies, call chains), git_exploration (repository exploration, commit history, diffs), git_operations (status, stage, commit, push, pull, branch management), files (CRUD operations - list, create, edit, delete, move files), repo_management (activate/deactivate repos), golden_repos (add/remove/refresh global repositories), system (health checks, job monitoring, statistics), user_management (create/delete users, manage roles), ssh_keys (manage SSH keys for git operations), meta (documentation, quick reference). "
        "OUTPUT: Returns tool names with TL;DR descriptions extracted from full tool definitions. Use category filter to narrow results. "
        'EXAMPLE: {"category": "scip"} returns all 7 SCIP tools with their TL;DR summaries. {"category": null} returns all 53 tools.'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "category": {
                "type": ["string", "null"],
                "enum": [
                    "search",
                    "scip",
                    "git_exploration",
                    "git_operations",
                    "files",
                    "repo_management",
                    "golden_repos",
                    "system",
                    "user_management",
                    "ssh_keys",
                    "meta",
                    None,
                ],
                "default": None,
                "description": "Optional category filter. null/omitted returns all tools. Options: search, scip, git_exploration, git_operations, files, repo_management, golden_repos, system, user_management, ssh_keys, meta.",
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
                "description": "Whether the operation succeeded",
            },
            "total_tools": {
                "type": "integer",
                "description": "Total number of tools returned",
            },
            "category_filter": {
                "type": ["string", "null"],
                "description": "Category filter applied (null if showing all)",
            },
            "tools": {
                "type": "array",
                "description": "List of tool summaries",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Tool name"},
                        "category": {"type": "string", "description": "Tool category"},
                        "summary": {
                            "type": "string",
                            "description": "TL;DR summary from tool description",
                        },
                        "required_permission": {
                            "type": "string",
                            "description": "Permission required to use this tool",
                        },
                    },
                    "required": ["name", "category", "summary", "required_permission"],
                },
            },
            "error": {
                "type": "string",
                "description": "Error message if operation failed",
            },
        },
        "required": ["success", "total_tools", "tools"],
    },
}

TOOL_REGISTRY["get_tool_categories"] = {
    "name": "get_tool_categories",
    "description": """TL;DR: Get organized list of all available MCP tools grouped by category. Use this to discover what tools are available and what each category offers.

USE CASES:
(1) New user wanting to see what CIDX can do
(2) Looking for tools in a specific category (search, git, file operations, etc.)
(3) Discovering related tools when you know one tool in a category

RETURNS: Tools organized into logical categories with one-line descriptions.

CATEGORIES INCLUDED:
- SEARCH & DISCOVERY: Code search, browsing, file exploration
- GIT HISTORY & EXPLORATION: Commit history, blame, diffs, temporal queries
- GIT OPERATIONS: Stage, commit, push, pull, branch management
- FILE CRUD: Create, edit, delete files in activated repositories
- SCIP CODE INTELLIGENCE: Find definitions, references, call chains, dependencies
- REPOSITORY MANAGEMENT: Activate, deactivate, sync repositories
- SYSTEM & ADMIN: User management, repository administration, system info

EXAMPLE OUTPUT:
{
  "categories": {
    "SEARCH & DISCOVERY": [
      "search_code - Semantic/FTS code search across repositories",
      "regex_search - Pattern matching without requiring indexes",
      "browse_directory - List files with metadata and filtering",
      ...
    ],
    ...
  },
  "total_tools": 55
}

RELATED TOOLS:
- cidx_quick_reference: Decision guide for choosing tools
- first_time_user_guide: Step-by-step getting started guide
""",
    "inputSchema": {"type": "object", "properties": {}, "required": []},
    "required_permission": None,
    "outputSchema": {
        "type": "object",
        "properties": {
            "categories": {
                "type": "object",
                "description": "Tools organized by category",
                "additionalProperties": {"type": "array", "items": {"type": "string"}},
            },
            "total_tools": {
                "type": "integer",
                "description": "Total number of tools available",
            },
        },
    },
}

TOOL_REGISTRY["first_time_user_guide"] = {
    "name": "first_time_user_guide",
    "description": """TL;DR: Get step-by-step quick start guide for new CIDX MCP server users. Shows the essential workflow to get started productively.

USE CASES:
(1) Brand new user who just connected to CIDX MCP server
(2) User who wants to verify they understand the basic workflow
(3) Onboarding team members to CIDX

WHAT YOU'LL LEARN:
- How to check your permissions and role
- How to discover available repositories
- How to run your first search
- How to explore repository structure
- How to activate repositories for file editing
- How to use git operations

THE WORKFLOW:
Step 1: Check your identity and permissions
  whoami() -> See your username, role, and what you can do

Step 2: Discover available repositories
  list_global_repos() -> See all repositories you can search

Step 3: Check repository capabilities
  global_repo_status('repo-name-global') -> Check what indexes exist (semantic, FTS, temporal, SCIP)

Step 4: Run your first search
  search_code(query_text='authentication', repository_alias='backend-global', limit=5)
  -> Find code related to authentication, start with small limit

Step 5: Explore repository structure
  browse_directory(repository_alias='backend-global', path='src')
  -> See what files and folders exist

Step 6: Use code intelligence (if SCIP available)
  scip_definition(symbol='authenticate_user', repository_alias='backend-global')
  -> Find where functions are defined

Step 7: For file editing - activate a repository
  activate_repository(username='yourname', golden_repo_alias='backend-golden', user_alias='my-backend')
  -> Creates your personal writable copy

Step 8: Make changes with git workflow
  create_file(...) -> edit_file(...) -> git_stage(...) -> git_commit(...) -> git_push(...)

NEXT STEPS:
- Use get_tool_categories() to discover more tools
- Use cidx_quick_reference(category='search') for detailed tool selection guidance
- Check permission_reference if you get permission errors

COMMON QUESTIONS:
Q: When do I use '-global' suffix?
A: Always for global repos (read-only, shared). Never for activated repos (your personal copies).

Q: What's the difference between search_code and regex_search?
A: search_code uses pre-built indexes (fast, approximate). regex_search scans files directly (comprehensive, slower).

Q: Why can't I edit files in global repos?
A: Global repos are read-only. Activate them first to get your personal writable copy.
""",
    "inputSchema": {"type": "object", "properties": {}, "required": []},
    "required_permission": None,
    "outputSchema": {
        "type": "object",
        "properties": {
            "guide": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step_number": {"type": "integer"},
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "example_call": {"type": "string"},
                                "expected_result": {"type": "string"},
                            },
                        },
                    },
                    "quick_start_summary": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "One-line summary of each step for quick reference",
                    },
                    "common_errors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "error": {"type": "string"},
                                "solution": {"type": "string"},
                            },
                        },
                    },
                },
            }
        },
    },
}

# =============================================================================
# File CRUD Tools (Story #628)
# =============================================================================

TOOL_REGISTRY["create_file"] = {
    "name": "create_file",
    "description": (
        "Create a new file in an activated repository. "
        "USE CASES: (1) Create new source files, (2) Add configuration files, (3) Create documentation. "
        "REQUIREMENTS: Repository must be activated via activate_global_repo. File must not exist. "
        "RETURNS: File metadata including content_hash for future edits (optimistic locking). "
        "PERMISSIONS: Requires repository:write. "
        'EXAMPLE: {"repository_alias": "my-repo", "file_path": "src/new_module.py", "content": "def hello():\\n    return \'world\'"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {
                "type": "string",
                "description": "Repository alias (user workspace identifier)",
            },
            "file_path": {
                "type": "string",
                "description": "Path to new file within repository (relative path)",
                "pattern": "^(?!.*\\.git/).*$",  # Block .git/ paths
            },
            "content": {"type": "string", "description": "File content (UTF-8 text)"},
        },
        "required": ["repository_alias", "file_path", "content"],
        "additionalProperties": False,
    },
    "required_permission": "repository:write",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {
                "type": "boolean",
                "description": "Whether the file creation succeeded",
            },
            "file_path": {
                "type": "string",
                "description": "Relative path to created file (present when success=true)",
            },
            "content_hash": {
                "type": "string",
                "description": "SHA-256 hash of file content for optimistic locking in future edits (present when success=true)",
            },
            "size_bytes": {
                "type": "integer",
                "description": "File size in bytes (present when success=true)",
            },
            "created_at": {
                "type": "string",
                "description": "ISO 8601 timestamp when file was created (present when success=true)",
            },
            "error": {
                "type": "string",
                "description": "Error message (present when success=false)",
            },
        },
        "required": ["success"],
    },
}

TOOL_REGISTRY["edit_file"] = {
    "name": "edit_file",
    "description": (
        "Edit existing file using exact string replacement with optimistic locking. "
        "USE CASES: (1) Update source code, (2) Modify configurations, (3) Fix bugs. "
        "OPTIMISTIC LOCKING: content_hash prevents concurrent edit conflicts - hash from get_file_content or previous edit. "
        "STRING REPLACEMENT: old_string must match exactly (including whitespace). Use replace_all=true to replace all occurrences. "
        "REQUIREMENTS: File must exist, content_hash must match current state. "
        "PERMISSIONS: Requires repository:write. "
        'EXAMPLE: {"repository_alias": "my-repo", "file_path": "src/auth.py", "old_string": "def old_func():", "new_string": "def new_func():", "content_hash": "abc123def456"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"},
            "file_path": {
                "type": "string",
                "description": "Path to file within repository",
            },
            "old_string": {
                "type": "string",
                "description": "Exact string to replace (must match exactly including whitespace)",
            },
            "new_string": {"type": "string", "description": "Replacement string"},
            "content_hash": {
                "type": "string",
                "description": "SHA-256 hash for optimistic locking (from get_file_content or previous edit)",
            },
            "replace_all": {
                "type": "boolean",
                "description": "Replace all occurrences of old_string (default: false - replace first only)",
                "default": False,
            },
        },
        "required": [
            "repository_alias",
            "file_path",
            "old_string",
            "new_string",
            "content_hash",
        ],
        "additionalProperties": False,
    },
    "required_permission": "repository:write",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {
                "type": "boolean",
                "description": "Whether the file edit succeeded",
            },
            "file_path": {
                "type": "string",
                "description": "Relative path to edited file (present when success=true)",
            },
            "content_hash": {
                "type": "string",
                "description": "SHA-256 hash of updated file content for future edits (present when success=true)",
            },
            "modified_at": {
                "type": "string",
                "description": "ISO 8601 timestamp when file was modified (present when success=true)",
            },
            "changes_made": {
                "type": "integer",
                "description": "Number of replacements made (1 if replace_all=false, N if replace_all=true) (present when success=true)",
            },
            "error": {
                "type": "string",
                "description": "Error message (present when success=false)",
            },
        },
        "required": ["success"],
    },
}

TOOL_REGISTRY["delete_file"] = {
    "name": "delete_file",
    "description": (
        "Delete a file from an activated repository. "
        "USE CASES: (1) Remove obsolete files, (2) Clean up temporary files, (3) Delete test fixtures. "
        "SAFETY: Optional content_hash validation prevents accidental deletion of modified files. "
        "REQUIREMENTS: File must exist. Repository must be activated. "
        "PERMISSIONS: Requires repository:write. "
        'EXAMPLE: {"repository_alias": "my-repo", "file_path": "src/old_module.py", "content_hash": "xyz789"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"},
            "file_path": {"type": "string", "description": "Path to file to delete"},
            "content_hash": {
                "type": "string",
                "description": "Optional SHA-256 hash for validation before delete (prevents accidental deletion of modified files)",
            },
        },
        "required": ["repository_alias", "file_path"],
        "additionalProperties": False,
    },
    "required_permission": "repository:write",
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Operation success status"},
            "file_path": {"type": "string", "description": "Deleted file path"},
            "deleted_at": {
                "type": "string",
                "description": "Deletion timestamp (ISO 8601)",
            },
        },
        "required": ["success", "file_path", "deleted_at"],
    },
}

# =============================================================================
# Git Operations Tools (Story #628)
# =============================================================================

TOOL_REGISTRY["git_status"] = {
    "name": "git_status",
    "description": (
        "Get git working tree status for an activated repository. "
        "USE CASES: (1) Check modified/staged/untracked files, (2) Verify working tree state before commits, (3) Identify conflicts. "
        "RETURNS: Staged files, unstaged changes, untracked files, current branch, merge conflicts. "
        "PERMISSIONS: Requires repository:read. "
        'EXAMPLE: {"repository_alias": "my-repo"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"}
        },
        "required": ["repository_alias"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Operation success status"},
            "staged": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of staged files",
            },
            "unstaged": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of unstaged files",
            },
            "untracked": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of untracked files",
            },
        },
        "required": ["success"],
    },
    "required_permission": "repository:read",
}

TOOL_REGISTRY["git_stage"] = {
    "name": "git_stage",
    "description": (
        "Stage files for commit (git add). "
        "USE CASES: (1) Stage modified files, (2) Stage new files, (3) Prepare files for commit. "
        "REQUIREMENTS: Files must exist and have changes. "
        "PERMISSIONS: Requires repository:write. "
        'EXAMPLE: {"repository_alias": "my-repo", "file_paths": ["src/file1.py", "src/file2.py"]}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"},
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Array of file paths to stage (relative to repository root)",
            },
        },
        "required": ["repository_alias", "file_paths"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Operation succeeded"},
            "staged_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of file paths that were staged",
            },
        },
    },
    "required_permission": "repository:write",
}

TOOL_REGISTRY["git_unstage"] = {
    "name": "git_unstage",
    "description": (
        "Unstage files (git reset HEAD). "
        "USE CASES: (1) Remove files from staging area, (2) Un-stage accidentally staged files. "
        "REQUIREMENTS: Files must be currently staged. "
        "PERMISSIONS: Requires repository:write. "
        'EXAMPLE: {"repository_alias": "my-repo", "file_paths": ["src/file1.py"]}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"},
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Array of file paths to unstage",
            },
        },
        "required": ["repository_alias", "file_paths"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Operation succeeded"},
            "unstaged_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of file paths that were unstaged",
            },
        },
    },
    "required_permission": "repository:write",
}

TOOL_REGISTRY["git_commit"] = {
    "name": "git_commit",
    "description": (
        "Create a git commit with staged changes. "
        "USE CASES: (1) Commit staged files, (2) Create checkpoint with message, (3) Record changes with attribution. "
        "REQUIREMENTS: Must have staged files. "
        "OPTIONAL: author_name and author_email for custom commit attribution. "
        "PERMISSIONS: Requires repository:write. "
        'EXAMPLE: {"repository_alias": "my-repo", "message": "Fix authentication bug", "author_name": "John Doe", "author_email": "john@example.com"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"},
            "message": {"type": "string", "description": "Commit message"},
            "author_name": {
                "type": "string",
                "description": "Optional author name for commit attribution",
            },
            "author_email": {
                "type": "string",
                "description": "Optional author email for commit attribution",
            },
        },
        "required": ["repository_alias", "message"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Operation succeeded"},
            "commit_hash": {
                "type": "string",
                "description": "Full 40-character commit SHA",
            },
            "short_hash": {
                "type": "string",
                "description": "7-character short commit SHA",
            },
            "message": {"type": "string", "description": "Commit message"},
            "author": {"type": "string", "description": "Commit author"},
            "files_committed": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of files included in commit",
            },
        },
    },
    "required_permission": "repository:write",
}

TOOL_REGISTRY["git_push"] = {
    "name": "git_push",
    "description": (
        "Push commits to remote repository. "
        "USE CASES: (1) Push committed changes, (2) Sync local commits to remote, (3) Share work with team. "
        "OPTIONAL: Specify remote (default: origin) and branch (default: current). "
        "PERMISSIONS: Requires repository:write. "
        'EXAMPLE: {"repository_alias": "my-repo", "remote": "origin", "branch": "main"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"},
            "remote": {
                "type": "string",
                "description": "Remote name (default: origin)",
                "default": "origin",
            },
            "branch": {
                "type": "string",
                "description": "Branch name (default: current branch)",
            },
        },
        "required": ["repository_alias"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Operation succeeded"},
            "remote": {"type": "string", "description": "Remote name (e.g., 'origin')"},
            "branch": {"type": "string", "description": "Branch name pushed"},
            "commits_pushed": {
                "type": "integer",
                "description": "Number of commits pushed",
            },
        },
    },
    "required_permission": "repository:write",
}

TOOL_REGISTRY["git_pull"] = {
    "name": "git_pull",
    "description": (
        "Pull changes from remote repository. "
        "USE CASES: (1) Fetch and merge remote changes, (2) Update local branch, (3) Sync with team changes. "
        "OPTIONAL: Specify remote (default: origin) and branch (default: current). "
        "PERMISSIONS: Requires repository:write. "
        'EXAMPLE: {"repository_alias": "my-repo", "remote": "origin", "branch": "main"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"},
            "remote": {
                "type": "string",
                "description": "Remote name (default: origin)",
                "default": "origin",
            },
            "branch": {
                "type": "string",
                "description": "Branch name (default: current branch)",
            },
        },
        "required": ["repository_alias"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Operation succeeded"},
            "remote": {"type": "string", "description": "Remote name"},
            "branch": {"type": "string", "description": "Branch name"},
            "files_changed": {
                "type": "integer",
                "description": "Number of files changed",
            },
            "commits_pulled": {
                "type": "integer",
                "description": "Number of new commits",
            },
        },
    },
    "required_permission": "repository:write",
}

TOOL_REGISTRY["git_fetch"] = {
    "name": "git_fetch",
    "description": (
        "Fetch changes from remote repository without merging. "
        "USE CASES: (1) Download remote updates, (2) Check remote changes before merge, (3) Update remote-tracking branches. "
        "OPTIONAL: Specify remote (default: origin). "
        "PERMISSIONS: Requires repository:write. "
        'EXAMPLE: {"repository_alias": "my-repo", "remote": "origin"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"},
            "remote": {
                "type": "string",
                "description": "Remote name (default: origin)",
                "default": "origin",
            },
        },
        "required": ["repository_alias"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Operation succeeded"},
            "remote": {"type": "string", "description": "Remote name"},
            "refs_fetched": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of refs/branches fetched",
            },
        },
    },
    "required_permission": "repository:write",
}

TOOL_REGISTRY["git_reset"] = {
    "name": "git_reset",
    "description": (
        "Reset working tree to specific state (DESTRUCTIVE). "
        "USE CASES: (1) Discard commits, (2) Reset to specific commit, (3) Clean working tree. "
        "MODES: soft (keep changes staged), mixed (keep changes unstaged), hard (discard all changes). "
        "SAFETY: Requires explicit mode. Optional commit_hash and confirmation_token for destructive operations. "
        "PERMISSIONS: Requires repository:admin (destructive operation). "
        'EXAMPLE: {"repository_alias": "my-repo", "mode": "hard", "commit_hash": "abc123", "confirmation_token": "CONFIRM_RESET"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"},
            "mode": {
                "type": "string",
                "enum": ["soft", "mixed", "hard"],
                "description": "Reset mode: soft (keep staged), mixed (keep unstaged), hard (discard all)",
            },
            "commit_hash": {
                "type": "string",
                "description": "Optional commit hash to reset to (default: HEAD)",
            },
            "confirmation_token": {
                "type": "string",
                "description": "Confirmation token for destructive modes (required for hard reset)",
            },
        },
        "required": ["repository_alias", "mode"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "oneOf": [
            {
                "type": "object",
                "description": "Success response after reset performed",
                "properties": {
                    "success": {
                        "type": "boolean",
                        "description": "Operation succeeded",
                    },
                    "reset_mode": {
                        "type": "string",
                        "description": "Reset mode used (hard/mixed/soft)",
                    },
                    "target_commit": {
                        "type": "string",
                        "description": "Commit reset to",
                    },
                },
            },
            {
                "type": "object",
                "description": "Confirmation token response for destructive operations",
                "properties": {
                    "requires_confirmation": {
                        "type": "boolean",
                        "description": "Confirmation required",
                    },
                    "token": {
                        "type": "string",
                        "description": "Confirmation token to use in next call",
                    },
                },
            },
        ]
    },
    "required_permission": "repository:admin",
}

TOOL_REGISTRY["git_clean"] = {
    "name": "git_clean",
    "description": (
        "Remove untracked files from working tree (DESTRUCTIVE). "
        "USE CASES: (1) Remove build artifacts, (2) Clean untracked files, (3) Restore clean state. "
        "SAFETY: Requires confirmation_token to prevent accidental deletion. "
        "PERMISSIONS: Requires repository:admin (destructive operation). "
        'EXAMPLE: {"repository_alias": "my-repo", "confirmation_token": "CONFIRM_DELETE_UNTRACKED"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"},
            "confirmation_token": {
                "type": "string",
                "description": "Confirmation token (must be 'CONFIRM_DELETE_UNTRACKED')",
            },
        },
        "required": ["repository_alias", "confirmation_token"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "oneOf": [
            {
                "type": "object",
                "description": "Success response after clean performed",
                "properties": {
                    "success": {
                        "type": "boolean",
                        "description": "Operation succeeded",
                    },
                    "removed_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of untracked files/directories removed",
                    },
                },
            },
            {
                "type": "object",
                "description": "Confirmation token response",
                "properties": {
                    "requires_confirmation": {
                        "type": "boolean",
                        "description": "Confirmation required",
                    },
                    "token": {
                        "type": "string",
                        "description": "Confirmation token to use in next call",
                    },
                },
            },
        ]
    },
    "required_permission": "repository:admin",
}

TOOL_REGISTRY["git_merge_abort"] = {
    "name": "git_merge_abort",
    "description": (
        "Abort an in-progress merge operation. "
        "USE CASES: (1) Cancel merge with conflicts, (2) Restore pre-merge state, (3) Abandon merge attempt. "
        "REQUIREMENTS: Must have merge in progress. "
        "PERMISSIONS: Requires repository:write. "
        'EXAMPLE: {"repository_alias": "my-repo"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"}
        },
        "required": ["repository_alias"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Operation succeeded"},
            "message": {"type": "string", "description": "Confirmation message"},
        },
    },
    "required_permission": "repository:write",
}

TOOL_REGISTRY["git_checkout_file"] = {
    "name": "git_checkout_file",
    "description": (
        "Restore file to HEAD version (discard local changes). "
        "USE CASES: (1) Discard unwanted changes, (2) Restore deleted file, (3) Reset file to last commit. "
        "SAFETY: This discards local modifications to the file. "
        "PERMISSIONS: Requires repository:write. "
        'EXAMPLE: {"repository_alias": "my-repo", "file_path": "src/file.py"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"},
            "file_path": {
                "type": "string",
                "description": "File path to restore (relative to repository root)",
            },
        },
        "required": ["repository_alias", "file_path"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Operation succeeded"},
            "restored_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of files restored to HEAD state",
            },
        },
    },
    "required_permission": "repository:write",
}

TOOL_REGISTRY["git_branch_list"] = {
    "name": "git_branch_list",
    "description": (
        "List all branches in repository. "
        "USE CASES: (1) View available branches, (2) Check current branch, (3) Identify remote branches. "
        "RETURNS: Local and remote branches with current branch indicator. "
        "PERMISSIONS: Requires repository:read. "
        'EXAMPLE: {"repository_alias": "my-repo"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"}
        },
        "required": ["repository_alias"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Operation success status"},
            "current": {"type": "string", "description": "Current branch name"},
            "local": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of local branches",
            },
            "remote": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of remote branches",
            },
        },
        "required": ["success", "current", "local", "remote"],
    },
    "required_permission": "repository:read",
}

TOOL_REGISTRY["git_branch_create"] = {
    "name": "git_branch_create",
    "description": (
        "Create a new git branch. "
        "USE CASES: (1) Create feature branch, (2) Create bugfix branch, (3) Isolate work in new branch. "
        "REQUIREMENTS: Branch name must be unique. "
        "PERMISSIONS: Requires repository:write. "
        'EXAMPLE: {"repository_alias": "my-repo", "branch_name": "feature/new-feature"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"},
            "branch_name": {"type": "string", "description": "Name for new branch"},
        },
        "required": ["repository_alias", "branch_name"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Operation succeeded"},
            "created_branch": {
                "type": "string",
                "description": "Name of newly created branch",
            },
        },
    },
    "required_permission": "repository:write",
}

TOOL_REGISTRY["git_branch_switch"] = {
    "name": "git_branch_switch",
    "description": (
        "Switch to a different branch (git checkout). "
        "USE CASES: (1) Switch to existing branch, (2) Change working context, (3) Review different branch. "
        "REQUIREMENTS: Branch must exist, working tree must be clean. "
        "PERMISSIONS: Requires repository:write. "
        'EXAMPLE: {"repository_alias": "my-repo", "branch_name": "main"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"},
            "branch_name": {
                "type": "string",
                "description": "Branch name to switch to",
            },
        },
        "required": ["repository_alias", "branch_name"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Operation succeeded"},
            "from_branch": {"type": "string", "description": "Previous branch"},
            "to_branch": {"type": "string", "description": "New current branch"},
        },
    },
    "required_permission": "repository:write",
}

TOOL_REGISTRY["git_branch_delete"] = {
    "name": "git_branch_delete",
    "description": (
        "Delete a git branch (DESTRUCTIVE). "
        "USE CASES: (1) Delete merged feature branch, (2) Remove obsolete branch, (3) Clean up branches. "
        "SAFETY: Requires confirmation_token to prevent accidental deletion. Cannot delete current branch. "
        "PERMISSIONS: Requires repository:admin (destructive operation). "
        'EXAMPLE: {"repository_alias": "my-repo", "branch_name": "old-feature", "confirmation_token": "CONFIRM_DELETE_BRANCH"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"},
            "branch_name": {"type": "string", "description": "Branch name to delete"},
            "confirmation_token": {
                "type": "string",
                "description": "Confirmation token (must be 'CONFIRM_DELETE_BRANCH')",
            },
        },
        "required": ["repository_alias", "branch_name", "confirmation_token"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "oneOf": [
            {
                "type": "object",
                "description": "Success response after deletion",
                "properties": {
                    "success": {
                        "type": "boolean",
                        "description": "Operation succeeded",
                    },
                    "deleted_branch": {
                        "type": "string",
                        "description": "Name of deleted branch",
                    },
                },
            },
            {
                "type": "object",
                "description": "Confirmation token response",
                "properties": {
                    "requires_confirmation": {
                        "type": "boolean",
                        "description": "Confirmation required",
                    },
                    "token": {
                        "type": "string",
                        "description": "Confirmation token to use in next call",
                    },
                },
            },
        ]
    },
    "required_permission": "repository:admin",
}

# =============================================================================
# Re-indexing Tools (Story #628)
# =============================================================================

TOOL_REGISTRY["trigger_reindex"] = {
    "name": "trigger_reindex",
    "description": (
        "Trigger manual re-indexing for specified index types. "
        "USE CASES: (1) Rebuild corrupted indexes, (2) Add new index types (e.g., SCIP), (3) Refresh indexes after bulk code changes. "
        "INDEX TYPES: semantic (embedding vectors), fts (full-text search), temporal (git history), scip (code intelligence). "
        "CLEAR FLAG: When clear=true, completely rebuilds from scratch (slower but thorough). When false, performs incremental update. "
        "PERMISSIONS: Requires repository:write. "
        'EXAMPLE: {"repository_alias": "my-repo", "index_types": ["semantic", "fts"], "clear": false}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"},
            "index_types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["semantic", "fts", "temporal", "scip"],
                },
                "description": "Array of index types to rebuild: semantic (embeddings), fts (full-text), temporal (git history), scip (call graphs)",
            },
            "clear": {
                "type": "boolean",
                "description": "Rebuild from scratch (true) or incremental update (false). Default: false",
                "default": False,
            },
        },
        "required": ["repository_alias", "index_types"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Operation success status"},
            "job_id": {
                "type": "string",
                "description": "Background job ID for tracking",
            },
            "status": {"type": "string", "description": "Initial job status"},
            "index_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Index types being rebuilt",
            },
            "started_at": {
                "type": "string",
                "description": "Job start time (ISO 8601)",
            },
            "estimated_duration_minutes": {
                "type": "integer",
                "description": "Estimated completion time in minutes",
            },
        },
        "required": ["success"],
    },
    "required_permission": "repository:write",
}

TOOL_REGISTRY["get_index_status"] = {
    "name": "get_index_status",
    "description": (
        "Query current index status for all index types in a repository. "
        "USE CASES: (1) Check if indexes exist before querying, (2) Verify index freshness, (3) Monitor index health. "
        "RETURNS: Status for each index type (semantic, fts, temporal, scip) including: existence, file count, last updated timestamp, size. "
        "PERMISSIONS: Requires repository:read. "
        'EXAMPLE: {"repository_alias": "my-repo"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository_alias": {"type": "string", "description": "Repository alias"}
        },
        "required": ["repository_alias"],
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Operation success status"},
            "repository_alias": {"type": "string", "description": "Repository alias"},
            "semantic": {
                "type": "object",
                "description": "Semantic index status",
                "properties": {
                    "exists": {"type": "boolean"},
                    "last_updated": {"type": "string"},
                    "document_count": {"type": "integer"},
                    "size_bytes": {"type": "integer"},
                },
            },
            "fts": {
                "type": "object",
                "description": "Full-text search index status",
                "properties": {
                    "exists": {"type": "boolean"},
                    "last_updated": {"type": "string"},
                    "document_count": {"type": "integer"},
                    "size_bytes": {"type": "integer"},
                },
            },
            "temporal": {
                "type": "object",
                "description": "Temporal (git history) index status",
                "properties": {
                    "exists": {"type": "boolean"},
                    "last_updated": {"type": "string"},
                    "document_count": {"type": "integer"},
                    "size_bytes": {"type": "integer"},
                },
            },
            "scip": {
                "type": "object",
                "description": "SCIP (call graph) index status",
                "properties": {
                    "exists": {"type": "boolean"},
                    "last_updated": {"type": "string"},
                    "document_count": {"type": "integer"},
                    "size_bytes": {"type": "integer"},
                },
            },
        },
        "required": [
            "success",
            "repository_alias",
            "semantic",
            "fts",
            "temporal",
            "scip",
        ],
    },
    "required_permission": "repository:read",
}

# =============================================================================
# ADMIN LOG MANAGEMENT TOOLS
# =============================================================================

TOOL_REGISTRY["admin_logs_query"] = {
    "name": "admin_logs_query",
    "description": (
        "Query operational logs from SQLite database with pagination and filtering. "
        "USE CASES: (1) View recent server logs, (2) Search for specific errors/events, (3) Trace requests by correlation_id, (4) Filter by log level. "
        "RETURNS: Paginated array of log entries with timestamp, level, source, message, correlation_id, user_id, request_path. "
        "PERMISSIONS: Requires admin role (admin only). "
        'EXAMPLE: {"page": 1, "page_size": 50, "search": "SSO", "level": "ERROR"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "page": {
                "type": "integer",
                "description": "Page number (1-indexed, default 1)",
            },
            "page_size": {
                "type": "integer",
                "description": "Number of logs per page (default 50, max 1000)",
            },
            "sort_order": {
                "type": "string",
                "description": "Sort order: 'asc' (oldest first) or 'desc' (newest first, default)",
                "enum": ["asc", "desc"],
            },
            "search": {
                "type": "string",
                "description": "Text search across message and correlation_id (case-insensitive)",
            },
            "level": {
                "type": "string",
                "description": "Filter by log level(s), comma-separated (e.g., 'ERROR' or 'ERROR,WARNING')",
            },
            "correlation_id": {
                "type": "string",
                "description": "Filter by exact correlation ID",
            },
        },
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Operation success status"},
            "logs": {
                "type": "array",
                "description": "Array of log entries",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "timestamp": {"type": "string"},
                        "level": {"type": "string"},
                        "source": {"type": "string"},
                        "message": {"type": "string"},
                        "correlation_id": {"type": ["string", "null"]},
                        "user_id": {"type": ["string", "null"]},
                        "request_path": {"type": ["string", "null"]},
                    },
                },
            },
            "pagination": {
                "type": "object",
                "description": "Pagination metadata",
                "properties": {
                    "page": {"type": "integer"},
                    "page_size": {"type": "integer"},
                    "total": {"type": "integer"},
                    "total_pages": {"type": "integer"},
                },
            },
        },
        "required": ["success", "logs", "pagination"],
    },
    "required_permission": "manage_users",  # admin only
}

TOOL_REGISTRY["admin_logs_export"] = {
    "name": "admin_logs_export",
    "description": (
        "Export operational logs in JSON or CSV format for offline analysis or external tool import. "
        "USE CASES: (1) Download filtered logs for support tickets, (2) Import into Excel/log analysis tools, (3) Share error logs with team, (4) Archive logs. "
        "RETURNS: ALL logs matching filter criteria (no pagination) formatted as JSON or CSV. Includes export metadata with count and applied filters. "
        "PERMISSIONS: Requires admin role (admin only). "
        'EXAMPLE: {"format": "json", "search": "OAuth", "level": "ERROR"}'
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "description": "Export format: 'json' (default) or 'csv'",
                "enum": ["json", "csv"],
            },
            "search": {
                "type": "string",
                "description": "Text search across message and correlation_id (case-insensitive)",
            },
            "level": {
                "type": "string",
                "description": "Filter by log level(s), comma-separated (e.g., 'ERROR' or 'ERROR,WARNING')",
            },
            "correlation_id": {
                "type": "string",
                "description": "Filter by exact correlation ID",
            },
        },
        "additionalProperties": False,
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Operation success status"},
            "format": {
                "type": "string",
                "description": "Export format used (json or csv)",
            },
            "count": {
                "type": "integer",
                "description": "Total number of logs exported",
            },
            "data": {
                "type": "string",
                "description": "Exported log data as JSON string (with metadata) or CSV string (with BOM)",
            },
            "filters": {
                "type": "object",
                "description": "Filters applied to export",
                "properties": {
                    "search": {"type": ["string", "null"]},
                    "level": {"type": ["string", "null"]},
                    "correlation_id": {"type": ["string", "null"]},
                },
            },
        },
        "required": ["success", "format", "count", "data", "filters"],
    },
    "required_permission": "manage_users",  # admin only
}

# =============================================================================
# GITHUB ACTIONS MONITORING TOOLS (Story #633)
# =============================================================================

TOOL_REGISTRY["gh_actions_list_runs"] = {
    "name": "gh_actions_list_runs",
    "description": (
        "TL;DR: List recent GitHub Actions workflow runs with optional filtering by branch and status. "
        "QUICK START: gh_actions_list_runs(repository='owner/repo') returns recent runs. "
        "USE CASES: (1) Monitor CI/CD status, (2) Find failed workflows, (3) Check workflow history. "
        "FILTERS: branch='main' (filter by branch), status='failure' (filter by conclusion). "
        "RETURNS: List of workflow runs with id, name, status, conclusion, branch, created_at. "
        "PERMISSIONS: Requires repository:read. "
        "AUTHENTICATION: Uses stored GitHub token from token storage. "
        "EXAMPLE: gh_actions_list_runs(repository='owner/repo', branch='main', status='failure')"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository": {
                "type": "string",
                "description": "Repository in 'owner/repo' format",
            },
            "branch": {
                "type": "string",
                "description": "Optional branch filter",
            },
            "status": {
                "type": "string",
                "description": "Optional status filter (e.g., 'failure', 'success')",
            },
        },
        "required": ["repository"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "runs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                        "status": {"type": "string"},
                        "conclusion": {"type": "string"},
                        "branch": {"type": "string"},
                        "created_at": {"type": "string"},
                    },
                },
            },
        },
    },
    "required_permission": "repository:read",
}

TOOL_REGISTRY["gh_actions_get_run"] = {
    "name": "gh_actions_get_run",
    "description": (
        "TL;DR: Get detailed information for a specific GitHub Actions workflow run. "
        "QUICK START: gh_actions_get_run(repository='owner/repo', run_id=12345) returns detailed run info. "
        "USE CASES: (1) Investigate specific workflow run, (2) Get timing information, (3) Find jobs URL. "
        "RETURNS: Detailed run information including jobs_url, updated_at, run_started_at. "
        "PERMISSIONS: Requires repository:read. "
        "EXAMPLE: gh_actions_get_run(repository='owner/repo', run_id=12345)"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository": {
                "type": "string",
                "description": "Repository in 'owner/repo' format",
            },
            "run_id": {
                "type": "integer",
                "description": "Workflow run ID",
            },
        },
        "required": ["repository", "run_id"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "run": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "status": {"type": "string"},
                    "conclusion": {"type": "string"},
                    "branch": {"type": "string"},
                    "created_at": {"type": "string"},
                    "updated_at": {"type": "string"},
                    "html_url": {"type": "string"},
                    "jobs_url": {"type": "string"},
                    "run_started_at": {"type": "string"},
                },
            },
        },
    },
    "required_permission": "repository:read",
}

TOOL_REGISTRY["gh_actions_search_logs"] = {
    "name": "gh_actions_search_logs",
    "description": (
        "TL;DR: Search workflow run logs for a pattern using ripgrep-style matching. "
        "QUICK START: gh_actions_search_logs(repository='owner/repo', run_id=12345, pattern='error') finds errors in logs. "
        "USE CASES: (1) Find error messages in logs, (2) Search for specific patterns, (3) Debug workflow failures. "
        "RETURNS: List of matching log lines with job_id, job_name, line, line_number. "
        "PERMISSIONS: Requires repository:read. "
        "EXAMPLE: gh_actions_search_logs(repository='owner/repo', run_id=12345, pattern='ERROR|FAIL')"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository": {
                "type": "string",
                "description": "Repository in 'owner/repo' format",
            },
            "run_id": {
                "type": "integer",
                "description": "Workflow run ID",
            },
            "pattern": {
                "type": "string",
                "description": "Pattern to search for (case-insensitive regex)",
            },
        },
        "required": ["repository", "run_id", "pattern"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "integer"},
                        "job_name": {"type": "string"},
                        "line": {"type": "string"},
                        "line_number": {"type": "integer"},
                    },
                },
            },
        },
    },
    "required_permission": "repository:read",
}

TOOL_REGISTRY["gh_actions_get_job_logs"] = {
    "name": "gh_actions_get_job_logs",
    "description": (
        "TL;DR: Get full log output for a specific job. "
        "QUICK START: gh_actions_get_job_logs(repository='owner/repo', job_id=67890) returns complete logs. "
        "USE CASES: (1) Read full job logs, (2) Debug specific job failure, (3) Analyze job output. "
        "RETURNS: Full log output as text. "
        "PERMISSIONS: Requires repository:read. "
        "EXAMPLE: gh_actions_get_job_logs(repository='owner/repo', job_id=67890)"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository": {
                "type": "string",
                "description": "Repository in 'owner/repo' format",
            },
            "job_id": {
                "type": "integer",
                "description": "Job ID",
            },
        },
        "required": ["repository", "job_id"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "logs": {"type": "string", "description": "Full log output"},
        },
    },
    "required_permission": "repository:read",
}

TOOL_REGISTRY["gh_actions_retry_run"] = {
    "name": "gh_actions_retry_run",
    "description": (
        "TL;DR: Retry a failed GitHub Actions workflow run. "
        "QUICK START: gh_actions_retry_run(repository='owner/repo', run_id=12345) triggers retry. "
        "USE CASES: (1) Retry flaky test failures, (2) Re-run after fixing issue, (3) Resume failed deployment. "
        "RETURNS: Confirmation with run_id. "
        "PERMISSIONS: Requires repository:write (GitHub Actions write access). "
        "EXAMPLE: gh_actions_retry_run(repository='owner/repo', run_id=12345)"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository": {
                "type": "string",
                "description": "Repository in 'owner/repo' format",
            },
            "run_id": {
                "type": "integer",
                "description": "Workflow run ID to retry",
            },
        },
        "required": ["repository", "run_id"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "run_id": {"type": "integer"},
        },
    },
    "required_permission": "repository:write",
}

TOOL_REGISTRY["gh_actions_cancel_run"] = {
    "name": "gh_actions_cancel_run",
    "description": (
        "TL;DR: Cancel a running GitHub Actions workflow. "
        "QUICK START: gh_actions_cancel_run(repository='owner/repo', run_id=12345) cancels workflow. "
        "USE CASES: (1) Stop unnecessary workflow execution, (2) Cancel failed deployment, (3) Abort long-running jobs. "
        "RETURNS: Confirmation with run_id. "
        "PERMISSIONS: Requires repository:write (GitHub Actions write access). "
        "EXAMPLE: gh_actions_cancel_run(repository='owner/repo', run_id=12345)"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repository": {
                "type": "string",
                "description": "Repository in 'owner/repo' format",
            },
            "run_id": {
                "type": "integer",
                "description": "Workflow run ID to cancel",
            },
        },
        "required": ["repository", "run_id"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "run_id": {"type": "integer"},
        },
    },
    "required_permission": "repository:write",
}

# ==============================================================================
# GitLab CI Monitoring Tools (Story #634)
# ==============================================================================

TOOL_REGISTRY["gitlab_ci_list_pipelines"] = {
    "name": "gitlab_ci_list_pipelines",
    "description": (
        "TL;DR: List recent GitLab CI pipelines with optional filtering by ref and status. "
        "QUICK START: gitlab_ci_list_pipelines(project_id='namespace/project') returns recent pipelines. "
        "USE CASES: (1) Monitor CI/CD status, (2) Find failed pipelines, (3) Check pipeline history. "
        "FILTERS: ref='main' (filter by branch/tag), status='failed' (filter by status). "
        "RETURNS: List of pipelines with id, status, ref, created_at, web_url. "
        "PERMISSIONS: Requires repository:read. "
        "AUTHENTICATION: Uses stored GitLab token from token storage. "
        "SELF-HOSTED: Supports custom GitLab instances via base_url parameter. "
        "EXAMPLE: gitlab_ci_list_pipelines(project_id='namespace/project', ref='main', status='failed')"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "Project in 'namespace/project' format or numeric ID",
            },
            "ref": {
                "type": "string",
                "description": "Optional branch or tag filter",
            },
            "status": {
                "type": "string",
                "description": "Optional status filter (e.g., 'failed', 'success', 'running')",
            },
            "base_url": {
                "type": "string",
                "description": "Optional GitLab instance base URL (default: https://gitlab.com)",
            },
        },
        "required": ["project_id"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "pipelines": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "status": {"type": "string"},
                        "ref": {"type": "string"},
                        "created_at": {"type": "string"},
                        "web_url": {"type": "string"},
                    },
                },
            },
        },
    },
    "required_permission": "repository:read",
}

TOOL_REGISTRY["gitlab_ci_get_pipeline"] = {
    "name": "gitlab_ci_get_pipeline",
    "description": (
        "TL;DR: Get detailed information for a specific GitLab CI pipeline. "
        "QUICK START: gitlab_ci_get_pipeline(project_id='namespace/project', pipeline_id=12345) returns detailed pipeline info. "
        "USE CASES: (1) Investigate specific pipeline run, (2) Get timing information, (3) View jobs and stages. "
        "RETURNS: Detailed pipeline information including jobs, duration, coverage, commit SHA. "
        "PERMISSIONS: Requires repository:read. "
        "EXAMPLE: gitlab_ci_get_pipeline(project_id='namespace/project', pipeline_id=12345)"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "Project in 'namespace/project' format or numeric ID",
            },
            "pipeline_id": {
                "type": "integer",
                "description": "Pipeline ID",
            },
            "base_url": {
                "type": "string",
                "description": "Optional GitLab instance base URL (default: https://gitlab.com)",
            },
        },
        "required": ["project_id", "pipeline_id"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "pipeline": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "status": {"type": "string"},
                    "ref": {"type": "string"},
                    "sha": {"type": "string"},
                    "created_at": {"type": "string"},
                    "updated_at": {"type": "string"},
                    "web_url": {"type": "string"},
                    "duration": {"type": "integer"},
                    "coverage": {"type": "string"},
                    "jobs": {"type": "array"},
                },
            },
        },
    },
    "required_permission": "repository:read",
}

TOOL_REGISTRY["gitlab_ci_search_logs"] = {
    "name": "gitlab_ci_search_logs",
    "description": (
        "TL;DR: Search GitLab CI pipeline logs for a pattern using regex matching. "
        "QUICK START: gitlab_ci_search_logs(project_id='namespace/project', pipeline_id=12345, pattern='error') finds errors in logs. "
        "USE CASES: (1) Find error messages in logs, (2) Search for specific patterns, (3) Debug pipeline failures. "
        "RETURNS: List of matching log lines with job_id, job_name, stage, line, line_number. "
        "PERMISSIONS: Requires repository:read. "
        "EXAMPLE: gitlab_ci_search_logs(project_id='namespace/project', pipeline_id=12345, pattern='ERROR|FAIL')"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "Project in 'namespace/project' format or numeric ID",
            },
            "pipeline_id": {
                "type": "integer",
                "description": "Pipeline ID",
            },
            "pattern": {
                "type": "string",
                "description": "Regex pattern to search for (case-insensitive)",
            },
            "base_url": {
                "type": "string",
                "description": "Optional GitLab instance base URL (default: https://gitlab.com)",
            },
        },
        "required": ["project_id", "pipeline_id", "pattern"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "integer"},
                        "job_name": {"type": "string"},
                        "stage": {"type": "string"},
                        "line": {"type": "string"},
                        "line_number": {"type": "integer"},
                    },
                },
            },
        },
    },
    "required_permission": "repository:read",
}

TOOL_REGISTRY["gitlab_ci_get_job_logs"] = {
    "name": "gitlab_ci_get_job_logs",
    "description": (
        "TL;DR: Get full log output for a specific GitLab CI job. "
        "QUICK START: gitlab_ci_get_job_logs(project_id='namespace/project', job_id=67890) returns complete logs. "
        "USE CASES: (1) Read full job logs, (2) Debug specific job failure, (3) Analyze job output. "
        "RETURNS: Full log output as text. "
        "PERMISSIONS: Requires repository:read. "
        "EXAMPLE: gitlab_ci_get_job_logs(project_id='namespace/project', job_id=67890)"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "Project in 'namespace/project' format or numeric ID",
            },
            "job_id": {
                "type": "integer",
                "description": "Job ID",
            },
            "base_url": {
                "type": "string",
                "description": "Optional GitLab instance base URL (default: https://gitlab.com)",
            },
        },
        "required": ["project_id", "job_id"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "logs": {"type": "string", "description": "Full log output"},
        },
    },
    "required_permission": "repository:read",
}

TOOL_REGISTRY["gitlab_ci_retry_pipeline"] = {
    "name": "gitlab_ci_retry_pipeline",
    "description": (
        "TL;DR: Retry a failed GitLab CI pipeline. "
        "QUICK START: gitlab_ci_retry_pipeline(project_id='namespace/project', pipeline_id=12345) triggers retry. "
        "USE CASES: (1) Retry flaky test failures, (2) Re-run after fixing issue, (3) Resume failed deployment. "
        "RETURNS: Confirmation with pipeline_id. "
        "PERMISSIONS: Requires repository:write (GitLab CI write access). "
        "EXAMPLE: gitlab_ci_retry_pipeline(project_id='namespace/project', pipeline_id=12345)"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "Project in 'namespace/project' format or numeric ID",
            },
            "pipeline_id": {
                "type": "integer",
                "description": "Pipeline ID to retry",
            },
            "base_url": {
                "type": "string",
                "description": "Optional GitLab instance base URL (default: https://gitlab.com)",
            },
        },
        "required": ["project_id", "pipeline_id"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "pipeline_id": {"type": "integer"},
        },
    },
    "required_permission": "repository:write",
}

TOOL_REGISTRY["gitlab_ci_cancel_pipeline"] = {
    "name": "gitlab_ci_cancel_pipeline",
    "description": (
        "TL;DR: Cancel a running GitLab CI pipeline. "
        "QUICK START: gitlab_ci_cancel_pipeline(project_id='namespace/project', pipeline_id=12345) cancels pipeline. "
        "USE CASES: (1) Stop unnecessary pipeline execution, (2) Cancel failed deployment, (3) Abort long-running jobs. "
        "RETURNS: Confirmation with pipeline_id. "
        "PERMISSIONS: Requires repository:write (GitLab CI write access). "
        "EXAMPLE: gitlab_ci_cancel_pipeline(project_id='namespace/project', pipeline_id=12345)"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "Project in 'namespace/project' format or numeric ID",
            },
            "pipeline_id": {
                "type": "integer",
                "description": "Pipeline ID to cancel",
            },
            "base_url": {
                "type": "string",
                "description": "Optional GitLab instance base URL (default: https://gitlab.com)",
            },
        },
        "required": ["project_id", "pipeline_id"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "pipeline_id": {"type": "integer"},
        },
    },
    "required_permission": "repository:write",
}

# =============================================================================
# GITHUB ACTIONS TOOLS
# =============================================================================

TOOL_REGISTRY["github_actions_list_runs"] = {
    "name": "github_actions_list_runs",
    "description": (
        "TL;DR: List GitHub Actions workflow runs with optional filtering by workflow, status, and branch. "
        "QUICK START: github_actions_list_runs(owner='user', repo='project') returns recent workflow runs. "
        "USE CASES: (1) Monitor CI/CD status, (2) Find failed workflow runs, (3) Check workflow run history. "
        "FILTERS: workflow_id='ci.yml' (filter by workflow), status='completed' (filter by status), branch='main' (filter by branch). "
        "RETURNS: List of workflow runs with id, name, status, conclusion, branch, created_at. "
        "PERMISSIONS: Requires repository:read. "
        "AUTHENTICATION: Uses stored GitHub token from token storage. "
        "EXAMPLE: github_actions_list_runs(owner='user', repo='project', status='failure', branch='main', limit=20)"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "owner": {
                "type": "string",
                "description": "Repository owner (user or organization)",
            },
            "repo": {
                "type": "string",
                "description": "Repository name",
            },
            "workflow_id": {
                "type": "string",
                "description": "Optional workflow ID or filename (e.g., 'ci.yml')",
            },
            "status": {
                "type": "string",
                "enum": ["queued", "in_progress", "completed"],
                "description": "Optional status filter",
            },
            "branch": {
                "type": "string",
                "description": "Optional branch name filter",
            },
            "limit": {
                "type": "integer",
                "default": 20,
                "description": "Maximum number of runs to return (default: 20)",
            },
        },
        "required": ["owner", "repo"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "runs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                        "status": {"type": "string"},
                        "conclusion": {"type": "string"},
                        "branch": {"type": "string"},
                        "created_at": {"type": "string"},
                    },
                },
            },
        },
    },
    "required_permission": "repository:read",
}

TOOL_REGISTRY["github_actions_get_run"] = {
    "name": "github_actions_get_run",
    "description": (
        "TL;DR: Get detailed information for a specific GitHub Actions workflow run. "
        "QUICK START: github_actions_get_run(owner='user', repo='project', run_id=12345) returns detailed run info. "
        "USE CASES: (1) Investigate specific workflow run, (2) Get timing and job information, (3) View run artifacts. "
        "RETURNS: Detailed run information including jobs with steps, duration, commit SHA, artifacts, html_url. "
        "PERMISSIONS: Requires repository:read. "
        "EXAMPLE: github_actions_get_run(owner='user', repo='project', run_id=12345)"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "owner": {
                "type": "string",
                "description": "Repository owner",
            },
            "repo": {
                "type": "string",
                "description": "Repository name",
            },
            "run_id": {
                "type": "integer",
                "description": "Workflow run ID",
            },
        },
        "required": ["owner", "repo", "run_id"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "run": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "status": {"type": "string"},
                    "conclusion": {"type": "string"},
                    "branch": {"type": "string"},
                    "commit_sha": {"type": "string"},
                    "duration_seconds": {"type": "integer"},
                    "created_at": {"type": "string"},
                    "updated_at": {"type": "string"},
                    "html_url": {"type": "string"},
                    "jobs": {"type": "array"},
                    "artifacts": {"type": "array"},
                },
            },
        },
    },
    "required_permission": "repository:read",
}

TOOL_REGISTRY["github_actions_search_logs"] = {
    "name": "github_actions_search_logs",
    "description": (
        "TL;DR: Search GitHub Actions workflow run logs for a pattern using regex matching. "
        "QUICK START: github_actions_search_logs(owner='user', repo='project', run_id=12345, query='error') finds errors in logs. "
        "USE CASES: (1) Find error messages in logs, (2) Search for specific patterns, (3) Debug workflow failures. "
        "RETURNS: List of matching log lines with job_id, job_name, line, line_number. "
        "PERMISSIONS: Requires repository:read. "
        "EXAMPLE: github_actions_search_logs(owner='user', repo='project', run_id=12345, query='ERROR|FAIL')"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "owner": {
                "type": "string",
                "description": "Repository owner",
            },
            "repo": {
                "type": "string",
                "description": "Repository name",
            },
            "run_id": {
                "type": "integer",
                "description": "Workflow run ID",
            },
            "query": {
                "type": "string",
                "description": "Search query string (case-insensitive regex)",
            },
        },
        "required": ["owner", "repo", "run_id", "query"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "integer"},
                        "job_name": {"type": "string"},
                        "line": {"type": "string"},
                        "line_number": {"type": "integer"},
                    },
                },
            },
        },
    },
    "required_permission": "repository:read",
}

TOOL_REGISTRY["github_actions_get_job_logs"] = {
    "name": "github_actions_get_job_logs",
    "description": (
        "TL;DR: Get full log output for a specific GitHub Actions job. "
        "QUICK START: github_actions_get_job_logs(owner='user', repo='project', job_id=67890) returns complete logs. "
        "USE CASES: (1) Read full job logs, (2) Debug specific job failure, (3) Analyze job output. "
        "RETURNS: Full log output as text. "
        "PERMISSIONS: Requires repository:read. "
        "EXAMPLE: github_actions_get_job_logs(owner='user', repo='project', job_id=67890)"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "owner": {
                "type": "string",
                "description": "Repository owner",
            },
            "repo": {
                "type": "string",
                "description": "Repository name",
            },
            "job_id": {
                "type": "integer",
                "description": "Job ID",
            },
        },
        "required": ["owner", "repo", "job_id"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "logs": {"type": "string", "description": "Full log output"},
        },
    },
    "required_permission": "repository:read",
}

TOOL_REGISTRY["github_actions_retry_run"] = {
    "name": "github_actions_retry_run",
    "description": (
        "TL;DR: Retry a failed GitHub Actions workflow run. "
        "QUICK START: github_actions_retry_run(owner='user', repo='project', run_id=12345) triggers retry. "
        "USE CASES: (1) Retry flaky test failures, (2) Re-run after fixing issue, (3) Resume failed deployment. "
        "RETURNS: Confirmation with run_id and success status. "
        "PERMISSIONS: Requires repository:write (GitHub Actions write access). "
        "EXAMPLE: github_actions_retry_run(owner='user', repo='project', run_id=12345)"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "owner": {
                "type": "string",
                "description": "Repository owner",
            },
            "repo": {
                "type": "string",
                "description": "Repository name",
            },
            "run_id": {
                "type": "integer",
                "description": "Workflow run ID to retry",
            },
        },
        "required": ["owner", "repo", "run_id"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "run_id": {"type": "integer"},
        },
    },
    "required_permission": "repository:write",
}

TOOL_REGISTRY["github_actions_cancel_run"] = {
    "name": "github_actions_cancel_run",
    "description": (
        "TL;DR: Cancel a running GitHub Actions workflow run. "
        "QUICK START: github_actions_cancel_run(owner='user', repo='project', run_id=12345) cancels workflow run. "
        "USE CASES: (1) Stop unnecessary workflow execution, (2) Cancel failed deployment, (3) Abort long-running jobs. "
        "RETURNS: Confirmation with run_id and success status. "
        "PERMISSIONS: Requires repository:write (GitHub Actions write access). "
        "EXAMPLE: github_actions_cancel_run(owner='user', repo='project', run_id=12345)"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "owner": {
                "type": "string",
                "description": "Repository owner",
            },
            "repo": {
                "type": "string",
                "description": "Repository name",
            },
            "run_id": {
                "type": "integer",
                "description": "Workflow run ID to cancel",
            },
        },
        "required": ["owner", "repo", "run_id"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "run_id": {"type": "integer"},
        },
    },
    "required_permission": "repository:write",
}

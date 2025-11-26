# CIDX MCP Bridge API Reference

Last Updated: 2025-11-26

## Overview

The CIDX MCP Bridge exposes 22 tools via the Model Context Protocol (MCP). All tools follow JSON-RPC 2.0 specification.

Tool registry: src/code_indexer/server/mcp/tools.py:7-503

## Tool Organization

Tools are organized into 5 categories:

1. Search Tools (2 tools): search_code, discover_repositories
2. Repository Management (6 tools): list_repositories, activate_repository, deactivate_repository, get_repository_status, sync_repository, switch_branch
3. Files and Health (5 tools): list_files, get_file_content, browse_directory, get_branches, check_health
4. Administration (5 tools): add_golden_repo, remove_golden_repo, refresh_golden_repo, list_users, create_user
5. Analytics (4 tools): get_repository_statistics, get_job_statistics, get_all_repositories_status, manage_composite_repository

## Request Format

All requests follow JSON-RPC 2.0 format:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "TOOL_NAME",
    "arguments": {
      "param1": "value1",
      "param2": "value2"
    }
  },
  "id": 1
}
```

Required fields:
- `jsonrpc`: Must be "2.0"
- `method`: Must be "tools/call" for tool invocation or "tools/list" for tool discovery
- `id`: Request identifier (integer or string)

Optional fields:
- `params`: Tool parameters (required for tools/call)

## Response Format

Success response:

```json
{
  "jsonrpc": "2.0",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Result data here"
      }
    ]
  },
  "id": 1
}
```

Error response:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32000,
    "message": "Error description",
    "data": {
      "detail": "Additional error information"
    }
  },
  "id": 1
}
```

## Error Codes

JSON-RPC standard error codes (from src/code_indexer/mcpb/protocol.py):

- `-32700`: Parse error (invalid JSON)
- `-32600`: Invalid request (missing required fields)
- `-32601`: Method not found
- `-32602`: Invalid params
- `-32603`: Internal error
- `-32000`: Server error (CIDX server errors, authentication failures, timeouts)

## Search Tools

### search_code

Search code using semantic search, full-text search (FTS), or hybrid mode.

Tool definition: src/code_indexer/server/mcp/tools.py:9-147

Required permission: `query_repos`

Parameters (25 total):

#### Core Parameters

**query_text** (string, required)
- Search query text
- Examples: "authentication", "database connection", "test_.*"

**repository_alias** (string, optional)
- Repository alias to search
- If not specified, searches all activated repositories
- Get available aliases with `list_repositories` tool

**limit** (integer, optional)
- Maximum number of results
- Default: 10
- Range: 1-100
- Important: Start with limit=5 to conserve context tokens. Each result consumes tokens proportional to code snippet size. Only increase if initial results insufficient.

**min_score** (number, optional)
- Minimum similarity score for results
- Default: 0.5
- Range: 0.0-1.0
- Higher values return fewer but more relevant results

**search_mode** (string, optional)
- Search mode: "semantic", "fts", "hybrid"
- Default: "semantic"
- "semantic": Vector similarity search (query meaning)
- "fts": Full-text search (exact token matching)
- "hybrid": Both semantic and FTS combined

#### Filtering Parameters

**language** (string, optional)
- Filter by programming language
- Supported languages: c, cpp, csharp, dart, go, java, javascript, kotlin, php, python, ruby, rust, scala, swift, typescript, css, html, vue, markdown, xml, json, yaml, bash, shell
- Can use friendly names (python) or extensions (py, js, ts)
- Example: "python", "py", "javascript", "js"

**exclude_language** (string, optional)
- Exclude files of specified language
- Use same language names as `language` parameter
- Example: "javascript" (exclude all JS files)

**path_filter** (string, optional)
- Filter by file path pattern using glob syntax
- Supports wildcards: `*`, `**`, `?`, `[seq]`
- Examples:
  - `*/tests/*`: Test files
  - `*/src/**/*.py`: Python files in src directory
  - `**/models/*.py`: Python files in any models directory

**exclude_path** (string, optional)
- Exclude files matching path pattern
- Supports glob patterns
- Examples:
  - `*/tests/*`: Exclude all test files
  - `*.min.js`: Exclude minified JavaScript
  - `**/vendor/**`: Exclude vendor directories

**file_extensions** (array of strings, optional)
- Filter by file extensions
- Alternative to `language` filter for exact extension matching
- Example: `[".py", ".js"]`, `[".md", ".rst"]`

**accuracy** (string, optional)
- Search accuracy profile
- Options: "fast", "balanced", "high"
- Default: "balanced"
- "fast": Lower accuracy, faster response
- "balanced": Good tradeoff between accuracy and speed
- "high": Higher accuracy, slower response
- Affects embedding search precision

#### Temporal Query Parameters

Temporal queries require temporal index built with `cidx index --index-commits`.

**time_range** (string, optional)
- Time range filter for temporal queries
- Format: `YYYY-MM-DD..YYYY-MM-DD`
- Example: `2024-01-01..2024-12-31`
- Returns only code that existed during this period
- Requires temporal index

**time_range_all** (boolean, optional)
- Query across all git history without time range limit
- Default: false
- Requires temporal index
- Equivalent to querying from first commit to HEAD

**at_commit** (string, optional)
- Query code at specific commit hash or ref
- Examples: `abc123ef`, `HEAD~5`, `v1.0.0`
- Returns code state as it existed at that commit
- Requires temporal index

**include_removed** (boolean, optional)
- Include files removed from current HEAD
- Default: false
- Only applicable with temporal queries
- Removed files have `is_removed` flag in `temporal_context`

**show_evolution** (boolean, optional)
- Include code evolution timeline with commit history and diffs
- Default: false
- Shows how code changed over time
- Requires temporal index
- Increases response size significantly

**evolution_limit** (integer, optional)
- Limit number of evolution entries per result
- No maximum limit (user-controlled)
- Minimum: 1
- Only applicable when `show_evolution=true`
- Higher values provide more complete history but increase response size

#### FTS-Specific Parameters

FTS parameters only applicable when `search_mode` is "fts" or "hybrid".

**case_sensitive** (boolean, optional)
- Enable case-sensitive FTS matching
- Default: false
- When true, query matches must have exact case
- Example: "User" won't match "user"

**fuzzy** (boolean, optional)
- Enable fuzzy matching with edit distance tolerance
- Default: false
- Allows typo tolerance
- Incompatible with `regex=true`
- Use `edit_distance` parameter to control tolerance level

**edit_distance** (integer, optional)
- Fuzzy match tolerance level
- Default: 0 (exact match)
- Range: 0-3
- 0: Exact match only
- 1: 1 typo allowed
- 2: 2 typos allowed
- 3: 3 typos allowed
- Higher values allow more typos but may reduce precision

**snippet_lines** (integer, optional)
- Number of context lines to show around FTS matches
- Default: 5
- Range: 0-50
- 0: List matching files only (no context)
- 1-50: Show N lines of context around each match
- Higher values provide more context but increase response size

**regex** (boolean, optional)
- Interpret query as regex pattern for token-based matching
- Default: false
- Incompatible with `fuzzy=true`
- Token-based matching (whitespace removed during indexing)
- Works: `def`, `login.*`, `test_.*`
- Doesn't work: `def\s+\w+` (whitespace patterns)
- 10-50x faster than grep for large codebases

#### Temporal Filtering Parameters

Temporal filtering parameters only applicable when `time_range` is specified.

**diff_type** (string, optional)
- Filter temporal results by diff type
- Options: added, modified, deleted, renamed, binary
- Can be comma-separated for multiple types
- Example: `added,modified`

**author** (string, optional)
- Filter temporal results by commit author
- Can be name or email
- Example: `john.doe@example.com`, `John Doe`

**chunk_type** (string, optional)
- Filter temporal results by chunk type
- Options: "commit_message", "commit_diff"
- "commit_message": Search commit messages
- "commit_diff": Search code diffs

#### Example Requests

Basic semantic search:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "authentication",
      "limit": 5
    }
  },
  "id": 1
}
```

Language-filtered search:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "database connection",
      "language": "python",
      "exclude_path": "*/tests/*",
      "limit": 10
    }
  },
  "id": 2
}
```

Full-text search with regex:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "test_.*auth",
      "search_mode": "fts",
      "regex": true,
      "case_sensitive": true,
      "limit": 20
    }
  },
  "id": 3
}
```

Temporal search (git history):

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "JWT authentication",
      "time_range": "2024-01-01..2024-12-31",
      "show_evolution": true,
      "evolution_limit": 10,
      "author": "developer@example.com"
    }
  },
  "id": 4
}
```

Hybrid search with fuzzy matching:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "authentcation",
      "search_mode": "hybrid",
      "fuzzy": true,
      "edit_distance": 2,
      "snippet_lines": 10,
      "limit": 5
    }
  },
  "id": 5
}
```

High-accuracy search with filters:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "error handling strategy",
      "accuracy": "high",
      "min_score": 0.8,
      "language": "python",
      "path_filter": "*/src/**/*.py",
      "limit": 5
    }
  },
  "id": 6
}
```

### discover_repositories

Discover available repositories from configured sources.

Tool definition: src/code_indexer/server/mcp/tools.py:148-162

Required permission: `query_repos`

Parameters:

**source_type** (string, optional)
- Source type filter
- If not specified, returns all sources

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "discover_repositories",
    "arguments": {}
  },
  "id": 1
}
```

## Repository Management Tools

### list_repositories

List activated repositories for current user.

Tool definition: src/code_indexer/server/mcp/tools.py:164-173

Required permission: `query_repos`

Parameters: None

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "list_repositories",
    "arguments": {}
  },
  "id": 1
}
```

### activate_repository

Activate a repository for querying (supports single or composite repositories).

Tool definition: src/code_indexer/server/mcp/tools.py:174-201

Required permission: `activate_repos`

Parameters:

**golden_repo_alias** (string, optional)
- Golden repository alias (for single repository activation)
- Mutually exclusive with `golden_repo_aliases`

**golden_repo_aliases** (array of strings, optional)
- Multiple golden repository aliases (for composite repository)
- Mutually exclusive with `golden_repo_alias`

**branch_name** (string, optional)
- Branch to activate
- If not specified, uses default branch

**user_alias** (string, optional)
- User-defined alias for activated repository
- If not specified, uses golden repository alias

Example request (single repository):

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "activate_repository",
    "arguments": {
      "golden_repo_alias": "myproject",
      "branch_name": "main",
      "user_alias": "myproject-main"
    }
  },
  "id": 1
}
```

Example request (composite repository):

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "activate_repository",
    "arguments": {
      "golden_repo_aliases": ["frontend", "backend", "shared"],
      "user_alias": "fullstack-app"
    }
  },
  "id": 2
}
```

### deactivate_repository

Deactivate a repository.

Tool definition: src/code_indexer/server/mcp/tools.py:202-216

Required permission: `activate_repos`

Parameters:

**user_alias** (string, required)
- User alias of repository to deactivate

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "deactivate_repository",
    "arguments": {
      "user_alias": "myproject-main"
    }
  },
  "id": 1
}
```

### get_repository_status

Get detailed status of a repository.

Tool definition: src/code_indexer/server/mcp/tools.py:217-231

Required permission: `query_repos`

Parameters:

**user_alias** (string, required)
- User alias of repository

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "get_repository_status",
    "arguments": {
      "user_alias": "myproject-main"
    }
  },
  "id": 1
}
```

### sync_repository

Sync repository with upstream (git pull).

Tool definition: src/code_indexer/server/mcp/tools.py:232-246

Required permission: `activate_repos`

Parameters:

**user_alias** (string, required)
- User alias of repository

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "sync_repository",
    "arguments": {
      "user_alias": "myproject-main"
    }
  },
  "id": 1
}
```

### switch_branch

Switch repository to different branch.

Tool definition: src/code_indexer/server/mcp/tools.py:247-266

Required permission: `activate_repos`

Parameters:

**user_alias** (string, required)
- User alias of repository

**branch_name** (string, required)
- Target branch name

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "switch_branch",
    "arguments": {
      "user_alias": "myproject-main",
      "branch_name": "develop"
    }
  },
  "id": 1
}
```

## Files and Health Tools

### list_files

List files in a repository.

Tool definition: src/code_indexer/server/mcp/tools.py:267-285

Required permission: `query_repos`

Parameters:

**repository_alias** (string, required)
- Repository alias

**path** (string, optional)
- Directory path
- If not specified, lists root directory

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "list_files",
    "arguments": {
      "repository_alias": "myproject-main",
      "path": "src/auth"
    }
  },
  "id": 1
}
```

### get_file_content

Get content of a specific file.

Tool definition: src/code_indexer/server/mcp/tools.py:286-304

Required permission: `query_repos`

Parameters:

**repository_alias** (string, required)
- Repository alias

**file_path** (string, required)
- File path relative to repository root

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "get_file_content",
    "arguments": {
      "repository_alias": "myproject-main",
      "file_path": "src/auth/login.py"
    }
  },
  "id": 1
}
```

### browse_directory

Browse directory recursively.

Tool definition: src/code_indexer/server/mcp/tools.py:305-328

Required permission: `query_repos`

Parameters:

**repository_alias** (string, required)
- Repository alias

**path** (string, optional)
- Directory path
- If not specified, browses root directory

**recursive** (boolean, optional)
- Recursive listing
- Default: true

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "browse_directory",
    "arguments": {
      "repository_alias": "myproject-main",
      "path": "src",
      "recursive": true
    }
  },
  "id": 1
}
```

### get_branches

Get available branches for a repository.

Tool definition: src/code_indexer/server/mcp/tools.py:329-343

Required permission: `query_repos`

Parameters:

**repository_alias** (string, required)
- Repository alias

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "get_branches",
    "arguments": {
      "repository_alias": "myproject-main"
    }
  },
  "id": 1
}
```

### check_health

Check system health status.

Tool definition: src/code_indexer/server/mcp/tools.py:344-353

Required permission: `query_repos`

Parameters: None

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "check_health",
    "arguments": {}
  },
  "id": 1
}
```

## Administration Tools

Administration tools require admin-level permissions.

### add_golden_repo

Add a golden repository to the server.

Tool definition: src/code_indexer/server/mcp/tools.py:354-377

Required permission: `manage_golden_repos`

Parameters:

**url** (string, required)
- Repository URL (git clone URL)

**alias** (string, required)
- Repository alias (unique identifier)

**branch** (string, optional)
- Default branch
- If not specified, uses repository default

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "add_golden_repo",
    "arguments": {
      "url": "https://github.com/example/myproject.git",
      "alias": "myproject",
      "branch": "main"
    }
  },
  "id": 1
}
```

### remove_golden_repo

Remove a golden repository from the server.

Tool definition: src/code_indexer/server/mcp/tools.py:378-392

Required permission: `manage_golden_repos`

Parameters:

**alias** (string, required)
- Repository alias

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "remove_golden_repo",
    "arguments": {
      "alias": "myproject"
    }
  },
  "id": 1
}
```

### refresh_golden_repo

Refresh a golden repository (re-index).

Tool definition: src/code_indexer/server/mcp/tools.py:393-407

Required permission: `manage_golden_repos`

Parameters:

**alias** (string, required)
- Repository alias

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "refresh_golden_repo",
    "arguments": {
      "alias": "myproject"
    }
  },
  "id": 1
}
```

### list_users

List all users.

Tool definition: src/code_indexer/server/mcp/tools.py:408-417

Required permission: `manage_users`

Parameters: None

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "list_users",
    "arguments": {}
  },
  "id": 1
}
```

### create_user

Create a new user.

Tool definition: src/code_indexer/server/mcp/tools.py:418-441

Required permission: `manage_users`

Parameters:

**username** (string, required)
- Username (unique)

**password** (string, required)
- Password (will be hashed)

**role** (string, required)
- User role
- Options: "admin", "power_user", "normal_user"

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "create_user",
    "arguments": {
      "username": "developer1",
      "password": "secure-password-here",
      "role": "normal_user"
    }
  },
  "id": 1
}
```

## Analytics Tools

### get_repository_statistics

Get repository statistics (file counts, language breakdown, index status).

Tool definition: src/code_indexer/server/mcp/tools.py:442-457

Required permission: `query_repos`

Parameters:

**repository_alias** (string, required)
- Repository alias

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "get_repository_statistics",
    "arguments": {
      "repository_alias": "myproject-main"
    }
  },
  "id": 1
}
```

### get_job_statistics

Get background job statistics (indexing jobs, sync jobs).

Tool definition: src/code_indexer/server/mcp/tools.py:458-467

Required permission: `query_repos`

Parameters: None

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "get_job_statistics",
    "arguments": {}
  },
  "id": 1
}
```

### get_all_repositories_status

Get status summary of all repositories.

Tool definition: src/code_indexer/server/mcp/tools.py:468-477

Required permission: `query_repos`

Parameters: None

Example request:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "get_all_repositories_status",
    "arguments": {}
  },
  "id": 1
}
```

### manage_composite_repository

Manage composite repository operations (create, update, delete).

Tool definition: src/code_indexer/server/mcp/tools.py:478-503

Required permission: `activate_repos`

Parameters:

**operation** (string, required)
- Operation type
- Options: "create", "update", "delete"

**user_alias** (string, required)
- Composite repository alias

**golden_repo_aliases** (array of strings, optional)
- Golden repository aliases to include
- Required for "create" and "update" operations

Example request (create composite):

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "manage_composite_repository",
    "arguments": {
      "operation": "create",
      "user_alias": "fullstack-app",
      "golden_repo_aliases": ["frontend", "backend", "shared"]
    }
  },
  "id": 1
}
```

Example request (delete composite):

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "manage_composite_repository",
    "arguments": {
      "operation": "delete",
      "user_alias": "fullstack-app"
    }
  },
  "id": 2
}
```

## SSE Streaming

For large query results, CIDX server may use Server-Sent Events (SSE) streaming.

SSE implementation: src/code_indexer/mcpb/http_client.py:123-190

Request headers include:
```
Accept: text/event-stream, application/json
```

SSE event format:

```
data: {"type":"chunk","content":"partial result data"}

data: {"type":"chunk","content":"more partial result data"}

data: {"type":"complete","content":{"final":"result"}}
```

Bridge automatically assembles SSE chunks into single JSON-RPC response.

## Authentication

All requests require Bearer token authentication.

Authentication headers (from src/code_indexer/mcpb/http_client.py:44-54):

```
Authorization: Bearer YOUR_TOKEN_HERE
Content-Type: application/json
Accept: text/event-stream, application/json
```

Authentication errors return 401 status:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32000,
    "message": "Authentication failed: 401 Unauthorized"
  },
  "id": 1
}
```

## Tool Discovery

List available tools:

```json
{
  "jsonrpc": "2.0",
  "method": "tools/list",
  "params": {},
  "id": 1
}
```

Response includes all 22 tools with full schemas:

```json
{
  "jsonrpc": "2.0",
  "result": {
    "tools": [
      {
        "name": "search_code",
        "description": "Search code using semantic search, FTS, or hybrid mode",
        "inputSchema": {
          "type": "object",
          "properties": {...},
          "required": ["query_text"]
        }
      }
    ]
  },
  "id": 1
}
```

## Version Information

- MCPB version: 8.1.0
- Entry point: cidx-bridge (from pyproject.toml:80)
- CLI implementation: src/code_indexer/mcpb/bridge.py:187-222
- Tool registry: src/code_indexer/server/mcp/tools.py

Last Updated: 2025-11-26

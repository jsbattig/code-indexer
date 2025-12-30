# MCP Tool Definitions Comprehensive Overhaul Specification

**Status**: In Progress
**Created**: 2025-12-28
**Purpose**: Document all changes needed to complete the MCP tool definitions overhaul based on critical user-perspective review

---

## Completed Tasks

### 1. Repository Alias Rules and Permission System Documentation ✅

Added comprehensive documentation block at top of TOOL_REGISTRY (lines 6-190) covering:
- Global vs Activated repository naming conventions
- Tools that accept each type
- Common errors and fixes
- Typical workflows
- Complete permission system matrix
- Role capabilities summary
- Permission troubleshooting guide

### 2. File CRUD Output Schemas ✅

Added outputSchema to:
- **create_file**: Returns {success, file_path, content_hash, size_bytes, created_at, error}
- **edit_file**: Returns {success, file_path, new_content_hash, modified_at, changes_made, error}
- **delete_file**: Returns {success, file_path, deleted_at, error}

### 3. get_file_content Token-Limiting Documentation ✅

Added comprehensive documentation for token-based pagination (Section 8):
- **BREAKING CHANGE documentation**: Default behavior change (entire file → first chunk only)
- **Token enforcement configuration**: Configurable limits (1000-20000 tokens, default 5000)
- **Input parameters**: Detailed description of offset/limit parameters
- **Output schema**: Complete metadata documentation with 6 new token-enforcement fields
- **Pagination workflow**: Step-by-step guide for handling large files
- **Usage examples**: 5 detailed examples (small file, large file, pagination, truncation, errors)
- **Best practices**: 5 patterns including recommended limits by use case
- **Comparison to Claude Code Read tool**: Feature comparison and design philosophy
- **When to use/not use**: Clear decision matrix
- **Troubleshooting**: 5 common problems with solutions
- **Migration guide**: How to update existing code

---

## Remaining Tasks

### 4. Git Operations Output Schemas (HIGH PRIORITY)

Need to add outputSchema to 14 git tools:

#### git_stage
```python
"outputSchema": {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "description": "Whether staging succeeded"},
        "staged_files": {"type": "array", "items": {"type": "string"}, "description": "List of successfully staged file paths"},
        "error": {"type": "string", "description": "Error message (present when success=false)"}
    },
    "required": ["success"]
}
```

#### git_unstage
```python
"outputSchema": {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "description": "Whether unstaging succeeded"},
        "unstaged_files": {"type": "array", "items": {"type": "string"}, "description": "List of successfully unstaged file paths"},
        "error": {"type": "string", "description": "Error message (present when success=false)"}
    },
    "required": ["success"]
}
```

#### git_commit
```python
"outputSchema": {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "description": "Whether commit succeeded"},
        "commit_hash": {"type": "string", "description": "Full commit SHA-1 hash (present when success=true)"},
        "short_hash": {"type": "string", "description": "Short commit hash (7 chars) (present when success=true)"},
        "message": {"type": "string", "description": "Commit message (present when success=true)"},
        "author": {"type": "string", "description": "Commit author name and email (present when success=true)"},
        "files_committed": {"type": "array", "items": {"type": "string"}, "description": "List of files included in commit (present when success=true)"},
        "error": {"type": "string", "description": "Error message (present when success=false)"}
    },
    "required": ["success"]
}
```

#### git_push
```python
"outputSchema": {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "description": "Whether push succeeded"},
        "remote": {"type": "string", "description": "Remote name (e.g., 'origin') (present when success=true)"},
        "branch": {"type": "string", "description": "Branch name pushed (present when success=true)"},
        "commits_pushed": {"type": "integer", "description": "Number of commits pushed (present when success=true)"},
        "error": {"type": "string", "description": "Error message (present when success=false)"}
    },
    "required": ["success"]
}
```

#### git_pull
```python
"outputSchema": {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "description": "Whether pull succeeded"},
        "remote": {"type": "string", "description": "Remote name (present when success=true)"},
        "branch": {"type": "string", "description": "Branch name pulled (present when success=true)"},
        "files_changed": {"type": "array", "items": {"type": "string"}, "description": "List of files modified by pull (present when success=true)"},
        "commits_pulled": {"type": "integer", "description": "Number of new commits pulled (present when success=true)"},
        "error": {"type": "string", "description": "Error message (present when success=false)"}
    },
    "required": ["success"]
}
```

#### git_fetch
```python
"outputSchema": {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "description": "Whether fetch succeeded"},
        "remote": {"type": "string", "description": "Remote name (present when success=true)"},
        "refs_fetched": {"type": "array", "items": {"type": "string"}, "description": "List of fetched refs (present when success=true)"},
        "error": {"type": "string", "description": "Error message (present when success=false)"}
    },
    "required": ["success"]
}
```

#### git_reset (destructive - has confirmation flow)
```python
"outputSchema": {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "description": "Whether reset succeeded"},
        "requires_confirmation": {"type": "boolean", "description": "True if operation requires user confirmation (mutually exclusive with success)"},
        "confirmation_token": {"type": "string", "description": "Token to pass in confirmed_token parameter (present when requires_confirmation=true)"},
        "mode": {"type": "string", "description": "Reset mode (soft/mixed/hard) (present when success=true)"},
        "target_commit": {"type": "string", "description": "Target commit hash or ref (present when success=true)"},
        "warning_message": {"type": "string", "description": "Warning about operation impact (present when requires_confirmation=true)"},
        "error": {"type": "string", "description": "Error message (present when success=false)"}
    }
}
```

#### git_clean (destructive - has confirmation flow)
```python
"outputSchema": {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "description": "Whether clean succeeded"},
        "requires_confirmation": {"type": "boolean", "description": "True if operation requires user confirmation"},
        "confirmation_token": {"type": "string", "description": "Token to pass in confirmed_token parameter (present when requires_confirmation=true)"},
        "removed_files": {"type": "array", "items": {"type": "string"}, "description": "List of removed file paths (present when success=true)"},
        "warning_message": {"type": "string", "description": "Warning about files to be removed (present when requires_confirmation=true)"},
        "error": {"type": "string", "description": "Error message (present when success=false)"}
    }
}
```

#### git_merge_abort
```python
"outputSchema": {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "description": "Whether merge abort succeeded"},
        "message": {"type": "string", "description": "Status message (present when success=true)"},
        "error": {"type": "string", "description": "Error message (present when success=false)"}
    },
    "required": ["success"]
}
```

#### git_checkout_file
```python
"outputSchema": {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "description": "Whether checkout succeeded"},
        "restored_files": {"type": "array", "items": {"type": "string"}, "description": "List of restored file paths (present when success=true)"},
        "error": {"type": "string", "description": "Error message (present when success=false)"}
    },
    "required": ["success"]
}
```

#### git_branch_list
```python
"outputSchema": {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "description": "Whether listing succeeded"},
        "current_branch": {"type": "string", "description": "Currently checked out branch (present when success=true)"},
        "branches": {
            "type": "array",
            "description": "List of all branches (present when success=true)",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Branch name"},
                    "is_current": {"type": "boolean", "description": "Whether this is the current branch"},
                    "last_commit": {"type": "string", "description": "Last commit hash on this branch"}
                }
            }
        },
        "error": {"type": "string", "description": "Error message (present when success=false)"}
    },
    "required": ["success"]
}
```

#### git_branch_create
```python
"outputSchema": {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "description": "Whether branch creation succeeded"},
        "created_branch": {"type": "string", "description": "Name of created branch (present when success=true)"},
        "error": {"type": "string", "description": "Error message (present when success=false)"}
    },
    "required": ["success"]
}
```

#### git_branch_switch
```python
"outputSchema": {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "description": "Whether branch switch succeeded"},
        "from_branch": {"type": "string", "description": "Previous branch (present when success=true)"},
        "to_branch": {"type": "string", "description": "New current branch (present when success=true)"},
        "error": {"type": "string", "description": "Error message (present when success=false)"}
    },
    "required": ["success"]
}
```

#### git_branch_delete (destructive - has confirmation flow)
```python
"outputSchema": {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "description": "Whether branch deletion succeeded"},
        "requires_confirmation": {"type": "boolean", "description": "True if operation requires user confirmation"},
        "confirmation_token": {"type": "string", "description": "Token to pass in confirmed_token parameter (present when requires_confirmation=true)"},
        "deleted_branch": {"type": "string", "description": "Name of deleted branch (present when success=true)"},
        "warning_message": {"type": "string", "description": "Warning about deletion impact (present when requires_confirmation=true)"},
        "error": {"type": "string", "description": "Error message (present when success=false)"}
    }
}
```

---

### 5. Expand Severely Under-Documented Tools (HIGH PRIORITY)

Three tools have minimal 3-4 word descriptions. Need to expand to full TL;DR format:

#### deactivate_repository (currently "Deactivate an activated repository")

**New Description**:
```
TL;DR: Remove a user-specific repository activation and delete associated indexes. This frees storage and removes the repository from your workspace.

USE CASES:
(1) Clean up activations you no longer need after completing work
(2) Free storage from unused composite repositories and their indexes
(3) Remove old branch-specific or experimental activations
(4) Reclaim disk space from user-specific semantic/FTS indexes

WHAT IT DOES:
Removes repository from your activated list and deletes user-specific indexes including composite indexes and branch-specific indexes. Does NOT affect the underlying golden repository or global indexes shared by other users. Other users' activations of the same golden repo are unaffected.

REQUIREMENTS:
- You must have 'activate_repos' permission (power_user or admin role)
- Repository must be currently activated (check with list_activated_repos)
- Cannot deactivate global repositories ending in '-global' (those are managed by admins via remove_golden_repo)

RETURNS:
Confirmation of deactivation with list of deleted index directories and space freed.

EXAMPLE:
{
  "repository_alias": "my-old-project"
}
->
{
  "success": true,
  "repository_alias": "my-old-project",
  "indexes_deleted": [".code-indexer/composite/my-old-project", ".code-indexer/branch-specific/my-old-project-feat123"],
  "space_freed_mb": 487
}

COMMON ERRORS:
- "Repository 'my-repo' not activated" -> Check list_activated_repos() for correct alias
- "Cannot deactivate global repository" -> Global repos ending in '-global' require admin's remove_golden_repo
- "Permission denied: requires activate_repos" -> Need power_user or admin role

FAILURE EXAMPLE:
{
  "success": false,
  "error": "Repository 'nonexistent-repo' is not activated",
  "hint": "Use list_activated_repos() to see your activated repositories"
}

RELATED TOOLS:
activate_repository (create activation), list_activated_repos (see your activations), remove_golden_repo (admin tool for global repos), manage_composite_repository (manage composite repo components before deactivation)
```

#### sync_repository (currently "Sync repository with remote")

**New Description**:
```
TL;DR: Synchronize activated repository with remote origin by fetching latest changes and updating local branches. Equivalent to git fetch + status check.

USE CASES:
(1) Get latest commits from remote before starting work
(2) Update local view of remote branches without merging
(3) Check if local branch is behind/ahead of remote
(4) Prepare for pull/merge decisions by seeing what's new

WHAT IT DOES:
Fetches all refs from remote origin and provides detailed sync status for current branch showing commits ahead/behind remote. Does NOT merge or modify working tree - only updates remote tracking branches. Safe operation that doesn't change your code.

REQUIREMENTS:
- Repository must be activated (not a global repository)
- Repository must have remote origin configured
- Network access to remote repository
- Requires 'repository:read' permission

PARAMETERS:
- repository_alias: Your activated repository alias (NOT '-global' repos)
- prune: (optional, default=false) Remove remote-tracking branches that no longer exist on remote

RETURNS:
Sync status including commits ahead/behind, updated refs, and current branch state.

EXAMPLE:
{
  "repository_alias": "my-backend-work",
  "prune": true
}
->
{
  "success": true,
  "current_branch": "feature-123",
  "ahead": 2,
  "behind": 5,
  "updated_refs": ["refs/remotes/origin/main", "refs/remotes/origin/develop"],
  "pruned_refs": ["refs/remotes/origin/old-feature"],
  "needs_pull": true,
  "needs_push": true
}

COMMON ERRORS:
- "Repository has no remote origin" -> Repository not connected to remote, can't sync
- "Network unreachable" -> Check internet connection and remote URL
- "Permission denied: requires repository:read" -> Need at least normal_user role
- "Cannot sync global repository" -> Global repos don't support sync (admins manage them)

FAILURE EXAMPLE:
{
  "success": false,
  "error": "Repository 'backend-global' is a global repository",
  "hint": "Only activated repositories can be synced. Global repositories are managed by administrators."
}

WORKFLOW INTEGRATION:
Typical sync workflow:
1. sync_repository('my-repo') -> Check what's new remotely
2. If behind > 0: git_pull('my-repo') -> Get remote changes
3. If ahead > 0: git_push('my-repo') -> Push local commits
4. Continue work with synchronized state

RELATED TOOLS:
git_fetch (lower-level fetch without status), git_pull (sync + merge), git_push (push local commits), git_status (local working tree status), activate_repository (create workspace to sync)
```

#### manage_composite_repository (currently "Manage composite repository components")

**New Description**:
```
TL;DR: Add or remove component repositories from a composite repository workspace. Composite repos let you search across multiple repositories as one unified codebase.

USE CASES:
(1) Create multi-repo workspace for microservices architecture (search backend + frontend + shared libs together)
(2) Add new component to existing composite after activating additional repos
(3) Remove component that's no longer relevant to your work
(4) Build custom search scope combining related repositories

WHAT COMPOSITE REPOSITORIES ARE:
A composite repository is an activated workspace that combines multiple golden repositories into a single searchable unit. When you search a composite repo, CIDX searches all component repos simultaneously and merges results. This is powerful for architectures where related code spans multiple repositories.

OPERATIONS:

ADD COMPONENT:
Adds a golden repository as component to existing composite. The golden repo must exist and you must have access. Component gets its own subdirectory in the composite workspace.

REMOVE COMPONENT:
Removes a component repository from composite. Does NOT deactivate the component repo individually - just removes it from this composite workspace.

LIST COMPONENTS:
Shows all component repositories in the composite with their paths and index status.

REQUIREMENTS:
- Composite repository must be activated
- Target component (for add) must be a golden repository ending in '-global'
- Requires 'activate_repos' permission (power_user or admin)
- Requires 'repository:write' permission for add/remove operations

PARAMETERS:
- composite_alias: Your activated composite repository alias
- operation: "add" | "remove" | "list"
- component_repo: (for add/remove) Golden repository alias ending in '-global'

RETURNS:
Updated component list after operation.

EXAMPLE - Add Component:
{
  "composite_alias": "my-fullstack-workspace",
  "operation": "add",
  "component_repo": "shared-library-global"
}
->
{
  "success": true,
  "composite_alias": "my-fullstack-workspace",
  "operation": "add",
  "components": [
    {"alias": "backend-global", "path": "/composites/my-fullstack-workspace/backend"},
    {"alias": "frontend-global", "path": "/composites/my-fullstack-workspace/frontend"},
    {"alias": "shared-library-global", "path": "/composites/my-fullstack-workspace/shared-library"}
  ],
  "total_components": 3
}

EXAMPLE - List Components:
{
  "composite_alias": "my-fullstack-workspace",
  "operation": "list"
}
->
{
  "success": true,
  "composite_alias": "my-fullstack-workspace",
  "components": [
    {"alias": "backend-global", "path": "/composites/my-fullstack-workspace/backend", "indexed": true},
    {"alias": "frontend-global", "path": "/composites/my-fullstack-workspace/frontend", "indexed": true}
  ],
  "total_components": 2
}

COMMON ERRORS:
- "Composite repository 'my-repo' not found" -> Repository not activated or not a composite type
- "Component 'my-repo' must be a global repository" -> Only golden repos (ending '-global') can be components
- "Component 'backend-global' already exists in composite" -> Component already added
- "Permission denied: requires activate_repos" -> Need power_user or admin role

FAILURE EXAMPLE:
{
  "success": false,
  "error": "Component repository 'nonexistent-global' not found",
  "hint": "Use list_global_repos() to see available golden repositories that can be added as components"
}

COMPOSITE REPOSITORY WORKFLOW:
1. activate_repository('backend-global', 'my-workspace', composite=true) -> Create composite
2. manage_composite_repository('my-workspace', 'add', 'frontend-global') -> Add component
3. manage_composite_repository('my-workspace', 'add', 'shared-global') -> Add another
4. search_code('authentication', 'my-workspace') -> Search all 3 repos together
5. manage_composite_repository('my-workspace', 'remove', 'shared-global') -> Remove if not needed
6. deactivate_repository('my-workspace') -> Clean up when done

RELATED TOOLS:
activate_repository (create composite workspace), deactivate_repository (remove composite), search_code (search across components), list_global_repos (find components to add)
```

---

### 6. Remove Duplicate cidx_quick_reference Definition

**Location**: Line 287 (first definition) and Line 4131 (second definition)

**Action**: Delete the FIRST definition at line 287. Keep the more complete second definition at line 4131.

**Verification**: Search for "cidx_quick_reference" in file - should only find ONE definition.

---

### 7. Standardize All Tool Descriptions (LARGE TASK)

Convert ALL remaining tool descriptions to this format:

```
TL;DR: [One sentence - what it does]

USE CASES: (1) [specific scenario], (2) [specific scenario], (3) [specific scenario]

REQUIREMENTS: [Prerequisites - permissions, index types, etc.]

PARAMETERS:
- key_param: [What it does, when to use it]

RETURNS: [Key output fields with brief explanation]

EXAMPLE:
{
  "param1": "value1",
  "param2": "value2"
}
->
{
  "success": true,
  "field1": "result",
  "field2": 123
}

COMMON ERRORS:
- Error 1: Explanation and fix
- Error 2: Explanation and fix

FAILURE EXAMPLE:
{
  "success": false,
  "error": "Specific error message",
  "hint": "How to fix it"
}

RELATED TOOLS: [Similar/complementary tools]
```

**Tools needing this treatment** (examples - full audit needed):
- regex_search
- git_log
- git_blame
- git_file_history
- git_diff
- git_search_commits
- git_search_diffs
- browse_directory
- directory_tree
- ~~get_file_content~~ (DOCUMENTED - see section below)
- list_global_repos
- global_repo_status
- list_activated_repos
- activate_repository
- add_golden_repo
- remove_golden_repo
- scip_* tools (all SCIP tools)
- whoami
- list_users
- And many more...

---

### 8. get_file_content Token-Limiting Documentation (COMPLETED)

**Purpose**: Document the breaking change in `get_file_content` default behavior and new token-based pagination system.

**Status**: IMPLEMENTED - Documentation below describes current behavior in tools.py (lines 1163-1286)

---

#### BREAKING CHANGE: Token-Limited Default Behavior

**OLD BEHAVIOR** (pre-pagination):
```python
get_file_content('repo-global', 'large_file.py')
# Returned ENTIRE file regardless of size (could be 10,000+ lines)
# No token awareness, could exhaust LLM context window
```

**NEW BEHAVIOR** (current):
```python
get_file_content('repo-global', 'large_file.py')
# Returns FIRST CHUNK ONLY (up to 5000 tokens, approximately 200-250 lines)
# Forces explicit pagination for large files
# Prevents LLM context window exhaustion
```

**Backward Compatibility**: Existing calls work but get different default behavior. To maintain old behavior, explicitly pass `offset=1, limit=None` (NOT RECOMMENDED - defeats token limiting).

---

#### Token Enforcement Configuration

**Configurable Limits** (via Web UI):
- **Token range**: 1000-20000 tokens per request
- **Default**: 5000 tokens (~20,000 characters at 4 chars/token estimate)
- **Estimation**: Characters per token ratio configurable (3-5 chars/token, default 4)

**Token Calculation**:
```
estimated_tokens = len(content) / chars_per_token
```

**Enforcement**:
- Content ALWAYS truncated if exceeds `max_tokens_per_request`
- Truncation happens at line boundaries (never mid-line)
- `metadata.truncated` indicates if token limit was hit
- `metadata.truncated_at_line` shows where content was cut

---

#### Input Parameters

**Required Parameters**:
- `repository_alias` (string): Repository alias (global or activated)
- `file_path` (string): Relative path to file within repository

**Optional Parameters**:
- `offset` (integer, min=1): Line number to start reading from (1-indexed)
  - Default: 1 (read from beginning)
  - Example: `offset=100` starts at line 100

- `limit` (integer, min=1): Maximum number of lines to return
  - Default: Token-limited chunk (up to 5000 tokens)
  - **Recommended**: 200-250 lines per request to stay within 5000 token budget
  - **Note**: Token limits enforced even if larger limit specified
  - Example: `limit=250` attempts to read 250 lines (may be truncated by token limit)

---

#### Output Schema

**Success Response**:
```python
{
  "success": true,
  "content": [
    {
      "type": "text",
      "text": "... file content ..."
    }
  ],
  "metadata": {
    # Basic file info
    "path": "src/auth.py",
    "size": 15000,
    "modified_at": "2025-12-29T10:30:00Z",
    "language": "python",
    "total_lines": 450,

    # Pagination state
    "offset": 1,
    "limit": 250,
    "returned_lines": 210,
    "has_more": true,

    # Token enforcement (NEW)
    "estimated_tokens": 4500,
    "max_tokens_per_request": 5000,
    "truncated": false,
    "truncated_at_line": null,
    "requires_pagination": true,
    "pagination_hint": "File has more content. Continue with offset=211"
  }
}
```

**New Metadata Fields** (Token Enforcement):

| Field | Type | Description |
|-------|------|-------------|
| `estimated_tokens` | integer | Estimated token count of returned content (content_length / chars_per_token) |
| `max_tokens_per_request` | integer | Current server-configured token limit (default 5000) |
| `truncated` | boolean | True if content was cut due to token limit (not just line limit) |
| `truncated_at_line` | integer\|null | Line number where token truncation occurred (null if not truncated) |
| `requires_pagination` | boolean | True if more content exists (either `has_more=true` OR `truncated=true`) |
| `pagination_hint` | string\|null | Human-readable message with suggested next offset (null if no more content) |

**Existing Metadata Fields** (Still Present):

| Field | Type | Description |
|-------|------|-------------|
| `path` | string | Relative file path |
| `size` | integer | File size in bytes |
| `modified_at` | string | ISO 8601 timestamp of last modification |
| `language` | string\|null | Detected programming language |
| `total_lines` | integer | Total lines in complete file |
| `offset` | integer | Starting line number (1-indexed) for returned content |
| `limit` | integer\|null | Line limit used (null if unlimited) |
| `returned_lines` | integer | Number of lines returned in this response |
| `has_more` | boolean | True if more lines exist beyond current range |

---

#### Pagination Workflow

**Step 1: Initial Request (No Parameters)**
```python
result = get_file_content('backend-global', 'large_file.py')

# If file is large:
result['metadata']['requires_pagination']  # -> true
result['metadata']['pagination_hint']      # -> "File has more content. Continue with offset=211"
result['metadata']['estimated_tokens']     # -> 4850
result['metadata']['returned_lines']       # -> 210
```

**Step 2: Check Pagination Need**
```python
if result['metadata']['requires_pagination']:
    # More content exists - need to continue reading
    next_offset = result['metadata']['offset'] + result['metadata']['returned_lines']
```

**Step 3: Continue Reading**
```python
result2 = get_file_content('backend-global', 'large_file.py',
                           offset=211, limit=250)

# Repeat until requires_pagination == false
```

**Step 4: Handle Truncation**
```python
if result['metadata']['truncated']:
    print(f"Content truncated at line {result['metadata']['truncated_at_line']}")
    print(f"Exceeded {result['metadata']['max_tokens_per_request']} token limit")
    # Reduce limit parameter or continue with next offset
```

---

#### Usage Examples

**Example 1: Small File (Fits in Single Response)**
```python
# Request
{
  "repository_alias": "backend-global",
  "file_path": "config/settings.json"
}

# Response
{
  "success": true,
  "content": [{"type": "text", "text": "... entire file content (50 lines) ..."}],
  "metadata": {
    "path": "config/settings.json",
    "total_lines": 50,
    "returned_lines": 50,
    "offset": 1,
    "limit": null,
    "has_more": false,
    "estimated_tokens": 800,
    "max_tokens_per_request": 5000,
    "truncated": false,
    "truncated_at_line": null,
    "requires_pagination": false,
    "pagination_hint": null
  }
}
```

**Example 2: Large File (Token-Limited, First Chunk)**
```python
# Request
{
  "repository_alias": "backend-global",
  "file_path": "src/large_module.py"
}

# Response
{
  "success": true,
  "content": [{"type": "text", "text": "... first ~200-250 lines ..."}],
  "metadata": {
    "path": "src/large_module.py",
    "total_lines": 850,
    "returned_lines": 218,
    "offset": 1,
    "limit": null,
    "has_more": true,
    "estimated_tokens": 4950,
    "max_tokens_per_request": 5000,
    "truncated": false,
    "truncated_at_line": null,
    "requires_pagination": true,
    "pagination_hint": "File has more content. Continue with offset=219"
  }
}
```

**Example 3: Explicit Pagination**
```python
# Request (read middle section)
{
  "repository_alias": "backend-global",
  "file_path": "src/large_module.py",
  "offset": 300,
  "limit": 200
}

# Response
{
  "success": true,
  "content": [{"type": "text", "text": "... lines 300-499 ..."}],
  "metadata": {
    "path": "src/large_module.py",
    "total_lines": 850,
    "returned_lines": 200,
    "offset": 300,
    "limit": 200,
    "has_more": true,
    "estimated_tokens": 4200,
    "max_tokens_per_request": 5000,
    "truncated": false,
    "truncated_at_line": null,
    "requires_pagination": true,
    "pagination_hint": "File has more content. Continue with offset=500"
  }
}
```

**Example 4: Token Truncation (Limit Too Large)**
```python
# Request (trying to read 500 lines but hits token limit)
{
  "repository_alias": "backend-global",
  "file_path": "src/verbose_file.py",
  "offset": 1,
  "limit": 500
}

# Response (truncated at line 180 due to token limit)
{
  "success": true,
  "content": [{"type": "text", "text": "... lines 1-180 only ..."}],
  "metadata": {
    "path": "src/verbose_file.py",
    "total_lines": 800,
    "returned_lines": 180,
    "offset": 1,
    "limit": 500,
    "has_more": true,
    "estimated_tokens": 5000,
    "max_tokens_per_request": 5000,
    "truncated": true,
    "truncated_at_line": 180,
    "requires_pagination": true,
    "pagination_hint": "Content truncated at token limit. Continue with offset=181"
  }
}
```

**Example 5: Error Handling**
```python
# Request (file not found)
{
  "repository_alias": "backend-global",
  "file_path": "nonexistent.py"
}

# Response
{
  "success": false,
  "error": "File 'nonexistent.py' not found in repository 'backend-global'",
  "metadata": null
}
```

---

#### Best Practices

**1. Start Small (Conserve Context Window)**
```python
# GOOD: Start with default token limit
result = get_file_content('repo-global', 'file.py')

# Check if you need more
if result['metadata']['requires_pagination']:
    # Decide if you actually need more content
```

**2. Token Awareness**
```python
# Before reading, check estimated size
if result['metadata']['total_lines'] > 500:
    # Large file - use targeted pagination
    result = get_file_content('repo-global', 'file.py', offset=1, limit=200)
else:
    # Small file - read completely
    result = get_file_content('repo-global', 'file.py')
```

**3. Pagination Loop Pattern**
```python
def read_entire_file(repo_alias: str, file_path: str) -> str:
    """Read entire file with automatic pagination."""
    content_parts = []
    offset = 1

    while True:
        result = get_file_content(repo_alias, file_path, offset=offset, limit=250)
        if not result['success']:
            raise Exception(result['error'])

        content_parts.append(result['content'][0]['text'])

        if not result['metadata']['requires_pagination']:
            break

        offset = result['metadata']['offset'] + result['metadata']['returned_lines']

    return '\n'.join(content_parts)
```

**4. Handle Truncation Gracefully**
```python
result = get_file_content('repo-global', 'file.py', limit=500)

if result['metadata']['truncated']:
    print(f"WARNING: Content truncated at line {result['metadata']['truncated_at_line']}")
    print(f"Requested 500 lines but hit {result['metadata']['max_tokens_per_request']} token limit")
    print("Consider reducing limit parameter or using pagination")
```

**5. Recommended Limits by Use Case**

| Use Case | Recommended Limit | Rationale |
|----------|------------------|-----------|
| Quick inspection | Default (no limit param) | Token-limited chunk, ~200-250 lines |
| Reading imports/headers | 50-100 lines | Most files have metadata at top |
| Code review | 200-250 lines | Fits comfortably in 5000 token budget |
| Searching specific section | Use `search_code` first | Then use targeted offset/limit |
| Reading entire file | Pagination loop (see above) | Automatic chunk handling |

---

#### Comparison to Claude Code's Read Tool

**Similarities**:
- Both use token-based limits to prevent context exhaustion
- Both support pagination with offset/limit parameters
- Both return metadata about truncation and pagination needs
- Both provide hints for continuing pagination

**Differences**:

| Feature | CIDX get_file_content | Claude Code Read |
|---------|----------------------|------------------|
| Default behavior | Token-limited first chunk | Entire file up to 2000 lines |
| Token limit | Configurable (1000-20000, default 5000) | Fixed at model context limits |
| Truncation metadata | `truncated`, `truncated_at_line`, `estimated_tokens` | Less detailed |
| Pagination hints | Automatic with suggested offset | Manual calculation |
| Content format | MCP-compliant content blocks | Plain text with line numbers |
| Repository context | Multi-repo support (global/activated) | Local filesystem only |

**Design Philosophy**:
CIDX's approach is more conservative with context budget, forcing users to make conscious decisions about large file reads. This prevents accidental context window exhaustion when exploring unfamiliar codebases.

---

#### When to Use get_file_content

**USE when**:
1. Reading source code after `search_code` identifies relevant files
2. Inspecting configuration files (package.json, tsconfig.json, etc.)
3. Reviewing file content before editing (to get `content_hash` for optimistic locking)
4. Reading documentation files (README.md, API docs)
5. Navigating large files efficiently with pagination

**DO NOT USE when**:
1. Need file listing -> Use `list_files` or `browse_directory`
2. Need to search file content -> Use `search_code` or `regex_search` FIRST
3. Need directory structure -> Use `directory_tree` or `browse_directory`
4. Want to read multiple files -> Use `search_code` with appropriate filters
5. Exploring unfamiliar codebase -> Start with `browse_directory` + `directory_tree`

---

#### Troubleshooting

**Problem 1: "File not found" Error**
```
Symptom: {"success": false, "error": "File 'path/to/file.py' not found"}

Solutions:
1. Verify file_path with list_files() or browse_directory()
2. Check repository_alias is correct (list_global_repos() or list_activated_repos())
3. Ensure file path is relative to repository root (no leading /)
4. Check repository is accessible (permissions)
```

**Problem 2: "Permission denied" Error**
```
Symptom: {"success": false, "error": "Permission denied: requires repository:read"}

Solutions:
1. Check your role with whoami()
2. Verify repository is activated (for write operations) or global (for read)
3. Confirm you have 'query_repos' permission (all roles have this)
4. Check repository isn't restricted by admin
```

**Problem 3: Content Truncated Unexpectedly**
```
Symptom: metadata.truncated = true when expecting full content

Solutions:
1. Check metadata.estimated_tokens vs metadata.max_tokens_per_request
2. Reduce limit parameter (try 200 lines instead of 500)
3. Use pagination to read in chunks
4. If file has unusually dense content (minified JS, etc.), expect earlier truncation
```

**Problem 4: Pagination Loop Doesn't Terminate**
```
Symptom: Infinite loop when reading file with pagination

Debug:
1. Log metadata.requires_pagination, metadata.has_more, metadata.truncated each iteration
2. Verify offset calculation: next_offset = metadata.offset + metadata.returned_lines
3. Check for off-by-one errors (offset is 1-indexed, not 0-indexed)
4. Add iteration limit to prevent infinite loops during development
```

**Problem 5: High Token Usage Despite Pagination**
```
Symptom: Still consuming too much context window

Solutions:
1. Start with even smaller limits (100-150 lines)
2. Use targeted pagination (read specific sections, not entire file)
3. Consider if you actually need file content (maybe search_code results are sufficient)
4. Use browse_directory to inspect file metadata before reading
```

---

#### Migration Guide

**For existing code using get_file_content**:

**Before (assumed entire file returned)**:
```python
result = get_file_content('backend-global', 'large_file.py')
full_content = result['content'][0]['text']
# Used to get entire file, might be 1000+ lines
```

**After (handle pagination)**:
```python
# Option 1: Accept token-limited first chunk (RECOMMENDED)
result = get_file_content('backend-global', 'large_file.py')
first_chunk = result['content'][0]['text']
# Only ~200-250 lines, but saves context window

# Check if you need more
if result['metadata']['requires_pagination']:
    print(f"File has {result['metadata']['total_lines']} total lines")
    print(f"Use pagination if you need more than first {result['metadata']['returned_lines']} lines")

# Option 2: Read entire file with pagination (NOT RECOMMENDED - defeats token limiting)
def read_entire_file_legacy(repo, path):
    parts = []
    offset = 1
    while True:
        result = get_file_content(repo, path, offset=offset, limit=250)
        parts.append(result['content'][0]['text'])
        if not result['metadata']['requires_pagination']:
            break
        offset += result['metadata']['returned_lines']
    return '\n'.join(parts)
```

**Recommended Approach**: Use search-then-read pattern
```python
# 1. Search for relevant code first
search_results = search_code('authentication logic', 'backend-global', limit=5)

# 2. Read only relevant files (likely small sections)
for result in search_results['results']:
    file_content = get_file_content('backend-global', result['path'])
    # First chunk is usually sufficient after targeted search
```

---

### 9. Add get_tool_categories Tool

**Purpose**: Help users discover tools by category

**Add after existing tool definitions**:

```python
TOOL_REGISTRY["get_tool_categories"] = {
    "name": "get_tool_categories",
    "description": (
        "TL;DR: Get organized list of all MCP tools by category. "
        "USE CASES: (1) Discover available tools, (2) Find right tool for your task, (3) Understand tool organization. "
        "RETURNS: Tools grouped by category with brief descriptions. "
        "PERMISSIONS: None required (public reference tool)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {},
        "required": []
    },
    "required_permission": None,
    "outputSchema": {
        "type": "object",
        "properties": {
            "categories": {
                "type": "object",
                "description": "Tools organized by category",
                "properties": {
                    "SEARCH_AND_DISCOVERY": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Code search and exploration tools"
                    },
                    "GIT_HISTORY": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Git history exploration tools"
                    },
                    "GIT_OPERATIONS": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Git write operations"
                    },
                    "FILE_CRUD": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "File create/read/update/delete operations"
                    },
                    "SCIP_CODE_INTELLIGENCE": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "SCIP-based code intelligence (call graphs, dependencies)"
                    },
                    "REPOSITORY_MANAGEMENT": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Repository activation and administration"
                    },
                    "USER_MANAGEMENT": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "User and permission management"
                    },
                    "REFERENCE": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Quick reference and help tools"
                    }
                }
            },
            "total_tools": {
                "type": "integer",
                "description": "Total number of available tools"
            }
        }
    }
}
```

**Handler implementation needed**: Add handler in handlers.py to return categorized tool list

---

### 10. Add first_time_user_guide Tool

**Purpose**: Onboarding guide for new users

**Add after get_tool_categories**:

```python
TOOL_REGISTRY["first_time_user_guide"] = {
    "name": "first_time_user_guide",
    "description": (
        "TL;DR: Get quick start guide for new CIDX MCP server users. "
        "USE CASES: (1) First-time user onboarding, (2) Learn essential workflows, (3) Understand key concepts. "
        "RETURNS: Step-by-step getting started guide. "
        "PERMISSIONS: None required (public guide)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {},
        "required": []
    },
    "required_permission": None,
    "outputSchema": {
        "type": "object",
        "properties": {
            "quick_start_steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ordered list of steps for first-time users"
            },
            "essential_concepts": {
                "type": "object",
                "description": "Key concepts to understand"
            },
            "example_workflows": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Common workflow examples"
            }
        }
    }
}
```

**Content to return**:
```python
{
  "quick_start_steps": [
    "1. whoami() - Check your role and permissions",
    "2. list_global_repos() - See available repositories",
    "3. global_repo_status('repo-name-global') - Check what indexes exist for a repository",
    "4. get_file_content('cidx-meta-global', 'repo-name-global.md') - Read repository description from catalog",
    "5. search_code('your query', 'repo-name-global', limit=5) - Run first semantic search",
    "6. browse_directory('repo-name-global') - Explore repository file structure",
    "7. directory_tree('repo-name-global') - See visual directory hierarchy",
    "8. (Power users) activate_repository('repo-global', 'my-workspace') - Create workspace for editing",
    "9. get_tool_categories() - Discover all available tools by category"
  ],
  "essential_concepts": {
    "global_repositories": "Shared read-only repositories ending in '-global'. Use for search and exploration. Managed by administrators.",
    "activated_repositories": "Your personal writable workspaces. Required for file editing and git operations. Create with activate_repository().",
    "semantic_search": "Searches code by MEANING, not exact text. Use search_code() with search_mode='semantic' for conceptual queries.",
    "fts_search": "Full-text search for exact identifier matches. Use search_code() with search_mode='fts' for precise text.",
    "permissions": "Role-based: normal_user (read-only), power_user (read+write), admin (full control). Check with whoami().",
    "scip_intelligence": "Call graphs, dependencies, and code relationships. Requires SCIP indexes (check global_repo_status)."
  },
  "example_workflows": [
    {
      "name": "Search Existing Code (Read-Only)",
      "steps": [
        "list_global_repos() -> Get available repos",
        "search_code('authentication', 'backend-global', limit=5) -> Find auth code",
        "get_file_content('backend-global', 'src/auth.py') -> Read full file"
      ]
    },
    {
      "name": "Edit Code and Commit",
      "steps": [
        "activate_repository('backend-global', 'my-work') -> Create workspace",
        "edit_file('my-work', 'src/auth.py', old_string='...', new_string='...', content_hash='...') -> Modify",
        "git_stage('my-work', ['src/auth.py']) -> Stage changes",
        "git_commit('my-work', 'Fix auth bug') -> Commit",
        "git_push('my-work') -> Push to remote"
      ]
    },
    {
      "name": "Explore Unfamiliar Codebase",
      "steps": [
        "get_file_content('cidx-meta-global', 'backend-global.md') -> Read repo description",
        "directory_tree('backend-global') -> See structure",
        "search_code('main entry point', 'backend-global') -> Find starting point",
        "scip_call_graph('backend-global', 'main') -> Understand execution flow"
      ]
    }
  ]
}
```

---

## Implementation Priority

1. ~~**HIGH**: get_file_content token-limiting documentation~~ ✅ COMPLETED
2. **HIGH**: Git Operations output schemas (14 tools) - Critical for API contract clarity
3. **HIGH**: Expand under-documented tools (3 tools) - User confusion without proper docs
4. **MEDIUM**: Remove duplicate cidx_quick_reference - Cleanup issue
5. **MEDIUM**: Add get_tool_categories and first_time_user_guide - Discovery enhancement
6. **LOW**: Standardize all tool descriptions - Large task, incremental improvement

---

## Verification Checklist

After implementation, verify:

- [x] get_file_content has comprehensive token-limiting documentation (Section 8)
- [x] All File CRUD tools have outputSchema (3 tools)
- [ ] All Git Operations tools have outputSchema (14 tools)
- [ ] deactivate_repository has comprehensive TL;DR description
- [ ] sync_repository has comprehensive TL;DR description
- [ ] manage_composite_repository has comprehensive TL;DR description
- [ ] Only ONE cidx_quick_reference definition exists
- [ ] get_tool_categories tool exists and returns categorized list
- [ ] first_time_user_guide tool exists and returns onboarding content
- [ ] Python syntax valid (no JSON errors in schemas)
- [ ] All permission matrix info matches actual permissions in auth system

---

## Notes

- This is documentation-only work (no functional code changes)
- All schemas describe existing API responses
- Changes improve user experience by reducing confusion and discovery friction
- Repository alias documentation at top provides critical context for all tools

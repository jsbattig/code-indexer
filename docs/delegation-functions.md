# Claude Delegation Functions

Execute AI workflows against protected repositories without exposing source code to the client.

## Table of Contents

- [Overview](#overview)
- [Key Value Proposition](#key-value-proposition)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [MCP Tools Reference](#mcp-tools-reference)
- [Function Definition Format](#function-definition-format)
- [Workflow](#workflow)
- [Security Model](#security-model)
- [Troubleshooting](#troubleshooting)

## Overview

Claude Delegation enables CIDX to delegate AI work to an external **Claude Server** instance. This pattern allows:

- **Protected Repository Access**: AI can work on repositories not directly exposed to the MCP client
- **Group-Based Access Control**: Functions are restricted by user group membership
- **Async Execution**: Long-running AI tasks execute in the background with callback-based completion
- **Template-Based Workflows**: Reusable prompt templates with parameter substitution

### When to Use

- Source code should NOT be exposed directly to the client (security/compliance)
- Work needs to happen on repositories managed by a centralized Claude Server
- Standardized AI workflows need to be executed by different users
- Long-running AI tasks need async execution with progress tracking

## Key Value Proposition

### Problem: Protected Source Code

Many organizations cannot expose source code directly to AI assistants due to:

- Security policies prohibiting code exposure to external services
- Compliance requirements (SOC2, HIPAA, PCI-DSS)
- Intellectual property concerns
- Network segmentation requirements

### Solution: Delegation Pattern

Claude Delegation solves this by:

1. **Indirection**: MCP client calls CIDX, CIDX calls Claude Server, Claude Server has code access
2. **Function Templates**: Pre-approved prompt templates define what AI can do
3. **Group Security**: Users can only execute functions their groups permit
4. **No Code Exposure**: The MCP client never sees the source code - only the AI's response

```
MCP Client (Claude.ai)     CIDX Server           Claude Server
        |                      |                      |
        | "Run code_review"    |                      |
        |--------------------->|                      |
        |                      | Execute function     |
        |                      |--------------------->|
        |                      |                      | (Has repo access)
        |                      |                      | (Runs Claude)
        |                      |<-- Callback ---------|
        |<-- Result -----------|                      |
        |                      |                      |
   (Never sees code)      (Orchestrator)        (Has code)
```

## Architecture

### Component Overview

| Component | Location | Purpose |
|-----------|----------|---------|
| MCP Tools | `mcp/tools.py` | Tool definitions exposed to MCP clients |
| Handlers | `mcp/handlers.py` | Request processing logic |
| Function Loader | `services/delegation_function_loader.py` | Parses function definitions from markdown |
| Template Processor | `services/prompt_template_processor.py` | Renders Jinja2-style templates |
| Job Tracker | `services/delegation_job_tracker.py` | Async job tracking with Futures |
| Claude Client | `clients/claude_server_client.py` | HTTP client for Claude Server API |
| Callback Router | `routers/delegation_callbacks.py` | Receives completion callbacks |

### Data Flow

```
Function Repository (Golden Repo)
        |
        v
DelegationFunctionLoader -----> DelegationFunction objects
        |                            |
        |                            v
        |                    PromptTemplateProcessor
        |                            |
        v                            v
ClaudeServerClient.create_job(rendered_prompt)
        |
        v
Claude Server (external) -----> Job execution
        |
        v
Callback POST to /api/delegation/callback/{job_id}
        |
        v
DelegationJobTracker.complete_job() -----> Resolves asyncio Future
        |
        v
poll_delegation_job returns result
```

## Configuration

### Prerequisites

1. **Claude Server** running and accessible from CIDX server
2. **Function Repository** - Golden repo containing function definitions
3. **User Groups** configured in CIDX for access control

### Server Configuration

Configure delegation via the CIDX Web UI (Settings > Claude Delegation) or directly in the config file:

**Location**: `~/.cidx-server/claude_delegation.json`

```json
{
  "function_repo_alias": "delegation-functions",
  "claude_server_url": "http://claude-server.internal:5185",
  "claude_server_username": "cidx_service",
  "claude_server_credential_type": "password",
  "claude_server_credential": "<encrypted>",
  "skip_ssl_verify": false,
  "cidx_callback_url": "http://cidx-server.internal:8000"
}
```

| Field | Description |
|-------|-------------|
| `function_repo_alias` | Golden repo alias containing function definitions |
| `claude_server_url` | Base URL of Claude Server |
| `claude_server_username` | Service account username |
| `claude_server_credential_type` | `password` or `token` |
| `claude_server_credential` | Encrypted credential (use Web UI) |
| `skip_ssl_verify` | Skip SSL verification (testing only) |
| `cidx_callback_url` | URL Claude Server uses for callbacks |

### Callback URL Requirements

The `cidx_callback_url` must be reachable from Claude Server. For Claude Server's `AllowPrivateIps` setting:

- **Production**: Use HTTPS with valid certificates, `AllowPrivateIps: false`
- **Development**: HTTP allowed, set `AllowPrivateIps: true` in Claude Server config

## MCP Tools Reference

### list_delegation_functions

**Purpose**: Discover available functions based on user's group membership.

**When to Use**: When you need to discover what delegation functions are available before executing one.

**Input**:
```json
{}
```

**Output**:
```json
{
  "success": true,
  "functions": [
    {
      "name": "code_review",
      "description": "Perform code review on specified files",
      "parameters": [
        {"name": "file_paths", "required": true, "type": "string"},
        {"name": "focus_areas", "required": false, "type": "string"}
      ]
    }
  ]
}
```

**Security**: Only functions where user's groups intersect with `allowed_groups` are returned.

---

### execute_delegation_function

**Purpose**: Execute a delegation function by creating a job on Claude Server.

**When to Use**: After discovering functions via `list_delegation_functions`, execute a specific function.

**Input**:
```json
{
  "function_name": "code_review",
  "parameters": {
    "file_paths": "src/auth/*.py",
    "focus_areas": "security, error handling"
  },
  "prompt": "Optional additional context",
  "enable_callback": true
}
```

**Output**:
```json
{
  "success": true,
  "job_id": "cdd38abc-a240-47d7-a25f-2a63f1d37d10"
}
```

**Execution Flow**:
1. Load function definition from repository
2. Validate user has access (group membership)
3. Validate required parameters provided
4. Ensure required repositories registered in Claude Server
5. Render prompt template with parameters
6. Create and start job on Claude Server
7. Register callback URL for completion notification
8. Return job_id for async polling

---

### poll_delegation_job

**Purpose**: Wait for job completion via callback mechanism.

**When to Use**: After `execute_delegation_function` returns a job_id.

**Input**:
```json
{
  "job_id": "cdd38abc-a240-47d7-a25f-2a63f1d37d10",
  "timeout_seconds": 45
}
```

**Output (waiting)**:
```json
{
  "status": "waiting",
  "message": "Job still running, callback not yet received",
  "continue_polling": true
}
```

**Output (completed)**:
```json
{
  "status": "completed",
  "result": "The AI's response...",
  "continue_polling": false
}
```

**Output (failed)**:
```json
{
  "status": "failed",
  "error": "Error message",
  "continue_polling": false
}
```

**Polling Strategy**:
1. Call with job_id from execute_delegation_function
2. Check `continue_polling` field:
   - `true`: Job in progress, call again after delay
   - `false`: Job completed or failed, stop polling
3. On timeout: Returns `status: "waiting"` - safe to retry same job_id

**Timeout Behavior**:
- Default: 45 seconds (safely below MCP's 60s timeout)
- Range: 0.01-300 seconds
- On timeout, job stays in tracker - retry with same job_id gets cached result

## Function Definition Format

Functions are defined as Markdown files with YAML frontmatter in the function repository.

### File Structure

```markdown
---
name: function_name
description: Human-readable description
allowed_groups:
  - admins
  - developers
required_repos:
  - alias: my-repo
    remote: https://github.com/org/repo.git
    branch: main
impersonation_user: service_account  # Optional
parameters:
  - name: param1
    description: Parameter description
    required: true
    type: string
  - name: param2
    description: Optional parameter
    required: false
    type: string
---

# Function Prompt Template

This is the prompt sent to Claude Server.

Parameters are substituted using {{ param1 }} syntax.

User's additional prompt: {{ user_prompt }}
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique function identifier |
| `description` | No | Human-readable description |
| `allowed_groups` | Yes | List of groups that can execute |
| `required_repos` | No | Repositories needed for execution |
| `impersonation_user` | No | User identity for Claude Server queries |
| `parameters` | No | Input parameters with validation |

### Template Syntax

- `{{ param_name }}` - Substitutes parameter value
- `{{ user_prompt }}` - Substitutes user's additional prompt
- Flexible whitespace: `{{param}}`, `{{ param }}`, `{{  param  }}` all work

### Impersonation Instruction

All rendered prompts are automatically prepended with:

```
CRITICAL: As your FIRST action before any other operations, call the MCP tool
`set_session_impersonation` with username "{impersonation_user}". All your
subsequent queries to CIDX must use this impersonated identity.
```

This ensures Claude Server queries use the correct user context.

## Workflow

### Complete Flow Diagram

```
1. DISCOVER
   MCP Client                    CIDX Server
       |  list_delegation_functions  |
       |--------------------------->|
       |  [functions filtered by    |
       |   user groups]             |
       |<---------------------------|

2. EXECUTE
   MCP Client                    CIDX Server                Claude Server
       |  execute_delegation_function |                           |
       |  {function_name, params}     |                           |
       |----------------------------->|                           |
       |                              |-- authenticate() -------->|
       |                              |<-- JWT token -------------|
       |                              |-- create_job(prompt) ---->|
       |                              |<-- {jobId} ---------------|
       |                              |-- register_callback() --->|
       |                              |-- start_job() ----------->|
       |  {success: true, job_id}     |                           |
       |<-----------------------------|                           |

3. POLL (with callback)
   MCP Client                    CIDX Server                Claude Server
       |  poll_delegation_job         |                           |
       |  {job_id, timeout: 45}       |                           |
       |----------------------------->|                           |
       |                              |  [wait on Future]         |
       |                              |                           |
       |                              |  (Claude finishes work)   |
       |                              |                           |
       |                              |<-- POST /callback/{id} ---|
       |                              |  [resolve Future]         |
       |                              |  [cache result]           |
       |  {status: completed,         |                           |
       |   result: "..."}             |                           |
       |<-----------------------------|                           |

4. RETRY (on timeout)
   MCP Client                    CIDX Server
       |  poll_delegation_job         |
       |  {job_id, timeout: 45}       |
       |----------------------------->|
       |                              |  [check cache - HIT]
       |  {status: completed,         |
       |   result: "..."}             |
       |<-----------------------------|
```

### Timeout and Retry Behavior

The callback-based completion is designed to be timeout-safe:

1. **First poll**: Waits up to `timeout_seconds` for callback
2. **Timeout occurs**: Returns `status: "waiting"`, job stays in tracker
3. **Callback arrives**: Result cached in PayloadCache
4. **Retry poll**: Checks cache first, returns cached result immediately

This means:
- MCP client can use short timeouts (< 60s for MCP protocol limits)
- Jobs are never lost due to timeout
- Results are cached for efficient retry

## Security Model

### Group-Based Access Control

1. **Function Definition**: Each function specifies `allowed_groups`
2. **User Groups**: Users belong to groups managed by CIDX GroupManager
3. **Access Check**: User can execute function if `user_groups ∩ allowed_groups ≠ ∅`

### Impersonation Support

When an admin impersonates another user:
- `list_delegation_functions` uses impersonated user's groups
- `execute_delegation_function` uses impersonated user's groups
- The impersonation instruction in prompts uses appropriate identity

### Credential Protection

- Claude Server credentials are encrypted in configuration
- Credentials never exposed to MCP clients
- JWT tokens managed internally by ClaudeServerClient

### Network Security

- Claude Server should be on internal network (not exposed to internet)
- Callback URL should use HTTPS in production
- `skip_ssl_verify` only for development/testing

## Troubleshooting

### "Claude Delegation not configured"

**Cause**: Delegation config missing or incomplete

**Solution**:
1. Check `~/.cidx-server/claude_delegation.json` exists
2. Verify all required fields are set
3. Use Web UI to configure (Settings > Claude Delegation)

### "Function not found"

**Cause**: Function doesn't exist or user doesn't have access

**Solution**:
1. Verify function exists in function repository
2. Check function's `allowed_groups` includes user's group
3. Use `list_delegation_functions` to see accessible functions

### "Job creation failed: HTTP 400"

**Cause**: Claude Server rejected the request

**Common causes**:
- Repository not registered or in failed state
- Invalid repository alias in function definition
- Claude Server callback validation rejecting URL

**Solution**:
1. Check Claude Server logs for detailed error
2. Verify repository exists and is cloned: `GET /repositories/{alias}`
3. For private IP callbacks, ensure `AllowPrivateIps: true` in Claude Server

### "Callback not received"

**Cause**: Claude Server cannot reach CIDX callback URL

**Solution**:
1. Verify `cidx_callback_url` is reachable from Claude Server
2. Check network/firewall allows connection
3. For HTTPS, verify SSL certificate is valid
4. Test connectivity: `curl -X POST {callback_url}/api/delegation/callback/test`

### "Job not found or already completed"

**Cause**: Job ID invalid or already processed

**Solution**:
1. Verify job_id matches what `execute_delegation_function` returned
2. Job may have completed and been cleaned up - execute new function
3. Check if callback was received (job completes and removes from tracker)

---

## Related Documentation

- [AI Integration Guide](ai-integration.md) - Overall AI platform integration
- [Server Deployment](server-deployment.md) - CIDX server setup
- [Configuration Guide](configuration.md) - Server configuration options
- [Architecture](architecture.md) - System architecture overview

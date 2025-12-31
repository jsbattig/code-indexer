# CIDX MCP Bridge for Claude Desktop

Complete guide to connecting Claude Desktop to CIDX server using the MCP Bridge.

## Table of Contents

- [Overview](#overview)
- [What is MCP Bridge](#what-is-mcp-bridge)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Authentication](#authentication)
- [Available Tools](#available-tools)
- [Usage Examples](#usage-examples)
- [Troubleshooting](#troubleshooting)

## Overview

**MCP Bridge** connects Claude Desktop to CIDX server, enabling semantic code search directly within AI conversations.

**Key Features**:
- **MCP Protocol 2024-11-05** - Standard Model Context Protocol implementation
- **Credential-Based Authentication** - Secure encrypted credential storage with automatic token refresh
- **75 MCP Tools** - Comprehensive code search, navigation, and git operations
- **Remote Access** - Query centralized team code repositories
- **Permission Controls** - Role-based access (admin, power_user, normal_user)

**Use Case**: Team-wide semantic code search with Claude Desktop interface.

## What is MCP Bridge

### Architecture

```
Claude Desktop → MCP Bridge → CIDX Server → Golden Repositories
                      ↓             ↓                ↓
                MCP Protocol   JWT Tokens      Semantic Indexes
                2024-11-05    (auto-refresh)
```

**MCP Bridge** is a Python module that:
1. Implements MCP (Model Context Protocol) server interface
2. Proxies requests from Claude Desktop to CIDX server
3. Handles credential-based authentication with encrypted storage
4. Manages automatic token refresh and session state
5. Translates MCP tool calls to CIDX REST API requests

**Why Needed**: Claude Desktop speaks MCP protocol, CIDX server provides REST API. Bridge translates between the two.

## Prerequisites

### Server Requirements

**CIDX Server** must be deployed and accessible:
- CIDX server v8.0+ running
- HTTPS endpoint accessible (e.g., https://your-server.com:8383)
- Golden repositories indexed
- User accounts configured with username/password authentication

See [Server Deployment Guide](../server-deployment.md) for server setup.

### Client Requirements

**Claude Desktop**:
- Claude Desktop app installed (macOS, Windows, or Linux)
- MCP configuration support
- Network access to CIDX server

**Platforms**:
- macOS (Intel or Apple Silicon)
- Windows (x64)
- Linux (x64)

## Installation

### Step 1: Install CIDX with MCP Bridge

**Via pip** (recommended):
```bash
# Clone repository
git clone https://github.com/jsbattig/code-indexer.git
cd code-indexer

# Install with pip
pip3 install -e .

# Verify installation
python3 -m code_indexer.mcpb --version
```

**Via pipx** (isolated environment):
```bash
pipx install git+https://github.com/jsbattig/code-indexer.git@v8.0.0
python3 -m code_indexer.mcpb --version
```

### Step 2: Set Up Credentials

Run the credential setup utility:
```bash
python3 -m code_indexer.mcpb --setup-credentials
```

This will prompt for:
- Username
- Password (entered twice for confirmation)

Credentials are stored encrypted in:
- `~/.mcpb/credentials.enc` (encrypted credentials)
- `~/.mcpb/encryption.key` (encryption key, permissions 600)

## Configuration

### Step 1: Create Server Configuration

Create `~/.mcpb/config.json` with your CIDX server URL:

```bash
# macOS/Linux
mkdir -p ~/.mcpb
cat > ~/.mcpb/config.json << EOF
{
  "server_url": "https://your-server.com:8383"
}
EOF

# Windows (PowerShell)
mkdir $env:USERPROFILE\.mcpb -Force
'{"server_url": "https://your-server.com:8383"}' | Out-File -FilePath $env:USERPROFILE\.mcpb\config.json -Encoding utf8
```

Replace `https://your-server.com:8383` with your actual CIDX server URL.

### Step 2: Configure Claude Desktop

**Location**: Claude Desktop MCP configuration file

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**Linux**: `~/.config/Claude/claude_desktop_config.json`

**Configuration**:
```json
{
  "mcpServers": {
    "cidx": {
      "command": "python3",
      "args": [
        "-m",
        "code_indexer.mcpb"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

**Note**: Ensure `python3` is in your PATH. On Windows, use `python` instead of `python3`.

**Alternative (using wrapper script)**:

For more control, create a wrapper script at `~/.mcpb/mcpb-wrapper.sh`:

```bash
#!/bin/bash
export HOME=/your/home/directory
export PYTHONPATH=/path/to/code-indexer/src
export PYTHONUNBUFFERED=1
exec python3 -m code_indexer.mcpb "$@"
```

Make it executable:
```bash
chmod +x ~/.mcpb/mcpb-wrapper.sh
```

Then configure Claude Desktop to use the wrapper:
```json
{
  "mcpServers": {
    "cidx": {
      "command": "/Users/yourname/.mcpb/mcpb-wrapper.sh"
    }
  }
}
```

### Step 3: Restart Claude Desktop

After editing configuration:
1. Quit Claude Desktop completely
2. Restart Claude Desktop
3. MCP Bridge will auto-start when Claude Desktop launches

## Authentication

### Authentication Flow

MCP Bridge uses credential-based authentication with automatic token management:

**Initial Setup** (one-time):
1. Run `python3 -m code_indexer.mcpb --setup-credentials`
2. Enter username and password (encrypted and stored locally)
3. Credentials saved to `~/.mcpb/credentials.enc` (encrypted)

**First Request** (automatic):
1. Claude Desktop launches MCP Bridge
2. MCP Bridge loads encrypted credentials
3. Sends HTTP POST to `/auth/login` endpoint
4. Server returns JWT access_token and refresh_token
5. Tokens saved to `~/.mcpb/config.json`

**Token Storage Format**:
```json
{
  "server_url": "https://your-server.com:8383",
  "bearer_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Note**: Token expiry is embedded in JWT payload, not stored separately.

**Automatic Token Refresh**:
- On 401 (Unauthorized) errors, MCP Bridge automatically:
  1. Uses refresh_token to get new access_token (if available)
  2. Falls back to auto-login using encrypted credentials
  3. Updates `~/.mcpb/config.json` with new tokens
  4. Retries the original request transparently

**Server-Side OAuth 2.1**:
The CIDX server implements OAuth 2.1 with authorization_code grant and PKCE for browser-based clients. However, MCP Bridge uses the simpler credential-based flow for unattended operation.

### Re-authentication

**When Needed**:
- Password changed on server
- Credentials corrupted or deleted
- Token refresh failed repeatedly

**Manual Re-authentication**:
```bash
# Option 1: Re-run credential setup
python3 -m code_indexer.mcpb --setup-credentials

# Option 2: Delete stored credentials and tokens
rm ~/.mcpb/credentials.enc ~/.mcpb/encryption.key ~/.mcpb/config.json
python3 -m code_indexer.mcpb --setup-credentials

# Then restart Claude Desktop
```

## Available Tools

MCP Bridge exposes **75 tools** to Claude Desktop.

### Tool Categories

**Search & Discovery** (5 tools):
- `search_code` - Semantic/FTS/temporal search
- `regex_search` - Pattern matching without indexes
- `browse_directory` - List files with metadata
- `list_files` - Flat file listing
- `get_file_content` - Read file contents

**SCIP Code Intelligence** (7 tools):
- `scip_definition` - Find symbol definitions
- `scip_references` - Find symbol usages
- `scip_dependencies` - Find dependencies
- `scip_dependents` - Find dependents
- `scip_impact` - Impact analysis
- `scip_callchain` - Trace call chains
- `scip_context` - Get symbol context

**Git History & Exploration** (9 tools):
- `git_log` - Commit history
- `git_show_commit` - Commit details
- `git_diff` - Compare revisions
- `git_blame` - Line attribution
- `git_file_at_revision` - View file at commit
- `git_file_history` - File commit history
- `git_search_commits` - Search commit messages
- `git_search_diffs` - Search code changes
- `directory_tree` - Visual directory structure

**Git Operations** (15 tools):
- `git_status`, `git_stage`, `git_unstage`, `git_commit`, `git_push`, `git_pull`, `git_fetch`
- `git_reset`, `git_clean`, `git_merge_abort`, `git_checkout_file`
- `git_branch_list`, `git_branch_create`, `git_branch_switch`, `git_branch_delete`

**File CRUD** (4 tools):
- `create_file` - Create new file
- `edit_file` - Edit existing file
- `delete_file` - Delete file
- `trigger_reindex` - Manual re-indexing

**Repository Management** (15 tools):
- `list_repositories`, `list_global_repos`, `activate_repository`, `deactivate_repository`
- `get_repository_status`, `global_repo_status`, `sync_repository`, `switch_branch`
- `get_branches`, `manage_composite_repository`
- `add_golden_repo`, `remove_golden_repo`, `refresh_golden_repo`
- `add_golden_repo_index`, `get_golden_repo_indexes`

**System & Admin** (20 tools):
- User management (5 tools)
- SSH key management (6 tools)
- Configuration (4 tools)
- Status/health (5 tools)

**Total**: 75 tools across 7 categories

For complete tool reference, see [AI Integration Guide](../ai-integration.md).

## Usage Examples

### Example 1: Semantic Code Search in Conversation

**User**: "Where is the JWT authentication code?"

**Claude** (via MCP Bridge):
```
I'll search for JWT authentication in the codebase.
<Uses search_code tool>

The JWT authentication is implemented in:
- backend-global: src/auth/jwt_validator.py (lines 42-87)
- backend-global: src/middleware/auth.py (lines 15-35)

The main validation logic is in jwt_validator.py...
```

### Example 2: SCIP Code Navigation

**User**: "Find all usages of the DatabaseManager class"

**Claude** (via MCP Bridge):
```
<Uses scip_references tool with symbol="DatabaseManager">

DatabaseManager is used in 12 files:
1. src/services/user_service.py - Line 15 (import)
2. src/services/order_service.py - Line 22 (instantiation)
...
```

### Example 3: Git History Analysis

**User**: "When was OAuth integration added?"

**Claude** (via MCP Bridge):
```
<Uses search_code with time_range_all and query="OAuth integration">

OAuth integration was added in:
- Commit abc123 on 2024-03-15 by John Doe
- File: src/auth/oauth_handler.py
- Initial implementation with Google OAuth support
```

### Example 4: Multi-Repository Search

**User**: "Search for authentication logic across all backend services"

**Claude** (via MCP Bridge):
```
<Uses search_code with repository_alias=['backend-api-global', 'backend-auth-global']>

Found authentication logic in:

backend-api-global:
- src/middleware/auth_middleware.py (score: 0.92)

backend-auth-global:
- src/services/auth_service.py (score: 0.95)
- src/validators/token_validator.py (score: 0.88)
```

## Troubleshooting

### MCP Bridge Not Starting

**Symptom**: Claude Desktop shows "MCP server failed to start"

**Check**:
1. **Binary permissions**:
   ```bash
   chmod +x /usr/local/bin/cidx-mcpb
   ```

2. **Binary exists at configured path**:
   ```bash
   which cidx-mcpb
   # Should match path in claude_desktop_config.json
   ```

3. **Server URL accessible**:
   ```bash
   curl https://your-server.com:8383/health
   # Should return {"status": "healthy"}
   ```

4. **Check Claude Desktop logs**:
   - macOS: `~/Library/Logs/Claude/`
   - Windows: `%APPDATA%\Claude\logs\`
   - Linux: `~/.config/Claude/logs/`

### Authentication Failures

**Symptom**: Browser auth flow fails or repeats

**Solutions**:

1. **Clear existing tokens**:
   ```bash
   rm ~/.mcpb/config.json
   ```

2. **Check server OAuth configuration**:
   ```bash
   curl https://your-server.com:8383/api/v1/auth/status
   ```

3. **Verify redirect URI matches server config**:
   - Default: `http://localhost:8080/oauth/callback`

4. **Check firewall/network**:
   - Ensure localhost:8080 not blocked
   - Ensure server HTTPS accessible

### Tool Execution Errors

**Symptom**: Claude shows "Tool execution failed"

**Check**:

1. **Token validity**:
   ```bash
   # Check token expiry in config
   cat ~/.mcpb/config.json
   ```

2. **User permissions**:
   - normal_user: Can only query
   - power_user: Can activate repos, write files
   - admin: Full access

3. **Repository access**:
   ```bash
   # List accessible repositories via REST API
   curl -H "Authorization: Bearer YOUR_TOKEN" \
     https://your-server.com:8383/api/v1/repositories
   ```

4. **Server logs**:
   ```bash
   # Check CIDX server logs for errors
   journalctl -u cidx-server -f
   ```

### Slow Tool Responses

**Symptom**: Tools take >10 seconds to respond

**Causes**:
- Cold cache (first query on repository)
- Large result sets
- Network latency
- Server under load

**Solutions**:

1. **Warm cache**:
   - First query on repo loads indexes (~277ms)
   - Subsequent queries use cache (<1ms)

2. **Reduce result limits**:
   - Use `limit=5` for initial queries
   - Increase if needed

3. **Check network latency**:
   ```bash
   ping your-server.com
   # Should be <50ms for good performance
   ```

4. **Monitor server performance**:
   ```bash
   curl https://your-server.com:8383/cache/stats
   # Check cache hit ratio (should be >95%)
   ```

### Configuration Issues

**Symptom**: Configuration not loading

**Check**:

1. **JSON syntax**:
   ```bash
   # Validate JSON
   python3 -c "import json; json.load(open('~/Library/Application Support/Claude/claude_desktop_config.json'))"
   ```

2. **Path expansion**:
   - Use absolute paths: `/Users/name/.mcpb` not `~/.mcpb`
   - Windows: Use double backslashes `C:\\Users\\name\\.mcpb`

3. **Restart required**:
   - Always restart Claude Desktop after config changes

### SSL/TLS Certificate Errors

**Symptom**: "Certificate verification failed"

**Solutions**:

1. **Self-signed certificates**:
   - Not recommended for production
   - Add to system trust store

2. **Let's Encrypt certificates**:
   - Ensure full certificate chain installed on server
   - Check intermediate certificates

3. **Verify server certificate**:
   ```bash
   openssl s_client -connect your-server.com:8383 -showcerts
   ```

---

## Next Steps

- **Server Setup**: [Server Deployment Guide](../server-deployment.md)
- **Authentication Details**: [Architecture Guide](../architecture.md)
- **Tool Reference**: [AI Integration Guide](../ai-integration.md)
- **Main Documentation**: [README](../../README.md)

---

## Related Documentation

- **Local CLI Integration**: [AI Integration Guide](../ai-integration.md)
- **Operating Modes**: [Operating Modes Guide](../operating-modes.md)
- **Query Guide**: [Query Guide](../query-guide.md)

---


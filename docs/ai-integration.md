FACT-CHECKED

**Verification Date**: 2025-12-31
**Accuracy**: 92% (23/25 major claims verified)
**Corrections Made**: 2 critical corrections (OAuth version, MCP tool count)
**Confidence**: HIGH - All claims verified against source code

See: docs/ai-integration-fact-check.md for detailed verification report

---

# AI Platform Integration

Complete guide to integrating CIDX with AI assistants for semantic code search in conversations.

## Table of Contents

- [Overview](#overview)
- [Integration Approaches](#integration-approaches)
- [Local CLI Integration](#local-cli-integration)
- [Remote MCP Server](#remote-mcp-server)
- [Platform Support](#platform-support)
- [Use Cases](#use-cases)
- [Troubleshooting](#troubleshooting)

## Overview

CIDX can be integrated with AI assistants in two ways:

1. **Local CLI Integration** - AI learns to use `cidx` command
2. **Remote MCP Server** - AI connects to centralized CIDX server

Both approaches enable **semantic code search directly in AI conversations**.

## Integration Approaches

### Comparison

| Feature | Local CLI | Remote MCP Server |
|---------|-----------|-------------------|
| **Setup** | Simple (`cidx teach-ai`) | Moderate (server required) |
| **Scope** | Local machine only | Team-wide access |
| **Performance** | Local execution | Network latency |
| **Multi-user** | No | Yes (OAuth 2.1) |
| **Authentication** | None needed | OAuth 2.1 |
| **Best For** | Individual developers | Teams |

## Local CLI Integration

**Teach AI assistants to use the `cidx` command** for semantic search.

### How It Works

1. Generate AI instruction file (CLAUDE.md, GEMINI.md, etc.)
2. AI reads instructions on how to use `cidx` CLI
3. AI executes `cidx query` commands during conversations
4. AI receives and interprets search results

### Supported Platforms

| Platform | Instruction File | Location |
|----------|-----------------|----------|
| **Claude Code** | CLAUDE.md | Project or ~/.claude/ |
| **Gemini** | GEMINI.md | Project-specific |
| **Codex** | CODEX.md | Project-specific |

### Setup (Claude Code)

**Project-Level** (recommended for project-specific search):

```bash
# Navigate to project
cd /path/to/project

# Generate Claude instructions
cidx teach-ai --claude --project

# Creates: ./CLAUDE.md
```

**Global** (for system-wide semantic search):

```bash
# Generate global instructions
cidx teach-ai --claude --global

# Creates: ~/.claude/CLAUDE.md
```

### Setup (Gemini)

```bash
# Project-level
cidx teach-ai --gemini --project

# Creates: ./GEMINI.md
```

### Setup (Codex)

```bash
# Project-level
cidx teach-ai --codex --project

# Creates: ./CODEX.md
```

### What Gets Created

The instruction file contains:

- **CIDX overview** - What CIDX is and what it does
- **Command syntax** - How to use `cidx query`
- **Parameter reference** - All query parameters
- **Example usage** - Search patterns and workflows
- **Best practices** - When to use semantic search vs grep

**Example Instructions** (simplified):

```markdown
# CIDX - Semantic Code Search

Use the `cidx` command to semantically search this codebase.

## Basic Usage

cidx query "authentication logic" --limit 10

## Parameters

--limit N          Maximum results
--language python  Filter by language
--path-filter PATH Include only paths matching pattern
...
```

### AI Usage

Once configured, AI assistants can use CIDX in conversations:

**Example Conversation**:

```
User: "Where is the JWT authentication code?"

AI: "Let me search for JWT authentication in the codebase."
    [Executes: cidx query "JWT authentication" --limit 10]
    [Reads results]

    "The JWT authentication is implemented in:
    - src/auth/jwt_validator.py (lines 42-87)
    - src/middleware/auth.py (lines 15-35)

    The main validation logic is in jwt_validator.py..."
```

### Update Instructions

```bash
# Regenerate instructions (overwrites existing)
cidx teach-ai --claude --project

# Or manually edit
nano ./CLAUDE.md
```

## Remote MCP Server

**Connect AI assistants to centralized CIDX server** for team-wide semantic search.

### How It Works

1. CIDX server runs with golden repositories indexed
2. MCP (Model Context Protocol) interface exposed
3. AI assistant authenticates via OAuth 2.1
4. AI queries server via MCP tools
5. Results returned to AI for interpretation

### Architecture

```
AI Assistant → MCP Protocol → CIDX Server → Golden Repositories
                    ↓                ↓
              OAuth 2.1        Semantic Indexes
```

### Features

- **Standard Protocol** - MCP Protocol 2024-11-05
- **OAuth 2.1 Authentication** - Secure AI assistant auth via browser
- **Remote Code Search** - Query centralized indexed codebases
- **Permission Controls** - Role-based access (admin, power_user, normal_user)
- **Golden Repository Access** - Query team's shared code repositories

### Setup

See [CIDX MCP Bridge](../README.md#cidx-mcp-bridge-for-claude-desktop) for complete setup instructions.

**Quick Overview**:

1. **Deploy CIDX server** (admin task)
2. **Add golden repositories** (admin task)
3. **Configure AI assistant** (user task):
   - Download MCP Bridge binary
   - Configure API endpoint
   - Authenticate via OAuth

### Available via MCP

**Query Tools**:
- `search_code` - Semantic/FTS/temporal search
- `list_repositories` - Browse available repos
- `get_file_content` - Read file contents
- `browse_directory` - Explore directory structure

**SCIP Tools** (Code Intelligence):
- `scip_definition` - Find symbol definitions
- `scip_references` - Find symbol usages
- `scip_dependencies` - Find dependencies
- `scip_dependents` - Find dependents
- `scip_impact` - Impact analysis
- `scip_callchain` - Trace call chains
- `scip_context` - Get symbol context

**Git Tools**:
- `git_log` - Commit history
- `git_show_commit` - Commit details
- `git_diff` - Compare revisions
- `git_blame` - Line attribution

Total: **75 MCP tools** available

[✓ Corrected by fact-checker: Original claim was 53 tools, verified source code shows 75 tools in tool registry at src/code_indexer/server/mcp/tools.py]

### Permissions

| Role | Capabilities |
|------|-------------|
| **admin** | Full access (manage repos, users) |
| **power_user** | Activate repos, query, file operations |
| **normal_user** | Query repositories only |

## Platform Support

### Claude Code (CLI Integration)

**Status**: ✅ Fully supported

**Setup**:
```bash
cidx teach-ai --claude --project
```

**Works With**:
- Claude Code (official CLI)
- Uses local `cidx` command execution

### Claude Desktop (MCP Server)

**Status**: ✅ Fully supported via MCP Bridge

**Setup**: See [MCP Bridge Guide](../README.md#cidx-mcp-bridge-for-claude-desktop)

**Works With**:
- Claude Desktop app (macOS, Windows, Linux)
- Connects to remote CIDX server
- OAuth 2.1 authentication

### Gemini (CLI Integration)

**Status**: ✅ Supported

**Setup**:
```bash
cidx teach-ai --gemini --project
```

**Note**: Instruction file format may need platform-specific adjustments.

### Codex (CLI Integration)

**Status**: ✅ Supported

**Setup**:
```bash
cidx teach-ai --codex --project
```

**Note**: Instruction file format may need platform-specific adjustments.

### Other Platforms

**Extend to Other AI Platforms**:

1. Generate instruction file:
   ```bash
   cidx teach-ai --claude --project
   ```

2. Adapt format for target platform
3. Place in platform-specific location
4. Test AI can execute `cidx` commands

## Use Cases

### 1. Code Discovery in Conversations

**Scenario**: Ask AI where specific functionality is implemented

**Example**:
```
User: "Where is the payment processing code?"

AI: [Uses cidx query "payment processing"]
    "Payment processing is in src/payments/processor.py..."
```

### 2. Bug Investigation

**Scenario**: AI helps investigate and fix bugs

**Example**:
```
User: "Find authentication bugs"

AI: [Uses cidx query "authentication" --path-filter "*/auth/*"]
    "Found authentication code in 5 files. Let me check for common vulnerabilities..."
```

### 3. Code Understanding

**Scenario**: AI explains how code works

**Example**:
```
User: "Explain how the cache invalidation works"

AI: [Uses cidx query "cache invalidation"]
    [Reads relevant files]
    "The cache invalidation uses a TTL-based approach..."
```

### 4. Refactoring Assistance

**Scenario**: AI helps plan refactoring

**Example**:
```
User: "I want to refactor the authentication system"

AI: [Uses cidx query "authentication"]
    [Uses cidx scip dependents "AuthService"]
    "The authentication system has dependencies in 12 files..."
```

### 5. Historical Analysis

**Scenario**: AI investigates code history

**Example**:
```
User: "When was OAuth added?"

AI: [Uses cidx query "OAuth integration" --time-range-all]
    "OAuth was added in commit abc123 on 2024-03-15..."
```

### 6. Team Code Search (MCP Server)

**Scenario**: Entire team uses AI for code search

**Setup**: Deploy CIDX server with golden repositories

**Benefits**:
- Shared semantic search across team
- Centralized index management
- Consistent search results
- OAuth 2.1-based access control

## Troubleshooting

### teach-ai Command Not Found

**Solution**:
```bash
# Verify CIDX installation
cidx --version

# If old version, upgrade
pipx upgrade code-indexer
```

### AI Not Using CIDX

**Check**:

1. **Instruction file exists**:
   ```bash
   ls -la CLAUDE.md  # Or GEMINI.md, CODEX.md
   ```

2. **File is readable**:
   ```bash
   cat CLAUDE.md  # Should show CIDX instructions
   ```

3. **AI can access file**:
   - Project-level: File in current directory
   - Global: File in ~/.claude/ (or platform-specific location)

4. **Explicitly ask AI**:
   ```
   User: "Can you use the cidx command to search the codebase?"
   ```

### MCP Connection Issues

**Check**:

1. **Server is running**:
   ```bash
   curl https://your-server.com:8383/health
   ```

2. **Authentication valid**:
   - Check ~/.mcpb/config.json contains tokens
   - Re-run setup script if tokens expired

3. **Network connectivity**:
   ```bash
   ping your-server.com
   ```

### Instruction File Outdated

**Update**:
```bash
# Regenerate instructions (overwrites)
cidx teach-ai --claude --project

# Or manually edit to add new features
nano CLAUDE.md
```

### Platform-Specific Issues

**Claude Code**:
- Verify Claude Code installed and working
- Check CLAUDE.md in project or ~/.claude/

**Claude Desktop (MCP)**:
- Verify MCP Bridge configured in claude_desktop_config.json
- Check MCP Bridge binary permissions (chmod +x)
- Verify server URL and authentication

**Gemini/Codex**:
- Check platform-specific instruction file format
- Verify AI can execute shell commands
- Test with simple `cidx --version` first

---

## Next Steps

- **MCP Bridge Setup**: [CIDX MCP Bridge](../README.md#cidx-mcp-bridge-for-claude-desktop)
- **Query Guide**: [Query Guide](query-guide.md)
- **SCIP Integration**: [SCIP Code Intelligence](scip/README.md)
- **Main Documentation**: [README](../README.md)

---

## Related Documentation

- **Server Deployment**: [Server Deployment Guide](server-deployment.md)
- **Architecture**: [Architecture Guide](architecture.md)
- **Configuration**: [Configuration Guide](configuration.md)

---


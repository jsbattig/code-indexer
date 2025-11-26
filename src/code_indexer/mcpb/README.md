# MCP Stdio Bridge

Bridge connecting Claude Desktop to CIDX server via stdin/stdout protocol.

## Overview

The MCP Stdio Bridge enables Claude Desktop to perform semantic code searches against a CIDX server by translating JSON-RPC requests over stdin/stdout into HTTP requests with Bearer token authentication.

## Installation

Install the bridge as part of the code-indexer package:

```bash
pip install code-indexer
```

Or install from source:

```bash
cd /path/to/code-indexer
pip install -e .
```

After installation, verify the `cidx-bridge` command is available:

```bash
cidx-bridge --help
```

## Configuration

The bridge requires configuration for server URL and authentication.

### Configuration File (Recommended)

Create `~/.mcpb/config.json`:

```json
{
  "server_url": "https://your-cidx-server.com",
  "bearer_token": "your-bearer-token-here",
  "timeout": 30
}
```

### Environment Variables (Alternative)

Set environment variables instead of using a config file:

```bash
export MCPB_SERVER_URL="https://your-cidx-server.com"
export MCPB_BEARER_TOKEN="your-bearer-token-here"
export MCPB_TIMEOUT=30
```

### Configuration Options

| Option | Description | Required | Default |
|--------|-------------|----------|---------|
| `server_url` | Base URL of CIDX server (without trailing slash) | Yes | - |
| `bearer_token` | Bearer token for authentication | Yes | - |
| `timeout` | Request timeout in seconds | No | 30 |

## Usage

### Running the Bridge

The bridge reads JSON-RPC requests from stdin and writes responses to stdout:

```bash
cidx-bridge
```

With environment variables:

```bash
MCPB_SERVER_URL="https://cidx.example.com" \
MCPB_BEARER_TOKEN="token-123" \
cidx-bridge
```

### Integration with Claude Desktop

Add the bridge to your Claude Desktop MCP servers configuration file (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "cidx": {
      "command": "cidx-bridge",
      "env": {
        "MCPB_SERVER_URL": "https://your-cidx-server.com",
        "MCPB_BEARER_TOKEN": "your-bearer-token-here"
      }
    }
  }
}
```

Restart Claude Desktop after updating the configuration.

### Available Tools

The bridge provides access to all 22 CIDX MCP tools:

**Search**
- `search_code` - Search code using semantic search, FTS, or hybrid mode (24 parameters)

**Repository Management**
- `list_repositories` - List all repositories
- `get_repository_status` - Get status of a specific repository
- `get_all_repositories_status` - Get status of all repositories
- `activate_repository` - Activate a repository for indexing
- `deactivate_repository` - Deactivate a repository
- `sync_repository` - Sync repository with remote
- `discover_repositories` - Discover repositories in a directory
- `manage_composite_repository` - Create/update composite repository

**Branch Management**
- `get_branches` - List branches for a repository
- `switch_branch` - Switch to a different branch

**File Operations**
- `browse_directory` - Browse directory structure
- `list_files` - List files in a directory
- `get_file_content` - Get content of a specific file

**Golden Repository (Reference Docs)**
- `add_golden_repo` - Add a golden repository
- `remove_golden_repo` - Remove a golden repository
- `refresh_golden_repo` - Refresh golden repository index

**Statistics**
- `get_repository_statistics` - Get repository indexing statistics
- `get_job_statistics` - Get indexing job statistics

**System**
- `check_health` - Check server health status
- `list_users` - List all users (admin only)
- `create_user` - Create a new user (admin only)

## Protocol

### JSON-RPC Format

**Request (stdin):**
```json
{"jsonrpc": "2.0", "method": "tools/list", "id": 1}
```

**Response (stdout):**
```json
{"jsonrpc": "2.0", "result": {"tools": [...]}, "id": 1}
```

### Error Handling

The bridge returns standard JSON-RPC error responses:

| Error Code | Description |
|------------|-------------|
| -32700 | Parse error (malformed JSON) |
| -32600 | Invalid request (missing required fields) |
| -32000 | Server error (HTTP errors, timeouts, connection failures) |

**Error Response:**
```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32000,
    "message": "Connection failed to https://cidx.example.com: Connection refused"
  },
  "id": 1
}
```

## Authentication

The bridge includes the Bearer token in the `Authorization` header of all HTTP requests:

```
Authorization: Bearer <your-token>
```

Authentication failures (401 responses) from the CIDX server are propagated to the client as JSON-RPC errors.

## Troubleshooting

### Bridge fails to start

**Error:** `Configuration error: Config file not found`

**Solution:** Create `~/.mcpb/config.json` or set environment variables `MCPB_SERVER_URL` and `MCPB_BEARER_TOKEN`.

### Authentication failures

**Error:** `Authentication failed: 401 Unauthorized`

**Solution:** Verify your Bearer token is correct and has not expired. Check with your CIDX server administrator.

### Connection failures

**Error:** `Connection failed to https://cidx.example.com: Connection refused`

**Solution:**
- Verify the CIDX server is running
- Check the server URL is correct
- Ensure network connectivity to the server
- Check firewall rules allow outbound connections

### Request timeouts

**Error:** `Request timed out after 30 seconds`

**Solution:**
- Increase timeout in configuration (for large repositories or slow networks)
- Check CIDX server performance and resource usage
- Verify network latency is acceptable

## Architecture

The bridge consists of four main components:

1. **Protocol Handler** (`protocol.py`) - JSON-RPC message parsing and validation
2. **HTTP Client** (`http_client.py`) - HTTP communication with Bearer token authentication
3. **Bridge Core** (`bridge.py`) - Main stdin/stdout loop and error handling
4. **Configuration** (`config.py`) - Configuration loading from files and environment

## Development

### Running Tests

```bash
pytest tests/mcpb/ -v
```

### Code Quality

```bash
./lint.sh
```

## Performance

| Metric | Target | Typical |
|--------|--------|---------|
| Stdio read latency | <10ms | ~1-2ms |
| HTTP round-trip (local) | <100ms | ~20-50ms |
| Memory footprint | <50MB | ~30MB |

## License

MIT License - See LICENSE file in repository root.

## Support

For issues or questions:
- GitHub Issues: https://github.com/jsbattig/code-indexer/issues
- Documentation: https://github.com/jsbattig/code-indexer

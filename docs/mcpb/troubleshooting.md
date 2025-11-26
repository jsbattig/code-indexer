# CIDX MCP Bridge Troubleshooting Guide

Last Updated: 2025-11-26

## Overview

This guide provides solutions to common CIDX MCP Bridge (MCPB) issues based on verified implementation details from the codebase.

## Diagnostic Commands

### Check Configuration

Run diagnostics to verify configuration and connectivity:

```bash
cidx-bridge --diagnose
```

This command (from src/code_indexer/mcpb/bridge.py:194-219):
- Displays environment variables (tokens masked for security)
- Shows configuration file contents (tokens masked)
- Reports effective configuration with sources
- Tests server connectivity
- Reports server version if reachable

Example output (successful):

```
Configuration Diagnostics
==================================================

Environment Variables:
  CIDX_SERVER_URL: https://cidx.example.com
  CIDX_TOKEN: ****abc

Config File (~/.mcpb/config.json):
  (not used)

Effective Configuration:
  bearer_token: ****abc (from environment)
  log_level: info (from default)
  server_url: https://cidx.example.com (from environment)
  timeout: 30 (from default)

Server Connectivity:
  Status: Server reachable

```

Example output (error):

```
Configuration Diagnostics
==================================================

...

Server Connectivity:
  Status: Connection failed: Connection refused to https://cidx.example.com: ...

```

### Check Version

Verify MCPB installation:

```bash
cidx-bridge --help
```

Expected output includes version information and command-line options.

### Test Basic Request

Test JSON-RPC communication:

```bash
echo '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}' | cidx-bridge
```

Successful response returns JSON with available tools.

## Connection Issues

### Connection Refused

Symptom:

```
Connection failed to https://cidx.example.com: Connection refused
```

Error source: src/code_indexer/mcpb/http_client.py:112-113

Causes:
1. CIDX server not running
2. Incorrect server URL
3. Firewall blocking connection
4. Server running on different port

Solutions:

1. Verify server is running:

```bash
# On CIDX server host
ps aux | grep "cidx server"
```

Expected: Process running with `cidx server start` or similar.

2. Test server accessibility:

```bash
curl -I https://cidx.example.com/health
```

Expected: HTTP 200 response with health status.

3. Check server URL in configuration:

```bash
cidx-bridge --diagnose | grep server_url
```

Verify URL matches actual server address.

4. Check firewall rules:

```bash
# Test port connectivity
telnet cidx.example.com 443
# Or
nc -zv cidx.example.com 443
```

Expected: Connection successful.

5. Verify HTTPS port (default: 8000 or 443):

```bash
# Check server configuration
ssh admin@cidx-server
cidx server config show
```

### Network Timeout

Symptom:

```
Request timed out after 30 seconds: ...
```

Error source: src/code_indexer/mcpb/http_client.py:107-110

Causes:
1. Network latency
2. Large query result set
3. Slow server response
4. Server under heavy load

Solutions:

1. Increase timeout:

Environment variable:
```bash
export CIDX_TIMEOUT="120"
```

Configuration file:
```json
{
  "timeout": 120
}
```

Timeout range: 1-300 seconds (from src/code_indexer/mcpb/config.py:62-66)

2. Reduce query complexity:

```bash
# Reduce limit
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "complex query",
      "limit": 5
    }
  },
  "id": 1
}' | cidx-bridge
```

3. Add filters to narrow search:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "database",
      "language": "python",
      "path_filter": "*/src/*",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

4. Check server load:

```bash
ssh admin@cidx-server
top
```

If server CPU/memory maxed, consider scaling or reducing concurrent queries.

### SSL/TLS Certificate Errors

Symptom:

```
SSL: CERTIFICATE_VERIFY_FAILED
```

Causes:
1. Self-signed certificate
2. Expired certificate
3. Certificate hostname mismatch
4. Missing certificate chain

Solutions:

1. Verify certificate validity:

```bash
openssl s_client -connect cidx.example.com:443 -servername cidx.example.com
```

Check:
- Certificate expiration date
- Hostname in certificate matches server URL
- Certificate chain complete

2. For self-signed certificates (testing only):

Self-signed certificates not recommended. MCPB enforces HTTPS validation. Use valid certificates in production (Let's Encrypt, commercial CA).

3. Check certificate chain:

```bash
curl -v https://cidx.example.com/health
```

Look for "SSL certificate verify ok" or certificate errors.

4. Update CA certificates:

```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install --reinstall ca-certificates

# macOS
brew install ca-certificates
```

### DNS Resolution Failure

Symptom:

```
Network error connecting to https://cidx.example.com: Name or service not known
```

Error source: src/code_indexer/mcpb/http_client.py:115-118

Causes:
1. Invalid hostname
2. DNS server unreachable
3. /etc/hosts entry missing (for internal servers)

Solutions:

1. Test DNS resolution:

```bash
nslookup cidx.example.com
# Or
dig cidx.example.com
```

Expected: IP address returned.

2. Check /etc/hosts for internal servers:

```bash
cat /etc/hosts | grep cidx
```

Add entry if missing:
```
192.168.1.100  cidx.example.com
```

3. Use IP address instead of hostname (temporary):

```bash
export CIDX_SERVER_URL="https://192.168.1.100"
```

Note: May cause SSL hostname mismatch warnings.

## Authentication Errors

### Authentication Failed (401)

Symptom:

```
Authentication failed: 401 Unauthorized
```

Error source: src/code_indexer/mcpb/http_client.py:83-86

Causes:
1. Invalid bearer token
2. Expired token
3. Token not set
4. Typo in token

Solutions:

1. Verify token is set:

```bash
cidx-bridge --diagnose | grep bearer_token
```

Expected: `bearer_token: ****abc (from environment)`

If shows `(not set)`, token is missing.

2. Check token value (masked):

```bash
echo $CIDX_TOKEN | tail -c 4
```

Compare last 3 characters with diagnostics output.

3. Request new token from admin:

```bash
ssh admin@cidx-server
cidx server create-token --username yourname
```

4. Set token correctly:

```bash
export CIDX_TOKEN="your-actual-token-here"
```

Verify:
```bash
cidx-bridge --diagnose
```

5. Check for whitespace in token:

```bash
# Wrong (has trailing newline)
export CIDX_TOKEN=$(cat token.txt)

# Correct (trim whitespace)
export CIDX_TOKEN=$(cat token.txt | tr -d '\n')
```

### Permission Denied Errors

Symptom:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32000,
    "message": "Permission denied: User lacks required permission 'manage_users'"
  },
  "id": 1
}
```

Causes:
1. User role lacks required permission
2. Tool requires higher privilege level

Solutions:

1. Check user role:

Contact CIDX server admin to verify your role and permissions.

2. Permission requirements by tool category:

- Search tools: `query_repos` (all users)
- Repository management: `activate_repos` (power_user, admin)
- Administration: `manage_golden_repos`, `manage_users` (admin only)
- Analytics: `query_repos` (all users)

Full permission mapping: src/code_indexer/server/mcp/tools.py (see `required_permission` field for each tool)

3. Request role upgrade from admin:

If you need higher privileges, contact CIDX server admin.

## Configuration Problems

### Missing Required Field

Symptom:

```
Missing required field: server_url
  Fix: Set CIDX_SERVER_URL environment variable
  Or: Add 'server_url' to ~/.mcpb/config.json
```

Error source: src/code_indexer/mcpb/config.py:157-168

Solutions:

1. Set environment variable:

```bash
export CIDX_SERVER_URL="https://cidx.example.com"
export CIDX_TOKEN="your-token-here"
```

2. Create configuration file:

```bash
mkdir -p ~/.mcpb
cat > ~/.mcpb/config.json <<EOF
{
  "server_url": "https://cidx.example.com",
  "bearer_token": "your-token-here"
}
EOF
chmod 600 ~/.mcpb/config.json
```

3. Verify configuration:

```bash
cidx-bridge --diagnose
```

### HTTPS Required Error

Symptom:

```
server_url must use HTTPS for security. Got: http://...
```

Error source: src/code_indexer/mcpb/config.py:51-59

Causes:
1. Using HTTP URL for non-localhost server

Solutions:

1. Change URL to HTTPS:

```bash
export CIDX_SERVER_URL="https://cidx.example.com"
```

2. Localhost exception (testing only):

```bash
# Allowed for localhost/127.0.0.1
export CIDX_SERVER_URL="http://localhost:8000"
# Or
export CIDX_SERVER_URL="http://127.0.0.1:8000"
```

Production servers MUST use HTTPS.

### Invalid Timeout Value

Symptom:

```
timeout must be between 1 and 300 seconds. Got: 500
```

Error source: src/code_indexer/mcpb/config.py:62-66

Solutions:

1. Use valid timeout range:

```bash
# Minimum: 1 second
export CIDX_TIMEOUT="1"

# Maximum: 300 seconds (5 minutes)
export CIDX_TIMEOUT="300"
```

2. Recommended values:
- Fast queries: 30 seconds (default)
- Standard queries: 60 seconds
- Complex queries: 120 seconds
- Maximum: 300 seconds

### Invalid Log Level

Symptom:

```
log_level must be one of ['debug', 'info', 'warning', 'error']. Got: verbose
```

Error source: src/code_indexer/mcpb/config.py:69-73

Solutions:

1. Use valid log level:

```bash
export CIDX_LOG_LEVEL="debug"    # Most verbose
export CIDX_LOG_LEVEL="info"     # Default
export CIDX_LOG_LEVEL="warning"  # Warnings and errors only
export CIDX_LOG_LEVEL="error"    # Errors only
```

2. Verify configuration:

```bash
cidx-bridge --diagnose | grep log_level
```

### Insecure File Permissions

Symptom (warning):

```
Configuration file /home/user/.mcpb/config.json has insecure permissions 0644.
Recommend setting to 0600: chmod 0600 /home/user/.mcpb/config.json
```

Warning source: src/code_indexer/mcpb/config.py:118-122

Causes:
1. Configuration file readable by other users
2. Bearer token exposed to unauthorized users

Solutions:

1. Fix permissions:

```bash
chmod 600 ~/.mcpb/config.json
```

2. Verify permissions:

```bash
ls -la ~/.mcpb/config.json
```

Expected: `-rw-------` (0600)

3. Fix directory permissions:

```bash
chmod 700 ~/.mcpb
```

## SSE Streaming Issues

### Incomplete SSE Stream

Symptom:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32603,
    "message": "SSE stream ended without complete event"
  },
  "id": 1
}
```

Error source: src/code_indexer/mcpb/http_client.py:186-190

Causes:
1. Server terminated stream early
2. Network interruption
3. Proxy/load balancer timeout

Solutions:

1. Increase timeout:

```bash
export CIDX_TIMEOUT="120"
```

2. Reduce query complexity (smaller result set):

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "simple query",
      "limit": 5
    }
  },
  "id": 1
}' | cidx-bridge
```

3. Check server logs:

```bash
ssh admin@cidx-server
tail -f /var/log/cidx/server.log
```

Look for errors during query processing.

4. Check proxy/load balancer timeout settings:

If CIDX server behind proxy (HAProxy, nginx), verify timeout settings allow long-running requests.

### SSE Parse Error

Symptom:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32603,
    "message": "SSE parsing error: Invalid event format"
  },
  "id": 1
}
```

Error source: src/code_indexer/mcpb/http_client.py:176-180

Causes:
1. Malformed SSE response from server
2. Server bug
3. Network corruption

Solutions:

1. Retry request:

```bash
# Same request may succeed on retry
echo '{...}' | cidx-bridge
```

2. Report to server admin:

Provide request details and error message for investigation.

3. Try non-streaming query (smaller result set):

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "test",
      "limit": 1
    }
  },
  "id": 1
}' | cidx-bridge
```

Smaller responses may not trigger SSE streaming.

## Query Errors

### Parse Error (Invalid JSON)

Symptom:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32700,
    "message": "Parse error",
    "data": {
      "detail": "Expecting value: line 1 column 1 (char 0)"
    }
  }
}
```

Error code: -32700 (from src/code_indexer/mcpb/protocol.py)

Causes:
1. Malformed JSON in request
2. Missing quotes around strings
3. Trailing commas
4. Unescaped quotes in strings

Solutions:

1. Validate JSON:

```bash
echo '{...}' | python3 -m json.tool
```

2. Common JSON errors:

Wrong (missing quotes):
```json
{"jsonrpc":"2.0","method":"tools/call","params":{"name":search_code}}
```

Correct:
```json
{"jsonrpc":"2.0","method":"tools/call","params":{"name":"search_code"}}
```

Wrong (trailing comma):
```json
{"jsonrpc":"2.0","method":"tools/call","params":{"name":"search_code",}}
```

Correct:
```json
{"jsonrpc":"2.0","method":"tools/call","params":{"name":"search_code"}}
```

3. Use JSON linter:

```bash
cat request.json | jq .
```

### Invalid Request (Missing Fields)

Symptom:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32600,
    "message": "Invalid Request: missing 'method' field"
  }
}
```

Error code: -32600 (from src/code_indexer/mcpb/protocol.py)

Causes:
1. Missing required JSON-RPC fields

Solutions:

Required fields:
- `jsonrpc`: Must be "2.0"
- `method`: Tool method to invoke
- `id`: Request identifier

Correct request:
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "test"
    }
  },
  "id": 1
}
```

### Invalid Parameters

Symptom:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32602,
    "message": "Invalid params: limit must be between 1 and 100"
  },
  "id": 1
}
```

Error code: -32602 (from src/code_indexer/mcpb/protocol.py)

Causes:
1. Parameter value out of range
2. Wrong parameter type
3. Mutually exclusive parameters

Solutions:

1. Check parameter constraints:

See [API Reference](api-reference.md) for all parameter constraints.

2. Common parameter errors:

Wrong (limit too high):
```json
{"query_text":"test","limit":1000}
```

Correct:
```json
{"query_text":"test","limit":50}
```

Wrong (fuzzy + regex):
```json
{"query_text":"test","search_mode":"fts","fuzzy":true,"regex":true}
```

Correct (choose one):
```json
{"query_text":"test","search_mode":"fts","fuzzy":true}
```

3. Verify parameter types:

Wrong (limit as string):
```json
{"query_text":"test","limit":"10"}
```

Correct (limit as integer):
```json
{"query_text":"test","limit":10}
```

## Platform-Specific Issues

### macOS: Command Not Found

Symptom:

```bash
cidx-bridge: command not found
```

Causes:
1. pip install location not in PATH
2. Python user bin directory not in PATH

Solutions:

1. Check installation location:

```bash
python3 -m pip show code-indexer | grep Location
```

2. Add to PATH:

```bash
# Add to ~/.zshrc or ~/.bash_profile
export PATH="$HOME/.local/bin:$PATH"
```

3. Reload shell:

```bash
source ~/.zshrc
```

4. Verify:

```bash
which cidx-bridge
cidx-bridge --help
```

### Linux: Permission Denied

Symptom:

```bash
bash: /home/user/.local/bin/cidx-bridge: Permission denied
```

Causes:
1. Executable bit not set

Solutions:

1. Fix permissions:

```bash
chmod +x ~/.local/bin/cidx-bridge
```

2. Verify:

```bash
ls -la ~/.local/bin/cidx-bridge
```

Expected: `-rwxr-xr-x`

### Windows: Python Module Not Found

Symptom:

```
ModuleNotFoundError: No module named 'code_indexer'
```

Causes:
1. Installation failed
2. Multiple Python installations
3. Virtual environment not activated

Solutions:

1. Verify installation:

```cmd
python -m pip show code-indexer
```

2. Reinstall:

```cmd
python -m pip uninstall code-indexer
python -m pip install --break-system-packages code-indexer
```

3. Use absolute path:

```cmd
python -m code_indexer.mcpb.bridge --help
```

## Claude Desktop Integration Issues

### MCP Server Not Appearing

Symptom:
CIDX tools not available in Claude Desktop

Causes:
1. Configuration file in wrong location
2. Invalid JSON in configuration
3. Claude Desktop not restarted after configuration change

Solutions:

1. Verify configuration file location:

macOS:
```bash
cat ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

Linux:
```bash
cat ~/.config/Claude/claude_desktop_config.json
```

2. Validate JSON:

```bash
python3 -m json.tool < ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

3. Correct configuration format:

```json
{
  "mcpServers": {
    "cidx": {
      "command": "cidx-bridge",
      "args": [],
      "env": {
        "CIDX_SERVER_URL": "https://cidx.example.com",
        "CIDX_TOKEN": "your-token-here"
      }
    }
  }
}
```

4. Restart Claude Desktop:

macOS:
```bash
killall Claude
open -a Claude
```

Linux:
```bash
killall claude
claude &
```

5. Check Claude Desktop logs:

macOS:
```bash
tail -f ~/Library/Logs/Claude/mcp*.log
```

Look for errors related to cidx-bridge startup.

### MCP Server Connection Failed

Symptom:
Claude Desktop shows "MCP server connection failed"

Causes:
1. cidx-bridge not in PATH
2. Configuration error
3. Server unreachable

Solutions:

1. Test bridge directly:

```bash
echo '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}' | cidx-bridge
```

If fails, fix bridge configuration first.

2. Use absolute path in configuration:

```json
{
  "mcpServers": {
    "cidx": {
      "command": "/Users/yourname/.local/bin/cidx-bridge",
      "args": [],
      "env": {...}
    }
  }
}
```

Find absolute path:
```bash
which cidx-bridge
```

3. Check environment variables in config:

```json
{
  "mcpServers": {
    "cidx": {
      "command": "cidx-bridge",
      "args": [],
      "env": {
        "CIDX_SERVER_URL": "https://cidx.example.com",
        "CIDX_TOKEN": "your-actual-token-here"
      }
    }
  }
}
```

Verify URL and token are correct.

## FAQ

### Q: Why do I get "server_url must use HTTPS"?

A: MCPB enforces HTTPS for security (src/code_indexer/mcpb/config.py:51-59). Use HTTPS URLs for all servers except localhost/127.0.0.1.

Exception for testing:
```bash
export CIDX_SERVER_URL="http://localhost:8000"
```

Production servers MUST use HTTPS.

### Q: How do I find my bearer token?

A: Contact CIDX server administrator. They can generate a token:

```bash
ssh admin@cidx-server
cidx server create-token --username yourname
```

### Q: What's the difference between CIDX_* and MCPB_* environment variables?

A: Both work, but CIDX_* takes precedence (src/code_indexer/mcpb/config.py:129-154):

Priority order:
1. CIDX_SERVER_URL > MCPB_SERVER_URL
2. CIDX_TOKEN > MCPB_BEARER_TOKEN
3. CIDX_TIMEOUT > MCPB_TIMEOUT
4. CIDX_LOG_LEVEL > MCPB_LOG_LEVEL

Recommendation: Use CIDX_* for consistency.

### Q: How do I debug configuration issues?

A: Run diagnostics:

```bash
cidx-bridge --diagnose
```

This shows:
- Environment variables (tokens masked)
- Configuration file contents
- Effective configuration with sources
- Server connectivity status

### Q: Can I use self-signed certificates?

A: Not recommended. MCPB uses standard httpx SSL verification. For testing, use localhost with HTTP. For production, use valid certificates (Let's Encrypt free).

### Q: What's the maximum timeout value?

A: 300 seconds (5 minutes), enforced by src/code_indexer/mcpb/config.py:62-66.

### Q: How do I increase query result limits?

A: Use `limit` parameter (max 100):

```json
{
  "query_text": "test",
  "limit": 50
}
```

Warning: High limits consume more context tokens. Start with limit=5.

### Q: Why are my queries timing out?

A: Possible causes:
1. Large result set (reduce limit)
2. Complex semantic search (add filters)
3. Network latency (increase timeout)
4. Server under load (reduce concurrent queries)

See "Network Timeout" section for solutions.

### Q: How do I check server health?

A: Use check_health tool:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "check_health",
    "arguments": {}
  },
  "id": 1
}' | cidx-bridge
```

Or HTTP directly:
```bash
curl https://cidx.example.com/health
```

### Q: What does "SSE stream ended without complete event" mean?

A: Server-Sent Events (SSE) stream terminated before sending complete response. Causes:
1. Server error during processing
2. Network interruption
3. Timeout

Solutions:
1. Retry request
2. Increase timeout
3. Reduce query complexity
4. Check server logs

## Getting Help

### Collect Diagnostic Information

Before requesting support, collect:

1. Configuration diagnostics:

```bash
cidx-bridge --diagnose > diagnostics.txt
```

2. Error messages:

```bash
echo '{...}' | cidx-bridge 2> error.txt
```

3. Version information:

```bash
python3 -m pip show code-indexer > version.txt
```

4. Platform information:

```bash
uname -a > platform.txt
python3 --version >> platform.txt
```

### Contact Support

Provide diagnostic information to:
- GitHub issues: https://github.com/jsbattig/code-indexer/issues
- CIDX server administrator (for server-side issues)

## Version Information

- MCPB version: 8.1.0
- Diagnostics module: src/code_indexer/mcpb/diagnostics.py
- Configuration module: src/code_indexer/mcpb/config.py
- HTTP client: src/code_indexer/mcpb/http_client.py

Last Updated: 2025-11-26

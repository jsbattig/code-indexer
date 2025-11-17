# MCP Endpoint Must Return 401 for Unauthenticated Requests

**Date**: 2025-11-17
**Branch**: `feature/epic-477-mcp-oauth-integration`
**Issue**: Claude.ai hangs when connecting - gets infinite SSE stream instead of 401
**Root Cause**: GET `/mcp` returns SSE stream for unauthenticated requests (violates MCP spec)

---

## Problem Description

### Current Behavior (INCORRECT ❌)

```bash
$ curl -s https://linner.ddns.net:8383/mcp
event: endpoint
data: {"protocol": "mcp", "version": "2024-11-05", "authentication": "oauth2"}

: ping - 2025-11-17 19:12:04.880940+00:00

event: ping
data: keepalive

: ping - 2025-11-17 19:12:19.881819+00:00

event: ping
data: keepalive

[infinite stream continues forever...]
```

**What happens:**
1. Claude.ai sends GET request to `/mcp` without authentication
2. Server returns HTTP 200 with SSE stream
3. Stream sends one "endpoint" event, then pings forever
4. Claude.ai waits for something specific to happen
5. Stream never closes, Claude.ai hangs indefinitely
6. User sees error: "There was an error connecting to CidxServer"

### Expected Behavior Per MCP Spec (CORRECT ✅)

```bash
$ curl -v https://linner.ddns.net:8383/mcp
< HTTP/1.1 401 Unauthorized
< WWW-Authenticate: Bearer realm="mcp", resource_metadata="https://linner.ddns.net:8383/.well-known/oauth-authorization-server"
< Content-Type: application/json

{"error": "unauthorized", "message": "Bearer token required"}
```

**What should happen:**
1. Claude.ai sends GET request to `/mcp` without authentication
2. Server returns **HTTP 401 Unauthorized**
3. Response includes `WWW-Authenticate` header with OAuth discovery URL
4. Claude.ai reads the header
5. Claude.ai fetches OAuth metadata from discovery URL
6. Claude.ai initiates OAuth authorization flow
7. User sees login form
8. After auth, Claude.ai connects with Bearer token

---

## MCP Specification Requirements

### From MCP Authorization Spec (RFC 9728)

**Servers MUST:**
- Return HTTP 401 for requests requiring authorization
- Include `WWW-Authenticate` header in 401 responses
- Header must contain `resource_metadata` URL pointing to OAuth discovery

**Quote from spec:**
> "Servers MUST return appropriate HTTP status codes for authorization errors"
> "401: Authorization required or token invalid"
> "WWW-Authenticate: Bearer resource_metadata=..."

### Example from GitHub's MCP Server

```http
HTTP/2 401
www-authenticate: Bearer error="invalid_request",
    error_description="No access token was provided in this request",
    resource_metadata="https://api.githubcopilot.com/.well-known/oauth-protected-resource/mcp"
```

---

## Root Cause Analysis

### Why Current Implementation is Wrong

**Previous recommendation** (in `reports/mcp-endpoint-authentication-issue.md`):
- Return SSE stream for unauthenticated requests
- Provide "discovery" events in the stream
- Keep connection alive with pings

**Why it seemed correct:**
- Allows clients to "discover" the server exists
- Provides MCP protocol information
- Seemed like a reasonable approach

**Why it's actually wrong:**
1. **Violates MCP spec** - Spec requires 401 for unauthenticated requests
2. **Infinite stream hangs clients** - Claude.ai expects 401, gets stuck waiting
3. **No OAuth trigger** - 401 response is what triggers OAuth flow
4. **Security issue** - Bypasses authorization requirements

### Current Implementation Location

**File:** `src/code_indexer/server/mcp/protocol.py:298-355`

```python
@mcp_router.get("/mcp")
async def mcp_sse_endpoint(
    authorization: Optional[str] = Header(None),
) -> EventSourceResponse:
    """
    MCP SSE endpoint for server-to-client notifications.

    Supports both:
    - Unauthenticated: Returns minimal discovery stream for claude.ai  # ❌ WRONG
    - Authenticated: Returns full MCP notification stream with Bearer token
    """
    user = None

    # Try to authenticate if Authorization header provided
    if authorization:
        if authorization.startswith("Bearer "):
            # ... token validation ...
            pass

    # Return appropriate SSE stream
    if user:
        # Authenticated: full MCP capabilities
        return EventSourceResponse(authenticated_sse_generator(user))
    else:
        # Unauthenticated: minimal discovery stream  # ❌ THIS IS THE PROBLEM
        return EventSourceResponse(discovery_sse_generator())
```

**Function:** `discovery_sse_generator()` (lines 358-371)

```python
async def discovery_sse_generator():
    """Minimal SSE stream for unauthenticated MCP discovery."""
    # Send initial endpoint info
    yield {
        "event": "endpoint",
        "data": json.dumps(
            {"protocol": "mcp", "version": "2024-11-05", "authentication": "oauth2"}
        ),
    }

    # Keep connection alive with periodic pings
    while True:  # ❌ INFINITE LOOP - HANGS CLAUDE.AI
        await asyncio.sleep(30)
        yield {"event": "ping", "data": "keepalive"}
```

---

## The Fix

### Step 1: Return 401 for Unauthenticated Requests

**File:** `src/code_indexer/server/mcp/protocol.py`

**Replace the entire `mcp_sse_endpoint` function:**

```python
from fastapi import Response

@mcp_router.get("/mcp")
async def mcp_sse_endpoint(
    authorization: Optional[str] = Header(None),
) -> Union[Response, EventSourceResponse]:
    """
    MCP SSE endpoint for server-to-client notifications.

    Per MCP specification (RFC 9728):
    - Unauthenticated requests: Return HTTP 401 with WWW-Authenticate header
    - Authenticated requests: Return SSE stream with full MCP capabilities
    """
    user = None

    # Try to authenticate if Authorization header provided
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        try:
            # Use existing auth logic - manually validate token and get user
            from ..auth.dependencies import jwt_manager, user_manager, oauth_manager
            from ..auth.jwt_manager import TokenExpiredError, InvalidTokenError

            if jwt_manager and user_manager:
                # Try OAuth token validation first
                if oauth_manager:
                    oauth_result = oauth_manager.validate_token(token)
                    if oauth_result:
                        username = oauth_result.get("user_id")
                        if username:
                            user = user_manager.get_user(username)

                # Fallback to JWT validation if OAuth didn't work
                if user is None:
                    try:
                        payload = jwt_manager.validate_token(token)
                        username = payload.get("username")
                        if username:
                            # Check if token is blacklisted
                            from ..app import is_token_blacklisted

                            jti = payload.get("jti")
                            if not (jti and is_token_blacklisted(jti)):
                                user = user_manager.get_user(username)
                    except (TokenExpiredError, InvalidTokenError):
                        pass
        except Exception:
            pass

    # If no valid authentication, return 401 with WWW-Authenticate header
    if user is None:
        # Get the server's issuer URL from environment or config
        import os
        issuer_url = os.getenv("CIDX_ISSUER_URL", "http://localhost:8000")

        return Response(
            status_code=401,
            headers={
                "WWW-Authenticate": f'Bearer realm="mcp", resource_metadata="{issuer_url}/.well-known/oauth-authorization-server"',
                "Content-Type": "application/json",
            },
            content='{"error": "unauthorized", "message": "Bearer token required for MCP access"}',
        )

    # Authenticated: return SSE stream with full MCP capabilities
    return EventSourceResponse(authenticated_sse_generator(user))
```

### Step 2: Remove Unauthenticated SSE Generator

**Delete the `discovery_sse_generator()` function** (lines 358-371):

```python
# ❌ DELETE THIS ENTIRE FUNCTION
async def discovery_sse_generator():
    """Minimal SSE stream for unauthenticated MCP discovery."""
    # ...
```

It's no longer needed since unauthenticated requests now return 401.

### Step 3: Update Function Return Type

Add `Response` to the return type annotation:

```python
from typing import Union
from fastapi import Response

@mcp_router.get("/mcp")
async def mcp_sse_endpoint(
    authorization: Optional[str] = Header(None),
) -> Union[Response, EventSourceResponse]:  # ✅ ADD Union[Response, ...]
    ...
```

### Step 4: Update Imports

Add necessary imports at the top of `protocol.py`:

```python
from typing import Dict, Any, List, Optional, Tuple, Union  # Add Union
from fastapi import APIRouter, Depends, Request, Response, Header  # Add Response, Header
```

---

## Testing the Fix

### Test 1: Unauthenticated Request Returns 401

```bash
curl -v https://linner.ddns.net:8383/mcp 2>&1 | grep -E "HTTP|WWW-Authenticate"

# Expected output:
< HTTP/1.1 401 Unauthorized
< WWW-Authenticate: Bearer realm="mcp", resource_metadata="https://linner.ddns.net:8383/.well-known/oauth-authorization-server"
```

**Success criteria:**
- ✅ HTTP 401 status
- ✅ WWW-Authenticate header present
- ✅ resource_metadata points to correct OAuth discovery URL
- ✅ Connection closes immediately (no infinite stream)

### Test 2: Authenticated Request Returns SSE Stream

```bash
# Get a valid token first
TOKEN=$(curl -s -X POST https://linner.ddns.net:8383/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code&code=...&client_id=...&code_verifier=..." \
  | jq -r .access_token)

# Connect with token
curl -H "Authorization: Bearer $TOKEN" https://linner.ddns.net:8383/mcp

# Expected output:
event: endpoint
data: {"protocol":"mcp","version":"2024-11-05","capabilities":{"tools":{}},"user":"username"}

event: ping
data: authenticated
```

**Success criteria:**
- ✅ HTTP 200 status
- ✅ SSE stream starts
- ✅ Endpoint event includes user info
- ✅ Stream continues with authenticated pings

### Test 3: Invalid Token Returns 401

```bash
curl -v -H "Authorization: Bearer invalid_token_here" https://linner.ddns.net:8383/mcp 2>&1 | grep HTTP

# Expected output:
< HTTP/1.1 401 Unauthorized
```

**Success criteria:**
- ✅ HTTP 401 status (not 200 with empty stream)

### Test 4: Claude.ai Connection Works

**In Claude.ai Settings > Connectors:**

1. Add connector: `https://linner.ddns.net:8383`
2. Click "Connect"
3. **Expected:** Browser opens to authorization page
4. **Expected:** URL shows: `https://linner.ddns.net:8383/oauth/authorize?...`
5. Enter credentials
6. **Expected:** Redirect to `https://claude.ai/api/mcp/auth_callback?code=...`
7. **Expected:** Connection shows as "Connected" in Claude.ai
8. **Expected:** Can use MCP tools

**Success criteria:**
- ✅ OAuth flow initiates (no more about:blank)
- ✅ Login form appears
- ✅ After login, redirects to Claude properly
- ✅ Connection establishes successfully
- ✅ No "error connecting" message

---

## Implementation Checklist

### Code Changes

- [ ] Update `mcp_sse_endpoint()` to return 401 for unauthenticated requests
- [ ] Add `Response` to return type: `Union[Response, EventSourceResponse]`
- [ ] Include `WWW-Authenticate` header with `resource_metadata` URL
- [ ] Use `CIDX_ISSUER_URL` environment variable for issuer URL
- [ ] Remove `discovery_sse_generator()` function
- [ ] Update imports: add `Response`, `Union`

### Testing

- [ ] Test unauthenticated request returns 401 with proper headers
- [ ] Test authenticated request returns SSE stream
- [ ] Test invalid token returns 401
- [ ] Test connection closes immediately for 401 (no infinite stream)
- [ ] Verify OAuth discovery URL in WWW-Authenticate header is correct

### Integration Testing

- [ ] Test with Claude.ai web interface
- [ ] Test with Claude Desktop app
- [ ] Test with MCP Inspector tool
- [ ] Verify OAuth flow initiates properly
- [ ] Verify login form appears
- [ ] Verify connection establishes after authentication

### Regression Testing

- [ ] Verify Claude Code CLI still works (--transport http)
- [ ] Verify existing authenticated connections still work
- [ ] Run fast-automation.sh test suite
- [ ] Check for any broken tests related to MCP endpoint

---

## Files to Modify

### Primary Changes

1. **`src/code_indexer/server/mcp/protocol.py`**
   - Modify `mcp_sse_endpoint()` function (lines ~298-355)
   - Delete `discovery_sse_generator()` function (lines ~358-371)
   - Update imports: add `Response`, `Union`
   - Add 401 response logic with WWW-Authenticate header
   - Keep `authenticated_sse_generator()` unchanged

### Testing Updates (If Applicable)

2. **`tests/unit/server/mcp/test_protocol.py`**
   - Update tests expecting SSE stream for unauthenticated requests
   - Add test for 401 response with WWW-Authenticate header
   - Add test for resource_metadata URL format
   - Ensure authenticated tests still pass

---

## Security Considerations

### Why This Fix is More Secure

**Before (Current):**
- ❌ Unauthenticated clients get SSE stream (even if minimal)
- ❌ Exposes server is MCP-capable without authentication
- ❌ Allows connection exhaustion (infinite streams)
- ❌ Violates authorization requirements

**After (Fixed):**
- ✅ Unauthenticated requests rejected immediately (401)
- ✅ Proper authorization challenge via WWW-Authenticate header
- ✅ No resources consumed for unauthenticated clients
- ✅ Compliant with MCP security specification

### Attack Surface Reduction

**Before:**
- Unauthenticated clients could open many SSE connections
- Each connection stays open forever (30s pings)
- Potential DoS via connection exhaustion

**After:**
- Unauthenticated requests return 401 immediately
- Connection closes instantly
- No resource consumption for unauthorized access

---

## Expected Results After Fix

### Unauthenticated Request Behavior

```bash
$ curl -v https://linner.ddns.net:8383/mcp

< HTTP/1.1 401 Unauthorized
< WWW-Authenticate: Bearer realm="mcp", resource_metadata="https://linner.ddns.net:8383/.well-known/oauth-authorization-server"
< Content-Type: application/json
< Content-Length: 78

{"error": "unauthorized", "message": "Bearer token required for MCP access"}

# Connection closes immediately ✅
```

### Claude.ai Connection Flow

1. **User action:** Add `https://linner.ddns.net:8383` in Settings > Connectors
2. **Claude.ai:** GET `https://linner.ddns.net:8383/mcp` → receives 401
3. **Claude.ai:** Parses `WWW-Authenticate` header
4. **Claude.ai:** GET `https://linner.ddns.net:8383/.well-known/oauth-authorization-server`
5. **Claude.ai:** POST `https://linner.ddns.net:8383/oauth/register` (registers itself)
6. **Claude.ai:** Opens browser to `https://linner.ddns.net:8383/oauth/authorize?...`
7. **User:** Sees login form, enters credentials
8. **Server:** Redirects to `https://claude.ai/api/mcp/auth_callback?code=...&state=...`
9. **Claude.ai:** POST `https://linner.ddns.net:8383/oauth/token` (exchanges code for token)
10. **Claude.ai:** GET `https://linner.ddns.net:8383/mcp` with `Authorization: Bearer <token>`
11. **Server:** Returns SSE stream (HTTP 200)
12. **Connection:** Established ✅

---

## Comparison: Before vs After

### GET /mcp Without Authentication

| Aspect | Before (WRONG ❌) | After (CORRECT ✅) |
|--------|------------------|-------------------|
| HTTP Status | 200 OK | 401 Unauthorized |
| Response Type | SSE stream (infinite) | JSON error message |
| Headers | `Content-Type: text/event-stream` | `WWW-Authenticate: Bearer ...` |
| Connection | Stays open forever | Closes immediately |
| Claude.ai behavior | Hangs waiting for event | Starts OAuth flow |
| Spec compliance | Violates MCP spec | Compliant with RFC 9728 |
| Security | Exposes server info | Proper auth challenge |

### GET /mcp With Valid Bearer Token

| Aspect | Before | After |
|--------|--------|-------|
| HTTP Status | 200 OK | 200 OK (no change) |
| Response Type | SSE stream | SSE stream (no change) |
| Content | Authenticated events | Authenticated events (no change) |
| Connection | Long-lived SSE | Long-lived SSE (no change) |

---

## Why Previous Recommendation Was Wrong

### Original Reasoning (Flawed)

**From `reports/mcp-endpoint-authentication-issue.md`:**

> "Make GET `/mcp` Unauthenticated for Discovery"
> "Allow unauthenticated GET requests to `/mcp` that return minimal SSE stream for discovery"
> "Allows claude.ai discovery"

**Why it seemed logical:**
- Server was returning "Missing authentication credentials"
- Thought claude.ai needed to verify server exists before OAuth
- Seemed like a "discovery" phase before authentication

**What was missed:**
- MCP spec explicitly requires 401 for unauthenticated requests
- 401 response IS the discovery mechanism (via WWW-Authenticate header)
- SSE stream for unauthenticated requests violates security model
- Infinite stream would hang clients (didn't anticipate this)

### Lessons Learned

1. **Always read the full spec** - Not just blog posts or GitHub issues
2. **Test with actual client** - Would have caught the infinite stream hang
3. **Security-first approach** - 401 is correct for auth requirements
4. **Don't invent protocols** - Follow RFC 9728 exactly

---

## Rollback Plan

If this fix causes issues:

### Quick Rollback

```bash
git revert <commit-hash>
git push origin feature/epic-477-mcp-oauth-integration
```

### Alternative: Environment Flag

Add a feature flag to toggle between behaviors:

```python
import os

USE_401_FOR_UNAUTH = os.getenv("MCP_USE_401_RESPONSE", "true").lower() == "true"

if user is None:
    if USE_401_FOR_UNAUTH:
        return Response(status_code=401, ...)  # New behavior
    else:
        return EventSourceResponse(discovery_sse_generator())  # Old behavior
```

Then if issues occur:
```bash
export MCP_USE_401_RESPONSE=false
cidx server restart
```

---

## Additional Resources

### MCP Specification

- **Authorization Spec:** https://modelcontextprotocol.io/specification/draft/basic/authorization
- **RFC 9728:** OAuth 2.0 Protected Resource Metadata
- **RFC 8414:** OAuth 2.0 Authorization Server Metadata

### Related Issues

- GitHub issue #5826: Claude Desktop doesn't connect to custom MCPs
- GitHub issue #3515: Claude Desktop MCP OAuth Integration Issue

### Testing Tools

- **MCP Inspector:** https://github.com/modelcontextprotocol/inspector
- **Online HTTP client:** https://reqbin.com/ (for testing 401 responses)

---

## Conclusion

The current implementation violates the MCP specification by returning an SSE stream for unauthenticated requests instead of HTTP 401 with a `WWW-Authenticate` header.

**This causes:**
- Claude.ai to hang waiting for events that never come
- Connection to stay open indefinitely
- OAuth flow to never initiate

**The fix:**
- Return HTTP 401 for unauthenticated GET `/mcp` requests
- Include `WWW-Authenticate` header with OAuth discovery URL
- Keep authenticated behavior unchanged (SSE stream)

**Impact:**
- ✅ Claude.ai will connect successfully
- ✅ OAuth flow will work as expected
- ✅ Compliant with MCP specification
- ✅ More secure (no unauthenticated access)

**Recommendation:** Implement immediately to unblock Claude.ai integration.

---

**End of Report**

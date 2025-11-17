# MCP Endpoint Authentication Issue - claude.ai Cannot Discover Server

**Date**: 2025-11-17
**Branch**: `feature/epic-477-mcp-oauth-integration`
**Issue**: claude.ai returns "Server not found" error when trying to connect
**Root Cause**: GET `/mcp` endpoint requires authentication, preventing discovery

---

## Problem Description

### User Experience

When user enters `https://linner.ddns.net:8383` in claude.ai Settings > Connectors:
- Clicks "Connect"
- Receives error: `{"type":"error","error":{"type":"not_found_error","message":"Server not found"}}`
- No OAuth flow initiates
- No login screen appears

### Technical Root Cause

**Current Implementation** (src/code_indexer/server/mcp/protocol.py:298-303):
```python
@mcp_router.get("/mcp")
async def mcp_sse_endpoint(
    current_user: User = Depends(get_current_user)  # ❌ REQUIRES AUTH
) -> EventSourceResponse:
    """MCP SSE endpoint for server-to-client notifications."""
    return EventSourceResponse(sse_event_generator())
```

**What Happens:**
1. claude.ai tries to verify server at `https://linner.ddns.net:8383/mcp`
2. GET request returns: `{"detail":"Missing authentication credentials"}`
3. claude.ai cannot verify it's an MCP server
4. Returns "Server not found" error
5. OAuth flow never starts

### Expected Flow

According to [Anthropic Documentation](https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers):

1. **Discovery Phase** (Unauthenticated):
   - claude.ai accesses SSE endpoint to verify server exists
   - Server responds with SSE connection (minimal)
   - claude.ai identifies server as valid MCP server

2. **OAuth Phase** (If server supports OAuth):
   - claude.ai reads OAuth discovery metadata
   - Starts OAuth 2.1 authorization flow
   - User logs in via browser
   - claude.ai receives access token

3. **Authenticated Connection**:
   - claude.ai reconnects to SSE endpoint with Bearer token
   - JSON-RPC POST requests use Bearer token
   - Full MCP functionality available

---

## Current State Analysis

### All Endpoints Require Authentication

**GET `/mcp`** (SSE):
```python
current_user: User = Depends(get_current_user)  # ❌ Auth required
```

**POST `/mcp`** (JSON-RPC):
```python
current_user: User = Depends(get_current_user)  # ❌ Auth required
```

**DELETE `/mcp`** (Session termination):
```python
current_user: User = Depends(get_current_user)  # ❌ Auth required
```

**Result:** claude.ai cannot even discover the server exists.

---

## Solution Options

### Option 1: Make GET `/mcp` Unauthenticated for Discovery (SIMPLEST)

**Approach:** Allow unauthenticated GET requests to `/mcp` that return minimal SSE stream for discovery.

**Implementation:**
```python
from fastapi import Header
from typing import Optional

@mcp_router.get("/mcp")
async def mcp_sse_endpoint(
    authorization: Optional[str] = Header(None)
) -> EventSourceResponse:
    """MCP SSE endpoint - allows discovery without auth, full functionality with auth."""

    # Parse Bearer token if provided
    user = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        try:
            # Validate token and get user
            from .auth.dependencies import verify_access_token
            user = verify_access_token(token)
        except Exception:
            pass  # Invalid token, continue as unauthenticated

    # Return SSE stream (minimal for unauthenticated, full for authenticated)
    if user:
        return EventSourceResponse(authenticated_event_generator(user))
    else:
        return EventSourceResponse(discovery_event_generator())
```

**New Event Generators:**
```python
async def discovery_event_generator():
    """Minimal SSE stream for unauthenticated discovery."""
    # Send initial connection event
    yield {"event": "endpoint", "data": json.dumps({"type": "mcp", "version": "2024-11-05"})}
    # Keep connection open
    while True:
        await asyncio.sleep(30)
        yield {"event": "ping", "data": "keepalive"}

async def authenticated_event_generator(user: User):
    """Full SSE stream for authenticated clients."""
    yield {"event": "endpoint", "data": json.dumps({
        "type": "mcp",
        "version": "2024-11-05",
        "capabilities": {"tools": {}},
        "user": user.username
    })}
    # Full MCP notification stream...
```

**Pros:**
- ✅ Simple implementation
- ✅ Allows claude.ai discovery
- ✅ OAuth flow can start
- ✅ Full functionality requires authentication

**Cons:**
- ⚠️ Exposes that an MCP server exists (minimal info)
- ⚠️ Unauthenticated clients can hold open SSE connections

---

### Option 2: Separate Discovery Endpoint (MORE SECURE)

**Approach:** Create separate endpoint for discovery that doesn't require auth.

**Implementation:**
```python
@mcp_router.get("/mcp/discover")
async def mcp_discovery_endpoint() -> Dict[str, Any]:
    """Unauthenticated MCP discovery endpoint."""
    return {
        "protocol": "mcp",
        "version": "2024-11-05",
        "transport": "sse",
        "endpoint": "/mcp",
        "authentication": {
            "type": "oauth2",
            "discovery": "/.well-known/oauth-authorization-server"
        }
    }

@mcp_router.get("/mcp")
async def mcp_sse_endpoint(
    current_user: User = Depends(get_current_user)  # Still requires auth
) -> EventSourceResponse:
    """MCP SSE endpoint - requires authentication."""
    return EventSourceResponse(authenticated_event_generator(current_user))
```

**Configure claude.ai with:** `https://linner.ddns.net:8383/mcp/discover`

**Pros:**
- ✅ Clear separation of concerns
- ✅ Main endpoint still requires auth
- ✅ Minimal information exposure

**Cons:**
- ⚠️ Requires claude.ai to support custom discovery endpoints (may not work)
- ⚠️ Non-standard approach

---

### Option 3: OPTIONS Preflight with MCP Headers (STANDARDS-BASED)

**Approach:** Return MCP capabilities in OPTIONS response (CORS preflight).

**Implementation:**
```python
@mcp_router.options("/mcp")
async def mcp_options() -> Response:
    """OPTIONS endpoint for MCP discovery via CORS preflight."""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type",
            "X-MCP-Version": "2024-11-05",
            "X-MCP-Transport": "sse",
            "X-MCP-Auth": "oauth2",
        }
    )
```

**Pros:**
- ✅ Standards-compliant (CORS)
- ✅ No authentication required for OPTIONS
- ✅ Minimal exposure

**Cons:**
- ⚠️ claude.ai may not check OPTIONS headers for discovery
- ⚠️ Untested approach

---

## Recommended Solution

**Use Option 1** (Unauthenticated GET with minimal response) because:

1. **Most likely to work with claude.ai**: Standard SSE endpoint at `/mcp`
2. **Security acceptable**: Only exposes that MCP server exists (public info anyway)
3. **OAuth still required**: Full functionality requires authentication
4. **Simple implementation**: Minimal code changes

---

## Implementation Plan

### Step 1: Update SSE Endpoint to Support Optional Auth

**File:** `src/code_indexer/server/mcp/protocol.py`

**Changes:**
1. Make `current_user` optional in GET `/mcp`
2. Parse Authorization header manually
3. Return different SSE streams based on authentication

**Code:**
```python
from typing import Optional
from fastapi import Header

@mcp_router.get("/mcp")
async def mcp_sse_endpoint(
    authorization: Optional[str] = Header(None)
) -> EventSourceResponse:
    """
    MCP SSE endpoint for server-to-client notifications.

    Supports both:
    - Unauthenticated: Returns minimal discovery stream for claude.ai
    - Authenticated: Returns full MCP notification stream with Bearer token
    """
    user = None

    # Try to authenticate if Authorization header provided
    if authorization:
        if authorization.startswith("Bearer "):
            token = authorization.split(" ", 1)[1]
            try:
                # Import and use existing auth logic
                from ..auth.dependencies import get_user_from_token
                user = await get_user_from_token(token)
            except Exception as e:
                # Invalid token - continue as unauthenticated
                pass

    # Return appropriate SSE stream
    if user:
        # Authenticated: full MCP capabilities
        return EventSourceResponse(authenticated_sse_generator(user))
    else:
        # Unauthenticated: minimal discovery stream
        return EventSourceResponse(discovery_sse_generator())


async def discovery_sse_generator():
    """Minimal SSE stream for unauthenticated MCP discovery."""
    import json

    # Send initial endpoint info
    yield {
        "event": "endpoint",
        "data": json.dumps({
            "protocol": "mcp",
            "version": "2024-11-05",
            "authentication": "oauth2"
        })
    }

    # Keep connection alive with periodic pings
    while True:
        await asyncio.sleep(30)
        yield {"event": "ping", "data": "keepalive"}


async def authenticated_sse_generator(user: User):
    """Full SSE stream for authenticated MCP clients."""
    import json

    # Send authenticated endpoint info
    yield {
        "event": "endpoint",
        "data": json.dumps({
            "protocol": "mcp",
            "version": "2024-11-05",
            "capabilities": {"tools": {}},
            "user": user.username
        })
    }

    # Full MCP notification stream
    # TODO: Implement actual MCP notifications
    while True:
        await asyncio.sleep(30)
        yield {"event": "ping", "data": "authenticated"}
```

### Step 2: Keep POST `/mcp` Fully Authenticated

**No changes needed** - JSON-RPC endpoint should always require authentication.

```python
@mcp_router.post("/mcp")
async def mcp_endpoint(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user)  # Still required
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    # ... existing implementation
```

### Step 3: Test Discovery Flow

**Test 1: Unauthenticated Discovery**
```bash
curl -s https://linner.ddns.net:8383/mcp
# Expected: SSE stream with discovery event
```

**Test 2: Authenticated SSE**
```bash
# Get token first
TOKEN=$(curl -s -X POST https://linner.ddns.net:8383/oauth/token ...)

# Connect with auth
curl -s -H "Authorization: Bearer $TOKEN" https://linner.ddns.net:8383/mcp
# Expected: SSE stream with full capabilities
```

**Test 3: claude.ai Discovery**
1. Enter URL: `https://linner.ddns.net:8383`
2. **Expected:** OAuth flow initiates (no more "Server not found")
3. Login with credentials
4. **Expected:** Connection successful

---

## Security Considerations

### What Information is Exposed Without Auth?

**Minimal:**
- MCP server exists at this URL
- Protocol version (2024-11-05)
- Requires OAuth authentication

**NOT Exposed:**
- User data
- Repository information
- MCP tools/capabilities
- Server internals

### Attack Surface

**SSE Connection Exhaustion:**
- Unauthenticated clients could open many SSE connections
- **Mitigation:** Rate limit by IP address

**Recommendation:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@mcp_router.get("/mcp")
@limiter.limit("10/minute")  # Max 10 SSE connections per minute per IP
async def mcp_sse_endpoint(...):
    ...
```

---

## Testing Checklist

### Phase 1: Endpoint Testing
- [ ] GET `/mcp` without auth returns discovery SSE stream
- [ ] GET `/mcp` with valid Bearer token returns authenticated SSE stream
- [ ] GET `/mcp` with invalid Bearer token returns discovery SSE stream
- [ ] POST `/mcp` without auth returns 401
- [ ] POST `/mcp` with valid auth works

### Phase 2: claude.ai Integration
- [ ] Enter `https://linner.ddns.net:8383` in claude.ai Settings > Connectors
- [ ] No "Server not found" error
- [ ] OAuth flow initiates
- [ ] Browser shows CIDX login form
- [ ] After login, redirects to claude.ai
- [ ] Connection shows as active in claude.ai

### Phase 3: Functionality Testing
- [ ] Can list MCP tools from claude.ai
- [ ] Can execute search_code tool
- [ ] Can browse repositories
- [ ] All tools work with authenticated connection

---

## Files to Modify

1. **`src/code_indexer/server/mcp/protocol.py`**
   - Modify `mcp_sse_endpoint` to accept optional Authorization header
   - Add `discovery_sse_generator` function
   - Add `authenticated_sse_generator` function (rename existing)
   - Add rate limiting (optional but recommended)

2. **`tests/unit/server/mcp/test_protocol.py`** (if exists)
   - Add tests for unauthenticated SSE discovery
   - Add tests for authenticated SSE with Bearer token
   - Add tests for invalid token handling

---

## Alternative: Check Anthropic Documentation

Before implementing, verify with Anthropic support/documentation:
- Does claude.ai support OAuth-based MCP servers?
- What discovery mechanism does it use?
- Is there a specific endpoint format required?

**Contact:**
- Anthropic support
- MCP GitHub issues: https://github.com/modelcontextprotocol
- Claude.ai documentation

---

## Conclusion

The "Server not found" error occurs because claude.ai cannot discover the MCP server due to authentication requirement on GET `/mcp`.

**Fix:** Allow unauthenticated GET requests to return minimal SSE discovery stream, while keeping all actual functionality (POST requests, tools) behind authentication.

**Risk:** Low - only exposes that MCP server exists (public info)
**Benefit:** Enables claude.ai OAuth flow to start
**Implementation:** ~50 lines of code changes

---

**End of Report**

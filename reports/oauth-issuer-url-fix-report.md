# OAuth Issuer URL Fix - Comprehensive Report

**Date**: 2025-11-17
**Branch**: `feature/epic-477-mcp-oauth-integration`
**Issue**: claude.ai cannot connect to CIDX MCP server, but Claude Code CLI works
**Root Cause**: Hardcoded `http://localhost:8000` in OAuth discovery metadata

---

## Executive Summary

The CIDX MCP server has a **critical OAuth configuration bug** that prevents claude.ai from connecting while Claude Code CLI works around it. The OAuth discovery endpoint returns hardcoded `localhost:8000` URLs, which breaks claude.ai's strict OAuth compliance but is ignored by Claude Code CLI's more lenient implementation.

**Impact**:
- ❌ claude.ai web interface: Cannot connect (click connect → UI refreshes → fails)
- ❌ Claude Desktop app: Browser opens to blank page → infinite loop → cannot connect
- ✅ Claude Code CLI with `--transport http`: Works (ignores discovery metadata, constructs correct URLs)

**Required Action**: Fix hardcoded issuer URLs in three locations to support BOTH clients.

---

## Technical Analysis

### How MCP Clients Connect to CIDX Server

#### **Claude Code CLI** (Currently Working ✅)

**Two Transport Modes**:

1. **STDIO Transport** (Default, No OAuth):
   ```json
   {
     "mcpServers": {
       "cidx": {
         "command": "cidx",
         "args": ["mcp"],
         "transport": "stdio"
       }
     }
   }
   ```
   - Spawns `cidx mcp` as subprocess
   - Communication via stdin/stdout pipes
   - No HTTP, no OAuth, no discovery needed
   - **This is why "it works with Claude Code"**

2. **HTTP Transport** (With OAuth, User Confirmed Working):
   ```bash
   claude mcp add --transport http cidx https://linner.ddns.net:8383
   ```
   - User confirmed: "I registered with claude code using --transport http and it made me do an oauth auth loop"
   - OAuth flow completed successfully with login page
   - **Key difference**: Claude Code appears to **ignore discovery metadata** and construct OAuth URLs from base URL provided

**Why Claude Code HTTP Transport Works Despite Broken Discovery Metadata**:
- Fetches `https://linner.ddns.net:8383/.well-known/oauth-authorization-server`
- Sees `"issuer": "http://localhost:8000"` in response
- **Ignores these URLs** (non-compliant but practical)
- **Constructs correct URLs** using base URL: `https://linner.ddns.net:8383/oauth/*`
- Registers with localhost redirect_uri (standard for CLI OAuth)
- Completes flow successfully

#### **claude.ai** (Currently Broken ❌)

**HTTP Transport Only** (No STDIO Option):

**Connection Flow**:
1. User adds MCP server URL: `https://linner.ddns.net:8383` or `https://linner.ddns.net:8383/mcp`
2. claude.ai fetches: `https://linner.ddns.net:8383/.well-known/oauth-authorization-server`
3. claude.ai reads metadata:
   ```json
   {
     "issuer": "http://localhost:8000",
     "authorization_endpoint": "http://localhost:8000/oauth/authorize",
     "token_endpoint": "http://localhost:8000/oauth/token",
     "registration_endpoint": "http://localhost:8000/oauth/register"
   }
   ```
4. claude.ai **strictly follows OAuth 2.1 spec** and attempts: `http://localhost:8000/oauth/register`
5. **FAILS**: localhost doesn't exist for claude.ai's servers
6. Authorization flow never initiates
7. Login screen never appears

**Expected OAuth Callback**:
- claude.ai uses: `https://claude.ai/api/mcp/auth_callback` (may change to `.com` in future)
- OAuth client name: "Claude"

**Why It Fails**:
- claude.ai is OAuth-compliant and trusts discovery metadata
- Cannot ignore invalid URLs like Claude Code does
- Proper fix required for compatibility

---

## Current Discovery Metadata (BROKEN)

```bash
$ curl -s https://linner.ddns.net:8383/.well-known/oauth-authorization-server
```

```json
{
  "issuer": "http://localhost:8000",
  "authorization_endpoint": "http://localhost:8000/oauth/authorize",
  "token_endpoint": "http://localhost:8000/oauth/token",
  "registration_endpoint": "http://localhost:8000/oauth/register",
  "code_challenge_methods_supported": ["S256"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "response_types_supported": ["code"]
}
```

**Problem**: All URLs point to `localhost:8000` instead of `https://linner.ddns.net:8383`

---

## Root Cause: Hardcoded Issuer URLs

### Three Locations Where Issuer is Hardcoded

#### **Location 1**: `src/code_indexer/server/app.py:1360`
```python
oauth_manager = OAuthManager(
    db_path=oauth_db_path,
    issuer="http://localhost:8000",  # ❌ HARDCODED
    user_manager=user_manager
)
```

#### **Location 2**: `src/code_indexer/server/app.py:5351`
```python
# RFC 8414 compliance: OAuth discovery at root level
manager = OAuthManager(
    db_path=str(oauth_db),
    issuer="http://localhost:8000"  # ❌ HARDCODED
)
return manager.get_discovery_metadata()
```

#### **Location 3**: `src/code_indexer/server/auth/oauth/routes.py:22`
```python
def get_oauth_manager() -> OAuthManager:
    """Get OAuth manager instance."""
    oauth_db = Path.home() / ".cidx-server" / "oauth.db"
    return OAuthManager(
        db_path=str(oauth_db),
        issuer="http://localhost:8000"  # ❌ HARDCODED
    )
```

#### **Default Parameter**: `src/code_indexer/server/auth/oauth/oauth_manager.py:34`
```python
def __init__(
    self,
    db_path: Optional[str] = None,
    issuer: str = "http://localhost:8000",  # ❌ HARDCODED DEFAULT
    user_manager: Optional["UserManager"] = None,
    audit_logger: Optional["PasswordChangeAuditLogger"] = None
):
    self.issuer = issuer
```

### How Discovery Metadata is Generated

```python
# oauth_manager.py:88-97
def get_discovery_metadata(self) -> Dict[str, Any]:
    return {
        "issuer": self.issuer,  # Uses hardcoded value
        "authorization_endpoint": f"{self.issuer}/oauth/authorize",
        "token_endpoint": f"{self.issuer}/oauth/token",
        "registration_endpoint": f"{self.issuer}/oauth/register",
        "code_challenge_methods_supported": ["S256"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "response_types_supported": ["code"]
    }
```

---

## Proposed Solution

### **Approach: Environment Variable with Smart Default**

Use `CIDX_ISSUER_URL` environment variable with fallback to localhost for development.

**Advantages**:
- ✅ Supports production deployment (`https://linner.ddns.net:8383`)
- ✅ Supports local development (`http://localhost:8000`)
- ✅ No code changes to discovery endpoint logic
- ✅ Works for both claude.ai and Claude Code CLI
- ✅ Can be set in systemd service, Docker, or startup script
- ✅ Backward compatible (defaults to localhost)

**Implementation Steps**:

#### **Step 1**: Update `oauth_manager.py` to Read Environment Variable

```python
# src/code_indexer/server/auth/oauth/oauth_manager.py

import os  # Add import

def __init__(
    self,
    db_path: Optional[str] = None,
    issuer: Optional[str] = None,  # Make optional
    user_manager: Optional["UserManager"] = None,
    audit_logger: Optional["PasswordChangeAuditLogger"] = None
):
    # Priority: explicit issuer > environment variable > default localhost
    self.issuer = issuer or os.getenv("CIDX_ISSUER_URL", "http://localhost:8000")
    # ... rest of __init__
```

#### **Step 2**: Update All Three Instantiation Sites

**Site 1** - `app.py:1360`:
```python
oauth_manager = OAuthManager(
    db_path=oauth_db_path,
    issuer=None,  # Will use environment variable or default
    user_manager=user_manager
)
```

**Site 2** - `app.py:5351`:
```python
manager = OAuthManager(
    db_path=str(oauth_db),
    issuer=None  # Will use environment variable or default
)
```

**Site 3** - `routes.py:22`:
```python
def get_oauth_manager() -> OAuthManager:
    oauth_db = Path.home() / ".cidx-server" / "oauth.db"
    return OAuthManager(
        db_path=str(oauth_db),
        issuer=None  # Will use environment variable or default
    )
```

**Alternative**: Pass `issuer=None` to all three locations, or simply remove the parameter (will use default from `__init__`).

#### **Step 3**: Set Environment Variable on Server

**For systemd service**:
```bash
# Edit /etc/systemd/system/cidx-server.service
[Service]
Environment="CIDX_ISSUER_URL=https://linner.ddns.net:8383"
```

**For manual start**:
```bash
export CIDX_ISSUER_URL="https://linner.ddns.net:8383"
cidx server start
```

**For Docker/container**:
```bash
docker run -e CIDX_ISSUER_URL=https://linner.ddns.net:8383 ...
```

---

## Expected Results After Fix

### Discovery Metadata (CORRECT)

```json
{
  "issuer": "https://linner.ddns.net:8383",
  "authorization_endpoint": "https://linner.ddns.net:8383/oauth/authorize",
  "token_endpoint": "https://linner.ddns.net:8383/oauth/token",
  "registration_endpoint": "https://linner.ddns.net:8383/oauth/register",
  "code_challenge_methods_supported": ["S256"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "response_types_supported": ["code"]
}
```

### Claude.ai Connection Flow (FIXED)

1. User adds: `https://linner.ddns.net:8383`
2. claude.ai fetches discovery metadata
3. claude.ai sees correct URLs: `https://linner.ddns.net:8383/oauth/*`
4. claude.ai registers at: `https://linner.ddns.net:8383/oauth/register`
5. claude.ai redirects to: `https://linner.ddns.net:8383/oauth/authorize`
6. User sees login form ✅
7. User enters credentials
8. Server redirects to: `https://claude.ai/api/mcp/auth_callback?code=...&state=...`
9. claude.ai exchanges code for token
10. claude.ai connects to SSE endpoint: `GET https://linner.ddns.net:8383/mcp` with Bearer token
11. Connection established ✅

### Claude Code CLI (STILL WORKS)

**STDIO Transport** (no change):
- Still works exactly as before
- No OAuth, no discovery needed

**HTTP Transport** (no change):
- Still works, now with correct discovery metadata
- Either uses discovery metadata (if fixed) or ignores it (current behavior)
- Either way: **no breaking changes**

---

## Testing Plan

### Step 1: Verify Current State (Baseline)

```bash
# Test 1: Current broken discovery metadata
curl -s https://linner.ddns.net:8383/.well-known/oauth-authorization-server | jq .issuer
# Expected: "http://localhost:8000" ❌

# Test 2: Claude Code CLI STDIO still works
claude # In existing session with STDIO transport
/mcp
# Expected: Works ✅

# Test 3: Claude Code CLI HTTP still works
claude mcp list
# Expected: Shows cidx server if already registered ✅
```

### Step 2: Deploy Fix

```bash
# On server (192.168.60.30):
cd /path/to/code-indexer
git pull origin feature/epic-477-mcp-oauth-integration

# Set environment variable
export CIDX_ISSUER_URL="https://linner.ddns.net:8383"

# Restart server
cidx server stop
cidx server start

# OR if using systemd:
sudo systemctl edit cidx-server  # Add Environment line
sudo systemctl restart cidx-server
```

### Step 3: Verify Fix

```bash
# Test 1: Discovery metadata now correct
curl -s https://linner.ddns.net:8383/.well-known/oauth-authorization-server | jq .issuer
# Expected: "https://linner.ddns.net:8383" ✅

# Test 2: All OAuth endpoints return correct URLs
curl -s https://linner.ddns.net:8383/.well-known/oauth-authorization-server | jq '{issuer, authorization_endpoint, token_endpoint, registration_endpoint}'
# Expected: All URLs use https://linner.ddns.net:8383 ✅

# Test 3: Registration endpoint works
curl -X POST https://linner.ddns.net:8383/oauth/register \
  -H "Content-Type: application/json" \
  -d '{"client_name": "Test", "redirect_uris": ["http://localhost:8080/callback"]}'
# Expected: Returns client_id and registration details ✅
```

### Step 4: Test Claude Code CLI (Regression Test)

```bash
# Test STDIO transport (should still work)
claude # Existing session
/mcp
# Expected: Works ✅

# Test HTTP transport (should still work)
# If already registered: should continue working
# If new registration: should work with correct discovery URLs
```

### Step 5: Test claude.ai Connection

**Web Interface**:
1. Go to claude.ai
2. Settings → Connectors
3. Add MCP server: `https://linner.ddns.net:8383` or `https://linner.ddns.net:8383/mcp`
4. **Expected**: OAuth flow initiates ✅
5. **Expected**: Browser shows login form ✅
6. Enter credentials
7. **Expected**: Successful authorization and connection ✅

**Desktop App**:
1. Open Claude Desktop
2. Settings → Connectors
3. Add MCP server: `https://linner.ddns.net:8383`
4. **Expected**: Browser opens with login form ✅
5. Enter credentials
6. Click "Open Claude" in dialog
7. **Expected**: Returns to app, connection successful ✅

---

## Alternative Solutions Considered

### Option 2: Auto-detect from Request Headers

```python
def get_oauth_manager(request: Request) -> OAuthManager:
    # Derive issuer from incoming request
    scheme = "https" if request.url.scheme == "https" else "http"
    issuer = f"{scheme}://{request.headers.get('host')}"
    return OAuthManager(db_path=str(oauth_db), issuer=issuer)
```

**Pros**:
- Automatic for all environments
- No configuration needed

**Cons**:
- Requires passing Request object to all OAuth manager instantiations
- More complex refactoring
- May not work for app.py:1360 (server startup, no request context)

**Recommendation**: Consider for future enhancement after environment variable approach is working.

### Option 3: Configuration File

Add to server config:
```json
{
  "host": "0.0.0.0",
  "port": 8383,
  "issuer_url": "https://linner.ddns.net:8383"
}
```

**Pros**:
- Centralized configuration

**Cons**:
- Need to add config file support
- More code changes
- Server config may not exist yet

**Recommendation**: Good for future, but environment variable is simpler for now.

---

## Files to Modify

### Required Changes (4 files):

1. **`src/code_indexer/server/auth/oauth/oauth_manager.py`**
   - Add `import os`
   - Change `issuer` parameter to `Optional[str] = None`
   - Add logic: `self.issuer = issuer or os.getenv("CIDX_ISSUER_URL", "http://localhost:8000")`

2. **`src/code_indexer/server/app.py`** (2 locations)
   - Line ~1360: Change `issuer="http://localhost:8000"` to `issuer=None`
   - Line ~5351: Change `issuer="http://localhost:8000"` to `issuer=None`

3. **`src/code_indexer/server/auth/oauth/routes.py`**
   - Line ~22: Change `issuer="http://localhost:8000"` to `issuer=None`

### Server Deployment:

4. **Set environment variable** on server (192.168.60.30):
   - Systemd service file, or
   - Shell environment, or
   - Docker/container environment

---

## Risk Assessment

### Compatibility Risks: **LOW** ✅

- **Claude Code CLI STDIO**: No change (doesn't use OAuth)
- **Claude Code CLI HTTP**: Will continue working (uses discovery or ignores it)
- **claude.ai**: Currently broken, will be fixed
- **Local development**: Defaults to `http://localhost:8000` (backward compatible)

### Breaking Changes: **NONE** ✅

- Default behavior preserved (localhost)
- Existing clients continue working
- Only enables new functionality (claude.ai support)

### Rollback Plan: **SIMPLE** ✅

```bash
# If issues occur:
unset CIDX_ISSUER_URL
cidx server restart
# Reverts to localhost URLs
```

---

## Success Criteria

### Must Have (Critical):
1. ✅ Discovery metadata returns `https://linner.ddns.net:8383` URLs when environment variable set
2. ✅ claude.ai web interface can connect and complete OAuth flow
3. ✅ Claude Desktop app can connect and complete OAuth flow
4. ✅ Claude Code CLI STDIO transport still works (regression test)
5. ✅ Claude Code CLI HTTP transport still works (regression test)

### Should Have (Important):
6. ✅ Local development still works without environment variable
7. ✅ Documentation updated with environment variable usage

### Nice to Have (Future):
8. Request-based auto-detection (Option 2)
9. Configuration file support (Option 3)
10. Server admin UI to set issuer URL

---

## Documentation Updates Needed

### README.md

Add section on OAuth configuration:

```markdown
### OAuth Configuration for Remote Access

When deploying CIDX server for remote access (claude.ai integration), set the issuer URL:

**Environment Variable**:
```bash
export CIDX_ISSUER_URL="https://your-domain.com:8383"
cidx server start
```

**Systemd Service**:
```ini
[Service]
Environment="CIDX_ISSUER_URL=https://your-domain.com:8383"
```

**Default**: `http://localhost:8000` (for local development)
```

### Server Documentation

Update MCP integration docs to explain:
- Why issuer URL must match public URL
- How to set environment variable
- Troubleshooting OAuth discovery issues

---

## Conclusion

The hardcoded `localhost:8000` issuer URLs break OAuth-compliant clients (claude.ai) while more lenient clients (Claude Code CLI) work around it.

**Recommended Fix**: Environment variable approach
- **Minimal code changes** (4 files, ~10 lines)
- **Zero breaking changes** (backward compatible)
- **Supports both clients** (claude.ai + Claude Code CLI)
- **Production ready** (can be deployed immediately)

**Next Steps**:
1. Implement environment variable support in oauth_manager.py
2. Update three instantiation sites to pass `issuer=None`
3. Deploy to server with `CIDX_ISSUER_URL=https://linner.ddns.net:8383`
4. Test discovery metadata returns correct URLs
5. Test claude.ai connection
6. Verify Claude Code CLI still works (regression)

---

## Appendix: Debugging Commands

```bash
# Check current discovery metadata
curl -s https://linner.ddns.net:8383/.well-known/oauth-authorization-server | jq

# Test OAuth registration
curl -X POST https://linner.ddns.net:8383/oauth/register \
  -H "Content-Type: application/json" \
  -d '{"client_name":"Test","redirect_uris":["http://localhost/callback"]}'

# Check server environment
ssh sebabattig@192.168.60.30 'env | grep CIDX'

# Restart server with new environment
ssh sebabattig@192.168.60.30 'export CIDX_ISSUER_URL=https://linner.ddns.net:8383 && cidx server restart'

# Check server logs
ssh sebabattig@192.168.60.30 'tail -f ~/.cidx-server/logs/server.log'
```

---

**End of Report**

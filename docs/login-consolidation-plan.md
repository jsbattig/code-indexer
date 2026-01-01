# Login Page Consolidation Plan

**Status**: Planning
**Created**: 2025-12-31
**Author**: Architecture Planning Session

## Executive Summary

This document outlines the plan to consolidate three separate login pages (admin, user, OAuth) into a single unified login page with smart routing, consistent SSO support, and proper OAuth 2.1 authorization flow separation.

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [Proposed Architecture](#proposed-architecture)
3. [Implementation Plan](#implementation-plan)
4. [Testing Strategy](#testing-strategy)
5. [Migration Considerations](#migration-considerations)
6. [Open Questions](#open-questions)

---

## Current State Analysis

### Three Login Pages Identified

| Page | Route | Template | Role Access | SSO Support | Landing Page |
|------|-------|----------|-------------|-------------|--------------|
| **Admin Login** | `/admin/login` | `login.html` | Admin only | Yes (if enabled) | `/admin` dashboard |
| **User Login** | `/user/login` | `user_login.html` | Any role | No | `/user/api-keys` |
| **OAuth Login** | `/oauth/authorize` | Dynamic HTML | Any role | Yes (if enabled) | Back to OAuth client |

**File Locations:**
- Admin: `src/code_indexer/server/web/templates/login.html` + `routes.py:148-273`
- User: `src/code_indexer/server/web/templates/user_login.html` + `routes.py:3748-3846`
- OAuth: `src/code_indexer/server/auth/oauth/routes.py:195-321` (dynamic HTML)

### Session Management Analysis

**Good News: Already Unified!**

All three login pages use the same `SessionManager` (`src/code_indexer/server/web/auth.py`):
- Cookie name: `"session"`
- Timeout: 8 hours (28,800 seconds)
- Signing: `itsdangerous.URLSafeTimedSerializer`
- Session data: `username`, `role`, `csrf_token`, `created_at`
- Security: httpOnly, secure (non-localhost), samesite=lax

**Minor Difference:**
- User login sets CSRF cookie with `path="/user"` (lines 3780, 3831)
- Admin/OAuth use default path (no restriction)

**Implication:** No complex session consolidation needed. Sessions already work across all interfaces.

### Feature Comparison: Admin vs User Interfaces

**Admin Interface** (`base.html` template, 9 pages):
- Dashboard (system health, statistics)
- Users (create, edit, delete users)
- Golden Repos (add, remove, refresh global repos)
- Repositories (view all user activations)
- Jobs (background job monitoring)
- Query (semantic code search interface)
- Config (system configuration)
- API Keys (manage admin API access)
- SSH Keys (manage SSH keys for git operations)

**Access Control:** Requires `UserRole.ADMIN` (enforced by `require_admin_session()`)

**User Interface** (`user_base.html` template, 2 pages):
- API Keys (view/regenerate personal API keys)
- MCP Credentials (view MCP-specific credentials)

**Access Control:** Accepts ANY role (normal_user, power_user, admin)

**Key Observation:** Admin users can access both interfaces, but regular users cannot access admin interface. No overlap in features - admin interface is superset functionality.

### OAuth Authorization Flow Analysis

**Current Flow (Problematic):**

```
GET /oauth/authorize?client_id=...&redirect_uri=...&code_challenge=...
  |
  v
Shows login form (username/password + SSO button)
  |
  v
POST /oauth/authorize with credentials
  |
  v
Authenticates user + issues authorization code in single step
  |
  v
Redirects to OAuth client with code
```

**Problems with Current Flow:**

1. **Authentication and authorization conflated** - Should be separate steps per OAuth 2.1 spec
2. **No session reuse** - User must re-authenticate even if already logged in
3. **OAuth-specific login page** - Duplicates authentication logic from admin/user logins

**Standard OAuth 2.1 Flow (Recommended):**

```
GET /oauth/authorize?client_id=...&redirect_uri=...&code_challenge=...
  |
  v
Check if user has valid session
  |
  +--- NO ---> Redirect to /login?redirect_to=/oauth/authorize?...
  |              |
  |              v
  |            User authenticates (creates session)
  |              |
  |              v
  |            Redirect back to /oauth/authorize
  |
  +--- YES --> User is authenticated
                  |
                  v
                Show authorization consent screen
                  |
                  v
                User clicks "Authorize"
                  |
                  v
                Issue authorization code
                  |
                  v
                Redirect to OAuth client with code
```

**Benefits of Separation:**

1. **Session reuse** - If user already logged in to admin/user interface, OAuth flow skips login
2. **Proper consent** - User sees what they're authorizing (OAuth 2.1 best practice)
3. **Single authentication logic** - All login flows use same unified page

### SSO/OIDC Integration Status

**Current SSO Support:**

| Context | SSO Button | Implementation |
|---------|------------|----------------|
| Admin Login | Yes (if OIDC enabled) | `login.html` shows SSO button, redirects to `/auth/sso/login` |
| User Login | No | No SSO button in `user_login.html` |
| OAuth Login | Yes (if OIDC enabled) | Dynamic HTML shows SSO button, redirects to `/oauth/authorize/sso` |

**OIDC Callback Handlers:**

1. `/auth/sso/callback` - Admin SSO callback (`src/code_indexer/server/auth/oidc/routes.py:19-142`)
   - Exchanges OIDC code for tokens
   - Creates user session
   - Redirects to `/admin`

2. `/oauth/authorize/sso` - OAuth SSO initiation (`src/code_indexer/server/auth/oauth/routes.py:324-374`)
   - Stores OAuth parameters in OIDC state
   - Redirects to OIDC provider
   - After OIDC callback: Issues OAuth authorization code

**OIDC Configuration** (`src/code_indexer/server/auth/oidc/oidc_manager.py`):
- Lazy initialization of OIDC provider
- Just-in-time user provisioning
- Configurable via environment variables

**Gap Identified:** User login lacks SSO support, creating inconsistent experience.

---

## Proposed Architecture

### Design Principles

1. **Single Login Page** - One unified login page serves all contexts (admin, user, OAuth)
2. **Smart Routing** - Post-login redirect based on:
   - Explicit `redirect_to` parameter (highest priority)
   - User role (admin → admin dashboard, others → user interface)
   - Context detection (OAuth flow returns to authorization)
3. **Consistent SSO** - OIDC available for all login contexts, not just admin/OAuth
4. **OAuth Separation** - Authentication (login) separate from authorization (consent)
5. **Session Reuse** - If user already authenticated, skip login in OAuth flow

### Unified Login Page Design

**Route:** `/login`

**Visual Design:**
- Modern gradient background (like current OAuth page)
- Clean, centered login card
- Username/password fields
- SSO button (conditional, if OIDC enabled)
- Error/info message display
- Responsive layout (mobile-friendly)

**Template:** `unified_login.html` (standalone, doesn't extend base templates)

**Parameters:**
- `redirect_to` (optional) - URL to redirect after successful login
- `error` (optional) - Error message to display
- `info` (optional) - Info message to display (e.g., "Session expired")

### Smart Redirect Logic

**After successful authentication:**

```
1. If redirect_to parameter exists → Redirect to that URL
2. Else if user.role == "admin" → Redirect to /admin (admin dashboard)
3. Else → Redirect to /user/api-keys (user interface)
```

**URL Validation for redirect_to:**
- Must be relative URL (starts with `/`)
- Prevents open redirect vulnerabilities
- Example: `/oauth/authorize?client_id=...` is valid
- Example: `https://evil.com` is blocked

### OAuth Authorization Flow (Revised)

**New Flow:**

```
Claude Code initiates OAuth:
GET /oauth/authorize?client_id=...&redirect_uri=...&code_challenge=...
  |
  v
Check if user has valid session
  |
  +--- NO ---> Redirect to /login?redirect_to=/oauth/authorize?...
  |              |
  |              v
  |            User logs in via unified login page
  |              |
  |              v
  |            Session created, redirect to /oauth/authorize
  |
  +--- YES --> User is authenticated
                  |
                  v
                Show authorization consent screen
                "CIDX is requesting access to your account"
                [Authorize Access] button
                  |
                  v
                User clicks Authorize
                  |
                  v
                Generate authorization code with PKCE
                  |
                  v
                Redirect to OAuth client: {redirect_uri}?code=...&state=...
```

**Key Changes:**

1. `/oauth/authorize` GET endpoint checks for existing session first
2. If no session: redirects to `/login?redirect_to=/oauth/authorize?...`
3. After login: user returns to `/oauth/authorize` (now authenticated)
4. Shows consent screen (new template: `oauth_authorize_consent.html`)
5. POST to `/oauth/authorize` issues authorization code

**New Template:** `oauth_authorize_consent.html`
- Shows: "CIDX Server is requesting access to your account"
- Displays: Username, client information
- Button: "Authorize Access"
- Hidden form fields: client_id, redirect_uri, code_challenge, etc.

### SSO Integration (Unified)

**New SSO Initiation Route:** `/login/sso`

**Parameters:**
- `redirect_to` (optional) - Preserved through OIDC flow

**Flow:**

```
User clicks "Sign in with SSO" on unified login page
  |
  v
GET /login/sso?redirect_to=/oauth/authorize?...
  |
  v
Store redirect_to in OIDC state parameter
  |
  v
Redirect to OIDC provider authorization URL
  |
  v
User authenticates at OIDC provider
  |
  v
OIDC provider redirects to: /auth/sso/callback?code=...&state=...
  |
  v
Exchange OIDC code for tokens
  |
  v
Extract user info from OIDC claims
  |
  v
Match or create user (JIT provisioning)
  |
  v
Create user session
  |
  v
Extract redirect_to from state
  |
  +--- redirect_to exists --> Redirect to redirect_to URL
  |
  +--- No redirect_to --> Use smart redirect logic (role-based)
```

**OIDC Callback Enhancement:**

Update `/auth/sso/callback` to handle three contexts:
1. **OAuth flow** - redirect_to points to `/oauth/authorize?...` (existing)
2. **Admin login** - no redirect_to, user is admin (existing)
3. **Unified login** - redirect_to from login page (NEW)

---

## Implementation Plan

### Phase 1: Create Unified Login Template

**File:** `src/code_indexer/server/web/templates/unified_login.html`

**Template Features:**

```html
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CIDX Login</title>
    <style>
        /* Modern gradient design from OAuth page */
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            max-width: 400px;
            width: 100%;
        }
        /* ... rest of styles ... */
    </style>
</head>
<body>
    <div class="container">
        <h2>CIDX Login</h2>
        <p>Sign in to access your account</p>

        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}

        {% if info %}
        <div class="info">{{ info }}</div>
        {% endif %}

        {% if sso_enabled %}
        <button type="button" class="sso-button" onclick="redirectToSSO()">
            Sign in with SSO
        </button>
        <div class="divider"><span>or</span></div>
        {% endif %}

        <form method="post" action="/login">
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
            {% if redirect_to %}
            <input type="hidden" name="redirect_to" value="{{ redirect_to }}">
            {% endif %}
            <input type="text" name="username" placeholder="Username" required autofocus>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Sign In</button>
        </form>
    </div>

    <script>
        function redirectToSSO() {
            let url = '/login/sso';
            {% if redirect_to %}
            url += '?redirect_to=' + encodeURIComponent('{{ redirect_to | urlencode }}');
            {% endif %}
            window.location.href = url;
        }
    </script>
</body>
</html>
```

**Template Variables:**
- `csrf_token` - CSRF protection token
- `redirect_to` - Optional redirect URL after login
- `error` - Optional error message
- `info` - Optional info message
- `sso_enabled` - Boolean, whether OIDC is configured

**Styling Notes:**
- Reuse gradient design from current OAuth page (proven good UX)
- Responsive layout (mobile-friendly)
- Clean, modern aesthetic
- Error/info messages styled distinctly

### Phase 2: Create Unified Login Routes

**File:** `src/code_indexer/server/web/routes.py`

**Add to imports:**

```python
from urllib.parse import quote, unquote
```

**New routes (add to main app router):**

```python
@app.get("/login", response_class=HTMLResponse)
async def unified_login_page(
    request: Request,
    redirect_to: Optional[str] = None,
    error: Optional[str] = None,
    info: Optional[str] = None,
):
    """
    Unified login page for all contexts (admin, user, OAuth).

    Supports:
    - SSO via OIDC (if enabled)
    - Username/password authentication
    - Smart redirect after login based on redirect_to parameter or user role

    Args:
        request: FastAPI Request object
        redirect_to: Optional URL to redirect after successful login
        error: Optional error message to display
        info: Optional info message to display
    """
    # Generate CSRF token for the form
    csrf_token = generate_csrf_token()

    # Check if there's an expired session
    session_manager = get_session_manager()
    if not info and session_manager.is_session_expired(request):
        info = "Session expired, please login again"

    # Check if OIDC is enabled
    from code_indexer.server.auth.oidc import routes as oidc_routes
    sso_enabled = False
    if oidc_routes.oidc_manager and hasattr(oidc_routes.oidc_manager, "is_enabled"):
        sso_enabled = oidc_routes.oidc_manager.is_enabled()

    # Create response with CSRF token in signed cookie
    response = templates.TemplateResponse(
        "unified_login.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "redirect_to": redirect_to,
            "error": error,
            "info": info,
            "sso_enabled": sso_enabled,
        },
    )

    # Set CSRF token in signed cookie for validation on POST
    set_csrf_cookie(response, csrf_token)

    return response


@app.post("/login", response_class=HTMLResponse)
async def unified_login_submit(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: Optional[str] = Form(None),
    redirect_to: Optional[str] = Form(None),
):
    """
    Process unified login form submission.

    Validates credentials and creates session on success.
    Accepts ANY role (normal_user, power_user, admin).
    Redirects based on redirect_to parameter or user role.

    Args:
        request: FastAPI Request object
        response: FastAPI Response object
        username: Username from form
        password: Password from form
        csrf_token: CSRF token from form
        redirect_to: Optional redirect URL from form
    """
    # CSRF validation - validate token against signed cookie
    if not validate_login_csrf_token(request, csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing or invalid",
        )

    # Get user manager from dependencies
    user_manager = dependencies.user_manager
    if not user_manager:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User manager not available",
        )

    # Authenticate user (any role accepted)
    user = user_manager.authenticate_user(username, password)

    if user is None:
        # Invalid credentials - show error with new CSRF token
        new_csrf_token = generate_csrf_token()
        error_response = templates.TemplateResponse(
            "unified_login.html",
            {
                "request": request,
                "csrf_token": new_csrf_token,
                "redirect_to": redirect_to,
                "error": "Invalid username or password",
                "sso_enabled": False,  # Will be set by template logic
            },
            status_code=200,
        )
        set_csrf_cookie(error_response, new_csrf_token)
        return error_response

    # Validate redirect_to URL (prevent open redirect)
    safe_redirect = None
    if redirect_to:
        # Only allow relative URLs starting with /
        if redirect_to.startswith("/") and not redirect_to.startswith("//"):
            safe_redirect = redirect_to

    # Smart redirect logic
    if safe_redirect:
        # Explicit redirect_to parameter takes precedence
        redirect_url = safe_redirect
    elif user.role.value == "admin":
        # Admin users go to admin dashboard
        redirect_url = "/admin"
    else:
        # Non-admin users go to user interface
        redirect_url = "/user/api-keys"

    # Create session for authenticated user
    session_manager = get_session_manager()
    redirect_response = RedirectResponse(
        url=redirect_url,
        status_code=status.HTTP_303_SEE_OTHER,
    )
    session_manager.create_session(
        redirect_response,
        username=user.username,
        role=user.role.value,
    )

    return redirect_response
```

**Helper function (already exists, ensure it's available):**

```python
def validate_login_csrf_token(request: Request, submitted_token: Optional[str]) -> bool:
    """
    Validate CSRF token from signed cookie.

    Args:
        request: FastAPI Request object
        submitted_token: CSRF token from form submission

    Returns:
        True if valid, False otherwise
    """
    if not submitted_token:
        return False

    # Get CSRF token from signed cookie
    csrf_cookie = request.cookies.get("csrf_token")
    if not csrf_cookie:
        return False

    try:
        # Verify signature (using same serializer as SessionManager)
        serializer = URLSafeTimedSerializer(get_secret_key())
        stored_token = serializer.loads(csrf_cookie, salt="csrf-token", max_age=3600)
        return secrets.compare_digest(stored_token, submitted_token)
    except (SignatureExpired, BadSignature):
        return False
```

### Phase 3: Add SSO Initiation Route

**File:** `src/code_indexer/server/web/routes.py`

```python
@app.get("/login/sso")
async def unified_login_sso(
    request: Request,
    redirect_to: Optional[str] = None,
):
    """
    Initiate OIDC SSO flow from unified login page.

    Preserves redirect_to parameter through OIDC flow by storing
    it in the OIDC state parameter.

    Args:
        request: FastAPI Request object
        redirect_to: Optional URL to redirect after SSO completes
    """
    from code_indexer.server.auth.oidc import routes as oidc_routes

    # Check if OIDC is enabled
    if not oidc_routes.oidc_manager or not oidc_routes.oidc_manager.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSO is not enabled on this server",
        )

    # Generate state token for OIDC flow
    state_token = secrets.token_urlsafe(32)

    # Store redirect_to in state if provided
    state_data = {"token": state_token}
    if redirect_to:
        # Validate redirect_to (prevent open redirect)
        if redirect_to.startswith("/") and not redirect_to.startswith("//"):
            state_data["redirect_to"] = redirect_to

    # Build OIDC authorization URL
    oidc_auth_url = oidc_routes.oidc_manager.build_authorization_url(
        state=json.dumps(state_data),
        redirect_uri=str(request.base_url) + "auth/sso/callback",
    )

    return RedirectResponse(url=oidc_auth_url)
```

### Phase 4: Update OIDC Callback Handler

**File:** `src/code_indexer/server/auth/oidc/routes.py`

**Update `/auth/sso/callback` route:**

```python
@router.get("/callback")
async def oidc_callback(
    request: Request,
    code: str,
    state: str,
):
    """
    Handle OIDC provider callback.

    Enhanced to support three contexts:
    1. OAuth authorization flow (redirect_to=/oauth/authorize?...)
    2. Admin login flow (no redirect_to, user is admin)
    3. Unified login flow (redirect_to from /login/sso)

    Args:
        request: FastAPI Request object
        code: OIDC authorization code
        state: OIDC state parameter
    """
    # ... existing OIDC token exchange logic ...

    # Parse state parameter
    try:
        state_data = json.loads(state)
        redirect_to = state_data.get("redirect_to")
    except (json.JSONDecodeError, AttributeError):
        redirect_to = None

    # ... existing user matching/creation logic ...
    # After successful OIDC authentication, user object is available

    # Determine redirect destination
    if redirect_to:
        # Explicit redirect_to from unified login or OAuth flow
        if redirect_to.startswith("/oauth/authorize"):
            # OAuth flow - issue authorization code
            # ... existing OAuth authorization code logic ...
            pass
        else:
            # Generic redirect (e.g., from unified login)
            redirect_url = redirect_to
    elif user.role.value == "admin":
        # Admin user, no explicit redirect - go to admin dashboard
        redirect_url = "/admin"
    else:
        # Non-admin user - go to user interface
        redirect_url = "/user/api-keys"

    # Create session
    session_manager = get_session_manager()
    redirect_response = RedirectResponse(
        url=redirect_url,
        status_code=status.HTTP_303_SEE_OTHER,
    )
    session_manager.create_session(
        redirect_response,
        username=user.username,
        role=user.role.value,
    )

    return redirect_response
```

### Phase 5: Refactor OAuth Authorization Endpoint

**File:** `src/code_indexer/server/auth/oauth/routes.py`

**Update `/oauth/authorize` GET endpoint:**

```python
@router.get("/authorize", response_class=HTMLResponse)
async def oauth_authorize(
    request: Request,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    response_type: str,
    state: str,
    manager: OAuthManager = Depends(get_oauth_manager),
):
    """
    OAuth authorization endpoint (POST-authentication).

    NEW FLOW (OAuth 2.1 compliant):
    1. Check if user has valid session
    2. If not authenticated → Redirect to /login with redirect_to
    3. If authenticated → Show authorization consent screen

    Args:
        request: FastAPI Request object
        client_id: OAuth client ID
        redirect_uri: OAuth redirect URI
        code_challenge: PKCE code challenge
        response_type: OAuth response type (should be "code")
        state: OAuth state parameter
        manager: OAuth manager dependency
    """
    # Validate client_id exists (OAuth 2.1 requirement)
    client = manager.get_client(client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_client",
                "error_description": "Client ID not found",
            },
        )

    # NEW: Check if user has valid session
    from code_indexer.server.web import get_session_manager
    session_manager = get_session_manager()
    session = session_manager.get_session(request)

    if not session:
        # User not authenticated - redirect to unified login
        # Preserve all OAuth parameters in redirect_to
        auth_url = f"/oauth/authorize?{request.url.query}"
        login_url = f"/login?redirect_to={quote(auth_url)}"
        return RedirectResponse(url=login_url, status_code=status.HTTP_303_SEE_OTHER)

    # User is authenticated - show authorization consent screen
    # Check if OIDC is enabled (for SSO button on consent screen)
    from code_indexer.server.auth.oidc import routes as oidc_routes
    oidc_enabled = False
    if oidc_routes.oidc_manager and hasattr(oidc_routes.oidc_manager, "is_enabled"):
        oidc_enabled = oidc_routes.oidc_manager.is_enabled()

    return templates.TemplateResponse(
        "oauth_authorize_consent.html",
        {
            "request": request,
            "username": session.username,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "response_type": response_type,
            "state": state,
            "oidc_enabled": oidc_enabled,
        },
    )
```

**Update `/oauth/authorize` POST endpoint:**

```python
@router.post("/authorize")
async def oauth_authorize_consent(
    request: Request,
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    code_challenge: str = Form(...),
    response_type: str = Form(...),
    state: str = Form(...),
    manager: OAuthManager = Depends(get_oauth_manager),
):
    """
    Process authorization consent (NOT login).

    User is already authenticated via session.
    This endpoint just issues the authorization code.

    Args:
        request: FastAPI Request object
        client_id: OAuth client ID from form
        redirect_uri: OAuth redirect URI from form
        code_challenge: PKCE code challenge from form
        response_type: OAuth response type from form
        state: OAuth state parameter from form
        manager: OAuth manager dependency
    """
    # Verify user is authenticated
    from code_indexer.server.web import get_session_manager
    session_manager = get_session_manager()
    session = session_manager.get_session(request)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    # Validate client_id
    client = manager.get_client(client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_client",
                "error_description": "Client ID not found",
            },
        )

    # Issue authorization code
    auth_code = manager.create_authorization_code(
        client_id=client_id,
        username=session.username,
        code_challenge=code_challenge,
    )

    # Redirect back to OAuth client with authorization code
    redirect_url = f"{redirect_uri}?code={auth_code}&state={state}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
```

**Remove `/oauth/authorize/sso` route** (no longer needed - SSO now handled by unified login)

### Phase 6: Create OAuth Consent Template

**File:** `src/code_indexer/server/web/templates/oauth_authorize_consent.html`

```html
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CIDX Authorization</title>
    <style>
        /* Same styling as unified_login.html for consistency */
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            max-width: 400px;
            width: 100%;
        }
        h2 { margin: 0 0 10px 0; color: #333; }
        p { color: #666; margin: 0 0 20px 0; font-size: 14px; }
        .user-info {
            background: #f5f5f5;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .user-info strong { color: #333; }
        button {
            width: 100%;
            padding: 14px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            margin-top: 10px;
        }
        button:hover { background: #5568d3; }
        .cancel-btn {
            background: #999;
            margin-top: 10px;
        }
        .cancel-btn:hover { background: #888; }
    </style>
</head>
<body>
    <div class="container">
        <h2>CIDX Authorization</h2>
        <p>CIDX Server is requesting access to your account</p>

        <div class="user-info">
            <strong>Logged in as:</strong> {{ username }}
        </div>

        <p style="font-size: 13px; color: #888;">
            By authorizing access, you allow this application to access your CIDX account.
        </p>

        <form method="post" action="/oauth/authorize">
            <input type="hidden" name="client_id" value="{{ client_id }}">
            <input type="hidden" name="redirect_uri" value="{{ redirect_uri }}">
            <input type="hidden" name="code_challenge" value="{{ code_challenge }}">
            <input type="hidden" name="response_type" value="{{ response_type }}">
            <input type="hidden" name="state" value="{{ state }}">
            <button type="submit">Authorize Access</button>
        </form>

        <form method="get" action="/user/api-keys">
            <button type="submit" class="cancel-btn">Cancel</button>
        </form>
    </div>
</body>
</html>
```

### Phase 7: Update Protected Route Decorators

**File:** `src/code_indexer/server/web/auth.py`

**Update `require_admin_session`:**

```python
def require_admin_session(request: Request) -> SessionData:
    """
    Dependency to require valid admin session.

    Args:
        request: FastAPI Request object

    Returns:
        SessionData for authenticated admin

    Raises:
        HTTPException: If not authenticated or not admin
    """
    session_manager = get_session_manager()
    session = session_manager.get_session(request)

    if not session:
        # NEW: Redirect to unified /login with redirect_to
        current_path = str(request.url.path)
        if request.url.query:
            current_path += f"?{request.url.query}"
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": f"/login?redirect_to={quote(current_path)}"},
        )

    if session.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return session
```

**Add new `require_user_session`:**

```python
def require_user_session(request: Request) -> SessionData:
    """
    Dependency to require valid user session (any role).

    Use this for user interface routes that accept any authenticated user.

    Args:
        request: FastAPI Request object

    Returns:
        SessionData for authenticated user

    Raises:
        HTTPException: If not authenticated
    """
    session_manager = get_session_manager()
    session = session_manager.get_session(request)

    if not session:
        # Redirect to unified /login with redirect_to
        current_path = str(request.url.path)
        if request.url.query:
            current_path += f"?{request.url.query}"
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": f"/login?redirect_to={quote(current_path)}"},
        )

    return session
```

**Update user routes to use new decorator:**

```python
# In src/code_indexer/server/web/routes.py

@user_router.get("/api-keys", response_class=HTMLResponse)
async def user_api_keys_page(
    request: Request,
    session: SessionData = Depends(require_user_session),  # NEW
):
    """User API keys page (any authenticated user)."""
    # ... existing implementation ...

@user_router.get("/mcp-credentials", response_class=HTMLResponse)
async def user_mcp_credentials_page(
    request: Request,
    session: SessionData = Depends(require_user_session),  # NEW
):
    """User MCP credentials page (any authenticated user)."""
    # ... existing implementation ...
```

### Phase 8: Remove Old Login Routes

**Once unified login is tested and working:**

**In `src/code_indexer/server/web/routes.py`:**

1. **Remove admin login routes** (lines 148-273):
   ```python
   @admin_router.get("/login", response_class=HTMLResponse)
   async def admin_login_page(...):
       # DELETE THIS ENTIRE FUNCTION

   @admin_router.post("/login", response_class=HTMLResponse)
   async def admin_login_submit(...):
       # DELETE THIS ENTIRE FUNCTION
   ```

2. **Remove user login routes** (lines 3747-3846):
   ```python
   @user_router.get("/login", response_class=HTMLResponse)
   async def user_login_page(...):
       # DELETE THIS ENTIRE FUNCTION

   @user_router.post("/login", response_class=HTMLResponse)
   async def user_login_submit(...):
       # DELETE THIS ENTIRE FUNCTION
   ```

3. **Add backwards compatibility redirects:**
   ```python
   @admin_router.get("/login")
   async def admin_login_redirect():
       """Redirect old admin login URL to unified login."""
       return RedirectResponse(url="/login", status_code=301)

   @user_router.get("/login")
   async def user_login_redirect():
       """Redirect old user login URL to unified login."""
       return RedirectResponse(url="/login", status_code=301)
   ```

**Remove templates:**
- Delete `src/code_indexer/server/web/templates/login.html`
- Delete `src/code_indexer/server/web/templates/user_login.html`

**In `src/code_indexer/server/auth/oauth/routes.py`:**

Remove `/oauth/authorize/sso` route (lines 324-374):
```python
@router.get("/authorize/sso")
async def oauth_authorize_via_sso(...):
    # DELETE THIS ENTIRE FUNCTION
    # SSO now handled by unified /login/sso
```

### Phase 9: Update Tests

**Files to update:**
- `tests/unit/server/auth/oauth/test_oauth_sso_integration.py`
- `tests/unit/server/auth/oidc/test_oidc_provider.py`
- `tests/unit/server/test_branch_endpoints_unit.py`
- `tests/unit/server/test_branch_service.py`

**New test file:** `tests/unit/server/web/test_unified_login.py`

```python
import pytest
from fastapi.testclient import TestClient


class TestUnifiedLogin:
    """Tests for unified login page."""

    def test_login_page_renders(self, client: TestClient):
        """Test that unified login page renders successfully."""
        response = client.get("/login")
        assert response.status_code == 200
        assert "CIDX Login" in response.text
        assert "username" in response.text.lower()
        assert "password" in response.text.lower()

    def test_login_page_with_redirect_to(self, client: TestClient):
        """Test login page preserves redirect_to parameter."""
        response = client.get("/login?redirect_to=/admin/users")
        assert response.status_code == 200
        assert 'name="redirect_to"' in response.text
        assert '/admin/users' in response.text

    def test_login_with_valid_credentials_admin(self, client: TestClient, admin_user):
        """Test login with valid admin credentials redirects to admin dashboard."""
        response = client.post(
            "/login",
            data={
                "username": "admin",
                "password": "admin_password",
                "csrf_token": "valid_token",  # Mock CSRF validation
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin"

    def test_login_with_valid_credentials_user(self, client: TestClient, normal_user):
        """Test login with valid user credentials redirects to user interface."""
        response = client.post(
            "/login",
            data={
                "username": "user",
                "password": "user_password",
                "csrf_token": "valid_token",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/user/api-keys"

    def test_login_with_redirect_to_parameter(self, client: TestClient, admin_user):
        """Test login respects explicit redirect_to parameter."""
        response = client.post(
            "/login",
            data={
                "username": "admin",
                "password": "admin_password",
                "csrf_token": "valid_token",
                "redirect_to": "/admin/users",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/users"

    def test_login_prevents_open_redirect(self, client: TestClient, admin_user):
        """Test login prevents open redirect attacks."""
        response = client.post(
            "/login",
            data={
                "username": "admin",
                "password": "admin_password",
                "csrf_token": "valid_token",
                "redirect_to": "https://evil.com",
            },
            follow_redirects=False,
        )
        # Should ignore malicious redirect_to and use default logic
        assert response.status_code == 303
        assert response.headers["location"] == "/admin"

    def test_login_with_invalid_credentials(self, client: TestClient):
        """Test login with invalid credentials shows error."""
        response = client.post(
            "/login",
            data={
                "username": "admin",
                "password": "wrong_password",
                "csrf_token": "valid_token",
            },
        )
        assert response.status_code == 200
        assert "Invalid username or password" in response.text

    def test_login_csrf_protection(self, client: TestClient, admin_user):
        """Test login requires valid CSRF token."""
        response = client.post(
            "/login",
            data={
                "username": "admin",
                "password": "admin_password",
                # Missing csrf_token
            },
        )
        assert response.status_code == 403


class TestOAuthAuthorizationFlow:
    """Tests for updated OAuth authorization flow."""

    def test_oauth_authorize_redirects_to_login_when_not_authenticated(
        self, client: TestClient
    ):
        """Test OAuth authorize redirects to login for unauthenticated users."""
        response = client.get(
            "/oauth/authorize?client_id=test&redirect_uri=http://localhost&"
            "code_challenge=challenge&response_type=code&state=state",
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"].startswith("/login?redirect_to=")

    def test_oauth_authorize_shows_consent_when_authenticated(
        self, client: TestClient, authenticated_session
    ):
        """Test OAuth authorize shows consent screen for authenticated users."""
        response = client.get(
            "/oauth/authorize?client_id=test&redirect_uri=http://localhost&"
            "code_challenge=challenge&response_type=code&state=state",
            cookies=authenticated_session,
        )
        assert response.status_code == 200
        assert "CIDX Authorization" in response.text
        assert "Authorize Access" in response.text
        assert "Logged in as:" in response.text


class TestSSOIntegration:
    """Tests for SSO integration with unified login."""

    def test_sso_button_shown_when_oidc_enabled(
        self, client: TestClient, oidc_enabled
    ):
        """Test SSO button appears on login page when OIDC enabled."""
        response = client.get("/login")
        assert response.status_code == 200
        assert "Sign in with SSO" in response.text

    def test_sso_button_hidden_when_oidc_disabled(
        self, client: TestClient, oidc_disabled
    ):
        """Test SSO button hidden when OIDC disabled."""
        response = client.get("/login")
        assert response.status_code == 200
        assert "Sign in with SSO" not in response.text

    def test_sso_initiation_preserves_redirect_to(self, client: TestClient, oidc_enabled):
        """Test SSO initiation preserves redirect_to parameter."""
        response = client.get(
            "/login/sso?redirect_to=/admin/users",
            follow_redirects=False,
        )
        assert response.status_code == 303
        # Should redirect to OIDC provider with state containing redirect_to
        assert response.headers["location"].startswith("https://")
```

---

## Testing Strategy

### Unit Tests

**Test Coverage Areas:**

1. **Unified Login Page Rendering**
   - Page renders with all elements
   - CSRF token included
   - SSO button conditional rendering
   - Error/info message display
   - redirect_to parameter preservation

2. **Authentication Logic**
   - Valid credentials create session
   - Invalid credentials show error
   - CSRF validation
   - Session cookie set correctly

3. **Smart Redirect Logic**
   - Admin without redirect_to → /admin
   - User without redirect_to → /user/api-keys
   - Any user with redirect_to → specified URL
   - Open redirect prevention

4. **OAuth Authorization Flow**
   - Unauthenticated → redirect to login
   - Authenticated → show consent screen
   - Consent submission → issue auth code
   - redirect_to preserved through flow

5. **SSO Integration**
   - SSO initiation with redirect_to
   - OIDC callback handling
   - State parameter preservation
   - User session creation

### Integration Tests

**Test Scenarios:**

1. **Admin Login Flow**
   ```
   GET /admin/users (protected)
     → 303 redirect to /login?redirect_to=/admin/users
   POST /login (valid admin credentials)
     → 303 redirect to /admin/users
   GET /admin/users
     → 200 OK (authenticated)
   ```

2. **User Login Flow**
   ```
   GET /user/api-keys (protected)
     → 303 redirect to /login?redirect_to=/user/api-keys
   POST /login (valid user credentials)
     → 303 redirect to /user/api-keys
   GET /user/api-keys
     → 200 OK (authenticated)
   ```

3. **OAuth Flow (New User)**
   ```
   GET /oauth/authorize?client_id=...
     → 303 redirect to /login?redirect_to=/oauth/authorize?...
   POST /login (valid credentials)
     → 303 redirect to /oauth/authorize?...
   GET /oauth/authorize?...
     → 200 OK (shows consent screen)
   POST /oauth/authorize (consent)
     → 303 redirect to client with auth code
   ```

4. **OAuth Flow (Existing Session)**
   ```
   POST /login (create session)
     → 303 redirect to /admin
   GET /oauth/authorize?client_id=...
     → 200 OK (shows consent screen immediately, no login required)
   POST /oauth/authorize (consent)
     → 303 redirect to client with auth code
   ```

5. **SSO Flow**
   ```
   GET /login
     → 200 OK (shows SSO button)
   Click "Sign in with SSO"
     → GET /login/sso
     → 303 redirect to OIDC provider
   User authenticates at OIDC provider
     → 303 redirect to /auth/sso/callback?code=...
   GET /auth/sso/callback
     → Create session
     → 303 redirect to /admin or /user/api-keys
   ```

### Manual Testing Checklist

**Browser Testing:**

- [ ] Admin login via username/password
- [ ] User login via username/password
- [ ] Power user login via username/password
- [ ] Admin login via SSO
- [ ] User login via SSO
- [ ] Claude Code OAuth flow (new session)
- [ ] Claude Code OAuth flow (existing session)
- [ ] Session timeout redirects to login with redirect_to
- [ ] Logout clears session properly
- [ ] Back button after logout requires re-authentication
- [ ] CSRF protection blocks replay attacks
- [ ] Open redirect protection works
- [ ] Old login URLs redirect correctly (`/admin/login`, `/user/login`)

**Security Testing:**

- [ ] CSRF tokens validated
- [ ] Session cookies httpOnly
- [ ] Session cookies secure (non-localhost)
- [ ] Session timeout enforced
- [ ] Password not logged or exposed
- [ ] XSS protection (input sanitization)
- [ ] SQL injection protection
- [ ] Open redirect prevented
- [ ] Session fixation prevented

**Cross-Browser Testing:**

- [ ] Chrome (desktop)
- [ ] Firefox (desktop)
- [ ] Safari (desktop)
- [ ] Edge (desktop)
- [ ] Chrome (mobile)
- [ ] Safari (mobile)

### Performance Testing

**Metrics to Track:**

- Login page load time: < 500ms
- Login form submission: < 1000ms
- OAuth authorization flow: < 2000ms
- SSO redirect chain: < 3000ms

---

## Migration Considerations

### Database Changes

**None required!**

Session management already unified - all three login pages use same SessionManager with same cookie format. No database migration needed.

### Configuration Changes

**None required!**

OIDC configuration already supports all contexts. No new environment variables or config needed.

### Deployment Strategy

**Phased Rollout:**

1. **Phase 1: Deploy with both old and new routes active**
   - Deploy unified login as `/login`
   - Keep old routes (`/admin/login`, `/user/login`) active
   - Add redirects from old routes to new route (301 Moved Permanently)
   - Test new unified login thoroughly
   - Monitor error logs for issues

2. **Phase 2: Verify all flows work**
   - Test admin login
   - Test user login
   - Test OAuth flow
   - Test SSO for all contexts
   - Verify session management
   - Check analytics/logs for errors

3. **Phase 3: Remove old routes (1 week later)**
   - Remove old login route handlers
   - Remove old templates
   - Keep redirects in place (permanent)
   - Monitor for any issues

### Rollback Plan

**If issues discovered:**

1. **Immediate rollback** (if critical bug found):
   - Revert to previous commit
   - Old login routes still work (never deleted in Phase 1)
   - No data loss (sessions compatible)

2. **Partial rollback** (if minor issues):
   - Keep unified login for new users
   - Re-enable old login routes for specific contexts
   - Fix issues in unified login
   - Re-deploy when ready

### Breaking Changes

**None!**

- Old login URLs redirect to new unified login (301 permanent)
- Session format unchanged (same cookie, same data)
- API endpoints unchanged
- OAuth flow enhanced but backwards compatible

### Backwards Compatibility

**Redirects ensure compatibility:**

```python
# Old admin login URL
GET /admin/login → 301 redirect → GET /login

# Old user login URL
GET /user/login → 301 redirect → GET /login

# OAuth authorize still works (enhanced)
GET /oauth/authorize → Check session → Redirect to /login if needed
```

**Session cookies compatible:**
- Same cookie name: "session"
- Same data format
- Sessions created by old login pages work with new code
- Sessions created by new login page work with existing protected routes

---

## Open Questions

### 1. Landing Page for Admin Users

**Question:** When an admin user logs in via the user login URL (`/user/login`), where should they be redirected?

**Options:**
- **A)** Redirect to admin dashboard (`/admin`) - Leverages their full capabilities
- **B)** Redirect to user interface (`/user/api-keys`) - Respects the URL they visited
- **C)** Show choice screen - Let user choose admin or user interface

**Current Proposal:** Option A - Redirect to admin dashboard
- **Rationale:** Admins have more capabilities, should see full interface by default
- **User can navigate to user interface** if needed via `/user/api-keys` link
- **Consistent with smart redirect logic** (role-based routing)

**Decision:** _______________

### 2. OAuth Consent Screen

**Question:** Should we show an explicit consent screen ("CIDX is requesting access") or auto-issue authorization code for authenticated users?

**Options:**
- **A)** Show consent screen - OAuth 2.1 best practice, explicit user consent
- **B)** Auto-issue code - Faster flow, less user friction
- **C)** Configurable - Let server operator choose via config

**Current Proposal:** Option A - Show consent screen
- **Rationale:**
  - OAuth 2.1 spec recommends explicit consent
  - User sees what application is requesting access
  - Better security (prevents silent authorization)
  - Follows industry best practices (Google, GitHub, etc.)
- **UX Impact:** One extra click ("Authorize Access" button)
- **Implementation:** Simple template (already designed in Phase 6)

**Decision:** _______________

### 3. Session Scope Separation

**Question:** Should admin and user sessions be completely separate (different cookies) or unified (same cookie works for both)?

**Current State:** Unified session (same cookie works for both interfaces)

**Options:**
- **A)** Keep unified - Simpler, admin can access both interfaces seamlessly
- **B)** Separate sessions - More security isolation, explicit context switching
- **C)** Hybrid - Same session data, but separate cookies with path restrictions

**Current Proposal:** Option A - Keep unified
- **Rationale:**
  - Admin needs access to both interfaces (manage users, also use user API keys)
  - No security benefit to separation (same user, same privileges)
  - Simpler implementation and maintenance
  - Consistent with current implementation
- **Path Restriction Note:** User CSRF cookies use `path="/user"` but not necessary for session cookie

**Decision:** _______________

### 4. SSO Provider Display Name

**Question:** Should SSO button text be configurable (e.g., "Sign in with Okta" vs "Sign in with SSO")?

**Current Implementation:** Hardcoded "Sign in with SSO"

**Options:**
- **A)** Keep hardcoded "SSO" - Simple, generic
- **B)** Add config for display name - More professional, branded
- **C)** Auto-detect from OIDC metadata - Use provider's name from discovery

**Current Proposal:** Option B - Add config field
- **Add to OIDC config:** `display_name` (optional, defaults to "SSO")
- **Example:** `OIDC_DISPLAY_NAME="Okta"` → "Sign in with Okta"
- **Implementation:** Pass to templates, use in button text
- **Minimal effort:** Single config field, template variable

**Decision:** _______________

### 5. Logout Behavior

**Question:** Should logout redirect to unified login page or a separate logout success page?

**Current Implementation:**
- `/admin/logout` redirects to `/admin/login`
- `/user/logout` redirects to `/user/login`

**Options:**
- **A)** Redirect to unified login with info message ("Logged out successfully")
- **B)** Show dedicated logout success page with "Login Again" button
- **C)** Redirect to public landing page (if one exists)

**Current Proposal:** Option A - Redirect to unified login
- **URL:** `/login?info=Logged out successfully`
- **Rationale:** User likely wants to log in again (common pattern)
- **No extra page needed:** Reuse login page with info message
- **Consistent UX:** All authentication flows use same page

**Decision:** _______________

### 6. Remember Me / Stay Logged In

**Question:** Should we add "Remember Me" checkbox to extend session timeout?

**Current Implementation:** Fixed 8-hour session timeout for all sessions

**Options:**
- **A)** No remember me - Keep fixed 8-hour timeout (current behavior)
- **B)** Add remember me - Extend to 30 days if checked
- **C)** Add remember me - Issue long-lived refresh token

**Current Proposal:** Option A - No remember me (out of scope)
- **Rationale:**
  - Not requested in original requirements
  - Adds complexity (different session timeouts)
  - Security consideration (longer-lived sessions = more risk)
  - Can add later if needed (doesn't block consolidation)

**Decision:** _______________

### 7. Testing Approach

**Question:** Should we write tests before or during implementation?

**Options:**
- **A)** TDD - Write tests first, then implement
- **B)** Concurrent - Write tests alongside implementation
- **C)** Post-implementation - Implement first, then add comprehensive tests

**Current Proposal:** Option B - Concurrent
- **Rationale:**
  - Write basic tests to validate approach
  - Implement features incrementally
  - Add comprehensive tests as features complete
  - Ensures nothing breaks existing functionality
  - Fast feedback loop

**Decision:** _______________

---

## Success Criteria

### Must Have (P0)

- [ ] Single unified login page (`/login`) works for all contexts
- [ ] Admin users redirect to admin dashboard after login
- [ ] Non-admin users redirect to user interface after login
- [ ] OAuth flow separates authentication and authorization
- [ ] SSO works for all contexts (admin, user, OAuth)
- [ ] Session management unchanged (backwards compatible)
- [ ] All existing tests pass
- [ ] Old login URLs redirect to new unified login
- [ ] CSRF protection works
- [ ] Session timeout redirects correctly

### Should Have (P1)

- [ ] OAuth consent screen shows before issuing authorization code
- [ ] Comprehensive test coverage (>90% for new code)
- [ ] Open redirect protection
- [ ] Security audit passed (XSS, CSRF, injection)
- [ ] Documentation updated (API docs, user docs)
- [ ] Performance metrics met (login < 1s)

### Nice to Have (P2)

- [ ] SSO provider display name configurable
- [ ] Logout success message on login page
- [ ] UI polish (animations, loading states)
- [ ] Accessibility audit (WCAG 2.1 AA)
- [ ] Browser compatibility tested (6+ browsers)
- [ ] Mobile responsive design verified

---

## Timeline Estimate

**Total Effort:** 3-5 days (single developer)

**Breakdown:**

- **Phase 1-2:** Unified login template + routes - 1 day
- **Phase 3-4:** SSO integration + OIDC callback update - 0.5 days
- **Phase 5-6:** OAuth refactor + consent template - 1 day
- **Phase 7:** Protected route updates - 0.5 days
- **Phase 8:** Remove old routes + cleanup - 0.5 days
- **Phase 9:** Testing + bug fixes - 1-2 days

**Note:** Timeline assumes familiarity with codebase and no major blockers.

---

## References

### Related Files

**Templates:**
- `src/code_indexer/server/web/templates/login.html` (admin, to be removed)
- `src/code_indexer/server/web/templates/user_login.html` (user, to be removed)
- `src/code_indexer/server/web/templates/base.html` (admin base)
- `src/code_indexer/server/web/templates/user_base.html` (user base)

**Routes:**
- `src/code_indexer/server/web/routes.py` (admin and user login routes)
- `src/code_indexer/server/auth/oauth/routes.py` (OAuth authorization)
- `src/code_indexer/server/auth/oidc/routes.py` (OIDC SSO callback)

**Session Management:**
- `src/code_indexer/server/web/auth.py` (SessionManager)
- `src/code_indexer/server/auth/user_manager.py` (User authentication)
- `src/code_indexer/server/auth/oauth/oauth_manager.py` (OAuth client management)
- `src/code_indexer/server/auth/oidc/oidc_manager.py` (OIDC provider integration)

**Tests:**
- `tests/unit/server/auth/oauth/test_oauth_sso_integration.py`
- `tests/unit/server/auth/oidc/test_oidc_provider.py`
- `tests/unit/server/test_branch_endpoints_unit.py`
- `tests/unit/server/test_branch_service.py`

### OAuth 2.1 Specification

- RFC 6749: The OAuth 2.0 Authorization Framework
- RFC 7636: Proof Key for Code Exchange (PKCE)
- OAuth 2.1 Draft: https://datatracker.ietf.org/doc/html/draft-ietf-oauth-v2-1-07

### Security Best Practices

- OWASP Session Management Cheat Sheet
- OWASP CSRF Prevention Cheat Sheet
- OWASP Authentication Cheat Sheet

---

## Appendix A: Visual Mockup

### Unified Login Page

```
┌─────────────────────────────────────────────────┐
│                                                 │
│         [Gradient Purple Background]           │
│                                                 │
│     ┌───────────────────────────────────┐     │
│     │                                   │     │
│     │        CIDX Login                 │     │
│     │   Sign in to access your account  │     │
│     │                                   │     │
│     │   ┌───────────────────────────┐   │     │
│     │   │  Sign in with SSO         │   │     │
│     │   └───────────────────────────┘   │     │
│     │                                   │     │
│     │          ───── or ─────           │     │
│     │                                   │     │
│     │   Username: [________________]    │     │
│     │                                   │     │
│     │   Password: [________________]    │     │
│     │                                   │     │
│     │   ┌───────────────────────────┐   │     │
│     │   │       Sign In             │   │     │
│     │   └───────────────────────────┘   │     │
│     │                                   │     │
│     └───────────────────────────────────┘     │
│                                                 │
└─────────────────────────────────────────────────┘
```

### OAuth Consent Screen

```
┌─────────────────────────────────────────────────┐
│                                                 │
│         [Gradient Purple Background]           │
│                                                 │
│     ┌───────────────────────────────────┐     │
│     │                                   │     │
│     │      CIDX Authorization           │     │
│     │  CIDX Server is requesting access │     │
│     │       to your account             │     │
│     │                                   │     │
│     │  ┌─────────────────────────────┐  │     │
│     │  │ Logged in as: admin         │  │     │
│     │  └─────────────────────────────┘  │     │
│     │                                   │     │
│     │  By authorizing access, you allow │     │
│     │  this application to access your  │     │
│     │  CIDX account.                    │     │
│     │                                   │     │
│     │   ┌───────────────────────────┐   │     │
│     │   │   Authorize Access        │   │     │
│     │   └───────────────────────────┘   │     │
│     │                                   │     │
│     │   ┌───────────────────────────┐   │     │
│     │   │       Cancel              │   │     │
│     │   └───────────────────────────┘   │     │
│     │                                   │     │
│     └───────────────────────────────────┘     │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## Appendix B: Flow Diagrams

### Admin Login Flow

```
User visits /admin/users (protected)
  |
  v
No session? → Redirect: /login?redirect_to=/admin/users
  |
  v
Unified login page shown
  |
  +---[Username/Password]------+-------[SSO]----------+
  |                            |                      |
  v                            v                      v
POST /login              GET /login/sso      OIDC Provider Auth
  |                            |                      |
  v                            v                      v
Authenticate              OIDC Flow            Exchange tokens
  |                            |                      |
  v                            v                      v
Create session            Create session       Create session
  |                            |                      |
  +----------------------------+----------------------+
                               |
                               v
              Redirect to /admin/users (from redirect_to)
                               |
                               v
                    Admin dashboard loaded
```

### OAuth Authorization Flow

```
Claude Code initiates OAuth
  |
  v
GET /oauth/authorize?client_id=...&redirect_uri=...&code_challenge=...
  |
  v
Check session
  |
  +---[No Session]-------------+-------[Has Session]-----+
  |                            |                         |
  v                            |                         |
Redirect to /login            |                         |
?redirect_to=/oauth/authorize |                         |
  |                            |                         |
  v                            |                         |
User logs in                  |                         |
(unified login flow)          |                         |
  |                            |                         |
  v                            |                         |
Create session                |                         |
  |                            |                         |
  +----------------------------+-------------------------+
                               |
                               v
                  Show consent screen
                  "Authorize Access" button
                               |
                               v
                  User clicks Authorize
                               |
                               v
                  POST /oauth/authorize
                               |
                               v
              Generate authorization code (PKCE)
                               |
                               v
      Redirect to client: {redirect_uri}?code=...&state=...
                               |
                               v
                  Claude Code receives code
```

### SSO Flow (All Contexts)

```
User clicks "Sign in with SSO"
  |
  v
GET /login/sso?redirect_to={optional}
  |
  v
Store redirect_to in OIDC state
  |
  v
Redirect to OIDC provider
  |
  v
User authenticates at provider (Okta, Google, etc.)
  |
  v
OIDC provider redirects to /auth/sso/callback?code=...&state=...
  |
  v
Exchange OIDC code for tokens
  |
  v
Extract user info from OIDC claims (email, name, etc.)
  |
  v
Match or create user in local database (JIT provisioning)
  |
  v
Create session (SessionManager)
  |
  v
Parse state to get redirect_to
  |
  +---[redirect_to exists]----+-------[No redirect_to]----+
  |                           |                           |
  v                           v                           v
Redirect to redirect_to   Admin user?            Non-admin user?
                           |                            |
                           v                            v
                      Redirect to /admin        Redirect to /user/api-keys
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-31 | Architecture Planning | Initial comprehensive plan |

---

## Approval Sign-off

**Technical Lead:** _________________ Date: _______

**Product Owner:** _________________ Date: _______

**Security Review:** _________________ Date: _______

---

**End of Document**

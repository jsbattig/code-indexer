# CIDX Administrative Web UI - Architectural Analysis

## Executive Summary

This document provides a comprehensive architectural analysis for adding an administrative Web UI to the CIDX server. The analysis covers integration points, file structure, technical patterns, security considerations, and implementation sequencing.

---

## 1. Codebase Integration Analysis

### 1.1 Current FastAPI App Structure

**Entry Point**: `/home/jsbattig/Dev/code-indexer/src/code_indexer/server/main.py`
- Simple uvicorn runner that loads `code_indexer.server.app:app`
- Handles CLI arguments for host, port, and reload mode

**Main Application**: `/home/jsbattig/Dev/code-indexer/src/code_indexer/server/app.py`
- Large monolithic file (~5800 lines) with `create_app()` factory pattern
- Contains all Pydantic models, endpoint definitions, and business logic inline
- Uses `@asynccontextmanager` for lifespan management (startup/shutdown)
- Creates app instance at module level: `app = create_app()`

**Router Pattern**: The codebase uses APIRouter for modular routing:
- `oauth_router` - OAuth 2.1 endpoints at `/oauth/*`
- `mcp_router` - MCP protocol endpoints at `/mcp/*`
- `global_routes_router` - Global repository operations at `/global/*`

### 1.2 Integration Points for Web UI

**Recommendation**: Create a dedicated `web` subpackage with its own router.

#### Static Files Mount Point

Add in `create_app()` after CORS middleware setup (around line 1614):

```python
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# Mount static files for admin UI
static_dir = Path(__file__).parent / "web" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
```

#### Jinja2 Templates Setup

Add in `create_app()`:

```python
from fastapi.templating import Jinja2Templates

# Initialize Jinja2 templates for admin UI
templates_dir = Path(__file__).parent / "web" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Store in app.state for access by web routes
app.state.templates = templates
```

#### Web Router Inclusion

Add with other routers (around line 5773):

```python
from .web.routes import router as web_router
app.include_router(web_router)
```

### 1.3 Authentication Analysis

**Current Auth Flow**:
1. JWT-based authentication via `HTTPBearer` security scheme
2. OAuth 2.1 support for MCP clients (Claude.ai integration)
3. 3-tier RBAC: `admin`, `power_user`, `normal_user`
4. Token blacklist for logout functionality
5. Refresh token rotation with token families

**Web UI Authentication Requirements**:

For browser-based admin UI, we need cookie-based session management because:
- localStorage JWT is vulnerable to XSS attacks
- httpOnly cookies are more secure for admin interfaces
- Same-origin requests can use cookies transparently

**Recommended Approach**: Hybrid authentication

```python
# In auth/dependencies.py - add cookie-based auth support

def get_current_user_from_cookie_or_bearer(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """
    Get current user from either:
    1. JWT in httpOnly cookie (for web UI)
    2. Bearer token (for API clients)
    """
    # Try cookie first (web UI)
    session_token = request.cookies.get("cidx_session")
    if session_token:
        return validate_session_token(session_token)

    # Fall back to bearer token (API)
    if credentials:
        return validate_bearer_token(credentials.credentials)

    raise HTTPException(status_code=401, detail="Not authenticated")
```

### 1.4 CORS Configuration

**Current CORS** (lines 1598-1609):
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://claude.ai",
        "https://claude.com",
        "https://www.anthropic.com",
        "https://api.anthropic.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
```

**Impact on Web UI**: No changes needed. The Web UI is served from the same origin, so CORS doesn't apply. The existing CORS configuration supports external MCP clients.

---

## 2. File/Directory Structure Recommendation

### 2.1 Proposed Structure

```
src/code_indexer/server/
├── web/                          # New web UI package
│   ├── __init__.py
│   ├── routes.py                 # FastAPI router for web pages
│   ├── auth.py                   # Web-specific auth (cookies, sessions)
│   ├── dependencies.py           # Web route dependencies
│   ├── context.py                # Template context builders
│   │
│   ├── static/                   # Static assets
│   │   ├── css/
│   │   │   ├── pico.min.css      # Pico CSS framework
│   │   │   └── custom.css        # Custom overrides
│   │   ├── js/
│   │   │   ├── htmx.min.js       # htmx library
│   │   │   └── app.js            # Custom JS (minimal)
│   │   └── img/
│   │       └── logo.svg          # CIDX logo
│   │
│   └── templates/                # Jinja2 templates
│       ├── base.html             # Base layout with navigation
│       ├── components/           # Reusable template components
│       │   ├── nav.html          # Navigation bar
│       │   ├── flash.html        # Flash messages
│       │   ├── pagination.html   # Pagination controls
│       │   ├── modal.html        # Modal dialog
│       │   └── loading.html      # Loading indicator
│       │
│       ├── partials/             # htmx partial templates
│       │   ├── users/
│       │   │   ├── table.html    # User table rows
│       │   │   └── form.html     # User edit form
│       │   ├── repos/
│       │   │   ├── golden_table.html
│       │   │   ├── activated_table.html
│       │   │   └── form.html
│       │   ├── jobs/
│       │   │   ├── table.html
│       │   │   └── progress.html
│       │   └── dashboard/
│       │       ├── health.html
│       │       └── stats.html
│       │
│       └── pages/                # Full page templates
│           ├── login.html
│           ├── dashboard.html
│           ├── users/
│           │   ├── list.html
│           │   └── edit.html
│           ├── repos/
│           │   ├── golden.html
│           │   ├── activated.html
│           │   └── detail.html
│           ├── jobs/
│           │   └── list.html
│           ├── query/
│           │   └── test.html
│           └── config/
│               └── settings.html
```

### 2.2 Rationale

1. **Separate `web/` Package**: Isolates web UI concerns from REST API, making it easy to disable or remove if needed.

2. **`static/` vs `templates/`**: Clear separation between served files and server-side templates.

3. **`components/` Directory**: Reusable Jinja2 includes (navbar, flash messages) that are included in base template.

4. **`partials/` Directory**: htmx-specific fragments returned by AJAX calls for dynamic updates.

5. **`pages/` Directory**: Full page templates that extend base.html.

---

## 3. Technical Implementation Patterns

### 3.1 Jinja2 + htmx Integration Pattern

**Base Template** (`templates/base.html`):

```html
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}CIDX Admin{% endblock %}</title>
    <link rel="stylesheet" href="/static/css/pico.min.css">
    <link rel="stylesheet" href="/static/css/custom.css">
    <script src="/static/js/htmx.min.js"></script>
</head>
<body hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'>
    {% include "components/nav.html" %}

    <main class="container">
        {% include "components/flash.html" %}
        {% block content %}{% endblock %}
    </main>

    {% block scripts %}{% endblock %}
</body>
</html>
```

**htmx Partial Pattern** (`partials/users/table.html`):

```html
<table id="users-table" hx-swap-oob="true">
    <thead>
        <tr>
            <th>Username</th>
            <th>Role</th>
            <th>Created</th>
            <th>Actions</th>
        </tr>
    </thead>
    <tbody>
        {% for user in users %}
        <tr id="user-{{ user.username }}">
            <td>{{ user.username }}</td>
            <td>{{ user.role }}</td>
            <td>{{ user.created_at | format_datetime }}</td>
            <td>
                <button hx-get="/admin/users/{{ user.username }}/edit"
                        hx-target="#modal-container"
                        hx-swap="innerHTML">
                    Edit
                </button>
                <button hx-delete="/admin/users/{{ user.username }}"
                        hx-confirm="Delete user {{ user.username }}?"
                        hx-target="#user-{{ user.username }}"
                        hx-swap="outerHTML swap:1s">
                    Delete
                </button>
            </td>
        </tr>
        {% endfor %}
    </tbody>
</table>
```

### 3.2 Web Authentication Pattern

**Session Cookie Management** (`web/auth.py`):

```python
from datetime import datetime, timedelta
from fastapi import Response, Request, HTTPException
from itsdangerous import URLSafeTimedSerializer

SESSION_COOKIE_NAME = "cidx_session"
SESSION_MAX_AGE = 3600 * 8  # 8 hours

class WebSessionManager:
    def __init__(self, secret_key: str):
        self.serializer = URLSafeTimedSerializer(secret_key)

    def create_session(self, response: Response, username: str, role: str):
        """Create session cookie after successful login."""
        session_data = {
            "username": username,
            "role": role,
            "created_at": datetime.utcnow().isoformat()
        }
        token = self.serializer.dumps(session_data)

        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            secure=True,  # Require HTTPS
            samesite="lax"
        )

    def validate_session(self, request: Request) -> dict:
        """Validate session cookie, return session data or raise 401."""
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")

        try:
            session_data = self.serializer.loads(token, max_age=SESSION_MAX_AGE)
            return session_data
        except Exception:
            raise HTTPException(status_code=401, detail="Session expired")

    def destroy_session(self, response: Response):
        """Clear session cookie on logout."""
        response.delete_cookie(SESSION_COOKIE_NAME)
```

**Web Route Dependency** (`web/dependencies.py`):

```python
from fastapi import Depends, Request
from .auth import WebSessionManager, web_session_manager

def get_web_user(request: Request) -> dict:
    """
    Dependency for web routes requiring authentication.
    Returns session data with username and role.
    """
    return web_session_manager.validate_session(request)

def require_admin(session: dict = Depends(get_web_user)) -> dict:
    """Require admin role for web routes."""
    if session.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return session
```

### 3.3 API Consumption Pattern

**Internal API Client** (`web/api_client.py`):

```python
import httpx
from fastapi import Request

class InternalAPIClient:
    """
    Client for calling existing REST API endpoints from web routes.
    Uses the same authentication context as the web session.
    """

    def __init__(self, request: Request, session: dict):
        self.base_url = str(request.base_url).rstrip("/")
        self.session = session
        # Get the JWT for internal API calls
        self._token = self._get_internal_token()

    async def get_health(self) -> dict:
        """Call /health endpoint."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/health",
                headers={"Authorization": f"Bearer {self._token}"}
            )
            return response.json()

    async def list_users(self) -> list:
        """Call /api/admin/users endpoint."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/admin/users",
                headers={"Authorization": f"Bearer {self._token}"}
            )
            return response.json()

    # ... similar methods for other API endpoints
```

**Alternative: Direct Manager Access** (Recommended for performance):

```python
# Instead of HTTP calls, directly use the initialized managers
from code_indexer.server.app import (
    user_manager,
    golden_repo_manager,
    background_job_manager,
    activated_repo_manager,
)

async def get_dashboard_data():
    """Get dashboard data directly from managers."""
    return {
        "users": user_manager.get_all_users(),
        "golden_repos": golden_repo_manager.list_golden_repos(),
        "active_jobs": background_job_manager.get_active_job_count(),
        "pending_jobs": background_job_manager.get_pending_job_count(),
    }
```

### 3.4 Error Handling Pattern

**Flash Messages** (`web/flash.py`):

```python
from fastapi import Request, Response
from typing import List, Tuple
import json

def add_flash(response: Response, message: str, category: str = "info"):
    """Add flash message to response cookie."""
    existing = response.headers.get("Set-Cookie", "")
    # Use secure cookie for flash messages
    response.set_cookie(
        key="cidx_flash",
        value=json.dumps({"message": message, "category": category}),
        max_age=60,  # Short-lived
        httponly=True,
        samesite="lax"
    )

def get_flashes(request: Request) -> List[Tuple[str, str]]:
    """Get and clear flash messages from request cookie."""
    flashes = []
    flash_cookie = request.cookies.get("cidx_flash")
    if flash_cookie:
        try:
            data = json.loads(flash_cookie)
            flashes.append((data["category"], data["message"]))
        except Exception:
            pass
    return flashes
```

**Error Page Template** (`templates/pages/error.html`):

```html
{% extends "base.html" %}
{% block title %}Error - CIDX Admin{% endblock %}

{% block content %}
<article>
    <header>
        <h1>{{ error_code }}</h1>
        <p>{{ error_message }}</p>
    </header>
    <footer>
        <a href="/admin/dashboard" role="button">Return to Dashboard</a>
    </footer>
</article>
{% endblock %}
```

---

## 4. Risks and Considerations

### 4.1 Potential Route Conflicts

**Risk**: Web UI routes might conflict with existing API routes.

**Mitigation**: Use `/admin/*` prefix for all web UI routes:
- `/admin/` - Dashboard (redirect to `/admin/dashboard`)
- `/admin/dashboard` - Main dashboard
- `/admin/users` - User management
- `/admin/golden-repos` - Golden repository management
- `/admin/activated-repos` - Activated repository management
- `/admin/jobs` - Job monitoring
- `/admin/query` - Query testing
- `/admin/config` - Configuration

**Existing Routes to Avoid**:
- `/api/*` - All REST API endpoints
- `/oauth/*` - OAuth 2.1 endpoints
- `/mcp/*` - MCP protocol endpoints
- `/global/*` - Global repository operations
- `/health` - Health check
- `/docs`, `/redoc`, `/openapi.json` - API documentation
- `/.well-known/*` - OAuth discovery

### 4.2 Security Considerations

1. **CSRF Protection** (Required):
   ```python
   # Generate CSRF token per session
   csrf_token = secrets.token_urlsafe(32)
   # Validate on all state-changing requests
   ```

2. **Session Security**:
   - Use `httponly=True` for session cookies
   - Use `secure=True` in production (HTTPS only)
   - Use `samesite="lax"` to prevent CSRF from external sites
   - Implement session timeout (8 hours recommended)
   - Regenerate session ID after login

3. **Input Validation**:
   - All form inputs validated server-side
   - Use Pydantic models for request validation
   - Sanitize output in templates (Jinja2 auto-escapes by default)

4. **Rate Limiting**:
   - Apply existing rate limiters to web login endpoint
   - Consider additional rate limiting for admin operations

5. **Access Control**:
   - Enforce admin-only access for user management
   - Enforce power_user+ access for repository operations
   - Log all admin actions for audit trail

### 4.3 Session Management Approach

**Recommended**: Use `itsdangerous` for signed session cookies (same as Flask/Starlette):

```python
# pip install itsdangerous
from itsdangerous import URLSafeTimedSerializer

# Reuse the existing JWT secret for signing sessions
serializer = URLSafeTimedSerializer(jwt_secret_manager.get_or_create_secret())
```

**Alternative**: Use existing JWT infrastructure with cookie transport:
- Store JWT in httpOnly cookie instead of localStorage
- Reuse existing token validation logic
- Benefit: Single auth implementation for API and web

### 4.4 CSRF Protection Implementation

```python
from fastapi import Request, HTTPException
import secrets

CSRF_TOKEN_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"

def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)

def validate_csrf_token(request: Request, session: dict):
    """Validate CSRF token for state-changing requests."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return  # No CSRF check for safe methods

    # Get token from header (htmx sends it)
    header_token = request.headers.get(CSRF_HEADER_NAME)
    # Get token from session
    session_token = session.get(CSRF_TOKEN_NAME)

    if not header_token or not session_token:
        raise HTTPException(status_code=403, detail="CSRF token missing")

    if not secrets.compare_digest(header_token, session_token):
        raise HTTPException(status_code=403, detail="CSRF token invalid")
```

---

## 5. Implementation Sequence Recommendation

### Phase 1: Foundation (Story 1)
**Duration**: 2-3 days

1. Create `web/` package structure
2. Set up static files mount (`StaticFiles`)
3. Configure Jinja2 templates
4. Implement session-based authentication
   - Login page
   - Logout functionality
   - Session cookie management
5. Create base template with navigation
6. Add CSRF protection middleware
7. Create web router and register with app

**Deliverables**:
- Working login/logout flow
- Base template with navigation shell
- Static assets (Pico CSS, htmx) served

### Phase 2: Dashboard (Story 2)
**Duration**: 1-2 days

1. Implement dashboard page
2. Create health status partial (htmx polling)
3. Create job counts partial
4. Create repository stats partial
5. Add auto-refresh with htmx (every 30s)

**Deliverables**:
- Dashboard showing real-time server status
- Live-updating health indicators
- Job queue summary

### Phase 3: User Management (Story 3)
**Duration**: 2-3 days

1. User list page with table
2. Create user modal/form
3. Edit user role functionality
4. Delete user with confirmation
5. Password reset capability
6. Proper role-based access enforcement

**Deliverables**:
- Full CRUD for users
- Role management
- Admin-only access enforcement

### Phase 4: Golden Repository Management (Story 4)
**Duration**: 2-3 days

1. Golden repo list page
2. Add repository form (triggers background job)
3. Refresh repository action
4. Delete repository with confirmation
5. Repository status display
6. Progress indication for long-running operations

**Deliverables**:
- Golden repo CRUD
- Background job integration
- Progress feedback

### Phase 5: Activated Repository Management (Story 5)
**Duration**: 1-2 days

1. Activated repo list page
2. Filter by user/status
3. Deactivate repository action
4. Repository details view
5. Link to golden repo details

**Deliverables**:
- Activated repo listing with filters
- Deactivation capability
- Cross-reference to golden repos

### Phase 6: Job Monitoring (Story 6)
**Duration**: 2-3 days

1. Job list page with filters
2. Job status display with progress
3. Auto-refresh for running jobs
4. Cancel job functionality
5. Job cleanup action (admin only)
6. Job statistics view

**Deliverables**:
- Comprehensive job monitoring
- Real-time progress updates
- Job lifecycle management

### Phase 7: Query Testing Interface (Story 7)
**Duration**: 2-3 days

1. Query input form
2. Repository selector
3. Search mode selector (semantic/fts/hybrid)
4. Results display with code highlighting
5. Query parameter controls
6. Response time display

**Deliverables**:
- Interactive query testing
- All query modes supported
- Result visualization

### Phase 8: Configuration Management (Story 8)
**Duration**: 1-2 days

1. Configuration display page
2. Edit global refresh interval
3. View resource limits
4. Server configuration viewer
5. Save/cancel workflow

**Deliverables**:
- Configuration viewing
- Limited configuration editing
- Settings persistence

---

## 6. Shared Components to Extract

### 6.1 Template Components

Create these reusable includes early (Phase 1):

| Component | Purpose | Usage |
|-----------|---------|-------|
| `nav.html` | Navigation bar | All pages |
| `flash.html` | Flash messages | All pages |
| `pagination.html` | Table pagination | Lists |
| `modal.html` | Modal dialog container | Forms |
| `loading.html` | Loading spinner | htmx swaps |
| `confirm.html` | Confirmation dialog | Deletes |
| `empty.html` | Empty state display | Empty lists |
| `error.html` | Error display | Error responses |

### 6.2 JavaScript Utilities

Minimal JS needed (htmx handles most interaction):

```javascript
// app.js - Minimal custom JavaScript

// Show loading indicator on htmx requests
document.body.addEventListener('htmx:beforeRequest', function(event) {
    document.getElementById('loading-indicator')?.classList.remove('hidden');
});

document.body.addEventListener('htmx:afterRequest', function(event) {
    document.getElementById('loading-indicator')?.classList.add('hidden');
});

// Handle flash messages from responses
document.body.addEventListener('htmx:afterSwap', function(event) {
    // Check for flash message in response headers
    const flash = event.detail.xhr.getResponseHeader('X-Flash-Message');
    if (flash) {
        showFlash(JSON.parse(flash));
    }
});

function showFlash(flash) {
    const container = document.getElementById('flash-container');
    const html = `<article class="flash flash-${flash.category}">${flash.message}</article>`;
    container.insertAdjacentHTML('beforeend', html);
    setTimeout(() => container.firstElementChild?.remove(), 5000);
}
```

### 6.3 Python Utilities

```python
# web/context.py - Template context builders

from fastapi import Request
from typing import Any, Dict

def base_context(request: Request, session: dict) -> Dict[str, Any]:
    """Build base context for all templates."""
    return {
        "request": request,
        "user": session,
        "csrf_token": session.get("csrf_token"),
        "nav_items": get_nav_items(session.get("role")),
    }

def get_nav_items(role: str) -> list:
    """Get navigation items based on user role."""
    items = [
        {"label": "Dashboard", "url": "/admin/dashboard", "icon": "home"},
        {"label": "Jobs", "url": "/admin/jobs", "icon": "clock"},
        {"label": "Query", "url": "/admin/query", "icon": "search"},
    ]

    if role in ("admin", "power_user"):
        items.extend([
            {"label": "Golden Repos", "url": "/admin/golden-repos", "icon": "database"},
            {"label": "Activated Repos", "url": "/admin/activated-repos", "icon": "folder"},
        ])

    if role == "admin":
        items.extend([
            {"label": "Users", "url": "/admin/users", "icon": "users"},
            {"label": "Config", "url": "/admin/config", "icon": "settings"},
        ])

    return items
```

---

## 7. Testing Strategy

### 7.1 Unit Tests

- Test session management (create, validate, destroy)
- Test CSRF token generation and validation
- Test template context builders
- Test access control decorators

### 7.2 Integration Tests

- Test login/logout flow
- Test protected routes require authentication
- Test admin routes require admin role
- Test htmx partials return correct content-type
- Test flash messages work correctly

### 7.3 E2E Tests

- Use Playwright or Selenium for browser testing
- Test full user workflows (login, manage users, logout)
- Test htmx interactions update DOM correctly
- Test error handling shows appropriate messages

---

## 8. Dependencies

### 8.1 Python Dependencies

```python
# Already in requirements (FastAPI ecosystem):
# - fastapi
# - jinja2 (for Jinja2Templates)
# - python-multipart (for form handling)

# Additional required:
itsdangerous>=2.0.0  # For signed session cookies
```

### 8.2 Frontend Dependencies (Static Files)

| Library | Version | Purpose | Size |
|---------|---------|---------|------|
| Pico CSS | 2.0.6 | Classless CSS framework | 15KB gzip |
| htmx | 1.9.10 | AJAX interactions | 14KB gzip |

Total additional JS/CSS: ~30KB gzipped

**No build step required** - download minified files directly.

---

## 9. Appendix: API Endpoints to Consume

### Authentication
- `POST /auth/login` - Login (used for web login)
- `GET /api/admin/users` - List users (admin only)
- `POST /api/admin/users` - Create user
- `PUT /api/admin/users/{username}` - Update user role
- `DELETE /api/admin/users/{username}` - Delete user
- `PUT /api/users/change-password` - Change password

### Health & Status
- `GET /health` - Server health
- `GET /cache/stats` - Cache statistics

### Golden Repositories
- `GET /api/admin/golden-repos` - List golden repos
- `POST /api/admin/golden-repos` - Add golden repo (returns job_id)
- `POST /api/admin/golden-repos/{alias}/refresh` - Refresh repo
- `DELETE /api/admin/golden-repos/{alias}` - Delete repo
- `GET /api/repos/golden/{alias}` - Get repo details
- `GET /api/repos/golden/{alias}/branches` - List branches

### Activated Repositories
- `GET /api/repos` - List activated repos
- `POST /api/repos/activate` - Activate repo (returns job_id)
- `DELETE /api/repos/{user_alias}` - Deactivate repo
- `GET /api/repos/{user_alias}` - Get repo details
- `GET /api/repos/available` - List available repos
- `GET /api/repos/status` - Repository status summary

### Jobs
- `GET /api/jobs` - List jobs (with pagination)
- `GET /api/jobs/{job_id}` - Get job status
- `DELETE /api/jobs/{job_id}` - Cancel job
- `DELETE /api/admin/jobs/cleanup` - Cleanup old jobs
- `GET /api/admin/jobs/stats` - Job statistics

### Query
- `POST /api/query` - Execute semantic query

### Configuration
- `GET /global/config` - Get global config
- `PUT /global/config` - Update global config

---

## 10. Conclusion

This architectural analysis provides a comprehensive blueprint for adding an administrative Web UI to the CIDX server. The recommended approach:

1. **Uses existing infrastructure** - Leverages FastAPI's Jinja2 support, existing auth managers, and REST API endpoints
2. **Maintains separation of concerns** - Web UI in dedicated `web/` package, clear route prefixes
3. **Follows security best practices** - httpOnly cookies, CSRF protection, role-based access
4. **Minimizes complexity** - No build step, minimal JS, classless CSS framework
5. **Enables incremental delivery** - 8 stories can be implemented independently

The total effort is estimated at 15-20 development days for all 8 stories, with the foundation (Story 1) being the critical path that enables all subsequent work.

# External OAuth Provider Integration - Implementation Plan

## Executive Summary

Add single OIDC provider support (e.g., Keycloak) to CIDX server for enterprise SSO integration. Simple "Sign in with SSO" button on login page with auto-redirect preference cookie. Email-based user matching and JIT provisioning defaulting to NORMAL_USER role. After OIDC authentication, use standard CIDX JWT sessions (no ongoing OIDC token validation).

## User Requirements (Confirmed)

1. **Single OIDC Provider**: Support one external OIDC provider (e.g., Keycloak) if configured
2. **Simple SSO Integration**: "Sign in with SSO" link on login page when enabled
3. **JIT Provisioning**: Auto-create users with NORMAL_USER role by default
4. **Email-Based Matching**: Auto-link external identities to existing users by verified email
5. **SSO Preference Cookie**: Remember user's SSO choice for auto-redirect on subsequent visits

## Architecture Overview

### Dual OAuth System

**Internal OAuth (Existing)**:
- Continues working unchanged
- Used by existing MCP clients and API integrations
- No breaking changes

**External OIDC (New)**:
- Single OIDC provider support (if configured)
- Simple "Sign in with SSO" button on login page
- Email-based auto-linking
- JIT user provisioning
- SSO preference cookie for auto-redirect

### Key Design Decisions

1. **Configuration**: Single OIDC provider config in `config_manager.py` (no env vars, config file only)
2. **Session Handling**: OIDC ONLY for initial sign-in, then standard JWT sessions (like password login)
3. **Identity Tracking**: Track external identities in SQLite for fast lookup, metadata in `users.json`
4. **Provider Implementation**: Single generic `OIDCProvider` class (no provider-specific implementations)
5. **Token Validation**: NO CHANGE to `dependencies.py` - uses existing JWT validation after sign-in
6. **SSO Preference**: Cookie to remember user's SSO choice for auto-redirect

**Simplified Flow**:
```
1. User visits login page
2. If OIDC configured: Show "Sign in with SSO" button
3. User clicks SSO → Redirect to OIDC provider
4. OIDC callback with authorization code
5. Exchange code for tokens, extract user info
6. Match or create user (email-based)
7. Issue CIDX JWT session token (same as password login)
8. Set cidx_session cookie + sso_preference cookie
9. All subsequent requests → standard JWT validation

Auto-redirect on subsequent visits:
- If sso_preference cookie set → skip login page, redirect to SSO directly
```

This matches standard OAuth practice: OIDC for authentication, internal JWT for sessions.

## Implementation Plan

### Phase 1: Configuration & Foundation (Days 1-3)

#### 1.1 Configuration Schema (`config_manager.py`)

Add new dataclass for **single OIDC provider**:

```python
@dataclass
class OIDCProviderConfig:
    """Single external OIDC provider configuration."""

    enabled: bool = False  # Master kill switch
    provider_name: str = "SSO"  # Display name (e.g., "Company SSO")

    # OIDC Discovery
    issuer_url: str = ""  # Required: OIDC issuer URL

    # Client credentials
    client_id: str = ""
    client_secret: str = ""

    # Optional overrides (if not using discovery)
    authorization_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    userinfo_endpoint: Optional[str] = None
    jwks_uri: Optional[str] = None

    # Scopes and claims
    scopes: List[str] = field(default_factory=lambda: ["openid", "profile", "email"])
    email_claim: str = "email"
    username_claim: str = "preferred_username"

    # Security
    use_pkce: bool = True
    require_email_verification: bool = True

    # JIT provisioning
    enable_jit_provisioning: bool = True
    default_role: str = "normal_user"

    # SSO preference
    enable_auto_redirect: bool = True  # Auto-redirect if sso_preference cookie set

# Add to ServerConfig
@dataclass
class ServerConfig:
    # ... existing fields ...
    oidc_provider_config: Optional[OIDCProviderConfig] = None
```

**Configuration via config file only** (no env vars needed).

#### 1.2 Database Schema (`oidc_identities.db`)

Create new **lightweight** SQLite database at `~/.cidx-server/oidc_identities.db`:

```sql
-- OIDC identity links (for fast lookup during sign-in)
-- This allows quick subject → username lookups without scanning users.json
CREATE TABLE oidc_identity_links (
    username TEXT NOT NULL PRIMARY KEY,
    subject TEXT NOT NULL UNIQUE,  -- OIDC sub claim
    email TEXT,
    linked_at TEXT NOT NULL,
    last_login TEXT
);

CREATE INDEX idx_oidc_subject ON oidc_identity_links (subject);
CREATE INDEX idx_oidc_email ON oidc_identity_links (email);
```

**Note**: No sessions table needed! After sign-in, we use standard JWT sessions (same as password login).
**Note**: Single provider means no `provider_id` field needed.

#### 1.3 Extended User Model (`user_manager.py`)

Update `users.json` schema (inline storage, backwards compatible):

```json
{
  "john": {
    "role": "normal_user",
    "password_hash": "bcrypt_hash",
    "created_at": "2025-01-15T10:30:00Z",
    "email": "john@example.com",
    "oidc_identity": {
      "subject": "oidc-user-id-12345",
      "email": "john@example.com",
      "linked_at": "2025-01-15T10:30:00Z",
      "last_login": "2025-01-20T14:22:00Z"
    }
  }
}
```

**Note**: Single provider means single `oidc_identity` object (not array).

Add methods to `UserManager`:
```python
def get_user_by_email(self, email: str) -> Optional[User]
def set_oidc_identity(self, username: str, identity: Dict[str, Any]) -> bool
def remove_oidc_identity(self, username: str) -> bool
def create_oidc_user(self, username: str, role: UserRole, email: Optional[str], oidc_identity: Dict) -> User
```

### Phase 2: Provider Abstraction Layer (Days 4-7)

#### 2.1 Module Structure (Simplified - Single Provider)

```
src/code_indexer/server/auth/oidc/
├── __init__.py
├── oidc_provider.py           # Generic OIDC implementation (no base class needed)
├── oidc_manager.py            # Main orchestrator
├── state_manager.py           # CSRF state tokens
├── exceptions.py              # Custom exceptions
└── routes.py                  # FastAPI endpoints
```

**Removed** (not needed for single provider):
- ~~provider_base.py~~ - No abstraction needed
- ~~github_provider.py~~ - No GitHub support
- ~~google_provider.py~~ - No Google support
- ~~provider_registry.py~~ - No factory pattern needed

#### 2.2 OIDC Provider Class (`oidc_provider.py`)

Simple, concrete implementation (no abstraction):

```python
@dataclass
class OIDCMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: Optional[str] = None
    jwks_uri: Optional[str] = None

@dataclass
class OIDCUserInfo:
    email: Optional[str] = None
    username: Optional[str] = None
    name: Optional[str] = None
    subject: str = ""  # OIDC sub claim
    email_verified: bool = False
    raw_claims: Dict[str, Any] = field(default_factory=dict)

class OIDCProvider:
    """Generic OIDC provider implementation."""

    def __init__(self, config: OIDCProviderConfig):
        self.config = config
        self._metadata: Optional[OIDCMetadata] = None

    async def discover_metadata(self) -> OIDCMetadata:
        """Discover provider metadata via .well-known/openid-configuration"""

    def get_authorization_url(self, state: str, redirect_uri: str, code_challenge: str) -> str:
        """Build OIDC authorization URL with PKCE"""

    async def exchange_code_for_token(self, code: str, code_verifier: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange authorization code for tokens"""

    async def get_user_info(self, access_token: str) -> OIDCUserInfo:
        """Get user info from userinfo endpoint or ID token"""
```

#### 2.3 OIDC Provider Implementation Details

Generic OIDC-compliant implementation:
- Automatic discovery via `.well-known/openid-configuration`
- JWT validation using provider's JWKS
- Userinfo endpoint integration
- PKCE (S256) enforcement
- Email verification checking

### Phase 3: OIDC Manager (Days 8-10)

#### 3.1 Core Manager (`oidc_manager.py`)

Main orchestrator handling:
- Single OIDC provider lifecycle
- Email-based user matching
- JIT user provisioning
- Identity linking

**Key Methods**:

```python
class OIDCManager:
    def __init__(self, config: OIDCProviderConfig, user_manager: UserManager, jwt_manager: JWTManager):
        self.config = config
        self.user_manager = user_manager
        self.jwt_manager = jwt_manager  # For creating JWT sessions
        self.provider: Optional[OIDCProvider] = None
        self.db_path = str(Path.home() / ".cidx-server" / "oidc_identities.db")

    async def initialize(self):
        """Initialize OIDC provider if configured"""
        if self.config.enabled:
            self.provider = OIDCProvider(self.config)
            await self.provider.discover_metadata()

    def is_enabled(self) -> bool:
        """Check if OIDC is configured and enabled"""
        return self.config.enabled and self.provider is not None

    async def match_or_create_user(self, user_info: OIDCUserInfo) -> User:
        """
        Match OIDC identity to internal user by email, or create new user.

        Flow:
        1. Check if subject already exists in DB → return user
        2. Check if verified email matches existing user → auto-link, return user
        3. Check if JIT provisioning enabled → create new user
        4. Otherwise → raise error
        """

    def create_jwt_session(self, user: User) -> str:
        """
        Create CIDX JWT session token for user (same as password login).

        This is called after successful OIDC authentication.
        Returns JWT token to be set in cidx_session cookie.
        """
        return self.jwt_manager.create_token({
            "username": user.username,
            "role": user.role.value,
            "created_at": user.created_at.isoformat(),
        })

    async def link_oidc_identity(self, username: str, subject: str, email: Optional[str]):
        """Store OIDC identity link in database for future fast lookups"""
```

#### 3.2 Email Matching Algorithm

```python
def _match_user_by_email(self, email: str, email_verified: bool) -> Optional[User]:
    """
    Match user by email (case-insensitive).

    Security: Only match if email is verified by provider.
    """
    if not email_verified:
        logger.warning(f"Email {email} not verified, skipping auto-link")
        return None

    # Case-insensitive lookup
    users = self.user_manager._load_users()
    email_lower = email.lower().strip()

    matches = []
    for username, user_data in users.items():
        user_email = user_data.get("email")
        if user_email and user_email.lower().strip() == email_lower:
            matches.append(username)

    if len(matches) == 1:
        return self.user_manager.get_user(matches[0])
    elif len(matches) > 1:
        logger.warning(f"Multiple users with email {email}, skipping auto-link")
        return None

    return None
```

#### 3.3 JIT User Provisioning

```python
def _create_jit_user(self, user_info: OIDCUserInfo) -> User:
    """
    Create user via JIT provisioning.

    Username generation priority:
    1. preferred_username claim (if valid)
    2. Email prefix (before @)
    3. Subject (sanitized)
    4. Fallback: sso_user
    """
    # Generate username
    base_username = self._generate_username(user_info)
    username = self._ensure_unique_username(base_username)

    # Create user without password
    oidc_identity = {
        "subject": user_info.subject,
        "email": user_info.email,
        "linked_at": datetime.now(timezone.utc).isoformat(),
        "last_login": datetime.now(timezone.utc).isoformat(),
    }

    user = self.user_manager.create_oidc_user(
        username=username,
        role=UserRole(self.config.default_role),
        email=user_info.email,
        oidc_identity=oidc_identity
    )

    return user
```

### Phase 4: API Endpoints & Integration (Days 11-13)

#### 4.1 OIDC Routes (`routes.py`)

```python
router = APIRouter(prefix="/auth/sso", tags=["sso"])

@router.get("/login")
async def sso_login(request: Request, redirect_uri: Optional[str] = None):
    """
    Initiate OIDC flow.

    Flow:
    1. Generate PKCE challenge and state token
    2. Store state in server-side cache
    3. Redirect to OIDC provider's authorization endpoint
    """
    if not oidc_manager or not oidc_manager.is_enabled():
        raise HTTPException(status_code=404, detail="SSO not configured")

    # Generate PKCE
    code_verifier = secrets.token_urlsafe(32)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().rstrip("=")

    # Generate state token
    state = state_manager.create_state({
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri or "/admin"
    })

    # Build authorization URL
    callback_url = request.url_for("sso_callback")
    auth_url = oidc_manager.provider.get_authorization_url(state, callback_url, code_challenge)

    return RedirectResponse(url=auth_url)

@router.get("/callback")
async def sso_callback(code: str, state: str, response: Response):
    """
    Handle OIDC callback.

    Flow:
    1. Validate state token (CSRF protection)
    2. Exchange code for tokens (with PKCE verifier)
    3. Get user info from provider
    4. Match or create user (email-based)
    5. **Create CIDX JWT session token**
    6. Set cidx_session cookie + sso_preference cookie
    7. Redirect to dashboard
    """

    # Validate state
    state_data = state_manager.validate_state(state)
    if not state_data:
        raise HTTPException(status_code=400, detail="Invalid state")

    # Exchange code for tokens
    tokens = await oidc_manager.provider.exchange_code_for_token(
        code, state_data["code_verifier"], request.url_for("sso_callback")
    )

    # Get user info
    user_info = await oidc_manager.provider.get_user_info(tokens["access_token"])

    # Match or create user
    user = await oidc_manager.match_or_create_user(user_info)

    # Create JWT session (SAME as password login)
    jwt_token = oidc_manager.create_jwt_session(user)

    # Set cidx_session cookie
    response.set_cookie(
        key="cidx_session",
        value=jwt_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=36000,  # 10 hours
    )

    # Set SSO preference cookie for auto-redirect
    if oidc_manager.config.enable_auto_redirect:
        response.set_cookie(
            key="sso_preference",
            value="enabled",
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=2592000,  # 30 days
        )

    return RedirectResponse(url=state_data.get("redirect_uri", "/admin"), status_code=302)
```

#### 4.2 Token Validation Integration (`dependencies.py`)

**NO CHANGES NEEDED!**

After external OAuth sign-in, users have a standard CIDX JWT session token (same as password login). The existing `get_current_user()` code already handles JWT validation perfectly:

```python
def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    # Existing code handles JWT from cidx_session cookie or Bearer token
    # Works for both password login AND external OAuth login
    # No changes needed!
    ...
```

**Why this is simpler**:
- External OAuth users and password users both have JWT sessions
- No special handling needed in authentication middleware
- All existing endpoints work unchanged
- Session management (expiration, refresh) already implemented

#### 4.3 Login Page Auto-Redirect

Update web login page to check SSO preference cookie:

```python
@web_router.get("/login")
async def login_page(request: Request):
    """Login page with SSO support."""

    # Check SSO preference cookie
    sso_preference = request.cookies.get("sso_preference")

    if sso_preference == "enabled" and oidc_manager and oidc_manager.is_enabled():
        if oidc_manager.config.enable_auto_redirect:
            # Auto-redirect to SSO
            return RedirectResponse(url="/auth/sso/login", status_code=302)

    # Show login page with SSO button
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "sso_enabled": oidc_manager and oidc_manager.is_enabled(),
            "sso_name": oidc_manager.config.provider_name if oidc_manager else "SSO",
        },
    )
```

#### 4.4 App Initialization (`app.py`)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global oidc_manager

    # ... existing initialization ...

    # Initialize OIDC
    config = config_service.load_config()
    if config.oidc_provider_config and config.oidc_provider_config.enabled:
        oidc_manager = OIDCManager(
            config=config.oidc_provider_config,
            user_manager=user_manager,
            jwt_manager=jwt_manager,
        )
        await oidc_manager.initialize()
        dependencies.oidc_manager = oidc_manager

    yield

    if oidc_manager:
        await oidc_manager.shutdown()

# Register routes
app.include_router(oidc_router)
```

### Phase 5: Web UI & Admin Tools (Days 14-16)

#### 5.1 Admin Configuration UI

New section on `/admin/settings` page:

Features:
- Enable/disable SSO toggle
- Configure OIDC provider (issuer URL, client ID, client secret)
- Test connection button
- JIT provisioning settings

#### 5.2 User Profile Page

New section: "SSO Account"

Features:
- Show OIDC identity if linked (email, linked date)
- Unlink button (if password is set)
- Warning: "Set a password before unlinking SSO account"

#### 5.3 Login Page Enhancement

Simple additions:
- Show "Sign in with SSO" button (if configured)
- Auto-redirect on subsequent visits (if sso_preference cookie set)
- Existing username/password form remains
- Clear SSO preference link (for manual login)

### Phase 6: Security & Auditing (Days 17-18)

#### 6.1 Security Controls

1. **Email Verification Requirement**: Only trust `email_verified: true` claims
2. **Provider Trust List**: Validate issuer matches expected value
3. **PKCE Enforcement**: All flows use S256 PKCE
4. **State Token Protection**: Cryptographically signed, 5-minute TTL
5. **Rate Limiting**: OAuth callback endpoint rate limiting
6. **Session Security**: HttpOnly, Secure, SameSite cookies

#### 6.2 Audit Logging

Add to `audit_logger.py`:

```python
def log_oidc_identity_link(username, subject, email, auto_linked, ip)
def log_jit_provisioning(username, email, role, ip)
def log_oidc_login(username, ip)
def log_email_verification_failure(email, ip)
```

### Phase 7: Testing (Days 19-22)

#### 7.1 Unit Tests

```
tests/unit/server/auth/oidc/
├── test_oidc_provider.py              # OIDC discovery, token validation
├── test_oidc_manager.py               # User matching, JIT provisioning
├── test_username_generation.py        # Username conflict handling
└── test_email_matching.py             # Case-insensitive matching
```

#### 7.2 Integration Tests

```
tests/integration/server/auth/oidc/
├── test_keycloak_flow.py              # Full Keycloak flow
├── test_jit_provisioning.py           # Auto-create users
├── test_email_linking.py              # Auto-link via email
└── test_backwards_compatibility.py    # Existing auth still works
```

#### 7.3 Manual Testing Checklist

- [ ] Keycloak local setup and configuration
- [ ] First-time login (JIT provision)
- [ ] Second login (existing identity)
- [ ] Email-based auto-linking
- [ ] Manual account linking
- [ ] Token refresh flow
- [ ] Logout and session cleanup
- [ ] MCP client with JWT session

### Phase 8: Documentation (Days 23-24)

#### 8.1 Configuration Guide

- How to configure Keycloak realm and client
- Configuration file examples
- Troubleshooting guide

#### 8.2 User Guide

- How to link external accounts
- How to login with external providers
- How to unlink accounts
- Security best practices

#### 8.3 Admin Guide

- Provider management via web UI
- Troubleshooting OAuth errors
- Monitoring and audit logs
- User management with external identities

## Configuration Example

### Keycloak OIDC (in ~/.cidx-server/config.json)

```json
{
  "oidc_provider_config": {
    "enabled": true,
    "provider_name": "Company SSO",
    "issuer_url": "https://keycloak.example.com/realms/myrealm",
    "client_id": "cidx-server",
    "client_secret": "your-client-secret-here",
    "scopes": ["openid", "profile", "email"],
    "use_pkce": true,
    "require_email_verification": true,
    "enable_jit_provisioning": true,
    "default_role": "normal_user",
    "enable_auto_redirect": true
  }
}
```

**Note**: No env vars needed - all configuration in config file.

## Files Modified/Created

### New Files
- `src/code_indexer/server/auth/oidc/__init__.py`
- `src/code_indexer/server/auth/oidc/oidc_provider.py`
- `src/code_indexer/server/auth/oidc/oidc_manager.py`
- `src/code_indexer/server/auth/oidc/state_manager.py`
- `src/code_indexer/server/auth/oidc/exceptions.py`
- `src/code_indexer/server/auth/oidc/routes.py`

### Modified Files
- `src/code_indexer/server/utils/config_manager.py` - Add OIDCProviderConfig
- `src/code_indexer/server/auth/user_manager.py` - Add OIDC identity methods
- `src/code_indexer/server/auth/audit_logger.py` - Add OIDC audit events
- `src/code_indexer/server/app.py` - Initialize manager, register routes
- `src/code_indexer/server/web/routes.py` - Add SSO button to login page, auto-redirect logic

**NOT Modified**:
- `src/code_indexer/server/auth/dependencies.py` - No changes! JWT validation already works for OIDC users

### Database Files
- `~/.cidx-server/oidc_identities.db` - New lightweight SQLite (only identity links, no sessions)
- `~/.cidx-server/users.json` - Extended schema with `oidc_identity` field (backwards compatible)
- `~/.cidx-server/config.json` - New `oidc_provider_config` section

## Dependencies

**Existing** (no new packages needed):
- `python-jose[cryptography]` - JWT validation
- `httpx` - HTTP client for provider communication
- `pydantic` - Data validation
- `fastapi` - API framework
- `aiosqlite` - Async SQLite

## Security Checklist

- [x] Email verification required for auto-linking
- [x] PKCE mandatory for all OAuth flows
- [x] State token CSRF protection
- [x] JWT signature verification for OIDC tokens
- [x] Rate limiting on OAuth endpoints
- [x] Audit logging for all external auth events
- [x] Secure cookie configuration
- [x] Provider trust validation
- [x] No password requirements for external-only users
- [x] Multiple identity prevention across users

## Backwards Compatibility Guarantees

1. **Existing Users**: Continue using password auth unchanged
2. **Existing OAuth Clients**: Internal OAuth 2.1 server continues unchanged
3. **Existing Endpoints**: No breaking changes to any endpoints
4. **Data Migration**: NOT REQUIRED - new fields optional
5. **Configuration**: External OAuth disabled by default
6. **MCP Clients**: Continue using internal OAuth, can opt-in to external

## Success Criteria

1. **Functionality**: User can login with Keycloak (or other OIDC provider)
2. **JIT Provisioning**: New users auto-created with NORMAL_USER role
3. **Email Matching**: Existing users auto-linked by verified email
4. **MCP Support**: MCP clients can discover and use external providers
5. **Security**: All security controls implemented and tested
6. **Performance**: OAuth flow completes in <2 seconds
7. **Backwards Compat**: All existing tests pass unchanged
8. **Documentation**: Complete setup guides

## Timeline (REVISED - Single OIDC Provider)

- **Week 1** (Days 1-7): Foundation + OIDC Provider + Manager
- **Week 2** (Days 8-12): Routes + Integration + Web UI

**Total**: ~12 days (~2 weeks)

**Time savings**:
- ~6 days saved by using JWT sessions (no external token management)
- ~6 days saved by single provider (no multi-provider framework)
- **Total savings**: ~12 days (from original 24 to 12)

## Current Implementation Status (2025-12-30)

**Test Results**: See [oidc-test-results.md](./oidc-test-results.md) for detailed testing outcomes.

### Completed Components (55 tests passing)

**Configuration & Foundation**:
- `OIDCProviderConfig` dataclass in config_manager.py (lines 112-145)
- ServerConfig integration with deserialization support
- .gitignore updates for OIDC-related files

**Core OIDC Modules** (src/code_indexer/server/auth/oidc/):
- `oidc_provider.py` - Generic OIDC provider with discovery, PKCE, token exchange
- `oidc_manager.py` - User matching, JIT provisioning, identity linking
- `state_manager.py` - CSRF state token management (5-minute TTL)
- `routes.py` - `/auth/sso/login` and `/auth/sso/callback` endpoints
- `exceptions.py` - Custom exception classes
- `oidc_identity_store.py` - SQLite database manager (unused, see below)

**User Management Extensions** (user_manager.py:579-688):
- `get_user_by_email()` - Case-insensitive email lookup
- `set_oidc_identity()` - Link OIDC identity to user
- `remove_oidc_identity()` - Unlink OIDC identity
- `create_oidc_user()` - JIT provisioning with random password

**Web UI Integration**:
- Login page with "Sign in with SSO" button (login.html:40-48)
- SSO preference cookie auto-redirect logic (routes.py:133-153)
- CSS styling for SSO button and divider (admin.css)

**App Integration** (app.py:1798-1837):
- OIDC initialization on server startup
- Provider metadata discovery
- Route registration

**Test Coverage**:
- 38 tests in tests/unit/server/auth/oidc/
- 17 tests for identity store, user manager, config
- 7 web cookie security tests
- **Total: 62 tests passing**

### Critical Gaps Requiring Fixes

**1. SSO Preference Cookie Not Set** (HIGH PRIORITY)
- **Location**: routes.py:95 (sso_callback function)
- **Issue**: Callback only sets `cidx_session` cookie, missing `sso_preference` cookie
- **Expected**: Should set sso_preference=enabled cookie for auto-redirect feature
- **Plan Reference**: Lines 444-454 specify both cookies should be set
- **Impact**: Auto-redirect on subsequent logins won't work

**2. Database Schema Not Initialized** (HIGH PRIORITY)
- **Location**: oidc_manager.py:15-20 (initialize method)
- **Issue**: `_init_db()` method exists (line 32) but never called
- **Expected**: `initialize()` should call `await self._init_db()`
- **Impact**: OIDC identity links table never created, first login will fail

**3. HTTP Error Handling Missing** (MEDIUM PRIORITY)
- **Location**: oidc_provider.py (discover_metadata, exchange_code_for_token, get_user_info)
- **Issue**: No error handling for HTTP failures (4xx, 5xx responses)
- **Expected**: Proper exception handling with meaningful error messages
- **Impact**: Cryptic errors on provider failures, poor UX

**4. Token Exchange Response Validation Missing** (MEDIUM PRIORITY)
- **Location**: oidc_provider.py:83 (exchange_code_for_token)
- **Issue**: No validation that response contains required fields (access_token, id_token)
- **Expected**: Validate response structure, handle missing fields
- **Impact**: KeyError exceptions on malformed provider responses

**5. Userinfo Response Validation Missing** (MEDIUM PRIORITY)
- **Location**: oidc_provider.py:104 (get_user_info)
- **Issue**: No validation of required claims (sub, email_verified)
- **Expected**: Validate required claims exist, handle missing fields gracefully
- **Impact**: Incorrect user matching or failed authentication

### Missing Features (Per Original Plan)

**Admin UI (Phase 5)**:
- No admin settings page for OIDC configuration
- No test connection button
- No user profile SSO account section
- No ability to unlink OIDC accounts via UI

**Documentation**:
- No general OIDC provider setup guide (IDP-agnostic)
- No configuration reference documentation
- No troubleshooting guide for common issues
- No security best practices guide

**Integration Tests**:
- No end-to-end tests with mock OIDC provider
- No tests for error scenarios (invalid tokens, missing claims)
- No tests for JIT provisioning edge cases

### Technical Debt

**Unused Module**:
- `oidc_identity_store.py` exists but not used anywhere
- Database operations implemented directly in `oidc_manager.py`
- Consider: Remove or integrate this module

**Missing Logging**:
- No structured logging for OIDC events
- Missing audit log entries (per Phase 6 plan)
- No telemetry for troubleshooting

**Security Enhancements Not Implemented**:
- No rate limiting on OAuth endpoints (per plan line 575)
- No provider trust validation (per plan line 572)
- Email verification requirement implemented but not tested

## Next Steps

### Phase 1: Bug Fixes (Critical)
1. Add `await self._init_db()` to `oidc_manager.initialize()`
2. Set `sso_preference` cookie in `routes.sso_callback()`
3. Add HTTP error handling to all provider methods
4. Add response validation for token exchange and userinfo

### Phase 2: Integration Testing
1. Set up test OIDC provider (Keycloak or mock)
2. Test full authentication flow end-to-end
3. Test JIT provisioning with various user scenarios
4. Test email-based auto-linking
5. Test error scenarios (invalid tokens, missing claims)

### Phase 3: Admin UI & Documentation
1. Add admin settings page for OIDC configuration
2. Add user profile SSO account management
3. Write IDP-agnostic setup guide
4. Document configuration options with examples

### Phase 4: Production Readiness
1. Add structured logging and audit events
2. Implement rate limiting
3. Add provider trust validation
4. Security review and penetration testing

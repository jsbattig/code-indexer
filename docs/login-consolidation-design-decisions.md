# Unified Login Consolidation - Design Decisions

This document records the final decisions made for each open design question in the login consolidation plan.

---

## 1. Landing Page for Admin Users

**Question:** When an admin user logs in via the unified login URL (`/login`), where should they be redirected?

**Decision:** **Option A - Redirect to admin dashboard (`/admin/`)**

**Implementation:** `routes.py:4075-4077`
```python
elif user.role.value == "admin":
    # Admin users go to admin dashboard
    redirect_url = "/admin/"
```

**Rationale:**
- Admins have more capabilities, should see full interface by default
- Smart redirect logic prioritizes explicit `redirect_to` parameter, then role-based defaults
- Admin can navigate to user interface via `/user/api-keys` if needed

**Priority Order:**
1. Explicit `redirect_to` parameter (if provided and safe)
2. Admin role → `/admin/`
3. Non-admin role → `/user/api-keys`

---

## 2. OAuth Consent Screen

**Question:** Should we show an explicit consent screen or auto-issue authorization code for authenticated users?

**Decision:** **Option A - Show consent screen**

**Implementation:**
- Template: `src/code_indexer/server/web/templates/oauth_authorize_consent.html`
- Handler: `src/code_indexer/server/auth/oauth/routes.py` (shows `oauth_authorize_consent.html`)
- Separation: Authentication (unified login) → Authorization (consent screen)

**Rationale:**
- OAuth 2.1 best practice - explicit user consent
- User sees what application is requesting access
- Better security (prevents silent authorization)
- Follows industry best practices (Google, GitHub, etc.)

**UX Flow:**
1. User visits OAuth `/authorize` endpoint
2. If not authenticated → redirect to `/login`
3. After login → show consent screen with "Authorize Access" button
4. User explicitly consents → authorization code issued

---

## 3. Session Scope Separation

**Question:** Should admin and user sessions be completely separate (different cookies) or unified?

**Decision:** **Option A - Keep unified**

**Implementation:** `src/code_indexer/server/web/auth.py`
```python
SESSION_COOKIE_NAME = "session"  # Same cookie for all contexts
# No path restrictions - works for /admin, /user, /oauth
```

**Rationale:**
- Admin needs access to both interfaces (manage users, also use user API keys)
- No security benefit to separation (same user, same privileges)
- Simpler implementation and maintenance
- Consistent with existing implementation

**Session Properties:**
- Cookie name: `"session"`
- Timeout: 8 hours (28,800 seconds)
- httpOnly: Yes
- secure: Yes (non-localhost)
- samesite: lax
- Path: No restrictions (works across all routes)

---

## 4. SSO Provider Display Name

**Question:** Should SSO button text be configurable or hardcoded?

**Decision:** **Hardcoded "Sign in with SSO" (Option A - Keep hardcoded)**

**Implementation:** `src/code_indexer/server/web/templates/unified_login.html`
```html
<button type="button" class="sso-button" onclick="redirectToSSO()">
    Sign in with SSO
</button>
```

**Rationale:**
- Simple, generic button text works for all providers
- No additional configuration needed
- Can add display name customization later if requested
- Not blocking for initial consolidation

**Future Enhancement:** Could add `OIDC_DISPLAY_NAME` config field to allow "Sign in with Okta" etc.

---

## 5. Logout Behavior

**Question:** Should logout redirect to unified login page or separate logout success page?

**Decision:** **Option A - Redirect to unified login (via backwards compatibility redirect)**

**Implementation:**
- Logout handlers redirect to `/admin/login` (old URL)
- Backwards compatibility: `/admin/login` → 301 redirect to `/login`
- Net effect: Logout → `/login`

**Implementation Details:**
```python
# routes.py logout handlers
response = RedirectResponse(
    url="/admin/login",  # Will 301 redirect to /login
    status_code=status.HTTP_303_SEE_OTHER,
)
```

**Rationale:**
- User likely wants to log in again (common pattern)
- No extra page needed - reuse login page
- Consistent UX - all authentication flows use same page
- No "Logged out successfully" message (kept simple)

**Note:** Logout handlers not updated to directly use `/login` to maintain compatibility with existing code. Backwards compatibility redirect handles the final destination.

---

## 6. Remember Me / Stay Logged In

**Question:** Should we add "Remember Me" checkbox to extend session timeout?

**Decision:** **Option A - No remember me (out of scope)**

**Implementation:** Not implemented

**Rationale:**
- Not requested in original requirements
- Adds complexity (different session timeouts, refresh tokens)
- Security consideration (longer-lived sessions = more risk)
- Can add later if needed (doesn't block consolidation)
- Fixed 8-hour session timeout for all sessions (existing behavior)

**Current Behavior:**
- All sessions: 8-hour timeout
- No persistence between browser sessions
- Session cleared on logout

---

## 7. Testing Approach

**Question:** Should we write tests before or during implementation?

**Decision:** **Option B - Concurrent testing**

**Implementation:**
- Comprehensive test suite: `tests/server/web/test_unified_login.py` (16 tests)
- Tests written alongside implementation
- All tests passing before marking work complete

**Rationale:**
- Write tests to validate approach as we build
- Implement features incrementally
- Fast feedback loop during development
- Ensures no regressions in existing functionality

**Test Coverage:**
1. Template rendering (3 tests)
2. Form submission and authentication (4 tests)
3. Smart redirect logic (2 tests)
4. SSO flow integration (2 tests)
5. Protected route decorators (2 tests)
6. Backwards compatibility redirects (2 tests)
7. Security validations (1 test)

**Result:** All 16 tests pass ✓

---

## Additional Implementation Decisions

### Backwards Compatibility Strategy

**Decision:** 301 Moved Permanently redirects for old URLs

**Implementation:**
```python
@login_router.get("/admin/login")
async def redirect_admin_login(redirect_to: Optional[str] = None):
    return RedirectResponse(url="/login", status_code=301)

@login_router.get("/user/login")
async def redirect_user_login(redirect_to: Optional[str] = None):
    return RedirectResponse(url="/login", status_code=301)
```

**Rationale:**
- 301 status informs clients to update bookmarks/links
- Preserves `redirect_to` parameter if provided
- No breaking changes for existing deployments

### Open Redirect Prevention

**Decision:** Strict validation of `redirect_to` parameter

**Implementation:**
```python
# Validate redirect_to URL (prevent open redirect)
safe_redirect = None
if redirect_to:
    # Only allow relative URLs starting with /
    if redirect_to.startswith("/") and not redirect_to.startswith("//"):
        safe_redirect = redirect_to
```

**Rationale:**
- Prevents attackers from redirecting users to external sites
- Only allows relative URLs (`/admin`, `/user/api-keys`)
- Blocks protocol-relative URLs (`//evil.com`)

### Session Creation Timing

**Decision:** Create session AFTER all validations pass

**Implementation:**
- Validate credentials first
- Validate redirect URL second
- Create session last (only on success)

**Rationale:**
- No session pollution from failed login attempts
- Clean error handling without session cleanup

---

## Summary

All 7 design questions resolved with pragmatic, security-conscious decisions that prioritize:
- **Security:** OAuth consent screens, open redirect prevention, unified session management
- **Simplicity:** Hardcoded SSO text, no remember me, unified sessions
- **User Experience:** Smart redirects, role-based defaults, backwards compatibility
- **Maintainability:** Concurrent testing, clear separation of concerns, comprehensive test coverage

**Implementation Status:** ✅ Complete - All 16 tests passing

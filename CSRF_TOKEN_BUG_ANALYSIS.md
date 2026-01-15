# CSRF Token Bug Analysis - Auto-Discovery Page

## Problem

Users get "invalid CSRF token" error when clicking "Add" button on auto-discovery repo listing.

## Root Cause

**Bug Location**: `src/code_indexer/server/web/routes.py`

The HTMX partials for GitLab and GitHub repository listings **do not pass `csrf_token` to their templates**:

```python
# Lines 4367-4392
def _build_gitlab_repos_response(
    request: Request,
    repositories: Optional[list] = None,
    # ... other params ...
):
    """Build GitLab repos partial template response."""
    return templates.TemplateResponse(
        "partials/gitlab_repos.html",
        {
            "request": request,
            "repositories": repositories or [],
            # ... other context ...
            # ❌ MISSING: "csrf_token": csrf_token
        },
    )

# Lines 4395-4420 - Same issue for GitHub
def _build_github_repos_response(...):
    # ❌ MISSING: "csrf_token": csrf_token
```

But the templates **require** csrf_token:

```html
<!-- partials/gitlab_repos.html line 124 -->
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">

<!-- partials/github_repos.html line 136 -->
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
```

## The Flow (Broken)

```
1. User loads /auto-discovery
   └─> auto_discovery_page() generates csrf_token
   └─> Template includes csrf_token ✅

2. User clicks "GitLab" or "GitHub" tab
   └─> HTMX loads /partials/auto-discovery/gitlab
   └─> gitlab_repos_partial() called
   └─> _build_gitlab_repos_response() renders template
   └─> Template context DOES NOT include csrf_token ❌
   └─> Forms render with: <input name="csrf_token" value=""> (EMPTY!)

3. User clicks "Add" button on a repo
   └─> Form submits with empty csrf_token
   └─> add_golden_repo() validates CSRF
   └─> validate_login_csrf_token() returns False
   └─> Error: "Invalid CSRF token" ❌
```

## Additional Issues

### CSRF Token Expiration (10 Minutes)

```python
# Line 80
CSRF_MAX_AGE_SECONDS = 600  # 10 minutes
```

If user browses repos for >10 minutes before clicking "Add", token expires.

### HTMX Partial Requests Don't Refresh Token

When HTMX loads partials:
- Main page has csrf_token (10 min lifetime)
- Partials loaded later don't refresh the token
- User might spend 5 minutes browsing → token has 5 min left
- After more browsing, token expires

## The Fix

### Quick Fix (Immediate)

Pass csrf_token from cookie to partials:

```python
def _build_gitlab_repos_response(
    request: Request,
    repositories: Optional[list] = None,
    # ... other params ...
):
    """Build GitLab repos partial template response."""
    # Get existing csrf_token from cookie (or generate new one)
    csrf_token = get_csrf_token_from_cookie(request) or generate_csrf_token()

    return templates.TemplateResponse(
        "partials/gitlab_repos.html",
        {
            "request": request,
            "repositories": repositories or [],
            # ... other context ...
            "csrf_token": csrf_token,  # ✅ ADD THIS
        },
    )

# Same fix for _build_github_repos_response
```

### Better Fix (Recommended)

1. **Increase CSRF token lifetime** (reduce UX friction):
   ```python
   CSRF_MAX_AGE_SECONDS = 3600  # 1 hour (or match session timeout)
   ```

2. **Refresh CSRF token on partial loads**:
   ```python
   # In gitlab_repos_partial() and github_repos_partial()
   csrf_token = get_csrf_token_from_cookie(request)
   if not csrf_token:
       csrf_token = generate_csrf_token()

   response = _build_gitlab_repos_response(
       request,
       result.repositories,
       # ... other params ...
       csrf_token=csrf_token,  # Pass to builder
   )

   # Refresh the cookie if it's close to expiration
   set_csrf_cookie(response, csrf_token)
   return response
   ```

3. **Update function signature** to accept csrf_token:
   ```python
   def _build_gitlab_repos_response(
       request: Request,
       repositories: Optional[list] = None,
       total_count: int = 0,
       # ... other params ...
       csrf_token: Optional[str] = None,  # ADD THIS
   ):
       # Use provided token or generate new one
       if not csrf_token:
           csrf_token = get_csrf_token_from_cookie(request) or generate_csrf_token()

       return templates.TemplateResponse(
           "partials/gitlab_repos.html",
           {
               "request": request,
               "csrf_token": csrf_token,  # ✅ INCLUDE IN CONTEXT
               # ... rest of context ...
           },
       )
   ```

## Testing

### Reproduce the Bug

1. Open auto-discovery page: http://localhost:8090/auto-discovery
2. Click "GitLab" or "GitHub" tab
3. Open browser DevTools → Network tab
4. Click "Add" on any repo
5. Check form data in network request:
   ```
   csrf_token: (empty string)
   ```
6. See error: "Invalid CSRF token"

### Verify the Fix

1. Apply fix to pass csrf_token to partials
2. Reload auto-discovery page
3. Click "GitLab" or "GitHub" tab
4. Open browser DevTools → Inspect form
5. Check hidden input:
   ```html
   <input type="hidden" name="csrf_token" value="(long token string)">
   ```
6. Click "Add" → Should succeed

### Check Token Expiration

1. Open auto-discovery page
2. Wait 11 minutes (longer than CSRF_MAX_AGE_SECONDS)
3. Click "Add" → Should fail (token expired)
4. Refresh page → New token generated
5. Click "Add" → Should succeed

## Files Affected

### Primary Fix
- `src/code_indexer/server/web/routes.py`
  - `_build_gitlab_repos_response()` (line 4367)
  - `_build_github_repos_response()` (line 4395)
  - `gitlab_repos_partial()` (line 4444)
  - `github_repos_partial()` (line 4504)

### Optional Improvement
- `src/code_indexer/server/web/routes.py`
  - `CSRF_MAX_AGE_SECONDS` (line 80) - Increase to 3600

### Templates (No changes needed)
- `src/code_indexer/server/web/templates/partials/gitlab_repos.html` (line 124)
- `src/code_indexer/server/web/templates/partials/github_repos.html` (line 136)

## Impact

### Severity
**HIGH** - Primary workflow broken

### Affected Users
- All users trying to add repos from auto-discovery
- Especially users who browse repos before selecting (token expires)

### Workaround (for users)
1. Refresh the page before clicking "Add"
2. Don't spend >10 minutes browsing repos

## Estimated Fix Time
- **Quick fix**: 15 minutes (just pass csrf_token to partials)
- **Better fix**: 30 minutes (add token refresh logic)
- **Testing**: 15 minutes

## Priority
**P0** - User-facing bug in primary workflow, should fix immediately

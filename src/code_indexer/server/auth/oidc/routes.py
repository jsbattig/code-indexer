"""OIDC authentication routes for FastAPI."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from ...web.auth import get_session_manager

router = APIRouter(prefix="/auth/sso", tags=["sso"])


# Global OIDC manager instance (injected by app.py)
oidc_manager = None


# Global state manager instance (injected by app.py)
state_manager = None


@router.get("/login")
async def sso_login(request: Request, redirect_uri: Optional[str] = None):
    """Initiate OIDC authentication flow."""
    if not oidc_manager or not oidc_manager.is_enabled():
        raise HTTPException(status_code=404, detail="SSO not configured")

    # Generate PKCE code verifier
    import secrets
    import hashlib
    import base64
    
    code_verifier = secrets.token_urlsafe(32)
    
    # Generate PKCE code challenge (S256 method)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().rstrip("=")

    # Create state token with code verifier and redirect_uri
    state = state_manager.create_state({
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri or "/admin"
    })

    # Build callback URL
    callback_url = str(request.url_for("sso_callback"))

    # Build authorization URL
    auth_url = oidc_manager.provider.get_authorization_url(state, callback_url, code_challenge)

    return RedirectResponse(url=auth_url, status_code=302)



@router.get("/callback")
async def sso_callback(code: str, state: str, request: Request):
    """Handle OIDC callback."""
    # Validate state token (CSRF protection)
    state_data = state_manager.validate_state(state)
    if not state_data:
        raise HTTPException(status_code=400, detail="Invalid state")
    
    # Exchange authorization code for tokens (with PKCE verifier)
    callback_url = str(request.url_for("sso_callback"))
    tokens = await oidc_manager.provider.exchange_code_for_token(
        code, 
        state_data["code_verifier"], 
        callback_url
    )
    
    # Get user info from provider
    user_info = await oidc_manager.provider.get_user_info(tokens["access_token"])
    
    # Match or create user (email-based)
    user = await oidc_manager.match_or_create_user(user_info)

    # Check if user was found/created (JIT provisioning disabled or email not verified)
    if user is None:
        raise HTTPException(
            status_code=403,
            detail="User not authorized. Please contact administrator."
        )

    # Create session (same as password login)
    session_manager = get_session_manager()
    redirect_uri = state_data.get("redirect_uri", "/admin")
    redirect_response = RedirectResponse(url=redirect_uri, status_code=302)

    session_manager.create_session(
        redirect_response,
        username=user.username,
        role=user.role.value,
    )

    return redirect_response

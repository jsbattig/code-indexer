"""OIDC authentication routes for FastAPI."""

import os
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from ...web.auth import get_session_manager

router = APIRouter(prefix="/auth/sso", tags=["sso"])


# Global OIDC manager instance (injected by app.py)
oidc_manager = None


# Global state manager instance (injected by app.py)
state_manager = None


@router.get("/callback")
async def sso_callback(code: str, state: str, request: Request):
    """Handle OIDC callback."""
    # Validate state token (CSRF protection)
    # Try both state managers (oidc_routes and oauth_routes)
    state_data = state_manager.validate_state(state)
    if not state_data:
        # Try oauth state manager if available
        from code_indexer.server.auth import dependencies

        if hasattr(dependencies, "oidc_state_manager"):
            state_data = dependencies.oidc_state_manager.validate_state(state)

        if not state_data:
            raise HTTPException(status_code=400, detail="Invalid state")

    # Build callback URL using CIDX_ISSUER_URL if set (for reverse proxy scenarios)
    issuer_url = os.getenv("CIDX_ISSUER_URL")
    if issuer_url:
        callback_url = f"{issuer_url.rstrip('/')}/auth/sso/callback"
    else:
        callback_url = str(request.url_for("sso_callback"))

    # Use appropriate code_verifier based on flow type
    code_verifier = state_data.get("oidc_code_verifier") or state_data.get(
        "code_verifier"
    )

    tokens = await oidc_manager.provider.exchange_code_for_token(
        code, code_verifier, callback_url
    )

    # Get user info from provider
    user_info = await oidc_manager.provider.get_user_info(tokens["access_token"])

    # Match or create user (email-based)
    user = await oidc_manager.match_or_create_user(user_info)

    # Check if user was found/created (JIT provisioning disabled or email not verified)
    if user is None:
        raise HTTPException(
            status_code=403, detail="User not authorized. Please contact administrator."
        )

    # Check if this is OAuth authorization flow
    if state_data.get("flow") == "oauth_authorize":
        # This is OAuth flow - issue OAuth authorization code
        from code_indexer.server.auth.oauth.oauth_manager import OAuthManager
        from pathlib import Path

        oauth_db = Path.home() / ".cidx-server" / "oauth.db"
        oauth_manager = OAuthManager(db_path=str(oauth_db))

        # Generate OAuth authorization code
        oauth_code = oauth_manager.generate_authorization_code(
            client_id=state_data["client_id"],
            user_id=user.username,
            code_challenge=state_data["code_challenge"],
            redirect_uri=state_data["redirect_uri"],
            state=state_data["oauth_state"],
        )

        # Redirect back to OAuth client (Claude Code) with authorization code
        redirect_url = f"{state_data['redirect_uri']}?code={oauth_code}&state={state_data['oauth_state']}"
        return RedirectResponse(url=redirect_url, status_code=302)

    else:
        # This is unified login or admin UI flow - create session
        session_manager = get_session_manager()

        # Smart redirect logic (Phase 4: Login Consolidation)
        redirect_to = state_data.get("redirect_to")

        if redirect_to:
            # Explicit redirect_to from unified login or admin flow
            redirect_url = redirect_to
        elif user.role.value == "admin":
            # Admin user, no explicit redirect - go to admin dashboard
            redirect_url = "/admin/"
        else:
            # Non-admin user - go to user interface
            redirect_url = "/user/api-keys"

        redirect_response = RedirectResponse(url=redirect_url, status_code=302)

        session_manager.create_session(
            redirect_response,
            username=user.username,
            role=user.role.value,
        )

        return redirect_response

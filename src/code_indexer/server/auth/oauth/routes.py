"""FastAPI routes for OAuth 2.1 endpoints with rate limiting and audit logging.

CRITICAL WARNING - DO NOT MODIFY WITHOUT UNDERSTANDING:
==========================================================

This OAuth implementation is WORKING and TESTED with:
- Claude Code MCP integration (http transport)
- Claude Desktop (if configured)
- RFC 8414 OAuth 2.0 Authorization Server Metadata compliance

THINGS YOU MUST NOT DO:
------------------------
1. DO NOT add /mcp suffixes to discovery endpoints
   - The /.well-known/oauth-authorization-server endpoint is correct AS-IS
   - No /mcp suffix needed despite MCP protocol using /mcp SSE endpoint
   - MCP spec path-based discovery is for RESOURCE endpoints, not auth server

2. DO NOT create separate routers for .well-known endpoints
   - The router prefix="/oauth" is correct
   - FastAPI handles .well-known/* at root automatically
   - Creating a separate discovery_router will BREAK everything

3. DO NOT add /.well-known/oauth-protected-resource endpoints
   - MCP servers use WWW-Authenticate headers for resource metadata
   - Protected resource discovery happens via 401 responses, not .well-known
   - See src/code_indexer/server/auth/dependencies.py for WWW-Authenticate

4. DO NOT change the router prefix from "/oauth"
   - All OAuth endpoints (/register, /authorize, /token, /revoke) use this prefix
   - Discovery endpoint at /.well-known/* is handled correctly by FastAPI

WHY THIS WORKS:
---------------
- FastAPI serves /.well-known/* at domain root regardless of router prefix
- The /oauth prefix only affects non-.well-known routes
- MCP authentication uses standard OAuth 2.1, no special /mcp endpoints needed
- GET /mcp returns 401 with WWW-Authenticate pointing to this discovery endpoint

IF YOU THINK SOMETHING IS BROKEN:
----------------------------------
1. Test with: curl https://linner.ddns.net:8383/.well-known/oauth-authorization-server
2. Should return OAuth metadata JSON with issuer, endpoints, etc.
3. If working, DO NOT CHANGE ANYTHING
4. If broken, check server logs first, don't modify code blindly

VERIFIED WORKING:
-----------------
- Date: 2025-11-18
- Commit: 6bda63f
- Test: Claude Code MCP authentication successful
- DO NOT BREAK THIS AGAIN
"""

from fastapi import APIRouter, HTTPException, status, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import base64

from .oauth_manager import OAuthManager, OAuthError, PKCEVerificationError
from ..user_manager import UserManager
from ..mcp_credential_manager import MCPCredentialManager
from ..audit_logger import password_audit_logger
from ..oauth_rate_limiter import oauth_token_rate_limiter, oauth_register_rate_limiter


router = APIRouter(prefix="/oauth", tags=["oauth"])


# Initialize OAuth manager (singleton pattern)
def get_oauth_manager() -> OAuthManager:
    """Get OAuth manager instance."""
    oauth_db = Path.home() / ".cidx-server" / "oauth.db"
    return OAuthManager(db_path=str(oauth_db), issuer=None)


def get_user_manager() -> UserManager:
    return UserManager()


def get_mcp_credential_manager() -> MCPCredentialManager:
    """Get MCPCredentialManager instance with UserManager injected."""
    user_manager = get_user_manager()
    return MCPCredentialManager(user_manager=user_manager)


# Pydantic models for request/response
class ClientRegistrationRequest(BaseModel):
    client_name: str
    redirect_uris: List[str]
    grant_types: Optional[List[str]] = ["authorization_code", "refresh_token"]
    response_types: Optional[List[str]] = ["code"]
    token_endpoint_auth_method: Optional[str] = "none"
    scope: Optional[str] = None


class ClientRegistrationResponse(BaseModel):
    client_id: str
    client_name: str
    redirect_uris: List[str]
    client_secret_expires_at: int
    token_endpoint_auth_method: str
    grant_types: Optional[List[str]] = None
    response_types: Optional[List[str]] = None


class AuthorizeRequest(BaseModel):
    client_id: str
    redirect_uri: str
    response_type: str  # must be 'code'
    code_challenge: str  # PKCE required
    state: str
    username: str  # for authentication
    password: str  # for authentication


class TokenRequest(BaseModel):
    grant_type: str
    code: Optional[str] = None
    code_verifier: Optional[str] = None
    client_id: str
    refresh_token: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: Optional[str] = None


class RevokeRequest(BaseModel):
    token: str
    token_type_hint: Optional[str] = None  # 'access_token' or 'refresh_token'


@router.get("/.well-known/oauth-authorization-server")
async def discovery_endpoint(manager: OAuthManager = Depends(get_oauth_manager)):
    """OAuth 2.1 discovery endpoint."""
    return manager.get_discovery_metadata()


@router.post(
    "/register",
    response_model=ClientRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_client(
    request_model: ClientRegistrationRequest,
    http_request: Request,
    manager: OAuthManager = Depends(get_oauth_manager),
):
    """Dynamic client registration endpoint with rate limiting and audit logging."""
    ip_address = http_request.client.host if http_request.client else "unknown"
    user_agent = http_request.headers.get("user-agent")

    # Rate limit check
    rate_limit_error = oauth_register_rate_limiter.check_rate_limit(ip_address)
    if rate_limit_error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=rate_limit_error
        )

    try:
        result = manager.register_client(
            client_name=request_model.client_name,
            redirect_uris=request_model.redirect_uris,
            grant_types=request_model.grant_types,
            response_types=request_model.response_types,
            token_endpoint_auth_method=request_model.token_endpoint_auth_method,
            scope=request_model.scope,
        )

        # Record success
        oauth_register_rate_limiter.record_successful_attempt(ip_address)

        # Audit log
        password_audit_logger.log_oauth_client_registration(
            client_id=result["client_id"],
            client_name=result["client_name"],
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return result
    except Exception as e:
        # Record failure
        oauth_register_rate_limiter.record_failed_attempt(ip_address)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/authorize", response_class=HTMLResponse)
async def get_authorize_form(
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    response_type: str,
    state: str,
    manager: OAuthManager = Depends(get_oauth_manager),
    request: Request = None,
):
    """GET /oauth/authorize - OAuth authorization endpoint (Phase 5: Login Consolidation).

    Separates authentication from authorization per OAuth 2.1 best practices:
    1. Check for existing session
    2. If authenticated → show consent screen (authorization)
    3. If not authenticated → redirect to unified /login (authentication)

    Per OAuth 2.1 spec: Validates client_id exists. If invalid, returns HTTP 401
    with error="invalid_client" to trigger Claude.ai re-registration.
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

    # Check for existing session (Phase 5: Separate authentication from authorization)
    from code_indexer.server.web import get_session_manager

    session_manager = get_session_manager()
    session = session_manager.get_session(request)

    if not session:
        # Not authenticated - redirect to unified login
        from urllib.parse import urlencode, quote

        # Preserve OAuth parameters in redirect_to
        oauth_params = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                "response_type": response_type,
                "state": state,
            }
        )
        oauth_authorize_url = f"/oauth/authorize?{oauth_params}"

        # Redirect to unified login with OAuth authorize URL as redirect_to
        redirect_url = f"/login?redirect_to={quote(oauth_authorize_url)}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    # Authenticated - show consent screen (Phase 5: Separate authorization from authentication)
    from code_indexer.server.web.routes import templates

    return templates.TemplateResponse(
        "oauth_authorize_consent.html",
        {
            "request": request,
            "username": session.username,
            "client_id": client_id,
            "client_name": client.get("client_name", "Unknown Application"),
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "response_type": response_type,
            "state": state,
        },
    )


@router.post("/authorize/consent")
async def authorize_consent(
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    code_challenge: str = Form(...),
    response_type: str = Form(...),
    state: str = Form(...),
    consent: str = Form(...),
    request: Request = None,
    manager: OAuthManager = Depends(get_oauth_manager),
):
    """POST /oauth/authorize/consent - Handle consent form submission (Phase 5: Login Consolidation).

    User is already authenticated via unified login. This endpoint only handles authorization (consent).
    Generates OAuth authorization code and redirects back to client.
    """
    # Check for existing session (required)
    from code_indexer.server.web import get_session_manager

    session_manager = get_session_manager()
    session = session_manager.get_session(request)

    if not session:
        # Not authenticated - redirect to unified login
        from urllib.parse import urlencode, quote

        oauth_params = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                "response_type": response_type,
                "state": state,
            }
        )
        oauth_authorize_url = f"/oauth/authorize?{oauth_params}"
        redirect_url = f"/login?redirect_to={quote(oauth_authorize_url)}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    # Validate response_type
    if response_type != "code":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid response_type. Must be 'code'",
        )

    # Validate PKCE
    if not code_challenge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code_challenge required (PKCE)",
        )

    # Check consent
    if consent != "allow":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User denied consent"
        )

    try:
        # Generate authorization code (user already authenticated via session)
        code = manager.generate_authorization_code(
            client_id=client_id,
            user_id=session.username,
            code_challenge=code_challenge,
            redirect_uri=redirect_uri,
            state=state,
        )

        # Audit log
        ip_address = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent")
        password_audit_logger.log_oauth_authorization(
            username=session.username,
            client_id=client_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Redirect back to client with authorization code
        redirect_url = f"{redirect_uri}?code={code}&state={state}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)

    except OAuthError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/authorize/sso")
async def oauth_authorize_via_sso(
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    response_type: str,
    state: str,
    manager: OAuthManager = Depends(get_oauth_manager),
):
    """Initiate OIDC flow for OAuth authorization.

    Preserves OAuth parameters through OIDC authentication flow.
    After OIDC completes, issues OAuth authorization code and redirects
    back to OAuth client (Claude Code).
    """
    from code_indexer.server.auth.oidc import routes as oidc_routes
    from code_indexer.server.auth import dependencies

    # Check if OIDC is enabled
    if not oidc_routes.oidc_manager or not oidc_routes.oidc_manager.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO authentication not configured",
        )

    # Lazily initialize OIDC provider (discovers metadata)
    try:
        await oidc_routes.oidc_manager.ensure_provider_initialized()
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to initialize OIDC provider: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SSO provider is currently unavailable. Please try again later or contact administrator.",
        )

    # Validate OAuth parameters
    if response_type != "code":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid response_type. Must be 'code'",
        )

    # Validate client_id exists
    client = manager.get_client(client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_client",
                "error_description": "Client ID not found",
            },
        )

    # Validate redirect_uri
    if redirect_uri not in client["redirect_uris"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid redirect_uri"
        )

    # Validate PKCE
    if not code_challenge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code_challenge required (PKCE)",
        )

    # Get or create OIDC state manager singleton
    from code_indexer.server.auth.oidc.state_manager import StateManager

    if not hasattr(dependencies, "oidc_state_manager"):
        dependencies.oidc_state_manager = StateManager()

    state_manager = dependencies.oidc_state_manager

    # Create OIDC state containing OAuth parameters
    oauth_state_data = {
        "flow": "oauth_authorize",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "oauth_state": state,  # Preserve OAuth client's state
    }

    oidc_state = state_manager.create_state(oauth_state_data)

    # Build OIDC authorization URL
    oidc_provider = oidc_routes.oidc_manager.provider

    # Get callback URL (hardcoded to /auth/sso/callback)
    callback_url = f"{manager.issuer}/auth/sso/callback"

    # Generate PKCE for OIDC flow
    import secrets
    import hashlib
    import base64

    code_verifier = secrets.token_urlsafe(32)
    code_challenge_oidc = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )

    # Store code_verifier in state for callback
    oauth_state_data["oidc_code_verifier"] = code_verifier
    dependencies.oidc_state_manager.update_state_data(oidc_state, oauth_state_data)

    # Build OIDC authorization URL
    auth_url = oidc_provider.get_authorization_url(
        state=oidc_state, redirect_uri=callback_url, code_challenge=code_challenge_oidc
    )

    return RedirectResponse(url=auth_url)


@router.post("/authorize")
async def authorize_endpoint(
    http_request: Request,
    manager: OAuthManager = Depends(get_oauth_manager),
    user_manager: UserManager = Depends(get_user_manager),
    # Form parameters (for browser-based flow)
    client_id: Optional[str] = Form(None),
    redirect_uri: Optional[str] = Form(None),
    response_type: Optional[str] = Form(None),
    code_challenge: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    username: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
):
    """OAuth authorization endpoint with user authentication.

    Supports both:
    - Form data (application/x-www-form-urlencoded) for browser-based flows - returns redirect
    - JSON body for programmatic access - returns JSON response
    """
    ip_address = http_request.client.host if http_request.client else "unknown"
    user_agent = http_request.headers.get("user-agent")

    # Determine if this is Form data or JSON request
    content_type = http_request.headers.get("content-type", "")
    is_form_request = "application/x-www-form-urlencoded" in content_type

    # Handle JSON request (backward compatibility)
    if not is_form_request and client_id is None:
        # Parse JSON body
        try:
            body = await http_request.json()
            request_model = AuthorizeRequest(**body)
            client_id = request_model.client_id
            redirect_uri = request_model.redirect_uri
            response_type = request_model.response_type
            code_challenge = request_model.code_challenge
            state = request_model.state
            username = request_model.username
            password = request_model.password
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request body"
            )

    # Validate response_type
    if response_type != "code":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid response_type. Must be 'code'",
        )

    # Validate PKCE
    if not code_challenge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code_challenge required (PKCE)",
        )

    # Authenticate user
    user = user_manager.authenticate_user(username, password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    try:
        # Generate authorization code
        code = manager.generate_authorization_code(
            client_id=client_id,
            user_id=user.username,
            code_challenge=code_challenge,
            redirect_uri=redirect_uri,
            state=state,
        )

        # Audit log
        password_audit_logger.log_oauth_authorization(
            username=user.username,
            client_id=client_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Return redirect for Form requests, JSON for API requests
        if is_form_request:
            # Browser-based flow: redirect to callback URL with code and state
            redirect_url = f"{redirect_uri}?code={code}&state={state}"
            return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
        else:
            # Programmatic flow: return JSON response
            return {"code": code, "state": state}

    except OAuthError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/token", response_model=TokenResponse)
async def token_endpoint(
    grant_type: str = Form(...),
    code: Optional[str] = Form(None),
    code_verifier: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    client_secret: Optional[str] = Form(None),
    refresh_token: Optional[str] = Form(None),
    http_request: Request = None,
    manager: OAuthManager = Depends(get_oauth_manager),
    mcp_credential_manager: MCPCredentialManager = Depends(get_mcp_credential_manager),
):
    """Token endpoint for authorization code exchange with rate limiting and audit logging.

    OAuth 2.1 compliant - accepts application/x-www-form-urlencoded data.
    Supports grant types: authorization_code, refresh_token, client_credentials.
    """
    ip_address = http_request.client.host if http_request.client else "unknown"
    user_agent = http_request.headers.get("user-agent")

    # Extract client credentials from Authorization header (Basic Auth) if present
    auth_header = http_request.headers.get("authorization", "")
    if auth_header.startswith("Basic ") and grant_type == "client_credentials":
        try:
            # Decode Basic Auth: "Basic base64(client_id:client_secret)"
            encoded_credentials = auth_header[6:]  # Remove "Basic " prefix
            decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
            client_id, client_secret = decoded_credentials.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Authorization header format",
            )

    # Validate client_id for rate limiting (required for all grant types)
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="client_id required",
        )

    # Rate limit check
    rate_limit_error = oauth_token_rate_limiter.check_rate_limit(client_id)
    if rate_limit_error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=rate_limit_error
        )

    try:
        if grant_type == "authorization_code":
            if not code or not code_verifier:
                oauth_token_rate_limiter.record_failed_attempt(client_id)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="code and code_verifier required for authorization_code grant",
                )

            result = manager.exchange_code_for_token(
                code=code, code_verifier=code_verifier, client_id=client_id
            )

            # Record success
            oauth_token_rate_limiter.record_successful_attempt(client_id)

            # Audit log (extract username from token validation)
            token_info = manager.validate_token(result["access_token"])
            if token_info:
                password_audit_logger.log_oauth_token_exchange(
                    username=token_info["user_id"],
                    client_id=client_id,
                    grant_type="authorization_code",
                    ip_address=ip_address,
                    user_agent=user_agent,
                )

            return result

        elif grant_type == "refresh_token":
            if not refresh_token:
                oauth_token_rate_limiter.record_failed_attempt(client_id)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="refresh_token required for refresh_token grant",
                )

            result = manager.refresh_access_token(
                refresh_token=refresh_token, client_id=client_id
            )

            # Record success
            oauth_token_rate_limiter.record_successful_attempt(client_id)

            # Audit log
            token_info = manager.validate_token(result["access_token"])
            if token_info:
                password_audit_logger.log_oauth_token_exchange(
                    username=token_info["user_id"],
                    client_id=client_id,
                    grant_type="refresh_token",
                    ip_address=ip_address,
                    user_agent=user_agent,
                )

            return result

        elif grant_type == "client_credentials":
            if not client_secret:
                oauth_token_rate_limiter.record_failed_attempt(client_id)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="client_secret required for client_credentials grant",
                )

            result = manager.handle_client_credentials_grant(
                client_id=client_id,
                client_secret=client_secret,
                scope=None,
                mcp_credential_manager=mcp_credential_manager,
            )

            # Record success
            oauth_token_rate_limiter.record_successful_attempt(client_id)

            # Audit log
            token_info = manager.validate_token(result["access_token"])
            if token_info:
                password_audit_logger.log_oauth_token_exchange(
                    username=token_info["user_id"],
                    client_id=client_id,
                    grant_type="client_credentials",
                    ip_address=ip_address,
                    user_agent=user_agent,
                )

            return result

        else:
            oauth_token_rate_limiter.record_failed_attempt(client_id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported grant_type: {grant_type}",
            )
    except PKCEVerificationError as e:
        oauth_token_rate_limiter.record_failed_attempt(client_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_grant", "error_description": str(e)},
        )
    except OAuthError as e:
        oauth_token_rate_limiter.record_failed_attempt(client_id)
        # Return 401 for invalid credentials in client_credentials grant
        if grant_type == "client_credentials" and "Invalid client credentials" in str(
            e
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "invalid_client", "error_description": str(e)},
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_request", "error_description": str(e)},
        )


@router.post("/revoke")
async def revoke_endpoint(
    request_model: RevokeRequest,
    http_request: Request,
    manager: OAuthManager = Depends(get_oauth_manager),
):
    """Token revocation endpoint (always returns 200 per OAuth 2.1 spec)."""
    ip_address = http_request.client.host if http_request.client else "unknown"
    user_agent = http_request.headers.get("user-agent")

    # Revoke token
    result = manager.revoke_token(request_model.token, request_model.token_type_hint)

    # Audit log if token was found
    if result["username"]:
        password_audit_logger.log_oauth_token_revocation(
            username=result["username"],
            token_type=result["token_type"],
            ip_address=ip_address,
            user_agent=user_agent,
        )

    # Always return 200 (don't reveal if token existed)
    return {"status": "ok"}

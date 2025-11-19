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

from .oauth_manager import OAuthManager, OAuthError, PKCEVerificationError
from ..user_manager import UserManager
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


# Pydantic models for request/response
class ClientRegistrationRequest(BaseModel):
    client_name: str
    redirect_uris: List[str]
    grant_types: Optional[List[str]] = ["authorization_code", "refresh_token"]


class ClientRegistrationResponse(BaseModel):
    client_id: str
    client_name: str
    redirect_uris: List[str]
    client_secret_expires_at: int


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


@router.post("/register", response_model=ClientRegistrationResponse)
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
):
    """GET /oauth/authorize - Returns HTML login form for browser-based OAuth flow.

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

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CIDX Authorization</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
               background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
               display: flex; justify-content: center; align-items: center;
               min-height: 100vh; margin: 0; }}
        .container {{ background: white; padding: 40px; border-radius: 10px;
                      box-shadow: 0 10px 40px rgba(0,0,0,0.2); max-width: 400px; width: 100%; }}
        h2 {{ margin: 0 0 10px 0; color: #333; }}
        p {{ color: #666; margin: 0 0 30px 0; font-size: 14px; }}
        input {{ width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #ddd;
                 border-radius: 5px; box-sizing: border-box; font-size: 14px; }}
        input:focus {{ outline: none; border-color: #667eea; }}
        button {{ width: 100%; padding: 14px; background: #667eea; color: white;
                  border: none; border-radius: 5px; font-size: 16px; font-weight: 600;
                  cursor: pointer; margin-top: 10px; }}
        button:hover {{ background: #5568d3; }}
        .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #999; }}
    </style>
</head>
<body>
    <div class="container">
        <h2>CIDX Authorization</h2>
        <p>CIDX Server is requesting access to your account</p>
        <form method="post" action="/oauth/authorize">
            <input type="hidden" name="client_id" value="{client_id}">
            <input type="hidden" name="redirect_uri" value="{redirect_uri}">
            <input type="hidden" name="code_challenge" value="{code_challenge}">
            <input type="hidden" name="response_type" value="{response_type}">
            <input type="hidden" name="state" value="{state}">
            <input type="text" name="username" placeholder="Username" required autofocus>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Authorize Access</button>
        </form>
        <div class="footer">CIDX Semantic Code Search</div>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html)


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
    client_id: str = Form(...),
    refresh_token: Optional[str] = Form(None),
    http_request: Request = None,
    manager: OAuthManager = Depends(get_oauth_manager),
):
    """Token endpoint for authorization code exchange with rate limiting and audit logging.

    OAuth 2.1 compliant - accepts application/x-www-form-urlencoded data.
    """
    ip_address = http_request.client.host if http_request.client else "unknown"
    user_agent = http_request.headers.get("user-agent")

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

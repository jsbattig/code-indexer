"""FastAPI routes for OAuth 2.1 endpoints with rate limiting and audit logging."""

from fastapi import APIRouter, HTTPException, status, Depends, Request
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
    return OAuthManager(db_path=str(oauth_db), issuer="http://localhost:8000")


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
    manager: OAuthManager = Depends(get_oauth_manager)
):
    """Dynamic client registration endpoint with rate limiting and audit logging."""
    ip_address = http_request.client.host if http_request.client else "unknown"
    user_agent = http_request.headers.get("user-agent")

    # Rate limit check
    rate_limit_error = oauth_register_rate_limiter.check_rate_limit(ip_address)
    if rate_limit_error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=rate_limit_error
        )

    try:
        result = manager.register_client(
            client_name=request_model.client_name,
            redirect_uris=request_model.redirect_uris
        )

        # Record success
        oauth_register_rate_limiter.record_successful_attempt(ip_address)

        # Audit log
        password_audit_logger.log_oauth_client_registration(
            client_id=result["client_id"],
            client_name=result["client_name"],
            ip_address=ip_address,
            user_agent=user_agent
        )

        return result
    except Exception as e:
        # Record failure
        oauth_register_rate_limiter.record_failed_attempt(ip_address)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/authorize")
async def authorize_endpoint(
    request_model: AuthorizeRequest,
    http_request: Request,
    manager: OAuthManager = Depends(get_oauth_manager),
    user_manager: UserManager = Depends(get_user_manager)
):
    """OAuth authorization endpoint with user authentication."""
    ip_address = http_request.client.host if http_request.client else "unknown"
    user_agent = http_request.headers.get("user-agent")

    # Validate response_type
    if request_model.response_type != "code":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid response_type. Must be 'code'"
        )

    # Validate PKCE
    if not request_model.code_challenge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code_challenge required (PKCE)"
        )

    # Authenticate user
    user = user_manager.authenticate_user(request_model.username, request_model.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    try:
        # Generate authorization code
        code = manager.generate_authorization_code(
            client_id=request_model.client_id,
            user_id=user.username,
            code_challenge=request_model.code_challenge,
            redirect_uri=request_model.redirect_uri,
            state=request_model.state
        )

        # Audit log
        password_audit_logger.log_oauth_authorization(
            username=user.username,
            client_id=request_model.client_id,
            ip_address=ip_address,
            user_agent=user_agent
        )

        return {"code": code, "state": request_model.state}

    except OAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/token", response_model=TokenResponse)
async def token_endpoint(
    request_model: TokenRequest,
    http_request: Request,
    manager: OAuthManager = Depends(get_oauth_manager)
):
    """Token endpoint for authorization code exchange with rate limiting and audit logging."""
    ip_address = http_request.client.host if http_request.client else "unknown"
    user_agent = http_request.headers.get("user-agent")
    client_id = request_model.client_id

    # Rate limit check
    rate_limit_error = oauth_token_rate_limiter.check_rate_limit(client_id)
    if rate_limit_error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=rate_limit_error
        )

    try:
        if request_model.grant_type == "authorization_code":
            if not request_model.code or not request_model.code_verifier:
                oauth_token_rate_limiter.record_failed_attempt(client_id)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="code and code_verifier required for authorization_code grant"
                )

            result = manager.exchange_code_for_token(
                code=request_model.code,
                code_verifier=request_model.code_verifier,
                client_id=client_id
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
                    user_agent=user_agent
                )

            return result

        elif request_model.grant_type == "refresh_token":
            if not request_model.refresh_token:
                oauth_token_rate_limiter.record_failed_attempt(client_id)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="refresh_token required for refresh_token grant"
                )

            result = manager.refresh_access_token(
                refresh_token=request_model.refresh_token,
                client_id=client_id
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
                    user_agent=user_agent
                )

            return result
        else:
            oauth_token_rate_limiter.record_failed_attempt(client_id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported grant_type: {request_model.grant_type}"
            )
    except PKCEVerificationError as e:
        oauth_token_rate_limiter.record_failed_attempt(client_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_grant", "error_description": str(e)}
        )
    except OAuthError as e:
        oauth_token_rate_limiter.record_failed_attempt(client_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_request", "error_description": str(e)}
        )


@router.post("/revoke")
async def revoke_endpoint(
    request_model: RevokeRequest,
    http_request: Request,
    manager: OAuthManager = Depends(get_oauth_manager)
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
            user_agent=user_agent
        )

    # Always return 200 (don't reveal if token existed)
    return {"status": "ok"}

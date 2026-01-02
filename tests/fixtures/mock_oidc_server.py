"""Lightweight mock OIDC server for integration testing."""

import asyncio
import threading
from typing import Optional
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse


class MockOIDCServer:
    """Lightweight mock OIDC/OAuth2 server for testing.

    Implements minimal OIDC endpoints:
    - /.well-known/openid-configuration (discovery)
    - /authorize (authorization endpoint)
    - /token (token endpoint)
    - /userinfo (userinfo endpoint)
    """

    def __init__(self, port: int = 8888, host: str = "127.0.0.1"):
        self.port = port
        self.host = host
        self.base_url = f"http://{host}:{port}"
        self.app = FastAPI()
        self.server: Optional[uvicorn.Server] = None
        self.thread: Optional[threading.Thread] = None

        # Configurable responses for testing
        self.userinfo_response = {
            "sub": "test-user-123",
            "email": "test@example.com",
            "email_verified": True,
            "preferred_username": "testuser",  # Default username
        }

        self.token_response = {
            "access_token": "mock-access-token-12345",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        self._setup_routes()

    def _setup_routes(self):
        """Setup OIDC endpoint routes."""

        @self.app.get("/.well-known/openid-configuration")
        async def discovery():
            """OIDC discovery endpoint."""
            return JSONResponse(
                {
                    "issuer": self.base_url,
                    "authorization_endpoint": f"{self.base_url}/authorize",
                    "token_endpoint": f"{self.base_url}/token",
                    "userinfo_endpoint": f"{self.base_url}/userinfo",
                    "jwks_uri": f"{self.base_url}/jwks",
                    "response_types_supported": ["code"],
                    "subject_types_supported": ["public"],
                    "id_token_signing_alg_values_supported": ["RS256"],
                }
            )

        @self.app.get("/authorize")
        async def authorize(
            client_id: str,
            redirect_uri: str,
            state: str,
            response_type: str,
            scope: str,
            code_challenge: Optional[str] = None,
            code_challenge_method: Optional[str] = None,
        ):
            """Authorization endpoint - simulates user login and consent."""
            # In real OIDC, this would show login page
            # For testing, we immediately redirect back with auth code
            callback_url = f"{redirect_uri}?code=mock-auth-code-12345&state={state}"
            return RedirectResponse(url=callback_url)

        @self.app.post("/token")
        async def token(request: Request):
            """Token endpoint - exchanges auth code for tokens."""
            form_data = await request.form()

            # Validate required parameters exist
            if form_data.get("grant_type") != "authorization_code":
                return JSONResponse(
                    {"error": "unsupported_grant_type"}, status_code=400
                )

            if not form_data.get("code"):
                return JSONResponse(
                    {"error": "invalid_request", "error_description": "Missing code"},
                    status_code=400,
                )

            # Return token response
            return JSONResponse(self.token_response)

        @self.app.get("/userinfo")
        async def userinfo(request: Request):
            """Userinfo endpoint - returns user claims."""
            # Check for Authorization header
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return JSONResponse({"error": "invalid_token"}, status_code=401)

            # Return user info
            return JSONResponse(self.userinfo_response)

    def start(self):
        """Start the mock OIDC server in a background thread."""
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="error",  # Quiet logs during tests
        )
        self.server = uvicorn.Server(config)

        def run_server():
            asyncio.run(self.server.serve())

        self.thread = threading.Thread(target=run_server, daemon=True)
        self.thread.start()

        # Wait for server to be ready
        import time

        time.sleep(0.5)

    def stop(self):
        """Stop the mock OIDC server."""
        if self.server:
            self.server.should_exit = True
        if self.thread:
            self.thread.join(timeout=2.0)

    def set_userinfo(
        self,
        sub: str,
        email: Optional[str] = None,
        email_verified: bool = False,
        preferred_username: Optional[str] = None,
    ):
        """Configure userinfo response for testing."""
        self.userinfo_response = {
            "sub": sub,
            "email": email,
            "email_verified": email_verified,
        }

        # Add preferred_username if provided (or derive from email)
        if preferred_username:
            self.userinfo_response["preferred_username"] = preferred_username
        elif email:
            # Default: use email prefix as username
            self.userinfo_response["preferred_username"] = email.split("@")[0]

    def set_token(self, access_token: str):
        """Configure token response for testing."""
        self.token_response["access_token"] = access_token

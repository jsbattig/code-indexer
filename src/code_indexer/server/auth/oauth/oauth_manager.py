"""OAuth 2.1 Manager - Complete implementation following refresh_token_manager.py patterns."""

import os
import sqlite3
import secrets
import hashlib
import base64
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, TYPE_CHECKING
import json

if TYPE_CHECKING:
    from ..user_manager import UserManager
    from ..audit_logger import PasswordChangeAuditLogger


class OAuthError(Exception):
    pass


class PKCEVerificationError(OAuthError):
    pass


class OAuthManager:
    ACCESS_TOKEN_LIFETIME_HOURS = 8
    REFRESH_TOKEN_LIFETIME_DAYS = 30
    HARD_EXPIRATION_DAYS = 30
    EXTENSION_THRESHOLD_HOURS = 4

    def __init__(
        self,
        db_path: Optional[str] = None,
        issuer: Optional[str] = None,
        user_manager: Optional["UserManager"] = None,
        audit_logger: Optional["PasswordChangeAuditLogger"] = None,
    ):
        self.issuer = issuer or os.getenv("CIDX_ISSUER_URL", "http://localhost:8000")
        if db_path:
            self.db_path = Path(db_path)
        else:
            server_dir = Path.home() / ".cidx-server"
            server_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = server_dir / "oauth.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_clients (
                    client_id TEXT PRIMARY KEY,
                    client_name TEXT NOT NULL,
                    redirect_uris TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT
                )
            """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_codes (
                    code TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    code_challenge TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used INTEGER DEFAULT 0,
                    FOREIGN KEY (client_id) REFERENCES oauth_clients (client_id)
                )
            """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_tokens (
                    token_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    access_token TEXT UNIQUE NOT NULL,
                    refresh_token TEXT UNIQUE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_activity TEXT NOT NULL,
                    hard_expires_at TEXT NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES oauth_clients (client_id)
                )
            """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tokens_access ON oauth_tokens (access_token)"
            )
            conn.commit()

    def get_discovery_metadata(self) -> Dict[str, Any]:
        return {
            "authorization_endpoint": f"{self.issuer}/oauth/authorize",
            "token_endpoint": f"{self.issuer}/oauth/token",
            "registration_endpoint": f"{self.issuer}/oauth/register",
        }

    def register_client(
        self,
        client_name: str,
        redirect_uris: List[str],
        grant_types: Optional[List[str]] = None,
        response_types: Optional[List[str]] = None,
        token_endpoint_auth_method: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not client_name or client_name.strip() == "":
            raise OAuthError("client_name cannot be empty")
        client_id = secrets.token_urlsafe(32)
        created_at = datetime.now(timezone.utc).isoformat()
        metadata = {
            "token_endpoint_auth_method": token_endpoint_auth_method or "none",
            "grant_types": grant_types or ["authorization_code", "refresh_token"],
            "response_types": response_types or ["code"],
            "scope": scope,
        }
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute(
                "INSERT INTO oauth_clients (client_id, client_name, redirect_uris, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
                (client_id, client_name, json.dumps(redirect_uris), created_at, json.dumps(metadata)),
            )
            conn.commit()
        return {
            "client_id": client_id,
            "client_name": client_name,
            "redirect_uris": redirect_uris,
            "client_secret_expires_at": 0,
            "token_endpoint_auth_method": token_endpoint_auth_method or "none",
            "grant_types": grant_types or ["authorization_code", "refresh_token"],
            "response_types": response_types or ["code"],
        }

    def get_client(self, client_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM oauth_clients WHERE client_id = ?", (client_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "client_id": row["client_id"],
                    "client_name": row["client_name"],
                    "redirect_uris": json.loads(row["redirect_uris"]),
                    "created_at": row["created_at"],
                }
            return None

    def generate_authorization_code(
        self,
        client_id: str,
        user_id: str,
        code_challenge: str,
        redirect_uri: str,
        state: str,
    ) -> str:
        # Validate PKCE challenge
        if not code_challenge or code_challenge.strip() == "":
            raise OAuthError("code_challenge required")

        client = self.get_client(client_id)
        if not client:
            raise OAuthError(f"Invalid client_id: {client_id}")
        if redirect_uri not in client["redirect_uris"]:
            raise OAuthError(f"Invalid redirect_uri: {redirect_uri}")
        code = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute(
                "INSERT INTO oauth_codes (code, client_id, user_id, code_challenge, redirect_uri, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    code,
                    client_id,
                    user_id,
                    code_challenge,
                    redirect_uri,
                    expires_at.isoformat(),
                ),
            )
            conn.commit()
        return code

    def exchange_code_for_token(
        self, code: str, code_verifier: str, client_id: str
    ) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM oauth_codes WHERE code = ? AND client_id = ?",
                (code, client_id),
            )
            code_row = cursor.fetchone()
            if not code_row:
                raise OAuthError("Invalid authorization code")
            if code_row["used"]:
                raise OAuthError("Authorization code already used")
            expires_at = datetime.fromisoformat(code_row["expires_at"])
            if datetime.now(timezone.utc) > expires_at:
                raise OAuthError("Authorization code expired")

            # PKCE verification
            code_challenge = code_row["code_challenge"]
            computed_challenge = (
                base64.urlsafe_b64encode(
                    hashlib.sha256(code_verifier.encode()).digest()
                )
                .decode()
                .rstrip("=")
            )
            if computed_challenge != code_challenge:
                raise PKCEVerificationError("PKCE verification failed")

            conn.execute("UPDATE oauth_codes SET used = 1 WHERE code = ?", (code,))

            token_id = secrets.token_urlsafe(32)
            access_token = secrets.token_urlsafe(48)
            refresh_token = secrets.token_urlsafe(48)
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(hours=self.ACCESS_TOKEN_LIFETIME_HOURS)
            hard_expires_at = now + timedelta(days=self.HARD_EXPIRATION_DAYS)

            conn.execute(
                """INSERT INTO oauth_tokens (token_id, client_id, user_id, access_token, refresh_token,
                   expires_at, created_at, last_activity, hard_expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    token_id,
                    code_row["client_id"],
                    code_row["user_id"],
                    access_token,
                    refresh_token,
                    expires_at.isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                    hard_expires_at.isoformat(),
                ),
            )
            conn.commit()

            return {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": int(self.ACCESS_TOKEN_LIFETIME_HOURS * 3600),
                "refresh_token": refresh_token,
            }

    def validate_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM oauth_tokens WHERE access_token = ?", (access_token,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            expires_at = datetime.fromisoformat(row["expires_at"])
            if datetime.now(timezone.utc) > expires_at:
                return None
            return {
                "token_id": row["token_id"],
                "client_id": row["client_id"],
                "user_id": row["user_id"],
                "expires_at": row["expires_at"],
                "created_at": row["created_at"],
            }

    def extend_token_on_activity(self, access_token: str) -> bool:
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM oauth_tokens WHERE access_token = ?", (access_token,)
            )
            row = cursor.fetchone()
            if not row:
                return False
            now = datetime.now(timezone.utc)
            expires_at = datetime.fromisoformat(row["expires_at"])
            hard_expires_at = datetime.fromisoformat(row["hard_expires_at"])
            remaining = (expires_at - now).total_seconds() / 3600
            if remaining >= self.EXTENSION_THRESHOLD_HOURS:
                return False
            new_expires_at = now + timedelta(hours=self.ACCESS_TOKEN_LIFETIME_HOURS)
            if new_expires_at > hard_expires_at:
                new_expires_at = hard_expires_at
            conn.execute(
                "UPDATE oauth_tokens SET expires_at = ?, last_activity = ? WHERE access_token = ?",
                (new_expires_at.isoformat(), now.isoformat(), access_token),
            )
            conn.commit()
            return True

    def refresh_access_token(
        self, refresh_token: str, client_id: str
    ) -> Dict[str, Any]:
        """Exchange refresh token for new access and refresh tokens."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM oauth_tokens WHERE refresh_token = ?", (refresh_token,)
            )
            row = cursor.fetchone()

            if not row:
                raise OAuthError("Invalid refresh token")

            # Generate new tokens
            new_access_token = secrets.token_urlsafe(48)
            new_refresh_token = secrets.token_urlsafe(48)
            now = datetime.now(timezone.utc)
            new_expires_at = now + timedelta(hours=self.ACCESS_TOKEN_LIFETIME_HOURS)

            # Update tokens
            conn.execute(
                """UPDATE oauth_tokens
                   SET access_token = ?, refresh_token = ?, expires_at = ?, last_activity = ?
                   WHERE refresh_token = ?""",
                (
                    new_access_token,
                    new_refresh_token,
                    new_expires_at.isoformat(),
                    now.isoformat(),
                    refresh_token,
                ),
            )
            conn.commit()

            return {
                "access_token": new_access_token,
                "token_type": "Bearer",
                "expires_in": int(self.ACCESS_TOKEN_LIFETIME_HOURS * 3600),
                "refresh_token": new_refresh_token,
            }

    def revoke_token(
        self, token: str, token_type_hint: Optional[str] = None
    ) -> Dict[str, Optional[str]]:
        """
        Revoke an access or refresh token.

        Args:
            token: The token to revoke
            token_type_hint: Optional hint about token type ('access_token' or 'refresh_token')

        Returns:
            Dictionary with username and token_type if found, None values if not found.
            Per OAuth 2.1 spec, endpoint should return 200 either way.
        """
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.row_factory = sqlite3.Row

            # Find token
            if token_type_hint == "access_token":
                cursor = conn.execute(
                    "SELECT * FROM oauth_tokens WHERE access_token = ?", (token,)
                )
            elif token_type_hint == "refresh_token":
                cursor = conn.execute(
                    "SELECT * FROM oauth_tokens WHERE refresh_token = ?", (token,)
                )
            else:
                # Try both
                cursor = conn.execute(
                    "SELECT * FROM oauth_tokens WHERE access_token = ? OR refresh_token = ?",
                    (token, token),
                )

            row = cursor.fetchone()

            if not row:
                return {"username": None, "token_type": None}

            # Delete token
            conn.execute(
                "DELETE FROM oauth_tokens WHERE token_id = ?", (row["token_id"],)
            )
            conn.commit()

            # Determine which token type was revoked
            determined_type = (
                "access_token" if row["access_token"] == token else "refresh_token"
            )

            return {"username": row["user_id"], "token_type": determined_type}

    def handle_client_credentials_grant(
        self,
        client_id: str,
        client_secret: str,
        scope: Optional[str] = None,
        mcp_credential_manager: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Handle OAuth 2.1 client_credentials grant type.

        Args:
            client_id: MCP client ID
            client_secret: MCP client secret
            scope: Optional scope (not used currently)
            mcp_credential_manager: MCPCredentialManager instance for credential verification

        Returns:
            Token response with access_token, token_type, expires_in

        Raises:
            OAuthError: If credentials are invalid or missing
        """
        # Validate parameters
        if not client_id or not client_secret:
            raise OAuthError("client_id and client_secret required")

        # Verify credentials using MCPCredentialManager
        if not mcp_credential_manager:
            raise OAuthError("MCPCredentialManager not available")

        user_id = mcp_credential_manager.verify_credential(client_id, client_secret)
        if not user_id:
            raise OAuthError("Invalid client credentials")

        # Generate access token (no refresh token for client_credentials)
        token_id = secrets.token_urlsafe(32)
        access_token = secrets.token_urlsafe(48)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=self.ACCESS_TOKEN_LIFETIME_HOURS)
        hard_expires_at = now + timedelta(days=self.HARD_EXPIRATION_DAYS)

        # Store token in database (use "client_credentials" as client_id for tracking)
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute(
                """INSERT INTO oauth_tokens (token_id, client_id, user_id, access_token, refresh_token,
                   expires_at, created_at, last_activity, hard_expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    token_id,
                    "client_credentials",  # Special client_id for client_credentials grant
                    user_id,
                    access_token,
                    None,  # No refresh token for client_credentials
                    expires_at.isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                    hard_expires_at.isoformat(),
                ),
            )
            conn.commit()

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": int(self.ACCESS_TOKEN_LIFETIME_HOURS * 3600),
        }

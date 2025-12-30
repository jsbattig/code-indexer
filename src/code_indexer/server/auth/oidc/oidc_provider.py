"""OIDC provider implementation for generic OIDC-compliant providers."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class OIDCMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str

    userinfo_endpoint: Optional[str] = None

@dataclass
class OIDCUserInfo:
    subject: str
    email: Optional[str] = None
    email_verified: bool = False


class OIDCProvider:
    def __init__(self, config):
        self.config = config
        self._metadata = None

    async def discover_metadata(self):
        import httpx

        # Construct well-known URL
        well_known_url = f"{self.config.issuer_url}/.well-known/openid-configuration"

        # Fetch metadata from well-known endpoint
        async with httpx.AsyncClient() as client:
            response = await client.get(well_known_url)
            data = response.json()  # Not async in httpx

        # Create and return OIDCMetadata
        metadata = OIDCMetadata(
            issuer=data["issuer"],
            authorization_endpoint=data["authorization_endpoint"],
            token_endpoint=data["token_endpoint"],
            userinfo_endpoint=data.get("userinfo_endpoint"),
        )

        return metadata

    def get_authorization_url(self, state, redirect_uri, code_challenge):
        from urllib.parse import urlencode

        # Build query parameters for OIDC authorization request
        params = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "scope": "openid profile email",
        }

        # Build full authorization URL
        query_string = urlencode(params)
        auth_url = f"{self._metadata.authorization_endpoint}?{query_string}"

        return auth_url

    async def exchange_code_for_token(self, code, code_verifier, redirect_uri):
        import httpx

        # Build token request payload
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "code_verifier": code_verifier,
        }

        # Exchange code for tokens
        async with httpx.AsyncClient() as client:
            response = await client.post(self._metadata.token_endpoint, data=data)
            tokens = response.json()  # Not async in httpx

        return tokens

    async def get_user_info(self, access_token):
        import httpx

        # Construct userinfo endpoint (typically from discovery, but fallback to standard path)
        # Use userinfo endpoint from discovery metadata (preferred) or fallback
        if self._metadata and self._metadata.userinfo_endpoint:
            userinfo_endpoint = self._metadata.userinfo_endpoint
        else:
            userinfo_endpoint = f"{self.config.issuer_url}/protocol/openid-connect/userinfo"

        # Fetch user info from userinfo endpoint
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient() as client:
            response = await client.get(userinfo_endpoint, headers=headers)
            data = response.json()  # Not async in httpx

        # Create OIDCUserInfo from response
        user_info = OIDCUserInfo(
            subject=data.get("sub", ""),
            email=data.get(self.config.email_claim),
            email_verified=data.get("email_verified", False),
        )

        return user_info

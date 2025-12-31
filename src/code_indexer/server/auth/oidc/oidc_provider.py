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
    username: Optional[str] = None


class OIDCProvider:
    def __init__(self, config):
        self.config = config
        self._metadata = None

    async def discover_metadata(self):
        import httpx

        # Construct well-known URL
        well_known_url = f"{self.config.issuer_url}/.well-known/openid-configuration"

        # Fetch metadata from well-known endpoint
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(well_known_url)
                response.raise_for_status()  # Raise HTTPStatusError for 4xx/5xx
                data = response.json()  # Not async in httpx
        except httpx.HTTPStatusError as e:
            raise Exception(
                f"Failed to discover OIDC metadata: HTTP {e.response.status_code} - {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise Exception(
                f"Failed to connect to OIDC provider at {well_known_url}: {str(e)}"
            ) from e

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
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self._metadata.token_endpoint, data=data)
                response.raise_for_status()  # Raise HTTPStatusError for 4xx/5xx
                tokens = response.json()  # Not async in httpx
        except httpx.HTTPStatusError as e:
            raise Exception(
                f"Failed to exchange authorization code for token: HTTP {e.response.status_code} - {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise Exception(f"Failed to connect to token endpoint: {str(e)}") from e

        # Validate token response has required fields
        if "access_token" not in tokens:
            raise Exception("Invalid token response: missing access_token field")

        return tokens

    async def get_user_info(self, access_token):
        import httpx
        import logging

        logger = logging.getLogger(__name__)

        # Construct userinfo endpoint (typically from discovery, but fallback to standard path)
        # Use userinfo endpoint from discovery metadata (preferred) or fallback
        if self._metadata and self._metadata.userinfo_endpoint:
            userinfo_endpoint = self._metadata.userinfo_endpoint
        else:
            userinfo_endpoint = (
                f"{self.config.issuer_url}/protocol/openid-connect/userinfo"
            )

        # Fetch user info from userinfo endpoint
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(userinfo_endpoint, headers=headers)
                response.raise_for_status()  # Raise HTTPStatusError for 4xx/5xx
                data = response.json()  # Not async in httpx
        except httpx.HTTPStatusError as e:
            raise Exception(
                f"Failed to get user info: HTTP {e.response.status_code} - {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise Exception(f"Failed to connect to userinfo endpoint: {str(e)}") from e

        # Validate userinfo response has required fields
        if "sub" not in data or not data["sub"]:
            raise Exception(
                "Invalid userinfo response: missing or empty sub (subject) claim"
            )

        # Log claim extraction for debugging
        logger.info(
            f"Extracting claims - email_claim: {self.config.email_claim}, username_claim: {self.config.username_claim}"
        )
        logger.info(f"Available claims in userinfo: {list(data.keys())}")

        email_value = data.get(self.config.email_claim)
        logger.info(
            f"Extracted email from '{self.config.email_claim}' claim: {email_value}"
        )

        username_value = data.get(self.config.username_claim)
        logger.info(
            f"Extracted username from '{self.config.username_claim}' claim: {username_value}"
        )

        # Create OIDCUserInfo from response
        user_info = OIDCUserInfo(
            subject=data.get("sub", ""),
            email=email_value,
            email_verified=data.get("email_verified", False),
            username=username_value,
        )

        return user_info

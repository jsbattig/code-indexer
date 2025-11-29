"""Unit tests for automatic login functionality.

This module tests the auto-login functionality that allows mcpb to
automatically re-authenticate when tokens expire.
"""

import pytest
import httpx

from code_indexer.mcpb.auto_login import attempt_auto_login
from code_indexer.mcpb.http_client import HttpError


@pytest.fixture
def mock_credentials(monkeypatch, tmp_path):
    """Fixture to set up mock credentials for testing."""
    from pathlib import Path
    from code_indexer.mcpb.credential_storage import save_credentials

    # Patch Path.home() to use tmp_path
    def mock_home():
        return tmp_path

    monkeypatch.setattr(Path, "home", mock_home)

    # Create .mcpb directory
    mcpb_dir = tmp_path / ".mcpb"
    mcpb_dir.mkdir(parents=True, exist_ok=True)

    # Save test credentials
    save_credentials("test_user", "test_password")

    yield tmp_path


class TestAutoLogin:
    """Test automatic login functionality."""

    @pytest.mark.asyncio
    async def test_attempt_auto_login_success(self, mock_credentials, httpx_mock):
        """Test successful auto-login returns access and refresh tokens."""
        # Mock login endpoint
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/auth/login",
            json={
                "access_token": "new-access-token-123",
                "refresh_token": "new-refresh-token-456",
            },
            status_code=200,
        )

        # Attempt auto-login
        access_token, refresh_token = await attempt_auto_login(
            "https://cidx.example.com", timeout=30
        )

        # Verify tokens
        assert access_token == "new-access-token-123"
        assert refresh_token == "new-refresh-token-456"

        # Verify request was made with correct credentials
        requests = httpx_mock.get_requests()
        assert len(requests) == 1
        request = requests[0]
        assert request.method == "POST"
        assert request.url.path == "/auth/login"

        # Verify request body
        import json

        body = json.loads(request.content)
        assert body["username"] == "test_user"
        assert body["password"] == "test_password"

    @pytest.mark.asyncio
    async def test_attempt_auto_login_no_credentials_raises_error(
        self, monkeypatch, tmp_path
    ):
        """Test that auto-login raises error when no credentials exist."""
        from pathlib import Path

        # Patch Path.home() to use empty tmp_path
        def mock_home():
            return tmp_path

        monkeypatch.setattr(Path, "home", mock_home)

        # Create .mcpb directory but no credentials
        mcpb_dir = tmp_path / ".mcpb"
        mcpb_dir.mkdir(parents=True, exist_ok=True)

        # Attempt auto-login should fail
        with pytest.raises(ValueError, match="No credentials available for auto-login"):
            await attempt_auto_login("https://cidx.example.com", timeout=30)

    @pytest.mark.asyncio
    async def test_attempt_auto_login_http_401_raises_error(
        self, mock_credentials, httpx_mock
    ):
        """Test that 401 response raises authentication error."""
        # Mock login endpoint returning 401
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/auth/login",
            status_code=401,
            text="Invalid credentials",
        )

        # Attempt auto-login should fail
        with pytest.raises(HttpError, match="Auto-login failed.*401.*Invalid credentials"):
            await attempt_auto_login("https://cidx.example.com", timeout=30)

    @pytest.mark.asyncio
    async def test_attempt_auto_login_http_500_raises_error(
        self, mock_credentials, httpx_mock
    ):
        """Test that 500 response raises server error."""
        # Mock login endpoint returning 500
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/auth/login",
            status_code=500,
            text="Internal server error",
        )

        # Attempt auto-login should fail
        with pytest.raises(HttpError, match="Auto-login failed.*500"):
            await attempt_auto_login("https://cidx.example.com", timeout=30)

    @pytest.mark.asyncio
    async def test_attempt_auto_login_connection_error_raises_error(
        self, mock_credentials, httpx_mock
    ):
        """Test that connection error raises HttpError."""
        # Mock connection error
        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"),
            url="https://cidx.example.com/auth/login",
        )

        # Attempt auto-login should fail
        with pytest.raises(HttpError, match="Auto-login failed.*Connection"):
            await attempt_auto_login("https://cidx.example.com", timeout=30)

    @pytest.mark.asyncio
    async def test_attempt_auto_login_malformed_response_raises_error(
        self, mock_credentials, httpx_mock
    ):
        """Test that malformed response (missing tokens) raises error."""
        # Mock login endpoint returning incomplete response
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/auth/login",
            json={"access_token": "token123"},  # Missing refresh_token
            status_code=200,
        )

        # Attempt auto-login should fail
        with pytest.raises(
            HttpError, match="Invalid login response.*refresh_token"
        ):
            await attempt_auto_login("https://cidx.example.com", timeout=30)

    @pytest.mark.asyncio
    async def test_attempt_auto_login_missing_access_token_raises_error(
        self, mock_credentials, httpx_mock
    ):
        """Test that response missing access_token raises error."""
        # Mock login endpoint returning incomplete response
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/auth/login",
            json={"refresh_token": "refresh123"},  # Missing access_token
            status_code=200,
        )

        # Attempt auto-login should fail
        with pytest.raises(HttpError, match="Invalid login response.*access_token"):
            await attempt_auto_login("https://cidx.example.com", timeout=30)

    @pytest.mark.asyncio
    async def test_attempt_auto_login_logs_to_stderr(
        self, mock_credentials, httpx_mock, capsys
    ):
        """Test that auto-login logs success to stderr (for debugging)."""
        # Mock successful login
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/auth/login",
            json={
                "access_token": "new-access-token-1234567890123456789012345678901234567890",
                "refresh_token": "new-refresh-token",
            },
            status_code=200,
        )

        # Attempt auto-login
        await attempt_auto_login("https://cidx.example.com", timeout=30)

        # Verify stderr logging
        captured = capsys.readouterr()
        assert "Auto-login successful:" in captured.err
        # Verify only first 20 chars logged
        assert "new-access-token-123" in captured.err
        # Verify full token NOT logged
        assert (
            "new-access-token-1234567890123456789012345678901234567890"
            not in captured.err
        )

    @pytest.mark.asyncio
    async def test_attempt_auto_login_does_not_log_password(
        self, mock_credentials, httpx_mock, capsys
    ):
        """Test that auto-login NEVER logs the password."""
        # Mock successful login
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/auth/login",
            json={
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
            },
            status_code=200,
        )

        # Attempt auto-login
        await attempt_auto_login("https://cidx.example.com", timeout=30)

        # Verify password NOT in stderr
        captured = capsys.readouterr()
        assert "test_password" not in captured.err
        assert "password" not in captured.err.lower() or "password" in "Auto-login"

    @pytest.mark.asyncio
    async def test_attempt_auto_login_timeout_raises_error(
        self, mock_credentials, httpx_mock
    ):
        """Test that timeout error is properly handled."""
        # Mock timeout
        httpx_mock.add_exception(
            httpx.TimeoutException("Request timeout"),
            url="https://cidx.example.com/auth/login",
        )

        # Attempt auto-login should fail with timeout error
        with pytest.raises(HttpError, match="Auto-login failed.*timeout"):
            await attempt_auto_login("https://cidx.example.com", timeout=30)

    @pytest.mark.asyncio
    async def test_attempt_auto_login_network_error_raises_error(
        self, mock_credentials, httpx_mock
    ):
        """Test that network error is properly handled."""
        # Mock network error
        httpx_mock.add_exception(
            httpx.NetworkError("Network unreachable"),
            url="https://cidx.example.com/auth/login",
        )

        # Attempt auto-login should fail
        with pytest.raises(HttpError, match="Auto-login failed.*Network"):
            await attempt_auto_login("https://cidx.example.com", timeout=30)

    @pytest.mark.asyncio
    async def test_attempt_auto_login_invalid_json_response_raises_error(
        self, mock_credentials, httpx_mock
    ):
        """Test that invalid JSON response raises error."""
        # Mock login endpoint returning invalid JSON
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/auth/login",
            text="Not JSON",
            status_code=200,
        )

        # Attempt auto-login should fail
        with pytest.raises(HttpError, match="Auto-login failed.*Invalid JSON"):
            await attempt_auto_login("https://cidx.example.com", timeout=30)

    @pytest.mark.asyncio
    async def test_attempt_auto_login_uses_correct_timeout(
        self, mock_credentials, httpx_mock
    ):
        """Test that auto-login uses the provided timeout value."""
        # Mock successful login
        httpx_mock.add_response(
            method="POST",
            url="https://cidx.example.com/auth/login",
            json={
                "access_token": "token",
                "refresh_token": "refresh",
            },
            status_code=200,
        )

        # Attempt auto-login with specific timeout
        await attempt_auto_login("https://cidx.example.com", timeout=60)

        # Verify request was made (httpx_mock handles timeout internally)
        requests = httpx_mock.get_requests()
        assert len(requests) == 1

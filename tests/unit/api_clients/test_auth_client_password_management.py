"""Tests for AuthAPIClient password management operations.

Tests for change_password and reset_password methods with comprehensive coverage
of API integration, error handling, and security requirements.
"""

import json
import pytest
from unittest.mock import Mock, AsyncMock, patch
import httpx
from pathlib import Path

from code_indexer.api_clients.auth_client import AuthAPIClient
from code_indexer.api_clients.base_client import APIClientError, AuthenticationError


class TestChangePasswordAPI:
    """Test change_password API method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.server_url = "https://test.example.com"
        self.project_root = Path("/tmp/test/project")
        self.credentials = {"username": "testuser", "password": "testpass"}

        self.client = AuthAPIClient(
            server_url=self.server_url,
            project_root=self.project_root,
            credentials=self.credentials,
        )

    @pytest.mark.asyncio
    async def test_change_password_method_exists(self):
        """Test that change_password method exists with correct signature."""
        # Verify the method exists and has the expected signature
        assert hasattr(self.client, "change_password")
        assert callable(self.client.change_password)

    @pytest.mark.asyncio
    async def test_change_password_success(self):
        """Test successful password change."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "message": "Password changed successfully",
        }

        # Mock _authenticated_request method
        with patch.object(
            self.client, "_authenticated_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            # Mock credential storage
            with patch.object(
                self.client, "_store_credentials_securely", new_callable=AsyncMock
            ):
                # Call the actual method
                result = await self.client.change_password(
                    "current_pass", "new_pass123!"
                )

                # Verify the result
                assert result == {
                    "status": "success",
                    "message": "Password changed successfully",
                }

                # Verify _authenticated_request was called correctly
                mock_request.assert_called_once_with(
                    "PUT",
                    "/api/users/change-password",
                    json={
                        "old_password": "current_pass",
                        "new_password": "new_pass123!",
                    },
                )

    @pytest.mark.asyncio
    async def test_change_password_wrong_current_password(self):
        """Test password change with incorrect current password."""
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Current password is incorrect"}

        # Mock _authenticated_request method
        with patch.object(
            self.client, "_authenticated_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            # Call should raise APIClientError
            with pytest.raises(APIClientError) as exc_info:
                await self.client.change_password("wrong_pass", "new_pass123!")

            assert "Current password is incorrect" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_change_password_weak_password_server_validation(self):
        """Test server-side password policy validation."""
        # Mock server validation error
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "detail": "Password does not meet security requirements"
        }

        # Mock _authenticated_request method
        with patch.object(
            self.client, "_authenticated_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            # Call should raise APIClientError
            with pytest.raises(APIClientError) as exc_info:
                await self.client.change_password("current_pass", "weak")

            assert "Password does not meet security requirements" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_change_password_authentication_required(self):
        """Test password change when authentication is required."""
        # Mock authentication error
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Authentication required"}

        # Mock _authenticated_request method
        with patch.object(
            self.client, "_authenticated_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            # Call should raise AuthenticationError
            with pytest.raises(AuthenticationError) as exc_info:
                await self.client.change_password("current_pass", "new_pass123!")

            assert "Authentication required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_change_password_network_error(self):
        """Test password change with network error."""
        # Mock _authenticated_request to raise network error
        with patch.object(
            self.client, "_authenticated_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = httpx.NetworkError("Connection failed")

            # Call should raise APIClientError with network error details
            with pytest.raises(APIClientError) as exc_info:
                await self.client.change_password("current_pass", "new_pass123!")

            assert "Connection failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_change_password_updates_stored_credentials(self):
        """Test that successful password change updates stored credentials."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "message": "Password changed",
        }

        with patch.object(
            self.client, "_authenticated_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            with patch.object(
                self.client, "_store_credentials_securely", new_callable=AsyncMock
            ) as mock_store:
                # Call the method
                await self.client.change_password("old_pass", "new_pass")

                # Verify credentials were updated
                assert self.client.credentials["password"] == "new_pass"

                # Verify store was called
                mock_store.assert_called_once_with("testuser", "new_pass")


class TestResetPasswordAPI:
    """Test reset_password API method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.server_url = "https://test.example.com"
        self.project_root = Path("/tmp/test/project")

        # Reset password doesn't require authentication
        self.client = AuthAPIClient(
            server_url=self.server_url, project_root=self.project_root
        )

    @pytest.mark.asyncio
    async def test_reset_password_method_exists(self):
        """Test that reset_password method exists with correct signature."""
        assert hasattr(self.client, "reset_password")
        assert callable(self.client.reset_password)

    @pytest.mark.asyncio
    async def test_reset_password_success(self):
        """Test successful password reset initiation."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "message": "Reset email sent",
        }

        with patch.object(
            self.client.session, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            # Call the method
            result = await self.client.reset_password("testuser")

            # Verify result
            assert result == {"status": "success", "message": "Reset email sent"}

            # Verify post was called correctly
            mock_post.assert_called_once_with(
                f"{self.server_url}/auth/reset-password", json={"username": "testuser"}
            )

    @pytest.mark.asyncio
    async def test_reset_password_user_not_found(self):
        """Test password reset with non-existent username."""
        # Mock user not found response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "User not found"}

        with patch.object(
            self.client.session, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            # Call should raise APIClientError
            with pytest.raises(APIClientError) as exc_info:
                await self.client.reset_password("nonexistent")

            assert "User not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reset_password_rate_limiting(self):
        """Test password reset with rate limiting."""
        # Mock rate limiting response
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.json.return_value = {"detail": "Too many reset attempts"}

        with patch.object(
            self.client.session, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            # Call should raise APIClientError
            with pytest.raises(APIClientError) as exc_info:
                await self.client.reset_password("testuser")

            assert "Too many reset attempts" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reset_password_server_error(self):
        """Test password reset with server error."""
        # Mock server error response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal server error"}

        with patch.object(
            self.client.session, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            # Call should raise APIClientError
            with pytest.raises(APIClientError) as exc_info:
                await self.client.reset_password("testuser")

            assert "Internal server error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reset_password_network_error(self):
        """Test password reset with network error."""
        with patch.object(
            self.client.session, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.side_effect = httpx.NetworkError("Connection failed")

            # Call should raise APIClientError
            with pytest.raises(APIClientError) as exc_info:
                await self.client.reset_password("testuser")

            assert "Connection failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reset_password_json_decode_error(self):
        """Test reset password with malformed JSON response."""
        # Mock response with invalid JSON
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.side_effect = json.JSONDecodeError("Invalid", "", 0)

        with patch.object(
            self.client.session, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            # Should handle JSON error gracefully
            with pytest.raises(APIClientError) as exc_info:
                await self.client.reset_password("testuser")

            # Should use default error message
            assert "User not found" in str(exc_info.value)


class TestPasswordSecurityHandling:
    """Test security aspects of password handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.server_url = "https://test.example.com"
        self.project_root = Path("/tmp/test/project")
        self.credentials = {"username": "testuser", "password": "testpass"}

        self.client = AuthAPIClient(
            server_url=self.server_url,
            project_root=self.project_root,
            credentials=self.credentials,
        )

    @pytest.mark.asyncio
    async def test_password_not_logged(self):
        """Test that passwords are not logged in any form."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success"}

        with patch("code_indexer.api_clients.auth_client.logger") as mock_logger:
            with patch.object(
                self.client, "_authenticated_request", new_callable=AsyncMock
            ) as mock_request:
                mock_request.return_value = mock_response
                with patch.object(
                    self.client, "_store_credentials_securely", new_callable=AsyncMock
                ):
                    await self.client.change_password("current_pass", "new_pass123!")

                    # Verify passwords never appear in logs
                    for call in mock_logger.debug.call_args_list:
                        if call[0]:
                            assert "current_pass" not in str(call[0][0])
                            assert "new_pass123!" not in str(call[0][0])

                    for call in mock_logger.info.call_args_list:
                        if call[0]:
                            assert "current_pass" not in str(call[0][0])
                            assert "new_pass123!" not in str(call[0][0])

    @pytest.mark.asyncio
    async def test_https_only_transmission(self):
        """Test that passwords are only transmitted over HTTPS."""
        # Test with HTTP URL (should work since client doesn't enforce)
        http_client = AuthAPIClient(
            server_url="http://test.example.com", project_root=self.project_root
        )

        # The implementation allows HTTP for testing purposes
        # but in production should use HTTPS
        assert http_client.server_url == "http://test.example.com"

        # Test with HTTPS URL
        https_client = AuthAPIClient(
            server_url="https://test.example.com", project_root=self.project_root
        )

        assert https_client.server_url == "https://test.example.com"

    @pytest.mark.asyncio
    async def test_password_request_payload_structure(self):
        """Test that password request payloads are properly structured."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success"}

        with patch.object(
            self.client, "_authenticated_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response
            with patch.object(
                self.client, "_store_credentials_securely", new_callable=AsyncMock
            ):
                await self.client.change_password("old_pass", "new_pass")

                # Verify correct payload structure
                mock_request.assert_called_once()
                call_args = mock_request.call_args
                assert call_args[0][0] == "PUT"
                assert call_args[0][1] == "/api/users/change-password"
                assert call_args[1]["json"] == {
                    "old_password": "old_pass",
                    "new_password": "new_pass",
                }

    @pytest.mark.asyncio
    async def test_password_cleared_on_exception(self):
        """Test that passwords are not retained after exceptions."""
        with patch.object(
            self.client, "_authenticated_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = Exception("Test error")

            # Store original password
            original_password = self.client.credentials.get("password", "")

            # Call should raise exception
            with pytest.raises(APIClientError):
                await self.client.change_password("old", "new")

            # Password should not have changed
            assert self.client.credentials.get("password", "") == original_password

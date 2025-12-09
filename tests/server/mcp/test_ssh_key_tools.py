"""Tests for SSH Key MCP tools."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from datetime import datetime
import json

from code_indexer.server.services.ssh_key_manager import (
    SSHKeyManager,
    KeyMetadata,
    KeyListResult,
    KeyNotFoundError,
)
from code_indexer.server.auth.user_manager import User, UserRole


def parse_mcp_response(response):
    """Parse MCP-formatted response to extract actual data."""
    content = response.get("content", [])
    if content and len(content) > 0:
        text = content[0].get("text", "{}")
        return json.loads(text)
    return {}


@pytest.fixture
def mock_user():
    """Create a mock admin user."""
    return User(
        username="admin",
        password_hash="hash",
        role=UserRole.ADMIN,
        created_at=datetime.now(),
    )


class TestSSHKeyCreateTool:
    """Tests for cidx_ssh_key_create MCP tool."""

    @pytest.mark.asyncio
    async def test_create_key_success(self, mock_user):
        """Should create SSH key and return public key."""
        from code_indexer.server.mcp.handlers import handle_ssh_key_create

        mock_manager = MagicMock(spec=SSHKeyManager)
        mock_manager.create_key.return_value = KeyMetadata(
            name="test-key",
            fingerprint="SHA256:abc123",
            key_type="ed25519",
            private_path="/home/user/.ssh/test-key",
            public_path="/home/user/.ssh/test-key.pub",
            public_key="ssh-ed25519 AAAA... test@example.com",
            email="test@example.com",
        )

        args = {"name": "test-key", "email": "test@example.com"}

        with patch(
            "code_indexer.server.mcp.handlers.get_ssh_key_manager",
            return_value=mock_manager,
        ):
            response = await handle_ssh_key_create(args, mock_user)

        data = parse_mcp_response(response)
        assert data["success"] is True
        assert data["public_key"] == "ssh-ed25519 AAAA... test@example.com"
        mock_manager.create_key.assert_called_once()


class TestSSHKeyListTool:
    """Tests for cidx_ssh_key_list MCP tool."""

    @pytest.mark.asyncio
    async def test_list_keys_success(self, mock_user):
        """Should list managed and unmanaged keys."""
        from code_indexer.server.mcp.handlers import handle_ssh_key_list

        mock_manager = MagicMock(spec=SSHKeyManager)
        mock_manager.list_keys.return_value = KeyListResult(
            managed=[
                KeyMetadata(
                    name="managed-key",
                    fingerprint="SHA256:abc",
                    key_type="ed25519",
                    private_path="/home/user/.ssh/managed-key",
                    public_path="/home/user/.ssh/managed-key.pub",
                    hosts=["github.com"],
                )
            ],
            unmanaged=[],
        )

        with patch(
            "code_indexer.server.mcp.handlers.get_ssh_key_manager",
            return_value=mock_manager,
        ):
            response = await handle_ssh_key_list({}, mock_user)

        data = parse_mcp_response(response)
        assert data["success"] is True
        assert len(data["managed"]) == 1
        assert data["managed"][0]["name"] == "managed-key"


class TestSSHKeyDeleteTool:
    """Tests for cidx_ssh_key_delete MCP tool."""

    @pytest.mark.asyncio
    async def test_delete_key_success(self, mock_user):
        """Should delete key and return success."""
        from code_indexer.server.mcp.handlers import handle_ssh_key_delete

        mock_manager = MagicMock(spec=SSHKeyManager)
        mock_manager.delete_key.return_value = True

        args = {"name": "test-key"}

        with patch(
            "code_indexer.server.mcp.handlers.get_ssh_key_manager",
            return_value=mock_manager,
        ):
            response = await handle_ssh_key_delete(args, mock_user)

        data = parse_mcp_response(response)
        assert data["success"] is True
        mock_manager.delete_key.assert_called_once_with("test-key")


class TestSSHKeyShowPublicTool:
    """Tests for cidx_ssh_key_show_public MCP tool."""

    @pytest.mark.asyncio
    async def test_show_public_key_success(self, mock_user):
        """Should return public key content."""
        from code_indexer.server.mcp.handlers import handle_ssh_key_show_public

        mock_manager = MagicMock(spec=SSHKeyManager)
        mock_manager.get_public_key.return_value = "ssh-ed25519 AAAA... test"

        args = {"name": "test-key"}

        with patch(
            "code_indexer.server.mcp.handlers.get_ssh_key_manager",
            return_value=mock_manager,
        ):
            response = await handle_ssh_key_show_public(args, mock_user)

        data = parse_mcp_response(response)
        assert data["success"] is True
        assert data["public_key"] == "ssh-ed25519 AAAA... test"


class TestSSHKeyAssignHostTool:
    """Tests for cidx_ssh_key_assign_host MCP tool."""

    @pytest.mark.asyncio
    async def test_assign_host_success(self, mock_user):
        """Should assign host to key."""
        from code_indexer.server.mcp.handlers import handle_ssh_key_assign_host

        mock_manager = MagicMock(spec=SSHKeyManager)
        mock_manager.assign_key_to_host.return_value = KeyMetadata(
            name="test-key",
            fingerprint="SHA256:abc",
            key_type="ed25519",
            private_path="/home/user/.ssh/test-key",
            public_path="/home/user/.ssh/test-key.pub",
            hosts=["github.com"],
        )

        args = {"name": "test-key", "hostname": "github.com"}

        with patch(
            "code_indexer.server.mcp.handlers.get_ssh_key_manager",
            return_value=mock_manager,
        ):
            response = await handle_ssh_key_assign_host(args, mock_user)

        data = parse_mcp_response(response)
        assert data["success"] is True
        assert "github.com" in data["hosts"]

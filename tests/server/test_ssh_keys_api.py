"""Tests for SSH Keys REST API endpoints."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import json

from code_indexer.server.services.ssh_key_manager import (
    SSHKeyManager,
    KeyMetadata,
    KeyListResult,
    KeyNotFoundError,
    HostConflictError,
)
from code_indexer.server.services.ssh_key_generator import (
    InvalidKeyNameError,
    KeyAlreadyExistsError,
)


class TestSSHKeysRouterModels:
    """Tests for SSH Keys API request/response models."""

    def test_create_key_request_valid(self):
        """Should validate CreateKeyRequest model."""
        from code_indexer.server.routers.ssh_keys import CreateKeyRequest

        request = CreateKeyRequest(name="my-key", email="test@example.com")
        assert request.name == "my-key"
        assert request.email == "test@example.com"
        assert request.key_type == "ed25519"  # default

    def test_assign_host_request_valid(self):
        """Should validate AssignHostRequest model."""
        from code_indexer.server.routers.ssh_keys import AssignHostRequest

        request = AssignHostRequest(hostname="github.com")
        assert request.hostname == "github.com"


class TestSSHKeysRouterEndpoints:
    """Tests for SSH Keys router endpoint functions."""

    def test_create_key_success(self):
        """Should create key and return response."""
        from code_indexer.server.routers.ssh_keys import (
            create_ssh_key,
            CreateKeyRequest,
        )

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

        request = CreateKeyRequest(name="test-key", email="test@example.com")

        with patch(
            "code_indexer.server.routers.ssh_keys.get_ssh_key_manager",
            return_value=mock_manager,
        ):
            response = create_ssh_key(request)

        assert response.name == "test-key"
        assert response.public_key == "ssh-ed25519 AAAA... test@example.com"
        mock_manager.create_key.assert_called_once()

    def test_list_keys_returns_managed_and_unmanaged(self):
        """Should list both managed and unmanaged keys."""
        from code_indexer.server.routers.ssh_keys import list_ssh_keys

        mock_manager = MagicMock(spec=SSHKeyManager)
        mock_manager.list_keys.return_value = KeyListResult(
            managed=[
                KeyMetadata(
                    name="managed-key",
                    fingerprint="SHA256:abc",
                    key_type="ed25519",
                    private_path="/home/user/.ssh/managed-key",
                    public_path="/home/user/.ssh/managed-key.pub",
                )
            ],
            unmanaged=[],
        )

        with patch(
            "code_indexer.server.routers.ssh_keys.get_ssh_key_manager",
            return_value=mock_manager,
        ):
            response = list_ssh_keys()

        assert len(response.managed) == 1
        assert response.managed[0].name == "managed-key"

    def test_delete_key_idempotent(self):
        """Should return success even for non-existent key."""
        from code_indexer.server.routers.ssh_keys import delete_ssh_key

        mock_manager = MagicMock(spec=SSHKeyManager)
        mock_manager.delete_key.return_value = True

        with patch(
            "code_indexer.server.routers.ssh_keys.get_ssh_key_manager",
            return_value=mock_manager,
        ):
            response = delete_ssh_key("nonexistent")

        assert response.success is True
        mock_manager.delete_key.assert_called_once_with("nonexistent")

    def test_get_public_key_success(self):
        """Should return public key content."""
        from code_indexer.server.routers.ssh_keys import get_public_key
        from fastapi import Response

        mock_manager = MagicMock(spec=SSHKeyManager)
        mock_manager.get_public_key.return_value = "ssh-ed25519 AAAA... test"

        with patch(
            "code_indexer.server.routers.ssh_keys.get_ssh_key_manager",
            return_value=mock_manager,
        ):
            response = get_public_key("my-key")

        assert response.body == b"ssh-ed25519 AAAA... test"
        assert response.media_type == "text/plain"

    def test_assign_host_success(self):
        """Should assign host to key."""
        from code_indexer.server.routers.ssh_keys import (
            assign_host,
            AssignHostRequest,
        )

        mock_manager = MagicMock(spec=SSHKeyManager)
        mock_manager.assign_key_to_host.return_value = KeyMetadata(
            name="my-key",
            fingerprint="SHA256:abc",
            key_type="ed25519",
            private_path="/home/user/.ssh/my-key",
            public_path="/home/user/.ssh/my-key.pub",
            hosts=["github.com"],
        )

        request = AssignHostRequest(hostname="github.com")

        with patch(
            "code_indexer.server.routers.ssh_keys.get_ssh_key_manager",
            return_value=mock_manager,
        ):
            response = assign_host("my-key", request)

        assert "github.com" in response.hosts
        mock_manager.assign_key_to_host.assert_called_once()

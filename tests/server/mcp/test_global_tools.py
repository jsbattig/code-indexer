"""Tests for Global Repository MCP Tools.

Tests the 4 MCP tools for global repository operations:
- list_global_repos
- global_repo_status
- get_global_config
- set_global_config
"""

import pytest
from code_indexer.server.mcp.handlers import (
    handle_list_global_repos,
    handle_global_repo_status,
    handle_get_global_config,
    handle_set_global_config,
)
from code_indexer.server.auth.user_manager import User, UserRole
import tempfile
from pathlib import Path
import json
from datetime import datetime, timezone


@pytest.fixture
def test_user():
    """Create test user with admin role."""
    return User(
        username="test",
        password_hash="fake_hash",
        role=UserRole.ADMIN,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def global_repos_setup(tmp_path, monkeypatch):
    """Setup test environment with global registry."""
    from code_indexer.global_repos.global_registry import GlobalRegistry

    # Create test directory structure
    golden_repos_dir = tmp_path / "golden-repos"
    golden_repos_dir.mkdir()

    # Set environment variable so handlers use this directory
    monkeypatch.setenv("GOLDEN_REPOS_DIR", str(golden_repos_dir))

    # Create global registry and register a test repo
    registry = GlobalRegistry(str(golden_repos_dir))
    test_repo_path = tmp_path / "test-repo"
    test_repo_path.mkdir()

    registry.register_global_repo(
        "test-repo",
        "test-repo-global",
        "http://example.com/test.git",
        str(test_repo_path),
        allow_reserved=False
    )

    return golden_repos_dir


@pytest.mark.asyncio
async def test_list_global_repos_returns_repos(test_user, global_repos_setup):
    """Test list_global_repos returns repository list."""
    result = await handle_list_global_repos({}, test_user)

    # Parse MCP response
    assert "content" in result
    assert len(result["content"]) == 1
    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "repos" in data
    assert isinstance(data["repos"], list)


@pytest.mark.asyncio
async def test_global_repo_status_returns_metadata(test_user, global_repos_setup):
    """Test global_repo_status returns repository metadata."""
    result = await handle_global_repo_status({"alias": "test-repo-global"}, test_user)

    # Parse MCP response
    assert "content" in result
    data = json.loads(result["content"][0]["text"])

    # Debug: Print data if failure
    if not data.get("success"):
        print(f"\nError in response: {data}")

    assert data["success"] is True
    assert "repo_name" in data
    assert "alias" in data
    assert data["alias"] == "test-repo-global"


@pytest.mark.asyncio
async def test_global_repo_status_raises_for_nonexistent(test_user, global_repos_setup):
    """Test global_repo_status handles nonexistent repository."""
    result = await handle_global_repo_status({"alias": "nonexistent"}, test_user)

    # Parse MCP response
    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "not found" in data["error"]


@pytest.mark.asyncio
async def test_global_repo_status_missing_alias(test_user):
    """Test global_repo_status validates required alias parameter."""
    result = await handle_global_repo_status({}, test_user)

    # Parse MCP response
    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "Missing required parameter: alias" in data["error"]


@pytest.mark.asyncio
async def test_get_global_config_returns_interval(test_user):
    """Test get_global_config returns refresh interval."""
    result = await handle_get_global_config({}, test_user)

    # Parse MCP response
    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "refresh_interval" in data


@pytest.mark.asyncio
async def test_set_global_config_updates_interval(test_user):
    """Test set_global_config updates refresh interval."""
    result = await handle_set_global_config({"refresh_interval": 120}, test_user)

    # Parse MCP response
    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert data["status"] == "updated"
    assert data["refresh_interval"] == 120


@pytest.mark.asyncio
async def test_set_global_config_validates_minimum(test_user):
    """Test set_global_config validates minimum interval."""
    result = await handle_set_global_config({"refresh_interval": 30}, test_user)

    # Parse MCP response
    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "at least 60" in data["error"]


@pytest.mark.asyncio
async def test_set_global_config_missing_parameter(test_user):
    """Test set_global_config validates required parameter."""
    result = await handle_set_global_config({}, test_user)

    # Parse MCP response
    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "Missing required parameter: refresh_interval" in data["error"]

"""Tests for directory_tree MCP handler (Story #557).

Tests the directory_tree MCP tool that generates hierarchical tree views
of repository directory structure.
"""

import json
import pytest
from datetime import datetime, timezone
from code_indexer.server.auth.user_manager import User, UserRole


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
def repo_with_tree_structure(tmp_path, monkeypatch):
    """Create a repository with directory structure for tree testing."""
    from code_indexer.global_repos.global_registry import GlobalRegistry
    from code_indexer.server import app as app_module

    # Create golden repos directory
    golden_repos_dir = tmp_path / "golden-repos"
    golden_repos_dir.mkdir()

    # Set app state
    app_module.app.state.golden_repos_dir = str(golden_repos_dir)

    # Create test repository with directory structure
    repo_path = tmp_path / "test-tree-repo"
    repo_path.mkdir()

    # Create directory structure
    (repo_path / "src").mkdir()
    (repo_path / "src" / "main.py").write_text("def main(): pass")
    (repo_path / "src" / "utils").mkdir()
    (repo_path / "src" / "utils" / "helper.py").write_text("def help(): pass")
    (repo_path / "src" / "utils" / "validators.py").write_text("def validate(): pass")
    (repo_path / "tests").mkdir()
    (repo_path / "tests" / "test_main.py").write_text("def test_main(): pass")
    (repo_path / "README.md").write_text("# Project")
    (repo_path / "setup.py").write_text("setup()")

    # Register global repo
    registry = GlobalRegistry(str(golden_repos_dir))
    registry.register_global_repo(
        "test-tree-repo",
        "test-tree-repo-global",
        "http://example.com/test-tree.git",
        str(repo_path),
        allow_reserved=False,
    )

    return {
        "repo_path": repo_path,
        "golden_repos_dir": golden_repos_dir,
    }


@pytest.mark.asyncio
async def test_directory_tree_returns_tree_structure(test_user, repo_with_tree_structure):
    """Test directory_tree returns hierarchical tree structure."""
    from code_indexer.server.mcp.handlers import handle_directory_tree

    result = await handle_directory_tree(
        {"repo_identifier": "test-tree-repo-global"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "tree_string" in data
    assert "root" in data
    assert "total_directories" in data
    assert "total_files" in data
    assert data["total_directories"] == 3  # src, src/utils, tests
    assert data["total_files"] == 6


@pytest.mark.asyncio
async def test_directory_tree_tree_string_format(test_user, repo_with_tree_structure):
    """Test directory_tree returns properly formatted tree string."""
    from code_indexer.server.mcp.handlers import handle_directory_tree

    result = await handle_directory_tree(
        {"repo_identifier": "test-tree-repo-global"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    tree_string = data["tree_string"]

    # Check tree contains expected elements
    assert "src" in tree_string
    assert "README.md" in tree_string
    # Check tree uses proper formatting characters
    assert "|--" in tree_string or "+--" in tree_string


@pytest.mark.asyncio
async def test_directory_tree_with_path_filter(test_user, repo_with_tree_structure):
    """Test directory_tree starting from subdirectory."""
    from code_indexer.server.mcp.handlers import handle_directory_tree

    result = await handle_directory_tree(
        {
            "repo_identifier": "test-tree-repo-global",
            "path": "src",
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert data["root"]["name"] == "src"
    # Should not contain tests or README.md since we're starting from src/
    assert "tests" not in data["tree_string"]


@pytest.mark.asyncio
async def test_directory_tree_respects_max_depth(test_user, repo_with_tree_structure):
    """Test directory_tree respects max_depth parameter."""
    from code_indexer.server.mcp.handlers import handle_directory_tree

    result = await handle_directory_tree(
        {
            "repo_identifier": "test-tree-repo-global",
            "max_depth": 1,
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    # With max_depth=1, deeper directories should show [...]
    assert "[...]" in data["tree_string"]


@pytest.mark.asyncio
async def test_directory_tree_with_include_patterns(test_user, repo_with_tree_structure):
    """Test directory_tree with include_patterns filter."""
    from code_indexer.server.mcp.handlers import handle_directory_tree

    result = await handle_directory_tree(
        {
            "repo_identifier": "test-tree-repo-global",
            "include_patterns": ["*.py"],
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    # Should show .py files but not README.md
    assert "main.py" in data["tree_string"]
    assert "README.md" not in data["tree_string"]


@pytest.mark.asyncio
async def test_directory_tree_with_show_stats(test_user, repo_with_tree_structure):
    """Test directory_tree with show_stats enabled."""
    from code_indexer.server.mcp.handlers import handle_directory_tree

    result = await handle_directory_tree(
        {
            "repo_identifier": "test-tree-repo-global",
            "show_stats": True,
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    # Stats should appear in tree_string
    assert "directories" in data["tree_string"].lower()
    assert "files" in data["tree_string"].lower()


@pytest.mark.asyncio
async def test_directory_tree_validates_required_params(test_user):
    """Test directory_tree validates required parameters."""
    from code_indexer.server.mcp.handlers import handle_directory_tree

    # Missing repo_identifier
    result = await handle_directory_tree({}, test_user)

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "repo_identifier" in data["error"].lower()


@pytest.mark.asyncio
async def test_directory_tree_handles_invalid_repo(test_user, repo_with_tree_structure):
    """Test directory_tree handles nonexistent repository."""
    from code_indexer.server.mcp.handlers import handle_directory_tree

    result = await handle_directory_tree(
        {"repo_identifier": "nonexistent-repo"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "error" in data


@pytest.mark.asyncio
async def test_directory_tree_handles_invalid_path(test_user, repo_with_tree_structure):
    """Test directory_tree handles nonexistent subdirectory path."""
    from code_indexer.server.mcp.handlers import handle_directory_tree

    result = await handle_directory_tree(
        {
            "repo_identifier": "test-tree-repo-global",
            "path": "nonexistent-dir",
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "error" in data

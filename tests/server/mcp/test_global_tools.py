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
    from code_indexer.server import app as app_module

    # Create test directory structure
    golden_repos_dir = tmp_path / "golden-repos"
    golden_repos_dir.mkdir()

    # Set environment variable so handlers use this directory
    monkeypatch.setenv("GOLDEN_REPOS_DIR", str(golden_repos_dir))

    # Set app.state.golden_repos_dir to avoid RuntimeError in handlers
    app_module.app.state.golden_repos_dir = str(golden_repos_dir)

    # Create global registry and register a test repo
    registry = GlobalRegistry(str(golden_repos_dir))
    test_repo_path = tmp_path / "test-repo"
    test_repo_path.mkdir()

    registry.register_global_repo(
        "test-repo",
        "test-repo-global",
        "http://example.com/test.git",
        str(test_repo_path),
        allow_reserved=False,
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
async def test_global_repo_status_includes_enable_temporal_false(
    test_user, tmp_path, monkeypatch
):
    """Test global_repo_status includes enable_temporal=False when not enabled."""
    from code_indexer.global_repos.global_registry import GlobalRegistry
    from code_indexer.server import app as app_module

    # Create test directory structure
    golden_repos_dir = tmp_path / "golden-repos"
    golden_repos_dir.mkdir()
    monkeypatch.setenv("GOLDEN_REPOS_DIR", str(golden_repos_dir))
    app_module.app.state.golden_repos_dir = str(golden_repos_dir)

    # Register repo WITHOUT enable_temporal
    registry = GlobalRegistry(str(golden_repos_dir))
    test_repo_path = tmp_path / "test-repo"
    test_repo_path.mkdir()
    registry.register_global_repo(
        "test-repo",
        "test-repo-global",
        "http://example.com/test.git",
        str(test_repo_path),
        enable_temporal=False,
    )

    result = await handle_global_repo_status({"alias": "test-repo-global"}, test_user)
    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "enable_temporal" in data
    assert data["enable_temporal"] is False


@pytest.mark.asyncio
async def test_global_repo_status_includes_enable_temporal_true(
    test_user, tmp_path, monkeypatch
):
    """Test global_repo_status includes enable_temporal=True when enabled."""
    from code_indexer.global_repos.global_registry import GlobalRegistry
    from code_indexer.server import app as app_module

    # Create test directory structure
    golden_repos_dir = tmp_path / "golden-repos"
    golden_repos_dir.mkdir()
    monkeypatch.setenv("GOLDEN_REPOS_DIR", str(golden_repos_dir))
    app_module.app.state.golden_repos_dir = str(golden_repos_dir)

    # Register repo WITH enable_temporal
    registry = GlobalRegistry(str(golden_repos_dir))
    test_repo_path = tmp_path / "test-repo"
    test_repo_path.mkdir()
    registry.register_global_repo(
        "test-repo",
        "test-repo-global",
        "http://example.com/test.git",
        str(test_repo_path),
        enable_temporal=True,
        temporal_options={"max_commits": 100},
    )

    result = await handle_global_repo_status({"alias": "test-repo-global"}, test_user)
    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "enable_temporal" in data
    assert data["enable_temporal"] is True


@pytest.mark.asyncio
async def test_global_repo_status_defaults_enable_temporal_to_false(
    test_user, tmp_path, monkeypatch
):
    """Test global_repo_status defaults enable_temporal to False for legacy repos."""
    from code_indexer.global_repos.global_registry import GlobalRegistry
    from code_indexer.server import app as app_module

    # Create test directory structure
    golden_repos_dir = tmp_path / "golden-repos"
    golden_repos_dir.mkdir()
    monkeypatch.setenv("GOLDEN_REPOS_DIR", str(golden_repos_dir))
    app_module.app.state.golden_repos_dir = str(golden_repos_dir)

    # Manually create registry entry WITHOUT enable_temporal field (legacy repo)
    registry = GlobalRegistry(str(golden_repos_dir))
    test_repo_path = tmp_path / "test-repo"
    test_repo_path.mkdir()

    # Manually manipulate registry to simulate legacy repo
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    registry._registry_data["test-repo-global"] = {
        "repo_name": "test-repo",
        "alias_name": "test-repo-global",
        "repo_url": "http://example.com/test.git",
        "index_path": str(test_repo_path),
        "created_at": now,
        "last_refresh": now,
        # enable_temporal field intentionally missing
    }
    registry._save_registry()

    result = await handle_global_repo_status({"alias": "test-repo-global"}, test_user)
    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "enable_temporal" in data
    assert data["enable_temporal"] is False


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


# Tests for regex_search tool (Story #553)
@pytest.fixture
def repo_with_files(tmp_path, monkeypatch):
    """Setup test environment with a repo containing searchable files."""
    from code_indexer.global_repos.global_registry import GlobalRegistry
    from code_indexer.server import app as app_module

    # Create test directory structure
    golden_repos_dir = tmp_path / "golden-repos"
    golden_repos_dir.mkdir()

    # Set app.state.golden_repos_dir
    monkeypatch.setenv("GOLDEN_REPOS_DIR", str(golden_repos_dir))
    app_module.app.state.golden_repos_dir = str(golden_repos_dir)

    # Create test repo with files
    test_repo_path = tmp_path / "test-repo"
    test_repo_path.mkdir()
    (test_repo_path / "src").mkdir()
    (test_repo_path / "src" / "main.py").write_text(
        "def authenticate_user(username, password):\n" "    return True\n"
    )
    (test_repo_path / "src" / "utils.py").write_text(
        "def helper_function():\n" "    pass\n"
    )

    # Register in global registry
    registry = GlobalRegistry(str(golden_repos_dir))
    registry.register_global_repo(
        "test-repo",
        "test-repo-global",
        "http://example.com/test.git",
        str(test_repo_path),
    )

    return {"golden_repos_dir": golden_repos_dir, "repo_path": test_repo_path}


@pytest.mark.asyncio
async def test_regex_search_returns_matches(test_user, repo_with_files):
    """Test regex_search returns matching results."""
    from code_indexer.server.mcp.handlers import handle_regex_search

    result = await handle_regex_search(
        {"repo_identifier": "test-repo-global", "pattern": "def.*user"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "matches" in data
    assert data["total_matches"] >= 1
    assert data["search_engine"] in ("ripgrep", "grep")


@pytest.mark.asyncio
async def test_regex_search_handles_invalid_repo(test_user, repo_with_files):
    """Test regex_search handles nonexistent repository."""
    from code_indexer.server.mcp.handlers import handle_regex_search

    result = await handle_regex_search(
        {"repo_identifier": "nonexistent-repo", "pattern": "def"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "error" in data


@pytest.mark.asyncio
async def test_regex_search_validates_required_params(test_user):
    """Test regex_search validates required parameters."""
    from code_indexer.server.mcp.handlers import handle_regex_search

    # Missing pattern
    result = await handle_regex_search(
        {"repo_identifier": "test-repo-global"},
        test_user,
    )
    data = json.loads(result["content"][0]["text"])
    assert data["success"] is False
    assert "pattern" in data["error"].lower()

    # Missing repo_identifier
    result = await handle_regex_search(
        {"pattern": "def"},
        test_user,
    )
    data = json.loads(result["content"][0]["text"])
    assert data["success"] is False
    assert "repo_identifier" in data["error"].lower()


@pytest.mark.asyncio
async def test_regex_search_with_path_filter(test_user, repo_with_files):
    """Test regex_search with path subdirectory filter."""
    from code_indexer.server.mcp.handlers import handle_regex_search

    result = await handle_regex_search(
        {
            "repo_identifier": "test-repo-global",
            "pattern": "def",
            "path": "src",
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])
    assert data["success"] is True


@pytest.mark.asyncio
async def test_regex_search_with_include_patterns(test_user, repo_with_files):
    """Test regex_search with include glob patterns."""
    from code_indexer.server.mcp.handlers import handle_regex_search

    result = await handle_regex_search(
        {
            "repo_identifier": "test-repo-global",
            "pattern": "def",
            "include_patterns": ["*.py"],
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])
    assert data["success"] is True


# Tests for git exploration tools (Story #554)
@pytest.fixture
def git_repo_with_commits(tmp_path, monkeypatch):
    """Setup test environment with a git repo containing commits."""
    import subprocess
    from code_indexer.global_repos.global_registry import GlobalRegistry
    from code_indexer.server import app as app_module

    # Create test directory structure
    golden_repos_dir = tmp_path / "golden-repos"
    golden_repos_dir.mkdir()

    # Set app.state.golden_repos_dir
    monkeypatch.setenv("GOLDEN_REPOS_DIR", str(golden_repos_dir))
    app_module.app.state.golden_repos_dir = str(golden_repos_dir)

    # Create test git repo with commits
    test_repo_path = tmp_path / "test-repo"
    test_repo_path.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=test_repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=test_repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=test_repo_path,
        capture_output=True,
        check=True,
    )

    # Create initial commit
    (test_repo_path / "main.py").write_text("def main():\n    pass\n")
    subprocess.run(["git", "add", "."], cwd=test_repo_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=test_repo_path,
        capture_output=True,
    )

    # Create second commit
    (test_repo_path / "utils.py").write_text("def helper():\n    pass\n")
    subprocess.run(["git", "add", "."], cwd=test_repo_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add utils"],
        cwd=test_repo_path,
        capture_output=True,
    )

    # Get commit hashes
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=test_repo_path,
        capture_output=True,
        text=True,
    )
    head_hash = result.stdout.strip()

    result = subprocess.run(
        ["git", "rev-parse", "HEAD~1"],
        cwd=test_repo_path,
        capture_output=True,
        text=True,
    )
    first_hash = result.stdout.strip()

    # Register in global registry
    registry = GlobalRegistry(str(golden_repos_dir))
    registry.register_global_repo(
        "test-repo",
        "test-repo-global",
        "http://example.com/test.git",
        str(test_repo_path),
    )

    return {
        "golden_repos_dir": golden_repos_dir,
        "repo_path": test_repo_path,
        "head_hash": head_hash,
        "first_hash": first_hash,
    }


@pytest.mark.asyncio
async def test_git_log_returns_commits(test_user, git_repo_with_commits):
    """Test git_log returns commit history."""
    from code_indexer.server.mcp.handlers import handle_git_log

    result = await handle_git_log(
        {"repo_identifier": "test-repo-global"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "commits" in data
    assert len(data["commits"]) == 2


@pytest.mark.asyncio
async def test_git_log_respects_limit(test_user, git_repo_with_commits):
    """Test git_log respects the limit parameter."""
    from code_indexer.server.mcp.handlers import handle_git_log

    result = await handle_git_log(
        {"repo_identifier": "test-repo-global", "limit": 1},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert len(data["commits"]) == 1
    assert data["truncated"] is True


@pytest.mark.asyncio
async def test_git_log_filter_by_path(test_user, git_repo_with_commits):
    """Test git_log filters by path."""
    from code_indexer.server.mcp.handlers import handle_git_log

    result = await handle_git_log(
        {"repo_identifier": "test-repo-global", "path": "main.py"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert len(data["commits"]) == 1
    assert data["commits"][0]["subject"] == "Initial commit"


@pytest.mark.asyncio
async def test_git_log_handles_invalid_repo(test_user, git_repo_with_commits):
    """Test git_log handles nonexistent repository."""
    from code_indexer.server.mcp.handlers import handle_git_log

    result = await handle_git_log(
        {"repo_identifier": "nonexistent-repo"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "error" in data


@pytest.mark.asyncio
async def test_git_log_validates_required_params(test_user):
    """Test git_log validates required parameters."""
    from code_indexer.server.mcp.handlers import handle_git_log

    result = await handle_git_log({}, test_user)

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "repo_identifier" in data["error"].lower()


@pytest.mark.asyncio
async def test_git_show_commit_returns_details(test_user, git_repo_with_commits):
    """Test git_show_commit returns commit details."""
    from code_indexer.server.mcp.handlers import handle_git_show_commit

    result = await handle_git_show_commit(
        {
            "repo_identifier": "test-repo-global",
            "commit_hash": git_repo_with_commits["head_hash"],
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "commit" in data
    assert data["commit"]["subject"] == "Add utils"


@pytest.mark.asyncio
async def test_git_show_commit_includes_stats(test_user, git_repo_with_commits):
    """Test git_show_commit includes file change stats."""
    from code_indexer.server.mcp.handlers import handle_git_show_commit

    result = await handle_git_show_commit(
        {
            "repo_identifier": "test-repo-global",
            "commit_hash": git_repo_with_commits["head_hash"],
            "include_stats": True,
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "stats" in data
    assert len(data["stats"]) == 1
    assert data["stats"][0]["path"] == "utils.py"


@pytest.mark.asyncio
async def test_git_show_commit_includes_diff(test_user, git_repo_with_commits):
    """Test git_show_commit can include diff."""
    from code_indexer.server.mcp.handlers import handle_git_show_commit

    result = await handle_git_show_commit(
        {
            "repo_identifier": "test-repo-global",
            "commit_hash": git_repo_with_commits["head_hash"],
            "include_diff": True,
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "diff" in data
    assert data["diff"] is not None
    assert "def helper" in data["diff"]


@pytest.mark.asyncio
async def test_git_show_commit_handles_invalid_hash(test_user, git_repo_with_commits):
    """Test git_show_commit handles invalid commit hash."""
    from code_indexer.server.mcp.handlers import handle_git_show_commit

    result = await handle_git_show_commit(
        {
            "repo_identifier": "test-repo-global",
            "commit_hash": "0000000000000000000000000000000000000000",
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "error" in data


@pytest.mark.asyncio
async def test_git_show_commit_validates_required_params(test_user):
    """Test git_show_commit validates required parameters."""
    from code_indexer.server.mcp.handlers import handle_git_show_commit

    # Missing commit_hash
    result = await handle_git_show_commit(
        {"repo_identifier": "test-repo-global"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "commit_hash" in data["error"].lower()


@pytest.mark.asyncio
async def test_git_file_at_revision_returns_content(test_user, git_repo_with_commits):
    """Test git_file_at_revision returns file content."""
    from code_indexer.server.mcp.handlers import handle_git_file_at_revision

    result = await handle_git_file_at_revision(
        {
            "repo_identifier": "test-repo-global",
            "path": "main.py",
            "revision": git_repo_with_commits["head_hash"],
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "content" in data
    assert "def main" in data["content"]


@pytest.mark.asyncio
async def test_git_file_at_revision_different_versions(test_user, git_repo_with_commits):
    """Test git_file_at_revision returns correct content for different versions."""
    from code_indexer.server.mcp.handlers import handle_git_file_at_revision
    import subprocess

    # Modify main.py and commit
    repo_path = git_repo_with_commits["repo_path"]
    (repo_path / "main.py").write_text("def main():\n    print('updated')\n")
    subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Update main"],
        cwd=repo_path,
        capture_output=True,
    )

    # Get old version
    old_result = await handle_git_file_at_revision(
        {
            "repo_identifier": "test-repo-global",
            "path": "main.py",
            "revision": git_repo_with_commits["head_hash"],
        },
        test_user,
    )

    old_data = json.loads(old_result["content"][0]["text"])

    # Get new version
    new_result = await handle_git_file_at_revision(
        {
            "repo_identifier": "test-repo-global",
            "path": "main.py",
            "revision": "HEAD",
        },
        test_user,
    )

    new_data = json.loads(new_result["content"][0]["text"])

    assert old_data["success"] is True
    assert new_data["success"] is True
    assert "pass" in old_data["content"]
    assert "updated" in new_data["content"]


@pytest.mark.asyncio
async def test_git_file_at_revision_handles_invalid_file(
    test_user, git_repo_with_commits
):
    """Test git_file_at_revision handles nonexistent file."""
    from code_indexer.server.mcp.handlers import handle_git_file_at_revision

    result = await handle_git_file_at_revision(
        {
            "repo_identifier": "test-repo-global",
            "path": "nonexistent.py",
            "revision": "HEAD",
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "error" in data


@pytest.mark.asyncio
async def test_git_file_at_revision_validates_required_params(test_user):
    """Test git_file_at_revision validates required parameters."""
    from code_indexer.server.mcp.handlers import handle_git_file_at_revision

    # Missing path
    result = await handle_git_file_at_revision(
        {"repo_identifier": "test-repo-global", "revision": "HEAD"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "path" in data["error"].lower()


# Story #555: Git Diff and Blame Tests
@pytest.fixture
def git_repo_with_diff_history(tmp_path, monkeypatch):
    """Create git repo with multiple commits for diff testing."""
    import subprocess
    from code_indexer.global_repos.global_registry import GlobalRegistry
    from code_indexer.server import app as app_module

    # Create golden repos directory
    golden_repos_dir = tmp_path / "golden-repos"
    golden_repos_dir.mkdir()

    # Set app state
    app_module.app.state.golden_repos_dir = str(golden_repos_dir)

    # Create test repository with history
    repo_path = tmp_path / "test-diff-repo"
    repo_path.mkdir()

    subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        capture_output=True,
    )

    # First commit - initial file
    (repo_path / "file.py").write_text("def hello():\n    pass\n")
    subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        capture_output=True,
    )
    first_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    first_hash = first_result.stdout.strip()

    # Second commit - modify file
    (repo_path / "file.py").write_text("def hello():\n    print('hello')\n\ndef world():\n    pass\n")
    subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add print and world function"],
        cwd=repo_path,
        capture_output=True,
    )
    second_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    second_hash = second_result.stdout.strip()

    # Register global repo
    registry = GlobalRegistry(str(golden_repos_dir))
    registry.register_global_repo(
        "test-diff-repo",
        "test-diff-repo-global",
        "http://example.com/test-diff.git",
        str(repo_path),
        allow_reserved=False,
    )

    return {
        "repo_path": repo_path,
        "golden_repos_dir": golden_repos_dir,
        "first_hash": first_hash,
        "second_hash": second_hash,
    }


@pytest.mark.asyncio
async def test_git_diff_handler_returns_diff(test_user, git_repo_with_diff_history):
    """Test git_diff handler returns diff between revisions."""
    from code_indexer.server.mcp.handlers import handle_git_diff

    result = await handle_git_diff(
        {
            "repo_identifier": "test-diff-repo-global",
            "from_revision": git_repo_with_diff_history["first_hash"],
            "to_revision": git_repo_with_diff_history["second_hash"],
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "files" in data
    assert len(data["files"]) > 0
    assert data["total_insertions"] > 0


@pytest.mark.asyncio
async def test_git_diff_handler_validates_required_params(test_user):
    """Test git_diff handler validates required parameters."""
    from code_indexer.server.mcp.handlers import handle_git_diff

    # Missing from_revision
    result = await handle_git_diff(
        {"repo_identifier": "test-repo-global"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "from_revision" in data["error"].lower()


@pytest.mark.asyncio
async def test_git_blame_handler_returns_annotations(test_user, git_repo_with_diff_history):
    """Test git_blame handler returns blame annotations."""
    from code_indexer.server.mcp.handlers import handle_git_blame

    result = await handle_git_blame(
        {
            "repo_identifier": "test-diff-repo-global",
            "path": "file.py",
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "lines" in data
    assert len(data["lines"]) > 0
    assert "unique_commits" in data


@pytest.mark.asyncio
async def test_git_blame_handler_validates_required_params(test_user):
    """Test git_blame handler validates required parameters."""
    from code_indexer.server.mcp.handlers import handle_git_blame

    # Missing path
    result = await handle_git_blame(
        {"repo_identifier": "test-repo-global"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "path" in data["error"].lower()


@pytest.mark.asyncio
async def test_git_file_history_handler_returns_commits(test_user, git_repo_with_diff_history):
    """Test git_file_history handler returns commit history."""
    from code_indexer.server.mcp.handlers import handle_git_file_history

    result = await handle_git_file_history(
        {
            "repo_identifier": "test-diff-repo-global",
            "path": "file.py",
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "commits" in data
    assert len(data["commits"]) == 2  # Two commits modifying file.py
    assert "total_count" in data


@pytest.mark.asyncio
async def test_git_file_history_handler_validates_required_params(test_user):
    """Test git_file_history handler validates required parameters."""
    from code_indexer.server.mcp.handlers import handle_git_file_history

    # Missing path
    result = await handle_git_file_history(
        {"repo_identifier": "test-repo-global"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "path" in data["error"].lower()


# Story #556: Git Content Search Tests
@pytest.fixture
def git_repo_with_searchable_commits(tmp_path, monkeypatch):
    """Create git repo with commits containing searchable content."""
    import subprocess
    from code_indexer.global_repos.global_registry import GlobalRegistry
    from code_indexer.server import app as app_module

    # Create golden repos directory
    golden_repos_dir = tmp_path / "golden-repos"
    golden_repos_dir.mkdir()

    # Set app state
    app_module.app.state.golden_repos_dir = str(golden_repos_dir)

    # Create test repository
    repo_path = tmp_path / "test-search-repo"
    repo_path.mkdir()

    subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        capture_output=True,
    )

    # First commit - fix a bug
    (repo_path / "auth.py").write_text("def authenticate():\n    pass\n")
    subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Fix authentication bug in login flow"],
        cwd=repo_path,
        capture_output=True,
    )

    # Second commit - add feature
    (repo_path / "auth.py").write_text(
        "def authenticate():\n    return True\n\ndef validate_token(token):\n    pass\n"
    )
    subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add token validation feature"],
        cwd=repo_path,
        capture_output=True,
    )

    # Third commit - refactor
    (repo_path / "auth.py").write_text(
        "def authenticate():\n    return True\n\ndef validate_token(token):\n    return token is not None\n"
    )
    subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Refactor token validation logic"],
        cwd=repo_path,
        capture_output=True,
    )

    # Register global repo
    registry = GlobalRegistry(str(golden_repos_dir))
    registry.register_global_repo(
        "test-search-repo",
        "test-search-repo-global",
        "http://example.com/test-search.git",
        str(repo_path),
        allow_reserved=False,
    )

    return {
        "repo_path": repo_path,
        "golden_repos_dir": golden_repos_dir,
    }


@pytest.mark.asyncio
async def test_git_search_commits_returns_matches(test_user, git_repo_with_searchable_commits):
    """Test git_search_commits returns matching commits."""
    from code_indexer.server.mcp.handlers import handle_git_search_commits

    result = await handle_git_search_commits(
        {
            "repo_identifier": "test-search-repo-global",
            "query": "authentication",
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "matches" in data
    assert data["total_matches"] >= 1
    assert any("authentication" in m["subject"].lower() for m in data["matches"])


@pytest.mark.asyncio
async def test_git_search_commits_with_regex(test_user, git_repo_with_searchable_commits):
    """Test git_search_commits with regex pattern."""
    from code_indexer.server.mcp.handlers import handle_git_search_commits

    result = await handle_git_search_commits(
        {
            "repo_identifier": "test-search-repo-global",
            "query": "Fix.*bug",
            "is_regex": True,
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert data["is_regex"] is True
    assert data["total_matches"] >= 1


@pytest.mark.asyncio
async def test_git_search_commits_validates_required_params(test_user):
    """Test git_search_commits validates required parameters."""
    from code_indexer.server.mcp.handlers import handle_git_search_commits

    # Missing query
    result = await handle_git_search_commits(
        {"repo_identifier": "test-repo-global"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "query" in data["error"].lower()

    # Missing repo_identifier
    result = await handle_git_search_commits(
        {"query": "test"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "repo_identifier" in data["error"].lower()


@pytest.mark.asyncio
async def test_git_search_commits_handles_invalid_repo(test_user, git_repo_with_searchable_commits):
    """Test git_search_commits handles nonexistent repository."""
    from code_indexer.server.mcp.handlers import handle_git_search_commits

    result = await handle_git_search_commits(
        {"repo_identifier": "nonexistent-repo", "query": "test"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "error" in data


@pytest.mark.asyncio
async def test_git_search_commits_respects_limit(test_user, git_repo_with_searchable_commits):
    """Test git_search_commits respects limit parameter."""
    from code_indexer.server.mcp.handlers import handle_git_search_commits

    result = await handle_git_search_commits(
        {
            "repo_identifier": "test-search-repo-global",
            "query": ".",  # Match all commits (regex)
            "is_regex": True,
            "limit": 1,
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert len(data["matches"]) <= 1


@pytest.mark.asyncio
async def test_git_search_diffs_returns_matches(test_user, git_repo_with_searchable_commits):
    """Test git_search_diffs returns commits that introduced/removed the search term."""
    from code_indexer.server.mcp.handlers import handle_git_search_diffs

    result = await handle_git_search_diffs(
        {
            "repo_identifier": "test-search-repo-global",
            "search_string": "validate_token",
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "matches" in data
    assert data["total_matches"] >= 1


@pytest.mark.asyncio
async def test_git_search_diffs_with_regex(test_user, git_repo_with_searchable_commits):
    """Test git_search_diffs with regex pattern."""
    from code_indexer.server.mcp.handlers import handle_git_search_diffs

    result = await handle_git_search_diffs(
        {
            "repo_identifier": "test-search-repo-global",
            "search_pattern": "def.*token",
            "is_regex": True,
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert data["is_regex"] is True


@pytest.mark.asyncio
async def test_git_search_diffs_validates_required_params(test_user):
    """Test git_search_diffs validates required parameters."""
    from code_indexer.server.mcp.handlers import handle_git_search_diffs

    # Missing search_string/search_pattern
    result = await handle_git_search_diffs(
        {"repo_identifier": "test-repo-global"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "search_string" in data["error"].lower() or "search_pattern" in data["error"].lower()

    # Missing repo_identifier
    result = await handle_git_search_diffs(
        {"search_string": "test"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "repo_identifier" in data["error"].lower()


@pytest.mark.asyncio
async def test_git_search_diffs_handles_invalid_repo(test_user, git_repo_with_searchable_commits):
    """Test git_search_diffs handles nonexistent repository."""
    from code_indexer.server.mcp.handlers import handle_git_search_diffs

    result = await handle_git_search_diffs(
        {"repo_identifier": "nonexistent-repo", "search_string": "test"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is False
    assert "error" in data


@pytest.mark.asyncio
async def test_git_search_diffs_with_path_filter(test_user, git_repo_with_searchable_commits):
    """Test git_search_diffs with path filter."""
    from code_indexer.server.mcp.handlers import handle_git_search_diffs

    result = await handle_git_search_diffs(
        {
            "repo_identifier": "test-search-repo-global",
            "search_string": "def",
            "path": "auth.py",
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True


@pytest.mark.asyncio
async def test_git_search_diffs_returns_match_structure(test_user, git_repo_with_searchable_commits):
    """Test git_search_diffs returns properly structured matches."""
    from code_indexer.server.mcp.handlers import handle_git_search_diffs

    result = await handle_git_search_diffs(
        {
            "repo_identifier": "test-search-repo-global",
            "search_string": "validate_token",
        },
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    assert data["success"] is True
    assert "matches" in data
    assert "total_matches" in data
    assert "truncated" in data
    assert "search_time_ms" in data
    if data["total_matches"] > 0:
        match = data["matches"][0]
        assert "hash" in match
        assert "short_hash" in match
        assert "author_name" in match
        assert "author_date" in match
        assert "subject" in match
        assert "files_changed" in match
        # diff_snippet is optional (may be None)
        assert "diff_snippet" in match

# Test for _resolve_repo_path bug fix (Story #554 follow-up)
@pytest.fixture
def production_style_repo_layout(tmp_path, monkeypatch):
    """Setup production-style directory layout where index_path != git_repo_path.

    In production:
    - index_path: .cidx-server/data/golden-repos/{name} (vector index, NO .git)
    - git_repo: .cidx-server/golden-repos/{name} (actual git repo WITH .git)
    """
    import subprocess
    from code_indexer.global_repos.global_registry import GlobalRegistry
    from code_indexer.server import app as app_module

    # Create directory structure mimicking production
    cidx_server_dir = tmp_path / ".cidx-server"
    data_dir = cidx_server_dir / "data"
    golden_repos_data = data_dir / "golden-repos"
    golden_repos_data.mkdir(parents=True)

    golden_repos_actual = cidx_server_dir / "golden-repos"
    golden_repos_actual.mkdir(parents=True)

    # Set app state to use data/golden-repos (vector index location)
    monkeypatch.setenv("GOLDEN_REPOS_DIR", str(golden_repos_data))
    app_module.app.state.golden_repos_dir = str(golden_repos_data)

    # Create actual git repo in golden-repos/{name}
    git_repo_path = golden_repos_actual / "test-prod-repo"
    git_repo_path.mkdir()

    subprocess.run(["git", "init"], cwd=git_repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=git_repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=git_repo_path,
        capture_output=True,
        check=True,
    )

    # Create a commit
    (git_repo_path / "main.py").write_text("def production():\n    pass\n")
    subprocess.run(["git", "add", "."], cwd=git_repo_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Production commit"],
        cwd=git_repo_path,
        capture_output=True,
    )

    # Create vector index directory (NO .git here - this is the bug scenario)
    index_path = golden_repos_data / "test-prod-repo"
    index_path.mkdir()
    # Add some dummy index files to make it look like a vector index
    (index_path / "metadata.json").write_text('{"indexed": true}')

    # Register in global registry with index_path pointing to data/golden-repos
    # (which does NOT have .git)
    registry = GlobalRegistry(str(golden_repos_data))
    registry.register_global_repo(
        "test-prod-repo",
        "test-prod-repo-global",
        "http://example.com/test-prod.git",
        str(index_path),  # This points to vector index, NOT git repo
    )

    return {
        "golden_repos_dir": golden_repos_data,
        "git_repo_path": git_repo_path,
        "index_path": index_path,
    }


@pytest.mark.asyncio
async def test_resolve_repo_path_finds_git_repo_in_alternate_location(
    test_user, production_style_repo_layout
):
    """Test _resolve_repo_path finds actual git repo when index_path has no .git.

    This validates the bug fix where index_path points to vector index storage
    (without .git) and the actual git repo is in a different location.
    """
    from code_indexer.server.mcp.handlers import handle_git_log

    # Try to use git_log - this should find the actual git repo despite
    # index_path not being a git repo
    result = await handle_git_log(
        {"repo_identifier": "test-prod-repo-global"},
        test_user,
    )

    data = json.loads(result["content"][0]["text"])

    # Should succeed and find commits
    assert data["success"] is True
    assert "commits" in data
    assert len(data["commits"]) == 1
    assert data["commits"][0]["subject"] == "Production commit"


# Test for cidx_quick_reference tool (documentation-only tool)
def test_cidx_quick_reference_in_registry():
    """Test cidx_quick_reference tool is registered in TOOL_REGISTRY with correct schema."""
    from code_indexer.server.mcp.tools import TOOL_REGISTRY

    assert "cidx_quick_reference" in TOOL_REGISTRY

    tool = TOOL_REGISTRY["cidx_quick_reference"]

    # Verify required fields
    assert tool["name"] == "cidx_quick_reference"
    assert "description" in tool
    assert "CIDX Quick Reference" in tool["description"]
    assert "inputSchema" in tool
    assert "outputSchema" in tool
    assert "required_permission" in tool
    assert tool["required_permission"] == "query_repos"

    # Verify inputSchema (no inputs required)
    assert tool["inputSchema"]["type"] == "object"
    assert tool["inputSchema"]["properties"] == {}
    assert tool["inputSchema"]["required"] == []

    # Verify outputSchema structure
    assert tool["outputSchema"]["type"] == "object"
    assert "success" in tool["outputSchema"]["properties"]
    assert "reference" in tool["outputSchema"]["properties"]
    assert tool["outputSchema"]["required"] == ["success", "reference"]

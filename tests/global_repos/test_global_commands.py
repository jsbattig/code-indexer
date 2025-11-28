"""
Tests for 'cidx global list' and 'cidx global status' commands.

Tests Story #524 AC4 & AC5:
- AC4: 'cidx global list' shows all registered repos
- AC5: 'cidx global status' shows catalog freshness indicator
"""

import subprocess


from code_indexer.global_repos.global_registry import GlobalRegistry


class TestGlobalListCommand:
    """Test 'cidx global list' command for catalog completeness verification."""

    def test_global_list_shows_all_registered_repos(self, tmp_path):
        """Test that 'cidx global list' shows all registered global repos."""
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        # Pre-register multiple repos
        registry = GlobalRegistry(str(golden_repos_dir))
        repos = [
            {
                "repo_name": "auth-service",
                "alias_name": "auth-service-global",
                "repo_url": "https://github.com/org/auth-service",
                "index_path": str(tmp_path / "auth-service"),
            },
            {
                "repo_name": "user-management",
                "alias_name": "user-management-global",
                "repo_url": "https://github.com/org/user-management",
                "index_path": str(tmp_path / "user-management"),
            },
            {
                "repo_name": "api-gateway",
                "alias_name": "api-gateway-global",
                "repo_url": "https://github.com/org/api-gateway",
                "index_path": str(tmp_path / "api-gateway"),
            },
        ]

        for repo in repos:
            registry.register_global_repo(**repo)

        # Run CLI command
        env = {"CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir)}
        result = subprocess.run(
            ["cidx", "global", "list"],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )

        # Command should succeed
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Verify output contains all repos
        output = result.stdout
        assert "auth-service-global" in output
        assert "user-management-global" in output
        assert "api-gateway-global" in output

        # Should show count
        assert "3" in output or "three" in output.lower()

    def test_global_list_shows_empty_when_no_repos(self, tmp_path):
        """Test that 'cidx global list' handles empty registry gracefully."""
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        # Initialize empty registry
        GlobalRegistry(str(golden_repos_dir))

        # Run CLI command
        env = {"CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir)}
        result = subprocess.run(
            ["cidx", "global", "list"],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )

        # Command should succeed
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Verify output indicates empty
        output = result.stdout.lower()
        assert any(
            phrase in output
            for phrase in [
                "no repos",
                "no global",
                "0 repos",
                "empty",
                "none registered",
            ]
        )

    def test_global_list_includes_repo_url(self, tmp_path):
        """Test that 'cidx global list' includes repo URLs in output."""
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        registry = GlobalRegistry(str(golden_repos_dir))
        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(tmp_path / "test-repo"),
        )

        env = {"CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir)}
        result = subprocess.run(
            ["cidx", "global", "list"],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )

        assert result.returncode == 0
        # URL may be truncated in table, so check for domain at least
        assert "github.com" in result.stdout or "https://" in result.stdout

    def test_global_list_shows_repo_with_no_url(self, tmp_path):
        """Test that repos with repo_url=None display correctly."""
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        registry = GlobalRegistry(str(golden_repos_dir))
        # Register a local-only repo (not a reserved name)
        registry.register_global_repo(
            repo_name="local-repo",
            alias_name="local-repo-global",
            repo_url=None,
            index_path=str(tmp_path / "local-repo"),
        )

        env = {"CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir)}
        result = subprocess.run(
            ["cidx", "global", "list"],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )

        assert result.returncode == 0
        output = result.stdout
        assert "local-repo-global" in output
        # Should indicate no URL somehow (N/A, None, local, etc.)
        assert any(
            marker in output.lower() for marker in ["n/a", "none", "(local)", "local"]
        )


class TestGlobalStatusCommand:
    """Test 'cidx global status' command for catalog freshness indicator."""

    def test_global_status_shows_repo_metadata(self, tmp_path):
        """Test that 'cidx global status <alias>' shows repo metadata."""
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        registry = GlobalRegistry(str(golden_repos_dir))
        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(tmp_path / "test-repo"),
        )

        env = {"CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir)}
        result = subprocess.run(
            ["cidx", "global", "status", "test-repo-global"],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        output = result.stdout
        assert "test-repo-global" in output
        assert "https://github.com/org/test-repo" in output

    def test_global_status_shows_last_refresh_timestamp(self, tmp_path):
        """Test that status shows last_refresh timestamp (AC5)."""
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        registry = GlobalRegistry(str(golden_repos_dir))
        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(tmp_path / "test-repo"),
        )

        env = {"CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir)}
        result = subprocess.run(
            ["cidx", "global", "status", "test-repo-global"],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )

        assert result.returncode == 0
        output = result.stdout.lower()

        # Should show timestamp information
        assert any(
            word in output for word in ["refresh", "updated", "timestamp", "last"]
        )

        # Should show a timestamp (ISO format or human-readable)
        assert any(
            char in result.stdout
            for char in [":", "-", "T", "Z"]  # ISO timestamp chars
        )

    def test_global_status_shows_index_path(self, tmp_path):
        """Test that status shows the index_path for the repo."""
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        # Register test repo
        registry = GlobalRegistry(str(golden_repos_dir))
        test_index_path = str(tmp_path / "test-repo" / ".code-indexer" / "index")

        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=test_index_path,
        )

        env = {"CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir)}
        result = subprocess.run(
            ["cidx", "global", "status", "test-repo-global"],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )

        assert result.returncode == 0
        output = result.stdout.lower()

        # Should show index path or reference to storage
        assert any(word in output for word in ["index", "path", "location", "storage"])

    def test_global_status_nonexistent_repo_shows_error(self, tmp_path):
        """Test that status for nonexistent repo shows helpful error."""
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        GlobalRegistry(str(golden_repos_dir))

        env = {"CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir)}
        result = subprocess.run(
            ["cidx", "global", "status", "nonexistent-repo"],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )

        # Should fail
        assert result.returncode != 0

        # Should show helpful error
        error_output = (result.stderr + result.stdout).lower()
        assert "not found" in error_output or "does not exist" in error_output
        assert "nonexistent-repo" in error_output

    def test_global_status_shows_created_timestamp(self, tmp_path):
        """Test that status shows when repo was created."""
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        registry = GlobalRegistry(str(golden_repos_dir))
        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(tmp_path / "test-repo"),
        )

        env = {"CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir)}
        result = subprocess.run(
            ["cidx", "global", "status", "test-repo-global"],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
        )

        assert result.returncode == 0
        output = result.stdout.lower()

        # Should show creation info
        assert any(word in output for word in ["created", "registered", "added"])

"""End-to-end tests for proxy mode initialization command.

These tests execute the actual cidx init --proxy-mode command with zero mocking
to verify complete functionality from CLI to configuration creation.
"""

import json
import subprocess


class TestProxyModeInitCommand:
    """E2E tests for cidx init --proxy-mode command execution."""

    def test_init_proxy_mode_creates_configuration(self, tmp_path):
        """cidx init --proxy-mode creates proxy configuration structure."""
        proxy_dir = tmp_path / "my_proxy"
        proxy_dir.mkdir()

        # Execute real command
        result = subprocess.run(
            ["cidx", "init", "--proxy-mode"],
            cwd=proxy_dir,
            capture_output=True,
            text=True,
        )

        # Verify command succeeded
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        assert "Proxy mode initialized successfully" in result.stdout

        # Verify .code-indexer directory created
        config_dir = proxy_dir / ".code-indexer"
        assert config_dir.exists()
        assert config_dir.is_dir()

        # Verify config.json created
        config_file = config_dir / "config.json"
        assert config_file.exists()

    def test_init_proxy_mode_sets_proxy_flag_in_config(self, tmp_path):
        """config.json contains proxy_mode: true."""
        proxy_dir = tmp_path / "my_proxy"
        proxy_dir.mkdir()

        # Execute real command
        result = subprocess.run(
            ["cidx", "init", "--proxy-mode"],
            cwd=proxy_dir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Verify config contains proxy_mode flag
        config_file = proxy_dir / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        assert "proxy_mode" in config_data
        assert config_data["proxy_mode"] is True

    def test_init_proxy_mode_discovers_existing_repositories(self, tmp_path):
        """cidx init --proxy-mode discovers repositories in subdirectories."""
        proxy_dir = tmp_path / "my_proxy"
        proxy_dir.mkdir()

        # Create some repositories with .code-indexer directories
        for i in range(1, 4):
            repo = proxy_dir / f"repo{i}"
            repo.mkdir()
            (repo / ".code-indexer").mkdir()

        # Execute real command
        result = subprocess.run(
            ["cidx", "init", "--proxy-mode"],
            cwd=proxy_dir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Verify discovered repositories in config
        config_file = proxy_dir / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        assert "discovered_repos" in config_data
        discovered = set(config_data["discovered_repos"])
        assert discovered == {"repo1", "repo2", "repo3"}

        # Verify output shows discovered repos
        assert "Discovered 3 repositories" in result.stdout
        assert "repo1" in result.stdout
        assert "repo2" in result.stdout
        assert "repo3" in result.stdout

    def test_init_proxy_mode_fails_when_already_initialized(self, tmp_path):
        """cidx init --proxy-mode fails gracefully if already initialized."""
        proxy_dir = tmp_path / "my_proxy"
        proxy_dir.mkdir()

        # First initialization
        result1 = subprocess.run(
            ["cidx", "init", "--proxy-mode"],
            cwd=proxy_dir,
            capture_output=True,
            text=True,
        )
        assert result1.returncode == 0

        # Second initialization should fail
        result2 = subprocess.run(
            ["cidx", "init", "--proxy-mode"],
            cwd=proxy_dir,
            capture_output=True,
            text=True,
        )

        assert result2.returncode != 0
        assert "already initialized" in result2.stdout.lower()

    def test_init_proxy_mode_force_allows_reinitialization(self, tmp_path):
        """cidx init --proxy-mode --force allows overwriting existing config."""
        proxy_dir = tmp_path / "my_proxy"
        proxy_dir.mkdir()

        # Create old repository
        old_repo = proxy_dir / "old_repo"
        old_repo.mkdir()
        (old_repo / ".code-indexer").mkdir()

        # First initialization
        result1 = subprocess.run(
            ["cidx", "init", "--proxy-mode"],
            cwd=proxy_dir,
            capture_output=True,
            text=True,
        )
        assert result1.returncode == 0

        # Remove old repo and add new one
        import shutil

        shutil.rmtree(old_repo)
        new_repo = proxy_dir / "new_repo"
        new_repo.mkdir()
        (new_repo / ".code-indexer").mkdir()

        # Re-initialization with --force
        result2 = subprocess.run(
            ["cidx", "init", "--proxy-mode", "--force"],
            cwd=proxy_dir,
            capture_output=True,
            text=True,
        )

        assert result2.returncode == 0

        # Verify config updated with new repository
        config_file = proxy_dir / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        assert config_data["discovered_repos"] == ["new_repo"]
        assert "old_repo" not in config_data["discovered_repos"]

    def test_init_proxy_mode_prevents_nested_proxy(self, tmp_path):
        """cidx init --proxy-mode prevents creating nested proxy configurations."""
        # Create parent proxy
        parent_proxy = tmp_path / "parent_proxy"
        parent_proxy.mkdir()

        result1 = subprocess.run(
            ["cidx", "init", "--proxy-mode"],
            cwd=parent_proxy,
            capture_output=True,
            text=True,
        )
        assert result1.returncode == 0

        # Try to create child proxy (should fail)
        child_proxy = parent_proxy / "child_proxy"
        child_proxy.mkdir()

        result2 = subprocess.run(
            ["cidx", "init", "--proxy-mode"],
            cwd=child_proxy,
            capture_output=True,
            text=True,
        )

        assert result2.returncode != 0
        assert "nested proxy" in result2.stdout.lower()
        assert str(parent_proxy) in result2.stdout

        # Verify no config created in child
        assert not (child_proxy / ".code-indexer").exists()

    def test_init_proxy_mode_shows_success_message(self, tmp_path):
        """Command output contains clear success message."""
        proxy_dir = tmp_path / "my_proxy"
        proxy_dir.mkdir()

        result = subprocess.run(
            ["cidx", "init", "--proxy-mode"],
            cwd=proxy_dir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Proxy mode initialized successfully" in result.stdout
        assert "Configuration saved to" in result.stdout

    def test_init_proxy_mode_stores_relative_paths(self, tmp_path):
        """Config stores relative paths to repositories, not absolute."""
        proxy_dir = tmp_path / "my_proxy"
        proxy_dir.mkdir()

        # Create repository
        repo = proxy_dir / "myrepo"
        repo.mkdir()
        (repo / ".code-indexer").mkdir()

        # Execute command
        result = subprocess.run(
            ["cidx", "init", "--proxy-mode"],
            cwd=proxy_dir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        # Verify relative path stored
        config_file = proxy_dir / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        assert config_data["discovered_repos"] == ["myrepo"]
        # Verify it's not an absolute path
        assert not config_data["discovered_repos"][0].startswith("/")

    def test_init_proxy_mode_with_codebase_dir_option(self, tmp_path):
        """cidx init --proxy-mode --codebase-dir works correctly."""
        proxy_dir = tmp_path / "target_proxy"
        proxy_dir.mkdir()

        # Execute from different directory using --codebase-dir
        result = subprocess.run(
            ["cidx", "init", "--proxy-mode", "--codebase-dir", str(proxy_dir)],
            cwd=tmp_path,  # Run from parent directory
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        # Verify config created in target directory
        config_dir = proxy_dir / ".code-indexer"
        assert config_dir.exists()

        config_file = config_dir / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        assert config_data["proxy_mode"] is True

    def test_init_proxy_mode_handles_empty_directory(self, tmp_path):
        """cidx init --proxy-mode works in empty directory with no repositories."""
        proxy_dir = tmp_path / "empty_proxy"
        proxy_dir.mkdir()

        result = subprocess.run(
            ["cidx", "init", "--proxy-mode"],
            cwd=proxy_dir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Discovered 0 repositories" in result.stdout
        assert "No repositories found" in result.stdout

        # Verify config created with empty discovered_repos
        config_file = proxy_dir / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        assert config_data["discovered_repos"] == []


class TestProxyModeIntegrationScenarios:
    """Integration scenarios testing realistic proxy mode usage."""

    def test_proxy_mode_full_workflow(self, tmp_path):
        """Complete workflow: initialize proxy, discover repos, verify structure."""
        # Step 1: Create workspace structure
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create multiple projects
        projects = ["frontend", "backend", "mobile"]
        for project in projects:
            project_dir = workspace / project
            project_dir.mkdir()
            (project_dir / ".code-indexer").mkdir()
            # Add some dummy config
            config = project_dir / ".code-indexer" / "config.json"
            config.write_text('{"embedding_provider": "voyage-ai"}')

        # Step 2: Initialize proxy mode
        result = subprocess.run(
            ["cidx", "init", "--proxy-mode"],
            cwd=workspace,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        # Step 3: Verify proxy configuration
        proxy_config = workspace / ".code-indexer" / "config.json"
        with open(proxy_config) as f:
            config_data = json.load(f)

        assert config_data["proxy_mode"] is True
        assert set(config_data["discovered_repos"]) == set(projects)

        # Step 4: Verify each project config remains intact
        for project in projects:
            project_config = workspace / project / ".code-indexer" / "config.json"
            assert project_config.exists()
            with open(project_config) as f:
                proj_data = json.load(f)
            assert proj_data.get("embedding_provider") == "voyage-ai"

    def test_proxy_mode_ignores_non_indexed_directories(self, tmp_path):
        """Proxy mode only discovers directories with .code-indexer/."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create indexed project
        indexed = workspace / "indexed_project"
        indexed.mkdir()
        (indexed / ".code-indexer").mkdir()

        # Create regular directories (no .code-indexer)
        (workspace / "docs").mkdir()
        (workspace / "assets").mkdir()
        (workspace / "temp").mkdir()

        # Initialize proxy
        result = subprocess.run(
            ["cidx", "init", "--proxy-mode"],
            cwd=workspace,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        # Verify only indexed project discovered
        config_file = workspace / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        assert config_data["discovered_repos"] == ["indexed_project"]
        assert "docs" not in config_data["discovered_repos"]
        assert "assets" not in config_data["discovered_repos"]

    def test_proxy_mode_discovers_nested_repositories_recursively(self, tmp_path):
        """Proxy mode discovers repositories at all nesting levels recursively."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create nested structure with repositories at different depths
        nested_repos = [
            "services/auth",
            "services/user",
            "services/payment/gateway",
            "frontend",
            "backend/api/v1",
            "backend/api/v2",
        ]

        for repo_path in nested_repos:
            full_path = workspace / repo_path
            full_path.mkdir(parents=True)
            (full_path / ".code-indexer").mkdir()

        # Initialize proxy
        result = subprocess.run(
            ["cidx", "init", "--proxy-mode"],
            cwd=workspace,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Verify all nested repositories discovered
        config_file = workspace / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        discovered = set(config_data["discovered_repos"])
        expected = set(nested_repos)
        assert discovered == expected, f"Expected {expected}, got {discovered}"

        # Verify output mentions all discovered repos
        assert "Discovered 6 repositories" in result.stdout

    def test_proxy_mode_excludes_own_config_from_discovery(self, tmp_path):
        """Proxy mode excludes its own .code-indexer directory from discovered repos."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create proxy config first (simulating re-initialization)
        proxy_config = workspace / ".code-indexer"
        proxy_config.mkdir()

        # Create actual repositories
        repos = ["repo1", "repo2"]
        for repo in repos:
            repo_dir = workspace / repo
            repo_dir.mkdir()
            (repo_dir / ".code-indexer").mkdir()

        # Initialize proxy (should exclude own config)
        result = subprocess.run(
            ["cidx", "init", "--proxy-mode", "--force"],
            cwd=workspace,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        # Verify proxy's own config not in discovered list
        config_file = workspace / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        assert set(config_data["discovered_repos"]) == {"repo1", "repo2"}
        assert "." not in config_data["discovered_repos"]
        assert "" not in config_data["discovered_repos"]

    def test_proxy_mode_deeply_nested_structure(self, tmp_path):
        """Proxy mode handles deeply nested repository structures (3+ levels)."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create very deep nesting
        deep_repos = [
            "a/b/c/d/repo1",
            "x/y/z/repo2",
            "services/api/v1/endpoints/users",
        ]

        for repo_path in deep_repos:
            full_path = workspace / repo_path
            full_path.mkdir(parents=True)
            (full_path / ".code-indexer").mkdir()

        # Initialize proxy
        result = subprocess.run(
            ["cidx", "init", "--proxy-mode"],
            cwd=workspace,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        # Verify all deep repos discovered
        config_file = workspace / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        discovered = set(config_data["discovered_repos"])
        expected = set(deep_repos)
        assert discovered == expected

    def test_proxy_mode_mixed_depth_repositories(self, tmp_path):
        """Proxy mode discovers repositories at mixed depths correctly."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Mix of immediate children and nested repos
        repos = [
            "immediate1",
            "immediate2",
            "nested/level1",
            "deeply/nested/level2/repo",
        ]

        for repo_path in repos:
            full_path = workspace / repo_path
            full_path.mkdir(parents=True)
            (full_path / ".code-indexer").mkdir()

        # Initialize proxy
        result = subprocess.run(
            ["cidx", "init", "--proxy-mode"],
            cwd=workspace,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        # Verify all repos discovered regardless of depth
        config_file = workspace / ".code-indexer" / "config.json"
        with open(config_file) as f:
            config_data = json.load(f)

        assert set(config_data["discovered_repos"]) == set(repos)
        assert "Discovered 4 repositories" in result.stdout

    def test_regular_init_allowed_within_proxy_directory(self, tmp_path):
        """
        Acceptance Criterion 4: Regular `cidx init` (without --proxy-mode)
        still allowed within proxy-managed folders.

        Test Flow:
        1. Create parent proxy directory with cidx init --proxy-mode
        2. Create subdirectory within proxy
        3. Run cidx init (WITHOUT --proxy-mode) in subdirectory
        4. Verify: Command succeeds (exit code 0)
        5. Verify: .code-indexer directory created in subdirectory
        6. Verify: config.json has proxy_mode=false (regular init, not proxy)
        7. Verify: Parent proxy config remains unchanged
        """
        # Step 1: Create parent proxy
        parent_proxy = tmp_path / "parent_proxy"
        parent_proxy.mkdir()

        result1 = subprocess.run(
            ["cidx", "init", "--proxy-mode"],
            cwd=parent_proxy,
            capture_output=True,
            text=True,
        )
        assert result1.returncode == 0, f"Parent proxy init failed: {result1.stderr}"
        assert "Proxy mode initialized successfully" in result1.stdout

        # Step 2: Create subdirectory within proxy
        child_dir = parent_proxy / "my_regular_repo"
        child_dir.mkdir()

        # Step 3: Run regular init (WITHOUT --proxy-mode) in subdirectory
        result2 = subprocess.run(
            ["cidx", "init"],
            cwd=child_dir,
            capture_output=True,
            text=True,
        )

        # Step 4: Verify command succeeds
        assert (
            result2.returncode == 0
        ), f"Regular init failed: {result2.stderr}\nStdout: {result2.stdout}"

        # Step 5: Verify .code-indexer directory created in subdirectory
        child_config_dir = child_dir / ".code-indexer"
        assert child_config_dir.exists(), ".code-indexer directory not created"
        assert child_config_dir.is_dir(), ".code-indexer is not a directory"

        # Step 6: Verify config.json has proxy_mode=false (regular init, not proxy)
        child_config_file = child_config_dir / "config.json"
        assert child_config_file.exists(), "config.json not created in child"

        with open(child_config_file) as f:
            child_config = json.load(f)

        # Regular init should NOT have proxy_mode=true
        assert (
            child_config.get("proxy_mode", False) is False
        ), "Child config incorrectly marked as proxy"

        # Step 7: Verify parent proxy config remains unchanged
        parent_config_file = parent_proxy / ".code-indexer" / "config.json"
        assert parent_config_file.exists(), "Parent config disappeared"

        with open(parent_config_file) as f:
            parent_config = json.load(f)

        assert parent_config.get("proxy_mode") is True, "Parent proxy_mode flag changed"

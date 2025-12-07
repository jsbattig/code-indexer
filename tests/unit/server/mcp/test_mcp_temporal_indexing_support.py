"""
Unit tests for MCP Temporal Indexing Support (Story #527).

Tests verify that the MCP layer properly exposes temporal indexing parameters
for add_golden_repo, and that these parameters are stored and used during
refresh cycles.

Test Methodology: TDD (Red-Green-Refactor)
- Tests written FIRST (should fail initially)
- Implementation follows to make tests pass
- Refactoring for quality after green
"""

import json

import pytest
from unittest.mock import MagicMock, Mock, patch


class TestMCPToolsTemporalSchema:
    """Test that add_golden_repo tool schema includes temporal parameters."""

    def test_add_golden_repo_schema_includes_enable_temporal_parameter(self):
        """
        Test that add_golden_repo inputSchema includes enable_temporal parameter.

        Acceptance Criterion: MCP add_golden_repo tool schema includes enable_temporal boolean.
        """
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        schema = TOOL_REGISTRY["add_golden_repo"]["inputSchema"]
        props = schema["properties"]

        assert (
            "enable_temporal" in props
        ), "add_golden_repo inputSchema missing 'enable_temporal' parameter"
        assert (
            props["enable_temporal"]["type"] == "boolean"
        ), "enable_temporal should be boolean type"
        assert (
            "default" in props["enable_temporal"]
        ), "enable_temporal should have a default value"
        assert (
            props["enable_temporal"]["default"] is False
        ), "enable_temporal should default to false for backward compatibility"

    def test_add_golden_repo_schema_includes_temporal_options_parameter(self):
        """
        Test that add_golden_repo inputSchema includes temporal_options parameter.

        Acceptance Criterion: MCP add_golden_repo tool schema includes temporal_options object.
        """
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        schema = TOOL_REGISTRY["add_golden_repo"]["inputSchema"]
        props = schema["properties"]

        assert (
            "temporal_options" in props
        ), "add_golden_repo inputSchema missing 'temporal_options' parameter"
        assert (
            props["temporal_options"]["type"] == "object"
        ), "temporal_options should be object type"
        assert (
            "description" in props["temporal_options"]
        ), "temporal_options should have a description"

    def test_temporal_options_schema_includes_max_commits(self):
        """
        Test that temporal_options schema includes max_commits parameter.
        """
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        schema = TOOL_REGISTRY["add_golden_repo"]["inputSchema"]
        temporal_props = schema["properties"]["temporal_options"]["properties"]

        assert (
            "max_commits" in temporal_props
        ), "temporal_options missing 'max_commits' parameter"
        assert (
            temporal_props["max_commits"]["type"] == "integer"
        ), "max_commits should be integer type"

    def test_temporal_options_schema_includes_since_date(self):
        """
        Test that temporal_options schema includes since_date parameter.
        """
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        schema = TOOL_REGISTRY["add_golden_repo"]["inputSchema"]
        temporal_props = schema["properties"]["temporal_options"]["properties"]

        assert (
            "since_date" in temporal_props
        ), "temporal_options missing 'since_date' parameter"
        assert (
            temporal_props["since_date"]["type"] == "string"
        ), "since_date should be string type"

    def test_temporal_options_schema_includes_diff_context(self):
        """
        Test that temporal_options schema includes diff_context parameter.
        """
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        schema = TOOL_REGISTRY["add_golden_repo"]["inputSchema"]
        temporal_props = schema["properties"]["temporal_options"]["properties"]

        assert (
            "diff_context" in temporal_props
        ), "temporal_options missing 'diff_context' parameter"
        assert (
            temporal_props["diff_context"]["type"] == "integer"
        ), "diff_context should be integer type"
        assert (
            temporal_props["diff_context"].get("default") == 5
        ), "diff_context should default to 5"


class TestMCPHandlersTemporalPassing:
    """Test that add_golden_repo handler passes temporal parameters to GoldenRepoManager."""

    @pytest.mark.asyncio
    async def test_add_golden_repo_handler_passes_enable_temporal(self):
        """
        Test that add_golden_repo handler extracts and passes enable_temporal parameter.

        Acceptance Criterion: Handler passes enable_temporal to GoldenRepoManager.add_golden_repo()
        """
        from code_indexer.server.mcp.handlers import add_golden_repo
        from code_indexer.server.auth.user_manager import User, UserRole

        user = Mock(spec=User)
        user.username = "admin"
        user.role = UserRole.ADMIN

        params = {
            "url": "https://github.com/org/test-repo.git",
            "alias": "test-repo",
            "branch": "main",
            "enable_temporal": True,
        }

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.golden_repo_manager.add_golden_repo.return_value = "job-123"

            await add_golden_repo(params, user)

            # Verify enable_temporal was passed
            call_kwargs = mock_app.golden_repo_manager.add_golden_repo.call_args
            assert call_kwargs is not None, "add_golden_repo was not called"

            # Check both positional and keyword args
            if call_kwargs.kwargs:
                assert (
                    call_kwargs.kwargs.get("enable_temporal") is True
                ), "enable_temporal=True not passed to GoldenRepoManager"
            else:
                # Enable temporal should be in the call
                assert True in call_kwargs.args or any(
                    k == "enable_temporal" and v is True
                    for k, v in (call_kwargs.kwargs or {}).items()
                ), "enable_temporal=True not passed to GoldenRepoManager"

    @pytest.mark.asyncio
    async def test_add_golden_repo_handler_passes_temporal_options(self):
        """
        Test that add_golden_repo handler extracts and passes temporal_options parameter.

        Acceptance Criterion: Handler passes temporal_options to GoldenRepoManager.add_golden_repo()
        """
        from code_indexer.server.mcp.handlers import add_golden_repo
        from code_indexer.server.auth.user_manager import User, UserRole

        user = Mock(spec=User)
        user.username = "admin"
        user.role = UserRole.ADMIN

        temporal_options = {
            "max_commits": 1000,
            "since_date": "2024-01-01",
            "diff_context": 10,
        }

        params = {
            "url": "https://github.com/org/test-repo.git",
            "alias": "test-repo",
            "branch": "main",
            "enable_temporal": True,
            "temporal_options": temporal_options,
        }

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.golden_repo_manager.add_golden_repo.return_value = "job-123"

            await add_golden_repo(params, user)

            # Verify temporal_options was passed
            call_kwargs = mock_app.golden_repo_manager.add_golden_repo.call_args
            assert call_kwargs is not None, "add_golden_repo was not called"

            if call_kwargs.kwargs:
                passed_options = call_kwargs.kwargs.get("temporal_options")
                assert (
                    passed_options == temporal_options
                ), f"temporal_options not passed correctly. Expected {temporal_options}, got {passed_options}"

    @pytest.mark.asyncio
    async def test_add_golden_repo_handler_defaults_enable_temporal_to_false(self):
        """
        Test that enable_temporal defaults to False when not provided (backward compatibility).

        Acceptance Criterion: Repository indexed without temporal indexing when not specified.
        """
        from code_indexer.server.mcp.handlers import add_golden_repo
        from code_indexer.server.auth.user_manager import User, UserRole

        user = Mock(spec=User)
        user.username = "admin"
        user.role = UserRole.ADMIN

        # No enable_temporal in params
        params = {
            "url": "https://github.com/org/test-repo.git",
            "alias": "test-repo",
        }

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.golden_repo_manager.add_golden_repo.return_value = "job-123"

            await add_golden_repo(params, user)

            call_kwargs = mock_app.golden_repo_manager.add_golden_repo.call_args
            if call_kwargs.kwargs:
                # Should either not be passed or be False
                enable_temporal = call_kwargs.kwargs.get("enable_temporal", False)
                assert (
                    enable_temporal is False
                ), "enable_temporal should default to False"


class TestGlobalRegistryTemporalStorage:
    """Test that GlobalRegistry stores and retrieves temporal settings."""

    def test_register_global_repo_stores_enable_temporal(self, tmp_path):
        """
        Test that register_global_repo stores enable_temporal in registry.

        Acceptance Criterion: GlobalRegistry stores enable_temporal alongside repo metadata.
        """
        from code_indexer.global_repos.global_registry import GlobalRegistry

        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(tmp_path / "index"),
            enable_temporal=True,
        )

        repo = registry.get_global_repo("test-repo-global")
        assert repo is not None, "Repository not found in registry"
        assert "enable_temporal" in repo, "enable_temporal not stored in registry"
        assert repo["enable_temporal"] is True, "enable_temporal value not correct"

    def test_register_global_repo_stores_temporal_options(self, tmp_path):
        """
        Test that register_global_repo stores temporal_options in registry.

        Acceptance Criterion: GlobalRegistry stores temporal_options alongside repo metadata.
        """
        from code_indexer.global_repos.global_registry import GlobalRegistry

        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        temporal_options = {
            "max_commits": 1000,
            "since_date": "2024-01-01",
            "diff_context": 10,
        }

        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(tmp_path / "index"),
            enable_temporal=True,
            temporal_options=temporal_options,
        )

        repo = registry.get_global_repo("test-repo-global")
        assert repo is not None, "Repository not found in registry"
        assert "temporal_options" in repo, "temporal_options not stored in registry"
        assert (
            repo["temporal_options"] == temporal_options
        ), "temporal_options value not correct"

    def test_register_global_repo_defaults_enable_temporal_to_false(self, tmp_path):
        """
        Test that enable_temporal defaults to False when not provided.
        """
        from code_indexer.global_repos.global_registry import GlobalRegistry

        golden_repos_dir = tmp_path / "golden_repos"
        registry = GlobalRegistry(str(golden_repos_dir))

        # Don't provide enable_temporal
        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(tmp_path / "index"),
        )

        repo = registry.get_global_repo("test-repo-global")
        assert repo is not None
        # Should default to False
        assert repo.get("enable_temporal", False) is False

    def test_temporal_settings_persist_across_reload(self, tmp_path):
        """
        Test that temporal settings persist across registry reload.
        """
        from code_indexer.global_repos.global_registry import GlobalRegistry

        golden_repos_dir = tmp_path / "golden_repos"

        # Register with temporal settings
        registry1 = GlobalRegistry(str(golden_repos_dir))
        registry1.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(tmp_path / "index"),
            enable_temporal=True,
            temporal_options={"max_commits": 500},
        )

        # Create new registry instance (simulates restart)
        registry2 = GlobalRegistry(str(golden_repos_dir))

        repo = registry2.get_global_repo("test-repo-global")
        assert repo is not None
        assert repo.get("enable_temporal") is True
        assert repo.get("temporal_options") == {"max_commits": 500}


class TestGlobalActivatorTemporalPassing:
    """Test that GlobalActivator passes temporal settings to GlobalRegistry."""

    def test_activate_golden_repo_passes_enable_temporal(self, tmp_path):
        """
        Test that activate_golden_repo passes enable_temporal to registry.

        Acceptance Criterion: GlobalActivator passes temporal settings through activation workflow.
        """
        from code_indexer.global_repos.global_activation import GlobalActivator

        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        activator = GlobalActivator(str(golden_repos_dir))

        # Create a test clone path
        clone_path = tmp_path / "clone"
        clone_path.mkdir()

        activator.activate_golden_repo(
            repo_name="test-repo",
            repo_url="https://github.com/org/test-repo",
            clone_path=str(clone_path),
            enable_temporal=True,
        )

        repo = activator.registry.get_global_repo("test-repo-global")
        assert repo is not None
        assert repo.get("enable_temporal") is True

    def test_activate_golden_repo_passes_temporal_options(self, tmp_path):
        """
        Test that activate_golden_repo passes temporal_options to registry.
        """
        from code_indexer.global_repos.global_activation import GlobalActivator

        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        activator = GlobalActivator(str(golden_repos_dir))

        clone_path = tmp_path / "clone"
        clone_path.mkdir()

        temporal_options = {"max_commits": 1000, "diff_context": 10}

        activator.activate_golden_repo(
            repo_name="test-repo",
            repo_url="https://github.com/org/test-repo",
            clone_path=str(clone_path),
            enable_temporal=True,
            temporal_options=temporal_options,
        )

        repo = activator.registry.get_global_repo("test-repo-global")
        assert repo is not None
        assert repo.get("temporal_options") == temporal_options


class TestRefreshSchedulerTemporalCommand:
    """Test that RefreshScheduler uses temporal settings from registry during refresh."""

    def test_create_new_index_uses_temporal_flags_when_enabled(self, tmp_path):
        """
        Test that _create_new_index runs TWO separate commands when enable_temporal=True:
        1. cidx index --fts (semantic + FTS)
        2. cidx index --index-commits (temporal)

        Acceptance Criterion: Refresh includes separate --index-commits command when temporal enabled.
        """
        from pathlib import Path

        from code_indexer.config import ConfigManager
        from code_indexer.global_repos.cleanup_manager import CleanupManager
        from code_indexer.global_repos.query_tracker import QueryTracker
        from code_indexer.global_repos.refresh_scheduler import RefreshScheduler

        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        config_mgr = ConfigManager(tmp_path / ".code-indexer" / "config.json")
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker)

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        # Register a repo with temporal enabled
        scheduler.registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(tmp_path / "index"),
            enable_temporal=True,
        )

        source_path = tmp_path / "source"
        source_path.mkdir()

        captured_commands = []

        def capture_subprocess(cmd, *args, **kwargs):
            captured_commands.append(cmd)
            # Create index dir for cidx index command
            if len(cmd) >= 2 and cmd[0] == "cidx" and cmd[1] == "index":
                # Get cwd from kwargs
                cwd = kwargs.get("cwd", "")
                if cwd:
                    index_dir = Path(cwd) / ".code-indexer" / "index"
                    index_dir.mkdir(parents=True, exist_ok=True)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("code_indexer.global_repos.refresh_scheduler.datetime") as mock_dt:
            mock_dt.utcnow.return_value.timestamp.return_value = 1234567890

            with patch("subprocess.run", side_effect=capture_subprocess):
                scheduler._create_new_index(
                    alias_name="test-repo-global",
                    source_path=str(source_path),
                )

        # Find cidx index commands
        cidx_index_cmds = [
            c for c in captured_commands if c[0] == "cidx" and c[1] == "index"
        ]
        assert (
            len(cidx_index_cmds) == 2
        ), f"Expected 2 cidx index commands (semantic+FTS and temporal), got {len(cidx_index_cmds)}: {cidx_index_cmds}"

        # First command should be semantic+FTS (cidx index --fts)
        fts_cmd = cidx_index_cmds[0]
        assert "--fts" in fts_cmd, f"First command should have --fts: {fts_cmd}"
        assert (
            "--index-commits" not in fts_cmd
        ), f"First command should NOT have --index-commits: {fts_cmd}"

        # Second command should be temporal (cidx index --index-commits)
        temporal_cmd = cidx_index_cmds[1]
        assert (
            "--index-commits" in temporal_cmd
        ), f"Second command should have --index-commits: {temporal_cmd}"
        assert (
            "--fts" not in temporal_cmd
        ), f"Second command should NOT have --fts: {temporal_cmd}"

    def test_create_new_index_includes_temporal_options(self, tmp_path):
        """
        Test that _create_new_index includes --max-commits, --since-date, --diff-context
        in the SECOND command (temporal command), not in the first (semantic+FTS).
        """
        from pathlib import Path

        from code_indexer.config import ConfigManager
        from code_indexer.global_repos.cleanup_manager import CleanupManager
        from code_indexer.global_repos.query_tracker import QueryTracker
        from code_indexer.global_repos.refresh_scheduler import RefreshScheduler

        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        config_mgr = ConfigManager(tmp_path / ".code-indexer" / "config.json")
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker)

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        temporal_options = {
            "max_commits": 500,
            "since_date": "2024-06-01",
            "diff_context": 8,
        }

        scheduler.registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(tmp_path / "index"),
            enable_temporal=True,
            temporal_options=temporal_options,
        )

        source_path = tmp_path / "source"
        source_path.mkdir()

        captured_commands = []

        def capture_subprocess(cmd, *args, **kwargs):
            captured_commands.append(cmd)
            if len(cmd) >= 2 and cmd[0] == "cidx" and cmd[1] == "index":
                cwd = kwargs.get("cwd", "")
                if cwd:
                    index_dir = Path(cwd) / ".code-indexer" / "index"
                    index_dir.mkdir(parents=True, exist_ok=True)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("code_indexer.global_repos.refresh_scheduler.datetime") as mock_dt:
            mock_dt.utcnow.return_value.timestamp.return_value = 1234567890

            with patch("subprocess.run", side_effect=capture_subprocess):
                scheduler._create_new_index(
                    alias_name="test-repo-global",
                    source_path=str(source_path),
                )

        cidx_index_cmds = [
            c for c in captured_commands if c[0] == "cidx" and c[1] == "index"
        ]
        assert (
            len(cidx_index_cmds) == 2
        ), f"Expected 2 cidx index commands, got {len(cidx_index_cmds)}: {cidx_index_cmds}"

        # First command: semantic+FTS (should NOT have temporal options)
        fts_cmd = cidx_index_cmds[0]
        assert "--fts" in fts_cmd
        assert "--index-commits" not in fts_cmd

        # Second command: temporal (should have all temporal options)
        temporal_cmd = cidx_index_cmds[1]
        assert "--index-commits" in temporal_cmd
        assert "--max-commits" in temporal_cmd
        assert "500" in temporal_cmd
        assert "--since-date" in temporal_cmd
        assert "2024-06-01" in temporal_cmd
        assert "--diff-context" in temporal_cmd
        assert "8" in temporal_cmd

    def test_create_new_index_no_temporal_flags_when_disabled(self, tmp_path):
        """
        Test that _create_new_index runs ONLY ONE command when enable_temporal=False.
        Only semantic+FTS indexing, no temporal indexing command.

        Acceptance Criterion: Repository indexed without temporal indexing (backward compatible).
        """
        from pathlib import Path

        from code_indexer.config import ConfigManager
        from code_indexer.global_repos.cleanup_manager import CleanupManager
        from code_indexer.global_repos.query_tracker import QueryTracker
        from code_indexer.global_repos.refresh_scheduler import RefreshScheduler

        golden_repos_dir = tmp_path / ".code-indexer" / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        config_mgr = ConfigManager(tmp_path / ".code-indexer" / "config.json")
        tracker = QueryTracker()
        cleanup_mgr = CleanupManager(tracker)

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_mgr,
            query_tracker=tracker,
            cleanup_manager=cleanup_mgr,
        )

        # Register WITHOUT temporal
        scheduler.registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(tmp_path / "index"),
            enable_temporal=False,
        )

        source_path = tmp_path / "source"
        source_path.mkdir()

        captured_commands = []

        def capture_subprocess(cmd, *args, **kwargs):
            captured_commands.append(cmd)
            if len(cmd) >= 2 and cmd[0] == "cidx" and cmd[1] == "index":
                cwd = kwargs.get("cwd", "")
                if cwd:
                    index_dir = Path(cwd) / ".code-indexer" / "index"
                    index_dir.mkdir(parents=True, exist_ok=True)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("code_indexer.global_repos.refresh_scheduler.datetime") as mock_dt:
            mock_dt.utcnow.return_value.timestamp.return_value = 1234567890

            with patch("subprocess.run", side_effect=capture_subprocess):
                scheduler._create_new_index(
                    alias_name="test-repo-global",
                    source_path=str(source_path),
                )

        cidx_index_cmds = [
            c for c in captured_commands if c[0] == "cidx" and c[1] == "index"
        ]

        # Should have exactly ONE cidx index command (semantic+FTS only)
        assert (
            len(cidx_index_cmds) == 1
        ), f"Expected 1 cidx index command when temporal disabled, got {len(cidx_index_cmds)}: {cidx_index_cmds}"

        fts_cmd = cidx_index_cmds[0]

        # Should have --fts flag
        assert "--fts" in fts_cmd, f"Command should have --fts: {fts_cmd}"

        # Should NOT have temporal flags
        assert (
            "--index-commits" not in fts_cmd
        ), f"--index-commits should NOT be in command when temporal disabled: {fts_cmd}"


class TestDiscoverRepositoriesTemporalOutput:
    """Test that discover_repositories returns temporal settings."""

    @pytest.mark.asyncio
    async def test_discover_repositories_includes_temporal_fields(self):
        """
        Test that discover_repositories response includes enable_temporal and temporal_options.

        Acceptance Criterion: discover_repositories includes temporal fields in response.
        """
        from code_indexer.server.auth.user_manager import User, UserRole
        from code_indexer.server.mcp.handlers import discover_repositories

        user = Mock(spec=User)
        user.username = "testuser"
        user.role = UserRole.NORMAL_USER

        mock_repos = [
            {
                "alias": "test-repo",
                "repo_url": "https://github.com/org/test-repo",
                "default_branch": "main",
                "clone_path": "/path/to/clone",
                "created_at": "2025-01-01T00:00:00Z",
                "enable_temporal": True,
                "temporal_options": {"max_commits": 500},
            }
        ]

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.golden_repo_manager.list_golden_repos.return_value = mock_repos

            result = await discover_repositories({}, user)

            response_data = json.loads(result["content"][0]["text"])

            assert response_data["success"] is True
            assert len(response_data["repositories"]) == 1

            repo = response_data["repositories"][0]
            assert "enable_temporal" in repo
            assert repo["enable_temporal"] is True
            assert "temporal_options" in repo
            assert repo["temporal_options"]["max_commits"] == 500


class TestGetRepositoryStatusTemporalOutput:
    """Test that get_repository_status returns temporal settings."""

    @pytest.mark.asyncio
    async def test_get_repository_status_includes_temporal_fields(self):
        """
        Test that get_repository_status includes enable_temporal and temporal_options.

        Acceptance Criterion: get_repository_status includes temporal fields for temporally-indexed repos.
        """
        from code_indexer.server.auth.user_manager import User, UserRole
        from code_indexer.server.mcp.handlers import get_repository_status

        user = Mock(spec=User)
        user.username = "testuser"
        user.role = UserRole.NORMAL_USER

        mock_status = {
            "alias": "test-repo",
            "repo_url": "https://github.com/org/test-repo",
            "default_branch": "main",
            "clone_path": "/path/to/clone",
            "created_at": "2025-01-01T00:00:00Z",
            "activation_status": "active",
            "enable_temporal": True,
            "temporal_status": {
                "enabled": True,
                "diff_context": 5,
            },
        }

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.repository_listing_manager.get_repository_details.return_value = (
                mock_status
            )

            result = await get_repository_status(
                {"user_alias": "test-repo-global"}, user
            )

            response_data = json.loads(result["content"][0]["text"])

            assert response_data["success"] is True
            status = response_data["status"]

            assert "enable_temporal" in status
            assert status["enable_temporal"] is True
            assert "temporal_status" in status

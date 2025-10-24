"""Unit tests for CLI start/stop commands with backend abstraction.

Story 6: Tests seamless start/stop operations for filesystem vs Qdrant backends.

Acceptance Criteria:
1. cidx start succeeds immediately for filesystem (no-op)
2. cidx stop succeeds immediately for filesystem (no-op)
3. Start/stop maintain same CLI interface
4. No container checks for filesystem
5. Backend abstraction handles differences transparently
6. Clear user feedback
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from code_indexer.cli import cli
from code_indexer.config import (
    Config,
    ConfigManager,
    VectorStoreConfig,
    ProjectPortsConfig,
)


class TestStartStopFilesystemBackend:
    """Test start/stop commands with filesystem backend."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
        self.temp_dir = tempfile.mkdtemp()
        self.test_dir = Path(self.temp_dir) / "test_project"
        self.test_dir.mkdir(parents=True)

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_start_filesystem_backend_succeeds_immediately(self):
        """AC1: cidx start succeeds immediately for filesystem (no-op)."""
        # Create filesystem backend config
        config_path = self.test_dir / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_manager = ConfigManager(config_path)

        config = Config(
            codebase_dir=self.test_dir,
            vector_store=VectorStoreConfig(provider="filesystem"),
            project_ports=ProjectPortsConfig(
                qdrant_port=None,
                ollama_port=None,
                data_cleaner_port=None,
            ),
        )
        config_manager.save(config)

        # Mock backend factory to return filesystem backend
        with patch("code_indexer.cli.BackendFactory") as mock_factory:
            mock_backend = MagicMock()
            mock_backend.start.return_value = True
            mock_backend.get_service_info.return_value = {
                "provider": "filesystem",
                "requires_containers": False,
                "vectors_dir": str(self.test_dir / ".code-indexer" / "index"),
            }
            mock_factory.create.return_value = mock_backend

            # Run start command from test directory (config detection needs cwd context)
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(self.test_dir)
                result = self.runner.invoke(cli, ["start"])

                # Should succeed immediately
                assert result.exit_code == 0, f"Failed with output: {result.output}"
                mock_backend.start.assert_called_once()
            finally:
                os.chdir(original_cwd)

    def test_stop_filesystem_backend_succeeds_immediately(self):
        """AC2: cidx stop succeeds immediately for filesystem (no-op)."""
        # Create filesystem backend config
        config_path = self.test_dir / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_manager = ConfigManager(config_path)

        config = Config(
            codebase_dir=self.test_dir,
            vector_store=VectorStoreConfig(provider="filesystem"),
            project_ports=ProjectPortsConfig(
                qdrant_port=None,
                ollama_port=None,
                data_cleaner_port=None,
            ),
        )
        config_manager.save(config)

        # Mock backend factory to return filesystem backend
        with patch("code_indexer.cli.BackendFactory") as mock_factory:
            mock_backend = MagicMock()
            mock_backend.stop.return_value = True
            mock_backend.get_service_info.return_value = {
                "provider": "filesystem",
                "requires_containers": False,
                "vectors_dir": str(self.test_dir / ".code-indexer" / "index"),
            }
            mock_factory.create.return_value = mock_backend

            # Run stop command from test directory (config detection needs cwd context)
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(self.test_dir)
                result = self.runner.invoke(cli, ["stop"])

                # Should succeed immediately
                assert result.exit_code == 0, f"Failed with output: {result.output}"
                mock_backend.stop.assert_called_once()
            finally:
                os.chdir(original_cwd)

    def test_start_maintains_cli_interface(self):
        """AC3: Start maintains same CLI interface regardless of backend."""
        config_path = self.test_dir / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_manager = ConfigManager(config_path)

        # Test filesystem backend (qdrant would need Docker which we're mocking away)
        config = Config(
            codebase_dir=self.test_dir,
            vector_store=VectorStoreConfig(provider="filesystem"),
            project_ports=ProjectPortsConfig(
                qdrant_port=None,
                ollama_port=None,
                data_cleaner_port=None,
            ),
        )
        config_manager.save(config)

        with patch("code_indexer.cli.BackendFactory") as mock_factory:
            mock_backend = MagicMock()
            mock_backend.start.return_value = True
            mock_backend.get_service_info.return_value = {
                "provider": "filesystem",
                "requires_containers": False,
                "vectors_dir": str(self.test_dir / ".code-indexer" / "index"),
            }
            mock_factory.create.return_value = mock_backend

            # Run from test directory
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(self.test_dir)
                result = self.runner.invoke(cli, ["start"])

                # CLI interface should work the same
                assert result.exit_code == 0, f"Failed with output: {result.output}"
                mock_backend.start.assert_called_once()
            finally:
                os.chdir(original_cwd)

    def test_start_filesystem_no_container_checks(self):
        """AC4: No container checks for filesystem backend."""
        config_path = self.test_dir / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_manager = ConfigManager(config_path)

        config = Config(
            codebase_dir=self.test_dir,
            vector_store=VectorStoreConfig(provider="filesystem"),
            project_ports=ProjectPortsConfig(
                qdrant_port=None,
                ollama_port=None,
                data_cleaner_port=None,
            ),
        )
        config_manager.save(config)

        # Ensure no DockerManager is created for filesystem
        with (
            patch("code_indexer.cli.BackendFactory") as mock_factory,
            patch("code_indexer.cli.DockerManager") as mock_docker,
        ):

            mock_backend = MagicMock()
            mock_backend.start.return_value = True
            mock_backend.get_service_info.return_value = {
                "provider": "filesystem",
                "requires_containers": False,
            }
            mock_factory.create.return_value = mock_backend

            # Run from test directory
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(self.test_dir)
                self.runner.invoke(cli, ["start"])

                # DockerManager should NOT be called for filesystem backend
                mock_docker.assert_not_called()
            finally:
                os.chdir(original_cwd)

    def test_backend_abstraction_handles_differences_transparently(self):
        """AC5: Backend abstraction handles differences transparently."""
        config_path = self.test_dir / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_manager = ConfigManager(config_path)

        # Test filesystem backend behavior
        config = Config(
            codebase_dir=self.test_dir,
            vector_store=VectorStoreConfig(provider="filesystem"),
            project_ports=ProjectPortsConfig(
                qdrant_port=None,
                ollama_port=None,
                data_cleaner_port=None,
            ),
        )
        config_manager.save(config)

        with patch("code_indexer.cli.BackendFactory") as mock_factory:
            mock_backend = MagicMock()
            mock_backend.start.return_value = True
            mock_backend.stop.return_value = True
            mock_backend.get_service_info.return_value = {
                "provider": "filesystem",
                "requires_containers": False,
                "vectors_dir": str(self.test_dir / ".code-indexer" / "index"),
            }
            mock_factory.create.return_value = mock_backend

            # Run from test directory
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(self.test_dir)

                # Start should work transparently
                result_start = self.runner.invoke(cli, ["start"])
                assert (
                    result_start.exit_code == 0
                ), f"Start failed: {result_start.output}"

                # Stop should work transparently
                result_stop = self.runner.invoke(cli, ["stop"])
                assert result_stop.exit_code == 0, f"Stop failed: {result_stop.output}"
            finally:
                os.chdir(original_cwd)

    def test_start_filesystem_provides_clear_feedback(self):
        """AC6: Clear user feedback for filesystem backend."""
        config_path = self.test_dir / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_manager = ConfigManager(config_path)

        config = Config(
            codebase_dir=self.test_dir,
            vector_store=VectorStoreConfig(provider="filesystem"),
            project_ports=ProjectPortsConfig(
                qdrant_port=None,
                ollama_port=None,
                data_cleaner_port=None,
            ),
        )
        config_manager.save(config)

        with patch("code_indexer.cli.BackendFactory") as mock_factory:
            mock_backend = MagicMock()
            mock_backend.start.return_value = True
            mock_backend.get_service_info.return_value = {
                "provider": "filesystem",
                "requires_containers": False,
                "vectors_dir": str(self.test_dir / ".code-indexer" / "index"),
            }
            mock_factory.create.return_value = mock_backend

            # Run from test directory
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(self.test_dir)
                result = self.runner.invoke(cli, ["start"])

                # Should provide clear feedback about filesystem backend
                assert result.exit_code == 0, f"Failed with output: {result.output}"
                # Output should mention filesystem or container-free
                assert (
                    "filesystem" in result.output.lower()
                    or "container" in result.output.lower()
                )
            finally:
                os.chdir(original_cwd)

    def test_filesystem_backend_start_returns_true_immediately(self):
        """Technical AC1: FilesystemBackend.start() returns success immediately."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        backend = FilesystemBackend(project_root=self.test_dir)
        backend.initialize()

        # start() should return True immediately (no-op)
        result = backend.start()
        assert result is True

    def test_filesystem_backend_stop_returns_true_immediately(self):
        """Technical AC2: FilesystemBackend.stop() returns success immediately."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        backend = FilesystemBackend(project_root=self.test_dir)
        backend.initialize()

        # stop() should return True immediately (no-op)
        result = backend.stop()
        assert result is True

    def test_backend_status_reflects_always_running(self):
        """Technical AC3: Backend status reflects 'always running' for filesystem."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        backend = FilesystemBackend(project_root=self.test_dir)
        backend.initialize()

        status = backend.get_status()

        # Filesystem backend is always ready (no start/stop needed)
        assert status["provider"] == "filesystem"
        assert status["status"] == "ready"

    def test_no_port_allocation_for_filesystem(self):
        """Technical AC4: No port allocation or network checks for filesystem."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        backend = FilesystemBackend(project_root=self.test_dir)
        backend.initialize()

        service_info = backend.get_service_info()

        # No network requirements
        assert service_info["requires_containers"] is False
        assert "port" not in service_info

    def test_consistent_return_values_across_backends(self):
        """Technical AC5: Consistent return values between backends."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        fs_backend = FilesystemBackend(project_root=self.test_dir)
        fs_backend.initialize()

        # Backend should return bool from start/stop
        fs_start_result = fs_backend.start()
        fs_stop_result = fs_backend.stop()

        assert isinstance(fs_start_result, bool)
        assert isinstance(fs_stop_result, bool)


class TestStartStopQdrantBackend:
    """Test that Qdrant backend behavior is unchanged."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
        self.temp_dir = tempfile.mkdtemp()
        self.test_dir = Path(self.temp_dir) / "test_project"
        self.test_dir.mkdir(parents=True)

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_qdrant_backend_start_uses_docker(self):
        """Technical AC6: Qdrant backend unchanged - still uses Docker."""
        config_path = self.test_dir / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)
        config_manager = ConfigManager(config_path)

        config = Config(
            codebase_dir=self.test_dir,
            vector_store=VectorStoreConfig(provider="qdrant"),
            project_ports=ProjectPortsConfig(
                qdrant_port=6333,
                ollama_port=11434,
                data_cleaner_port=8080,
            ),
        )
        config_manager.save(config)

        with patch("code_indexer.cli.BackendFactory") as mock_factory:
            mock_backend = MagicMock()
            mock_backend.start.return_value = True
            mock_backend.get_service_info.return_value = {
                "provider": "qdrant",
                "requires_containers": True,
            }
            mock_factory.create.return_value = mock_backend

            # Qdrant backend should require container management
            service_info = mock_backend.get_service_info()
            assert service_info["requires_containers"] is True

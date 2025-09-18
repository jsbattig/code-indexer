"""
Test resource management issues in DockerManager cleanup.
"""

import logging
import pytest
from unittest.mock import Mock, patch

from src.code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepoManager,
    GoldenRepo,
    GitOperationError,
)


class TestDockerManagerResourceManagement:
    """Test proper resource management for DockerManager in cleanup operations."""

    @pytest.fixture
    def golden_repo_manager(self, tmp_path):
        """Create a GoldenRepoManager for testing."""
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir()
        return GoldenRepoManager(str(golden_repos_dir))

    def test_docker_manager_resource_cleanup_proper_pattern(self, golden_repo_manager):
        """Test that DockerManager resources are properly managed using context manager."""
        # Create test repository
        test_repo = GoldenRepo(
            alias="test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path="/tmp/test-repo",
            created_at="2023-01-01T00:00:00Z",
        )
        golden_repo_manager.golden_repos["test-repo"] = test_repo

        # Track DockerManager instantiation and cleanup
        docker_manager_instances = []

        class MockDockerManager:
            def __init__(self, *args, **kwargs):
                self.health_checker = Mock()
                self.port_registry = Mock()
                self.cleanup_called = False
                self.context_entered = False
                self.context_exited = False
                docker_manager_instances.append(self)

            def cleanup(self, **kwargs):
                self.cleanup_called = True
                return True

            def close(self):
                """Proper resource cleanup method."""
                if hasattr(self.health_checker, "close"):
                    self.health_checker.close()
                if hasattr(self.port_registry, "close"):
                    self.port_registry.close()

            def __enter__(self):
                self.context_entered = True
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.context_exited = True
                self.close()

        with patch(
            "src.code_indexer.services.docker_manager.DockerManager", MockDockerManager
        ):
            with patch("os.path.exists", return_value=True):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("shutil.rmtree"):
                        # This should properly manage resources using context manager
                        golden_repo_manager._cleanup_repository_files("/tmp/test-repo")

        # Verify proper resource management using context manager
        assert len(docker_manager_instances) == 1
        docker_manager = docker_manager_instances[0]
        assert docker_manager.cleanup_called
        assert docker_manager.context_entered
        assert docker_manager.context_exited

    def test_resource_leak_detection_specificity(self, golden_repo_manager, caplog):
        """Test that resource leak detection provides specific failure details."""
        test_repo = GoldenRepo(
            alias="leak-test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path="/tmp/leak-test-repo",
            created_at="2023-01-01T00:00:00Z",
        )
        golden_repo_manager.golden_repos["leak-test-repo"] = test_repo

        # Mock various failure scenarios with context manager support
        class FailingDockerManager:
            def __init__(self, *args, **kwargs):
                self.health_checker = Mock()
                self.port_registry = Mock()

            def cleanup(self, **kwargs):
                # Simulate partial failure with specific resource details
                raise RuntimeError(
                    "Container 'cidx-abc123-qdrant' failed to stop: timeout after 30s"
                )

            def close(self):
                pass  # Mock close method

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.close()

        with patch(
            "src.code_indexer.services.docker_manager.DockerManager",
            FailingDockerManager,
        ):
            with patch("os.path.exists", return_value=True):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("shutil.rmtree"):
                        # Should provide specific resource failure details
                        result = golden_repo_manager._cleanup_repository_files(
                            "/tmp/leak-test-repo"
                        )

                        # Verify improved error reporting provides specific details
                        assert any(
                            "cidx-abc123-qdrant" in record.message
                            and "timeout after 30s" in record.message
                            for record in caplog.records
                            if record.levelno >= logging.WARNING
                        ), "Expected specific container failure details in logs"

                        # Should return False (cleanup failed) but allow deletion to proceed
                        assert result is False

    def test_docker_manager_null_assignment_antipattern(self, golden_repo_manager):
        """Test that demonstrates the resource management anti-pattern."""
        # This test demonstrates the current problematic pattern
        docker_manager = Mock()
        docker_manager.health_checker = Mock()
        docker_manager.port_registry = Mock()

        # Current anti-pattern: docker_manager = None
        # This doesn't actually clean up the resources properly
        original_health_checker = docker_manager.health_checker
        original_port_registry = docker_manager.port_registry

        # Simulate current cleanup pattern
        docker_manager = None

        # Resources are still accessible but not properly cleaned
        assert original_health_checker is not None
        assert original_port_registry is not None
        # This test exposes that setting to None doesn't clean up resources

    def test_permission_error_raises_git_operation_error(self, golden_repo_manager):
        """Test that PermissionError is properly wrapped in GitOperationError."""
        test_repo = GoldenRepo(
            alias="permission-test-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path="/tmp/permission-test-repo",
            created_at="2023-01-01T00:00:00Z",
        )
        golden_repo_manager.golden_repos["permission-test-repo"] = test_repo

        # Mock DockerManager to raise PermissionError during cleanup
        class PermissionDeniedDockerManager:
            def __init__(self, *args, **kwargs):
                pass

            def cleanup(self, **kwargs):
                raise PermissionError("Permission denied: /root/.local/share/qdrant")

            def close(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.close()

        with patch(
            "src.code_indexer.services.docker_manager.DockerManager",
            PermissionDeniedDockerManager,
        ):
            with patch("os.path.exists", return_value=True):
                with patch("pathlib.Path.exists", return_value=True):
                    with pytest.raises(
                        GitOperationError,
                        match="Insufficient permissions for Docker cleanup",
                    ):
                        golden_repo_manager._cleanup_repository_files(
                            "/tmp/permission-test-repo"
                        )

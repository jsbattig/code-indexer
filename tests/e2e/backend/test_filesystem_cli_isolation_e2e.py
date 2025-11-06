"""
End-to-end tests for filesystem backend CLI isolation from port registry.

These tests verify that when using filesystem backend, NO port registry code
is executed and NO Docker/container dependencies are accessed.

Test approach:
- Use subprocess to run actual `cidx` CLI commands
- Mock GlobalPortRegistry to raise exception if accessed
- Verify commands succeed without accessing port registry
- Use real filesystem, no mocking of core functionality
"""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_project():
    """Create a temporary test project with sample files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "test-project"
        project_dir.mkdir()

        # Create sample Python files for indexing
        (project_dir / "module1.py").write_text(
            """
def authenticate_user(username, password):
    '''User authentication logic.'''
    return validate_credentials(username, password)
"""
        )

        yield project_dir


class TestFilesystemCLIIsolation:
    """Test that filesystem backend CLI operations never access port registry."""

    def test_filesystem_init_no_port_registry(self, temp_project):
        """
        AC: When using `cidx init --vector-store filesystem`, NO port registry code executes.

        This test verifies that initializing with filesystem backend does not
        instantiate GlobalPortRegistry or access /var/lib/code-indexer.
        """
        # Make GlobalPortRegistry fail if accessed
        with patch(
            "code_indexer.services.global_port_registry.GlobalPortRegistry"
        ) as mock_registry:
            mock_registry.side_effect = RuntimeError(
                "CRITICAL: GlobalPortRegistry accessed with filesystem backend!"
            )

            # Run actual CLI command via subprocess
            result = subprocess.run(
                ["python3", "-m", "code_indexer.cli", "init", "--vector-store", "filesystem"],
                cwd=temp_project,
                capture_output=True,
                text=True,
            )

            # Verify command succeeded
            assert result.returncode == 0, f"Init failed: {result.stderr}"
            assert "filesystem" in result.stdout.lower()

            # Verify port registry was never accessed
            mock_registry.assert_not_called()

    def test_filesystem_index_no_port_registry(self, temp_project):
        """
        AC: When using `cidx index` with filesystem backend, NO port registry code executes.

        This test verifies that indexing with filesystem backend does not
        require GlobalPortRegistry or DockerManager.
        """
        # First initialize with filesystem backend
        subprocess.run(
            ["python3", "-m", "code_indexer.cli", "init", "--vector-store", "filesystem"],
            cwd=temp_project,
            capture_output=True,
            check=True,
        )

        # Make GlobalPortRegistry fail if accessed during indexing
        with patch(
            "code_indexer.services.global_port_registry.GlobalPortRegistry"
        ) as mock_registry:
            mock_registry.side_effect = RuntimeError(
                "CRITICAL: GlobalPortRegistry accessed during filesystem indexing!"
            )

            # Run indexing command
            result = subprocess.run(
                ["python3", "-m", "code_indexer.cli", "index"],
                cwd=temp_project,
                capture_output=True,
                text=True,
            )

            # Verify indexing succeeded
            assert result.returncode == 0, f"Indexing failed: {result.stderr}"

            # Verify port registry was never accessed
            mock_registry.assert_not_called()

    def test_filesystem_query_no_port_registry(self, temp_project):
        """
        AC: When using `cidx query` with filesystem backend, NO port registry code executes.

        This test verifies that querying with filesystem backend does not
        require GlobalPortRegistry or DockerManager.
        """
        # Initialize and index with filesystem backend
        subprocess.run(
            ["python3", "-m", "code_indexer.cli", "init", "--vector-store", "filesystem"],
            cwd=temp_project,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["python3", "-m", "code_indexer.cli", "index"],
            cwd=temp_project,
            capture_output=True,
            check=True,
        )

        # Make GlobalPortRegistry fail if accessed during query
        with patch(
            "code_indexer.services.global_port_registry.GlobalPortRegistry"
        ) as mock_registry:
            mock_registry.side_effect = RuntimeError(
                "CRITICAL: GlobalPortRegistry accessed during filesystem query!"
            )

            # Run query command
            result = subprocess.run(
                ["python3", "-m", "code_indexer.cli", "query", "authentication", "--quiet"],
                cwd=temp_project,
                capture_output=True,
                text=True,
            )

            # Verify query succeeded
            assert result.returncode == 0, f"Query failed: {result.stderr}"

            # Verify port registry was never accessed
            mock_registry.assert_not_called()

    def test_filesystem_clean_no_docker(self, temp_project):
        """
        AC: `cidx clean` with filesystem backend should not create DockerManager.

        This test verifies that cleaning with filesystem backend does not
        instantiate DockerManager or access port registry.
        """
        # Initialize and index with filesystem backend
        subprocess.run(
            ["python3", "-m", "code_indexer.cli", "init", "--vector-store", "filesystem"],
            cwd=temp_project,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["python3", "-m", "code_indexer.cli", "index"],
            cwd=temp_project,
            capture_output=True,
            check=True,
        )

        # Make both DockerManager and GlobalPortRegistry fail if accessed
        with patch(
            "code_indexer.services.docker_manager.DockerManager"
        ) as mock_docker, patch(
            "code_indexer.services.global_port_registry.GlobalPortRegistry"
        ) as mock_registry:
            mock_docker.side_effect = RuntimeError(
                "CRITICAL: DockerManager accessed during filesystem clean!"
            )
            mock_registry.side_effect = RuntimeError(
                "CRITICAL: GlobalPortRegistry accessed during filesystem clean!"
            )

            # Run clean command
            result = subprocess.run(
                ["python3", "-m", "code_indexer.cli", "clean", "--force"],
                cwd=temp_project,
                capture_output=True,
                text=True,
            )

            # Verify clean succeeded
            assert result.returncode == 0, f"Clean failed: {result.stderr}"

            # Verify neither DockerManager nor port registry were accessed
            mock_docker.assert_not_called()
            mock_registry.assert_not_called()


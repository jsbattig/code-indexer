"""Tests for the clean command functionality."""

import os
import tempfile
import shutil
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestCleanCommand:
    """Test cases for the clean command with different options."""

    @pytest.fixture(autouse=True)
    def setup_test_environment(self):
        """Setup test environment for each test."""
        # Create temporary directory for test
        self.test_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Create test config directory
        self.config_dir = self.test_dir / ".code-indexer"
        self.config_dir.mkdir()

        # Create test config file
        self.config_file = self.config_dir / "config.yaml"
        self.config_file.write_text(
            """
codebase_dir: .
qdrant:
  host: http://localhost:6333
  collection: test_collection
ollama:
  host: http://localhost:11434
  model: nomic-embed-text
"""
        )

        yield

        # Cleanup
        os.chdir(self.original_cwd)
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_clean_services_only(self):
        """Test clean command without --remove-data (services only)."""
        from click.testing import CliRunner
        from code_indexer.cli import cli

        runner = CliRunner()

        with patch("code_indexer.cli.DockerManager") as mock_docker:
            mock_docker_instance = MagicMock()
            mock_docker_instance.cleanup.return_value = True
            mock_docker.return_value = mock_docker_instance

            result = runner.invoke(cli, ["clean"])

            assert result.exit_code == 0
            mock_docker_instance.cleanup.assert_called_once_with(remove_data=False)
            assert "Services stopped" in result.output

            # Config should still exist
            assert self.config_file.exists()
            assert self.config_dir.exists()

    def test_clean_current_project_data(self):
        """Test clean --remove-data (current project only, new default behavior)."""
        from click.testing import CliRunner
        from code_indexer.cli import cli

        runner = CliRunner()

        with patch("code_indexer.cli.DockerManager") as mock_docker, patch(
            "code_indexer.cli.QdrantClient"
        ) as mock_qdrant:

            # Setup mocks
            mock_docker_instance = MagicMock()
            mock_docker_instance.cleanup.return_value = True
            mock_docker.return_value = mock_docker_instance

            mock_qdrant_instance = MagicMock()
            mock_qdrant_instance.health_check.return_value = True
            mock_qdrant_instance.collection_exists.return_value = True
            mock_qdrant_instance.clear_collection.return_value = True
            mock_qdrant.return_value = mock_qdrant_instance

            # Use the full CLI to get proper context setup
            result = runner.invoke(cli, ["clean", "--remove-data"])

            assert result.exit_code == 0

            # Should call cleanup with remove_data=False (project-specific cleanup)
            mock_docker_instance.cleanup.assert_called_once_with(remove_data=False)

            # Should clear the project's collection
            mock_qdrant_instance.clear_collection.assert_called_once()

            assert "Current project data and configuration removed" in result.output

            # Config should be removed
            assert not self.config_file.exists()
            assert not self.config_dir.exists()

    def test_clean_all_projects_data(self):
        """Test clean --remove-data --all-projects (old behavior for all projects)."""
        from click.testing import CliRunner
        from code_indexer.cli import cli

        runner = CliRunner()

        with patch("code_indexer.cli.DockerManager") as mock_docker:
            mock_docker_instance = MagicMock()
            mock_docker_instance.cleanup.return_value = True
            mock_docker.return_value = mock_docker_instance

            result = runner.invoke(cli, ["clean", "--remove-data", "--all-projects"])

            assert result.exit_code == 0

            # Should call cleanup with remove_data=True (removes all data including volumes)
            mock_docker_instance.cleanup.assert_called_once_with(remove_data=True)

            assert "All project data and configuration removed" in result.output

            # Config should be removed
            assert not self.config_file.exists()
            assert not self.config_dir.exists()

    def test_clean_all_projects_without_remove_data_fails(self):
        """Test that --all-projects without --remove-data fails with error."""
        from click.testing import CliRunner
        from code_indexer.cli import cli

        runner = CliRunner()

        result = runner.invoke(cli, ["clean", "--all-projects"])

        assert result.exit_code == 1
        assert "--all-projects can only be used with --remove-data" in result.output

    def test_clean_current_project_with_qdrant_unavailable(self):
        """Test clean --remove-data when Qdrant is unavailable (graceful fallback)."""
        from click.testing import CliRunner
        from code_indexer.cli import cli

        runner = CliRunner()

        with patch("code_indexer.cli.DockerManager") as mock_docker, patch(
            "code_indexer.cli.QdrantClient"
        ) as mock_qdrant:

            # Setup mocks
            mock_docker_instance = MagicMock()
            mock_docker_instance.cleanup.return_value = True
            mock_docker.return_value = mock_docker_instance

            mock_qdrant_instance = MagicMock()
            mock_qdrant_instance.health_check.return_value = False  # Qdrant unavailable
            mock_qdrant.return_value = mock_qdrant_instance

            result = runner.invoke(cli, ["clean", "--remove-data"])

            assert result.exit_code == 0

            # Should still remove local config even if Qdrant is unavailable
            assert "Current project data and configuration removed" in result.output

            # Config should be removed
            assert not self.config_file.exists()
            assert not self.config_dir.exists()

    def test_clean_current_project_with_config_load_failure(self):
        """Test clean --remove-data when config loading fails (graceful fallback)."""
        from click.testing import CliRunner
        from code_indexer.cli import cli

        runner = CliRunner()

        # Remove config file to simulate load failure
        self.config_file.unlink()

        with patch("code_indexer.cli.DockerManager") as mock_docker:
            mock_docker_instance = MagicMock()
            mock_docker_instance.cleanup.return_value = True
            mock_docker.return_value = mock_docker_instance

            result = runner.invoke(cli, ["clean", "--remove-data"])

            assert result.exit_code == 0

            # Should either succeed in clearing collection or handle failure gracefully
            assert (
                "Current project data and configuration removed" in result.output
                or "Could not clear project collection" in result.output
                or "Local configuration removed" in result.output
            )

            # Config directory should still be removed
            assert not self.config_dir.exists()

    def test_clean_quiet_mode(self):
        """Test clean command with --quiet flag."""
        from click.testing import CliRunner
        from code_indexer.cli import cli

        runner = CliRunner()

        with patch("code_indexer.cli.DockerManager") as mock_docker:
            mock_docker_instance = MagicMock()
            mock_docker_instance.cleanup.return_value = True
            mock_docker.return_value = mock_docker_instance

            result = runner.invoke(cli, ["clean", "--quiet"])

            assert result.exit_code == 0
            # In quiet mode, output should be minimal
            assert (
                len(result.output.strip()) == 0 or "Services stopped" in result.output
            )

    def test_clean_docker_cleanup_failure(self):
        """Test clean command when Docker cleanup fails."""
        from click.testing import CliRunner
        from code_indexer.cli import cli

        runner = CliRunner()

        with patch("code_indexer.cli.DockerManager") as mock_docker:
            mock_docker_instance = MagicMock()
            mock_docker_instance.cleanup.return_value = False  # Simulate failure
            mock_docker.return_value = mock_docker_instance

            result = runner.invoke(cli, ["clean"])

            assert result.exit_code == 1  # Should exit with error code

    def test_clean_help_text(self):
        """Test that help text is properly updated."""
        from click.testing import CliRunner
        from code_indexer.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["clean", "--help"])

        assert result.exit_code == 0
        assert "Remove current project's data and configuration" in result.output
        assert "Remove data for ALL projects" in result.output
        assert (
            "By default, --remove-data only removes the current project's data"
            in result.output
        )


class TestCleanCommandIntegration:
    """Integration tests for clean command (requires actual services in CI-excluded tests)."""

    @pytest.mark.skipif(
        os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
        reason="Integration tests require Docker services which are not available in CI",
    )
    def test_clean_integration_project_specific(self):
        """Integration test for project-specific cleanup."""
        # This would require actual Docker services running
        # Implementation would be similar to existing end-to-end tests
        # but testing the new project-specific behavior
        pass

    @pytest.mark.skipif(
        os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
        reason="Integration tests require Docker services which are not available in CI",
    )
    def test_clean_integration_all_projects(self):
        """Integration test for all-projects cleanup."""
        # This would require actual Docker services running
        # Implementation would test that --all-projects removes everything
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

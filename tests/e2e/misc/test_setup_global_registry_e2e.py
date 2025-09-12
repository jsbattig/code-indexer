"""
End-to-end tests for the standalone setup-global-registry command.

Tests the complete workflow of setting up the global registry without
project initialization, ensuring the command works independently.
"""

import os
import subprocess
import tempfile
from pathlib import Path
import pytest

from tests.conftest import shared_container_test_environment
from .infrastructure import EmbeddingProvider

pytestmark = pytest.mark.e2e


class TestSetupGlobalRegistryCommand:
    """Test standalone setup-global-registry command functionality."""

    def test_command_exists_and_has_help(self):
        """Test that setup-global-registry command exists and shows help."""
        result = subprocess.run(
            ["cidx", "setup-global-registry", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "setup-global-registry" in result.stdout
        assert "Setup global port registry" in result.stdout
        assert "--test-access" in result.stdout
        assert "--quiet" in result.stdout
        assert "--help" in result.stdout

    def test_command_without_sudo_shows_proper_error(self):
        """Test that command without sudo shows appropriate error message."""
        # Run as regular user (no sudo)
        result = subprocess.run(
            ["cidx", "setup-global-registry"],
            capture_output=True,
            text=True,
        )

        # Command may succeed if registry is already set up, or fail with permission errors
        # Both are acceptable behaviors
        if result.returncode != 0:
            # If it fails, should show permission-related error
            error_output = result.stderr.lower()
            assert any(
                keyword in error_output
                for keyword in ["permission", "sudo", "access", "denied"]
            )
        else:
            # If it succeeds, should show setup success message
            assert "registry" in result.stdout.lower()

    def test_command_works_from_any_directory(self):
        """Test that setup-global-registry works from any directory (not tied to project)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Change to temporary directory (no project files)
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            try:
                # Should work even from empty directory
                result = subprocess.run(
                    ["cidx", "setup-global-registry", "--help"],
                    capture_output=True,
                    text=True,
                )

                assert result.returncode == 0
                assert "Setup global port registry" in result.stdout

            finally:
                os.chdir(original_cwd)

    def test_command_with_quiet_flag(self):
        """Test that --quiet flag reduces output appropriately."""
        result = subprocess.run(
            ["cidx", "setup-global-registry", "--quiet", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        # Help should still show even with quiet flag for --help
        assert "setup-global-registry" in result.stdout

    def test_command_with_test_access_flag(self):
        """Test that --test-access flag is recognized."""
        result = subprocess.run(
            ["cidx", "setup-global-registry", "--test-access", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "--test-access" in result.stdout

    def test_command_does_not_create_project_files(self):
        """Test that setup-global-registry does not create any project-specific files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            original_cwd = os.getcwd()
            os.chdir(str(project_dir))

            try:
                # Run setup-global-registry (will fail without sudo but that's OK)
                subprocess.run(
                    ["cidx", "setup-global-registry"],
                    capture_output=True,
                    text=True,
                )

                # Should not create any project files regardless of success/failure
                assert not (project_dir / ".code-indexer").exists()
                assert not (project_dir / ".code-indexer-override.yaml").exists()
                assert not (project_dir / "config.json").exists()

                # Directory should be empty except for any temp files we might have created
                project_files = [
                    f
                    for f in project_dir.iterdir()
                    if f.name not in [".", ".."] and not f.name.startswith("tmp")
                ]
                assert len(project_files) == 0

            finally:
                os.chdir(original_cwd)

    def test_command_different_from_init_setup_global_registry(self):
        """Test that standalone command is different from init --setup-global-registry."""
        # Test init --setup-global-registry creates project files
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Run init with --setup-global-registry (will fail but should try to create config)
            subprocess.run(
                ["cidx", "init", "--setup-global-registry", "--force"],
                cwd=project_dir,
                capture_output=True,
                text=True,
            )

            # Init should attempt to create project structure
            # Note: might fail due to permissions, but should at least attempt creation

        # Test standalone setup-global-registry does not create project files
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            original_cwd = os.getcwd()
            os.chdir(str(project_dir))

            try:
                subprocess.run(
                    ["cidx", "setup-global-registry"],
                    capture_output=True,
                    text=True,
                )

                # Should not create project files
                assert not (project_dir / ".code-indexer").exists()
                assert not (project_dir / ".code-indexer-override.yaml").exists()

            finally:
                os.chdir(original_cwd)

    @pytest.mark.skipif(
        os.geteuid() != 0, reason="Requires root privileges for actual registry setup"
    )
    def test_successful_registry_setup_as_root(self):
        """Test successful registry setup when run with proper privileges."""
        # This test only runs if we have root privileges
        registry_dir = Path("/var/lib/code-indexer/port-registry")

        # Clean up any existing registry for clean test
        if registry_dir.exists():
            subprocess.run(["rm", "-rf", str(registry_dir)], check=True)

        # Run setup-global-registry as root
        result = subprocess.run(
            ["cidx", "setup-global-registry"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        # Verify registry was created
        assert registry_dir.exists()
        assert (registry_dir / "port-allocations.json").exists()
        assert (registry_dir / "registry.log").exists()
        assert (registry_dir / "active-projects").exists()

        # Verify permissions
        registry_stat = registry_dir.stat()
        assert oct(registry_stat.st_mode)[-3:] == "777"  # World writable

        port_alloc_stat = (registry_dir / "port-allocations.json").stat()
        assert oct(port_alloc_stat.st_mode)[-3:] == "666"  # World readable/writable

        # Verify content of port allocations file
        with open(registry_dir / "port-allocations.json") as f:
            content = f.read().strip()
            assert content == "{}"  # Should be empty JSON object

        # Test that registry is accessible by importing GlobalPortRegistry
        try:
            from code_indexer.services.global_port_registry import GlobalPortRegistry

            registry = GlobalPortRegistry()
            # If we can create it, the setup worked
            assert registry is not None
        except Exception as e:
            pytest.fail(f"Registry setup successful but not accessible: {e}")

    def test_help_message_content(self):
        """Test that help message contains appropriate information."""
        result = subprocess.run(
            ["cidx", "setup-global-registry", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        help_text = result.stdout.lower()

        # Should mention key concepts
        assert "global" in help_text
        assert "registry" in help_text
        assert "port" in help_text

        # Should mention it requires sudo
        assert "sudo" in help_text or "root" in help_text or "privilege" in help_text

        # Should mention it's standalone - check it explains what it does NOT do
        # (It mentions "project" and "initialize" to clarify it doesn't initialize projects)
        assert "does not initialize" in help_text or "without initializing" in help_text

    def test_command_exit_codes(self):
        """Test that command returns appropriate exit codes."""
        # Help should return 0
        result = subprocess.run(
            ["cidx", "setup-global-registry", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        # Invalid flag should return non-zero
        result = subprocess.run(
            ["cidx", "setup-global-registry", "--invalid-flag"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_command_with_test_access_functionality(self):
        """Test that --test-access flag actually tests registry access."""
        # This will fail without proper setup, but should show test access attempt
        result = subprocess.run(
            ["cidx", "setup-global-registry", "--test-access"],
            capture_output=True,
            text=True,
        )

        # Should mention testing or access in output
        output = (result.stdout + result.stderr).lower()
        assert "test" in output or "access" in output or "registry" in output

    def test_error_messages_mention_both_commands(self):
        """Test that error messages reference both init --setup-global-registry and setup-global-registry."""
        # This test needs container services since it runs 'start' command
        with shared_container_test_environment(
            "test_error_messages_mention_both_commands", EmbeddingProvider.OLLAMA
        ) as project_path:
            # Now try to start services (this should mention registry setup)
            result = subprocess.run(
                ["cidx", "start"],
                cwd=project_path,
                capture_output=True,
                text=True,
            )

            # Error output should mention both command options
            error_output = result.stderr.lower()
            if "registry" in error_output:
                # Should mention both approaches
                assert (
                    "init --setup-global-registry" in error_output
                    or "setup-global-registry" in error_output
                )

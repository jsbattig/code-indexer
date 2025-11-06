"""E2E tests for complete filesystem backend isolation from port registry in ALL CLI commands."""

import os
import subprocess
import tempfile
from pathlib import Path
import pytest


class TestFilesystemCompleteIsolation:
    """Tests ensuring NO port registry access for ALL CLI commands with filesystem backend."""

    def test_clean_data_command_no_port_registry_access(self):
        """Test that clean-data command with filesystem backend never touches port registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "test_project"
            project_dir.mkdir()

            # Create test file
            test_file = project_dir / "test.py"
            test_file.write_text("def hello(): pass")

            # Initialize with filesystem backend
            result = subprocess.run(
                ["cidx", "init", "--vector-store", "filesystem"],
                cwd=project_dir,
                capture_output=True,
                text=True
            )
            assert result.returncode == 0, f"Init failed: {result.stderr}"

            # Index to create some data
            result = subprocess.run(
                ["cidx", "index"],
                cwd=project_dir,
                capture_output=True,
                text=True
            )
            assert result.returncode == 0, f"Index failed: {result.stderr}"

            # Set environment to detect port registry access
            env = os.environ.copy()
            env["CIDX_TEST_PORT_REGISTRY_PATH"] = "/tmp/SHOULD_NOT_EXIST"
            env["CIDX_TEST_FAIL_ON_PORT_REGISTRY"] = "1"

            # Run clean-data - should NOT trigger port registry
            result = subprocess.run(
                ["cidx", "clean-data"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                env=env
            )

            # Should succeed without port registry
            assert result.returncode == 0, f"Clean-data failed: {result.stderr}"
            assert "Filesystem backend" in result.stdout or "no containers to clean" in result.stdout.lower(), \
                f"Expected filesystem message in output: {result.stdout}"

            # Verify no port registry file was created
            assert not Path("/tmp/SHOULD_NOT_EXIST").exists(), \
                "Port registry was accessed despite filesystem backend"

    def test_uninstall_command_no_port_registry_access(self):
        """Test that uninstall command with filesystem backend never touches port registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "test_project"
            project_dir.mkdir()

            # Create test file
            test_file = project_dir / "test.py"
            test_file.write_text("def world(): pass")

            # Initialize with filesystem backend
            result = subprocess.run(
                ["cidx", "init", "--vector-store", "filesystem"],
                cwd=project_dir,
                capture_output=True,
                text=True
            )
            assert result.returncode == 0, f"Init failed: {result.stderr}"

            # Set environment to detect port registry access
            env = os.environ.copy()
            env["CIDX_TEST_PORT_REGISTRY_PATH"] = "/tmp/SHOULD_NOT_EXIST_UNINSTALL"
            env["CIDX_TEST_FAIL_ON_PORT_REGISTRY"] = "1"

            # Run uninstall with --confirm to skip confirmation prompt
            result = subprocess.run(
                ["cidx", "uninstall", "--confirm"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                env=env
            )

            # Should succeed without port registry
            assert result.returncode == 0, f"Uninstall failed: {result.stderr}"

            # Should mention filesystem or no containers
            output_lower = result.stdout.lower()
            assert "filesystem" in output_lower or "no containers" in output_lower or \
                   "skipping container" in output_lower, \
                f"Expected filesystem/container message in output: {result.stdout}"

            # Verify no port registry file was created
            assert not Path("/tmp/SHOULD_NOT_EXIST_UNINSTALL").exists(), \
                "Port registry was accessed despite filesystem backend"

    def test_clean_command_no_port_registry_access(self):
        """Verify cidx clean with filesystem backend doesn't access port registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "test_project"
            project_dir.mkdir()

            # Create test file
            test_file = project_dir / "test.py"
            test_file.write_text("def cleanup_test(): pass")

            # Initialize with filesystem backend
            result = subprocess.run(
                ["cidx", "init", "--vector-store", "filesystem"],
                cwd=project_dir,
                capture_output=True,
                text=True
            )
            assert result.returncode == 0, f"Init failed: {result.stderr}"

            # Index to create some data
            result = subprocess.run(
                ["cidx", "index"],
                cwd=project_dir,
                capture_output=True,
                text=True
            )
            assert result.returncode == 0, f"Index failed: {result.stderr}"

            # Set environment to detect port registry access
            env = os.environ.copy()
            env["CIDX_TEST_PORT_REGISTRY_PATH"] = "/tmp/SHOULD_NOT_EXIST_CLEANUP"
            env["CIDX_TEST_FAIL_ON_PORT_REGISTRY"] = "1"

            # Run clean - should NOT trigger port registry
            result = subprocess.run(
                ["cidx", "clean", "--force"],  # Add --force to skip prompt
                cwd=project_dir,
                capture_output=True,
                text=True,
                env=env
            )

            # Should succeed without port registry
            assert result.returncode == 0, f"Clean failed: {result.stderr}"

            # Should mention successful cleaning
            output_lower = result.stdout.lower()
            assert "cleaned successfully" in output_lower or "storage reclaimed" in output_lower or \
                   "nothing to clean" in output_lower, \
                f"Expected clean success message in output: {result.stdout}"

            # Verify no port registry file was created
            assert not Path("/tmp/SHOULD_NOT_EXIST_CLEANUP").exists(), \
                "Port registry was accessed despite filesystem backend"

    def test_uninstall_wipe_all_no_port_registry_access(self):
        """Verify cidx uninstall --wipe-all with filesystem backend doesn't access port registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "test_project"
            project_dir.mkdir()

            # Create test file
            test_file = project_dir / "test.py"
            test_file.write_text("def wipe_test(): pass")

            # Initialize with filesystem backend
            result = subprocess.run(
                ["cidx", "init", "--vector-store", "filesystem"],
                cwd=project_dir,
                capture_output=True,
                text=True
            )
            assert result.returncode == 0, f"Init failed: {result.stderr}"

            # Set environment to detect port registry access
            env = os.environ.copy()
            env["CIDX_TEST_PORT_REGISTRY_PATH"] = "/tmp/SHOULD_NOT_EXIST_WIPE_ALL"
            env["CIDX_TEST_FAIL_ON_PORT_REGISTRY"] = "1"

            # Run uninstall --wipe-all with --confirm to skip confirmation prompt
            result = subprocess.run(
                ["cidx", "uninstall", "--wipe-all", "--confirm"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                env=env
            )

            # Should succeed without port registry
            assert result.returncode == 0, f"Uninstall --wipe-all failed: {result.stderr}"

            # Should mention filesystem or no containers
            output_lower = result.stdout.lower()
            assert "filesystem" in output_lower or "no containers" in output_lower or \
                   "skipping container" in output_lower or "wipe" in output_lower or \
                   "uninstall complete" in output_lower, \
                f"Expected filesystem/wipe message in output: {result.stdout}"

            # Verify no port registry file was created
            assert not Path("/tmp/SHOULD_NOT_EXIST_WIPE_ALL").exists(), \
                "Port registry was accessed despite filesystem backend"


if __name__ == "__main__":
    pytest.main([__file__, "-xvs"])
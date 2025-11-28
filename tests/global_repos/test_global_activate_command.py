"""
Tests for 'cidx global activate' retry command (AC4).

Tests manual global activation command for retrying failed activations.
"""

import subprocess
import tempfile
from pathlib import Path


class TestGlobalActivateCommand:
    """
    Tests for AC4: Retry Mechanism via cidx global activate command.
    """

    def test_global_activate_command_creates_alias(self):
        """
        Test that 'cidx global activate' creates a global alias.

        AC4 Requirement: Manual retry command for global activation.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup: Create a golden repo directory
            golden_repos_dir = Path(tmpdir) / "golden-repos"
            repos_dir = golden_repos_dir / "repos"
            repos_dir.mkdir(parents=True)

            # Create a fake golden repo
            test_repo_dir = repos_dir / "test-repo"
            test_repo_dir.mkdir(parents=True)
            index_dir = test_repo_dir / ".code-indexer" / "index"
            index_dir.mkdir(parents=True)

            # Test: Run cidx global activate
            env = {
                **subprocess.os.environ,
                "CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir),
            }

            result = subprocess.run(
                ["cidx", "global", "activate", "test-repo"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                env=env,
            )

            # Verify: Command succeeded
            assert result.returncode == 0, f"Command failed: {result.stderr}"

            # Verify: Alias was created
            alias_file = golden_repos_dir / "aliases" / "test-repo-global.json"
            assert alias_file.exists(), "Alias file not created"

    def test_global_activate_command_with_nonexistent_repo_fails(self):
        """
        Test that 'cidx global activate' fails gracefully for nonexistent repo.

        AC4 Requirement: Error handling for retry command.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_repos_dir = Path(tmpdir) / "golden-repos"

            env = {
                **subprocess.os.environ,
                "CIDX_GOLDEN_REPOS_DIR": str(golden_repos_dir),
            }

            result = subprocess.run(
                ["cidx", "global", "activate", "nonexistent-repo"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                env=env,
            )

            # Verify: Command failed with appropriate error
            assert (
                result.returncode != 0
            ), "Expected command to fail for nonexistent repo"
            assert (
                "not found" in result.stderr.lower()
                or "not found" in result.stdout.lower()
            ), "Expected error message about repo not found"

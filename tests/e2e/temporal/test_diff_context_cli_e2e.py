"""E2E tests for diff-context configuration via CLI.

Tests the --diff-context flag, --set-diff-context config command,
and config --show display of diff-context settings.
"""

import json
import pytest
import subprocess


class TestDiffContextCLIE2E:
    """End-to-end tests for diff-context CLI integration."""

    @pytest.fixture
    def temp_test_repo(self, tmp_path):
        """Create a temporary git repository for testing."""
        repo_path = tmp_path / "test_diff_context_repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create initial commit with a function
        file_path = repo_path / "example.py"
        file_path.write_text("# Initial version\ndef function_v1():\n    return 1\n")
        subprocess.run(
            ["git", "add", "."], cwd=repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Initialize cidx
        cidx_dir = repo_path / ".code-indexer"
        cidx_dir.mkdir(parents=True, exist_ok=True)
        config_file = cidx_dir / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "codebase_dir": str(repo_path),
                    "embedding_provider": "voyage-ai",
                    "voyage_ai": {
                        "model": "voyage-code-3",
                        "parallel_requests": 1,
                    },
                }
            )
        )

        return repo_path

    def test_config_show_displays_default_diff_context(self, temp_test_repo):
        """Test that cidx config --show displays default diff-context value.

        Given a CIDX repository without explicit temporal config
        When I run cidx config --show
        Then output should display "Diff Context: 5 lines (default)"
        """
        # Act: Run config --show
        result = subprocess.run(
            ["cidx", "config", "--show"],
            cwd=temp_test_repo,
            capture_output=True,
            text=True,
        )

        # Assert: Command succeeds
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Assert: Output contains default diff context
        assert "Diff Context:" in result.stdout
        assert "5 lines" in result.stdout
        assert "(default)" in result.stdout

    def test_config_show_displays_custom_diff_context(self, temp_test_repo):
        """Test that cidx config --show displays custom diff-context value.

        Given a CIDX repository with custom temporal config (10 lines)
        When I run cidx config --show
        Then output should display "Diff Context: 10 lines (custom)"
        """
        # Arrange: Set custom diff-context in config
        config_path = temp_test_repo / ".code-indexer" / "config.json"
        with open(config_path, "r") as f:
            config = json.load(f)
        config["temporal"] = {"diff_context_lines": 10}
        with open(config_path, "w") as f:
            json.dump(config, f)

        # Act: Run config --show
        result = subprocess.run(
            ["cidx", "config", "--show"],
            cwd=temp_test_repo,
            capture_output=True,
            text=True,
        )

        # Assert: Command succeeds
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Assert: Output contains custom diff context
        assert "Diff Context:" in result.stdout
        assert "10 lines" in result.stdout
        assert "(custom)" in result.stdout

    def test_set_diff_context_updates_config(self, temp_test_repo):
        """Test that cidx config --set-diff-context updates configuration.

        Given a CIDX repository
        When I run cidx config --set-diff-context 10
        Then config.json should contain temporal.diff_context_lines = 10
        And command should output success message
        """
        # Act: Set diff-context to 10
        result = subprocess.run(
            ["cidx", "config", "--set-diff-context", "10"],
            cwd=temp_test_repo,
            capture_output=True,
            text=True,
        )

        # Assert: Command succeeds
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Assert: Success message displayed
        assert "Diff context set to 10 lines" in result.stdout or "✅" in result.stdout

        # Assert: Config file updated
        config_path = temp_test_repo / ".code-indexer" / "config.json"
        with open(config_path, "r") as f:
            config = json.load(f)
        assert "temporal" in config
        assert config["temporal"]["diff_context_lines"] == 10

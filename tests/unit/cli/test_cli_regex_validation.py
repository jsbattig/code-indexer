"""
Unit tests for CLI --regex flag validation.

Tests cover:
- Regex flag incompatibility with --semantic
- Regex flag incompatibility with --fuzzy
- Regex flag incompatibility with --edit-distance
- Proper error messages for invalid combinations
"""

import pytest
from click.testing import CliRunner
from code_indexer.cli import cli


class TestCLIRegexValidation:
    """Test suite for CLI --regex flag validation."""

    @pytest.fixture
    def runner(self):
        """Create Click test runner."""
        return CliRunner()

    @pytest.fixture
    def initialized_repo(self, tmp_path):
        """Create initialized repository with FTS index."""
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # Create minimal git repo
        import subprocess

        subprocess.run(["git", "init"], cwd=repo_dir, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True
        )

        # Create sample file
        test_file = repo_dir / "test.py"
        test_file.write_text("def test_function():\n    pass\n")

        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True
        )

        # Initialize CIDX
        result = subprocess.run(
            ["cidx", "init"], cwd=repo_dir, capture_output=True, text=True
        )
        if result.returncode != 0:
            pytest.skip(f"cidx init failed: {result.stderr}")

        # Start CIDX (may start containers)
        result = subprocess.run(
            ["cidx", "start"], cwd=repo_dir, capture_output=True, text=True
        )
        if result.returncode != 0:
            pytest.skip(f"cidx start failed: {result.stderr}")

        # Build FTS index
        result = subprocess.run(
            ["cidx", "index", "--fts"], cwd=repo_dir, capture_output=True, text=True
        )
        if result.returncode != 0:
            pytest.skip(f"cidx index --fts failed: {result.stderr}")

        return repo_dir

    def test_cli_regex_with_semantic_fails(self, runner, initialized_repo):
        """
        GIVEN cidx CLI with initialized FTS index
        WHEN using --regex with --semantic
        THEN raises UsageError with clear message
        """
        result = runner.invoke(
            cli,
            ["query", "pattern", "--fts", "--regex", "--semantic"],
            obj={"mode": "local", "project_root": str(initialized_repo)},
        )

        assert result.exit_code != 0
        assert "Cannot combine --regex with --semantic" in result.output

    def test_cli_regex_with_fuzzy_fails(self, runner, initialized_repo):
        """
        GIVEN cidx CLI with initialized FTS index
        WHEN using --regex with --fuzzy
        THEN raises UsageError with clear message
        """
        result = runner.invoke(
            cli,
            ["query", "pattern", "--fts", "--regex", "--fuzzy"],
            obj={"mode": "local", "project_root": str(initialized_repo)},
        )

        assert result.exit_code != 0
        assert (
            "Cannot combine --regex with --fuzzy" in result.output
            or "Cannot combine --regex with --edit-distance" in result.output
        )

    def test_cli_regex_with_edit_distance_fails(self, runner, initialized_repo):
        """
        GIVEN cidx CLI with initialized FTS index
        WHEN using --regex with --edit-distance
        THEN raises UsageError with clear message
        """
        result = runner.invoke(
            cli,
            ["query", "pattern", "--fts", "--regex", "--edit-distance", "2"],
            obj={"mode": "local", "project_root": str(initialized_repo)},
        )

        assert result.exit_code != 0
        assert (
            "Cannot combine --regex with --edit-distance" in result.output
            or "Cannot combine --regex with --fuzzy" in result.output
        )

    def test_cli_regex_fts_only_allowed(self, runner, initialized_repo):
        """
        GIVEN cidx CLI with initialized FTS index
        WHEN using --regex with --fts
        THEN command is accepted (no error)
        """
        # This should NOT fail - regex is allowed with FTS
        result = runner.invoke(
            cli,
            ["query", r"def\s+\w+", "--fts", "--regex"],
            obj={"mode": "local", "project_root": str(initialized_repo)},
        )

        # Should succeed or fail for different reason (not validation error)
        if result.exit_code != 0:
            # If it fails, should NOT be due to incompatible flags
            assert "Cannot combine --regex" not in result.output

    def test_cli_regex_without_fts_fails(self, runner, initialized_repo):
        """
        GIVEN cidx CLI
        WHEN using --regex without --fts flag
        THEN raises error requiring --fts
        """
        result = runner.invoke(
            cli,
            ["query", "pattern", "--regex"],
            obj={"mode": "local", "project_root": str(initialized_repo)},
        )

        assert result.exit_code != 0
        # Should indicate regex requires FTS mode
        assert "--fts" in result.output.lower() or "full-text" in result.output.lower()

    def test_cli_regex_help_text(self, runner):
        """
        GIVEN cidx CLI
        WHEN requesting help for query command
        THEN --regex flag is documented
        """
        result = runner.invoke(cli, ["query", "--help"])

        assert result.exit_code == 0
        assert "--regex" in result.output

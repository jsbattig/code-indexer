"""Tests for CLI global configuration commands.

Tests the 2 CLI commands for global repository configuration:
- set-global-refresh
- show-global
"""

import pytest
from click.testing import CliRunner
from code_indexer.cli import cli
import tempfile
from pathlib import Path
import json


@pytest.fixture
def temp_golden_repos(monkeypatch):
    """Create temporary golden repos directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        golden_dir = Path(tmpdir) / "golden-repos"
        golden_dir.mkdir(parents=True)

        # Set environment variable
        monkeypatch.setenv("GOLDEN_REPOS_DIR", str(golden_dir))

        yield str(golden_dir)


def test_cli_show_global_config(temp_golden_repos):
    """Test show-global command displays configuration."""
    runner = CliRunner()
    result = runner.invoke(cli, ['show-global'])
    assert result.exit_code == 0
    assert "Global Repository Configuration" in result.output
    assert "Refresh Interval" in result.output


def test_cli_set_global_refresh(temp_golden_repos):
    """Test set-global-refresh command updates interval."""
    runner = CliRunner()
    result = runner.invoke(cli, ['set-global-refresh', '300'])
    assert result.exit_code == 0
    assert "300 seconds" in result.output


def test_cli_set_global_refresh_validates_minimum(temp_golden_repos):
    """Test set-global-refresh validates minimum interval."""
    runner = CliRunner()
    result = runner.invoke(cli, ['set-global-refresh', '30'])
    assert result.exit_code == 4
    assert "at least 60" in result.output


def test_cli_set_global_refresh_persists(temp_golden_repos):
    """Test set-global-refresh persists configuration."""
    runner = CliRunner()

    # Set interval
    result1 = runner.invoke(cli, ['set-global-refresh', '120'])
    assert result1.exit_code == 0

    # Verify it persists
    result2 = runner.invoke(cli, ['show-global'])
    assert result2.exit_code == 0
    assert "120 seconds" in result2.output

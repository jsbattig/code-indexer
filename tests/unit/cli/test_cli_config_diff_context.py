"""Unit tests for cidx config diff-context commands (Story #443 - AC4, AC5).

Tests the config set-diff-context and config show commands.
"""

import json
import subprocess
import sys

import pytest


class TestConfigDiffContext:
    """Test config commands for diff-context management."""

    def run_cli_command(self, args, cwd=None, expect_failure=False):
        """Run CLI command and return result."""
        cmd = [sys.executable, "-m", "code_indexer.cli"] + args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=cwd,
        )

        if expect_failure:
            assert (
                result.returncode != 0
            ), f"Command should have failed: {' '.join(cmd)}"
        else:
            if result.returncode != 0:
                print(f"STDOUT: {result.stdout}")
                print(f"STDERR: {result.stderr}")
            assert result.returncode == 0, f"Command failed: {result.stderr}"

        return result

    def test_config_set_diff_context_saves_to_config_file(self, tmp_path):
        """AC4: config --set-diff-context saves setting persistently."""
        # Create test project with config
        test_dir = tmp_path / "test_project"
        test_dir.mkdir()
        config_dir = test_dir / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"

        # Create minimal config
        config_file.write_text(json.dumps({"codebase_dir": str(test_dir)}))

        # Run config --set-diff-context
        result = self.run_cli_command(
            ["config", "--set-diff-context", "10"], cwd=test_dir
        )

        # Should show success message
        assert "✅" in result.stdout or "success" in result.stdout.lower()
        assert "10" in result.stdout

        # Verify config file was updated
        config_data = json.loads(config_file.read_text())
        assert "temporal" in config_data
        assert config_data["temporal"]["diff_context_lines"] == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Integration test for YAML creation during CLI init."""

import tempfile
import shutil
from pathlib import Path
from click.testing import CliRunner
import os

from code_indexer.cli import cli


class TestCLIInitYAMLCreation:
    """Test YAML file creation during cidx init."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        self.runner = CliRunner()

    def teardown_method(self):
        """Clean up."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)

    def test_init_creates_language_mappings_yaml(self):
        """Test that cidx init creates language-mappings.yaml."""
        result = self.runner.invoke(cli, ["init"])

        # Check command succeeded
        assert result.exit_code == 0

        # Check YAML file was created
        yaml_path = Path(self.temp_dir) / ".code-indexer" / "language-mappings.yaml"
        assert yaml_path.exists()

        # Verify content
        with open(yaml_path, "r") as f:
            content = f.read()
            assert "python:" in content
            assert "[py, pyw, pyi]" in content

        # Verify success message
        assert (
            "Created language-mappings.yaml for query language filtering"
            in result.output
        )

    def test_init_force_overwrites_yaml(self):
        """Test that --force overwrites existing YAML."""
        # First init
        self.runner.invoke(cli, ["init"])

        # Modify YAML
        yaml_path = Path(self.temp_dir) / ".code-indexer" / "language-mappings.yaml"
        with open(yaml_path, "w") as f:
            f.write("custom: content\n")

        # Force init
        result = self.runner.invoke(cli, ["init", "--force"])
        assert result.exit_code == 0

        # Verify YAML was reset
        with open(yaml_path, "r") as f:
            content = f.read()
            assert "python:" in content
            assert "custom: content" not in content

        # Verify success message appears again
        assert (
            "Created language-mappings.yaml for query language filtering"
            in result.output
        )

    def test_init_no_overwrite_existing_yaml(self):
        """Test that existing YAML is not overwritten without force."""
        # First init
        result1 = self.runner.invoke(cli, ["init"])
        assert result1.exit_code == 0
        assert (
            "Created language-mappings.yaml for query language filtering"
            in result1.output
        )

        # Modify YAML
        yaml_path = Path(self.temp_dir) / ".code-indexer" / "language-mappings.yaml"
        with open(yaml_path, "w") as f:
            f.write("custom: modified\n")

        # Second init without force should fail because config exists
        result2 = self.runner.invoke(cli, ["init"])
        assert result2.exit_code == 1
        assert "Configuration already exists" in result2.output

        # Verify YAML was not modified (because init exited early)
        with open(yaml_path, "r") as f:
            content = f.read()
            assert "custom: modified" in content

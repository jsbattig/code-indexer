"""Tests for CLI init command --qdrant-segment-size option."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


class TestCLIInitSegmentSize:
    """Test CLI init command --qdrant-segment-size option."""

    def run_init_command(self, args, cwd=None, expect_failure=False):
        """Run init command and return result."""
        cmd = [sys.executable, "-m", "code_indexer.cli", "init"] + args
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
            assert (
                result.returncode == 0
            ), f"Command failed: {result.stderr}\nStdout: {result.stdout}"

        return result

    def test_init_with_qdrant_segment_size_option_exists(self):
        """Test that --qdrant-segment-size option exists in init command help."""
        result = subprocess.run(
            [sys.executable, "-m", "code_indexer.cli", "init", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "--qdrant-segment-size" in result.stdout
        assert "Qdrant segment size in MB" in result.stdout

    def test_init_qdrant_segment_size_default_100mb(self):
        """Test that --qdrant-segment-size has default of 100 MB."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)
            self.run_init_command(["--force"], cwd=test_dir)

            # Check that config was created with default 102400 KB (100MB)
            config_file = test_dir / ".code-indexer" / "config.json"
            assert config_file.exists()

            with open(config_file) as f:
                config = json.load(f)

            assert config["qdrant"]["max_segment_size_kb"] == 102400

    def test_init_qdrant_segment_size_custom_value(self):
        """Test setting custom segment size via CLI option."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)

            # Test 50 MB = 51200 KB
            self.run_init_command(
                ["--qdrant-segment-size", "50", "--force"], cwd=test_dir
            )

            config_file = test_dir / ".code-indexer" / "config.json"
            assert config_file.exists()

            with open(config_file) as f:
                config = json.load(f)

            assert config["qdrant"]["max_segment_size_kb"] == 51200

    def test_init_qdrant_segment_size_mb_to_kb_conversion(self):
        """Test conversion from MB input to KB storage."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)

            # Test various conversions
            test_cases = [
                (10, 10240),  # 10 MB = 10240 KB
                (25, 25600),  # 25 MB = 25600 KB
                (200, 204800),  # 200 MB = 204800 KB
            ]

            for mb_input, expected_kb in test_cases:
                subdir = test_dir / f"test_{mb_input}mb"
                subdir.mkdir()

                self.run_init_command(
                    ["--qdrant-segment-size", str(mb_input), "--force"], cwd=subdir
                )

                config_file = subdir / ".code-indexer" / "config.json"
                assert config_file.exists()

                with open(config_file) as f:
                    config = json.load(f)

                assert config["qdrant"]["max_segment_size_kb"] == expected_kb

    def test_init_qdrant_segment_size_validation_positive(self):
        """Test that segment size must be positive."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)

            # Zero should be rejected
            result = self.run_init_command(
                ["--qdrant-segment-size", "0", "--force"],
                cwd=test_dir,
                expect_failure=True,
            )
            assert "Qdrant segment size must be positive" in result.stdout

            # Negative should be rejected
            result = self.run_init_command(
                ["--qdrant-segment-size", "-5", "--force"],
                cwd=test_dir,
                expect_failure=True,
            )
            assert "Qdrant segment size must be positive" in result.stdout

    def test_init_qdrant_segment_size_combines_with_other_options(self):
        """Test that --qdrant-segment-size works with other init options."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)

            self.run_init_command(
                [
                    "--qdrant-segment-size",
                    "75",
                    "--embedding-provider",
                    "voyage-ai",
                    "--max-file-size",
                    "2000000",
                    "--force",
                ],
                cwd=test_dir,
            )

            config_file = test_dir / ".code-indexer" / "config.json"
            assert config_file.exists()

            with open(config_file) as f:
                config = json.load(f)

            # Check segment size was set
            assert config["qdrant"]["max_segment_size_kb"] == 76800  # 75 MB

            # Check other options were also applied
            assert config["embedding_provider"] == "voyage-ai"
            assert config["indexing"]["max_file_size"] == 2000000

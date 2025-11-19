"""Integration test for ExceptionLogger initialization in CLI mode.

Verifies that ExceptionLogger is properly initialized when CLI starts and creates
the error log file in .code-indexer/ directory.
"""

import subprocess


class TestCLIModeExceptionLogger:
    """Test ExceptionLogger initialization in CLI mode."""

    def test_cli_initializes_exception_logger(self, tmp_path):
        """Test that CLI mode creates error log in .code-indexer/."""
        # Create a temporary project directory
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        # Initialize a git repo (required for CLI operations)
        subprocess.run(
            ["git", "init"],
            cwd=project_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=project_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=project_dir,
            check=True,
            capture_output=True,
        )

        # Create a dummy Python file to index
        test_file = project_dir / "test.py"
        test_file.write_text("def test():\n    pass\n")

        # Commit the test file
        subprocess.run(
            ["git", "add", "test.py"],
            cwd=project_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=project_dir,
            check=True,
            capture_output=True,
        )

        # Run CLI command that should initialize ExceptionLogger
        # Use 'cidx init' which definitely initializes the system
        result = subprocess.run(
            ["cidx", "init"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )

        # Verify .code-indexer directory exists
        code_indexer_dir = project_dir / ".code-indexer"
        assert code_indexer_dir.exists()

        # Find error log files (format: error_YYYYMMDD_HHMMSS_PID.log)
        error_logs = list(code_indexer_dir.glob("error_*.log"))

        # Should have at least one error log file
        assert len(error_logs) >= 1, f"No error log files found in {code_indexer_dir}"

        # Verify log file naming format
        log_file = error_logs[0]
        assert log_file.name.startswith("error_")
        assert log_file.name.endswith(".log")

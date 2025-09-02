"""E2E Test Story 1: Complete CLI cleanup verification with proper service cleanup.

End-to-end test that verifies deprecated semantic options are completely removed
from CLI help and functionality, ensuring the cleanup is thorough and complete.
This test uses real CLI commands and performs proper cleanup.
"""

import subprocess
import tempfile
import shutil
import os
from pathlib import Path


class TestStory1CLICleanupE2E:
    """End-to-end test for CLI cleanup verification with proper service cleanup."""

    def setup_method(self):
        """Set up clean test environment."""
        # Create temporary directory for test operations
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

        # Track any containers/services started during test
        self.started_services = []

    def teardown_method(self):
        """Clean up test environment and any running services."""
        # Change back to original directory
        os.chdir(self.original_cwd)

        # Remove temporary directory
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

        # Stop any services that were started during test
        for service_info in self.started_services:
            try:
                subprocess.run(
                    ["python", "-m", "code_indexer.cli", "stop"],
                    capture_output=True,
                    timeout=30,
                )
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                pass  # Services might already be stopped

    def test_e2e_deprecated_semantic_options_completely_removed(self):
        """E2E test: Verify all deprecated semantic options are completely removed from CLI."""
        # Test each deprecated option to ensure it's not recognized
        deprecated_options = [
            ["--semantic-type", "function"],
            ["--type", "function"],
            ["--semantic-scope", "global"],
            ["--scope", "global"],
            ["--semantic-features", "async,static"],
            ["--features", "async,static"],
            ["--semantic-parent", "ClassName"],
            ["--parent", "ClassName"],
            ["--semantic-only"],
        ]

        for options in deprecated_options:
            # Test with query command
            cmd = (
                ["python", "-m", "code_indexer.cli", "query"] + options + ["test query"]
            )
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            # Should fail with "No such option" error
            assert (
                result.returncode != 0
            ), f"Command should fail for deprecated option: {options}"
            assert (
                "No such option" in result.stderr or "No such option" in result.stdout
            ), f"Should show 'No such option' error for: {options}"

    def test_e2e_query_help_contains_no_semantic_references(self):
        """E2E test: Verify query help contains no references to deprecated semantic options."""
        cmd = ["python", "-m", "code_indexer.cli", "query", "--help"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        assert result.returncode == 0, "Query help command should succeed"

        help_text = result.stdout.lower()

        # Check that deprecated options are not mentioned
        deprecated_mentions = [
            "--semantic-type",
            "--semantic-scope",
            "--semantic-features",
            "--semantic-parent",
            "--semantic-only",
            "result filtering (code structure)",
            "structured only:",
            "semantic filtering",
        ]

        for mention in deprecated_mentions:
            assert (
                mention not in help_text
            ), f"Deprecated reference '{mention}' found in query help text"

    def test_e2e_query_help_contains_no_semantic_examples(self):
        """E2E test: Verify query help contains no examples using deprecated semantic options."""
        cmd = ["python", "-m", "code_indexer.cli", "query", "--help"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        assert result.returncode == 0, "Query help command should succeed"

        help_text = result.stdout.lower()

        # Check that deprecated example patterns are not present
        deprecated_examples = [
            "--type function",
            "--type class",
            "--scope global",
            "--parent user",
            "--features async",
            "semantic-only",
        ]

        for example in deprecated_examples:
            assert (
                example not in help_text
            ), f"Deprecated example '{example}' found in query help text"

    def test_e2e_main_help_contains_no_semantic_references(self):
        """E2E test: Verify main CLI help contains no deprecated semantic references."""
        cmd = ["python", "-m", "code_indexer.cli", "--help"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        assert result.returncode == 0, "Main help command should succeed"

        help_text = result.stdout.lower()

        # Should not mention deprecated semantic options or AST chunking
        deprecated_references = [
            "semantic chunking",
            "ast-based",
            "tree-sitter",
            "tree sitter",
            "--semantic-type",
            "--semantic-scope",
            "--semantic-features",
            "--semantic-parent",
            "--semantic-only",
        ]

        for reference in deprecated_references:
            assert (
                reference not in help_text
            ), f"Deprecated reference '{reference}' found in main help text"

    def test_e2e_debug_files_are_removed(self):
        """E2E test: Verify debug files from failed C# implementation are removed."""
        # Navigate to project root dynamically
        project_root = Path(__file__).parent.parent.parent.parent
        debug_files = [
            project_root / "debug" / "test_async_api_implementation.py",
            project_root / "debug" / "test_async_api_no_auth.py",
        ]

        for debug_file in debug_files:
            assert not os.path.exists(
                debug_file
            ), f"Debug file {debug_file} should be removed from filesystem"

    def test_e2e_query_command_still_functional(self):
        """E2E test: Verify query command still works with valid options after cleanup."""
        # Test that basic query functionality still works
        cmd = ["python", "-m", "code_indexer.cli", "query", "--help"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        assert result.returncode == 0, "Query help should still work"

        help_text = result.stdout.lower()

        # Should still have valid options
        valid_options = [
            "--limit",
            "--language",
            "--path",
            "--min-score",
            "--accuracy",
            "--quiet",
        ]

        for option in valid_options:
            assert option in help_text, f"Valid option {option} should still be present"

    def test_e2e_comprehensive_cleanup_verification(self):
        """E2E test: Comprehensive verification that all cleanup requirements are met."""
        # Verify all acceptance criteria are satisfied:

        # 1. Debug files removed
        # Navigate to project root dynamically
        project_root = Path(__file__).parent.parent.parent.parent
        debug_files = [
            project_root / "debug" / "test_async_api_implementation.py",
            project_root / "debug" / "test_async_api_no_auth.py",
        ]
        for debug_file in debug_files:
            assert not os.path.exists(
                debug_file
            ), f"Debug file {debug_file} not removed"

        # 2. Deprecated options removed
        cmd = [
            "python",
            "-m",
            "code_indexer.cli",
            "query",
            "--semantic-type",
            "function",
            "test",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        assert result.returncode != 0, "Deprecated --semantic-type should not work"

        # 3. Help text cleaned up
        cmd = ["python", "-m", "code_indexer.cli", "query", "--help"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, "Query help should work"
        help_text = result.stdout.lower()
        assert (
            "--semantic-type" not in help_text
        ), "Help should not mention --semantic-type"

        # 4. Core functionality preserved
        cmd = ["python", "-m", "code_indexer.cli", "query", "--quiet", "test"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        # Should fail gracefully (no config/services) but not due to missing options
        assert (
            "No such option" not in result.stderr
            and "No such option" not in result.stdout
        ), "Should not fail due to missing options"

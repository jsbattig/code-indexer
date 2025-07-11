"""
End-to-end test for CLI progress behavior.

This test simulates the exact CLI execution path to identify where
individual progress messages are still being generated instead of
progress bar updates.
"""

import pytest

from .conftest import local_temporary_directory
from .test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)

import subprocess
import os


class TestCLIProgressE2E:
    """End-to-end tests for CLI progress behavior."""

    def setup_method(self):
        """Setup test environment using shared infrastructure."""
        # Use shared test infrastructure to avoid container conflicts
        self.temp_context = local_temporary_directory()
        self.temp_path = self.temp_context.__enter__()

        # Create test project with inventory system
        create_test_project_with_inventory(
            self.temp_path, TestProjectInventory.CLI_PROGRESS
        )

        # Create test files (small enough to process quickly)
        self.test_files = []
        for i in range(3):
            file_path = self.temp_path / f"test_file_{i}.py"
            content = f"""
def function_{i}():
    '''Function {i} with content for chunking.'''
    return "This is function {i} with content for testing."

class TestClass_{i}:
    '''Test class {i}'''
    
    def method_1(self):
        return "Method implementation"
    
    def method_2(self):
        return "Another method"
"""
            file_path.write_text(content)
            self.test_files.append(file_path)

        # Initialize and start services for this test
        self._ensure_services_ready()

    @pytest.mark.skipif(
        not os.getenv("VOYAGE_API_KEY"),
        reason="VoyageAI API key required for E2E tests",
    )
    @pytest.mark.e2e
    def test_cli_progress_output_format(self):
        """Test that CLI progress output follows the correct format."""
        # The shared test infrastructure handles service setup automatically
        # Services should be ready via the inventory system

        # Run indexing and capture output
        index_result = subprocess.run(
            ["code-indexer", "index", "--clear"],
            cwd=self.temp_path,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Check for successful completion
        assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

        # Check output format - should have progress indicators
        output_lines = index_result.stdout.split("\n")

        # Look for problematic individual file messages
        problematic_lines = []
        for line in output_lines:
            # Check for individual file processing messages that shouldn't appear
            if "ℹ️" in line and ".py" in line and "Processing" in line:
                problematic_lines.append(line)

        # Assert no problematic output
        assert len(problematic_lines) == 0, (
            f"Found {len(problematic_lines)} individual file processing messages "
            f"that should be shown in progress bar instead. Examples: {problematic_lines[:3]}"
        )

    @pytest.mark.skipif(
        not os.getenv("VOYAGE_API_KEY"),
        reason="VoyageAI API key required for E2E tests",
    )
    @pytest.mark.e2e
    def test_cli_clear_command_no_individual_messages(self):
        """Test that 'cidx index --clear' doesn't show individual file messages."""
        # The shared test infrastructure handles service setup automatically
        # Services should be ready via the inventory system

        # Run indexing with --clear and check output
        index_result = subprocess.run(
            ["code-indexer", "index", "--clear"],
            cwd=self.temp_path,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Check for successful completion
        assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

        # Analyze output for problematic patterns
        output = index_result.stdout
        lines = output.split("\n")

        # Count different types of messages
        setup_messages = []
        progress_messages = []
        individual_file_messages = []

        for line in lines:
            if "ℹ️" in line:
                if (
                    any(ext in line for ext in [".py", ".md", ".txt"])
                    and "Processing" in line
                ):
                    individual_file_messages.append(line)
                else:
                    setup_messages.append(line)
            elif "█" in line or "▌" in line:  # Progress bar characters
                progress_messages.append(line)

        # Should have setup messages and progress bar, but no individual file messages
        assert len(individual_file_messages) == 0, (
            f"Found {len(individual_file_messages)} individual file processing messages. "
            f"These should be shown in progress bar instead. Examples: {individual_file_messages[:3]}"
        )

        # Verify we processed files (should see success message)
        assert (
            "✅" in output or "complete" in output.lower()
        ), "Should show completion message"

    def _ensure_services_ready(self):
        """Ensure services are initialized and running for the test."""
        import subprocess
        import pytest

        # Initialize code-indexer
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=self.temp_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if init_result.returncode != 0:
            pytest.skip(f"Failed to initialize code-indexer: {init_result.stderr}")

        # Start services
        start_result = subprocess.run(
            ["code-indexer", "start"],
            cwd=self.temp_path,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if start_result.returncode != 0:
            # Check if services are already running
            if (
                "already in use" in start_result.stdout
                or "already running" in start_result.stdout
            ):
                # Verify services are accessible
                status_result = subprocess.run(
                    ["code-indexer", "status"],
                    cwd=self.temp_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if status_result.returncode == 0 and "✅" in status_result.stdout:
                    return  # Services are running and accessible
            pytest.skip(f"Failed to start services: {start_result.stdout}")

    def teardown_method(self):
        """Cleanup test environment."""
        # Exit the shared test infrastructure context
        if hasattr(self, "temp_context"):
            self.temp_context.__exit__(None, None, None)


if __name__ == "__main__":
    pytest.main([__file__])

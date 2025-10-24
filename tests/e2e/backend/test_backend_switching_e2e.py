"""
End-to-end tests for switching between Qdrant and filesystem vector backends.

Tests the complete workflow of switching from one backend to another including:
- Clean removal of old backend data
- Proper initialization of new backend
- Re-indexing with new backend
- Configuration updates
- No leftover artifacts
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_project():
    """Create a temporary test project with sample files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "test-project"
        project_dir.mkdir()

        # Create sample Python files for indexing
        (project_dir / "module1.py").write_text(
            """
def authenticate_user(username, password):
    '''User authentication logic.'''
    return validate_credentials(username, password)
"""
        )

        (project_dir / "module2.py").write_text(
            """
def calculate_total(items):
    '''Calculate total price of items.'''
    return sum(item.price for item in items)
"""
        )

        yield project_dir


class TestBackendSwitching:
    """Test complete backend switching workflows."""

    def test_switch_from_filesystem_to_qdrant(self, temp_project):
        """
        Test switching from filesystem backend to Qdrant backend.

        Acceptance Criteria:
        - AC1: Can switch from filesystem to Qdrant (destroy, reinit, reindex)
        - AC3: Switching preserves codebase, only changes vector storage
        - AC7: Clean removal of old backend data
        - AC8: Proper initialization of new backend
        - AC9: Configuration update to reflect new backend
        - AC10: No leftover artifacts
        """
        # Step 1: Initialize with filesystem backend
        result = subprocess.run(
            ["cidx", "init", "--vector-store", "filesystem"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Verify filesystem backend config
        config_path = temp_project / ".code-indexer" / "config.json"
        assert config_path.exists(), "Config file not created"

        with open(config_path) as f:
            config = json.load(f)
        assert (
            config.get("vector_store", {}).get("provider") == "filesystem"
        ), "Wrong backend in config"

        # Step 2: Start services and index
        result = subprocess.run(
            ["cidx", "start"], cwd=temp_project, capture_output=True, text=True
        )
        assert result.returncode == 0, f"Start failed: {result.stderr}"

        result = subprocess.run(
            ["cidx", "index"], cwd=temp_project, capture_output=True, text=True
        )
        assert result.returncode == 0, f"Index failed: {result.stderr}"

        # Verify filesystem index directory exists
        filesystem_index = temp_project / ".code-indexer" / "index"
        assert filesystem_index.exists(), "Filesystem index not created"
        assert any(
            filesystem_index.iterdir()
        ), "Filesystem index is empty after indexing"

        # Query to verify data exists
        result = subprocess.run(
            ["cidx", "query", "authenticate", "--quiet"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Query failed: {result.stderr}"
        assert "module1.py" in result.stdout, "Expected search results not found"

        # Step 3: Switch to Qdrant backend (uninstall + reinit)
        result = subprocess.run(
            ["cidx", "stop"], cwd=temp_project, capture_output=True, text=True
        )
        # stop may fail if no containers, that's OK for filesystem backend

        result = subprocess.run(
            ["cidx", "uninstall", "--confirm"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Uninstall failed: {result.stderr}"

        # Verify filesystem index is removed
        assert not filesystem_index.exists(), "Filesystem index not removed"

        # Verify codebase files still exist (AC3)
        assert (temp_project / "module1.py").exists(), "Codebase file was deleted!"
        assert (temp_project / "module2.py").exists(), "Codebase file was deleted!"

        # Step 4: Initialize with Qdrant backend
        result = subprocess.run(
            ["cidx", "init", "--vector-store", "qdrant"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Reinit with Qdrant failed: {result.stderr}"

        # Verify Qdrant backend config
        with open(config_path) as f:
            config = json.load(f)
        assert (
            config.get("vector_store", {}).get("provider") == "qdrant"
        ), "Backend not updated to Qdrant"

        # Step 5: Start services and reindex
        result = subprocess.run(
            ["cidx", "start"], cwd=temp_project, capture_output=True, text=True
        )
        assert result.returncode == 0, f"Start with Qdrant failed: {result.stderr}"

        result = subprocess.run(
            ["cidx", "index"], cwd=temp_project, capture_output=True, text=True
        )
        assert result.returncode == 0, f"Reindex with Qdrant failed: {result.stderr}"

        # Query to verify data exists in new backend
        result = subprocess.run(
            ["cidx", "query", "authenticate", "--quiet"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Query after switch failed: {result.stderr}"
        assert (
            "module1.py" in result.stdout
        ), "Expected search results not found after switch"

        # Cleanup
        subprocess.run(
            ["cidx", "stop"], cwd=temp_project, capture_output=True, text=True
        )
        subprocess.run(
            ["cidx", "uninstall", "--confirm"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )

    def test_switch_from_qdrant_to_filesystem(self, temp_project):
        """
        Test switching from Qdrant backend to filesystem backend.

        Acceptance Criteria:
        - AC2: Can switch from Qdrant to filesystem (destroy, reinit, reindex)
        - AC3: Switching preserves codebase, only changes vector storage
        - AC7: Clean removal of old backend data
        - AC8: Proper initialization of new backend
        - AC9: Configuration update to reflect new backend
        - AC10: No leftover artifacts
        """
        # Step 1: Initialize with Qdrant backend
        result = subprocess.run(
            ["cidx", "init", "--vector-store", "qdrant"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Verify Qdrant backend config
        config_path = temp_project / ".code-indexer" / "config.json"
        with open(config_path) as f:
            config = json.load(f)
        assert (
            config.get("vector_store", {}).get("provider") == "qdrant"
        ), "Wrong backend in config"

        # Step 2: Start services and index
        result = subprocess.run(
            ["cidx", "start"], cwd=temp_project, capture_output=True, text=True
        )
        assert result.returncode == 0, f"Start failed: {result.stderr}"

        result = subprocess.run(
            ["cidx", "index"], cwd=temp_project, capture_output=True, text=True
        )
        assert result.returncode == 0, f"Index failed: {result.stderr}"

        # Query to verify data exists
        result = subprocess.run(
            ["cidx", "query", "calculate", "--quiet"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Query failed: {result.stderr}"
        assert "module2.py" in result.stdout, "Expected search results not found"

        # Step 3: Switch to filesystem backend (stop + uninstall + reinit)
        result = subprocess.run(
            ["cidx", "stop"], cwd=temp_project, capture_output=True, text=True
        )
        assert result.returncode == 0, f"Stop failed: {result.stderr}"

        result = subprocess.run(
            ["cidx", "uninstall", "--confirm"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Uninstall failed: {result.stderr}"

        # Verify codebase files still exist (AC3)
        assert (temp_project / "module1.py").exists(), "Codebase file was deleted!"
        assert (temp_project / "module2.py").exists(), "Codebase file was deleted!"

        # Step 4: Initialize with filesystem backend
        result = subprocess.run(
            ["cidx", "init", "--vector-store", "filesystem"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Reinit failed: {result.stderr}"

        # Verify filesystem backend config
        with open(config_path) as f:
            config = json.load(f)
        assert (
            config.get("vector_store", {}).get("provider") == "filesystem"
        ), "Backend not updated to filesystem"

        # Step 5: Start services and reindex
        result = subprocess.run(
            ["cidx", "start"], cwd=temp_project, capture_output=True, text=True
        )
        assert result.returncode == 0, f"Start with filesystem failed: {result.stderr}"

        result = subprocess.run(
            ["cidx", "index"], cwd=temp_project, capture_output=True, text=True
        )
        assert result.returncode == 0, f"Reindex failed: {result.stderr}"

        # Verify filesystem index directory exists
        filesystem_index = temp_project / ".code-indexer" / "index"
        assert filesystem_index.exists(), "Filesystem index not created"

        # Query to verify data exists in new backend
        result = subprocess.run(
            ["cidx", "query", "calculate", "--quiet"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Query after switch failed: {result.stderr}"
        assert (
            "module2.py" in result.stdout
        ), "Expected search results not found after switch"

        # Cleanup
        subprocess.run(
            ["cidx", "stop"], cwd=temp_project, capture_output=True, text=True
        )
        subprocess.run(
            ["cidx", "uninstall", "--confirm"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )

    def test_backend_switching_preserves_git_history(self, temp_project):
        """
        Test that backend switching preserves git repository and history.

        Acceptance Criteria:
        - AC3: Switching preserves codebase, only changes vector storage
        - AC11: Git history considerations
        """
        # Initialize git repository
        subprocess.run(
            ["git", "init"], cwd=temp_project, capture_output=True, text=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "add", "."], cwd=temp_project, capture_output=True, text=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )

        # Get initial git log
        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )
        initial_log = result.stdout

        # Initialize with filesystem, index, switch to Qdrant
        subprocess.run(
            ["cidx", "init", "--vector-store", "filesystem"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["cidx", "start"], cwd=temp_project, capture_output=True, text=True
        )
        subprocess.run(
            ["cidx", "index"], cwd=temp_project, capture_output=True, text=True
        )
        subprocess.run(
            ["cidx", "stop"], cwd=temp_project, capture_output=True, text=True
        )
        subprocess.run(
            ["cidx", "uninstall", "--confirm"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )

        subprocess.run(
            ["cidx", "init", "--vector-store", "qdrant"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )

        # Verify git history is preserved
        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )
        assert result.stdout == initial_log, "Git history was modified!"

        # Verify .git directory still exists
        assert (temp_project / ".git").exists(), "Git directory was removed!"

        # Cleanup
        subprocess.run(
            ["cidx", "stop"], cwd=temp_project, capture_output=True, text=True
        )
        subprocess.run(
            ["cidx", "uninstall", "--confirm"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )

    def test_force_reinit_with_different_backend(self, temp_project):
        """
        Test using --force flag to reinitialize with different backend.

        Acceptance Criteria:
        - AC8: Proper initialization of new backend
        - AC9: Configuration update to reflect new backend
        - AC12: Explicit confirmation before destroying data (warning displayed)
        """
        # Initialize with filesystem backend
        subprocess.run(
            ["cidx", "init", "--vector-store", "filesystem"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )

        config_path = temp_project / ".code-indexer" / "config.json"
        with open(config_path) as f:
            original_config = json.load(f)
        assert original_config.get("vector_store", {}).get("provider") == "filesystem"

        # Use --force to attempt reinitialize with Qdrant
        # This will show the safety warning (AC12) and prompt for confirmation
        result = subprocess.run(
            ["cidx", "init", "--vector-store", "qdrant", "--force"],
            cwd=temp_project,
            capture_output=True,
            text=True,
            input="n\n",  # Decline the prompt to test safety warning
        )

        # Verify the safety warning was displayed (AC12)
        assert (
            "Backend switch detected" in result.stdout
        ), "Safety warning not displayed"
        assert (
            "Removing existing vector index data" in result.stdout
        ), "Warning details missing"
        assert (
            "Proceed with backend switch" in result.stdout
        ), "Confirmation prompt not shown"

        # Since we declined, config should NOT be updated
        with open(config_path) as f:
            unchanged_config = json.load(f)
        assert (
            unchanged_config.get("vector_store", {}).get("provider") == "filesystem"
        ), "Config was changed despite declining confirmation"

        # Now test accepting the confirmation
        result = subprocess.run(
            ["cidx", "init", "--vector-store", "qdrant", "--force"],
            cwd=temp_project,
            capture_output=True,
            text=True,
            input="y\n",  # Accept the prompt
        )
        assert result.returncode == 0, f"Force reinit failed: {result.stderr}"

        # Verify configuration was updated after accepting
        with open(config_path) as f:
            new_config = json.load(f)
        assert (
            new_config.get("vector_store", {}).get("provider") == "qdrant"
        ), "Config not updated after accepting"

        # Cleanup
        subprocess.run(
            ["cidx", "uninstall", "--confirm"],
            cwd=temp_project,
            capture_output=True,
            text=True,
        )
